"""Free-trial reminder against an isolated local database (docs/RECORDATORIO_PRUEBA.md).

The audience, the claim and the ledger run for real; Resend is httpx's
MockTransport. The database clock decides who is due, so the tests move the
trials in time (profiles.free_trial_started_at) and pass `now` only for the
Argentine send hours and the daily cap. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/<name>_test pytest
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta
from uuid import uuid4

import httpx
import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from db.repos import trial_reminders as repo
from notifications.channels.email import ResendEmailChannel
from notifications.links import Links
from notifications.service import AR
from notifications.trial_reminder import DEFAULTS, run_trial_reminders
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]

LINKS = Links("https://automotive.app")
SENDER = "Ese Auto <hola@automotive.test>"
PLANS_URL = "https://automotive.app/app/pro?utm_source=email&utm_medium=email&utm_campaign=trial_reminder"
CONFIG_KEYS = ("plan_limits", "commercial_pilot", "trial_reminder", "pro_offer")


def art(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    """Today in Argentina (plus `days`) at hour:minute, Argentine time."""
    return datetime.combine(datetime.now(AR).date() + timedelta(days=days), time(hour, minute), tzinfo=AR)


class TrialReminderTests(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            self.saved = await (await cx.execute(
                "SELECT key, value FROM app_config WHERE key = ANY(%s)", (list(CONFIG_KEYS),))).fetchall()
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{enforced}', 'true') "
                             " WHERE key = 'plan_limits'")
            await cx.execute("UPDATE app_config SET value = '{\"enabled\": true}' WHERE key = 'commercial_pilot'")
            await cx.execute("INSERT INTO app_config (key, value) VALUES ('trial_reminder', %s) "
                             "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (Jsonb(DEFAULTS),))
            await cx.execute("DELETE FROM trial_reminders")
        app_config.clear_config_cache()

        self.requests: list[httpx.Request] = []
        self.statuses: list[int] = []

        def resend(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            status = self.statuses.pop(0) if self.statuses else 200
            if status == 200:
                return httpx.Response(200, json={"id": f"email_{len(self.requests)}"})
            return httpx.Response(status, json={"message": "nope"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(resend))
        self.addAsyncCleanup(client.aclose)
        self.channel = ResendEmailChannel("re_test", SENDER, LINKS, client=client)
        self.admin = await self.account(trial_ended_hours_ago=None, admin=True)

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            for row in self.saved:
                await cx.execute("UPDATE app_config SET value = %s WHERE key = %s", (Jsonb(row["value"]), row["key"]))
            if not any(row["key"] == "trial_reminder" for row in self.saved):
                await cx.execute("DELETE FROM app_config WHERE key = 'trial_reminder'")
        app_config.clear_config_cache()
        await super().asyncTearDown()

    # -- helpers -----------------------------------------------------------

    async def rows(self, sql: str, *params, actor: str | None = None) -> list[dict]:
        async with db.connection() as cx:
            if actor:
                await cx.execute("SELECT set_config('request.jwt.claim.sub', %s, true)", (actor,))
                await cx.execute("SET LOCAL ROLE authenticated")
            cursor = await cx.execute(sql, params)
            return await cursor.fetchall() if cursor.description else []

    async def account(self, *, trial_ended_hours_ago: float | None = 1, admin: bool = False) -> str:
        """A user (profile through handle_new_user) whose 72 h trial ended that long ago."""
        [row] = await self.rows(
            "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
            "        'authenticated', %s, now(), now()) RETURNING id::text AS id", f"{uuid4()}@automotive.test")
        if admin:
            await self.rows("UPDATE profiles SET role = 'admin' WHERE id = %s", row["id"])
        if trial_ended_hours_ago is not None:
            await self.trial_ended(row["id"], trial_ended_hours_ago)
        return row["id"]

    async def trial_ended(self, user: str, hours_ago: float) -> None:
        await self.rows("UPDATE profiles SET free_trial_started_at = now() - make_interval(hours => 72) "
                        "  - make_interval(secs => %s) WHERE id = %s", hours_ago * 3600, user)

    async def config(self, key: str = "trial_reminder", **values) -> None:
        await self.rows("UPDATE app_config SET value = value || %s WHERE key = %s", Jsonb(values), key)
        app_config.clear_config_cache()

    async def remind(self, now: datetime | None = None, *, links: Links = LINKS, channel="default") -> int:
        return await run_trial_reminders(self.channel if channel == "default" else channel, links,
                                         now=now or art(15))

    async def ledger(self, user: str) -> dict | None:
        found = await self.rows("SELECT * FROM trial_reminders WHERE user_id = %s", user)
        return found[0] if found else None

    async def pay(self, user: str, ref: str = "tx-001", offer: str = "pass_30") -> int:
        [row] = await self.rows("SELECT record_commercial_payment(%s, %s, 'Mercado Pago', %s, now(), null) AS id",
                                user, offer, ref, actor=self.admin)
        return row["id"]

    async def checkout(self, user: str, status: str, *, age_hours: float = 1, sync_error: str | None = None) -> None:
        await self.rows("INSERT INTO billing_checkouts (user_id, offer, offer_version, amount, billing_email, "
                        "                               status, created_at, sync_error) "
                        "VALUES (%s, 'pass_30', 'ars-launch-2026-10', 15000, 'pago@automotive.test', %s, "
                        "        now() - make_interval(secs => %s), %s)",
                        user, status, age_hours * 3600, sync_error)

    def emails(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]

    def recipients(self) -> list[str]:
        return [e["to"][0] for e in self.emails()]

    async def email_of(self, user: str) -> str:
        [row] = await self.rows("SELECT email, email_unsubscribe_token::text AS token FROM profiles WHERE id = %s",
                                user)
        return row["email"]

    # -- the email ---------------------------------------------------------

    async def test_expired_trial_never_paid_gets_exactly_one_email(self):
        user = await self.account(trial_ended_hours_ago=1)
        [profile] = await self.rows("SELECT email, email_unsubscribe_token::text AS token FROM profiles "
                                    " WHERE id = %s", user)
        events_before = await self.rows("SELECT count(*) AS n FROM events")

        self.assertEqual(await self.remind(), 1)

        [req] = self.requests
        self.assertEqual(req.headers["Idempotency-Key"], f"trial-reminder-{user}")
        body = json.loads(req.content)
        self.assertEqual(body["to"], [profile["email"]])
        self.assertEqual(body["from"], SENDER)
        self.assertEqual(body["subject"], "Terminó tu prueba gratis en Ese Auto")
        self.assertEqual(body["headers"], {
            "List-Unsubscribe": f"<https://automotive.app/api/baja?t={profile['token']}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
        self.assertIn(f"Ver planes: {PLANS_URL}", body["text"])
        self.assertIn(f"Dejar de recibir estos emails: https://automotive.app/baja?t={profile['token']}",
                      body["text"])
        self.assertIn("Particular (ARS 15.000 por 30 días, pago único) o Agencia (ARS 75.000 por mes).",
                      body["text"])
        self.assertIn(PLANS_URL.replace("&", "&amp;"), body["html"])

        row = await self.ledger(user)
        self.assertEqual((row["status"], row["provider_id"], row["attempts"], row["error"]),
                         ("sent", "email_1", 1, None))
        self.assertIsNotNone(row["sent_at"])
        [access] = await self.rows("SELECT (plan_limits_for(%s)->>'trial_expires_at')::timestamptz AS t", user)
        self.assertEqual(row["trial_expires_at"], access["t"])
        # The ledger is the funnel record: no events (they would count as activity).
        self.assertEqual(await self.rows("SELECT count(*) AS n FROM events"), events_before)

    async def test_never_twice_not_even_after_a_restart(self):
        user = await self.account()
        self.assertEqual(await self.remind(), 1)
        self.assertEqual(await self.remind(), 0)
        # A restart: new process state, new channel, a later day.
        app_config.clear_config_cache()
        await db.close_pool()
        from pgcase import TEST_DATABASE_URL
        await db.open_pool(TEST_DATABASE_URL, max_size=2)
        self.assertEqual(await self.remind(art(10, days=1)), 0)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual((await self.ledger(user))["status"], "sent")

    # -- who gets it -------------------------------------------------------

    async def test_trial_still_running_gets_nothing(self):
        user = await self.account(trial_ended_hours_ago=-1)     # ends in an hour
        self.assertEqual(await self.remind(), 0)
        self.assertIsNone(await self.ledger(user))

    async def test_paid_accounts_get_nothing(self):
        paid = await self.account()
        await self.pay(paid)
        granted = await self.account()      # a plan without a payment row (e.g. set by hand)
        await self.rows("UPDATE profiles SET plan = 'pass', plan_expires_at = now() + interval '10 days' "
                        " WHERE id = %s", granted)
        self.assertEqual(await self.remind(), 0)
        self.assertEqual(self.requests, [])
        self.assertIsNone(await self.ledger(paid))
        self.assertIsNone(await self.ledger(granted))

    async def test_refunded_payment_still_counts_as_bought(self):
        user = await self.account()
        payment = await self.pay(user)
        await self.rows("SELECT refund_commercial_payment(%s, 'refund-001')", payment, actor=self.admin)
        [access] = await self.rows("SELECT plan_limits_for(%s)->>'state' AS state, plan::text AS plan "
                                   "  FROM profiles WHERE id = %s", user, user)
        self.assertEqual((access["state"], access["plan"]), ("expired", "free"))
        self.assertEqual(await self.remind(), 0)
        self.assertIsNone(await self.ledger(user))

    async def test_admins_and_opted_out_accounts_get_nothing(self):
        admin = await self.account(admin=True)
        opted_out = await self.account()
        await self.rows("UPDATE profiles SET default_channels = '{web}' WHERE id = %s", opted_out)
        no_email = await self.account()
        await self.rows("UPDATE profiles SET email = NULL WHERE id = %s", no_email)
        self.assertEqual(await self.remind(), 0)
        for user in (admin, opted_out, no_email):
            self.assertIsNone(await self.ledger(user))

    async def test_nothing_in_the_open_pilot_or_with_checkout_closed(self):
        user = await self.account()
        await self.config("plan_limits", enforced=False)
        self.assertEqual(await self.remind(), 0)
        await self.config("plan_limits", enforced=True)
        await self.config("commercial_pilot", enabled=False)
        self.assertEqual(await self.remind(), 0)
        self.assertIsNone(await self.ledger(user))
        await self.config("commercial_pilot", enabled=True)
        self.assertEqual(await self.remind(), 1)

    async def test_an_open_checkout_blocks_an_abandoned_one_does_not(self):
        pending = await self.account(trial_ended_hours_ago=3)
        await self.checkout(pending, "pending", age_hours=2)
        authorized = await self.account(trial_ended_hours_ago=3)
        await self.checkout(authorized, "authorized", age_hours=200)
        unsynced = await self.account(trial_ended_hours_ago=3)
        await self.checkout(unsynced, "pending", age_hours=100, sync_error="timeout")
        abandoned = await self.account(trial_ended_hours_ago=3)
        await self.checkout(abandoned, "pending", age_hours=73)
        failed = await self.account(trial_ended_hours_ago=3)
        await self.checkout(failed, "failed", age_hours=2, sync_error="rejected")

        self.assertEqual(await self.remind(), 2)
        self.assertCountEqual(self.recipients(), [await self.email_of(abandoned), await self.email_of(failed)])
        for user in (pending, authorized, unsynced):
            self.assertIsNone(await self.ledger(user))

    # -- when --------------------------------------------------------------

    async def test_long_expired_trials_are_never_mailed(self):
        """A rollout, or re-enabling plan_limits.enforced, must not mail old trials."""
        old = await self.account(trial_ended_hours_ago=49)
        recent = await self.account(trial_ended_hours_ago=47)
        self.assertEqual(await self.remind(), 1)
        self.assertEqual(self.recipients(), [await self.email_of(recent)])
        self.assertIsNone(await self.ledger(old))

    async def test_delay_hours(self):
        await self.config(delay_hours=2)
        early = await self.account(trial_ended_hours_ago=1)
        due = await self.account(trial_ended_hours_ago=3)
        self.assertEqual(await self.remind(), 1)
        self.assertEqual(self.recipients(), [await self.email_of(due)])
        self.assertIsNone(await self.ledger(early))

    async def test_only_inside_the_send_hours(self):
        user = await self.account()
        for now in (art(8, 59), art(21), art(23, 30), art(3)):
            with self.subTest(now=now):
                self.assertEqual(await self.remind(now), 0)
        self.assertIsNone(await self.ledger(user))
        self.assertEqual(self.requests, [])
        self.assertEqual(await self.remind(art(9)), 1)

    async def test_daily_cap_and_the_rest_the_next_day(self):
        await self.config(max_per_day=2)
        users = [await self.account(trial_ended_hours_ago=h) for h in (5, 4, 3)]
        self.assertEqual(await self.remind(art(10)), 2)
        self.assertEqual(self.recipients(), [await self.email_of(users[0]), await self.email_of(users[1])])
        self.assertEqual(await self.remind(art(18)), 0)          # same Argentine day: cap reached
        self.assertIsNone(await self.ledger(users[2]))
        self.assertEqual(await self.remind(art(9, 30, days=1)), 1)
        self.assertEqual(self.recipients()[-1], await self.email_of(users[2]))

    async def test_disabled_sends_and_claims_nothing(self):
        user = await self.account()
        await self.config(enabled=False)
        self.assertEqual(await self.remind(), 0)
        self.assertIsNone(await self.ledger(user))

    async def test_without_web_base_url_or_email_channel_nothing_is_claimed(self):
        """No WEB_BASE_URL means no unsubscribe link: never a commercial email without opt-out."""
        user = await self.account()
        self.assertEqual(await self.remind(links=Links("")), 0)
        self.assertEqual(await self.remind(channel=None), 0)
        self.assertEqual(self.requests, [])
        self.assertIsNone(await self.ledger(user))

    # -- between claim and send --------------------------------------------

    async def test_no_longer_eligible_when_its_turn_comes_is_skipped(self):
        paid = await self.account(trial_ended_hours_ago=2)
        opted_out = await self.account(trial_ended_hours_ago=1)
        claimed = await repo.claim(0, 48, 10)
        self.assertCountEqual([r["user_id"] for r in claimed], [paid, opted_out])
        await self.pay(paid)
        [token] = await self.rows("SELECT email_unsubscribe_token AS t FROM profiles WHERE id = %s", opted_out)
        await self.rows("SELECT unsubscribe_email(%s)", token["t"])

        self.assertEqual(await self.remind(), 0)
        self.assertEqual(self.requests, [])
        for user in (paid, opted_out):
            row = await self.ledger(user)
            self.assertEqual((row["status"], row["error"], row["sent_at"]), ("skipped", "not_eligible", None))

    async def test_pending_beyond_the_window_is_skipped(self):
        """Claimed, then the worker went down for longer than the window."""
        user = await self.account()
        await repo.claim(0, 48, 10)
        await self.rows("UPDATE trial_reminders SET trial_expires_at = now() - interval '49 hours' "
                        " WHERE user_id = %s", user)
        self.assertEqual(await self.remind(), 0)
        self.assertEqual(((await self.ledger(user))["status"], (await self.ledger(user))["error"]),
                         ("skipped", "outside_window"))

    async def test_resend_errors(self):
        transient = await self.account(trial_ended_hours_ago=2)
        self.statuses = [500]
        self.assertEqual(await self.remind(), 0)
        row = await self.ledger(transient)
        self.assertEqual((row["status"], row["attempts"]), ("pending", 1))
        self.assertIn("resend 500", row["error"])
        self.assertEqual(await self.remind(), 1)                  # the next tick, same key
        self.assertEqual([r.headers["Idempotency-Key"] for r in self.requests],
                         [f"trial-reminder-{transient}"] * 2)
        row = await self.ledger(transient)
        self.assertEqual((row["status"], row["attempts"], row["error"]), ("sent", 2, None))

        permanent = await self.account(trial_ended_hours_ago=1)
        self.statuses = [422]
        self.assertEqual(await self.remind(), 0)
        row = await self.ledger(permanent)
        self.assertEqual((row["status"], row["attempts"]), ("failed", 1))
        [error] = await self.rows("SELECT stage, ref FROM pipeline_errors WHERE stage = 'trial_reminder'")
        self.assertEqual(error["ref"], f"user:{permanent}")
        self.assertEqual(await self.remind(), 0)
        self.assertEqual(len(self.requests), 3)

    async def test_three_transient_failures_give_up(self):
        user = await self.account()
        self.statuses = [503, 503, 429]
        for _ in range(4):
            self.assertEqual(await self.remind(), 0)
        row = await self.ledger(user)
        self.assertEqual((row["status"], row["attempts"]), ("failed", 3))
        self.assertEqual(len(self.requests), 3)
