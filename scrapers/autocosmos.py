"""AutoCosmos AR scraper.

AutoCosmos exposes a public listings page at
`/auto/usado/{marca}/{modelo}` with rich schema.org microdata, no login,
no anti-bot. Filters are applied client-side via BaseScraper.matches_filters
because the site's server-side filters aren't always honored via URL params.
"""
from __future__ import annotations
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, Listing


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-AR,es;q=0.9",
}


def _slug(s: str) -> str:
    s = s.lower().strip()
    s = s.translate(str.maketrans("áéíóúñü", "aeiounu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _to_int(s: str | None) -> int | None:
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


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
        title_pieces = [
            (marca_el.get_text(strip=True) if marca_el else None),
            (modelo_el.get_text(strip=True) if modelo_el else None),
            (version_el.get_text(strip=True) if version_el else None),
        ]
        title = " ".join(p for p in title_pieces if p).strip() or \
                (meta_name.get("content") if meta_name else "")
        year_el = art.select_one(".listing-card__year")
        km_el = art.select_one(".listing-card__km")
        city_el = art.select_one(".listing-card__city")
        prov_el = art.select_one(".listing-card__province")
        cur_el = art.select_one("meta[itemprop='priceCurrency']")
        price_el = art.select_one(".listing-card__price-value, [itemprop='price']")
        img = art.select_one("img[itemprop='image'], figure img")

        anio = _to_int(year_el.get_text() if year_el else None)
        # km element has both content="KMT 150000" and inner text "150000 km"
        km = None
        if km_el:
            content = km_el.get("content") or km_el.get_text() or ""
            km = _to_int(content)

        precio = None
        if price_el is not None:
            content = price_el.get("content") or price_el.get_text()
            precio = float(_to_int(content)) if _to_int(content) else None

        moneda = (cur_el.get("content") if cur_el else None) or None

        # City field sometimes has trailing " | " — strip that and join with province
        city = city_el.get_text(strip=True).rstrip("|").strip() if city_el else ""
        prov = prov_el.get_text(strip=True) if prov_el else ""
        ubic = ", ".join(p for p in (city, prov) if p) or None

        return Listing(
            source="autocosmos",
            listing_id=lid,
            titulo=title[:200],
            url=full_url,
            precio=precio,
            moneda=moneda,
            marca=(marca_el.get_text(strip=True) if marca_el else None),
            modelo=(modelo_el.get_text(strip=True) if modelo_el else None),
            anio=anio,
            km=km,
            ubicacion=ubic,
            extra={"img": img.get("src")} if img and img.get("src") else {},
        )

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
                    break
                if r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, "lxml")
                arts = soup.select("article.listing-card, article[itemtype*='Car']")
                if not arts:
                    break
                for art in arts:
                    listing = self._parse_article(art)
                    if not listing or listing.listing_id in seen:
                        continue
                    seen.add(listing.listing_id)
                    self.annotate_partial_price(listing)
                    if self.matches_filters(listing, filters):
                        out.append(listing)
        return out
