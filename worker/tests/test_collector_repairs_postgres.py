"""The private repair queue consumes the same snapshot as Revisar fuentes."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.errors import InsufficientPrivilege, UniqueViolation
from psycopg.types.json import Jsonb

import db
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]


class CollectorRepairTests(PostgresTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        async with db.connection() as cx:
            await cx.execute("TRUNCATE collector_repair_incidents")
            await cx.execute("DELETE FROM platform_health_checks")

    async def snapshot(self, checks, checked_at=None):
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO platform_health_checks(id,checked_at,checks) VALUES (1,%s,%s) "
                "ON CONFLICT(id) DO UPDATE SET checked_at=excluded.checked_at,checks=excluded.checks",
                (checked_at or datetime.now(timezone.utc), Jsonb(checks)))

    async def incidents(self):
        async with db.connection() as cx:
            return await (await cx.execute(
                "SELECT * FROM collector_repair_incidents ORDER BY created_at,id")).fetchall()

    async def claim(self, owner='monitor', lease_seconds=900):
        from db.repos import collector_repairs
        async with db.connection() as cx:
            return await collector_repairs.claim(cx, owner, lease_seconds)

    async def attach(self, incident_id, token, thread_id):
        from db.repos import collector_repairs
        async with db.connection() as cx:
            return await collector_repairs.attach(cx, incident_id, token, thread_id)

    async def needs_input(self, incident_id, note):
        from db.repos import collector_repairs
        async with db.connection() as cx:
            return await collector_repairs.needs_input(cx, incident_id, note)

    async def test_repeated_revisar_updates_one_incident(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres corridas fallidas'})
        first, = await self.incidents()
        await self.snapshot({'base': None, 'collector:kavak': 'Parser sin avisos'})
        current, = await self.incidents()
        self.assertEqual(current['id'], first['id'])
        self.assertEqual(current['problem'], 'Parser sin avisos')
        self.assertEqual(current['status'], 'pending')
        self.assertIsNone(current['resolved_at'])

    async def test_healthy_closes_and_later_failure_creates_a_new_incident(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Sin avisos'})
        first, = await self.incidents()
        await self.snapshot({'base': None, 'collector:kavak': None})
        resolved, = await self.incidents()
        self.assertEqual(resolved['status'], 'resolved')
        self.assertIsNotNone(resolved['resolved_at'])
        await self.snapshot({'base': None, 'collector:kavak': 'Otro fallo'})
        old, active = await self.incidents()
        self.assertEqual(old['id'], first['id'])
        self.assertNotEqual(active['id'], first['id'])
        self.assertEqual(active['status'], 'pending')

    async def test_removing_a_collector_cancels_its_incident(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Sin avisos'})
        await self.snapshot({'base': None, 'worker': 'Worker detenido', 'web': 'HTTP 503'})
        cancelled, = await self.incidents()
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertIsNotNone(cancelled['resolved_at'])

    async def test_a_claim_reserves_once_and_repeated_health_keeps_the_lease(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        reserved = await self.claim('PC-Juan')
        self.assertEqual(reserved['source'], 'kavak')
        self.assertEqual(reserved['status'], 'dispatching')
        self.assertEqual(reserved['lease_owner'], 'PC-Juan')
        self.assertFalse(reserved['lease_recovered'])
        self.assertIsNotNone(reserved['claim_token'])
        self.assertGreater(reserved['lease_expires_at'], reserved['updated_at'])
        self.assertIsNone(await self.claim('other-monitor'))
        await self.snapshot({'base': None, 'collector:kavak': 'Nuevo detalle'})
        current, = await self.incidents()
        self.assertEqual(current['id'], reserved['id'])
        self.assertEqual(current['claim_token'], reserved['claim_token'])
        self.assertEqual(current['lease_expires_at'], reserved['lease_expires_at'])
        self.assertEqual(current['status'], 'dispatching')

    async def test_attach_requires_the_token_and_is_idempotent_for_the_same_chat(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        reserved = await self.claim()
        incident_id, token = reserved['id'], reserved['claim_token']
        self.assertFalse(await self.attach(incident_id, uuid4(), 'chat-1'))
        self.assertTrue(await self.attach(incident_id, token, 'chat-1'))
        self.assertTrue(await self.attach(incident_id, token, 'chat-1'))
        self.assertFalse(await self.attach(incident_id, token, 'chat-2'))
        self.assertFalse(await self.attach(incident_id, uuid4(), 'chat-1'))
        current, = await self.incidents()
        self.assertEqual(current['status'], 'open')
        self.assertEqual(current['thread_id'], 'chat-1')
        self.assertEqual(current['claim_token'], token)
        self.assertIsNone(await self.claim())

    async def test_ambiguous_chat_creation_waits_for_input_without_reclaiming(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        pending, = await self.incidents()
        self.assertFalse(await self.needs_input(pending['id'], 'Aún no hay reserva'))
        reserved = await self.claim()
        self.assertTrue(await self.needs_input(reserved['id'], 'Consultar el chat ya creado'))
        current, = await self.incidents()
        self.assertEqual(current['status'], 'needs_input')
        self.assertEqual(current['note'], 'Consultar el chat ya creado')
        self.assertEqual(current['claim_token'], reserved['claim_token'])
        self.assertIsNone(current['thread_id'])
        self.assertIsNone(await self.claim())

    async def test_quarantined_creation_can_attach_the_matching_chat_after_expiry(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        reserved = await self.claim()
        self.assertTrue(await self.needs_input(reserved['id'], 'Creación incierta: reconciliar por UUID'))
        async with db.connection() as cx:
            await cx.execute("UPDATE collector_repair_incidents SET lease_expires_at=now()-interval '1 minute'")
        self.assertIsNone(await self.claim('another-monitor'))
        self.assertFalse(await self.attach(reserved['id'], uuid4(), 'quarantined-chat'))
        self.assertTrue(await self.attach(reserved['id'], reserved['claim_token'], 'quarantined-chat'))
        self.assertFalse(await self.attach(reserved['id'], reserved['claim_token'], 'another-chat'))
        current, = await self.incidents()
        self.assertEqual(current['status'], 'needs_input')
        self.assertEqual(current['thread_id'], 'quarantined-chat')
        self.assertEqual(current['note'], 'Creación incierta: reconciliar por UUID')

    async def test_recovery_between_chat_creation_and_attach_retains_the_association(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        reserved = await self.claim()
        await self.snapshot({'base': None, 'collector:kavak': None})
        async with db.connection() as cx:
            await cx.execute("UPDATE collector_repair_incidents SET lease_expires_at=now()-interval '1 minute'")
        self.assertFalse(await self.attach(reserved['id'], uuid4(), 'created-before-recovery'))
        self.assertTrue(await self.attach(reserved['id'], reserved['claim_token'], 'created-before-recovery'))
        self.assertTrue(await self.attach(reserved['id'], reserved['claim_token'], 'created-before-recovery'))
        current, = await self.incidents()
        self.assertEqual(current['status'], 'resolved')
        self.assertEqual(current['thread_id'], 'created-before-recovery')
        self.assertEqual(current['claim_token'], reserved['claim_token'])
        self.assertIsNotNone(current['resolved_at'])
        self.assertIsNone(await self.claim())

    async def test_disabled_source_cancels_an_active_incident_even_with_the_old_key(self):
        checks = {'base': None, 'collector:kavak': 'Tres fallos'}
        await self.snapshot(checks)
        reserved = await self.claim()
        async with db.connection() as cx:
            await cx.execute("UPDATE sources SET enabled=false WHERE id='kavak'")
        try:
            self.assertIsNone(await self.claim())
            await self.snapshot(checks)
            current, = await self.incidents()
            self.assertEqual(current['status'], 'cancelled')
            self.assertEqual(current['claim_token'], reserved['claim_token'])
            self.assertIsNotNone(current['resolved_at'])
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE sources SET enabled=true WHERE id='kavak'")

    async def test_stale_future_failed_or_unknown_base_snapshots_cannot_change_or_claim_incidents(self):
        checks = {'base': None, 'collector:kavak': 'Tres fallos'}
        await self.snapshot(checks)
        first, = await self.incidents()
        now = datetime.now(timezone.utc)
        for invalid, checked_at in (
            ({'base': None}, now - timedelta(minutes=12)),
            ({'base': None}, now + timedelta(minutes=2)),
            ({'base': 'No se pudo comprobar la base'}, now),
            ({}, now),
            ({'base': False}, now),
        ):
            with self.subTest(checks=invalid, checked_at=checked_at):
                # An absent collector must not be misread as a recovery or removal.
                await self.snapshot(invalid, checked_at)
                current, = await self.incidents()
                self.assertEqual(current['status'], 'pending')
                self.assertEqual(current['problem'], first['problem'])
                self.assertEqual(current['health_checked_at'], first['health_checked_at'])
                self.assertIsNone(await self.claim())
                # Neither should a failure create a new incident under unknown health.
                await self.snapshot({**invalid, 'collector:autocosmos': 'Parser falló'}, checked_at)
                self.assertEqual(len(await self.incidents()), 1)

    async def test_malformed_collector_values_are_unknown_and_cannot_recover_or_claim(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        first, = await self.incidents()
        for malformed in ('', '  ', False, 123, {}, []):
            with self.subTest(value=malformed):
                await self.snapshot({'base': None, 'collector:kavak': malformed})
                current, = await self.incidents()
                self.assertEqual(current['id'], first['id'])
                self.assertEqual(current['status'], 'pending')
                self.assertEqual(current['problem'], 'Tres fallos')
                self.assertIsNone(await self.claim())

    async def test_unknown_disabled_worker_and_web_problems_do_not_create_incidents(self):
        async with db.connection() as cx:
            await cx.execute("UPDATE sources SET enabled=false WHERE id='kavak'")
        try:
            await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos',
                                 'collector:unknown-source': 'Tres fallos',
                                 'worker': 'Detenido', 'web': 'HTTP 503'})
            self.assertEqual(await self.incidents(), [])
            self.assertIsNone(await self.claim())
        finally:
            async with db.connection() as cx:
                await cx.execute("UPDATE sources SET enabled=true WHERE id='kavak'")

    async def test_an_expired_lease_is_recovered_with_a_new_token(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        expired = await self.claim('old-monitor')
        async with db.connection() as cx:
            await cx.execute("UPDATE collector_repair_incidents SET lease_expires_at=now()-interval '1 minute'")
        self.assertFalse(await self.attach(expired['id'], expired['claim_token'], 'orphan-chat'))
        recovered = await self.claim('new-monitor')
        self.assertEqual(recovered['id'], expired['id'])
        self.assertEqual(recovered['lease_owner'], 'new-monitor')
        self.assertTrue(recovered['lease_recovered'])
        self.assertNotEqual(recovered['claim_token'], expired['claim_token'])
        self.assertFalse(await self.attach(expired['id'], expired['claim_token'], 'orphan-chat'))
        self.assertTrue(await self.attach(recovered['id'], recovered['claim_token'], 'orphan-chat'))
        self.assertIsNone(await self.claim())

    async def test_two_connections_claim_distinct_incidents_without_waiting_for_commit(self):
        from db.repos import collector_repairs
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos',
                             'collector:autocosmos': 'Parser sin avisos'})
        async with db.connection() as first, db.connection() as second:
            left, right = await asyncio.wait_for(asyncio.gather(
                collector_repairs.claim(first, 'left-monitor'),
                collector_repairs.claim(second, 'right-monitor')), timeout=5)
            self.assertNotEqual(left['id'], right['id'])
            self.assertEqual({left['source'], right['source']}, {'kavak', 'autocosmos'})
        self.assertIsNone(await self.claim())

    async def test_a_chat_waiting_for_input_keeps_its_chat_and_is_not_redispatched(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        reserved = await self.claim()
        self.assertTrue(await self.attach(reserved['id'], reserved['claim_token'], 'chat-1'))
        self.assertTrue(await self.needs_input(reserved['id'], 'Renovar sesión de acceso'))
        await self.snapshot({'base': None, 'collector:kavak': 'Sigue bloqueado'})
        self.assertTrue(await self.attach(reserved['id'], reserved['claim_token'], 'chat-1'))
        current, = await self.incidents()
        self.assertEqual(current['status'], 'needs_input')
        self.assertEqual(current['thread_id'], 'chat-1')
        self.assertEqual(current['note'], 'Renovar sesión de acceso')
        self.assertIsNone(await self.claim())
        await self.snapshot({'base': None, 'collector:kavak': None})
        self.assertFalse(await self.needs_input(reserved['id'], 'No debe reabrirse'))

    async def test_cancelled_dispatch_can_attach_late_without_reopening(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        reserved = await self.claim()
        await self.snapshot({'base': None})
        self.assertTrue(await self.attach(reserved['id'], reserved['claim_token'], 'chat-1'))
        self.assertFalse(await self.attach(reserved['id'], reserved['claim_token'], 'chat-2'))
        current, = await self.incidents()
        self.assertEqual(current['status'], 'cancelled')
        self.assertEqual(current['thread_id'], 'chat-1')
        self.assertIsNone(await self.claim())

    async def test_database_prevents_two_active_incidents_for_one_source(self):
        await self.snapshot({'base': None, 'collector:kavak': 'Tres fallos'})
        async with db.connection() as cx:
            with self.assertRaises(UniqueViolation):
                async with cx.transaction():
                    await cx.execute("INSERT INTO collector_repair_incidents(source,problem,health_checked_at) "
                                     "VALUES ('kavak','Otro fallo',now())")
        self.assertEqual(len(await self.incidents()), 1)

    async def test_browser_roles_cannot_read_write_or_invoke_the_private_queue(self):
        async with db.connection() as cx:
            security = await (await cx.execute(
                "SELECT relrowsecurity FROM pg_class WHERE oid='public.collector_repair_incidents'::regclass")).fetchone()
            self.assertTrue(security['relrowsecurity'])
            for role in ('anon', 'authenticated'):
                for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                    with self.subTest(role=role, privilege=privilege):
                        row = await (await cx.execute("SELECT has_table_privilege(%s,"
                            "'public.collector_repair_incidents',%s) AS allowed", (role, privilege))).fetchone()
                        self.assertFalse(row['allowed'])
                for function in ('public.capture_collector_repairs(timestamptz,jsonb)',
                                 'public.capture_collector_repairs_on_health()'):
                    row = await (await cx.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') AS allowed",
                                                  (role, function))).fetchone()
                    self.assertFalse(row['allowed'])
                with self.assertRaises(InsufficientPrivilege):
                    async with cx.transaction():
                        await cx.execute(f"SET LOCAL ROLE {role}")
                        await cx.execute("SELECT * FROM collector_repair_incidents")
            for privilege in ('SELECT', 'INSERT', 'UPDATE', 'DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER'):
                row = await (await cx.execute("SELECT has_table_privilege('service_role',"
                    "'public.collector_repair_incidents',%s) AS allowed", (privilege,))).fetchone()
                self.assertEqual(row['allowed'], privilege in ('SELECT', 'INSERT', 'UPDATE'))
            functions = await (await cx.execute(
                "SELECT prosecdef,proconfig FROM pg_proc WHERE oid IN ("
                "'public.capture_collector_repairs(timestamptz,jsonb)'::regprocedure,"
                "'public.capture_collector_repairs_on_health()'::regprocedure)")).fetchall()
            self.assertEqual(len(functions), 2)
            for function in functions:
                self.assertFalse(function['prosecdef'])
                self.assertIn('search_path=""', function['proconfig'])

    async def test_service_role_health_publish_captures_and_dispatches_incidents(self):
        from db.repos import collector_repairs
        async with db.connection() as cx:
            await cx.execute("SET LOCAL ROLE service_role")
            await cx.execute("INSERT INTO platform_health_checks(id,checked_at,checks) "
                             "VALUES (1,now(),%s)", (Jsonb({'base': None, 'collector:kavak': 'Tres fallos'}),))
            reserved = await collector_repairs.claim(cx, 'server-role')
            self.assertTrue(await collector_repairs.attach(cx, reserved['id'], reserved['claim_token'], 'chat-1'))
            self.assertTrue(await collector_repairs.needs_input(cx, reserved['id'], 'Renovar sesión'))
        current, = await self.incidents()
        self.assertEqual(current['status'], 'needs_input')

    async def test_migration_backfills_fresh_snapshots_but_ignores_unknown_health(self):
        migration = (Path(__file__).resolve().parents[2] / 'supabase' / 'migrations' /
                     '20261015120000_collector_repair_incidents.sql').read_text(encoding='utf-8')
        for age, base, expected in ((0, None, 1), (13, None, 0), (0, 'Base inaccesible', 0)):
            with self.subTest(age=age, base=base):
                await self.snapshot({'base': base, 'collector:kavak': 'Tres fallos'},
                                    datetime.now(timezone.utc) - timedelta(minutes=age))
                async with db.connection() as cx:
                    # Exercise installing the actual migration over an existing
                    # snapshot. DDL and fixture changes roll back together.
                    async with cx.transaction(force_rollback=True):
                        await cx.execute("DROP TRIGGER platform_health_capture_collector_repairs ON platform_health_checks")
                        await cx.execute("DROP FUNCTION capture_collector_repairs_on_health()")
                        await cx.execute("DROP FUNCTION capture_collector_repairs(timestamptz,jsonb)")
                        await cx.execute("DROP TABLE collector_repair_incidents")
                        await cx.execute(migration)
                        row = await (await cx.execute("SELECT count(*) AS n FROM collector_repair_incidents")).fetchone()
                        self.assertEqual(row['n'], expected)
