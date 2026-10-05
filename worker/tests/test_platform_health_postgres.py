from datetime import datetime, timezone
from uuid import uuid4

import pytest

import db
from pgcase import PostgresTestCase, requires_db
from tools.platform_health import COLLECTORS_SQL, collector_checks

pytestmark = [pytest.mark.db, requires_db]


class HealthDatabaseTests(PostgresTestCase):
    async def test_only_enabled_accessible_search_targets_are_monitored(self):
        async with db.connection() as cx:
            user = await (await cx.execute("INSERT INTO auth.users(id,email,created_at,updated_at) VALUES (gen_random_uuid(),%s,now(),now()) RETURNING id",
                                          (f'{uuid4()}@automotive.test',))).fetchone()
            await cx.execute("INSERT INTO search_profiles(user_id,name,filters) VALUES (%s,'Health fixture','{\"make\":\"Ford\",\"model\":\"Fiesta\",\"sources\":[\"kavak\"]}')", (user['id'],))
            for source in ('kavak', 'facebook'):
                await cx.execute("INSERT INTO crawl_targets(source,make,model) VALUES (%s,'Ford','Fiesta')", (source,))
            target = await (await cx.execute("SELECT id FROM crawl_targets WHERE source='kavak'")).fetchone()
            for _ in range(3):
                await cx.execute("INSERT INTO collector_runs(source,target_id,status,finished_at,error) VALUES ('kavak',%s,'failed',now(),'RuntimeError: login wall')", (target['id'],))
            rows = await (await cx.execute(COLLECTORS_SQL, {'history':3})).fetchall()
            self.assertEqual([r['source'] for r in rows], ['kavak'])
            self.assertIn('login wall', collector_checks(rows, datetime.now(timezone.utc))['collector:kavak'])
            await cx.execute("UPDATE search_profiles SET enabled=false WHERE user_id=%s", (user['id'],))
            self.assertEqual(await (await cx.execute(COLLECTORS_SQL, {'history':3})).fetchall(), [])

    async def test_browser_roles_cannot_read_health_snapshot(self):
        async with db.connection() as cx:
            grants = await (await cx.execute("SELECT has_table_privilege('anon','public.platform_health_checks','SELECT') AS anonymous, has_table_privilege('authenticated','public.platform_health_checks','SELECT') AS signed_in, has_table_privilege('service_role','public.platform_health_checks','SELECT') AS server")).fetchone()
            self.assertEqual(grants, {'anonymous':False, 'signed_in':False, 'server':True})
            security = await (await cx.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.platform_health_checks'::regclass")).fetchone()
            self.assertTrue(security['relrowsecurity'])
