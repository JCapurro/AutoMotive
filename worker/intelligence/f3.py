"""f3 «precio × encaje» (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §3), in SHADOW MODE. Pure.

    assess_f3(listing, profile, result, ref, diff_pct, cfg, fx_rate=…) → F3
    shadow(listing, profile, result, ref, score, cfg, fx_rate=…)       → the JSON of matches.score_breakdown.shadow_f3

Two axes instead of six components: **deal** (how cheap and how credible the price is, 0–1) and **fit**
(how much of what the search prefers the car meets, 0–1). The level reads them (§3.3), and the score is
the level's band ordered by 0.6·deal + 0.4·fit (§3.4).

f2 (intelligence/scoring.py, SCORING_VERSION) keeps deciding everything: scores, levels, alerts, digest,
mails, web. f3 is computed next to it on every evaluation of a match while app_config.score_model_f3.mode
is 'shadow' (or 'live', which behaves as 'shadow' until the live PR), and nothing of f2 reads it. `shadow()`
never raises: an f3 failure is logged (rate-limited) and the evaluation goes on without it.

f3 reads the same inputs as f2 at the same moment: f2's d (`Score.extra["diff_pct"]`, None with fewer than
comparables.min_n comparables), the price reference, the MatchResult (hard unknowns, soft results) and
the listing. Its own parameters come from IntelligenceConfig.f3 (config.score_model_f3); the
suspicious/exclusion percentages are f2's score_curves.guards, so the two can never drift apart.

Deliberate differences from the SQL the design was measured with (recalibracion-score-f2.sql), all
documented in the spec's header or required by its final text:
  * placeholder price: one digit 1–8 repeated 4+ times (no 9; no «same price on 3 cars» rule), computed
    live from listings.price; it counts as «sin precio» for the deal and for price_target;
  * agency voice: the narrowed regex of intelligence/seller.agency_voice, live from listings.description;
  * «Sold ·» is not a score rule (it goes to the Facebook collector);
  * at d ≥ suspicious_pct the deal is 0.6 by d (spec text), the SQL read d_eff (only Kavak 50–59 % differs,
    whose level the `suspicious` flag caps either way);
  * would_defer: an FB or ML card without a seller, as the spec (§4.1) and the SQL's `defer_here`; the
    same test on any source is logged next to it (would_defer_any_source);
  * excluded = f2's exclusion (price_partial or the published d ≥ partial_pct), a placeholder included:
    decision 3(a) applies only to listings that already match with their published price.
"""
from __future__ import annotations

import logging
import math
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

from intelligence.comparables import PriceRef
from intelligence.matching import FAIL, OK, UNKNOWN, MatchResult, filter_currency, price_in, seller_types
from intelligence.scoring import Score, clamp, round_half_up
from intelligence.seller import agency_voice, effective_seller, seller_for_preference

log = logging.getLogger(__name__)

# The SCORING_VERSION f3 will write once it is live (spec §8). Shadow rows carry it as shadow_f3.v.
F3_VERSION = "f3-precio-encaje"

EXCLUDED, LOW, MATCH, GOOD, HIGH = "excluded", "low", "match", "good", "high"
LEVELS = (EXCLUDED, LOW, MATCH, GOOD, HIGH)

# Flags: any of them keeps a listing out of 🔥 (spec §3.3).
NO_PRICE = "no_price"
PLACEHOLDER_PRICE = "placeholder_price"
NO_YEAR = "no_year"
NO_COMPARABLES = "no_comparables"
FEW_COMPARABLES = "few_comparables"
FAR_BELOW = "far_below"
SUSPICIOUS = "suspicious"
SELLER_UNKNOWN = "seller_unknown"
SELLER_MISMATCH = "seller_mismatch"

# deal_tier (spec §6: «oferta creíble» = strong or good).
TIERS = ("unknown", "strong", "verify", "good", "fair", "pricey", "expensive")

# Literals of the spec (§3.1, §3.2, §3.4), not tunable.
D_FULL_WITHOUT_P25 = 16.0      # d_full when the reference has no p25
N_RELIABLE_FROM = 5            # r = 0.5 + 0.5·clamp((n − 5)/15)
N_RELIABLE_SPAN = 15
DEAL_AT_MEDIAN = 0.4           # the deal of a price at the median
DEAL_FLOOR_D = -20.0           # 20 % above the median or more: deal 0
DEAL_SUSPICIOUS = 0.6          # d ≥ suspicious_pct
DEAL_DROP = 0.3                # cred_max → suspicious_pct falls from 1 to 0.7
W_DEAL = 0.6                   # score: 0.6·deal + 0.4·fit
NO_DEAL_WITH_PRICE = 0.4       # deal' without comparables
NO_DEAL_WITHOUT_PRICE = 0.2    # deal' without a price
PRICE_TARGET_SPAN = 0.15       # without price_max: down to fit.fail at +15 % of the target
KM_TARGET_SPAN = 0.30          # down to fit.fail at +30 % of the target

# A decision waits for the detail only on these sources' cards (spec §4.1; the SQL's `defer_here` = a
# card of the FB/ML card model): elsewhere the card is what the search gets.
DEFER_SOURCES = frozenset({"facebook", "mercadolibre"})

# The order the SQL measured the fit mean in (sum order, so ties land the same).
PREF_KEYS = ("price_target", "km_target", "seller_type", "colors", "max_distance_km", "trim")


# ---------------------------------------------------------------------------
# Rate-limited warnings (the decision log of notifications/decision_log.py uses it too)
# ---------------------------------------------------------------------------

_WARNED: dict[str, list[float]] = {}     # key → [monotonic time of the last warning, suppressed since]


def warn_limited(logger: logging.Logger, key: str, msg: str, *args: Any, every: float = 600.0,
                 **kwargs: Any) -> bool:
    """logger.warning at most once per `every` seconds per key; the next one says how many were
    suppressed in between. Returns whether it logged. Never raises."""
    try:
        now = time.monotonic()
        last = _WARNED.get(key)
        if last is not None and now - last[0] < every:
            last[1] += 1
            return False
        suppressed = last[1] if last is not None else 0
        _WARNED[key] = [now, 0]
        if suppressed:
            msg = f"{msg} (%d similar suppressed)"
            args = (*args, suppressed)
        logger.warning(msg, *args, **kwargs)
        return True
    except Exception:          # logging must never break the caller
        return False


# ---------------------------------------------------------------------------
# Placeholder price (spec §3.5)
# ---------------------------------------------------------------------------

# One digit 1–8 repeated 4 or more times: USD 1.111 / 11.111, ARS 1.111.111. Not the 9: 9.999 is a
# shop-window price (on ML at −9 %, +3 % and −1 % of the median).
_PLACEHOLDER = re.compile(r"^([1-8])\1{3,}$")


def placeholder_price(price: Any) -> bool:
    """Whether the published amount (listings.price, any currency) looks like a filler number."""
    value = _num(price)
    if value is None or value <= 0:
        return False
    return bool(_PLACEHOLDER.match(str(round_half_up(value))))


# ---------------------------------------------------------------------------
# Pieces
# ---------------------------------------------------------------------------

def d_full_of(ref: PriceRef | None, deal: Mapping[str, Any]) -> tuple[float | None, float]:
    """(s_lo, d_full): the cheap quartile's distance to the median in %, and where the curve reaches
    full credit, clamp_[d_floor, d_ceil](d_mult · s_lo) (16 without p25)."""
    s_lo = None
    if ref is not None and ref.p25 and ref.median and ref.p25 > 0 and ref.median > 0:
        s_lo = 100 * (1 - ref.p25 / ref.median)
    base = deal["d_mult"] * s_lo if s_lo is not None else D_FULL_WITHOUT_P25
    return s_lo, max(float(deal["d_floor"]), min(float(deal["d_ceil"]), base))


def deal_curve(d: float | None, d_eff: float | None, *, d_full: float, cred_max: float,
               susp: float) -> float | None:
    """The raw deal 0–1 of §3.1: 0 at 20 % above the median, 0.4 at the median, 1 from d_full to
    cred_max, down to 0.7 at suspicious_pct, 0.6 from there (by the published d)."""
    if d_eff is None:
        return None
    if d is not None and d >= susp:
        return DEAL_SUSPICIOUS
    if d_eff <= DEAL_FLOOR_D:
        return 0.0
    if d_eff <= 0:
        return DEAL_AT_MEDIAN * (d_eff - DEAL_FLOOR_D) / -DEAL_FLOOR_D
    if d_eff <= d_full:
        return DEAL_AT_MEDIAN + (1 - DEAL_AT_MEDIAN) * d_eff / d_full
    if d_eff <= cred_max:
        return 1.0
    # cred_max < d_eff ≤ d < susp here (kavak_offset ≥ 0), so susp − cred_max > 0.
    return 1 - DEAL_DROP * (d_eff - cred_max) / (susp - cred_max)


def reliability(n: int | None, level_used: str | None, year: Any, deal: Mapping[str, Any]) -> float:
    """How much the reference promises: 0.5–1 by n, ×r_model for a model-level pool, ×r_noyear without year."""
    r = 0.5 + 0.5 * clamp(((n or 0) - N_RELIABLE_FROM) / N_RELIABLE_SPAN)
    if level_used == "model":
        r *= deal["r_model"]
    if year is None:
        r *= deal["r_noyear"]
    return r


def shrink(raw: float | None, r: float) -> float | None:
    """deal = raw on the expensive side; a weaker reference brings the cheap side towards «en línea»."""
    if raw is None:
        return None
    return raw if raw <= DEAL_AT_MEDIAN else DEAL_AT_MEDIAN + r * (raw - DEAL_AT_MEDIAN)


def _graded(value: float, target: float, span: float, floor: float) -> float:
    """1 at the target, down to `floor` at target + span (and below that, floor)."""
    if span <= 0:
        return floor
    return 1 - (1 - floor) * clamp((value - target) / span)


def price_target_value(listing: Mapping[str, Any], profile: Mapping[str, Any], fx_rate: float | None,
                       fit: Mapping[str, Any], *, has_price: bool) -> float | None:
    """price_target graded inside the budget: 1 at the target, fit.price_target_at_max at price_max
    (without one: fit.fail at +15 %). None = sin dato (no price, partial, placeholder, no quote)."""
    p = profile.get("preferences") or {}
    f = profile.get("filters") or {}
    target = p.get("price_target")
    if not has_price or target is None:
        return None
    currency = filter_currency(target, p.get("price_target_currency") or f.get("currency"))
    value = price_in(listing, currency, fx_rate)
    if value is None:
        return None
    if value <= target:
        return 1.0
    pmax = _price_max_in(f, currency, fx_rate)
    if pmax is not None and pmax > target:
        return _graded(value, target, pmax - target, fit["price_target_at_max"])
    return _graded(value, target, PRICE_TARGET_SPAN * target, fit["fail"])


def _price_max_in(f: Mapping[str, Any], currency: str, fx_rate: float | None) -> float | None:
    hi = f.get("price_max")
    if hi is None or isinstance(hi, bool) or not isinstance(hi, (int, float)):
        return None
    own = filter_currency(hi, f.get("currency"))
    if own == currency:
        return float(hi)
    if not fx_rate:
        return None
    return float(hi) / fx_rate if currency == "USD" else float(hi) * fx_rate


def km_target_value(listing: Mapping[str, Any], target: Any, fit: Mapping[str, Any]) -> float | None:
    km = listing.get("mileage_km")
    if km is None or target is None:
        return None
    if km <= target:
        return 1.0
    return _graded(km, target, KM_TARGET_SPAN * max(target, 1), fit["fail"])


def wanted_seller(profile: Mapping[str, Any], result: MatchResult) -> tuple[tuple[str, ...] | None, bool]:
    """(the seller types the search asks for, strict): the strict filter's list (PRO-01) when it ran,
    else the soft preference (preferences.seller_type or filters.seller_types[0]); (None, False) without."""
    f = profile.get("filters") or {}
    if "seller" in result.hard:
        return tuple(seller_types(f)) or None, True
    if "seller_type" in result.soft:
        p = profile.get("preferences") or {}
        stored = seller_types(f)
        wanted = p.get("seller_type") or (stored[0] if stored else None)
        return ((wanted,) if wanted else None), False
    return None, False


def level_f3(deal: float | None, fit_level: float, lv: Mapping[str, Any], *, excluded: bool = False,
             flags: tuple[str, ...] | list[str] = (), has_price: bool = True, suspicious: bool = False,
             year_known: bool = True, credible: bool = False, d_eff: float | None = None) -> str:
    """The level table of §3.3, in order, before the seller cap. `d_eff` None = no comparables."""
    if excluded:
        return EXCLUDED
    if (not flags and deal is not None and deal >= lv["x_high"] and fit_level >= lv["y_high"]
            and W_DEAL * deal + (1 - W_DEAL) * fit_level >= lv["c_high"]):
        return HIGH
    good_price = ((deal is not None and deal >= lv["x_good"]) or credible) and fit_level >= lv["y_deal"]
    fits_fair = fit_level >= lv["y_good"] and (d_eff is None or d_eff >= lv["fair_min_d"])
    if has_price and not suspicious and year_known and (good_price or fits_fair):
        return GOOD
    if fit_level >= lv["y_min"] and (not has_price or d_eff is None or d_eff >= lv["low_d"] or suspicious):
        return MATCH
    return LOW


def band_score(level: str, raw: float, c_high: float) -> int:
    """The level's band (§3.4): 🔥 85–99 from 100·c_high, good 70–84, match 50–69, low 0–49."""
    if level == HIGH:
        start = 100 * c_high
        return 85 + round_half_up(14 * clamp((raw - start) / (100 - start)))
    if level == GOOD:
        return 70 + round_half_up(14 * clamp((raw - 45) / 50))
    if level == MATCH:
        return 50 + round_half_up(19 * clamp((raw - 25) / 60))
    return round_half_up(49 * clamp(raw / 70))


def deal_tier(deal: float | None, d: float | None, d_eff: float | None, *, credible: bool, year: Any,
              n: int | None, lv: Mapping[str, Any], cred_max: float, susp: float) -> str:
    """unknown · strong (credible 🔥-grade) · verify (cheap but something to check) · good · fair (en
    línea) · pricey (algo caro) · expensive. Stored for the mails' «por debajo» count of the live PR."""
    if deal is None or d_eff is None:
        return "unknown"
    if credible and deal >= lv["x_high"]:
        return "strong"
    if deal >= lv["x_good"] and (d_eff > cred_max or (d is not None and d >= susp) or year is None
                                 or (n or 0) < lv["n_min_high"]):
        return "verify"
    if credible or deal >= lv["x_good"]:
        return "good"
    if d_eff >= lv["fair_min_d"]:
        return "fair"
    if d_eff >= lv["low_d"]:
        return "pricey"
    return "expensive"


# ---------------------------------------------------------------------------
# The evaluation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class F3:
    """One f3 evaluation: the level and score, and every intermediate the decision log needs to
    recompute an alternative offline (spec §4.4)."""
    mode: str
    params: str
    level: str
    level_uncapped: str               # before the seller cap
    score: int
    raw: float                        # 100·(0.6·deal' + 0.4·fit_score), before the bands
    deal: float | None                # None = desconocido
    deal_raw: float | None
    r: float
    diff_pct: float | None            # f2's d: the published price against the median
    d: float | None                   # f3's d: None for a placeholder price
    d_eff: float | None               # d − kavak_offset for Kavak
    d_full: float
    s_lo: float | None
    n: int | None
    level_used: str | None
    kavak: bool
    placeholder: bool                 # the published amount looks like a filler (whatever rules.placeholder says)
    has_price: bool
    credible: bool
    tier: str
    fit_level: float                  # the levels read it
    fit_score: float                  # the score reads it: fit_level − unknown_hard·(hard unknowns)
    unknown_hard: tuple[str, ...]
    prefs: dict[str, float] = field(default_factory=dict)
    flags: tuple[str, ...] = ()
    a_verificar: tuple[str, ...] = ()
    seller_wanted: tuple[str, ...] | None = None
    seller_strict: bool = False
    seller_effective: str | None = None
    seller_for_preference: str | None = None
    agency_voice: str | None = None   # the phrase, when the listing says «particular» and its text an agency's
    seller_mismatch: bool = False
    seller_capped: bool = False
    would_defer: bool = False         # an FB/ML card of a search that asks for a seller, without one (§4.1)
    would_defer_any_source: bool = False   # the same on any source: logged to weigh the broader rule offline
    version: str = F3_VERSION

    def to_json(self, alternatives: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """The shadow_f3 JSON the decision log (match_decisions.f3) and explain_match read: floats rounded
        to 4 decimals, nothing time-dependent (a re-score with the same data stores the same value)."""
        return {
            "v": self.version, "mode": self.mode, "params": self.params,
            "level": self.level, "level_uncapped": self.level_uncapped, "score": self.score, "raw": _r(self.raw),
            "deal": {"value": _r(self.deal), "raw": _r(self.deal_raw), "r": _r(self.r),
                     "diff_pct": _r(self.diff_pct), "d": _r(self.d), "d_eff": _r(self.d_eff),
                     "d_full": _r(self.d_full), "s_lo": _r(self.s_lo), "n": self.n, "level_used": self.level_used,
                     "kavak": self.kavak, "placeholder": self.placeholder, "has_price": self.has_price,
                     "credible": self.credible, "tier": self.tier},
            "fit": {"level": _r(self.fit_level), "score": _r(self.fit_score), "unknown_hard": list(self.unknown_hard),
                    "prefs": {k: _r(v) for k, v in self.prefs.items()}},
            "flags": list(self.flags), "a_verificar": list(self.a_verificar),
            "seller": {"wanted": list(self.seller_wanted) if self.seller_wanted else None,
                       "strict": self.seller_strict, "effective": self.seller_effective,
                       "for_preference": self.seller_for_preference, "agency_voice": self.agency_voice,
                       "mismatch": self.seller_mismatch, "capped": self.seller_capped},
            "would_defer": self.would_defer, "would_defer_any_source": self.would_defer_any_source,
            "alternatives": dict(alternatives or {}),
        }


def _r(x: float | None) -> float | None:
    if x is None:
        return None
    x = float(x)
    return round(x, 4) if math.isfinite(x) else None


def _num(x: Any) -> float | None:
    """A finite number as float (numeric columns may come as Decimal), else None."""
    if isinstance(x, bool) or not isinstance(x, (int, float, Decimal)):
        return None
    try:
        value = float(x)
    except (ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def assess_f3(listing: Mapping[str, Any], profile: Mapping[str, Any], result: MatchResult,
              ref: PriceRef | None, diff_pct: float | None, cfg: Any, *, fx_rate: float | None = None,
              f3cfg: Mapping[str, Any] | None = None) -> F3:
    """f3 for one (listing, profile). `diff_pct` is f2's d (Score.extra["diff_pct"]); `cfg` the
    IntelligenceConfig (guards, min_n, and .f3 unless `f3cfg` is given). Raises on malformed input:
    shadow() is the guarded entry point."""
    p = f3cfg if f3cfg is not None else cfg.f3
    deal_p, fit_p, lv, rules = p["deal"], p["fit"], p["levels"], p["rules"]
    guards = cfg.curve("guards")
    susp, partial = float(guards["suspicious_pct"]), float(guards["partial_pct"])
    n_min_high = max(int(lv["n_min_high"]), int(cfg.min_n))

    year = listing.get("year")
    source = listing.get("source")
    price = _num(listing.get("price"))
    price_partial = bool(listing.get("price_partial"))
    diff_pct = _num(diff_pct)

    # Price and deal (§3.1, §3.5).
    is_placeholder = placeholder_price(price)
    treat_placeholder = bool(rules["placeholder"]) and is_placeholder
    has_price = price is not None and price > 0 and not price_partial and not treat_placeholder
    d = None if treat_placeholder else diff_pct
    kavak = source == "kavak"
    d_eff = (d - float(deal_p["kavak_offset"]) if kavak else d) if d is not None else None
    n = ref.n if ref is not None else None
    level_used = ref.level_used if ref is not None else None
    s_lo, d_full = d_full_of(ref, deal_p)
    raw = deal_curve(d, d_eff, d_full=d_full, cred_max=float(deal_p["cred_max"]), susp=susp)
    r = reliability(n, level_used, year, deal_p)
    deal = shrink(raw, r) if has_price and d_eff is not None else None
    suspicious = d is not None and d >= susp
    credible = (has_price and d_eff is not None and deal_p["cred_min"] <= d_eff <= deal_p["cred_max"]
                and (n or 0) >= n_min_high and year is not None and not suspicious)

    # Seller (§3.2, §3.3): the agency voice counts as an agency for the preference and the cap only.
    effective = effective_seller(listing)
    phrase = None
    if listing.get("seller_type") == "private" and effective != "dealer":
        phrase = agency_voice(listing.get("description"))
    seller2 = seller_for_preference(listing) if rules["agency_voice"] else effective
    wanted, strict = wanted_seller(profile, result)
    has_sel = "seller_type" in result.soft or "seller" in result.hard
    mismatch = bool(has_sel and seller2 is not None and wanted and seller2 not in wanted)

    # Fit (§3.2): the mean of the stated preferences; 0.75 sin dato.
    soft = result.soft
    values: dict[str, float] = {}
    unknown_prefs: list[str] = []

    def put(key: str, value: float | None) -> None:
        if value is None:
            unknown_prefs.append(key)
            value = fit_p["unknown"]
        values[key] = float(value)

    by_result = {OK: 1.0, FAIL: fit_p["fail"], UNKNOWN: None}
    for key in PREF_KEYS:
        if key not in soft:
            continue
        if key == "price_target":
            put(key, price_target_value(listing, profile, fx_rate, fit_p, has_price=has_price))
        elif key == "km_target":
            put(key, km_target_value(listing, (profile.get("preferences") or {}).get("km_target"), fit_p))
        elif key == "seller_type":
            put(key, None if seller2 is None else 1.0 if wanted and seller2 in wanted else fit_p["fail"])
        elif key == "trim":
            put(key, {OK: 1.0, FAIL: fit_p["trim_other"], UNKNOWN: None}[soft[key].result])
        else:                               # colors, max_distance_km
            put(key, by_result[soft[key].result])
    fit_level = sum(values.values()) / len(values) if values else 1.0
    unknown_hard = tuple(result.unknown)
    fit_score = max(0.0, fit_level - fit_p["unknown_hard"] * len(unknown_hard))

    # Flags and level (§3.3).
    flags: list[str] = []
    if not has_price:
        flags.append(PLACEHOLDER_PRICE if treat_placeholder else NO_PRICE)
    if year is None:
        flags.append(NO_YEAR)
    if has_price and d is None:
        flags.append(NO_COMPARABLES)
    if d is not None and (n or 0) < n_min_high:
        flags.append(FEW_COMPARABLES)
    if d_eff is not None and d_eff > deal_p["cred_max"] and not suspicious:
        flags.append(FAR_BELOW)
    if suspicious:
        flags.append(SUSPICIOUS)
    if has_sel and seller2 is None:
        flags.append(SELLER_UNKNOWN)
    if rules["seller_cap"] and mismatch:
        flags.append(SELLER_MISMATCH)

    excluded = price_partial or (diff_pct is not None and diff_pct >= partial)
    level0 = level_f3(deal, fit_level, lv, excluded=excluded, flags=flags, has_price=has_price,
                      suspicious=suspicious, year_known=year is not None, credible=credible, d_eff=d_eff)
    capped = bool(rules["seller_cap"] and mismatch and level0 in (HIGH, GOOD))
    level = MATCH if capped else level0

    # Score (§3.4).
    deal_prime = deal if deal is not None else NO_DEAL_WITH_PRICE if has_price else NO_DEAL_WITHOUT_PRICE
    raw_score = 100 * (W_DEAL * deal_prime + (1 - W_DEAL) * fit_score)
    score = band_score(level, raw_score, float(lv["c_high"]))

    tier = deal_tier(deal, d, d_eff, credible=credible, year=year, n=n, lv={**lv, "n_min_high": n_min_high},
                     cred_max=float(deal_p["cred_max"]), susp=susp)
    a_verificar = (*unknown_hard, *unknown_prefs)
    waits = bool(has_sel and seller2 is None and listing.get("enriched_at") is None)
    would_defer = waits and source in DEFER_SOURCES
    return F3(mode=str(p.get("mode", "off")), params=str(p.get("params", "")), level=level,
              level_uncapped=level0, score=score, raw=raw_score, deal=deal, deal_raw=raw, r=r,
              diff_pct=diff_pct, d=d, d_eff=d_eff, d_full=d_full, s_lo=s_lo, n=n, level_used=level_used,
              kavak=kavak, placeholder=is_placeholder, has_price=has_price, credible=bool(credible), tier=tier,
              fit_level=fit_level, fit_score=fit_score, unknown_hard=unknown_hard, prefs=values,
              flags=tuple(flags), a_verificar=a_verificar, seller_wanted=wanted, seller_strict=strict,
              seller_effective=effective, seller_for_preference=seller2, agency_voice=phrase,
              seller_mismatch=mismatch, seller_capped=capped, would_defer=would_defer,
              would_defer_any_source=waits)


def _with(p: Mapping[str, Any], group: str, **changes: Any) -> dict[str, Any]:
    return {**p, group: {**p[group], **changes}}


def alternatives(main: F3, listing: Mapping[str, Any], profile: Mapping[str, Any], result: MatchResult,
                 ref: PriceRef | None, diff_pct: float | None, cfg: Any, *, fx_rate: float | None,
                 f3cfg: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """{name: {level, score}} with one switch of §14 flipped, only where it can matter: the seller cap
    (a confirmed mismatch), the agency voice (it changed the seller of a search that asks for one), the
    placeholder price (one was detected) and Kavak's offset (a Kavak listing)."""
    rules = f3cfg["rules"]
    variants: list[tuple[str, dict[str, Any]]] = []
    if main.seller_wanted is not None:      # the search asks for a seller type (preference or strict filter)
        if main.seller_mismatch:
            on = bool(rules["seller_cap"])
            variants.append(("seller_cap_off" if on else "seller_cap_on", _with(f3cfg, "rules", seller_cap=not on)))
        if main.agency_voice and main.seller_effective != "dealer":
            on = bool(rules["agency_voice"])
            variants.append(("agency_voice_off" if on else "agency_voice_on",
                             _with(f3cfg, "rules", agency_voice=not on)))
    if main.placeholder:
        on = bool(rules["placeholder"])
        variants.append(("placeholder_off" if on else "placeholder_on", _with(f3cfg, "rules", placeholder=not on)))
    if main.kavak and f3cfg["deal"]["kavak_offset"]:
        variants.append(("kavak_offset_0", _with(f3cfg, "deal", kavak_offset=0)))
    out: dict[str, dict[str, Any]] = {}
    for name, alt in variants:
        a = assess_f3(listing, profile, result, ref, diff_pct, cfg, fx_rate=fx_rate, f3cfg=alt)
        out[name] = {"level": a.level, "score": a.score}
    return out


def shadow(listing: Mapping[str, Any], profile: Mapping[str, Any], result: MatchResult,
           ref: PriceRef | None, score: Score, cfg: Any, *, fx_rate: float | None = None) -> dict[str, Any] | None:
    """matches.score_breakdown.shadow_f3 for an f2 match, or None: mode 'off' (no work at all), or f3
    failed (logged at most every 10 min). Never raises."""
    try:
        p = getattr(cfg, "f3", None)
        if not isinstance(p, Mapping) or p.get("mode") not in ("shadow", "live"):
            return None
        d = score.extra.get("diff_pct")
        main = assess_f3(listing, profile, result, ref, d, cfg, fx_rate=fx_rate, f3cfg=p)
        alts = alternatives(main, listing, profile, result, ref, d, cfg, fx_rate=fx_rate, f3cfg=p)
        return main.to_json(alts)
    except Exception:
        warn_limited(log, "f3.shadow", "f3 shadow failed (listing %s); f2 is unaffected",
                     listing.get("id") if isinstance(listing, Mapping) else None, exc_info=True)
        return None


__all__ = ["DEFER_SOURCES", "F3", "F3_VERSION", "LEVELS", "TIERS", "alternatives", "assess_f3", "band_score",
           "deal_curve", "deal_tier", "level_f3", "placeholder_price", "reliability", "shadow", "shrink",
           "warn_limited"]
