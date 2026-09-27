"""One listing × one profile → everything a match row stores. Pure.

    evaluate(listing, profile, price_ref=…, cfg=…, now=…) → Evaluation | None

None means no match: a hard filter failed, or the price is a down payment
(price_partial or the ≥65% guard). The pipeline (pipeline/scoring.py) does
the I/O around it: loads rows, comparables and config, writes `matches`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from intelligence.comparables import PriceRef
from intelligence.config import SCORING_VERSION, IntelligenceConfig
from intelligence.matching import MatchResult, evaluate as evaluate_filters
from intelligence.red_flags import RedFlag, red_flags
from intelligence.scoring import Score, score as compute_score
from intelligence.seller_questions import seller_questions


@dataclass
class Evaluation:
    match: MatchResult
    score: Score
    price_ref: PriceRef | None
    red_flags: list[RedFlag]
    questions: str

    @property
    def level(self) -> str:
        return self.score.level

    def row(self) -> dict[str, Any]:
        """The columns of `matches` this evaluation fills."""
        return {
            "score": self.score.score,
            "level": self.score.level,
            "score_breakdown": self.score.breakdown(),
            "match_reasons": self.match.to_json(),
            "price_ref": self.price_ref.to_json() if self.price_ref else None,
            "red_flags": [f.to_json() for f in self.red_flags],
            "scoring_version": SCORING_VERSION,
        }


def assess(listing: Mapping[str, Any], profile: Mapping[str, Any], *,
           price_ref: PriceRef | None, cfg: IntelligenceConfig, now: datetime,
           fx_rate: float | None = None, timing_belt: bool | None = None) -> tuple[MatchResult, Score, Evaluation]:
    """Match, score, flags and questions whether or not it matches (explain_match)."""
    result = evaluate_filters(listing, profile, fx_rate=fx_rate)
    s = compute_score(listing, profile, result, price_ref, cfg, now=now)
    flags = red_flags(listing, diff_pct=s.extra.get("diff_pct"), guard=s.guard,
                      timing_belt=timing_belt, cfg=cfg, now=now)
    questions = seller_questions(listing, flags, timing_belt=timing_belt, now=now)
    return result, s, Evaluation(result, s, price_ref, flags, questions)


def evaluate(listing: Mapping[str, Any], profile: Mapping[str, Any], *,
             price_ref: PriceRef | None, cfg: IntelligenceConfig, now: datetime,
             fx_rate: float | None = None, timing_belt: bool | None = None) -> Evaluation | None:
    result, s, ev = assess(listing, profile, price_ref=price_ref, cfg=cfg, now=now,
                           fx_rate=fx_rate, timing_belt=timing_belt)
    if not result.is_match or s.excluded:
        return None
    return ev
