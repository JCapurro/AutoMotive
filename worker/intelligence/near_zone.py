"""Aviso de auto cerca de la zona (docs/AVISO_CERCA_DE_ZONA.md). Pure: no database, no channels.

    a search with one zone of its own and few results
      → its make/model's listings first seen since it exists, still recent
      → the ones every hard filter passes but the zone (matching.evaluate),
        with a known year and nothing the search asked for left unknown
      → within max_extra_km of the zone's edge: the closest one

The search is never widened here: the email shows the car and its owner decides.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any, Iterable, Mapping

from intelligence.matching import evaluate, search_zones
from normalization.geo import haversine_km
from normalization.not_vehicle import part_reason, toy_reason, wanted_reason

DEFAULTS: dict[str, Any] = {"enabled": False, "max_results": 3, "max_extra_km": 100, "max_age_days": 3,
                            "cooldown_days": 3, "max_per_tick": 10, "send_from": "09:00", "send_until": "21:00"}
_NUMBERS = ("max_results", "max_extra_km", "max_age_days", "cooldown_days", "max_per_tick")


def _clock(value: Any) -> time | None:
    """'09:00' → 09:00; None if it isn't HH:MM."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), "%H:%M").time()
    except ValueError:
        return None


def settings(raw: Any) -> dict[str, Any]:
    """app_config.near_zone over DEFAULTS. On only with enabled exactly true; a
    bad number or hour falls back to its default."""
    cfg = raw if isinstance(raw, Mapping) else {}
    out: dict[str, Any] = {"enabled": cfg.get("enabled") is True}
    for key in _NUMBERS:
        value = cfg.get(key)
        ok = isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
        out[key] = value if ok else DEFAULTS[key]
    start, end = _clock(cfg.get("send_from")), _clock(cfg.get("send_until"))
    if start is None or end is None or start >= end:
        start, end = _clock(DEFAULTS["send_from"]), _clock(DEFAULTS["send_until"])
    out["send_from"], out["send_until"] = start, end
    return out


def own_zone(profile: Mapping[str, Any]) -> tuple[float, float, float] | None:
    """The search's single zone (lat, lon, radius_km), or None: no zone, or
    extra places («Chaco o Corrientes»), where «a N km de tu zona» has no one answer."""
    zones = search_zones(profile)
    if len(zones) != 1 or (profile.get("filters") or {}).get("extra_locations"):
        return None
    return zones[0]


def eligible(profile: Mapping[str, Any]) -> bool:
    f = profile.get("filters") or {}
    return bool(f.get("make") and f.get("model")) and own_zone(profile) is not None


def confirmed(listing: Mapping[str, Any], profile: Mapping[str, Any], *, fx_rate: float | None = None) -> bool:
    """Whether the listing is a car this search would show but for its zone,
    on known data. A result may pass a filter as unknown; this email shows one
    car alone, so it may not: on 14/11/2026 the first pass told a search for a
    2003 Gol about a listing without a year, and another about an engine.
    The year is always needed (a car without one can't be told from an older
    one), and a title that names a part, a scale model or a wanted post is out
    whatever else the listing says."""
    title = listing.get("title")
    if listing.get("year") is None or part_reason(title) or toy_reason(title) or wanted_reason(title):
        return False
    result = evaluate(listing, profile, fx_rate=fx_rate)
    return result.failed == ["location"] and not result.unknown


def pick(listings: Iterable[Mapping[str, Any]], profile: Mapping[str, Any], *, created_at: datetime,
         now: datetime, cfg: Mapping[str, Any], fx_rate: float | None = None,
         seen: Iterable[int] = ()) -> tuple[Mapping[str, Any], float] | None:
    """The listing to tell this search about and its distance in km, or None.

    New for the search (first seen since it was created) and still recent,
    with a full price and coordinates, failing only the zone on known data
    (`confirmed`), at most max_extra_km past its edge. `seen` are the
    listings already told."""
    zone = own_zone(profile)
    if zone is None:
        return None
    lat, lon, radius = zone
    told, oldest = frozenset(seen), now - timedelta(days=cfg["max_age_days"])
    best: tuple[Mapping[str, Any], float] | None = None
    for listing in listings:
        first = listing.get("first_seen_at")
        if (listing.get("id") in told or first is None or first < created_at
                or (listing.get("published_at") or first) < oldest
                or listing.get("price") is None or listing.get("price_partial")
                or listing.get("lat") is None or listing.get("lon") is None):
            continue
        dist = haversine_km(lat, lon, listing["lat"], listing["lon"])
        if dist <= radius or dist - radius > cfg["max_extra_km"] or (best is not None and dist >= best[1]):
            continue
        if confirmed(listing, profile, fx_rate=fx_rate):
            best = (listing, dist)
    return best
