"""Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice A).

Everything tunable lives in app_config so the pilot can adjust it without a
deploy. `IntelligenceConfig.from_app_config` is pure: it takes the raw values
(missing keys fall back to the defaults below, which mirror supabase/seed.sql);
`load()` reads them through the cached db.get_config.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, NamedTuple

from normalization.price_check import ALMOST_CERTAIN_BELOW_MEDIAN_PCT, SUSPICIOUS_BELOW_MEDIAN_PCT


# Bump when matching or scoring logic changes: every match is re-scored (sección 6.1).
# f2-v2: matches also store seller_questions (F4), so the old rows get them.
# f2-v5-seller-margin: F-02 paso 2 (a «posible agencia» counts as a dealer in the
# seller preference) and PRO-02 (margin) share this one bump and ship in the
# same deploy (Juan, 30/10/2026; one bump per deploy). PRO-02 reuses it: it
# must not bump again, and F-02 paso 2 is not deployed alone.
SCORING_VERSION = "f2-v5-seller-margin"

COMPONENTS = ("price", "match", "km", "trim", "recency", "completeness")

DEFAULT_WEIGHTS = {"price": 35, "match": 25, "km": 15, "trim": 10, "recency": 10, "completeness": 5}
DEFAULT_THRESHOLDS = {"high": 85, "good": 70, "match": 50}
DEFAULT_COMPARABLES = {"min_n": 5, "year_tol": 1, "km_tol_pct": 25, "max_age_days": 30}
DEFAULT_CURVES: dict[str, dict[str, float]] = {
    # c = base + d / pct_per_unit, d = % below the median (sección 6.3)
    "price": {"base": 0.5, "pct_per_unit": 20},
    # fraction of soft preferences met − penalty per hard filter "unknown"
    "match": {"unknown_penalty": 0.15},
    # c = base + slope · (1 − km / median_km)
    "km": {"base": 0.5, "slope": 1.25},
    "trim": {"preferred": 1.0, "unknown": 0.5, "other": 0.2, "no_preference": 1.0},
    # c = 0.5 ^ (hours / half_life_hours)
    "recency": {"half_life_hours": 24},
    "completeness": {"min_description_chars": 150, "min_images": 3},
    # price_check guards: from suspicious_pct the level is capped at `good`;
    # from partial_pct the price is taken for a down payment and the listing excluded.
    "guards": {"suspicious_pct": SUSPICIOUS_BELOW_MEDIAN_PCT,
               "partial_pct": ALMOST_CERTAIN_BELOW_MEDIAN_PCT},
}
# much_cheaper_verify_pct (PAR-02): from there the much_cheaper text asks to verify
# everything before a down payment; only used when much_cheaper_pct < it <= anticipo_pct.
# order (PAR-02 resto, decision 8): the priority the email cuts its two flags by
# (notifications/service.flag_texts) and the order matches.red_flags is stored in.
# The default reproduces the order before it existed and slots the new flags in.
DEFAULT_FLAG_ORDER = (
    "duplicate_photos", "much_cheaper", "partial_price_suspect", "private_many_listings",
    "cross_source_duplicate", "no_owners", "service_unavailable", "no_service", "timing_pending",
    "no_timing_belt", "short_description", "damage_mentioned", "commercial_use", "vtv_pending",
    "low_km_for_age", "repost", "price_mismatch", "year_mismatch", "km_mismatch")
DEFAULT_RED_FLAGS = {"much_cheaper_pct": 25, "much_cheaper_verify_pct": 35, "anticipo_pct": 50,
                     "min_km_per_year": 5000, "min_description_chars": 150,
                     "order": list(DEFAULT_FLAG_ORDER)}
DEFAULT_RESCORE = {"days": 14, "hour": "04:00", "every_hours": 24}


class Bound(NamedTuple):
    """A finite number in [lo, hi] (lo excluded when `above`), whole when `integer`."""
    lo: float
    hi: float
    integer: bool = False
    above: bool = False

    def accepts(self, value: Any) -> bool:
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            return False
        if self.integer and value != int(value):
            return False
        return (value > self.lo if self.above else value >= self.lo) and value <= self.hi


# Same bounds as the /admin/config validator (web/lib/admin-config.ts,
# scoringConfigProblem). Before them a threshold saved as "80" raised in
# level_for, a 0 divisor in the price or recency curve raised
# ZeroDivisionError, and a rescore.hour like "04:60" ended the nightly loop
# ("25:00" wrapped to 01:00 without a word).
# A bad value falls back to its default, key by key (_merge).
_SHARE = Bound(0, 1)                                    # a component value c
_WEIGHTS_BOUNDS = {k: Bound(0, 1000) for k in COMPONENTS}
_THRESHOLDS_BOUNDS = {k: Bound(0, 100) for k in DEFAULT_THRESHOLDS}
_CURVES_BOUNDS: dict[str, dict[str, Bound]] = {
    "price": {"base": _SHARE, "pct_per_unit": Bound(0, 100, above=True)},
    "match": {"unknown_penalty": _SHARE},
    "km": {"base": _SHARE, "slope": Bound(0, 10)},
    "trim": {k: _SHARE for k in DEFAULT_CURVES["trim"]},
    "recency": {"half_life_hours": Bound(0, 720, above=True)},
    "completeness": {"min_description_chars": Bound(0, 5000, integer=True),
                     "min_images": Bound(0, 50, integer=True)},
    # From 25% below the median a price is still a deal, not a down payment.
    "guards": {"suspicious_pct": Bound(25, 100), "partial_pct": Bound(25, 100)},
}
# public.comparables() casts year_tol, max_age_days and gone_max_age_days to
# integer. confirm_grace_hours and gone_max_age_days are read by SQL only.
_COMPARABLES_BOUNDS = {"min_n": Bound(1, 1000, integer=True), "year_tol": Bound(0, 10, integer=True),
                       "km_tol_pct": Bound(0, 100, integer=True), "max_age_days": Bound(1, 180, integer=True),
                       "confirm_grace_hours": Bound(0, 720, integer=True),
                       "gone_max_age_days": Bound(1, 180, integer=True)}
_CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
_RESCORE_BOUNDS: dict[str, Bound | re.Pattern[str]] = {
    "days": Bound(1, 180, integer=True), "hour": _CLOCK, "every_hours": Bound(1, 24, integer=True)}
# The plain-number keys: (default, bound). SQL casts alerts_max_per_user_day
# to integer (immediate_alert_cap), so a 7.5 would stop every batch.
_SCALARS: dict[str, tuple[int | float, Bound]] = {
    "digest_top_n": (10, Bound(1, 50, integer=True)),
    "price_drop_min_pct": (3, Bound(0, 100)),
    "alerts_max_per_user_day": (10, Bound(0, 2_147_483_647, integer=True)),
}


def _within(bound: Bound | re.Pattern[str], value: Any) -> bool:
    if isinstance(bound, re.Pattern):
        return isinstance(value, str) and bound.fullmatch(value) is not None
    return bound.accepts(value)


def _merge(defaults: Mapping[str, Any], value: Any,
           bounds: Mapping[str, Bound | re.Pattern[str]] | None = None) -> dict[str, Any]:
    """`defaults` overlaid with the keys of `value` (None skipped). A key in
    `bounds` takes the value only within them; otherwise it keeps its default,
    or stays out when it has none."""
    out = dict(defaults)
    if not isinstance(value, Mapping):
        return out
    for k, v in value.items():
        bound = bounds.get(k) if bounds else None
        if v is None or (bound is not None and not _within(bound, v)):
            continue
        out[k] = int(v) if isinstance(bound, Bound) and bound.integer else v
    return out


def _weights(raw: Any) -> dict[str, Any]:
    out = _merge(DEFAULT_WEIGHTS, raw, _WEIGHTS_BOUNDS)
    # Every weight at 0 scores every match 0 (level low): the defaults instead.
    return out if sum(out[k] for k in COMPONENTS) > 0 else dict(DEFAULT_WEIGHTS)


def _thresholds(raw: Any) -> dict[str, Any]:
    out = _merge(DEFAULT_THRESHOLDS, raw, _THRESHOLDS_BOUNDS)
    # Out of order (good above high...) the levels make no sense: all three defaults.
    return out if out["high"] > out["good"] > out["match"] else dict(DEFAULT_THRESHOLDS)


def _curves(raw: Any) -> dict[str, dict[str, Any]]:
    raw = raw if isinstance(raw, Mapping) else {}
    out = {k: _merge(v, raw.get(k), _CURVES_BOUNDS[k]) for k, v in DEFAULT_CURVES.items()}
    if out["guards"]["suspicious_pct"] > out["guards"]["partial_pct"]:
        out["guards"] = dict(DEFAULT_CURVES["guards"])
    return out


def comparables_config(raw: Any) -> dict[str, Any]:
    """app_config.comparables as the worker uses it; other keys (confirm_sources) as stored."""
    return _merge(DEFAULT_COMPARABLES, raw, _COMPARABLES_BOUNDS)


def rescore_config(raw: Any) -> dict[str, Any]:
    """app_config.rescore as pipeline/rescore.py uses it: days, hour (HH:MM, ART), every_hours."""
    out = _merge(DEFAULT_RESCORE, raw, _RESCORE_BOUNDS)
    # Only a divisor of 24 spaces the slots evenly; next_slot runs any other once a day.
    if 24 % out["every_hours"]:
        out["every_hours"] = DEFAULT_RESCORE["every_hours"]
    return out


def config_number(key: str, raw: Any) -> int | float:
    """app_config.<key> for digest_top_n, price_drop_min_pct and
    alerts_max_per_user_day: the default when missing or out of bounds."""
    default, bound = _SCALARS[key]
    if not bound.accepts(raw):
        return default
    return int(raw) if bound.integer else raw


@dataclass(frozen=True)
class IntelligenceConfig:
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    thresholds: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))
    comparables: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_COMPARABLES))
    curves: dict[str, dict[str, float]] = field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_CURVES.items()})
    red_flags: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_RED_FLAGS))
    # PAR-02 resto: app_config.risk as risk() normalizes it (the signals' switches).
    risk: dict[str, Any] = field(default_factory=lambda: risk(None))
    # f3 «precio × encaje» in shadow (intelligence/f3.py): app_config.score_model_f3
    # as score_model_f3() normalizes it. Only f3 reads it; mode 'off' by default.
    f3: dict[str, Any] = field(default_factory=lambda: score_model_f3(None))

    @property
    def flag_order(self) -> tuple[str, ...]:
        return flag_order(self.red_flags.get("order"))

    @property
    def min_n(self) -> int:
        return int(self.comparables["min_n"])

    def curve(self, name: str) -> dict[str, float]:
        return self.curves[name]

    @classmethod
    def from_app_config(cls, values: Mapping[str, Any]) -> "IntelligenceConfig":
        comparables = comparables_config(values.get("comparables"))
        curves = _curves(values.get("score_curves"))
        try:
            # A bad score_model_f3 row must never break f2 (Scorer.create).
            f3 = score_model_f3(values.get("score_model_f3"),
                                suspicious_pct=curves["guards"].get("suspicious_pct"),
                                min_n=comparables.get("min_n"))
        except Exception:
            f3 = score_model_f3(None)
        return cls(
            weights=_weights(values.get("score_weights")),
            thresholds=_thresholds(values.get("level_thresholds")),
            comparables=comparables,
            curves=curves,
            red_flags=_merge(DEFAULT_RED_FLAGS, values.get("red_flags")),
            risk=risk(values.get("risk")),
            f3=f3,
        )

    @classmethod
    async def load(cls) -> "IntelligenceConfig":
        import db
        keys = ("score_weights", "level_thresholds", "comparables", "score_curves", "red_flags", "risk",
                "score_model_f3")
        return cls.from_app_config({k: await db.get_config(k) for k in keys})


# F-02 (docs/superpowers/specs/2026-10-30-f02-vendedor-design.md): the seller
# classification job. Same bounds as the /admin/config validator; a missing or
# bad value falls back to its default, key by key. `enabled` false turns the
# «posible agencia» inference (dealer_inferred, step 2) off everywhere.
DEFAULT_SELLER_CLASSIFICATION = {"enabled": True, "min_listings": 6, "window_days": 30}
_SELLER_BOUNDS = {"min_listings": (2, 100), "window_days": (1, 180)}


def seller_classification(raw: Any) -> dict[str, Any]:
    """app_config.seller_classification as the worker uses it."""
    out = dict(DEFAULT_SELLER_CLASSIFICATION)
    if not isinstance(raw, Mapping):
        return out
    if isinstance(raw.get("enabled"), bool):
        out["enabled"] = raw["enabled"]
    for key, (lo, hi) in _SELLER_BOUNDS.items():
        value = raw.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and lo <= value <= hi:
            out[key] = value
    return out


def flag_order(raw: Any) -> tuple[str, ...]:
    """app_config.red_flags.order as the worker uses it: the ids as listed,
    without repeats; anything but a list of strings is the default. Unknown ids
    are harmless (no flag carries them); ids it leaves out go last."""
    if not isinstance(raw, (list, tuple)) or not all(isinstance(x, str) for x in raw):
        return DEFAULT_FLAG_ORDER
    return tuple(dict.fromkeys(raw))


# PAR-02 resto (docs/superpowers/specs/2026-11-02-par02-resto-design.md,
# decision 9): app_config.risk beyond the checklist. The photo hash is off by
# default until Juan approves it; Facebook and Instagram images are never
# downloaded (skip_sources holds the source ids: Instagram is onlycarsusados and
# sc_clasificados, worker/collectors/instagram.py; pipeline/photo_hash.py also
# refuses Meta's image hosts whatever the config says). signals.<kind>: "on" shows it, "shadow" stores the pairs without
# showing them (only the duplicate kinds have pairs), "off" drops it.
# Same bounds as the /admin/config validator; a missing or bad value falls
# back to its default, key by key.
SIGNAL_MODES = ("on", "shadow", "off")
DEFAULT_RISK: dict[str, Any] = {
    "photo_hash_count": 3,
    "phash_max_distance": 6,
    "photo_hash": {"enabled": False, "daily_image_cap": 600, "max_attempts": 2, "max_bytes": 2_000_000,
                   "timeout_seconds": 10, "per_host_interval_seconds": 1, "common_min_sellers": 3,
                   "skip_sources": ["facebook", "onlycarsusados", "sc_clasificados"]},
    # photo_conflict_*: how far apart two listings with a shared photo must be
    # to count as other data (duplicate_photos) rather than the same car.
    "cross_source": {"km_tol_pct": 3, "price_tol_pct": 5, "data_min_km": 10_000, "data_max_dist_km": 50,
                     "photo_conflict_km_pct": 10, "photo_conflict_price_pct": 15},
    "signals": {"private_many_listings": "on", "cross_source_photos": "on",
                "cross_source_data": "shadow", "duplicate_photos": "on"},
}
_RISK_BOUNDS = {"photo_hash_count": (1, 5), "phash_max_distance": (0, 16)}
_PHOTO_HASH_BOUNDS = {"daily_image_cap": (0, 5000), "max_attempts": (1, 10), "max_bytes": (10_000, 20_000_000),
                      "timeout_seconds": (1, 60), "per_host_interval_seconds": (0, 60),
                      "common_min_sellers": (2, 100)}
_CROSS_SOURCE_BOUNDS = {"km_tol_pct": (0, 20), "price_tol_pct": (0, 20), "data_min_km": (0, 1_000_000),
                        "data_max_dist_km": (1, 500), "photo_conflict_km_pct": (0, 50),
                        "photo_conflict_price_pct": (0, 50)}


def _bounded(out: dict[str, Any], raw: Mapping[str, Any], bounds: Mapping[str, tuple[float, float]]) -> None:
    for key, (lo, hi) in bounds.items():
        value = raw.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and lo <= value <= hi:
            out[key] = value


def risk(raw: Any) -> dict[str, Any]:
    """app_config.risk as the worker uses it (the checklist's keys are the web's)."""
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_RISK.items()}
    out["photo_hash"]["skip_sources"] = list(DEFAULT_RISK["photo_hash"]["skip_sources"])
    if not isinstance(raw, Mapping):
        return out
    _bounded(out, raw, _RISK_BOUNDS)
    photo = raw.get("photo_hash")
    if isinstance(photo, Mapping):
        if isinstance(photo.get("enabled"), bool):
            out["photo_hash"]["enabled"] = photo["enabled"]
        _bounded(out["photo_hash"], photo, _PHOTO_HASH_BOUNDS)
        skip = photo.get("skip_sources")
        if isinstance(skip, list) and all(isinstance(s, str) for s in skip):
            out["photo_hash"]["skip_sources"] = list(skip)
    cross = raw.get("cross_source")
    if isinstance(cross, Mapping):
        _bounded(out["cross_source"], cross, _CROSS_SOURCE_BOUNDS)
    cs = out["cross_source"]
    # A conflict is never inside the data match's own tolerance.
    cs["photo_conflict_km_pct"] = max(cs["photo_conflict_km_pct"], cs["km_tol_pct"])
    cs["photo_conflict_price_pct"] = max(cs["photo_conflict_price_pct"], cs["price_tol_pct"])
    signals = raw.get("signals")
    if isinstance(signals, Mapping):
        for key in out["signals"]:
            if signals.get(key) in SIGNAL_MODES:
                out["signals"][key] = signals[key]
    return out


# f3 «precio × encaje» (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §8):
# app_config.score_model_f3, read only by intelligence/f3.py. Its own versioned key:
# f2's score_weights / score_curves are never reused, so a deploy or a rollback
# can't mix the formulas. mode: 'off' computes nothing (the default here, so an
# un-migrated database and the tests behave as before); 'shadow' computes and
# stores f3 next to f2 (matches.score_breakdown.shadow_f3, match_decisions) while
# f2 keeps deciding; 'live' is accepted and, until the live PR, behaves as
# 'shadow'. The bounds are /admin/config's (web/lib/admin-config.ts); a missing
# or bad value falls back to its default key by key, and a group that breaks one
# of its cross-key rules falls back as a whole.
F3_MODES = ("off", "shadow", "live")
DEFAULT_SCORE_MODEL_F3: dict[str, Any] = {
    "mode": "off",
    "deal": {"d_floor": 12, "d_ceil": 20, "d_mult": 2.5, "cred_min": 5, "cred_max": 35,
             "r_model": 0.9, "r_noyear": 0.3, "kavak_offset": 9},
    "fit": {"unknown": 0.75, "fail": 0.4, "trim_other": 0.5, "unknown_hard": 0.03, "price_target_at_max": 0.6},
    "levels": {"x_high": 0.70, "y_high": 0.70, "c_high": 0.82, "x_good": 0.65, "y_deal": 0.45,
               "y_good": 0.85, "y_min": 0.30, "n_min_high": 10, "fair_min_d": -2, "low_d": -10},
    "rules": {"seller_cap": True, "agency_voice": True, "placeholder": True, "pro_deal_d": True},
}
F3_GROUPS = ("deal", "fit", "levels")
# (low, high, high excluded): closed intervals except deal.cred_max, [20, 50).
F3_BOUNDS: dict[str, dict[str, tuple[float, float, bool]]] = {
    "deal": {"d_floor": (5, 30, False), "d_ceil": (5, 30, False), "d_mult": (1, 4, False),
             "cred_min": (0, 15, False), "cred_max": (20, 50, True), "r_model": (0.1, 1, False),
             "r_noyear": (0.1, 1, False), "kavak_offset": (0, 20, False)},
    "fit": {"unknown": (0, 1, False), "fail": (0, 1, False), "trim_other": (0, 1, False),
            "unknown_hard": (0, 0.15, False), "price_target_at_max": (0.3, 1, False)},
    "levels": {"x_high": (0.5, 0.95, False), "y_high": (0.5, 0.95, False), "c_high": (0.70, 0.95, False),
               "x_good": (0.3, 0.95, False), "y_deal": (0.1, 0.95, False), "y_good": (0.5, 1, False),
               "y_min": (0.1, 0.6, False), "n_min_high": (5, 100, False), "fair_min_d": (-10, 5, False),
               "low_d": (-30, 0, False)},
}
F3_INTEGERS = frozenset({("levels", "n_min_high")})
_F3_SUSPICIOUS_PCT = SUSPICIOUS_BELOW_MEDIAN_PCT
_EPS = 1e-9


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _f3_group_ok(group: str, g: Mapping[str, Any], suspicious_pct: float) -> bool:
    """The cross-key rules of spec §8 (and of the TS validator)."""
    if group == "deal":
        return g["d_floor"] < g["d_ceil"] and g["cred_min"] < g["cred_max"] and g["cred_max"] < suspicious_pct
    if group == "fit":
        return g["fail"] <= g["unknown"]
    # levels: the combined rule must be able to bite (else it does nothing), and the gates keep their order.
    return (g["c_high"] + _EPS >= 0.6 * g["x_high"] + 0.4 * g["y_high"] and g["x_good"] < g["x_high"]
            and g["y_deal"] < g["y_high"] and g["y_good"] > g["y_min"] and g["low_d"] < g["fair_min_d"])


def f3_params_hash(model: Mapping[str, Any]) -> str:
    """The first 12 hex of sha1 over the parameters (mode excluded), numbers as floats: a shadow row
    carries it, so a moved parameter restarts the measurement (spec §11.4)."""
    def norm(v: Any) -> Any:
        if isinstance(v, Mapping):
            return {str(k): norm(x) for k, x in v.items()}
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return v
        return float(v)
    body = json.dumps({k: norm(model[k]) for k in (*F3_GROUPS, "rules")}, sort_keys=True)
    return hashlib.sha1(body.encode()).hexdigest()[:12]


def score_model_f3(raw: Any, *, suspicious_pct: Any = None, min_n: Any = None) -> dict[str, Any]:
    """app_config.score_model_f3 as f3 uses it. Never raises. Per key: a finite number (never a bool or a
    string: "0.82" is refused) inside its bound, else the default; rules are booleans. Then the cross-key
    rules: a group (deal / fit / levels) that breaks one falls back to its defaults as a whole.
    deal.cred_max must stay below score_curves.guards.suspicious_pct (f3's «sospechoso» is f2's guard).
    levels.n_min_high is at least comparables.min_n. mode outside F3_MODES is 'off'. Adds "params"."""
    susp = float(suspicious_pct) if _finite(suspicious_pct) else float(_F3_SUSPICIOUS_PCT)
    floor_n = int(min_n) if _finite(min_n) else int(DEFAULT_COMPARABLES["min_n"])
    out: dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULT_SCORE_MODEL_F3.items()}
    src = raw if isinstance(raw, Mapping) else {}
    mode = src.get("mode")
    out["mode"] = mode if isinstance(mode, str) and mode in F3_MODES else DEFAULT_SCORE_MODEL_F3["mode"]
    for group in F3_GROUPS:
        given = src.get(group)
        g = dict(DEFAULT_SCORE_MODEL_F3[group])
        if isinstance(given, Mapping):
            for key, (lo, hi, open_hi) in F3_BOUNDS[group].items():
                value = given.get(key)
                if not _finite(value) or value < lo or value > hi or (open_hi and value >= hi):
                    continue
                if (group, key) in F3_INTEGERS:
                    if float(value) != int(value):
                        continue
                    value = int(value)
                g[key] = value
        if not _f3_group_ok(group, g, susp):
            g = dict(DEFAULT_SCORE_MODEL_F3[group])
        out[group] = g
    out["levels"]["n_min_high"] = max(int(out["levels"]["n_min_high"]), floor_n)
    rules_in = src.get("rules")
    if isinstance(rules_in, Mapping):
        for key in DEFAULT_SCORE_MODEL_F3["rules"]:
            if isinstance(rules_in.get(key), bool):
                out["rules"][key] = rules_in[key]
    out["params"] = f3_params_hash(out)
    return out
