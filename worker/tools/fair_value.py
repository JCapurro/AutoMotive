"""
Fit the «valor justo» curves without writing anything (docs/superpowers/specs/2026-11-20-valor-justo-design.md §4.3).

Reads app_config, the models and each model's public.price_pool, fits and gates them as the daily job does
(pipeline/fair_value.fit_all) and prints the result. Writes no curve, no run and no error row, whatever
app_config.fair_value.mode says.

Usage (from worker/):
    python -m tools.fair_value --dry-run
    python -m tools.fair_value --dry-run --model "Toyota Hilux"
    python -m tools.fair_value --dry-run --model "Volkswagen Gol Trend" --json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import db
from aio import run
from pipeline.fair_value import fit_all


async def split_model(cx, text: str) -> tuple[str, str]:
    """«Toyota Hilux» → ('toyota', 'hilux'), the make being the longest known prefix (makes and models have
    spaces: «Mercedes Benz», «Gol Trend»)."""
    words = text.strip().split()
    if len(words) < 2:
        raise SystemExit("--model necesita marca y modelo, por ejemplo «Toyota Hilux»")
    for cut in range(len(words) - 1, 0, -1):
        make, model = " ".join(words[:cut]), " ".join(words[cut:])
        row = await (await cx.execute(
            "SELECT 1 FROM listings WHERE lower(make) = lower(%s) AND lower(model) = lower(%s) LIMIT 1",
            (make, model))).fetchone()
        if row:
            return make.lower(), model.lower()
    raise SystemExit(f"no encontré avisos de «{text}»")


def _pct(x: Any) -> str:
    return "—" if not isinstance(x, (int, float)) else f"{100 * x:.1f}%"


def render(result: dict[str, Any], *, detail: bool) -> str:
    lines = [f"Valor justo · prueba en seco · params {result['params']['params']} · modo {result['params']['mode']}",
             ""]
    if result["status"] != "ok":
        lines.append(f"Falló: {result.get('error')}")
        return "\n".join(lines)
    lines.append(f"{'modelo':<34} {'n':>6} {'muestra':>7} {'err valor justo':>15} {'err hoy':>8} "
                 f"{'B':>7} {'flips':>5}  habilitada")
    for m in result["models"]:
        lines.append(f"{(m['make'] + ' ' + m['model'])[:34]:<34} {m['n']:>6} {m['sample']:>7} "
                     f"{_pct(m['cv_err']):>15} {_pct(m['cohort_err']):>8} "
                     f"{m['km_slope'] if m['km_slope'] is not None else '—':>7} {m['guard_flips']:>5}  "
                     f"{'sí' if m['enabled'] else 'no'}{'' if m['fitted'] else ' (sin curva)'}")
    lines.append("")
    lines.append(f"{len(result['models'])} modelos, {sum(m['fitted'] for m in result['models'])} con curva, "
                 f"{sum(m['enabled'] for m in result['models'])} habilitados.")
    if detail:
        for (make, model), curve in result["curves"].items():
            c = curve.curve_json()
            lines += ["", f"{make} {model}"]
            lines.append("  años: " + ", ".join(f"{y} {v['a']:.3f} (n {v['n']})" for y, v in c["years"].items()))
            lines.append("  versiones: " + (", ".join(f"{k} {v['g']:+.3f} (n {v['n']})"
                                                       for k, v in c["trims"].items()) or "ninguna con prima"))
            lines.append("  cajas: " + (", ".join(f"{k} {v['h']:+.3f} (n {v['n']})"
                                                  for k, v in c["transmissions"].items()) or "ninguna con prima"))
            lines.append(f"  km: B {c['km_slope']} · residuo q25 {c['resid']['q25']} q75 {c['resid']['q75']}")
    return "\n".join(lines)


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", required=True,
                   help="ajustar y mostrar sin escribir (el único modo de esta herramienta)")
    p.add_argument("--model", help="un solo modelo, por ejemplo «Toyota Hilux»")
    p.add_argument("--json", action="store_true", help="imprimir el resultado como JSON")
    args = p.parse_args(argv)

    await db.open_pool()
    try:
        only = None
        if args.model:
            async with db.connection() as cx:
                only = await split_model(cx, args.model)
        result = await fit_all(trigger="cli", dry_run=True, only=only)
    finally:
        await db.close_pool()
    if args.json:
        out = {**result, "curves": {f"{k[0]} {k[1]}": c.curve_json() for k, c in result["curves"].items()}}
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(result, detail=only is not None))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(run(main()))
