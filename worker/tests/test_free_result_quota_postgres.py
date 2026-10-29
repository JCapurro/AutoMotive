"""A lifetime quota must hold when two collectors finish concurrently."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]


class FreeResultQuotaCase(PostgresTestCase):
    async def test_two_searches_share_one_atomic_quota(self):
        async with db.connection() as cx:
            config = await (await cx.execute("SELECT value FROM app_config WHERE key='plan_limits'")).fetchone()
            await cx.execute("UPDATE app_config SET value=jsonb_set(jsonb_set(value,'{enforced}','true'),'{free,max_profiles}','3') WHERE key='plan_limits'")
            user = uuid4()
            await cx.execute("INSERT INTO auth.users(instance_id,id,aud,role,email,created_at,updated_at) VALUES ('00000000-0000-0000-0000-000000000000',%s,'authenticated','authenticated',%s,now(),now())", (user, f'{user}@automotive.test'))
            profiles = []
            for radius in (1, 2):
                row = await (await cx.execute("INSERT INTO search_profiles(user_id,name,filters,radius_km) VALUES (%s,'Quota','{\"make\":\"Ford\",\"model\":\"Fiesta\"}',%s) RETURNING id", (user, radius))).fetchone()
                profiles.append(row['id'])
            rows = await (await cx.execute("INSERT INTO listings(source,external_id,url,title,make,model) SELECT 'mercadolibre','quota-concurrent-'||n,'https://example.test/'||n,'Quota','Ford','Fiesta' FROM generate_series(1,60) n RETURNING id")).fetchall()
        try:
            async def admit(profile, listing_ids):
                async with db.connection() as cx:
                    await cx.execute("INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,scoring_version) SELECT %s,id,90,'good','{}','{}','test' FROM unnest(%s::bigint[]) id", (profile, listing_ids))

            ids = [r['id'] for r in rows]
            await asyncio.gather(admit(profiles[0], ids[:30]), admit(profiles[1], ids[30:]))
            async with db.connection() as cx:
                row = await (await cx.execute("SELECT count(*) n FROM free_trial_results WHERE user_id=%s", (user,))).fetchone()
                self.assertEqual(row['n'], 50)
                row = await (await cx.execute("SELECT count(*) n FROM matches WHERE search_profile_id=ANY(%s)", (profiles,))).fetchone()
                self.assertEqual(row['n'], 60)
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value=%s WHERE key='plan_limits'", (Jsonb(config['value']),))
