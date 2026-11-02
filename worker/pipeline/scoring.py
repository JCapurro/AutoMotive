"""The I/O around intelligence/: rows, comparables, fx and config in; matches out.

A `Scorer` is built once per batch (crawl target, rematch, re-score): it
loads the config and today's USD/ARS quote, and caches each listing's row and
comparables, which don't depend on the profile. `evaluate` is then the pure
intelligence.engine call for any (listing, profile) pair, plus (PRO-02) the
margin against the dealers' median with the profile's own zones
(intelligence/margin.py): app_config.dealer_margin, cost_estimator and the
latest stored quote are read once per batch too.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import db
from db.repos import listings as listings_repo
from db.repos.fx import latest_stored, quote_for_today
from intelligence import comparables, cost_estimator, margin
from intelligence.comparables import PriceRef
from intelligence.config import IntelligenceConfig
from intelligence.engine import Evaluation, evaluate

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

    @classmethod
    async def create(cls, now: datetime | None = None) -> "Scorer":
        cfg = await IntelligenceConfig.load()
        margin_cfg = margin.parse_config(await db.get_config("dealer_margin"))
        cost_cfg = cost_estimator.parse_config(await db.get_config("cost_estimator"))
        async with db.connection() as cx:
            quote = await quote_for_today(cx)
            fx_latest = await latest_stored(cx)
        return cls(cfg, quote.rate, now or datetime.now(timezone.utc),
                   margin_cfg=margin_cfg, cost_cfg=cost_cfg, fx_latest=fx_latest)

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
        ref = self.refs.get(listing_id)
        ev = evaluate(row, profile, price_ref=ref, cfg=self.cfg,
                      now=self.now, fx_rate=self.fx_rate, timing_belt=row.get("timing_belt"))
        if ev is not None:
            ev.margin_ref = margin.compute(row, ref, profile_zones(profile), self.margin_cfg, self.cost_cfg,
                                           self.fx_latest, self.cfg.min_n, self.now.astimezone(_AR).date())
        return ev


def profile_zones(profile: dict[str, Any]) -> list[dict[str, Any]]:
    """The search's zones as cost_estimator reads them: its origin and filters.extra_locations."""
    f = profile.get("filters") if isinstance(profile.get("filters"), dict) else {}
    return cost_estimator.search_zones({"lat": profile.get("origin_lat"), "lon": profile.get("origin_lon"),
                                        "label": f.get("location_label"), "extra_locations": f.get("extra_locations")})
