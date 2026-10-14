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
        self.config = await self.rows("SELECT key,value FROM app_config WHERE key IN ('plan_limits','commercial_pilot','agency_founders')")
        await self.rows("UPDATE billing_checkouts SET founder_number=NULL, founder_price_until=NULL")
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

    # -- precio fundador (docs/PLANES_2026-10.md) ----------------------------

    async def subscribe(self, ref, status='approved'):
        """A new account's Agencia subscription and its first Mercado Pago payment."""
        user = await self.account()
        checkout = (await self.rows("SELECT begin_billing_checkout(%s,'pro_monthly',%s,'ars-launch-2026-10',75000) AS v", user, f"buyer{ref}@automotive.test"))[0]['v']
        await self.apply(checkout, ref=ref, status=status)
        return checkout

    async def founder(self, checkout):
        return (await self.rows("SELECT founder_number, founder_price_until, user_id::text AS user_id FROM billing_checkouts WHERE id=%s", checkout['id']))[0]

    async def founder_slots(self, value):
        await self.rows("UPDATE app_config SET value=%s WHERE key='agency_founders'", Jsonb(value))

    async def test_the_first_agency_subscriptions_keep_their_price_for_six_months(self):
        first = await self.subscribe('901')
        row = await self.founder(first)
        self.assertEqual(row['founder_number'], 1)
        [paid] = await self.rows("SELECT paid_at + interval '6 months' AS until, amount FROM commercial_payments WHERE checkout_id=%s", first['id'])
        self.assertEqual(row['founder_price_until'], paid['until'])
        [event] = await self.rows("SELECT props FROM events WHERE name='agency_founder_marked' AND user_id=%s", row['user_id'])
        self.assertEqual((event['props']['founder_number'], event['props']['amount']), (1, 75000))
        # Later payments neither move the date nor take another slot.
        await self.apply(first, ref='902', start="now()-interval '30 days'", end="now()")
        self.assertEqual(await self.founder(first), row)
        self.assertEqual((await self.founder(await self.subscribe('903')))['founder_number'], 2)
        # A pass is not a subscription.
        particular = await self.checkout()
        await self.apply(particular, ref='904')
        self.assertIsNone((await self.founder(particular))['founder_number'])
        # An authorized subscription without an approved payment has not started.
        self.assertIsNone((await self.founder(await self.subscribe('905', status='authorized')))['founder_number'])

    async def test_founder_slots_run_out_and_a_bad_config_never_blocks_a_payment(self):
        await self.founder_slots({"slots": 2, "months": 6})
        numbers = [(await self.founder(await self.subscribe(ref)))['founder_number'] for ref in ('911', '912', '913')]
        self.assertEqual(numbers, [1, 2, None])
        for i, broken in enumerate(({"slots": "diez", "months": 6}, {"slots": 2.5, "months": 6}, {"slots": 10, "months": 0}, {})):
            await self.founder_slots(broken)
            late = await self.subscribe(f"92{i}")
            row = await self.founder(late)
            self.assertIsNone(row['founder_number'])
            self.assertEqual((await self.rows("SELECT plan FROM profiles WHERE id=%s", row['user_id']))[0]['plan'], 'pro')

    async def test_a_fully_refunded_subscription_frees_its_founder_slot(self):
        await self.founder_slots({"slots": 1, "months": 6})
        first = await self.subscribe('931')
        self.assertEqual((await self.founder(first))['founder_number'], 1)
        # One of two payments refunded: the subscription did start.
        await self.apply(first, ref='932', start="now()-interval '30 days'", end="now()")
        await self.apply(first, ref='932', status='refunded')
        self.assertEqual((await self.founder(first))['founder_number'], 1)
        self.assertIsNone((await self.founder(await self.subscribe('933')))['founder_number'])
        # Every payment refunded: it never started, and the next new subscription takes the slot.
        await self.apply(first, ref='931', status='charged_back')
        row = await self.founder(first)
        self.assertEqual((row['founder_number'], row['founder_price_until']), (None, None))
        self.assertEqual(len(await self.rows("SELECT 1 FROM events WHERE name='agency_founder_released' AND user_id=%s", row['user_id'])), 1)
        self.assertEqual((await self.founder(await self.subscribe('934')))['founder_number'], 1)
        # A refund that arrives before its approval never makes a founder.
        await self.founder_slots({"slots": 5, "months": 6})
        self.assertIsNone((await self.founder(await self.subscribe('935', status='refunded')))['founder_number'])

