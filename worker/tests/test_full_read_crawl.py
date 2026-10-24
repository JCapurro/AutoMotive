"""crawl.full_read (comparables fase 2): when a Mercado Libre target also
reads its whole stock, what it searches, and what it records."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from collectors.base import CollectorBlocked, SearchResults
from collectors.mercadolibre import FullRead
from pipeline import crawl
from pipeline.ingest import IngestResult

NOW = datetime.now(timezone.utc)
TARGET = {"id": 7, "source": "mercadolibre", "make": "Ford", "model": "Ka", "body_type": None,
          "query": {"year_min": 2010, "year_max": 2016, "year_band": 1, "km_max": 150_000,
                    "publication_policy": 1, "profile_ids": [1]},
          "first_run_done": True, "last_run_at": NOW, "last_full_read_at": None}


class FullReadCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        crawl._full_reads.clear()
        p = patch.multiple(crawl.config, FULL_READ=True, FULL_READ_HOURS=48, FULL_READ_SPACING_SECONDS=1800)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(crawl._full_reads.clear)


class DueTests(FullReadCase):
    def test_a_mercado_libre_target_that_never_read_its_stock(self):
        self.assertTrue(crawl.full_read_due(TARGET))

    def test_not_again_before_full_read_hours(self):
        self.assertFalse(crawl.full_read_due(dict(TARGET, last_full_read_at=NOW - timedelta(hours=47))))
        self.assertTrue(crawl.full_read_due(dict(TARGET, last_full_read_at=NOW - timedelta(hours=49))))

    def test_not_for_body_types_other_sources_or_with_the_switch_off(self):
        self.assertFalse(crawl.full_read_due(dict(TARGET, body_type="suv", make=None, model=None)))
        for source in ("facebook", "kavak", "deruedas"):
            with self.subTest(source=source):
                self.assertFalse(crawl.full_read_due(dict(TARGET, source=source)))
        with patch.object(crawl.config, "FULL_READ", False):
            self.assertFalse(crawl.full_read_due(TARGET))

    def test_one_per_source_every_full_read_spacing(self):
        crawl._full_reads["mercadolibre"] = crawl.time.monotonic() - 60
        self.assertFalse(crawl.full_read_due(TARGET))
        crawl._full_reads["mercadolibre"] = crawl.time.monotonic() - 1801
        self.assertTrue(crawl.full_read_due(TARGET))

    def test_it_searches_what_listing_unconfirmed_takes_it_to_cover(self):
        self.assertEqual(crawl.full_read_filters(TARGET),
                         {"marca": "Ford", "modelo": "Ka", "anio_min": 2009, "anio_max": 2017, "km_max": 150_000})
        self.assertEqual(crawl.full_read_filters(dict(TARGET, query={"count_only": True})),
                         {"marca": "Ford", "modelo": "Ka"})


class FullReadTests(FullReadCase):
    async def read(self, result, target=TARGET):
        scraper = MagicMock()
        scraper.return_value.full_read = AsyncMock(side_effect=[result])
        with patch.dict(crawl.REGISTRY, {"mercadolibre": scraper}), \
                patch.object(crawl, "full_read_due", return_value=True), \
                patch.object(crawl.targets_repo, "record_full_read", AsyncMock(return_value=3)) as record, \
                patch.object(crawl.runs, "log_error", AsyncMock()) as log_error, \
                patch.object(crawl.breaker, "pause") as pause:
            blocked = await crawl.full_read(target)
        return blocked, scraper.return_value.full_read, record, log_error, pause

    async def test_records_what_it_saw_and_whether_it_saw_it_all(self):
        for complete in (True, False):
            with self.subTest(complete=complete):
                blocked, search, record, _, _ = await self.read(FullRead({"a", "b"}, complete=complete))
                self.assertFalse(blocked)
                search.assert_awaited_once_with(crawl.full_read_filters(TARGET))
                (target, started, ids), kwargs = record.await_args
                self.assertEqual((target, ids, kwargs), (TARGET, {"a", "b"}, {"complete": complete}))
                self.assertLessEqual(started, datetime.now(timezone.utc))

    async def test_a_wall_pauses_the_source(self):
        blocked, _, record, _, pause = await self.read(CollectorBlocked("login required"))
        self.assertTrue(blocked)
        record.assert_not_awaited()
        pause.assert_called_once()

    async def test_a_failure_is_logged_and_the_run_goes_on(self):
        blocked, _, record, log_error, _ = await self.read(RuntimeError("boom"))
        self.assertFalse(blocked)
        record.assert_not_awaited()
        log_error.assert_awaited_once()

    async def test_not_due_reads_nothing(self):
        with patch.object(crawl, "full_read_due", return_value=False), \
                patch.object(crawl.targets_repo, "record_full_read", AsyncMock()) as record:
            self.assertFalse(await crawl.full_read(TARGET))
        record.assert_not_awaited()


class RunOneTests(FullReadCase):
    async def run_one(self, target, blocked=False):
        batch = crawl.TargetRun(target, SearchResults([]), IngestResult(found=1), first_run=False)
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl, "full_read", AsyncMock(return_value=blocked)) as full_read, \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target, dict(target, id=8)], None, 0, None)
        return full_read, finish

    async def test_runs_after_the_batch_and_finishes_the_target(self):
        full_read, finish = await self.run_one(TARGET)
        self.assertEqual(full_read.await_count, 2)
        self.assertEqual(finish.await_count, 2)
        self.assertFalse(finish.await_args.kwargs["full_read"])               # the window read is no evidence

    async def test_a_blocked_full_read_stops_the_lane_after_finishing_its_target(self):
        full_read, finish = await self.run_one(TARGET, blocked=True)
        full_read.assert_awaited_once()
        finish.assert_awaited_once()

    async def test_a_source_without_dates_says_its_read_was_full(self):
        _, finish = await self.run_one(dict(TARGET, source="deruedas"))
        self.assertTrue(finish.await_args.kwargs["full_read"])


if __name__ == "__main__":
    unittest.main()
