"""PRO-02 against the local Supabase Postgres: margin_ref from comparables()'s
dealer split, and the fill of existing matches without a SCORING_VERSION bump
(matches_repo.WITHOUT_MARGIN). Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest -m db tests/test_margin_postgres.py
"""
from __future__ import annotations

import pytest

import db
from db.repos import matches as matches_repo
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

    async def test_not_enough_dealers_is_null(self):
        lid = await self.listing(price=10_300, price_usd=10_300)
        for p in (11_000, 11_100, 11_200, 11_300, 11_400):
            await self.listing(price=p, price_usd=p, seller_type="private")
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        self.assertIsNone((await self.match_row(aid, lid))["margin_ref"])

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
