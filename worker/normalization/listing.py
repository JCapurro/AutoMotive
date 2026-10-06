"""Normalization v2: a collector Listing → a `listings` row (sección 5.2).

Pure: the catalog, the crawl target and the day's FX quote are passed in.
Geocoding (paso 4) needs the database cache and happens in pipeline/ingest.py.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from collectors.base import Listing
from normalization import transmission as tx
from normalization.description_facts import DescriptionFacts, parse as parse_facts, resolve_price
from normalization.fx import FxQuote
from normalization.geo import normalize_location_query
from normalization.normalize import normalize_text
from normalization.price_check import keyword_partial
from normalization.vehicle import CatalogModel, resolve_trim, resolve_vehicle


_CURRENCIES = {"USD": "USD", "U$S": "USD", "US$": "USD", "U$D": "USD", "ARS": "ARS", "$": "ARS"}

# Columns whose change is an 'attrs' snapshot (sección 5.3, "hash(attrs clave)").
# published_at is left out on purpose: relative dates ("hace 3 días") drift a
# little on every crawl.
KEY_ATTRS = ("title", "make", "model", "trim", "year", "transmission", "fuel",
             "location_text", "seller_type", "seller_name")


@dataclass(frozen=True)
class Target:
    """The crawl target a card was found through: a hint, never the truth."""
    make: str | None = None
    model: str | None = None


def _hash(value: Any) -> str:
    return hashlib.md5(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
                       .encode()).hexdigest()


def attrs_hash(row: dict[str, Any]) -> str:
    return _hash({k: row.get(k) for k in KEY_ATTRS})


def text_hash(value: Any) -> str | None:
    return _hash(value) if value not in (None, "", [], {}) else None


def fingerprint(row: dict[str, Any]) -> str | None:
    """hash(make, model, year, round(km, -3), seller, location) — sección 5.4.

    Without make, model, year and km the fingerprint would lump unrelated cars
    together, so it is left empty and no repost is inferred.
    """
    if not (row.get("make") and row.get("model") and row.get("year") and row.get("mileage_km")):
        return None
    parts = (
        normalize_text(row["make"]), normalize_text(row["model"]), int(row["year"]),
        int(round(int(row["mileage_km"]), -3)),
        normalize_text(row.get("seller_name")),
        normalize_location_query(row.get("location_text")),
    )
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()


def price_usd(price: float | None, currency: str | None, fx: FxQuote | None) -> float | None:
    if not price or price <= 0 or not currency:
        return None
    if currency == "USD":
        return round(float(price), 2)
    if currency == "ARS" and fx and fx.rate > 0:
        return round(float(price) / fx.rate, 2)
    return None


def listing_facts(item: Listing, *, now_year: int | None = None) -> DescriptionFacts | None:
    """What the item's title and description state, or what the LLM already
    read from them (item.extra["description_facts"], pipeline/enrich.py)."""
    if pre := item.extra.get("description_facts"):
        return DescriptionFacts.from_json(pre)
    return parse_facts(item.descripcion, item.titulo, now_year=now_year)


def normalize_listing(item: Listing, *, catalog: list[CatalogModel], target: Target | None = None,
                      fx: FxQuote | None = None) -> dict[str, Any]:
    """Map one scraped (or detail) Listing onto `listings` columns.

    Values that don't fit a column's domain are kept in `attributes`, like
    the F0 mapping did, together with how make/model were resolved.

    The price is the effective one (normalization v3): the description may
    say the published number is a list price (the cash one wins) or a down
    payment (the total wins). The published number goes to price_published.
    Year, km, transmission and fuel fall back to what the description says.
    """
    target = target or Target()
    vehicle = resolve_vehicle(
        catalog, title=item.titulo, source_make=item.marca, source_model=item.modelo,
        source_version=item.version, target_make=target.make, target_model=target.model,
        year=item.anio,
    )
    raw_currency = (item.moneda or "").strip().upper() or None
    currency = _CURRENCIES.get(raw_currency) if raw_currency else None
    facts = listing_facts(item, now_year=datetime.now(timezone.utc).year)
    # A version mentioned only in the description may fill a missing trim,
    # but must match the resolved model's catalog. Never replace a page/title trim.
    described_trim = None
    if facts and not vehicle.trim and facts.claims.get("trim"):
        model = next((m for m in catalog if m.make == vehicle.make and m.model == vehicle.model), None)
        if model:
            described_trim = resolve_trim(model, facts.claims["trim"])

    attributes: dict[str, Any] = dict(item.atributos)
    for key, value in (("transmision", item.transmision), ("vendedor", item.vendedor),
                       ("moneda", item.moneda), ("version", item.version),
                       ("marca", item.marca), ("modelo", item.modelo)):
        if value:
            attributes.setdefault(key, value)
    attributes["_normalization"] = {"method": vehicle.method, "notes": list(vehicle.notes)}
    described = {
        "year": not item.anio,
        "mileage_km": item.km is None,
        "transmission": not tx.transmission(item.transmision, item.version, item.titulo),
        "fuel": not tx.fuel(item.combustible, item.version, item.titulo),
        "trim": bool(described_trim),
    }

    published = item.precio if item.precio and item.precio > 0 else None
    # Why the title or the page's structure (Autocosmos' "Anticipo" block)
    # already say the published number isn't the total.
    partial_reason = (item.price_partial_reason or "parcial") if item.price_partial         else keyword_partial(item.titulo)
    usd_rate = fx.rate if fx and fx.rate > 0 else None
    price = resolve_price(published, currency, partial_reason=partial_reason, facts=facts,
                          usd_rate=usd_rate)
    if facts is not None:
        facts.price_check = price.check()

    row: dict[str, Any] = {
        "source": item.source,
        "external_id": str(item.listing_id),
        "url": item.url,
        "title": item.titulo,
        "description": item.descripcion or None,
        "make": vehicle.make,
        "model": vehicle.model,
        "trim": vehicle.trim or described_trim,
        "year": item.anio or (facts.year if facts else None),
        "price": price.price,
        "currency": price.currency,
        "price_published": published,
        "price_published_currency": currency,
        "price_source": price.source,
        "mileage_km": item.km if item.km is not None else (facts.mileage_km if facts else None),
        "transmission": tx.transmission(item.transmision, item.version, item.titulo)
                        or (facts.transmission if facts else None),
        "fuel": tx.fuel(item.combustible, item.version, item.titulo) or (facts.fuel if facts else None),
        "location_text": item.ubicacion or None,
        "seller_name": item.vendedor_nombre or None,
        "seller_type": tx.seller_type(item.vendedor),
        "images": list(dict.fromkeys(i for i in item.imagenes if i)),
        "attributes": attributes,
        "published_at": (datetime.fromtimestamp(item.published_at, tz=timezone.utc)
                         if item.published_at else None),
        "price_partial": price.partial,
        "price_partial_reason": price.partial_reason,
        "description_facts": facts.to_json() if facts is not None and not facts.is_empty() else None,
        "normalization_confidence": vehicle.confidence,
    }
    row["price_usd"] = price_usd(row["price"], row["currency"], fx)
    row["fx_rate"] = fx.rate if fx and row["currency"] == "ARS" and row["price_usd"] else None
    attributes["_description_filled"] = [key for key, missing in described.items() if missing and row.get(key) is not None]
    # Not columns: what merge() needs to re-resolve the price against stored facts.
    row["usd_rate"] = usd_rate
    row["published_partial_reason"] = partial_reason
    row["fingerprint"] = fingerprint(row)
    return row
