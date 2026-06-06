from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any

from price_check import keyword_partial


@dataclass
class Listing:
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
    # a unix timestamp. None = unknown (caller should fall back to seen_listings
    # and the bootstrap flag for freshness).
    published_at: int | None = None
    # True when the advertised price is suspected to be a down payment,
    # installment, or savings-plan slot rather than the total. Such listings
    # are excluded from comparables and never flagged as opportunities.
    price_partial: bool = False
    price_partial_reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("extra", None)
        return d


class BaseScraper:
    name: str = "base"

    async def search(self, filters: dict) -> list[Listing]:
        raise NotImplementedError

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
