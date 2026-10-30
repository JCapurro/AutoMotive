"""Why a search brings few results (bot de pocos resultados). Pure: no I/O.

The market of a search is every active listing of its make/model stored in
the last 30 days, from every source. Each one goes through the same hard
filters as matching (intelligence/matching.evaluate), and the funnel counts,
per filter:

    fails   listings that filter discards
    only    listings that filter alone discards: loosening it would add them

The `only` count is what explains a short list ("solo elegiste 2015: hay 3
de ese año y 18 de 2014 a 2016"). The LLM writes the explanation from this
funnel (pipeline/low_results.py); `fallback_text` writes one when it fails.

Whether the results are good matches or opportunities doesn't matter here:
every result the search shows counts.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from intelligence import copy
from intelligence.matching import FAIL, evaluate, model_less

# The filters the funnel reports, in the order a person reads them.
FILTERS = ("year", "price", "km", "location", "transmission", "fuel", "body_type", "trim", "source", "model")

LABEL = {
    "year": "año",
    "price": "precio",
    "km": "kilometraje",
    "location": "zona",
    "transmission": "transmisión",
    "fuel": "combustible",
    "body_type": "carrocería",
    "trim": "versión",
    "source": "fuentes",
    "model": "modelo",
}

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    # A search with this many results or fewer gets a diagnosis.
    "max_results": 3,
    # Time a new search has to fill up before it is judged.
    "min_age_hours": 24,
    # A diagnosis with the same filters is redone after this many days.
    "recheck_days": 7,
    # Diagnoses per tick: each one is an LLM call.
    "max_per_tick": 10,
    "notify": True,
}


def settings(raw: Any) -> dict[str, Any]:
    """app_config.low_results over DEFAULTS; a bad value keeps the default."""
    out = dict(DEFAULTS)
    if not isinstance(raw, Mapping):
        return out
    for key, default in DEFAULTS.items():
        value = raw.get(key)
        if isinstance(default, bool):
            if isinstance(value, bool):
                out[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            out[key] = type(default)(value)
    return out


def eligible(filters: Mapping[str, Any]) -> bool:
    """Searches by model only: a search by body type has a whole market behind it."""
    return not model_less(filters)


def fingerprint(profile: Mapping[str, Any]) -> str:
    """Changes when what decides the results changes (filters, place, radius)."""
    key = {k: profile.get(k) for k in ("filters", "origin_lat", "origin_lon", "radius_km")}
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()[:16]


@dataclass
class Funnel:
    market: int = 0                                   # listings of the model
    matched: int = 0                                  # that pass every hard filter
    fails: dict[str, int] = field(default_factory=dict)
    only: dict[str, int] = field(default_factory=dict)
    years: dict[int, int] = field(default_factory=dict)       # market by model year
    price_usd: dict[str, float] = field(default_factory=dict)  # min / median / max
    km: dict[str, float] = field(default_factory=dict)         # min / median / max
    sources: dict[str, int] = field(default_factory=dict)

    @property
    def main_blocker(self) -> str | None:
        """The filter whose loosening alone adds the most listings."""
        best = max(((n, k) for k, n in self.only.items() if n), default=None)
        return best[1] if best else None

    def to_json(self) -> dict[str, Any]:
        return {"market": self.market, "matched": self.matched, "fails": self.fails, "only": self.only,
                "years": {str(y): n for y, n in sorted(self.years.items())},
                "price_usd": self.price_usd, "km": self.km, "sources": self.sources,
                "main_blocker": self.main_blocker}


def _spread(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    return {"min": round(min(values)), "median": round(statistics.median(values)), "max": round(max(values))}


def _usd(listing: Mapping[str, Any], fx_rate: float | None) -> float | None:
    if listing.get("price_partial"):
        return None
    if listing.get("price_usd"):
        return float(listing["price_usd"])
    price, currency = listing.get("price"), (listing.get("currency") or "").upper()
    if not price:
        return None
    if currency == "USD":
        return float(price)
    if currency == "ARS" and fx_rate:
        return float(price) / fx_rate
    return None


def funnel(listings: Iterable[Mapping[str, Any]], profile: Mapping[str, Any], *,
           fx_rate: float | None = None) -> Funnel:
    out = Funnel()
    fails: Counter[str] = Counter()
    only: Counter[str] = Counter()
    years: Counter[int] = Counter()
    sources: Counter[str] = Counter()
    prices: list[float] = []
    kms: list[float] = []
    for listing in listings:
        out.market += 1
        failed = [k for k in evaluate(listing, profile, fx_rate=fx_rate).failed if k in FILTERS]
        fails.update(failed)
        if not failed:
            out.matched += 1
        elif len(failed) == 1:
            only[failed[0]] += 1
        if listing.get("year"):
            years[int(listing["year"])] += 1
        if listing.get("source"):
            sources[listing["source"]] += 1
        if (usd := _usd(listing, fx_rate)) is not None:
            prices.append(usd)
        if listing.get("mileage_km") is not None:
            kms.append(float(listing["mileage_km"]))
    out.fails = {k: fails[k] for k in FILTERS if fails[k]}
    out.only = {k: only[k] for k in FILTERS if only[k]}
    out.years = dict(years)
    out.sources = dict(sources.most_common())
    out.price_usd = _spread(prices)
    out.km = _spread(kms)
    return out


def _years(f: Mapping[str, Any]) -> tuple[int | None, int | None]:
    years = f.get("years") or []
    lo = f.get("year_min") or (min(years) if years else None)
    hi = f.get("year_max") or (max(years) if years else None)
    return lo, hi


def _n(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def hints(fun: Funnel, profile: Mapping[str, Any]) -> list[str]:
    """Deterministic facts the explanation should rely on, in Spanish. They go
    to the LLM as context and are the fallback's body."""
    f = profile.get("filters") or {}
    out: list[str] = []
    vehicle = " ".join(x for x in (f.get("make"), f.get("model")) if x) or "este modelo"
    if fun.market == 0:
        out.append(f"En los últimos 30 días no vimos publicaciones de {vehicle} en ninguna fuente: "
                   "es un modelo que se publica poco.")
        return out
    out.append(f"En los últimos 30 días vimos {_n(fun.market, 'publicación', 'publicaciones')} de {vehicle}; "
               f"{fun.matched} {'pasa' if fun.matched == 1 else 'pasan'} todos tus filtros.")
    lo, hi = _years(f)
    if lo is not None and lo == hi:
        same = fun.years.get(int(lo), 0)
        around = sum(n for y, n in fun.years.items() if abs(y - int(lo)) <= 1)
        out.append(f"Elegiste un solo año ({lo}): de ese año hubo {same}; "
                   f"sumando un año para cada lado serían {around}.")
    for key in sorted(fun.only, key=lambda k: -fun.only[k]):
        n = fun.only[key]
        out.append(f"El filtro de {LABEL[key]} deja afuera {_n(n, 'publicación que cumple', 'publicaciones que cumplen')} "
                   "todo lo demás.")
    if fun.market < 10:
        out.append(f"De {vehicle} se publican pocos autos: es normal que tarde en aparecer uno.")
    return out


def fallback_text(fun: Funnel, profile: Mapping[str, Any]) -> str:
    """The explanation when the LLM doesn't answer: the hints, as a paragraph."""
    lines = hints(fun, profile)
    lines.append("Seguimos atentos: si aparece uno que cumpla tus filtros, te avisamos.")
    return " ".join(lines)


def llm_context(fun: Funnel, profile: Mapping[str, Any], results: int) -> dict[str, Any]:
    """What the LLM reads: the search, the funnel and the hints. No user data
    beyond the search's own filters."""
    f = profile.get("filters") or {}
    keep = ("make", "model", "trims", "trim_strict", "year_min", "year_max", "years", "price_min", "price_max",
            "currency", "km_min", "km_max", "transmission", "fuel", "body_types", "sources")
    search = {k: f[k] for k in keep if f.get(k) not in (None, [], "")}
    if profile.get("radius_km"):
        search["radius_km"] = profile["radius_km"]
    if search.get("transmission"):
        search["transmission"] = copy.TRANSMISSION.get(search["transmission"], search["transmission"])
    return {"busqueda": search, "resultados_actuales": results, "embudo": fun.to_json(),
            "filtros": {k: LABEL[k] for k in FILTERS}, "hechos": hints(fun, profile)}
