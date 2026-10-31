"""PRO-01 against Postgres (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md):
the plan flag on every read of a search (crawl, rematch, rescore, low results),
the soft preference a Particular keeps, and no second notice for a listing
the strict filter dropped and took back. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest -m db
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import low_results as low_repo
from db.repos.listings import recent_active
from db.repos.profiles import alerts_for_target, pending_rematch, profiles_by_ids
from intelligence import low_results as lr
from pgcase import requires_db
from pipeline import low_results as low_job
from pipeline import rematch, rescore, scheduler
from test_notifications_postgres import NotificationsCase

pytestmark = [pytest.mark.db, requires_db]

TARGET = {"id": None, "source": "mercadolibre", "make": "Ford", "model": "Fiesta", "body_type": None, "query": {}}


class Pro01Case(NotificationsCase):
    async def plan(self, plan: str) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE profiles SET plan = %s, plan_expires_at = now() + interval '20 days' "
                             " WHERE id = %s", (plan, self.user))

    async def strict(self, *types: str) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET filters = filters || %s, notify_min_level = 'low' "
                             " WHERE id = %s", (Jsonb({"seller_types": list(types)}), self.profile))

    async def flag(self) -> bool:
        [alert] = await profiles_by_ids([self.profile])
        return alert["profile"]["seller_filter"]

    async def seller_listing(self, seller_type: str | None, **kw) -> int:
        now = datetime.now(timezone.utc)
        return await self.listing(seller_type=seller_type, published_at=now - timedelta(minutes=5),
                                  first_seen_at=now - timedelta(minutes=5), **kw)

    async def match_of(self, listing_id: int) -> dict | None:
        rows = await self.rows("SELECT * FROM matches WHERE search_profile_id = %s AND listing_id = %s",
                               self.profile, listing_id)
        return rows[0] if rows else None

    async def rematch(self) -> None:
        """The web asked for a rematch (an edit): the backfill against what is stored."""
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET rematch_requested_at = now() WHERE id = %s", (self.profile,))
        await rematch.run_pending()

    async def crawl(self, *ids: int) -> None:
        await scheduler.process_batch(self.notifier, TARGET, list(ids), first_run=False)


class SellerFlagReadTests(Pro01Case):
    async def test_the_flag_follows_the_plan_and_the_key(self):
        await self.plan("pro")
        self.assertFalse(await self.flag())                       # Pro without seller_types: no call, false
        await self.strict("private")
        self.assertTrue(await self.flag())
        await self.plan("pass")
        self.assertFalse(await self.flag())                       # downgrade: read on every query
        async with db.connection() as cx:
            await cx.execute("UPDATE profiles SET role = 'admin' WHERE id = %s", (self.user,))
        self.assertTrue(await self.flag())

    async def test_every_read_of_a_search_carries_it(self):
        await self.plan("pro")
        await self.strict("private")
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET rematch_requested_at = now() WHERE id = %s", (self.profile,))
        [pending] = [a for a in await pending_rematch() if a["id"] == self.profile]
        self.assertTrue(pending["profile"]["seller_filter"])
        [crawl] = await alerts_for_target("mercadolibre", "Ford", "Fiesta", telegram_only=False)
        self.assertTrue(crawl["profile"]["seller_filter"])

    async def test_the_plan_switch_turns_it_off_at_once(self):
        await self.plan("pro")
        await self.strict("private")
        [limits] = await self.rows("SELECT value FROM app_config WHERE key = 'plan_limits'")
        await self.set_config("plan_limits", {**limits["value"], "pro": {**limits["value"]["pro"],
                                                                         "seller_filter": False}})
        self.assertFalse(await self.flag())


class ParticularKeepsThePreferenceTests(Pro01Case):
    """A Particular with seller_types written by SQL (a downgrade, or the API)
    still gets agencies: the stored type is a soft preference."""

    async def test_crawl_rematch_and_rescore(self):
        await self.plan("pass")
        await self.strict("private")
        dealer = await self.seller_listing("dealer")
        inferred = await self.seller_listing("private", dealer_inferred=True)
        private = await self.seller_listing("private")

        await self.rematch()                                      # the backfill
        for lid in (dealer, inferred, private):
            self.assertIsNotNone(await self.match_of(lid))
        reasons = (await self.match_of(dealer))["match_reasons"]
        self.assertEqual(reasons["seller_type"]["result"], "fail")
        self.assertEqual(reasons["seller_type"]["kind"], "soft")
        self.assertNotIn("seller", reasons)

        await rescore.rescore_listings([dealer, inferred, private])
        self.assertIsNotNone(await self.match_of(dealer))

        late = await self.seller_listing("dealer")
        await self.crawl(late)
        self.assertIsNotNone(await self.match_of(late))

    async def test_pro_drops_them(self):
        await self.plan("pro")
        await self.strict("private")
        dealer = await self.seller_listing("dealer")
        inferred = await self.seller_listing("private", dealer_inferred=True)
        private = await self.seller_listing("private")
        unknown = await self.seller_listing(None)
        await self.rematch()
        self.assertIsNone(await self.match_of(dealer))
        self.assertIsNone(await self.match_of(inferred))
        self.assertEqual((await self.match_of(private))["match_reasons"]["seller"]["result"], "ok")
        self.assertEqual((await self.match_of(unknown))["match_reasons"]["seller"]["result"], "unknown")


class NoSecondNoticeTests(Pro01Case):
    """Decisión 12: a listing the strict filter drops and takes back is matched
    again by a crawl, not notified again (dedupe_key match:<listing_id>)."""

    async def notices(self, listing_id: int) -> list[dict]:
        return await self.rows("SELECT channel::text AS channel FROM notifications WHERE dedupe_key = %s ORDER BY id",
                               f"match:{listing_id}")

    async def drop_and_take_back(self, take_back) -> None:
        await self.plan("pro")
        await self.strict("private")
        lid = await self.seller_listing("private")
        await self.crawl(lid)
        self.assertIsNotNone(await self.match_of(lid))
        first = await self.notices(lid)
        self.assertTrue(first)                                   # notified once, per channel

        async with db.connection() as cx:                        # the inference turns it into an agency
            await cx.execute("UPDATE listings SET dealer_inferred = true WHERE id = %s", (lid,))
        await rescore.rescore_listings([lid])
        self.assertIsNone(await self.match_of(lid))

        await take_back(lid)
        await self.crawl(lid)
        self.assertIsNotNone(await self.match_of(lid))           # matched again by the crawl
        self.assertEqual(await self.notices(lid), first)         # not notified again

    async def test_the_inference_goes_back(self):
        async def back(lid):
            async with db.connection() as cx:
                await cx.execute("UPDATE listings SET dealer_inferred = false WHERE id = %s", (lid,))
        await self.drop_and_take_back(back)

    async def test_the_plan_switch_is_turned_off(self):
        async def off(lid):
            [limits] = await self.rows("SELECT value FROM app_config WHERE key = 'plan_limits'")
            await self.set_config("plan_limits", {**limits["value"], "pro": {**limits["value"]["pro"],
                                                                             "seller_filter": False}})
        await self.drop_and_take_back(off)


class LowResultsFlagTests(Pro01Case):
    async def test_candidates_carry_the_flag_to_the_funnel(self):
        await self.plan("pro")
        await self.strict("private")
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET created_at = now() - interval '3 days', "
                             "  bootstrapped_at = now() WHERE id = %s", (self.profile,))
        for seller in ("dealer", "dealer", "private"):
            await self.seller_listing(seller)
        [row] = [r for r in await low_repo.candidates(max_results=3, min_age_hours=1) if r["id"] == self.profile]
        self.assertIs(row["seller_filter"], True)
        profile = low_job._profile(row)
        market = await recent_active("Ford", "Fiesta", days=30)
        fun = lr.funnel(market, profile)
        self.assertEqual(fun.only, {"seller": 2})
        self.assertEqual(fun.main_blocker, "seller")

        await self.plan("pass")
        [row] = [r for r in await low_repo.candidates(max_results=3, min_age_hours=1) if r["id"] == self.profile]
        self.assertIs(row["seller_filter"], False)
        self.assertNotEqual(lr.fingerprint(low_job._profile(row)), lr.fingerprint(profile))


class ContactMessageDbTests(Pro01Case):
    """Paso 2: matches.contact_questions, the audience's contact_email flag and
    template, and the rendered message in a Pro opportunity."""

    async def test_contact_questions_are_stored_with_the_match(self):
        await self.plan("pro")
        lid = await self.seller_listing("private", description=None, transmission=None)
        await self.rematch()
        m = await self.match_of(lid)
        self.assertIsInstance(m["contact_questions"], list)
        self.assertTrue(1 <= len(m["contact_questions"]) <= 3)
        self.assertNotIn("¿Lo seguís teniendo?", m["contact_questions"])     # only the specific ones
        self.assertIn(m["contact_questions"][0], m["seller_questions"])         # seller_questions unchanged

    async def test_audiences_carry_the_flag_and_the_template(self):
        from db.repos import notifications as repo
        await self.plan("pass")
        a = (await repo.profile_audiences([self.profile]))[self.profile]
        self.assertIs(a["contact_email"], False)
        self.assertIsNone(a["contact_template"])
        await self.plan("pro")
        async with db.connection() as cx:
            await cx.execute("UPDATE profiles SET contact_template = %s WHERE id = %s",
                             ("Buenas, ¿tu {auto} sigue?", self.user))
        a = (await repo.profile_audiences([self.profile]))[self.profile]
        self.assertIs(a["contact_email"], True)
        self.assertEqual(a["contact_template"], "Buenas, ¿tu {auto} sigue?")

    async def test_a_pro_opportunity_email_carries_the_block_and_a_bad_template_is_the_default(self):
        await self.plan("pro")
        async with db.connection() as cx:                     # written by API, past the web's lint
            await cx.execute("UPDATE profiles SET contact_template = %s WHERE id = %s",
                             ("Llamame al 11 5555-5555 {auto.__class__}", self.user))
        deal = await self.listing(seller_type="private")
        with self.assertLogs("contact_message", "WARNING"):
            await self.matched(await self.match(self.profile, deal, "high", 90))
        [row] = await self.rows("SELECT payload FROM notifications WHERE channel = 'email' AND listing_id = %s", deal)
        text = row["payload"]["contact_message"]
        self.assertTrue(text.startswith("Hola, vi tu Fiesta 2017 publicado.\n¿Lo seguís teniendo?\n"), text)
        await self.notifier.deliver()
        [mail] = [m for m in self.emails if m["subject"].startswith("🔥")]
        self.assertIn("Mensaje listo para mandar", mail["text"])
        self.assertNotIn("5555", mail["text"])
