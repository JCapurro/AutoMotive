"""A hung source must not stop the crawl loop (incident 2026-10-21: one
Facebook run hung for an hour and no new search got its first crawl)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from collectors._isolated import TERMINATE_GRACE_SECONDS, IsolatedCrash, call as isolated_call, isolated
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
    """targets.claim_next is faked by a queue: a target is handed out once."""

    async def asyncSetUp(self):
        self.due: list[dict] = []
        self.claimed: set[int] = set()
        self.ran: list[int] = []
        self.release = asyncio.Event()
        self.hung = {"facebook"}

        def unclaimed():
            return [t for t in self.due if t["id"] not in self.claimed]

        async def due_targets():
            return unclaimed()

        async def claim_next(source, worker, lease_seconds):
            mine = sorted((t for t in unclaimed() if t["source"] == source), key=lambda t: t["first_run_done"])
            if not mine:
                return None
            self.claimed.add(mine[0]["id"])
            return mine[0]

        async def run_one(target, on_batch, on_health=None):
            if target["source"] in self.hung:
                await self.release.wait()
            self.ran.append(target["id"])
            self.due.remove(target)         # finish_target: not due anymore

        registry = {s: object for s in ("facebook", "kavak", "v6")}
        for p in (patch.object(crawl.targets_repo, "due_targets", due_targets),
                  patch.object(crawl.targets_repo, "claim_next", claim_next),
                  patch.object(crawl, "_run_one", run_one),
                  patch.dict(crawl.REGISTRY, registry, clear=True)):
            p.start()
            self.addCleanup(p.stop)
        self.lanes = crawl.Lanes()
        self.addAsyncCleanup(self.lanes.close)

    async def settle(self):
        for _ in range(10):
            await asyncio.sleep(0)

    async def test_a_hung_source_does_not_hold_up_the_others(self):
        self.due = [_target(1, "facebook"), _target(2, "kavak")]
        self.assertEqual(await self.lanes.start_due(jitter_seconds=0), ["facebook", "kavak"])
        await self.settle()
        self.assertEqual(self.ran, [2])
        self.assertEqual(self.lanes.running(), {"facebook"})

        # A new search's targets, next tick: kavak starts, facebook is left alone.
        self.due += [_target(3, "kavak", first_run_done=False), _target(4, "facebook", first_run_done=False)]
        self.assertEqual(await self.lanes.start_due(jitter_seconds=0), ["kavak"])
        await self.settle()
        self.assertEqual(self.ran, [2, 3])

        # The facebook lane takes what came in meanwhile once its run ends.
        self.release.set()
        await self.settle()
        self.assertEqual(self.ran, [2, 3, 1, 4])
        self.assertEqual(self.lanes.running(), set())

    async def test_first_runs_go_first_within_a_source(self):
        self.hung = set()
        self.due = [_target(1, "kavak"), _target(2, "kavak", first_run_done=False), _target(3, "kavak")]
        await self.lanes.start_due(jitter_seconds=0)
        await self.settle()
        self.assertEqual(self.ran, [2, 1, 3])

    async def test_a_claimed_target_is_not_crawled_twice(self):
        self.due = [_target(1, "facebook")]
        await self.lanes.start_due(jitter_seconds=0)
        await self.settle()
        other = crawl.Lanes()                  # another worker
        self.addAsyncCleanup(other.close)
        self.assertEqual(await other.start_due(jitter_seconds=0), [])
        self.release.set()
        await self.settle()
        self.assertEqual(self.ran, [1])

    async def test_sources_without_a_collector_are_skipped(self):
        self.due = [_target(1, "instagram")]
        self.assertEqual(await self.lanes.start_due(jitter_seconds=0), [])

    async def test_close_cancels_running_lanes(self):
        self.due = [_target(1, "facebook")]
        await self.lanes.start_due(jitter_seconds=0)
        await self.settle()
        await self.lanes.close()
        self.assertEqual(self.lanes.running(), set())
        self.assertEqual(self.ran, [])


if __name__ == "__main__":
    unittest.main()


class IsolatedCollectorTests(unittest.IsolatedAsyncioTestCase):
    """Facebook and Instagram run in a child process (collectors/_isolated.py)."""

    def setUp(self):
        # The child imports the fakes by module name, as this process does.
        import os
        from pathlib import Path

        here = str(Path(__file__).resolve().parent)
        path = os.pathsep.join(p for p in (here, os.environ.get("PYTHONPATH")) if p)
        p = patch.dict(os.environ, {"PYTHONPATH": path})
        p.start()
        self.addCleanup(p.stop)

    async def test_results_come_back_with_their_attributes(self):
        from isolated_fakes import Echo

        items = await run_collector(isolated_call(Echo(), "search", {"q": "Ford Ka"}, timeout=60))
        self.assertEqual([i.titulo for i in items], ["Ford Ka"])
        self.assertFalse(items.complete)
        self.assertEqual(items.reason, "scroll cap")

    async def test_the_collectors_exception_is_raised_here(self):
        from collectors.base import CollectorBlocked
        from isolated_fakes import Blocked

        with self.assertRaisesRegex(CollectorBlocked, "session expired"):
            await run_collector(isolated_call(Blocked(), "search", {}, timeout=60))

    async def test_a_hung_child_is_killed(self):
        import os
        import tempfile
        import time
        from isolated_fakes import Hang

        fd, pidfile = tempfile.mkstemp()
        os.close(fd)
        self.addCleanup(os.unlink, pidfile)
        started = time.monotonic()
        with self.assertRaises(CollectorTimeout):
            await run_collector(isolated_call(Hang(), "search", {"pidfile": pidfile}, timeout=8))
        self.assertLess(time.monotonic() - started, 8 + 2 * TERMINATE_GRACE_SECONDS)
        pid = int(open(pidfile).read())
        if os.name != "nt":
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    async def test_a_child_that_dies_fails_the_run(self):
        from isolated_fakes import Crash

        with self.assertRaises(IsolatedCrash):
            await run_collector(isolated_call(Crash(), "search", {}, timeout=60))

    def test_only_flagged_collectors_are_isolated(self):
        from unittest.mock import MagicMock
        from collectors import REGISTRY

        self.assertTrue(isolated(REGISTRY["facebook"]()))
        self.assertFalse(isolated(REGISTRY["kavak"]()))
        self.assertFalse(isolated(MagicMock()))
