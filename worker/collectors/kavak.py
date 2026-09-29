"""Kavak Argentina scraper.

Kavak is a SPA — search results render via JS only, so search uses the
shared headless browser. Each card links to `/ar/venta/{slug}` (marca,
modelo, version, year) and carries the car's numeric id in `data-testid`;
the slug is shared by every car of the same version and year, so the id is
the listing id and the detail URL is `/ar/venta/{slug}?id={id}`.

Item pages are server-rendered with schema.org JSON-LD and read with a plain
GET. When a car is sold Kavak serves another car of the same model at that
URL, so fetch_detail compares the page's canonical slug with the one asked for.
"""
from __future__ import annotations
from dataclasses import replace
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, ListingDetail
from ._browser import browser_context
from ._http import Page, dedupe, fetch_page, slim_html, json_ld_of_type, soup, text_of, to_int
from normalization.fx import usd_ars_rate


_KM_RE = re.compile(r"([\d\.\,]+)\s*km", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
_PRICE_RE = re.compile(r"(US\$|u\$s|\$)\s*([\d\.\,]+)", re.IGNORECASE)
_TESTID_RE = re.compile(r"(\d{4,})$")


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _to_int(s: str) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _venta_slug(url: str) -> str:
    return urlparse(url).path.rstrip("/").rsplit("/ar/venta/", 1)[-1]


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
        ubicacion=location,
        vendedor="concesionaria",  # Kavak is dealer-only
        vendedor_nombre="Kavak",
        imagenes=[img["src"]] if img and img.get("src") else [],
    )


def parse_search(html: str) -> list[Listing]:
    doc = BeautifulSoup(html, "lxml")
    out: dict[str, Listing] = {}
    for a in doc.select("a[data-testid][href*='/ar/venta/']"):
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
        ubicacion=location,
        vendedor="concesionaria",
        vendedor_nombre="Kavak",
        # The last JSON-LD image is a promotional banner, not the car.
        imagenes=dedupe([i for i in (images if isinstance(images, list) else [images])
                         if "BANNER" not in str(i).upper()]),
        atributos={k: str(car[k]) for k in ("bodyType", "color", "vehicleConfiguration")
                   if car.get(k)},
    ))


class KavakScraper(BaseScraper):
    name = "kavak"
    BASE = "https://www.kavak.com/ar/usados"

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
        url = self._build_url(filters)
        out: list[Listing] = []
        async with browser_context() as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                # Kavak lazy-loads via scroll
                for _ in range(4):
                    await page.mouse.wheel(0, 4000)
                    await page.wait_for_timeout(900)
                html = await page.content()
            finally:
                await page.close()
        for listing in parse_search(html):
            self.annotate_partial_price(listing)
            if self.matches_filters(listing, filters):
                out.append(listing)
        return out

    parse_detail = staticmethod(parse_detail)

    async def fetch_detail_page(self, url: str) -> Page:
        return await fetch_page(url)

    def slim_page(self, page: Page) -> str:
        # parse_detail() checks the car_id in the page's data script.
        return slim_html(page.html, scripts_with="car_id")
