"""The plan emails against an isolated local database (docs/MAILS_DE_PLAN.md).

Audiences, claims, the ledger and the events run for real; Resend is httpx's
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
from db.repos import lifecycle_emails as repo
from notifications.channels.email import ResendEmailChannel
from notifications.lifecycle import DEFAULTS, run_lifecycle_emails
from notifications.links import Links
from notifications.service import AR
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]

LINKS = Links("https://automotive.app")
SENDER = "Ese Auto <hola@automotive.test>"
CONFIG_KEYS = ("plan_limits", "commercial_pilot", "lifecycle_emails", "pro_offer")


def art(hour: int, minute: int = 0, *, days: int = 0) -> datetime:
    """Today in Argentina (plus `days`) at hour:minute, Argentine time."""
    return datetime.combine(datetime.now(AR).date() + timedelta(days=days), time(hour, minute), tzinfo=AR)


class LifecycleCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            self.saved = await (await cx.execute(
                "SELECT key, value FROM app_config WHERE key = ANY(%s)", (list(CONFIG_KEYS),))).fetchall()
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{enforced}', 'true') "
                             " WHERE key = 'plan_limits'")
            await cx.execute("UPDATE app_config SET value = '{\"enabled\": true}' WHERE key = 'commercial_pilot'")
            await cx.execute("INSERT INTO app_config (key, value) VALUES ('lifecycle_emails', %s) "
                             "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (Jsonb(DEFAULTS),))
            await cx.execute("DELETE FROM lifecycle_emails")
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
            await self.started(row["id"], 72 + trial_ended_hours_ago)
        return row["id"]

    async def started(self, user: str, hours_ago: float) -> None:
        """The trial started that long ago (72 h later it ends)."""
        await self.rows("UPDATE profiles SET free_trial_started_at = now() - make_interval(secs => %s) "
                        " WHERE id = %s", hours_ago * 3600, user)

    async def search(self, user: str, model: str = "Fiesta", make: str = "Ford") -> int:
        """An enabled search, created without the plan triggers (the trial clock is set by the test)."""
        async with db.connection() as cx:
            await cx.execute("SET LOCAL session_replication_role = replica")
            [row] = await (await cx.execute(
                "INSERT INTO search_profiles (user_id, name, filters, enabled) VALUES (%s, %s, %s, true) RETURNING id",
                (user, f"{make} {model}", Jsonb({"make": make, "model": model})))).fetchall()
        return row["id"]

    async def match(self, profile: int, *, level: str = "good", hours_ago: float = 1, backfill: bool = False) -> None:
        """A stored match, without the plan guard (its time is set by the test)."""
        async with db.connection() as cx:
            await cx.execute("SET LOCAL session_replication_role = replica")
            n = uuid4().hex[:10]
            [listing] = await (await cx.execute(
                "INSERT INTO listings (source, external_id, url, title, make, model) "
                "VALUES ('mercadolibre', %s, %s, 'Ford Fiesta', 'Ford', 'Fiesta') RETURNING id",
                (n, f"https://example.test/{n}"))).fetchall()
            await cx.execute(
                "INSERT INTO matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, "
                "                     scoring_version, is_backfill, generated_at) "
                "VALUES (%s, %s, 80, %s, '{}', '{}', 'test', %s, now() - make_interval(secs => %s))",
                (profile, listing["id"], level, backfill, hours_ago * 3600))

    async def config(self, key: str = "lifecycle_emails", **values) -> None:
        await self.rows("UPDATE app_config SET value = value || %s WHERE key = %s", Jsonb(values), key)
        app_config.clear_config_cache()

    async def send(self, now: datetime | None = None, *, links: Links = LINKS, channel="default") -> int:
        return await run_lifecycle_emails(self.channel if channel == "default" else channel, links,
                                          now=now or art(15))

    async def ledger(self, user: str, kind: str = "trial_ended") -> dict | None:
        found = await self.rows("SELECT * FROM lifecycle_emails WHERE user_id = %s AND kind = %s", user, kind)
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

    async def events(self, user: str, name: str) -> list[dict]:
        return [r["props"] for r in await self.rows(
            "SELECT props FROM events WHERE user_id = %s AND name = %s ORDER BY id", user, name)]

    def emails(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]

    def recipients(self) -> list[str]:
        return [e["to"][0] for e in self.emails()]

    async def email_of(self, user: str) -> str:
        [row] = await self.rows("SELECT email FROM profiles WHERE id = %s", user)
        return row["email"]


class TrialEndedTests(LifecycleCase):
    """2.2: when the 72 h trial ends without a purchase."""

    async def test_an_expired_trial_that_never_paid_gets_exactly_one_email(self):
        user = await self.account(trial_ended_hours_ago=1)
        [profile] = await self.rows("SELECT email, email_unsubscribe_token::text AS token FROM profiles "
                                    " WHERE id = %s", user)

        self.assertEqual(await self.send(), 1)

        row = await self.ledger(user)
        [req] = self.requests
        self.assertEqual(req.headers["Idempotency-Key"], f"lifecycle-{row['id']}")
        body = json.loads(req.content)
        self.assertEqual((body["to"], body["from"], body["subject"]), ([profile["email"]], SENDER, "Terminó tu prueba"))
        self.assertEqual(body["headers"], {
            "List-Unsubscribe": f"<https://automotive.app/api/baja?t={profile['token']}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
        self.assertIn(f"Seguir con Particular: https://automotive.app/m/{row['id']}", body["text"])
        self.assertIn("Particular sale $15.000 por 30 días, con 3 búsquedas y pago único.", body["text"])
        self.assertIn(f"Dejar de recibir estos emails: https://automotive.app/baja?t={profile['token']}", body["text"])

        self.assertEqual((row["status"], row["provider_id"], row["attempts"], row["error"], row["target"]),
                         ("sent", "email_1", 1, None, "/app/pro?plan=pass_30"))
        self.assertEqual(await self.events(user, "lifecycle_email_sent"),
                         [{"email_id": row["id"], "kind": "trial_ended", "search_profile_id": None}])

    async def test_what_the_trial_found_and_what_was_below_comparables(self):
        user = await self.account(trial_ended_hours_ago=2)
        profile = await self.search(user, "Focus")
        for level in ("high", "high", "good"):
            await self.match(profile, level=level, hours_ago=3)
        await self.match(profile, level="high", hours_ago=1)            # after the trial ended: not counted

        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user)
        self.assertEqual((row["search_profile_id"], row["payload"]),
                         (profile, {"model": "Ford Focus", "found": 3, "below": 2}))
        [body] = self.emails()
        self.assertEqual(body["subject"], "Terminó tu prueba: encontramos 3 autos para tu búsqueda")
        self.assertIn("En 3 días encontramos 3 autos para tu búsqueda de Ford Focus, y 2 estaban por debajo "
                      "de publicaciones comparables.", body["text"])

    async def test_never_twice_not_even_after_a_restart(self):
        user = await self.account()
        self.assertEqual(await self.send(), 1)
        self.assertEqual(await self.send(), 0)
        app_config.clear_config_cache()
        await db.close_pool()
        from pgcase import TEST_DATABASE_URL
        await db.open_pool(TEST_DATABASE_URL, max_size=2)
        self.assertEqual(await self.send(art(10, days=1)), 0)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual((await self.ledger(user))["status"], "sent")

    async def test_a_trial_still_running_gets_nothing(self):
        user = await self.account(trial_ended_hours_ago=-1)     # ends in an hour
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user))

    async def test_paid_accounts_get_nothing(self):
        paid = await self.account()
        await self.pay(paid)
        granted = await self.account()      # a plan without a payment row (e.g. set by hand)
        await self.rows("UPDATE profiles SET plan = 'pass', plan_expires_at = now() + interval '10 days' "
                        " WHERE id = %s", granted)
        self.assertEqual(await self.send(), 0)
        self.assertEqual(self.requests, [])
        self.assertIsNone(await self.ledger(paid))
        self.assertIsNone(await self.ledger(granted))

    async def test_a_refunded_payment_still_counts_as_bought(self):
        user = await self.account()
        payment = await self.pay(user)
        await self.rows("SELECT refund_commercial_payment(%s, 'refund-001')", payment, actor=self.admin)
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user))

    async def test_admins_and_opted_out_accounts_get_nothing(self):
        admin = await self.account(admin=True)
        opted_out = await self.account()
        await self.rows("UPDATE profiles SET default_channels = '{web}' WHERE id = %s", opted_out)
        no_email = await self.account()
        await self.rows("UPDATE profiles SET email = NULL WHERE id = %s", no_email)
        self.assertEqual(await self.send(), 0)
        for user in (admin, opted_out, no_email):
            self.assertIsNone(await self.ledger(user))

    async def test_nothing_in_the_open_pilot_or_with_checkout_closed(self):
        user = await self.account()
        await self.config("plan_limits", enforced=False)
        self.assertEqual(await self.send(), 0)
        await self.config("plan_limits", enforced=True)
        await self.config("commercial_pilot", enabled=False)
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user))
        await self.config("commercial_pilot", enabled=True)
        self.assertEqual(await self.send(), 1)

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

        self.assertEqual(await self.send(), 2)
        self.assertCountEqual(self.recipients(), [await self.email_of(abandoned), await self.email_of(failed)])
        for user in (pending, authorized, unsynced):
            self.assertIsNone(await self.ledger(user))

    async def test_long_expired_trials_are_never_mailed(self):
        """A rollout, or re-enabling plan_limits.enforced, must not mail old trials."""
        old = await self.account(trial_ended_hours_ago=49)
        recent = await self.account(trial_ended_hours_ago=47)
        self.assertEqual(await self.send(), 1)
        self.assertEqual(self.recipients(), [await self.email_of(recent)])
        self.assertIsNone(await self.ledger(old))


class TrialNoMatchesTests(LifecycleCase):
    """2.1: 24 h into the trial without a new match."""

    async def test_a_quiet_first_day_gets_the_email_with_a_link_to_its_filters(self):
        user = await self.account(trial_ended_hours_ago=None)
        profile = await self.search(user, "Cruze", "Chevrolet")
        await self.started(user, 25)
        await self.match(profile, level="high", hours_ago=24.5, backfill=True)    # stored at creation: not new

        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "trial_no_matches")
        self.assertEqual((row["search_profile_id"], row["payload"], row["target"]),
                         (profile, {"model": "Chevrolet Cruze"}, f"/app/searches/{profile}/edit"))
        [body] = self.emails()
        self.assertEqual(body["subject"], "Tu búsqueda de Chevrolet Cruze todavía no tuvo coincidencias nuevas")
        self.assertIn(f"Ajustar filtros: https://automotive.app/m/{row['id']}", body["text"])
        self.assertEqual(await self.send(), 0)

    async def test_a_new_match_means_no_email(self):
        user = await self.account(trial_ended_hours_ago=None)
        profile = await self.search(user)
        await self.started(user, 25)
        await self.match(profile, hours_ago=2)
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user, "trial_no_matches"))

    async def test_not_before_24_hours_nor_after_the_trial(self):
        early = await self.account(trial_ended_hours_ago=None)
        await self.search(early)
        await self.started(early, 23)
        ended = await self.account(trial_ended_hours_ago=None)
        await self.search(ended)
        await self.started(ended, 73)
        self.assertEqual(await self.send(), 1)                   # only the end of `ended`'s trial
        self.assertIsNone(await self.ledger(early, "trial_no_matches"))
        self.assertIsNone(await self.ledger(ended, "trial_no_matches"))
        self.assertEqual((await self.ledger(ended))["status"], "sent")

    async def test_each_kind_once_across_the_trial(self):
        user = await self.account(trial_ended_hours_ago=None)
        await self.search(user)
        await self.started(user, 25)
        self.assertEqual(await self.send(), 1)
        await self.started(user, 73)
        self.assertEqual(await self.send(art(16)), 1)
        self.assertEqual(await self.send(art(17)), 0)
        self.assertEqual([e["subject"].split(":")[0] for e in self.emails()],
                         ["Tu búsqueda de Ford Fiesta todavía no tuvo coincidencias nuevas", "Terminó tu prueba"])

    async def test_a_kind_can_be_turned_off(self):
        user = await self.account(trial_ended_hours_ago=None)
        await self.search(user)
        await self.started(user, 25)
        await self.config(kinds={"trial_no_matches": False, "trial_ended": True})
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user, "trial_no_matches"))


class SendingTests(LifecycleCase):
    """When and how: send hours, the daily cap, failures."""

    async def test_only_inside_the_send_hours(self):
        user = await self.account()
        for now in (art(8, 59), art(21), art(23, 30), art(3)):
            with self.subTest(now=now):
                self.assertEqual(await self.send(now), 0)
        self.assertIsNone(await self.ledger(user))
        self.assertEqual(await self.send(art(9)), 1)

    async def test_daily_cap_and_the_rest_the_next_day(self):
        await self.config(max_per_day=2)
        users = [await self.account(trial_ended_hours_ago=h) for h in (5, 4, 3)]
        self.assertEqual(await self.send(art(10)), 2)
        self.assertEqual(self.recipients(), [await self.email_of(users[0]), await self.email_of(users[1])])
        self.assertEqual(await self.send(art(18)), 0)          # same Argentine day: cap reached
        self.assertIsNone(await self.ledger(users[2]))
        self.assertEqual(await self.send(art(9, 30, days=1)), 1)
        self.assertEqual(self.recipients()[-1], await self.email_of(users[2]))

    async def test_disabled_without_web_base_url_or_channel_nothing_is_claimed(self):
        """No WEB_BASE_URL means no unsubscribe link: never a plan email without opt-out."""
        user = await self.account()
        await self.config(enabled=False)
        self.assertEqual(await self.send(), 0)
        await self.config(enabled=True)
        self.assertEqual(await self.send(links=Links("")), 0)
        self.assertEqual(await self.send(channel=None), 0)
        self.assertEqual(self.requests, [])
        self.assertIsNone(await self.ledger(user))

    async def test_no_longer_eligible_when_its_turn_comes_is_skipped(self):
        paid = await self.account(trial_ended_hours_ago=2)
        opted_out = await self.account(trial_ended_hours_ago=1)
        claimed = await repo.claim("trial_ended", 48, 10)
        self.assertCountEqual([r["user_id"] for r in claimed], [paid, opted_out])
        await self.pay(paid)
        [token] = await self.rows("SELECT email_unsubscribe_token AS t FROM profiles WHERE id = %s", opted_out)
        await self.rows("SELECT unsubscribe_email(%s)", token["t"])

        self.assertEqual(await self.send(), 0)
        self.assertEqual(self.requests, [])
        for user in (paid, opted_out):
            row = await self.ledger(user)
            self.assertEqual((row["status"], row["error"], row["sent_at"]), ("skipped", "not_eligible", None))

    async def test_pending_beyond_the_window_is_skipped(self):
        """Claimed, then the worker went down for longer than the window."""
        user = await self.account()
        await repo.claim("trial_ended", 48, 10)
        await self.rows("UPDATE lifecycle_emails SET created_at = now() - interval '49 hours' WHERE user_id = %s", user)
        self.assertEqual(await self.send(), 0)
        row = await self.ledger(user)
        self.assertEqual((row["status"], row["error"]), ("skipped", "outside_window"))

    async def test_resend_errors(self):
        transient = await self.account(trial_ended_hours_ago=2)
        self.statuses = [500]
        self.assertEqual(await self.send(), 0)
        row = await self.ledger(transient)
        self.assertEqual((row["status"], row["attempts"]), ("pending", 1))
        self.assertIn("resend 500", row["error"])
        self.assertEqual(await self.send(), 1)                  # the next tick, same key
        self.assertEqual([r.headers["Idempotency-Key"] for r in self.requests], [f"lifecycle-{row['id']}"] * 2)
        row = await self.ledger(transient)
        self.assertEqual((row["status"], row["attempts"], row["error"]), ("sent", 2, None))

        permanent = await self.account(trial_ended_hours_ago=1)
        self.statuses = [422]
        self.assertEqual(await self.send(), 0)
        row = await self.ledger(permanent)
        self.assertEqual((row["status"], row["attempts"]), ("failed", 1))
        [error] = await self.rows("SELECT ref FROM pipeline_errors WHERE stage = 'lifecycle_email'")
        self.assertEqual(error["ref"], f"lifecycle:{row['id']}")
        self.assertEqual(await self.send(), 0)
        self.assertEqual(len(self.requests), 3)

    async def test_three_transient_failures_give_up(self):
        user = await self.account()
        self.statuses = [503, 503, 429]
        for _ in range(4):
            self.assertEqual(await self.send(), 0)
        row = await self.ledger(user)
        self.assertEqual((row["status"], row["attempts"]), ("failed", 3))
        self.assertEqual(len(self.requests), 3)


class MeasuringTests(LifecycleCase):
    """The events the plans document asks for."""

    async def test_trial_ended_once_per_account_with_what_the_trial_got(self):
        user = await self.account(trial_ended_hours_ago=None)
        profile = await self.search(user)
        await self.started(user, 80)
        await self.match(profile, level="high", hours_ago=60)
        await self.match(profile, level="good", hours_ago=30)
        await self.match(profile, level="high", hours_ago=2)             # after the end
        async with db.connection() as cx:          # past alerts, without the access guard
            await cx.execute("SET LOCAL session_replication_role = replica")
            await cx.execute("INSERT INTO notifications (user_id, search_profile_id, kind, channel, status, dedupe_key, "
                             "                           created_at) "
                             "VALUES (%s, %s, 'opportunity', 'email', 'sent', 'match:1', now() - interval '60 hours'), "
                             "       (%s, %s, 'digest', 'email', 'sent', 'digest:1', now() - interval '50 hours')",
                             (user, profile, user, profile))
        running = await self.account(trial_ended_hours_ago=-5)

        self.assertGreaterEqual(await repo.record_trial_ends(), 1)
        [props] = await self.events(user, "trial_ended")
        self.assertEqual({k: props[k] for k in ("results", "opportunities", "immediate_alerts_sent", "converted")},
                         {"results": 2, "opportunities": 1, "immediate_alerts_sent": 1, "converted": False})
        self.assertEqual(await self.events(running, "trial_ended"), [])
        await repo.record_trial_ends()
        self.assertEqual(len(await self.events(user, "trial_ended")), 1)

    async def test_a_click_is_recorded_and_leads_to_the_email_target(self):
        user = await self.account()
        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user)
        [click] = await self.rows("SELECT track_lifecycle_click(%s) AS target", row["id"])
        self.assertEqual(click["target"], "/app/pro?plan=pass_30")
        await self.rows("SELECT track_lifecycle_click(%s)", row["id"])
        self.assertIsNotNone((await self.ledger(user))["clicked_at"])
        self.assertEqual(await self.events(user, "lifecycle_email_clicked"),
                         [{"email_id": row["id"], "kind": "trial_ended", "search_profile_id": None}] * 2)
        [unknown] = await self.rows("SELECT track_lifecycle_click(%s) AS target", row["id"] + 1000)
        self.assertIsNone(unknown["target"])

    async def test_only_the_server_reads_the_ledger(self):
        user = await self.account()
        await self.send()
        with self.assertRaisesRegex(Exception, "permission denied"):
            await self.rows("SELECT * FROM lifecycle_emails", actor=user)
        with self.assertRaisesRegex(Exception, "permission denied"):
            await self.rows("SELECT track_lifecycle_click(1)", actor=user)
