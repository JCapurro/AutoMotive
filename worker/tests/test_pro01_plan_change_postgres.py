"""PRO-01, Respuestas de Juan 02/11, 3 (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md):
a change of plan that flips plan_feature('seller_filter') marks the user's
strict searches for rematch (migration 20261129120000_pro01_plan_change_rematch.sql),
through every path that changes a plan: the admin's manual payment and
refund, the Mercado Pago webhook (approval and refund), an admin editing
plan_limits, a Telegram merge, a role change and the time-based expiry the
worker's tick sweeps. Then the rematch applies or lifts the filter with its
own semantics: what stops matching is deleted, what starts matching is
backfill, nothing is notified again; and match_cards.seller_unknown (option C)
follows. The SQL rules alone are in supabase/tests/pro01_plan_change_test.sql. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest -m db
"""
from __future__ import annotations

import asyncio

import pytest
from psycopg.types.json import Jsonb

import db
from pgcase import requires_db
from pipeline import rematch
from test_commercial_postgres import CommercialCase
from test_pro01_postgres import Pro01Case

pytestmark = [pytest.mark.db, requires_db]

STRICT = {"make": "Ford", "model": "Fiesta", "seller_types": ["private"]}
PLAIN = {"make": "Ford", "model": "Fiesta"}


class PlanPathCase(CommercialCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # The pilot: access never pauses a search here, only the plan's features move.
        await self.rows("UPDATE app_config SET value=jsonb_set(value,'{enforced}','false') WHERE key='plan_limits'")
        self.strict_id, self.plain_id = await self.searches_of(self.user)

    async def searches_of(self, user) -> tuple[int, int]:
        ids = []
        for radius, filters in ((1, STRICT), (2, PLAIN)):
            [row] = await self.rows("INSERT INTO search_profiles(user_id,name,filters,enabled,radius_km) "
                                    "VALUES (%s,'Fiesta',%s,true,%s) RETURNING id", user, Jsonb(filters), radius)
            ids.append(row["id"])
        return ids[0], ids[1]

    async def marked(self) -> set[int]:
        rows = await self.rows("SELECT id FROM search_profiles WHERE rematch_requested_at IS NOT NULL")
        return {r["id"] for r in rows}

    async def reset(self) -> None:
        await self.rows("UPDATE search_profiles SET rematch_requested_at = NULL")

    async def stored_flag(self, user=None) -> bool:
        [row] = await self.rows("SELECT seller_filter_access FROM profiles WHERE id=%s", user or self.user)
        return row["seller_filter_access"]


class AdminAndPaymentPathTests(PlanPathCase):
    async def test_the_admin_records_a_pro_payment_and_refunds_it(self):
        self.assertEqual(await self.marked(), set())
        paid = await self.pay("pro_monthly")                              # record_commercial_payment, /admin/billing
        self.assertEqual(await self.marked(), {self.strict_id})           # only the search with seller_types
        self.assertTrue(await self.stored_flag())
        await self.reset()
        await self.rows("SELECT refund_commercial_payment(%s,'refund-001')", paid, actor=self.admin)
        self.assertEqual((await self.access())["plan"], "free")
        self.assertEqual(await self.marked(), {self.strict_id})
        self.assertFalse(await self.stored_flag())

    async def test_a_pass_payment_flips_nothing(self):
        await self.pay("pass_30")
        self.assertEqual((await self.access())["plan"], "pass")
        self.assertEqual(await self.marked(), set())

    async def test_a_pro_renewal_flips_nothing(self):
        await self.pay("pro_monthly")
        await self.reset()
        await self.pay("pro_monthly", ref="tx-002")
        self.assertEqual(await self.marked(), set())

    async def test_a_role_change(self):
        await self.rows("UPDATE profiles SET role='admin' WHERE id=%s", self.user)
        self.assertEqual(await self.marked(), {self.strict_id})
        await self.reset()
        await self.rows("UPDATE profiles SET role='user' WHERE id=%s", self.user)
        self.assertEqual(await self.marked(), {self.strict_id})

    async def test_an_admin_edits_plan_limits(self):
        await self.pay("pro_monthly")
        await self.reset()
        [cfg] = await self.rows("SELECT value FROM app_config WHERE key='plan_limits'")
        off = {**cfg["value"], "pro": {**cfg["value"]["pro"], "seller_filter": False}}
        await self.rows("SELECT admin_update_setting('app_config','plan_limits',%s,%s,%s)",
                        Jsonb(cfg["value"]), Jsonb(off), self.admin)   # /admin/config
        self.assertEqual(await self.marked(), {self.strict_id})
        self.assertFalse(await self.stored_flag())
        await self.reset()
        other = {**off, "pro": {**off["pro"], "max_profiles": 21}}
        await self.rows("SELECT admin_update_setting('app_config','plan_limits',%s,%s,%s)",
                        Jsonb(off), Jsonb(other), self.admin)
        self.assertEqual(await self.marked(), set())                      # another key: nothing flips


class MercadoPagoPathTests(PlanPathCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.mp_config = await self.rows("SELECT key,value FROM app_config WHERE key IN ('commercial_pilot','agency_founders')")
        await self.rows("UPDATE app_config SET value='{\"enabled\":true}' WHERE key='commercial_pilot'")
        self.offer = (await self.rows("SELECT value FROM app_config WHERE key='pro_offer'"))[0]["value"]

    async def asyncTearDown(self):
        await self.rows("UPDATE billing_checkouts SET status='cancelled'")
        for row in self.mp_config:
            await self.rows("UPDATE app_config SET value=%s WHERE key=%s", Jsonb(row["value"]), row["key"])
        await super().asyncTearDown()

    async def apply(self, checkout, status="approved"):
        return (await self.rows("SELECT apply_mercadopago_payment(%s,'7001',%s,%s::numeric,'ARS',now(),now(),"
                                "now()+interval '1 month') AS id", checkout["id"], status, checkout["amount"]))[0]["id"]

    async def test_the_webhook_approves_pro_and_then_refunds_it(self):
        checkout = (await self.rows("SELECT begin_billing_checkout(%s,'pro_monthly','buyer@automotive.test',%s,%s) AS v",
                                    self.user, self.offer["version"], self.offer["pro_monthly"]["amount"]))[0]["v"]
        await self.apply(checkout, "pending")
        self.assertEqual(await self.marked(), set())                      # nothing paid yet
        await self.apply(checkout)
        self.assertEqual((await self.access())["plan"], "pro")
        self.assertEqual(await self.marked(), {self.strict_id})
        await self.reset()
        await self.apply(checkout, "refunded")
        self.assertEqual((await self.access())["plan"], "free")
        self.assertEqual(await self.marked(), {self.strict_id})


class TelegramMergeTests(PlanPathCase):
    async def test_a_strict_search_moved_to_a_pro_account(self):
        await self.pay("pro_monthly")
        await self.reset()
        [moved] = await db.create_alert(user_id=865007001, chat_id=865007001, name="Fiesta",
                                        filters={"marcas": ["Ford"], "modelos": ["Fiesta"]})
        await self.rows("UPDATE search_profiles SET filters = filters || %s WHERE id=%s",
                        Jsonb({"seller_types": ["private"]}), moved)
        [plain] = await db.create_alert(user_id=865007001, chat_id=865007001, name="Fiesta plano",
                                        filters={"marcas": ["Ford"], "modelos": ["Fiesta"], "anio_desde": 2015})
        await self.reset()
        code = (await self.rows("SELECT telegram_link_code FROM profiles WHERE id=%s", self.user))[0]["telegram_link_code"]
        self.assertEqual(await db.link_telegram(code, 865007001, 865007001), self.user)
        self.assertEqual(await self.marked(), {moved})                    # not the plain one, not the Pro's own


class TimeBasedExpiryTests(PlanPathCase):
    async def test_the_workers_tick_sweeps_a_pro_that_ran_out(self):
        from db.repos import profiles
        await self.rows("UPDATE profiles SET plan='pro', plan_expires_at = now() + interval '2 seconds' WHERE id=%s",
                        self.user)
        await self.reset()                                                # the upgrade marked it; start clean
        await asyncio.sleep(2.5)                                          # the clock passes, nothing is written
        [row] = await self.rows("SELECT plan_feature(%s,'seller_filter') AS v", self.user)
        self.assertFalse(row["v"])
        self.assertTrue(await self.stored_flag())                         # stale until the sweep
        self.assertEqual(await self.marked(), set())
        await profiles.enabled_profiles()                                 # scheduler tick: expire_commercial_access()
        self.assertEqual(await self.marked(), {self.strict_id})
        self.assertFalse(await self.stored_flag())
        await self.reset()
        await profiles.enabled_profiles()
        self.assertEqual(await self.marked(), set())                      # once


class RematchSemanticsTests(Pro01Case):
    """The rematch a plan change asks for (worker/pipeline/rematch.py): the
    strict filter applied or lifted, without a second notice."""

    async def notices(self) -> dict[int, int]:
        rows = await self.rows("SELECT listing_id, count(*)::int AS n FROM notifications "
                               " WHERE listing_id IS NOT NULL GROUP BY listing_id")
        return {r["listing_id"]: r["n"] for r in rows}

    async def card(self, listing_id: int) -> dict | None:
        rows = await self.rows("SELECT is_backfill, seller_unknown FROM match_cards "
                               " WHERE search_profile_id=%s AND listing_id=%s", self.profile, listing_id)
        return rows[0] if rows else None

    async def unmark(self) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET rematch_requested_at = NULL WHERE id=%s", (self.profile,))

    async def tick(self) -> None:
        """What the scheduler does every tick: sweep (expire_commercial_access) and rematch."""
        from db.repos import profiles
        await profiles.enabled_profiles()
        await rematch.run_pending()

    async def test_downgrade_and_upgrade(self):
        await self.plan("pass")
        await self.strict("private")
        await self.unmark()
        dealer = await self.seller_listing("dealer")
        private = await self.seller_listing("private")
        unknown = await self.seller_listing(None)
        await self.crawl(dealer, private, unknown)                        # Particular: a soft preference
        before = await self.notices()
        self.assertEqual(set(before), {dealer, private, unknown})
        self.assertFalse((await self.card(unknown))["seller_unknown"])

        await self.plan("pro")                                            # upgrade: marked, then the rematch
        [row] = await self.rows("SELECT rematch_requested_at FROM search_profiles WHERE id=%s", self.profile)
        self.assertIsNotNone(row["rematch_requested_at"])
        await self.tick()
        self.assertIsNone(await self.card(dealer))                        # dropped at once
        self.assertEqual((await self.card(private))["seller_unknown"], False)
        self.assertEqual((await self.card(unknown))["seller_unknown"], True)    # «vendedor sin dato»
        self.assertEqual(await self.notices(), before)                    # nothing notified

        await self.plan("pass")                                           # downgrade
        await self.tick()
        self.assertTrue((await self.card(dealer))["is_backfill"])         # back, as backfill
        self.assertFalse((await self.card(unknown))["seller_unknown"])
        self.assertEqual(await self.notices(), before)                    # matched before: not notified again

        await self.crawl(dealer)                                          # and a later crawl doesn't either
        self.assertEqual(await self.notices(), before)

    async def test_a_new_match_after_the_filter_is_lifted_is_backfill(self):
        await self.plan("pro")
        await self.strict("private")
        await self.unmark()
        dealer = await self.seller_listing("dealer")
        await self.crawl(dealer)
        self.assertIsNone(await self.card(dealer))
        self.assertEqual(await self.notices(), {})

        async with db.connection() as cx:                                 # the time-based expiry, no write
            await cx.execute("ALTER TABLE profiles DISABLE TRIGGER profiles_sync_seller_filter")
            try:
                await cx.execute("UPDATE profiles SET plan_expires_at = now() - interval '1 minute' WHERE id=%s",
                                 (self.user,))
            finally:
                await cx.execute("ALTER TABLE profiles ENABLE TRIGGER profiles_sync_seller_filter")
        await self.tick()
        self.assertTrue((await self.card(dealer))["is_backfill"])         # lifted at once, as backfill
        self.assertEqual(await self.notices(), {})                        # the rematch never notifies
