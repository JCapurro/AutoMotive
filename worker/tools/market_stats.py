"""
Compute the weekly market stats by hand (F-03 fase 0).

    python -m tools.market_stats [--week [2026-W44]] --dry-run
    python -m tools.market_stats [--week [2026-W44]] --write

Without a value, --week is the last closed ISO week (Monday to Sunday,
Argentina time); the job also recomputes the app_config.market_stats.recompute_weeks
before it, and rejects older weeks (they are not rebuilt).

--dry-run writes nothing at all (not even the zones or the run) and prints
the report: rows, price sample sizes, listings without a zone per source and
the size 26 weeks would take. --write writes market_stats, and only when
app_config.market_stats.write_enabled is true (Juan turns it on in /admin/config).
Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys

import db
from aio import run
from pipeline.market_stats import WeekRejected, report_lines, run_market_stats

log = logging.getLogger("market_stats")


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.market_stats", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--week", nargs="?", const=None, default=None,
                    help="semana ISO, ej. 2026-W44 (sin valor: la última cerrada)")
    what = ap.add_mutually_exclusive_group(required=True)
    what.add_argument("--dry-run", action="store_true", help="calcular e imprimir el informe, sin escribir nada")
    what.add_argument("--write", action="store_true", help="escribir market_stats (requiere write_enabled)")
    args = ap.parse_args(argv)

    await db.open_pool()
    try:
        write_enabled = False
        if args.write:
            write_enabled = bool((await db.get_config("market_stats", {}) or {}).get("write_enabled"))
            if not write_enabled:
                print("app_config.market_stats.write_enabled es false: no se escribe nada. "
                      "Lo prende Juan desde /admin/config; mientras tanto, usar --dry-run.")
                return 2
        try:
            result = await run_market_stats(args.week, mode="write" if args.write else "preview",
                                             write_enabled=write_enabled)
        except WeekRejected as exc:
            print(exc)
            return 2
    finally:
        await db.close_pool()

    if result["status"] != "ok":
        print(f"la corrida falló (quedó en pipeline_errors):\n{result.get('error', '')}")
        return 1
    if result["report"]:
        print("\n".join(report_lines(result["report"])))
    print(f"semanas: {', '.join(result['weeks'])}; filas calculadas {result['rows_computed']}, "
          f"escritas {result['rows_written']}")
    if not args.write:
        print("(simulación: no se escribió nada)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main(sys.argv[1:])))
