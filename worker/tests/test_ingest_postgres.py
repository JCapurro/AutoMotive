"""F1 ingestion against the local Supabase Postgres (docs/TECHNICAL_PLAN.md, secciones 5.1–5.7).

Collectors are fakes; everything else — crawl targets, normalization, the
canonical upsert, snapshots, events, enrichment, watchlist, the Telegram
path — runs for real. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Awaitable, Callable
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import pytest
from psycopg.types.json import Jsonb

import collectors
import db
from collectors._http import Page
from collectors._recency import POLICY_VERSION
from collectors.base import BaseScraper, Listing, ListingDetail, SearchResults
from pgcase import TEST_FX_RATE, PostgresTestCase, requires_db
from intelligence import comparables
from intelligence.config import SCORING_VERSION
from notifications.channels.telegram import TelegramChannel
from notifications.channels.web import WebChannel
from notifications.links import Links
from notifications.ops import SourceAlerts
from notifications.service import Notifier
from db.repos import listings as repo_listings, raw_pages
from db.repos import runs as repo_runs, targets as repo_targets
from db.repos import config as app_config
from llm.schemas import ListingFacts
from pipeline import crawl, enrich, news, rematch, retention, scheduler, watchlist
from pipeline.ingest import ingest
from tools import reprocess

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866


def card(listing_id: str, source: str = "mercadolibre", **kw) -> Listing:
    base = dict(source=source, listing_id=listing_id, titulo=f"Ford Fiesta Titanium {listing_id}",
                url=f"https://example.test/{source}/{listing_id}", precio=10_000.0, moneda="USD",
                anio=2017, km=100_000)
    base.update(kw)
    return Listing(**base)


class FakeSource(BaseScraper):
    """Stands in for a collector: returns `results[name]`, serves `details[url]`
    (an exception there fails the fetch; one in `parse_errors[url]`, the parse).
    `during[name]` is awaited inside the next search of `name`, once, on the
    test's loop (`loop`): on Windows a search runs on the collectors' loop
    (collectors/_loop.py), where the pool can't be used."""
    results: dict[str, list[Listing]] = {}
    details: dict[str, ListingDetail | Exception] = {}
    parse_errors: dict[str, Exception] = {}
    searches: list[tuple[str, dict]] = []
    during: dict[str, Callable[[], Awaitable[None]]] = {}
    loop: asyncio.AbstractEventLoop | None = None

    async def search(self, filters: dict) -> list[Listing]:
        FakeSource.searches.append((self.name, filters))
        if (hook := FakeSource.during.pop(self.name, None)) is not None:
            await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(hook(), FakeSource.loop))
        outcome = FakeSource.results.get(self.name, [])
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, SearchResults):
            return SearchResults([replace(l) for l in outcome], complete=outcome.complete, reason=outcome.reason)
        return [replace(l) for l in outcome]

    async def fetch_detail_page(self, url: str) -> Page:
        outcome = FakeSource.details[url]
        if isinstance(outcome, Exception):
            raise outcome
        return Page(200, url, f"<html><body><script>x()</script><p>detalle {url}</p></body></html>")

    @staticmethod
    def parse_detail(html: str, url: str, status: int = 200) -> ListingDetail:
        if url in FakeSource.parse_errors:
            raise FakeSource.parse_errors[url]
        return replace(FakeSource.details[url])


def fake(name: str) -> type[FakeSource]:
    return type(f"Fake_{name}", (FakeSource,), {"name": name})


class _FakeBot:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.fail = fail

    async def send_message(self, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("telegram unavailable")
        self.sent.append(kwargs)


class IngestCase(PostgresTestCase):
    SOURCES = ("mercadolibre", "kavak")

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        FakeSource.results, FakeSource.details, FakeSource.searches = {}, {}, []
        FakeSource.parse_errors, FakeSource.during = {}, {}
        FakeSource.loop = asyncio.get_running_loop()
        for p in (patch.dict(collectors.REGISTRY, {s: fake(s) for s in self.SOURCES}, clear=True),
                  patch("normalization.geo.GEOCODING_ENABLED", False)):
            p.start()
            self.addCleanup(p.stop)
        async with db.connection() as cx:
            await cx.execute("UPDATE sources SET detail_interval_seconds = 0")

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE sources s SET detail_interval_seconds = v.seconds FROM (VALUES "
                             "('mercadolibre', 8), ('facebook', 30), ('v6', 5), ('kavak', 5), "
                             "('autocosmos', 5)) AS v (id, seconds) WHERE s.id = v.id")
        await super().asyncTearDown()

    # -- helpers -----------------------------------------------------------

    async def fiesta_alert(self, user: int = TG_USER, **filters) -> int:
        f = {"marcas": ["Ford"], "modelos": ["Fiesta"], "sources": ["mercadolibre"],
             "descuento_pct": 15}
        f.update(filters)
        [aid] = await db.create_alert(user_id=user, chat_id=user, name="Ford Fiesta", filters=f)
        return aid

    async def tick(self, bot=None, on_health=None, *, due: str = "true") -> int:
        """One crawl-loop tick with every target due (or the ones the SQL
        condition `due` names), no jitter."""
        async with db.connection() as cx:
            await cx.execute(f"UPDATE crawl_targets SET next_run_at = NULL WHERE {due}")
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        await rematch.run_pending()
        notifier = Notifier({"telegram": TelegramChannel(bot or _FakeBot(), Links()),
                             "web": WebChannel(Links())})
        return await crawl.crawl_due(scheduler.batch_handler(notifier), jitter_seconds=0, on_health=on_health)

    async def rows(self, sql: str, *params) -> list[dict]:
        async with db.connection() as cx:
            return await (await cx.execute(sql, params)).fetchall()

    async def listing(self, external_id: str) -> dict:
        [row] = await self.rows("SELECT * FROM listings WHERE external_id = %s", external_id)
        return row

    async def snapshots(self, external_id: str) -> list[str]:
        return [r["change_kind"] for r in await self.rows(
            "SELECT s.change_kind FROM listing_snapshots s JOIN listings l ON l.id = s.listing_id "
            " WHERE l.external_id = %s ORDER BY s.id", external_id)]


class CanonicalUpsertTests(IngestCase):
    async def test_missing_publication_keeps_first_detection_when_date_arrives_later(self):
        await ingest([card("1")], geocode=None)
        first = await self.listing("1")
        self.assertIsNone(first["published_at"])
        published = int(first["first_seen_at"].timestamp()) - 7 * 86400
        await ingest([card("1", published_at=published)], geocode=None)
        await ingest([card("1")], geocode=None)
        later = await self.listing("1")
        self.assertEqual(later["first_seen_at"], first["first_seen_at"])
        self.assertEqual(int(later["published_at"].timestamp()), published)
        self.assertEqual(await self.snapshots("1"), ["new"])

    async def test_two_runs_in_a_row_do_not_duplicate_and_first_seen_never_moves(self):
        await self.fiesta_alert()
        FakeSource.results["mercadolibre"] = [card("1"), card("2"), card("2"), card("3")]

        await self.tick()
        first = await self.listing("1")
        await self.tick()
        again = await self.listing("1")

        self.assertEqual(len(await self.rows("SELECT id FROM listings")), 3)
        self.assertEqual(await self.snapshots("1"), ["new"])          # nothing changed
        self.assertEqual(first["first_seen_at"], again["first_seen_at"])
        self.assertGreater(again["last_seen_at"], first["last_seen_at"])
        runs = await self.rows("SELECT status, found, new, updated FROM collector_runs ORDER BY id")
        self.assertEqual([tuple(r.values()) for r in runs], [("ok", 3, 3, 0), ("ok", 3, 0, 0)])

    async def test_simulated_price_change_snapshots_price_and_emits_price_drop(self):
        run1 = await ingest([card("1")], geocode=None)
        run2 = await ingest([card("1", precio=9_000.0)], geocode=None)      # -10%
        run3 = await ingest([card("1", precio=9_050.0)], geocode=None)      # up: no drop
        run4 = await ingest([card("1", precio=8_900.0, km=101_000)], geocode=None)   # -1.7%

        self.assertEqual([e.kind for e in run1.events], ["listing_new"])
        self.assertEqual([e.kind for e in run2.events], ["listing_updated", "price_drop"])
        drop = run2.events[1]
        self.assertEqual((drop.old_price, drop.new_price, drop.drop_pct), (10_000.0, 9_000.0, 10.0))
        self.assertEqual([e.kind for e in run3.events], ["listing_updated"])
        self.assertEqual([e.kind for e in run4.events], ["listing_updated"])   # under price_drop_min_pct
        self.assertEqual(run4.events[0].changes, ("price", "mileage"))
        self.assertEqual(await self.snapshots("1"), ["new", "price", "price", "price"])
        [snap] = await self.rows("SELECT price, price_usd, mileage_km FROM listing_snapshots "
                                 "ORDER BY id DESC LIMIT 1")
        self.assertEqual((float(snap["price"]), snap["mileage_km"]), (8_900.0, 101_000))
        row = await self.listing("1")
        self.assertEqual((float(row["price"]), row["mileage_km"]), (8_900.0, 101_000))

    async def test_first_seen_at_does_not_change_on_updates(self):
        await ingest([card("1")], geocode=None)
        before = await self.listing("1")
        await ingest([card("1", precio=9_500.0, titulo="Ford Fiesta Titanium impecable")], geocode=None)
        after = await self.listing("1")

        self.assertEqual(before["first_seen_at"], after["first_seen_at"])
        self.assertEqual(await self.snapshots("1"), ["new", "price"])   # one row per observation
        self.assertEqual(after["title"], "Ford Fiesta Titanium impecable")

    async def test_normalization_v2_stores_catalog_names_price_usd_and_freezes_the_rate(self):
        await ingest([card("1", titulo="Ford Ka 1.5 SEL", precio=12_000_000.0, moneda="ARS",
                           transmision="Manual")], geocode=None)
        row = await self.listing("1")

        # Title beats a search for "Ford Fiesta"; the catalog's spelling is stored.
        self.assertEqual((row["make"], row["model"], row["trim"], row["transmission"]),
                         ("Ford", "Ka", "SEL", "manual"))
        self.assertEqual(float(row["price_usd"]), 12_000_000 / TEST_FX_RATE)
        self.assertGreaterEqual(row["normalization_confidence"], 0.9)
        [fx] = await self.rows("SELECT kind, rate FROM fx_rates")
        self.assertEqual((fx["kind"], float(fx["rate"])), ("blue", TEST_FX_RATE))
        [snap] = await self.rows("SELECT fx_rate FROM listing_snapshots")
        self.assertEqual(float(snap["fx_rate"]), TEST_FX_RATE)

    async def test_a_listing_that_fails_to_normalize_is_logged_and_the_batch_goes_on(self):
        real = __import__("pipeline.ingest", fromlist=["normalize_listing"]).normalize_listing

        def flaky(item, **kw):
            if item.listing_id == "bad":
                raise ValueError("boom")
            return real(item, **kw)

        with patch("pipeline.ingest.normalize_listing", flaky):
            result = await ingest([card("ok"), card("bad")], geocode=None)

        self.assertEqual((result.found, result.new), (1, 1))
        [err] = await self.rows("SELECT stage, ref, error FROM pipeline_errors")
        self.assertEqual((err["stage"], err["ref"]), ("normalize", "mercadolibre:bad"))
        self.assertIn("boom", err["error"])


class RepostTests(IngestCase):
    async def test_same_car_republished_points_to_the_original_and_leaves_comparables(self):
        same_car = dict(km=112_300, ubicacion="Vicente López", vendedor_nombre="Juan Pérez")
        await ingest([card("A", **same_car)], geocode=None)
        result = await ingest([card("B", source="kavak", precio=9_600.0, **dict(same_car, km=111_900))],
                              geocode=None)
        await ingest([card("C", precio=7_000.0, **same_car)], geocode=None)     # 30% off: another car

        a, b, c = [await self.listing(x) for x in "ABC"]
        self.assertEqual(b["probable_repost_of"], a["id"])
        self.assertEqual(result.events[0].repost_of, a["id"])
        self.assertIsNone(c["probable_repost_of"])
        async with db.connection() as cx:
            ref = await comparables.fetch(cx, c["id"], {"min_n": 1})
        self.assertEqual((ref.n, ref.median), (1, 10_000.0))              # A only: B is A again

    async def test_old_listings_are_outside_the_window(self):
        await ingest([card("A", ubicacion="Munro")], geocode=None)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET first_seen_at = now() - interval '61 days'")
        await ingest([card("B", ubicacion="Munro")], geocode=None)
        self.assertIsNone((await self.listing("B"))["probable_repost_of"])


class CountAfterExpiryCrawlTests(IngestCase):
    """2.5: a search whose access ended keeps its model crawled once a day, and
    the new listings it would match are only counted (docs/MAILS_DE_PLAN.md).
    test_lifecycle_emails_postgres.py has the emails."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.saved = await self.rows("SELECT key, value FROM app_config "
                                     " WHERE key IN ('plan_limits', 'commercial_pilot', 'lifecycle_emails')")
        await self.execute("UPDATE app_config SET value = jsonb_set(value, '{enforced}', 'true') WHERE key = 'plan_limits'")
        await self.execute("UPDATE app_config SET value = '{\"enabled\": true}' WHERE key = 'commercial_pilot'")
        app_config.clear_config_cache()

    async def asyncTearDown(self) -> None:
        for row in self.saved:
            await self.execute("UPDATE app_config SET value = %s WHERE key = %s", Jsonb(row["value"]), row["key"])
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def execute(self, sql: str, *params) -> None:
        async with db.connection() as cx:
            await cx.execute(sql, params)

    async def web_search(self, filters: dict | None = None) -> tuple[str, int]:
        """A web account whose first search starts its 72 h trial (the plan triggers run)."""
        [user] = await self.rows(
            "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
            "        'authenticated', %s, now(), now()) RETURNING id::text AS id", f"{uuid4()}@automotive.test")
        [search] = await self.rows(
            "INSERT INTO search_profiles (user_id, name, filters) VALUES (%s, 'Ford Fiesta', %s) RETURNING id",
            user["id"], Jsonb(filters or {"make": "Ford", "model": "Fiesta", "sources": ["mercadolibre"]}))
        return user["id"], search["id"]

    async def end_trial(self, user: str) -> None:
        await self.execute("UPDATE profiles SET free_trial_started_at = now() - interval '73 hours' WHERE id = %s", user)

    async def test_an_ended_trial_is_crawled_once_a_day_and_only_counted(self):
        user, search = await self.web_search()
        FakeSource.results["mercadolibre"] = [card("A")]
        await self.tick()                                       # during the trial
        await self.execute("UPDATE listings SET first_seen_at = now() - interval '2 hours'")
        await self.end_trial(user)                              # an hour ago
        FakeSource.results["mercadolibre"] = [card("A"), card("B")]
        await self.tick()

        [target] = await self.rows("SELECT query, next_run_at - now() AS wait FROM crawl_targets")
        self.assertEqual((target["query"].get("count_only"), target["query"].get("count_profile_ids"),
                          target["query"].get("profile_ids")), (True, [search], None))
        self.assertGreater(target["wait"], timedelta(hours=23))
        self.assertEqual(await crawl.crawl_due(), 0)
        counted = await self.rows("SELECT l.external_id, e.level::text AS level FROM expired_search_matches e "
                                  "  JOIN listings l ON l.id = e.listing_id WHERE e.search_profile_id = %s", search)
        self.assertEqual([r["external_id"] for r in counted], ["B"])     # A was there before the end
        self.assertIn(counted[0]["level"], ("high", "good", "match", "low"))
        shown = await self.rows("SELECT l.external_id FROM matches m JOIN listings l ON l.id = m.listing_id "
                                " WHERE m.search_profile_id = %s", search)
        self.assertEqual([r["external_id"] for r in shown], ["A"])
        self.assertEqual(await self.rows("SELECT id FROM notifications WHERE user_id = %s", user), [])

    async def test_a_new_portal_first_pass_is_not_counted_on_its_next_runs(self):
        # deRuedas, 2026-10-14: its first pass was found again the next day,
        # first seen after the end, and counted as news.
        user, search = await self.web_search()
        await self.end_trial(user)
        FakeSource.results["mercadolibre"] = [card("A")]
        await self.tick()                                       # the target's first run: history
        FakeSource.results["mercadolibre"] = [card("A"), card("B")]
        await self.tick()
        counted = await self.rows("SELECT l.external_id FROM expired_search_matches e "
                                  "  JOIN listings l ON l.id = e.listing_id WHERE e.search_profile_id = %s", search)
        self.assertEqual([r["external_id"] for r in counted], ["B"])

    async def test_an_active_search_takes_the_model_back_at_once(self):
        user, search = await self.web_search()
        await self.end_trial(user)
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        await self.execute("UPDATE crawl_targets SET next_run_at = now() + interval '20 hours'")
        [target] = await self.rows("SELECT query FROM crawl_targets")
        self.assertTrue(target["query"]["count_only"])

        _, other = await self.web_search()
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        [target] = await self.rows("SELECT query, next_run_at FROM crawl_targets")
        self.assertEqual((target["query"].get("profile_ids"), target["query"].get("count_only")), ([other], None))
        self.assertIsNone(target["next_run_at"])               # due now, at the source's cadence

    @staticmethod
    def ka(listing_id: str, year: int) -> Listing:
        return card(listing_id, source="kavak", titulo=f"Ford Ka 1.5 SE {listing_id}", marca="Ford", modelo="Ka",
                    anio=year)

    async def band_read(self, *, classify_fails: bool = False) -> int:
        """A counted Ka search from 2005 rides an active one from 2010 on Kavak,
        which reads 2009 too (the reference band). The second read brings a
        new Ka 2009, which only the band read, and a new Ka 2011."""
        user, counted = await self.web_search({"make": "Ford", "model": "Ka", "year_min": 2005, "sources": ["kavak"]})
        await self.end_trial(user)
        _, active = await self.web_search({"make": "Ford", "model": "Ka", "year_min": 2010, "sources": ["kavak"]})
        FakeSource.results["kavak"] = [self.ka("A", 2012)]
        await self.tick()                                       # the target's first run: history
        [target] = await self.rows("SELECT query FROM crawl_targets WHERE active")
        self.assertEqual({k: target["query"].get(k) for k in ("year_min", "year_band", "profile_ids")},
                         {"year_min": 2010, "year_band": 1, "profile_ids": [active]})
        FakeSource.results["kavak"] = [self.ka("A", 2012), self.ka("old", 2009), self.ka("new", 2011)]
        if classify_fails:
            with patch.object(news, "_classify", AsyncMock(side_effect=RuntimeError("db"))):
                await self.tick()
        else:
            await self.tick()
        return counted

    async def counted(self, search: int) -> list[str]:
        return [r["external_id"] for r in await self.rows(
            "SELECT l.external_id FROM expired_search_matches e JOIN listings l ON l.id = e.listing_id "
            " WHERE e.search_profile_id = %s ORDER BY l.external_id", search)]

    async def test_a_band_row_is_not_counted_after_expiry(self):
        # The target read 2009 from its first run: a 2009 listed later carries
        # no mark, and this target still never counts its band.
        counted = await self.band_read()
        self.assertEqual(await self.counted(counted), ["new"])
        self.assertNotIn("_not_news", (await self.listing("old"))["attributes"])

    async def test_a_band_row_is_not_counted_when_classify_fails_nor_on_the_next_runs(self):
        counted = await self.band_read(classify_fails=True)
        [err] = await self.rows("SELECT stage FROM pipeline_errors")
        self.assertEqual(err["stage"], "news")
        self.assertNotIn("_not_news", (await self.listing("old"))["attributes"])
        self.assertEqual(await self.counted(counted), ["new"])
        await self.tick()                                       # unmarked, and still the band's
        self.assertEqual(await self.counted(counted), ["new"])

    async def test_turning_the_kind_off_stops_the_extra_crawl(self):
        user, _ = await self.web_search()
        await self.end_trial(user)
        await self.execute("UPDATE app_config SET value = jsonb_set(value, '{kinds,count_after_expiry}', 'false') "
                           " WHERE key = 'lifecycle_emails'")
        await self.tick()
        self.assertEqual(await self.rows("SELECT id FROM crawl_targets WHERE active"), [])
        self.assertEqual(FakeSource.searches, [])


class CrawlTargetsTests(IngestCase):
    async def test_publication_policy_resets_existing_bootstrap_once(self):
        await self.fiesta_alert()
        await self.tick()
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET query = query - 'publication_policy'")
        specs = await crawl.sync_targets(await db.enabled_profiles())
        [t] = await self.rows("SELECT id, first_run_done, next_run_at FROM crawl_targets")
        self.assertFalse(t["first_run_done"])
        self.assertIsNone(t["next_run_at"])
        await repo_targets.finish_target(t["id"], ok=True, retry_seconds=0)
        await repo_targets.sync_targets(specs)
        [t] = await self.rows("SELECT first_run_done, next_run_at FROM crawl_targets")
        self.assertTrue(t["first_run_done"])
        self.assertIsNotNone(t["next_run_at"])

    async def test_a_new_publication_policy_empties_the_date_memory(self):
        """Facebook's date memory (collectors/_recency.py) holds while `since` can't move back."""
        await self.fiesta_alert()
        [spec] = await crawl.sync_targets(await db.enabled_profiles())
        memory = ["1", "2@1700000000#1"]
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET first_run_done = true, prefilter_rejected = %s", (memory,))
        await repo_targets.sync_targets([replace(spec, query={**spec.query, "year_min": 2015})])
        [t] = await self.rows("SELECT first_run_done, prefilter_rejected FROM crawl_targets")
        self.assertEqual((t["first_run_done"], t["prefilter_rejected"]), (True, memory))
        await repo_targets.sync_targets([replace(spec, query={**spec.query, "year_min": 2015,
                                                              "publication_policy": POLICY_VERSION + 1})])
        [t] = await self.rows("SELECT first_run_done, prefilter_rejected FROM crawl_targets")
        self.assertEqual((t["first_run_done"], t["prefilter_rejected"]), (False, []))

    async def test_adding_the_band_keeps_the_bootstrap(self):
        """REFERENCE_YEAR_BAND is no new publication policy: targets keep their bootstrap and schedule."""
        await self.fiesta_alert(anio_min=2010, sources=["mercadolibre", "kavak"])
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 0):
            await crawl.sync_targets(await db.enabled_profiles())
        await self.execute("UPDATE crawl_targets SET first_run_done = true, next_run_at = now() + interval '7 minutes', "
                           "  prefilter_rejected = '{x}'")
        before = {t["source"]: t for t in await self.rows("SELECT * FROM crawl_targets")}
        self.assertNotIn("year_band", before["kavak"]["query"])

        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 1):
            await crawl.sync_targets(await db.enabled_profiles())
        for t in await self.rows("SELECT * FROM crawl_targets"):
            self.assertEqual((t["query"]["year_min"], t["query"]["year_band"]), (2010, 1), t["source"])
            self.assertEqual({k: v for k, v in t["query"].items() if k != "year_band"}, before[t["source"]]["query"])
            self.assertEqual((t["first_run_done"], t["next_run_at"], t["prefilter_rejected"]),
                             (True, before[t["source"]]["next_run_at"], ["x"]), t["source"])

    async def execute(self, sql: str, *params) -> None:
        async with db.connection() as cx:
            await cx.execute(sql, params)

    async def test_publication_dates_of_a_model_cover_its_longer_names_and_skip_stale_rows(self):
        """A Facebook search for Corolla also brings Corolla Cross (by text): its dates count too."""
        published = int(datetime.now(timezone.utc).timestamp()) - 3600
        toyota = dict(source="facebook", marca="Toyota", published_at=published)
        await ingest([card("1", titulo="Toyota Corolla XEI 2.0", modelo="Corolla", **toyota),
                      card("2", titulo="Toyota Corolla Cross XEI", modelo="Corolla Cross", **toyota),
                      card("3", source="facebook", published_at=published),          # a Ford Fiesta
                      card("4", titulo="Toyota Corolla SEG", modelo="Corolla", **toyota)], geocode=None)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '40 days' WHERE external_id = '4'")
        self.assertNotEqual((await self.listing("2"))["model"].lower(), "corolla")
        dates = await repo_targets.publication_dates({"source": "facebook", "make": "Toyota", "model": "Corolla"})
        self.assertEqual(dates, {"1": published, "2": published})

    async def test_failed_retry_preserves_successful_coverage_start(self):
        await self.fiesta_alert()
        await self.tick()
        [t] = await self.rows("SELECT id FROM crawl_targets")
        covered = datetime.now(timezone.utc) - timedelta(hours=2)
        await repo_targets.finish_target(t["id"], ok=True, retry_seconds=0, covered_until=covered)
        await repo_targets.finish_target(t["id"], ok=False, retry_seconds=900)
        [t] = await self.rows("SELECT first_run_done, last_run_at, next_run_at > now() AS later "
                             "FROM crawl_targets")
        self.assertTrue(t["first_run_done"] and t["later"])
        self.assertEqual(t["last_run_at"], covered)

    async def test_cost_does_not_grow_with_a_repeated_profile(self):
        await self.fiesta_alert(sources=["mercadolibre", "kavak"])
        await self.tick()
        one_profile = len(FakeSource.searches)

        await self.fiesta_alert(user=1, sources=["mercadolibre", "kavak"], km_max=90_000)
        FakeSource.searches.clear()
        await self.tick()

        self.assertEqual(one_profile, 2)
        self.assertEqual(len(FakeSource.searches), one_profile)
        targets = await self.rows("SELECT source, make, model, query FROM crawl_targets ORDER BY source")
        self.assertEqual([(t["source"], t["make"], t["model"]) for t in targets],
                         [("kavak", "Ford", "Fiesta"), ("mercadolibre", "Ford", "Fiesta")])
        self.assertNotIn("km_max", targets[0]["query"])        # one profile has no km bound
        self.assertEqual(len(targets[0]["query"]["profile_ids"]), 2)

    async def test_cadence_follows_the_source_interval(self):
        await self.fiesta_alert()
        await self.tick()
        [t] = await self.rows("SELECT last_run_at, next_run_at, first_run_done, "
                             "next_run_at > now() AS later, "
                             "next_run_at <= now() + interval '600 seconds' AS within_interval "
                             "FROM crawl_targets")

        self.assertTrue(t["first_run_done"])
        # Cadence follows completion; coverage follows the beginning of the scan.
        self.assertGreaterEqual(t["next_run_at"] - t["last_run_at"], timedelta(seconds=600))
        self.assertTrue(t["later"] and t["within_interval"])       # seed: ML 10 min
        self.assertEqual(await crawl.crawl_due(), 0)              # not due again yet

    async def test_targets_without_profiles_are_deactivated(self):
        aid = await self.fiesta_alert()
        await self.tick()
        await db.set_alert_active(aid, False)
        await crawl.sync_targets(await db.enabled_profiles())
        [t] = await self.rows("SELECT active FROM crawl_targets")
        self.assertFalse(t["active"])

    async def test_a_failed_run_is_recorded_and_retried(self):
        await self.fiesta_alert()
        FakeSource.results["mercadolibre"] = RuntimeError("login wall")
        await self.tick()

        [run] = await self.rows("SELECT status, error FROM collector_runs")
        [src] = await self.rows("SELECT consecutive_failures, last_ok_at FROM sources WHERE id = 'mercadolibre'")
        [t] = await self.rows("SELECT first_run_done, next_run_at > now() AS later FROM crawl_targets")
        self.assertEqual(run["status"], "failed")
        self.assertIn("login wall", run["error"])
        self.assertEqual((src["consecutive_failures"], src["last_ok_at"]), (1, None))
        self.assertEqual((t["first_run_done"], t["later"]), (False, True))

        FakeSource.results["mercadolibre"] = [card("1")]
        await self.tick()
        [src] = await self.rows("SELECT consecutive_failures, last_ok_at FROM sources WHERE id = 'mercadolibre'")
        self.assertEqual(src["consecutive_failures"], 0)
        self.assertIsNotNone(src["last_ok_at"])

    async def test_a_failing_source_alerts_the_admin_once_and_again_when_back(self):
        await self.fiesta_alert()
        admin = _FakeBot()
        alerts = SourceAlerts(admin, 777, "https://automotive.test")
        FakeSource.results["mercadolibre"] = RuntimeError("login wall")
        for _ in range(4):                                       # seed: alert after 3
            await self.tick(on_health=alerts.on_health)
        [src] = await self.rows("SELECT consecutive_failures FROM sources WHERE id = 'mercadolibre'")
        self.assertEqual(src["consecutive_failures"], 4)
        [msg] = admin.sent
        self.assertEqual(msg["chat_id"], 777)
        self.assertIn("<b>MercadoLibre</b> falló 3 veces seguidas", msg["text"])
        self.assertIn("RuntimeError: login wall", msg["text"])
        self.assertIn("https://automotive.test/admin/sources", msg["text"])

        FakeSource.results["mercadolibre"] = [card("1")]
        await self.tick(on_health=alerts.on_health)
        await self.tick(on_health=alerts.on_health)
        self.assertEqual(len(admin.sent), 2)
        self.assertIn("volvió a funcionar después de 4 fallas seguidas", admin.sent[1]["text"])

    async def test_the_admin_alert_never_breaks_the_crawl(self):
        await self.fiesta_alert()
        alerts = SourceAlerts(_FakeBot(fail=True), 777)
        FakeSource.results["mercadolibre"] = RuntimeError("login wall")
        for _ in range(3):
            await self.tick(on_health=alerts.on_health)
        FakeSource.results["mercadolibre"] = [card("1")]
        await self.tick(on_health=alerts.on_health)
        [n] = await self.rows("SELECT count(*) AS n FROM listings")
        self.assertEqual(n["n"], 1)


class TargetResetTests(IngestCase):
    """targets.sync_targets: what a change of spec does to a target's
    bootstrap, its last read (query._read) and Facebook's date memory."""
    READ = {"year_min": 2015, "km_max": 100_000}

    @staticmethod
    def spec(source: str = "kavak", **query) -> crawl.TargetSpec:
        if source in ("mercadolibre", "facebook"):
            query.setdefault("publication_policy", POLICY_VERSION)
        return crawl.TargetSpec(source, "Ford", "Fiesta", {"profile_ids": [1], **query})

    async def sync(self, *specs: crawl.TargetSpec, keep_count_only: bool = False) -> None:
        await repo_targets.sync_targets(specs, undated=news.UNDATED_SOURCES, keep_count_only=keep_count_only)

    async def back_after_a_day(self, *specs: crawl.TargetSpec) -> None:
        """The specs come back to targets deactivated over REACTIVATION_IDLE_SECONDS ago."""
        with patch.object(repo_targets, "REACTIVATION_IDLE_SECONDS", 0):
            await self.sync(*specs)

    async def target(self, source: str = "kavak") -> dict:
        [t] = await self.rows("SELECT id, query, active, first_run_done, prefilter_rejected, updated_at "
                              "  FROM crawl_targets WHERE source = %s", source)
        return t

    async def read_through(self, source: str = "kavak") -> None:
        """A complete run: it finishes the bootstrap and leaves what it read."""
        await repo_targets.finish_target((await self.target(source))["id"], ok=True, retry_seconds=0,
                                         read=self.READ)

    async def test_the_last_read_stays_and_a_spec_without_it_rewrites_nothing(self):
        await self.sync(self.spec(year_min=2015, km_max=100_000))
        await self.read_through()
        before = await self.target()
        await self.sync(self.spec(year_min=2015, km_max=100_000))
        after = await self.target()
        self.assertEqual((after["updated_at"], after["query"]["_read"]), (before["updated_at"], self.READ))
        # A wider search keeps the bootstrap and the read: the envelope tells what it brings.
        await self.sync(self.spec(year_min=2010, km_max=150_000))
        t = await self.target()
        self.assertEqual(t["query"], {"profile_ids": [1], "year_min": 2010, "km_max": 150_000, "_read": self.READ})
        self.assertTrue(t["first_run_done"])

    async def test_what_a_whole_stock_target_covered_stays_like_the_last_read(self):
        # query._covers (news.read_covers), {} for an inventory: kept across
        # edits, not a reason to rewrite, forgotten after a day inactive.
        suv = crawl.TargetSpec("kavak", None, None, {"year_max": 2014, "profile_ids": [2]}, body_type="suv")
        inventory = crawl.TargetSpec("autocity", None, None, {"inventory": True, "profile_ids": [2]})
        await self.sync(suv, inventory)
        for source, covers in (("kavak", {"year_max": 2014}), ("autocity", {})):
            await repo_targets.finish_target((await self.target(source))["id"], ok=True, retry_seconds=0,
                                             covers=covers)
        before = {s: await self.target(s) for s in ("kavak", "autocity")}
        await self.sync(suv, inventory)
        for source, t in before.items():
            self.assertEqual((await self.target(source))["updated_at"], t["updated_at"], source)
        wider = replace(suv, query={**suv.query, "year_max": 2022})
        await self.sync(wider, inventory)
        self.assertEqual((await self.target())["query"], {**wider.query, "_covers": {"year_max": 2014}})
        self.assertEqual((await self.target("autocity"))["query"]["_covers"], {})
        await self.sync()
        await self.back_after_a_day(wider, inventory)
        for source in ("kavak", "autocity"):
            self.assertNotIn("_covers", (await self.target(source))["query"], source)

    async def test_a_reactivated_undated_target_starts_over_without_its_read(self):
        # kavak has no publication dates: what it finds after a day without
        # searches was listed while nobody read it. v6 dates its listings and
        # Mercado Libre reads by date: their bootstrap holds.
        specs = [self.spec("kavak"), self.spec("v6"), self.spec("mercadolibre")]
        await self.sync(*specs)
        for spec in specs:
            await self.read_through(spec.source)
        await self.sync()
        self.assertEqual([t["active"] for t in await self.rows("SELECT active FROM crawl_targets")], [False] * 3)
        await self.back_after_a_day(*specs)
        for source, done in (("kavak", False), ("v6", True), ("mercadolibre", True)):
            t = await self.target(source)
            self.assertEqual((t["active"], t["first_run_done"], "_read" in t["query"]), (True, done, False), source)

    async def test_a_pause_of_a_moment_keeps_the_bootstrap_and_the_read(self):
        # A search paused and resumed, or a tick without the counted searches.
        await self.sync(self.spec())
        await self.read_through()
        await self.sync()
        self.assertFalse((await self.target())["active"])
        await self.sync(self.spec())
        t = await self.target()
        self.assertEqual((t["active"], t["first_run_done"], t["query"].get("_read")), (True, True, self.READ))

    async def test_count_only_targets_stay_when_the_counted_searches_cant_be_read(self):
        counted = crawl.TargetSpec("kavak", "Toyota", "Corolla", {"count_only": True, "count_profile_ids": [7]})
        await self.sync(self.spec(), counted)
        await self.sync(self.spec(), keep_count_only=True)
        targets = {(r["model"], r["active"]) for r in await self.rows("SELECT model, active FROM crawl_targets")}
        self.assertEqual(targets, {("Fiesta", True), ("Corolla", True)})
        await self.sync(self.spec())
        targets = {(r["model"], r["active"]) for r in await self.rows("SELECT model, active FROM crawl_targets")}
        self.assertEqual(targets, {("Fiesta", True), ("Corolla", False)})

    async def test_a_coverage_bump_resets_the_bootstrap_once_and_keeps_the_read(self):
        await self.sync(self.spec())
        await self.read_through()
        for coverage, done in ((2, False), (2, True), (3, False)):
            await self.sync(self.spec(coverage=coverage))
            t = await self.target()
            self.assertEqual((t["first_run_done"], t["query"].get("_read")), (done, self.READ), coverage)
            await self.read_through()
        # A collector that stops declaring it changes nothing either.
        await self.sync(self.spec())
        self.assertTrue((await self.target())["first_run_done"])

    async def test_a_coverage_bump_empties_facebook_s_date_memory(self):
        # Its window goes back to 30 days; what a body type's prefilter dropped still holds.
        memory = ["1", "2@1700000000#1"]
        suv = crawl.TargetSpec("kavak", None, None, {"year_min": 2015, "profile_ids": [2]}, body_type="suv")
        await self.sync(self.spec("facebook"), suv)
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET first_run_done = true, prefilter_rejected = %s", (memory,))
        await self.sync(self.spec("facebook", coverage=2), replace(suv, query={**suv.query, "coverage": 2}))
        fb, kavak = await self.target("facebook"), await self.target("kavak")
        self.assertEqual((fb["first_run_done"], fb["prefilter_rejected"]), (False, []))
        self.assertEqual((kavak["first_run_done"], kavak["prefilter_rejected"]), (False, memory))

    async def test_every_change_of_spec_through_the_one_update(self):
        """Plan 2.5: the UPDATE that E2 (date memory), E4 (_read, coverage,
        reactivation) and E5 (year_band) share, one change after the other."""
        async def state(source: str) -> dict:
            [t] = await self.rows("SELECT query, active, first_run_done, next_run_at, prefilter_rejected, "
                                  "  updated_at FROM crawl_targets WHERE source = %s", source)
            return t

        kavak, ml = self.spec(year_min=2015, km_max=100_000), self.spec("mercadolibre", year_min=2015, km_max=100_000)
        await self.sync(kavak, ml)
        for source in ("kavak", "mercadolibre"):
            await self.read_through(source)
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET prefilter_rejected = '{x}'")

        # Only _read tells the target from its spec: the row is not rewritten.
        before = {s: await state(s) for s in ("kavak", "mercadolibre")}
        await self.sync(kavak, ml)
        for source, t in before.items():
            self.assertEqual((await state(source))["updated_at"], t["updated_at"], source)

        # A new year_band keeps the bootstrap, the schedule, the date memory and the read.
        kavak, ml = (replace(s, query={**s.query, "year_band": 1}) for s in (kavak, ml))
        await self.sync(kavak, ml)
        for source, t in before.items():
            after = await state(source)
            self.assertEqual(after["query"], {**t["query"], "year_band": 1}, source)
            self.assertEqual((after["first_run_done"], after["next_run_at"], after["prefilter_rejected"]),
                             (True, t["next_run_at"], ["x"]), source)

        # A new publication policy, with a read there: Mercado Libre starts over
        # once and empties its date memory; the read stays, Kavak is untouched.
        ml = replace(ml, query={**ml.query, "publication_policy": POLICY_VERSION + 1})
        await self.sync(kavak, ml)
        t = await state("mercadolibre")
        self.assertEqual((t["first_run_done"], t["next_run_at"], t["prefilter_rejected"], t["query"]["_read"]),
                         (False, None, [], self.READ))
        self.assertTrue((await state("kavak"))["first_run_done"])

        # A coverage bump: Kavak starts over once and keeps its read and its memory.
        kavak = replace(kavak, query={**kavak.query, "coverage": 2})
        await self.sync(kavak, ml)
        t = await state("kavak")
        self.assertEqual((t["first_run_done"], t["query"]["_read"], t["prefilter_rejected"]), (False, self.READ, ["x"]))

        # A pause of a moment changes nothing.
        for source in ("kavak", "mercadolibre"):
            await self.read_through(source)
        await self.sync()
        await self.sync(kavak, ml)
        for source in ("kavak", "mercadolibre"):
            t = await state(source)
            self.assertEqual((t["active"], t["first_run_done"], t["query"]["_read"]), (True, True, self.READ), source)

        # A reactivation after a day drops the read; only the undated source starts over.
        await self.sync()
        await self.back_after_a_day(kavak, ml)
        for source, done in (("kavak", False), ("mercadolibre", True)):
            t = await state(source)
            self.assertEqual((t["active"], t["first_run_done"], "_read" in t["query"], t["query"].get("year_band")),
                             (True, done, False, 1), source)


class NotNewsCase(IngestCase):
    """pipeline/news.py on sources without publication dates: old stock read
    as new is backfill for every search and never notified."""
    SOURCES = ("mercadolibre", "kavak", "rosariogarage", "v6")
    # app_config.comparables.confirm_sources, whatever the test database has:
    # the sources whose reads are trusted whole (the reappearance needs it).
    TRUSTED = ["autocity", "carone", "deruedas", "gruporandazzo", "mardelusados", "rosariogarage"]

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        [self.comparables_config] = await self.rows("SELECT value FROM app_config WHERE key = 'comparables'")
        await self.execute("UPDATE app_config SET value = value || %s WHERE key = 'comparables'",
                           Jsonb({"confirm_sources": self.TRUSTED}))
        app_config.clear_config_cache()

    async def asyncTearDown(self) -> None:
        await self.execute("UPDATE app_config SET value = %s WHERE key = 'comparables'",
                           Jsonb(self.comparables_config["value"]))
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def execute(self, sql: str, *params) -> None:
        async with db.connection() as cx:
            await cx.execute(sql, params)

    async def market(self) -> None:
        """The comparables a first car alone needs, from a source no target reads."""
        await ingest(self.comps("mercadolibre"), geocode=None)

    async def fiesta_alert(self, user: int = TG_USER, **filters) -> int:
        """Notified on the web: search_profiles.channels defaults to email,
        and the Telegram account has none."""
        aid = await super().fiesta_alert(user, **filters)
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET channels = '{web}' WHERE id = %s", (aid,))
        return aid

    @staticmethod
    def comps(source: str, n: int = 6) -> list[Listing]:
        """A market around USD 12.000, distinct km (not reposts of each other)."""
        return [card(f"c{i}", source=source, precio=12_000.0 + i * 100, km=90_000 + i * 2_000) for i in range(n)]

    @staticmethod
    def deals(source: str, n: int, **kw) -> list[Listing]:
        """Cars 25 % below it: opportunities, if they are news."""
        return [card(f"d{i}", source=source, precio=9_000.0, km=91_000 + i * 2_000, **kw) for i in range(n)]

    async def notified(self) -> set[str]:
        return {r["external_id"] for r in await self.rows(
            "SELECT l.external_id FROM notifications n JOIN listings l ON l.id = n.listing_id")}

    async def live(self) -> set[str]:
        """Listings with a live (non-backfill) match."""
        return {r["external_id"] for r in await self.rows(
            "SELECT l.external_id FROM matches m JOIN listings l ON l.id = m.listing_id WHERE NOT m.is_backfill")}

    async def not_news(self, external_id: str) -> dict | None:
        return (await self.listing(external_id))["attributes"].get("_not_news")


class StepTests(NotNewsCase):
    async def test_a_read_that_brings_half_the_stock_again_is_backfill_for_everyone(self):
        # autocosmos Fox, 03/10: 2 → 16 after the search was widened.
        await self.fiesta_alert(sources=["kavak"])
        await self.fiesta_alert(user=1, sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 5)
        await self.tick()

        self.assertEqual(await self.notified(), set())
        self.assertEqual(await self.live(), set())
        [target] = await self.rows("SELECT id FROM crawl_targets")
        [run] = await self.rows("SELECT id FROM collector_runs ORDER BY id DESC LIMIT 1")
        self.assertEqual(await self.not_news("d0"), {"reason": "step", "run_id": run["id"],
                                                     "target_id": target["id"], "prev_id": None})
        self.assertEqual((await self.not_news("c0"))["reason"], "first_run")      # only for 2.5

    async def test_a_normal_day_of_new_listings_is_news(self):
        # rosariogarage Gol: 20 new of 181 is a normal day.
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak", 12)
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak", 12) + self.deals("kavak", 5)
        await self.tick()
        deals = {f"d{i}" for i in range(5)}
        self.assertEqual(await self.notified(), deals)
        self.assertEqual(await self.live(), deals)
        self.assertIsNone(await self.not_news("d0"))

    async def test_a_batch_that_fails_after_the_step_is_retried_without_notifying(self):
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 5)
        with patch.object(scheduler, "process_batch", AsyncMock(side_effect=RuntimeError("notifier down"))):
            await self.tick()
        [err] = await self.rows("SELECT stage FROM pipeline_errors")
        self.assertEqual(err["stage"], "notify")
        await self.tick()                       # the retry: nothing is listing_new anymore

        self.assertEqual(await self.notified(), set())
        self.assertEqual(await self.live(), set())
        self.assertEqual({r["external_id"] for r in await self.rows(
            "SELECT l.external_id FROM matches m JOIN listings l ON l.id = m.listing_id WHERE m.is_backfill")},
            {f"c{i}" for i in range(6)} | {f"d{i}" for i in range(5)})

    async def test_a_recent_publication_inside_a_step_is_news(self):
        # v6 dates its listings: a step doesn't silence what was just published.
        await self.fiesta_alert(sources=["v6"])
        FakeSource.results["v6"] = self.comps("v6")
        await self.tick()
        yesterday = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
        FakeSource.results["v6"] = (self.comps("v6") + self.deals("v6", 4)
                                    + [card("fresh", source="v6", precio=9_000.0, km=99_500, published_at=yesterday)])
        await self.tick()
        self.assertEqual(await self.notified(), {"fresh"})
        self.assertEqual((await self.not_news("d0"))["reason"], "step")
        self.assertIsNone(await self.not_news("fresh"))

    async def test_an_empty_first_run_does_not_bootstrap(self):
        # kavak Fox: its first run read 0 cars, the next one its whole stock.
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = []
        await self.tick()
        [t] = await self.rows("SELECT id, first_run_done, next_run_at > now() AS later FROM crawl_targets")
        self.assertEqual((t["first_run_done"], t["later"]), (False, True))

        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        [t] = await self.rows("SELECT id, first_run_done FROM crawl_targets")
        self.assertTrue(t["first_run_done"])
        self.assertEqual(await self.notified(), set())
        self.assertEqual((await self.not_news("c0"))["reason"], "first_run")
        self.assertEqual((await self.not_news("c0"))["target_id"], t["id"])

        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 1)
        await self.tick()
        self.assertEqual(await self.notified(), {"d0"})

    async def test_the_third_empty_read_ends_the_hold_and_the_first_car_is_news(self):
        # kavak Sentra read 0 for days: when a car shows up, it is new.
        await self.market()
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = []
        for done in (False, False, True):
            await self.tick()
            [t] = await self.rows("SELECT first_run_done FROM crawl_targets")
            self.assertEqual(t["first_run_done"], done)
        FakeSource.results["kavak"] = self.deals("kavak", 1)
        await self.tick()
        self.assertEqual(await self.notified(), {"d0"})

    async def test_a_target_that_never_loaded_gets_its_stock_as_a_step(self):
        # autocosmos Sentra answered three 403s as "0 results": the hold ended,
        # and the next read brings its whole stock.
        await self.market()
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = []
        for _ in range(3):
            await self.tick()
        FakeSource.results["kavak"] = self.deals("kavak", 5)
        await self.tick()
        self.assertEqual(await self.notified(), set())
        self.assertEqual((await self.not_news("d0"))["reason"], "step")

    async def test_a_dated_source_finishes_its_bootstrap_on_an_empty_read(self):
        # v6 Yaris read 0; its first car, published yesterday, is news.
        await self.market()
        await self.fiesta_alert(sources=["v6"])
        FakeSource.results["v6"] = []
        await self.tick()
        [t] = await self.rows("SELECT first_run_done FROM crawl_targets")
        self.assertTrue(t["first_run_done"])
        yesterday = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
        FakeSource.results["v6"] = [card("fresh", source="v6", precio=9_000.0, km=99_500, published_at=yesterday)]
        await self.tick()
        self.assertEqual(await self.notified(), {"fresh"})

    async def test_a_held_first_run_lets_a_recent_publication_through(self):
        # The searches already waited a run: a car dated yesterday is news, old stock isn't.
        await self.market()
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = []
        await self.tick()
        yesterday = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
        FakeSource.results["kavak"] = self.deals("kavak", 2) + [
            card("fresh", source="kavak", precio=9_000.0, km=99_500, published_at=yesterday)]
        await self.tick()
        self.assertEqual(await self.notified(), {"fresh"})
        self.assertEqual(await self.live(), {"fresh"})

    async def test_reads_that_found_nothing_are_not_the_step_s_base(self):
        # autocosmos took three blocks for "0 results": the next read's 6 new cars are news.
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        [t] = await self.rows("SELECT id FROM crawl_targets")
        for found in (60, 0, 0, 0):
            await repo_runs.finish_run(await repo_runs.start_run("kavak", t["id"]), ok=True, found=found)
        self.assertEqual(await repo_runs.recent_ok_found(t["id"]), 60)
        self.assertFalse(news.is_step(6, await repo_runs.recent_ok_found(t["id"])))

    async def test_what_a_failed_batch_already_classified_is_not_counted_again(self):
        # Three new cars, then the notifier fails; the next run brings three more: no step of six.
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 3)
        with patch.object(scheduler, "process_batch", AsyncMock(side_effect=RuntimeError("notifier down"))):
            await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 6)
        await self.tick()
        self.assertEqual(await self.notified(), {f"d{i}" for i in range(6)})

    async def test_a_cut_run_is_caught_up_past_a_run_that_failed_in_its_collector(self):
        # A restart cuts the step's run; after it, kavak times out once; then it reads fine.
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 5)
        with patch.object(crawl.news, "classify", AsyncMock(side_effect=RuntimeError("worker restarted"))):
            await self.tick()
        # What fail_orphan_runs does to it on the next start.
        await self.execute("UPDATE collector_runs SET status = 'failed', finished_at = now(), error = %s "
                           " WHERE status = 'running'", repo_runs.ORPHAN_ERROR)
        FakeSource.results["kavak"] = RuntimeError("page.goto: Timeout 30000ms exceeded")
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 5)
        await self.tick()
        self.assertEqual(await self.notified(), set())
        self.assertEqual(await self.live(), set())
        self.assertEqual((await self.not_news("d0"))["reason"], "step")

    async def test_a_run_cut_between_its_ingest_and_its_marks_is_caught_up_next_run(self):
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + self.deals("kavak", 5)
        with patch.object(crawl.news, "classify", AsyncMock(side_effect=RuntimeError("worker restarted"))):
            await self.tick()                   # stored, then cut: no marks, no batch
        self.assertIsNone(await self.not_news("d0"))
        await self.tick()
        self.assertEqual(await self.notified(), set())
        self.assertEqual(await self.live(), set())
        self.assertEqual((await self.not_news("d0"))["reason"], "step")


class EnvelopeTests(NotNewsCase):
    """A target whose search was widened: the stock its last complete read
    left out (crawl_targets.query._read) is backfill for every search."""
    READ = {"year_min": 2015, "km_max": 100_000}
    WIDE = {"year_min": 2014, "km_max": 150_000}

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        # The envelope alone, over the searches' exact years: the reference
        # band (REFERENCE_YEAR_BAND) has its own tests at the end.
        p = patch.object(crawl.config, "REFERENCE_YEAR_BAND", 0)
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def widened(source: str = "kavak") -> list[Listing]:
        """New cars 25 % below the market: one inside the last read, two it
        left out (2014, 120.000 km)."""
        return [card("in", source=source, precio=9_000.0, km=80_000),
                card("old", source=source, precio=9_000.0, anio=2014, km=95_000),
                card("far", source=source, precio=9_000.0, km=120_000)]

    async def read(self) -> dict | None:
        [t] = await self.rows("SELECT query FROM crawl_targets WHERE active")
        return t["query"].get("_read")

    async def matched(self, aid: int) -> dict[str, bool]:
        """external_id -> is_backfill of a search's matches."""
        return {r["external_id"]: r["is_backfill"] for r in await self.rows(
            "SELECT l.external_id, m.is_backfill FROM matches m JOIN listings l ON l.id = m.listing_id "
            " WHERE m.search_profile_id = %s", aid)}

    async def widen(self, aid: int) -> None:
        await self.execute("UPDATE search_profiles SET filters = filters || %s WHERE id = %s", Jsonb(self.WIDE), aid)

    async def test_a_widened_target_brings_its_new_stock_as_backfill_and_keeps_news_inside(self):
        # kavak Fiesta 05/10: year >= 2015 and km <= 100.000, then a search for 2014 and 150.000 km.
        first = await self.fiesta_alert(sources=["kavak"], anio_min=2015, km_max=100_000)
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        self.assertEqual(await self.read(), self.READ)
        wide = await self.fiesta_alert(user=1, sources=["kavak"], anio_min=2014, km_max=150_000)
        FakeSource.results["kavak"] = self.comps("kavak") + self.widened()
        await self.tick()

        self.assertEqual(await self.notified(), {"in"})
        self.assertEqual(await self.live(), {"in"})
        self.assertEqual({k: v for k, v in (await self.matched(wide)).items() if k in {"in", "old", "far"}},
                         {"in": False, "old": True, "far": True})
        self.assertFalse((await self.matched(first))["in"])
        [run] = await self.rows("SELECT id, target_id FROM collector_runs ORDER BY id DESC LIMIT 1")
        self.assertEqual(await self.not_news("old"), {"reason": "envelope", "run_id": run["id"],
                                                      "target_id": run["target_id"], "prev_id": None})
        self.assertEqual((await self.not_news("far"))["reason"], "envelope")
        self.assertIsNone(await self.not_news("in"))
        self.assertEqual(await self.read(), self.WIDE)

    async def test_a_model_less_search_gets_the_widening_as_backfill_too(self):
        def eco(listing_id: str, **kw) -> Listing:
            return card(listing_id, source="rosariogarage", titulo=f"Ford EcoSport 1.6 Freestyle {listing_id}",
                        marca="Ford", modelo="EcoSport", **kw)

        await self.fiesta_alert(modelos=["EcoSport"], sources=["rosariogarage"], anio_min=2015, km_max=100_000)
        [suv] = await db.create_alert(user_id=2, chat_id=2, name="suv", filters={
            "carroceria": ["suv"], "precio_max": 20_000, "moneda": "USD", "sources": ["rosariogarage"]})
        FakeSource.results["rosariogarage"] = [eco(f"c{i}", precio=12_000.0 + i * 100, km=90_000 + i * 2_000)
                                               for i in range(6)]
        await self.tick()
        await self.fiesta_alert(user=1, modelos=["EcoSport"], sources=["rosariogarage"], anio_min=2014,
                                km_max=150_000)
        FakeSource.results["rosariogarage"] += [eco("in", precio=9_000.0, km=80_000),
                                                eco("old", precio=9_000.0, anio=2014, km=95_000),
                                                eco("far", precio=9_000.0, km=120_000)]
        await self.tick()

        self.assertEqual({k: v for k, v in (await self.matched(suv)).items() if k in {"in", "old", "far"}},
                         {"in": False, "old": True, "far": True})
        self.assertEqual(await self.live(), {"in"})

    async def test_what_a_body_type_target_reads_whole_is_news_to_every_search(self):
        # kavak 'suv' reads every SUV on each run. A Ford EcoSport target
        # widened to 2012 sees a new EcoSport 2013 before it: new to kavak, not
        # stock the widening brings.
        def eco(listing_id: str, **kw) -> Listing:
            return card(listing_id, source="kavak", titulo=f"Ford EcoSport 1.6 Freestyle {listing_id}",
                        marca="Ford", modelo="EcoSport", **kw)

        collectors.REGISTRY["kavak"].BODY_TYPES = frozenset({"suv"})
        await self.fiesta_alert(modelos=["EcoSport"], sources=["kavak"], anio_min=2016)
        [suv] = await db.create_alert(user_id=2, chat_id=2, name="suv", filters={
            "carroceria": ["suv"], "precio_max": 20_000, "moneda": "USD", "sources": ["kavak"]})
        await self.execute("UPDATE search_profiles SET channels = '{web}' WHERE id = %s", suv)
        FakeSource.results["kavak"] = [eco(f"c{i}", precio=18_000.0 + i * 100, km=60_000 + i * 2_000)
                                       for i in range(6)]
        await self.tick()
        self.assertEqual({r["body_type"] for r in await self.rows("SELECT body_type FROM crawl_targets")},
                         {None, "suv"})
        wide = await self.fiesta_alert(user=1, modelos=["EcoSport"], sources=["kavak"], anio_min=2012)
        FakeSource.results["kavak"] += [eco("x", precio=12_000.0, anio=2013, km=80_000)]
        await self.tick(due="body_type IS NULL")       # the SUV target read before x was listed

        self.assertEqual((await self.listing("x"))["body_type"], "suv")
        self.assertIsNone(await self.not_news("x"))
        self.assertEqual(((await self.matched(suv)).get("x"), (await self.matched(wide)).get("x")), (False, False))

    async def test_a_body_type_target_covers_only_what_its_last_read_sent_its_collector(self):
        # kavak 'suv' up to 2014 sends its collector anio_max 2014, which drops
        # an EcoSport 2020 before the prefilter: never stored, never remembered.
        # Widened to 2022, the EcoSport target reads it: old stock, also once
        # the SUV search wants 2022 too, until the SUV target reads that.
        def eco(listing_id: str, **kw) -> Listing:
            return card(listing_id, source="kavak", titulo=f"Ford EcoSport 1.6 Freestyle {listing_id}",
                        marca="Ford", modelo="EcoSport", **kw)

        collectors.REGISTRY["kavak"].BODY_TYPES = frozenset({"suv"})
        ecosport = await self.fiesta_alert(modelos=["EcoSport"], sources=["kavak"], anio_min=2016, anio_max=2018)
        [suv] = await db.create_alert(user_id=2, chat_id=2, name="suv", filters={
            "carroceria": ["suv"], "anio_max": 2014, "precio_max": 20_000, "moneda": "USD", "sources": ["kavak"]})
        await self.execute("UPDATE search_profiles SET channels = '{web}' WHERE id = %s", suv)
        FakeSource.results["kavak"] = [eco(f"c{i}", precio=18_000.0 + i * 100, km=60_000 + i * 2_000)
                                       for i in range(6)]
        await self.tick()
        self.assertEqual({r["body_type"]: r["query"].get("_covers") for r in await self.rows(
            "SELECT body_type, query FROM crawl_targets")}, {None: None, "suv": {"year_max": 2014}})
        await self.execute("UPDATE search_profiles SET filters = filters || %s WHERE id = ANY(%s)",
                           Jsonb({"year_max": 2022}), [ecosport, suv])
        FakeSource.results["kavak"] += [eco("x", precio=12_000.0, anio=2020, km=80_000)]
        await self.tick(due="body_type IS NULL")

        self.assertEqual((await self.not_news("x"))["reason"], "envelope")
        self.assertEqual(((await self.matched(suv)).get("x"), (await self.matched(ecosport)).get("x")), (True, True))
        self.assertNotIn("x", await self.notified())

    async def test_the_envelope_is_the_claimed_query_not_the_current_one(self):
        aid = await self.fiesta_alert(sources=["kavak"], anio_min=2015, km_max=100_000)
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()

        async def widen() -> None:
            # The search is edited and the targets synced while kavak is being read.
            await self.widen(aid)
            await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        FakeSource.during["kavak"] = widen
        await self.tick()
        [t] = await self.rows("SELECT query FROM crawl_targets")
        self.assertEqual((t["query"]["year_min"], t["query"]["km_max"], t["query"]["_read"]),
                         (2014, 150_000, self.READ))

        FakeSource.results["kavak"] = self.comps("kavak") + self.widened()
        await self.tick()
        self.assertEqual(await self.live(), {"in"})
        self.assertEqual({(await self.not_news(e))["reason"] for e in ("old", "far")}, {"envelope"})

    async def test_an_incomplete_read_keeps_the_previous_envelope(self):
        aid = await self.fiesta_alert(sources=["kavak"], anio_min=2015, km_max=100_000)
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        await self.widen(aid)
        inside, old, far = self.widened()
        FakeSource.results["kavak"] = SearchResults(self.comps("kavak") + [old], complete=False,
                                                    reason="partial: page 2")
        await self.tick()
        self.assertEqual(await self.read(), self.READ)
        FakeSource.results["kavak"] = self.comps("kavak") + [inside, old, far]
        await self.tick()
        self.assertEqual(await self.read(), self.WIDE)
        # A 2014 car listed now is inside what the target reads: news.
        FakeSource.results["kavak"] = self.comps("kavak") + [inside, old, far, card(
            "fresh", source="kavak", precio=9_000.0, anio=2014, km=70_000)]
        await self.tick()

        self.assertEqual(await self.live(), {"in", "fresh"})
        self.assertEqual({(await self.not_news(e))["reason"] for e in ("old", "far")}, {"envelope"})

    async def test_the_read_includes_the_band_and_a_band_row_is_marked_once(self):
        # Searches from 2015 read 2014 too: a 2014 car listed later is news.
        # Widened to 2013, the target reads 2012: 2013 is the envelope's,
        # 2012 the band's, never both.
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 1):
            aid = await self.fiesta_alert(sources=["kavak"], anio_min=2015, km_max=100_000)
            FakeSource.results["kavak"] = self.comps("kavak")
            await self.tick()
            self.assertEqual(await self.read(), {"year_min": 2014, "km_max": 100_000})
            await self.execute("UPDATE search_profiles SET filters = filters || %s WHERE id = %s",
                               Jsonb({"year_min": 2013}), aid)
            FakeSource.results["kavak"] = self.comps("kavak") + [
                card(f"y{year}", source="kavak", precio=9_000.0, anio=year, km=95_000 + year)
                for year in (2014, 2013, 2012)]
            await self.tick()
        self.assertEqual(await self.read(), {"year_min": 2012, "km_max": 100_000})
        self.assertIsNone(await self.not_news("y2014"))
        self.assertEqual({e: (await self.not_news(e))["reason"] for e in ("y2013", "y2012")},
                         {"y2013": "envelope", "y2012": "band"})
        self.assertEqual(await self.live(), {"y2014"})

    async def test_the_band_s_first_read_marks_its_rows_band_not_envelope(self):
        # The deploy: the last read had the searches' exact years.
        await self.fiesta_alert(sources=["kavak"], anio_min=2015, km_max=100_000)
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        self.assertEqual(await self.read(), self.READ)
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 1):
            FakeSource.results["kavak"] = self.comps("kavak") + [
                card("y2014", source="kavak", precio=9_000.0, anio=2014, km=95_000)]
            await self.tick()
        self.assertEqual((await self.not_news("y2014"))["reason"], "band")
        self.assertEqual(await self.read(), {"year_min": 2014, "km_max": 100_000})
        self.assertEqual(await self.live(), set())

    async def test_a_cut_first_band_read_leaves_the_band_unread(self):
        # autocosmos EcoSport at the deploy: the band's first read loses its
        # page 2 (a partial read, collectors/autocosmos.py). It covered no
        # band year, so the 2014s that page had are still the band's first
        # read on the next run, not cars just listed.
        await self.fiesta_alert(sources=["kavak"], anio_min=2015, km_max=100_000)
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        band = [card(f"y{i}", source="kavak", precio=9_000.0, anio=2014, km=95_000 + i) for i in range(3)]
        with patch.object(crawl.config, "REFERENCE_YEAR_BAND", 1):
            FakeSource.results["kavak"] = SearchResults(self.comps("kavak") + band[:1], complete=False,
                                                        reason="autocosmos: página 2 respondió 403")
            await self.tick()
            self.assertEqual(await self.read(), self.READ)
            FakeSource.results["kavak"] = self.comps("kavak") + band
            await self.tick()
        self.assertEqual({(await self.not_news(f"y{i}"))["reason"] for i in range(3)}, {"band"})
        self.assertEqual(await self.read(), {"year_min": 2014, "km_max": 100_000})
        self.assertEqual(await self.live(), set())


class CoverageTests(NotNewsCase):
    async def test_a_target_back_after_a_day_starts_over_and_still_tells_its_price_drops(self):
        aid = await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        await db.set_alert_active(aid, False)
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        await db.set_alert_active(aid, True)
        FakeSource.results["kavak"] = ([card("c0", source="kavak", precio=11_000.0, km=90_000)]
                                       + self.comps("kavak")[1:] + self.deals("kavak", 1))
        with patch.object(repo_targets, "REACTIVATION_IDLE_SECONDS", 0):
            await self.tick()

        self.assertEqual((await self.not_news("d0"))["reason"], "first_run")
        self.assertEqual(await self.live(), set())
        self.assertEqual({(r["external_id"], r["kind"]) for r in await self.rows(
            "SELECT l.external_id, n.kind::text AS kind FROM notifications n JOIN listings l ON l.id = n.listing_id")},
            {("c0", "price_drop")})

    async def test_a_search_created_during_the_pause_gets_no_price_drop_from_before_it(self):
        # It never saw the old price: its match is this first run's backfill.
        aid = await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak")
        await self.tick()
        await db.set_alert_active(aid, False)
        await crawl.sync_targets(await db.enabled_profiles(), await db.counting_profiles())
        await db.set_alert_active(aid, True)
        late = await self.fiesta_alert(user=1, sources=["kavak"])
        [access] = await self.rows("SELECT public.commercial_access_active(user_id) AS ok FROM search_profiles "
                                   " WHERE id = %s", late)
        self.assertTrue(access["ok"])                   # else it would get nothing anyway
        FakeSource.results["kavak"] = ([card("c0", source="kavak", precio=11_000.0, km=90_000)]
                                       + self.comps("kavak")[1:])
        with patch.object(repo_targets, "REACTIVATION_IDLE_SECONDS", 0):
            await self.tick()

        self.assertEqual({(r["profile_id"], r["external_id"], r["kind"]) for r in await self.rows(
            "SELECT n.profile_id, l.external_id, n.kind::text AS kind FROM notifications n "
            "  JOIN listings l ON l.id = n.listing_id")}, {(aid, "c0", "price_drop")})
        [m] = await self.rows("SELECT m.is_backfill FROM matches m JOIN listings l ON l.id = m.listing_id "
                              " WHERE m.search_profile_id = %s AND l.external_id = 'c0'", late)
        self.assertTrue(m["is_backfill"])

    async def test_a_collector_that_reads_more_reloads_its_targets_in_silence(self):
        # E6: kavak reads every page of a model (COVERAGE_VERSION 2). The 4 cars
        # it finds now are no step, and they were listed before.
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak", 12)
        await self.tick()
        with patch.object(collectors.REGISTRY["kavak"], "COVERAGE_VERSION", 2):
            FakeSource.results["kavak"] = self.comps("kavak", 12) + self.deals("kavak", 4)
            await self.tick()
            self.assertEqual(await self.notified(), set())
            self.assertEqual(await self.live(), set())
            self.assertEqual((await self.not_news("d0"))["reason"], "first_run")
            FakeSource.results["kavak"] = self.comps("kavak", 12) + self.deals("kavak", 5)
            await self.tick()
        self.assertEqual(await self.notified(), {"d4"})
        [t] = await self.rows("SELECT query, first_run_done FROM crawl_targets")
        self.assertEqual((t["query"]["coverage"], t["first_run_done"]), (2, True))


class ReappearanceTests(NotNewsCase):
    """rosariogarage republishes a car under another ID: 7 notifications in
    23 days. The old copy has a location (it was enriched), the card doesn't,
    so the fingerprint (sección 5.4) misses it."""

    OLD = dict(source="rosariogarage", precio=9_000.0, km=88_000, vendedor_nombre="DOX Cars", ubicacion="Rosario")

    async def republish(self, read: list[Listing]) -> None:
        await self.fiesta_alert(sources=["rosariogarage"])
        FakeSource.results["rosariogarage"] = self.comps("rosariogarage") + [card("A", **self.OLD)]
        await self.tick()
        FakeSource.results["rosariogarage"] = read

    def copy(self, **kw) -> Listing:
        return card("B", **{**self.OLD, "ubicacion": None, **kw})

    async def test_a_card_republished_after_its_old_copy_vanished_is_backfill(self):
        await self.republish(self.comps("rosariogarage") + [self.copy()])
        await self.tick()
        self.assertEqual(await self.notified(), set())
        self.assertEqual(await self.live(), set())
        a, b = await self.listing("A"), await self.listing("B")
        self.assertEqual(((await self.not_news("B"))["reason"], (await self.not_news("B"))["prev_id"]),
                         ("reappearance", a["id"]))
        # Until comparables count the live copy (E3), the repost link waits for NEWS_LINK_REPOST.
        self.assertIsNone(b["probable_repost_of"])

    async def test_with_link_repost_it_points_to_the_copy_before(self):
        await self.republish(self.comps("rosariogarage") + [self.copy()])
        with patch("config.NEWS_LINK_REPOST", True):
            await self.tick()
        self.assertEqual((await self.listing("B"))["probable_repost_of"], (await self.listing("A"))["id"])

    async def test_with_link_repost_a_chain_of_copies_counts_once_in_comparables(self):
        # rosariogarage ML Automotores republishes its Fiesta every day.
        [pool] = await self.rows("SELECT to_regproc('public.comparable_listings') IS NOT NULL AS ok")
        if not pool["ok"]:
            self.skipTest("the test database predates 20261105120000_comparables_confirmed_pool.sql")
        await self.fiesta_alert(sources=["rosariogarage"])
        with patch("config.NEWS_LINK_REPOST", True):
            # Another place each: no fingerprint ties them (sección 5.4).
            for copy_id, place in (("R", "Rosario"), ("O", "Funes"), ("N", None)):
                FakeSource.results["rosariogarage"] = self.comps("rosariogarage") + [
                    card(copy_id, **{**self.OLD, "ubicacion": place})]
                await self.tick()
        r, o, n = [await self.listing(x) for x in "RON"]
        self.assertEqual((o["probable_repost_of"], n["probable_repost_of"]), (r["id"], o["id"]))
        # R left days ago: the target's later complete reads no longer confirm it.
        await self.execute("UPDATE listings SET first_seen_at = now() - interval '4 days', "
                           "  last_seen_at = now() - interval '3 days' WHERE external_id = 'R'")
        c0 = (await self.listing("c0"))["id"]
        counted = {row["external_id"] for row in await self.rows(
            "SELECT external_id FROM public.comparable_listings(%s)", c0)}
        self.assertEqual(counted & {"R", "O", "N"}, {"O"})
        async with db.connection() as cx:
            ref = await comparables.fetch(cx, c0, {"min_n": 1})
        self.assertEqual(ref.n, 6)                                    # c1-c5 and the car, once

    async def test_a_source_whose_reads_are_cut_short_never_infers_a_vanished_copy(self):
        # kavak stops at 30 cards: the other unit may be past the cut, still for sale.
        twin = dict(source="kavak", precio=9_000.0, km=88_000, vendedor_nombre="Kavak", ubicacion="CABA")
        await self.fiesta_alert(sources=["kavak"])
        FakeSource.results["kavak"] = self.comps("kavak") + [card("A", **twin)]
        await self.tick()
        FakeSource.results["kavak"] = self.comps("kavak") + [card("B", **{**twin, "ubicacion": None})]
        await self.tick()
        self.assertEqual(await self.notified(), {"B"})
        self.assertIsNone(await self.not_news("B"))

    async def test_twins_in_the_same_read_are_both_news(self):
        # A dealer's two identical units: the old copy is still listed.
        await self.republish(self.comps("rosariogarage") + [card("A", **self.OLD), self.copy()])
        await self.tick()
        self.assertEqual(await self.notified(), {"B"})
        self.assertIsNone(await self.not_news("B"))

    async def test_a_republish_3pct_cheaper_is_notified_as_republished(self):
        await self.republish(self.comps("rosariogarage") + [self.copy(precio=8_700.0)])
        await self.tick()
        [n] = await self.rows("SELECT DISTINCT n.kind::text AS kind, n.payload->>'repost' AS repost "
                              "  FROM notifications n JOIN listings l ON l.id = n.listing_id WHERE l.external_id = 'B'")
        self.assertEqual((n["kind"], n["repost"]), ("new_match", "true"))
        b = await self.listing("B")
        self.assertIsNone(b["attributes"].get("_not_news"))
        self.assertEqual(b["attributes"]["_republished"]["prev_id"], (await self.listing("A"))["id"])

    async def test_an_incomplete_read_never_infers_a_vanished_copy(self):
        await self.republish(SearchResults(self.comps("rosariogarage") + [self.copy()], complete=False,
                                           reason="partial: page 2"))
        await self.tick()
        self.assertEqual(await self.notified(), {"B"})


class FindReappearedTests(NotNewsCase):
    """listings.find_reappeared: who counts as the same car."""
    SOURCES = ("rosariogarage", "autocity", "gruporandazzo")

    async def old_copy(self, new: Listing, *old: Listing, read: tuple[str, ...] = ()) -> str | None:
        """The old copy find_reappeared picks for `new` among `old`, ingested
        before it; `read` are the other IDs the same read brought."""
        await ingest(list(old), geocode=None)
        await ingest([new], geocode=None)
        return await self.find(new.listing_id, *read)

    async def find(self, external_id: str, *read: str) -> str | None:
        async with db.connection() as cx:
            [row] = await repo_listings.new_rows(cx, [(await self.listing(external_id))["id"]])
            found = await repo_listings.find_reappeared(cx, row, batch_external_ids=[external_id, *read],
                                                        window_days=60, price_tol_pct=10, km_tol=100,
                                                        unsellered_hours=72)
        if found is None:
            return None
        [r] = await self.rows("SELECT external_id FROM listings WHERE id = %s", found["id"])
        return r["external_id"]

    @staticmethod
    def car(listing_id: str, source: str = "rosariogarage", **kw) -> Listing:
        return card(listing_id, source=source, **{"precio": 9_000.0, "km": 88_000, "vendedor_nombre": "DOX Cars",
                                                  **kw})

    async def test_the_same_seller_within_100_km(self):
        self.assertEqual(await self.old_copy(self.car("new", km=88_100), self.car("old")), "old")

    async def test_km_off_by_more_than_100_is_another_car(self):
        self.assertIsNone(await self.old_copy(self.car("new", km=88_101), self.car("old")))

    async def test_without_seller_only_the_exact_km_reappears(self):
        self.assertIsNone(await self.old_copy(self.car("n1", km=88_050, vendedor_nombre=None),
                                              self.car("o1", vendedor_nombre=None)))
        self.assertEqual(await self.old_copy(self.car("n2", anio=2016, vendedor_nombre=None),
                                             self.car("o2", anio=2016, vendedor_nombre=None)), "o2")

    async def test_another_seller_gearbox_or_price_is_another_car(self):
        # One year each, so the cars of one case can't be the old copy of another.
        self.assertIsNone(await self.old_copy(self.car("n1", anio=2015, vendedor_nombre="Ivan"),
                                              self.car("o1", anio=2015)))
        self.assertIsNone(await self.old_copy(self.car("n2", anio=2016, transmision="Automática"),
                                              self.car("o2", anio=2016, transmision="Manual")))
        self.assertIsNone(await self.old_copy(self.car("n3", anio=2018, precio=10_000.0),
                                              self.car("o3", anio=2018)))                          # +11 %
        self.assertEqual(await self.old_copy(self.car("n4", anio=2019, transmision="Automática"),
                                             self.car("o4", anio=2019)), "o4")                     # unknown gearbox

    async def test_a_version_that_starts_the_other_is_compatible(self):
        # rosariogarage AUTODESCO's Etios: 'XLS' on the old copy, 'XLS Pack' on the new one.
        await ingest([self.car("old"), self.car("new")], geocode=None)
        await self.execute("UPDATE listings SET trim = CASE external_id WHEN 'old' THEN 'XLS' ELSE 'XLS Pack' END")
        self.assertEqual(await self.find("new"), "old")
        await self.execute("UPDATE listings SET trim = 'GLI' WHERE external_id = 'old'")
        self.assertIsNone(await self.find("new"))

    async def test_a_version_that_only_starts_with_the_other_s_letters_is_another_car(self):
        # Chevrolet LT and LTZ, Ford SEL and S: another version, another car.
        for i, (old, new) in enumerate((("LT", "LTZ"), ("SEL", "S"))):
            with self.subTest(old=old, new=new):
                await ingest([self.car(f"o{i}", anio=2015 + i), self.car(f"n{i}", anio=2015 + i)], geocode=None)
                await self.execute("UPDATE listings SET trim = %s WHERE external_id = %s", old, f"o{i}")
                await self.execute("UPDATE listings SET trim = %s WHERE external_id = %s", new, f"n{i}")
                self.assertIsNone(await self.find(f"n{i}"))

    async def test_without_seller_an_old_copy_seen_days_ago_needs_the_same_title(self):
        # Private sellers round their km: two Fiestas of 88.000 km are often two cars.
        await ingest([self.car("old", vendedor_nombre=None, titulo="Ford Fiesta Titanium dueño directo")],
                     geocode=None)
        await self.execute("UPDATE listings SET last_seen_at = now() - interval '4 days'")
        await ingest([self.car("other", vendedor_nombre=None, titulo="Ford Fiesta Titanium escucho ofertas")],
                     geocode=None)
        self.assertIsNone(await self.find("other"))
        await ingest([self.car("again", vendedor_nombre=None, titulo="Ford  Fiesta Titanium Dueño directo")],
                     geocode=None)
        self.assertEqual(await self.find("again", "other"), "old")

    async def test_without_seller_a_copy_seen_within_72_hours_reappears(self):
        await ingest([self.car("old", vendedor_nombre=None, titulo="Ford Fiesta Titanium impecable")], geocode=None)
        await self.execute("UPDATE listings SET last_seen_at = now() - interval '60 hours'")
        await ingest([self.car("new", vendedor_nombre=None)], geocode=None)
        self.assertEqual(await self.find("new"), "old")

    async def test_a_copy_still_in_the_read_is_not_an_old_one(self):
        self.assertIsNone(await self.old_copy(self.car("new"), self.car("old"), read=("old",)))

    async def test_a_copy_unseen_for_60_days_is_too_old(self):
        await ingest([self.car("old")], geocode=None)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '61 days'")
        self.assertIsNone(await self.old_copy(self.car("new")))

    async def test_under_1000_km_never_reappears(self):
        # Many 0 km cars look alike.
        self.assertIsNone(await self.old_copy(self.car("new", km=500), self.car("old", km=500)))

    async def test_another_photo_on_autocity_is_another_car(self):
        # A dealer lists the same model, year and km twice: the photo tells the units apart.
        photo = dict(source="autocity", vendedor_nombre="Autocity")
        self.assertIsNone(await self.old_copy(self.car("n1", imagenes=["https://cdn.test/b.jpg"], **photo),
                                              self.car("o1", imagenes=["https://cdn.test/a.jpg"], **photo)))
        self.assertEqual(await self.old_copy(self.car("n2", imagenes=["https://cdn.test/c.jpg"], **photo),
                                             self.car("o2", imagenes=["https://cdn.test/c.jpg"], **photo)), "o2")

    async def test_another_plate_on_gruporandazzo_is_another_car(self):
        plate = dict(source="gruporandazzo", vendedor_nombre="Grupo Randazzo")
        self.assertIsNone(await self.old_copy(self.car("AB123CD_2", **plate), self.car("AB999ZZ_1", **plate)))
        self.assertEqual(await self.old_copy(self.car("AC456EF_9", **plate), self.car("AC456EF_3", **plate)),
                         "AC456EF_3")


class TelegramAlertsTests(IngestCase):
    """The crawl feeds the notification engine (sección 7): silent first run,
    one alert per new match at or above notify_min_level (good by default),
    nothing twice."""

    async def test_first_target_run_is_silent_then_new_opportunities_alert_once(self):
        aid = await self.fiesta_alert()
        # Six comparables around USD 12.000 give a market median. Distinct km, or
        # the repost detector would (rightly) take them for the same car.
        FakeSource.results["mercadolibre"] = [card(f"c{i}", precio=12_000.0 + i * 100, km=90_000 + i * 3_000) for i in range(6)]
        bot = _FakeBot()

        await self.tick(bot)
        self.assertEqual(bot.sent, [])
        FakeSource.results["mercadolibre"] += [card("deal", precio=9_000.0),     # 27% below median: high
                                               card("meh", precio=11_800.0, km=120_000),
                                               card("ka", titulo="Ford Ka SE 2017", precio=5_000.0)]
        await self.tick(bot)
        await self.tick(bot)                                                     # nothing new

        [text] = [m["text"] for m in bot.sent if "Nueva oportunidad" in m["text"]]
        self.assertTrue(text.startswith("<b>🔥 Nueva oportunidad</b>\n<b>Ford Fiesta Titanium 2017</b>"))
        self.assertIn("% debajo de publicaciones comparables.", text)          # n=7: c0–c5 + meh
        sent = await self.rows("SELECT l.external_id, n.kind::text AS kind, n.status::text AS status "
                               "  FROM notifications n JOIN listings l ON l.id = n.listing_id "
                               " WHERE n.channel = 'telegram'")
        rows = await self.rows("SELECT l.external_id, m.is_backfill, m.price_ref, m.level, m.score, "
                               "       m.scoring_version, m.match_reasons FROM matches m "
                               "JOIN listings l ON l.id = m.listing_id ORDER BY m.id")
        self.assertEqual({r["external_id"] for r in rows if r["is_backfill"]}, {f"c{i}" for i in range(6)})
        deal = next(r for r in rows if r["external_id"] == "deal")
        self.assertEqual((deal["level"], deal["scoring_version"]), ("high", SCORING_VERSION))
        self.assertEqual((deal["price_ref"]["n"], deal["price_ref"]["level_used"]), (7, "model"))
        self.assertEqual(deal["match_reasons"]["model"]["result"], "ok")
        meh = next(r for r in rows if r["external_id"] == "meh")
        self.assertNotEqual(meh["level"], "high")
        # 🔥 deal is an opportunity; meh alerts only at notify_min_level (good) or more.
        expected = {"deal": "opportunity", **({"meh": "new_match"} if meh["level"] == "good" else {})}
        self.assertEqual({r["external_id"]: r["kind"] for r in sent}, expected)
        self.assertEqual({r["status"] for r in sent}, {"sent"})
        self.assertEqual(len(bot.sent), len(expected))
        # A Ka found by the Fiesta search is stored as a Ka, not matched to the Fiesta alert.
        self.assertNotIn("ka", {r["external_id"] for r in rows})
        self.assertEqual((await db.get_alert(aid))["bootstrapped"], 1)

    async def test_a_price_drop_of_a_matched_listing_alerts_through_the_crawl(self):
        await self.fiesta_alert()
        FakeSource.results["mercadolibre"] = [card(f"c{i}", precio=12_000.0 + i * 100, km=90_000 + i * 3_000) for i in range(6)]
        await self.tick()
        bot = _FakeBot()
        FakeSource.results["mercadolibre"][0] = card("c0", precio=11_000.0, km=90_000)   # -8,3%
        await self.tick(bot)

        [msg] = bot.sent
        self.assertTrue(msg["text"].startswith("<b>📉 Bajó de precio</b>\n<b>Ford Fiesta Titanium 2017</b>\n"
                                               "Antes: USD 12.000\nAhora: USD 11.000\n-8,3%\n"))
        await self.tick(bot)                                                     # same price: nothing
        self.assertEqual(len(bot.sent), 1)

    async def test_failed_delivery_is_retried_on_the_next_run(self):
        await self.fiesta_alert()
        FakeSource.results["mercadolibre"] = [card(f"c{i}", precio=12_000.0 + i * 100, km=90_000 + i * 3_000) for i in range(6)]
        await self.tick()
        FakeSource.results["mercadolibre"].append(card("deal", precio=9_000.0))

        await self.tick(_FakeBot(fail=True))
        ok = _FakeBot()
        await self.tick(ok)

        self.assertEqual(len(ok.sent), 1)
        self.assertIn("Nueva oportunidad", ok.sent[0]["text"])
        [n] = await self.rows("SELECT status::text AS status, attempts FROM notifications "
                              "WHERE channel = 'telegram'")
        self.assertEqual((n["status"], n["attempts"]), ("sent", 2))

    async def test_a_new_profile_on_an_existing_target_is_bootstrapped_from_stored_listings(self):
        await self.fiesta_alert()
        FakeSource.results["mercadolibre"] = [card("1"), card("2", km=200_000)]
        await self.tick()

        aid = await self.fiesta_alert(user=1, km_max=150_000)
        self.assertEqual([a["id"] for a in await db.pending_rematch()], [aid])
        await rematch.run_pending()

        rows = await self.rows("SELECT l.external_id, m.is_backfill FROM matches m "
                               "JOIN listings l ON l.id = m.listing_id WHERE m.search_profile_id = %s", aid)
        self.assertEqual([(r["external_id"], r["is_backfill"]) for r in rows], [("1", True)])
        self.assertEqual(await db.pending_rematch(), [])

        await db.update_alert(aid, "Ford Fiesta", {"marcas": ["Ford"], "modelos": ["Fiesta"],
                                                   "sources": ["mercadolibre"]})
        await rematch.run_pending()                              # edited: wider km, silently
        rows = await self.rows("SELECT count(*) AS n FROM matches WHERE search_profile_id = %s "
                               "AND is_backfill", aid)
        self.assertEqual(rows[0]["n"], 2)


class EnrichmentTests(IngestCase):
    async def _matched(self, *ids: str, backfill: bool = False) -> int:
        aid = await self.fiesta_alert()
        await ingest([card(i) for i in ids], geocode=None)
        await db.mark_seen(aid, [card(i).to_dict() for i in ids], backfill=backfill)
        return aid

    def _detail(self, listing_id: str, **kw) -> None:
        url = f"https://example.test/mercadolibre/{listing_id}"
        FakeSource.details[url] = ListingDetail(url, listing=card(
            listing_id, titulo="Ford Fiesta 1.6 Titanium", marca="Ford", modelo="Fiesta",
            version="1.6 Titanium", transmision="Manual", vendedor="Particular",
            descripcion="Único dueño, services oficiales.", imagenes=["1.jpg", "2.jpg", "3.jpg"], **kw))

    async def test_only_listings_with_a_match_are_enriched(self):
        await self._matched("1")
        await ingest([card("2")], geocode=None)          # no match: never fetched
        self._detail("1")

        result = await enrich.enrich_pass()

        one, two = await self.listing("1"), await self.listing("2")
        self.assertIsNotNone(one["enriched_at"])
        self.assertIsNone(two["enriched_at"])
        self.assertEqual((one["description"], one["seller_type"], one["transmission"]),
                         ("Único dueño, services oficiales.", "private", "manual"))
        self.assertEqual(len(one["images"]), 3)
        self.assertEqual(await self.snapshots("1"), ["new", "description"])
        self.assertEqual([e.kind for e in result.events], ["listing_updated"])
        self.assertEqual(await enrich.enrich_pass(), enrich.IngestResult())   # done: not refetched

    async def test_a_gone_page_marks_the_listing_gone(self):
        await self._matched("1")
        FakeSource.details["https://example.test/mercadolibre/1"] = ListingDetail(
            "https://example.test/mercadolibre/1", gone=True, gone_reason="404")

        result = await enrich.enrich_pass()

        self.assertEqual((await self.listing("1"))["status"], "gone")
        self.assertEqual([e.kind for e in result.events], ["listing_gone"])
        await ingest([card("1")], geocode=None)            # seen again in a search
        self.assertEqual((await self.listing("1"))["status"], "active")

    async def test_a_failed_fetch_is_logged_and_waits(self):
        await self._matched("1")
        FakeSource.details["https://example.test/mercadolibre/1"] = RuntimeError("timeout")

        await enrich.enrich_pass()

        [err] = await self.rows("SELECT stage FROM pipeline_errors")
        self.assertEqual(err["stage"], "enrich")
        row = await self.listing("1")
        self.assertIsNone(row["enriched_at"])
        self.assertIsNotNone(row["detail_checked_at"])
        self.assertEqual((await enrich.enrich_pass()).found, 0)        # retried hours later, not now

    async def test_card_crawls_after_enrichment_keep_the_detail(self):
        await self._matched("1")
        self._detail("1")
        await enrich.enrich_pass()

        result = await ingest([card("1", precio=9_000.0)], geocode=None)

        row = await self.listing("1")
        self.assertEqual(row["title"], "Ford Fiesta 1.6 Titanium")
        self.assertEqual(len(row["images"]), 3)
        self.assertEqual(result.events[0].changes, ("price",))


class EnrichmentBandTests(IngestCase):
    """The reference year band's rows (pipeline/crawl.py) are read for their
    version and transmission, which comparables() wants, without the LLM."""
    SOURCES = ("mercadolibre", "deruedas", "facebook")

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        collectors.REGISTRY["facebook"].YEAR_BAND = False                # as the real one

    @staticmethod
    def ka(listing_id: str, year: int, source: str = "deruedas", **kw) -> Listing:
        return card(listing_id, source=source, titulo=f"Ford Ka 1.5 SE {listing_id}", marca="Ford", modelo="Ka",
                    anio=year, **kw)

    async def test_the_queue_takes_band_rows_without_a_transmission_and_reads_them_without_the_llm(self):
        aid = await self.fiesta_alert(marcas=["Ford"], modelos=["Ka"], anio_min=2010, sources=["deruedas", "facebook"])
        await crawl.sync_targets(await db.enabled_profiles())
        queries = {t["source"]: t["query"] for t in await self.rows("SELECT source, query FROM crawl_targets")}
        self.assertEqual((queries["deruedas"].get("year_band"), queries["facebook"].get("year_band")), (1, None))
        await ingest([self.ka("band", 2009), self.ka("geared", 2009, transmision="Manual"), self.ka("older", 2008),
                      self.ka("fb", 2009, source="facebook"), self.ka("matched", 2012)], geocode=None)
        await db.mark_seen(aid, [self.ka("matched", 2012).to_dict()])

        queue = await repo_listings.enrichment_queue(per_source=20, max_age_days=30)
        self.assertEqual([(r["external_id"], r["band"]) for r in queue], [("matched", False), ("band", True)])

        for listing_id, year in (("matched", 2012), ("band", 2009)):
            url = f"https://example.test/deruedas/{listing_id}"
            FakeSource.details[url] = ListingDetail(url, listing=self.ka(
                listing_id, year, version="1.5 SE", transmision="Manual", descripcion="Único dueño."))
        llm = SimpleNamespace(refine=AsyncMock())
        with patch.object(enrich.DescriptionLLM, "create", AsyncMock(return_value=llm)):
            await enrich.enrich_pass()
        self.assertEqual([c.args[0] for c in llm.refine.await_args_list], [(await self.listing("matched"))["id"]])
        band = await self.listing("band")
        self.assertEqual(band["transmission"], "manual")
        self.assertIsNotNone(band["enriched_at"])
        self.assertEqual(await self.rows("SELECT id FROM description_llm_runs"), [])


class DescriptionFactsTests(IngestCase):
    """Normalization v3: the description as a source of the price."""

    def _detail(self, listing_id: str, descripcion: str, **kw) -> str:
        url = f"https://example.test/mercadolibre/{listing_id}"
        FakeSource.details[url] = ListingDetail(url, listing=card(listing_id, descripcion=descripcion, **kw))
        return url

    async def test_a_partial_price_is_enriched_and_the_description_gives_the_total(self):
        await self.fiesta_alert()
        down = dict(titulo="Ford Fiesta Titanium retirá con $5.000.000 y cuotas", precio=5_000_000.0, moneda="ARS")
        await ingest([card("1", **down)], geocode=None)
        row = await self.listing("1")
        self.assertTrue(row["price_partial"])                    # no match: only the partial flag

        self._detail("1", "Precio final $15.000.000. Retirá con $5.000.000 y cuotas fijas.", **down)
        result = await enrich.enrich_pass()

        row = await self.listing("1")
        self.assertEqual((float(row["price"]), row["currency"], row["price_partial"], row["price_source"]),
                         (15_000_000.0, "ARS", False, "description"))
        self.assertEqual(float(row["price_published"]), 5_000_000.0)
        self.assertEqual(float(row["price_usd"]), 15_000_000 / TEST_FX_RATE)
        self.assertEqual(row["description_facts"]["financing"]["down_payment"],
                         {"amount": 5_000_000.0, "currency": "ARS"})
        self.assertEqual([e.kind for e in result.events], ["listing_updated"])      # no price_drop
        self.assertEqual(await self.snapshots("1"), ["new", "description"])

        await ingest([card("1", **down)], geocode=None)          # the card again: the total stays
        self.assertEqual(float((await self.listing("1"))["price"]), 15_000_000.0)

    async def test_the_cash_price_wins_and_price_drops_follow_the_published_one(self):
        await ingest([card("1", precio=11_500.0)], geocode=None)
        await ingest([card("1", precio=11_500.0,
                           descripcion="PRECIO DE CONTADO U$S 10.900\nPRECIO DE LISTA/PERMUTA U$S 11.500")],
                     geocode=None)
        row = await self.listing("1")
        self.assertEqual((float(row["price"]), row["price_source"], float(row["price_published"])),
                         (10_900.0, "description", 11_500.0))
        self.assertEqual(row["description_facts"]["price_check"]["effective_kind"], "cash")

        drop = await ingest([card("1", precio=11_000.0)], geocode=None)    # the seller lowers the list price
        self.assertEqual([e.kind for e in drop.events], ["listing_updated", "price_drop"])
        self.assertEqual((drop.events[1].old_price, drop.events[1].new_price), (11_500.0, 11_000.0))
        self.assertEqual(float((await self.listing("1"))["price"]), 10_900.0)
        [snap] = await self.rows("SELECT price FROM listing_snapshots ORDER BY id DESC LIMIT 1")
        self.assertEqual(float(snap["price"]), 11_000.0)

    async def test_the_raw_page_is_kept_even_when_the_parser_fails(self):
        await ingest([card("1")], geocode=None)
        await db.mark_seen(await self.fiesta_alert(), [card("1").to_dict()], backfill=False)
        url = self._detail("1", "Único dueño")
        FakeSource.parse_errors[url] = ValueError("layout changed")

        await enrich.enrich_pass()

        [err] = await self.rows("SELECT stage FROM pipeline_errors")
        self.assertEqual(err["stage"], "enrich")
        [page] = await self.rows("SELECT url, status, parser_version, html_gz FROM raw_pages")
        html = raw_pages.decompress(page["html_gz"])
        self.assertIn(f"detalle {url}", html)
        self.assertNotIn("<script>", html)                       # slimmed
        self.assertEqual((page["url"], page["status"], page["parser_version"]), (url, 200, 1))

    async def test_reprocess_reads_stored_pages_and_texts_again(self):
        await ingest([card("1")], geocode=None)
        await db.mark_seen(await self.fiesta_alert(), [card("1").to_dict()], backfill=False)
        url = self._detail("1", "Único dueño")
        await enrich.enrich_pass()
        before = await self.listing("1")

        # A better parser now reads a cash price from the same page.
        self._detail("1", "Contado U$S 9.500, único dueño")
        with patch.object(FakeSource, "DETAIL_PARSER_VERSION", 2):
            result = await reprocess.reprocess_raw(dry_run=False, outdated=True)
            again = await reprocess.reprocess_raw(dry_run=False, outdated=True)
        after = await self.listing("1")
        self.assertEqual(float(after["price"]), 9_500.0)
        self.assertEqual(after["last_seen_at"], before["last_seen_at"])       # no sighting
        self.assertEqual(result.updated, 1)
        self.assertEqual(again.updated, 0)                                    # already at version 2

        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET price = 10000, price_source = 'published', "
                             "description_facts = NULL WHERE id = %s", (after["id"],))
        self.assertEqual(await reprocess.reprocess_facts(dry_run=True, llm=False), [after["id"]])
        self.assertEqual(float((await self.listing("1"))["price"]), 10_000.0)  # dry run
        await reprocess.reprocess_facts(dry_run=False, llm=False)
        self.assertEqual(float((await self.listing("1"))["price"]), 9_500.0)
        self.assertEqual(await reprocess.reprocess_facts(dry_run=True, llm=False), [])

    async def test_retention_drops_old_pages_and_listings_take_theirs(self):
        await ingest([card("1"), card("2")], geocode=None)
        one, two = await self.listing("1"), await self.listing("2")
        for lid in (one["id"], two["id"]):
            await raw_pages.save(lid, url="u", status=200, parser_version=1, html="<p>x</p>")
        async with db.connection() as cx:
            await cx.execute("UPDATE raw_pages SET fetched_at = now() - interval '91 days' WHERE listing_id = %s",
                             (one["id"],))
        self.assertEqual(await retention.purge_raw_pages(), 1)
        async with db.connection() as cx:
            await cx.execute("DELETE FROM listings WHERE id = %s", (two["id"],))
        self.assertEqual(await self.rows("SELECT listing_id FROM raw_pages"), [])

    async def test_ambiguous_descriptions_ask_the_llm_once(self):
        await ingest([card("1")], geocode=None)
        await db.mark_seen(await self.fiesta_alert(), [card("1").to_dict()], backfill=False)
        self._detail("1", "Contado USD 9.800. Contado USD 10.000. El precio publicado es el de lista.")

        class FakeLLM:
            calls = 0

            async def extract_listing_facts(self, title, description):
                FakeLLM.calls += 1
                return ListingFacts(transmission=None, fuel=None, single_owner=None, service_history=None,
                                    timing_belt_changed=None, accepts_trade_in=None, financing=None,
                                    damage_mentioned=None, cash_price=9_800, list_price=None, down_payment=None,
                                    installment_amount=None, installment_count=None, price_currency="USD",
                                    published_price_kind="list", mileage_km=None, year=None,
                                    evidence=[{"field": "cash_price", "quote": "Contado USD 9.800"},
                                              {"field": "price_currency", "quote": "Contado USD 9.800"},
                                              {"field": "published_price_kind", "quote": "El precio publicado es el de lista"}])

        llm = enrich.DescriptionLLM(FakeLLM(), daily_cap=5)
        with patch.object(enrich.DescriptionLLM, "create", AsyncMock(return_value=llm)):
            await enrich.enrich_pass()
        row = await self.listing("1")
        self.assertEqual((row["description_facts"]["source"], float(row["price"])), ("llm", 9_800.0))

        async with db.connection() as cx:              # the watchlist reads the same text again
            await cx.execute("UPDATE listings SET enriched_at = NULL, detail_checked_at = NULL")
        with patch.object(enrich.DescriptionLLM, "create", AsyncMock(return_value=llm)):
            await enrich.enrich_pass()
        self.assertEqual(FakeLLM.calls, 1)
        self.assertEqual((await self.listing("1"))["description_facts"]["source"], "llm")


class WatchlistTests(IngestCase):
    async def _saved(self, listing_id: str, **card_kw) -> None:
        await self.fiesta_alert()
        await ingest([card(listing_id, **card_kw)], geocode=None)
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO user_listing_interactions (user_id, listing_id, saved) "
                "SELECT p.id, l.id, true FROM profiles p, listings l WHERE l.external_id = %s",
                (listing_id,))

    async def test_saved_listing_is_refreshed_daily_with_change_detection(self):
        await self._saved("1")
        url = "https://example.test/mercadolibre/1"
        FakeSource.details[url] = ListingDetail(url, listing=card("1", precio=9_000.0))

        result = await watchlist.refresh_watchlist()
        again = await watchlist.refresh_watchlist()             # already checked today

        self.assertEqual([e.kind for e in result.events], ["listing_updated", "price_drop"])
        self.assertEqual(again.events, [])
        self.assertEqual(await self.snapshots("1"), ["new", "price"])

    async def test_gone_and_stale(self):
        long_ago = int((datetime.now(timezone.utc) - timedelta(days=45)).timestamp())
        await self._saved("1", published_at=long_ago)
        url = "https://example.test/mercadolibre/1"
        FakeSource.details[url] = ListingDetail(url, listing=card("1", published_at=long_ago))

        stale = await watchlist.refresh_watchlist()
        self.assertEqual([(e.kind, e.changes) for e in stale.events], [("listing_stale", ("45d",))])

        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET detail_checked_at = now() - interval '1 day'")
        FakeSource.details[url] = ListingDetail(url, gone=True, gone_reason="publicacion pausada")
        gone = await watchlist.refresh_watchlist()
        self.assertEqual([e.kind for e in gone.events], ["listing_gone"])
        self.assertEqual((await self.listing("1"))["status"], "gone")
        self.assertEqual((await watchlist.refresh_watchlist()).events, [])   # gone: not watched


class MatchedRecheckTests(IngestCase):
    """Listings with a match the crawl stopped seeing are checked through their detail page."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.profile = await self.fiesta_alert()

    async def _matched(self, external_id: str, *, level: str | None = "good", unseen_hours: int = 24,
                       checked_hours_ago: int | None = None, enriched: bool = True, **card_kw) -> str:
        await ingest([card(external_id, **card_kw)], geocode=None)
        async with db.connection() as cx:
            await cx.execute(
                "UPDATE listings SET last_seen_at = now() - make_interval(hours => %s), "
                "       enriched_at = CASE WHEN %s THEN now() - interval '2 days' END, "
                "       detail_checked_at = now() - make_interval(hours => %s) "
                " WHERE external_id = %s", (unseen_hours, enriched, checked_hours_ago, external_id))
            if level:
                await cx.execute(
                    "INSERT INTO matches (search_profile_id, listing_id, score, level, score_breakdown, "
                    "                     match_reasons, scoring_version) "
                    "SELECT %s, id, 75, %s, '{}', '[]', %s FROM listings WHERE external_id = %s",
                    (self.profile, level, SCORING_VERSION, external_id))
        return f"https://example.test/mercadolibre/{external_id}"

    async def test_only_matched_listings_the_crawl_stopped_seeing_are_queued(self):
        await self._matched("1")
        await self._matched("2", unseen_hours=1)             # still in the search results
        await self._matched("3", level="low")
        await self._matched("4", level=None)
        await self._matched("5", checked_hours_ago=2)        # checked a moment ago
        await self._matched("6", checked_hours_ago=20)       # checked yesterday: due again
        await self._matched("7", enriched=False)             # enrichment_queue's

        queue = await watchlist.matched_queue()

        self.assertEqual([r["external_id"] for r in queue], ["1", "6"])
        capped = await repo_listings.matched_recheck_queue(unseen_hours=6, recheck_hours=12,
                                                           max_age_days=60, per_source=1)
        self.assertEqual([r["external_id"] for r in capped], ["1"])      # never checked first

    async def test_price_drop_and_end_of_ad_come_from_the_detail_page(self):
        long_ago = int((datetime.now(timezone.utc) - timedelta(days=45)).timestamp())
        url = await self._matched("1", published_at=long_ago)
        FakeSource.details[url] = ListingDetail(url, listing=card("1", precio=9_000.0,
                                                                   published_at=long_ago))

        result = await watchlist.refresh_watchlist()
        again = await watchlist.refresh_watchlist()          # checked: waits recheck_hours

        # Not saved nor followed: no "lleva X días".
        self.assertEqual([e.kind for e in result.events], ["listing_updated", "price_drop"])
        self.assertEqual(again.events, [])
        self.assertEqual(await self.snapshots("1"), ["new", "price"])
        self.assertEqual(await self.rows("SELECT * FROM pipeline_errors"), [])

        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '1 day', "
                             "       detail_checked_at = now() - interval '1 day'")
        FakeSource.details[url] = ListingDetail(url, gone=True, gone_reason="404")
        gone = await watchlist.refresh_watchlist()
        self.assertEqual([e.kind for e in gone.events], ["listing_gone"])
        self.assertEqual((await self.listing("1"))["status"], "gone")


if __name__ == "__main__":
    unittest.main()
