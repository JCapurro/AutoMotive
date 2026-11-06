"""Kavak read whole (INVENTORY_TARGET, 06/11/2026) and the vehicle gate that
keeps scoring an inventory batch cheap (pipeline/scheduler.py, pipeline/scoring.py).

One Kavak target reads /ar/usados to its last page for every search, by model
or by body type; ingest tells each card's model. A batch then holds every
model of the source, so each search only scores the listings the vehicle rule
(intelligence.matching._model) doesn't fail.
"""
from __future__ import annotations

import itertools
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from collectors import REGISTRY
from collectors import kavak as kv
from collectors._http import Page
from intelligence.matching import vehicle_fails
from pipeline.crawl import BodyTypeTargets, derive_targets, scraper_filters
from pipeline import scheduler
from pipeline.scheduler import _candidates, _vehicle_keys, _wanted

BODY = BodyTypeTargets(frozenset({"mercadolibre", "kavak"}), 1800, fx_rate=1_000.0)


def profile(pid: int, **filters) -> dict:
    return {"id": pid, "filters": filters, "origin_lat": None, "origin_lon": None}


class KavakTargetTests(unittest.TestCase):
    def test_every_search_rides_one_unfiltered_kavak_target(self):
        profiles = [profile(1, make="Ford", model="Fiesta", year_min=2015),
                    profile(2, make="Toyota", model="Etios", km_max=90_000),
                    profile(3, body_types=["suv"], price_max=20_000, currency="USD")]
        specs = derive_targets(profiles, ["kavak", "mercadolibre"], body_types=BODY)
        [kavak] = [s for s in specs if s.source == "kavak"]
        self.assertEqual((kavak.make, kavak.model, kavak.body_type), (None, None, None))
        self.assertEqual(kavak.query["inventory"], True)
        self.assertEqual(kavak.query["profile_ids"], [1, 2, 3])
        self.assertEqual(scraper_filters({"make": None, "model": None, "query": kavak.query}), {})
        # Mercado Libre keeps a target per model and per body type.
        self.assertEqual(sorted(((s.make, s.model, s.body_type) for s in specs if s.source == "mercadolibre"),
                                key=str),
                         [("Ford", "Fiesta", None), ("Toyota", "Etios", None), (None, None, "suv")])

    def test_counted_searches_ride_it_without_a_count_only_target(self):
        specs = derive_targets([profile(1, make="Ford", model="Fiesta")], ["kavak"],
                               [profile(9, make="Fiat", model="Cronos")])
        self.assertEqual([(s.source, s.make, s.query.get("count_only")) for s in specs], [("kavak", None, None)])


def catalog_page(page: int, pages: int) -> Page:
    """A /ar/usados page with three cars of its own and the state the collector reads."""
    cards = "".join(
        f'<a data-testid="card-product-{100_000 + page * 10 + i}" href="/ar/venta/ford-fiesta-se-2018">'
        f'<h3>Ford • Fiesta</h3><p>2018 • 60.000 km • SE • Manual</p><span>$ 15.000.000</span></a>'
        for i in range(3))
    state = (r'<script>self.__next_f.push([1,"{\"pagination\":{\"pages\":' + str(pages)
             + r'},\"resultsQuantity\":\"' + str(pages * 3) + r' Resultados\"}"])</script>')
    return Page(200, "https://www.kavak.com/ar/usados", f"<html><body>{cards}{state}</body></html>")


class KavakCatalogReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_the_whole_catalog_past_the_old_forty_page_cap(self):
        asked: list[str] = []

        async def fetch(url, **_):
            asked.append(url)
            page = int(url.rsplit("=", 1)[1]) if "?page=" in url else 0
            return catalog_page(page, 47)

        with patch.object(kv, "fetch_page", fetch), patch.object(kv, "_page_pause", AsyncMock()):
            found = await kv.KavakScraper().search({})
        self.assertEqual(asked[0], "https://www.kavak.com/ar/usados")
        self.assertEqual(len(asked), 47)
        self.assertTrue(found.complete, found.reason)
        self.assertEqual(len(found), 47 * 3)

    def test_kavak_is_an_inventory_source(self):
        self.assertTrue(REGISTRY["kavak"].INVENTORY_TARGET)


class VehicleGateTests(unittest.TestCase):
    MAKES = (None, "", "Ford", "ford", "Toyota", "Volkswagen", "VW")
    MODELS = (None, "", "Fiesta", "fiesta", "Fiesta Kinetic", "Etios", "Gol Trend")

    def listings(self) -> dict[int, dict]:
        return {i: {"make": make, "model": model}
                for i, (make, model) in enumerate(itertools.product(self.MAKES, self.MODELS))}

    def test_the_candidates_are_exactly_what_the_vehicle_rule_doesnt_fail(self):
        rows = self.listings()
        keys = _vehicle_keys(rows, rows)
        searches = [{"filters": {"make": make, "model": model}}
                    for make, model in itertools.product(self.MAKES, self.MODELS)]
        searches += [{"filters": {"body_types": ["suv"]}}, {"filters": {}}, {"filters": {"make": 3}},
                     {"filters": {"make": "  ", "model": "Fiesta"}}]
        for search in searches:
            with self.subTest(filters=search["filters"]):
                passing = {lid for lid, row in rows.items() if not vehicle_fails(row, search["filters"])}
                got = set(_candidates(search, keys))
                self.assertEqual(passing, got)

    def test_a_batch_of_one_model_keeps_it_and_drops_the_listings_without_one(self):
        rows = {1: {"make": "Ford", "model": "Fiesta"}, 2: {"make": "ford", "model": "FIESTA"},
                3: {"make": "Ford", "model": None}, 4: {"make": None, "model": None}}
        self.assertEqual(_candidates({"filters": {"make": "Ford", "model": "Fiesta"}}, _vehicle_keys(rows, rows)),
                         [1, 2])

    def test_another_or_an_unknown_model_fails(self):
        wanted = {"make": "Ford", "model": "Fiesta"}
        self.assertTrue(vehicle_fails({"make": "Ford", "model": "Ka"}, wanted))
        self.assertTrue(vehicle_fails({"make": "Fiat", "model": "Fiesta"}, wanted))
        self.assertFalse(vehicle_fails({"make": "Ford", "model": "Fiesta"}, wanted))
        # A card of a whole stock the catalog couldn't tell ("Ford F100"): no longer
        # matched to every search of a vehicle as unknown.
        self.assertTrue(vehicle_fails({"make": "Ford", "model": None}, wanted))
        self.assertTrue(vehicle_fails({"make": None, "model": None}, wanted))
        self.assertTrue(vehicle_fails({"make": None, "model": None}, {"make": "Ford"}))
        self.assertFalse(vehicle_fails({"make": "Ford", "model": None}, {"make": "Ford"}))
        # A search by body type alone doesn't look at the vehicle.
        self.assertFalse(vehicle_fails({"make": None, "model": None}, {"body_types": ["suv"]}))

class WantedTests(unittest.IsolatedAsyncioTestCase):
    """Comparables (a query each) only for the listings some search could match."""
    ROWS = {1: {"make": "Ford", "model": "Fiesta"}, 2: {"make": "Ford", "model": "Ka"},
            3: {"make": "Toyota", "model": "Etios"}, 4: {"make": None, "model": None}}
    TARGET = {"id": 7, "source": "kavak", "make": None, "model": None, "query": {"inventory": True}}
    FIESTA = {"profile": {"filters": {"make": "Ford", "model": "Fiesta"}}}
    ETIOS = {"profile": {"filters": {"make": "Toyota", "model": "Etios"}}}

    async def wanted(self, counting, *, first_run=False):
        keys = _vehicle_keys(self.ROWS, self.ROWS)
        with patch.object(scheduler.db, "counting_alerts_for_target", counting), \
                patch.object(scheduler, "log_error", AsyncMock()) as log_error:
            got = await _wanted(self.TARGET, [self.FIESTA], keys, first_run=first_run, listing_ids=[1, 2, 3, 4])
        return got, log_error

    async def test_the_active_and_the_counted_searches_models(self):
        got, _ = await self.wanted(AsyncMock(return_value=[self.ETIOS]))
        self.assertEqual(got, [1, 3])

    async def test_a_first_run_counts_nothing(self):
        counting = AsyncMock(return_value=[self.ETIOS])
        got, _ = await self.wanted(counting, first_run=True)
        self.assertEqual(got, [1])
        counting.assert_not_awaited()

    async def test_all_of_them_if_the_counted_searches_cant_be_read(self):
        got, log_error = await self.wanted(AsyncMock(side_effect=RuntimeError("db down")))
        self.assertEqual(got, [1, 2, 3, 4])
        self.assertEqual(log_error.await_args.args[0], "count_after_expiry")

    async def test_process_batch_reads_the_rows_then_the_comparables_it_needs(self):
        rows = {lid: dict(row, id=lid) for lid, row in self.ROWS.items()}
        scorer = MagicMock(rows=rows, prepare=AsyncMock(), evaluate=MagicMock(return_value=None))
        notifier = MagicMock(on_matches=AsyncMock(), on_listing_events=AsyncMock(), deliver=AsyncMock())
        with patch.object(scheduler.Scorer, "create", AsyncMock(return_value=scorer)), \
                patch.object(scheduler.db, "get_config", AsyncMock(return_value=15)), \
                patch.object(scheduler.db, "alerts_for_target", AsyncMock(return_value=[dict(self.FIESTA, id=1)])), \
                patch.object(scheduler.db, "counting_alerts_for_target", AsyncMock(return_value=[])), \
                patch.object(scheduler.db, "filter_unseen", AsyncMock(return_value=[])), \
                patch.object(scheduler.db, "matched_by_other_profiles", AsyncMock(return_value=set())), \
                patch.object(scheduler.news, "old_band", AsyncMock(return_value=set())), \
                patch.object(scheduler, "match_alert", AsyncMock(return_value=[])), \
                patch.object(scheduler, "count_after_expiry", AsyncMock()):
            await scheduler.process_batch(notifier, self.TARGET, [1, 2, 3, 4], first_run=False)
        self.assertEqual([c.args for c in scorer.prepare.await_args_list], [([1, 2, 3, 4],), ([1],)])
        self.assertEqual(scorer.prepare.await_args_list[0].kwargs, {"refs_limit": 0})
        self.assertEqual({c.args[0] for c in scorer.evaluate.call_args_list}, {1})

if __name__ == "__main__":
    unittest.main()
