"""The bot's data layer against a real Postgres with the supabase/ migrations.

Run with TEST_DATABASE_URL pointing at the local stack, e.g.
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import psycopg
import pytest

import db
from collectors.base import Listing
from pgcase import PostgresTestCase, requires_db
from test_legacy_filters import WIZARD_ALERT

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866


def _listing(listing_id: str, **kw) -> dict:
    base = dict(source="mercadolibre", listing_id=listing_id, titulo=f"Ford Fiesta {listing_id}",
                url=f"https://example.test/{listing_id}", precio=10000.0, moneda="USD",
                marca="Ford", modelo="Fiesta", anio=2018, km=100000)
    base.update(kw)
    return Listing(**base).to_dict()


class AlertRepoTests(PostgresTestCase):
    async def test_wizard_alert_is_stored_as_profile_and_read_back_unchanged(self):
        ids = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Ford Fiesta",
                                    filters=WIZARD_ALERT)

        self.assertEqual(len(ids), 1)
        alerts = await db.list_alerts(user_id=TG_USER)
        self.assertEqual(len(alerts), 1)
        a = alerts[0]
        self.assertEqual((a["id"], a["user_id"], a["chat_id"], a["name"]),
                         (ids[0], TG_USER, TG_USER, "Ford Fiesta"))
        self.assertEqual(a["filters"], WIZARD_ALERT)
        self.assertEqual((a["active"], a["bootstrapped"], a["last_scraped_at"]), (1, 0, None))

        async with db.connection() as cx:
            row = await (await cx.execute(
                "SELECT sp.filters, sp.radius_km, u.is_anonymous "
                "FROM search_profiles sp JOIN auth.users u ON u.id = sp.user_id")).fetchone()
        self.assertEqual(row["filters"]["make"], "Ford")
        self.assertEqual(row["filters"]["transmission"], "manual")
        self.assertEqual(row["radius_km"], 12.0)
        self.assertTrue(row["is_anonymous"])

    async def test_multi_model_alert_becomes_one_canonical_profile_per_vehicle(self):
        ids = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="VW Gol/Fox",
                                    filters={"marcas": ["vw"], "modelos": ["gol trend", "Fox"]})
        again = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="x",
                                      filters={"marcas": ["Tesla"], "modelos": ["Model 3"]})

        alerts = {a["id"]: a for a in await db.list_alerts(user_id=TG_USER)}
        self.assertEqual(len(ids), 2)
        self.assertEqual([alerts[i]["name"] for i in ids],
                         ["Volkswagen Gol Trend", "Volkswagen Fox"])
        self.assertEqual(alerts[ids[0]]["filters"]["modelos"], ["Gol Trend"])
        # Not in the catalog: kept as typed, so the bot still searches it.
        self.assertEqual(alerts[again[0]]["filters"]["marcas"], ["Tesla"])
        async with db.connection() as cx:
            users = await (await cx.execute("SELECT count(*) AS n FROM profiles")).fetchone()
        self.assertEqual(users["n"], 1)

    async def test_pause_resume_delete_and_scrape_stamps(self):
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                                      filters={"marcas": ["Ford"], "modelos": ["Ka"]})

        await db.set_alert_active(aid, False)
        self.assertEqual(await db.list_alerts(only_active=True), [])
        await db.set_alert_active(aid, True)
        await db.mark_scraped(aid, bootstrapped=True)
        a = await db.get_alert(aid)
        self.assertEqual(a["bootstrapped"], 1)
        self.assertIsInstance(a["last_scraped_at"], int)

        await db.delete_alert(aid)
        self.assertIsNone(await db.get_alert(aid))

    async def test_plan_limit_is_measured_but_not_enforced_during_the_pilot(self):
        await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                              filters={"marcas": ["Ford"], "modelos": ["Ka", "Fiesta"]})
        async with db.connection() as cx:
            hits = await (await cx.execute(
                "SELECT props FROM events WHERE name = 'plan_limit_hit'")).fetchall()
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["props"]["enforced"], False)

    async def test_plan_limit_rejects_inserts_when_enforced(self):
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{enforced}', 'true') "
                             "WHERE key = 'plan_limits'")
        try:
            await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                                  filters={"marcas": ["Ford"], "modelos": ["Ka"]})
            with self.assertRaises(psycopg.errors.RaiseException):
                await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="b",
                                      filters={"marcas": ["Ford"], "modelos": ["Fiesta"]})
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{enforced}', 'false') "
                                 "WHERE key = 'plan_limits'")


class ListingRepoTests(PostgresTestCase):
    async def _snapshots(self) -> list[str]:
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT change_kind FROM listing_snapshots ORDER BY id")).fetchall()
        return [r["change_kind"] for r in rows]

    async def _listing_row(self, external_id: str) -> dict:
        async with db.connection() as cx:
            return await (await cx.execute(
                "SELECT * FROM listings WHERE external_id = %s", (external_id,))).fetchone()

    async def test_upsert_keeps_first_seen_and_snapshots_only_changes(self):
        await db.upsert_listings([_listing("1"), _listing("1")])   # duplicate in batch
        first = await self._listing_row("1")
        await db.upsert_listings([_listing("1")])
        same = await self._listing_row("1")
        await db.upsert_listings([_listing("1", precio=9500.0)])
        cheaper = await self._listing_row("1")
        await db.upsert_listings([_listing("1", precio=9500.0, km=101000)])

        self.assertEqual(await self._snapshots(), ["new", "price", "mileage"])
        self.assertEqual(first["first_seen_at"], cheaper["first_seen_at"])
        self.assertGreater(same["last_seen_at"], first["last_seen_at"])
        self.assertEqual(float(cheaper["price"]), 9500.0)
        self.assertEqual((first["make"], first["model"]), ("ford", "fiesta"))

    async def test_values_outside_column_domains_are_kept_as_attributes(self):
        await db.upsert_listings([_listing("2", moneda="U$S", transmision="Automática",
                                           vendedor="Concesionaria", published_at=1_700_000_000)])
        row = await self._listing_row("2")

        self.assertIsNone(row["currency"])
        self.assertEqual(row["transmission"], "automatic")
        self.assertEqual(row["seller_type"], "dealer")
        self.assertEqual(row["attributes"]["moneda"], "U$S")
        self.assertEqual(int(row["published_at"].timestamp()), 1_700_000_000)

    async def test_comparables_use_the_legacy_keys_and_skip_partial_prices(self):
        await db.upsert_listings([
            _listing("a", anio=2018), _listing("b", anio=2019, km=None),
            _listing("c", anio=2021), _listing("d", price_partial=True),
            _listing("e", modelo="Focus"), _listing("f", km=200000),
        ])
        comps = await db.comparables("ford", "FIESTA", 2018, km=100000)

        self.assertEqual(sorted(c["listing_id"] for c in comps), ["a", "b"])
        self.assertEqual(comps[0]["precio"], 10000.0)
        self.assertEqual(comps[0]["moneda"], "USD")


class SeenMatchesTests(PostgresTestCase):
    async def test_seen_listings_become_matches(self):
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                                      filters={"marcas": ["Ford"], "modelos": ["Fiesta"]})
        items = [_listing("1"), _listing("2")]
        await db.upsert_listings(items)

        self.assertEqual(len(await db.filter_unseen(aid, items)), 2)
        await db.mark_seen(aid, items[:1], backfill=True)
        await db.mark_seen(aid, items[:1])   # idempotent
        unseen = await db.filter_unseen(aid, items)

        self.assertEqual([u["listing_id"] for u in unseen], ["2"])
        async with db.connection() as cx:
            m = await (await cx.execute("SELECT * FROM matches")).fetchall()
        self.assertEqual(len(m), 1)
        self.assertTrue(m[0]["is_backfill"])
        self.assertEqual(m[0]["scoring_version"], "legacy-v0")

    async def test_other_profiles_of_the_same_user_are_detected(self):
        ids = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                                    filters={"marcas": ["Ford", "Volkswagen"], "modelos": ["Fiesta"]})
        [other_user] = await db.create_alert(user_id=1, chat_id=1, name="b",
                                             filters={"marcas": ["Ford"], "modelos": ["Fiesta"]})
        item = [_listing("1")]
        await db.upsert_listings(item)
        await db.mark_seen(ids[0], item)
        await db.mark_seen(other_user, item)

        self.assertEqual(await db.matched_by_other_profiles(ids[1], item), {("mercadolibre", "1")})
        self.assertEqual(await db.matched_by_other_profiles(ids[0], item), set())


class GeocodeAndConfigTests(PostgresTestCase):
    async def test_geocode_cache_positive_and_negative(self):
        self.assertIsNone(await db.get_geocode_cache("munro"))
        await db.set_geocode_cache("munro", -34.52, -58.52, "nominatim")
        self.assertEqual(await db.get_geocode_cache("munro"), (-34.52, -58.52))

        await db.set_geocode_cache_failure("villa inventada", "nominatim")
        self.assertIsNone(await db.get_geocode_cache("villa inventada"))
        self.assertTrue(await db.has_fresh_geocode_failure("villa inventada"))
        self.assertFalse(await db.has_fresh_geocode_failure("munro"))

    async def test_app_config_comes_from_the_seed(self):
        self.assertEqual(await db.get_config("recommended_max_age_days"), 15)
        self.assertEqual((await db.get_config("comparables"))["min_n"], 5)
        self.assertEqual(await db.get_config("missing", "fallback"), "fallback")


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        self.sent.append(kwargs)


class SchedulerOnPostgresTests(PostgresTestCase):
    """The bot's flow end to end: silent bootstrap, one alert per new
    opportunity, nothing twice."""

    async def test_bootstrap_then_notify_new_opportunity_once(self):
        from pipeline import scheduler

        results: list[Listing] = []

        class FakeScraper:
            async def search(self, filters):
                return list(results)

        [aid] = await db.create_alert(user_id=TG_USER, chat_id=4242, name="Ford Fiesta",
                                      filters={"marcas": ["Ford"], "modelos": ["Fiesta"],
                                               "sources": ["mercadolibre"], "descuento_pct": 15})
        # Six comparables around USD 12.000 give a market median.
        results[:] = [Listing(**{**_listing(f"c{i}", precio=12000.0 + i * 100)}) for i in range(6)]
        bot = _FakeBot()

        with patch.dict(scheduler.REGISTRY, {"mercadolibre": FakeScraper}, clear=True):
            await scheduler._run_alert(bot, await db.get_alert(aid))       # bootstrap
            self.assertEqual(bot.sent, [])
            results.append(Listing(**_listing("deal", precio=9000.0)))    # 25% below median
            results.append(Listing(**_listing("meh", precio=11800.0)))
            await scheduler._run_alert(bot, await db.get_alert(aid))
            await scheduler._run_alert(bot, await db.get_alert(aid))       # nothing new

        self.assertEqual(len(bot.sent), 1)
        self.assertEqual(bot.sent[0]["chat_id"], 4242)
        self.assertIn("Ford Fiesta deal", bot.sent[0]["text"])
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT l.external_id, m.is_backfill, m.price_ref FROM matches m "
                "JOIN listings l ON l.id = m.listing_id ORDER BY m.id")).fetchall()
        self.assertEqual(len(rows), 8)
        self.assertTrue(all(r["is_backfill"] for r in rows[:6]))
        deal = next(r for r in rows if r["external_id"] == "deal")
        self.assertFalse(deal["is_backfill"])
        self.assertTrue(deal["price_ref"]["is_opportunity"])
        # Like the SQLite bot, the batch is cached before scoring, so the
        # listing itself counts as a comparable (sección 6.2 fixes this in F2).
        self.assertEqual(deal["price_ref"]["n"], 8)


if __name__ == "__main__":
    unittest.main()
