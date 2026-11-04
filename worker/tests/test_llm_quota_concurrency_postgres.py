"""Real concurrent trigger checks in an empty, dedicated local scratch database.

Set LLM_QUOTA_TEST_DATABASE_URL to a loopback database named llm_quota_*_test.
This module refuses databases with existing public tables and never loads .env.
It installs the latest real trigger definition from the migration history into
minimal tables, so it can run without touching the shared Supabase stack.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4

import psycopg


TEST_URL = os.getenv("LLM_QUOTA_TEST_DATABASE_URL", "").strip()
MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
FUNCTION = re.compile(
    r"create\s+(?:or\s+replace\s+)?function\s+public\.enforce_llm_rate_limit\(\)"
    r"\s+returns\s+trigger\b.*?\$\$\s*;",
    re.IGNORECASE | re.DOTALL,
)


def latest_trigger_definition() -> str:
    definitions = [
        match.group()
        for migration in sorted(MIGRATIONS.glob("*.sql"))
        for match in FUNCTION.finditer(migration.read_text(encoding="utf-8"))
    ]
    if not definitions:
        raise AssertionError("enforce_llm_rate_limit migration not found")
    return definitions[-1]


@unittest.skipUnless(TEST_URL, "LLM_QUOTA_TEST_DATABASE_URL not set (dedicated local scratch DB only)")
class LlmQuotaConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = urlparse(TEST_URL)
        name = url.path.lstrip("/")
        if url.hostname not in {"127.0.0.1", "localhost", "::1"} or not re.fullmatch(r"llm_quota_[a-z0-9_]+_test", name):
            raise AssertionError("quota regression requires a dedicated loopback llm_quota_*_test database")
        cls.observer = psycopg.connect(TEST_URL, autocommit=True)
        if cls.observer.execute("select tablename from pg_tables where schemaname='public'").fetchone():
            cls.observer.close()
            raise AssertionError("quota regression refuses a database with existing public tables")
        cls.observer.execute("""
            create table public.profiles (id uuid primary key, email_only boolean not null default false);
            create table public.app_config (key text primary key, value jsonb not null);
            create table public.llm_jobs (
                id bigint generated always as identity primary key,
                user_id uuid not null references public.profiles(id),
                kind text not null default 'parse_search',
                created_at timestamptz not null default now()
            );
        """)
        cls.observer.execute(latest_trigger_definition())
        cls.observer.execute("""
            create trigger llm_jobs_enforce_rate_limit before insert on public.llm_jobs
            for each row execute function public.enforce_llm_rate_limit();
        """)

    @classmethod
    def tearDownClass(cls):
        cls.observer.execute("""
            drop table public.llm_jobs, public.app_config, public.profiles;
            drop function public.enforce_llm_rate_limit();
        """)
        cls.observer.close()

    def setUp(self):
        self.observer.execute("truncate public.llm_jobs, public.profiles")
        self.observer.execute("""
            insert into public.app_config values ('llm_limits', '{"per_user_hour":1,"email_only_per_user_hour":1}')
            on conflict (key) do update set value=excluded.value
        """)
        self.user, self.other = uuid4(), uuid4()
        self.observer.execute("insert into public.profiles(id) values (%s),(%s)", (self.user, self.other))

    def connection(self):
        cx = psycopg.connect(TEST_URL)
        cx.execute("set transaction isolation level read committed")
        cx.execute("set local statement_timeout='5s'")
        self.assertEqual(cx.execute("show transaction_isolation").fetchone()[0], "read committed")
        self.addCleanup(cx.close)
        return cx

    def concurrent_inserts(self, *, commit_first: bool, same_user: bool = True):
        first, second = self.connection(), self.connection()
        first_pid = first.execute("select pg_backend_pid()").fetchone()[0]
        second_pid = second.execute("select pg_backend_pid()").fetchone()[0]
        first.execute("insert into public.llm_jobs(user_id) values (%s)", (self.user,))

        def insert_second():
            try:
                second.execute("insert into public.llm_jobs(user_id) values (%s)",
                               (self.user if same_user else self.other,))
                second.commit()
                return "accepted"
            except psycopg.errors.RaiseException as error:
                second.rollback()
                return error.diag.message_primary

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(insert_second)
            blocked = False
            try:
                deadline = time.monotonic() + 3
                while not pending.done() and time.monotonic() < deadline:
                    blockers = self.observer.execute("select pg_blocking_pids(%s)", (second_pid,)).fetchone()[0]
                    if first_pid in blockers:
                        blocked = True
                        break
                    time.sleep(0.01)
                if commit_first:
                    first.commit()
                else:
                    first.rollback()
                result = pending.result(timeout=6)
            finally:
                # Also release the lock if an assertion or observer query fails.
                first.rollback()
        count = self.observer.execute("select count(*) from public.llm_jobs").fetchone()[0]
        return blocked, result, count

    def test_concurrent_same_account_cannot_exceed_hourly_cap(self):
        self.assertEqual(self.concurrent_inserts(commit_first=True), (True, "llm_rate_limited", 1))

    def test_rolled_back_request_does_not_consume_quota(self):
        self.assertEqual(self.concurrent_inserts(commit_first=False), (True, "accepted", 1))

    def test_other_account_does_not_wait_for_uncommitted_request(self):
        self.assertEqual(self.concurrent_inserts(commit_first=True, same_user=False), (False, "accepted", 2))

    def test_email_only_account_keeps_its_lower_limit(self):
        self.observer.execute("update public.profiles set email_only=true where id=%s", (self.user,))
        self.observer.execute("""
            update public.app_config set value='{"per_user_hour":30,"email_only_per_user_hour":1}'
            where key='llm_limits'
        """)
        self.assertEqual(self.concurrent_inserts(commit_first=True), (True, "llm_rate_limited", 1))

    def test_model_guides_do_not_consume_the_assisted_quota(self):
        self.observer.execute("""
            insert into public.llm_jobs(user_id,kind) values (%s,'model_guide'),(%s,'model_guide')
        """, (self.user, self.user))
        self.assertEqual(self.concurrent_inserts(commit_first=True), (True, "llm_rate_limited", 3))

    def test_model_guide_is_allowed_when_assisted_cap_is_exhausted(self):
        self.observer.execute("insert into public.llm_jobs(user_id) values (%s)", (self.user,))
        self.observer.execute("insert into public.llm_jobs(user_id,kind) values (%s,'model_guide')", (self.user,))
        self.assertEqual(self.observer.execute("select count(*) from public.llm_jobs").fetchone()[0], 2)
