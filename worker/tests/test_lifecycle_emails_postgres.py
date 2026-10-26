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


class PassExpiryTests(LifecycleCase):
    """2.3: 5 days before a Particular pass ends, and on its last day."""

    async def pass_user(self, ends_sql: str) -> str:
        """A Particular pass set by hand, ending at `ends_sql` (it started 30 days before)."""
        user = await self.account(trial_ended_hours_ago=None)
        await self.rows(f"UPDATE profiles SET plan = 'pass', plan_expires_at = {ends_sql} WHERE id = %s", user)
        return user

    async def test_five_days_before_with_what_the_pass_found(self):
        user = await self.pass_user("now() + interval '4 days 20 hours'")
        profile = await self.search(user, "Corolla", "Toyota")
        for level, hours in (("high", 100), ("good", 50), ("high", 800)):     # the last one is before the pass
            await self.match(profile, level=level, hours_ago=hours)

        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "pass_expiring")
        [ends] = await self.rows("SELECT extract(epoch from plan_expires_at)::bigint::text AS key FROM profiles WHERE id = %s", user)
        self.assertEqual((row["event_key"], row["target"], row["payload"]["found"], row["payload"]["below"], row["payload"]["ended"]),
                         (ends["key"], "/app/pro?plan=pass_30", 2, 1, False))
        [body] = self.emails()
        self.assertEqual(body["subject"], "Te quedan 5 días de Ese Auto")
        self.assertIn("Desde que activaste Particular encontramos 2 autos, 1 por debajo de comparables.", body["text"])
        self.assertIn(f"Extender 30 días: https://automotive.app/m/{row['id']}", body["text"])
        self.assertEqual(await self.send(), 0)

    async def test_not_too_early_nor_too_late_and_never_for_agencia(self):
        early = await self.pass_user("now() + interval '6 days'")
        late = await self.pass_user("now() + interval '3 days'")
        agency = await self.pass_user("now() + interval '4 days 20 hours'")
        await self.rows("UPDATE profiles SET plan = 'pro' WHERE id = %s", agency)
        self.assertEqual(await self.send(), 0)
        for user in (early, late, agency):
            self.assertIsNone(await self.ledger(user, "pass_expiring"))

    async def test_the_last_day(self):
        user = await self.pass_user("(date_trunc('day', now() at time zone 'America/Argentina/Buenos_Aires') "
                                    " + interval '23 hours 59 minutes') at time zone 'America/Argentina/Buenos_Aires'")
        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "pass_expires_today")
        self.assertFalse(row["payload"]["ended"])
        [body] = self.emails()
        self.assertEqual(body["subject"], "Hoy vence tu acceso a Ese Auto")
        self.assertIn("Desde mañana dejamos de buscar y de avisarte.", body["text"])

    async def test_an_extension_moves_the_end_and_its_emails(self):
        user = await self.pass_user("now() + interval '4 days 20 hours'")
        [claimed] = await repo.claim("pass_expiring", 48, 10)
        # Extended before the email went out: that end no longer applies.
        await self.rows("UPDATE profiles SET plan_expires_at = plan_expires_at + interval '30 days' WHERE id = %s", user)
        self.assertEqual(await self.send(), 0)
        row = await self.ledger(user, "pass_expiring")
        self.assertEqual((row["id"], row["status"], row["error"]), (claimed["id"], "skipped", "not_eligible"))
        # Five days before the new end, its own email.
        await self.rows("UPDATE profiles SET plan_expires_at = now() + interval '4 days 21 hours' WHERE id = %s", user)
        self.assertEqual(await self.send(), 1)
        self.assertEqual(len(await self.rows("SELECT 1 FROM lifecycle_emails WHERE user_id = %s AND kind = 'pass_expiring'", user)), 2)


class CountAfterExpiryTests(LifecycleCase):
    """2.5: 7, 14 and 21 days after access ended, how many new listings matched
    the searches it paused. The crawl side is in test_ingest_postgres.py."""

    async def ended_trial(self, days_ago: float, model: str = "Fiesta", make: str = "Ford") -> tuple[str, int]:
        """An account whose trial ended `days_ago`, with the search that end paused."""
        user = await self.account(trial_ended_hours_ago=days_ago * 24)
        profile = await self.search(user, model, make)
        await self.rows("SELECT expire_commercial_access(%s)", user)
        return user, profile

    async def ended_plan(self, plan: str, days_ago: float) -> tuple[str, int]:
        """An account whose pass (or Agencia) ended `days_ago`, never on trial."""
        user = await self.account(trial_ended_hours_ago=None)
        await self.rows("UPDATE profiles SET plan = %s, plan_expires_at = now() - make_interval(secs => %s) "
                        " WHERE id = %s", plan, days_ago * 86400, user)
        profile = await self.search(user, "Corolla", "Toyota")
        await self.rows("SELECT expire_commercial_access(%s)", user)
        return user, profile

    async def counted(self, user: str, profile: int, n: int, *, high: int = 0, end=None) -> None:
        """n listings counted for the search since its access ended, `high` of them opportunities."""
        if end is None:
            [row] = await self.rows("SELECT count_after_expiry_end(%s) AS t", user)
            end = row["t"]
        for i in range(n):
            ref = uuid4().hex[:10]
            [listing] = await self.rows(
                "INSERT INTO listings (source, external_id, url, title, make, model) "
                "VALUES ('mercadolibre', %s, %s, 'Auto', 'Ford', 'Fiesta') RETURNING id", ref, f"https://example.test/{ref}")
            await self.rows("INSERT INTO expired_search_matches (search_profile_id, listing_id, access_ended_at, level) "
                            "VALUES (%s, %s, %s, %s)", profile, listing["id"], end, "high" if i < high else "good")

    async def event_key(self, user: str, stage: int) -> str:
        [row] = await self.rows("SELECT extract(epoch from count_after_expiry_end(%s))::bigint::text AS k", user)
        return f"{row['k']}:{stage}"

    async def test_day_seven_counts_what_appeared_since_the_end(self):
        user, profile = await self.ended_trial(7 + 2 / 24)
        await self.counted(user, profile, 3, high=1)

        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "count_after_expiry")
        self.assertEqual((row["event_key"], row["search_profile_id"], row["target"]),
                         (await self.event_key(user, 7), profile, "/app/pro?plan=pass_30"))
        self.assertEqual({k: row["payload"][k] for k in ("model", "found", "below", "stage")},
                         {"model": "Ford Fiesta", "found": 3, "below": 1, "stage": 7})
        [body] = self.emails()
        self.assertEqual(body["subject"], "Aparecieron 3 autos nuevos para tu búsqueda de Ford Fiesta")
        self.assertIn("Desde que venció tu acceso aparecieron 3 autos nuevos que coinciden con tu búsqueda, "
                      "y 1 está por debajo de comparables.", body["text"])
        self.assertIn(f"Reactivar por $15.000: https://automotive.app/m/{row['id']}", body["text"])
        self.assertEqual(await self.send(), 0)                  # once per stage

    async def test_nothing_counted_means_no_email_until_something_appears_that_day(self):
        user, profile = await self.ended_trial(7 + 2 / 24)
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user, "count_after_expiry"))
        await self.counted(user, profile, 1)
        self.assertEqual(await self.send(), 1)
        self.assertEqual(self.emails()[0]["subject"], "Apareció 1 auto nuevo para tu búsqueda de Ford Fiesta")

    async def test_only_on_days_seven_fourteen_and_twenty_one(self):
        users = {}
        for days in (6.9, 7.1, 8.1, 14.1, 21.1, 22.1):
            user, profile = await self.ended_trial(days)
            await self.counted(user, profile, 2)
            users[days] = user
        self.assertEqual(await self.send(), 3)
        stages = {days: ((await self.ledger(user, "count_after_expiry")) or {}).get("payload", {}).get("stage")
                  for days, user in users.items()}
        self.assertEqual(stages, {6.9: None, 7.1: 7, 8.1: None, 14.1: 14, 21.1: 21, 22.1: None})

    async def test_once_per_account_ever(self):
        # Juan, 26/10/2026: one 2.5 email per account, not one per stage or per end.
        user, profile = await self.ended_trial(14.1)
        await self.counted(user, profile, 2)
        await self.rows("INSERT INTO lifecycle_emails (user_id, kind, event_key, target, status, sent_at) "
                        "VALUES (%s, 'count_after_expiry', 'older-end:7', '/app/pro?plan=pass_30', 'sent', "
                        "        now() - interval '7 days')", user)
        self.assertEqual(await self.send(), 0)
        # A failed or skipped one never arrived: it doesn't count.
        await self.rows("UPDATE lifecycle_emails SET status = 'failed' WHERE user_id = %s", user)
        self.assertEqual(await self.send(), 1)

    async def test_the_search_that_found_the_most_and_only_this_end(self):
        user, fiesta = await self.ended_trial(7.1)
        corolla = await self.search(user, "Corolla", "Toyota")
        await self.rows("SELECT expire_commercial_access(%s)", user)
        await self.counted(user, fiesta, 1)
        await self.counted(user, corolla, 2, high=2)
        # Counted for an older end: not this email's.
        await self.counted(user, fiesta, 5, end=datetime(2026, 1, 1, tzinfo=AR))
        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "count_after_expiry")
        self.assertEqual((row["search_profile_id"], row["payload"]["found"], row["payload"]["below"]), (corolla, 2, 2))

    async def test_an_expired_pass_too_but_not_agencia(self):
        pass_user, pass_search = await self.ended_plan("pass", 7.1)
        agency, agency_search = await self.ended_plan("pro", 7.1)
        await self.counted(pass_user, pass_search, 2)
        [end] = await self.rows("SELECT plan_expires_at AS t FROM profiles WHERE id = %s", agency)
        await self.counted(agency, agency_search, 2, end=end["t"])

        self.assertEqual(await self.send(), 1)
        self.assertIsNone(await self.ledger(agency, "count_after_expiry"))
        self.assertEqual(self.emails()[0]["subject"], "Aparecieron 2 autos nuevos para tu búsqueda de Toyota Corolla")
        self.assertEqual([r["search_profile_id"] for r in await self.rows("SELECT * FROM count_after_expiry_searches()")],
                         [pass_search])

    async def test_who_is_counted(self):
        counted, counted_search = await self.ended_trial(3)
        await self.search(counted, "Corolla", "Toyota")           # enabled after the end: not one it paused
        manual, manual_search = await self.ended_trial(3)
        await self.rows("DELETE FROM events WHERE user_id = %s AND name = 'search_paused_by_plan'", manual)
        old, _ = await self.ended_trial(22.1)
        unsubscribed, _ = await self.ended_trial(3)
        await self.rows("UPDATE profiles SET default_channels = '{web}' WHERE id = %s", unsubscribed)
        buyer, _ = await self.ended_trial(3)
        await self.rows("INSERT INTO commercial_payments (user_id, offer, offer_version, amount, currency, provider, "
                        "  reference, paid_at, period_start, period_end, refunded_at) "
                        "VALUES (%s, 'pass_30', 'v', 15000, 'ARS', 'Mercado Pago', 'tx-refunded', now() - interval '20 days', "
                        "        now() - interval '20 days', now() + interval '10 days', now() - interval '19 days')", buyer)

        searches = await self.rows("SELECT search_profile_id, user_id::text AS user_id FROM count_after_expiry_searches()")
        self.assertEqual([(r["search_profile_id"], r["user_id"]) for r in searches], [(counted_search, counted)])
        # Turning the kind off stops the counting (and its crawling) too.
        await self.config(kinds={"count_after_expiry": "false"})
        self.assertEqual(await self.rows("SELECT * FROM count_after_expiry_searches()"), [])
        await self.config(kinds={"count_after_expiry": True})
        await self.config("commercial_pilot", enabled=False)
        self.assertEqual(await self.rows("SELECT * FROM count_after_expiry_searches()"), [])

    async def test_not_while_a_checkout_is_in_progress(self):
        user, profile = await self.ended_trial(7.1)
        await self.counted(user, profile, 2)
        await self.checkout(user, "pending")
        self.assertEqual(await self.send(), 0)
        await self.rows("UPDATE billing_checkouts SET created_at = now() - interval '73 hours' WHERE user_id = %s", user)
        self.assertEqual(await self.send(), 1)

    async def test_buying_stops_them_and_records_the_reactivation(self):
        user, profile = await self.ended_trial(7.1)
        await self.counted(user, profile, 2)
        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "count_after_expiry")
        await self.rows("SELECT track_lifecycle_click(%s)", row["id"])
        silent, _ = await self.ended_trial(7.1)                    # never got a count email

        await self.pay(user)
        await self.pay(silent, "tx-silent")
        [event] = await self.events(user, "reactivated_from_count_email")
        self.assertEqual((event["email_id"], event["stage"], event["clicked"], event["days_after_email"]),
                         (row["id"], 7, True, 0))
        self.assertEqual(await self.events(silent, "reactivated_from_count_email"), [])
        [search] = await self.rows("SELECT enabled FROM search_profiles WHERE id = %s", profile)
        self.assertTrue(search["enabled"])                         # 2.4 brings the search back
        self.assertEqual(await self.rows("SELECT * FROM count_after_expiry_searches()"), [])
        # Extending later is not another reactivation.
        await self.pay(user, "tx-002")
        self.assertEqual(len(await self.events(user, "reactivated_from_count_email")), 1)

    async def test_a_count_email_waiting_is_skipped_after_a_purchase(self):
        user, profile = await self.ended_trial(7.1)
        await self.counted(user, profile, 2)
        await repo.claim("count_after_expiry", 48, 10)
        await self.pay(user)
        self.assertEqual(await self.send(), 0)
        row = await self.ledger(user, "count_after_expiry")
        self.assertEqual((row["status"], row["error"]), ("skipped", "not_eligible"))


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


class SearchActivatedTests(LifecycleCase):
    """The welcome: 45 minutes after the account's first search."""

    async def first_search(self, user: str, *, minutes_ago: float, model: str = "Focus") -> int:
        profile = await self.search(user, model)
        await self.rows("UPDATE search_profiles SET created_at = now() - make_interval(secs => %s) WHERE id = %s",
                        minutes_ago * 60, profile)
        return profile

    async def test_once_per_account_with_what_its_search_already_found(self):
        user = await self.account(trial_ended_hours_ago=None)
        profile = await self.first_search(user, minutes_ago=50)
        for level in ("high", "good", "good"):
            await self.match(profile, level=level)

        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "search_activated")
        self.assertEqual((row["status"], row["event_key"], row["search_profile_id"], row["target"], row["payload"]),
                         ("sent", "first", profile, f"/app/searches/{profile}",
                          {"model": "Ford Focus", "found": 3, "below": 1}))
        [body] = self.emails()
        self.assertEqual((body["to"], body["subject"]), ([await self.email_of(user)], "Tu búsqueda de Ford Focus ya está activa"))
        self.assertIn(f"Ver mis resultados: https://automotive.app/m/{row['id']}", body["text"])
        self.assertIn(f"/o/{row['id']}?k=m", body["html"])

        await self.first_search(user, minutes_ago=50, model="Ka")     # a second search: no second welcome
        self.assertEqual(await self.send(), 0)

    async def test_not_before_45_minutes_nor_for_a_paused_search_or_an_admin(self):
        early = await self.account(trial_ended_hours_ago=None)
        await self.first_search(early, minutes_ago=10)
        paused = await self.account(trial_ended_hours_ago=None)
        await self.rows("UPDATE search_profiles SET enabled = false WHERE id = %s",
                        await self.first_search(paused, minutes_ago=50))
        await self.first_search(self.admin, minutes_ago=50)

        self.assertEqual(await self.send(), 0)
        for user in (early, paused, self.admin):
            self.assertIsNone(await self.ledger(user, "search_activated"))

    async def test_skipped_if_the_search_was_paused_before_its_turn(self):
        user = await self.account(trial_ended_hours_ago=None)
        profile = await self.first_search(user, minutes_ago=50)
        [row] = await self.rows("SELECT id FROM claim_lifecycle_emails('search_activated', interval '48 hours', 5)")
        await self.rows("UPDATE search_profiles SET enabled = false WHERE id = %s", profile)

        self.assertEqual(await self.send(), 0)
        self.assertEqual((await self.ledger(user, "search_activated"))["id"], row["id"])
        self.assertEqual((await self.ledger(user, "search_activated"))["status"], "skipped")

    async def test_a_first_search_older_than_the_window_never_gets_one(self):
        user = await self.account(trial_ended_hours_ago=None)
        await self.first_search(user, minutes_ago=60 * 50)
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user, "search_activated"))


class RemarketingTests(LifecycleCase):
    """Accounts without a search: 1A wrote one and never saved it, 1B never wrote one; the follow-up asks why."""

    KINDS_ON = {"search_abandoned": True, "search_not_started": True, "search_feedback": True}

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            self.saved += await (await cx.execute(
                "SELECT key, value FROM app_config WHERE key = 'remarketing'")).fetchall()
        await self.config(kinds={**DEFAULTS["kinds"], **self.KINDS_ON})
        await self.config("remarketing", backfill_since=None, reply_to="juan@automotive.test")

    async def signed_up(self, *, hours_ago: float) -> str:
        user = await self.account(trial_ended_hours_ago=None)
        await self.rows("UPDATE profiles SET created_at = now() - make_interval(secs => %s) WHERE id = %s",
                        hours_ago * 3600, user)
        return user

    async def asked(self, user: str, text: str, *, hours_ago: float, model: str | None = "Hilux",
                    status: str = "done") -> int:
        output = {"drafts": [{"values": {"make": "Toyota", "model": model} if model else {}, "resolved": bool(model)}]}
        [row] = await self.rows(
            "INSERT INTO llm_jobs (user_id, kind, input, output, status, created_at) "
            "VALUES (%s, 'parse_search', %s, %s, %s::llm_job_status, now() - make_interval(secs => %s)) RETURNING id",
            user, Jsonb({"text": text}), Jsonb(output), status, hours_ago * 3600)
        return row["id"]

    async def test_an_abandoned_request_gets_its_own_search_back_ready_to_activate(self):
        user = await self.signed_up(hours_ago=30)
        await self.asked(user, "Toyota hilux 2013 a 2016", hours_ago=29)
        job = await self.asked(user, "Toyota hilux 2.5 de 2013 a 2016 & más", hours_ago=25)

        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "search_abandoned")
        self.assertEqual((row["status"], row["event_key"], row["target"]),
                         ("sent", "first", "/app/searches/new?prompt=Toyota%20hilux%202.5%20de%202013%20a%202016"
                                           "%20%26%20m%C3%A1s"))
        self.assertEqual((row["payload"]["text"], row["payload"]["model"], row["payload"]["job_id"]),
                         ("Toyota hilux 2.5 de 2013 a 2016 & más", "Toyota Hilux", job))
        [body] = self.emails()
        self.assertEqual((body["reply_to"], body["subject"]),
                         ("juan@automotive.test", "Tu búsqueda de Toyota Hilux está lista"))
        self.assertIn("attachments", body)
        self.assertIn(f"Activar mi búsqueda: https://automotive.app/m/{row['id']}", body["text"])
        self.assertIn("List-Unsubscribe", body["headers"])
        # Not a second time, nor the 1B email.
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(user, "search_not_started"))

    async def test_who_never_wrote_anything_is_asked_what_car(self):
        user = await self.signed_up(hours_ago=25)
        self.assertEqual(await self.send(), 1)
        row = await self.ledger(user, "search_not_started")
        self.assertEqual((row["target"], row["payload"]), ("/app/searches/new", {}))
        [body] = self.emails()
        self.assertEqual(body["subject"], "¿Qué auto estás buscando?")
        self.assertNotIn("r=wrong_search", body["text"])

    async def test_not_before_24_hours_nor_with_a_search_nor_to_an_admin_or_an_opt_out(self):
        early = await self.signed_up(hours_ago=5)
        with_search = await self.signed_up(hours_ago=30)
        await self.rows("UPDATE search_profiles SET enabled = false WHERE id = %s", await self.search(with_search))
        opted_out = await self.signed_up(hours_ago=30)
        await self.rows("UPDATE profiles SET default_channels = '{web}' WHERE id = %s", opted_out)
        await self.rows("UPDATE profiles SET created_at = now() - interval '30 hours' WHERE id = %s", self.admin)
        fresh_request = await self.signed_up(hours_ago=30)
        await self.asked(fresh_request, "Gol trend", hours_ago=2)      # the request resets the clock

        self.assertEqual(await self.send(), 0)
        self.assertEqual(await self.rows("SELECT * FROM lifecycle_emails"), [])

    async def test_skipped_if_the_search_was_created_before_its_turn(self):
        user = await self.signed_up(hours_ago=30)
        await self.asked(user, "Gol trend", hours_ago=25)
        await self.rows("SELECT id FROM claim_lifecycle_emails('search_abandoned', interval '48 hours', 5)")
        await self.search(user, "Gol", "Volkswagen")

        self.assertEqual(await self.send(), 0)
        self.assertEqual((await self.ledger(user, "search_abandoned"))["status"], "skipped")

    async def test_the_backfill_reaches_accounts_older_than_the_window_once(self):
        old = await self.signed_up(hours_ago=24 * 20)
        await self.asked(old, "Chery Arrizo 8", hours_ago=24 * 19)
        older = await self.signed_up(hours_ago=24 * 40)

        self.assertEqual(await self.send(), 0)                          # no backfill: too old for the window
        await self.config("remarketing", backfill_since=(datetime.now(AR) - timedelta(days=30)).isoformat())
        self.assertEqual(await self.send(), 1)
        self.assertEqual((await self.ledger(old, "search_abandoned"))["status"], "sent")
        self.assertIsNone(await self.ledger(older, "search_not_started"))

    async def test_one_remarketing_email_per_account_no_follow_up(self):
        # Juan, 26/10/2026: one email, 1A or 1B; the follow-up never goes out.
        asked, answered = [await self.signed_up(hours_ago=30) for _ in range(2)]
        for user in (asked, answered):
            await self.asked(user, "Renault Sandero 2021", hours_ago=25, model="Sandero")
        self.assertEqual(await self.send(), 2)
        firsts = {u: (await self.ledger(u, "search_abandoned"))["id"] for u in (asked, answered)}
        await self.rows("UPDATE lifecycle_emails SET sent_at = now() - interval '4 days 1 hour'")
        [fb] = await self.rows("SELECT record_email_feedback(%s, 'browsing', '  solo miraba ') AS id", firsts[answered])
        self.assertIsNotNone(fb["id"])

        self.requests.clear()
        self.assertEqual(await self.send(), 0)
        self.assertIsNone(await self.ledger(asked, "search_feedback"))
        self.assertEqual(self.emails(), [])
        self.assertEqual(await self.events(answered, "email_feedback"),
                         [{"email_id": firsts[answered], "kind": "search_abandoned", "reason": "browsing",
                           "comment": True}])

    async def test_feedback_only_for_a_sent_remarketing_email_and_a_second_answer_replaces_it(self):
        user = await self.signed_up(hours_ago=25)
        self.assertEqual(await self.send(), 1)
        email = (await self.ledger(user, "search_not_started"))["id"]
        await self.rows("SELECT record_email_feedback(%s, 'unclear', 'no entendí')", email)
        await self.rows("SELECT record_email_feedback(%s, 'bought', null)", email)
        [fb] = await self.rows("SELECT reason, comment FROM email_feedback WHERE lifecycle_email_id = %s", email)
        self.assertEqual((fb["reason"], fb["comment"]), ("bought", "no entendí"))

        other = await self.account(trial_ended_hours_ago=1)
        await self.config(kinds={**DEFAULTS["kinds"], **self.KINDS_ON, "search_not_started": False})
        self.assertEqual(await self.send(), 1)
        trial = (await self.ledger(other, "trial_ended"))["id"]
        [row] = await self.rows("SELECT record_email_feedback(%s, 'bought', null) AS id", trial)
        self.assertIsNone(row["id"])
        with self.assertRaisesRegex(Exception, "email_feedback_reason_check"):
            await self.rows("SELECT record_email_feedback(%s, 'spam', null)", email)
        with self.assertRaisesRegex(Exception, "permission denied"):
            await self.rows("SELECT record_email_feedback(%s, 'other', null)", email, actor=user)


class BonusTrialTests(LifecycleCase):
    """The extra 7-day trial: offered on day 7 after the 72 h trial, started by the person (/app/bonus)."""

    KINDS_ON = {"bonus_trial_offer": True, "bonus_trial_ending": True, "bonus_trial_ended": True}

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            self.saved += await (await cx.execute(
                "SELECT key, value FROM app_config WHERE key = 'bonus_trial'")).fetchall()
        await self.config(kinds={**DEFAULTS["kinds"], **self.KINDS_ON})
        await self.config("bonus_trial", backfill_since=None)

    async def ended_trial(self, days_ago: float) -> tuple[str, int]:
        """An account whose trial ended `days_ago`, with a search that found something and that the end paused."""
        user = await self.account(trial_ended_hours_ago=days_ago * 24)
        profile = await self.search(user, "Ka")
        await self.match(profile, level="high", hours_ago=days_ago * 24 + 2)
        await self.match(profile, hours_ago=days_ago * 24 + 3)
        await self.rows("UPDATE listings SET year = 2018, price = 9800, currency = 'USD', mileage_km = 72000")
        await self.rows("SELECT expire_commercial_access(%s)", user)
        return user, profile

    async def counted(self, user: str, profile: int, n: int) -> None:
        [row] = await self.rows("SELECT count_after_expiry_end(%s) AS t", user)
        for _ in range(n):
            ref = uuid4().hex[:10]
            [listing] = await self.rows(
                "INSERT INTO listings (source, external_id, url, title, make, model) "
                "VALUES ('mercadolibre', %s, %s, 'Ford Ka', 'Ford', 'Ka') RETURNING id", ref, f"https://example.test/{ref}")
            await self.rows("INSERT INTO expired_search_matches (search_profile_id, listing_id, access_ended_at, level) "
                            "VALUES (%s, %s, %s, 'good')", profile, listing["id"], row["t"])

    async def bonus(self, user: str, fn: str = "my_bonus_trial") -> dict:
        [row] = await self.rows(f"SELECT {fn}() AS v", actor=user)
        return row["v"]

    async def test_day_seven_offers_it_instead_of_the_count(self):
        user, profile = await self.ended_trial(7 + 2 / 24)
        await self.counted(user, profile, 4)

        self.assertEqual(await self.send(), 1)
        offer = await self.ledger(user, "bonus_trial_offer")
        self.assertEqual((offer["target"], offer["search_profile_id"], offer["event_key"]), ("/app/bonus", profile, "bonus"))
        self.assertEqual({k: offer["payload"][k] for k in ("model", "found", "new", "below")},
                         {"model": "Ford Ka", "found": 2, "new": 4, "below": 0})
        self.assertEqual(offer["payload"]["cars"][0],
                         {"title": "Ford Fiesta", "year": 2018, "price": 9800, "currency": "USD", "km": 72000,
                          "below": True})                                # the opportunity first
        [body] = self.emails()
        self.assertEqual(body["subject"], "Te damos 7 días más para tu búsqueda de Ford Ka")
        self.assertIn(f"Activar mis 7 días: https://automotive.app/m/{offer['id']}", body["text"])
        count = await self.ledger(user, "count_after_expiry")
        self.assertTrue(count is None or count["status"] == "skipped")

    async def test_not_before_day_seven_nor_to_a_payer_nor_without_results(self):
        early, _ = await self.ended_trial(5)
        payer, _ = await self.ended_trial(8)
        await self.pay(payer)
        empty = await self.account(trial_ended_hours_ago=8 * 24)
        await self.search(empty)
        self.assertEqual(await self.send(), 0)
        for user in (early, payer, empty):
            self.assertIsNone(await self.ledger(user, "bonus_trial_offer"))

    async def test_the_backfill_reaches_trials_that_ended_long_ago(self):
        user, _ = await self.ended_trial(30)
        self.assertEqual(await self.send(), 0)
        await self.config("bonus_trial", backfill_since=(datetime.now(AR) - timedelta(days=60)).isoformat())
        self.assertEqual(await self.send(), 1)
        self.assertEqual((await self.ledger(user, "bonus_trial_offer"))["status"], "sent")

    async def test_the_click_starts_seven_days_once_and_brings_the_search_back(self):
        user, profile = await self.ended_trial(8)
        self.assertEqual((await self.bonus(user))["state"], "unavailable")    # no offer sent yet
        self.assertEqual(await self.send(), 1)
        self.assertEqual(await self.bonus(user), {"state": "available", "days": 7})

        started = await self.bonus(user, "start_my_bonus_trial")
        self.assertEqual((started["state"], started["started"], started["searches_reactivated"]), ("active", True, 1))
        [search] = await self.rows("SELECT enabled FROM search_profiles WHERE id = %s", profile)
        self.assertTrue(search["enabled"])
        [access] = await self.rows("SELECT plan_limits_for(%s) AS v", user)
        self.assertEqual((access["v"]["state"], access["v"]["bonus_trial"]), ("trial", True))
        [event] = await self.events(user, "bonus_trial_started")
        self.assertEqual((event["email_id"], event["searches_reactivated"]),
                         ((await self.ledger(user, "bonus_trial_offer"))["id"], 1))
        self.assertEqual(await self.events(user, "reactivated_from_count_email"), [])

        again = await self.bonus(user, "start_my_bonus_trial")
        self.assertEqual((again["state"], again["started"]), ("active", False))
        self.assertEqual(len(await self.events(user, "bonus_trial_started")), 1)
        with self.assertRaisesRegex(Exception, "authentication_required"):
            await self.rows("SELECT start_my_bonus_trial()")              # no signed-in account

    async def test_day_five_and_the_end_then_two_five_counts_from_the_new_end(self):
        user, profile = await self.ended_trial(8)
        self.assertEqual(await self.send(), 1)
        await self.bonus(user, "start_my_bonus_trial")
        await self.match(profile, level="high", hours_ago=1)

        await self.rows("UPDATE profiles SET bonus_trial_started_at = now() - interval '5 days 1 hour' WHERE id = %s",
                        user)
        self.requests.clear()
        self.assertEqual(await self.send(), 1)
        ending = await self.ledger(user, "bonus_trial_ending")
        self.assertEqual((ending["target"], ending["payload"]["found"], ending["payload"]["below"]),
                         (f"/app/searches/{profile}", 1, 1))
        self.assertEqual(self.emails()[0]["subject"], "Te quedan 2 días gratis para tu búsqueda de Ford Ka")

        await self.rows("UPDATE profiles SET bonus_trial_started_at = now() - interval '7 days 1 hour' WHERE id = %s",
                        user)
        await self.rows("SELECT expire_commercial_access(%s)", user)
        self.requests.clear()
        self.assertEqual(await self.send(), 1)
        ended = await self.ledger(user, "bonus_trial_ended")
        self.assertEqual((ended["target"], ended["payload"]["found"]), ("/app/pro?plan=pass_30", 1))
        self.assertEqual(self.emails()[0]["subject"], "Terminaron tus 7 días: encontramos 1 auto para tu búsqueda")
        [event] = await self.events(user, "bonus_trial_ended")
        self.assertEqual((event["results"], event["opportunities"], event["converted"]), (1, 1, False))
        [row] = await self.rows("SELECT count_after_expiry_end(%s) > now() - interval '2 hours' AS fresh, "
                                "       (SELECT count(*) FROM count_after_expiry_searches() c WHERE c.user_id = %s) AS n",
                                user, user)
        self.assertEqual((row["fresh"], row["n"]), (True, 1))
        self.assertEqual((await self.bonus(user))["state"], "unavailable")    # once per account
