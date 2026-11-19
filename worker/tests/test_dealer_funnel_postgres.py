"""The dealer funnel against Postgres (migration 20261230120000_dealer_funnel.sql).

The worker writes matches as always; a statement trigger keeps the first match
of each dealer car with each search in dealer_match_log, so the funnel still
counts it after the car is hidden and its matches are swept. Needs a database
with 20261228120000_dealer_program.sql and 20261230120000_dealer_funnel.sql
applied; skipped on one without them.
"""
from __future__ import annotations

import pytest

import db
from pgcase import requires_db
from test_dealers_postgres import ON, DealersCase

pytestmark = [pytest.mark.db, requires_db]


class FunnelCase(DealersCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            r = await (await cx.execute("SELECT to_regclass('public.dealer_match_log') IS NOT NULL AS ok")).fetchone()
        if not r["ok"]:
            self.skipTest("migration 20261230120000_dealer_funnel.sql not applied")

    async def log(self) -> list[dict]:
        return await self.rows("SELECT listing_id, search_profile_id, dealer_id, user_id::text AS user_id FROM dealer_match_log")

    async def funnel(self, dealer_id: int) -> dict:
        [r] = await self.rows("SELECT public.dealer_funnel(now() - interval '1 day', now() + interval '1 minute', %s) AS f",
                              dealer_id)
        return r["f"]


class MatchLogTests(FunnelCase):
    async def test_the_worker_match_of_a_dealer_car_is_logged_and_survives_the_sweep(self):
        await self.program(ON)
        d = await self.dealer()
        i = await self.item(d, price=10_000, currency="USD")
        await self.tick()
        lid = (await self.item_row(i))["listing_id"]
        self.assertTrue(await self.rows("SELECT id FROM matches WHERE listing_id = %s", lid))
        self.assertEqual(await self.log(), [{"listing_id": lid, "search_profile_id": self.profile, "dealer_id": d,
                                             "user_id": str(self.user)}])
        self.assertEqual((await self.funnel(d))["matched_cars"], 1)

        # Unconfirmed: the sweep deletes its matches, the funnel keeps the first match.
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET dealer_confirmed_at = now() - interval '8 days' WHERE id = %s", (lid,))
        await self.tick()
        self.assertEqual(await self.rows("SELECT id FROM matches WHERE listing_id = %s", lid), [])
        self.assertEqual(len(await self.log()), 1)
        f = await self.funnel(d)
        self.assertEqual((f["matched_cars"], f["matched_searches"], f["visible"]), (1, 1, 0))

    async def test_a_common_listing_leaves_no_log(self):
        await self.program(ON)
        lid = await self.listing()
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, "
                "                     scoring_version) VALUES (%s, %s, 70, 'good', '{}', '{}', 'test')",
                (self.profile, lid))
        self.assertTrue(await self.rows("SELECT id FROM matches WHERE listing_id = %s", lid))
        self.assertEqual(await self.log(), [])
