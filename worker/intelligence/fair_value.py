"""«Valor justo» per model (docs/superpowers/specs/2026-11-20-valor-justo-design.md §3, §5), in SHADOW MODE. Pure.

    fit(rows, params)                        → Curve | None       (§3.2)
    evaluate(curve, rows, params, …)         → Gate               (§3.5: cv_err, cohort_err, enabled)
    fair_value(listing, curve)               → FairValue | None   (§3.3)
    rule_h(ref, fetched, value, min_n=…)     → bool               (§3.4)
    shadow(listing, profile, result, …)      → the JSON of matches.score_breakdown.shadow_fair_value (§5)

Per model, in logs of the USD price:

    ln(value) = A[year] + G[trim] + H[transmission] + B · (ln(km) − KM[year])

fitted with medians (the worker has no numpy) over public.price_pool(make, model). G is keyed by lower(trim),
the key today's twins use; H by lower(transmission); both 0 for a missing or rare value. KM[year] is the
mean ln(km) of that year's listings inside km_range; the km term is 0 outside it or without km.

f2 keeps deciding everything with today's reference (comparables()); nothing here changes a score, a level,
an alert or a text. `shadow()` never raises and only returns JSON-safe values (finite rounded floats, ints,
booleans, strings): it travels in the same JSON as f2's match row, where a NaN or a Decimal would fail the
write of the whole batch.

Choices the spec leaves open, documented here:
  * convergence (§3.2 step 7): «no coefficient moves more than 0.5 %» is read in log units, |Δ| ≤ 0.005;
  * a year keeps its A once it had min_year_n listings before the price trim, as the annex's SQL does;
  * the cross-validated sample (§3.5) is up to cohort_sample listings evenly spread by id; a listing enters
    both errors only when both references exist for it (its fold's curve values it inside that curve's
    price band, and today's model-level rules give it min_n comparables after floor_of_p75);
  * a model without a measurable cohort_err is not enabled (nothing to compare against);
  * guard_flips (§5) are counted on that same sample, with the full curve.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping

from intelligence import f3
from intelligence.comparables import PriceRef
from intelligence.f3 import warn_limited
from intelligence.matching import MatchResult, filter_currency, price_in
from intelligence.scoring import Score, score as compute_score

log = logging.getLogger(__name__)

FV_VERSION = "fv1"
FOLDS = 5
CONVERGED = 0.005            # |Δ| of a log coefficient: 0.5 %
CURVE, CURVE_NOVERSION = "curve", "curve_noversion"
DEFAULT_FLOOR_OF_P75 = 0.35  # comparables()'s default


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------

def _num(x: Any) -> float | None:
    """A finite number as float (numeric columns come as Decimal), else None."""
    if isinstance(x, bool) or not isinstance(x, (int, float, Decimal)):
        return None
    try:
        value = float(x)
    except (ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _int(x: Any) -> int | None:
    value = _num(x)
    return int(value) if value is not None and value == int(value) else None


def _key(x: Any) -> str | None:
    """lower(x) as the twins key it; None for a missing or blank value."""
    return x.lower() if isinstance(x, str) and x.strip() else None


def percentile(values: Iterable[float], q: float) -> float | None:
    """percentile_cont(q): linear between the closest ranks."""
    xs = sorted(values)
    if not xs:
        return None
    pos = q * (len(xs) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def median(values: Iterable[float]) -> float | None:
    return percentile(values, 0.5)


def slope(xs: list[float], ys: list[float]) -> float:
    """regr_slope(y, x); 0 without two distinct x."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = sum(xs) / n, sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    if var <= 1e-12:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var


def _r(x: float | None, digits: int = 4) -> float | None:
    if x is None:
        return None
    x = float(x)
    return round(x, digits) if math.isfinite(x) else None


# ---------------------------------------------------------------------------
# Observations and the curve
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Obs:
    id: int
    repost_of: int | None
    year: int
    trim: str | None
    transmission: str | None
    km: float | None
    price: float
    lp: float


def observations(rows: Iterable[Mapping[str, Any]]) -> list[Obs]:
    """price_pool rows with a year and a positive price, as the fit reads them."""
    out = []
    for r in rows:
        year, price, lid = _int(r.get("year")), _num(r.get("price_usd")), _int(r.get("id"))
        if year is None or price is None or price <= 0 or lid is None:
            continue
        km = _num(r.get("mileage_km"))
        out.append(Obs(lid, _int(r.get("probable_repost_of")), year, _key(r.get("trim")),
                       _key(r.get("transmission")), km, price, math.log(price)))
    return out


@dataclass(frozen=True)
class Curve:
    make: str
    model: str
    years: dict[int, dict[str, Any]]             # {year: {"a", "n", "km"}}; km = exp(KM[year]) or None
    trims: dict[str, dict[str, Any]]             # {lower(trim): {"g", "n"}}
    transmissions: dict[str, dict[str, Any]]     # {lower(transmission): {"h", "n"}}
    km_slope: float
    resid: dict[str, float]                      # {"q25", "q75"} of the final residual
    n: int                                       # listings in the fit (after the price trim)
    km_range: tuple[float, float] = (5000.0, 400000.0)
    params: str = ""
    fitted_at: datetime | None = None
    enabled: bool = False
    cv_err: float | None = None
    cohort_err: float | None = None
    # A0[year] (§3.2 step 1): the price band of the trim; kept to value a fold's sample, never stored.
    a0: dict[int, float] = field(default_factory=dict, repr=False, compare=False)
    band: tuple[float, float] = (0.45, 2.2)

    def curve_json(self) -> dict[str, Any]:
        """model_price_curves.curve."""
        return {"years": {str(y): {"a": _r(v["a"], 6), "n": int(v["n"]),
                                   "km": _r(v["km"], 1) if v.get("km") is not None else None}
                          for y, v in sorted(self.years.items())},
                "trims": {k: {"g": _r(v["g"], 6), "n": int(v["n"])} for k, v in sorted(self.trims.items())},
                "transmissions": {k: {"h": _r(v["h"], 6), "n": int(v["n"])}
                                  for k, v in sorted(self.transmissions.items())},
                "km_slope": _r(self.km_slope, 6), "km_range": [self.km_range[0], self.km_range[1]],
                "resid": {"q25": _r(self.resid.get("q25"), 6), "q75": _r(self.resid.get("q75"), 6)}}

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "Curve | None":
        """A model_price_curves row back; None when malformed."""
        try:
            c = row["curve"]
            years = {int(y): {"a": float(v["a"]), "n": int(v["n"]),
                              "km": float(v["km"]) if v.get("km") is not None else None}
                     for y, v in (c.get("years") or {}).items()}
            trims = {str(k): {"g": float(v["g"]), "n": int(v["n"])} for k, v in (c.get("trims") or {}).items()}
            trs = {str(k): {"h": float(v["h"]), "n": int(v["n"])} for k, v in (c.get("transmissions") or {}).items()}
            kr = c.get("km_range") or (5000, 400000)
            resid = c.get("resid") or {}
            return cls(make=str(row["make"]), model=str(row["model"]), years=years, trims=trims, transmissions=trs,
                       km_slope=float(c.get("km_slope") or 0.0), km_range=(float(kr[0]), float(kr[1])),
                       resid={"q25": float(resid.get("q25") or 0.0), "q75": float(resid.get("q75") or 0.0)},
                       n=int(row.get("n") or 0), params=str(row.get("params_hash") or ""),
                       fitted_at=row.get("fitted_at"), enabled=bool(row.get("enabled")),
                       cv_err=_num(row.get("cv_err")), cohort_err=_num(row.get("cohort_err")))
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            return None


def _as_obs(rows: Iterable[Any]) -> list[Obs]:
    rows = list(rows)
    return rows if rows and all(isinstance(r, Obs) for r in rows) else observations(rows)


def _km_x(km: float | None, year: int, kmc: Mapping[int, float], km_range: tuple[float, float]) -> float | None:
    """ln(km) − KM[year], or None (no km, outside km_range, or a year without a typical km)."""
    if km is None or km <= 0 or not km_range[0] <= km <= km_range[1] or year not in kmc:
        return None
    return math.log(km) - kmc[year]


def _medians(groups: Mapping[Any, list[float]], min_n: int) -> dict[Any, float]:
    return {k: median(v) for k, v in groups.items() if k is not None and len(v) >= min_n}


def fit(rows: Iterable[Mapping[str, Any]] | list[Obs], params: Mapping[str, Any], *,
        make: str = "", model: str = "") -> Curve | None:
    """§3.2 over a model's pool. None without a single year of min_year_n listings."""
    obs = _as_obs(rows)
    min_year_n, min_trim_n = int(params["min_year_n"]), int(params["min_trim_n"])
    low, high = float(params["price_trim"]["low"]), float(params["price_trim"]["high"])
    km_range = (float(params["km_range"]["min"]), float(params["km_range"]["max"]))
    b_min = float(params["km_slope_min"])

    # 1. A0[year]
    by_year: dict[int, list[float]] = {}
    for o in obs:
        by_year.setdefault(o.year, []).append(o.lp)
    a0 = _medians(by_year, min_year_n)
    if not a0:
        return None
    # 2. the price trim
    lo, hi = math.log(low), math.log(high)
    kept = [o for o in obs if o.year in a0 and a0[o.year] + lo <= o.lp <= a0[o.year] + hi]
    if not kept:
        return None
    kms: dict[int, list[float]] = {}
    for o in kept:
        if o.km is not None and o.km > 0 and km_range[0] <= o.km <= km_range[1]:
            kms.setdefault(o.year, []).append(math.log(o.km))
    kmc = {y: sum(v) / len(v) for y, v in kms.items()}
    xs = [_km_x(o.km, o.year, kmc, km_range) for o in kept]

    a: dict[int, float] = dict(a0)
    g: dict[str, float] = {}
    h: dict[str, float] = {}
    b = 0.0
    for step in range(max(1, int(params["max_passes"]))):
        def bx(i: int) -> float:
            return b * xs[i] if xs[i] is not None else 0.0
        # 3. G against the year level (A0 on the first pass), H and B
        groups: dict[Any, list[float]] = {}
        for i, o in enumerate(kept):
            groups.setdefault(o.trim, []).append(o.lp - a[o.year] - h.get(o.transmission, 0.0) - bx(i))
        g_new = _medians(groups, min_trim_n)
        # 4. A without the trims' effect
        groups = {}
        for i, o in enumerate(kept):
            groups.setdefault(o.year, []).append(o.lp - g_new.get(o.trim, 0.0) - h.get(o.transmission, 0.0) - bx(i))
        a_new = {y: median(v) for y, v in groups.items()}
        # 5. H
        groups = {}
        for i, o in enumerate(kept):
            groups.setdefault(o.transmission, []).append(o.lp - a_new[o.year] - g_new.get(o.trim, 0.0) - bx(i))
        h_new = _medians(groups, min_trim_n)
        # 6. B on the residual, inside km_range
        px, py = [], []
        for i, o in enumerate(kept):
            if xs[i] is not None:
                px.append(xs[i])
                py.append(o.lp - a_new[o.year] - g_new.get(o.trim, 0.0) - h_new.get(o.transmission, 0.0))
        b_new = max(b_min, min(0.0, slope(px, py)))
        moved = max([abs(b_new - b)]
                    + [abs(v - a.get(k, 0.0)) for k, v in a_new.items()]
                    + [abs(v - g.get(k, 0.0)) for k, v in g_new.items()]
                    + [abs(v - h.get(k, 0.0)) for k, v in h_new.items()])
        a, g, h, b = a_new, g_new, h_new, b_new
        # 7. until nothing moves more than 0.5 % (the first pass always runs the second)
        if step > 0 and moved <= CONVERGED:
            break

    counts_y: dict[int, int] = {}
    counts_t: dict[str, int] = {}
    counts_h: dict[str, int] = {}
    resid = []
    for i, o in enumerate(kept):
        counts_y[o.year] = counts_y.get(o.year, 0) + 1
        if o.trim is not None:
            counts_t[o.trim] = counts_t.get(o.trim, 0) + 1
        if o.transmission is not None:
            counts_h[o.transmission] = counts_h.get(o.transmission, 0) + 1
        resid.append(o.lp - a[o.year] - g.get(o.trim, 0.0) - h.get(o.transmission, 0.0)
                     - (b * xs[i] if xs[i] is not None else 0.0))
    # 8. the residual's quartiles: the «barato / caro» range
    return Curve(make=make.lower(), model=model.lower(),
                 years={y: {"a": v, "n": counts_y.get(y, 0),
                            "km": math.exp(kmc[y]) if y in kmc else None} for y, v in a.items()},
                 trims={k: {"g": v, "n": counts_t.get(k, 0)} for k, v in g.items()},
                 transmissions={k: {"h": v, "n": counts_h.get(k, 0)} for k, v in h.items()},
                 km_slope=b, resid={"q25": percentile(resid, 0.25) or 0.0, "q75": percentile(resid, 0.75) or 0.0},
                 n=len(kept), km_range=km_range, params=str(params.get("params", "")), a0=a0, band=(low, high))


# ---------------------------------------------------------------------------
# The value of a listing (§3.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FairValue:
    value: float          # USD
    p25: float
    p75: float
    n: int                # listings of that year in the fit
    level: str            # curve | curve_noversion
    known: dict[str, bool]
    d: float | None       # % below the value (positive = cheaper)
    log_value: float


def _log_value(curve: Curve, year: int | None, trim: Any, transmission: Any,
               km: Any) -> tuple[float, dict[str, bool]] | None:
    if year is None or year not in curve.years:
        return None
    t, tr = _key(trim), _key(transmission)
    kmv = _num(km)
    typical = curve.years[year].get("km")
    lv = float(curve.years[year]["a"])
    known = {"trim": t in curve.trims, "transmission": tr in curve.transmissions, "km": False}
    if known["trim"]:
        lv += float(curve.trims[t]["g"])
    if known["transmission"]:
        lv += float(curve.transmissions[tr]["h"])
    if (kmv is not None and kmv > 0 and typical and typical > 0
            and curve.km_range[0] <= kmv <= curve.km_range[1]):
        lv += curve.km_slope * (math.log(kmv) - math.log(typical))
        known["km"] = True
    return lv, known


def fair_value(listing: Mapping[str, Any], curve: Curve | None) -> FairValue | None:
    """What the listing is worth by its model's curve, or None (no curve, no year, a year without A)."""
    if curve is None:
        return None
    got = _log_value(curve, _int(listing.get("year")), listing.get("trim"), listing.get("transmission"),
                     listing.get("mileage_km"))
    if got is None:
        return None
    lv, known = got
    try:
        value = math.exp(lv)
        p25, p75 = value * math.exp(curve.resid["q25"]), value * math.exp(curve.resid["q75"])
    except (OverflowError, KeyError, TypeError):
        return None
    if not all(math.isfinite(x) and x > 0 for x in (value, p25, p75)):
        return None
    price = _num(listing.get("price_usd"))
    d = (1 - price / value) * 100 if price is not None and price > 0 else None
    year = _int(listing.get("year"))
    return FairValue(value=value, p25=p25, p75=p75, n=int(curve.years[year]["n"]),
                     level=CURVE if known["trim"] else CURVE_NOVERSION, known=known, d=d, log_value=lv)


def rule_h(ref: PriceRef | None, fetched: bool, value: FairValue | None, *, min_n: int,
           enabled: bool = True) -> bool:
    """§3.4: whether the hybrid rule would use the fair value. Twins (trim_transmission with min_n) keep
    today's reference; otherwise an enabled curve's value, when there is one."""
    if value is None or not enabled:
        return False
    if fetched and ref is not None and ref.level_used == "trim_transmission" and ref.enough(min_n):
        return False
    return True


# ---------------------------------------------------------------------------
# The per-model gate (§3.5)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Gate:
    n: int                      # pool rows with a year and a price
    sample: int                 # listings both errors were measured on
    cv_err: float | None        # median |ln(price / fair value)|, 5 folds
    cohort_err: float | None    # median |ln(price / model-level median)|, today's rules
    enabled: bool
    guard_flips: int


def sample_of(obs: list[Obs], size: int) -> list[Obs]:
    """Up to `size` listings evenly spread by id (deterministic)."""
    ordered = sorted(obs, key=lambda o: o.id)
    if len(ordered) <= size:
        return ordered
    step = len(ordered) / size
    return [ordered[int(i * step)] for i in range(size)]


def _cohort_median(t: Obs, by_year: Mapping[int, list[Obs]], comparables: Mapping[str, Any],
                   floor_of_p75: float) -> float | None:
    """Today's model-level reference for t: the pool with year ±year_tol, km ±km_tol_pct (a comparable without
    km passes), without t or its reposts, then the floor_of_p75 floor; None under min_n."""
    tol = int(comparables.get("year_tol", 1))
    pct = float(comparables.get("km_tol_pct", 25)) / 100
    min_n = int(comparables.get("min_n", 5))
    prices = []
    for y in range(t.year - tol, t.year + tol + 1):
        for o in by_year.get(y, ()):
            if o.id == t.id or o.repost_of == t.id:
                continue
            if t.km is not None and o.km is not None and not t.km * (1 - pct) <= o.km <= t.km * (1 + pct):
                continue
            prices.append(o.price)
    if floor_of_p75 > 0 and prices:
        floor = floor_of_p75 * (percentile(prices, 0.75) or 0.0)
        prices = [p for p in prices if p >= floor]
    if len(prices) < min_n:
        return None
    m = median(prices)
    return m if m and m > 0 else None


def _floor(comparables: Mapping[str, Any]) -> float:
    v = _num(comparables.get("floor_of_p75"))
    return v if v is not None and 0 <= v <= 1 else DEFAULT_FLOOR_OF_P75


def enabled_by(n: int, cv_err: float | None, cohort_err: float | None, params: Mapping[str, Any], *,
               was_enabled: bool) -> bool:
    """§3.5: min_listings and cv_err ≤ cohort_err; an enabled curve stays until cv_err > disable_margin ·
    cohort_err, so a model where both are even does not switch references from one day to the next."""
    if n < int(params["min_listings"]) or cv_err is None or cohort_err is None:
        return False
    return cv_err <= cohort_err * (float(params["disable_margin"]) if was_enabled else 1.0)


def evaluate(curve: Curve | None, rows: Iterable[Mapping[str, Any]] | list[Obs], params: Mapping[str, Any], *,
             comparables: Mapping[str, Any], partial_pct: float, was_enabled: bool = False) -> Gate:
    """cv_err against cohort_err on the same sample; enabled with min_listings and cv_err ≤ cohort_err, or
    (already enabled) until cv_err > disable_margin · cohort_err. guard_flips: sample listings that cross
    partial_pct below one reference and not below the other (fair value of the full curve, cohort median)."""
    obs = _as_obs(rows)
    sample = sample_of(obs, int(params["cohort_sample"]))
    by_year: dict[int, list[Obs]] = {}
    for o in obs:
        by_year.setdefault(o.year, []).append(o)
    floor = _floor(comparables)

    cv: dict[int, float] = {}
    for k in range(FOLDS):
        test = [s for s in sample if s.id % FOLDS == k]
        if not test:
            continue
        fc = fit([o for o in obs if o.id % FOLDS != k], params)
        if fc is None:
            continue
        lo, hi = math.log(fc.band[0]), math.log(fc.band[1])
        for s in test:
            if s.year not in fc.a0 or not fc.a0[s.year] + lo <= s.lp <= fc.a0[s.year] + hi:
                continue
            got = _log_value(fc, s.year, s.trim, s.transmission, s.km)
            if got is not None:
                cv[s.id] = abs(s.lp - got[0])
    cohort: dict[int, float] = {}
    medians: dict[int, float] = {}
    for s in sample:
        if s.id in cv:
            m = _cohort_median(s, by_year, comparables, floor)
            if m is not None:
                medians[s.id] = m
                cohort[s.id] = abs(s.lp - math.log(m))
    both = [s for s in sample if s.id in cv and s.id in cohort]
    cv_err = median(cv[s.id] for s in both)
    cohort_err = median(cohort[s.id] for s in both)

    flips = 0
    if curve is not None:
        for s in both:
            got = _log_value(curve, s.year, s.trim, s.transmission, s.km)
            if got is None:
                continue
            d_fv = (1 - s.price / math.exp(got[0])) * 100
            d_c = (1 - s.price / medians[s.id]) * 100
            flips += (d_fv >= partial_pct) != (d_c >= partial_pct)

    enabled = curve is not None and enabled_by(len(obs), cv_err, cohort_err, params, was_enabled=was_enabled)
    return Gate(n=len(obs), sample=len(both), cv_err=cv_err, cohort_err=cohort_err, enabled=enabled,
                guard_flips=flips)


# ---------------------------------------------------------------------------
# The shadow block (§5)
# ---------------------------------------------------------------------------

def _json_safe(x: Any) -> Any:
    """Only what the match row's JSON can carry; raises on anything else (shadow() then stores nothing)."""
    if x is None or isinstance(x, (bool, str)):
        return x
    if isinstance(x, int):
        return x
    if isinstance(x, (float, Decimal)):
        v = float(x)
        return v if math.isfinite(v) else None
    if isinstance(x, Mapping):
        return {str(k): _json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_json_safe(v) for v in x]
    raise TypeError(f"not JSON-safe: {type(x).__name__}")


def _iso(ts: Any) -> str | None:
    if isinstance(ts, datetime):
        ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(ts, date):
        return ts.isoformat()
    return ts if isinstance(ts, str) else None


def budget(profile: Mapping[str, Any], listing: Mapping[str, Any], fv: FairValue,
           fx_rate: float | None) -> dict[str, Any] | None:
    """{usd, value_ratio, price_ratio} against the search's price_max, in the filter's currency
    (matching.filter_currency / price_in, as the price filter); None without price_max or a quote."""
    f = profile.get("filters") if isinstance(profile.get("filters"), Mapping) else {}
    pmax = _num(f.get("price_max"))
    rate = _num(fx_rate)
    if pmax is None or pmax <= 0 or not rate or rate <= 0:
        return None
    currency = filter_currency(pmax, f.get("currency"))
    usd = pmax if currency == "USD" else pmax / rate
    value = fv.value if currency == "USD" else fv.value * rate
    price = price_in(listing, currency, rate)
    return {"usd": _r(usd, 2), "value_ratio": _r(value / pmax),
            "price_ratio": _r(price / pmax) if price is not None else None}


def shadow(listing: Mapping[str, Any], profile: Mapping[str, Any], result: MatchResult, ref: PriceRef | None,
           score: Score, cfg: Any, *, curve: Curve | None, fetched: bool, now: datetime,
           fx_rate: float | None = None) -> dict[str, Any] | None:
    """matches.score_breakdown.shadow_fair_value for an f2 match, or None: mode 'off', no curve or no value
    for this listing, or a failure (logged at most every 10 min). Never raises."""
    try:
        p = getattr(cfg, "fair_value", None)
        if not isinstance(p, Mapping) or p.get("mode") not in ("shadow", "live") or curve is None:
            return None
        fv = fair_value(listing, curve)
        if fv is None:
            return None
        use = rule_h(ref, fetched, fv, min_n=int(cfg.min_n), enabled=curve.enabled)
        block: dict[str, Any] = {
            "v": FV_VERSION, "params": str(p.get("params", "")), "fitted_at": _iso(curve.fitted_at),
            "value": _r(fv.value, 2), "p25": _r(fv.p25, 2), "p75": _r(fv.p75, 2), "n": fv.n, "level": fv.level,
            "known": dict(fv.known), "d": _r(fv.d, 2),
            "ref": {"fetched": bool(fetched), "d": _r(ref.diff_pct, 2) if ref is not None else None,
                    "level_used": ref.level_used if ref is not None else None,
                    "n": int(ref.n) if ref is not None else None},
            "rule_h": use,
        }
        if use:
            # A new PriceRef, never a replace() of today's: its diff_pct would win over the median.
            # median_km empty: the value already adjusts for km, so f2's km component stays neutral.
            alt = PriceRef(n=fv.n, level_used=fv.level, median=fv.value, p25=fv.p25, p75=fv.p75,
                           median_km=None, diff_pct=fv.d)
            s2 = compute_score(listing, profile, result, alt, cfg, now=now)
            block["f2"] = {"score": int(s2.score), "level": s2.level, "guard": s2.guard,
                           "excluded": bool(s2.excluded)}
            f3p = getattr(cfg, "f3", None)
            if isinstance(f3p, Mapping) and f3p.get("mode") in ("shadow", "live"):
                try:
                    # f3 knows «model» as the less reliable pool: curve_noversion takes its discount.
                    ref3 = replace(alt, level_used="model" if fv.level == CURVE_NOVERSION else CURVE)
                    a = f3.assess_f3(listing, profile, result, ref3, s2.extra.get("diff_pct"), cfg,
                                     fx_rate=fx_rate, f3cfg=f3p)
                    block["f3"] = {"score": int(a.score), "level": a.level}
                except Exception:
                    warn_limited(log, "fair_value.f3", "fair value's f3 alternative failed (listing %s)",
                                 listing.get("id"), exc_info=True)
                    block["f3"] = None
        b = budget(profile, listing, fv, fx_rate)
        if b is not None:
            block["budget"] = b
        out = _json_safe(block)
        json.dumps(out, allow_nan=False)
        return out
    except Exception:
        warn_limited(log, "fair_value.shadow", "fair value shadow failed (listing %s); f2 is unaffected",
                     listing.get("id") if isinstance(listing, Mapping) else None, exc_info=True)
        return None


__all__ = ["CURVE", "CURVE_NOVERSION", "Curve", "FV_VERSION", "FairValue", "Gate", "Obs", "budget", "enabled_by", "evaluate",
           "fair_value", "fit", "median", "observations", "percentile", "rule_h", "sample_of", "shadow", "slope"]
