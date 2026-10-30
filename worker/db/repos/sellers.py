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

Who writes it, and which count wins: in step 1 only the startup, nightly and
CLI runs (pipeline/seller_classification.py) write counts, over every group.
When step 2 also counts the groups an ingest touched, that count can differ
from the nightly one, because news.classify may set probable_repost_of after
the ingest commit (NEWS_LINK_REPOST); the next full run is authoritative and
overwrites it. Nothing reads the count in step 1, so there is nothing to flap.
"""
from __future__ import annotations

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

_TARGET = """,
target AS (
  SELECT l.id, g.n
    FROM listings l LEFT JOIN grp g ON g.seller_key = l.seller_key
   WHERE l.source = %(source)s AND l.status = 'active' AND l.seller_key = ANY(%(keys)s)
     AND l.seller_listing_count IS DISTINCT FROM g.n
   ORDER BY l.id {lock})
"""

_WRITE = (_GROUPS.format(keys="l.seller_key = ANY(%(keys)s)") + _TARGET.format(lock="FOR UPDATE OF l")
          + "UPDATE listings SET seller_listing_count = t.n FROM target t WHERE listings.id = t.id")
_WOULD_WRITE = (_GROUPS.format(keys="l.seller_key = ANY(%(keys)s)") + _TARGET.format(lock="")
                + "SELECT count(*)::int AS n FROM target")

_REPORT = _GROUPS.format(keys="l.seller_key IS NOT NULL") + """
SELECT l.seller_key, g.n, count(*)::int AS active,
       (array_agg(DISTINCT l.seller_name ORDER BY l.seller_name))[1:5] AS names
  FROM listings l LEFT JOIN grp g ON g.seller_key = l.seller_key
 WHERE l.source = %(source)s AND l.status = 'active' AND l.seller_key IS NOT NULL
 GROUP BY l.seller_key, g.n
"""

_STALE = """
SELECT id FROM listings
 WHERE source = %(source)s AND status = 'active' AND seller_key IS NULL AND seller_listing_count IS NOT NULL
 ORDER BY id
"""


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
                       dry_run: bool = False) -> int:
    """Write the count of these groups on their active rows; only the rows
    whose value changes, locked in id order. Returns the rows written (or that
    would be, with dry_run)."""
    if not keys:
        return 0
    params = {"source": source, "keys": list(keys), "window": int(cfg["window_days"])}
    if dry_run:
        return (await (await cx.execute(_WOULD_WRITE, params)).fetchone())["n"]
    return (await cx.execute(_WRITE, params)).rowcount


async def clear_stale(cx: AsyncConnection, source: str, *, dry_run: bool = False) -> int:
    """Active rows that lost their key keep no count. (A group with nothing in
    the window gets null from write_groups.)"""
    if dry_run:
        return len(await (await cx.execute(_STALE, {"source": source})).fetchall())
    return (await cx.execute(
        f"UPDATE listings SET seller_listing_count = NULL WHERE id IN ({_STALE} FOR UPDATE)",
        {"source": source})).rowcount


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
                     rows_written: int | None = None, error: str | None = None) -> None:
    await cx.execute(
        "UPDATE seller_classification_runs SET status = %s, finished_at = now(), rows_read = %s, "
        "  rows_written = %s, error = %s WHERE id = %s",
        (status, rows_read, rows_written, error, run_id))
