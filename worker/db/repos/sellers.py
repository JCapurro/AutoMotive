"""listings.seller_key / seller_listing_count and seller_classification_runs
(F-02, docs/superpowers/specs/2026-10-30-f02-vendedor-design.md, decisions 3, 4
and 8). Callers own the transaction: one per batch.

The count of a group (source, seller_key) is how many distinct cars
(`coalesce(fingerprint, id)`) it has active and published in the window
(`coalesce(published_at, first_seen_at)` in the last window_days days). It is
written on every active row of the group, also the ones published before the
window; a group with nothing in the window gets null. A probable repost is left
out only while its original is itself counted in the same group (active, same
key, in the window): it never takes away the only live copy of a car.

Step 2: the same statement writes listings.dealer_inferred («posible
agencia»): `enabled and count >= min_listings and seller_type is distinct from
'dealer'` (app_config.seller_classification). It also applies when the source
says 'private' (Juan, 30/10/2026) and never marks a listing the source already
calls a dealer. A row whose group falls out of the window or that lost its key
goes back to null / false. Gone listings keep their last values, except that
with enabled = false every row goes to false (clear_inferred), so the
comparables pool forgets the inference too.

Who writes it, and which count wins: the startup, nightly and CLI runs
(pipeline/seller_classification.py) over every group, and the ingest over the
groups it touched (pipeline/ingest.py, before scoring). The ingest count can
differ from the nightly one, because news.classify may set probable_repost_of
after the ingest commit (NEWS_LINK_REPOST); the next full run is authoritative
and overwrites it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from normalization.seller import seller_key

GROUP_BATCH = 2_000
KEY_BATCH = 1_000

_IN_WINDOW = "coalesce({t}.published_at, {t}.first_seen_at) >= now() - make_interval(days => %(window)s)"

_GROUPS = f"""
WITH grp AS (
  SELECT l.seller_key, count(DISTINCT coalesce(l.fingerprint, l.id::text))::int AS n
    FROM listings l
   WHERE l.source = %(source)s AND l.status = 'active' AND {{keys}}
     AND {_IN_WINDOW.format(t="l")}
     AND NOT EXISTS (
       SELECT 1 FROM listings o
        WHERE o.id = l.probable_repost_of AND o.source = l.source AND o.seller_key = l.seller_key
          AND o.status = 'active' AND {_IN_WINDOW.format(t="o")})
   GROUP BY l.seller_key)
"""

# The rule (design, decision 5). `g.n` is null for a group with nothing in the window.
_INFERRED = ("(%(enabled)s AND coalesce(g.n >= %(min_listings)s, false) "
             "AND l.seller_type IS DISTINCT FROM 'dealer')")

_TARGET = f""",
target AS (
  SELECT l.id, g.n, {_INFERRED} AS inferred, l.dealer_inferred AS was, l.seller_listing_count AS was_n
    FROM listings l LEFT JOIN grp g ON g.seller_key = l.seller_key
   WHERE l.source = %(source)s AND l.status = 'active' AND l.seller_key = ANY(%(keys)s)
     AND (l.seller_listing_count, l.dealer_inferred) IS DISTINCT FROM (g.n, {_INFERRED})
   ORDER BY l.id {{lock}})
"""

# flipped: dealer_inferred changed. recount: still inferred with another count;
# the match reason carries N («publica N autos»), so it is re-scored too.
_CHANGES = ("t.was IS DISTINCT FROM t.inferred AS flipped, "
            "(t.was AND t.inferred AND t.was_n IS DISTINCT FROM t.n) AS recount")

_WRITE = (_GROUPS.format(keys="l.seller_key = ANY(%(keys)s)") + _TARGET.format(lock="FOR UPDATE OF l")
          + "UPDATE listings SET seller_listing_count = t.n, dealer_inferred = t.inferred FROM target t "
            f"WHERE listings.id = t.id RETURNING listings.id, {_CHANGES}")
_WOULD_WRITE = (_GROUPS.format(keys="l.seller_key = ANY(%(keys)s)") + _TARGET.format(lock="")
                + f"SELECT t.id, {_CHANGES} FROM target t")

_REPORT = _GROUPS.format(keys="l.seller_key IS NOT NULL") + """
SELECT l.seller_key, g.n, count(*)::int AS active,
       (array_agg(DISTINCT l.seller_name ORDER BY l.seller_name))[1:5] AS names
  FROM listings l LEFT JOIN grp g ON g.seller_key = l.seller_key
 WHERE l.source = %(source)s AND l.status = 'active' AND l.seller_key IS NOT NULL
 GROUP BY l.seller_key, g.n
"""

_STALE = """
SELECT id, dealer_inferred AS was FROM listings
 WHERE source = %(source)s AND status = 'active' AND seller_key IS NULL
   AND (seller_listing_count IS NOT NULL OR dealer_inferred)
 ORDER BY id
"""


@dataclass
class Written:
    """Rows a write changed (or would, in a dry run); among them, the ids
    whose dealer_inferred flipped, and the ids still inferred whose count
    changed. The matches of both are re-scored (`rescore`)."""
    rows: int = 0
    flipped: list[int] = field(default_factory=list)
    recounted: list[int] = field(default_factory=list)

    def add(self, other: "Written") -> "Written":
        self.rows += other.rows
        self.flipped += other.flipped
        self.recounted += other.recounted
        return self

    @property
    def rescore(self) -> list[int]:
        return self.flipped + self.recounted


def _written(rows: list[dict[str, Any]]) -> Written:
    return Written(len(rows), [r["id"] for r in rows if r["flipped"]],
                   [r["id"] for r in rows if r.get("recount")])


async def sources(cx: AsyncConnection) -> list[str]:
    """The sources with active listings."""
    rows = await (await cx.execute(
        "SELECT DISTINCT source FROM listings WHERE status = 'active' ORDER BY source")).fetchall()
    return [r["source"] for r in rows]


async def active_count(cx: AsyncConnection, source: str) -> int:
    row = await (await cx.execute(
        "SELECT count(*)::int AS n FROM listings WHERE source = %s AND status = 'active'", (source,))).fetchone()
    return row["n"]


async def group_keys(cx: AsyncConnection, source: str) -> list[str]:
    """Every seller key with an active listing in the source, in order (index only)."""
    rows = await (await cx.execute(
        "SELECT DISTINCT seller_key FROM listings "
        " WHERE source = %s AND status = 'active' AND seller_key IS NOT NULL ORDER BY seller_key",
        (source,))).fetchall()
    return [r["seller_key"] for r in rows]


async def write_groups(cx: AsyncConnection, source: str, keys: Sequence[str], cfg: dict[str, Any], *,
                       dry_run: bool = False) -> Written:
    """Write the count and dealer_inferred of these groups on their active
    rows; only the rows whose values change, locked in id order."""
    if not keys:
        return Written()
    params = {"source": source, "keys": list(keys), "window": int(cfg["window_days"]),
              "enabled": bool(cfg["enabled"]), "min_listings": int(cfg["min_listings"])}
    return _written(await (await cx.execute(_WOULD_WRITE if dry_run else _WRITE, params)).fetchall())


async def clear_stale(cx: AsyncConnection, source: str, *, dry_run: bool = False) -> Written:
    """Active rows that lost their key keep no count and no inference. (A
    group with nothing in the window gets null / false from write_groups.)"""
    if dry_run:
        rows = await (await cx.execute(_STALE, {"source": source})).fetchall()
        return Written(len(rows), [r["id"] for r in rows if r["was"]])
    return _written(await (await cx.execute(
        f"WITH stale AS ({_STALE} FOR UPDATE) "
        "UPDATE listings l SET seller_listing_count = NULL, dealer_inferred = false FROM stale s "
        " WHERE l.id = s.id RETURNING l.id, s.was AS flipped",
        {"source": source})).fetchall())


async def clear_listings(cx: AsyncConnection, ids: Sequence[int]) -> Written:
    """These listings, if they have no key now, keep no count and no inference
    (the ingest, for a listing whose name became generic or empty)."""
    if not ids:
        return Written()
    return _written(await (await cx.execute(
        "WITH stale AS (SELECT id, dealer_inferred AS was FROM listings "
        "                WHERE id = ANY(%s) AND seller_key IS NULL "
        "                  AND (seller_listing_count IS NOT NULL OR dealer_inferred) ORDER BY id FOR UPDATE) "
        "UPDATE listings l SET seller_listing_count = NULL, dealer_inferred = false FROM stale s "
        " WHERE l.id = s.id RETURNING l.id, s.was AS flipped", (list(ids),))).fetchall())


async def clear_inferred(cx: AsyncConnection, *, limit: int = KEY_BATCH, dry_run: bool = False) -> Written:
    """enabled = false: one batch of listings (active or gone) still marked,
    by id, back to false. Call until it writes nothing. The dry run counts
    only the rows that are not active: write_groups and clear_stale already
    counted the active ones, which the real run writes once, not twice."""
    select = "SELECT id FROM listings WHERE dealer_inferred ORDER BY id"
    if dry_run:
        rows = await (await cx.execute(
            "SELECT id FROM listings WHERE dealer_inferred AND status <> 'active' ORDER BY id")).fetchall()
        return Written(len(rows), [r["id"] for r in rows])
    rows = await (await cx.execute(
        f"UPDATE listings SET dealer_inferred = false WHERE id IN ({select} LIMIT %s FOR UPDATE) RETURNING id",
        (limit,))).fetchall()
    return Written(len(rows), [r["id"] for r in rows])


async def report_groups(cx: AsyncConnection, source: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Per group of the source: key, count (null: nothing in the window),
    active rows and up to 5 raw names. For the CLI's report."""
    return await (await cx.execute(
        _REPORT, {"source": source, "window": int(cfg["window_days"])})).fetchall()


async def _set_keys(cx: AsyncConnection, rows: list[dict[str, Any]]) -> int:
    changed = [(r["id"], k) for r in rows if (k := seller_key(r["seller_name"])) != r["seller_key"]]
    if not changed:
        return 0
    return (await cx.execute(
        "UPDATE listings l SET seller_key = v.k "
        "  FROM unnest(%s::bigint[], %s::text[]) AS v(id, k) "
        " WHERE l.id = v.id AND l.seller_key IS DISTINCT FROM v.k",
        ([i for i, _ in changed], [k for _, k in changed]))).rowcount


async def backfill_keys(cx: AsyncConnection, after_id: int, *, limit: int = KEY_BATCH,
                        missing_only: bool = False) -> tuple[int | None, int]:
    """One batch of seller_key recomputed from seller_name, by id after
    `after_id`: every listing (also gone), or with missing_only the active ones
    that have a name and no key. Returns the last id read (None: no more rows)
    and the rows written."""
    where = "AND status = 'active' AND seller_key IS NULL AND seller_name IS NOT NULL" if missing_only else ""
    rows = await (await cx.execute(
        f"SELECT id, seller_name, seller_key FROM listings WHERE id > %s {where} ORDER BY id LIMIT %s",
        (after_id, limit))).fetchall()
    if not rows:
        return None, 0
    return rows[-1]["id"], await _set_keys(cx, rows)


async def start_run(cx: AsyncConnection, trigger: str, mode: str, params: dict[str, Any]) -> int:
    row = await (await cx.execute(
        "INSERT INTO seller_classification_runs (trigger, mode, params) VALUES (%s, %s, %s) RETURNING id",
        (trigger, mode, Jsonb(params)))).fetchone()
    return row["id"]


async def finish_run(cx: AsyncConnection, run_id: int, *, status: str, rows_read: int | None = None,
                     rows_written: int | None = None, inferred_changed: int | None = None,
                     error: str | None = None) -> None:
    await cx.execute(
        "UPDATE seller_classification_runs SET status = %s, finished_at = now(), rows_read = %s, "
        "  rows_written = %s, inferred_changed = %s, error = %s WHERE id = %s",
        (status, rows_read, rows_written, inferred_changed, error, run_id))
