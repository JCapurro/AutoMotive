"""Ruido de avisos against Postgres: the twin SQL (db/repos/notifications.repost_twins, alerted_twins) and
the three switches of app_config.listing_noise end to end through Notifier.on_matches / on_listing_events.
Run with TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from db.repos import notifications as repo
from pgcase import requires_db

from test_notifications_postgres import NotificationsCase

pytestmark = [pytest.mark.db, requires_db]


class NoiseCase(NotificationsCase):
    async def noise(self, **switches) -> None:
        value = {"placeholder_f2": False, "repost_groups": False, "ended_guard": False, **switches}
        async with db.connection() as cx:
            await cx.execute("INSERT INTO app_config (key, value) VALUES ('listing_noise', %s) "
                             "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (Jsonb(value),))
        app_config.clear_config_cache()

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            await cx.execute("DELETE FROM app_config WHERE key = 'listing_noise'")
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def fb(self, seller="s1", **kw) -> int:
        """A Facebook-style listing without km (so with no fingerprint), one more copy of a seller's car."""
        kw.setdefault("mileage_km", None)
        return await self.listing(source="facebook", seller_key=seller, **kw)

    async def alerted(self, listing_id: int) -> list[dict]:
        return [r for r in await self.notifications("web") if r["listing_id"] == listing_id]


class TwinSqlTests(NoiseCase):
    async def test_same_seller_same_car_without_km_are_twins(self):
        a, b = await self.fb(), await self.fb(price_usd=10_500)
        self.assertEqual(await repo.repost_twins([a, b]), [(a, b)])

    async def test_what_is_not_the_same_car(self):
        a = await self.fb()
        c = await self.fb(mileage_km=50_000)
        d = await self.fb(mileage_km=90_000)
        self.assertEqual(await repo.repost_twins([c, d]), [])            # km contradict
        ids = [a, await self.fb(seller="s2"), await self.fb(year=2018), await self.fb(price_usd=13_000)]
        self.assertEqual(await repo.repost_twins(ids), [])

    async def test_a_dealers_identical_units_are_two_cars(self):
        a = await self.fb(seller_type="dealer")
        b = await self.fb(seller_type="dealer")
        c, d = await self.fb(seller="s3", dealer_inferred=True), await self.fb(seller="s3", dealer_inferred=True)
        self.assertEqual(await repo.repost_twins([a, b, c, d]), [])

    async def test_a_fingerprint_or_repost_link_ties_them_across_sources(self):
        a = await self.listing(fingerprint="same")
        b = await self.listing(source="autocity", fingerprint="same", price_usd=9_000)
        c = await self.listing(source="carone", probable_repost_of=a)
        self.assertEqual(sorted(await repo.repost_twins([a, b, c])), sorted([(a, b), (a, c)]))


class RepostGroupsTests(NoiseCase):
    async def run_batch(self, *listing_ids, level="good", score=75):
        cands = [await self.match(self.profile, lid, level, score + i) for i, lid in enumerate(listing_ids)]
        return await self.matched(*cands)

    async def test_off_alerts_every_copy(self):
        a, b, c = await self.fb(), await self.fb(), await self.fb()
        await self.run_batch(a, b, c)
        self.assertEqual({r["listing_id"] for r in await self.notifications("web")}, {a, b, c})

    async def test_on_one_alert_per_car_in_a_batch(self):
        await self.noise(repost_groups=True)
        a, b, c = await self.fb(), await self.fb(), await self.fb()
        other = await self.fb(seller="s2")
        await self.run_batch(a, b, c, other)
        got = {r["listing_id"] for r in await self.notifications("web")}
        self.assertEqual(got, {c, other})                    # the best (highest score) of the three, and another car

    async def test_on_a_repost_of_a_car_already_alerted_gets_nothing(self):
        await self.noise(repost_groups=True)
        a = await self.fb()
        await self.run_batch(a)
        before = len(await self.notifications("web"))
        b = await self.fb()
        await self.run_batch(b)
        self.assertEqual(len(await self.notifications("web")), before)
        self.assertEqual(await self.alerted(b), [])

    async def test_on_a_repost_of_a_car_never_alerted_still_says_re_publicado(self):
        await self.noise(repost_groups=True)
        a = await self.fb()                                  # the original: never alerted to this user
        b = await self.listing(source="facebook", seller_key="s9", probable_repost_of=a, mileage_km=None)
        cand = await self.match(self.profile, b, "good", 75)
        cand = type(cand)(cand.profile_id, cand.listing_id, cand.match_id, cand.evaluation, repost=True)
        await self.matched(cand)
        rows = await self.alerted(b)
        self.assertTrue(rows and all(r["payload"].get("repost") for r in rows))

    async def test_another_user_still_hears_of_the_car(self):
        await self.noise(repost_groups=True)
        a = await self.fb()
        await self.run_batch(a)
        other_profile = await self.alert(user=555001, email="otro@automotive.test")
        b = await self.fb()
        await self.matched(await self.match(other_profile, b, "good", 80))
        self.assertTrue(await self.alerted(b))


class EndedGuardTests(NoiseCase):
    async def test_a_gone_listing_is_not_announced_only_with_the_switch(self):
        gone = await self.listing(status="gone")
        await self.matched(await self.match(self.profile, gone, "high", 90))
        self.assertTrue(await self.alerted(gone))            # off: as before
        await self.noise(ended_guard=True)
        gone2 = await self.listing(status="gone")
        await self.matched(await self.match(self.profile, gone2, "high", 90))
        self.assertEqual(await self.alerted(gone2), [])
        live = await self.listing()
        await self.matched(await self.match(self.profile, live, "high", 90))
        self.assertTrue(await self.alerted(live))
