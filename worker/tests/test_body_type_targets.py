"""Crawl targets by body type, for searches without a model (docs/CARROCERIA.md).

Pure: fake collectors, no database and no network.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from collectors import REGISTRY
from collectors._recency import BODY_TYPE_SPAN, DAY, PublicationWindow, target_window
from db.legacy_filters import to_legacy, to_profile
from pipeline import crawl, ingest as ingest_module
from pipeline.crawl import BodyTypeTargets, TargetSpec, derive_targets, prefilter, scraper_filters
from pipeline.ingest import IngestResult, ListingEvent
from normalization.listing import Target

NOW = 1_700_000_000


def scraper(name: str, *, body_types=(), inventory=False) -> type:
    return type(name, (), {"BODY_TYPES": frozenset(body_types), "INVENTORY_TARGET": inventory})


FAKES = {
    "mercadolibre": scraper("ML", body_types={"suv", "pickup", "sedan"}),
    "kavak": scraper("Kavak", body_types={"suv"}),
    "autocosmos": scraper("Autocosmos", body_types={"suv"}),
    "mardelusados": scraper("Mardel", inventory=True),
}
SOURCES = list(FAKES)
BODY = BodyTypeTargets(frozenset({"mercadolibre", "kavak"}), 1800, fx_rate=1_000.0)


def suv(pid: int, **filters) -> dict:
    f = {"body_types": ["suv"], "price_max": 20_000, "currency": "USD"}
    f.update(filters)
    return {"id": pid, "filters": f, "origin_lat": None, "origin_lon": None}


class BodyTypeTargetTests(unittest.TestCase):
    def setUp(self):
        p = patch.dict(REGISTRY, FAKES, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def derive(self, profiles, counting=(), body=BODY):
        return derive_targets(profiles, SOURCES, counting, body_types=body)

    def test_a_search_by_body_type_gets_one_target_per_source_that_can_search_it(self):
        specs = self.derive([suv(1, body_types=["suv", "pickup", "suv"])])
        self.assertEqual([(s.source, s.make, s.model, s.body_type) for s in specs], [
            ("kavak", None, None, "suv"),
            ("mardelusados", None, None, None),             # inventory: as before
            ("mercadolibre", None, None, "pickup"),
            ("mercadolibre", None, None, "suv"),
        ])
        # Autocosmos can search SUVs, but body_type_targets doesn't name it.
        self.assertNotIn("autocosmos", {s.source for s in specs})
        self.assertEqual(specs[0].query["profile_ids"], [1])     # a repeated code adds nothing

    def test_the_query_is_the_widest_with_a_usd_price_ceiling_and_its_own_cadence(self):
        specs = self.derive([
            suv(1, year_min=2016, km_max=80_000, sources=["kavak"]),
            # ARS 25.000.000 at 1.000 = USD 25.000; read by magnitude without a currency.
            suv(2, year_min=2012, km_max=120_000, price_max=25_000_000, currency=None, sources=["kavak"]),
        ])
        [kavak] = specs
        self.assertEqual(kavak.query, {"year_min": 2012, "km_max": 120_000, "price_usd_max": 25_000,
                                       "interval_seconds": 1800, "profile_ids": [1, 2]})

    def test_mercado_libre_keeps_its_publication_policy(self):
        [spec] = self.derive([suv(1, sources=["mercadolibre"])])
        self.assertEqual(spec.query["publication_policy"], crawl.POLICY_VERSION)
        self.assertEqual(spec.body_type, "suv")

    def test_no_ceiling_when_one_search_has_no_cap_or_an_ars_cap_cannot_be_converted(self):
        [spec] = self.derive([suv(1, sources=["kavak"]), suv(2, price_max=None, sources=["kavak"])])
        self.assertNotIn("price_usd_max", spec.query)
        no_rate = BodyTypeTargets(BODY.sources, 1800, fx_rate=None)
        [spec] = self.derive([suv(1, price_max=30_000_000, currency="ARS", sources=["kavak"])], body=no_rate)
        self.assertNotIn("price_usd_max", spec.query)

    def test_the_profile_s_sources_and_the_collector_s_body_types_are_respected(self):
        specs = self.derive([suv(1, body_types=["pickup", "rural"], sources=["kavak", "mercadolibre"])])
        # Kavak can't search pick-ups and nobody can search rurales.
        self.assertEqual([(s.source, s.body_type) for s in specs], [("mercadolibre", "pickup")])

    def test_without_the_config_or_a_body_type_a_search_without_a_model_gets_no_target(self):
        self.assertEqual([s.source for s in self.derive([suv(1)], body=None)], ["mardelusados"])
        self.assertEqual([s.source for s in self.derive([suv(1, body_types=[])])], ["mardelusados"])

    def test_a_blank_make_and_model_count_as_none(self):
        specs = self.derive([suv(1, make=" ", model="", sources=["kavak"])])
        self.assertEqual([(s.source, s.make, s.body_type) for s in specs], [("kavak", None, "suv")])

    def test_the_body_types_of_a_search_with_a_model_are_a_filter_not_a_target(self):
        specs = self.derive([suv(1, make="Ford", model="Ka", body_types=["sedan"], sources=["mercadolibre"])])
        self.assertEqual([(s.source, s.make, s.model, s.body_type) for s in specs],
                         [("mercadolibre", "Ford", "Ka", None)])
        self.assertNotIn("price_usd_max", specs[0].query)
        self.assertNotIn("interval_seconds", specs[0].query)

    def test_counted_searches_never_get_a_target_by_body_type(self):
        """2.5 counts models: a counted search without a model adds nothing."""
        specs = self.derive([], counting=[suv(7, sources=["mercadolibre"])])
        self.assertEqual(specs, [])

    def test_target_identity_includes_the_body_type(self):
        self.assertNotEqual(TargetSpec("kavak", None, None, {}, body_type="suv"),
                            TargetSpec("kavak", None, None, {}, body_type="pickup"))
        self.assertEqual(TargetSpec("kavak", None, None, {"a": 1}, body_type="suv"),
                         TargetSpec("kavak", None, None, {"b": 2}, body_type="suv"))
        self.assertNotEqual(TargetSpec("kavak", None, None, {}), TargetSpec("kavak", None, None, {}, body_type="suv"))


class ScraperFilterTests(unittest.TestCase):
    TARGET = {"source": "kavak", "make": None, "model": None, "body_type": "suv", "first_run_done": False,
              "query": {"year_min": 2015, "km_max": 100_000, "price_usd_max": 20_000, "interval_seconds": 1800}}

    def test_a_target_by_body_type_asks_for_the_code_and_no_vehicle(self):
        self.assertEqual(scraper_filters(self.TARGET), {"carroceria": "suv", "anio_min": 2015, "km_max": 100_000})

    def test_mercado_libre_reads_today_also_on_the_first_run(self):
        with patch("collectors._recency.time.time", return_value=NOW):
            f = scraper_filters(dict(self.TARGET, source="mercadolibre"))
        self.assertEqual((f["carroceria"], f["published_today_only"], f["publication_days"]), ("suv", True, 1))
        self.assertNotIn("marca", f)
        self.assertNotIn("modelo", f)


class BodyTypeWindowTests(unittest.TestCase):
    def window(self, source="mercadolibre", **target):
        return target_window({"source": source, "body_type": "suv", **target}, now=NOW)

    def test_the_first_run_reads_the_last_day_not_thirty(self):
        w = self.window(first_run_done=False)
        self.assertEqual((w["published_since"], w["publication_days"], w["published_today_only"]),
                         (NOW - DAY, 1, True))

    def test_a_gap_widens_the_window_to_25_hours_at_most(self):
        for gap, since in ((600, NOW - DAY), (DAY + 1800, NOW - DAY - 2400), (3 * DAY, NOW - BODY_TYPE_SPAN)):
            w = self.window(first_run_done=True, last_run_at=datetime.fromtimestamp(NOW - gap, timezone.utc))
            self.assertEqual(w["published_since"], since)
            self.assertLessEqual(w["publication_until"] - w["published_since"], 25 * 3600)
            self.assertTrue(w["published_today_only"])
            self.assertIsNotNone(PublicationWindow.from_filters(w))

    def test_facebook_dates_are_checked_and_other_sources_have_no_window(self):
        self.assertFalse(self.window("facebook", first_run_done=False)["published_today_only"])
        self.assertEqual(self.window("kavak", first_run_done=False), {})

    def test_model_targets_keep_the_thirty_day_bootstrap(self):
        w = target_window({"source": "mercadolibre", "first_run_done": False}, now=NOW)
        self.assertEqual(w["publication_days"], 30)


class PrefilterTests(unittest.TestCase):
    TARGET = {"body_type": "suv", "query": {"year_min": 2015, "km_max": 100_000, "price_usd_max": 20_000}}

    def test_only_targets_by_body_type_prefilter(self):
        self.assertIsNone(prefilter({"make": "Ford", "model": "Ka", "query": {"year_min": 2015}}))
        self.assertIsNone(prefilter({"query": {"inventory": True}}))

    def test_what_no_search_can_want_goes_and_unknown_values_pass(self):
        keep = prefilter(self.TARGET)
        ok = {"year": 2018, "mileage_km": 50_000, "price_usd": 18_000}
        self.assertTrue(keep(ok))
        self.assertFalse(keep(dict(ok, year=2014)))
        self.assertFalse(keep(dict(ok, mileage_km=100_001)))
        self.assertFalse(keep(dict(ok, price_usd=21_001)))              # above the ceiling plus 5 %
        self.assertTrue(keep(dict(ok, price_usd=20_900)))               # inside the margin
        self.assertTrue(keep(dict(ok, price_usd=60_000, price_partial=True)))   # a down payment says nothing
        self.assertTrue(keep({"year": None, "mileage_km": None, "price_usd": None}))

    def test_an_unbounded_query_keeps_everything(self):
        keep = prefilter({"body_type": "suv", "query": {}})
        self.assertTrue(keep({"year": 1980, "mileage_km": 900_000, "price_usd": 1_000_000}))


class IngestPrefilterTests(unittest.IsolatedAsyncioTestCase):
    async def test_dropped_rows_are_not_geocoded_or_stored_but_count_as_found(self):
        rows = [{"source": "kavak", "external_id": str(i), "year": year} for i, year in enumerate((2010, 2020))]
        geocode = AsyncMock(return_value=None)
        with patch.object(ingest_module, "normalize_items", AsyncMock(return_value=rows)) as normalize, \
                patch.object(ingest_module, "_geocode_rows", AsyncMock()) as geocoded, \
                patch.object(ingest_module, "ingest_rows", AsyncMock(return_value=IngestResult(found=1))) as stored:
            result = await ingest_module.ingest([], target=Target(body_type="suv"), geocode=geocode,
                                                config=ingest_module.IngestConfig(),
                                                keep=lambda r: r["year"] >= 2015)
        self.assertEqual(normalize.await_args.kwargs["geocode"], None)
        self.assertEqual(geocoded.await_args.args[0], [rows[1]])
        self.assertEqual(stored.await_args.args[0], [rows[1]])
        self.assertEqual(result.found, 2)


class RunTargetTests(unittest.IsolatedAsyncioTestCase):
    TARGET = dict(ScraperFilterTests.TARGET, id=9, first_run_done=True, last_run_at=None,
                  prefilter_rejected=["old-1", "gone"])

    async def run_target(self, target: dict, ingest, *, not_news: frozenset[int] = frozenset()):
        class Kavak:
            BODY_TYPES = frozenset({"suv"})
            searched: list[dict] = []

            async def search(self, filters):
                Kavak.searched.append(filters)
                return []

        self.searched = Kavak.searched
        with patch.dict(REGISTRY, {"kavak": Kavak}, clear=True), \
                patch.object(crawl.runs, "start_run", AsyncMock(return_value=1)), \
                patch.object(crawl.runs, "finish_run", AsyncMock(return_value=None)), \
                patch.object(crawl.targets_repo, "set_prefilter_rejected", AsyncMock()) as self.remember, \
                patch.object(crawl.news, "classify", AsyncMock(return_value=not_news)) as self.classify, \
                patch.object(crawl, "ingest", AsyncMock(side_effect=ingest)) as self.ingested:
            return await crawl.run_target(target)

    async def test_a_target_by_body_type_ingests_with_its_hint_and_prefilter(self):
        async def ingest(items, *, target, keep):
            self.assertFalse(keep({"external_id": "old-2", "year": 2010}))     # dropped now
            self.assertTrue(keep({"external_id": "old-1", "year": 2020}))      # dropped before, kept now
            self.assertTrue(keep({"external_id": "new", "year": 2020}))
            result = IngestResult()
            result.events = [ListingEvent("listing_new", 31, "kavak", "old-1"),
                             ListingEvent("listing_new", 32, "kavak", "new")]
            return result

        run = await self.run_target(self.TARGET, ingest)
        self.assertEqual(self.searched, [{"carroceria": "suv", "anio_min": 2015, "km_max": 100_000}])
        self.assertEqual(self.ingested.await_args.kwargs["target"], Target(None, None, "suv"))
        # Old stock the prefilter let in later is backfill; the next run remembers what it dropped now.
        self.assertEqual(run.backfill_ids, frozenset({31}))
        self.remember.assert_awaited_once_with(9, {"old-2"})
        self.assertEqual(self.classify.await_args.kwargs, {"run_id": 1, "first_run": False, "complete": True})

    async def test_news_ids_join_the_prefilter_backfill(self):
        async def ingest(items, *, target, keep):
            result = IngestResult()
            result.events = [ListingEvent("listing_new", 31, "kavak", "old-1"),
                             ListingEvent("listing_new", 33, "kavak", "step")]
            return result

        run = await self.run_target(self.TARGET, ingest, not_news=frozenset({33}))
        self.assertEqual(run.backfill_ids, frozenset({31, 33}))

    async def test_a_model_target_never_writes_prefilter_rejected(self):
        async def ingest(items, *, target, keep):
            self.assertIsNone(keep)
            return IngestResult()

        target = {"id": 4, "source": "kavak", "make": "Ford", "model": "Ka", "body_type": None,
                  "query": {"year_min": 2015, "profile_ids": [1]}, "first_run_done": True, "last_run_at": None,
                  "prefilter_rejected": []}
        run = await self.run_target(target, ingest, not_news=frozenset({40}))
        self.assertEqual(run.backfill_ids, frozenset({40}))
        self.remember.assert_not_awaited()


class PlatformHealthLabelTests(unittest.TestCase):
    def test_a_broken_target_by_body_type_is_named_by_its_body_type(self):
        from tools import platform_health as health
        now = datetime(2026, 10, 15, tzinfo=timezone.utc)
        row = dict(id=4, source="mercadolibre", name="Mercado Libre", make=None, model=None, body_type="suv",
                   created_at=now, updated_at=now, next_run_at=now, crawl_interval_seconds=1800,
                   started_at=now, latest_status="failed", latest_error="RuntimeError: filtro ignorado",
                   statuses=["failed"] * 3, found=[0] * 3, had_results=True)
        problem = health.collector_checks([row], now)["collector:mercadolibre"]
        self.assertTrue(problem.startswith("Mercado Libre · SUV: 3 corridas fallidas"), problem)


class LegacyBodyTypeTests(unittest.TestCase):
    def test_the_wizard_dict_carries_body_types_both_ways(self):
        legacy = {"carroceria": ["suv", "pickup"], "precio_max": 20_000, "moneda": "USD"}
        values = to_profile(legacy, None, None)
        self.assertEqual(values["filters"]["body_types"], ["suv", "pickup"])
        self.assertNotIn("legacy_extra", values["preferences"])
        self.assertEqual(to_legacy(values["filters"], values["preferences"]), legacy)
        self.assertEqual(to_profile({"carroceria": "suv"}, None, None)["filters"]["body_types"], ["suv"])
        self.assertNotIn("body_types", to_profile({}, "Ford", "Ka")["filters"])


if __name__ == "__main__":
    unittest.main()


class WebBodyTypeSearchesTests(unittest.TestCase):
    def test_the_web_knows_what_each_collector_searches(self):
        """web/lib/search-collection.ts waits for a target per body type the collector can search."""
        import json
        import re
        from pathlib import Path
        import collectors

        ts = (Path(__file__).resolve().parents[2] / "web" / "lib" / "search-collection.ts").read_text(encoding="utf-8")
        m = re.search(r"BODY_TYPE_SEARCHES: Record<string, readonly string\[\]> = (\{.*\});", ts)
        self.assertIsNotNone(m)
        expected = {name: sorted(cls.BODY_TYPES) for name, cls in collectors.REGISTRY.items()
                    if getattr(cls, "BODY_TYPES", None)}
        self.assertEqual(json.loads(m.group(1)), expected)
