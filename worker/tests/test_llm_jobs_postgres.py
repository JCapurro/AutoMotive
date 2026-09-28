"""The llm_jobs queue against the local Supabase Postgres (sección 8.4):
what the web may insert (RLS, input check, rate limit), the SKIP LOCKED claim,
the loop with recorded answers, failures and expiry. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

import asyncio
import json

import psycopg
import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import llm_jobs as jobs_repo
from llm.replay import replay_provider
from pgcase import PostgresTestCase, requires_db
from pipeline import llm_jobs

pytestmark = [pytest.mark.db, requires_db]

FIESTA_TEXT = "Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500 y menos de 150.000 km"
TWO_TEXT = "Fiesta Titanium o Polo Highline, 2017 en adelante, hasta 12 mil dólares"


class LlmJobsCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            await cx.execute("DELETE FROM llm_jobs")
            row = await (await cx.execute(
                "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
                "        'authenticated', 'llm@automotive.test', now(), now()) RETURNING id::text AS id")).fetchone()
        self.user = row["id"]

    async def enqueue(self, text: str, **cols) -> int:
        async with db.connection() as cx:
            row = await (await cx.execute(
                "INSERT INTO llm_jobs (user_id, kind, input) VALUES (%s, 'parse_search', %s) RETURNING id",
                (self.user, Jsonb({"text": text})))).fetchone()
            for col, value in cols.items():
                await cx.execute(f"UPDATE llm_jobs SET {col} = {value} WHERE id = %s", (row["id"],))
        return row["id"]

    async def job(self, job_id: int) -> dict:
        async with db.connection() as cx:
            return await (await cx.execute("SELECT * FROM llm_jobs WHERE id = %s", (job_id,))).fetchone()

    async def as_user(self, sql: str, params: tuple = ()) -> None:
        """Run `sql` as the signed-in web user (role authenticated, RLS on)."""
        async with db.connection() as cx:
            await cx.execute("SET LOCAL ROLE authenticated")
            await cx.execute("SELECT set_config('request.jwt.claims', %s, true)",
                             (json.dumps({"sub": self.user, "role": "authenticated"}),))
            await cx.execute(sql, params)


class QueueTests(LlmJobsCase):
    async def test_parse_search_job_end_to_end_with_recorded_answers(self):
        one = await self.enqueue(FIESTA_TEXT)
        two = await self.enqueue(TWO_TEXT)

        self.assertEqual(await llm_jobs.drain(replay_provider()), 2)

        job = await self.job(one)
        self.assertEqual((job["status"], job["provider"], job["error"]), ("done", "replay", None))
        self.assertIsNotNone(job["latency_ms"])
        self.assertIsNotNone(job["started_at"])
        self.assertIsNotNone(job["finished_at"])
        [draft] = job["output"]["drafts"]
        self.assertTrue(draft["resolved"])
        self.assertEqual({k: draft["values"][k] for k in ("make", "model", "trim", "year_min", "year_max",
                                                          "price_max", "currency", "km_max", "transmission")},
                         {"make": "Ford", "model": "Fiesta", "trim": "Titanium", "year_min": 2016,
                          "year_max": 2018, "price_max": 11500, "currency": "USD", "km_max": 150000,
                          "transmission": "manual"})
        models = [d["values"]["model"] for d in (await self.job(two))["output"]["drafts"]]
        self.assertEqual(models, ["Fiesta", "Polo"])

    async def test_provider_failure_marks_the_job_failed(self):
        job_id = await self.enqueue("Un texto que nadie grabó")
        await llm_jobs.drain(replay_provider())
        job = await self.job(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIsNone(job["output"])
        self.assertIn("grabada", job["error"])
        self.assertNotIn("nadie grabó", job["error"])  # the user's text never lands in error

    async def test_unexpected_errors_fail_the_job_too(self):
        class Broken:
            name = "broken"

            async def parse_search(self, text, catalog=()):
                raise RuntimeError("bug")

        job_id = await self.enqueue(FIESTA_TEXT)
        await llm_jobs.drain(Broken())
        job = await self.job(job_id)
        self.assertEqual((job["status"], job["error"]), ("failed", "error interno del worker"))

    async def test_claim_skips_locked_rows(self):
        first = await self.enqueue(FIESTA_TEXT)
        second = await self.enqueue(TWO_TEXT)
        async with db.connection() as a:
            got_a = await jobs_repo.claim(a, ["parse_search"], "a")
            # `a` hasn't committed: its row stays locked, so `b` takes the next one.
            async with db.connection() as b:
                got_b = await jobs_repo.claim(b, ["parse_search"], "b")
                self.assertIsNone(await jobs_repo.claim(b, ["parse_search"], "b"))
        self.assertEqual((got_a["id"], got_b["id"]), (first, second))

    async def test_concurrent_consumers_take_each_job_once(self):
        ids = [await self.enqueue(FIESTA_TEXT) for _ in range(4)]
        seen: list[str] = []

        class Counting:
            name = "counting"

            async def parse_search(self, text, catalog=()):
                seen.append(text)
                await asyncio.sleep(0.05)
                return []

        stop = asyncio.Event()
        loop = asyncio.create_task(llm_jobs.llm_jobs_loop(Counting(), stop, concurrency=2, poll=0.05))
        for _ in range(100):
            await asyncio.sleep(0.05)
            async with db.connection() as cx:
                left = await (await cx.execute(
                    "SELECT count(*) AS n FROM llm_jobs WHERE status <> 'done'")).fetchone()
            if left["n"] == 0:
                break
        stop.set()
        await loop
        self.assertEqual(len(seen), 4)
        for job_id in ids:
            self.assertEqual((await self.job(job_id))["output"], {"drafts": []})

    async def test_stale_jobs_expire(self):
        old_queued = await self.enqueue(FIESTA_TEXT, created_at="now() - interval '10 minutes'")
        fresh = await self.enqueue(FIESTA_TEXT)
        dead = await self.enqueue(FIESTA_TEXT, status="'running'", started_at="now() - interval '10 minutes'")

        self.assertEqual(await llm_jobs.expire_stale(), 2)

        self.assertEqual(((await self.job(old_queued))["status"], (await self.job(old_queued))["error"]),
                         ("failed", "vencido en la cola"))
        self.assertEqual((await self.job(dead))["error"], "interrumpido")
        self.assertEqual((await self.job(fresh))["status"], "queued")

    async def test_finish_only_touches_running_jobs(self):
        job_id = await self.enqueue(FIESTA_TEXT)
        async with db.connection() as cx:
            await jobs_repo.finish(cx, job_id, output={"drafts": []}, latency_ms=1)
        self.assertEqual((await self.job(job_id))["status"], "queued")

    async def test_latency_stats(self):
        await self.enqueue(FIESTA_TEXT)
        await self.enqueue("sin grabación")
        await llm_jobs.drain(replay_provider())
        async with db.connection() as cx:
            row = await (await cx.execute(
                "SELECT jobs, done, failed, latency_p95_ms FROM llm_job_stats WHERE provider = 'replay'")).fetchone()
        self.assertEqual((row["jobs"], row["done"], row["failed"]), (2, 1, 1))
        self.assertIsNotNone(row["latency_p95_ms"])


class WebAccessTests(LlmJobsCase):
    """What the web can do with the user's session (sección 4.4)."""

    async def test_user_enqueues_own_parse_search(self):
        await self.as_user("INSERT INTO llm_jobs (kind, input) VALUES ('parse_search', %s)",
                           (Jsonb({"text": FIESTA_TEXT}),))
        async with db.connection() as cx:
            row = await (await cx.execute("SELECT user_id::text AS u, status FROM llm_jobs")).fetchone()
        self.assertEqual((row["u"], row["status"]), (self.user, "queued"))

    async def test_user_cannot_write_results(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            await self.as_user("INSERT INTO llm_jobs (kind, input, status, output) "
                               "VALUES ('parse_search', %s, 'done', '{}')", (Jsonb({"text": FIESTA_TEXT}),))

    async def test_input_must_be_a_reasonable_text(self):
        for bad in ({"text": "  a "}, {"text": "x" * 1001}, {"txt": FIESTA_TEXT}, {"text": 42}):
            with self.subTest(bad=bad), self.assertRaises(psycopg.errors.CheckViolation):
                await self.as_user("INSERT INTO llm_jobs (kind, input) VALUES ('parse_search', %s)", (Jsonb(bad),))

    async def test_hourly_rate_limit(self):
        async with db.connection() as cx:
            before = await (await cx.execute("SELECT value FROM app_config WHERE key = 'llm_limits'")).fetchone()
            await cx.execute("UPDATE app_config SET value = '{\"per_user_hour\": 2}' WHERE key = 'llm_limits'")
        try:
            insert = "INSERT INTO llm_jobs (kind, input) VALUES ('parse_search', %s)"
            await self.as_user(insert, (Jsonb({"text": FIESTA_TEXT}),))
            await self.as_user(insert, (Jsonb({"text": FIESTA_TEXT}),))
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "llm_rate_limited"):
                await self.as_user(insert, (Jsonb({"text": FIESTA_TEXT}),))
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = %s WHERE key = 'llm_limits'", (Jsonb(before["value"]),))

    async def test_stats_are_server_only(self):
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            await self.as_user("SELECT * FROM llm_job_stats")
