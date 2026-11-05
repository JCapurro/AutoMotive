"""Facebook's pace (2026-11-05): its session lasted less the harder it was read."""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import config
from pipeline import crawl, pacing


def _at(hour: int, minute: int = 0) -> float:
    return datetime(2026, 11, 5, hour, minute, tzinfo=ZoneInfo("America/Argentina/Buenos_Aires")).timestamp()


class ConfigTests(unittest.TestCase):
    def test_pairs_and_hours(self):
        self.assertEqual(config._per_source(" facebook=25, kavak = 10 ,bad, =3,x="), {"facebook": "25", "kavak": "10"})
        self.assertEqual(config._hours("1-7"), (1, 7))
        self.assertEqual(config._hours("22-6"), (22, 6))
        for bad in ("7", "a-b", "3-3", "25-2", "-1-4"):
            self.assertIsNone(config._hours(bad), bad)

    def test_facebook_is_paced_by_default(self):
        # tests/conftest.py turns the pace off for the other tests; the worker's defaults:
        self.assertEqual(config._per_source(config.DEFAULT_RUNS_PER_HOUR), {"facebook": "25"})
        self.assertEqual(config._hours(config._per_source(config.DEFAULT_QUIET_HOURS)["facebook"]), (1, 7))


class PacingTests(unittest.TestCase):
    def setUp(self):
        pacing.clear()
        for p in (patch.dict(pacing.SOURCE_RUNS_PER_HOUR, {"facebook": 25}, clear=True),
                  patch.dict(pacing.SOURCE_QUIET_HOURS, {"facebook": (1, 7)}, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(pacing.clear)

    def test_runs_are_spread_one_every_3600_over_n_seconds(self):
        now = _at(12)
        self.assertTrue(pacing.ready("facebook", now))
        pacing.mark("facebook", now)
        self.assertEqual(pacing.wait_seconds("facebook", now + 100), 44)
        self.assertFalse(pacing.ready("facebook", now + 143))
        self.assertTrue(pacing.ready("facebook", now + 144))

    def test_quiet_hours_are_local_and_end_exclusive(self):
        self.assertFalse(pacing.quiet("facebook", _at(0, 59)))
        for hour in range(1, 7):
            self.assertTrue(pacing.quiet("facebook", _at(hour, 30)), hour)
        self.assertFalse(pacing.quiet("facebook", _at(7)))

    def test_a_window_may_wrap_midnight(self):
        with patch.dict(pacing.SOURCE_QUIET_HOURS, {"facebook": (22, 6)}):
            self.assertTrue(pacing.quiet("facebook", _at(23)))
            self.assertTrue(pacing.quiet("facebook", _at(2)))
            self.assertFalse(pacing.quiet("facebook", _at(12)))

    def test_other_sources_are_untouched(self):
        pacing.mark("kavak", _at(12))
        self.assertTrue(pacing.ready("kavak", _at(3)))
        self.assertEqual(pacing.wait_seconds("kavak", _at(12)), 0)


class PacedLaneTests(unittest.IsolatedAsyncioTestCase):
    """A paced lane reads one target and ends; the next tick waits for its turn."""

    async def asyncSetUp(self):
        pacing.clear()
        self.clock = _at(12)
        self.due = [{"id": i, "source": "facebook", "first_run_done": True, "next_run_at": None, "query": {}}
                    for i in (1, 2, 3)]
        self.ran: list[int] = []

        async def due_targets():
            return list(self.due)

        async def claim_next(source, worker, lease_seconds):
            return self.due[0] if self.due else None

        async def run_one(target, on_batch, on_health=None):
            self.ran.append(target["id"])
            self.due.remove(target)

        for p in (patch.object(crawl.targets_repo, "due_targets", due_targets),
                  patch.object(crawl.targets_repo, "claim_next", claim_next),
                  patch.object(crawl, "_run_one", run_one),
                  patch.dict(crawl.REGISTRY, {"facebook": object}, clear=True),
                  patch.dict(pacing.SOURCE_RUNS_PER_HOUR, {"facebook": 25}, clear=True),
                  patch.dict(pacing.SOURCE_QUIET_HOURS, {"facebook": (1, 7)}, clear=True),
                  patch.object(pacing.time, "time", lambda: self.clock)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(pacing.clear)
        self.lanes = crawl.Lanes()
        self.addAsyncCleanup(self.lanes.close)

    async def tick(self) -> list[str]:
        started = await self.lanes.start_due(jitter_seconds=0)
        for _ in range(10):
            await asyncio.sleep(0)
        return started

    async def test_a_backlog_drains_one_target_per_turn(self):
        self.assertEqual(await self.tick(), ["facebook"])
        self.assertEqual(self.ran, [1])
        self.clock += 60
        self.assertEqual(await self.tick(), [])
        self.clock += 84
        self.assertEqual(await self.tick(), ["facebook"])
        self.assertEqual(self.ran, [1, 2])

    async def test_nothing_is_read_in_quiet_hours(self):
        self.clock = _at(3)
        self.assertEqual(await self.tick(), [])
        self.assertEqual(self.ran, [])
        self.clock = _at(7)
        self.assertEqual(await self.tick(), ["facebook"])
        self.assertEqual(self.ran, [1])


if __name__ == "__main__":
    unittest.main()
