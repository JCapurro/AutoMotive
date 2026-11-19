"""Agencias against Postgres (docs/superpowers/specs/2026-11-18-agencias-design.md §7.2).

Needs a database with migration 20261228120000_dealer_program.sql applied
(spec §7.1: automotive_agencias_test); skipped on one without it. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_agencias_test pytest -m db
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import dealers as dealers_repo
from db.repos import duplicates as duplicates_repo
from db.repos import listings as listings_repo
from db.repos.listings import recent_active, rows_for_scoring
from intelligence.config import dealer_program
from intelligence.dealer import hidden_reason
from pgcase import TEST_FX_RATE, requires_db
from pipeline import market_stats
from pipeline.dealers import run_dealers
from pipeline.risk_duplicates import detect_for
from pipeline.scoring import Scorer
from test_notifications_postgres import LINKS, NotificationsCase

pytestmark = [pytest.mark.db, requires_db]

QUILMES = (-34.72, -58.25)
ON = {"enabled": True, "channel_enabled": True, "manual_confirm_days": 7, "demand_min_count": 3}
PANEL_ONLY = {**ON, "channel_enabled": False}
OFF = {**ON, "enabled": False, "channel_enabled": False}
H1 = "ac53862cd38c73d3"


class DealersCase(NotificationsCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            if not await dealers_repo.schema_ready(cx):
                self.skipTest("migration 20261228120000_dealer_program.sql not applied")
        listings_repo._has_duplicates = None
        await self.set_config("dealer_program", OFF)
        # The search takes every source, so a 'directo' listing can reach it.
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET filters = filters - 'sources', notify_min_level = 'low' "
                             " WHERE id = %s", (self.profile,))
            await cx.execute("UPDATE profiles SET plan = 'pro', plan_expires_at = now() + interval '20 days' "
                             " WHERE id = %s", (self.user,))

    async def program(self, value: dict) -> None:
        await self.set_config("dealer_program", value)

    async def dealer(self, *, approved: bool = True, status: str = "active", name: str = "TT Autos") -> int:
        [r] = await self.rows(
            "INSERT INTO dealers (name, locality_label, lat, lon, approved_at, status, contact_email) "
            "VALUES (%s, 'Quilmes', %s, %s, CASE WHEN %s THEN now() END, %s, 'tt@agencia.test') RETURNING id",
            name, *QUILMES, approved, status)
        return r["id"]

    async def item(self, dealer_id: int, **kw) -> int:
        row = dict(dealer_id=dealer_id, origin="manual", make="Ford", model="Fiesta", trim="Titanium", year=2017,
                   mileage_km=112_000, price=15_000_000, currency="ARS", status="available",
                   confirmed_at=datetime.now(timezone.utc), sync_state="pending")
        row.update(kw)
        cols = list(row)
        [r] = await self.rows(f"INSERT INTO dealer_stock_items ({', '.join(cols)}) "
                              f"VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id", *row.values())
        return r["id"]

    async def item_row(self, item_id: int) -> dict:
        [r] = await self.rows("SELECT * FROM dealer_stock_items WHERE id = %s", item_id)
        return r

    async def listing_row(self, listing_id: int) -> dict:
        [r] = await self.rows("SELECT * FROM listings WHERE id = %s", listing_id)
        return r

    async def tick(self):
        return await run_dealers(self.notifier, LINKS)

    async def counts(self) -> dict[str, int]:
        out = {}
        for t in ("listings", "matches", "notifications", "expired_search_matches", "dealer_stock_items",
                  "listing_duplicates"):
            [r] = await self.rows(f"SELECT count(*)::int AS n FROM {t}")
            out[t] = r["n"]
        return out


class SwitchOffTests(DealersCase):
    async def test_disabled_without_rows_writes_nothing(self):
        await self.listing()
        before = await self.counts()
        tick = await self.tick()
        self.assertEqual(await self.counts(), before)
        self.assertFalse(any(vars(tick).values()))

    async def test_disabled_never_syncs_items(self):
        d = await self.dealer()
        i = await self.item(d)
        await self.tick()
        self.assertEqual((await self.item_row(i))["sync_state"], "pending")
        self.assertEqual(await self.rows("SELECT id FROM listings WHERE source = 'directo'"), [])


class DirectoTests(DealersCase):
    async def test_manual_item_becomes_a_directo_listing(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        i = await self.item(d)
        tick = await self.tick()
        item = await self.item_row(i)
        self.assertEqual(item["sync_state"], "synced")
        listing = await self.listing_row(item["listing_id"])
        self.assertEqual((listing["source"], listing["external_id"]), ("directo", str(i)))
        self.assertAlmostEqual(float(listing["price_usd"]), 15_000_000 / TEST_FX_RATE)
        self.assertEqual((listing["dealer_id"], listing["dealer_status"]), (d, "available"))
        self.assertEqual((listing["lat"], listing["lon"]), QUILMES)
        self.assertEqual(listing["seller_type"], "dealer")
        self.assertEqual(listing["dealer_confirmed_at"], item["confirmed_at"])
        self.assertEqual(tick.created, 1)
        # Panel only: hidden (channel_off), so no match nor notification.
        self.assertEqual(await self.rows("SELECT id FROM matches"), [])
        self.assertEqual(await self.rows("SELECT id FROM notifications"), [])

    async def test_an_edit_updates_the_same_listing(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        i = await self.item(d)
        await self.tick()
        first = (await self.item_row(i))["listing_id"]
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_stock_items SET price = 14000000, sync_state = 'pending' WHERE id = %s",
                             (i,))
        tick = await self.tick()
        self.assertEqual((await self.item_row(i))["listing_id"], first)
        self.assertEqual(tick.updated, 1)
        self.assertEqual(float((await self.listing_row(first))["price"]), 14_000_000)

    async def test_sold_item_ends_its_listing(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        i = await self.item(d)
        await self.tick()
        lid = (await self.item_row(i))["listing_id"]
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_stock_items SET status = 'sold' WHERE id = %s", (i,))
            await cx.execute("UPDATE listings SET dealer_status = 'sold' WHERE id = %s", (lid,))
        await self.tick()
        self.assertEqual((await self.listing_row(lid))["status"], "gone")


class DuplicateItemTests(DealersCase):
    async def approve(self, dealer_id: int, source: str, seller_key: str) -> None:
        async with db.connection() as cx:
            await cx.execute("INSERT INTO dealer_sources (dealer_id, source, seller_key, status, approved_at) "
                             "VALUES (%s, %s, %s, 'approved', now())", (dealer_id, source, seller_key))

    async def test_approved_source_links_and_confirms_with_each_read(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        seen = datetime.now(timezone.utc) - timedelta(hours=3)
        ml = await self.listing(seller_name="TT Autos", seller_key="tt autos", last_seen_at=seen)
        await self.approve(d, "mercadolibre", "tt autos")
        tick = await self.tick()
        row = await self.listing_row(ml)
        self.assertEqual((row["dealer_id"], row["dealer_status"]), (d, "available"))
        self.assertEqual(row["dealer_confirmed_at"], max(row["last_seen_at"], row["last_full_seen_at"] or seen))
        [item] = await self.rows("SELECT * FROM dealer_stock_items WHERE listing_id = %s", ml)
        self.assertEqual((item["origin"], item["sync_state"]), ("sync", "linked"))
        self.assertEqual(tick.linked, 1)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET last_seen_at = now() WHERE id = %s", (ml,))
        await self.tick()
        row = await self.listing_row(ml)
        self.assertEqual(row["dealer_confirmed_at"], max(row["last_seen_at"], row["last_full_seen_at"] or seen))

    async def test_own_duplicate_links_without_a_copy(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        ml = await self.listing(seller_name="TT Autos", seller_key="tt autos", price=15_200, price_usd=15_200,
                                currency="USD")
        await self.approve(d, "mercadolibre", "tt autos")
        await self.tick()
        i = await self.item(d, price=15_000, currency="USD", mileage_km=110_000)
        await self.tick()
        self.assertEqual((await self.item_row(i))["listing_id"], ml)
        self.assertEqual([r["id"] for r in await self.rows("SELECT id FROM dealer_stock_items")], [i])
        self.assertEqual(await self.rows("SELECT id FROM listings WHERE source = 'directo'"), [])

    async def test_foreign_duplicate_waits_for_review(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        other = await self.listing(seller_type="dealer", lat=QUILMES[0] + 0.01, lon=QUILMES[1], mileage_km=112_500,
                                   price=20_000, price_usd=20_000, currency="USD")
        i = await self.item(d)
        tick = await self.tick()
        item = await self.item_row(i)
        self.assertEqual((item["sync_state"], item["duplicate_listing_id"], item["listing_id"]),
                         ("review", other, None))
        self.assertEqual(tick.review, 1)
        self.assertEqual(await self.rows("SELECT id FROM listings WHERE source = 'directo'"), [])

    async def test_review_answered_mine_ends_in_one_linked_item(self):
        """«¿Es este aviso tuyo? → Sí, es mío», then Juan approves that seller: one car, one item."""
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        other = await self.listing(seller_type="dealer", seller_key="tt ml", lat=QUILMES[0] + 0.01, lon=QUILMES[1],
                                   mileage_km=112_500, price=20_000, price_usd=20_000, currency="USD")
        i = await self.item(d)
        await self.tick()
        self.assertEqual((await self.item_row(i))["sync_state"], "review")
        await self.approve(d, "mercadolibre", "tt ml")
        await self.tick()
        item = await self.item_row(i)
        self.assertEqual((item["sync_state"], item["listing_id"], item["duplicate_listing_id"]), ("linked", other, None))
        self.assertEqual([r["id"] for r in await self.rows("SELECT id FROM dealer_stock_items")], [i])
        self.assertEqual((await self.listing_row(other))["dealer_id"], d)
        self.assertEqual(await self.rows("SELECT id FROM listings WHERE source = 'directo'"), [])

    async def test_review_of_a_look_alike_that_ended_goes_back_to_pending(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        other = await self.listing(seller_type="dealer", lat=QUILMES[0] + 0.01, lon=QUILMES[1], mileage_km=112_500,
                                   price=20_000, price_usd=20_000, currency="USD")
        i = await self.item(d)
        await self.tick()
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (other,))
        await self.tick()   # released to pending
        await self.tick()   # and published
        item = await self.item_row(i)
        self.assertEqual(item["sync_state"], "synced")
        self.assertEqual((await self.listing_row(item["listing_id"]))["source"], "directo")

    async def test_linked_item_whose_portal_listing_ended_gets_its_own_listing(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        ml = await self.listing(seller_name="TT Autos", seller_key="tt autos", price=15_200, price_usd=15_200,
                                currency="USD")
        await self.approve(d, "mercadolibre", "tt autos")
        await self.tick()
        i = await self.item(d, price=15_000, currency="USD", mileage_km=110_000)
        await self.tick()
        self.assertEqual((await self.item_row(i))["listing_id"], ml)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (ml,))
        await self.tick()
        item = await self.item_row(i)
        self.assertEqual(item["sync_state"], "synced")
        self.assertNotEqual(item["listing_id"], ml)
        self.assertEqual((await self.listing_row(item["listing_id"]))["source"], "directo")

    async def test_a_synced_listing_that_comes_back_brings_its_item_back(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        ml = await self.listing(seller_name="TT Autos", seller_key="tt autos")
        await self.approve(d, "mercadolibre", "tt autos")
        await self.tick()
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (ml,))
        await self.tick()
        [item] = await self.rows("SELECT * FROM dealer_stock_items WHERE listing_id = %s", ml)
        self.assertEqual((item["status"], item["sync_state"]), ("archived", "gone"))
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'active', last_seen_at = now() WHERE id = %s", (ml,))
        await self.tick()
        [item] = await self.rows("SELECT * FROM dealer_stock_items WHERE listing_id = %s", ml)
        self.assertEqual((item["status"], item["sync_state"]), ("available", "linked"))


class RetryTests(DealersCase):
    async def test_a_failed_ingest_is_retried_after_30_minutes(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        late = await self.item(d, sync_state="error", sync_error="ingest_failed", updated_at=old)
        fresh = await self.item(d, sync_state="error", sync_error="ingest_failed", model="Focus")
        stored = await self.item(d, sync_state="error", sync_error="not_stored", updated_at=old, model="Ka")
        await self.tick()
        self.assertEqual((await self.item_row(late))["sync_state"], "synced")
        self.assertEqual((await self.item_row(fresh))["sync_state"], "error")
        self.assertEqual((await self.item_row(stored))["sync_state"], "error")


class LeadQueueTests(DealersCase):
    async def lead(self, dealer_id: int) -> int:
        [r] = await self.rows(
            "INSERT INTO dealer_leads (dealer_id, buyer_user_id, buyer_name, buyer_phone, consent_text, origin) "
            "VALUES (%s, %s, 'Juana', '1155556666', 'Acepto que le pasen mis datos a la agencia.', 'ficha') "
            "RETURNING id", dealer_id, self.user)
        return r["id"]

    async def test_a_dealer_without_email_never_holds_back_the_others(self):
        [r] = await self.rows("INSERT INTO dealers (name, locality_label, lat, lon) VALUES ('Sin Mail', 'Quilmes', %s, %s) "
                              "RETURNING id", *QUILMES)
        mute = r["id"]
        told = await self.dealer()
        await self.lead(mute)
        await self.lead(mute)
        mine = await self.lead(told)
        rows = await dealers_repo.unnotified_leads(1)
        self.assertEqual([(x["lead_id"], x["email"]) for x in rows], [(mine, "tt@agencia.test")])


class ChannelTests(DealersCase):
    async def private_search(self) -> int:
        [r] = await self.rows(
            "INSERT INTO search_profiles (user_id, name, filters, channels, notification_frequency, notify_min_level, "
            "                             bootstrapped_at, enabled) "
            "SELECT user_id, 'Solo particulares', filters || '{\"seller_types\": [\"private\"]}'::jsonb, channels, "
            "       notification_frequency, notify_min_level, now(), true FROM search_profiles WHERE id = %s "
            "RETURNING id", self.profile)
        return r["id"]

    async def test_channel_on_matches_and_notifies_with_the_label(self):
        await self.program(ON)
        private = await self.private_search()
        d = await self.dealer()
        i = await self.item(d, price=10_000, currency="USD")
        tick = await self.tick()
        lid = (await self.item_row(i))["listing_id"]
        self.assertEqual(tick.matched, 1)
        self.assertIsNotNone((await self.item_row(i))["matched_at"])
        matched = {r["search_profile_id"] for r in await self.rows("SELECT * FROM matches WHERE listing_id = %s", lid)}
        self.assertIn(self.profile, matched)
        self.assertNotIn(private, matched)                                   # C4
        notes = await self.rows("SELECT payload FROM notifications WHERE listing_id = %s", lid)
        self.assertTrue(notes)
        self.assertEqual(notes[0]["payload"]["listing"]["dealer"], {"label": "Agencia", "name": "TT Autos"})

    async def test_reserved_or_unconfirmed_leaves_no_matches(self):
        await self.program(ON)
        d = await self.dealer()
        i = await self.item(d, price=10_000, currency="USD")
        await self.tick()
        lid = (await self.item_row(i))["listing_id"]
        self.assertTrue(await self.rows("SELECT id FROM matches WHERE listing_id = %s", lid))
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET dealer_confirmed_at = now() - interval '8 days' WHERE id = %s",
                             (lid,))
        tick = await self.tick()
        self.assertEqual(await self.rows("SELECT id FROM matches WHERE listing_id = %s", lid), [])
        self.assertGreaterEqual(tick.swept_matches, 1)
        self.assertEqual(await self.rows("SELECT id FROM notifications WHERE listing_id = %s "
                                         "   AND status IN ('queued', 'digest')", lid), [])

    async def test_channel_off_never_matches_a_directo(self):
        await self.program(PANEL_ONLY)
        d = await self.dealer()
        await self.item(d, price=10_000, currency="USD")
        await self.tick()
        self.assertEqual(await self.rows("SELECT id FROM matches"), [])
        self.assertEqual(await self.rows("SELECT id FROM notifications"), [])


class TwinTests(DealersCase):
    async def test_python_gate_equals_sql_gate(self):
        approved, pending, paused = await self.dealer(), await self.dealer(approved=False), \
            await self.dealer(status="paused")
        flags = {approved: (True, True), pending: (False, True), paused: (True, False)}
        now = datetime.now(timezone.utc)
        for value in (ON, PANEL_ONLY, OFF):
            await self.program(value)
            program = dealer_program(value)
            for source in ("directo", "mercadolibre"):
                for dealer_id in (None, approved, pending, paused):
                    for status in (None, "available", "reserved", "sold"):
                        for confirmed in (None, now - timedelta(days=1), now - timedelta(days=8)):
                            [r] = await self.rows("SELECT public.dealer_listing_hidden(%s, %s, %s, %s) AS r",
                                                  source, dealer_id, status, confirmed)
                            ok, active = flags.get(dealer_id, (False, False))
                            row = {"source": source, "dealer_id": dealer_id, "dealer_status": status,
                                   "dealer_confirmed_at": confirmed, "dealer_approved": ok, "dealer_active": active}
                            with self.subTest(program=value, row=row):
                                self.assertEqual(hidden_reason(row, program, now=now), r["r"])


class ReadsTests(DealersCase):
    async def directo(self, dealer_id: int, **kw) -> int:
        return await self.listing(source="directo", external_id=f"x{self._n}", dealer_id=dealer_id,
                                  dealer_status="available", dealer_confirmed_at=datetime.now(timezone.utc),
                                  seller_type="dealer", **kw)

    async def test_recent_active_and_market_stats_ignore_directo(self):
        d = await self.dealer()
        ml = await self.listing()
        hidden = await self.directo(d)
        await self.program(PANEL_ONLY)
        self.assertEqual({r["id"] for r in await recent_active("Ford", "Fiesta", days=30)}, {ml})
        await self.program(ON)
        self.assertEqual({r["id"] for r in await recent_active("Ford", "Fiesta", days=30)}, {ml, hidden})
        rows = await market_stats.fetch_rows(date.today(), {})
        self.assertNotIn(hidden, {r["id"] for r in rows})

    async def test_scorer_never_evaluates_a_hidden_listing(self):
        """count_after_expiry, rematch and rescore all go through Scorer.evaluate."""
        d = await self.dealer()
        lid = await self.directo(d)
        [profile] = [a["profile"] for a in await db.alerts_for_target("directo", "Ford", "Fiesta",
                                                                       telegram_only=False)]
        await self.program(PANEL_ONLY)
        s = await Scorer.create()
        await s.prepare([lid])
        self.assertIsNone(s.evaluate(lid, profile))
        await self.program(ON)
        s = await Scorer.create()
        await s.prepare([lid])
        self.assertIsNotNone(s.evaluate(lid, profile))

    async def test_rows_for_scoring_carries_the_dealer(self):
        d = await self.dealer()
        lid = await self.directo(d)
        async with db.connection() as cx:
            row = (await rows_for_scoring(cx, [lid]))[lid]
        self.assertEqual((row["dealer_name"], row["dealer_approved"], row["dealer_active"]), ("TT Autos", True, True))


class RiskDuplicateTests(DealersCase):
    def photos(self) -> Jsonb:
        return Jsonb({"_photo_hashes": {"v": 1, "urls": [], "hashes": [H1], "attempts": 1}})

    async def pairs(self) -> set[tuple[int, int]]:
        return {(r["listing_id"], r["other_id"]) for r in await self.rows("SELECT * FROM listing_duplicates")}

    async def test_a_directo_never_forms_pairs(self):
        await self.program(ON)
        d = await self.dealer()
        common = dict(price=12_000, currency="USD", price_usd=12_000, mileage_km=90_000, location_text="Rosario",
                      images=Jsonb(["https://img.example.test/a.jpg"]))
        directo = await self.listing(source="directo", external_id="z1", dealer_id=d, dealer_status="available",
                                     dealer_confirmed_at=datetime.now(timezone.utc), seller_type="dealer",
                                     attributes=self.photos(), **common)
        ml = await self.listing(attributes=self.photos(), seller_key="vendedor ml", **common)
        await detect_for([directo, ml])
        self.assertFalse(any(directo in p for p in await self.pairs()))
        async with db.connection() as cx:
            row = (await rows_for_scoring(cx, [ml]))[ml]
        self.assertEqual(row["risk_duplicates"], [])
        queue = await duplicates_repo.photo_hash_queue(limit=50, skip_sources=[], km_tol_pct=5, price_tol_pct=5,
                                                       version=2, max_attempts=3)
        self.assertNotIn(directo, {r["id"] for r in queue})
        await self.program(PANEL_ONLY)
        await detect_for([directo, ml])
        self.assertFalse(any(directo in p for p in await self.pairs()))

    async def test_control_and_synced_pairs(self):
        common = dict(price=12_000, currency="USD", price_usd=12_000, mileage_km=90_000, location_text="Rosario",
                      images=Jsonb(["https://img.example.test/a.jpg"]))
        ml = await self.listing(attributes=self.photos(), seller_key="vendedor ml", **common)
        other = await self.listing(source="rosariogarage", external_id="rg1", attributes=self.photos(),
                                   seller_key="vendedor rg", **{**common, "mileage_km": 91_000})
        await detect_for([ml, other])
        self.assertEqual(await self.pairs(), {(ml, other), (other, ml)})           # as today
        d = await self.dealer()
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET dealer_id = %s, dealer_status = 'available' WHERE id = %s", (d, ml))
            shown = (await rows_for_scoring(cx, [other]))[other]["risk_duplicates"]
            self.assertEqual([p["other_id"] for p in shown], [ml])
            await cx.execute("UPDATE listings SET dealer_status = 'sold' WHERE id = %s", (ml,))
            self.assertEqual((await rows_for_scoring(cx, [other]))[other]["risk_duplicates"], [])
