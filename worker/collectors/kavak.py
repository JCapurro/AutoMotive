"""Kavak Argentina scraper.

Kavak is a SPA — search results render via JS only, so search uses the
shared headless browser, scrolling until no more cards load: the model page
lists every car of the model, whatever its order, so reading all of it
misses no new arrival. Each card links to `/ar/venta/{slug}` (marca,
modelo, version, year) and carries the car's numeric id in `data-testid`;
the slug is shared by every car of the same version and year, so the id is
the listing id and the detail URL is `/ar/venta/{slug}?id={id}`.

Item pages are server-rendered with schema.org JSON-LD and read with a plain
GET. When a car is sold Kavak serves another car of the same model at that
URL, so fetch_detail compares the page's canonical slug with the one asked for.

A target by body type (docs/CARROCERIA.md) reads `/ar/usados/{carroceria}`
with plain GETs instead: Kavak renders those pages on the server, 30 cars a
page, `?page=N` from 0.
"""
from __future__ import annotations
import asyncio
from dataclasses import dataclass, replace
import logging
import random
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, CollectorBlocked, Listing, ListingDetail, SearchResults
from ._dates import publication_date
from ._browser import browser_context
from ._http import Page, dedupe, fetch_page, slim_html, json_ld_of_type, soup, text_of, to_int
from normalization import body_type
from normalization.fx import usd_ars_rate


log = logging.getLogger("collectors.kavak")


_KM_RE = re.compile(r"([\d\.\,]+)\s*km", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
_PRICE_RE = re.compile(r"(US\$|u\$s|\$)\s*([\d\.\,]+)", re.IGNORECASE)
_TESTID_RE = re.compile(r"(\d{4,})$")
_CARD_SELECTOR = "a[data-testid][href*='/ar/venta/']"
# The slug's components are joined by "-", their words by "_": the body
# type is the one before the year ("…-16_se-hatchback-2018").
_SLUG_BODY_RE = re.compile(r"-([a-z_]+)-(?:19|20)\d{2}$")

# Kavak's "Carrocería" filter (/ar/usados/{value}, 15/10/2026) for each code
# it has. Its "camioneta" is an SUV or a pick-up: no code searches it.
BODY_TYPE_SLUGS = {"sedan": "sedan", "hatchback": "hatchback", "suv": "suv", "pickup": "pickup",
                   "rural": "wagon", "monovolumen": "minivan", "utilitario": "van"}


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _to_int(s: str) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _venta_slug(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/ar/venta/", 1)[-1]


def _slug_body(slug: str) -> str | None:
    """The body type the card's slug names, as Kavak writes it ("suv",
    "minivan", "wagon"), when it is one: normalization maps it."""
    m = _SLUG_BODY_RE.search(slug)
    return m.group(1) if m and body_type.from_source(m.group(1)) else None


def _parse_card(a) -> Listing | None:
    href = a.get("href") or ""
    if "/ar/venta/" not in href:
        return None
    full_url = (href if href.startswith("http") else "https://www.kavak.com" + href).split("?")[0]
    slug = _venta_slug(full_url)
    m = _TESTID_RE.search(a.get("data-testid") or "")
    car_id = m.group(1) if m else None
    lid = car_id or slug
    if not lid:
        return None

    # "Ford • Fiesta Kinetic Design" / "2018 • 106.000 km • 1.6 SE • Manual"
    header = text_of(a.select_one("h3"))
    subtitle = text_of(a.select_one("h3 + p")) or ""
    marca = modelo = None
    if header and "•" in header:
        marca, modelo = (p.strip() for p in header.split("•", 1))
    parts = [p.strip() for p in subtitle.split("•")]
    anio = next((int(m.group(1)) for p in parts if (m := _YEAR_RE.fullmatch(p))), None)
    km = next((_to_int(p) for p in parts if _KM_RE.search(p)), None)
    rest = [p for p in parts if p and not _YEAR_RE.fullmatch(p) and not _KM_RE.search(p)]
    transmision = rest[-1] if len(rest) >= 2 else None
    version = rest[0] if rest else None

    lines = [ln.strip() for ln in a.get_text("\n").splitlines() if ln.strip()]
    text = "\n".join(lines)
    # "Precio de contado $ 16.110.000", or on promotions a struck-through
    # "Precio desde $ 15.100.000" followed by the current "$ 14.791.000": the last one counts.
    precio = moneda = None
    if prices := _PRICE_RE.findall(text.replace("\n", " ")):
        sym, num = prices[-1]
        moneda = "USD" if "us" in sym.lower() else "ARS"
        precio = float(_to_int(num) or 0) or None
    location = lines[-1] if lines and not _PRICE_RE.search(lines[-1]) and not _to_int(lines[-1]) else None

    title = " ".join(p for p in (marca, modelo, version, str(anio) if anio else None) if p) \
        or slug.replace("_", " ").replace("-", " ").title()
    img = a.select_one("img")
    return Listing(
        source="kavak",
        listing_id=lid,
        titulo=title[:200],
        url=f"{full_url}?id={car_id}" if car_id else full_url,
        precio=precio,
        moneda=moneda,
        marca=marca,
        modelo=modelo,
        version=version,
        anio=anio or (int(m.group(1)) if (m := _YEAR_RE.search(slug)) else None),
        km=km,
        transmision=transmision,
        carroceria=_slug_body(slug),
        ubicacion=location,
        vendedor="concesionaria",  # Kavak is dealer-only
        vendedor_nombre="Kavak",
        published_at=publication_date(a),
        imagenes=[img["src"]] if img and img.get("src") else [],
    )


def parse_search(html: str) -> list[Listing]:
    doc = BeautifulSoup(html, "lxml")
    out: dict[str, Listing] = {}
    for a in doc.select(_CARD_SELECTOR):
        listing = _parse_card(a)
        if listing and listing.listing_id not in out:
            out[listing.listing_id] = listing
    return list(out.values())


def _shows_car(html: str, car_id: str) -> bool:
    """The page's data names the car it shows: …"car_id":549997,… (JSON, maybe escaped)."""
    return re.search(r'car_id\\*"\s*:\s*' + re.escape(car_id) + r'(?!\d)', html) is not None


def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
    if status == 404:
        return ListingDetail(url, gone=True, gone_reason="404")
    doc = soup(html)
    car = json_ld_of_type(doc, "Car", "Vehicle")
    if not car:
        return ListingDetail(url, gone=True, gone_reason="sin vehículo en la página")
    asked = _venta_slug(url)
    served = _venta_slug(str(car.get("url") or ""))
    car_id = (parse_qs(urlparse(url).query).get("id") or [None])[0]
    if served != asked or (car_id and not _shows_car(html, car_id)):
        return ListingDetail(url, gone=True, gone_reason="la página muestra otro auto")

    offer = car.get("offers") or {}
    brand = car.get("brand") or {}
    engine = car.get("vehicleEngine") or {}
    images = car.get("image") or []
    # "106.000 km • Buenos Aires" under the title.
    location = None
    for line in doc.get_text("\n", strip=True).splitlines():
        if " km • " in line:
            location = line.split("•", 1)[1].strip()
            break
    return ListingDetail(url, listing=Listing(
        source="kavak",
        listing_id=car_id or asked,
        titulo=str(car.get("name") or asked),
        url=url,
        precio=float(offer["price"]) if offer.get("price") else None,
        moneda={"ARS": "ARS", "USD": "USD"}.get(str(offer.get("priceCurrency") or "").upper()),
        marca=brand.get("name") if isinstance(brand, dict) else brand,
        modelo=car.get("model"),
        version=car.get("vehicleConfiguration"),
        anio=to_int(car.get("vehicleModelDate")),
        km=to_int((car.get("mileageFromOdometer") or {}).get("value")),
        transmision=car.get("vehicleTransmission"),
        combustible=engine.get("fuelType") if isinstance(engine, dict) else None,
        carroceria=car["bodyType"] if isinstance(car.get("bodyType"), str) else None,
        ubicacion=location,
        vendedor="concesionaria",
        vendedor_nombre="Kavak",
        published_at=publication_date(doc, structured=car),
        # The last JSON-LD image is a promotional banner, not the car.
        imagenes=dedupe([i for i in (images if isinstance(images, list) else [images])
                         if "BANNER" not in str(i).upper()]),
        atributos={k: str(car[k]) for k in ("bodyType", "color", "vehicleConfiguration")
                   if car.get(k)},
    ))


class BodyTypeNotApplied(RuntimeError):
    """A /ar/usados page of a search by body type that doesn't show the filter
    applied. The run fails."""


@dataclass(frozen=True)
class ListState:
    """What a /ar/usados page says about itself in its Next.js flight data
    (JSON inside JS strings, quotes escaped): the body types of its applied
    filter, its page count and its result count."""
    body_types: frozenset[str]
    pages: int | None
    total: int | None


def list_state(html: str) -> ListState:
    text = html.replace('\\"', '"')
    active = re.search(r'"active":\[(.*?)\]', text)
    pages = re.search(r'"pagination":\{"pages":(\d+)', text)
    total = re.search(r'"resultsQuantity":"(\d[\d.]*) Resultados?"', text)
    return ListState(
        body_types=frozenset(re.findall(r'"key":"body_type","value":"([^"]+)"', active.group(1))
                             if active else ()),
        pages=int(pages.group(1)) if pages else None,
        total=to_int(total.group(1)) if total else None,
    )


def _searched_body_type(filters: dict) -> str | None:
    """The code a target by body type searches (docs/CARROCERIA.md):
    filters["carroceria"] without a make or model. None for any other search."""
    code = filters.get("carroceria")
    if not code or filters.get("marca") or filters.get("modelo"):
        return None
    return str(code)


async def _get_list(url: str) -> str:
    page = await fetch_page(url, timeout=45.0)
    if page.status in (403, 429):
        raise CollectorBlocked(f"kavak search: HTTP {page.status}; destination={url}")
    if page.status >= 400:
        raise RuntimeError(f"kavak search HTTP {page.status}: {url}")
    return page.html


async def _page_pause() -> None:
    await asyncio.sleep(random.uniform(2.0, 4.0))


class KavakScraper(BaseScraper):
    DETAIL_PARSER_VERSION = 2
    name = "kavak"
    BASE = "https://www.kavak.com/ar/usados"
    MAX_SCROLLS = 30
    BODY_TYPES = frozenset(BODY_TYPE_SLUGS)
    # The pages of a body type a run reads at most: SUV had 15 (422 cars) on
    # 15/10/2026, the whole catalog 47.
    MAX_BODY_TYPE_PAGES = 40

    @staticmethod
    def matches_filters(item: Listing, f: dict) -> bool:
        filters = {k: v for k, v in f.items() if k != "vendedor"}
        wanted_currency = (filters.get("moneda") or "").upper()
        item_currency = (item.moneda or "").upper()
        if item.precio and wanted_currency and item_currency and wanted_currency != item_currency:
            rate = usd_ars_rate()
            if wanted_currency == "USD" and item_currency == "ARS":
                item = replace(item, precio=item.precio / rate, moneda="USD")
            elif wanted_currency == "ARS" and item_currency == "USD":
                item = replace(item, precio=item.precio * rate, moneda="ARS")
        return BaseScraper.matches_filters(item, filters)

    def _build_url(self, f: dict) -> str:
        parts = [_slug(f[k]) for k in ("marca", "modelo") if f.get(k)]
        if not parts:
            return self.BASE
        return f"{self.BASE}/" + "-".join(parts)

    async def search(self, filters: dict) -> list[Listing]:
        if code := _searched_body_type(filters):
            return await self._search_body_type(filters, code)
        url = self._build_url(filters)
        out: list[Listing] = []
        async with browser_context() as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                # Kavak lazy-loads via scroll: stop once two scrolls in a row add no card.
                counts: list[int] = []
                for _ in range(self.MAX_SCROLLS):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(900)
                    counts.append(await page.locator(_CARD_SELECTOR).count())
                    if len(counts) >= 4 and counts[-1] == counts[-2] == counts[-3]:
                        break
                html = await page.content()
            finally:
                await page.close()
        for listing in parse_search(html):
            self.annotate_partial_price(listing)
            if self.matches_filters(listing, filters):
                out.append(listing)
        return out

    async def _search_body_type(self, filters: dict, code: str) -> SearchResults:
        """A target by body type: the pages of /ar/usados/{slug} up to the
        count the first one states (or one without new cars), at most
        MAX_BODY_TYPE_PAGES.

        Each card's slug names its body. A card whose slug doesn't gets the
        code, and only from a page that shows the filter applied; a page that
        doesn't show it fails the run: Kavak ignoring the filter would serve
        its whole catalog."""
        slug = BODY_TYPE_SLUGS.get(code)
        if not slug:
            raise ValueError(f"kavak: no listing for body type {code!r}")
        results = SearchResults()
        seen: set[str] = set()
        page, pages = 0, None
        try:
            while pages is None or page < pages:
                if page >= self.MAX_BODY_TYPE_PAGES:
                    results.complete = False
                    results.reason = (f"kavak: read the first {page} pages of /ar/usados/{slug}"
                                      + (f", of {pages}" if pages else ""))
                    break
                if page:
                    await _page_pause()
                url = f"{self.BASE}/{slug}" + (f"?page={page}" if page else "")
                html = await _get_list(url)
                state = list_state(html)
                cards = parse_search(html)
                if not cards:
                    if page == 0 and state.total != 0:
                        raise RuntimeError(f"kavak: {url} shows no cars and doesn't say it has none")
                    break
                if slug not in state.body_types:
                    raise BodyTypeNotApplied(f"kavak: {url} doesn't show its body type filter applied")
                pages = pages or state.pages
                page += 1
                fresh = [c for c in cards if c.listing_id not in seen]
                if not fresh:
                    if pages is not None and page < pages:
                        results.complete, results.reason = False, "kavak: pagination repeated a page"
                    break
                for listing in fresh:
                    seen.add(listing.listing_id)
                    if body_type.from_source(listing.carroceria) is None:
                        listing.carroceria = code
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        results.append(listing)
        except BodyTypeNotApplied:
            raise
        except Exception as exc:
            if not seen:
                raise
            results.complete, results.reason = False, f"kavak: {type(exc).__name__}: {exc}"
        log.info("kavak body type %s: pages=%d of %s kept=%d complete=%s reason=%s",
                 code, page, pages, len(results), results.complete, results.reason)
        return results

    parse_detail = staticmethod(parse_detail)

    async def fetch_detail_page(self, url: str) -> Page:
        return await fetch_page(url)

    def slim_page(self, page: Page) -> str:
        # parse_detail() checks the car_id in the page's data script.
        return slim_html(page.html, scripts_with="car_id")
