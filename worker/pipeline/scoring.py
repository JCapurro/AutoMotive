"""The I/O around intelligence/: rows, comparables, fx and config in; matches out.

A `Scorer` is built once per batch (crawl target, rematch, re-score): it
loads the config and today's USD/ARS quote, and caches each listing's row and
comparables, which don't depend on the profile. `evaluate` is then the pure
intelligence.engine call for any (listing, profile) pair, plus (PRO-02) the
margin against the dealers' median with the profile's own zones
(intelligence/margin.py): app_config.dealer_margin, cost_estimator and the
latest stored quote are read once per batch too.

«Valor justo» in shadow (intelligence/fair_value.py): with app_config.fair_value.mode
'shadow' or 'live', `create` takes the enabled model curves from pipeline/fair_value's
process cache, and `evaluate` adds score_breakdown.shadow_fair_value next to f2's row.
With 'off' nothing is read and the row is today's.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import db
from db.repos import guides as guides_repo
from db.repos import listings as listings_repo
from db.repos.fx import latest_stored, quote_for_today
from intelligence import comparables, cost_estimator, fair_value, margin
from intelligence.comparables import PriceRef
from intelligence.config import IntelligenceConfig, dealer_program
from intelligence.dealer import hidden_reason
from intelligence.engine import Evaluation, evaluate
from intelligence.f3 import warn_limited
from intelligence.guides import DEFAULT_MAX_QUESTIONS_IN_LISTING, MAX_QUESTIONS_IN_LISTING, GuideIndex, pick
from intelligence.matching import vehicle_fails
from pipeline import fair_value as fair_value_job

log = logging.getLogger(__name__)

# America/Argentina/Buenos_Aires (no DST since 2009): "today" for fx.max_age_days.
_AR = timezone(timedelta(hours=-3))


@dataclass
class Scorer:
    cfg: IntelligenceConfig
    fx_rate: float | None
    now: datetime
    rows: dict[int, dict[str, Any]] = field(default_factory=dict)
    refs: dict[int, PriceRef | None] = field(default_factory=dict)
    # PRO-02: margin.parse_config, cost_estimator.parse_config, latest_stored.
    margin_cfg: dict[str, Any] | None = None
    cost_cfg: dict[str, Any] | None = None
    fx_latest: dict[str, Any] | None = None
    # PAR-04: the published guides' questions (db/repos/guides.published_index)
    # and how many a listing gets (llm_limits.model_guide.max_questions_in_listing).
    guides: GuideIndex = field(default_factory=dict)
    guide_limit: int = DEFAULT_MAX_QUESTIONS_IN_LISTING
    # Agencias (spec §2): app_config.dealer_program, sanitized. A hidden
    # dealer's listing is never evaluated, so no path (crawl, rematch,
    # re-score, color, near_zone, count_after_expiry) stores a match for it.
    program: dict[str, Any] = field(default_factory=lambda: dealer_program(None))
    # «Valor justo»: the enabled curves by (lower(make), lower(model)); empty with mode 'off'.
    curves: dict[tuple[str, str], fair_value.Curve] = field(default_factory=dict)

    @classmethod
    async def create(cls, now: datetime | None = None) -> "Scorer":
        cfg = await IntelligenceConfig.load()
        margin_cfg = margin.parse_config(await db.get_config("dealer_margin"))
        cost_cfg = cost_estimator.parse_config(await db.get_config("cost_estimator"))
        guide_limit = guide_questions_limit(await db.get_config("llm_limits"))
        program = dealer_program(await db.get_config("dealer_program"))
        async with db.connection() as cx:
            quote = await quote_for_today(cx)
            fx_latest = await latest_stored(cx)
            guides = await guides_repo.published_index(cx)
        # Never raises; reads nothing with mode 'off' (the code default).
        curves = await fair_value_job.cached_curves(cfg.fair_value)
        return cls(cfg, quote.rate, now or datetime.now(timezone.utc),
                   margin_cfg=margin_cfg, cost_cfg=cost_cfg, fx_latest=fx_latest,
                   guides=guides, guide_limit=guide_limit, program=program, curves=curves)

    async def prepare(self, listing_ids: Iterable[int], *,
                      refs_limit: int | None = None) -> dict[int, dict[str, Any]]:
        """Load the rows and comparables of these listings (once each).
        `refs_limit`: comparables only for the first that many ids; the rest
        are scored without a price reference (the nightly re-score adds it)."""
        ids = list(dict.fromkeys(listing_ids))
        new = [i for i in ids if i not in self.rows]
        if new:
            async with db.connection() as cx:
                self.rows.update(await listings_repo.rows_for_scoring(cx, new))
        wanted = [i for i in ids if i in self.rows]
        if refs_limit is not None:
            wanted = wanted[:max(0, refs_limit)]
        if missing := [i for i in wanted if i not in self.refs]:
            async with db.connection() as cx:
                self.refs.update(await comparables.fetch_many(cx, missing, self.cfg.comparables))
        return self.rows

    def evaluate(self, listing_id: int, profile: dict[str, Any]) -> Evaluation | None:
        row = self.rows.get(listing_id)
        if row is None:
            return None
        # The send gate only excludes: a visible dealer's car is scored like any listing (C1).
        if hidden_reason(row, self.program, now=self.now) is not None:
            return None
        # Another make or model never matches: skip the scoring (0.7 ms a
        # call), which a batch with every model of a source (an inventory
        # target: Kavak's 1.300 cars) would spend on every search.
        if vehicle_fails(row, profile.get("filters") or {}):
            return None
        ref = self.refs.get(listing_id)
        ev = evaluate(row, profile, price_ref=ref, cfg=self.cfg,
                      now=self.now, fx_rate=self.fx_rate, timing_belt=row.get("timing_belt"),
                      guide=pick(self.guides, row), guide_limit=self.guide_limit)
        if ev is not None:
            ev.margin_ref = margin.compute(row, ref, profile_zones(profile), self.margin_cfg, self.cost_cfg,
                                           self.fx_latest, self.cfg.min_n, self.now.astimezone(_AR).date())
            if self.curves:
                ev.shadow_fair_value = self.fair_value_shadow(row, profile, ev, listing_id)
        return ev

    def fair_value_shadow(self, row: dict[str, Any], profile: dict[str, Any], ev: Evaluation,
                          listing_id: int) -> dict[str, Any] | None:
        """The shadow block of this evaluation, or None. Never raises: f2's row is never at stake."""
        try:
            curve = self.curves.get(fair_value_job.model_key(row))
            if curve is None:
                return None
            return fair_value.shadow(row, profile, ev.match, ev.price_ref, ev.score, self.cfg, curve=curve,
                                     fetched=listing_id in self.refs, now=self.now, fx_rate=self.fx_rate)
        except Exception:
            warn_limited(log, "scorer.fair_value", "fair value shadow failed (listing %s)", listing_id,
                         exc_info=True)
            return None


def profile_zones(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """The search's zones as cost_estimator reads them: its origin and filters.extra_locations."""
    f = profile.get("filters") if isinstance(profile.get("filters"), dict) else {}
    return cost_estimator.search_zones({"lat": profile.get("origin_lat"), "lon": profile.get("origin_lon"),
                                        "label": f.get("location_label"), "extra_locations": f.get("extra_locations")})


def guide_questions_limit(llm_limits: Any) -> int:
    """llm_limits.model_guide.max_questions_in_listing, 0 to 3 (3 without it).

    The backlog's rule is «hasta 3» questions of the guide per listing: a
    larger value is clamped (/admin/config refuses it too, lib/admin-config.ts)."""
    cfg = llm_limits.get("model_guide") if isinstance(llm_limits, dict) else None
    value = cfg.get("max_questions_in_listing") if isinstance(cfg, dict) else None
    if isinstance(value, bool) or not isinstance(value, int):
        return DEFAULT_MAX_QUESTIONS_IN_LISTING
    return max(0, min(MAX_QUESTIONS_IN_LISTING, value))
