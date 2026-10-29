"""
Give every stored listing with coordinates its zone (F-03 fase 0).

    python -m tools.backfill_zones [--dry-run] [--source facebook]

Derives listing_zones (Georef province, department, precision) from the
coordinates each listing already has, for the ones without a zone row or
whose coordinates changed: pipeline.market_zones.sync_zones, the same the
weekly market_stats job runs first. Prints, per source and over active
listings, how many get a region, a province without one, no coordinates, or
the source's default town; the goal is 90 % with a region.

--dry-run prints what would change, per source, and writes nothing.
Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter

import db
from aio import run
from pipeline.market_zones import sync_zones

log = logging.getLogger("backfill_zones")


def report(counts: Counter, *, dry_run: bool) -> list[str]:
    lines = [f"{source:<14} {what:<22} {n:>6}" for (source, what), n in sorted(counts.items())]
    lines.append("(simulación: no se escribió nada)" if dry_run else "listo")
    return lines


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.backfill_zones", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="solo contar qué cambiaría")
    ap.add_argument("--source", help="una sola fuente")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        counts = await sync_zones(dry_run=args.dry_run, source=args.source)
    finally:
        await db.close_pool()
    print("\n".join(report(counts, dry_run=args.dry_run)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main(sys.argv[1:])))
