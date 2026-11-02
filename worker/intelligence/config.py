"""Weights, curves and thresholds of the intelligence layer (sección 6, Apéndice A).

Everything tunable lives in app_config so the pilot can adjust it without a
deploy. `IntelligenceConfig.from_app_config` is pure: it takes the raw values
(missing keys fall back to the defaults below, which mirror supabase/seed.sql);
`load()` reads them through the cached db.get_config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

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


def _merge(defaults: Mapping[str, Any], value: Any) -> dict[str, Any]:
    out = dict(defaults)
    if isinstance(value, Mapping):
        out.update({k: v for k, v in value.items() if v is not None})
    return out


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
        curves_in = values.get("score_curves") or {}
        return cls(
            weights=_merge(DEFAULT_WEIGHTS, values.get("score_weights")),
            thresholds=_merge(DEFAULT_THRESHOLDS, values.get("level_thresholds")),
            comparables=_merge(DEFAULT_COMPARABLES, values.get("comparables")),
            curves={k: _merge(v, curves_in.get(k)) for k, v in DEFAULT_CURVES.items()},
            red_flags=_merge(DEFAULT_RED_FLAGS, values.get("red_flags")),
            risk=risk(values.get("risk")),
        )

    @classmethod
    async def load(cls) -> "IntelligenceConfig":
        import db
        keys = ("score_weights", "level_thresholds", "comparables", "score_curves", "red_flags", "risk")
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
# downloaded. signals.<kind>: "on" shows it, "shadow" stores the pairs without
# showing them (only the duplicate kinds have pairs), "off" drops it.
# Same bounds as the /admin/config validator; a missing or bad value falls
# back to its default, key by key.
SIGNAL_MODES = ("on", "shadow", "off")
DEFAULT_RISK: dict[str, Any] = {
    "photo_hash_count": 3,
    "phash_max_distance": 6,
    "photo_hash": {"enabled": False, "daily_image_cap": 600, "max_attempts": 2, "max_bytes": 2_000_000,
                   "timeout_seconds": 10, "per_host_interval_seconds": 1, "common_min_sellers": 3,
                   "skip_sources": ["facebook", "instagram"]},
    "cross_source": {"km_tol_pct": 3, "price_tol_pct": 5, "data_min_km": 10_000, "data_max_dist_km": 50},
    "signals": {"private_many_listings": "on", "cross_source_photos": "on",
                "cross_source_data": "shadow", "duplicate_photos": "on"},
}
_RISK_BOUNDS = {"photo_hash_count": (1, 5), "phash_max_distance": (0, 16)}
_PHOTO_HASH_BOUNDS = {"daily_image_cap": (0, 5000), "max_attempts": (1, 10), "max_bytes": (10_000, 20_000_000),
                      "timeout_seconds": (1, 60), "per_host_interval_seconds": (0, 60),
                      "common_min_sellers": (2, 100)}
_CROSS_SOURCE_BOUNDS = {"km_tol_pct": (0, 20), "price_tol_pct": (0, 20), "data_min_km": (0, 1_000_000),
                        "data_max_dist_km": (1, 500)}


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
    signals = raw.get("signals")
    if isinstance(signals, Mapping):
        for key in out["signals"]:
            if signals.get(key) in SIGNAL_MODES:
                out["signals"][key] = signals[key]
    return out
