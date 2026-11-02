"""listing_duplicates and photo_hash_runs (PAR-02 resto,
docs/superpowers/specs/2026-11-02-par02-resto-design.md, decisions 2, 5 and 7).
Callers own the transaction, except where a function opens its own.

A group is (lower(make), lower(model)). Its stored pairs are the ones whose
listing_id has that make and model, whatever its status: a gone listing's
pairs are rewritten (deleted) with its group.
"""
from __future__ import annotations

from typing import Any, Iterable

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from db.pool import connection
from db.repos.profiles import LIVE_SEARCHES

Group = tuple[str, str]

# A group is worth comparing with 2+ sources or any photo hash in it.
_GROUPS = """
SELECT lower(make) AS make, lower(model) AS model
  FROM listings
 WHERE status = 'active' AND make IS NOT NULL AND model IS NOT NULL {only}
 GROUP BY 1, 2
HAVING count(*) >= 2 AND (count(DISTINCT source) >= 2 OR bool_or(attributes ? '_photo_hashes'))
 ORDER BY 1, 2
"""


async def groups(cx: AsyncConnection, only: Group | None = None) -> list[Group]:
    sql = _GROUPS.format(only="AND lower(make) = %s AND lower(model) = %s" if only else "")
    rows = await (await cx.execute(sql, [only[0].lower(), only[1].lower()] if only else [])).fetchall()
    return [(r["make"], r["model"]) for r in rows]


async def groups_of(cx: AsyncConnection, listing_ids: Iterable[int]) -> list[Group]:
    rows = await (await cx.execute(
        "SELECT DISTINCT lower(make) AS make, lower(model) AS model FROM listings "
        " WHERE id = ANY(%s) AND make IS NOT NULL AND model IS NOT NULL ORDER BY 1, 2",
        (list(listing_ids),))).fetchall()
    return [(r["make"], r["model"]) for r in rows]


async def lock_group(cx: AsyncConnection, group: Group) -> None:
    """One writer per group at a time (the nightly run and an ingest)."""
    await cx.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 7060141300))", (f"{group[0]}/{group[1]}",))


async def group_rows(cx: AsyncConnection, group: Group) -> list[dict[str, Any]]:
    """The active listings of a group as intelligence/duplicates.py reads them."""
    rows = await (await cx.execute(
        "SELECT l.id, l.source, l.year, l.mileage_km, l.price_usd::float AS price_usd, l.price_partial, "
        "       l.probable_repost_of, l.trim, l.transmission, l.fuel, l.seller_type, l.dealer_inferred, "
        "       l.seller_key, l.attributes -> '_photo_hashes' -> 'hashes' AS hashes, "
        "       CASE WHEN z.listing_id IS NULL THEN NULL ELSE jsonb_build_object("
        "         'province_id', z.province_id, 'department', z.department, 'precision', z.precision, "
        "         'lat', z.lat, 'lon', z.lon) END AS zone "
        "  FROM listings l LEFT JOIN listing_zones z ON z.listing_id = l.id "
        " WHERE l.status = 'active' AND lower(l.make) = %s AND lower(l.model) = %s",
        group)).fetchall()
    for r in rows:
        r["hashes"] = [h for h in (r["hashes"] or []) if isinstance(h, str)] if isinstance(r["hashes"], list) else []
    return rows


async def stored(cx: AsyncConnection, group: Group) -> dict[tuple[int, int], dict[str, Any]]:
    rows = await (await cx.execute(
        "SELECT d.listing_id, d.other_id, d.kind, d.shown, d.photo_distance, d.evidence "
        "  FROM listing_duplicates d JOIN listings l ON l.id = d.listing_id "
        " WHERE lower(l.make) = %s AND lower(l.model) = %s", group)).fetchall()
    return {(r["listing_id"], r["other_id"]): r for r in rows}


async def stored_elsewhere(cx: AsyncConnection, groups_seen: list[Group]) -> dict[tuple[int, int], dict[str, Any]]:
    """Pairs whose listing is in no group of this full run (its make or model
    changed, or the group fell under two sources): the run deletes them."""
    rows = await (await cx.execute(
        "SELECT d.listing_id, d.other_id, d.kind, d.shown FROM listing_duplicates d "
        "  JOIN listings l ON l.id = d.listing_id "
        " WHERE (lower(l.make), lower(l.model)) NOT IN (SELECT * FROM unnest(%s::text[], %s::text[])) "
        "    OR l.make IS NULL OR l.model IS NULL",
        ([g[0] for g in groups_seen], [g[1] for g in groups_seen]))).fetchall()
    return {(r["listing_id"], r["other_id"]): r for r in rows}


async def write(cx: AsyncConnection, deletes: Iterable[tuple[int, int]], upserts: Iterable[dict[str, Any]]) -> None:
    deletes = list(deletes)
    if deletes:
        await cx.execute(
            "DELETE FROM listing_duplicates WHERE (listing_id, other_id) IN "
            "(SELECT * FROM unnest(%s::bigint[], %s::bigint[]))",
            ([d[0] for d in deletes], [d[1] for d in deletes]))
    rows = list(upserts)
    if rows:
        async with cx.cursor() as cur:
            await cur.executemany(
                "INSERT INTO listing_duplicates (listing_id, other_id, kind, shown, photo_distance, evidence) "
                "VALUES (%(listing_id)s, %(other_id)s, %(kind)s, %(shown)s, %(photo_distance)s, %(evidence)s) "
                "ON CONFLICT (listing_id, other_id) DO UPDATE SET kind = excluded.kind, shown = excluded.shown, "
                "  photo_distance = excluded.photo_distance, evidence = excluded.evidence, "
                "  detected_at = CASE WHEN (listing_duplicates.kind, listing_duplicates.shown) "
                "                     IS DISTINCT FROM (excluded.kind, excluded.shown) "
                "                     THEN now() ELSE listing_duplicates.detected_at END",
                [{**r, "evidence": Jsonb(r["evidence"])} for r in rows])


async def describe(cx: AsyncConnection, ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """What --report prints of a listing."""
    rows = await (await cx.execute(
        "SELECT id, source, url, year, mileage_km, price_usd::float AS price_usd, seller_name "
        "  FROM listings WHERE id = ANY(%s)", (list(ids),))).fetchall()
    return {r["id"]: r for r in rows}


# ---------------------------------------------------------------------------
# Photo hash (decision 5)
# ---------------------------------------------------------------------------

# How many other listings of the same model each queued listing pulls in for
# duplicate_photos (copied photos come with another price or year, outside the
# data tolerances): the closest by year and km, another source first.
PHOTO_CANDIDATES = 10

# Whether a listing's stored _photo_hashes (alias ph) still needs work: none,
# another version, its images changed since (src = md5 of listings.images,
# written by save_photo_hashes and mark_photo_hashes_seen), or some photo
# failed with attempts left. CASE keeps the jsonb functions off non-arrays.
_NEEDS_HASH = """
  (ph IS NULL OR jsonb_typeof(ph) <> 'object'
   OR ph ->> 'v' IS DISTINCT FROM %(version)s
   OR ph ->> 'src' IS DISTINCT FROM md5(l.images::text)
   OR CASE WHEN jsonb_typeof(ph -> 'urls') <> 'array' THEN true
           WHEN jsonb_array_length(ph -> 'urls') = 0 THEN false
           WHEN CASE WHEN jsonb_typeof(ph -> 'attempts') = 'number' THEN (ph ->> 'attempts')::numeric
                     ELSE 0 END >= %(max_attempts)s THEN false
           WHEN coalesce(jsonb_typeof(ph -> 'hashes'), '') <> 'array' THEN true
           WHEN jsonb_array_length(ph -> 'hashes') <> jsonb_array_length(ph -> 'urls') THEN true
           ELSE EXISTS (SELECT 1 FROM jsonb_array_elements(ph -> 'hashes') e WHERE jsonb_typeof(e) <> 'string')
      END)
"""


async def photo_hash_queue(*, limit: int, skip_sources: list[str], max_age_days: int = 30,
                           km_tol_pct: float, price_tol_pct: float, version: int,
                           max_attempts: int) -> list[dict[str, Any]]:
    """Active listings with images whose photos still need a hash (_NEEDS_HASH,
    in SQL so that finished ones never fill the page): the ones with a live
    match or a partial price, then their data candidates in another source
    (same make, model and year, km and price in tolerance), then up to
    PHOTO_CANDIDATES other listings of their model each: without the other side
    hashed there is no pair. Newest first within each tier.
    pipeline/photo_hash.needs_hash has the final word."""
    async with connection() as cx:
        return await (await cx.execute(
            LIVE_SEARCHES + """,
            base AS (
              SELECT l.id, l.source, lower(l.make) AS make, lower(l.model) AS model, l.year, l.mileage_km,
                     l.price_usd
                FROM listings l
               WHERE l.status = 'active' AND jsonb_array_length(l.images) > 0
                 AND l.last_seen_at >= now() - make_interval(days => %(days)s)
                 AND NOT (l.source = ANY(%(skip)s))
                 AND (l.price_partial OR EXISTS (
                       SELECT 1 FROM matches m JOIN live ON live.id = m.search_profile_id WHERE m.listing_id = l.id))),
            cand AS (
              SELECT o.id FROM base b JOIN listings o
                ON lower(o.make) = b.make AND lower(o.model) = b.model AND o.year = b.year
               AND o.source <> b.source AND o.status = 'active' AND jsonb_array_length(o.images) > 0
               AND NOT (o.source = ANY(%(skip)s))
               AND o.mileage_km IS NOT NULL AND b.mileage_km IS NOT NULL
               AND abs(o.mileage_km - b.mileage_km) <= %(km)s / 100.0 * greatest(o.mileage_km, b.mileage_km)
               AND o.price_usd > 0 AND b.price_usd > 0
               AND abs(o.price_usd - b.price_usd) <= %(price)s / 100.0 * greatest(o.price_usd, b.price_usd)),
            photo_cand AS (
              SELECT c.id FROM base b CROSS JOIN LATERAL (
                SELECT o.id FROM listings o
                 WHERE lower(o.make) = b.make AND lower(o.model) = b.model AND o.id <> b.id
                   AND o.status = 'active' AND jsonb_array_length(o.images) > 0
                   AND o.last_seen_at >= now() - make_interval(days => %(days)s)
                   AND NOT (o.source = ANY(%(skip)s))
                   AND (o.year IS NULL OR b.year IS NULL OR abs(o.year - b.year) <= 1)
                 ORDER BY (o.source = b.source), abs(coalesce(o.year, b.year, 0) - coalesce(b.year, 0)),
                          abs(coalesce(o.mileage_km, 0) - coalesce(b.mileage_km, 0)), o.id
                 LIMIT %(per)s) c),
            tiers AS (
              SELECT id, min(tier) AS tier FROM (
                SELECT id, 0 AS tier FROM base UNION ALL SELECT id, 1 FROM cand
                UNION ALL SELECT id, 2 FROM photo_cand) t GROUP BY id)
            SELECT l.id, l.source, l.images, l.attributes -> '_photo_hashes' AS photo_hashes
              FROM listings l JOIN tiers t ON t.id = l.id
             CROSS JOIN LATERAL (SELECT l.attributes -> '_photo_hashes' AS ph) x
             WHERE """ + _NEEDS_HASH + """
             ORDER BY t.tier, l.first_seen_at DESC, l.id
             LIMIT %(limit)s
            """,
            {"days": max_age_days, "skip": list(skip_sources), "km": km_tol_pct, "price": price_tol_pct,
             "limit": limit, "per": PHOTO_CANDIDATES, "version": str(version),
             "max_attempts": max_attempts})).fetchall()


async def reserve_photo_run(listing_id: int, images: int, daily_cap: int) -> int | None:
    """Atomic rolling-24h image budget (the description_llm_runs pattern): the
    reservation counts even if the download fails or the process dies."""
    if daily_cap <= 0 or images <= 0:
        return None
    async with connection() as cx:
        async with cx.transaction():
            await cx.execute("SELECT pg_advisory_xact_lock(7060141301)")
            used = await (await cx.execute(
                "SELECT coalesce(sum(images_requested), 0)::int AS n FROM photo_hash_runs "
                " WHERE started_at > now() - interval '1 day'")).fetchone()
            if int(used["n"]) + images > daily_cap:
                return None
            run = await (await cx.execute(
                "INSERT INTO photo_hash_runs (listing_id, images_requested) VALUES (%s, %s) RETURNING id",
                (listing_id, images))).fetchone()
            return int(run["id"])


async def finish_photo_run(run_id: int, *, hashed: int, error: str | None) -> None:
    async with connection() as cx:
        await cx.execute("UPDATE photo_hash_runs SET finished_at = now(), images_hashed = %s, error = %s "
                         " WHERE id = %s", (hashed, error, run_id))


async def save_photo_hashes(listing_id: int, value: dict[str, Any]) -> None:
    """attributes._photo_hashes, with src = md5 of the images it was computed
    from (photo_hash_queue skips it until they change); not a key attribute,
    so no listing_updated."""
    async with connection() as cx:
        await cx.execute("UPDATE listings SET attributes = attributes || jsonb_build_object('_photo_hashes', "
                         "  %s::jsonb || jsonb_build_object('src', md5(images::text))) WHERE id = %s",
                         (Jsonb(value), listing_id))


async def mark_photo_hashes_seen(listing_id: int, value: dict[str, Any]) -> None:
    """A queued listing that needs no download (its hashes are done or out of
    attempts, or it has no photo that may be downloaded): store `value` with
    the current src so the queue stops returning it."""
    await save_photo_hashes(listing_id, value)
