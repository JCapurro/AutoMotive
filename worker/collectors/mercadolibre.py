"""MercadoLibre Argentina scraper.

Uses Playwright against the public search page. The official Mercado Libre
API exposes /sites/MLA/search but it is gated by their PolicyAgent for
non-Partner apps (returns 403 for any query, regardless of OAuth scopes),
so we don't bother with the API path.

Item pages (fetch_detail) are server-rendered and read with a plain GET.
"""
from __future__ import annotations
import asyncio
import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

import config
from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail
from ._browser import browser_context
from ._dates import parse_relative_date
from ._http import dedupe, fetch_page, json_ld_of_type, multiline_text, soup, text_of, to_int


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
        # Security challenge (captcha): never solved automatically, the run fails.
        or ("por seguridad" in text_l and "complet" in text_l and "desaf" in text_l)
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


def _parse_card(card_html: str) -> Listing | None:
    """One search result. Make/model are left to normalization (sección 5.2):
    the card only has the title, and the search filter is not evidence."""
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
        anio=anio,
        km=km,
        ubicacion=location,
        imagenes=[img_url] if img_url else [],
    )


def parse_search(html: str) -> list[Listing]:
    """Cards of a search results page, in page order, without duplicates."""
    doc = BeautifulSoup(html, "lxml")
    out: dict[str, Listing] = {}
    for card in doc.select("li.ui-search-layout__item"):
        listing = _parse_card(str(card))
        if listing and listing.listing_id not in out:
            out[listing.listing_id] = listing
    return list(out.values())


# ---------- detail page ----------

_GONE_TEXTS = ("publicacion pausada", "publicacion finalizada", "esta publicacion esta pausada",
               "esta publicacion finalizo", "publicacion inactiva")


def _plain(s: str) -> str:
    return s.lower().translate(str.maketrans("áéíóú", "aeiou"))


def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
    """An item page (auto.mercadolibre.com.ar/MLA-…)."""
    if status == 404:
        return ListingDetail(url, gone=True, gone_reason="404")
    doc = soup(html)
    page_text = _plain(doc.get_text(" ", strip=True))
    if reason := next((t for t in _GONE_TEXTS if t in page_text), None):
        return ListingDetail(url, gone=True, gone_reason=reason)

    ld = json_ld_of_type(doc, "Vehicle", "Car", "Product") or {}
    offer = ld.get("offers") or {}
    availability = str(offer.get("availability") or "")
    if availability and not availability.endswith("InStock"):
        return ListingDetail(url, gone=True, gone_reason=availability.rsplit("/", 1)[-1])

    title = text_of(doc.select_one("h1.ui-pdp-title")) or ld.get("name")
    lid = _extract_id(url) or (str(ld["sku"]) if ld.get("sku") else None)
    if not title or not lid:
        raise ValueError(f"mercadolibre detail without title/id: {url}")

    # "Características" tables: Marca, Modelo, Año, Versión, Kilómetros, Transmisión…
    specs: dict[str, str] = {}
    for row in doc.select("table tr"):
        th, td = row.select_one("th"), row.select_one("td")
        if th and td and (k := text_of(th)) and (v := text_of(td)):
            specs.setdefault(k, v)

    precio = float(offer["price"]) if offer.get("price") else None
    moneda = {"ARS": "ARS", "USD": "USD"}.get(str(offer.get("priceCurrency") or "").upper())
    if precio is None:
        price_el = doc.select_one(".ui-pdp-price__second-line [data-andes-money-amount='true']")
        meta = price_el.select_one("meta[itemprop='price']") if price_el else None
        if meta and meta.get("content"):
            precio = float(meta["content"])
            sym = text_of(price_el.select_one(".andes-money-amount__currency-symbol")) or ""
            moneda = "USD" if "US" in sym.upper() else "ARS"

    # "2026 | 0 km · Publicado hace 7 meses"
    subtitle = text_of(doc.select_one(".ui-pdp-subtitle, .ui-pdp-header__subtitle")) or ""
    published = re.search(r"publicado\s+(hace\s+.+)$", subtitle, re.IGNORECASE)

    seller_header = _plain(text_of(doc.select_one(".ui-vip-seller-profile__header")) or "")
    vendedor = ("concesionaria" if "concesionaria" in seller_header or "tienda oficial" in seller_header
                else "particular" if "vendedor" in seller_header or "particular" in seller_header
                else None)
    seller_name = text_of(doc.select_one(".ui-pdp-seller-validated__title"))
    if seller_name:
        seller_name = re.sub(r"^publicado por\s+", "", seller_name, flags=re.IGNORECASE)

    images = dedupe([img.get("data-zoom") or img.get("src")
                     for img in doc.select("figure.ui-pdp-gallery__figure img")])
    brand = ld.get("brand")

    return ListingDetail(url, listing=Listing(
        source="mercadolibre",
        listing_id=lid,
        titulo=title,
        url=url,
        precio=precio,
        moneda=moneda,
        marca=specs.get("Marca") or (brand if isinstance(brand, str) else None),
        modelo=specs.get("Modelo"),
        version=specs.get("Versión"),
        anio=to_int(specs.get("Año")),
        km=to_int(specs.get("Kilómetros")),
        combustible=specs.get("Tipo de combustible"),
        transmision=specs.get("Transmisión"),
        vendedor=vendedor,
        vendedor_nombre=seller_name,
        descripcion=multiline_text(doc.select_one(".ui-pdp-description__content")),
        imagenes=images,
        atributos=specs,
        published_at=parse_relative_date(published.group(1)) if published else None,
    ))


# ---------- scraper ----------

def _blocked(page_number: int) -> None:
    """A wall on the first page fails the run; on a later page, keep what we have."""
    log.warning("MercadoLibre requires account verification/login. "
                "Run: python -m collectors.mercadolibre")
    if page_number == 1:
        raise CollectorBlocked("mercadolibre: login wall or security challenge")


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
            try:
                for p in range(1, self.MAX_PAGES + 1):
                    url = _build_url(filters, page=p)
                    try:
                        await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                        if await _page_looks_like_login_wall(page):
                            _blocked(p)
                            break
                        await page.wait_for_selector(
                            "li.ui-search-layout__item, .ui-search-rescue",
                            timeout=15_000,
                        )
                    except CollectorBlocked:
                        raise
                    except Exception as exc:
                        if await _page_looks_like_login_wall(page):
                            _blocked(p)
                        else:
                            log.warning("MercadoLibre scrape failed: %s", exc)
                        break  # no results / blocked
                    if await page.locator(".ui-search-rescue").count() > 0:
                        # ML's "no results" placeholder
                        break
                    cards = parse_search(await page.content())
                    if not cards:
                        break
                    for listing in cards:
                        if listing.listing_id in seen_ids:
                            continue
                        seen_ids.add(listing.listing_id)
                        self.annotate_partial_price(listing)
                        if self.matches_filters(listing, filters):
                            out.append(listing)
            finally:
                await page.close()
        return out

    async def fetch_detail(self, url: str) -> ListingDetail:
        page = await fetch_page(url)
        if _looks_like_login_wall(page.url, text_of(soup(page.html).body) or ""):
            raise CollectorBlocked("mercadolibre: login wall or security challenge")
        return parse_detail(page.html, url, page.status)


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
