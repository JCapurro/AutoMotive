"""The LLM's search drafts, checked against vehicle_catalog (sección 8.4, paso 4).

Deterministic: the LLM proposes, this decides what reaches the form. Make and
model go through the same catalog matching as listing titles
(normalization/vehicle.py), so a draft only carries names the structured form
can select. Anything that doesn't fit (a model the catalog doesn't know, a
trim of another model, a year in the future, a negative price) is dropped
and explained in `notes`, which the review screen shows next to the form.

The output is what llm_jobs.output stores for 'parse_search':

    {"drafts": [{"values": {...}, "resolved": true, "notes": [...]}, ...]}

`values` uses the web form's field names (web/lib/search-form.ts); the web
maps `location` onto its list of places.
"""
from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from llm.schemas import MAX_VEHICLES, SearchDraft
from normalization.normalize import normalize_brand, normalize_text
from normalization.vehicle import CatalogModel, resolve_trim, resolve_vehicle

# resolve_vehicle methods that name a catalog model (the rest echo the input).
_RESOLVED = {"source", "title", "title_model", "fuzzy"}

MIN_YEAR = 1950
MAX_PRICE = 1e12
MAX_KM = 2_000_000
MAX_RADIUS_KM = 3000
# Without a stated currency, amounts below this are dollars (the prompt's rule, enforced here).
USD_BELOW = 200_000


def _money(v: float | None) -> str:
    return f"{v:,.0f}".replace(",", ".") if v is not None else ""


def _vehicle(models: Sequence[CatalogModel], d: SearchDraft,
             notes: list[str]) -> tuple[CatalogModel | None, str, str]:
    """The catalog model the draft names, or the make alone, or nothing."""
    make, model = (d.make or "").strip(), (d.model or "").strip()
    said = " ".join(p for p in (make, model) if p)
    if model:
        found = resolve_vehicle(list(models), title=" ".join(p for p in (make, model, d.trim or "") if p),
                                source_make=make or None, source_model=model)
        if found.method in _RESOLVED:
            entry = next(m for m in models if m.make == found.make and m.model == found.model)
            if make and normalize_brand(make) != normalize_brand(entry.make):
                notes.append(f"Interpretamos «{said}» como {entry.make} {entry.model}.")
            return entry, entry.make, entry.model
    brand = normalize_brand(make) if make else ""
    catalog_make = next((m.make for m in models if normalize_brand(m.make) == brand), "") if brand else ""
    if model:
        notes.append(f"No encontramos «{said}» en el catálogo: elegí marca y modelo de la lista.")
    elif catalog_make:
        notes.append(f"Falta el modelo de {catalog_make}: elegilo de la lista.")
    elif said:
        notes.append(f"No encontramos «{said}» en el catálogo: elegí marca y modelo de la lista.")
    return None, catalog_make, ""


def _trim(entry: CatalogModel | None, d: SearchDraft, notes: list[str]) -> str:
    trim = (d.trim or "").strip()
    if entry is None:
        return ""
    if not trim:
        # "Gol Trend Highline" in the model field: the trim is in there.
        return resolve_trim(entry, d.model) or ""
    if not entry.trims:
        return trim[:60]  # the form takes free text for models without known trims
    found = resolve_trim(entry, trim)
    if found:
        return found
    notes.append(f"La versión «{trim}» no figura para el {entry.model}: elegila de la lista.")
    return ""


def _year(value: int | None, label: str, this_year: int, notes: list[str]) -> int | None:
    if value is None:
        return None
    if MIN_YEAR <= value <= this_year + 1:
        return value
    notes.append(f"Descartamos el año {label} {value}: está fuera de rango.")
    return None


def _positive(value: float | None, label: str, notes: list[str]) -> int | None:
    if value is None:
        return None
    if 0 < value <= MAX_PRICE:
        return round(value)
    notes.append(f"Descartamos el {label} {_money(value)}: no es un monto válido.")
    return None


def _km(value: int | None, label: str, notes: list[str]) -> int | None:
    if value is None:
        return None
    if 0 <= value <= MAX_KM:
        return value
    notes.append(f"Descartamos el {label} de {_money(value)} km: está fuera de rango.")
    return None


def normalize_draft(models: Sequence[CatalogModel], d: SearchDraft,
                    today: dt.date | None = None) -> dict[str, Any]:
    this_year = (today or dt.date.today()).year
    notes: list[str] = []
    entry, make, model = _vehicle(models, d, notes)
    trim = _trim(entry, d, notes)
    trims: list[str] = []
    for wanted in list(dict.fromkeys([*(d.trims or []), *([d.trim] if d.trim else [])])):
        resolved_trim = trim if wanted == d.trim else _trim(entry, d.model_copy(update={"trim": wanted}), notes)
        if resolved_trim and resolved_trim not in trims:
            trims.append(resolved_trim)
    if not trims and trim:
        trims = [trim]
    trim = trims[0] if trims else ""

    year_min = _year(d.year_min, "desde", this_year, notes)
    year_max = _year(d.year_max, "hasta", this_year, notes)
    if year_min is not None and year_max is not None and year_min > year_max:
        year_min, year_max = year_max, year_min
    if entry and (entry.year_from or entry.year_to):
        lo, hi = year_min or MIN_YEAR, year_max or this_year + 1
        if (entry.year_to and lo > entry.year_to) or (entry.year_from and hi < entry.year_from):
            span = f"{entry.year_from or '…'}–{entry.year_to or 'hoy'}"
            notes.append(f"Ojo: el {entry.model} se fabricó {span}; con esos años puede no haber publicaciones.")

    price_max = _positive(d.price_max, "precio máximo", notes)
    price_target = _positive(d.price_target, "precio ideal", notes)
    currency = d.currency
    if currency is None and (price_max or price_target):
        currency = "USD" if max(price_max or 0, price_target or 0) < USD_BELOW else "ARS"
        notes.append(f"No dijiste la moneda: tomamos {currency}.")
    if price_max and price_target and price_target > price_max:
        price_target = None
        notes.append("El precio ideal superaba el máximo: lo dejamos vacío.")

    km_max = _km(d.km_max, "kilometraje máximo", notes)
    km_target = _km(d.km_target, "kilometraje ideal", notes)

    radius = d.radius_km if d.radius_km and 0 < d.radius_km <= MAX_RADIUS_KM else None
    location = (d.location or "").strip()[:80]

    values = {
        "make": make,
        "model": model,
        "trim": trim,
        "trims": trims,
        "trim_strict": bool(trim) and d.trim_strict,
        "year_min": year_min,
        "year_max": year_max,
        "price_max": price_max,
        "price_target": price_target,
        "currency": currency or "USD",
        "km_max": km_max,
        "km_target": km_target,
        "transmission": d.transmission or "",
        "fuel": d.fuel or "",
        "seller_type": d.seller_type or "",
        "location": location,
        "radius_km": radius,
    }
    return {"values": values, "resolved": entry is not None, "notes": list(dict.fromkeys(notes))}


def normalize_drafts(models: Sequence[CatalogModel], drafts: Sequence[SearchDraft],
                     today: dt.date | None = None) -> dict[str, Any]:
    """One search per resolved model, with all its requested versions."""
    out: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for d in drafts:
        draft = normalize_draft(models, d, today)
        v = draft["values"]
        key = (normalize_text(v["make"]), normalize_text(v["model"]))
        if draft["resolved"] and key in seen:
            first = seen[key]
            previous = first["values"]
            # A proposal without versions means any version of this model.
            previous["trims"] = (list(dict.fromkeys(previous["trims"] + v["trims"]))
                                 if previous["trims"] and v["trims"] else [])
            previous["trim"] = previous["trims"][0] if previous["trims"] else ""
            previous["trim_strict"] = bool(previous["trims"]) and previous["trim_strict"] and v["trim_strict"]
            for field in ("year_min", "year_max", "price_max", "km_max"):
                a, b = previous[field], v[field]
                if a != b:
                    previous[field] = None if a is None or b is None else (min(a, b) if field == "year_min" else max(a, b))
                    first["notes"].append("Agrupamos las versiones con un rango común: revisá los años, precio y kilómetros.")
            for field in ("transmission", "fuel", "seller_type", "location", "radius_km", "price_target", "km_target", "currency"):
                if previous[field] != v[field]:
                    label = {"transmission": "transmisión", "fuel": "combustible", "seller_type": "vendedor",
                             "location": "ubicación", "radius_km": "radio", "price_target": "precio ideal",
                             "km_target": "kilometraje ideal", "currency": "moneda"}[field]
                    first["notes"].append(f"Las versiones tienen distintos valores de {label}: revisá este filtro antes de guardar.")
                    if field != "currency":
                        previous[field] = "" if isinstance(previous[field], str) else None
                    else:
                        previous["price_max"] = previous["price_target"] = None
            first["notes"] = list(dict.fromkeys(first["notes"] + draft["notes"]))
            continue
        if draft["resolved"]:
            seen[key] = draft
        out.append(draft)
    return {"drafts": out[:MAX_VEHICLES]}
