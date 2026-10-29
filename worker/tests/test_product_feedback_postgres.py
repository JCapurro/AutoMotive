"""Queue leases and retries run against an isolated database, with no real emails."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
import db
from db.repos import product_feedback as repo
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]


class FeedbackDeliveryCase(PostgresTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with db.connection() as cx:
            user=uuid4()
            await cx.execute("INSERT INTO auth.users(instance_id,id,aud,role,email,created_at,updated_at) VALUES ('00000000-0000-0000-0000-000000000000',%s,'authenticated','authenticated',%s,now(),now())",(user,f'{user}@automotive.test'))
            row=await (await cx.execute("INSERT INTO product_feedback(user_id,request_id,email,message) VALUES (%s,%s,'buyer@automotive.test','Comentario de prueba suficientemente largo.') RETURNING id",(user,uuid4()))).fetchone()
            self.feedback=row['id']

    async def test_two_workers_do_not_claim_the_same_lead(self):
        first,second=await asyncio.gather(repo.claim(1),repo.claim(1))
        self.assertEqual(len(first)+len(second),1)
        row=(first or second)[0]
        await repo.mark_sent(row['id'],uuid4(),'wrong-claim')
        async with db.connection() as cx:
            status=await (await cx.execute('SELECT delivery_status FROM product_feedback WHERE id=%s',(self.feedback,))).fetchone()
        self.assertEqual(status['delivery_status'],'pending')
        await repo.mark_sent(row['id'],row['claim_token'],'provider-123')
        self.assertEqual(await repo.claim(),[])

    async def test_retries_back_off_and_failed_delivery_keeps_the_lead(self):
        for n in range(5):
            row=(await repo.claim())[0]
            await repo.mark_retry(row['id'],row['claim_token'],'temporary provider failure')
            async with db.connection() as cx:
                state=await (await cx.execute('SELECT delivery_status,attempts,next_attempt_at>now() AS backoff FROM product_feedback WHERE id=%s',(self.feedback,))).fetchone()
                self.assertEqual(state['attempts'],n+1)
                self.assertTrue(state['backoff'])
                if n<4:
                    self.assertEqual(state['delivery_status'],'pending')
                    self.assertEqual(await repo.claim(),[])
                    await cx.execute("UPDATE product_feedback SET next_attempt_at=now()-interval '1 second' WHERE id=%s",(self.feedback,))
        self.assertEqual(state['delivery_status'],'failed')
        self.assertEqual(await repo.claim(),[])
