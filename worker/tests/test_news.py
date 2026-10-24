"""Which new listings are not news on the sources without publication dates
(pipeline/news.py). Pure: the repos are mocks. The PostgreSQL flow is in
test_ingest_postgres.py (StepTests, ReappearanceTests)."""
from __future__ import annotations

import unittest
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

from collectors import REGISTRY
from collectors.base import Listing, SearchResults
from pipeline import crawl, news, scheduler
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


class ReadEnvelopeTests(unittest.TestCase):
    def test_a_target_by_model_keeps_the_year_and_km_sent_to_its_collector(self):
        target = dict(TARGET, query={"year_min": 2015, "km_max": 100_000, "profile_ids": [1]})
        self.assertEqual(news.read_envelope(target, crawl.scraper_filters(target)),
                         {"year_min": 2015, "km_max": 100_000})
        unbounded = dict(TARGET, query={"profile_ids": [1]})
        self.assertEqual(news.read_envelope(unbounded, crawl.scraper_filters(unbounded)), {})

    def test_sources_by_publication_date_body_types_and_inventories_keep_none(self):
        filters = {"anio_min": 2015, "km_max": 100_000}
        for target in (dict(TARGET, source="mercadolibre"), dict(TARGET, source="facebook"),
                       dict(TARGET, source="kavak", make=None, model=None, body_type="suv"),
                       dict(TARGET, source="autocity", make=None, model=None, query={"inventory": True})):
            self.assertIsNone(news.read_envelope(target, filters), target)

    def test_a_target_reading_a_whole_stock_keeps_what_its_collector_was_sent_apart(self):
        # kavak 'suv' 2010-2014 reads 2009-2015 with the band: its collector drops
        # a 2016 card before the prefilter, which never remembers it.
        suv = dict(TARGET, source="kavak", make=None, model=None, body_type="suv",
                   query={"year_min": 2010, "year_max": 2014, "year_band": 1, "price_usd_max": 20_000})
        self.assertEqual(news.read_covers(suv, crawl.scraper_filters(suv)), {"year_min": 2009, "year_max": 2015})
        inventory = dict(TARGET, source="autocity", make=None, model=None, query={"inventory": True})
        self.assertEqual(news.read_covers(inventory, crawl.scraper_filters(inventory)), {})
        for target in (TARGET, dict(suv, source="mercadolibre")):
            self.assertIsNone(news.read_covers(target, {"anio_min": 2009, "anio_max": 2015}), target)


class BandTests(unittest.TestCase):
    """The reference year band (pipeline/crawl.py): Ka 2010 reads 2009 too."""
    QUERY = {"year_min": 2010, "year_max": 2020, "year_band": 1, "profile_ids": [1]}
    KAVAK = {"id": 7, "source": "kavak", "make": "Ford", "model": "Ka", "query": QUERY}

    def test_a_year_past_the_searches_own_is_the_band_s(self):
        self.assertTrue(news.is_band({"year": 2009}, self.QUERY))
        self.assertTrue(news.is_band({"year": 2021}, self.QUERY))
        for year in (2010, 2015, 2020, None):
            self.assertFalse(news.is_band({"year": year}, self.QUERY), year)

    def test_without_a_band_or_a_bound_nothing_is(self):
        self.assertFalse(news.is_band({"year": 2009}, {"year_min": 2010}))
        self.assertFalse(news.is_band({"year": 2009}, None))
        self.assertFalse(news.is_band({"year": 2030}, {"year_min": 2010, "year_band": 1}))   # no year_max
        self.assertTrue(news.is_band({"year": 2009}, {"year_min": "2010", "year_band": 1}))

    def test_band_ids_are_the_band_s_rows_of_a_source_without_a_window(self):
        rows = [row(1, year=2009), row(2, year=2010), row(3, year=None), row(4, year=2021)]
        with patch.object(news.config, "NEWS_GUARD_BAND", True):
            self.assertEqual(news.band_ids(self.KAVAK, rows, max_age_days=15), frozenset({1, 4}))
            # Mercado Libre reads the band only in "Publicados hoy": real news.
            self.assertEqual(news.band_ids(dict(self.KAVAK, source="mercadolibre"), rows, max_age_days=15),
                             frozenset())
            self.assertEqual(news.band_ids(dict(self.KAVAK, query={"year_min": 2010}), rows, max_age_days=15),
                             frozenset())
            # v6 dates its listings: one published yesterday is news, band or not.
            dated = [row(1, year=2009, published_at=NOW - timedelta(days=1)),
                     row(2, year=2009, published_at=NOW - timedelta(days=40))]
            self.assertEqual(news.band_ids(dict(self.KAVAK, source="v6"), dated, max_age_days=15), frozenset({2}))
        with patch.object(news.config, "NEWS_GUARD_BAND", False):
            self.assertEqual(news.band_ids(self.KAVAK, rows, max_age_days=15), frozenset())

    def test_the_read_envelope_includes_the_band(self):
        # What the collector is sent: a widening by the band's year is no envelope.
        self.assertEqual(news.read_envelope(self.KAVAK, crawl.scraper_filters(self.KAVAK)),
                         {"year_min": 2009, "year_max": 2021})

    def test_the_core_share_of_a_read_leaves_the_band_out(self):
        items = [Listing("kavak", str(i), "Ford Ka", "https://example.test", anio=year)
                 for i, year in enumerate((2009, 2009, 2012, 2015, None))]
        self.assertEqual(news._core_share(items, self.QUERY), 0.6)
        self.assertEqual(news._core_share(items, {"year_min": 2010}), 1.0)
        self.assertEqual(news._core_share([], self.QUERY), 1.0)

    def test_the_band_s_first_read_is_what_the_last_read_did_not_cover(self):
        rows = [row(1, year=2009), row(2, year=2021)]
        before = dict(self.KAVAK, query=dict(self.QUERY, _read={"year_min": 2010, "year_max": 2020}))
        self.assertEqual(news.first_band_read(before, rows), frozenset({1, 2}))
        read = dict(self.KAVAK, query=dict(self.QUERY, _read={"year_min": 2009, "year_max": 2021}))
        self.assertEqual(news.first_band_read(read, rows), frozenset())
        # A search moved its year_min down a year: its new band year is unread.
        self.assertEqual(news.first_band_read(read, [row(3, year=2008)]), frozenset({3}))
        # deruedas drops a top bound past this year: the read had no ceiling.
        open_top = dict(self.KAVAK, query=dict(self.QUERY, _read={"year_min": 2009}))
        self.assertEqual(news.first_band_read(open_top, rows), frozenset())
        # Without a last read (a body type, or none complete yet) nothing was covered.
        self.assertEqual(news.first_band_read(self.KAVAK, rows), frozenset({1, 2}))

    def test_the_step_base_is_scaled_only_once_a_read_had_the_band(self):
        self.assertFalse(news._band_read_before(dict(self.QUERY, _read={"year_min": 2010, "year_max": 2020})))
        self.assertTrue(news._band_read_before(dict(self.QUERY, _read={"year_min": 2009, "year_max": 2021})))
        self.assertTrue(news._band_read_before(dict(self.QUERY, _read={"year_min": 2009})))
        self.assertFalse(news._band_read_before(self.QUERY))
        self.assertFalse(news._band_read_before({"year_min": 2010, "_read": {"year_min": 2009}}))


class MarkTests(unittest.TestCase):
    def marked(self, reason: str, target_id: int = 7) -> dict:
        return {"attributes": {"_not_news": {"reason": reason, "run_id": 1, "target_id": target_id, "prev_id": None}}}

    def test_old_stock_is_muted_and_never_counted(self):
        for reason in ("step", "reappearance", "envelope"):
            self.assertTrue(news.muted(self.marked(reason)), reason)
            self.assertTrue(news.uncounted(self.marked(reason, target_id=9), 7), reason)

    def test_a_first_run_or_band_mark_is_only_its_own_target_s(self):
        # Another target that wants it (a body type next to a model on Kavak) still gets it.
        for reason in ("first_run", "band"):
            mark = self.marked(reason)
            self.assertFalse(news.muted(mark), reason)
            self.assertTrue(news.uncounted(mark, 7), reason)
            self.assertFalse(news.uncounted(mark, 9), reason)

    def test_rows_without_a_mark(self):
        for r in (None, {}, {"attributes": None}, {"attributes": {"_not_news": "x"}}):
            self.assertFalse(news.muted(r) or news.uncounted(r, 7) or news.republished(r))
        self.assertTrue(news.republished({"attributes": {"_republished": {"prev_id": 3}}}))


class ClassifyTests(unittest.IsolatedAsyncioTestCase):
    @contextmanager
    def patched(self, rows: list[dict] | Exception, *, prev_found=None, reappeared=None, left=(),
                trusted=("autocosmos",), empty_streak=0, wide=(), **switches):
        """news.py over mocks: `rows` its new rows, `left` what an earlier run
        left unclassified, `trusted` app_config.comparables.confirm_sources,
        `wide` the source's other bootstrapped targets (targets.covering_targets)."""
        @asynccontextmanager
        async def connection():
            yield object()

        async def get_config(key, default=None):
            return {"recommended_max_age_days": 15, "comparables": {"confirm_sources": list(trusted)}}.get(key, default)

        flags = {"NEWS_GUARD_STEP": True, "NEWS_GUARD_REAPPEARANCE": True, "NEWS_GUARD_ENVELOPE": True,
                 "NEWS_GUARD_BAND": True, "NEWS_LINK_REPOST": False, **switches}
        self.found = AsyncMock(side_effect=lambda cx, r, **kw: (reappeared or {}).get(r["id"]))
        self.marks = AsyncMock()
        self.recent = AsyncMock(return_value=prev_found)
        self.streak = AsyncMock(return_value=empty_streak)
        self.log_error = AsyncMock()
        self.unclassified = AsyncMock(return_value=list(left))
        self.wide = AsyncMock(return_value=list(wide))
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
                patch.object(news.listings, "mark_not_news", self.marks), \
                patch.object(news.targets, "covering_targets", self.wide):
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

    async def test_a_widened_search_brings_what_the_last_read_left_out_as_envelope(self):
        # kavak Fiesta 05/10: read with year >= 2015 and km <= 100.000, then a
        # search widened it to 2014 and 150.000 km.
        target = dict(TARGET, query={"year_min": 2014, "km_max": 150_000, "profile_ids": [1, 2],
                                     "_read": {"year_min": 2015, "km_max": 100_000}})
        rows = [row(1, year=2014, mileage_km=60_000), row(2, year=2016, mileage_km=139_000),
                row(3, year=2017, mileage_km=80_000), row(4, year=None, mileage_km=None)]
        muted = await self.classify(result(1, 2, 3, 4), rows, target=target, prev_found=40)
        self.assertEqual(muted, frozenset({1, 2}))
        self.assertEqual(self.marked(), {lid: {"_not_news": {"reason": "envelope", "run_id": 40, "target_id": 7,
                                                             "prev_id": None}} for lid in (1, 2)})
        self.assertEqual(self.found.await_count, 2)            # 3 and 4 still go through the reappearance

    async def test_what_a_target_reading_its_whole_body_type_covers_is_news(self):
        # kavak 'suv' reads every SUV on each run: an EcoSport 2013 it covers and
        # never stored is new to kavak, though the EcoSport target read 2016 on.
        # What it covers is what its last read sent the collector, which drops
        # the rest before its prefilter: 2010-2015, though its searches want 2005-2022 now.
        suv = {"id": 3, "source": "kavak", "make": None, "model": None, "body_type": "suv",
               "query": {"price_usd_max": 15_000, "year_min": 2005, "year_max": 2022,
                         "_covers": {"year_min": 2010, "year_max": 2015}},
               "prefilter_rejected": ["n4"]}
        target = dict(TARGET, source="kavak", query={"year_min": 2008, "year_max": 2022,
                                                     "_read": {"year_min": 2016, "year_max": 2018}})
        rows = [row(1, year=2013, body_type="suv", price_usd=9_000.0),     # covered
                row(2, year=2013, body_type="sedan", price_usd=9_000.0),   # another body type
                row(3, year=2013, body_type="suv", price_usd=20_000.0),    # above its cap, not dropped: listed since
                row(4, year=2013, body_type="suv", price_usd=9_000.0),     # its prefilter dropped it before
                row(5, year=2008, body_type="suv", price_usd=9_000.0),     # below what it read
                row(6, year=2020, body_type="suv", price_usd=9_000.0)]     # past what it read (kavak's year_max)
        muted = await self.classify(result(1, 2, 3, 4, 5, 6), rows, target=target, wide=[suv], trusted=())
        self.assertEqual(muted, frozenset({2, 4, 5, 6}))
        self.wide.assert_awaited_once_with("kavak", exclude=7)
        # Not read since it keeps what it covered: it vouches for nothing.
        unread = dict(suv, query={k: v for k, v in suv["query"].items() if k != "_covers"})
        self.assertEqual(await self.classify(result(1), rows, target=target, wide=[unread], trusted=()),
                         frozenset({1}))
        # A target of the whole source covers everything.
        inventory = {"id": 4, "source": "kavak", "make": None, "model": None, "body_type": None,
                     "query": {"inventory": True, "_covers": {}}, "prefilter_rejected": []}
        self.assertEqual(await self.classify(result(2, 6), rows, target=target, wide=[inventory], trusted=()),
                         frozenset())

    async def test_a_sibling_model_target_covers_what_it_reads_in_its_searches_years(self):
        # deruedas walks Sandero cards for a Stepway: 'Stepway 2018-2020'
        # widened to 2022 stores a Sandero 2022 before 'Sandero 2019-2022' reads it.
        sandero = {"id": 5, "source": "deruedas", "make": "Renault", "model": "Sandero", "body_type": None,
                   "query": {"year_min": 2019, "year_max": 2022, "km_max": 100_000,
                             "_read": {"year_min": 2019, "year_max": 2022}}, "prefilter_rejected": []}
        target = dict(TARGET, source="deruedas", make="Renault", model="Stepway",
                      query={"year_min": 2018, "year_max": 2022, "_read": {"year_min": 2018, "year_max": 2020}})

        def renault(lid: int, model: str, year: int, **kw) -> dict:
            return row(lid, source="deruedas", make="Renault", model=model, year=year, **kw)
        rows = [renault(1, "Sandero", 2022, mileage_km=10_000),             # the Sandero target reads it
                renault(2, "SANDERO", 2022),
                renault(3, "Sandero", 2022, mileage_km=150_000),            # past its km
                renault(4, "Logan", 2022),                                  # another model
                renault(5, "Stepway", 2022)]                                # the target's own
        muted = await self.classify(result(1, 2, 3, 4, 5), rows, target=target, wide=[sandero], trusted=())
        self.assertEqual(muted, frozenset({3, 4, 5}))
        # Its search just widened to 2022: it never read that year.
        widened = dict(sandero, query=dict(sandero["query"], _read={"year_min": 2019, "year_max": 2021}))
        self.assertEqual(await self.classify(result(1), rows, target=target, wide=[widened], trusted=()),
                         frozenset({1}))
        # No last read kept: its searches may have widened since, so it vouches for nothing.
        bare = dict(sandero, query={"year_min": 2019, "year_max": 2022})
        self.assertEqual(await self.classify(result(1, 3), rows, target=target, wide=[bare], trusted=()),
                         frozenset({1, 3}))

    async def test_a_recent_publication_outside_the_last_read_is_news(self):
        target = dict(TARGET, query={"year_min": 2014, "_read": {"year_min": 2015}})
        rows = [row(1, year=2014, published_at=NOW - timedelta(days=1)),
                row(2, year=2014, published_at=NOW - timedelta(days=40))]
        self.assertEqual(await self.classify(result(1, 2), rows, target=target), frozenset({2}))

    async def test_without_a_last_read_or_with_the_switch_off_nothing_is_envelope(self):
        rows = [row(1, year=2010, mileage_km=300_000)]
        for query in ({"year_min": 2014}, {"year_min": 2014, "_read": {}}, {"year_min": 2014, "_read": [2015]}):
            self.assertEqual(await self.classify(result(1), rows, target=dict(TARGET, query=query)), frozenset(),
                             query)
            self.log_error.assert_not_awaited()
        target = dict(TARGET, query={"year_min": 2014, "_read": {"year_min": 2015}})
        self.assertEqual(await self.classify(result(1), rows, target=target, NEWS_GUARD_ENVELOPE=False),
                         frozenset())

    async def test_a_first_run_ignores_the_last_read(self):
        # A target that starts over (a reactivation, a coverage bump) marks it all 'first_run'.
        target = dict(TARGET, query={"year_min": 2014, "_read": {"year_min": 2015}})
        muted = await self.classify(result(1), [row(1, year=2014)], target=target, first_run=True)
        self.assertEqual(muted, frozenset())
        self.assertEqual(self.marked()[1]["_not_news"]["reason"], "first_run")

    async def test_run_target_keeps_what_a_complete_read_sent(self):
        class Kavak:
            complete = True

            async def search(self, filters):
                filters["anio_min"] = 1990             # what the collector does with the dict doesn't count
                return SearchResults([item("n1")], complete=self.complete)

        target = dict(TARGET, source="kavak", query={"year_min": 2015, "km_max": 100_000,
                                                     "_read": {"year_min": 2016}},
                      body_type=None, prefilter_rejected=[], last_run_at=None)
        for complete, read in ((True, {"year_min": 2015, "km_max": 100_000}), (False, None)):
            Kavak.complete = complete
            with self.patched([], trusted=()), self.kavak(Kavak, IngestResult(found=1)):
                run = await crawl.run_target(target)
            self.assertEqual((run.read_envelope, run.read_covers), (read, None), complete)
        # A target by body type keeps it apart, for the others (news._covered).
        suv = dict(target, make=None, model=None, body_type="suv", query={"year_min": 2010, "year_max": 2014})
        for complete, covers in ((True, {"year_min": 2010, "year_max": 2014}), (False, None)):
            Kavak.complete = complete
            with self.patched([], trusted=()), self.kavak(Kavak, IngestResult(found=1)):
                run = await crawl.run_target(suv)
            self.assertEqual((run.read_envelope, run.read_covers), (None, covers), complete)

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

    BANDED = {"year_min": 2010, "year_band": 1, "profile_ids": [1]}
    # The band's first read: the last read had the searches' exact years.
    BEFORE = dict(TARGET, query=dict(BANDED, _read={"year_min": 2010}))
    # A later read: the last one already had the band.
    AFTER = dict(TARGET, query=dict(BANDED, _read={"year_min": 2009}))

    async def test_the_band_s_first_read_is_old_stock_for_its_target_and_makes_no_step(self):
        # Turned on, the band brings Fox 2009 at once: 5 of them, next to 2 real ones.
        rows = [row(i, year=2009) for i in range(1, 6)] + [row(6, year=2012), row(7, year=2011)]
        muted = await self.classify(result(*range(1, 8)), rows, target=self.BEFORE, prev_found=10)
        self.assertEqual(muted, frozenset(range(1, 6)))
        self.assertEqual({lid: m["_not_news"]["reason"] for lid, m in self.marked().items()},
                         {i: "band" for i in range(1, 6)})
        self.new_rows.assert_awaited_once()
        # Read again later, five 2009s next to two real ones are old stock back
        # at once (a search without a model would get them): a step of the
        # band's rows alone, the two of the searches' years still news.
        self.assertEqual(await self.classify(result(*range(1, 8)), rows, target=self.AFTER, prev_found=10),
                         frozenset(range(1, 6)))
        self.assertEqual({lid: m["_not_news"]["reason"] for lid, m in self.marked().items()},
                         {i: "step" for i in range(1, 6)})
        self.recent.assert_awaited_once()
        # A new 2009 is a car just listed: no mark.
        self.assertEqual(await self.classify(result(1, 6, 7), rows, target=self.AFTER, prev_found=10),
                         frozenset())
        self.assertEqual(self.marked(), {})
        # Switched off they are news, and they make the step they are.
        self.assertEqual(await self.classify(result(*range(1, 8)), rows, target=self.BEFORE, prev_found=10,
                                             NEWS_GUARD_BAND=False), frozenset(range(1, 8)))

    async def test_the_band_s_first_read_that_a_whole_stock_target_covers_is_news(self):
        # A bootstrapped target reading every SUV from 2005 would have stored an old Fox 2009 SUV.
        suv = {"id": 3, "source": "autocosmos", "body_type": "suv",
               "query": {"year_min": 2005, "_covers": {"year_min": 2005}}, "prefilter_rejected": []}
        rows = [row(1, year=2009, body_type="suv"), row(2, year=2009, body_type="hatchback")]
        muted = await self.classify(result(1, 2), rows, target=self.BEFORE, wide=[suv], prev_found=40)
        self.assertEqual(muted, frozenset({2}))
        self.assertEqual({lid: m["_not_news"]["reason"] for lid, m in self.marked().items()}, {2: "band"})

    async def test_a_step_is_measured_against_the_core_once_a_read_had_the_band(self):
        # Eight new cars of the searches' years on a read that is a fifth band:
        # the last reads' 20 were 16 inside, and eight is half of that.
        items = ([Listing("autocosmos", f"n{i}", "Volkswagen Fox", "https://example.test", anio=2012)
                  for i in range(1, 9)]
                 + [Listing("autocosmos", f"b{i}", "Volkswagen Fox", "https://example.test", anio=2009)
                    for i in range(2)])
        rows = [row(i, year=2012) for i in range(1, 9)]
        muted = await self.classify(result(*range(1, 9)), rows, target=self.AFTER, items=items, prev_found=20)
        self.assertEqual(muted, frozenset(range(1, 9)))
        # Right after it is turned on the last reads' 20 were all core: no step.
        self.assertEqual(await self.classify(result(*range(1, 9)), rows, target=self.BEFORE, items=items,
                                             prev_found=20), frozenset())
        self.assertEqual(await self.classify(result(*range(1, 9)), rows, target=self.AFTER, items=items,
                                             prev_found=20, NEWS_GUARD_BAND=False), frozenset())

    async def test_the_band_read_before_back_at_once_is_a_step_of_its_own(self):
        # autocosmos Fox: a read cut short, then the whole one brings 4 old
        # Fox of the searches' years and 12 of the band's, which the last
        # complete read covered. 4 make no step of the target's own news,
        # but the 16 are one against the 2 of the last reads.
        rows = [row(i, year=2012) for i in range(1, 5)] + [row(i, year=2009) for i in range(5, 17)]
        muted = await self.classify(result(*range(1, 17)), rows, target=self.AFTER, prev_found=2)
        self.assertEqual(muted, frozenset(range(5, 17)))
        self.assertEqual({m["_not_news"]["reason"] for m in self.marked().values()}, {"step"})
        # Measured against the whole `found`, band included: 6 new cars on a
        # read half band are a step of its core's 10, not of the 20 it found.
        items = [Listing("autocosmos", f"i{i}", "Volkswagen Fox", "https://example.test", anio=2012 - 3 * (i % 2))
                 for i in range(10)]
        rows = [row(1, year=2012), row(2, year=2012)] + [row(i, year=2009) for i in range(3, 7)]
        self.assertEqual(await self.classify(result(*range(1, 7)), rows, target=self.AFTER, items=items,
                                             prev_found=20), frozenset())
        # A target that never loaded (an empty first read's hold ended, its
        # empty reads leaving the band in _read): 3 of its years and 10 of the band's.
        rows = [row(i, year=2012) for i in range(1, 4)] + [row(i, year=2009) for i in range(4, 14)]
        self.assertEqual(await self.classify(result(*range(1, 14)), rows, target=self.AFTER, empty_streak=3),
                         frozenset(range(4, 14)))
        # The band's first read is no part of it: 'band' already, and
        # measured against a base that never had it.
        self.assertEqual(await self.classify(result(*range(1, 14)), rows, target=self.BEFORE, empty_streak=3),
                         frozenset(range(4, 14)))
        self.assertEqual({m["_not_news"]["reason"] for m in self.marked().values()}, {"band"})
        # Nor a first read that a target reading the whole stock covers, which
        # stays news: a search moved its year_min down to 2010, the top
        # band year (2015) read before.
        suv = {"id": 3, "source": "autocosmos", "body_type": "suv",
               "query": {"year_min": 2005, "_covers": {"year_min": 2005}}, "prefilter_rejected": []}
        moved = dict(TARGET, query={"year_min": 2010, "year_max": 2014, "year_band": 1, "profile_ids": [1],
                                    "_read": {"year_min": 2010, "year_max": 2015}})
        rows = ([row(1, year=2012), row(2, year=2012), row(3, year=2015)]
                + [row(i, year=2009, body_type="suv") for i in range(4, 9)])
        self.assertEqual(await self.classify(result(*range(1, 9)), rows, target=moved, wide=[suv], prev_found=6),
                         frozenset())
        self.assertEqual(self.marked(), {})

    async def test_a_first_run_marks_everything_first_run(self):
        muted = await self.classify(result(1, 2), [row(1, year=2009), row(2, year=2015)], target=self.BEFORE,
                                    first_run=True)
        self.assertEqual(muted, frozenset())
        self.assertEqual({lid: m["_not_news"]["reason"] for lid, m in self.marked().items()},
                         {1: "first_run", 2: "first_run"})
        self.recent.assert_not_awaited()


class SyncTargetsTests(unittest.IsolatedAsyncioTestCase):
    """crawl.sync_targets and scheduler.tick: what targets.sync_targets is told."""

    async def sync(self, counting=(), **switches) -> AsyncMock:
        with patch.object(crawl.targets_repo, "enabled_sources", AsyncMock(return_value={})), \
                patch.object(crawl, "body_type_targets", AsyncMock(return_value=crawl.BodyTypeTargets())), \
                patch.object(crawl.targets_repo, "sync_targets", AsyncMock()) as sync, \
                patch.multiple(crawl.config, **{"NEWS_GUARD_REACTIVATION": True, **switches}):
            await crawl.sync_targets([], counting)
        return sync

    async def test_the_reactivation_reset_has_its_switch(self):
        self.assertEqual(set((await self.sync()).call_args.kwargs["undated"]), news.UNDATED_SOURCES)
        self.assertEqual(tuple((await self.sync(NEWS_GUARD_REACTIVATION=False)).call_args.kwargs["undated"]), ())

    async def test_count_only_targets_stay_when_the_counted_searches_cant_be_read(self):
        self.assertFalse((await self.sync([])).call_args.kwargs["keep_count_only"])
        self.assertTrue((await self.sync(None)).call_args.kwargs["keep_count_only"])

    async def test_a_tick_that_cant_read_the_counted_searches_says_so(self):
        # A timeout in count_after_expiry_searches() would deactivate every
        # count-only target for a tick.
        with patch.object(scheduler.db, "enabled_profiles", AsyncMock(return_value=[])), \
                patch.object(scheduler.db, "counting_profiles", AsyncMock(side_effect=RuntimeError("timeout"))), \
                patch.object(scheduler, "log_error", AsyncMock()) as log_error, \
                patch.object(scheduler.crawl, "sync_targets", AsyncMock()) as sync, \
                patch.object(scheduler.rematch, "run_pending", AsyncMock()):
            await scheduler.tick(MagicMock(), MagicMock(start_due=AsyncMock(return_value=[])))
        sync.assert_awaited_once_with([], None)
        self.assertEqual(log_error.await_args.args[:2], ("count_after_expiry", "counting_profiles"))


class ListingEventsTests(unittest.IsolatedAsyncioTestCase):
    """scheduler.process_batch: whom a batch's price drops reach."""

    async def events_of(self, *, first_run: bool, last_run_at: datetime | None) -> AsyncMock:
        notifier = MagicMock(on_matches=AsyncMock(), on_listing_events=AsyncMock(), deliver=AsyncMock())
        scorer = MagicMock(rows={}, prepare=AsyncMock())
        with patch.object(scheduler.Scorer, "create", AsyncMock(return_value=scorer)), \
                patch.object(scheduler.db, "get_config", AsyncMock(return_value=15)), \
                patch.object(scheduler.db, "alerts_for_target", AsyncMock(return_value=[])), \
                patch.object(scheduler, "count_after_expiry", AsyncMock()):
            await scheduler.process_batch(notifier, dict(TARGET, last_run_at=last_run_at), [1], first_run=first_run,
                                          events=["drop"])
        return notifier.on_listing_events

    async def test_a_reset_first_run_tells_its_price_drops_only_to_the_matches_before_it(self):
        # kavak Fiesta back after two months: a search created during the
        # pause, or matched by this very batch, never had the old price.
        before = NOW - timedelta(days=60)
        (await self.events_of(first_run=True, last_run_at=before)).assert_awaited_once_with(
            ["drop"], matched_before=before)
        (await self.events_of(first_run=False, last_run_at=before)).assert_awaited_once_with(["drop"])
        (await self.events_of(first_run=True, last_run_at=None)).assert_not_awaited()


class RunOneTests(unittest.IsolatedAsyncioTestCase):
    """crawl._run_one: the empty first read and the retry of a partial one."""

    async def run_one(self, target: dict, *, found: int = 0, first_run: bool = True, complete: bool = True,
                      reason: str | None = None, empty_runs: int = 0, read: dict | None = None,
                      covers: dict | None = None, rejected: frozenset[str] | None = None,
                      on_batch: AsyncMock | None = None) -> AsyncMock:
        items = SearchResults([], complete=complete, reason=reason)
        batch = crawl.TargetRun(target, items, IngestResult(found=found), first_run=first_run, complete=complete,
                                empty_runs=empty_runs, read_envelope=read, read_covers=covers, rejected=rejected)
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.runs, "log_error", AsyncMock()), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], on_batch, 0, None)
        return finish

    async def test_an_empty_first_read_does_not_finish_the_bootstrap(self):
        finish = await self.run_one(dict(TARGET, source="kavak", first_run_done=False))
        finish.assert_awaited_once_with(7, ok=True, retry_seconds=0, covered_until=None, bootstrap=False,
                                       read=None, covers=None, rejected=None, full_read=True)
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

    async def test_a_complete_read_leaves_what_it_covered_in_the_query(self):
        finish = await self.run_one(TARGET, found=3, first_run=False, read={"year_min": 2015})
        self.assertEqual((finish.call_args.kwargs["ok"], finish.call_args.kwargs["read"]), (True, {"year_min": 2015}))
        finish = await self.run_one(TARGET, found=3, first_run=False, covers={})
        self.assertEqual((finish.call_args.kwargs["read"], finish.call_args.kwargs["covers"]), (None, {}))

    async def test_what_the_prefilter_dropped_is_written_with_what_the_read_covered(self):
        # One UPDATE, so news._covered never pairs a _covers with another read's drops.
        suv = dict(TARGET, source="kavak", make=None, model=None, body_type="suv")
        kept = ("ok", "covers", "rejected")
        finish = await self.run_one(suv, found=3, first_run=False, covers={"year_min": 2009},
                                    rejected=frozenset({"r"}))
        self.assertEqual({k: finish.call_args.kwargs[k] for k in kept},
                         {"ok": True, "covers": {"year_min": 2009}, "rejected": frozenset({"r"})})
        # A partial read keeps no _covers, but what it dropped joins the last ones (run_target).
        finish = await self.run_one(suv, found=3, first_run=False, complete=False, rejected=frozenset({"r"}))
        self.assertEqual({k: finish.call_args.kwargs[k] for k in kept},
                         {"ok": False, "covers": None, "rejected": frozenset({"r"})})
        # Its batch failed: neither.
        finish = await self.run_one(suv, found=3, first_run=False, covers={"year_min": 2012},
                                    rejected=frozenset(), on_batch=AsyncMock(side_effect=RuntimeError("boom")))
        finish.assert_awaited_once_with(7, ok=False, retry_seconds=900)

    def test_retry_seconds(self):
        self.assertEqual(crawl.retry_seconds(TARGET), 900)                                 # a failure
        self.assertEqual(crawl.retry_seconds(TARGET, partial=True), 3600)
        self.assertEqual(crawl.retry_seconds(dict(TARGET, source="facebook"), partial=True), 900)
        self.assertEqual(crawl.retry_seconds(dict(TARGET, query={"count_only": True}), partial=True), 6 * 3600)


if __name__ == "__main__":
    unittest.main()
