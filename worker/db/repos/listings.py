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
           "body_type", "location_text", "lat", "lon", "seller_name", "seller_type", "images", "attributes",
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


async def new_rows(cx: AsyncConnection, ids: Iterable[int]) -> list[dict[str, Any]]:
    """A run's new listings as pipeline/news.py reads them."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    rows = await (await cx.execute(
        "SELECT id, source, external_id, title, make, model, year, mileage_km, trim, transmission, seller_name, "
        "       price, currency, price_usd, price_partial, images, published_at, first_seen_at, probable_repost_of "
        "  FROM listings WHERE id = ANY(%s) ORDER BY id", (ids,))).fetchall()
    return [_pythonic(r) for r in rows]


async def unclassified(cx: AsyncConnection, ids: Iterable[int], *, target_id: int, run_id: int) -> list[int]:
    """Of these listings, the ones pipeline/news.py never looked at: first
    seen after the end of the target's last run that got to classify
    (`run_id`, the current one, left out) and without a mark. Only a run
    cut between its ingest and classify (a restart) leaves them so. A run
    that got to classify records how many it stored (collector_runs.new);
    one that failed in the collector or the ingest, or that a restart cut
    (fail_orphan_runs), doesn't, and leaves the window open."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    rows = await (await cx.execute(
        "SELECT id FROM listings WHERE id = ANY(%(ids)s) "
        "   AND first_seen_at > (SELECT max(r.finished_at) FROM collector_runs r "
        "                         WHERE r.target_id = %(target)s AND r.id <> %(run)s AND r.new IS NOT NULL) "
        "   AND NOT (attributes ? '_not_news' OR attributes ? '_republished') ORDER BY id",
        {"ids": ids, "target": target_id, "run": run_id})).fetchall()
    return [r["id"] for r in rows]


# A title compared without case or repeated spaces.
_TITLE = "lower(regexp_replace(btrim({}), '\\s+', ' ', 'g'))"


async def find_reappeared(cx: AsyncConnection, row: dict[str, Any], *, batch_external_ids: list[str],
                          window_days: int, price_tol_pct: float, km_tol: int,
                          unsellered_hours: int) -> dict[str, Any] | None:
    """The old copy of a car that `row` publishes again under another ID
    (pipeline/news.py): the same source, make, model and year, seller (km
    within `km_tol`), compatible version (the same, or one is the other
    plus more words: XLS and XLS Pack, never LT and LTZ) and gearbox, a price within `price_tol_pct` (in USD across
    currencies), seen in the last `window_days`, and missing from this read
    (`batch_external_ids`, everything the collector returned). Without a
    seller, the same km, and seen at most `unsellered_hours` before `row`
    or under the same title: private sellers round their km. On top of it
    the same plate on Grupo Randazzo, and the same first photo on Autocity
    and Car One when both have one. A row without make, model, year, 1.000
    km or a full price never reappears: too many cars look alike.
    Returns {id, price, currency, price_usd}, or None."""
    if (not (row.get("make") and row.get("model") and row.get("year")) or (row.get("mileage_km") or 0) < 1000
            or row.get("price_partial") or not row.get("price")):
        return None
    images = row.get("images") or []
    found = await (await cx.execute(
        "SELECT o.id, o.price, o.currency, o.price_usd "
        "  FROM listings o "
        " WHERE o.source = %(source)s AND o.id <> %(id)s AND NOT o.external_id = ANY(%(batch)s::text[]) "
        "   AND lower(o.make) = lower(%(make)s) AND lower(o.model) = lower(%(model)s) AND o.year = %(year)s "
        "   AND lower(o.seller_name) IS NOT DISTINCT FROM lower(%(seller)s::text) "
        "   AND CASE WHEN o.seller_name IS NULL "
        "            THEN o.mileage_km = %(km)s::int "
        "                 AND (o.last_seen_at >= coalesce(%(seen)s::timestamptz, now()) "
        "                                        - make_interval(hours => %(hours)s) "
        f"                     OR {_TITLE.format('o.title')} = {_TITLE.format('%(title)s::text')}) "
        "            ELSE abs(o.mileage_km - %(km)s::int) <= %(km_tol)s END "
        "   AND (o.trim IS NULL OR %(trim)s::text IS NULL OR lower(o.trim) = lower(%(trim)s::text) "
        "        OR starts_with(lower(o.trim), lower(%(trim)s::text) || ' ') "
        "        OR starts_with(lower(%(trim)s::text), lower(o.trim) || ' ')) "
        "   AND (o.transmission IS NULL OR %(gearbox)s::text IS NULL "
        "        OR lower(o.transmission) = lower(%(gearbox)s::text)) "
        "   AND NOT o.price_partial "
        "   AND o.last_seen_at >= now() - make_interval(days => %(window)s) "
        "   AND CASE WHEN o.currency = %(currency)s::text "
        "            THEN o.price > 0 AND abs(o.price - %(price)s::numeric) <= o.price * %(tol)s::numeric / 100 "
        "            ELSE o.price_usd > 0 "
        "                 AND abs(o.price_usd - %(price_usd)s::numeric) <= o.price_usd * %(tol)s::numeric / 100 END "
        "   AND (o.source <> 'gruporandazzo' "
        "        OR split_part(o.external_id, '_', 1) = split_part(%(external_id)s, '_', 1)) "
        "   AND (o.source NOT IN ('autocity', 'carone') OR o.images->>0 IS NULL OR %(image)s::text IS NULL "
        "        OR o.images->>0 = %(image)s::text) "
        " ORDER BY o.last_seen_at DESC, o.id DESC LIMIT 1",
        {"source": row["source"], "id": row["id"], "batch": list(batch_external_ids),
         "make": row["make"], "model": row["model"], "year": row["year"], "seller": row.get("seller_name"),
         "km": row["mileage_km"], "km_tol": km_tol, "trim": row.get("trim"), "gearbox": row.get("transmission"),
         "seen": row.get("first_seen_at"), "hours": unsellered_hours, "title": row.get("title"),
         "window": window_days, "currency": row.get("currency"), "price": row["price"],
         "price_usd": row.get("price_usd"), "tol": price_tol_pct, "external_id": row["external_id"],
         "image": images[0] if images and isinstance(images[0], str) else None})).fetchone()
    return _pythonic(found) if found else None


async def mark_not_news(cx: AsyncConnection, marks: Iterable[tuple[int, dict[str, Any], int | None]]) -> None:
    """pipeline/news.py's marks, (listing_id, attributes, repost_of): the
    attributes (_not_news, _republished) join the listing's, and repost_of
    becomes its probable_repost_of if it has none."""
    marks = list(marks)
    if not marks:
        return
    async with cx.cursor() as cur:
        await cur.executemany(
            "UPDATE listings SET attributes = attributes || %s, "
            "  probable_repost_of = coalesce(probable_repost_of, %s::bigint) WHERE id = %s",
            [(Jsonb(attrs), repost_of, lid) for lid, attrs, repost_of in marks])


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


async def reserve_description_run(listing_id: int, input_hash: str, daily_cap: int) -> int | None:
    """Atomic rolling-24h budget, shared across sources/passes; failed attempts also count.

    At most one attempt for the same listing/text/version in 24h. The transaction
    ends before network I/O; the reservation remains counted if a process dies.
    """
    if daily_cap <= 0:
        return None
    async with connection() as cx:
        async with cx.transaction():
            await cx.execute("SELECT pg_advisory_xact_lock(7060141200)")
            count = await (await cx.execute(
                "SELECT count(*) AS n FROM description_llm_runs "
                "WHERE started_at > now() - interval '1 day'")).fetchone()
            # Honor legacy successful analyses until their first rolling window expires.
            legacy = await (await cx.execute(
                "SELECT count(*) AS n FROM listings WHERE description_facts ->> 'source' = 'llm' "
                "AND (description_facts ->> 'llm_at')::timestamptz > now() - interval '1 day' "
                "AND NOT EXISTS (SELECT 1 FROM description_llm_runs r WHERE r.listing_id = listings.id "
                "AND r.started_at > now() - interval '1 day')")).fetchone()
            if int(count["n"]) + int(legacy["n"]) >= daily_cap:
                return None
            duplicate = await (await cx.execute(
                "SELECT id FROM description_llm_runs WHERE listing_id = %s AND input_hash = %s "
                "AND started_at > now() - interval '1 day' LIMIT 1", (listing_id, input_hash))).fetchone()
            if duplicate:
                return None
            run = await (await cx.execute(
                "INSERT INTO description_llm_runs (listing_id, input_hash) VALUES (%s, %s) RETURNING id",
                (listing_id, input_hash))).fetchone()
            return int(run["id"])


async def finish_description_run(run_id: int, *, error: str | None) -> None:
    async with connection() as cx:
        await cx.execute("UPDATE description_llm_runs SET completed_at = now(), error = %s WHERE id = %s",
                         (error, run_id))


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


async def recent_active_by_body(body_types: list[str], *, days: int, sources: list[str] | None = None,
                                year_min: int | None = None, year_max: int | None = None,
                                km_max: int | None = None, price_max: float | None = None,
                                currency: str = "USD", fx_rate: float | None = None) -> list[dict]:
    """Active listings of these body types seen in the last `days`, for the
    rematch of a search without a model (docs/CARROCERIA.md), on
    listings_body_type_active_idx. A body type has thousands of listings and
    scoring each costs a comparables() call, so what intelligence/matching.py
    would discard is left out here: a year outside [year_min, year_max], km
    above km_max, a price above `price_max` (in `currency`, converted the way
    matching.price_in does with `fx_rate`) and partial prices, like
    preview_search: scoring excludes those from every match (a batch never
    matches them either, intelligence/scoring.py). Unknown values pass."""
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT l.* FROM listings l CROSS JOIN LATERAL (SELECT CASE "
            "    WHEN l.price IS NULL OR l.price <= 0 THEN NULL "
            "    WHEN coalesce(nullif(upper(l.currency), ''), %(currency)s) = %(currency)s THEN l.price "
            "    WHEN %(currency)s = 'USD' THEN coalesce(nullif(l.price_usd, 0), l.price / %(fx)s::numeric) "
            "    ELSE l.price * %(fx)s::numeric END AS value) p "
            " WHERE l.status = 'active' AND l.body_type = ANY(%(body_types)s) "
            "   AND l.last_seen_at >= now() - make_interval(days => %(days)s) "
            "   AND NOT l.price_partial "
            "   AND (%(sources)s::text[] IS NULL OR l.source = ANY(%(sources)s)) "
            "   AND (%(year_min)s::int IS NULL OR l.year IS NULL OR l.year >= %(year_min)s) "
            "   AND (%(year_max)s::int IS NULL OR l.year IS NULL OR l.year <= %(year_max)s) "
            "   AND (%(km_max)s::int IS NULL OR l.mileage_km IS NULL OR l.mileage_km <= %(km_max)s) "
            "   AND (%(price_max)s::numeric IS NULL OR p.value IS NULL OR p.value <= %(price_max)s) "
            " ORDER BY l.first_seen_at DESC",
            {"body_types": list(body_types), "days": days, "sources": list(sources) if sources else None,
             "year_min": year_min, "year_max": year_max, "km_max": km_max, "price_max": price_max,
             "currency": currency.upper(), "fx": fx_rate})).fetchall()
    return [_pythonic(r) for r in rows]


# Failed detail fetches are retried after this long, not on every pass.
_DETAIL_RETRY = "6 hours"


# A listing only a target's reference year band brought (pipeline/crawl.py,
# crawl_targets.query.year_band): its year one past the searches' own, on
# the target's source. Facebook targets never read the band.
_BAND_ROW = (
    "EXISTS (SELECT 1 FROM crawl_targets t "
    "         WHERE t.active AND t.body_type IS NULL AND t.source = l.source AND t.query ? 'year_band' "
    "           AND lower(t.make) = lower(l.make) AND lower(t.model) = lower(l.model) "
    "           AND ((l.year < (t.query->>'year_min')::numeric "
    "                 AND l.year >= (t.query->>'year_min')::numeric - (t.query->>'year_band')::numeric) "
    "             OR (l.year > (t.query->>'year_max')::numeric "
    "                 AND l.year <= (t.query->>'year_max')::numeric + (t.query->>'year_band')::numeric)))")


async def enrichment_queue(*, per_source: int, max_age_days: int) -> list[dict]:
    """Listings to read the detail page of (sección 5.5), per source newest
    first: the ones with a live (non-backfill) match, then backfill matches,
    then listings without a match whose published price looks partial (an
    anticipo or a cuota): only their description can give the total that
    would let them match, and the reference band's (_BAND_ROW) without a
    transmission, which comparables() needs at its finer levels. `band` is
    true for those last ones when nothing else queued them: pipeline/enrich.py
    reads them without the LLM, since only the version and the transmission
    are wanted, and they never take its daily budget."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM ("
            "  SELECT l.id, l.source, l.external_id, l.url, l.make, l.model, "
            "         count(m.listing_id) = 0 AND NOT l.price_partial AS band, "
            "         row_number() OVER (PARTITION BY l.source "
            "           ORDER BY coalesce(bool_or(NOT m.is_backfill), false) DESC, "
            "                    count(m.listing_id) > 0 DESC, l.first_seen_at DESC) AS n "
            "    FROM listings l LEFT JOIN matches m ON m.listing_id = l.id AND public.search_access_active(m.search_profile_id) "
            "   WHERE l.enriched_at IS NULL AND l.status = 'active' "
            "     AND l.last_seen_at >= now() - make_interval(days => %s) "
            f"    AND (l.detail_checked_at IS NULL OR l.detail_checked_at < now() - interval '{_DETAIL_RETRY}') "
            "   GROUP BY l.id "
            "  HAVING count(m.listing_id) > 0 OR l.price_partial "
            f"     OR (l.transmission IS NULL AND l.year IS NOT NULL AND {_BAND_ROW})) q "
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
            "                WHERE i.listing_id = l.id AND public.commercial_access_active(i.user_id) "
            "                  AND (i.saved OR i.status IN "
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
            "                  WHERE m.listing_id = l.id AND m.level <> 'low' "
            "                    AND public.search_access_active(m.search_profile_id))) q "
            "WHERE n <= %s ORDER BY source, n",
            (unseen_hours, recheck_hours, max_age_days, per_source))).fetchall()
