"""Primera lectura completa (docs/PLAN_PRIMERA_LECTURA_COMPLETA.md) on
Postgres: a stock read stores old stock that every search of the model gets
as backfill and nobody is notified of, a widened search reads only the years
it adds, and a new search is built from all the stock still listed."""
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest
from psycopg.types.json import Jsonb

import collectors
import db
from collectors.base import SearchResults
from db.repos import config as app_config, listings as repo_listings, targets as repo_targets
from pgcase import requires_db
from pipeline import crawl, rematch
from pipeline.ingest import ingest

from test_ingest_postgres import FakeSource, IngestCase, card

pytestmark = [pytest.mark.db, requires_db]


class StockSource(FakeSource):
    """FakeSource with the collectors' stock_read: `stock[name]`, once each read."""
    stock: dict[str, list] = {}
    stock_calls: list[tuple[str, dict]] = []

    async def stock_read(self, filters: dict) -> SearchResults:
        StockSource.stock_calls.append((self.name, filters))
        return SearchResults([replace(l) for l in StockSource.stock.get(self.name, [])])


class StockCase(IngestCase):
    SOURCES = ("mercadolibre", "v6")

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        StockSource.stock, StockSource.stock_calls = {}, []
        crawl._full_reads.clear()
        for p in (patch.dict(collectors.REGISTRY, {"mercadolibre": type("Fake_mercadolibre", (StockSource,),
                                                                         {"name": "mercadolibre"})}),
                  patch.multiple(crawl.config, STOCK_READ=True, STOCK_READ_TARGETS=0, FULL_READ=False,
                                 FULL_READ_SPACING_SECONDS=0)):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(crawl._full_reads.clear)

    async def execute(self, sql: str, *params) -> None:
        async with db.connection() as cx:
            await cx.execute(sql, params)

    async def matched(self, aid: int) -> dict[str, bool]:
        return {r["external_id"]: r["is_backfill"] for r in await self.rows(
            "SELECT l.external_id, m.is_backfill FROM matches m JOIN listings l ON l.id = m.listing_id "
            " WHERE m.search_profile_id = %s", aid)}

    async def stored(self) -> set[str]:
        return {r["external_id"] for r in await self.rows("SELECT external_id FROM listings")}

    async def query(self) -> dict:
        [row] = await self.rows("SELECT query FROM crawl_targets WHERE source = 'mercadolibre' AND active")
        return row["query"]


class StockReadTests(StockCase):
    async def test_a_new_model_stores_its_stock_and_a_widened_search_reads_only_its_years(self):
        first = await self.fiesta_alert(anio_min=2015)
        FakeSource.results["mercadolibre"] = [card("MLA2200000100", anio=2017)]
        StockSource.stock["mercadolibre"] = [card("MLA2200000100", anio=2017),
                                             card("MLA2100000050", anio=2016, precio=9_000.0),
                                             # Published after the run's read: left to the next one.
                                             card("MLA2200000900", anio=2016)]
        await self.tick()

        self.assertEqual(StockSource.stock_calls, [("mercadolibre", {"marca": "Ford", "modelo": "Fiesta",
                                                                     "anio_min": 2014})])
        self.assertEqual(await self.stored(), {"MLA2200000100", "MLA2100000050"})
        mark = (await self.listing("MLA2100000050"))["attributes"]["_not_news"]
        self.assertEqual(mark["reason"], "stock")
        self.assertNotIn("_not_news", (await self.listing("MLA2200000100"))["attributes"])
        self.assertEqual((await self.matched(first)).get("MLA2100000050"), True)
        self.assertEqual({k: v for k, v in (await self.query())["_stock"].items() if k != "at"}, {"year_min": 2014})

        # Covered: no stock read. The card it left is news to the next run.
        FakeSource.results["mercadolibre"] = [card("MLA2200000900", anio=2016)]
        await self.tick()
        self.assertEqual(len(StockSource.stock_calls), 1)
        self.assertEqual((await self.matched(first)).get("MLA2200000900"), False)

        # Search 558's case: a new search widens the model's years.
        wide = await self.fiesta_alert(user=1, anio_min=2010)
        FakeSource.results["mercadolibre"] = []
        StockSource.stock["mercadolibre"] = [card("MLA2000000300", anio=2011)]
        await self.tick()
        self.assertEqual(StockSource.stock_calls[-1], ("mercadolibre", {"marca": "Ford", "modelo": "Fiesta",
                                                                        "anio_min": 2009, "anio_max": 2013}))
        wide_matches = await self.matched(wide)
        self.assertTrue(wide_matches["MLA2000000300"])                      # backfill, already bootstrapped
        self.assertTrue(wide_matches["MLA2100000050"])                      # the rematch, from the stock
        self.assertEqual((await self.query())["_stock"]["year_min"], 2009)
        self.assertFalse(await self.notified() & {"MLA2100000050", "MLA2000000300"})

    async def notified(self) -> set[str]:
        return {r["external_id"] for r in await self.rows(
            "SELECT l.external_id FROM notifications n JOIN listings l ON l.id = n.listing_id")}

    async def test_switch_off_reads_no_stock(self):
        await self.fiesta_alert(anio_min=2015)
        FakeSource.results["mercadolibre"] = [card("MLA2200000100", anio=2017)]
        StockSource.stock["mercadolibre"] = [card("MLA2100000050", anio=2016)]
        with patch.object(crawl.config, "STOCK_READ", False):
            await self.tick()
        self.assertEqual(StockSource.stock_calls, [])
        self.assertEqual(await self.stored(), {"MLA2200000100"})
        self.assertNotIn("_stock", await self.query())


class TargetsRepoTests(StockCase):
    async def test_sync_keeps_the_stock_coverage_when_a_search_widens(self):
        await self.fiesta_alert(anio_min=2015)
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        [t] = await self.rows("SELECT id FROM crawl_targets WHERE source = 'mercadolibre'")
        await repo_targets.set_stock(t["id"], tried_at=5)
        await repo_targets.set_stock(t["id"], covered={"year_min": 2014, "at": 9})
        await self.fiesta_alert(user=1, anio_min=2010)
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        q = await self.query()
        self.assertEqual((q["year_min"], q["_stock"], "_stock_tried" in q), (2010, {"year_min": 2014, "at": 9}, False))
        await repo_targets.set_stock(t["id"], tried_at=11)
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        self.assertEqual((await self.query())["_stock_tried"], 11)

    async def test_the_rollout_goes_by_searches(self):
        for user in (1, 2):
            await self.fiesta_alert(user=user)
        await self.fiesta_alert(modelos=["Focus"])
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        targets = {r["model"]: r for r in await self.rows(
            "SELECT id, source, model, query FROM crawl_targets WHERE source = 'mercadolibre'")}
        self.assertEqual(await repo_targets.stock_rank(targets["Fiesta"]), 0)
        self.assertEqual(await repo_targets.stock_rank(targets["Focus"]), 1)

    async def test_watermarks_skip_what_a_stock_read_stored(self):
        await ingest([card("MLA2200000100"), card("MLA1100000200")])
        self.assertEqual(await repo_targets.news_watermarks("mercadolibre"), {2: 2200000100, 1: 1100000200})
        await self.execute("UPDATE listings SET attributes = attributes || %s WHERE external_id = 'MLA2200000100'",
                           Jsonb({"_not_news": {"reason": "stock"}}))
        self.assertEqual(await repo_targets.news_watermarks("mercadolibre"), {1: 1100000200})


class RematchFromStockTests(StockCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        [self.comparables_config] = await self.rows("SELECT value FROM app_config WHERE key = 'comparables'")
        await self.execute("UPDATE app_config SET value = value || %s WHERE key = 'comparables'",
                           Jsonb({"confirm_sources": ["mercadolibre"], "confirm_grace_hours": 36}))
        app_config.clear_config_cache()

    async def asyncTearDown(self) -> None:
        await self.execute("UPDATE app_config SET value = %s WHERE key = 'comparables'",
                           Jsonb(self.comparables_config["value"]))
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def test_a_new_search_gets_the_stock_a_full_read_still_sees_and_not_what_left(self):
        await ingest([card("MLA2100000001"), card("MLA2100000002"), card("MLA2100000003")])
        # Stored 40 days ago by "Publicados hoy", seen yesterday by the 48-hour read: still listed.
        await self.execute("UPDATE listings SET first_seen_at = now() - interval '40 days', "
                           "  last_seen_at = now() - interval '40 days', last_full_seen_at = now() - interval '1 day' "
                           " WHERE external_id = 'MLA2100000001'")
        # Seen 10 days ago, and a complete read of its target since no longer saw it: it left.
        await self.execute("UPDATE listings SET last_seen_at = now() - interval '10 days' "
                           " WHERE external_id = 'MLA2100000002'")
        await self.execute("INSERT INTO crawl_targets (source, make, model, query, active, last_full_read_at) "
                           "VALUES ('mercadolibre', 'Ford', 'Fiesta', '{}', true, now() - interval '1 hour')")
        await self.execute("UPDATE listings SET last_full_seen_at = now() - interval '1 hour' "
                           " WHERE external_id = 'MLA2100000003'")

        found = {r["external_id"] for r in await repo_listings.recent_active("Ford", "Fiesta", days=30, confirmed=True)}
        self.assertEqual(found, {"MLA2100000001", "MLA2100000003"})
        before = {r["external_id"] for r in await repo_listings.recent_active("Ford", "Fiesta", days=30)}
        self.assertEqual(before, {"MLA2100000002", "MLA2100000003"})       # today's, with the switch off

        aid = await self.fiesta_alert()
        await rematch.run_pending()
        self.assertEqual(await self.matched(aid), {"MLA2100000001": True, "MLA2100000003": True})

    async def test_v6_a_new_search_gets_the_inventory_older_than_30_days(self):
        # V6 reads its whole site on every run (inventory target): last_seen_at is fresh, first_seen_at old.
        await ingest([card("V6-100", source="v6"), card("V6-200", source="v6")])
        await self.execute("UPDATE listings SET first_seen_at = now() - interval '60 days' WHERE source = 'v6'")
        await self.execute("UPDATE listings SET last_seen_at = now() - interval '45 days', status = 'active' "
                           " WHERE external_id = 'V6-200'")                    # the inventory no longer sees it
        aid = await self.fiesta_alert(sources=["v6"])
        await rematch.run_pending()
        self.assertEqual(await self.matched(aid), {"V6-100": True})


class EnrichmentTests(StockCase):
    async def test_old_stock_costs_a_detail_page_only_once_a_search_matches_it(self):
        await ingest([card("MLA2100000010", titulo="Ford Fiesta anticipo"), card("MLA2100000020",
                                                                                  titulo="Ford Fiesta anticipo")])
        await self.execute("UPDATE listings SET price_partial = true")
        await self.execute("UPDATE listings SET attributes = attributes || %s WHERE external_id = 'MLA2100000020'",
                           Jsonb({"_not_news": {"reason": "stock"}}))
        queued = {r["external_id"] for r in await repo_listings.enrichment_queue(per_source=20, max_age_days=30)}
        self.assertEqual(queued, {"MLA2100000010"})
