"""Ended ads stay as market history and never as actionable opportunities."""
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import notifications as repo
from notifications.dispatch import deliver_pending
from notifications.channels.base import SendResult
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]


class AvailabilityTests(PostgresTestCase):
    async def rows(self, sql, *params, actor=False):
        async with db.connection() as cx:
            if actor:
                await cx.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (self.user,))
                await cx.execute("SET LOCAL ROLE authenticated")
            cur = await cx.execute(sql, params)
            return await cur.fetchall() if cur.description else []

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.user = (await self.rows(
            "INSERT INTO auth.users(instance_id,id,aud,role,email,created_at,updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000000',gen_random_uuid(),"
            "'authenticated','authenticated',%s,now(),now()) RETURNING id::text AS id",
            f"{uuid4()}@automotive.test"))[0]['id']
        self.profile = (await self.rows(
            "INSERT INTO search_profiles(user_id,name,filters) VALUES (%s,'Fiesta',"
            "'{\"make\":\"Ford\",\"model\":\"Fiesta\"}') RETURNING id", self.user))[0]['id']
        self.active = await self.listing('active', 80)
        self.gone = await self.listing('gone', 99)

    async def listing(self, status, score):
        lid = (await self.rows(
            "INSERT INTO listings(source,external_id,url,title,make,model,price,price_usd,currency,status) "
            "VALUES ('mercadolibre',%s,'https://example.test/availability','Fiesta','Ford','Fiesta',"
            "10000,10000,'USD',%s) RETURNING id", str(uuid4()), status))[0]['id']
        await self.rows(
            "INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,"
            "match_reasons,scoring_version) VALUES (%s,%s,%s,'high','{}','{}','test')",
            self.profile, lid, score)
        return lid

    async def notification(self, kind, lid=None, status='queued', payload=None):
        return (await self.rows(
            "INSERT INTO notifications(user_id,search_profile_id,listing_id,kind,channel,status,"
            "dedupe_key,payload) VALUES (%s,%s,%s,%s,'web',%s,%s,%s) RETURNING id",
            self.user, self.profile, lid, kind, status, str(uuid4()), Jsonb(payload or {})))[0]['id']

    async def test_active_results_and_counts_keep_saved_history(self):
        await self.rows("INSERT INTO user_listing_interactions(user_id,listing_id,saved) VALUES (%s,%s,true)",
                        self.user, self.gone)
        for filter_name in ('new', 'opportunities', 'all'):
            rows = await self.rows("SELECT listing_id FROM search_results(%s,%s)",
                                   self.profile, filter_name, actor=True)
            self.assertEqual([r['listing_id'] for r in rows], [self.active])
        counts = (await self.rows("SELECT * FROM search_result_counts(%s)", self.profile, actor=True))[0]
        self.assertEqual(counts, dict(new_count=1, opportunities_count=1, all_count=1,
                                      saved_count=1, discarded_count=0))
        self.assertEqual((await self.rows("SELECT listing_id FROM search_results(%s,'saved')",
                                         self.profile, actor=True))[0]['listing_id'], self.gone)
        dashboard = (await self.rows("SELECT * FROM dashboard_summary()", actor=True))[0]
        self.assertEqual([dashboard[k] for k in ('new_this_week','opportunities_this_week','total','unseen')], [1]*4)
        # Filtering happens before pagination: the highest-scored ended ad consumes no slot.
        self.assertEqual((await self.rows("SELECT listing_id FROM search_results(%s,'all','score',1,0)",
                                         self.profile, actor=True))[0]['listing_id'], self.active)
        await self.rows("UPDATE listings SET status='active' WHERE id=%s", self.gone)
        self.assertEqual(len(await self.rows("SELECT * FROM search_results(%s)", self.profile, actor=True)), 2)

    async def test_dashboard_preserves_search_with_no_active_results(self):
        await self.rows("UPDATE listings SET status='gone'")
        row = (await self.rows("SELECT * FROM dashboard_summary()", actor=True))[0]
        self.assertEqual([row[k] for k in ('total','unseen','opportunities_this_week')], [0]*3)

    async def test_discarded_history_remains_accessible(self):
        await self.rows("INSERT INTO user_listing_interactions(user_id,listing_id,status) VALUES (%s,%s,'discarded')",
                        self.user, self.gone)
        self.assertEqual((await self.rows("SELECT listing_id FROM search_results(%s,'discarded')",
                                         self.profile, actor=True))[0]['listing_id'], self.gone)
        self.assertEqual((await self.rows("SELECT * FROM search_result_counts(%s)",
                                         self.profile, actor=True))[0]['discarded_count'], 1)

    async def test_retention_keeps_ended_listing_prices_and_matches(self):
        await self.rows("UPDATE listings SET last_seen_at=now()-interval '365 days'")
        await self.rows("INSERT INTO listing_snapshots(listing_id,price,currency,price_usd,attrs_hash,change_kind) "
                        "VALUES (%s,10000,'USD',10000,'test-history','new')", self.gone)
        self.assertEqual((await self.rows("SELECT purge_stale_listings(180) n"))[0]['n'], 1)
        self.assertEqual((await self.rows("SELECT id FROM listings"))[0]['id'], self.gone)
        self.assertEqual(len(await self.rows("SELECT * FROM listing_snapshots WHERE listing_id=%s", self.gone)), 1)
        self.assertEqual(len(await self.rows("SELECT * FROM matches WHERE listing_id=%s", self.gone)), 1)

    async def test_ended_ads_still_supply_comparable_prices(self):
        ref = (await self.rows("SELECT comparables(%s,1) ref", self.active))[0]['ref']
        self.assertEqual(ref['n'], 1)
        self.assertEqual(ref['median'], 10000)

    async def test_queued_alert_rechecks_status_and_gone_notification_is_allowed(self):
        for kind in ('new_match','opportunity','price_drop'):
            nid = await self.notification(kind, self.active)
            await self.rows("UPDATE listings SET status='gone' WHERE id=%s", self.active)
            self.assertFalse(await repo.prepare_delivery(nid))
            row = (await self.rows("SELECT status,error FROM notifications WHERE id=%s", nid))[0]
            self.assertEqual(row, dict(status='skipped', error='listing_unavailable'))
            await self.rows("UPDATE listings SET status='active' WHERE id=%s", self.active)
        nid = await self.notification('listing_gone', self.gone)
        self.assertTrue(await repo.prepare_delivery(nid))

    async def test_digest_only_delivers_active_matches_and_unavailability_notices(self):
        stale = await self.notification('opportunity', self.gone, status='digest')
        ended = await self.notification('listing_gone', self.gone, status='digest')
        pending = await repo.pending_digest(self.user, 'web')
        self.assertEqual([r['id'] for r in pending], [ended])
        items = [dict(section='matches',listing_id=self.gone),
                 dict(section='matches',listing_id=self.active,degraded='daily_cap'),
                 dict(section='gone',listing_id=self.gone)]
        digest = await self.notification('digest', payload={'items':items})

        class Channel:
            async def send(channel_self, notification):
                self.assertEqual(notification.payload['items'], items[1:])
                self.assertEqual(notification.payload['degraded'], 1)
                return SendResult(True)

        self.assertEqual(await deliver_pending({'web':Channel()}), 1)
        self.assertEqual((await self.rows("SELECT status FROM notifications WHERE id=%s", digest))[0]['status'], 'sent')
        self.assertEqual((await self.rows("SELECT status FROM notifications WHERE id=%s", stale))[0]['status'], 'digest')

    async def test_empty_digest_is_not_sent(self):
        nid = await self.notification('digest', payload={'items':[dict(section='matches',listing_id=self.gone)]})
        self.assertFalse(await repo.prepare_delivery(nid))
