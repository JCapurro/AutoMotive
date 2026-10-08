"""MercadoLibre Argentina scraper.

Search and detail pages use installed, visible Chrome with a dedicated
persistent profile, matching Tecc's transport. Manual verification opens that
same profile; a cookie snapshot in a fresh headless context is not used.
"""
from __future__ import annotations
import asyncio
import logging
import random
import re
from urllib.parse import urlsplit, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import config
from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail, SearchResults
from ._recency import PublicationWindow
from ._mercadolibre_browser import mercadolibre_context, shutdown as mercadolibre_shutdown
from ._dates import publication_date
from ._http import Page, dedupe, json_ld_of_type, multiline_text, soup, text_of, to_int


log = logging.getLogger("collectors.mercadolibre")


def _wall_reason(url: str, body_text: str = "") -> str | None:
    url_l = (url or "").lower()
    text_l = (body_text or "").lower()
    if "/captcha/" in url_l or ("por seguridad" in text_l and "complet" in text_l and "desaf" in text_l):
        return "security challenge"
    if ("account-verification" in url_l or "/login" in url_l
            or ("para continuar" in text_l and ("ingresa" in text_l or "ingresá" in text_l))):
        return "login required"
    return None


def _looks_like_login_wall(url: str, body_text: str = "") -> bool:
    return _wall_reason(url, body_text) is not None


async def _page_wall_reason(page) -> str | None:
    try:
        body_text = await page.locator("body").inner_text(timeout=2_000)
    except Exception:
        body_text = ""
    return _wall_reason(page.url, body_text)


def _safe_url(url: str) -> str:
    """Log the destination without login query parameters or fragments."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}{parts.path}"


async def _page_pause() -> None:
    await asyncio.sleep(random.uniform(3.0, 5.5))


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
        published_at=publication_date(soup),
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


def _search_link(html: str, current_url: str, *, today: bool = False) -> str | None:
    """Follow the site's date/pagination links without inventing filter suffixes."""
    doc = soup(html)
    if today:
        anchors = [a for a in doc.select("a[href]")
                   if _plain(a.get_text(" ", strip=True)).startswith("publicados hoy")]
    else:
        anchors = doc.select(".andes-pagination__button--next a[href], a[rel='next']")
    for a in anchors:
        if a.get("aria-disabled") == "true" or a.find_parent(attrs={"aria-disabled": "true"}):
            continue
        url = urljoin(current_url, a.get("href", ""))
        parts = urlsplit(url)
        if (parts.scheme == "https" and parts.hostname in {
                "listado.mercadolibre.com.ar", "autos.mercadolibre.com.ar", "vehiculos.mercadolibre.com.ar"}
                and url != current_url):
            return url
    return None


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
    published = re.search(r"publicad[oa]\s+(.+)$", subtitle, re.IGNORECASE)

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
        published_at=publication_date(doc, structured=ld,
                                      text=published.group(1) if published else None),
    ))


# ---------- scraper ----------

def _blocked(page_number: int, reason: str, url: str, status: int) -> None:
    """A wall on the first page fails the run; on a later page, keep what we have."""
    message = f"mercadolibre: {reason}; HTTP {status}; destination={_safe_url(url)}"
    log.warning(
        "%s. Complete verification in the existing Chrome window, or stop the worker "
        "before running python -m collectors.mercadolibre; restart it after verification.",
        message,
    )
    if page_number == 1:
        raise CollectorBlocked(message)


class MercadoLibreScraper(BaseScraper):
    DETAIL_PARSER_VERSION = 2
    name = "mercadolibre"

    MAX_PAGES = 2  # first 96 results per run is plenty for "newest" sort

    async def search(self, filters: dict) -> list[Listing]:
        if window := PublicationWindow.from_filters(filters):
            return await self._search_recent(filters, window)
        out: list[Listing] = []
        seen_ids: set[str] = set()
        async with mercadolibre_context() as ctx:
            page = await ctx.new_page()
            try:
                for p in range(1, self.MAX_PAGES + 1):
                    if p > 1:
                        await _page_pause()
                    url = _build_url(filters, page=p)
                    status = 0
                    try:
                        response = await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                        status = response.status if response else 0
                        if reason := await _page_wall_reason(page):
                            _blocked(p, reason, page.url, status)
                            break
                        if status >= 400:
                            raise RuntimeError(f"mercadolibre search HTTP {status}: {_safe_url(page.url)}")
                        await page.wait_for_selector(
                            "li.ui-search-layout__item, .ui-search-rescue",
                            timeout=15_000,
                        )
                    except CollectorBlocked:
                        raise
                    except Exception as exc:
                        if reason := await _page_wall_reason(page):
                            _blocked(p, reason, page.url, status)
                        else:
                            if p == 1:
                                raise
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

    async def _publication_date(self, ctx, listing: Listing) -> int | None:
        """Cards often omit dates: read the ad instead of using detection time."""
        page = await ctx.new_page()
        try:
            response = await page.goto(listing.url, timeout=45_000, wait_until="domcontentloaded")
            status = response.status if response else 0
            if reason := await _page_wall_reason(page):
                raise CollectorBlocked(f"mercadolibre date: {reason}")
            if status >= 400 and status != 404:
                raise RuntimeError(f"mercadolibre date HTTP {status}")
            if status != 404:
                try:
                    await page.wait_for_selector(".ui-pdp-container, h1.ui-pdp-title", timeout=8_000)
                except PlaywrightTimeoutError:
                    pass
            if reason := await _page_wall_reason(page):
                raise CollectorBlocked(f"mercadolibre date: {reason}")
            detail = parse_detail(await page.content(), listing.url, status)
            return detail.listing.published_at if detail.listing else None
        finally:
            await page.close()

    async def _search_recent(self, filters: dict, window: PublicationWindow) -> SearchResults:
        results = SearchResults()
        seen: set[str] = set()
        visited: set[str] = set()
        known = filters.get("known_publication_dates") or {}
        async with mercadolibre_context() as ctx:
            page = await ctx.new_page()
            url = _build_url(filters)
            today_checked = not window.today_only
            pages = 0
            try:
                while True:
                    if url in visited:
                        results.complete, results.reason = False, "mercadolibre: pagination repeated a page"
                        break
                    visited.add(url)
                    if pages:
                        await _page_pause()
                    response = await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                    status = response.status if response else 0
                    if reason := await _page_wall_reason(page):
                        raise CollectorBlocked(f"mercadolibre search: {reason}")
                    if status >= 400:
                        raise RuntimeError(f"mercadolibre search HTTP {status}")
                    await page.wait_for_selector("li.ui-search-layout__item, .ui-search-rescue", timeout=15_000)
                    html = await page.content()
                    if not today_checked:
                        today_checked = True
                        if today_url := _search_link(html, page.url, today=True):
                            url = today_url
                            continue
                        log.warning("MercadoLibre has no Publicados hoy link; verifying dates on unfiltered results")
                    if soup(html).select_one(".ui-search-rescue") is not None:
                        break
                    cards = parse_search(html)
                    if not cards:
                        raise ValueError("mercadolibre: result cards exist but none could be parsed")
                    pages += 1
                    for listing in cards:
                        if listing.listing_id in seen:
                            continue
                        seen.add(listing.listing_id)
                        self.annotate_partial_price(listing)
                        if not self.matches_filters(listing, filters):
                            continue
                        if listing.published_at is None:
                            listing.published_at = known.get(listing.listing_id)
                        if listing.published_at is None:
                            await asyncio.sleep(config.RECENT_ML_DETAIL_SECONDS)
                            try:
                                listing.published_at = await self._publication_date(ctx, listing)
                            except CollectorBlocked:
                                raise
                            except Exception as exc:
                                results.complete, results.reason = False, f"mercadolibre date fetch failed: {type(exc).__name__}"
                                log.warning("Could not read publication date for %s: %s", listing.listing_id, exc)
                        if listing.published_at is None:
                            results.unknown_dates += 1
                        elif window.contains(listing):
                            results.append(listing)
                    next_url = _search_link(html, page.url)
                    if not next_url:
                        break
                    if pages >= config.RECENT_ML_MAX_PAGES:
                        results.complete, results.reason = False, "mercadolibre: publication scan page limit reached"
                        break
                    url = next_url
            except Exception as exc:
                if not seen:
                    raise
                results.complete, results.reason = False, f"mercadolibre: {type(exc).__name__}: {exc}"
            finally:
                await page.close()
        log.info("mercadolibre publication window: pages=%d kept=%d unknown_dates=%d complete=%s reason=%s",
                 pages, len(results), results.unknown_dates, results.complete, results.reason)
        return results

    parse_detail = staticmethod(parse_detail)

    async def fetch_detail_page(self, url: str) -> Page:
        async with mercadolibre_context() as ctx:
            page = await ctx.new_page()
            try:
                response = await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                status = response.status if response else 0
                if reason := await _page_wall_reason(page):
                    _blocked(1, reason, page.url, status)
                if status >= 400 and status != 404:
                    raise RuntimeError(f"mercadolibre detail HTTP {status}: {_safe_url(page.url)}")
                if status != 404:
                    try:
                        await page.wait_for_selector(".ui-pdp-container, h1.ui-pdp-title", timeout=8_000)
                    except PlaywrightTimeoutError:
                        # Paused/finalized ads may lack the normal PDP container.
                        # The parser handles them, after checking for a wall.
                        pass
                    if reason := await _page_wall_reason(page):
                        _blocked(1, reason, page.url, status)
                return Page(status, page.url, await page.content())
            finally:
                await page.close()


# ------ Interactive login: `python -m collectors.mercadolibre` ------
async def _wait_for_enter() -> None:
    await asyncio.to_thread(input, "")


async def _login_and_save() -> None:
    async with mercadolibre_context() as ctx:
        page = await ctx.new_page()
        try:
            while True:
                response = await page.goto(_build_url({}), timeout=45_000, wait_until="domcontentloaded")
                status = response.status if response else 0
                if not await _page_wall_reason(page):
                    try:
                        await page.wait_for_selector("li.ui-search-layout__item", timeout=15_000)
                    except PlaywrightTimeoutError:
                        pass
                    if status == 200 and await page.locator("li.ui-search-layout__item").count() > 0:
                        print(f"[mercadolibre] busqueda verificada; perfil guardado en {config.ML_BROWSER_PROFILE_DIR}")
                        return
                print(
                    "La busqueda sigue bloqueada o sin publicaciones. Completa el ingreso/verificacion "
                    "en esta ventana de Chrome y presiona Enter para volver a comprobar."
                )
                await _wait_for_enter()
        finally:
            await page.close()


if __name__ == "__main__":
    async def _interactive_main() -> None:
        try:
            await _login_and_save()
        finally:
            await mercadolibre_shutdown()

    asyncio.run(_interactive_main())
