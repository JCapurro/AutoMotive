"""Real isolated PostgreSQL checks for automatic access and hostile/repeated money events."""
import asyncio
import pytest
from psycopg.types.json import Jsonb
from pgcase import PostgresTestCase, requires_db
import test_commercial_postgres as commercial
import db

pytestmark = [pytest.mark.db, requires_db]

class MercadoPagoTests(PostgresTestCase):
    account = commercial.CommercialTests.account
    rows = commercial.CommercialTests.rows
    access = commercial.CommercialTests.access

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.config = await self.rows("SELECT key,value FROM app_config WHERE key IN ('plan_limits','commercial_pilot')")
        await self.rows("UPDATE app_config SET value=jsonb_set(value,'{enforced}','true') WHERE key='plan_limits'")
        await self.rows("UPDATE app_config SET value='{\"enabled\":true}' WHERE key='commercial_pilot'")
        self.user = await self.account()

    async def asyncTearDown(self):
        await self.rows("UPDATE billing_checkouts SET status='cancelled'")
        for row in self.config:
            await self.rows("UPDATE app_config SET value=%s WHERE key=%s", Jsonb(row['value']), row['key'])
        await super().asyncTearDown()

    async def checkout(self, offer='pass_30'):
        return (await self.rows("SELECT begin_billing_checkout(%s,%s,'buyer@automotive.test','ars-launch-2026-10',%s) AS v", self.user, offer, 15000 if offer=='pass_30' else 75000))[0]['v']

    async def apply(self, checkout, ref='123', status='approved', amount=None, start="now()", end="now()+interval '30 days'"):
        return (await self.rows(f"SELECT apply_mercadopago_payment(%s,%s,%s,%s::numeric,'ARS',now(),{start},{end}) AS id", checkout['id'], ref, status, amount or checkout['amount']))[0]['id']

    async def test_atomic_checkout_privileges_paid_access_and_terminal_refund(self):
        attempts = await asyncio.gather(self.checkout(), self.checkout())
        self.assertEqual(attempts[0]['id'], attempts[1]['id'])
        self.assertEqual(sum(row['new'] for row in attempts), 1)
        checkout = attempts[0]
        other = await self.account()
        self.assertEqual(await self.rows("SELECT * FROM billing_checkouts", actor=other), [])
        with self.assertRaisesRegex(Exception, 'permission denied'):
            await self.rows("SELECT begin_billing_checkout(%s,'pass_30','buyer@automotive.test','ars-launch-2026-10',15000)", self.user, actor=self.user)
        with self.assertRaisesRegex(Exception, 'offer_changed'):
            await self.rows("SELECT begin_billing_checkout(%s,'pass_30','buyer@automotive.test','ars-launch-2026-10',1)", self.user)
        with self.assertRaisesRegex(Exception, 'permission denied'):
            await self.rows("UPDATE billing_checkouts SET status='paid' WHERE id=%s", checkout['id'], actor=self.user)
        with self.assertRaisesRegex(Exception, 'payment_mismatch'):
            await self.apply(checkout, amount=1)
        await self.apply(checkout, status='pending')
        self.assertEqual((await self.access())['plan'], 'free')
        paid = await self.apply(checkout)
        expiry = (await self.access())['expires_at']
        self.assertEqual((await self.access())['plan'], 'pass')
        self.assertEqual(await self.apply(checkout), paid)
        self.assertEqual((await self.access())['expires_at'], expiry)
        await self.apply(checkout, status='refunded')
        await self.apply(checkout)  # Stale/replayed approval cannot restore access.
        self.assertEqual((await self.access())['plan'], 'free')
        await self.apply(checkout, ref='124', status='charged_back')  # Terminal event arrived before approval.
        await self.apply(checkout, ref='124')
        self.assertEqual((await self.access())['plan'], 'free')

    async def test_recurring_invoice_order_cancel_retains_paid_period_and_guards_delete(self):
        checkout = await self.checkout('pro_monthly')
        await self.apply(checkout, status='authorized')
        self.assertEqual((await self.access())['plan'], 'free')
        with self.assertRaisesRegex(Exception, 'cancel_subscription_before_deleting'):
            await self.rows("DELETE FROM profiles WHERE id=%s", self.user)
        await self.apply(checkout, end="now()+interval '1 month'")
        expiry = (await self.access())['expires_at']
        await self.apply(checkout, ref='125', start="now()-interval '1 month'", end="now()")
        self.assertEqual((await self.access())['expires_at'], expiry)
        await self.rows("UPDATE billing_checkouts SET status='cancelled' WHERE id=%s", checkout['id'])
        self.assertEqual((await self.access())['plan'], 'pro')
        await self.rows("DELETE FROM profiles WHERE id=%s", self.user)
        self.assertEqual(await self.rows("SELECT * FROM billing_checkouts WHERE user_id=%s", self.user), [])

    async def test_telegram_merge_keeps_checkout_payment_and_subscription_owner(self):
        target = self.user
        [search] = await db.create_alert(user_id=865004999, chat_id=865004999, name='Fiesta', filters={'marcas':['Ford'],'modelos':['Fiesta']})
        self.user = (await self.rows("SELECT user_id FROM search_profiles WHERE id=%s", search))[0]['user_id']
        checkout = await self.checkout('pro_monthly')
        paid = await self.apply(checkout, end="now()+interval '1 month'")
        code = (await self.rows("SELECT telegram_link_code FROM profiles WHERE id=%s", target))[0]['telegram_link_code']
        self.assertEqual(await db.link_telegram(code, 865004999, 865004999), target)
        self.user = target
        self.assertEqual(str((await self.rows("SELECT user_id FROM billing_checkouts WHERE id=%s", checkout['id']))[0]['user_id']), target)
        self.assertEqual((await self.access())['plan'], 'pro')
        self.assertEqual(await self.apply(checkout), paid)
