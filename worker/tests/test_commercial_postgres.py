"""Commercial access and payment boundaries against an isolated local database."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import profiles, notifications, listings, matches, targets
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]


class CommercialTests(PostgresTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with db.connection() as cx:
            self.config = await (await cx.execute("SELECT key,value FROM app_config WHERE key IN ('plan_limits','commercial_pilot','pro_offer')")).fetchall()
            await cx.execute("UPDATE app_config SET value=jsonb_set(value,'{enforced}','true') WHERE key='plan_limits'")
        self.user = await self.account()
        self.admin = await self.account(admin=True)

    async def asyncTearDown(self):
        async with db.connection() as cx:
            for row in self.config:
                await cx.execute("UPDATE app_config SET value=%s WHERE key=%s", (Jsonb(row['value']), row['key']))
        await super().asyncTearDown()

    async def account(self, admin=False):
        async with db.connection() as cx:
            row = await (await cx.execute("INSERT INTO auth.users(instance_id,id,aud,role,email,created_at,updated_at) VALUES ('00000000-0000-0000-0000-000000000000',gen_random_uuid(),'authenticated','authenticated',%s,now(),now()) RETURNING id::text AS id", (f"{uuid4()}@automotive.test",))).fetchone()
            if admin:
                await cx.execute("UPDATE profiles SET role='admin' WHERE id=%s", (row['id'],))
            return row['id']

    async def rows(self, sql, *params, actor=None):
        async with db.connection() as cx:
            if actor:
                await cx.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (actor,))
                await cx.execute("SET LOCAL ROLE authenticated")
            cursor = await cx.execute(sql, params)
            return await cursor.fetchall() if cursor.description else []

    async def search(self, enabled=True):
        return (await self.rows("INSERT INTO search_profiles(user_id,name,filters,enabled) VALUES (%s,'Fiesta','{\"make\":\"Ford\",\"model\":\"Fiesta\"}',%s) RETURNING id", self.user, enabled))[0]['id']

    async def access(self):
        return (await self.rows("SELECT plan_limits_for(%s) AS v", self.user))[0]['v']

    async def pay(self, offer='pass_30', ref='tx-001', user=None, actor=None):
        return (await self.rows("SELECT record_commercial_payment(%s,%s,'Mercado Pago',%s,now(),null) AS id", user or self.user, offer, ref, actor=actor or self.admin))[0]['id']

    async def test_default_score_sort_and_recent_sort_use_publication(self):
        pid = await self.search()
        ids = []
        for name, score, published_days, detected_days in [('old-detected-today', 95, 30, 0), ('new-detected-earlier', 70, 1, 5), ('unknown', 80, None, 0)]:
            lid = (await self.rows("INSERT INTO listings(source,external_id,url,title,make,model,published_at,first_seen_at) VALUES ('mercadolibre',%s,'https://example.test/sort','Fiesta','Ford','Fiesta',now()-make_interval(days=>%s),now()-make_interval(days=>%s)) RETURNING id", name, published_days, detected_days))[0]['id']
            ids.append(lid)
            await self.rows("INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version) VALUES (%s,%s,%s,'good','{}','{}','test')", pid, lid, score)
        default = await self.rows("SELECT listing_id FROM search_results(%s)", pid, actor=self.user)
        self.assertEqual([r['listing_id'] for r in default], [ids[0], ids[2], ids[1]])
        recent = await self.rows("SELECT listing_id FROM search_results(%s,'all','recent')", pid, actor=self.user)
        self.assertEqual([r['listing_id'] for r in recent], [ids[2], ids[1], ids[0]])

    async def test_trial_never_resets_and_active_capacity_is_atomic(self):
        self.assertEqual((await self.access())['state'], 'available')
        attempts = await asyncio.gather(self.search(), self.search(), return_exceptions=True)
        self.assertEqual(sum(isinstance(x,int) for x in attempts), 1)
        self.assertTrue(any('plan_limit_exceeded' in str(x) for x in attempts))
        before = (await self.access())['trial_started_at']
        first = next(x for x in attempts if isinstance(x,int))
        await self.rows("UPDATE search_profiles SET enabled=false WHERE id=%s", first)
        second = await self.search()
        self.assertEqual((await self.access())['trial_started_at'], before)
        await self.rows("DELETE FROM search_profiles WHERE id IN (%s,%s)", first, second)
        await self.search()
        self.assertEqual((await self.access())['trial_started_at'], before)
        await self.rows("UPDATE profiles SET free_trial_started_at=now()-interval '72 hours' WHERE id=%s", self.user)
        self.assertEqual((await self.access())['state'], 'expired')
        with self.assertRaisesRegex(Exception, 'plan_access_expired'):
            await self.search()
        self.assertEqual(await profiles.enabled_profiles(), [])
        self.assertEqual((await self.access())['active_searches'], 0)

    async def test_regular_users_cannot_change_access_or_inspect_foreign_ledger(self):
        with self.assertRaisesRegex(Exception, 'permission denied'):
            await self.rows("UPDATE profiles SET free_trial_started_at=now() WHERE id=%s", self.user, actor=self.user)
        with self.assertRaisesRegex(Exception, 'permission denied'):
            await self.rows("UPDATE profiles SET plan='pro' WHERE id=%s", self.user, actor=self.user)
        with self.assertRaisesRegex(Exception, 'admin_required'):
            await self.pay(actor=self.user)
        await self.pay()
        other = await self.account()
        self.assertEqual(await self.rows("SELECT * FROM commercial_payments", actor=other), [])
        self.assertEqual(len(await self.rows("SELECT * FROM commercial_payments", actor=self.user)), 1)
        with self.assertRaisesRegex(Exception, 'permission denied'):
            await self.rows("SELECT plan_limits_for(%s)", self.user, actor=other)

    async def test_payment_idempotency_amount_snapshot_and_three_searches(self):
        first = await self.pay()
        expiry = (await self.access())['expires_at']
        self.assertEqual(await self.pay(), first)
        self.assertEqual((await self.access())['expires_at'], expiry)
        other = await self.account()
        with self.assertRaisesRegex(Exception, 'payment_reference_conflict'):
            await self.pay(user=other)
        for _ in range(3): await self.search()
        with self.assertRaisesRegex(Exception, 'plan_limit_exceeded'): await self.search()
        await self.rows("UPDATE app_config SET value=jsonb_set(value,'{pass_30,amount}','20000') WHERE key='pro_offer'")
        ledger = (await self.rows("SELECT amount,currency,period_end-period_start AS duration FROM commercial_payments WHERE id=%s", first))[0]
        self.assertEqual(ledger['amount'], 15000)
        self.assertEqual(ledger['currency'], 'ARS')
        self.assertEqual(ledger['duration'].days, 30)

    async def test_agency_renewal_and_refund_newest_first(self):
        first = await self.pay('pro_monthly')
        before = (await self.rows("SELECT plan_expires_at FROM profiles WHERE id=%s", self.user))[0]['plan_expires_at']
        second = await self.pay('pro_monthly','tx-002')
        after = (await self.rows("SELECT plan_expires_at FROM profiles WHERE id=%s", self.user))[0]['plan_expires_at']
        self.assertEqual((after-before).days,30)
        for _ in range(10): await self.search()
        with self.assertRaisesRegex(Exception,'plan_limit_exceeded'): await self.search()
        with self.assertRaisesRegex(Exception,'refund_newer_period_first'):
            await self.rows("SELECT refund_commercial_payment(%s,'refund-001')", first, actor=self.admin)
        await self.rows("SELECT refund_commercial_payment(%s,'refund-002')", second, actor=self.admin)
        self.assertEqual((await self.access())['plan'],'pro')
        await self.rows("SELECT refund_commercial_payment(%s,'refund-001')", first, actor=self.admin)
        self.assertEqual((await self.access())['state'],'available')
        self.assertEqual((await self.access())['active_searches'],0)
        await self.rows("SELECT refund_commercial_payment(%s,'refund-001')", first, actor=self.admin)
        self.assertEqual(len(await self.rows("SELECT * FROM events WHERE name='payment_refunded'")),2)

    async def test_expiry_stops_favorite_alerts_digest_and_last_minute_delivery(self):
        await self.pay()
        pid = await self.search()
        lid = (await self.rows("INSERT INTO listings(source,external_id,url,title,make,model) VALUES ('mercadolibre','saved','https://example.test/saved','Fiesta','Ford','Fiesta') RETURNING id"))[0]['id']
        await self.rows("INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version) VALUES (%s,%s,80,'high','{}','{}','test')",pid,lid)
        await self.rows("INSERT INTO user_listing_interactions(user_id,listing_id,saved) VALUES (%s,%s,true)",self.user,lid)
        await self.rows("INSERT INTO crawl_targets(source,make,model,query) VALUES ('mercadolibre','Ford','Fiesta','{}')")
        self.assertEqual(len(await listings.watchlist_queue()),1)
        self.assertEqual(len(await listings.enrichment_queue(per_source=10,max_age_days=30)),1)
        nid = (await self.rows("INSERT INTO notifications(user_id,listing_id,kind,channel,dedupe_key) VALUES (%s,%s,'price_drop','web','saved:1') RETURNING id", self.user,lid))[0]['id']
        await self.rows("UPDATE profiles SET plan_expires_at=now()-interval '1 second' WHERE id=%s", self.user)
        # A paid account with an unused trial still needs first activation to start it.
        self.assertFalse(await notifications.prepare_delivery(nid))
        self.assertEqual((await self.rows("SELECT status FROM notifications WHERE id=%s",nid))[0]['status'],'skipped')
        self.assertEqual(await notifications.digest_users(datetime.now(timezone.utc)), [])
        self.assertEqual(await listings.watchlist_queue(), [])
        self.assertEqual(await listings.enrichment_queue(per_source=10,max_age_days=30), [])
        self.assertEqual(await listings.matched_recheck_queue(unseen_hours=0,recheck_hours=0,max_age_days=30,per_source=10), [])
        self.assertEqual(await matches.rescore_queue(days=30,scoring_version="new"), [])
        self.assertEqual(await matches.matches_of_listings([lid]), [])
        self.assertEqual(await profiles.pending_rematch(), [])
        self.assertEqual(await targets.due_targets(), [])
        self.assertEqual(await self.rows("INSERT INTO notifications(user_id,kind,channel,dedupe_key) VALUES (%s,'price_drop','web','saved:2') RETURNING id",self.user), [])

    async def test_free_notifications_resolve_frequency_at_delivery(self):
        pid = await self.search()
        audience = await notifications.profile_audiences([pid])
        self.assertEqual(audience[pid]['frequency'],'daily')
        await self.pay()
        nid = (await self.rows("INSERT INTO notifications(user_id,search_profile_id,kind,channel,dedupe_key) VALUES (%s,%s,'new_match','web','new:1') RETURNING id",self.user,pid))[0]['id']
        await self.rows("UPDATE profiles SET plan_expires_at=now()-interval '1 second' WHERE id=%s",self.user)
        self.assertEqual((await self.access())['state'],'trial')
        self.assertFalse(await notifications.prepare_delivery(nid))
        self.assertEqual((await self.rows("SELECT status FROM notifications WHERE id=%s",nid))[0]['status'],'digest')
        self.assertEqual((await self.rows("SELECT notification_frequency FROM search_profiles WHERE id=%s",pid))[0]['notification_frequency'],'immediate')

    async def test_rollout_is_explicit_and_idempotent(self):
        await self.rows("UPDATE app_config SET value=jsonb_set(value,'{enforced}','false') WHERE key='plan_limits'")
        for _ in range(3): await self.search()
        self.assertIsNone((await self.access())['trial_started_at'])
        result = (await self.rows("SELECT enable_commercial_pilot() AS v",actor=self.admin))[0]['v']
        self.assertEqual(result['trials_started'],1)
        self.assertEqual(result['searches_paused'],2)
        before = (await self.access())['trial_started_at']
        self.assertTrue((await self.rows("SELECT enable_commercial_pilot() AS v",actor=self.admin))[0]['v']['already_enabled'])
        self.assertEqual((await self.access())['trial_started_at'],before)

    async def test_free_trial_rollout_keeps_paid_enrollment_closed(self):
        await self.rows("UPDATE app_config SET value=jsonb_set(value,'{enforced}','false') WHERE key='plan_limits'")
        await self.rows("UPDATE app_config SET value=jsonb_set(value,'{enabled}','false') WHERE key='commercial_pilot'")
        for _ in range(3): await self.search()
        with self.assertRaisesRegex(Exception, 'admin_required'):
            await self.rows("SELECT enable_free_trial()", actor=self.user)
        result = (await self.rows("SELECT enable_free_trial() AS v", actor=self.admin))[0]['v']
        self.assertEqual(result, {'trials_started': 1, 'searches_paused': 2})
        before = await self.access()
        self.assertEqual(before['active_searches'], 1)
        self.assertEqual(before['state'], 'trial')
        [pilot] = await self.rows("SELECT value FROM app_config WHERE key='commercial_pilot'")
        self.assertFalse(pilot['value']['enabled'])
        again = (await self.rows("SELECT enable_free_trial() AS v", actor=self.admin))[0]['v']
        self.assertTrue(again['already_enabled'])
        self.assertEqual((await self.access())['trial_started_at'], before['trial_started_at'])
        with self.assertRaisesRegex(Exception, 'plan_limit_exceeded'):
            await self.search()

    async def test_new_accounts_use_email_and_web_channels(self):
        [profile] = await self.rows("SELECT default_channels FROM profiles WHERE id=%s", self.user)
        self.assertEqual(profile['default_channels'], ['email'])

    async def test_service_role_can_roll_out_free_trial(self):
        await self.rows("UPDATE app_config SET value=jsonb_set(value,'{enforced}','false') WHERE key='plan_limits'")
        await self.search()
        async with db.connection() as cx:
            await cx.execute("SELECT set_config('request.jwt.claim.role','service_role',true)")
            row = await (await cx.execute("SELECT enable_free_trial() AS v")).fetchone()
        self.assertEqual(row['v']['trials_started'], 1)

    async def test_telegram_merge_preserves_consumed_trial(self):
        [pid] = await db.create_alert(user_id=865004321,chat_id=865004321,name='Fiesta',filters={'marcas':['Ford'],'modelos':['Fiesta']})
        old = (await self.rows("SELECT user_id FROM search_profiles WHERE id=%s",pid))[0]['user_id']
        await self.rows("UPDATE profiles SET free_trial_started_at=now()-interval '4 days' WHERE id=%s",old)
        code = (await self.rows("SELECT telegram_link_code FROM profiles WHERE id=%s",self.user))[0]['telegram_link_code']
        self.assertEqual(await db.link_telegram(code,865004321,865004321),self.user)
        self.assertEqual((await self.access())['state'],'expired')
        self.assertEqual((await self.access())['active_searches'],0)
        with self.assertRaisesRegex(Exception,'plan_access_expired'): await self.search()

    async def test_server_caps_results_across_offsets(self):
        pid = await self.search()
        await self.rows("INSERT INTO listings(source,external_id,url,title,make,model) SELECT 'mercadolibre',i::text,'https://example.test/'||i,'Fiesta','Ford','Fiesta' FROM generate_series(1,60) i")
        await self.rows("INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version) SELECT %s,id,80,'high','{}','{}','test' FROM listings",pid)
        self.assertEqual(len(await self.rows("SELECT * FROM search_results(%s,'all','recent',100,0)",pid,actor=self.user)),50)
        self.assertEqual(len(await self.rows("SELECT * FROM search_results(%s,'all','recent',100,45)",pid,actor=self.user)),5)
        self.assertEqual(await self.rows("SELECT * FROM search_results(%s,'all','recent',100,50)",pid,actor=self.user),[])
        await self.rows("UPDATE profiles SET free_trial_started_at=now()-interval '4 days' WHERE id=%s",self.user)
        self.assertEqual(await self.rows("INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version) VALUES (%s,1,90,'high','{}','{}','test') ON CONFLICT(search_profile_id,listing_id) DO UPDATE SET score=90 RETURNING id",pid),[])
        with self.assertRaisesRegex(Exception,'plan_access_expired'):
            await self.rows("INSERT INTO llm_jobs(user_id,kind,input) VALUES (%s,'parse_search','{}')",self.user)
