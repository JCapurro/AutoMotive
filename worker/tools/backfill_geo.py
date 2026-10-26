"""
Place the stored listings that have no coordinates.

    python -m tools.backfill_geo [--dry-run] [--source facebook] [--no-rescore]

Reads the location text each active listing already has, without asking the
sources: the source's decoration is dropped (normalization.geo.clean_location_text),
what is not a place ("Recién publicado", a title) is cleared, and the rest is
geocoded like a crawl would (known table, cache, Nominatim). A listing without
any text gets its source's default town (SOURCE_DEFAULT_LOCATIONS), as coordinates
only. Then the matches of the listings that gained coordinates are re-scored: a
search with a radius drops the ones that turn out to be outside it.

--dry-run prints what would change, per source, and writes nothing.
Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from typing import Any, Awaitable, Callable

import db
from aio import run
from normalization.geo import SOURCE_DEFAULT_LOCATIONS, clean_location_text, geocode_location
from pipeline.rescore import rescore_listings

log = logging.getLogger("backfill_geo")

Coords = tuple[float, float]
GeocodeFn = Callable[[str], Awaitable[Coords | None]]

_SELECT = ("SELECT id, source, location_text FROM listings "
           " WHERE status = 'active' AND lat IS NULL{source} ORDER BY id")


async def plan(rows: list[dict[str, Any]], geocode: GeocodeFn, counts: Counter | None = None
               ) -> list[tuple[int, Coords | None, bool]]:
    """(id, coordinates to write or None, clear the location text) for the rows that change."""
    cache: dict[tuple[str, str | None], tuple[Coords | None, bool]] = {}
    out: list[tuple[int, Coords | None, bool]] = []
    for row in rows:
        text = row["location_text"]
        key = (row["source"], text)
        if key not in cache:
            clean = clean_location_text(text)
            clear = bool(text and text.strip()) and clean is None
            place = clean or (SOURCE_DEFAULT_LOCATIONS.get(row["source"]) if clean is None else None)
            try:
                coords = await geocode(place) if place else None
            except Exception:
                log.warning("geocode failed for %r", place, exc_info=True)
                coords = None
            cache[key] = (coords, clear)
        coords, clear = cache[key]
        if counts is not None:
            counts[(row["source"], "ubicada" if coords else "sin ubicar")] += 1
            if clear:
                counts[(row["source"], "texto descartado")] += 1
        if coords or clear:
            out.append((row["id"], coords, clear))
    return out


async def backfill(*, dry_run: bool, source: str | None = None, rescore: bool = True,
                   geocode: GeocodeFn = geocode_location) -> Counter:
    counts: Counter = Counter()
    sql = _SELECT.format(source=" AND source = %s" if source else "")
    async with db.connection() as cx:
        rows = await (await cx.execute(sql, (source,) if source else ())).fetchall()
    updates = await plan(rows, geocode, counts)
    if updates and not dry_run:
        placed: list[int] = []
        async with db.connection() as cx:
            async with cx.cursor() as cur:
                for lid, coords, clear in updates:
                    # lat IS NULL: coordinates a crawl wrote meanwhile are kept.
                    await cur.execute(
                        "UPDATE listings SET lat = COALESCE(%s, lat), lon = COALESCE(%s, lon), "
                        "       location_text = CASE WHEN %s THEN NULL ELSE location_text END "
                        " WHERE id = %s AND lat IS NULL",
                        (coords[0] if coords else None, coords[1] if coords else None, clear, lid))
                    if coords:
                        placed.append(lid)
        if rescore and placed:
            counts[("*", "matches re-puntuados")] = await rescore_listings(placed)
    return counts


def report(counts: Counter, *, dry_run: bool) -> list[str]:
    lines = [f"{source:<14} {what:<22} {n:>6}" for (source, what), n in sorted(counts.items())]
    lines.append("(simulación: no se escribió nada)" if dry_run else "listo")
    return lines


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.backfill_geo", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="solo contar qué cambiaría")
    ap.add_argument("--source", help="una sola fuente")
    ap.add_argument("--no-rescore", action="store_true", help="no re-puntuar los matches")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        counts = await backfill(dry_run=args.dry_run, source=args.source, rescore=not args.no_rescore)
    finally:
        await db.close_pool()
    print("\n".join(report(counts, dry_run=args.dry_run)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main(sys.argv[1:])))
