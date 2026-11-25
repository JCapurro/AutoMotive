"""Cars that ended, out of sight sooner (docs/PLAN_DELISTADOS.md, pasos 1 y 2).

Paso 1: the matched re-check queue by source quota, by what the users have
most in view, only enabled searches, and spaced out for the cars found alive
again and again (listings.alive_checked_at / alive_unseen_checks).
Paso 2: the pre-send check of the cars a price_drop or a digest is about to tell.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from collectors.base import ListingDetail
from db.repos import listings as repo_listings
from intelligence.config import SCORING_VERSION
from notifications import dispatch
from notifications.channels.base import SendResult
from pgcase import requires_db
from pipeline import watchlist
from pipeline.ingest import IngestResult, ingest
from test_ingest_postgres import TG_USER, FakeSource, IngestCase, card

pytestmark = [pytest.mark.db, requires_db]

OTHER_USER = TG_USER + 1


def config(**values):
    """db.get_config with these keys answered (app_config of the clone stays as it is)."""
    real = db.get_config

    async def get(key, default=None):
        return values[key] if key in values else await real(key, default)
    return patch.object(db, "get_config", get)


class QueueCase(IngestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.profile = await self.fiesta_alert()

    async def matched(self, external_id: str, *, source: str = "mercadolibre", level: str = "good",
                      profile: int | None = None, unseen_hours: float = 24,
                      checked_hours_ago: float | None = 20, unseen_checks: int = 0) -> int:
        await ingest([card(external_id, source=source)], geocode=None)
        async with db.connection() as cx:
            row = await (await cx.execute(
                "UPDATE listings SET last_seen_at = now() - make_interval(secs => %s * 3600), "
                "       alive_checked_at = now() - make_interval(secs => %s * 3600), "
                "       enriched_at = now() - interval '2 days', alive_unseen_checks = %s, "
                "       detail_checked_at = now() - make_interval(secs => %s * 3600) "
                " WHERE source = %s AND external_id = %s RETURNING id",
                (unseen_hours, unseen_hours, unseen_checks, checked_hours_ago, source, external_id))).fetchone()
            await cx.execute(
                "INSERT INTO matches (search_profile_id, listing_id, score, level, score_breakdown, "
                "                     match_reasons, scoring_version) VALUES (%s, %s, 75, %s, '{}', '[]', %s)",
                (profile or self.profile, row["id"], level, SCORING_VERSION))
        return row["id"]

    async def queue(self, **kw) -> list[str]:
        args = dict(unseen_hours=6, recheck_hours=12, max_age_days=60, per_source=50)
        args.update(kw)
        return [f"{r['source'][:2]}:{r['external_id']}" if r["source"] != "mercadolibre" else r["external_id"]
                for r in await repo_listings.matched_recheck_queue(**args)]


class MatchedQueueTests(QueueCase):
    async def test_what_the_users_have_most_in_view_goes_first(self):
        await self.matched("old", unseen_hours=200, checked_hours_ago=None)   # the old order's first
        await self.matched("band", unseen_hours=48)
        digest = await self.matched("digest", unseen_hours=200)
        other = await self.fiesta_alert(user=OTHER_USER)
        await self.matched("paid", unseen_hours=200, profile=other)
        await self.matched("high", level="high", unseen_hours=200)
        async with db.connection() as cx:
            await cx.execute("UPDATE profiles SET plan = 'pro', plan_expires_at = now() + interval '30 days' "
                             " WHERE telegram_user_id = %s", (OTHER_USER,))
            await cx.execute(
                "INSERT INTO notifications (user_id, listing_id, kind, channel, status, dedupe_key) "
                "SELECT id, %s, 'new_match', 'web', 'digest', %s FROM profiles WHERE telegram_user_id = %s",
                (digest, str(uuid4()), TG_USER))

        self.assertEqual(await self.queue(), ["high", "paid", "digest", "band", "old"])
        self.assertEqual(await self.queue(per_source=2), ["high", "paid"])

    async def test_per_source_quota_by_source_with_a_default(self):
        for i in ("1", "2", "3"):
            await self.matched(i)
            await self.matched(i, source="kavak")

        self.assertEqual(await self.queue(per_source={"mercadolibre": 1, "default": 2}), ["ka:1", "ka:2", "1"])
        self.assertEqual(await self.queue(per_source={"kavak": 1, "default": 0}), ["ka:1"])
        self.assertEqual(await self.queue(per_source=2), ["ka:1", "ka:2", "1", "2"])     # the old shape
        with config(watchlist_matched={"per_source": {"mercadolibre": 3, "kavak": 0}}):
            self.assertEqual([r["external_id"] for r in await watchlist.matched_queue()], ["1", "2", "3"])
        with config(watchlist_matched={"per_source": 1}):
            self.assertEqual(len(await watchlist.matched_queue()), 2)

    async def test_only_enabled_searches_count(self):
        await self.matched("1")
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET enabled = false")
        self.assertEqual(await self.queue(), [])

    async def test_a_car_found_alive_again_and_again_is_spaced_out(self):
        await self.matched("n1-13h", unseen_checks=1, checked_hours_ago=13)     # 12 h
        await self.matched("n2-13h", unseen_checks=2, checked_hours_ago=13)     # 24 h
        await self.matched("n2-25h", unseen_checks=2, checked_hours_ago=25)
        await self.matched("n3-47h", unseen_checks=3, checked_hours_ago=47)     # 48 h
        await self.matched("n4-71h", unseen_checks=4, checked_hours_ago=71)     # 96 h, capped at 72
        await self.matched("n9-73h", unseen_checks=9, checked_hours_ago=73)

        self.assertEqual(sorted(await self.queue()), ["n1-13h", "n2-25h", "n9-73h"])
        self.assertEqual(sorted(await self.queue(backoff_max_hours=500)), ["n1-13h", "n2-25h"])

    async def test_checks_count_only_while_the_searches_dont_show_the_car(self):
        url = "https://example.test/mercadolibre/1"
        lid = await self.matched("1", unseen_hours=24, checked_hours_ago=None)
        FakeSource.details[url] = ListingDetail(url, listing=card("1"))

        await watchlist.refresh_matched()
        row = await self.listing("1")
        self.assertEqual(row["alive_unseen_checks"], 1)
        self.assertTrue((await self.rows("SELECT now() - alive_checked_at < interval '1 minute' AS fresh "
                                         "FROM listings WHERE id = %s", lid))[0]["fresh"])

        async with db.connection() as cx:                # 13 h later, still unseen: due, and a second check
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '13 hours', "
                             "       detail_checked_at = now() - interval '13 hours'")
        await watchlist.refresh_matched()
        self.assertEqual((await self.listing("1"))["alive_unseen_checks"], 2)

        await ingest([card("1")], geocode=None)          # a search sees it again: starts over
        self.assertEqual((await self.listing("1"))["alive_unseen_checks"], 0)

        # A detail read of a car the search just showed (an enrichment) is no unseen check.
        from pipeline.enrich import refresh_listing
        await refresh_listing(dict(await self.listing("1")), stage="enrich")
        self.assertEqual((await self.listing("1"))["alive_unseen_checks"], 0)

    async def test_a_worker_ahead_of_the_migration_keeps_todays_behavior(self):
        await self.matched("1", unseen_checks=3, checked_hours_ago=13)
        with patch.object(repo_listings, "_has_alive", False):
            self.assertEqual(await self.queue(), ["1"])                 # no back-off without the columns
            await ingest([card("1")], geocode=None)
        self.assertEqual((await self.listing("1"))["alive_unseen_checks"], 3)   # not written


class _Channel:
    def __init__(self) -> None:
        self.sent: list = []

    async def send(self, notification):
        self.sent.append(notification)
        return SendResult(True)


PRESEND_ON = {"enabled": True, "max_age_hours": 6, "kinds": ["price_drop", "digest"], "timeout_s": 5,
              "batch_timeout_s": 30, "max_per_pass": 40}


class PresendTests(QueueCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        [self.user] = [r["id"] for r in await self.rows(
            "SELECT id::text AS id FROM profiles WHERE telegram_user_id = %s", TG_USER)]

    async def car(self, external_id: str, *, alive_hours_ago: float) -> int:
        return await self.matched(external_id, unseen_hours=alive_hours_ago, checked_hours_ago=alive_hours_ago)

    async def notification(self, kind: str, lid: int | None = None, payload: dict | None = None) -> int:
        [row] = await self.rows(
            "INSERT INTO notifications (user_id, search_profile_id, listing_id, kind, channel, dedupe_key, payload) "
            "VALUES (%s, %s, %s, %s, 'web', %s, %s) RETURNING id",
            self.user, self.profile, lid, kind, str(uuid4()), Jsonb(payload or {}))
        return row["id"]

    async def status(self, nid: int) -> tuple:
        [row] = await self.rows("SELECT status::text, error FROM notifications WHERE id = %s", nid)
        return row["status"], row["error"]

    async def test_a_price_drop_of_a_car_that_ended_is_not_sent(self):
        lid = await self.car("1", alive_hours_ago=10)
        nid = await self.notification("price_drop", lid)
        FakeSource.details["https://example.test/mercadolibre/1"] = ListingDetail(
            "https://example.test/mercadolibre/1", gone=True, gone_reason="404")
        channel, found = _Channel(), []

        async def handled(result: IngestResult) -> None:
            found.extend(e.kind for e in result.events)

        with config(availability_presend=PRESEND_ON):
            self.assertEqual(await dispatch.deliver_pending({"web": channel}, on_presend=handled), 0)
        self.assertEqual(await self.status(nid), ("skipped", "listing_unavailable"))
        self.assertEqual((await self.listing("1"))["status"], "gone")
        self.assertEqual(found, ["listing_gone"])

    async def test_off_fresh_or_failing_the_alert_goes_out_as_it_is(self):
        stale = await self.car("1", alive_hours_ago=10)
        fresh = await self.car("2", alive_hours_ago=1)
        url = "https://example.test/mercadolibre/1"
        FakeSource.details[url] = ListingDetail(url, gone=True, gone_reason="404")

        channel = _Channel()
        off = await self.notification("price_drop", stale)                       # the switch off
        self.assertEqual(await dispatch.deliver_pending({"web": channel}), 1)
        self.assertEqual(await self.status(off), ("sent", None))

        on_fresh = await self.notification("price_drop", fresh)                  # alive an hour ago
        with config(availability_presend=PRESEND_ON):
            self.assertEqual(await dispatch.deliver_pending({"web": channel}), 1)
        self.assertEqual(await self.status(on_fresh), ("sent", None))

        async def slow(row, *, stage, llm=None):
            await asyncio.sleep(5)
            return IngestResult()

        timed_out = await self.notification("price_drop", stale)                 # the check runs out of time
        with config(availability_presend={**PRESEND_ON, "timeout_s": 0.05}), \
                patch("pipeline.enrich.refresh_listing", slow):
            self.assertEqual(await dispatch.deliver_pending({"web": channel}), 1)
        self.assertEqual(await self.status(timed_out), ("sent", None))
        self.assertEqual((await self.listing("1"))["status"], "active")

        new_match = await self.notification("new_match", stale)                  # not a kind it checks
        with config(availability_presend=PRESEND_ON):
            await dispatch.deliver_pending({"web": channel})
        self.assertEqual((await self.listing("1"))["status"], "active")
        self.assertEqual((await self.status(new_match))[1], None)

    async def test_a_digest_drops_the_cars_that_ended(self):
        ended = await self.car("1", alive_hours_ago=30)
        alive = await self.car("2", alive_hours_ago=30)
        for i, gone in (("1", True), ("2", False)):
            url = f"https://example.test/mercadolibre/{i}"
            FakeSource.details[url] = (ListingDetail(url, gone=True, gone_reason="404") if gone
                                       else ListingDetail(url, listing=card(i)))
        items = [dict(section="matches", listing_id=ended), dict(section="matches", listing_id=alive)]
        [plan] = await self.rows("SELECT public.plan_limits_for(%s::uuid)->>'plan' AS plan", self.user)
        nid = await self.notification("digest", payload={"items": items, "commercial_plan": plan["plan"]})
        channel = _Channel()

        with config(availability_presend=PRESEND_ON):
            self.assertEqual(await dispatch.deliver_pending({"web": channel}), 1)
        self.assertEqual([it["listing_id"] for it in channel.sent[0].payload["items"]], [alive])
        self.assertEqual(await self.status(nid), ("sent", None))
        self.assertTrue((await self.rows("SELECT now() - alive_checked_at < interval '1 minute' AS fresh "
                                         "FROM listings WHERE id = %s", alive))[0]["fresh"])
