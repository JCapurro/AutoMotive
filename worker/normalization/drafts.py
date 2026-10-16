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

Body types (docs/CARROCERIA.md) arrive as `values.body_types`, codes in the
canonical order. Within a model they are only those the catalog lists for it,
and only when it lists two or more: that is the choice the form offers. A
draft without make or model but with body types is a search without a model
("cualquier SUV"), which the plan may not allow: the web decides with
my_plan_feature('model_less_search').
"""
from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable, Sequence
from typing import Any

from llm.schemas import MAX_VEHICLES, SearchDraft
from normalization import body_type
from normalization.body_type import CODES as BODY_TYPES, LABELS as BODY_TYPE_LABELS
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

# Generic body-type names a provider may put where the vehicle goes ("una SUV"
# → model "SUV"); body_type.from_source maps each one to its code. Checked
# before the catalog: "Pick-up" alone resolves fuzzily to the VW Up. Submodel
# words (Weekend, Oroch) are not here.
_BODY_WORDS = frozenset(normalize_text(w) for w in (
    *BODY_TYPES, *BODY_TYPE_LABELS.values(), "pick up", "pickup", "hatch", "crossover", "todoterreno",
    "station wagon", "minivan", "cupe", "descapotable", "cabrio", "cabriolet", "roadster",
    "furgon", "furgoneta", "van"))
# Vehicle words that name no body type: a "camioneta" may be an SUV or a
# pick-up, and an "auto familiar" is about its use.
_NO_BODY_WORDS = frozenset({"camioneta", "camionetas", "familiar"})
_BODY_SPLIT = re.compile(r"\s*(?:,|/|\bo\b|\by\b)\s*")


def _money(v: float | None) -> str:
    return f"{v:,.0f}".replace(",", ".") if v is not None else ""


def _labels(codes: Iterable[str]) -> str:
    """"SUV", "SUV o Pick-up", "Sedán, Hatchback o SUV"."""
    names = [BODY_TYPE_LABELS[c] for c in codes]
    return " o ".join([", ".join(names[:-1]), names[-1]] if len(names) > 2 else names)


def _ordered(codes: Iterable[str]) -> list[str]:
    """Known codes, in the canonical order, once."""
    wanted = set(codes)
    return [c for c in BODY_TYPES if c in wanted]


def _body_words(text: str | None) -> list[str] | None:
    """The body types a field names when it holds nothing but body-type names
    ("SUV", "pick-up", "SUV o pick-up"; "camioneta" names none); None when it
    says anything else."""
    parts = [p for p in _BODY_SPLIT.split(normalize_text(text)) if p]
    if not parts or any(p not in _BODY_WORDS and p not in _NO_BODY_WORDS for p in parts):
        return None
    return [code for p in parts if p in _BODY_WORDS and (code := body_type.from_source(p))]


def _without_body_words(d: SearchDraft) -> SearchDraft:
    """Body-type names out of the vehicle fields and into body_types: the
    prompt forbids them there, but a provider may still do it."""
    found: list[str] = []
    update: dict[str, Any] = {}
    for field in ("make", "model", "trim"):
        if (codes := _body_words(getattr(d, field))) is not None:
            found += codes
            update[field] = None
    trims = [t for t in d.trims if _body_words(t) is None]
    if len(trims) != len(d.trims):
        found += [c for t in d.trims for c in (_body_words(t) or [])]
        update["trims"] = trims
    if not update:
        return d
    return d.model_copy(update={**update, "body_types": [*d.body_types, *found]})


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


def _body_types(entry: CatalogModel | None, make: str, d: SearchDraft, notes: list[str]) -> list[str]:
    """The body types the draft can carry to the form (see the module docstring)."""
    said = _ordered(c for c in d.body_types if c in BODY_TYPE_LABELS)
    if entry is None:
        # A vehicle the catalog doesn't know: the user picks one, and "Tesla
        # Model 3 sedán" must not become any sedán.
        unknown = (d.model or "").strip() or ((d.make or "").strip() and not make)
        return [] if unknown else said
    wanted = list(said)
    # A submodel or a body word written with the vehicle: "Palio Weekend", "Ka Plus", "A3 Sportback".
    if hit := body_type.explicit(entry.make, entry.model, d.model, d.trim, *d.trims):
        wanted.append(hit[0])
    possible = _ordered(entry.body_types)
    off = [c for c in said if c not in possible]
    if len(possible) < 2:
        # No choice to make in the form: the model only comes one way (or the catalog doesn't know).
        if off:
            notes.append(f"El {entry.model} solo viene como {BODY_TYPE_LABELS[possible[0]]}: "
                         f"no filtramos por {_labels(off)}." if possible else
                         f"No sabemos qué carrocerías tiene el {entry.model}: no filtramos por {_labels(off)}.")
        return []
    if off:
        notes.append(f"El {entry.model} no viene como {_labels(off)}: "
                     f"no {'la' if len(off) == 1 else 'las'} usamos como filtro.")
    return _ordered(c for c in wanted if c in possible)


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
    d = _without_body_words(d)
    entry, make, model = _vehicle(models, d, notes)
    body_types = _body_types(entry, make, d, notes)
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

    if not make and not model:
        if body_types and not price_max:
            # search_needs_max_price: the database refuses a search without a model and without a top.
            notes.append(f"Para buscar cualquier {_labels(body_types)} sin elegir modelo, poné un precio máximo.")
        elif not body_types and not ((d.make or "").strip() or (d.model or "").strip()):
            notes.append("Falta el vehículo: elegilo en el formulario.")

    values = {
        "make": make,
        "model": model,
        "trim": trim,
        "trims": trims,
        "trim_strict": bool(trim) and d.trim_strict,
        "body_types": body_types,
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


def _group_key(draft: dict[str, Any]) -> tuple | None:
    """Drafts with the same key are one search: a resolved model, or a search
    without a model and its body types ("cualquier SUV" and "cualquier pick-up"
    stay two). Other unresolved drafts are never grouped."""
    v = draft["values"]
    if draft["resolved"]:
        return normalize_text(v["make"]), normalize_text(v["model"])
    if not v["make"] and not v["model"] and v["body_types"]:
        return "", "", tuple(v["body_types"])
    return None


def normalize_drafts(models: Sequence[CatalogModel], drafts: Sequence[SearchDraft],
                     today: dt.date | None = None) -> dict[str, Any]:
    """One search per resolved model, with all its requested versions, and one
    per set of body types without a model."""
    out: list[dict[str, Any]] = []
    seen: dict[tuple, dict[str, Any]] = {}
    for d in drafts:
        draft = normalize_draft(models, d, today)
        v = draft["values"]
        key = _group_key(draft)
        if key is not None and key in seen:
            first = seen[key]
            previous = first["values"]
            # Within a model they are its versions; without one, repeated requests.
            what = "las versiones" if first["resolved"] else "los pedidos"
            # A proposal without versions means any version of this model.
            previous["trims"] = (list(dict.fromkeys(previous["trims"] + v["trims"]))
                                 if previous["trims"] and v["trims"] else [])
            previous["trim"] = previous["trims"][0] if previous["trims"] else ""
            previous["trim_strict"] = bool(previous["trims"]) and previous["trim_strict"] and v["trim_strict"]
            # The same for body types: one without them means any body type of the model.
            previous["body_types"] = (_ordered(previous["body_types"] + v["body_types"])
                                      if previous["body_types"] and v["body_types"] else [])
            for field in ("year_min", "year_max", "price_max", "km_max"):
                a, b = previous[field], v[field]
                if a != b:
                    previous[field] = None if a is None or b is None else (min(a, b) if field == "year_min" else max(a, b))
                    first["notes"].append(f"Agrupamos {what} con un rango común: revisá los años, precio y kilómetros.")
            for field in ("transmission", "fuel", "seller_type", "location", "radius_km", "price_target", "km_target", "currency"):
                if previous[field] != v[field]:
                    label = {"transmission": "transmisión", "fuel": "combustible", "seller_type": "vendedor",
                             "location": "ubicación", "radius_km": "radio", "price_target": "precio ideal",
                             "km_target": "kilometraje ideal", "currency": "moneda"}[field]
                    first["notes"].append(f"{what.capitalize()} tienen distintos valores de {label}: "
                                          "revisá este filtro antes de guardar.")
                    if field != "currency":
                        previous[field] = "" if isinstance(previous[field], str) else None
                    else:
                        previous["price_max"] = previous["price_target"] = None
            first["notes"] = list(dict.fromkeys(first["notes"] + draft["notes"]))
            continue
        if key is not None:
            seen[key] = draft
        out.append(draft)
    return {"drafts": out[:MAX_VEHICLES]}
