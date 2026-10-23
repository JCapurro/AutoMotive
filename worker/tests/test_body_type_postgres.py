"""Searches without a model, only by body type, through the pipeline (docs/CARROCERIA.md).

Crawl targets by body type, the batches they and the other targets match,
the rematch from stored listings and the enrichment hook, against the local
Postgres with fake collectors.
"""
from __future__ import annotations

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest

import collectors
import db
from db.repos import config as app_config, listings as repo_listings, profiles, targets as repo_targets
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from psycopg.types.json import Jsonb

from intelligence import comparables
from pgcase import TEST_FX_RATE, requires_db
from pipeline import crawl, enrich, rematch, scheduler
from pipeline.ingest import ingest
from collectors.base import ListingDetail
from notifications.channels.web import WebChannel
from notifications.links import Links
from notifications.service import Notifier
from test_ingest_postgres import FakeSource, IngestCase, card

pytestmark = [pytest.mark.db, requires_db]

SUV_USER, PICKUP_USER = 20001, 20002


def eco(listing_id: str, source: str = "kavak", **kw) -> object:
    base = dict(titulo=f"Ford EcoSport 1.6 Freestyle {listing_id}", marca="Ford", modelo="EcoSport",
                precio=18_000.0, anio=2018, km=60_000)
    base.update(kw)
    return card(listing_id, source=source, **base)


class BodyTypeCase(IngestCase):
    SOURCES = ("mercadolibre", "kavak", "mardelusados")

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        collectors.REGISTRY["mercadolibre"].BODY_TYPES = frozenset({"suv", "pickup"})
        collectors.REGISTRY["kavak"].BODY_TYPES = frozenset({"suv"})
        collectors.REGISTRY["mardelusados"].INVENTORY_TARGET = True

    async def body_alert(self, user: int = SUV_USER, body=("suv",), **wizard) -> int:
        f = {"carroceria": list(body), "precio_max": 20_000, "moneda": "USD", "sources": ["kavak"]}
        f.update(wizard)
        [aid] = await db.create_alert(user_id=user, chat_id=user, name=" o ".join(body), filters=f)
        return aid

    async def sync(self) -> None:
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())

    async def targets(self) -> list[tuple]:
        return [tuple(r.values()) for r in await self.rows(
            "SELECT source, make, model, body_type FROM crawl_targets WHERE active "
            " ORDER BY source, make NULLS FIRST, body_type NULLS FIRST")]

    async def matched(self, aid: int) -> list[tuple[str, bool]]:
        return [(r["external_id"], r["is_backfill"]) for r in await self.rows(
            "SELECT l.external_id, m.is_backfill FROM matches m JOIN listings l ON l.id = m.listing_id "
            " WHERE m.search_profile_id = %s ORDER BY l.external_id", aid)]


class BodyTypeTargetsTests(BodyTypeCase):
    async def test_the_three_target_shapes_are_synced_once_and_each_is_due_for_its_searches(self):
        await self.fiesta_alert(sources=["mercadolibre"])
        suv = await self.body_alert(sources=["mercadolibre", "kavak", "mardelusados"])
        await self.sync()
        await self.sync()               # null make/model/body_type conflict like any other value

        self.assertEqual(await self.targets(), [
            ("kavak", None, None, "suv"),
            ("mardelusados", None, None, None),
            ("mercadolibre", None, None, "suv"),
            ("mercadolibre", "Ford", "Fiesta", None),
        ])
        [kavak] = await self.rows("SELECT query FROM crawl_targets WHERE source = 'kavak'")
        self.assertEqual(kavak["query"], {"price_usd_max": 20_000, "interval_seconds": 1800,
                                          "profile_ids": [suv]})
        due = {(t["source"], t["make"], t["body_type"]): t["crawl_interval_seconds"]
               for t in await repo_targets.due_targets()}
        self.assertEqual(due, {("kavak", None, "suv"): 1800, ("mardelusados", None, None): 3600,
                               ("mercadolibre", None, "suv"): 1800, ("mercadolibre", "Ford", None): 600})

        # A search by another body type doesn't make the SUV targets due: they
        # have make and model null too, like the inventory target.
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET filters = jsonb_set(filters, '{body_types}', "
                             "'[\"pickup\"]') WHERE id = %s", (suv,))
        due = {(t["source"], t["make"], t["body_type"]) for t in await repo_targets.due_targets()}
        self.assertEqual(due, {("mardelusados", None, None), ("mercadolibre", "Ford", None)})
        await self.sync()
        self.assertEqual(await self.targets(), [
            ("mardelusados", None, None, None),
            ("mercadolibre", None, None, "pickup"),
            ("mercadolibre", "Ford", "Fiesta", None),
        ])

    async def test_an_ars_cap_becomes_the_usd_ceiling_and_a_target_runs_at_its_own_cadence(self):
        await self.body_alert(precio_max=30_000_000, moneda="ARS")
        await self.sync()
        [t] = await self.rows("SELECT id, query FROM crawl_targets")
        self.assertEqual(t["query"]["price_usd_max"], round(30_000_000 / TEST_FX_RATE))
        await repo_targets.finish_target(t["id"], ok=True, retry_seconds=0)
        [t] = await self.rows("SELECT next_run_at - now() AS wait FROM crawl_targets")
        self.assertTrue(timedelta(seconds=1700) < t["wait"] <= timedelta(seconds=1800))

    async def test_the_config_names_the_sources_and_counted_searches_get_none(self):
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{sources}', '[\"mercadolibre\"]') "
                             " WHERE key = 'body_type_targets'")
        try:
            app_config.clear_config_cache()
            await self.body_alert(sources=["mercadolibre", "kavak"])
            await self.sync()
            self.assertEqual(await self.targets(), [("mercadolibre", None, None, "suv")])
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{sources}', "
                                 "'[\"mercadolibre\", \"kavak\"]') WHERE key = 'body_type_targets'")

    async def test_publication_dates_of_a_target_by_body_type_are_its_recent_listings(self):
        published = int(datetime.now(timezone.utc).timestamp()) - 3600
        await ingest([eco("1", source="mercadolibre", published_at=published),
                      card("2", source="mercadolibre", titulo="Toyota Corolla XEI 2.0", marca="Toyota",
                           modelo="Corolla", published_at=published),
                      eco("3", source="mercadolibre", published_at=published)], geocode=None)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '3 days' WHERE external_id = '3'")
        dates = await repo_targets.publication_dates({"source": "mercadolibre", "make": None, "model": None,
                                                      "body_type": "suv"})
        self.assertEqual(dates, {"1": published})


class BatchProfilesTests(BodyTypeCase):
    async def test_every_batch_reaches_the_searches_without_a_model_and_a_body_type_batch_only_those(self):
        fiesta = await self.fiesta_alert(sources=["mercadolibre", "kavak"])
        suv = await self.body_alert(sources=["mercadolibre", "kavak"])
        pickup = await self.body_alert(user=PICKUP_USER, body=("pickup",), sources=["kavak"])

        def ids(alerts):
            return [a["id"] for a in alerts]

        self.assertEqual(ids(await profiles.alerts_for_target("mercadolibre", "Ford", "Fiesta",
                                                              telegram_only=False)), [fiesta, suv])
        self.assertEqual(ids(await profiles.alerts_for_target("kavak", "Toyota", "Hilux",
                                                              telegram_only=False)), [suv, pickup])
        self.assertEqual(ids(await profiles.alerts_for_target("kavak", None, None, telegram_only=False,
                                                              body_type="suv")), [suv, pickup])
        self.assertEqual(ids(await profiles.alerts_for_target("mardelusados", None, None, telegram_only=False,
                                                              inventory=True)), [])
        self.assertEqual(ids(await profiles.model_less_alerts()), [suv, pickup])
        self.assertEqual(await profiles.counting_alerts_for_target("kavak", None, None, body_type="suv"), [])
        await db.set_alert_active(suv, False)
        self.assertEqual(ids(await profiles.alerts_for_target("kavak", None, None, telegram_only=False,
                                                              body_type="suv")), [pickup])

    async def test_a_target_by_body_type_keeps_what_its_searches_can_want_and_matches_it(self):
        suv = await self.body_alert(anio_min=2015, km_max=120_000)
        FakeSource.results["kavak"] = [
            eco("ok"),
            eco("ars", precio=15_000_000.0, moneda="ARS"),                 # USD 15.000
            eco("no-price", precio=None, moneda=None),
            eco("expensive", precio=45_000.0),
            eco("old", anio=2010),
            eco("edge", anio=2014),                                     # the reference band's year
            eco("worn", km=200_000),
        ]
        await self.tick()

        self.assertEqual(FakeSource.searches, [("kavak", {"carroceria": "suv", "anio_min": 2014,
                                                          "km_max": 120_000})])
        stored = await self.rows("SELECT external_id, body_type FROM listings ORDER BY external_id")
        self.assertEqual([(r["external_id"], r["body_type"]) for r in stored],
                         [("ars", "suv"), ("edge", "suv"), ("no-price", "suv"), ("ok", "suv")])
        [run] = await self.rows("SELECT status, found, new FROM collector_runs")
        self.assertEqual(tuple(run.values()), ("ok", 7, 4))             # the dropped ones were found
        matched = dict(await self.matched(suv))
        self.assertTrue(matched["ok"] and matched["ars"])                # a first run is backfill
        self.assertNotIn("expensive", matched)

    async def test_an_suv_a_model_target_brings_reaches_the_search_by_body_type(self):
        await self.fiesta_alert(sources=["kavak"])
        suv = await self.body_alert(sources=["kavak"])
        collectors.REGISTRY["kavak"].BODY_TYPES = frozenset()       # Kavak only searches the Fiesta
        FakeSource.results["kavak"] = [card("fiesta", source="kavak"), eco("eco1")]
        await self.tick()
        FakeSource.results["kavak"] = [card("fiesta", source="kavak"), eco("eco1"), eco("eco2")]
        await self.tick()

        self.assertEqual(await self.targets(), [("kavak", "Ford", "Fiesta", None)])
        # The Fiesta's body type is unknown: never a match without a model.
        self.assertEqual(await self.matched(suv), [("eco1", True), ("eco2", False)])


class ForeignBatchTests(BodyTypeCase):
    """A batch that reaches a search without a model from a target that isn't its own."""

    def notifier(self):
        """Records the candidates each batch hands the notification engine."""
        self.candidates = []

        async def on_matches(candidates, rows):
            self.candidates += [rows[c.listing_id]["external_id"] for c in candidates]
        return SimpleNamespace(on_matches=on_matches, on_listing_events=AsyncMock(), deliver=AsyncMock())

    async def ids(self, *external_ids: str) -> list[int]:
        rows = await self.rows("SELECT id, external_id FROM listings WHERE external_id = ANY(%s)", list(external_ids))
        by = {r["external_id"]: r["id"] for r in rows}
        return [by[e] for e in external_ids]

    MODEL_TARGET = {"id": None, "source": "mercadolibre", "make": "Ford", "model": "Fiesta", "body_type": None,
                    "query": {}}
    BODY_TARGET = {"id": None, "source": "mercadolibre", "make": None, "model": None, "body_type": "suv",
                   "query": {}}

    async def test_a_new_model_targets_first_run_does_not_mute_a_bootstrapped_search_by_body_type(self):
        suv = await self.body_alert(sources=["mercadolibre"])
        await rematch.run_pending()                                     # bootstrapped, nothing stored yet
        now = int(datetime.now(timezone.utc).timestamp())
        await ingest([eco("today", source="mercadolibre", published_at=now - 3600),
                      eco("old", source="mercadolibre", published_at=now - 40 * 86_400),
                      eco("undated", source="mercadolibre")], geocode=None)
        today, old, undated = await self.ids("today", "old", "undated")

        # The Fiesta's first run brings its 30 days, and the SUVs in them reach
        # "any SUV": the recent publication is news, the rest backfill.
        await scheduler.process_batch(self.notifier(), self.MODEL_TARGET, [today, old, undated], first_run=True)
        self.assertEqual(await self.matched(suv), [("old", True), ("today", False), ("undated", True)])
        self.assertEqual(self.candidates, ["today"])

        # The target by body type finds them stored: nothing new.
        await scheduler.process_batch(self.notifier(), self.BODY_TARGET, [today, old, undated], first_run=False)
        self.assertEqual(self.candidates, [])

        # A search that isn't bootstrapped yet still gets only backfill.
        pickup = await self.body_alert(user=PICKUP_USER, sources=["mercadolibre"])
        await scheduler.process_batch(self.notifier(), self.MODEL_TARGET, [today, old, undated], first_run=True)
        self.assertEqual(await self.matched(pickup), [("old", True), ("today", True), ("undated", True)])
        self.assertEqual(self.candidates, [])

    async def test_a_body_type_the_batch_filled_in_is_old_news_without_a_model(self):
        fiesta = await self.fiesta_alert()
        suv = await self.body_alert(sources=["mercadolibre"])
        await rematch.run_pending()
        await ingest([eco("filled", source="mercadolibre"), eco("brand-new", source="mercadolibre")], geocode=None)
        filled, new = await self.ids("filled", "brand-new")

        await scheduler.process_batch(self.notifier(), self.BODY_TARGET, [filled, new], first_run=False,
                                      body_type_filled=[filled])
        self.assertEqual(await self.matched(suv), [("brand-new", False), ("filled", True)])
        self.assertEqual(self.candidates, ["brand-new"])
        # Searches with a model don't care: their batches matched it without the body type.
        self.assertEqual(await self.matched(fiesta), [])

    def ka(self, listing_id: str, year: int, **kw) -> object:
        base = dict(titulo=f"Ford Ka 1.5 SE {listing_id}", marca="Ford", modelo="Ka", anio=year,
                    carroceria="Hatchback")
        base.update(kw)
        return card(listing_id, source="kavak", **base)

    async def band_read(self, *, banded_before: bool = True, classify_fails: bool = False) -> int:
        """A Ka search from 2010 on Kavak, which reads 2009 too (the reference
        band), next to a bootstrapped search for any hatchback. The second
        read brings a new Ka 2009 and a new Ka 2011. `banded_before`: the
        first read had the band too; if not, the second is the band's first."""
        ka = await self.fiesta_alert(marcas=["Ford"], modelos=["Ka"], anio_min=2010, sources=["kavak"])
        hatch = await self.body_alert(body=("hatchback",), sources=["kavak"])
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET channels = '{web}' WHERE id = ANY(%s)", ([ka, hatch],))
        market = [self.ka(f"c{i}", 2011 + i % 2, precio=12_000.0 + i * 100, km=90_000 + i * 2_000)
                  for i in range(6)]
        FakeSource.results["kavak"] = market
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", int(banded_before)):
            await self.tick()                                           # the target's first run
        self.assertEqual(FakeSource.searches[0][1]["anio_min"], 2010 - banded_before)
        FakeSource.results["kavak"] = market + [self.ka("old", 2009, precio=9_000.0, km=95_000),
                                                self.ka("new", 2011, precio=9_000.0, km=95_500)]
        fails = (patch("pipeline.news._classify", AsyncMock(side_effect=RuntimeError("db"))) if classify_fails
                 else nullcontext())
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 1), fails:
            await self.tick()
        [t] = await self.rows("SELECT query FROM crawl_targets WHERE active")
        self.assertEqual((t["query"]["year_min"], t["query"]["year_band"], t["query"]["_read"]["year_min"]),
                         (2010, 1, 2009))
        return hatch

    async def notified(self) -> set[str]:
        return {r["external_id"] for r in await self.rows(
            "SELECT l.external_id FROM notifications n JOIN listings l ON l.id = n.listing_id")}

    async def test_a_band_row_listed_later_is_news_for_a_search_without_a_model(self):
        # Only the Ka search can't match a Ka 2009: for any hatchback it is a car just listed.
        hatch = await self.band_read()
        matched = dict(await self.matched(hatch))
        self.assertEqual((matched["old"], matched["new"]), (False, False))
        self.assertIn("new", await self.notified())
        self.assertNotIn("_not_news", (await self.listing("old"))["attributes"])

    async def test_the_band_s_first_read_is_backfill_for_a_search_without_a_model(self):
        hatch = await self.band_read(banded_before=False)
        matched = dict(await self.matched(hatch))
        self.assertEqual((matched["old"], matched["new"]), (True, False))
        self.assertEqual(await self.notified(), {"new"})
        [t] = await self.rows("SELECT id FROM crawl_targets WHERE active")
        self.assertEqual({k: v for k, v in (await self.listing("old"))["attributes"]["_not_news"].items()
                          if k in ("reason", "target_id")}, {"reason": "band", "target_id": t["id"]})

    async def test_the_band_s_first_read_stays_backfill_when_classify_fails(self):
        hatch = await self.band_read(banded_before=False, classify_fails=True)
        [err] = await self.rows("SELECT stage FROM pipeline_errors")
        self.assertEqual(err["stage"], "news")
        matched = dict(await self.matched(hatch))
        self.assertEqual((matched["old"], matched["new"]), (True, False))
        self.assertEqual(await self.notified(), {"new"})
        self.assertNotIn("_not_news", (await self.listing("old"))["attributes"])

    async def test_a_crawl_that_fills_a_body_type_lists_it(self):
        await ingest([card("1")], geocode=None)                         # a Fiesta, body type unknown
        result = await ingest([card("1", carroceria="Hatchback")], geocode=None)
        self.assertEqual(result.body_type_filled, [(await self.listing("1"))["id"]])


class BandOfAnotherTargetTests(BodyTypeCase):
    """A target's reference band is its own business: a car only its band
    reads is still news for another target's searches whose years include
    it, whichever target reads it first (E5 review)."""
    SOURCES = ("mercadolibre", "kavak", "mardelusados", "deruedas")

    @staticmethod
    def jeep(listing_id: str, year: int) -> object:
        return card(listing_id, source="kavak", titulo=f"Jeep Renegade 1.8 Sport {listing_id}", marca="Jeep",
                    modelo="Renegade", anio=year, carroceria="SUV", precio=15_000.0, km=60_000)

    @staticmethod
    def renault(listing_id: str, model: str, year: int) -> object:
        return card(listing_id, source="deruedas", titulo=f"Renault {model} 1.6 {listing_id}", marca="Renault",
                    modelo=model, anio=year, carroceria="Hatchback", precio=11_000.0, km=60_000)

    async def on_the_web(self, *aids: int) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET channels = '{web}' WHERE id = ANY(%s)", (list(aids),))

    async def crawl_only(self, column: str, value: str | None) -> None:
        """One crawl of the targets whose `column` is `value`, the others not due."""
        async with db.connection() as cx:
            await cx.execute(f"UPDATE crawl_targets SET next_run_at = CASE WHEN {column} IS NOT DISTINCT FROM %s "
                             "  THEN NULL ELSE now() + interval '1 hour' END", (value,))
        notifier = Notifier({"web": WebChannel(Links())})
        await crawl.crawl_due(scheduler.batch_handler(notifier), jitter_seconds=0)

    async def renegade_and_suv(self) -> tuple[int, int]:
        """'Any SUV from 2018' (kavak/suv reads 2017 too) and 'Renegade
        2015-2017' (kavak Renegade reads 2014-2018), past their first runs."""
        suv = await self.body_alert(anio_min=2018)
        renegade = await self.fiesta_alert(marcas=["Jeep"], modelos=["Renegade"], anio_min=2015, anio_max=2017,
                                           sources=["kavak"])
        await self.on_the_web(suv, renegade)
        FakeSource.results["kavak"] = [self.jeep("r16", 2016), self.jeep("r19", 2019)]
        await self.tick()
        queries = {t["body_type"]: t["query"] for t in await self.rows("SELECT body_type, query FROM crawl_targets")}
        self.assertEqual((queries["suv"]["year_band"], queries[None]["year_band"]), (1, 1))
        return suv, renegade

    async def test_a_car_a_body_type_reads_in_its_band_is_news_for_the_model_search_that_wants_it(self):
        suv, renegade = await self.renegade_and_suv()
        FakeSource.results["kavak"] += [self.jeep("r17", 2017)]
        await self.crawl_only("body_type", "suv")                       # its band: the SUVs from 2018 can't want it
        self.assertNotIn("r17", dict(await self.matched(suv)))
        await self.crawl_only("body_type", None)
        self.assertEqual(dict(await self.matched(renegade))["r17"], False)

    async def test_a_car_a_model_reads_in_its_band_is_news_for_the_search_by_body_type(self):
        suv, renegade = await self.renegade_and_suv()
        FakeSource.results["kavak"] += [self.jeep("r18", 2018)]
        await self.crawl_only("body_type", None)                        # the Renegade's band: its search can't want it
        self.assertNotIn("r18", dict(await self.matched(renegade)))
        self.assertEqual(dict(await self.matched(suv))["r18"], False)
        await self.crawl_only("body_type", "suv")
        self.assertEqual(dict(await self.matched(suv))["r18"], False)

    async def test_a_sibling_model_s_band_read_leaves_the_car_news_for_its_own_search(self):
        # deruedas searches a Stepway within the Sandero: turned on, the band of
        # 'Stepway 2018-2020' brings a Sandero 2021 first, which 'Sandero 2019-2022' wants.
        stepway = await self.fiesta_alert(marcas=["Renault"], modelos=["Stepway"], anio_min=2018, anio_max=2020,
                                          sources=["deruedas"])
        sandero = await self.fiesta_alert(marcas=["Renault"], modelos=["Sandero"], anio_min=2019, anio_max=2022,
                                          sources=["deruedas"])
        await self.on_the_web(stepway, sandero)
        FakeSource.results["deruedas"] = [self.renault("st19", "Stepway", 2019), self.renault("sa20", "Sandero", 2020)]
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 0):
            await self.tick()
        FakeSource.results["deruedas"] += [self.renault("sa21", "Sandero", 2021)]
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 1):
            await self.sync()
            await self.crawl_only("model", "Stepway")
        [t] = await self.rows("SELECT id FROM crawl_targets WHERE model = 'Stepway'")
        mark = (await self.listing("sa21"))["attributes"]["_not_news"]
        self.assertEqual((mark["reason"], mark["target_id"]), ("band", t["id"]))
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 1):
            await self.crawl_only("model", "Sandero")
        self.assertEqual(dict(await self.matched(sandero))["sa21"], False)


class KavakPrefilterMemoryTests(BodyTypeCase):
    async def test_stock_the_prefilter_dropped_is_backfill_when_it_gets_in(self):
        suv = await self.body_alert(sources=["kavak"])
        FakeSource.results["kavak"] = [eco("cheap"), eco("expensive", precio=45_000.0)]
        await self.tick()                                               # first run: backfill
        [t] = await self.rows("SELECT prefilter_rejected FROM crawl_targets WHERE source = 'kavak'")
        self.assertEqual(t["prefilter_rejected"], ["expensive"])

        # A price cut lets the expensive one in, and a new car shows up: only that one is news.
        FakeSource.results["kavak"] = [eco("cheap"), eco("expensive", precio=19_000.0), eco("arrived")]
        await self.tick()
        self.assertEqual(await self.matched(suv), [("arrived", False), ("cheap", True), ("expensive", True)])
        [t] = await self.rows("SELECT prefilter_rejected FROM crawl_targets WHERE source = 'kavak'")
        self.assertEqual(t["prefilter_rejected"], [])


class ModelLessParityTests(BodyTypeCase):
    async def test_the_database_and_the_worker_agree_on_model_less(self):
        from intelligence.matching import model_less
        from test_body_type import MODEL_LESS_CASES
        async with db.connection() as cx:
            for filters, expected in MODEL_LESS_CASES:
                [row] = await (await cx.execute("SELECT public.search_is_model_less(%s) AS v",
                                                (Jsonb(filters),))).fetchall()
                self.assertIs(row["v"], expected, filters)
                self.assertIs(model_less(filters), row["v"], filters)

    async def test_malformed_filters_are_rejected(self):
        await self.body_alert()
        [user] = await self.rows("SELECT user_id FROM search_profiles LIMIT 1")
        async with db.connection() as cx:
            for filters in ({"make": False, "body_types": ["suv"], "price_max": 20_000},
                            {"make": "Ford", "model": ["Ka"]},
                            {"body_types": ["suv", 3], "price_max": 20_000}):
                with self.subTest(filters):
                    with self.assertRaisesRegex(Exception, "invalid_filters"):
                        async with cx.transaction():
                            await cx.execute(
                                "INSERT INTO search_profiles (user_id, name, filters) VALUES (%s, 'x', %s)",
                                (user["user_id"], Jsonb(filters)))


class ModelLessRematchTests(BodyTypeCase):
    async def _stored(self) -> None:
        await ingest([
            eco("ok", source="mercadolibre"),
            eco("ars", precio=15_000_000.0, moneda="ARS"),
            eco("expensive", precio=25_000.0),
            eco("old", anio=2010),
            eco("worn", km=200_000),
            eco("partial", price_partial=True, price_partial_reason="anticipo"),
            eco("stale"), eco("gone"),
            card("corolla", source="kavak", titulo="Toyota Corolla XEI 2.0", marca="Toyota", modelo="Corolla"),
            card("fiesta", source="kavak"),                              # body type unknown
        ], geocode=None)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '40 days' WHERE external_id = 'stale'")
            await cx.execute("UPDATE listings SET status = 'gone' WHERE external_id = 'gone'")

    async def test_the_sql_prefilter_leaves_out_what_matching_would_discard(self):
        await self._stored()

        async def found(**kw) -> list[str]:
            args = dict(days=30, year_min=2015, km_max=120_000, price_max=20_000, currency="USD",
                        fx_rate=TEST_FX_RATE)
            args.update(kw)
            return sorted(r["external_id"] for r in await repo_listings.recent_active_by_body(["suv"], **args))

        self.assertEqual(await found(), ["ars", "ok"])
        # In pesos: ARS 16.000.000 lets the ARS 15.000.000 one in, not USD 18.000 (ARS 18.000.000).
        self.assertEqual(await found(price_max=16_000_000, currency="ARS"), ["ars"])
        self.assertEqual(await found(sources=["kavak"]), ["ars"])
        self.assertEqual(await found(price_max=None, year_min=None, km_max=None),
                         ["ars", "expensive", "ok", "old", "worn"])
        # Without a rate a USD price can't be read in pesos: unknown, it passes.
        self.assertEqual(await found(fx_rate=None, price_max=16_000_000, currency="ARS"),
                         ["ars", "expensive", "ok"])
        self.assertEqual(sorted(r["external_id"] for r in await repo_listings.recent_active_by_body(
            ["sedan"], days=30)), ["corolla"])

    async def test_only_the_newest_matches_get_comparables(self):
        await self._stored()
        suv = await self.body_alert(anio_min=2015, km_max=120_000, sources=["kavak", "mercadolibre"])
        calls: list[list[int]] = []
        fetch_many = comparables.fetch_many

        async def counted(cx, ids, cfg=None):
            calls.append(list(ids))
            return await fetch_many(cx, ids, cfg)

        with patch.object(rematch, "MODEL_LESS_COMPARABLES", 1), \
                patch.object(comparables, "fetch_many", side_effect=counted):
            await rematch.run_pending()
        # Both are backfill; only the newest asked for its price reference.
        self.assertEqual(await self.matched(suv), [("ars", True), ("ok", True)])
        self.assertEqual([len(c) for c in calls], [1])

    async def test_a_new_search_by_body_type_is_backfilled_from_every_source(self):
        await self._stored()
        suv = await self.body_alert(anio_min=2015, km_max=120_000, sources=["kavak", "mercadolibre"])
        self.assertEqual([a["id"] for a in await db.pending_rematch()], [suv])

        await rematch.run_pending()

        self.assertEqual(await self.matched(suv), [("ars", True), ("ok", True)])
        self.assertEqual(await db.pending_rematch(), [])

    async def test_a_telegram_edit_keeps_the_body_types(self):
        suv = await self.body_alert(body=("suv", "pickup"))
        alert = await db.get_alert(suv)
        await db.update_alert(suv, "SUV", dict(alert["filters"], km_max=90_000))
        [row] = await self.rows("SELECT filters FROM search_profiles WHERE id = %s", suv)
        self.assertEqual((row["filters"]["body_types"], row["filters"]["km_max"]), (["suv", "pickup"], 90_000))
        self.assertIsNone(row["filters"]["make"])


class EnrichmentBodyTypeTests(BodyTypeCase):
    async def test_a_detail_that_fills_the_body_type_matches_the_searches_without_a_model(self):
        fiesta = await self.fiesta_alert()
        hatch = await self.body_alert(body=("hatchback",), sources=["mercadolibre"])
        await ingest([card("1")], geocode=None)
        await db.mark_seen(fiesta, [card("1").to_dict()])
        self.assertIsNone((await self.listing("1"))["body_type"])
        url = "https://example.test/mercadolibre/1"
        FakeSource.details[url] = ListingDetail(url, listing=card(
            "1", titulo="Ford Fiesta 1.6 Titanium", marca="Ford", modelo="Fiesta", version="1.6 Titanium",
            carroceria="Hatchback", descripcion="Único dueño."))

        result = await enrich.enrich_pass()

        [lid] = result.body_type_filled
        self.assertEqual((await self.listing("1"))["body_type"], "hatchback")
        self.assertEqual(await self.matched(hatch), [("1", True)])       # backfill: nothing notified
        self.assertEqual(await self.rows("SELECT id FROM notifications"), [])
        # Its bootstrap is still the rematch's.
        self.assertIn(hatch, [a["id"] for a in await db.pending_rematch()])
        self.assertEqual(await rematch.match_model_less([lid]), 1)        # idempotent: re-scored
        self.assertEqual(await self.matched(hatch), [("1", True)])
