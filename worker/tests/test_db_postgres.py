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
from pipeline.ingest import ingest
from pgcase import PostgresTestCase, requires_db
from test_legacy_filters import WIZARD_ALERT

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866


async def store(*items: dict) -> None:
    await ingest([Listing(**it) for it in items], geocode=None)


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
        self.assertEqual((a["active"], a["bootstrapped"], a["rematch_requested"]), (1, 0, False))

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

    async def test_pause_resume_delete_and_bootstrap(self):
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                                      filters={"marcas": ["Ford"], "modelos": ["Ka"]})

        await db.set_alert_active(aid, False)
        self.assertEqual(await db.list_alerts(only_active=True), [])
        await db.set_alert_active(aid, True)
        await db.mark_bootstrapped(aid)
        a = await db.get_alert(aid)
        self.assertEqual(a["bootstrapped"], 1)
        self.assertEqual(await db.pending_rematch(), [])

        await db.delete_alert(aid)
        self.assertIsNone(await db.get_alert(aid))

    async def test_edit_keeps_history_and_splits_added_models(self):
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Ford Fiesta",
                                      filters={"marcas": ["Ford"], "modelos": ["Fiesta"],
                                               "descuento_pct": 15})
        await store(_listing("1"))
        await db.mark_seen(aid, [_listing("1")], backfill=True)
        await db.mark_bootstrapped(aid)
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET preferences = preferences || "
                             "'{\"sqlite_alert_id\": 5}' WHERE id = %s", (aid,))

        new_ids = await db.update_alert(aid, "Ford Fiesta/Ka", {
            "marcas": ["Ford"], "modelos": ["Fiesta", "Ka"], "descuento_pct": 20, "km_max": 90000})

        edited = await db.get_alert(aid)
        self.assertEqual(edited["filters"]["descuento_pct"], 20)
        self.assertEqual(edited["filters"]["km_max"], 90000)
        self.assertEqual(edited["filters"]["modelos"], ["Fiesta"])
        self.assertEqual(edited["name"], "Ford Fiesta")
        self.assertEqual(edited["bootstrapped"], 1)
        self.assertTrue(edited["rematch_requested"])        # backfilled silently next tick
        self.assertEqual(await db.filter_unseen(aid, [_listing("1")]), [])   # history kept
        self.assertEqual(len(new_ids), 1)
        added = await db.get_alert(new_ids[0])
        self.assertEqual((added["name"], added["bootstrapped"]), ("Ford Ka", 0))
        async with db.connection() as cx:
            prefs = (await (await cx.execute(
                "SELECT preferences FROM search_profiles WHERE id = %s", (aid,))).fetchone())["preferences"]
        self.assertEqual(prefs["sqlite_alert_id"], 5)

    async def test_plan_limit_is_measured_but_not_enforced_during_the_pilot(self):
        await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                              filters={"marcas": ["Ford"], "modelos": ["Ka", "Fiesta"]})
        async with db.connection() as cx:
            hits = await (await cx.execute(
                "SELECT props FROM events WHERE name = 'plan_limit_hit' ORDER BY id")).fetchall()
        # The second search goes over max_profiles; both ask for immediate alerts (Pro).
        self.assertEqual(sorted(h["props"]["limit"] for h in hits),
                         ["immediate_alerts", "immediate_alerts", "max_profiles"])
        self.assertTrue(all(h["props"]["enforced"] is False for h in hits))

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


class SeenMatchesTests(PostgresTestCase):
    async def test_seen_listings_become_matches(self):
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="a",
                                      filters={"marcas": ["Ford"], "modelos": ["Fiesta"]})
        items = [_listing("1"), _listing("2")]
        await store(*items)

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
        await store(*item)
        await db.mark_seen(ids[0], item)
        await db.mark_seen(other_user, item)

        self.assertEqual(await db.matched_by_other_profiles(ids[1], item), {("mercadolibre", "1")})
        self.assertEqual(await db.matched_by_other_profiles(ids[0], item), set())


class TelegramLinkTests(PostgresTestCase):
    """/start <code> (public.link_telegram, F4)."""

    async def web_user(self, email: str) -> tuple[str, str]:
        async with db.connection() as cx:
            row = await (await cx.execute(
                "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
                "        'authenticated', %s, now(), now()) RETURNING id::text AS id", (email,))).fetchone()
            code = await (await cx.execute(
                "SELECT telegram_link_code FROM profiles WHERE id = %s", (row["id"],))).fetchone()
        return row["id"], code["telegram_link_code"]

    async def profile(self, user_id: str) -> dict:
        async with db.connection() as cx:
            return await (await cx.execute(
                "SELECT telegram_user_id, telegram_chat_id, telegram_link_code FROM profiles WHERE id = %s",
                (user_id,))).fetchone()

    async def test_links_and_rotates_the_code(self):
        user, code = await self.web_user("web@automotive.test")
        self.assertEqual(await db.link_telegram(code, TG_USER, 777), user)
        p = await self.profile(user)
        self.assertEqual((p["telegram_user_id"], p["telegram_chat_id"]), (TG_USER, 777))
        self.assertNotEqual(p["telegram_link_code"], code)
        self.assertIsNone(await db.link_telegram(code, TG_USER, 777))        # used
        self.assertIsNone(await db.link_telegram("nope", TG_USER, 777))

    async def test_a_telegram_only_account_folds_into_the_web_account(self):
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Ford Fiesta",
                                      filters={"marcas": ["Ford"], "modelos": ["Fiesta"]})
        await store(_listing("1"))
        async with db.connection() as cx:
            anon = (await (await cx.execute("SELECT user_id::text AS id FROM search_profiles WHERE id = %s",
                                            (aid,))).fetchone())["id"]
            await cx.execute("INSERT INTO user_listing_interactions (user_id, listing_id, saved) "
                             "SELECT %s, id, true FROM listings", (anon,))
        user, code = await self.web_user("web@automotive.test")

        self.assertEqual(await db.link_telegram(code, TG_USER, TG_USER), user)

        async with db.connection() as cx:
            owner = await (await cx.execute("SELECT user_id::text AS id FROM search_profiles WHERE id = %s",
                                            (aid,))).fetchone()
            saved = await (await cx.execute("SELECT user_id::text AS id FROM user_listing_interactions")).fetchall()
            gone = await (await cx.execute("SELECT 1 FROM auth.users WHERE id = %s", (anon,))).fetchone()
        self.assertEqual(owner["id"], user)
        self.assertEqual([s["id"] for s in saved], [user])
        self.assertIsNone(gone)
        # The bot keeps finding the same account for this Telegram user.
        self.assertEqual([a["id"] for a in await db.list_alerts(user_id=TG_USER)], [aid])

    async def test_another_web_account_just_loses_the_link(self):
        first, first_code = await self.web_user("uno@automotive.test")
        second, second_code = await self.web_user("dos@automotive.test")
        await db.link_telegram(first_code, TG_USER, TG_USER)
        self.assertEqual(await db.link_telegram(second_code, TG_USER, TG_USER), second)
        self.assertIsNone((await self.profile(first))["telegram_user_id"])
        self.assertEqual((await self.profile(second))["telegram_user_id"], TG_USER)


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


if __name__ == "__main__":
    unittest.main()
