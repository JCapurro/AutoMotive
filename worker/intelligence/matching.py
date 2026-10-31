"""Matching with reasons (§16, sección 6.1). Pure: no I/O.

`match(listing, profile)` checks each hard filter of the profile and returns
one reason per filter — `ok`, `fail` or `unknown` — plus one per soft
preference. A hard `fail` means no match (None). `unknown` never discards
(the listing may not say its transmission yet, enrichment may fill it) but
lowers the score's match component. The exception is the body type of a
search without a model (docs/CARROCERIA.md): unknown there is a `fail`.

`listing` is a row of `listings`; `profile` a row of `search_profiles`
(filters and preferences as in sección 4.3, plus origin_* / radius_km).
Prices are compared after converting currencies: an ARS listing is checked
against a USD cap with its frozen price_usd, never discarded for being in
another currency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from intelligence import copy
from intelligence.seller import effective_seller, seller_kind
from normalization.geo import haversine_km
from normalization.normalize import normalize_brand, normalize_text


Result = Literal["ok", "fail", "unknown"]
OK: Result = "ok"
FAIL: Result = "fail"
UNKNOWN: Result = "unknown"

# A price filter without a currency (the Telegram wizard makes it optional) is
# read by magnitude: no car is advertised above USD 1.000.000, none below ARS 1.000.000.
_ARS_FROM = 1_000_000


@dataclass(frozen=True)
class Reason:
    result: Result
    detail: str
    hard: bool = True

    def to_json(self) -> dict[str, Any]:
        return {"result": self.result, "detail": self.detail, "kind": "hard" if self.hard else "soft"}


@dataclass
class MatchResult:
    reasons: dict[str, Reason] = field(default_factory=dict)

    @property
    def hard(self) -> dict[str, Reason]:
        return {k: r for k, r in self.reasons.items() if r.hard}

    @property
    def soft(self) -> dict[str, Reason]:
        return {k: r for k, r in self.reasons.items() if not r.hard}

    @property
    def failed(self) -> list[str]:
        return [k for k, r in self.hard.items() if r.result == FAIL]

    @property
    def unknown(self) -> list[str]:
        return [k for k, r in self.hard.items() if r.result == UNKNOWN]

    @property
    def is_match(self) -> bool:
        return not self.failed

    def to_json(self) -> dict[str, Any]:
        return {k: r.to_json() for k, r in self.reasons.items()}


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

def filter_currency(amount: float, currency: str | None) -> str:
    if currency:
        return currency.upper()
    return "ARS" if amount >= _ARS_FROM else "USD"


def price_in(listing: Mapping[str, Any], currency: str, fx_rate: float | None) -> float | None:
    """The listing's published price in `currency`. USD from ARS uses the frozen
    price_usd (the rate of the day it was seen); otherwise today's fx_rate."""
    price, own = listing.get("price"), (listing.get("currency") or "").upper()
    if not price or price <= 0:
        return None
    if own == currency or not own:
        return float(price)
    if currency == "USD":
        if listing.get("price_usd"):
            return float(listing["price_usd"])
        return float(price) / fx_rate if fx_rate else None
    # ARS wanted, USD published
    return float(price) * fx_rate if fx_rate else None


# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------

def _range_detail(value: float, lo: float | None, hi: float | None, fmt) -> tuple[Result, str]:
    if hi is not None and value > hi:
        return FAIL, copy.REASON["km_over"].format(km=fmt(value), cap=fmt(hi))
    if lo is not None and value < lo:
        return FAIL, copy.REASON["km_under"].format(km=fmt(value), floor=fmt(lo))
    shown = fmt(value)
    return OK, copy.REASON["km_ok"].format(km=shown, cap=fmt(hi)) if hi is not None else shown


# POSIX [[:space:]], what search_is_model_less trims.
_SPACE = " \t\n\r\f\v"


def _absent(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip(_SPACE))


def model_less(f: Mapping[str, Any]) -> bool:
    """A search by body type alone (docs/CARROCERIA.md): no make, no model.
    The database's search_is_model_less rule: missing, null or a blank string
    is none; anything else (a non-blank string, or a number, boolean or list
    the database rejects as invalid_filters) is a vehicle."""
    return _absent(f.get("make")) and _absent(f.get("model"))


def wanted_body_types(f: Mapping[str, Any]) -> list[str]:
    wanted = f.get("body_types") or []
    return [wanted] if isinstance(wanted, str) else [b for b in wanted if b]


def malformed_vehicle(f: Mapping[str, Any]) -> bool:
    """A make or model that is neither none nor text: the database rejects it
    (invalid_filters), and a row from before that check matches nothing."""
    return any(v is not None and not isinstance(v, str) for v in (f.get("make"), f.get("model")))


def _model(listing, f) -> Reason | None:
    make, model = f.get("make"), f.get("model")
    if malformed_vehicle(f):
        return Reason(FAIL, copy.REASON["no_vehicle"])
    if model_less(f):
        # Without a vehicle and without a body type, a search would match every listing.
        return None if wanted_body_types(f) else Reason(FAIL, copy.REASON["no_vehicle"])
    wanted = " ".join(x for x in (make, model) if x)
    l_make, l_model = listing.get("make"), listing.get("model")
    if (make and not l_make) or (model and not l_model):
        return Reason(UNKNOWN, copy.NOT_INFORMED)
    actual = " ".join(x for x in (l_make, l_model) if x)
    if make and normalize_brand(l_make) != normalize_brand(make):
        return Reason(FAIL, copy.REASON["model_other"].format(actual=actual, wanted=wanted))
    if model and normalize_text(l_model) != normalize_text(model):
        return Reason(FAIL, copy.REASON["model_other"].format(actual=actual, wanted=wanted))
    return Reason(OK, actual)


def _year(listing, f) -> Reason | None:
    years = f.get("years") or []
    lo = f.get("year_min") or (min(years) if years else None)
    hi = f.get("year_max") or (max(years) if years else None)
    if lo is None and hi is None:
        return None
    year = listing.get("year")
    if year is None:
        return Reason(UNKNOWN, copy.NOT_INFORMED)
    span = dict(lo=lo or "…", hi=hi or "…")
    inside = (lo is None or year >= lo) and (hi is None or year <= hi) and (not years or year in years)
    key = "year_range" if inside else "year_out"
    return Reason(OK if inside else FAIL, copy.REASON[key].format(year=year, **span))


def _price(listing, f, fx_rate) -> Reason | None:
    lo, hi = f.get("price_min"), f.get("price_max")
    if lo is None and hi is None:
        return None
    if listing.get("price_partial"):
        return Reason(UNKNOWN, copy.REASON["price_partial"])
    currency = filter_currency(hi if hi is not None else lo, f.get("currency"))
    own = (listing.get("currency") or currency).upper()
    value = price_in(listing, currency, fx_rate)
    if value is None:
        if not listing.get("price"):
            return Reason(UNKNOWN, copy.NOT_INFORMED)
        return Reason(UNKNOWN, copy.REASON["no_fx"].format(currency=own))
    shown = copy.money(value, currency)
    if own != currency:
        shown = f"{copy.money(listing['price'], own)} ≈ {shown}"
    if hi is not None and value > hi:
        return Reason(FAIL, copy.REASON["price_over"].format(shown=shown, cap=copy.money(hi, currency)))
    if lo is not None and value < lo:
        return Reason(FAIL, copy.REASON["price_under"].format(shown=shown, floor=copy.money(lo, currency)))
    cap = copy.money(hi, currency) if hi is not None else "—"
    return Reason(OK, copy.REASON["price_ok"].format(shown=shown, cap=cap))


def _km(listing, f) -> Reason | None:
    lo, hi = f.get("km_min"), f.get("km_max")
    if lo is None and hi is None:
        return None
    km = listing.get("mileage_km")
    if km is None:
        return Reason(UNKNOWN, copy.NOT_INFORMED)
    result, detail = _range_detail(km, lo, hi, copy.number)
    return Reason(result, detail)


def _choice(value: str | None, wanted: str | None, names: Mapping[str, str], key: str) -> Reason | None:
    if not wanted:
        return None
    if not value:
        return Reason(UNKNOWN, copy.NOT_INFORMED)
    shown = names.get(value, value)
    if normalize_text(wanted) not in normalize_text(value):
        return Reason(FAIL, copy.REASON[key].format(actual=shown, wanted=names.get(wanted, wanted)))
    return Reason(OK, shown)


def _body_type(listing, f) -> Reason | None:
    """Exact membership, never a substring. A listing without a body type is
    `unknown` within a model (it may be filled in later) but fails a search
    by body type alone, or "any SUV" would match every listing without one."""
    wanted = wanted_body_types(f)
    if not wanted:
        return None
    have = listing.get("body_type")
    if not have:
        if model_less(f):
            return Reason(FAIL, copy.REASON["body_type_unknown"])
        return Reason(UNKNOWN, copy.NOT_INFORMED)
    shown = copy.BODY_TYPE.get(have, have)
    if have in wanted:
        return Reason(OK, shown)
    names = " o ".join(copy.BODY_TYPE.get(b, b) for b in wanted)
    return Reason(FAIL, copy.REASON["body_type_other"].format(actual=shown, wanted=names))


def search_zones(profile) -> list[tuple[float, float, float]]:
    """The zones a search looks in as (lat, lon, radius_km): its own place
    (origin_*, radius_km) and the ones it adds (filters.extra_locations, "Chaco
    o Corrientes"). A listing in any of them qualifies."""
    zones: list[tuple[float, float, float]] = []
    if profile.get("radius_km") and profile.get("origin_lat") is not None and profile.get("origin_lon") is not None:
        zones.append((profile["origin_lat"], profile["origin_lon"], profile["radius_km"]))
    for z in (profile.get("filters") or {}).get("extra_locations") or []:
        try:
            lat, lon, radius = float(z["lat"]), float(z["lon"]), float(z["radius_km"])
        except (KeyError, TypeError, ValueError):
            continue
        if radius > 0:
            zones.append((lat, lon, radius))
    return zones


def distance_km(listing, profile) -> float | None:
    """Distance to the search's place; with several zones, to the closest one."""
    if None in (listing.get("lat"), listing.get("lon")):
        return None
    dists = [haversine_km(lat, lon, listing["lat"], listing["lon"]) for lat, lon, _ in search_zones(profile)]
    if not dists and None not in (profile.get("origin_lat"), profile.get("origin_lon")):
        return haversine_km(profile["origin_lat"], profile["origin_lon"], listing["lat"], listing["lon"])
    return min(dists) if dists else None


def _location(listing, profile) -> Reason | None:
    zones = search_zones(profile)
    if not zones:
        return None
    if None in (listing.get("lat"), listing.get("lon")):
        # The search asked for a zone: a listing that can't be placed in it
        # doesn't qualify (it used to pass as unknown and reached people 400 km away).
        return Reason(FAIL, copy.REASON["no_coords"])
    place = listing.get("location_text") or "—"
    # The zone it is in, or the one it misses by the least.
    dist, radius = min(((haversine_km(lat, lon, listing["lat"], listing["lon"]), r) for lat, lon, r in zones),
                       key=lambda zr: zr[0] - zr[1])
    if dist > radius:
        return Reason(FAIL, copy.REASON["distance_over"].format(
            place=place, km=copy.number(dist), radius=copy.number(radius)))
    return Reason(OK, copy.REASON["distance"].format(place=place, km=copy.number(dist)))


def _source(listing, f) -> Reason | None:
    sources = f.get("sources")
    if not sources:
        return None
    if listing.get("source") in sources:
        return Reason(OK, listing["source"])
    return Reason(FAIL, copy.REASON["source_other"].format(source=listing.get("source")))


# PRO-01: filters.seller_types, the strict seller filter (Pro). A
# «posible agencia» counts as a dealer (intelligence/seller.py, F-02).
SELLER_TYPES = ("private", "dealer")


def seller_types(f: Mapping[str, Any]) -> list[str]:
    """The valid values of filters.seller_types; anything else (a string, an
    unknown type, a write by API) is none. search_filters_problem rejects it too."""
    wanted = f.get("seller_types")
    if not isinstance(wanted, list):
        return []
    return [t for t in wanted if isinstance(t, str) and t in SELLER_TYPES]


def strict_seller(profile: Mapping[str, Any]) -> bool:
    """The hard seller check runs only for a plan with plan_feature('seller_filter'):
    db/repos/profiles.py reads it into profile["seller_filter"]. Without it the
    stored type is a soft preference (_preferences)."""
    return bool(profile.get("seller_filter")) and bool(seller_types(profile.get("filters") or {}))


def _seller(listing, profile) -> Reason | None:
    if not strict_seller(profile):
        return None
    wanted = seller_types(profile.get("filters") or {})
    have = effective_seller(listing)
    if not have:
        return Reason(UNKNOWN, copy.NOT_INFORMED)
    kind = seller_kind(listing)
    if have in wanted:
        return Reason(OK, copy.REASON["seller_ok"].format(kind=kind))
    names = " o ".join(copy.SELLER_ONLY.get(t, t) for t in wanted)
    return Reason(FAIL, copy.REASON["seller_only_other"].format(kind=kind, wanted=names))


def trim_matches(trim: str | None, wanted: str) -> bool:
    """"1.6 Titanium" is a Titanium: every word of the wanted trim is in it."""
    have = set(normalize_text(trim).replace("!", "").split())
    need = normalize_text(wanted).replace("!", "").split()
    return bool(need) and all(w in have for w in need)


def preferred_trims(profile) -> list[str]:
    f, p = profile.get("filters") or {}, profile.get("preferences") or {}
    out: list[str] = []
    for t in [*(f.get("trims") or []), *(p.get("preferred_trims") or [])]:
        if t and t not in out:
            out.append(t)
    return out


def _trim(listing, profile) -> Reason | None:
    f = profile.get("filters") or {}
    wanted = preferred_trims(profile)
    if not wanted:
        return None
    hard = bool(f.get("trim_strict")) and bool(f.get("trims"))
    trim = listing.get("trim")
    if not trim:
        return Reason(UNKNOWN, copy.NOT_INFORMED, hard=hard)
    if any(trim_matches(trim, w) for w in wanted):
        return Reason(OK, copy.REASON["trim_preferred"].format(trim=trim), hard=hard)
    return Reason(FAIL, copy.REASON["trim_other"].format(trim=trim, wanted=" / ".join(wanted)), hard=hard)


# ---------------------------------------------------------------------------
# Soft preferences (they feed the score, never discard)
# ---------------------------------------------------------------------------

def _soft(result: Result, detail: str) -> Reason:
    return Reason(result, detail, hard=False)


def _preferences(listing, profile, fx_rate) -> dict[str, Reason]:
    p = profile.get("preferences") or {}
    out: dict[str, Reason] = {}

    if (target := p.get("km_target")) is not None:
        km = listing.get("mileage_km")
        out["km_target"] = (_soft(UNKNOWN, copy.NOT_INFORMED) if km is None else
                            _soft(OK if km <= target else FAIL, f"{copy.number(km)} / {copy.number(target)}"))

    if (target := p.get("price_target")) is not None:
        currency = filter_currency(target, p.get("price_target_currency")
                                   or (profile.get("filters") or {}).get("currency"))
        value = None if listing.get("price_partial") else price_in(listing, currency, fx_rate)
        out["price_target"] = (_soft(UNKNOWN, copy.NOT_INFORMED) if value is None else
                               _soft(OK if value <= target else FAIL,
                                     f"{copy.money(value, currency)} / {copy.money(target, currency)}"))

    # PRO-01: with the hard check active the soft one is left out (no double
    # count); without the plan feature the stored type is the soft preference.
    stored = seller_types(profile.get("filters") or {})
    seller = None if strict_seller(profile) else (p.get("seller_type") or (stored[0] if stored else None))
    if seller:
        # F-02: a «posible agencia» counts as a dealer (intelligence/seller.py).
        have = effective_seller(listing)
        kind, want = seller_kind(listing), copy.SELLER.get(seller, seller)
        out["seller_type"] = (_soft(UNKNOWN, copy.NOT_INFORMED) if not have else
                              _soft(OK, copy.REASON["seller_ok"].format(kind=kind)) if have == seller else
                              _soft(FAIL, copy.REASON["seller_other"].format(kind=kind, wanted=want)))

    if colors := p.get("colors"):
        color = (listing.get("attributes") or {}).get("color") or (listing.get("attributes") or {}).get("Color")
        wanted = {normalize_text(c) for c in colors}
        out["colors"] = (_soft(UNKNOWN, copy.NOT_INFORMED) if not color else
                         _soft(OK, copy.REASON["color_ok"].format(color=color))
                         if normalize_text(color) in wanted else
                         _soft(FAIL, copy.REASON["color_other"].format(color=color, wanted=", ".join(colors))))

    if (max_km := p.get("max_distance_km")) is not None:
        dist = distance_km(listing, profile)
        out["max_distance_km"] = (_soft(UNKNOWN, copy.REASON["no_coords"]) if dist is None else
                                  _soft(OK if dist <= max_km else FAIL,
                                        f"{copy.number(dist)} km / {copy.number(max_km)} km"))
    return out


def evaluate(listing: Mapping[str, Any], profile: Mapping[str, Any], *,
             fx_rate: float | None = None) -> MatchResult:
    """Every reason, whether it matches or not (explain_match shows the fails too)."""
    f = profile.get("filters") or {}
    checks = {
        "model": _model(listing, f),
        "year": _year(listing, f),
        "price": _price(listing, f, fx_rate),
        "km": _km(listing, f),
        "transmission": _choice(listing.get("transmission"), f.get("transmission"),
                                copy.TRANSMISSION, "transmission_other"),
        "fuel": _choice(listing.get("fuel"), f.get("fuel"), {}, "fuel_other"),
        "body_type": _body_type(listing, f),
        "location": _location(listing, profile),
        "source": _source(listing, f),
        "seller": _seller(listing, profile),
        "trim": _trim(listing, profile),
    }
    result = MatchResult({k: r for k, r in checks.items() if r is not None})
    result.reasons.update(_preferences(listing, profile, fx_rate))
    return result


def match(listing: Mapping[str, Any], profile: Mapping[str, Any], *,
          fx_rate: float | None = None) -> MatchResult | None:
    """The reasons if every hard filter is ok or unknown; None if one fails."""
    result = evaluate(listing, profile, fx_rate=fx_rate)
    return result if result.is_match else None
