"""The repair bot's queue: its queries against the real schema, and its wiring with a fake connection."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import targets as targets_repo
from pgcase import PostgresTestCase, requires_db
from repairbot import queue
from tools.collector_repairs import json_text
from tools.platform_health import COLLECTORS_SQL

WORKER = Path(__file__).resolve().parents[1]
TRACE = ('Traceback (most recent call last):\n'
         '  File "/opt/automotive/worker/collectors/kavak.py", line 88, in search\n'
         'Cookie: sessionid=example_session\n'
         'RuntimeError: kavak catalog HTTP 503')


@pytest.mark.db
@requires_db
class QueuePostgresTests(PostgresTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with db.connection() as cx:
            await cx.execute("TRUNCATE collector_repair_incidents")
            await cx.execute("DELETE FROM platform_health_checks")

    async def target(self, source='kavak', model='Fiesta', *, active=True, monitored=True, query=None):
        """A Ford target; monitored ones get an accessible search of their own, like the health check needs."""
        async with db.connection() as cx:
            if monitored:
                user = await (await cx.execute(
                    "INSERT INTO auth.users(id,email,created_at,updated_at) "
                    "VALUES (gen_random_uuid(),%s,now(),now()) RETURNING id",
                    (f'{uuid4()}@automotive.test',))).fetchone()
                await cx.execute(
                    "INSERT INTO search_profiles(user_id,name,filters) VALUES (%s,'Queue fixture',%s)",
                    (user['id'], Jsonb({'make': 'Ford', 'model': model, 'sources': [source]})))
            row = await (await cx.execute(
                "INSERT INTO crawl_targets(source,make,model,query,active) VALUES (%s,'Ford',%s,%s,%s) RETURNING id",
                (source, model, Jsonb(query or {}), active))).fetchone()
        return row['id']

    async def now(self):
        """The database clock: the queries compare against it, not against this machine's."""
        async with db.connection() as cx:
            return await queue.db_now(cx)

    async def add_run(self, target_id, status, *, minutes_ago=0, at=None, source='kavak', error=None):
        started = at or await self.now() - timedelta(minutes=minutes_ago)
        async with db.connection() as cx:
            row = await (await cx.execute(
                "INSERT INTO collector_runs(source,target_id,status,started_at,finished_at,error) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (source, target_id, status, started, None if status == 'running' else started, error))).fetchone()
        return row['id']

    async def snapshot(self, checks):
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO platform_health_checks(id,checked_at,checks) VALUES (1,now(),%s) "
                "ON CONFLICT(id) DO UPDATE SET checked_at=excluded.checked_at,checks=excluded.checks",
                (Jsonb(checks),))

    async def test_failing_targets_are_monitored_targets_whose_latest_run_failed_or_is_stuck(self):
        failed = await self.target(model='Fiesta')
        recovered = await self.target(model='Focus')
        stuck = await self.target(model='Ka')
        busy = await self.target(model='Ranger')
        await self.target(model='Kuga')                      # never ran
        inactive = await self.target(model='Mondeo', active=False)
        unmonitored = await self.target(model='Escort', monitored=False)
        elsewhere = await self.target('autocosmos')
        await self.add_run(failed, 'ok', minutes_ago=60)
        await self.add_run(failed, 'failed', minutes_ago=5)
        await self.add_run(recovered, 'failed', minutes_ago=60)
        await self.add_run(recovered, 'ok', minutes_ago=5)
        await self.add_run(stuck, 'ok', minutes_ago=120)
        await self.add_run(stuck, 'running', minutes_ago=45)
        await self.add_run(busy, 'failed', minutes_ago=60)
        await self.add_run(busy, 'running', minutes_ago=5)
        await self.add_run(inactive, 'failed', minutes_ago=5)
        await self.add_run(unmonitored, 'failed', minutes_ago=5)
        await self.add_run(elsewhere, 'failed', minutes_ago=5, source='autocosmos')
        async with db.connection() as cx:
            self.assertEqual(await queue.failing_targets(cx, 'kavak'), [failed, stuck])
            self.assertEqual(await queue.failing_targets(cx, 'kavak', limit=1), [failed])
            self.assertEqual(await queue.failing_targets(cx, 'autocosmos'), [elsewhere])
            self.assertEqual(await queue.failing_targets(cx, 'facebook'), [])
            # The same answer the health snapshot derives from its own rows.
            rows = await (await cx.execute(COLLECTORS_SQL, {'history': 3})).fetchall()
            now = await queue.db_now(cx)
            expected = [row['id'] for row in rows if row['source'] == 'kavak' and (
                row['latest_status'] == 'failed' or (row['latest_status'] == 'running' and
                    now - row['started_at'] > timedelta(minutes=queue.STALLED_MINUTES)))]
            self.assertEqual(await queue.failing_targets(cx, 'kavak', limit=100), expected)

    async def test_latest_run_breaks_started_at_ties_by_id_like_the_health_check(self):
        ended_ok, ended_failed = await self.target(model='Fiesta'), await self.target(model='Focus')
        moment = await self.now() - timedelta(minutes=3)
        await self.add_run(ended_ok, 'failed', at=moment)
        await self.add_run(ended_ok, 'ok', at=moment)
        await self.add_run(ended_failed, 'ok', at=moment)
        await self.add_run(ended_failed, 'failed', at=moment)
        async with db.connection() as cx:
            self.assertEqual(await queue.failing_targets(cx, 'kavak'), [ended_failed])

    async def test_running_runs_count_recent_activity_of_the_source_only(self):
        target, elsewhere = await self.target(), await self.target('autocosmos')
        async with db.connection() as cx:
            self.assertEqual(await queue.running_runs(cx, 'kavak'), 0)
        await self.add_run(target, 'running', minutes_ago=2)
        await self.add_run(target, 'running', minutes_ago=20)
        await self.add_run(None, 'running', minutes_ago=1)       # a run whose target was deleted
        await self.add_run(target, 'running', minutes_ago=45)    # stuck: nobody is going to finish it
        await self.add_run(target, 'ok', minutes_ago=1)
        await self.add_run(target, 'failed', minutes_ago=1)
        await self.add_run(elsewhere, 'running', minutes_ago=1, source='autocosmos')
        async with db.connection() as cx:
            self.assertEqual(await queue.running_runs(cx, 'kavak'), 3)
            self.assertEqual(await queue.running_runs(cx, 'autocosmos'), 1)
            self.assertEqual(await queue.running_runs(cx, 'facebook'), 0)

    async def test_kick_makes_only_active_targets_of_the_source_due_and_reports_them(self):
        first, second = await self.target(model='Fiesta'), await self.target(model='Focus')
        untouched = await self.target(model='Ka')
        inactive = await self.target(model='Mondeo', active=False)
        elsewhere = await self.target('autocosmos')
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET next_run_at = now() + interval '2 hours'")
        self.assertEqual(await targets_repo.due_targets(), [])
        async with db.connection() as cx:
            self.assertEqual(await queue.kick(cx, 'kavak', []), [])
            kicked = await queue.kick(cx, 'kavak', [second, inactive, elsewhere, first, second, 2_000_000_000])
        self.assertEqual(kicked, [first, second])
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT id, next_run_at <= now() AS due FROM crawl_targets ORDER BY id")).fetchall()
        self.assertEqual({row['id']: row['due'] for row in rows},
                         {first: True, second: True, untouched: False, inactive: False, elsewhere: False})
        # The scheduler picks exactly the kicked targets up on its next tick.
        self.assertEqual(sorted(row['id'] for row in await targets_repo.due_targets()), [first, second])

    async def test_runs_since_returns_later_runs_of_the_given_targets_oldest_first(self):
        first, second = await self.target(model='Fiesta'), await self.target(model='Focus')
        ignored, elsewhere = await self.target(model='Ka'), await self.target('autocosmos')
        deployed = await self.now() - timedelta(minutes=10)
        await self.add_run(first, 'failed', minutes_ago=20)
        ok = await self.add_run(first, 'ok', minutes_ago=5)
        failed = await self.add_run(second, 'failed', minutes_ago=4, error=TRACE)
        running = await self.add_run(second, 'running', minutes_ago=1)
        await self.add_run(ignored, 'ok', minutes_ago=2)
        await self.add_run(elsewhere, 'ok', minutes_ago=2, source='autocosmos')
        async with db.connection() as cx:
            rows = await queue.runs_since(cx, 'kavak', [second, first], deployed)
            self.assertEqual([(row['id'], row['target_id'], row['status']) for row in rows],
                             [(ok, first, 'ok'), (failed, second, 'failed'), (running, second, 'running')])
            self.assertEqual(set(rows[0]), {'id', 'target_id', 'status', 'started_at', 'finished_at',
                                            'found', 'new', 'updated', 'error'})
            self.assertIsNone(rows[0]['error'])
            self.assertNotIn('example_session', rows[1]['error'])
            self.assertTrue(rows[1]['error'].endswith('RuntimeError: kavak catalog HTTP 503'))
            self.assertIsNone(rows[2]['finished_at'])
            self.assertEqual(await queue.runs_since(cx, 'kavak', [first], await queue.db_now(cx)), [])
            self.assertEqual(await queue.runs_since(cx, 'kavak', [], deployed), [])
            self.assertEqual(await queue.runs_since(cx, 'autocosmos', [first, second], deployed), [])

    async def test_active_incidents_follow_the_queue_from_claim_to_recovery(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos', 'collector:autocosmos': 'Parser'})
        async with db.connection() as cx:
            pending = await queue.active_incidents(cx)
            self.assertEqual([(row['source'], row['status']) for row in pending],
                             [('kavak', 'pending'), ('autocosmos', 'pending')])
            reserved = await queue.claim(cx, 'claude-repair-bot')
            self.assertEqual((reserved['id'], reserved['lease_owner']), (pending[0]['id'], 'claude-repair-bot'))
            self.assertTrue(await queue.attach(cx, reserved['id'], reserved['claim_token'], 'claude-bot:run-1'))
            self.assertTrue(await queue.needs_input(
                cx, reserved['id'], 'Renovar la sesión de Kavak.\nCookie: sessionid=example_session'))
        async with db.connection() as cx:
            active = await queue.active_incidents(cx)
        self.assertEqual([(row['source'], row['status'], row['thread_id']) for row in active],
                         [('kavak', 'needs_input', 'claude-bot:run-1'), ('autocosmos', 'pending', None)])
        self.assertIn('Renovar la sesión de Kavak.', active[0]['note'])
        self.assertNotIn('example_session', active[0]['note'])
        await self.snapshot({'base': None, 'collector:kavak': None, 'collector:autocosmos': 'Parser'})
        async with db.connection() as cx:
            self.assertEqual([row['source'] for row in await queue.active_incidents(cx)], ['autocosmos'])

    async def test_incident_context_is_sanitized_evidence_of_that_source(self):
        target = await self.target(query={'year_min': 2014, 'profile_ids': ['private-user'], 'origin_lat': -34.5})
        await self.target(model='Mondeo', active=False)
        await self.add_run(await self.target('autocosmos'), 'failed', source='autocosmos', error='RuntimeError: otra fuente')
        run = await self.add_run(target, 'failed', minutes_ago=1, error=TRACE)
        await self.snapshot({'base': None, 'collector:kavak': 'Kavak · Ford Fiesta: 3 corridas fallidas'})
        async with db.connection() as cx:
            incident, = await queue.active_incidents(cx)
            context = await queue.incident_context(cx, incident)
        self.assertEqual(set(context), {'incident', 'problem', 'health', 'targets', 'runs'})
        self.assertEqual(context['incident']['id'], incident['id'])
        self.assertEqual(context['health']['problem'], 'Kavak · Ford Fiesta: 3 corridas fallidas')
        self.assertEqual([(row['id'], row['query']) for row in context['targets']], [(target, {'year_min': 2014})])
        self.assertEqual([row['id'] for row in context['runs']], [run])
        self.assertTrue(context['runs'][0]['error'].endswith('RuntimeError: kavak catalog HTTP 503'))
        encoded = json_text(context)
        for private in ('example_session', 'private-user', 'origin_lat', 'claim_token', 'otra fuente'):
            self.assertNotIn(private, encoded)


class Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def fetchall(self):
        return self.rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None


class Connection:
    """Answers every statement with the same rows and remembers what it was asked."""

    def __init__(self, *rows):
        self.rows, self.statements = list(rows), []

    async def execute(self, sql, params=None):
        self.statements.append((sql, params))
        return Cursor(self.rows)


class QueueWiringTests(unittest.IsolatedAsyncioTestCase):
    def test_importing_the_queue_loads_neither_config_nor_the_database(self):
        loaded = subprocess.run(
            [sys.executable, '-c', 'import sys, repairbot.queue; print(sorted(set(sys.modules) & '
             '{"config", "db", "psycopg", "tools.collector_repairs", "tools.platform_health"}))'],
            cwd=WORKER, capture_output=True, encoding='utf-8', errors='replace', timeout=60)
        self.assertEqual((loaded.returncode, loaded.stdout.strip()), (0, '[]'), loaded.stderr)

    async def test_claim_attach_and_needs_input_use_the_repository(self):
        cx, incident, token = Connection(), uuid4(), uuid4()
        with patch('db.repos.collector_repairs.claim', AsyncMock(return_value={'id': incident})) as claim, \
             patch('db.repos.collector_repairs.attach', AsyncMock(return_value=True)) as attach, \
             patch('db.repos.collector_repairs.needs_input', AsyncMock(return_value=True)) as needs_input:
            self.assertEqual(await queue.claim(cx, 'claude-repair-bot'), {'id': incident})
            self.assertTrue(await queue.attach(cx, incident, token, 'claude-bot:run-1'))
            self.assertTrue(await queue.needs_input(cx, incident, 'Resolver el captcha.\ntoken=example_token'))
        claim.assert_awaited_once_with(cx, 'claude-repair-bot')
        attach.assert_awaited_once_with(cx, incident, token, 'claude-bot:run-1')
        (_, _, note), _ = needs_input.await_args
        self.assertIn('Resolver el captcha.', note)
        self.assertNotIn('example_token', note)
        self.assertEqual(cx.statements, [])

    async def test_active_incidents_reads_unresolved_rows_in_queue_order(self):
        cx = Connection({'id': uuid4(), 'source': 'kavak'})
        self.assertEqual(await queue.active_incidents(cx), cx.rows)
        (sql, params), = cx.statements
        self.assertIn('resolved_at IS NULL', sql)
        self.assertIn('ORDER BY created_at, id', sql)
        self.assertTrue(sql.startswith('SELECT'))
        self.assertIsNone(params)

    async def test_failing_targets_filters_the_health_query_itself(self):
        cx = Connection({'id': 4}, {'id': 9})
        self.assertEqual(await queue.failing_targets(cx, 'kavak', limit=2), [4, 9])
        (sql, params), = cx.statements
        self.assertIn(COLLECTORS_SQL, sql)
        self.assertTrue(sql.startswith('select id from ('))
        self.assertEqual(params, {'history': 1, 'source': 'kavak', 'stalled': 30, 'limit': 2})
        self.assertEqual(sql.count('%('), 4)   # one placeholder per parameter: none can be left unbound

    async def test_running_runs_returns_the_count(self):
        cx = Connection({'running': 2})
        self.assertEqual(await queue.running_runs(cx, 'kavak'), 2)
        (sql, params), = cx.statements
        self.assertIn("status = 'running'", sql)
        self.assertEqual(params, ('kavak', queue.STALLED_MINUTES))

    async def test_kick_updates_only_active_targets_of_the_source(self):
        cx = Connection({'id': 9}, {'id': 4})
        self.assertEqual(await queue.kick(cx, 'kavak', [9, 4, 9, 30]), [4, 9])
        (sql, params), = cx.statements
        self.assertTrue(sql.startswith('UPDATE crawl_targets SET next_run_at = now() WHERE source = %s AND active '))
        self.assertTrue(sql.endswith('RETURNING id'))
        self.assertEqual(params, ('kavak', [4, 9, 30]))

    async def test_nothing_to_kick_or_verify_runs_no_statement(self):
        cx = Connection({'id': 1})
        self.assertEqual(await queue.kick(cx, 'kavak', []), [])
        self.assertEqual(await queue.runs_since(cx, 'kavak', [], datetime.now(timezone.utc)), [])
        self.assertEqual(cx.statements, [])

    async def test_target_ids_must_be_integers(self):
        cx = Connection()
        for ids in (['7'], [7.0], [True], [None], ['1); DELETE FROM crawl_targets --']):
            with self.subTest(ids=ids):
                with self.assertRaises(ValueError):
                    await queue.kick(cx, 'kavak', ids)
                with self.assertRaises(ValueError):
                    await queue.runs_since(cx, 'kavak', ids, datetime.now(timezone.utc))
        self.assertEqual(cx.statements, [])

    async def test_runs_since_needs_an_aware_datetime_and_sanitizes_errors(self):
        since = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
        cx = Connection({'id': 1, 'target_id': 7, 'status': 'failed', 'error': TRACE},
                        {'id': 2, 'target_id': 7, 'status': 'ok', 'error': None})
        for naive in (datetime(2026, 10, 13, 12), '2026-10-13T12:00:00+00:00'):
            with self.assertRaises(ValueError):
                await queue.runs_since(cx, 'kavak', [7], naive)
        self.assertEqual(cx.statements, [])
        failed, ok = await queue.runs_since(cx, 'kavak', [7, 3], since)
        self.assertNotIn('example_session', failed['error'])
        self.assertTrue(failed['error'].endswith('RuntimeError: kavak catalog HTTP 503'))
        self.assertIsNone(ok['error'])
        (sql, params), = cx.statements
        self.assertTrue(sql.startswith('SELECT'))
        self.assertIn('started_at > %s', sql)
        self.assertEqual(params, ('kavak', [3, 7], since))

    async def test_incident_context_builds_the_prompt_evidence(self):
        incident = dict(id=uuid4(), source='kavak', status='open', problem='Tres fallos', claim_token=uuid4())
        cx = Connection(dict(id=40, target_id=1, status='failed', error=TRACE, make='Ford', model='Fiesta',
                             query={'year_min': 2014, 'profile_ids': ['private-user']}))
        context = await queue.incident_context(cx, incident)
        self.assertEqual(set(context), {'incident', 'problem', 'health', 'targets', 'runs'})
        self.assertEqual(context['targets'][0]['query'], {'year_min': 2014})
        self.assertTrue(all(sql.startswith('SELECT') for sql, _ in cx.statements))
        encoded = json_text(context)
        for private in ('example_session', 'private-user', 'claim_token'):
            self.assertNotIn(private, encoded)

    async def test_db_now_reads_the_database_clock(self):
        moment = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
        self.assertEqual(await queue.db_now(Connection({'now': moment})), moment)
