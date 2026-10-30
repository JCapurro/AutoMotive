"""
Seller classification by hand (F-02 pasos 1 y 2,
docs/superpowers/specs/2026-10-30-f02-vendedor-design.md).

    python -m tools.seller_classification --backfill-keys
    python -m tools.seller_classification --dry-run
    python -m tools.seller_classification --write

--backfill-keys recomputes listings.seller_key from seller_name for every
listing (active and gone), 1.000 ids per transaction; run it once after the
migration. --dry-run writes no listing and prints, per source: active
listings, seller groups, listings over app_config.seller_classification.min_listings
and the 10 biggest groups with their raw names (to review the stoplist in
normalization/seller.py). --write writes seller_listing_count and
dealer_inferred («posible agencia») and re-scores the matches of the listings
whose inference changed, as the worker does at startup and at the nightly
anchor slot. Both record the run in
seller_classification_runs. Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import db
from aio import run
from pipeline.seller_classification import backfill_keys, classify_sellers

log = logging.getLogger("seller_classification")


def report_lines(result: dict[str, Any]) -> list[str]:
    cfg = result["params"]
    lines = [f"ventana {cfg['window_days']} días, umbral {cfg['min_listings']} avisos"]
    for s in result["sources"]:
        lines.append(f"\n{s['source']}: {s['active']} activos, {s['groups']} vendedores, "
                     f"{s['over_threshold']} avisos sobre el umbral")
        for g in s["top"]:
            names = " | ".join(g["names"])
            lines.append(f"  {g['n']:>4} autos ({g['active']} activos)  {g['key']}  ← {names}")
    return lines


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.seller_classification", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--backfill-keys", action="store_true", help="recalcular seller_key de todos los avisos")
    what.add_argument("--dry-run", action="store_true", help="calcular e imprimir el informe, sin escribir avisos")
    what.add_argument("--write", action="store_true", help="escribir seller_listing_count y dealer_inferred")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        if args.backfill_keys:
            done = await backfill_keys()
            print(f"seller_key: {done['rows_written']} avisos actualizados en {done['batches']} lotes")
            return 0
        try:
            result = await classify_sellers("cli", dry_run=args.dry_run, report=args.dry_run)
        except Exception as e:
            print(f"la corrida falló (quedó en seller_classification_runs): {type(e).__name__}: {e}")
            return 1
    finally:
        await db.close_pool()

    if args.dry_run:
        print("\n".join(report_lines(result)))
        print(f"\nactivos leídos {result['rows_read']}; se escribirían {result['would_write']} filas, "
              f"{result['inferred_changed']} cambiarían de «posible agencia» "
              "(simulación: no se escribió ningún aviso; si faltan claves, correr antes --backfill-keys)")
    else:
        print(f"activos leídos {result['rows_read']}; filas escritas {result['rows_written']}; "
              f"claves completadas {result['keys_filled']}; «posible agencia» cambió en "
              f"{result['inferred_changed']}; matches re-puntuados {result['rescored']}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main(sys.argv[1:])))
