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
SCORING_VERSION = "f2-v2"

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
DEFAULT_RED_FLAGS = {"much_cheaper_pct": 25, "anticipo_pct": 50, "min_km_per_year": 5000,
                     "min_description_chars": 150}
DEFAULT_RESCORE = {"days": 14, "hour": "04:00"}


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
    red_flags: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_RED_FLAGS))

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
        )

    @classmethod
    async def load(cls) -> "IntelligenceConfig":
        import db
        keys = ("score_weights", "level_thresholds", "comparables", "score_curves", "red_flags")
        return cls.from_app_config({k: await db.get_config(k) for k in keys})
