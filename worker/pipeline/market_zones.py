"""Keep listing_zones in step with the listings' coordinates (F-03 fase 0).

sync_zones() writes a zone row (normalization.zone.derive_zone) for every
listing with coordinates that has none, and derives it again for the ones
whose lat/lon changed since. Gone listings too: the days until a listing
stopped being published need their zone. It runs at the start of every
market_stats run and from tools.backfill_zones; ingest.py is not touched.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import db
from normalization.zone import DEFAULT_ZONE_MAP, ZoneFacts, derive_zone, resolve_region

log = logging.getLogger("market_zones")

_SELECT = ("SELECT l.id, l.source, l.location_text, l.lat, l.lon, l.status::text AS status, "
           "       z.lat AS zone_lat, z.lon AS zone_lon, z.province_id AS zone_province_id, "
           "       z.department AS zone_department, z.precision AS zone_precision "
           "  FROM listings l LEFT JOIN listing_zones z ON z.listing_id = l.id{source} ORDER BY l.id")

_UPSERT = ("INSERT INTO listing_zones (listing_id, province_id, department, locality_id, dist_km, precision, "
           "                           lat, lon, derived_at) "
           "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now()) "
           "ON CONFLICT (listing_id) DO UPDATE SET province_id = excluded.province_id, "
           "  department = excluded.department, locality_id = excluded.locality_id, dist_km = excluded.dist_km, "
           "  precision = excluded.precision, lat = excluded.lat, lon = excluded.lon, derived_at = now()")


def plan_zones(rows: list[dict[str, Any]], zone_map: dict[str, Any] = DEFAULT_ZONE_MAP,
               counts: Counter | None = None) -> list[tuple[int, ZoneFacts]]:
    """(listing id, facts) for the listings without a zone row or whose
    coordinates moved. `counts` gets, per source and over active listings,
    how many end up with a region, a province without one, no coordinates,
    on their source's default town, and how many rows are to be written."""
    out: list[tuple[int, ZoneFacts]] = []
    for row in rows:
        source = row["source"]
        counted = counts is not None and row.get("status", "active") == "active"
        if row["lat"] is None or row["lon"] is None:
            if counted:
                counts[(source, "sin coordenadas")] += 1
            continue
        if (row.get("zone_lat"), row.get("zone_lon")) == (row["lat"], row["lon"]):
            province, department, precision = (row.get("zone_province_id"), row.get("zone_department"),
                                               row.get("zone_precision"))
        else:
            facts = derive_zone(row["lat"], row["lon"], row["location_text"], source)
            out.append((row["id"], facts))
            province, department, precision = facts.province_id, facts.department, facts.precision
            if counts is not None:
                counts[(source, "a escribir")] += 1
        if counted:
            region = resolve_region(zone_map, province, department, precision)
            counts[(source, "con región" if region else "provincia sin región")] += 1
            if precision == "source_default":
                counts[(source, "source_default")] += 1
    return out


async def _zone_map() -> dict[str, Any]:
    return await db.get_config("market_zones", None) or DEFAULT_ZONE_MAP


async def _fetch(source: str | None) -> list[dict[str, Any]]:
    sql = _SELECT.format(source=" WHERE l.source = %s" if source else "")
    async with db.connection() as cx:
        return await (await cx.execute(sql, (source,) if source else ())).fetchall()


async def _write(updates: list[tuple[int, ZoneFacts]]) -> None:
    async with db.connection() as cx:
        async with cx.cursor() as cur:
            await cur.executemany(_UPSERT, [
                (lid, f.province_id, f.department, f.locality_id, f.dist_km, f.precision, f.lat, f.lon)
                for lid, f in updates])


async def sync_zones(*, dry_run: bool = False, source: str | None = None) -> Counter:
    counts: Counter = Counter()
    updates = plan_zones(await _fetch(source), await _zone_map(), counts)
    if updates and not dry_run:
        await _write(updates)
        log.info("zonas: %d avisos ubicados", len(updates))
    return counts
