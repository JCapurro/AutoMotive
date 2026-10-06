"""Mardel Usados' public Astro catalog; its data attributes are authoritative."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from ._http import dedupe, multiline_text, soup, text_of, to_int
from ._regional import PublicCatalogScraper, matches_vehicle, price, timestamp
from .base import Listing, ListingDetail


class MardelUsadosScraper(PublicCatalogScraper):
    name = "mardelusados"
    BASE = "https://mardelusados.com"

    @staticmethod
    def _id(url: str) -> str:
        match = re.search(r"-(vh-\d+)/?$", urlparse(url).path, re.I)
        if not match:
            raise ValueError("mardelusados: missing vehicle ID")
        return match[1].upper()

    @classmethod
    def parse_search(cls, html: str) -> list[Listing]:
        doc = soup(html)
        cards = doc.select("[data-veh][data-tipo]")
        if not cards:
            raise RuntimeError("mardelusados: catalog markup missing")
        seen: dict[str, Listing] = {}
        for card in cards:
            if card.get("data-tipo") not in ("Auto", "Camioneta", "Utilitario"):
                continue
            anchor = card.select_one("a[href*='/vehiculo/']")
            title = text_of(card.select_one("h3"))
            if not anchor or not title:
                raise RuntimeError("mardelusados: incomplete vehicle card")
            url = urljoin(cls.BASE, anchor["href"])
            specs = [text_of(li) or "" for li in card.select("li")]
            img = card.select_one("img[src]")
            amount = to_int(card.get("data-precio"))
            item = Listing(source=cls.name, listing_id=cls._id(url), titulo=title, url=url,
                marca=card.get("data-marca") or None, modelo=card.get("data-modelo") or None,
                anio=to_int(card.get("data-a")) or next((int(v) for v in specs
                                                      if re.fullmatch(r"(?:19|20)\d{2}", v)), None),
                km=to_int(card.get("data-km")),
                precio=float(amount) if amount and amount > 1 else None,
                moneda={"ARS": "ARS", "USD": "USD"}.get(card.get("data-moneda", "").upper()),
                ubicacion=card.get("data-ciudad") or None,
                transmision=card.get("data-transmision") or None,
                combustible=next((v for v in specs if any(w in v.lower() for w in
                                           ("nafta", "diésel", "diesel", "gnc", "eléct", "híbr"))), None),
                imagenes=[img["src"]] if img else [],
                published_at=timestamp(card.get("data-fecha")))
            seen[item.listing_id] = cls.annotate_partial_price(item)
        return list(seen.values())

    async def search(self, filters: dict) -> list[Listing]:
        page = await self._get(self.BASE + "/")
        if page.status != 200:
            raise RuntimeError(f"mardelusados catalog HTTP {page.status}")
        return [item for item in self.parse_search(page.html) if matches_vehicle(item, filters)]

    @classmethod
    def parse_detail(cls, html: str, url: str, status: int = 200) -> ListingDetail:
        cls.check_status(status)
        if status in (404, 410):
            return ListingDetail(url, gone=True, gone_reason=f"HTTP {status}")
        doc = soup(html)
        article = doc.select_one("main > article")
        title = text_of(article.select_one("h1")) if article else None
        if not article or not title:
            raise RuntimeError("mardelusados: vehicle detail markup missing")
        canonical = doc.select_one("link[rel='canonical']")
        if canonical and cls._id(canonical["href"]) != cls._id(url):
            raise RuntimeError("mardelusados: response belongs to another vehicle")
        if re.search(r"\bvendido\b", text_of(article.select_one("aside")) or "", re.I):
            return ListingDetail(url, gone=True, gone_reason="vendido")
        attrs = {text_of(dt) or "": text_of(dt.find_next_sibling("dd")) or ""
                 for dt in article.select("dt")}
        amount, currency = price(text_of(article.select_one("h1 + p")))
        seller = article.select_one("aside p a[href*='instagram.com/']")
        item = Listing(source=cls.name, listing_id=cls._id(url), titulo=title, url=url,
            precio=amount, moneda=currency, anio=to_int(attrs.get("Año")),
            km=to_int(attrs.get("Kilómetros")), ubicacion=attrs.get("Ubicación") or None,
            combustible=attrs.get("Combustible") or None, transmision=attrs.get("Transmisión") or None,
            vendedor_nombre=text_of(seller), atributos=attrs,
            descripcion=multiline_text(article.select_one("section")),
            imagenes=dedupe([img.get("data-foto") for img in article.select("[data-foto]")] +
                            [img.get("src") for img in article.select("#foto-principal")]))
        return ListingDetail(url, listing=cls.annotate_partial_price(item))
