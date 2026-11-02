"""
Duplicate detection by hand and backfill (PAR-02 resto,
docs/superpowers/specs/2026-11-02-par02-resto-design.md, decision 7).

    python -m tools.risk_duplicates --dry-run --report
    python -m tools.risk_duplicates
    python -m tools.risk_duplicates --group "Ford/Fiesta" --report

Without --dry-run it rewrites listing_duplicates for every (make, model)
group with 2+ sources or a photo hash, deletes the pairs no group holds any
more and re-scores the matches of the listings whose shown pairs changed, as
the worker does at startup and at the nightly anchor slot. Idempotent: a
second run changes nothing. --dry-run writes and re-scores nothing and prints
how many pair rows (both ways) of each kind it would create and delete.
--report lists up to 20 pairs per kind with both links, Δkm, Δprice, photo
distance and zone: the tool to review the shadow mode (app_config.risk.signals).
Run from worker/.
"""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

import db
from aio import run
from db.repos import duplicates as repo
from pipeline.risk_duplicates import detect_all

log = logging.getLogger("risk_duplicates")


def _fmt_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "ninguno"


def summary_lines(result: dict[str, Any]) -> list[str]:
    signals = ", ".join(f"{k}={v}" for k, v in sorted(result["signals"].items()))
    verb = "se crearían" if result["mode"] == "dry_run" else "creados"
    gone = "se borrarían" if result["mode"] == "dry_run" else "borrados"
    lines = [f"señales: {signals}",
             f"{result['groups']} grupos (marca/modelo), {result['rows_read']} avisos activos leídos",
             f"pares (filas en los dos sentidos): {_fmt_counts(result['pairs'])}",
             f"{verb}: {_fmt_counts(result['created'])}; {gone}: {_fmt_counts(result['deleted'])}",
             f"avisos con cambios en lo que se muestra: {result['changed']}"]
    if result["mode"] == "dry_run":
        lines.append("(simulación: no se escribió nada ni se re-puntuó)")
    else:
        lines.append(f"matches re-puntuados: {result['rescored']}")
    return lines


def report_lines(result: dict[str, Any], listings: dict[int, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for kind, pairs in sorted(result["report"].items()):
        mode = result["signals"].get(kind)
        lines.append(f"\n{kind} ({mode}): {len(pairs)} pares de muestra")
        for p in pairs:
            a, b = listings.get(p.a, {}), listings.get(p.b, {})
            ev = p.evidence
            zone = ev.get("zone") or {}
            bits = []
            if "km_pct" in ev:
                bits.append(f"Δkm {ev['km_pct']}%")
            if "price_pct" in ev:
                bits.append(f"Δprecio {ev['price_pct']}%")
            if ev.get("reason"):
                bits.append("otra zona" if ev["reason"] == "other_zone"
                            else "otros datos: " + ", ".join(ev.get("conflicts") or []))
            if ev.get("data") == "unconfirmed":
                bits.append("datos sin confirmar")
            if p.distance is not None:
                bits.append(f"distancia foto {p.distance}")
            if zone.get("dist_km") is not None:
                bits.append(f"{zone['dist_km']} km")
            if zone:
                bits.append("mismo departamento" if zone.get("same_department") else "otro departamento")
            lines.append(f"  {p.a} ↔ {p.b}  " + " · ".join(bits))
            lines.append(f"    {a.get('source')}: {a.get('url')}")
            lines.append(f"    {b.get('source')}: {b.get('url')}")
    return lines


async def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.risk_duplicates", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="calcular sin escribir ni re-puntuar")
    ap.add_argument("--report", action="store_true", help="listar hasta 20 pares por tipo")
    ap.add_argument("--group", help='un solo grupo, "Marca/Modelo"')
    args = ap.parse_args(argv)
    only = None
    if args.group:
        make, _, model = args.group.partition("/")
        if not make.strip() or not model.strip():
            ap.error('--group tiene que ser "Marca/Modelo"')
        only = (make.strip().lower(), model.strip().lower())

    await db.open_pool()
    try:
        try:
            result = await detect_all("cli", dry_run=args.dry_run, report=args.report, only=only)
        except Exception as e:
            print(f"la corrida falló: {type(e).__name__}: {e}")
            return 1
        listings: dict[int, dict[str, Any]] = {}
        if args.report and result["report"]:
            ids = {i for pairs in result["report"].values() for p in pairs for i in (p.a, p.b)}
            async with db.connection() as cx:
                listings = await repo.describe(cx, ids)
    finally:
        await db.close_pool()

    if result["mode"] == "skipped":
        print("listing_duplicates no existe todavía: aplicar la migración 20261203120000_par02_duplicates")
        return 1
    print("\n".join(summary_lines(result)))
    if args.report:
        print("\n".join(report_lines(result, listings)) or "\nsin pares para mostrar")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main(sys.argv[1:])))
