"""
Read the color of the active listings with a match from their photos, once.

    python -m tools.backfill_color_vision [--limit 500] [--source deruedas] [--dry-run]

The same reader as the color pass (pipeline/color_vision.py): active listings
with a live match and no color from the source or the text, those of a
search with a color filter first. Up to 10 photos each through the safe
downloader, one call each to the provider (LLM_PROVIDER), within
app_config.color_vision.daily_cap like the pass: it stops when the cap is
reached, and the next run goes on where it stopped (what was read is not
read again). The matches of the listings that got a color are re-scored,
never notified.

--dry-run counts the listings and photos it would read and prints the
estimated cost; it downloads nothing, calls nothing and writes nothing.
The calls are one by one (synchronous API). Follow-up, not built: the Batch
API at half the price for the initial load (docs/COLOR.md).
Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import db
from aio import run
from pipeline import color_vision as cv
from pipeline.rescore import rescore_listings

log = logging.getLogger("backfill_color_vision")

# Measured in Fase 0 (docs/COLOR.md): about US$ 0.25 per thousand listings
# with all their photos. Only for the dry run's estimate.
DRY_RUN_USD_PER_LISTING = 0.25 / 1000


async def backfill(*, limit: int, source: str | None, dry_run: bool,
                   reader: cv.ColorVision | None = None) -> dict[str, Any]:
    owned = reader is None
    if reader is None:
        reader = await cv.ColorVision.create(dry_run=dry_run)
    if reader is None:
        return {"off": True}
    try:
        rows = await cv.queue(limit=limit, skip_sources=reader.cfg["skip_sources"], source=source)
        await reader.read_many(rows)
        out: dict[str, Any] = {"queued": len(rows), **reader.stats}
        if reader.written and not dry_run:
            out["rescored"] = await rescore_listings(reader.written)
        return out
    finally:
        if owned:
            await reader.close()


def report(out: dict[str, Any], *, dry_run: bool) -> list[str]:
    if out.get("off"):
        return ["app_config.color_vision apagado (o sin tope, sin Pillow o sin proveedor): no se leyó nada"]
    lines = [f"{key:<16} {value:>8}" for key, value in out.items()]
    if dry_run:
        cost = out.get("listings", 0) * DRY_RUN_USD_PER_LISTING
        lines.append(f"costo estimado  US$ {cost:.4f} ({out.get('listings', 0)} avisos, "
                     f"{out.get('photos', 0)} fotos; US$ 0,25 cada mil, medido en la Fase 0)")
        lines.append("(simulación: no se bajó, no se llamó ni se escribió nada)")
    else:
        cost = cv.estimated_cost(out.get("tokens_in", 0), out.get("tokens_out", 0))
        lines.append(f"costo           US$ {cost:.4f} ({out.get('tokens_in', 0)} tokens de entrada, "
                     f"{out.get('tokens_out', 0)} de salida)")
        if out.get("capped"):
            lines.append("se llegó al tope diario (app_config.color_vision.daily_cap): seguí mañana")
    return lines


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.backfill_color_vision", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=500, help="cuántos avisos como mucho (500)")
    ap.add_argument("--source", help="una sola fuente")
    ap.add_argument("--dry-run", action="store_true", help="solo contar y estimar el costo")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        out = await backfill(limit=max(1, args.limit), source=args.source, dry_run=args.dry_run)
    finally:
        await db.close_pool()
    print("\n".join(report(out, dry_run=args.dry_run)))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main(sys.argv[1:])))
