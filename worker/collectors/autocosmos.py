"""AutoCosmos AR scraper.

AutoCosmos exposes a public listings page at
`/auto/usado/{marca}/{modelo}` with rich schema.org microdata, no login,
no anti-bot. Filters are applied client-side via BaseScraper.matches_filters
because the site's server-side filters aren't always honored via URL params.

Many dealer ads show only the down payment ("Anticipo") and the installment:
those cards are kept but flagged as partial prices, so they never feed
comparables or opportunities.
"""
from __future__ import annotations
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, Listing, ListingDetail
from ._http import HEADERS, Page, dedupe, fetch_page, multiline_text, soup, text_of, to_int


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _to_int(s: str | None) -> int | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


def _price(container, block: str) -> tuple[float | None, str | None, str | None]:
    """(price, currency, partial reason) from the price blocks of a card or detail.

    A plain price wins. With only "Anticipo" / "Cuotas desde", the down
    payment is kept as the price and flagged as partial.
    """
    blocks = container.select(block)
    full = next((b for b in blocks if not {"m-anticipo", "m-cuota"} & set(b.get("class") or [])), None)
    anticipo = next((b for b in blocks if "m-anticipo" in (b.get("class") or [])), None)
    chosen, reason = (full, None) if full else (anticipo, "anticipo (autocosmos)") if anticipo \
        else (blocks[0] if blocks else None, "cuota (autocosmos)" if blocks else None)
    if chosen is None:
        return None, None, None
    value = chosen.select_one("[itemprop='price']")
    currency = chosen.select_one("meta[itemprop='priceCurrency']")
    amount = _to_int(value.get("content") or value.get_text()) if value else None
    return (float(amount) if amount else None,
            (currency.get("content") if currency else None) or None,
            reason)


class AutoCosmosScraper(BaseScraper):
    name = "autocosmos"
    BASE = "https://www.autocosmos.com.ar"
    MAX_PAGES = 2

    def _build_url(self, f: dict, page: int = 1) -> str:
        marca = _slug(f.get("marca", "")) if f.get("marca") else ""
        modelo = _slug(f.get("modelo", "")) if f.get("modelo") else ""

        if marca and modelo:
            path = f"/auto/usado/{marca}/{modelo}"
        elif marca:
            path = f"/auto/usado/{marca}"
        else:
            path = "/auto/usado"

        qs: dict[str, str] = {}
        if page > 1:
            qs["page"] = str(page)
        if f.get("anio_min"):
            qs["yearMin"] = str(int(f["anio_min"]))
        if f.get("anio_max"):
            qs["yearMax"] = str(int(f["anio_max"]))
        if f.get("precio_min"):
            qs["priceMin"] = str(int(f["precio_min"]))
        if f.get("precio_max"):
            qs["priceMax"] = str(int(f["precio_max"]))
        if f.get("moneda"):
            qs["currency"] = f["moneda"].upper()

        return self.BASE + path + ("?" + urllib.parse.urlencode(qs) if qs else "")

    @staticmethod
    def _parse_article(art) -> Listing | None:
        a = art.select_one("a[itemprop='url']")
        if not a:
            return None
        href = a.get("href") or ""
        if not href:
            return None
        # listing id is the trailing GUID segment
        m = re.search(r"/([0-9a-f]{32})(?:/|$)", href)
        lid = m.group(1) if m else href.rsplit("/", 1)[-1]
        full_url = href if href.startswith("http") else "https://www.autocosmos.com.ar" + href

        marca_el = art.select_one(".listing-card__brand")
        modelo_el = art.select_one(".listing-card__model")
        version_el = art.select_one(".listing-card__version")
        meta_name = art.select_one("meta[itemprop='name']")
        # Build title from brand+model+version (richer than the bare itemprop name)
        title_pieces = [text_of(marca_el), text_of(modelo_el), text_of(version_el)]
        title = " ".join(p for p in title_pieces if p).strip() or \
                (meta_name.get("content") if meta_name else "")
        year_el = art.select_one(".listing-card__year")
        km_el = art.select_one(".listing-card__km")
        city_el = art.select_one(".listing-card__city")
        prov_el = art.select_one(".listing-card__province")
        img = art.select_one("img[itemprop='image'], figure img")

        anio = _to_int(year_el.get_text() if year_el else None)
        # km element has both content="KMT 150000" and inner text "150000 km"
        km = None
        if km_el:
            content = km_el.get("content") or km_el.get_text() or ""
            km = _to_int(content)

        precio, moneda, partial = _price(art, ".listing-card__price")

        # City field sometimes has trailing " | " — strip that and join with province
        city = city_el.get_text(strip=True).rstrip("|").strip() if city_el else ""
        prov = prov_el.get_text(strip=True) if prov_el else ""
        ubic = ", ".join(p for p in (city, prov) if p) or None
        dealer_logo = art.select_one(".listing-card__logoimg img")

        return Listing(
            source="autocosmos",
            listing_id=lid,
            titulo=title[:200],
            url=full_url,
            precio=precio,
            moneda=moneda,
            marca=text_of(marca_el),
            modelo=text_of(modelo_el),
            version=text_of(version_el),
            anio=anio,
            km=km,
            ubicacion=ubic,
            vendedor="concesionaria" if dealer_logo else None,
            price_partial=partial is not None,
            price_partial_reason=partial,
            imagenes=[img.get("src")] if img and img.get("src") else [],
        )

    @classmethod
    def parse_search(cls, html: str) -> list[Listing]:
        doc = BeautifulSoup(html, "lxml")
        out: dict[str, Listing] = {}
        for art in doc.select("article.listing-card, article[itemtype*='Car']"):
            listing = cls._parse_article(art)
            if listing and listing.listing_id not in out:
                out[listing.listing_id] = listing
        return list(out.values())

    @staticmethod
    def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
        if status in (404, 410):
            return ListingDetail(url, gone=True, gone_reason=str(status))
        doc = soup(html)
        # The first Car is the ad; the ones after it are "related listings" cards.
        car = doc.select_one("article[itemscope][itemtype*='Car']")
        if car is None or car.select_one(".car-specifics__name") is None:
            return ListingDetail(url, gone=True, gone_reason="sin vehículo en la página")

        def meta(prop: str) -> str | None:
            el = car.select_one(f"meta[itemprop='{prop}']")
            return el.get("content") if el else None

        specs: dict[str, str] = {}
        for row in car.select("table.ficha tr"):
            cells = row.select("td")
            if len(cells) == 2 and (k := text_of(cells[0])) and (v := text_of(cells[1])):
                specs.setdefault(k, v)
        precio, moneda, partial = _price(car, ".car-specifics__price")
        city = text_of(car.select_one("[itemprop='addressLocality']"))
        region = text_of(car.select_one("[itemprop='addressRegion']"))
        km_el = car.select_one("[itemprop='mileageFromOdometer']")
        seller = text_of(car.select_one(".seller-name-container"))
        dealer = car.select_one(".seller-name-container a[href], .concessionaire-group")
        logo = car.select_one(".seller-name-container img[alt]")
        images = [el.get("content") for el in car.select("meta[itemprop='image']")]
        images += [(img.get("src") or "").replace("/Small/", "/Large/")
                   for img in car.select(".car-specifics__image img")]
        m = re.search(r"/([0-9a-f]{32})(?:/|$)", url)

        return ListingDetail(url, listing=Listing(
            source="autocosmos",
            listing_id=m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1],
            titulo=text_of(car.select_one(".car-specifics__name")) or meta("name") or "",
            url=url,
            precio=precio,
            moneda=moneda,
            marca=meta("brand"),
            modelo=text_of(car.select_one(".car-specifics__model")) or meta("model"),
            version=text_of(car.select_one(".car-specifics__version")),
            anio=to_int(text_of(car.select_one("[itemprop='modelDate']"))),
            km=to_int(km_el.get_text() if km_el else None),
            transmision=specs.get("Transmisión"),
            combustible=specs.get("Combustible"),
            ubicacion=", ".join(p for p in (city, region) if p) or None,
            vendedor="concesionaria" if dealer else ("particular" if seller and "particular" in seller.lower() else None),
            vendedor_nombre=logo.get("alt") if logo else None,
            descripcion=multiline_text(car.select_one("section.description .grid-container__content")),
            imagenes=dedupe(images),
            atributos=specs,
            price_partial=partial is not None,
            price_partial_reason=partial,
        ))

    async def search(self, filters: dict) -> list[Listing]:
        out: list[Listing] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(
            timeout=20, headers=HEADERS, follow_redirects=True, verify=True
        ) as cx:
            for p in range(1, self.MAX_PAGES + 1):
                url = self._build_url(filters, page=p)
                try:
                    r = await cx.get(url)
                except httpx.HTTPError:
                    if p == 1:
                        raise
                    break
                if r.status_code != 200:
                    if p == 1 and r.status_code >= 500:
                        r.raise_for_status()
                    break
                listings = self.parse_search(r.text)
                if not listings:
                    break
                for listing in listings:
                    if listing.listing_id in seen:
                        continue
                    seen.add(listing.listing_id)
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        out.append(listing)
        return out

    async def fetch_detail_page(self, url: str) -> Page:
        page = await fetch_page(url)
        if page.status >= 500:
            raise RuntimeError(f"autocosmos {page.status} for {url}")
        return page
