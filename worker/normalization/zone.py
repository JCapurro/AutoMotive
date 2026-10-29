"""The zone of a listing, from its coordinates (F-03 fase 0,
docs/superpowers/specs/2026-10-29-f03-market-stats-fase0-design.md).

derive_zone() takes the Georef locality nearest to the listing's lat/lon and
keeps only geographic facts: its province (INDEC code), department, locality
and distance, plus how much the place can be trusted (`precision`):

* locality: the text names a place below the province;
* province: the text is just a province name or "argentina" (geo.py puts
  "Buenos Aires" alone on CABA, so the coordinates say nothing more);
* source_default: no text, the source's town (SOURCE_DEFAULT_LOCATIONS).

The region is not stored with the listing: resolve_region() maps those facts
with app_config.market_zones (seeded from DEFAULT_ZONE_MAP) when the stats are
computed, so editing the map rewrites nothing. A province-precision place only
gets a region when its whole province is in one (Buenos Aires alone: none).

Pure: no network, no database. The localities are a copy of
web/lib/data/argentina-locations.json (a test keeps them identical).
"""
from __future__ import annotations

import copy
import json
import math
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from normalization.geo import (SOURCE_DEFAULT_LOCATIONS, clean_location_text, haversine_km,
                               normalize_location_query)

_DATA = Path(__file__).resolve().parent / "data" / "ar_localities.json"

# How many localities, nearest by a flat approximation, get the real distance.
_CANDIDATES = 8

_GBA_PARTIDOS = [
    "Almirante Brown", "Avellaneda", "Berazategui", "Esteban Echeverría", "Ezeiza",
    "Florencio Varela", "General San Martín", "Hurlingham", "Ituzaingó", "José C. Paz",
    "La Matanza", "Lanús", "Lomas de Zamora", "Malvinas Argentinas", "Merlo", "Moreno",
    "Morón", "Quilmes", "San Fernando", "San Isidro", "San Miguel", "Tigre",
    "Tres de Febrero", "Vicente López",
]

# Approved by Juan on 29/10/2026 (decision 1 of the design). Rules are tried in
# order, the first that matches wins: the GBA before the rest of province 06.
# The migration 20261119110000 seeds app_config.market_zones with this map.
DEFAULT_ZONE_MAP: dict[str, Any] = {
    "version": 1,
    "regions": {
        "amba": "AMBA",
        "buenos_aires_resto": "Resto de Buenos Aires",
        "cordoba": "Córdoba",
        "litoral": "Litoral",
        "nea": "NEA",
        "cuyo": "Cuyo",
        "noa": "NOA",
        "patagonia": "Patagonia",
    },
    "rules": [
        {"region": "amba", "province": "02"},
        {"region": "amba", "province": "06", "departments": _GBA_PARTIDOS},
        {"region": "buenos_aires_resto", "province": "06"},
        {"region": "cordoba", "province": "14"},
        *({"region": "litoral", "province": p} for p in ("82", "30")),
        *({"region": "nea", "province": p} for p in ("18", "54", "22", "34")),
        *({"region": "cuyo", "province": p} for p in ("50", "70", "74")),
        *({"region": "noa", "province": p} for p in ("66", "90", "38", "86", "10", "46")),
        *({"region": "patagonia", "province": p} for p in ("58", "62", "26", "78", "94", "42")),
    ],
}

# Province names as the sources write them, besides Georef's own.
_PROVINCE_ALIASES = {
    "caba": "02", "capital federal": "02", "ciudad de buenos aires": "02",
    "tierra del fuego": "94",
}


@dataclass(frozen=True)
class Locality:
    id: str
    name: str
    province_id: str
    department: str
    lat: float
    lon: float
    dist_km: float = 0.0


@dataclass(frozen=True)
class Localities:
    provinces: list[tuple[str, str]]
    cities: list[Locality]


@dataclass(frozen=True)
class ZoneFacts:
    province_id: str | None
    department: str | None
    locality_id: str | None
    dist_km: float | None
    precision: str          # locality | province | source_default
    lat: float
    lon: float


@lru_cache(maxsize=1)
def load_localities() -> Localities:
    data = json.loads(_DATA.read_text(encoding="utf-8"))
    return Localities(
        provinces=[(pid, name) for pid, name in data["provinces"]],
        cities=[Locality(cid, name, pid, dept, float(lat), float(lon))
                for cid, name, pid, dept, lat, lon in data["cities"]],
    )


@lru_cache(maxsize=1)
def _province_names() -> dict[str, str]:
    names = {normalize_location_query(name): pid for pid, name in load_localities().provinces}
    names.update(_PROVINCE_ALIASES)
    return names


@lru_cache(maxsize=4096)
def nearest_locality(lat: float, lon: float) -> Locality:
    """The Georef locality nearest to (lat, lon). A flat distance picks a few
    candidates, haversine_km decides among them."""
    scale = math.cos(math.radians(lat)) ** 2
    cities = load_localities().cities
    candidates = sorted(cities, key=lambda c: (c.lat - lat) ** 2 + scale * (c.lon - lon) ** 2)[:_CANDIDATES]
    best = min(candidates, key=lambda c: haversine_km(lat, lon, c.lat, c.lon))
    return Locality(best.id, best.name, best.province_id, best.department, best.lat, best.lon,
                    round(haversine_km(lat, lon, best.lat, best.lon), 2))


_CABA, _BUENOS_AIRES = "02", "06"


def _province_only(text: str) -> tuple[bool, str | None]:
    """Whether the text names just a province (or the country), and which one.
    CABA with Buenos Aires around it ("Capital Federal, Buenos Aires") is CABA."""
    parts = {normalize_location_query(p) for p in text.split(",")} - {""}
    names = _province_names()
    provinces = {names[p] for p in parts if p in names}
    if not parts or not parts <= set(names) | {"argentina"}:
        return False, None
    if provinces == {_CABA, _BUENOS_AIRES}:
        return True, _CABA
    return True, (provinces.pop() if len(provinces) == 1 else None)


def derive_zone(lat: float | None, lon: float | None, location_text: str | None,
                source: str | None) -> ZoneFacts | None:
    if lat is None or lon is None:
        return None
    lat, lon = float(lat), float(lon)
    clean = clean_location_text(location_text)
    if clean is not None:
        is_province, province_id = _province_only(clean)
        if is_province:
            return ZoneFacts(province_id, None, None, None, "province", lat, lon)
    loc = nearest_locality(lat, lon)
    precision = "source_default" if clean is None and source in SOURCE_DEFAULT_LOCATIONS else "locality"
    return ZoneFacts(loc.province_id, loc.department, loc.id, loc.dist_km, precision, lat, lon)


def _fold(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", value.lower()) if unicodedata.category(c) != "Mn")


@dataclass(frozen=True)
class _CompiledMap:
    # Per province, its rules in order: (region, folded departments or None for all).
    rules: dict[str, list[tuple[str | None, frozenset[str] | None]]]
    # Per province, its region when the whole province is in one (else None).
    whole: dict[str, str | None]


def _compile(zone_map: dict[str, Any]) -> _CompiledMap:
    rules: dict[str, list[tuple[str | None, frozenset[str] | None]]] = {}
    for r in zone_map.get("rules", []):
        departments = r.get("departments")
        rules.setdefault(r.get("province"), []).append(
            (r.get("region"), None if departments is None else frozenset(_fold(d) for d in departments)))
    whole = {}
    for province, prules in rules.items():
        regions = {region for region, _ in prules}
        whole[province] = regions.pop() if len(regions) == 1 else None
    return _CompiledMap(rules, whole)


def _compiled(zone_map: dict[str, Any]) -> _CompiledMap:
    """The map prepared once per config: the stats resolve a region per listing
    and the map only changes when /admin/config does. The last map is kept, by
    identity and, failing that, by value (get_config hands a new dict each run)."""
    hit = _compiled.cache
    if hit is not None and hit[0] is zone_map:
        return hit[2]
    if hit is not None and hit[1] == zone_map:
        _compiled.cache = (zone_map, hit[1], hit[2])   # same map, new dict: next lookup by identity
        return hit[2]
    compiled = _compile(zone_map)
    _compiled.cache = (zone_map, copy.deepcopy(zone_map), compiled)
    return compiled


_compiled.cache = None  # type: ignore[attr-defined]


def resolve_region(zone_map: dict[str, Any], province_id: str | None, department: str | None,
                   precision: str | None) -> str | None:
    """The region of a place by the first rule of `zone_map` that matches it.
    A province-precision place only when its whole province is in one region."""
    if not province_id:
        return None
    compiled = _compiled(zone_map or {})
    if precision == "province":
        return compiled.whole.get(province_id)
    folded = _fold(department) if department else None
    for region, departments in compiled.rules.get(province_id, ()):
        if departments is None or (folded is not None and folded in departments):
            return region
    return None
