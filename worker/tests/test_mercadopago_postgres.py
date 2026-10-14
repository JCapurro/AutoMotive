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

    # -- 2.4: extending Particular (docs/PLANES_2026-10.md) -----------------

    async def pass_period(self, checkout, start, end):
        """Move a paid pass in time: its period and the profile's expiry."""
        [t] = await self.rows(f"SELECT {start} AS start, {end} AS end")
        await self.rows("UPDATE commercial_payments SET period_start = %s, period_end = %s WHERE checkout_id = %s",
                        t['start'], t['end'], checkout['id'])
        await self.rows("UPDATE profiles SET plan_expires_at = %s WHERE id = %s", t['end'], self.user)

    async def expiry(self):
        return (await self.rows("SELECT plan::text AS plan, plan_expires_at FROM profiles WHERE id=%s", self.user))[0]

    async def paused_search(self, name, paused_hours_ago):
        """A search the expiry paused, with its search_paused_by_plan event."""
        async with db.connection() as cx:
            await cx.execute("SET LOCAL session_replication_role = replica")
            [row] = await (await cx.execute(
                "INSERT INTO search_profiles (user_id, name, filters, enabled) VALUES (%s, %s, '{\"make\":\"Ford\",\"model\":\"Fiesta\"}', false) RETURNING id",
                (self.user, name))).fetchall()
            await cx.execute("INSERT INTO events (user_id, name, props, created_at) VALUES (%s, 'search_paused_by_plan', %s, now() - make_interval(hours => %s))",
                             (self.user, Jsonb({"search_profile_id": row['id']}), paused_hours_ago))
        return row['id']

    async def test_a_pass_extended_before_it_ends_adds_30_days_to_its_end(self):
        """Acceptance: a pass ending on 20/11 extended on 15/11 ends on 20/12."""
        first = await self.checkout()
        await self.apply(first, ref='301')
        await self.pass_period(first, "now() - interval '25 days'", "now() + interval '5 days'")
        before = (await self.expiry())['plan_expires_at']
        second = await self.checkout()
        await self.apply(second, ref='302')
        [extension] = await self.rows("SELECT period_start, period_end FROM commercial_payments WHERE reference='302'")
        self.assertEqual((extension['period_start'], (extension['period_end'] - before).days), (before, 30))
        self.assertEqual(await self.expiry(), {'plan': 'pass', 'plan_expires_at': extension['period_end']})
        [event] = await self.rows("SELECT props FROM events WHERE name='pass_extended' AND user_id=%s", self.user)
        self.assertTrue(event['props']['before_expiry'])
        self.assertEqual(await self.apply(second, ref='302'), (await self.rows("SELECT id FROM commercial_payments WHERE reference='302'"))[0]['id'])
        self.assertEqual(len(await self.rows("SELECT 1 FROM events WHERE name='pass_extended' AND user_id=%s", self.user)), 1)

    async def test_a_pass_bought_after_it_ended_runs_from_the_approval_and_brings_back_three_searches(self):
        """Acceptance: a pass that ended on 1/11 and is renewed on 10/11 ends on 10/12, with its searches."""
        first = await self.checkout()
        await self.apply(first, ref='311')
        await self.pass_period(first, "now() - interval '39 days'", "now() - interval '9 days'")
        oldest = await self.paused_search('Gol', 300)
        newer = [await self.paused_search(name, hours) for name, hours in (('Cruze', 220), ('Focus', 218), ('Corolla', 216))]
        renewal = await self.checkout()
        await self.apply(renewal, ref='312')
        [period] = await self.rows("SELECT paid_at, period_start, period_end FROM commercial_payments WHERE reference='312'")
        self.assertEqual((period['period_start'], (period['period_end'] - period['paid_at']).days), (period['paid_at'], 30))
        self.assertEqual((await self.access())['state'], 'paid')
        enabled = {r['id'] for r in await self.rows("SELECT id FROM search_profiles WHERE user_id=%s AND enabled", self.user)}
        self.assertEqual(enabled, set(newer))
        self.assertNotIn(oldest, enabled)
        [event] = await self.rows("SELECT props FROM events WHERE name='pass_extended' AND user_id=%s", self.user)
        self.assertFalse(event['props']['before_expiry'])
        self.assertEqual(len(await self.rows("SELECT 1 FROM events WHERE name='searches_reactivated' AND user_id=%s", self.user)), 1)

    async def test_a_trial_that_buys_particular_gets_its_search_back_without_a_pass_extended(self):
        search = await self.paused_search('Fiesta', 5)
        await self.rows("UPDATE profiles SET free_trial_started_at = now() - interval '80 hours' WHERE id=%s", self.user)
        await self.apply(await self.checkout(), ref='321')
        self.assertTrue((await self.rows("SELECT enabled FROM search_profiles WHERE id=%s", search))[0]['enabled'])
        self.assertEqual(await self.rows("SELECT 1 FROM events WHERE name='pass_extended' AND user_id=%s", self.user), [])

    async def test_agencia_and_a_pass_still_block_each_other(self):
        await self.apply(await self.checkout('pro_monthly'), ref='331', end="now()+interval '1 month'")
        # A cancelled subscription keeps its paid month: still no pass on top.
        await self.rows("UPDATE billing_checkouts SET status='cancelled' WHERE user_id=%s", self.user)
        with self.assertRaisesRegex(Exception, 'paid_plan_already_active'):
            await self.checkout()
        self.user = await self.account()
        await self.apply(await self.checkout(), ref='332')
        with self.assertRaisesRegex(Exception, 'paid_plan_already_active'):
            await self.checkout('pro_monthly')

    async def test_refunding_the_extension_or_the_running_pass(self):
        first = await self.checkout()
        await self.apply(first, ref='341')
        await self.pass_period(first, "now() - interval '25 days'", "now() + interval '5 days'")
        running_end = (await self.expiry())['plan_expires_at']
        second = await self.checkout()
        await self.apply(second, ref='342')
        extension_end = (await self.expiry())['plan_expires_at']
        await self.apply(second, ref='342', status='refunded')
        self.assertEqual(await self.expiry(), {'plan': 'pass', 'plan_expires_at': running_end})
        third = await self.checkout()
        await self.apply(third, ref='343')
        self.assertEqual((await self.expiry())['plan_expires_at'], extension_end)
        # The running pass refunded and its extension kept: access until the extension ends.
        await self.apply(first, ref='341', status='refunded')
        self.assertEqual(await self.expiry(), {'plan': 'pass', 'plan_expires_at': extension_end})
        self.assertEqual((await self.access())['state'], 'paid')

