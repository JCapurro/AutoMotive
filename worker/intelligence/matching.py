"""Matching with reasons (§16, sección 6.1). Pure: no I/O.

`match(listing, profile)` checks each hard filter of the profile and returns
one reason per filter — `ok`, `fail` or `unknown` — plus one per soft
preference. A hard `fail` means no match (None). `unknown` never discards
(the listing may not say its transmission yet, enrichment may fill it) but
lowers the score's match component.

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


def _model(listing, f) -> Reason | None:
    make, model = f.get("make"), f.get("model")
    if not make and not model:
        return None
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


def distance_km(listing, profile) -> float | None:
    if None in (listing.get("lat"), listing.get("lon"), profile.get("origin_lat"), profile.get("origin_lon")):
        return None
    return haversine_km(profile["origin_lat"], profile["origin_lon"], listing["lat"], listing["lon"])


def _location(listing, profile) -> Reason | None:
    radius = profile.get("radius_km")
    if not radius or profile.get("origin_lat") is None or profile.get("origin_lon") is None:
        return None
    dist = distance_km(listing, profile)
    if dist is None:
        return Reason(UNKNOWN, copy.REASON["no_coords"])
    place = listing.get("location_text") or "—"
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

    if seller := p.get("seller_type"):
        have = listing.get("seller_type")
        kind, want = copy.SELLER.get(have or "", have), copy.SELLER.get(seller, seller)
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
        "location": _location(listing, profile),
        "source": _source(listing, f),
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
