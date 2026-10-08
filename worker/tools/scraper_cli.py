"""
Test a scraper without running the bot.

Usage:
    python -m tools.scraper_cli <source> [k=v ...]
    python -m tools.scraper_cli detail <url> [--html out.html] [--source source_id]

Examples:
    python -m tools.scraper_cli mercadolibre marca=Toyota modelo=Corolla anio_min=2018
    python -m tools.scraper_cli kavak marca=Volkswagen modelo=Gol
    python -m tools.scraper_cli autocosmos precio_max=15000 moneda=USD
    python -m tools.scraper_cli facebook marca=Ford modelo=Ranger
    python -m tools.scraper_cli detail https://www.autocosmos.com.ar/auto/usado/ford/ka/15l-s/ff56ff47...

`detail` reads one ad's page (the source comes from the URL) and prints what
the parser and the description's rules make of it: the published and the
effective price, financing, km and year. Nothing is written to the database.
--html saves the page as raw_pages keeps it (slimmed), handy for a test fixture.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Force UTF-8 stdout on Windows consoles (cp1252 default chokes on emoji/arrows)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from collectors import REGISTRY
from collectors._browser import shutdown as browser_shutdown
from collectors._loop import run_collector
from normalization.description_facts import parse as parse_facts, resolve_price
from normalization.fx import usd_ars_rate
from normalization.geo import filter_listings_by_radius
from normalization.listing import _CURRENCIES
from normalization.price_check import keyword_partial
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


def _money(amount: float | None, currency: str | None) -> str:
    return "-" if amount is None else f"{currency or ''} {int(round(amount)):,}".replace(",", ".").strip()


_HOSTS = {"mercadolibre": "mercadolibre", "facebook": "facebook", "v6.com": "v6", "kavak": "kavak",
          "autocosmos": "autocosmos"}
_REGIONAL_HOSTS = {"mardelusados.com": "mardelusados", "www.rosariogarage.com": "rosariogarage",
                   "rosariogarage.com": "rosariogarage", "usadossantafe.com.ar": "usadossantafe",
                   "autocity.com.ar": "autocity", "www.autocity.com.ar": "autocity",
                   "carone.com.ar": "carone", "www.carone.com.ar": "carone",
                   "www.gruporandazzo.com": "gruporandazzo", "gruporandazzo.com": "gruporandazzo"}


def _source_of(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in _REGIONAL_HOSTS:
        return _REGIONAL_HOSTS[host]
    if host in ("instagram.com", "www.instagram.com"):
        account = parsed.path.strip("/").split("/", 1)[0].lower()
        return account if account in ("onlycarsusados", "sc_clasificados") else None
    return next((src for part, src in _HOSTS.items() if part in host), None)


async def detail(url: str, html_out: str | None, source: str | None = None) -> None:
    src = source or _source_of(url)
    if src not in REGISTRY:
        print(f"❌ no sé qué fuente es {url}. Fuentes: {', '.join(REGISTRY)}")
        sys.exit(1)
    scraper = REGISTRY[src]()
    print(f"→ {src}: {url}\n")
    try:
        page = await run_collector(scraper.fetch_detail_page(url))
    finally:
        await run_collector(browser_shutdown())
    if html_out:
        Path(html_out).write_text(scraper.slim_page(page), encoding="utf-8")
        print(f"página guardada en {html_out}")
    d = scraper.parse_detail(page.html, url, page.status)
    if d.gone:
        print(f"🚫 ya no está: {d.gone_reason}")
        return
    item = d.listing
    facts = parse_facts(item.descripcion, item.titulo, now_year=datetime.now(timezone.utc).year)
    reason = (item.price_partial_reason or "parcial") if item.price_partial else keyword_partial(item.titulo)
    currency = _CURRENCIES.get((item.moneda or "").strip().upper())
    price = resolve_price(item.precio, currency, partial_reason=reason, facts=facts, usd_rate=usd_ars_rate())
    print(f"título:      {item.titulo}")
    print(f"publicado:   {_money(item.precio, item.moneda)}" + (f"  (parcial: {reason})" if reason else ""))
    print(f"efectivo:    {_money(price.price, price.currency)}  · {price.source}"
          + (f" · {price.effective_kind}" if price.effective_kind else "")
          + ("  · parcial" if price.partial else ""))
    if price.mismatch:
        print(f"otro precio: {_money(price.mismatch.amount, price.mismatch.currency)} en la descripción")
    print(f"año / km:    {item.anio or '-'} / {item.km or '-'}")
    if facts is None:
        print("\n(sin descripción)")
        return
    print("\nDescripción:")
    for a in facts.amounts:
        print(f"  {a.kind:13} {_money(a.amount, a.currency):>16}  «{a.text}»")
    fin = facts.financing
    if fin.offered:
        terms = {k: v for k, v in vars(fin).items() if v not in (None, False) and k != "offered"}
        print(f"  financiación: sí {terms or ''}")
    print(f"  año {facts.year or '-'} · km {facts.mileage_km or '-'} · {facts.transmission or '-'} · "
          f"{facts.fuel or '-'}{' · GNC' if facts.gnc else ''}{' · AMBIGUA (LLM)' if facts.ambiguous else ''}")
    print(f"\n{len(item.descripcion or '')} caracteres de descripción")


async def main() -> None:
    if len(sys.argv) >= 3 and sys.argv[1] == "detail":
        html_out = sys.argv[sys.argv.index("--html") + 1] if "--html" in sys.argv[3:-1] else None
        source = sys.argv[sys.argv.index("--source") + 1] if "--source" in sys.argv[3:-1] else None
        await detail(sys.argv[2], html_out, source)
        return
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
    complete, reason, unknown_dates = True, None, 0
    try:
        results = await run_collector(scraper.search(filters))
        complete = getattr(results, "complete", True)
        reason = getattr(results, "reason", None)
        unknown_dates = getattr(results, "unknown_dates", 0)
        results = await filter_listings_by_radius(results, filters)
    except Exception as e:
        print(f"❌ scraper falló: {type(e).__name__}: {e}")
        raise
    finally:
        await run_collector(browser_shutdown())
        await db.close_pool()

    if complete:
        print(f"✅ {len(results)} resultados\n")
    else:
        print(f"⚠ {len(results)} resultados; recorrido incompleto: {reason}\n")
    if unknown_dates:
        print(f"{unknown_dates} avisos excluidos por fecha de publicación desconocida\n")
    if not results:
        if not complete:
            sys.exit(2)
        return

    print(_fmt("ID", 14), _fmt("PUBLICADO", 20), _fmt("PRECIO", 14), _fmt("AÑO", 5),
          _fmt("KM", 10), _fmt("UBIC", 18), _fmt("TÍTULO", 60))
    print("-" * 125)
    for r in results[:30]:
        precio = f"{r.moneda or ''} {int(r.precio):,}".replace(",", ".") if r.precio else "-"
        km = f"{r.km:,}".replace(",", ".") if r.km else "-"
        published = (datetime.fromtimestamp(r.published_at, timezone.utc).isoformat()
                     if r.published_at is not None else "desconocida")
        print(_fmt(r.listing_id, 14), _fmt(published, 20), _fmt(precio, 14), _fmt(r.anio, 5),
              _fmt(km, 10), _fmt(r.ubicacion, 18), _fmt(r.titulo, 60))

    print("\nPrimera URL:", results[0].url)
    if not complete:
        sys.exit(2)


if __name__ == "__main__":
    run(main())
