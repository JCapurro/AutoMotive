"""2.5 counts what appears after the end, never a target's first run
(docs/MAILS_DE_PLAN.md); the PostgreSQL flow is in test_ingest_postgres.py
(CountAfterExpiryCrawlTests)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from pipeline import scheduler

NOW = datetime.now(timezone.utc)
ENDED = NOW - timedelta(days=1)
TARGET = {"id": 5, "source": "deruedas", "make": "Volkswagen", "model": "Gol Trend"}


class _Scorer:
    def __init__(self, rows: dict[int, dict]) -> None:
        self.rows = rows

    def evaluate(self, lid: int, profile: dict):
        return SimpleNamespace(level="good")


def _row(lid: int, *, hours_ago: float, not_news: dict | None = None) -> dict:
    row = {"source": "deruedas", "external_id": str(lid), "published_at": None,
           "first_seen_at": NOW - timedelta(hours=hours_ago)}
    if not_news is not None:
        row["attributes"] = {"_not_news": {"run_id": 1, "prev_id": None, **not_news}}
    return row


class CountAfterExpiryTests(unittest.IsolatedAsyncioTestCase):
    async def count(self, rows, *, bootstrapped_hours_ago=None, target=TARGET, first_run=False, exclude=()):
        alert = {"id": 7, "ended_at": ENDED, "profile": {}}
        at = None if bootstrapped_hours_ago is None else NOW - timedelta(hours=bootstrapped_hours_ago)
        with patch.object(scheduler.db, "counting_alerts_for_target", AsyncMock(return_value=[alert])) as alerts, \
             patch.object(scheduler, "bootstrapped_at", AsyncMock(return_value=at)) as boot, \
             patch.object(scheduler.expired_matches, "store", AsyncMock()) as store:
            n = await scheduler.count_after_expiry(target, list(rows), _Scorer(rows),
                                                   first_run=first_run, max_age_days=15, exclude=exclude)
        return n, alerts, boot, store

    async def test_a_portal_first_pass_found_again_is_not_counted(self):
        # deRuedas, 2026-10-14: its first pass (10 h ago, run ended 9.9 h ago)
        # came after the end and was found again the next day.
        rows = {1: _row(1, hours_ago=10), 2: _row(2, hours_ago=0)}
        n, _, boot, store = await self.count(rows, bootstrapped_hours_ago=9.9)
        self.assertEqual(n, 1)
        boot.assert_awaited_once_with(5)
        store.assert_awaited_once_with([(7, 2, ENDED, "good")])

    async def test_a_listing_another_target_inserted_after_the_bootstrap_counts(self):
        # An Onix Plus first stored by the Onix target is not new in this run,
        # but it appeared after the end and after this target's first run.
        rows = {1: _row(1, hours_ago=3)}
        n, *_ = await self.count(rows, bootstrapped_hours_ago=200)
        self.assertEqual(n, 1)

    async def test_a_listing_another_target_stored_on_its_first_run_counts(self):
        # The same Onix Plus, marked by the Onix target's first run (pipeline/news.py):
        # that target only found it first, it is still new.
        rows = {1: _row(1, hours_ago=3, not_news={"reason": "first_run", "target_id": 6})}
        n, *_ = await self.count(rows, bootstrapped_hours_ago=200)
        self.assertEqual(n, 1)

    async def test_this_target_s_own_first_run_is_not_counted_on_its_next_runs(self):
        # An empty first read doesn't bootstrap: the next one is still a first run.
        rows = {1: _row(1, hours_ago=3, not_news={"reason": "first_run", "target_id": 5})}
        n, *_ = await self.count(rows, bootstrapped_hours_ago=200)
        self.assertEqual(n, 0)

    async def test_listings_marked_not_news_are_never_counted(self):
        rows = {lid: _row(lid, hours_ago=3, not_news={"reason": reason, "target_id": 6})
                for lid, reason in enumerate(("step", "reappearance", "envelope", "band"), 1)}
        rows[5] = _row(5, hours_ago=3)
        n, _, _, store = await self.count(rows, bootstrapped_hours_ago=200)
        self.assertEqual(n, 1)
        store.assert_awaited_once_with([(7, 5, ENDED, "good")])

    async def test_backfill_ids_are_excluded(self):
        rows = {1: _row(1, hours_ago=3), 2: _row(2, hours_ago=3)}
        n, _, _, store = await self.count(rows, bootstrapped_hours_ago=200, exclude=frozenset({1}))
        self.assertEqual(n, 1)
        store.assert_awaited_once_with([(7, 2, ENDED, "good")])

    async def test_listings_first_seen_before_the_end_are_not_counted(self):
        n, *_ = await self.count({1: _row(1, hours_ago=48)}, bootstrapped_hours_ago=200)
        self.assertEqual(n, 0)

    async def test_without_a_successful_run_only_the_end_applies(self):
        n, _, boot, _ = await self.count({1: _row(1, hours_ago=3)}, target=dict(TARGET, id=None))
        self.assertEqual(n, 1)
        boot.assert_not_awaited()

    async def test_a_first_run_reads_nothing(self):
        n, alerts, boot, store = await self.count({1: _row(1, hours_ago=0)}, first_run=True)
        self.assertEqual(n, 0)
        for mock in (alerts, boot, store):
            mock.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
