from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any

from normalization.price_check import keyword_partial
from ._http import Page, slim_html


@dataclass
class Listing:
    """One ad as a collector read it, before normalization.

    `marca`/`modelo`/`version` are only set when the page states them
    structurally (a spec table, microdata); otherwise normalization resolves
    them from the title against vehicle_catalog (sección 5.2).
    """
    source: str
    listing_id: str
    titulo: str
    url: str
    precio: float | None = None
    moneda: str | None = None
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    km: int | None = None
    ubicacion: str | None = None
    combustible: str | None = None
    transmision: str | None = None
    vendedor: str | None = None
    # When the platform exposes how recently the ad was posted, store it as
    # a unix timestamp. None = unknown (caller should fall back to the seen set (matches)
    # and the bootstrap flag for freshness).
    published_at: int | None = None
    # True when the advertised price is suspected to be a down payment,
    # installment, or savings-plan slot rather than the total. Such listings
    # are excluded from comparables and never flagged as opportunities.
    price_partial: bool = False
    price_partial_reason: str | None = None
    version: str | None = None
    descripcion: str | None = None
    imagenes: list[str] = field(default_factory=list)
    vendedor_nombre: str | None = None
    # Raw structured attributes as the page labels them ("Transmisión": "MT").
    atributos: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("extra", None)
        return d


class CollectorBlocked(RuntimeError):
    """The source answered with a login wall, a security challenge or no
    session. The run fails (collector_runs) instead of looking like "0 results"."""


@dataclass
class ListingDetail:
    """What fetch_detail() found at a listing's URL (sección 5.5).

    `gone` means the page proves the ad is over: 404, paused, sold, or the
    source now serves a different vehicle there. A fetch that merely failed
    raises instead, so it is never mistaken for a removal.
    """
    url: str
    listing: Listing | None = None
    gone: bool = False
    gone_reason: str | None = None


class BaseScraper:
    name: str = "base"
    # Bump when parse_detail() changes what it reads: tools/reprocess.py --raw
    # --outdated re-parses the raw_pages stored with an older version.
    DETAIL_PARSER_VERSION: int = 1

    async def search(self, filters: dict) -> list[Listing]:
        raise NotImplementedError

    async def fetch_detail_page(self, url: str) -> Page:
        """Download the ad's own page, with the source's login-wall and session
        checks, without parsing it (pipeline/enrich.py keeps it in raw_pages
        first, so a page the parser chokes on is still there to look at)."""
        raise NotImplementedError

    @staticmethod
    def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
        """Read the ad's page: description, version, transmission, seller
        type, every image and the spec attributes."""
        raise NotImplementedError

    def slim_page(self, page: Page) -> str:
        """What raw_pages keeps of a detail page: enough for parse_detail()."""
        return slim_html(page.html)

    async def fetch_detail(self, url: str) -> ListingDetail:
        page = await self.fetch_detail_page(url)
        return self.parse_detail(page.html, url, page.status)

    @staticmethod
    def annotate_partial_price(item: Listing) -> Listing:
        """Run keyword detection over the title and tag the listing.
        Statistical detection happens later, in the opportunity engine,
        once we have comparables to compare against."""
        if item.price_partial:
            return item
        reason = keyword_partial(item.titulo)
        if reason:
            item.price_partial = True
            item.price_partial_reason = reason
        return item

    @staticmethod
    def matches_filters(item: Listing, f: dict) -> bool:
        """Apply user filters that the source could not enforce server-side."""
        if (anios := f.get("anios")) and item.anio and item.anio not in anios:
            return False
        if (a := f.get("anio_min")) and item.anio and item.anio < a:
            return False
        if (a := f.get("anio_max")) and item.anio and item.anio > a:
            return False
        if (k := f.get("km_max")) and item.km and item.km > k:
            return False
        if (k := f.get("km_min")) and item.km and item.km < k:
            return False
        if (p := f.get("precio_max")) and item.precio and item.precio > p:
            return False
        if (p := f.get("precio_min")) and item.precio and item.precio < p:
            return False
        if (mon := f.get("moneda")) and item.moneda and mon != item.moneda:
            return False
        if (c := f.get("combustible")) and item.combustible:
            if c.lower() not in item.combustible.lower():
                return False
        if (t := f.get("transmision")) and item.transmision:
            if t.lower() not in item.transmision.lower():
                return False
        if (u := f.get("ubicacion")) and item.ubicacion:
            if u.lower() not in item.ubicacion.lower():
                return False
        if (v := f.get("vendedor")) and item.vendedor:
            if v.lower() != item.vendedor.lower():
                return False
        return True
