"""PAR-04 against Postgres: the guide jobs (admin_request_model_guide, the
worker's handler with recorded synthetic answers, the cache, the caps, the
switch, expiry) and the published guides' questions in the matches. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest -m db
No real provider is called: replay_provider answers from
fixtures/llm/model_guide_recorded.json.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import guides as guides_repo
from db.repos import llm_jobs as jobs_repo
from llm.replay import replay_provider
from pgcase import PostgresTestCase, requires_db
from pipeline import llm_jobs
from test_pro01_postgres import Pro01Case

pytestmark = [pytest.mark.db, requires_db]


class CountingProvider:
    """replay_provider, counting the guide calls that reach it."""

    def __init__(self) -> None:
        self.inner = replay_provider()
        self.name = self.inner.name
        self.guide_calls = 0

    async def parse_search(self, *a, **kw):
        return await self.inner.parse_search(*a, **kw)

    async def model_guide(self, context, *, timeout=None):
        self.guide_calls += 1
        return await self.inner.model_guide(context, timeout=timeout)


class GuidesCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            limits = (await (await cx.execute("SELECT value FROM app_config WHERE key = 'llm_limits'")).fetchone())["value"]
            await cx.execute("DELETE FROM llm_jobs")
            await cx.execute("DELETE FROM model_guides")
            row = await (await cx.execute(
                "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
                "        'authenticated', 'guides-admin@automotive.test', now(), now()) RETURNING id::text AS id")).fetchone()
            self.admin = row["id"]
            await cx.execute("UPDATE profiles SET role = 'admin' WHERE id = %s", (self.admin,))
            row = await (await cx.execute(
                "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
                "        'authenticated', 'guides-user@automotive.test', now(), now()) RETURNING id::text AS id")).fetchone()
            self.user = row["id"]
        self.limits = limits
        await self.guide_cfg(enabled=True, per_day=30, per_month=60)

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = %s WHERE key = 'llm_limits'", (Jsonb(self.limits),))
        await super().asyncTearDown()

    async def guide_cfg(self, **values) -> None:
        async with db.connection() as cx:
            await cx.execute(
                "UPDATE app_config SET value = jsonb_set(value, '{model_guide}', "
                "       coalesce(value -> 'model_guide', '{}') || %s) WHERE key = 'llm_limits'", (Jsonb(values),))

    async def guide(self, make="Ford", model="Fiesta", generation=None, **cols) -> int:
        slug = model.lower().replace(" ", "-")
        async with db.connection() as cx:
            row = await (await cx.execute(
                "INSERT INTO model_guides (make, model, generation_label, slug_make, slug_model) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id", (make, model, generation, make.lower(), slug))).fetchone()
            if cols:
                await cx.execute(f"UPDATE model_guides SET {', '.join(f'{c} = %s' for c in cols)} WHERE id = %s",
                                 [*(Jsonb(v) if isinstance(v, (dict, list)) else v for v in cols.values()), row["id"]])
        return row["id"]

    async def request(self, guide_id: int, *, force: bool = False, actor: str | None = None) -> int:
        async with db.connection() as cx:
            row = await (await cx.execute("SELECT public.admin_request_model_guide(%s, %s, %s) AS id",
                                          (guide_id, force, actor or self.admin))).fetchone()
        return row["id"]

    async def one(self, sql: str, *params) -> dict:
        async with db.connection() as cx:
            return await (await cx.execute(sql, params)).fetchone()


class RequestTests(GuidesCase):
    async def assertRefused(self, code: str, guide_id: int, **kw) -> None:
        with self.assertRaises(psycopg.Error) as ctx:
            await self.request(guide_id, **kw)
        self.assertIn(code, str(ctx.exception))

    async def test_off_by_default_and_with_the_switch(self):
        self.assertIs(self.limits["model_guide"]["enabled"], False)
        self.assertEqual({k: self.limits["model_guide"][k] for k in ("per_day", "per_month", "max_questions_in_listing")},
                         {"per_day": 30, "per_month": 60, "max_questions_in_listing": 3})
        await self.guide_cfg(enabled=False)
        await self.assertRefused("guide_generation_off", await self.guide())

    async def test_only_an_admin_and_never_a_published_guide(self):
        gid = await self.guide()
        await self.assertRefused("admin_required", gid, actor=self.user)
        published = await self.guide(model="Ka", status="published", reviewed_at=datetime.now(timezone.utc),
                                     published_at=datetime.now(timezone.utc))
        await self.assertRefused("guide_published", published)

    async def test_daily_and_monthly_caps(self):
        await self.guide_cfg(per_day=1)
        first = await self.request(await self.guide())
        await self.assertRefused("guide_daily_cap", await self.guide(model="Ka"))
        await self.guide_cfg(per_day=30, per_month=1)
        await self.assertRefused("guide_monthly_cap", await self.guide(model="Focus"))
        # A job that never reached the provider (expired in the queue) frees its place.
        async with db.connection() as cx:
            await cx.execute("UPDATE llm_jobs SET status = 'failed', provider = NULL WHERE id = %s", (first,))
        await self.request(await self.guide(model="EcoSport"))

    async def test_a_user_cannot_enqueue_a_guide(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            async with db.connection() as cx:
                await cx.execute("SET LOCAL ROLE authenticated")
                await cx.execute("SELECT set_config('request.jwt.claims', %s, true)",
                                 (json.dumps({"sub": self.user, "role": "authenticated"}),))
                await cx.execute("INSERT INTO llm_jobs (user_id, kind, input) VALUES (%s, 'model_guide', %s)",
                                 (self.user, Jsonb({"guide_id": 1, "make": "Ford", "model": "Fiesta"})))

    async def test_guides_do_not_use_up_the_hourly_limit(self):
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{per_user_hour}', '1') "
                             " WHERE key = 'llm_limits'")
        await self.request(await self.guide())
        await self.request(await self.guide(model="Ka"))
        async with db.connection() as cx:
            await cx.execute("INSERT INTO llm_jobs (user_id, kind, input) VALUES (%s, 'parse_search', %s)",
                             (self.admin, Jsonb({"text": "Busco un Fiesta"})))


class WorkerTests(GuidesCase):
    async def job(self, job_id: int) -> dict:
        return await self.one("SELECT * FROM llm_jobs WHERE id = %s", job_id)

    async def row(self, guide_id: int) -> dict:
        return await self.one("SELECT * FROM model_guides WHERE id = %s", guide_id)

    async def test_a_draft_end_to_end(self):
        gid = await self.guide()
        job_id = await self.request(gid)
        provider = CountingProvider()
        self.assertEqual(await llm_jobs.drain(provider), 1)
        job = await self.job(job_id)
        self.assertEqual((job["status"], job["provider"], job["error"]), ("done", "replay", None))
        self.assertEqual(job["user_id"].__str__(), self.admin)
        self.assertEqual(job["output"]["cache_key"], "ford|fiesta||model_guide-v1")
        self.assertIs(job["output"]["applied"], True)
        g = await self.row(gid)
        self.assertEqual((g["status"], g["origin"], g["llm_job_id"], g["llm_version"]),
                         ("draft", "llm", job_id, "replay|model_guide-v1"))
        self.assertIsNotNone(g["generated_at"])
        self.assertTrue(all(g["body"][k] for k in ("known_issues", "visit_checklist", "versions_equipment",
                                                   "maintenance_costs", "generations")))
        self.assertTrue(3 <= len(g["questions"]) <= 8)
        self.assertTrue(g["sources"] and all(s["verified"] is False for s in g["sources"]))
        self.assertEqual(provider.guide_calls, 1)

    async def test_the_cache_skips_the_provider_and_the_cap(self):
        await self.guide_cfg(per_day=2)
        gid = await self.guide()
        await self.request(gid)
        provider = CountingProvider()
        await llm_jobs.drain(provider)
        # Asked again (no hand edits since): the cache answers.
        second = await self.request(gid)
        await llm_jobs.drain(provider)
        job = await self.job(second)
        self.assertEqual((job["status"], job["provider"], job["output"]["cached"]), ("done", "cache", True))
        self.assertEqual(provider.guide_calls, 1)
        # Two requests today, but only one called the provider: a third fits per_day = 2.
        third = await self.request(gid, force=True)
        await llm_jobs.drain(provider)
        self.assertEqual(provider.guide_calls, 2, "force («Regenerar») skips the cache")
        self.assertEqual((await self.job(third))["provider"], "replay")

    async def test_hand_edits_are_replaced_only_with_force(self):
        gid = await self.guide()
        await self.request(gid)
        await llm_jobs.drain(CountingProvider())
        async with db.connection() as cx:
            await cx.execute("UPDATE model_guides SET questions = '[]' WHERE id = %s", (gid,))
        with self.assertRaises(psycopg.Error) as ctx:
            await self.request(gid)
        self.assertIn("guide_has_manual_edits", str(ctx.exception))

    async def test_an_invalid_answer_fails_and_leaves_the_guide(self):
        gid = await self.guide(generation="dolares")
        job_id = await self.request(gid)
        await llm_jobs.drain(CountingProvider())
        job = await self.job(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIn("cifra de dinero", job["error"])
        g = await self.row(gid)
        self.assertEqual((g["body"], g["origin"], g["generated_at"]), ({}, "manual", None))

    async def test_switched_off_after_queueing_it_fails_without_calling(self):
        job_id = await self.request(await self.guide())
        await self.guide_cfg(enabled=False)
        provider = CountingProvider()
        await llm_jobs.drain(provider)
        job = await self.job(job_id)
        self.assertEqual((job["status"], job["provider"]), ("failed", None))
        self.assertIn("apagada", job["error"])
        self.assertEqual(provider.guide_calls, 0)

    async def test_a_guide_published_meanwhile_is_not_touched(self):
        gid = await self.guide()
        job_id = await self.request(gid)
        async with db.connection() as cx:
            await cx.execute("UPDATE model_guides SET status = 'published', reviewed_at = now(), published_at = now() "
                             " WHERE id = %s", (gid,))
        provider = CountingProvider()
        await llm_jobs.drain(provider)
        self.assertEqual((await self.job(job_id))["status"], "failed")
        self.assertEqual(provider.guide_calls, 0)
        self.assertEqual((await self.row(gid))["body"], {})

    async def test_edited_after_the_request_the_draft_stays_in_the_job(self):
        gid = await self.guide()
        job_id = await self.request(gid)
        async with db.connection() as cx:
            await cx.execute("UPDATE model_guides SET year_from = 2012 WHERE id = %s", (gid,))
        await llm_jobs.drain(CountingProvider())
        job = await self.job(job_id)
        self.assertEqual((job["status"], job["output"]["applied"]), ("done", False))
        self.assertTrue(job["output"]["guide"]["questions"])
        self.assertEqual((await self.row(gid))["origin"], "manual")

    async def test_guides_expire_on_their_own_clock(self):
        guide_job = await self.request(await self.guide())
        async with db.connection() as cx:
            assisted = (await (await cx.execute(
                "INSERT INTO llm_jobs (user_id, kind, input) VALUES (%s, 'parse_search', %s) RETURNING id",
                (self.admin, Jsonb({"text": "Busco un Fiesta"})))).fetchone())["id"]
            await cx.execute("UPDATE llm_jobs SET created_at = now() - interval '2 minutes'")
        await llm_jobs.expire_stale()
        self.assertEqual((await self.job(assisted))["status"], "failed")
        self.assertEqual((await self.job(guide_job))["status"], "queued", "a guide waits up to an hour")
        async with db.connection() as cx:
            await cx.execute("UPDATE llm_jobs SET created_at = now() - interval '61 minutes' WHERE id = %s", (guide_job,))
        await llm_jobs.expire_stale()
        self.assertEqual((await self.job(guide_job))["error"], "vencido en la cola")

    async def test_the_assisted_consumer_does_not_take_guides(self):
        await self.request(await self.guide())
        self.assertFalse(await llm_jobs.process_next(CountingProvider()))
        self.assertTrue(await llm_jobs.process_next(CountingProvider(), llm_jobs.GUIDE_KINDS))

    async def test_finish_keeps_or_replaces_the_provider(self):
        job_id = await self.request(await self.guide())
        async with db.connection() as cx:
            await jobs_repo.claim(cx, ["model_guide"], "replay")
            await jobs_repo.finish(cx, job_id, output={"x": 1}, latency_ms=1)
        self.assertEqual((await self.job(job_id))["provider"], "replay")


class PublishedIndexTests(GuidesCase):
    async def test_only_published_guides_with_questions(self):
        now = datetime.now(timezone.utc)
        qs = [{"text": "¿La caja hace tirones?", "why": ""}]
        await self.guide(questions=qs)
        pub = await self.guide(model="Ka", questions=qs, status="published", reviewed_at=now, published_at=now)
        async with db.connection() as cx:
            index = await guides_repo.published_index(cx)
        self.assertEqual(list(index), [("ford", "ka")])
        self.assertEqual(index[("ford", "ka")][0].guide_id, pub)

    async def test_an_old_base_has_no_guides(self):
        async with db.connection() as cx:
            async with cx.transaction(force_rollback=True):
                await cx.execute("ALTER TABLE model_guides RENAME TO model_guides_hidden")
                self.assertEqual(await guides_repo.published_index(cx), {})


class GuideQuestionsInMatchesTests(Pro01Case):
    """The rematch writes the published guide's questions, with their origin."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            await cx.execute("DELETE FROM model_guides")

    async def test_the_match_carries_the_guide_questions_and_their_origin(self):
        q = "¿La caja hace tirones o patina al arrancar en frío?"
        async with db.connection() as cx:
            gid = (await (await cx.execute(
                "INSERT INTO model_guides (make, model, slug_make, slug_model, year_from, year_to, questions, "
                "                          status, reviewed_at, published_at) "
                "VALUES ('Ford', 'Fiesta', 'ford', 'fiesta', 2011, 2019, %s, 'published', now(), now()) RETURNING id",
                (Jsonb([{"text": q, "why": ""}]),))).fetchone())["id"]
        lid = await self.seller_listing("private", description="Impecable, papeles al día", transmission="manual")
        await self.rematch()
        m = await self.match_of(lid)
        self.assertIn(q, m["seller_questions"])
        self.assertIn({"key": f"guide:{gid}:0", "origin": "guide", "guide_id": gid, "text": q}, m["question_origins"])
        self.assertEqual(m["question_origins"][0], {"key": "greeting", "origin": "template"})

    async def test_a_draft_guide_is_ignored(self):
        q = "¿La caja hace tirones o patina al arrancar en frío?"
        async with db.connection() as cx:
            await cx.execute("INSERT INTO model_guides (make, model, slug_make, slug_model, questions) "
                             "VALUES ('Ford', 'Fiesta', 'ford', 'fiesta', %s)", (Jsonb([{"text": q, "why": ""}]),))
        lid = await self.seller_listing("private", description="Impecable", transmission="manual")
        await self.rematch()
        m = await self.match_of(lid)
        self.assertNotIn(q, m["seller_questions"])
        self.assertTrue(all(o["origin"] == "template" for o in m["question_origins"]))


class WithdrawOnUnpublishTests(Pro01Case):
    """Unpublishing a guide takes its questions out of every match at once,
    whatever the listing's state or the search's access; saving a published
    guide takes out the questions it no longer has."""

    Q1 = "¿La caja hace tirones o patina al arrancar en frío?"
    Q2 = "¿Le cambiaron los bujes del tren delantero alguna vez?"

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            await cx.execute("DELETE FROM model_guides")
            await cx.execute("UPDATE profiles SET role = 'admin' WHERE id = %s", (self.user,))
            body = {k: [{"text": "Renglón de la guía."}] for k in
                    ("known_issues", "visit_checklist", "versions_equipment", "maintenance_costs", "generations")}
            self.gid = (await (await cx.execute(
                "INSERT INTO model_guides (make, model, slug_make, slug_model, year_from, year_to, body, questions, "
                "                          sources, status, reviewed_at, published_at) "
                "VALUES ('Ford', 'Fiesta', 'ford', 'fiesta', 2011, 2019, %s, %s, '[]', 'published', now(), now()) "
                "RETURNING id",
                (Jsonb(body), Jsonb([{"text": self.Q1, "why": ""}, {"text": self.Q2, "why": ""},
                                     {"text": "¿Tiene la rueda de auxilio original?", "why": ""}])))).fetchone())["id"]

    async def set_status(self, status: str) -> dict:
        async with db.connection() as cx:
            return (await (await cx.execute("SELECT public.admin_set_model_guide_status(%s, %s, %s) AS r",
                                            (self.gid, status, self.user))).fetchone())["r"]

    async def test_unpublishing_withdraws_at_once_even_from_old_matches(self):
        lid = await self.seller_listing("private", description="Impecable, papeles al día", transmission="manual")
        await self.rematch()
        before = await self.match_of(lid)
        self.assertIn(self.Q1, before["seller_questions"])
        # This listing has three questions of its own (the email's three); one
        # with fewer carries the guide's in contact_questions too.
        async with db.connection() as cx:
            await cx.execute("UPDATE matches SET contact_questions = contact_questions[1:2] || %s::text "
                             " WHERE listing_id = %s", (self.Q1, lid))
        # A listing nobody rescans and a search without access: nothing would rescore it.
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (lid,))
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{enforced}', 'true') "
                             " WHERE key = 'plan_limits'")
            await cx.execute("UPDATE profiles SET plan = 'free', plan_expires_at = now() - interval '1 day' "
                             " WHERE id = %s", (self.user,))
        try:
            result = await self.set_status("draft")
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{enforced}', 'false') "
                                 " WHERE key = 'plan_limits'")
        self.assertEqual(result["withdrawn_matches"], 1)
        after = await self.match_of(lid)
        self.assertNotIn(self.Q1, after["seller_questions"])
        self.assertNotIn(self.Q2, after["seller_questions"])
        self.assertTrue(after["seller_questions"].startswith(before["seller_questions"].split(" ¿")[0]))
        self.assertNotIn(self.Q1, after["contact_questions"] or [])
        self.assertTrue(all(o["origin"] == "template" for o in after["question_origins"]))
        self.assertEqual(len(after["question_origins"]), len(before["question_origins"]) - 3)
        # Everything else stays as scored.
        self.assertEqual((after["score"], after["level"]), (before["score"], before["level"]))

    async def test_saving_a_published_guide_withdraws_the_removed_questions(self):
        lid = await self.seller_listing("private", description="Impecable, papeles al día", transmission="manual")
        await self.rematch()
        async with db.connection() as cx:
            g = await (await cx.execute("SELECT * FROM model_guides WHERE id = %s", (self.gid,))).fetchone()
            values = {"make": "Ford", "model": "Fiesta", "slug_make": "ford", "slug_model": "fiesta",
                      "year_from": 2011, "year_to": 2019, "body": g["body"], "sources": [],
                      "questions": [q for q in g["questions"] if q["text"] != self.Q1]
                      + [{"text": "¿El aire acondicionado enfría bien?", "why": ""}]}
            await cx.execute("SELECT public.admin_save_model_guide(%s, %s, %s, %s)",
                             (self.gid, Jsonb(values), g["updated_at"], self.user))
        m = await self.match_of(lid)
        self.assertNotIn(self.Q1, m["seller_questions"])
        self.assertIn(self.Q2, m["seller_questions"])
        self.assertEqual([o["text"] for o in m["question_origins"] if o["origin"] == "guide"],
                         [self.Q2, "¿Tiene la rueda de auxilio original?"])

    async def test_publishing_and_unpublishing_is_not_a_hand_edit(self):
        async with db.connection() as cx:
            await cx.execute("UPDATE model_guides SET generated_at = now(), origin = 'llm' WHERE id = %s", (self.gid,))
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{model_guide,enabled}', 'true') "
                             " WHERE key = 'llm_limits'")
        try:
            await self.set_status("draft")
            await self.set_status("published")
            await self.set_status("draft")
            async with db.connection() as cx:
                job = (await (await cx.execute("SELECT public.admin_request_model_guide(%s, false, %s) AS id",
                                               (self.gid, self.user))).fetchone())["id"]
                self.assertIsNotNone(job)
                # A real edit still needs «Regenerar».
                await cx.execute("DELETE FROM llm_jobs WHERE id = %s", (job,))
                await cx.execute("UPDATE model_guides SET year_from = 2012 WHERE id = %s", (self.gid,))
                with self.assertRaises(psycopg.Error) as ctx:
                    await cx.execute("SELECT public.admin_request_model_guide(%s, false, %s)", (self.gid, self.user))
                self.assertIn("guide_has_manual_edits", str(ctx.exception))
        finally:
            async with db.connection() as cx:
                await cx.execute("DELETE FROM llm_jobs WHERE kind = 'model_guide'")
                await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{model_guide,enabled}', 'false') "
                                 " WHERE key = 'llm_limits'")
