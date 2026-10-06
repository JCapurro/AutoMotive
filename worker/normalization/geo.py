from __future__ import annotations

import asyncio
import logging
import math
import re
import unicodedata
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

import httpx
from http_clients import async_client

import db
from config import GEOCODING_ENABLED, GEOCODING_USER_AGENT


log = logging.getLogger("geo")

Coords = tuple[float, float]
GeocodeFn = Callable[[str], Awaitable[Coords | None]]

_EARTH_RADIUS_KM = 6371.0088
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(ch)
    )


def normalize_location_query(value: str | None) -> str:
    if not value:
        return ""
    s = _strip_accents(value).lower()
    s = s.replace("bs.as.", "buenos aires")
    s = s.replace("bs. as.", "buenos aires")
    s = s.replace("bs as", "buenos aires")
    s = s.replace("gba", "g b a")
    s = s.replace("c.a.b.a.", "caba")
    s = _NON_ALNUM_RE.sub(" ", s)
    return " ".join(s.split())


_KNOWN_LOCATIONS_RAW: dict[str, Coords] = {
    "argentina": (-38.4161, -63.6167),
    "buenos aires": (-34.6037, -58.3816),
    "capital federal": (-34.6037, -58.3816),
    "caba": (-34.6037, -58.3816),
    "ciudad autonoma de buenos aires": (-34.6037, -58.3816),
    "la plata": (-34.9205, -57.9536),
    "mar del plata": (-38.0055, -57.5426),
    "bahia blanca": (-38.7183, -62.2663),
    # GBA Norte
    "del viso": (-34.4500, -58.8000),
    "pilar": (-34.4587, -58.9142),
    "san isidro": (-34.4708, -58.5286),
    "tigre": (-34.4261, -58.5796),
    "vicente lopez": (-34.5299, -58.4742),
    "san fernando": (-34.4416, -58.5598),
    "escobar": (-34.3494, -58.7916),
    "san martin": (-34.5763, -58.5364),
    "general san martin": (-34.5763, -58.5364),
    "tres de febrero": (-34.6053, -58.5630),
    "caseros": (-34.6047, -58.5640),
    "munro": (-34.5273, -58.5224),
    "florida": (-34.5269, -58.4989),
    "olivos": (-34.5102, -58.4922),
    "boulogne": (-34.4991, -58.5644),
    "boulogne sur mer": (-34.4991, -58.5644),
    "beccar": (-34.4625, -58.5234),
    "acassuso": (-34.4712, -58.5018),
    "martinez": (-34.4865, -58.5007),
    "bella vista": (-34.5727, -58.6928),
    "don torcuato": (-34.4906, -58.6181),
    "general rodriguez": (-34.6072, -58.9489),
    "jose c paz": (-34.5167, -58.7667),
    "san miguel": (-34.5460, -58.7128),
    "malvinas argentinas": (-34.4950, -58.6925),
    "victoria": (-34.4533, -58.5483),
    "nordelta": (-34.4022, -58.6483),
    # GBA Oeste
    "moron": (-34.6534, -58.6198),
    "la matanza": (-34.7086, -58.6306),
    "ituzaingo": (-34.6584, -58.6691),
    "castelar": (-34.6494, -58.6448),
    "hurlingham": (-34.5897, -58.6394),
    "merlo": (-34.6664, -58.7282),
    "moreno": (-34.6334, -58.7895),
    "ramos mejia": (-34.6447, -58.5697),
    "ciudadela": (-34.6406, -58.5400),
    "haedo": (-34.6400, -58.5917),
    "san justo": (-34.6764, -58.5614),
    "gregorio de laferrere": (-34.7488, -58.6063),
    "san antonio de padua": (-34.6692, -58.7142),
    "padua": (-34.6692, -58.7142),
    "lujan": (-34.5703, -59.1051),
    # GBA Sur
    "quilmes": (-34.7203, -58.2545),
    "avellaneda": (-34.6611, -58.3669),
    "lanus": (-34.7058, -58.3917),
    "lomas de zamora": (-34.7612, -58.4302),
    "banfield": (-34.7424, -58.4015),
    "adrogue": (-34.7989, -58.3897),
    "almirante brown": (-34.8008, -58.3936),
    "berazategui": (-34.7644, -58.2125),
    "florencio varela": (-34.8005, -58.2770),
    "ezeiza": (-34.8553, -58.5238),
    "esteban echeverria": (-34.8067, -58.4783),
    "bernal": (-34.7110, -58.2823),
    "el pato": (-34.9183, -58.2522),
    "glew": (-34.8967, -58.3753),
    # Zonas genericas (ranking inferior)
    "g b a norte": (-34.4708, -58.5286),
    "g b a oeste": (-34.6534, -58.6198),
    "g b a sur": (-34.7203, -58.2545),
    "zona norte": (-34.4708, -58.5286),
    "zona oeste": (-34.6534, -58.6198),
    "zona sur": (-34.7203, -58.2545),
    # Bs.As. interior
    "chascomus": (-35.5734, -58.0103),
    "olavarria": (-36.8975, -60.3220),
    "tandil": (-37.3217, -59.1332),
    "junin": (-34.5934, -60.9486),
    "pergamino": (-33.8983, -60.5749),
    "arrecifes": (-34.0613, -60.1041),
    "zarate": (-34.0942, -59.0273),
    "campana": (-34.1670, -58.9601),
    "san pedro": (-33.6800, -59.6700),
    "baradero": (-33.8051, -59.5057),
    "lobos": (-35.1881, -59.0915),
    "mercedes": (-34.6517, -59.4317),
    # Resto del pais
    "cordoba": (-31.4201, -64.1888),
    "rosario": (-32.9442, -60.6505),
    "santa fe": (-31.6107, -60.6973),
    "rafaela": (-31.2503, -61.4864),
    "humboldt": (-31.0464, -60.8514),
    "mendoza": (-32.8895, -68.8458),
    "san miguel de tucuman": (-26.8083, -65.2176),
    "tucuman": (-26.8083, -65.2176),
    "salta": (-24.7821, -65.4232),
    "san juan": (-31.5375, -68.5364),
    "san luis": (-33.3017, -66.3378),
    "parana": (-31.7413, -60.5115),
    "entre rios": (-31.7747, -60.4956),
    "corrientes": (-27.4692, -58.8306),
    "resistencia": (-27.4519, -58.9867),
    "posadas": (-27.3621, -55.9009),
    "neuquen": (-38.9516, -68.0591),
    "rio negro": (-40.8135, -63.0000),
    "bariloche": (-41.1335, -71.3103),
    "viedma": (-40.8135, -62.9967),
    "chubut": (-43.2934, -65.1115),
    "comodoro rivadavia": (-45.8641, -67.4966),
    "santa cruz": (-51.6230, -69.2168),
    "rio gallegos": (-51.6230, -69.2168),
    "jujuy": (-24.1858, -65.2995),
    "san salvador de jujuy": (-24.1858, -65.2995),
    "formosa": (-26.1849, -58.1731),
    "catamarca": (-28.4696, -65.7852),
    "la rioja": (-29.4135, -66.8565),
    "la pampa": (-36.6208, -64.2906),
    "santa rosa": (-36.6208, -64.2906),
    "santiago del estero": (-27.7834, -64.2642),
    "ushuaia": (-54.8019, -68.3030),
    "tierra del fuego": (-54.8019, -68.3030),
}

KNOWN_LOCATIONS: dict[str, Coords] = {
    normalize_location_query(name): coords for name, coords in _KNOWN_LOCATIONS_RAW.items()
}

# When a listing string matches BOTH a specific city and a province-level
# fallback (e.g., "Munro - Buenos Aires" matches both "munro" and "buenos
# aires"), prefer the specific one. These broad keys lose the tiebreak.
_PROVINCE_FALLBACKS: set[str] = {
    normalize_location_query(name)
    for name in (
        "argentina", "buenos aires", "cordoba", "santa fe", "mendoza",
        "tucuman", "salta", "san juan", "san luis", "entre rios",
        "corrientes", "neuquen", "rio negro", "chubut", "santa cruz",
        "jujuy", "formosa", "catamarca", "la rioja", "la pampa",
        "santiago del estero", "tierra del fuego",
        "g b a norte", "g b a oeste", "g b a sur",
        "zona norte", "zona oeste", "zona sur",
    )
}

_VEHICLE_TERMS = {
    "ford", "chevrolet", "volkswagen", "vw", "toyota", "fiat", "renault",
    "peugeot", "citroen", "honda", "nissan", "jeep", "mercedes", "benz",
    "audi", "bmw", "fiesta", "onix", "gol", "trend", "ka", "polo",
    "yaris", "corolla", "ranger", "hilux", "cruze",
}
_DISTANCE_NOISE_RE = re.compile(
    r"\b\d+(?:\s+\d+)?\s*(?:mil\s+)?(?:km|kilometros?|miles?)\b"
)
_YEAR_TOKEN_RE = re.compile(r"\b(19[8-9]\d|20[0-3]\d)\b")


def _looks_like_non_location_query(normalized: str) -> bool:
    """Reject card noise before it can spend Nominatim quota."""
    if _DISTANCE_NOISE_RE.search(normalized):
        return True
    tokens = set(normalized.split())
    return bool(_YEAR_TOKEN_RE.search(normalized) and tokens.intersection(_VEHICLE_TERMS))


def _fallback_can_stand_alone(normalized: str, fallback_key: str) -> bool:
    """Allow broad fallbacks only for exact or duplicate broad labels."""
    tokens = normalized.split()
    key_tokens = set(fallback_key.split())
    return bool(tokens) and all(token in key_tokens for token in tokens)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _lookup_known_location(query: str) -> Coords | None:
    normalized = normalize_location_query(query)
    if not normalized:
        return None
    if normalized in KNOWN_LOCATIONS:
        return KNOWN_LOCATIONS[normalized]

    matches: list[tuple[int, str, Coords, bool]] = []  # (key_len, key, coords, is_specific)
    for key, coords in KNOWN_LOCATIONS.items():
        if key and re.search(rf"\b{re.escape(key)}\b", normalized):
            is_specific = key not in _PROVINCE_FALLBACKS
            matches.append((len(key), key, coords, is_specific))
    if not matches:
        return None
    # Specific city beats province-level fallback ("Munro - Buenos Aires" → Munro)
    specific = [m for m in matches if m[3]]
    if specific:
        return max(specific, key=lambda item: item[0])[2]

    fallback = max(matches, key=lambda item: item[0])
    if _fallback_can_stand_alone(normalized, fallback[1]):
        return fallback[2]
    return None


def nearest_known_location_name(lat: float, lon: float, names: Iterable[str]) -> str | None:
    best_name: str | None = None
    best_distance: float | None = None
    for name in names:
        coords = _lookup_known_location(name)
        if not coords:
            continue
        distance = haversine_km(lat, lon, coords[0], coords[1])
        if best_distance is None or distance < best_distance:
            best_name = name
            best_distance = distance
    return best_name


async def geocode_location(location: str) -> Coords | None:
    query = normalize_location_query(location)
    if not query:
        return None

    if known := _lookup_known_location(query):
        return known

    if _looks_like_non_location_query(query):
        return None

    cached = await db.get_geocode_cache(query)
    if cached:
        return cached

    # If we recently tried this query and Nominatim said "no" (or 429'd us),
    # don't keep hammering — the negative cache TTL will let us retry later.
    if await db.has_fresh_geocode_failure(query):
        return None

    if not GEOCODING_ENABLED:
        return None

    coords = await _geocode_nominatim(query)
    if coords:
        await db.set_geocode_cache(query, coords[0], coords[1], "nominatim")
    else:
        await db.set_geocode_cache_failure(query, "nominatim")
    return coords


# Nominatim public-policy: "absolute maximum 1 request per second". We add a
# small margin and serialize calls across this process via a module-level
# lock + last-call timestamp.
_NOMINATIM_MIN_INTERVAL = 1.1
_nominatim_lock = asyncio.Lock()
_nominatim_last_call = 0.0


async def _geocode_nominatim(query: str) -> Coords | None:
    global _nominatim_last_call
    params = {
        "q": f"{query}, Argentina",
        "format": "jsonv2",
        "limit": "1",
        "countrycodes": "ar",
    }
    headers = {"User-Agent": GEOCODING_USER_AGENT or "AutoMotiveAlerts/1.0"}
    async with _nominatim_lock:
        loop = asyncio.get_running_loop()
        elapsed = loop.time() - _nominatim_last_call
        if elapsed < _NOMINATIM_MIN_INTERVAL:
            await asyncio.sleep(_NOMINATIM_MIN_INTERVAL - elapsed)
        try:
            async with async_client(timeout=8.0, headers=headers) as client:
                response = await client.get(
                    "https://nominatim.openstreetmap.org/search", params=params
                )
                response.raise_for_status()
                data: list[dict[str, Any]] = response.json()
        except Exception as exc:
            log.warning("geocoding failed for %r: %s", query, exc)
            _nominatim_last_call = loop.time()
            return None
        finally:
            _nominatim_last_call = loop.time()

    if not data:
        return None
    try:
        return float(data[0]["lat"]), float(data[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def _origin_from_filters(filters: dict) -> Coords | None:
    try:
        lat = float(filters["origin_lat"])
        lon = float(filters["origin_lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _radius_from_filters(filters: dict) -> float | None:
    try:
        radius = float(filters["radio_km"])
    except (KeyError, TypeError, ValueError):
        return None
    return radius if radius > 0 else None


async def filter_listings_by_radius(
    listings: Iterable[Any],
    filters: dict,
    *,
    geocode_fn: GeocodeFn = geocode_location,
) -> list[Any]:
    origin = _origin_from_filters(filters)
    radius = _radius_from_filters(filters)
    items = list(listings)
    if not origin or radius is None:
        return items

    out: list[Any] = []
    cache: dict[str, Coords | None] = {}
    for item in items:
        location = getattr(item, "ubicacion", None)
        if not location:
            if getattr(item, "source", None) == "kavak":
                out.append(item)
            continue
        if location not in cache:
            cache[location] = await geocode_fn(location)
        coords = cache[location]
        if not coords:
            continue
        distance = haversine_km(origin[0], origin[1], coords[0], coords[1])
        if distance <= radius:
            extra = getattr(item, "extra", None)
            if isinstance(extra, dict):
                extra["distance_km"] = round(distance, 1)
            out.append(item)
    return out
