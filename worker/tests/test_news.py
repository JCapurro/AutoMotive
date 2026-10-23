"""Which new listings are not news on the sources without publication dates
(pipeline/news.py). Pure: the repos are mocks. The PostgreSQL flow is in
test_ingest_postgres.py (StepTests, ReappearanceTests)."""
from __future__ import annotations

import unittest
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, patch

from collectors import REGISTRY
from collectors.base import Listing, SearchResults
from pipeline import crawl, news
from pipeline.ingest import IngestConfig, IngestResult, ListingEvent

NOW = datetime.now(timezone.utc)
TARGET = {"id": 7, "source": "autocosmos", "make": "Volkswagen", "model": "Fox", "query": {"profile_ids": [1]},
          "first_run_done": True, "crawl_interval_seconds": 3600}


def result(*ids: int, updated: tuple[int, ...] = ()) -> IngestResult:
    out = IngestResult(found=len(ids) + len(updated))
    out.events = ([ListingEvent("listing_new", i, "autocosmos", f"n{i}") for i in ids]
                  + [ListingEvent("listing_updated", i, "autocosmos", f"u{i}") for i in updated])
    return out


def row(lid: int, **kw) -> dict:
    return {"id": lid, "source": "autocosmos", "external_id": f"n{lid}", "published_at": None,
            "price": 10_000.0, "currency": "USD", "price_usd": 10_000.0, **kw}


def item(listing_id: str) -> Listing:
    return Listing("autocosmos", listing_id, "Volkswagen Fox", f"https://example.test/{listing_id}")


class IsStepTests(unittest.TestCase):
    def test_old_stock_read_at_once_is_a_step(self):
        self.assertTrue(news.is_step(14, 2))           # autocosmos Fox 03/10: 2 → 16
        self.assertTrue(news.is_step(15, 9))           # kavak Fiesta 05/10: 9 → 24
        self.assertTrue(news.is_step(18, 24))          # autocosmos Gol Trend 29/09: 24 → 42 (a deploy)

    def test_a_day_of_news_is_not(self):
        self.assertFalse(news.is_step(20, 181))        # rosariogarage Gol, the largest normal day
        self.assertFalse(news.is_step(4, 0))           # under 5 new listings
        self.assertFalse(news.is_step(30, None))       # no ok run to compare with


class OutsideEnvelopeTests(unittest.TestCase):
    ENVELOPE = {"year_min": 2015, "year_max": None, "km_max": 100_000}

    def test_kavak_fiesta_widened_brings_stock_outside(self):
        self.assertTrue(news.outside_envelope({"year": 2014, "mileage_km": 60_000}, self.ENVELOPE))
        self.assertTrue(news.outside_envelope({"year": 2016, "mileage_km": 139_000}, self.ENVELOPE))
        self.assertFalse(news.outside_envelope({"year": 2017, "mileage_km": 80_000}, self.ENVELOPE))

    def test_no_bound_and_unknown_values_are_inside(self):
        self.assertFalse(news.outside_envelope({"year": 2030, "mileage_km": 1}, self.ENVELOPE))   # year_max None
        self.assertFalse(news.outside_envelope({"year": None, "mileage_km": None}, self.ENVELOPE))
        self.assertFalse(news.outside_envelope({"year": 1990, "mileage_km": 900_000}, None))


class MarkTests(unittest.TestCase):
    def marked(self, reason: str, target_id: int = 7) -> dict:
        return {"attributes": {"_not_news": {"reason": reason, "run_id": 1, "target_id": target_id, "prev_id": None}}}

    def test_old_stock_is_muted_and_never_counted(self):
        for reason in ("step", "reappearance", "envelope", "band"):
            self.assertTrue(news.muted(self.marked(reason)), reason)
            self.assertTrue(news.uncounted(self.marked(reason, target_id=9), 7), reason)

    def test_a_first_run_mark_is_backfill_only_for_its_own_target_in_2_5(self):
        mark = self.marked("first_run")
        self.assertFalse(news.muted(mark))
        self.assertTrue(news.uncounted(mark, 7))
        self.assertFalse(news.uncounted(mark, 9))

    def test_rows_without_a_mark(self):
        for r in (None, {}, {"attributes": None}, {"attributes": {"_not_news": "x"}}):
            self.assertFalse(news.muted(r) or news.uncounted(r, 7) or news.republished(r))
        self.assertTrue(news.republished({"attributes": {"_republished": {"prev_id": 3}}}))


class ClassifyTests(unittest.IsolatedAsyncioTestCase):
    @contextmanager
    def patched(self, rows: list[dict] | Exception, *, prev_found=None, reappeared=None, left=(),
                trusted=("autocosmos",), empty_streak=0, **switches):
        """news.py over mocks: `rows` its new rows, `left` what an earlier run
        left unclassified, `trusted` app_config.comparables.confirm_sources."""
        @asynccontextmanager
        async def connection():
            yield object()

        async def get_config(key, default=None):
            return {"recommended_max_age_days": 15, "comparables": {"confirm_sources": list(trusted)}}.get(key, default)

        flags = {"NEWS_GUARD_STEP": True, "NEWS_GUARD_REAPPEARANCE": True, "NEWS_LINK_REPOST": False, **switches}
        self.found = AsyncMock(side_effect=lambda cx, r, **kw: (reappeared or {}).get(r["id"]))
        self.marks = AsyncMock()
        self.recent = AsyncMock(return_value=prev_found)
        self.streak = AsyncMock(return_value=empty_streak)
        self.log_error = AsyncMock()
        self.unclassified = AsyncMock(return_value=list(left))
        if isinstance(rows, Exception):
            self.new_rows = AsyncMock(side_effect=rows)
        else:
            self.new_rows = AsyncMock(side_effect=lambda cx, ids: [r for r in rows if r["id"] in set(ids)])
        with patch.object(news, "connection", connection), \
                patch.multiple(news.config, **flags), \
                patch.object(news, "get_config", get_config), \
                patch.object(news.IngestConfig, "load", AsyncMock(return_value=IngestConfig())), \
                patch.object(news.runs, "recent_ok_found", self.recent), \
                patch.object(news.runs, "empty_ok_streak", self.streak), \
                patch.object(news.runs, "log_error", self.log_error), \
                patch.object(news.listings, "unclassified", self.unclassified), \
                patch.object(news.listings, "new_rows", self.new_rows), \
                patch.object(news.listings, "find_reappeared", self.found), \
                patch.object(news.listings, "mark_not_news", self.marks):
            yield

    async def classify(self, res: IngestResult, rows: list[dict] | Exception, *, target=TARGET, items=(),
                       first_run=False, complete=True, readmitted=(), **patched):
        with self.patched(rows, **patched):
            return await news.classify(target, list(items), res, run_id=40, first_run=first_run, complete=complete,
                                       readmitted=readmitted)

    @contextmanager
    def kavak(self, scraper: type, res: IngestResult):
        """crawl.run_target on `scraper` as kavak, its ingest giving `res`."""
        with patch.dict(REGISTRY, {"kavak": scraper}, clear=True), \
                patch.object(crawl.runs, "start_run", AsyncMock(return_value=1)), \
                patch.object(crawl.runs, "finish_run", AsyncMock(return_value=None)), \
                patch.object(crawl.targets_repo, "set_prefilter_rejected", AsyncMock()), \
                patch.object(crawl, "ingest", AsyncMock(return_value=res)):
            yield

    def marked(self) -> dict[int, dict]:
        return {lid: attrs for call in self.marks.await_args_list for lid, attrs, _ in call.args[1]}

    async def test_a_step_is_backfill_for_every_new_listing(self):
        ids = range(1, 15)
        muted = await self.classify(result(*ids, updated=(90, 91)), [row(i) for i in ids], prev_found=2)
        self.assertEqual(muted, frozenset(ids))
        self.recent.assert_awaited_once_with(7, exclude_run=40, n=3)
        self.assertEqual(self.marked()[1], {"_not_news": {"reason": "step", "run_id": 40, "target_id": 7,
                                                          "prev_id": None}})
        self.found.assert_not_awaited()

    async def test_a_target_that_never_loaded_measures_steps_against_0(self):
        # Its hold ended after empty reads (autocosmos answering 403 as "0 results"):
        # its whole stock showing up is a step, a few cars are news.
        ids = range(1, 13)
        self.assertEqual(await self.classify(result(*ids), [row(i) for i in ids], empty_streak=3), frozenset(ids))
        self.streak.assert_awaited_once_with(7, exclude_run=40)
        self.assertEqual(await self.classify(result(1, 2, 3, 4), [row(i) for i in range(1, 5)], empty_streak=3),
                         frozenset())
        # Without any ok run there is nothing to measure against.
        self.assertEqual(await self.classify(result(*ids), [row(i) for i in ids]), frozenset())

    async def test_a_recent_publication_date_is_always_news(self):
        # v6 dates its listings: a real one inside a step goes through.
        rows = [row(i) for i in range(1, 6)] + [row(6, published_at=NOW - timedelta(days=1)),
                                               row(7, published_at=NOW - timedelta(days=40))]
        muted = await self.classify(result(*range(1, 8)), rows, prev_found=10)
        self.assertEqual(muted, frozenset({1, 2, 3, 4, 5, 7}))

    async def test_an_inventory_target_or_the_switch_off_has_no_step(self):
        inventory = dict(TARGET, make=None, model=None, query={"inventory": True})
        self.assertEqual(await self.classify(result(*range(1, 15)), [row(i) for i in range(1, 15)],
                                             target=inventory, prev_found=2), frozenset())
        self.recent.assert_not_awaited()
        self.assertEqual(await self.classify(result(*range(1, 15)), [row(i) for i in range(1, 15)],
                                             prev_found=2, NEWS_GUARD_STEP=False), frozenset())

    async def test_a_reappearance_is_backfill_with_its_old_copy(self):
        old = {"id": 3, "price": 10_100.0, "currency": "USD", "price_usd": 10_100.0}
        muted = await self.classify(result(8, 9), [row(8), row(9)], items=[item("n8"), item("n9"), item("o5")],
                                    prev_found=40, reappeared={8: old})
        self.assertEqual(muted, frozenset({8}))
        self.assertEqual(self.found.await_args.kwargs, {"batch_external_ids": ["n8", "n9", "o5"],
                                                        "window_days": 60, "price_tol_pct": 10.0, "km_tol": 100,
                                                        "unsellered_hours": 72})
        self.assertEqual(self.marked()[8]["_not_news"]["prev_id"], 3)
        # Without E3, probable_repost_of stays as ingest left it.
        self.assertIsNone(self.marks.await_args.args[1][0][2])

    async def test_with_link_repost_the_reappearance_points_to_the_copy_before(self):
        # Not the chain's first copy: comparables() would count every later one
        # once that first copy stops counting.
        old = {"id": 3, "price": 10_000.0, "currency": "USD", "price_usd": 10_000.0}
        await self.classify(result(8), [row(8)], reappeared={8: old}, NEWS_LINK_REPOST=True)
        self.assertEqual(self.marks.await_args.args[1][0][2], 3)

    async def test_a_republication_3_pct_cheaper_is_news_labelled_republished(self):
        old = {"id": 3, "price": 10_400.0, "currency": "USD", "price_usd": 10_400.0}
        muted = await self.classify(result(8), [row(8)], reappeared={8: old})
        self.assertEqual(muted, frozenset())
        self.assertEqual(self.marked()[8], {"_republished": {"run_id": 40, "target_id": 7, "prev_id": 3,
                                                             "drop_pct": 3.85}})

    async def test_an_incomplete_read_never_infers_a_vanished_copy(self):
        old = {"id": 3, "price": 10_000.0, "currency": "USD", "price_usd": 10_000.0}
        self.assertEqual(await self.classify(result(8), [row(8)], reappeared={8: old}, complete=False), frozenset())
        self.found.assert_not_awaited()
        self.assertEqual(await self.classify(result(8), [row(8)], reappeared={8: old},
                                             NEWS_GUARD_REAPPEARANCE=False), frozenset())

    async def test_a_source_whose_reads_are_cut_short_never_infers_a_vanished_copy(self):
        # kavak, autocosmos, usadossantafe: not in app_config.comparables.confirm_sources.
        old = {"id": 3, "price": 10_000.0, "currency": "USD", "price_usd": 10_000.0}
        self.assertEqual(await self.classify(result(8), [row(8)], reappeared={8: old}, trusted=("rosariogarage",)),
                         frozenset())
        self.found.assert_not_awaited()
        self.assertEqual(await self.classify(result(8), [row(8)], reappeared={8: old}, trusted=()), frozenset())

    async def test_the_listings_the_prefilter_readmits_neither_step_nor_get_marked(self):
        # A wider kavak SUV search lets 12 dropped cars in, next to 2 new ones: not a step.
        rows = [row(i) for i in range(1, 15)]
        muted = await self.classify(result(*range(1, 15)), rows, readmitted=range(1, 13), prev_found=20)
        self.assertEqual(muted, frozenset())
        self.assertEqual(self.new_rows.await_args.args[1], [13, 14])
        self.marks.assert_awaited_once_with(ANY, [])

    async def test_run_target_leaves_the_prefilter_s_readmissions_out_of_the_step(self):
        class Kavak:
            BODY_TYPES = frozenset({"suv"})

            async def search(self, filters):
                return [item(f"r{i}") for i in range(12)] + [item("n1"), item("n2")]

        target = {"id": 9, "source": "kavak", "make": None, "model": None, "body_type": "suv",
                  "query": {"year_min": 2015}, "first_run_done": True, "last_run_at": None,
                  "prefilter_rejected": [f"r{i}" for i in range(12)]}
        res = IngestResult(found=14, new=14)
        res.events = ([ListingEvent("listing_new", 100 + i, "kavak", f"r{i}") for i in range(12)]
                      + [ListingEvent("listing_new", 201, "kavak", "n1"), ListingEvent("listing_new", 202, "kavak", "n2")])
        res.ids = {("kavak", e.external_id): e.listing_id for e in res.events}
        rows = [row(lid, source="kavak") for lid in (*range(100, 112), 201, 202)]
        with self.patched(rows, prev_found=20, trusted=()), self.kavak(Kavak, res):
            run = await crawl.run_target(target)
        # 14 new on 20 would be a step; the 12 readmitted are backfill already.
        self.assertEqual(run.backfill_ids, frozenset(range(100, 112)))
        self.assertEqual(self.new_rows.await_args.args[1], [201, 202])
        self.assertEqual(self.marked(), {})

    async def test_what_a_cut_run_readmitted_stays_out_of_the_next_run_s_step(self):
        # Run N readmitted r0..r11 and stored n1, n2, then a restart cut it before
        # prefilter_rejected was updated; run N+1 stores n3: three new cars, no step.
        class Kavak:
            BODY_TYPES = frozenset({"suv"})

            async def search(self, filters):
                return [item(f"r{i}") for i in range(12)] + [item("n1"), item("n2"), item("n3")]

        target = {"id": 9, "source": "kavak", "make": None, "model": None, "body_type": "suv",
                  "query": {"year_min": 2015}, "first_run_done": True, "last_run_at": NOW - timedelta(hours=1),
                  "prefilter_rejected": [f"r{i}" for i in range(12)]}
        res = IngestResult(found=15, new=1, updated=14)
        res.events = [ListingEvent("listing_new", 203, "kavak", "n3")]
        res.ids = {**{("kavak", f"r{i}"): 100 + i for i in range(12)},
                   ("kavak", "n1"): 201, ("kavak", "n2"): 202, ("kavak", "n3"): 203}
        rows = [row(lid, source="kavak") for lid in (*range(100, 112), 201, 202, 203)]
        with self.patched(rows, prev_found=20, trusted=(), left=[*range(100, 112), 201, 202]), \
                self.kavak(Kavak, res):
            run = await crawl.run_target(target)
        self.assertEqual(self.new_rows.await_args.args[1], [203, 201, 202])
        self.assertEqual(self.marked(), {})
        # Old stock for every search of this batch too.
        self.assertEqual(run.backfill_ids, frozenset(range(100, 112)))

    async def test_what_a_cut_run_left_unclassified_joins_this_run(self):
        # A restart between an ingest and its marks: the next run classifies them.
        res = result(9, updated=tuple(range(1, 6)))
        res.ids = {("autocosmos", f"x{i}"): i for i in (*range(1, 6), 9)}
        muted = await self.classify(res, [row(i) for i in (1, 2, 3, 4, 5, 9)], left=[1, 2, 3, 4], prev_found=8)
        self.assertEqual(muted, frozenset({1, 2, 3, 4, 9}))          # 5 new: a step on 8
        self.assertEqual(sorted(self.unclassified.await_args.args[1]), [1, 2, 3, 4, 5, 9])
        self.assertEqual(self.unclassified.await_args.kwargs, {"target_id": 7, "run_id": 40})

    async def test_a_run_with_nothing_new_or_left_reads_no_rows(self):
        res = result(updated=(1, 2))
        res.ids = {("autocosmos", "u1"): 1, ("autocosmos", "u2"): 2}
        self.assertEqual(await self.classify(res, [row(1), row(2)]), frozenset())
        self.unclassified.assert_awaited_once()
        self.new_rows.assert_not_awaited()

    async def test_a_first_run_is_marked_for_2_5_and_left_to_the_bootstrap(self):
        muted = await self.classify(result(1, 2), [], first_run=True, prev_found=0)
        self.assertEqual(muted, frozenset())
        self.assertEqual({lid: m["_not_news"]["reason"] for lid, m in self.marked().items()},
                         {1: "first_run", 2: "first_run"})
        self.recent.assert_not_awaited()

    async def test_mercadolibre_and_facebook_are_untouched(self):
        for source in ("mercadolibre", "facebook"):
            muted = await self.classify(result(*range(1, 15)), [row(i) for i in range(1, 15)],
                                        target=dict(TARGET, source=source), prev_found=2)
            self.assertEqual(muted, frozenset())
        self.marks.assert_not_awaited()

    async def test_it_fails_open(self):
        muted = await self.classify(result(1, 2, 3, 4, 5), RuntimeError("db"), prev_found=2)
        self.assertEqual(muted, frozenset())
        self.assertEqual(self.log_error.await_args.args[:2], ("news", "target:7"))
        self.assertIn("RuntimeError: db", self.log_error.await_args.args[2])
        self.marks.assert_not_awaited()


class RunOneTests(unittest.IsolatedAsyncioTestCase):
    """crawl._run_one: the empty first read and the retry of a partial one."""

    async def run_one(self, target: dict, *, found: int = 0, first_run: bool = True, complete: bool = True,
                      reason: str | None = None, empty_runs: int = 0) -> AsyncMock:
        items = SearchResults([], complete=complete, reason=reason)
        batch = crawl.TargetRun(target, items, IngestResult(found=found), first_run=first_run, complete=complete,
                                empty_runs=empty_runs)
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], None, 0, None)
        return finish

    async def test_an_empty_first_read_does_not_finish_the_bootstrap(self):
        finish = await self.run_one(dict(TARGET, source="kavak", first_run_done=False))
        finish.assert_awaited_once_with(7, ok=True, retry_seconds=0, covered_until=None, bootstrap=False)
        finish = await self.run_one(dict(TARGET, source="kavak", first_run_done=False), found=4)
        self.assertTrue(finish.call_args.kwargs["bootstrap"])

    async def test_the_third_empty_read_in_a_row_finishes_the_bootstrap(self):
        # A narrow search with nothing listed: its first car is news.
        for empty_runs, bootstrap in ((1, False), (2, True), (5, True)):
            finish = await self.run_one(dict(TARGET, source="kavak", first_run_done=False), empty_runs=empty_runs)
            self.assertEqual(finish.call_args.kwargs["bootstrap"], bootstrap, empty_runs)

    async def test_a_dated_source_or_the_switch_off_bootstraps_on_an_empty_read(self):
        for source in ("mercadolibre", "v6", "mardelusados", "usadossantafe", "onlycarsusados"):
            finish = await self.run_one(dict(TARGET, source=source, first_run_done=False))
            self.assertTrue(finish.call_args.kwargs["bootstrap"], source)
        with patch.object(crawl.config, "NEWS_GUARD_EMPTY_FIRST", False):
            finish = await self.run_one(dict(TARGET, source="kavak", first_run_done=False))
        self.assertTrue(finish.call_args.kwargs["bootstrap"])

    async def test_an_incomplete_later_run_waits_the_source_interval(self):
        finish = await self.run_one(TARGET, found=3, first_run=False, complete=False, reason="partial: page 2")
        self.assertEqual((finish.call_args.kwargs["ok"], finish.call_args.kwargs["retry_seconds"]), (False, 3600))
        with patch.object(crawl.config, "NEWS_PARTIAL_RETRY", False):
            finish = await self.run_one(TARGET, found=3, first_run=False, complete=False)
        self.assertEqual(finish.call_args.kwargs["retry_seconds"], 900)

    async def test_an_incomplete_first_run_retries_soon(self):
        finish = await self.run_one(dict(TARGET, first_run_done=False), found=3, complete=False)
        self.assertEqual(finish.call_args.kwargs["retry_seconds"], 900)

    def test_retry_seconds(self):
        self.assertEqual(crawl.retry_seconds(TARGET), 900)                                 # a failure
        self.assertEqual(crawl.retry_seconds(TARGET, partial=True), 3600)
        self.assertEqual(crawl.retry_seconds(dict(TARGET, source="facebook"), partial=True), 900)
        self.assertEqual(crawl.retry_seconds(dict(TARGET, query={"count_only": True}), partial=True), 6 * 3600)


if __name__ == "__main__":
    unittest.main()
