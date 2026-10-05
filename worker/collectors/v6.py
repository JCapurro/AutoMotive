"""V6 (v6.com.ar) scraper — AR used cars marketplace.

Listings render client-side via JS. Filters supported via URL:
    brand=<marca>      — e.g. brand=toyota
    model=<modelo>     — e.g. model=corolla
    search=<query>     — free-text fallback
    sortOrder=publicadoMasNuevo — newest first (`sort=recent` is ignored)
Year/price/km filters aren't honored server-side, so we apply them
client-side via BaseScraper.matches_filters.

Card markup uses `tc-v2-*` classes which have been stable since the
2024 redesign. Item pages (`/auto/<slug>-<id>`) carry schema.org JSON-LD
server-side, but the description and the spec grid (`v2-*`) render
client-side, so fetch_detail loads them in the browser.
"""
from __future__ import annotations
import re
import urllib.parse

from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, ListingDetail
from ._browser import browser_context
from ._dates import publication_date
from ._http import Page, dedupe, fetch_rendered, json_ld_of_type, multiline_text, soup, text_of, to_int


_PRICE_RE = re.compile(r"([\d\.\,]+)\s*(USD|U\$S|US\$|\$|ARS)", re.IGNORECASE)
_KM_RE = re.compile(r"([\d\.\,]+)\s*km", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")
_ID_RE = re.compile(r"-([A-Za-z0-9]{10})$")


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _to_int(s: str | None) -> int | None:
    digits = re.sub(r"\D", "", s or "")
    return int(digits) if digits else None


def _parse_price(txt: str) -> tuple[float | None, str | None]:
    m = _PRICE_RE.search(txt or "")
    if not m:
        return None, None
    num, cur = m.groups()
    moneda = "USD" if cur.upper() in ("USD", "U$S", "US$") else "ARS"
    digits = re.sub(r"[^\d]", "", num)
    return (float(digits) if digits else None), moneda


def _listing_id(path: str) -> str:
    """Trailing 10-char alphanumeric segment of /auto/<slug>-<id>."""
    path = path.split("?")[0].rstrip("/")
    m = _ID_RE.search(path)
    return m.group(1) if m else path.rsplit("/", 1)[-1]


_TRANSMISSION_TAGS = {"mt": "Manual", "manual": "Manual", "at": "Automática",
                      "automática": "Automática", "automatica": "Automática",
                      "cvt": "Automática", "dsg": "Automática"}
_FUEL_TAGS = {"nafta", "diésel", "diesel", "gnc", "híbrido", "hibrido", "eléctrico", "electrico"}


def _parse_card(a) -> Listing | None:
    href = a.get("href") or ""
    if not href:
        return None
    title_el = a.select_one(".tc-v2-title")
    version = text_of(a.select_one(".tc-v2-version"))
    title = text_of(title_el) or ""
    if version and version not in title:
        # version is nested inside title; tc-v2-title text already includes it.
        title = f"{title} {version}".strip()

    precio, moneda = _parse_price(text_of(a.select_one(".tc-v2-price")) or "")

    # Detail tags (year, km, transmission, fuel)
    anio = km = transmision = combustible = None
    for tag in a.select(".tc-v2-detail-tag"):
        t = tag.get_text(strip=True)
        if not anio and (m := _YEAR_RE.search(t)):
            anio = int(m.group(1)); continue
        if not km and (m := _KM_RE.search(t)):
            km = _to_int(m.group(1)); continue
        tl = t.lower()
        if not transmision and tl in _TRANSMISSION_TAGS:
            transmision = _TRANSMISSION_TAGS[tl]; continue
        if not combustible and tl in _FUEL_TAGS:
            combustible = t; continue

    img = a.select_one("img.tc-v2-img")
    days = text_of(a.select_one(".tc-v2-days-badge"))

    return Listing(
        source="v6",
        listing_id=_listing_id(href),
        titulo=title[:200] or "(sin título)",
        url="https://www.v6.com.ar" + href.split("?")[0],
        precio=precio,
        moneda=moneda,
        anio=anio,
        km=km,
        ubicacion=text_of(a.select_one(".tc-v2-location")),
        combustible=combustible,
        transmision=transmision,
        version=version,
        published_at=publication_date(a, text=days),
        imagenes=[img["src"]] if img and img.get("src") else [],
    )


def parse_search(html: str) -> list[Listing]:
    doc = BeautifulSoup(html, "lxml")
    out: dict[str, Listing] = {}
    for a in doc.select("a.tc-v2-link[href^='/auto/']"):
        listing = _parse_card(a)
        if listing and listing.listing_id not in out:
            out[listing.listing_id] = listing
    return list(out.values())


def _label_values(doc, cell: str, label: str, value: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in doc.select(cell):
        k, v = text_of(c.select_one(label)), text_of(c.select_one(value))
        if k and v:
            out.setdefault(k, v)
    return out


def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
    doc = soup(html)
    title_tag = text_of(doc.select_one("title")) or ""
    if status == 404 or "no encontrado" in title_tag.lower():
        return ListingDetail(url, gone=True, gone_reason="no encontrado")

    ld = json_ld_of_type(doc, "Car", "Vehicle") or {}
    h1 = doc.select_one("h1")
    if not ld and not h1:
        raise ValueError(f"v6 detail without vehicle data: {url}")

    # "Kilometraje", "Año", "Vendedor", "Transmisión", "Combustible" (stats) and
    # "Marca", "Modelo", "Versión", "Tipo" (data grid).
    specs = _label_values(doc, ".v2-stat-item", ".v2-stat-label", ".v2-stat-value")
    specs.update({k: v for k, v in _label_values(doc, ".v2-data-cell", ".v2-data-label",
                                                 ".v2-data-value").items() if k not in specs})

    precio, moneda = _parse_price(text_of(doc.select_one(".v2-price")) or "")
    location_row = doc.select_one(".v2-location-row")
    published = text_of(location_row.select_one(".top-carousel-item-publisheddate")) \
        if location_row else None
    mileage = (ld.get("mileageFromOdometer") or {}).get("value")
    brand = ld.get("brand") or {}
    images = ld.get("image") or []

    return ListingDetail(url, listing=Listing(
        source="v6",
        listing_id=_listing_id(url),
        titulo=text_of(h1) or ld.get("name") or "(sin título)",
        url=url,
        precio=precio,
        moneda=moneda,
        marca=specs.get("Marca") or (brand.get("name") if isinstance(brand, dict) else brand) or None,
        modelo=specs.get("Modelo") or ld.get("model"),
        version=specs.get("Versión") or text_of(doc.select_one(".v2-version-inline")),
        anio=to_int(specs.get("Año")) or to_int(ld.get("vehicleModelDate")),
        km=to_int(specs.get("Kilometraje")) or to_int(mileage),
        transmision=specs.get("Transmisión"),
        combustible=specs.get("Combustible"),
        ubicacion=text_of(location_row.select_one(".top-carousel-item-location")) if location_row else None,
        vendedor=specs.get("Vendedor") or specs.get("Tipo"),
        descripcion=multiline_text(doc.select_one(".v2-desc-text")),
        imagenes=dedupe(images if isinstance(images, list) else [images]),
        atributos=specs,
        published_at=publication_date(doc, structured=ld, text=published),
    ))


class V6Scraper(BaseScraper):
    DETAIL_PARSER_VERSION = 2
    name = "v6"
    BASE = "https://www.v6.com.ar/publicaciones"

    def _build_url(self, f: dict) -> str:
        qs: dict[str, str] = {"sortOrder": "publicadoMasNuevo"}
        if f.get("marca"):
            qs["brand"] = _slug(f["marca"])
        q_keys = ("modelo", "version") if qs.get("brand") else ("marca", "modelo", "version")
        q = " ".join(str(f[k]).strip().lower() for k in q_keys if f.get(k)).strip()
        if q:
            qs["search"] = q
        return f"{self.BASE}?{urllib.parse.urlencode(qs)}"

    async def search(self, filters: dict) -> list[Listing]:
        url = self._build_url(filters)
        out: list[Listing] = []
        async with browser_context() as ctx:
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=45_000, wait_until="domcontentloaded")
                await page.wait_for_timeout(2_500)
                # v6 uses infinite scroll; load up to ~3 batches
                for _ in range(4):
                    await page.mouse.wheel(0, 5_000)
                    await page.wait_for_timeout(1_000)
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
        return await fetch_rendered(url)
