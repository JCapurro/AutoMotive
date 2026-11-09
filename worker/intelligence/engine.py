"""One listing × one profile → everything a match row stores. Pure.

    evaluate(listing, profile, price_ref=…, cfg=…, now=…) → Evaluation | None

None means no match: a hard filter failed, or the price is a down payment
(price_partial or the ≥65% guard). The pipeline (pipeline/scoring.py) does
the I/O around it: loads rows, comparables and config, writes `matches`.

f3 in shadow (intelligence/f3.py): for a match, and only while
app_config.score_model_f3.mode is 'shadow' (or 'live'), f3 is computed after
f2 is complete and stored as score_breakdown.shadow_f3. Nothing of f2 reads
it, and an f3 failure leaves the evaluation exactly as without it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from intelligence import f3
from intelligence.comparables import PriceRef
from intelligence.config import SCORING_VERSION, IntelligenceConfig
from intelligence.matching import MatchResult, evaluate as evaluate_filters
from intelligence.red_flags import RedFlag, red_flags
from intelligence.scoring import Score, score as compute_score
from intelligence.guides import DEFAULT_MAX_QUESTIONS_IN_LISTING, GuideEntry
from intelligence.seller_questions import GENERIC_KEYS, question_items


@dataclass
class Evaluation:
    match: MatchResult
    score: Score
    price_ref: PriceRef | None
    red_flags: list[RedFlag]
    questions: str
    # PRO-01: the specific questions (question_texts), for the ready-to-send message.
    contact_questions: list[str] = field(default_factory=list)
    # PRO-02: matches.margin_ref (intelligence/margin.py), filled by
    # pipeline/scoring.Scorer, which has the config and the search's zones.
    margin_ref: dict[str, Any] | None = None
    # PAR-04: where each question of `questions` came from (matches.question_origins).
    question_origins: list[dict[str, Any]] = field(default_factory=list)
    # f3 in shadow: f3.shadow()'s JSON, or None (mode off, no match, or f3 failed).
    shadow_f3: dict[str, Any] | None = None

    @property
    def level(self) -> str:
        return self.score.level

    def row(self) -> dict[str, Any]:
        """The columns of `matches` this evaluation fills."""
        breakdown = self.score.breakdown()
        if self.shadow_f3 is not None:
            breakdown["shadow_f3"] = self.shadow_f3
        return {
            "score": self.score.score,
            "level": self.score.level,
            "score_breakdown": breakdown,
            "match_reasons": self.match.to_json(),
            "price_ref": self.price_ref.to_json() if self.price_ref else None,
            "red_flags": [f.to_json() for f in self.red_flags],
            "seller_questions": self.questions,
            "contact_questions": self.contact_questions,
            "scoring_version": SCORING_VERSION,
            "margin_ref": self.margin_ref,
            "question_origins": self.question_origins,
        }


def assess(listing: Mapping[str, Any], profile: Mapping[str, Any], *,
           price_ref: PriceRef | None, cfg: IntelligenceConfig, now: datetime,
           fx_rate: float | None = None, timing_belt: bool | None = None, guide: GuideEntry | None = None,
           guide_limit: int = DEFAULT_MAX_QUESTIONS_IN_LISTING) -> tuple[MatchResult, Score, Evaluation]:
    """Match, score, flags and questions whether or not it matches (explain_match).
    `guide`: the published model guide whose questions the listing gets (PAR-04)."""
    result = evaluate_filters(listing, profile, fx_rate=fx_rate)
    s = compute_score(listing, profile, result, price_ref, cfg, now=now)
    flags = red_flags(listing, diff_pct=s.extra.get("diff_pct"), guard=s.guard,
                      timing_belt=timing_belt, cfg=cfg, now=now)
    items = question_items(listing, flags, timing_belt=timing_belt, now=now, guide=guide, guide_limit=guide_limit)
    questions = " ".join(q.text for q in items)
    # question_texts: the specific ones, without the questions every seller gets.
    contact = [q.text for q in items if q.key not in GENERIC_KEYS][:3]
    # f3 after f2 is complete, for f2's matches only (f3's exclusion is f2's); never raises.
    shadow = (f3.shadow(listing, profile, result, price_ref, s, cfg, fx_rate=fx_rate)
              if result.is_match and not s.excluded else None)
    return result, s, Evaluation(result, s, price_ref, flags, questions, contact_questions=contact,
                                 question_origins=[q.origin_json() for q in items], shadow_f3=shadow)


def evaluate(listing: Mapping[str, Any], profile: Mapping[str, Any], *,
             price_ref: PriceRef | None, cfg: IntelligenceConfig, now: datetime,
             fx_rate: float | None = None, timing_belt: bool | None = None, guide: GuideEntry | None = None,
             guide_limit: int = DEFAULT_MAX_QUESTIONS_IN_LISTING) -> Evaluation | None:
    result, s, ev = assess(listing, profile, price_ref=price_ref, cfg=cfg, now=now,
                           fx_rate=fx_rate, timing_belt=timing_belt, guide=guide, guide_limit=guide_limit)
    if not result.is_match or s.excluded:
        return None
    return ev
