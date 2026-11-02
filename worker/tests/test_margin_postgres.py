"""PRO-02 against the local Supabase Postgres: margin_ref from comparables()'s
dealer split, and the fill of existing matches without a SCORING_VERSION bump
(matches_repo.WITHOUT_MARGIN). Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest -m db tests/test_margin_postgres.py
"""
from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import matches as matches_repo
from intelligence import margin
from intelligence.config import SCORING_VERSION
from pgcase import requires_db
from pipeline import rematch, rescore
from test_intelligence_postgres import IntelligenceCase

pytestmark = [pytest.mark.db, requires_db]


class MarginPostgresTests(IntelligenceCase):
    async def pool(self) -> int:
        """The target at USD 10.300 and 10 comparables: 6 dealers (one of them
        inferred) and 4 private sellers."""
        lid = await self.listing(price=10_300, price_usd=10_300, seller_type="private")
        dealers = [(12_000, "dealer", False), (12_100, "dealer", False), (12_200, "dealer", False),
                   (12_300, "dealer", False), (12_400, "dealer", False), (12_500, "private", True)]
        private = [(10_800, "private", False), (10_900, "private", False), (11_000, "private", False),
                   (11_100, "private", False)]
        for price, seller_type, inferred in dealers + private:
            await self.listing(price=price, price_usd=price, seller_type=seller_type, dealer_inferred=inferred)
        return lid

    async def test_six_dealers_and_four_private_sellers(self):
        lid = await self.pool()
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        self.assertEqual((m["price_ref"]["n"], m["price_ref"]["dealer_n"], m["price_ref"]["private_n"]), (10, 6, 4))
        ref = m["margin_ref"]
        self.assertIsNotNone(ref)
        self.assertEqual((ref["dealer_n"], ref["dealer_median"]), (6, 12_250.0))
        # The search has no place: no transfer, never another zone's.
        self.assertEqual(ref["transfer"]["status"], "no_zone")
        # 12.250 - 10.300 - max(515, 300)
        self.assertEqual(ref["gross_margin_usd"], {"min": 1435.0, "max": 1435.0})

    async def test_not_enough_dealers_says_so_and_leaves_the_queue(self):
        """Juan, 02/11: {status: few_dealers, dealer_n, min_n} instead of
        null, and the startup fill converges on it."""
        lid = await self.listing(price=10_300, price_usd=10_300)
        for p in (11_000, 11_100, 11_200, 11_300, 11_400):
            await self.listing(price=p, price_usd=p, seller_type="private")
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        self.assertEqual(m["price_ref"]["dealer_n"], 0)
        self.assertEqual({k: m["margin_ref"][k] for k in ("status", "dealer_n", "min_n")},
                         {"status": "few_dealers", "dealer_n": 0, "min_n": 5})
        async with db.connection() as cx:
            await cx.execute("UPDATE matches SET margin_ref = NULL WHERE id = %s", (m["id"],))
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5, outdated_only=True)
        self.assertIn(m["id"], [q["id"] for q in queue])
        await rescore.rescore_outdated()
        self.assertEqual((await self.match_row(aid, lid))["margin_ref"]["status"], "few_dealers")
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5, outdated_only=True)
        self.assertNotIn(m["id"], [q["id"] for q in queue])

    async def test_the_startup_pass_fills_existing_matches_once(self):
        lid = await self.pool()
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        async with db.connection() as cx:
            await cx.execute("UPDATE matches SET margin_ref = NULL WHERE id = %s", (m["id"],))
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5, outdated_only=True)
        self.assertIn(m["id"], [q["id"] for q in queue])
        await rescore.rescore_outdated()
        after = await self.match_row(aid, lid)
        self.assertIsNotNone(after["margin_ref"])
        self.assertEqual(after["generated_at"], m["generated_at"])
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5, outdated_only=True)
        self.assertNotIn(m["id"], [q["id"] for q in queue])
        async with db.connection() as cx:
            n = await (await cx.execute("SELECT count(*) AS n FROM notifications WHERE match_id = %s",
                                        (m["id"],))).fetchone()
        self.assertEqual(n["n"], 0)

    async def test_a_published_down_payment_leaves_the_queue(self):
        """A listing whose published price is a down payment but whose cash
        price came from the description still matches (price_partial false),
        and margin.compute never gives it a margin: WITHOUT_MARGIN must not
        queue it again on every pass."""
        lid = await self.pool()
        async with db.connection() as cx:
            await cx.execute(
                "UPDATE listings SET description_facts = %s WHERE id = %s",
                (Jsonb({"price_check": {"published_partial": True, "published_kind": "down_payment"}}), lid))
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        self.assertIsNotNone(m)
        self.assertEqual(m["price_ref"]["dealer_n"], 6)
        self.assertIsNone(m["margin_ref"])
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5, outdated_only=True)
        self.assertNotIn(m["id"], [q["id"] for q in queue])


class ImplausiblePricePostgresTests(IntelligenceCase):
    """PRO-02 after deploy: asking_usd above 3x or below 0,4x the dealers'
    median has no margin, the fill leaves it alone, and the margins stored
    before the guard are recomputed once, without alerts."""

    pool = MarginPostgresTests.pool

    async def queue_ids(self) -> list[int]:
        return [q["id"] for q in await matches_repo.rescore_queue(
            days=14, scoring_version=SCORING_VERSION, min_n=5, outdated_only=True)]

    async def implausible_pool(self, price_usd: float) -> int:
        lid = await self.pool()
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET price = %s, price_usd = %s WHERE id = %s", (price_usd, price_usd, lid))
        return lid

    async def no_margin_and_out_of_the_queue(self, price_usd: float) -> None:
        lid = await self.implausible_pool(price_usd)
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        self.assertIsNotNone(m)
        self.assertEqual((m["price_ref"]["dealer_n"], m["price_ref"]["dealer_median"]), (6, 12_250.0))
        self.assertIsNone(m["margin_ref"])
        self.assertNotIn(m["id"], await self.queue_ids())

    async def test_above_3x_the_median(self):
        await self.no_margin_and_out_of_the_queue(40_000)     # 3,27x the median of 12.250

    async def test_below_0_4x_the_median(self):
        await self.no_margin_and_out_of_the_queue(4_850)      # 0,396x (below 65 % off the overall median: still a match)

    async def test_on_the_bound_it_has_a_margin(self):
        lid = await self.implausible_pool(36_750)              # 3x exactly
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        self.assertEqual(m["margin_ref"]["asking_usd"], 36_750.0)
        self.assertNotIn(m["id"], await self.queue_ids())

    async def test_a_margin_stored_before_the_guard_is_recomputed_once(self):
        lid = await self.implausible_pool(4_850)
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        # What compute() stored before the guard: asking 4.850 against 12.250.
        stale = {"v": 1, "status": "ok", "dealer_median": 12_250.0, "dealer_n": 6, "n": 10, "level_used": "model",
                 "asking_usd": 4_850.0, "gross_margin_usd": {"min": 7_100.0, "max": 7_100.0},
                 "gross_margin_pct": {"min": 139.4, "max": 139.4}}
        async with db.connection() as cx:
            await cx.execute("UPDATE matches SET margin_ref = %s WHERE id = %s", (Jsonb(stale), m["id"]))
        self.assertIn(m["id"], await self.queue_ids())
        await rescore.rescore_outdated()
        after = await self.match_row(aid, lid)
        self.assertIsNone(after["margin_ref"])
        self.assertEqual(after["generated_at"], m["generated_at"])
        self.assertNotIn(m["id"], await self.queue_ids())
        async with db.connection() as cx:
            n = await (await cx.execute("SELECT count(*) AS n FROM notifications WHERE match_id = %s",
                                        (m["id"],))).fetchone()
        self.assertEqual(n["n"], 0)

    async def test_a_stale_implausible_margin_of_a_fixed_price_gets_the_real_one(self):
        """The listing's price was corrected (or the median moved): the
        recompute writes the plausible margin, and the queue lets it go."""
        lid = await self.pool()
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        stale = {**m["margin_ref"], "asking_usd": 600_000.0, "gross_margin_usd": {"min": -588_250.0, "max": -588_250.0}}
        stale.pop("plausible_ratio", None)
        async with db.connection() as cx:
            await cx.execute("UPDATE matches SET margin_ref = %s WHERE id = %s", (Jsonb(stale), m["id"]))
        self.assertIn(m["id"], await self.queue_ids())
        await rescore.rescore_outdated()
        after = await self.match_row(aid, lid)
        self.assertEqual(after["margin_ref"]["gross_margin_usd"], {"min": 1435.0, "max": 1435.0})
        self.assertEqual(after["margin_ref"]["plausible_ratio"], {"min": 0.4, "max": 3.0})
        self.assertNotIn(m["id"], await self.queue_ids())

    async def test_the_config_s_bounds_reach_the_queue(self):
        """A tighter app_config.dealer_margin.plausible_ratio re-queues a margin
        stored under the default, and the recompute drops it."""
        lid = await self.pool()
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        self.assertIsNotNone(m["margin_ref"])
        tight = {"min": 0.9, "max": 3}       # 10.300 / 12.250 = 0,84
        self.assertNotIn(m["id"], await self.queue_ids())
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5,
                                                 plausible_ratio=tight, outdated_only=True)
        self.assertIn(m["id"], [q["id"] for q in queue])
        from db.repos import config as app_config
        async with db.connection() as cx:
            before = (await (await cx.execute("SELECT value FROM app_config WHERE key = 'dealer_margin'")).fetchone())["value"]
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{plausible_ratio}', %s) "
                             "WHERE key = 'dealer_margin'", (Jsonb(tight),))
        app_config.clear_config_cache()
        try:
            await rescore.rescore_outdated()
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = %s WHERE key = 'dealer_margin'", (Jsonb(before),))
            app_config.clear_config_cache()
        self.assertIsNone((await self.match_row(aid, lid))["margin_ref"])
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5,
                                                 plausible_ratio=tight, outdated_only=True)
        self.assertNotIn(m["id"], [q["id"] for q in queue])

    async def test_a_looser_config_recomputes_an_old_ref_hidden_by_the_default(self):
        """A ref from before the guard (no plausible_ratio) at 3,27x the median
        is hidden by the default bounds (margin.plausible, the web). With a
        looser config it must still be re-queued, or it would stay hidden
        and never recomputed; the recompute stores the config's bounds."""
        lid = await self.pool()
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)
        stale = {**m["margin_ref"], "asking_usd": 40_000.0}
        stale.pop("plausible_ratio", None)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET price = 40000, price_usd = 40000 WHERE id = %s", (lid,))
            await cx.execute("UPDATE matches SET margin_ref = %s WHERE id = %s", (Jsonb(stale), m["id"]))
        self.assertFalse(margin.plausible(stale))
        loose = {"min": 0.4, "max": 5}
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5,
                                                 plausible_ratio=loose, outdated_only=True)
        self.assertIn(m["id"], [q["id"] for q in queue])
        from db.repos import config as app_config
        async with db.connection() as cx:
            before = (await (await cx.execute("SELECT value FROM app_config WHERE key = 'dealer_margin'")).fetchone())["value"]
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{plausible_ratio}', %s) "
                             "WHERE key = 'dealer_margin'", (Jsonb(loose),))
        app_config.clear_config_cache()
        try:
            await rescore.rescore_outdated()
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = %s WHERE key = 'dealer_margin'", (Jsonb(before),))
            app_config.clear_config_cache()
        after = (await self.match_row(aid, lid))["margin_ref"]
        self.assertEqual(after["asking_usd"], 40_000.0)
        self.assertEqual(after["plausible_ratio"], {"min": 0.4, "max": 5.0})
        self.assertTrue(margin.plausible(after))
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION, min_n=5,
                                                 plausible_ratio=loose, outdated_only=True)
        self.assertNotIn(m["id"], [q["id"] for q in queue])
        # Back to the default: the config's bounds re-queue it, and it leaves as null.
        self.assertIn(m["id"], await self.queue_ids())
