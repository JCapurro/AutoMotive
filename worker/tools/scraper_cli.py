"""
Test a scraper without running the bot.

Usage:
    python -m tools.scraper_cli <source> [k=v ...]

Examples:
    python -m tools.scraper_cli mercadolibre marca=Toyota modelo=Corolla anio_min=2018
    python -m tools.scraper_cli demotores marca=Volkswagen modelo=Gol
    python -m tools.scraper_cli olx precio_max=15000 moneda=USD
    python -m tools.scraper_cli facebook marca=Ford modelo=Ranger
"""
from __future__ import annotations
import sys
from typing import Any

# Force UTF-8 stdout on Windows consoles (cp1252 default chokes on emoji/arrows)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from collectors import REGISTRY
from collectors._browser import shutdown as browser_shutdown
from collectors._loop import run_collector
from normalization.geo import filter_listings_by_radius
from aio import run
import db


def _parse_kv(args: list[str]) -> dict[str, Any]:
    f: dict[str, Any] = {}
    for a in args:
        if "=" not in a:
            continue
        k, v = a.split("=", 1)
        k, v = k.strip(), v.strip()
        if v.isdigit():
            f[k] = int(v)
        else:
            try:
                f[k] = float(v)
            except ValueError:
                f[k] = v
    return f


def _fmt(v, width: int) -> str:
    s = "-" if v is None else str(v)
    if len(s) > width:
        s = s[: width - 1] + "…"
    return s.ljust(width)


async def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in REGISTRY:
        print(__doc__)
        print("Sources disponibles:", ", ".join(REGISTRY.keys()))
        sys.exit(1)

    src = sys.argv[1]
    filters = _parse_kv(sys.argv[2:])
    print(f"→ scraper: {src}")
    print(f"→ filtros: {filters}\n")

    await db.open_pool()   # geocode cache for the radius filter
    scraper = REGISTRY[src]()
    try:
        results = await run_collector(scraper.search(filters))
        results = await filter_listings_by_radius(results, filters)
    except Exception as e:
        print(f"❌ scraper falló: {type(e).__name__}: {e}")
        raise
    finally:
        await run_collector(browser_shutdown())
        await db.close_pool()

    print(f"✅ {len(results)} resultados\n")
    if not results:
        return

    print(_fmt("ID", 14), _fmt("PRECIO", 14), _fmt("AÑO", 5),
          _fmt("KM", 10), _fmt("UBIC", 18), _fmt("TÍTULO", 60))
    print("-" * 125)
    for r in results[:30]:
        precio = f"{r.moneda or ''} {int(r.precio):,}".replace(",", ".") if r.precio else "-"
        km = f"{r.km:,}".replace(",", ".") if r.km else "-"
        print(_fmt(r.listing_id, 14), _fmt(precio, 14), _fmt(r.anio, 5),
              _fmt(km, 10), _fmt(r.ubicacion, 18), _fmt(r.titulo, 60))

    print("\nPrimera URL:", results[0].url)


if __name__ == "__main__":
    run(main())
