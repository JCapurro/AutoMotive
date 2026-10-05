"""Opportunity Score 0–100 (§17–18, sección 6.3). Pure.

    score = round(100 · Σ wᵢ·cᵢ / Σ wᵢ)      cᵢ ∈ [0,1], wᵢ from app_config.score_weights

Every component keeps {c, w, contribution, explanation} in score_breakdown,
which is what the detail page and the admin inspector show. Curves and
weights come from IntelligenceConfig (app_config), so the pilot tunes them
without a deploy.

Guards carried over from price_check:
  * d ≥ partial_pct (65%)  → the price is taken for a down payment: excluded;
  * suspicious_pct (50%) ≤ d < partial_pct → level capped at `good` (+ red flag);
  * price_partial = true   → excluded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from intelligence import copy
from intelligence.comparables import PriceRef, diff_pct
from intelligence.config import COMPONENTS, SCORING_VERSION, IntelligenceConfig
from intelligence.levels import level_for
from intelligence.matching import OK, MatchResult, preferred_trims, trim_matches


@dataclass(frozen=True)
class Component:
    c: float
    explanation: str


@dataclass
class Score:
    score: int
    level: str
    components: dict[str, Component]
    weights: dict[str, float]
    guard: str | None = None           # None | 'suspicious' | 'partial'
    excluded: str | None = None        # why the listing can't be a match (partial price)
    extra: dict[str, Any] = field(default_factory=dict)

    def breakdown(self) -> dict[str, Any]:
        total_w = sum(self.weights.values()) or 1
        out: dict[str, Any] = {}
        for name, comp in self.components.items():
            w = self.weights[name]
            out[name] = {"c": round(comp.c, 4), "w": w,
                         "contribution": round(100 * w * comp.c / total_w, 2),
                         "explanation": comp.explanation}
        out["scoring_version"] = SCORING_VERSION
        if self.guard:
            out["guard"] = self.guard
        return out


def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def _pct(x: float) -> str:
    return f"{abs(x):.0f}"


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def price_component(listing: Mapping[str, Any], ref: PriceRef | None,
                    cfg: IntelligenceConfig) -> tuple[Component, float | None]:
    curve = cfg.curve("price")
    if ref is None or not ref.enough(cfg.min_n):
        n = ref.n if ref else 0
        return Component(0.5, copy.EXPLAIN["price_few"].format(n=n)), None
    d = ref.diff_pct if ref.diff_pct is not None else diff_pct(listing.get("price_usd"), ref.median)
    if d is None:
        return Component(0.5, copy.EXPLAIN["price_few"].format(n=ref.n)), None
    c = clamp(curve["base"] + d / curve["pct_per_unit"])
    key = "price_below" if round(d) > 0 else "price_above" if round(d) < 0 else "price_at"
    return Component(c, copy.EXPLAIN[key].format(pct=_pct(d), n=ref.n)), d


def match_component(result: MatchResult, cfg: IntelligenceConfig) -> Component:
    soft = result.soft
    # A non-strict trim is its own component (versión); it doesn't count twice.
    prefs = {k: r for k, r in soft.items() if k != "trim"}
    met = sum(1 for r in prefs.values() if r.result == OK)
    base = met / len(prefs) if prefs else 1.0
    unknown = result.unknown
    c = clamp(base - cfg.curve("match")["unknown_penalty"] * len(unknown))
    parts = [copy.EXPLAIN["match"].format(met=met, total=len(prefs)) if prefs else copy.EXPLAIN["match_none"]]
    if unknown:
        names = ", ".join(copy.FILTER_NAMES.get(k, k) for k in unknown)
        parts.append(copy.EXPLAIN["match_unknown"].format(names=names))
    return Component(c, "; ".join(parts))


def km_component(listing: Mapping[str, Any], ref: PriceRef | None, cfg: IntelligenceConfig) -> Component:
    km = listing.get("mileage_km")
    if km is None or ref is None or not ref.enough(cfg.min_n) or not ref.median_km:
        return Component(0.5, copy.EXPLAIN["km_none"])
    curve = cfg.curve("km")
    rel = 1 - km / ref.median_km
    c = clamp(curve["base"] + curve["slope"] * rel)
    pct = rel * 100
    key = "km_less" if round(pct) > 0 else "km_more" if round(pct) < 0 else "km_same"
    return Component(c, copy.EXPLAIN[key].format(pct=_pct(pct)))


def trim_component(listing: Mapping[str, Any], profile: Mapping[str, Any],
                   cfg: IntelligenceConfig) -> Component:
    curve = cfg.curve("trim")
    wanted = preferred_trims(profile)
    trim = listing.get("trim")
    if not wanted:
        return Component(curve["no_preference"], copy.EXPLAIN["trim_any"])
    if not trim:
        return Component(curve["unknown"], copy.EXPLAIN["trim_unknown"])
    if any(trim_matches(trim, w) for w in wanted):
        return Component(curve["preferred"], copy.EXPLAIN["trim_preferred"].format(trim=trim))
    return Component(curve["other"], copy.EXPLAIN["trim_other"].format(trim=trim))


def age_hours(listing: Mapping[str, Any], now: datetime) -> tuple[float | None, bool]:
    """Publication age only; detection time is not evidence of freshness."""
    published = listing.get("published_at")
    if published is None:
        return None, False
    return max(0.0, (now - published).total_seconds() / 3600), True


def recency_component(listing: Mapping[str, Any], cfg: IntelligenceConfig, now: datetime) -> Component:
    hours, _ = age_hours(listing, now)
    if hours is None:
        return Component(0.0, copy.EXPLAIN["recency_unknown"])
    c = clamp(0.5 ** (hours / cfg.curve("recency")["half_life_hours"]))
    return Component(c, copy.EXPLAIN["recency_published"].format(ago=copy.ago(hours)))


def completeness_fields(listing: Mapping[str, Any], cfg: IntelligenceConfig) -> dict[str, bool]:
    curve = cfg.curve("completeness")
    description = listing.get("description") or ""
    return {
        "year": listing.get("year") is not None,
        "km": listing.get("mileage_km") is not None,
        "price": bool(listing.get("price")),
        "transmission": bool(listing.get("transmission")),
        "trim": bool(listing.get("trim")),
        "location": bool(listing.get("location_text")) or listing.get("lat") is not None,
        "description": len(description.strip()) >= curve["min_description_chars"],
        "images": len(listing.get("images") or []) >= curve["min_images"],
        "seller_type": bool(listing.get("seller_type")),
        "date": listing.get("published_at") is not None,
    }


def completeness_component(listing: Mapping[str, Any], cfg: IntelligenceConfig) -> Component:
    fields = completeness_fields(listing, cfg)
    have = sum(fields.values())
    return Component(have / len(fields), copy.EXPLAIN["completeness"].format(have=have, total=len(fields)))


# ---------------------------------------------------------------------------
# Score
# ---------------------------------------------------------------------------

def score(listing: Mapping[str, Any], profile: Mapping[str, Any], result: MatchResult,
          ref: PriceRef | None, cfg: IntelligenceConfig, *, now: datetime) -> Score:
    price, d = price_component(listing, ref, cfg)
    components = {
        "price": price,
        "match": match_component(result, cfg),
        "km": km_component(listing, ref, cfg),
        "trim": trim_component(listing, profile, cfg),
        "recency": recency_component(listing, cfg, now),
        "completeness": completeness_component(listing, cfg),
    }
    weights = {k: float(cfg.weights.get(k, 0)) for k in COMPONENTS}
    total_w = sum(weights.values()) or 1
    value = round_half_up(100 * sum(weights[k] * components[k].c for k in COMPONENTS) / total_w)
    value = max(0, min(100, value))

    guards = cfg.curve("guards")
    guard = excluded = cap = None
    if listing.get("price_partial"):
        guard, excluded = "partial", listing.get("price_partial_reason") or "precio parcial"
    elif d is not None and d >= guards["partial_pct"]:
        guard, excluded = "partial", f"{d:.0f}% bajo la mediana: el precio publicado parece un anticipo"
    elif d is not None and d >= guards["suspicious_pct"]:
        guard, cap = "suspicious", "good"
    return Score(value, level_for(value, cfg.thresholds, cap=cap), components, weights,
                 guard=guard, excluded=excluded, extra={"diff_pct": d})
