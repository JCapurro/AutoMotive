"""Translate between the Telegram wizard's filter dict and search_profiles.

The wizard stores one dict per alert with multi-value `marcas` × `modelos`.
search_profiles holds one vehicle per row with `filters` / `preferences` shaped
as in docs/TECHNICAL_PLAN.md sección 4.3, plus origin columns.

The round trip is lossless for a single (marca, modelo): the bot keeps reading
the same dict it wrote, so its behavior doesn't change while it runs on
Postgres. Keys the plan has no slot for yet are kept under
`preferences.legacy_extra`; the legacy opportunity thresholds live under
`preferences.legacy_opportunity` until the 0–100 score replaces them (F2).
"""
from __future__ import annotations

from itertools import product
from typing import Any

from normalization.normalize import normalize_text


_TRANSMISSION_TO_PLAN = {"manual": "manual", "automatica": "automatic", "automatico": "automatic"}
_TRANSMISSION_TO_WIZARD = {"manual": "Manual", "automatic": "Automática"}
_SELLER_TO_PLAN = {"particular": "private", "concesionaria": "dealer"}
_SELLER_TO_WIZARD = {v: k for k, v in _SELLER_TO_PLAN.items()}

# Wizard keys that map onto a column or a sección 4.3 key.
_MAPPED_KEYS = {
    "marca", "marcas", "modelo", "modelos", "version", "anios", "anio_min", "anio_max",
    "precio_min", "precio_max", "moneda", "km_min", "km_max", "transmision",
    "combustible", "vendedor", "sources", "origin_lat", "origin_lon", "radio_km",
    "descuento_pct", "precio_max_oportunidad",
}


def split_vehicles(legacy: dict) -> list[tuple[str | None, str | None]]:
    """(marca, modelo) combinations of a wizard filter: one search profile each."""
    marcas = legacy.get("marcas") or ([legacy["marca"]] if legacy.get("marca") else [None])
    modelos = legacy.get("modelos") or ([legacy["modelo"]] if legacy.get("modelo") else [None])
    return list(product(marcas, modelos))


def _put(d: dict, key: str, value: Any) -> None:
    if value not in (None, "", [], {}):
        d[key] = value


def to_profile(legacy: dict, make: str | None, model: str | None) -> dict:
    """Wizard dict + one (make, model) → search_profiles column values."""
    filters: dict[str, Any] = {"make": make, "model": model}
    version = legacy.get("version")
    filters["trims"] = [version] if version else []
    filters["trim_strict"] = False

    anios = sorted(legacy.get("anios") or [])
    _put(filters, "years", anios)
    _put(filters, "year_min", legacy.get("anio_min") or (anios[0] if anios else None))
    _put(filters, "year_max", legacy.get("anio_max") or (anios[-1] if anios else None))
    _put(filters, "price_min", legacy.get("precio_min"))
    _put(filters, "price_max", legacy.get("precio_max"))
    _put(filters, "currency", legacy.get("moneda"))
    _put(filters, "km_min", legacy.get("km_min"))
    _put(filters, "km_max", legacy.get("km_max"))
    if trans := legacy.get("transmision"):
        filters["transmission"] = _TRANSMISSION_TO_PLAN.get(normalize_text(trans), trans)
    _put(filters, "fuel", legacy.get("combustible"))
    _put(filters, "sources", legacy.get("sources"))

    preferences: dict[str, Any] = {}
    if seller := legacy.get("vendedor"):
        preferences["seller_type"] = _SELLER_TO_PLAN.get(normalize_text(seller), seller)
    opportunity: dict[str, Any] = {}
    _put(opportunity, "discount_pct", legacy.get("descuento_pct"))
    _put(opportunity, "price_cap", legacy.get("precio_max_oportunidad"))
    _put(preferences, "legacy_opportunity", opportunity)
    _put(preferences, "legacy_extra", {k: v for k, v in legacy.items() if k not in _MAPPED_KEYS})

    return {
        "filters": filters,
        "preferences": preferences,
        "origin_lat": legacy.get("origin_lat"),
        "origin_lon": legacy.get("origin_lon"),
        "radius_km": legacy.get("radio_km"),
    }


def to_legacy(filters: dict, preferences: dict, origin_lat: float | None = None,
              origin_lon: float | None = None, radius_km: float | None = None) -> dict:
    """search_profiles column values → the wizard dict the scheduler and handlers expect."""
    out: dict[str, Any] = {}
    _put(out, "sources", filters.get("sources"))
    if filters.get("make"):
        out["marcas"] = [filters["make"]]
    if filters.get("model"):
        out["modelos"] = [filters["model"]]
    if trims := filters.get("trims"):
        out["version"] = trims[0]
    if years := filters.get("years"):
        out["anios"] = years
    else:
        _put(out, "anio_min", filters.get("year_min"))
        _put(out, "anio_max", filters.get("year_max"))
    _put(out, "km_min", filters.get("km_min"))
    _put(out, "km_max", filters.get("km_max"))
    _put(out, "precio_min", filters.get("price_min"))
    _put(out, "precio_max", filters.get("price_max"))
    _put(out, "moneda", filters.get("currency"))
    _put(out, "combustible", filters.get("fuel"))
    if trans := filters.get("transmission"):
        out["transmision"] = _TRANSMISSION_TO_WIZARD.get(trans, trans)
    if seller := preferences.get("seller_type"):
        out["vendedor"] = _SELLER_TO_WIZARD.get(seller, seller)
    if origin_lat is not None and origin_lon is not None:
        out["origin_lat"] = origin_lat
        out["origin_lon"] = origin_lon
    _put(out, "radio_km", radius_km)
    opportunity = preferences.get("legacy_opportunity") or {}
    _put(out, "descuento_pct", opportunity.get("discount_pct"))
    _put(out, "precio_max_oportunidad", opportunity.get("price_cap"))
    out.update(preferences.get("legacy_extra") or {})
    return out
