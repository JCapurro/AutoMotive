"""The I/O around intelligence/: rows, comparables, fx and config in; matches out.

A `Scorer` is built once per batch (crawl target, rematch, re-score): it
loads the config and today's USD/ARS quote, and caches each listing's row and
comparables, which don't depend on the profile. `evaluate` is then the pure
intelligence.engine call for any (listing, profile) pair.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

import db
from db.repos import listings as listings_repo
from db.repos.fx import quote_for_today
from intelligence import comparables
from intelligence.comparables import PriceRef
from intelligence.config import IntelligenceConfig
from intelligence.engine import Evaluation, evaluate


@dataclass
class Scorer:
    cfg: IntelligenceConfig
    fx_rate: float | None
    now: datetime
    rows: dict[int, dict[str, Any]] = field(default_factory=dict)
    refs: dict[int, PriceRef | None] = field(default_factory=dict)

    @classmethod
    async def create(cls, now: datetime | None = None) -> "Scorer":
        cfg = await IntelligenceConfig.load()
        async with db.connection() as cx:
            quote = await quote_for_today(cx)
        return cls(cfg, quote.rate, now or datetime.now(timezone.utc))

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
        return evaluate(row, profile, price_ref=self.refs.get(listing_id), cfg=self.cfg,
                        now=self.now, fx_rate=self.fx_rate, timing_belt=row.get("timing_belt"))
