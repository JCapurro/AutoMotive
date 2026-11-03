"""Aviso de zona (docs/AVISO_ZONA.md): a search whose zone the web just
widened waits for its rematch (rematch_requested_at). A lane that reads the
new zone before run_pending() finds listings published days ago that the old
zone left out: they are backfill, as the rematch stores them, not news; what
was first stored after the tap is news as usual. A new search counts as ready
(bootstrapped_at) only after its own 30-day backfill, never because a lane's
batch reached it first. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest -m db
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import db
from pgcase import requires_db
from pipeline import rematch, scheduler
from test_notifications_postgres import NotificationsCase

pytestmark = [pytest.mark.db, requires_db]

TARGET = {"id": None, "source": "mercadolibre", "make": "Ford", "model": "Fiesta", "body_type": None, "query": {}}
OBELISCO = (-34.6037, -58.3816)
LA_PLATA = (-34.92, -57.95)             # about 53 km away


class ZoneEditTests(NotificationsCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with db.connection() as cx:                               # 30 km, every level notifies
            await cx.execute("UPDATE search_profiles SET origin_lat = %s, origin_lon = %s, radius_km = 30, "
                             "  notify_min_level = 'low' WHERE id = %s", (*OBELISCO, self.profile))

    async def in_la_plata(self, ago: timedelta) -> int:
        when = datetime.now(timezone.utc) - ago
        return await self.listing(lat=LA_PLATA[0], lon=LA_PLATA[1], published_at=when, first_seen_at=when)

    async def crawl(self, *ids: int) -> None:
        await scheduler.process_batch(self.notifier, TARGET, list(ids), first_run=False)

    async def match_of(self, listing_id: int) -> dict | None:
        rows = await self.rows("SELECT is_backfill FROM matches WHERE search_profile_id = %s AND listing_id = %s",
                               self.profile, listing_id)
        return rows[0] if rows else None

    async def notified(self) -> set[int]:
        rows = await self.rows("SELECT DISTINCT listing_id FROM notifications WHERE listing_id IS NOT NULL")
        return {r["listing_id"] for r in rows}

    async def test_a_lane_before_the_rematch_stores_what_the_wider_zone_reaches_as_backfill(self):
        old = await self.in_la_plata(timedelta(days=3))
        await self.crawl(old)
        self.assertIsNone(await self.match_of(old))                     # outside the 30 km

        async with db.connection() as cx:                               # «Hasta 100 km» on the notice
            await cx.execute("UPDATE search_profiles SET radius_km = 100, rematch_requested_at = now() "
                             " WHERE id = %s", (self.profile,))
        await self.crawl(old)                                           # a lane reads it before run_pending()
        self.assertTrue((await self.match_of(old))["is_backfill"])      # three days old: not news
        await rematch.run_pending()
        self.assertTrue((await self.match_of(old))["is_backfill"])
        self.assertEqual(await self.notified(), set())

        new = await self.in_la_plata(timedelta(minutes=5))              # after the rematch, news again
        await self.crawl(new)
        self.assertFalse((await self.match_of(new))["is_backfill"])
        self.assertEqual(await self.notified(), {new})

    async def test_a_listing_first_stored_after_the_tap_is_news_before_the_rematch(self):
        async with db.connection() as cx:                               # «Hasta 100 km», a minute ago
            await cx.execute("UPDATE search_profiles SET radius_km = 100, "
                             "  rematch_requested_at = now() - interval '1 minute' WHERE id = %s", (self.profile,))
        new = await self.in_la_plata(timedelta(0))                      # published and stored after the tap
        await self.crawl(new)                                           # a lane reads it before run_pending()
        self.assertFalse((await self.match_of(new))["is_backfill"])
        self.assertEqual(await self.notified(), {new})

    async def test_a_batch_leaves_a_new_search_to_its_own_backfill(self):
        async with db.connection() as cx:                               # just saved: not bootstrapped
            await cx.execute("UPDATE search_profiles SET bootstrapped_at = NULL WHERE id = %s", (self.profile,))
        stock = await self.listing(lat=OBELISCO[0], lon=OBELISCO[1],
                                   published_at=datetime.now(timezone.utc) - timedelta(days=3))
        await self.crawl(await self.in_la_plata(timedelta(days=1)))     # a lane's batch: nothing in its zone
        pending = [alert["id"] for alert in await db.pending_rematch()]
        self.assertIn(self.profile, pending)                            # still waiting for its bootstrap
        await rematch.run_pending()                                     # the 30-day stock, as backfill
        self.assertTrue((await self.match_of(stock))["is_backfill"])
        self.assertNotIn(self.profile, [alert["id"] for alert in await db.pending_rematch()])
        self.assertEqual(await self.notified(), set())
