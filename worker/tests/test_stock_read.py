"""Primera lectura completa (docs/PLAN_PRIMERA_LECTURA_COMPLETA.md): Mercado
Libre's stock_read walk, and when crawl.stock_reads reads, what it reads and
what it keeps. Without a database or the network."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from collectors import mercadolibre as ml
from collectors.base import CollectorBlocked, Listing, SearchResults
from intelligence import near_zone, scoring
from pipeline import crawl, market_stats
from pipeline.ingest import IngestResult, ListingEvent

from test_mercadolibre_full_read import FILTERS, FakeSite, url

NOW = datetime.now(timezone.utc)
TARGET = {"id": 7, "source": "mercadolibre", "make": "Renault", "model": "Clio", "body_type": None,
          "query": {"year_min": 1995, "year_max": 2000, "year_band": 1, "publication_policy": 1,
                    "profile_ids": [1, 2]},
          "first_run_done": True, "last_run_at": NOW, "last_full_read_at": NOW - timedelta(hours=1)}
FULL = {"marca": "Renault", "modelo": "Clio", "anio_min": 1994, "anio_max": 2001}


def card(listing_id: str, *, published_at: int | None = None, **kw) -> Listing:
    return Listing("mercadolibre", listing_id, f"Renault Clio {listing_id}",
                   f"https://auto.mercadolibre.com.ar/{listing_id}", published_at=published_at, **kw)


class CardSite(FakeSite):
    """FakeSite whose pages carry km, to see the filters drop cards."""

    def results(self, html):
        return [Listing("mercadolibre", i, f"Ford Ka {i}", f"https://auto.mercadolibre.com.ar/{i}",
                        km=200_000 if i.startswith("far") else 50_000)
                for i in self.pages[html][0]]

    async def stock(self, filters=FILTERS) -> SearchResults:
        with patch.object(ml, "_get", self.get), patch.object(ml, "_results", self.results), \
                patch.object(ml, "search_state", self.state), patch.object(ml, "_page_pause", AsyncMock()), \
                patch.object(ml, "PAGE_SIZE", 3):
            return await ml.MercadoLibreScraper().stock_read(filters)


class MercadoLibreStockReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_keeps_the_cards_and_every_id_of_one_walk(self):
        site = CardSite({url(): (["a", "b", "far1"], 2), url(page=2): (["d"], 2)})
        read = await site.stock()
        self.assertIsInstance(read, SearchResults)
        self.assertEqual([c.listing_id for c in read], ["a", "b", "d"])      # km 200.000 > 150.000
        self.assertEqual(read.listed, {"a", "b", "far1", "d"})               # what record_full_read gets
        self.assertEqual((read.complete, read.pages), (True, 2))
        self.assertEqual(site.asked, [url(), url(page=2)])                    # the pages once

    async def test_a_year_at_a_time_keeps_each_card_once(self):
        site = CardSite({url(): (["a", "b", "c"], ml.MAX_PAGE_COUNT),
                         url(anio_min=2010, anio_max=2010): (["a", "e"], 1),
                         url(anio_min=2011, anio_max=2011): (["b", "c", "f"], 2),
                         url(anio_min=2011, anio_max=2011, page=2): (["g"], 2),
                         url(anio_min=2012, anio_max=2012): ([], None)})
        read = await site.stock()
        self.assertEqual(sorted(c.listing_id for c in read), ["a", "b", "c", "e", "f", "g"])
        self.assertTrue(read.complete)

    async def test_partial_like_full_read(self):
        site = CardSite({url(): (["a", "b", "c"], 2), url(page=2): RuntimeError("HTTP 500")})
        read = await site.stock()
        self.assertEqual(([c.listing_id for c in read], read.complete), (["a", "b", "c"], False))
        self.assertIn("HTTP 500", read.reason)

    async def test_a_wall_raises(self):
        site = CardSite({url(): CollectorBlocked("login required")})
        with self.assertRaises(CollectorBlocked):
            await site.stock()

    async def test_full_read_still_keeps_no_cards(self):
        read = await CardSite({url(): (["a"], 1)}).read()
        self.assertEqual((read.ids, read.cards), ({"a"}, []))


class Switch(unittest.TestCase):
    def setUp(self) -> None:
        p = patch.multiple(crawl.config, STOCK_READ=True, STOCK_READ_TARGETS=0)
        p.start()
        self.addCleanup(p.stop)


class SwitchTests(Switch):
    def test_only_targets_by_model_of_a_collector_that_can(self):
        self.assertTrue(crawl.stock_switched_on(TARGET))
        for name, target in (("body type", dict(TARGET, body_type="suv", make=None, model=None)),
                             ("count only", dict(TARGET, query={"count_only": True})),
                             ("inventory", dict(TARGET, source="v6", make=None, model=None,
                                                query={"inventory": True})),
                             ("no stock_read", dict(TARGET, source="deruedas"))):
            with self.subTest(name):
                self.assertFalse(crawl.stock_switched_on(target))
        with patch.object(crawl.config, "STOCK_READ", False):
            self.assertFalse(crawl.stock_switched_on(TARGET))


class MissingTests(Switch):
    def missing(self, **query):
        return crawl.stock_missing(dict(TARGET, query={**TARGET["query"], **query}), now=time.time())

    def test_never_read_reads_the_whole_range(self):
        self.assertEqual(self.missing(), [FULL])

    def test_covered_reads_nothing(self):
        self.assertEqual(self.missing(_stock={"year_min": 1994, "year_max": 2001, "at": 1}), [])
        self.assertEqual(self.missing(_stock={"year_min": 1980, "at": 1}), [])

    def test_wider_years_read_only_what_is_missing(self):
        # Search 558 widened Clio to 1990: only 1989-1993 (with the band) is read.
        cov = {"year_min": 1994, "year_max": 2001, "at": 1}
        self.assertEqual(self.missing(year_min=1990, _stock=cov), [dict(FULL, anio_min=1989, anio_max=1993)])
        self.assertEqual(self.missing(year_min=1990, year_max=2003, _stock=cov),
                         [dict(FULL, anio_min=1989, anio_max=1993), dict(FULL, anio_min=2002, anio_max=2004)])

    def test_a_search_without_a_year_bound_reads_the_open_side(self):
        cov = {"year_min": 1994, "year_max": 2001, "at": 1}
        target = dict(TARGET, query={k: v for k, v in TARGET["query"].items() if k != "year_min"} | {"_stock": cov})
        self.assertEqual(crawl.stock_missing(target), [{"marca": "Renault", "modelo": "Clio", "anio_max": 1993}])

    def test_a_wider_km_reads_the_whole_range_again(self):
        cov = {"year_min": 1994, "year_max": 2001, "km_max": 100_000, "at": 1}
        self.assertEqual(self.missing(km_max=150_000, _stock=cov), [dict(FULL, km_max=150_000)])
        self.assertEqual(self.missing(_stock=cov), [FULL])                    # no km cap now
        self.assertEqual(self.missing(km_max=80_000, _stock=cov), [])

    def test_a_partial_one_waits_before_trying_again(self):
        recent = int(time.time()) - 3600
        self.assertEqual(self.missing(_stock_tried=recent), [])
        old = int(time.time()) - (crawl.STOCK_RETRY_HOURS + 1) * 3600
        self.assertEqual(self.missing(_stock_tried=old), [FULL])

    def test_coverage_after_the_reads(self):
        target = dict(TARGET, query={**TARGET["query"], "year_min": 1990,
                                     "_stock": {"year_min": 1994, "year_max": 2001, "at": 1}})
        self.assertEqual(crawl.stock_coverage(target, [dict(FULL, anio_min=1989, anio_max=1993)], now=5),
                         {"year_min": 1989, "year_max": 2001, "at": 5})
        self.assertEqual(crawl.stock_coverage(TARGET, [FULL], now=5), {"year_min": 1994, "year_max": 2001, "at": 5})

    def test_fresh_cards_are_left_to_the_reads_by_date(self):
        since = NOW - timedelta(hours=25)
        marks = {2: 2_200_000_500}
        self.assertTrue(crawl._fresh(card("MLA2200000600"), marks, since))   # above the newest known
        self.assertFalse(crawl._fresh(card("MLA2200000400"), marks, since))
        self.assertFalse(crawl._fresh(card("MLA1100000400"), marks, since))  # an old series
        self.assertTrue(crawl._fresh(card("x", published_at=int(NOW.timestamp())), marks, since))
        self.assertFalse(crawl._fresh(card("MLA2200000900", published_at=int((NOW - timedelta(days=40)).timestamp())),
                                      marks, since))


def stock_result(items, *, listed=None, complete=True, reason=None):
    out = SearchResults(items, complete=complete, reason=reason)
    if listed is not None:
        out.listed, out.pages = listed, 3
    return out


class StockReadsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        crawl._full_reads.clear()
        p = patch.multiple(crawl.config, STOCK_READ=True, STOCK_READ_TARGETS=0, FULL_READ=True, FULL_READ_HOURS=48,
                           FULL_READ_SPACING_SECONDS=1800)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(crawl._full_reads.clear)

    async def reads(self, target=TARGET, outcomes=(), *, rank=0, scraper_cls=None, on_batch=None):
        scraper = scraper_cls or MagicMock(spec=["stock_read", "full_read"])
        if scraper_cls is None:
            scraper.return_value.stock_read = AsyncMock(side_effect=list(outcomes))
        result = IngestResult(found=2, new=1, ids={("mercadolibre", "MLA1"): 11, ("mercadolibre", "MLA2"): 12},
                              events=[ListingEvent("listing_new", 12, "mercadolibre", "MLA2")])
        run = crawl.TargetRun(target, SearchResults([]), IngestResult(), first_run=False)
        self.ingest = AsyncMock(return_value=result)
        with patch.dict(crawl.REGISTRY, {target["source"]: scraper}), \
                patch.object(crawl, "ingest", self.ingest), \
                patch.object(crawl.news, "mark_stock", AsyncMock(return_value=frozenset({12}))) as mark, \
                patch.object(crawl.targets_repo, "stock_rank", AsyncMock(return_value=rank)), \
                patch.object(crawl.targets_repo, "news_watermarks", AsyncMock(return_value={})), \
                patch.object(crawl.targets_repo, "record_full_read", AsyncMock(return_value=2)) as record, \
                patch.object(crawl.targets_repo, "set_stock", AsyncMock()) as set_stock, \
                patch.object(crawl, "full_read", AsyncMock(return_value=False)) as full_read, \
                patch.object(crawl.runs, "log_error", AsyncMock()) as log_error, \
                patch.object(crawl.breaker, "pause") as pause:
            blocked = await crawl.stock_reads(target, run, on_batch)
        return dict(blocked=blocked, scraper=scraper, mark=mark, record=record, set_stock=set_stock,
                    full_read=full_read, log_error=log_error, pause=pause)

    async def test_the_48_hour_read_stores_its_cards_in_the_same_walk(self):
        target = dict(TARGET, last_full_read_at=None)
        batches = []
        r = await self.reads(target, [stock_result([card("MLA1"), card("MLA2")], listed={"MLA1", "MLA2", "MLA3"})],
                             on_batch=AsyncMock(side_effect=batches.append))
        r["scraper"].return_value.stock_read.assert_awaited_once_with(crawl.full_read_filters(target))
        r["full_read"].assert_not_awaited()                                   # one walk, not two
        (_, _, listed), kwargs = r["record"].await_args
        self.assertEqual((listed, kwargs), ({"MLA1", "MLA2", "MLA3"}, {"complete": True}))
        r["mark"].assert_awaited_once()
        [batch] = batches
        self.assertTrue(batch.stock)
        self.assertEqual(batch.backfill_ids, frozenset({11, 12}))
        r["set_stock"].assert_awaited_once()
        self.assertEqual(r["set_stock"].await_args.kwargs["covered"]["year_min"], 1994)
        self.assertFalse(r["blocked"])

    async def test_a_widened_search_reads_only_the_missing_years_before_the_48_hours(self):
        target = dict(TARGET, query={**TARGET["query"], "year_min": 1990,
                                     "_stock": {"year_min": 1994, "year_max": 2001, "at": 1}})
        r = await self.reads(target, [stock_result([card("MLA1")], listed={"MLA1"})])
        r["scraper"].return_value.stock_read.assert_awaited_once_with(dict(FULL, anio_min=1989, anio_max=1993))
        self.assertEqual(r["record"].await_args.kwargs, {"complete": False})  # no evidence of the whole stock
        self.assertEqual(r["set_stock"].await_args.kwargs["covered"]["year_min"], 1989)

    async def test_covered_and_not_due_reads_nothing(self):
        target = dict(TARGET, query={**TARGET["query"], "_stock": {"year_min": 1994, "year_max": 2001, "at": 1}})
        r = await self.reads(target)
        r["scraper"].return_value.stock_read.assert_not_awaited()
        r["set_stock"].assert_not_awaited()

    async def test_one_long_read_per_source_every_spacing(self):
        crawl._full_reads["mercadolibre"] = time.monotonic() - 60
        r = await self.reads(dict(TARGET, query={**TARGET["query"], "year_min": 1990,
                                                 "_stock": {"year_min": 1994, "year_max": 2001, "at": 1}}))
        r["scraper"].return_value.stock_read.assert_not_awaited()

    async def test_outside_the_rollout_the_full_read_stays_as_it_was(self):
        with patch.object(crawl.config, "STOCK_READ_TARGETS", 10):
            r = await self.reads(dict(TARGET, last_full_read_at=None), rank=10)
        r["full_read"].assert_awaited_once()
        r["scraper"].return_value.stock_read.assert_not_awaited()
        with patch.object(crawl.config, "STOCK_READ_TARGETS", 10):
            r = await self.reads(dict(TARGET, last_full_read_at=None), [stock_result([], listed=set())], rank=9)
        r["scraper"].return_value.stock_read.assert_awaited_once()

    async def test_a_partial_read_keeps_what_it_read_and_tries_later(self):
        r = await self.reads(dict(TARGET, last_full_read_at=None),
                             [stock_result([card("MLA1")], listed={"MLA1"}, complete=False, reason="42 pages")])
        self.ingest.assert_awaited_once()
        self.assertEqual(r["record"].await_args.kwargs, {"complete": False})
        self.assertIn("tried_at", r["set_stock"].await_args.kwargs)

    async def test_a_wall_pauses_the_source(self):
        r = await self.reads(dict(TARGET, last_full_read_at=None), [CollectorBlocked("login required")])
        self.assertTrue(r["blocked"])
        r["pause"].assert_called_once()
        self.assertIn("tried_at", r["set_stock"].await_args.kwargs)

    async def test_any_other_failure_never_fails_the_run(self):
        r = await self.reads(dict(TARGET, last_full_read_at=None), [RuntimeError("boom")])
        self.assertFalse(r["blocked"])
        r["log_error"].assert_awaited()

    async def test_an_isolated_collector_reads_in_its_child_process(self):
        class Isolated:
            ISOLATED = True

            async def stock_read(self, filters):           # pragma: no cover - isolated_call stands in
                raise AssertionError

        target = dict(TARGET, source="facebook", query={**TARGET["query"], "origin_lat": -34.6, "origin_lon": -58.4})
        with patch.object(crawl, "isolated_call", AsyncMock(return_value=stock_result([card("1")]))) as call:
            r = await self.reads(target, scraper_cls=Isolated)
        (_, method, filters), kwargs = call.await_args
        self.assertEqual((method, filters), ("stock_read", crawl.stock_filters(target)))
        self.assertEqual(filters["origin_lat"], -34.6)
        r["record"].assert_not_awaited()                                      # no `listed`: not Mercado Libre's
        self.assertIn("covered", r["set_stock"].await_args.kwargs)


class RunOneTests(unittest.IsolatedAsyncioTestCase):
    async def run_one(self, *, switch: bool):
        batch = crawl.TargetRun(TARGET, SearchResults([]), IngestResult(found=1), first_run=False)
        with patch.object(crawl.config, "STOCK_READ", switch), \
                patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl, "full_read", AsyncMock(return_value=False)) as full_read, \
                patch.object(crawl, "stock_reads", AsyncMock(return_value=False)) as stock_reads, \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()):
            await crawl._run_source([TARGET], None, 0, None)
        return full_read, stock_reads

    async def test_switch_off_is_todays_full_read(self):
        full_read, stock_reads = await self.run_one(switch=False)
        full_read.assert_awaited_once_with(TARGET)
        stock_reads.assert_not_awaited()

    async def test_switch_on_goes_through_the_stock_reads(self):
        full_read, stock_reads = await self.run_one(switch=True)
        full_read.assert_not_awaited()
        stock_reads.assert_awaited_once()


STOCK_MARK = {"_not_news": {"reason": "stock", "run_id": None, "target_id": 7, "prev_id": None}}


class OldStockIsNoNewCarTests(unittest.TestCase):
    def test_no_recency_for_an_undated_stock_listing(self):
        row = {"first_seen_at": NOW, "published_at": None, "attributes": STOCK_MARK}
        self.assertEqual(scoring.age_hours(row, NOW), (None, False))
        self.assertEqual(scoring.age_hours(dict(row, attributes={}), NOW), (0.0, False))
        dated = dict(row, published_at=NOW - timedelta(days=53))
        self.assertAlmostEqual(scoring.age_hours(dated, NOW)[0], 53 * 24)

    def test_near_zone_never_tells_old_stock_as_a_new_car(self):
        profile = {"filters": {"make": "Renault", "model": "Clio", "lat": -34.6, "lon": -58.4, "radius_km": 10}}
        listing = {"id": 1, "first_seen_at": NOW, "published_at": None, "price": 5_000_000, "currency": "ARS",
                   "lat": -34.9, "lon": -57.9, "year": 1997, "make": "Renault", "model": "Clio", "title": "Clio",
                   "attributes": STOCK_MARK}
        cfg = near_zone.settings({"enabled": True})
        with patch.object(near_zone, "own_zone", return_value=(-34.6, -58.4, 10.0)), \
                patch.object(near_zone, "confirmed", return_value=True):
            self.assertIsNone(near_zone.pick([listing], profile, created_at=NOW - timedelta(hours=1), now=NOW,
                                             cfg=cfg))
            self.assertIsNotNone(near_zone.pick([dict(listing, attributes={})], profile,
                                                created_at=NOW - timedelta(hours=1), now=NOW, cfg=cfg))

    def test_market_stats_leave_undated_stock_out_of_the_days_and_the_new(self):
        start, end = NOW - timedelta(days=7), NOW
        row = {"seen_at": NOW - timedelta(days=2), "status": "gone", "unconfirmed": True, "confirm_source": True,
               "source": "mercadolibre", "first_seen_at": NOW - timedelta(days=5), "published_at": None,
               "not_news": True, "price_usd": 5000, "price_partial": False}
        facts = market_stats._facts(row, start, end, timedelta(days=30), {})
        self.assertTrue(facts.gone)
        self.assertIsNone(facts.days)                                         # read 5 days ago, not listed then
        self.assertFalse(facts.new)
        facts = market_stats._facts(dict(row, not_news=False), start, end, timedelta(days=30), {})
        self.assertEqual(round(facts.days), 3)


if __name__ == "__main__":
    unittest.main()
