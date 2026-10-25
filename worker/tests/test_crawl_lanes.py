"""A hung source must not stop the crawl loop (incident 2026-10-21: one
Facebook run hung for an hour and no new search got its first crawl)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from collectors._isolated import TERMINATE_GRACE_SECONDS, IsolatedCrash, call as isolated_call, isolated
from collectors._loop import CollectorTimeout, run_collector
from pipeline import crawl


def _target(id: int, source: str, first_run_done: bool = True, next_run_at: int | None = None,
            count_only: bool = False) -> dict:
    return {"id": id, "source": source, "first_run_done": first_run_done, "next_run_at": next_run_at,
            "query": {"count_only": True} if count_only else {}}


def _claim_order(t: dict) -> tuple:
    """targets.claim_next's ORDER BY: never ran, due targets that notify, then
    first-run retries and count-only targets, each by next_run_at."""
    notifies = t["first_run_done"] and t["query"].get("count_only") is not True
    return (t["next_run_at"] is not None, not notifies, t["next_run_at"] or 0, t["id"])


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
            mine = sorted((t for t in unclaimed() if t["source"] == source), key=_claim_order)
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

    async def test_due_targets_that_notify_go_before_retries_and_count_only(self):
        """Sentra waited ~140 minutes behind Facebook bootstraps (2026-10-22)."""
        self.hung = set()
        self.due = [_target(1, "kavak", next_run_at=5), _target(2, "kavak", first_run_done=False),
                    _target(3, "kavak", first_run_done=False, next_run_at=1),       # a bootstrap retry
                    _target(4, "kavak", next_run_at=2, count_only=True), _target(5, "kavak", next_run_at=7)]
        await self.lanes.start_due(jitter_seconds=0)
        await self.settle()
        self.assertEqual(self.ran, [2, 1, 5, 3, 4])

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

        items = await run_collector(isolated_call(Echo(), "search", {"q": "Ford Ka", "date_skips": ["7"]},
                                                  timeout=60))
        self.assertEqual([i.titulo for i in items], ["Ford Ka"])
        self.assertFalse(items.complete)
        self.assertEqual(items.reason, "scroll cap")
        self.assertEqual((items.date_skips, items.probe), (["7"], {"cards": 1}))   # the date memory too

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


class SourceBreakerTests(unittest.IsolatedAsyncioTestCase):
    """A source that blocks us is paused instead of failing target by target."""

    async def asyncSetUp(self):
        from pipeline import breaker

        breaker.clear()
        self.addCleanup(breaker.clear)
        self.due = [_target(1, "facebook"), _target(2, "facebook"), _target(3, "kavak")]
        self.ran: list[int] = []

        async def due_targets():
            return list(self.due)

        async def claim_next(source, worker, lease_seconds):
            mine = [t for t in self.due if t["source"] == source]
            if not mine:
                return None
            self.due.remove(mine[0])
            return mine[0]

        async def run_one(target, on_batch, on_health=None):
            self.ran.append(target["id"])
            if target["source"] == "facebook":
                breaker.pause("facebook", "facebook: session expired")
                raise crawl.SourceBlocked("facebook")

        for p in (patch.object(crawl.targets_repo, "due_targets", due_targets),
                  patch.object(crawl.targets_repo, "claim_next", claim_next),
                  patch.object(crawl, "_run_one", run_one),
                  patch.dict(crawl.REGISTRY, {s: object for s in ("facebook", "kavak")}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    async def test_a_blocked_source_stops_after_one_target_and_is_not_restarted(self):
        lanes = crawl.Lanes()
        self.addAsyncCleanup(lanes.close)
        self.assertEqual(await lanes.start_due(jitter_seconds=0), ["facebook", "kavak"])
        for _ in range(10):
            await asyncio.sleep(0)
        self.assertEqual(sorted(self.ran), [1, 3])           # target 2 never tried
        self.assertEqual(await lanes.start_due(jitter_seconds=0), [])

    async def test_the_pause_ends(self):
        from pipeline import breaker

        breaker.pause("facebook", "blocked", seconds=0.05)
        self.assertTrue(breaker.paused("facebook"))
        await asyncio.sleep(0.06)
        self.assertFalse(breaker.paused("facebook"))

    async def test_crawl_due_goes_on_with_the_other_sources(self):
        self.assertEqual(await crawl.crawl_due(jitter_seconds=0), 2)
        self.assertEqual(sorted(self.ran), [1, 3])


class BlockedRunTargetTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_blocked_collector_is_recorded_then_pauses_its_source(self):
        from unittest.mock import AsyncMock, MagicMock
        from collectors.base import CollectorBlocked
        from pipeline import breaker

        breaker.clear()
        self.addCleanup(breaker.clear)
        scraper = MagicMock(search=AsyncMock(side_effect=CollectorBlocked("facebook: session expired")))
        target = {"id": 1, "source": "facebook", "make": "Ford", "model": "Ka", "first_run_done": True,
                  "crawl_interval_seconds": 3600}

        async def on_collector(coroutine, timeout=None):
            return await coroutine

        with patch.dict(crawl.REGISTRY, {"facebook": lambda: scraper}), \
                patch.object(crawl.runs, "start_run", AsyncMock(return_value=1)), \
                patch.object(crawl.runs, "finish_run", AsyncMock()) as finish, \
                patch.object(crawl.targets_repo, "publication_dates", AsyncMock(return_value={})), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish_target, \
                patch.object(crawl, "run_collector", on_collector):
            with self.assertRaises(crawl.SourceBlocked):
                await crawl.run_target(target)
        finish.assert_awaited_once()
        finish_target.assert_awaited_once()
        self.assertTrue(breaker.paused("facebook"))


class EnrichBreakerTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_paused_source_is_skipped_and_its_pages_stay_unchecked(self):
        from unittest.mock import AsyncMock
        from pipeline import breaker, enrich

        breaker.clear()
        self.addCleanup(breaker.clear)
        seen: list[int] = []

        async def refresh(row):
            seen.append(row["id"])
            breaker.pause("facebook", "blocked")
            return enrich.IngestResult()

        rows = [{"id": i, "source": "facebook"} for i in (1, 2, 3)]
        with patch.dict(enrich.REGISTRY, {"facebook": object}):
            await enrich.drain(rows, refresh, intervals={"facebook": 0})
        self.assertEqual(seen, [1])

        mark = AsyncMock()
        with patch.dict(enrich.REGISTRY, {"facebook": object}), \
                patch.object(enrich.repo, "mark_detail_checked", mark):
            await enrich.refresh_listing({"id": 9, "source": "facebook", "url": "u"}, stage="enrich")
        mark.assert_not_awaited()


class CrawlLoopLivenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_heartbeat_waits_for_a_stuck_loop(self):
        import time
        from unittest.mock import AsyncMock
        import main
        from pipeline import scheduler

        beat = AsyncMock()
        with patch.object(main.heartbeat, "beat", beat):
            with patch.object(scheduler, "_last_round", time.monotonic()):
                await main.beat_while_crawling(None)
            beat.assert_awaited_once()
            with patch.object(scheduler, "_last_round", time.monotonic() - 10_000):
                await main.beat_while_crawling(None)
            beat.assert_awaited_once()


class DrainErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_target_that_raised_frees_its_claim(self):
        from unittest.mock import AsyncMock

        queue = [_target(1, "kavak")]

        async def claim_next(source, worker, lease_seconds):
            return queue.pop(0) if queue else None

        finish = AsyncMock()
        with patch.object(crawl.targets_repo, "claim_next", claim_next), \
                patch.object(crawl.targets_repo, "finish_target", finish), \
                patch.object(crawl, "_run_one", AsyncMock(side_effect=RuntimeError("db"))), \
                patch.object(crawl.runs, "log_error", AsyncMock()):
            self.assertEqual(await crawl._drain("kavak", None, 0, None), 1)
        finish.assert_awaited_once()
        self.assertFalse(finish.await_args.kwargs["ok"])
