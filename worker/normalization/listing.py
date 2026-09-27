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
from normalization.fx import FxQuote
from normalization.geo import normalize_location_query
from normalization.normalize import normalize_text
from normalization.vehicle import CatalogModel, resolve_vehicle


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


def normalize_listing(item: Listing, *, catalog: list[CatalogModel], target: Target | None = None,
                      fx: FxQuote | None = None) -> dict[str, Any]:
    """Map one scraped (or detail) Listing onto `listings` columns.

    Values that don't fit a column's domain are kept in `attributes`, like
    the F0 mapping did, together with how make/model were resolved.
    """
    target = target or Target()
    vehicle = resolve_vehicle(
        catalog, title=item.titulo, source_make=item.marca, source_model=item.modelo,
        source_version=item.version, target_make=target.make, target_model=target.model,
        year=item.anio,
    )
    raw_currency = (item.moneda or "").strip().upper() or None
    currency = _CURRENCIES.get(raw_currency) if raw_currency else None

    attributes: dict[str, Any] = dict(item.atributos)
    for key, value in (("transmision", item.transmision), ("vendedor", item.vendedor),
                       ("moneda", item.moneda), ("version", item.version),
                       ("marca", item.marca), ("modelo", item.modelo)):
        if value:
            attributes.setdefault(key, value)
    attributes["_normalization"] = {"method": vehicle.method, "notes": list(vehicle.notes)}

    row: dict[str, Any] = {
        "source": item.source,
        "external_id": str(item.listing_id),
        "url": item.url,
        "title": item.titulo,
        "description": item.descripcion or None,
        "make": vehicle.make,
        "model": vehicle.model,
        "trim": vehicle.trim,
        "year": item.anio,
        "price": item.precio if item.precio and item.precio > 0 else None,
        "currency": currency,
        "mileage_km": item.km,
        "transmission": tx.transmission(item.transmision, item.version, item.titulo),
        "fuel": tx.fuel(item.combustible, item.version, item.titulo),
        "location_text": item.ubicacion or None,
        "seller_name": item.vendedor_nombre or None,
        "seller_type": tx.seller_type(item.vendedor),
        "images": list(dict.fromkeys(i for i in item.imagenes if i)),
        "attributes": attributes,
        "published_at": (datetime.fromtimestamp(item.published_at, tz=timezone.utc)
                         if item.published_at else None),
        "price_partial": bool(item.price_partial),
        "price_partial_reason": item.price_partial_reason,
        "normalization_confidence": vehicle.confidence,
    }
    row["price_usd"] = price_usd(row["price"], currency, fx)
    row["fx_rate"] = fx.rate if fx and currency == "ARS" and row["price_usd"] else None
    row["fingerprint"] = fingerprint(row)
    return row
