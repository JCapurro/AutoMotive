"""A hung source must not stop the crawl loop (incident 2026-10-21: one
Facebook run hung for an hour and no new search got its first crawl)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from collectors._loop import CollectorTimeout, run_collector
from pipeline import crawl


def _target(id: int, source: str, first_run_done: bool = True) -> dict:
    return {"id": id, "source": source, "first_run_done": first_run_done}


class RunCollectorTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_hung_collector_is_cancelled(self):
        cancelled = asyncio.Event()

        async def hang():
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        with self.assertRaises(CollectorTimeout):
            await run_collector(hang(), timeout=0.05)
        self.assertTrue(cancelled.is_set())

    async def test_a_collector_in_time_returns_its_result(self):
        async def quick():
            return [1, 2]

        self.assertEqual(await run_collector(quick(), timeout=5), [1, 2])

    async def test_its_own_errors_go_through(self):
        async def broken():
            raise ValueError("parse")

        with self.assertRaises(ValueError):
            await run_collector(broken(), timeout=5)


class LanesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.due: list[dict] = []
        self.ran: list[int] = []
        self.release = asyncio.Event()
        self.hung = {"facebook"}

        async def due_targets():
            return list(self.due)

        async def run_target(target, on_health=None):
            if target["source"] in self.hung:
                await self.release.wait()
            self.ran.append(target["id"])
            return None

        registry = {s: object for s in ("facebook", "kavak", "v6")}
        for p in (patch.object(crawl.targets_repo, "due_targets", due_targets),
                  patch.object(crawl, "run_target", run_target),
                  patch.dict(crawl.REGISTRY, registry, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        self.lanes = crawl.Lanes()
        self.addAsyncCleanup(self.lanes.close)

    async def settle(self):
        for _ in range(5):
            await asyncio.sleep(0)

    async def test_a_hung_source_does_not_hold_up_the_others(self):
        self.due = [_target(1, "facebook"), _target(2, "kavak")]
        self.assertEqual(await self.lanes.start_due(jitter_seconds=0), 2)
        await self.settle()
        self.assertEqual(self.ran, [2])
        self.assertEqual(self.lanes.running(), {"facebook"})

        # A new search's targets, next tick: kavak starts, facebook is left alone.
        self.due = [_target(1, "facebook"), _target(3, "kavak", first_run_done=False)]
        self.assertEqual(await self.lanes.start_due(jitter_seconds=0), 1)
        await self.settle()
        self.assertEqual(self.ran, [2, 3])

        self.release.set()
        await self.settle()
        self.assertEqual(self.ran, [2, 3, 1])
        self.assertEqual(self.lanes.running(), set())

    async def test_first_runs_go_first_within_a_source(self):
        self.hung = set()
        self.due = [_target(1, "kavak"), _target(2, "kavak", first_run_done=False), _target(3, "kavak")]
        await self.lanes.start_due(jitter_seconds=0)
        await self.settle()
        self.assertEqual(self.ran, [2, 1, 3])

    async def test_sources_without_a_collector_are_skipped(self):
        self.due = [_target(1, "instagram")]
        self.assertEqual(await self.lanes.start_due(jitter_seconds=0), 0)

    async def test_close_cancels_running_lanes(self):
        self.due = [_target(1, "facebook")]
        await self.lanes.start_due(jitter_seconds=0)
        await self.settle()
        await self.lanes.close()
        self.assertEqual(self.lanes.running(), set())
        self.assertEqual(self.ran, [])


if __name__ == "__main__":
    unittest.main()
