"""listings + listing_snapshots: SQL for the canonical upsert (sección 5.3).

The change detection itself is pure Python (pipeline/ingest.py); this module
only reads, locks and writes rows. Callers own the transaction.
"""
from __future__ import annotations

from typing import Any, Iterable

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from db.pool import connection


Key = tuple[str, str]

# Columns the pipeline writes; id, first_seen_at, last_seen_at and status are managed here.
COLUMNS = ("source", "external_id", "url", "title", "description", "make", "model", "trim",
           "year", "price", "currency", "price_usd", "mileage_km", "transmission", "fuel",
           "location_text", "lat", "lon", "seller_name", "seller_type", "images", "attributes",
           "published_at", "price_partial", "price_partial_reason", "normalization_confidence",
           "fingerprint", "probable_repost_of", "price_published", "price_published_currency",
           "price_source", "description_facts")
_JSON = {"images", "attributes", "description_facts"}
_NUMERIC = ("price", "price_usd", "price_published")


def _param(column: str, value: Any) -> Any:
    return Jsonb(value) if column in _JSON else value


def _pythonic(row: dict[str, Any]) -> dict[str, Any]:
    """numeric columns come back as Decimal; the pipeline compares floats."""
    for c in _NUMERIC:
        if row.get(c) is not None:
            row[c] = float(row[c])
    return row


async def lock_existing(cx: AsyncConnection, keys: list[Key]) -> dict[Key, dict[str, Any]]:
    """Current rows for these (source, external_id), locked until the transaction ends."""
    if not keys:
        return {}
    rows = await (await cx.execute(
        "SELECT * FROM listings "
        " WHERE (source, external_id) IN (SELECT * FROM unnest(%s::text[], %s::text[])) "
        " ORDER BY id FOR UPDATE",
        ([k[0] for k in keys], [k[1] for k in keys]))).fetchall()
    return {(r["source"], r["external_id"]): _pythonic(r) for r in rows}


async def insert_listing(cx: AsyncConnection, row: dict[str, Any], *,
                         detail: bool = False) -> dict[str, Any] | None:
    """Insert a new listing. Returns the stored row, or None if another
    transaction inserted the same (source, external_id) first."""
    cols = [c for c in COLUMNS if c in row]
    stamps = ", enriched_at, detail_checked_at" if detail else ""
    stamp_values = ", now(), now()" if detail else ""
    stored = await (await cx.execute(
        f"INSERT INTO listings ({', '.join(cols)}{stamps}) "
        f"VALUES ({', '.join(['%s'] * len(cols))}{stamp_values}) "
        "ON CONFLICT (source, external_id) DO NOTHING RETURNING *",
        [_param(c, row[c]) for c in cols])).fetchone()
    return _pythonic(stored) if stored else None


async def update_listing(cx: AsyncConnection, listing_id: int, values: dict[str, Any], *,
                         detail: bool = False, seen: bool = True) -> None:
    """Write merged values and mark the listing seen (and active) now.
    `seen=False` (tools/reprocess.py): a stored page read again is no sighting."""
    cols = [c for c in COLUMNS if c in values and c not in ("source", "external_id")]
    sets = [f"{c} = %s" for c in cols]
    if seen:
        sets += ["last_seen_at = now()", "status = 'active'"]
    if detail and seen:
        sets += ["enriched_at = coalesce(enriched_at, now())", "detail_checked_at = now()"]
    await cx.execute(f"UPDATE listings SET {', '.join(sets)} WHERE id = %s",
                     [*(_param(c, values[c]) for c in cols), listing_id])


async def insert_snapshot(cx: AsyncConnection, listing_id: int, row: dict[str, Any],
                          change_kind: str, attrs_hash: str) -> int:
    fx_rate = None
    if row.get("currency") == "ARS" and row.get("price") and row.get("price_usd"):
        # The rate that produced the frozen price_usd.
        fx_rate = round(row["price"] / row["price_usd"], 4)
    snap = await (await cx.execute(
        "INSERT INTO listing_snapshots (listing_id, price, currency, price_usd, fx_rate, "
        "  mileage_km, attrs_hash, change_kind) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (listing_id, row.get("price"), row.get("currency"), row.get("price_usd"), fx_rate,
         row.get("mileage_km"), attrs_hash, change_kind))).fetchone()
    return snap["id"]


async def find_repost_of(cx: AsyncConnection, *, listing_id: int, fingerprint: str | None,
                         price_usd: float | None, window_days: int,
                         price_tol_pct: float) -> int | None:
    """The original listing this one probably re-publishes (sección 5.4): the
    same fingerprint first seen within `window_days`, priced within
    `price_tol_pct`. Chains collapse onto the first one."""
    if not fingerprint or not price_usd:
        return None
    row = await (await cx.execute(
        "SELECT coalesce(probable_repost_of, id) AS original FROM listings "
        " WHERE fingerprint = %s AND id <> %s "
        "   AND first_seen_at >= now() - make_interval(days => %s) "
        "   AND price_usd > 0 AND abs(price_usd - %s) / price_usd * 100 < %s "
        " ORDER BY first_seen_at, id LIMIT 1",
        (fingerprint, listing_id, window_days, price_usd, price_tol_pct))).fetchone()
    return row["original"] if row else None


async def set_repost_of(cx: AsyncConnection, listing_id: int, original_id: int) -> None:
    await cx.execute("UPDATE listings SET probable_repost_of = %s WHERE id = %s",
                     (original_id, listing_id))


async def mark_gone(cx: AsyncConnection, listing_id: int) -> bool:
    """status = 'gone'. True if it was active (so the caller emits listing_gone once)."""
    cur = await cx.execute(
        "UPDATE listings SET status = 'gone', detail_checked_at = now() "
        " WHERE id = %s AND status = 'active'", (listing_id,))
    return cur.rowcount > 0


async def stored_description(listing_id: int) -> dict[str, Any] | None:
    """The description and its facts as stored, to reuse the LLM's reading of the same text."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT description, description_facts FROM listings WHERE id = %s",
            (listing_id,))).fetchone()


async def llm_facts_last_day() -> int:
    """Descriptions the LLM read in the last 24 h (app_config.description_facts.llm_daily_cap)."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT count(*) AS n FROM listings "
            " WHERE description_facts ->> 'source' = 'llm' "
            "   AND (description_facts ->> 'llm_at')::timestamptz > now() - interval '1 day'")).fetchone()
    return int(row["n"])


async def mark_detail_checked(listing_ids: Iterable[int]) -> None:
    ids = list(listing_ids)
    if ids:
        async with connection() as cx:
            await cx.execute("UPDATE listings SET detail_checked_at = now() WHERE id = ANY(%s)", (ids,))


async def rows_for_scoring(cx: AsyncConnection, ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Listings by id as intelligence/ reads them, with the catalog's
    timing_belt for their model (red flag no_timing_belt, sección 6.5)."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    rows = await (await cx.execute(
        "SELECT l.*, vc.timing_belt FROM listings l "
        "  LEFT JOIN vehicle_catalog vc ON lower(vc.make) = lower(l.make) "
        "        AND lower(vc.model) = lower(l.model) AND vc.trim IS NULL "
        " WHERE l.id = ANY(%s)", (ids,))).fetchall()
    return {r["id"]: _pythonic(r) for r in rows}


async def recent_active(make: str | None, model: str | None, *, days: int,
                        sources: list[str] | None = None) -> list[dict]:
    """Active listings of a make/model seen in the last `days` (rematch, sección 5.7)."""
    sql = ("SELECT * FROM listings WHERE status = 'active' "
           "   AND last_seen_at >= now() - make_interval(days => %s) "
           "   AND lower(make) IS NOT DISTINCT FROM lower(%s)")
    params: list[Any] = [days, make]
    if model:
        sql += " AND lower(model) = lower(%s)"
        params.append(model)
    if sources:
        sql += " AND source = ANY(%s)"
        params.append(sources)
    async with connection() as cx:
        rows = await (await cx.execute(sql + " ORDER BY first_seen_at DESC", params)).fetchall()
    return [_pythonic(r) for r in rows]


# Failed detail fetches are retried after this long, not on every pass.
_DETAIL_RETRY = "6 hours"


async def enrichment_queue(*, per_source: int, max_age_days: int) -> list[dict]:
    """Listings to read the detail page of (sección 5.5), per source newest
    first: the ones with a live (non-backfill) match, then backfill matches,
    then listings without a match whose published price looks partial (an
    anticipo or a cuota): only their description can give the total that
    would let them match."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM ("
            "  SELECT l.id, l.source, l.external_id, l.url, l.make, l.model, "
            "         row_number() OVER (PARTITION BY l.source "
            "           ORDER BY coalesce(bool_or(NOT m.is_backfill), false) DESC, "
            "                    count(m.listing_id) > 0 DESC, l.first_seen_at DESC) AS n "
            "    FROM listings l LEFT JOIN matches m ON m.listing_id = l.id "
            "   WHERE l.enriched_at IS NULL AND l.status = 'active' "
            "     AND l.last_seen_at >= now() - make_interval(days => %s) "
            f"    AND (l.detail_checked_at IS NULL OR l.detail_checked_at < now() - interval '{_DETAIL_RETRY}') "
            "   GROUP BY l.id "
            "  HAVING count(m.listing_id) > 0 OR l.price_partial) q "
            "WHERE n <= %s ORDER BY source, n",
            (max_age_days, per_source))).fetchall()


async def watchlist_queue(*, min_hours_between_checks: int = 20) -> list[dict]:
    """Saved or followed listings still active and not checked in the last day (sección 5.6)."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT l.id, l.source, l.external_id, l.url, l.make, l.model, l.published_at, "
            "       l.first_seen_at "
            "  FROM listings l "
            " WHERE l.status = 'active' "
            "   AND (l.detail_checked_at IS NULL "
            "        OR l.detail_checked_at < now() - make_interval(hours => %s)) "
            "   AND EXISTS (SELECT 1 FROM user_listing_interactions i "
            "                WHERE i.listing_id = l.id AND (i.saved OR i.status IN "
            "                      ('interested', 'contacted', 'visit_scheduled'))) "
            " ORDER BY l.source, l.detail_checked_at NULLS FIRST, l.id",
            (min_hours_between_checks,))).fetchall()


async def matched_recheck_queue(*, unseen_hours: int, recheck_hours: int, max_age_days: int,
                                per_source: int) -> list[dict]:
    """Active listings with a match (above 'low') that the crawl stopped
    seeing: past the pages a search reads, only their detail page tells a
    price drop or the end of the ad (sección 5.6). Per source, the ones
    checked longest ago first; enrichment_queue takes the never enriched."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM ("
            "  SELECT l.id, l.source, l.external_id, l.url, l.make, l.model, l.published_at, "
            "         l.first_seen_at, "
            "         row_number() OVER (PARTITION BY l.source "
            "           ORDER BY l.detail_checked_at NULLS FIRST, l.id) AS n "
            "    FROM listings l "
            "   WHERE l.status = 'active' AND l.enriched_at IS NOT NULL "
            "     AND l.last_seen_at < now() - make_interval(hours => %s) "
            "     AND (l.detail_checked_at IS NULL "
            "          OR l.detail_checked_at < now() - make_interval(hours => %s)) "
            "     AND l.first_seen_at >= now() - make_interval(days => %s) "
            "     AND EXISTS (SELECT 1 FROM matches m "
            "                  WHERE m.listing_id = l.id AND m.level <> 'low')) q "
            "WHERE n <= %s ORDER BY source, n",
            (unseen_hours, recheck_hours, max_age_days, per_source))).fetchall()
