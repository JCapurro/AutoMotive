"""F1 ingestion against the local Supabase Postgres (docs/TECHNICAL_PLAN.md, secciones 5.1–5.7).

Collectors are fakes; everything else — crawl targets, normalization, the
canonical upsert, snapshots, events, enrichment, watchlist, the Telegram
path — runs for real. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

import collectors
import db
from collectors._http import Page
from collectors.base import BaseScraper, Listing, ListingDetail
from pgcase import TEST_FX_RATE, PostgresTestCase, requires_db
from intelligence import comparables
from intelligence.config import SCORING_VERSION
from notifications.channels.telegram import TelegramChannel
from notifications.channels.web import WebChannel
from notifications.links import Links
from notifications.ops import SourceAlerts
from notifications.service import Notifier
from db.repos import listings as repo_listings, raw_pages
from llm.schemas import ListingFacts
from pipeline import crawl, enrich, rematch, retention, scheduler, watchlist
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
    (an exception there fails the fetch; one in `parse_errors[url]`, the parse)."""
    results: dict[str, list[Listing]] = {}
    details: dict[str, ListingDetail | Exception] = {}
    parse_errors: dict[str, Exception] = {}
    searches: list[tuple[str, dict]] = []

    async def search(self, filters: dict) -> list[Listing]:
        FakeSource.searches.append((self.name, filters))
        outcome = FakeSource.results.get(self.name, [])
        if isinstance(outcome, Exception):
            raise outcome
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
        FakeSource.parse_errors = {}
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

    async def tick(self, bot=None, on_health=None) -> int:
        """One crawl-loop tick with every target due, no jitter."""
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET next_run_at = NULL")
        await crawl.sync_targets(await db.enabled_profiles())
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


class CrawlTargetsTests(IngestCase):
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
        [t] = await self.rows("SELECT last_run_at, next_run_at, first_run_done FROM crawl_targets")

        self.assertTrue(t["first_run_done"])
        self.assertEqual(t["next_run_at"] - t["last_run_at"], timedelta(seconds=600))   # seed: ML 10 min
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
        self._detail("1", "Precio U$S 12.000. Otro precio U$S 13.000")        # two plain prices

        class FakeLLM:
            calls = 0

            async def extract_listing_facts(self, title, description):
                FakeLLM.calls += 1
                return ListingFacts(transmission=None, fuel=None, single_owner=None, service_history=None,
                                    timing_belt_changed=None, accepts_trade_in=None, financing=None,
                                    damage_mentioned=None, cash_price=9_800, list_price=None, down_payment=None,
                                    installment_amount=None, installment_count=None, price_currency="USD",
                                    published_price_kind="list", mileage_km=None, year=None)

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
