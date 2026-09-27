from __future__ import annotations

from db.pool import connection


async def get_geocode_cache(query: str) -> tuple[float, float] | None:
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT lat, lon, not_found FROM geocode_cache WHERE query = %s", (query,),
        )).fetchone()
    if not row or row["not_found"]:
        return None
    return float(row["lat"]), float(row["lon"])


async def set_geocode_cache(query: str, lat: float, lon: float, source: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "INSERT INTO geocode_cache (query, lat, lon, source, not_found, updated_at) "
            "VALUES (%s, %s, %s, %s, false, now()) "
            "ON CONFLICT (query) DO UPDATE SET "
            "  lat = excluded.lat, lon = excluded.lon, source = excluded.source, "
            "  not_found = false, updated_at = excluded.updated_at",
            (query, lat, lon, source),
        )


async def set_geocode_cache_failure(query: str, source: str) -> None:
    """Cache that this query failed to geocode, so we don't keep retrying."""
    async with connection() as cx:
        await cx.execute(
            "INSERT INTO geocode_cache (query, lat, lon, source, not_found, updated_at) "
            "VALUES (%s, 0, 0, %s, true, now()) "
            "ON CONFLICT (query) DO UPDATE SET "
            "  source = excluded.source, not_found = true, updated_at = excluded.updated_at",
            (query, source),
        )


async def has_fresh_geocode_failure(query: str, max_age_days: int = 7) -> bool:
    """True if the query was tried and failed within the past `max_age_days`."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT 1 FROM geocode_cache "
            "WHERE query = %s AND not_found AND updated_at >= now() - make_interval(days => %s)",
            (query, max_age_days),
        )).fetchone()
    return row is not None
