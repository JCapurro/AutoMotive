"""MercadoLibre Argentina scraper.

Uses Playwright against the public search page. The official Mercado Libre
API exposes /sites/MLA/search but it is gated by their PolicyAgent for
non-Partner apps (returns 403 for any query, regardless of OAuth scopes),
so we don't bother with the API path.
"""
from __future__ import annotations
import asyncio
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

import config
from .base import BaseScraper, Listing
from ._browser import browser_context


log = logging.getLogger("collectors.mercadolibre")


def _browser_storage_state() -> str | None:
    """Return the saved MercadoLibre browser session, if it exists."""
    return config.ML_STORAGE_STATE if Path(config.ML_STORAGE_STATE).exists() else None


def _looks_like_login_wall(url: str, body_text: str = "") -> bool:
    url_l = (url or "").lower()
    text_l = (body_text or "").lower()
    return (
        "account-verification" in url_l
        or "/login" in url_l
        or ("para continuar" in text_l and "ingresa" in text_l)
    )


async def _page_looks_like_login_wall(page) -> bool:
    try:
        body_text = await page.locator("body").inner_text(timeout=2_000)
    except Exception:
        body_text = ""
    return _looks_like_login_wall(page.url, body_text)


# ---------- URL building ----------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(s: str) -> str:
    s = s.lower().strip()
    # strip accents minimally
    repl = str.maketrans("áéíóúñü", "aeiounu")
    s = s.translate(repl)
    return _SLUG_RE.sub("-", s).strip("-")


def _build_url(filters: dict, page: int = 1) -> str:
    """Build a MercadoLibre Argentina autos search URL."""
    parts: list[str] = []
    for k in ("marca", "modelo", "version"):
        v = filters.get(k)
        if v:
            parts.append(_slug(str(v)))
    slug = "-".join(parts) if parts else ""

    base = "https://listado.mercadolibre.com.ar"
    path = f"/autos/{slug}" if slug else "/autos"

    # ML encodes filters as _Filter_value pairs appended to the path
    suffix_segments: list[str] = []

    if filters.get("anio_min") or filters.get("anio_max"):
        lo = int(filters["anio_min"]) if filters.get("anio_min") else 1990
        hi = int(filters["anio_max"]) if filters.get("anio_max") else 2030
        suffix_segments.append(f"_VEHICLE*YEAR_{lo}-{hi}")

    if filters.get("km_max"):
        suffix_segments.append(f"_KILOMETERS_0-{int(filters['km_max'])}km")

    suffix_segments.append("_OrderId_BEGIN")  # newest first
    suffix_segments.append("_NoIndex_True")

    if page > 1:
        suffix_segments.append(f"_Desde_{(page - 1) * 48 + 1}")

    return base + path + "".join(suffix_segments)


# ---------- card parsing ----------

_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
_KM_RE = re.compile(r"([\d\.\,]+)\s*Km", re.IGNORECASE)


def _to_int(s: str) -> int | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


def _extract_id(href: str) -> str | None:
    if not href:
        return None
    m = re.search(r"MLA-?(\d+)", href)
    return f"MLA{m.group(1)}" if m else None


def _parse_card(card_html: str, fallback: dict) -> Listing | None:
    soup = BeautifulSoup(card_html, "lxml")

    a = soup.select_one("a.poly-component__title")
    if not a:
        return None
    href = a.get("href", "").split("#")[0]
    title = a.get_text(strip=True)
    lid = _extract_id(href)
    if not lid:
        return None

    # price
    precio: float | None = None
    moneda: str | None = None
    money_el = soup.select_one("[data-andes-money-amount='true']")
    if money_el:
        sym = money_el.select_one(".andes-money-amount__currency-symbol")
        frac = money_el.select_one(".andes-money-amount__fraction")
        cents = money_el.select_one(".andes-money-amount__cents")
        if frac:
            digits = re.sub(r"\D", "", frac.get_text())
            if digits:
                precio = float(digits)
                if cents:
                    cents_d = re.sub(r"\D", "", cents.get_text())
                    if cents_d:
                        precio += float(f"0.{cents_d}")
        # currency from aria-label
        aria = (money_el.get("aria-label") or "").lower()
        if "dólar" in aria or "dolar" in aria or "us$" in aria or sym and sym.get_text(strip=True) == "US$":
            moneda = "USD"
        elif sym and sym.get_text(strip=True) in ("$", "ARS"):
            moneda = "ARS"

    # attributes (year, km)
    anio = km = None
    for li in soup.select("li.poly-attributes_list__item"):
        txt = li.get_text(strip=True)
        if not anio and (m := _YEAR_RE.search(txt)):
            anio = int(m.group(1))
            continue
        if not km and (m := _KM_RE.search(txt)):
            km = _to_int(m.group(1))

    location = None
    loc_el = soup.select_one(".poly-component__location")
    if loc_el:
        location = loc_el.get_text(strip=True)

    img = soup.select_one("img.poly-component__picture")
    img_url = img.get("src") if img else None

    return Listing(
        source="mercadolibre",
        listing_id=lid,
        titulo=title,
        url=href,
        precio=precio,
        moneda=moneda,
        marca=fallback.get("marca"),
        modelo=fallback.get("modelo"),
        anio=anio,
        km=km,
        ubicacion=location,
        extra={"img": img_url} if img_url else {},
    )


# ---------- scraper ----------

class MercadoLibreScraper(BaseScraper):
    name = "mercadolibre"

    MAX_PAGES = 2  # first 96 results per run is plenty for "newest" sort

    async def search(self, filters: dict) -> list[Listing]:
        out: list[Listing] = []
        seen_ids: set[str] = set()
        storage_state = _browser_storage_state()
        if not storage_state:
            log.warning(
                "MercadoLibre browser session missing at %s. Run: python -m collectors.mercadolibre",
                config.ML_STORAGE_STATE,
            )
        async with browser_context(storage_state=storage_state) as ctx:
            page = await ctx.new_page()
            for p in range(1, self.MAX_PAGES + 1):
                url = _build_url(filters, page=p)
                try:
                    await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                    if await _page_looks_like_login_wall(page):
                        log.warning(
                            "MercadoLibre requires account verification/login. Run: python -m collectors.mercadolibre"
                        )
                        break
                    await page.wait_for_selector(
                        "li.ui-search-layout__item, .ui-search-rescue",
                        timeout=15_000,
                    )
                except Exception as exc:
                    if await _page_looks_like_login_wall(page):
                        log.warning(
                            "MercadoLibre requires account verification/login. Run: python -m collectors.mercadolibre"
                        )
                    else:
                        log.warning("MercadoLibre scrape failed: %s", exc)
                    break  # no results / blocked
                if await page.locator(".ui-search-rescue").count() > 0:
                    # ML's "no results" placeholder
                    break
                cards = await page.locator("li.ui-search-layout__item").all()
                if not cards:
                    break
                for c in cards:
                    try:
                        html = await c.inner_html()
                    except Exception:
                        continue
                    listing = _parse_card(html, filters)
                    if not listing or listing.listing_id in seen_ids:
                        continue
                    seen_ids.add(listing.listing_id)
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        out.append(listing)
            await page.close()
        return out


# ------ Interactive login: `python -m collectors.mercadolibre` ------
async def _login_and_save() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(locale="es-AR")
        page = await ctx.new_page()
        await page.goto("https://www.mercadolibre.com.ar/")
        print(
            "Inicia sesion o completa la verificacion de MercadoLibre en la ventana abierta. "
            "Cuando puedas ver el sitio normalmente, volve a esta consola y presiona Enter."
        )
        await asyncio.get_event_loop().run_in_executor(None, input, "")
        await ctx.storage_state(path=config.ML_STORAGE_STATE)
        print(f"[mercadolibre] sesion guardada en {config.ML_STORAGE_STATE}")
        await ctx.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(_login_and_save())
