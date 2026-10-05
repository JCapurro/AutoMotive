from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from tools import platform_health as health

NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)


def target(**changes):
    row = dict(id=1, source='kavak', name='Kavak', make='Ford', model='Fiesta',
               created_at=NOW-timedelta(days=1), updated_at=NOW-timedelta(days=1),
               next_run_at=NOW+timedelta(minutes=5), crawl_interval_seconds=600,
               started_at=NOW-timedelta(minutes=1), latest_status='ok', latest_error=None,
               statuses=['ok']*3, found=[12]*3, had_results=True)
    return {**row, **changes}


class CollectorChecksTests(unittest.TestCase):
    def check(self, **changes):
        return health.collector_checks([target(**changes)], NOW)['collector:kavak']

    def test_healthy_and_transient_failure(self):
        self.assertIsNone(self.check())
        self.assertIsNone(self.check(statuses=['failed','ok','ok'], latest_status='failed'))

    def test_repeated_failure_and_recovery(self):
        self.assertIn('3 corridas', self.check(statuses=['failed']*3, latest_status='failed', latest_error='RuntimeError: login wall'))
        self.assertIsNone(self.check(statuses=['ok','failed','failed']))

    def test_one_healthy_target_does_not_hide_another_broken_target(self):
        rows = [target(statuses=['failed']*3, latest_status='failed'), target(id=2)]
        self.assertIn('3 corridas', health.collector_checks(rows, NOW)['collector:kavak'])

    def test_stalled_run_but_not_running_normally(self):
        self.assertIn('trabada', self.check(latest_status='running', started_at=NOW-timedelta(hours=1)))
        self.assertIsNone(self.check(latest_status='running', next_run_at=NOW-timedelta(hours=3)))

    def test_missed_cadence_and_never_started_target(self):
        self.assertIn('vencida', self.check(next_run_at=NOW-timedelta(hours=2)))
        self.assertIn('vencida', self.check(next_run_at=None, latest_status=None, statuses=[], found=[]))

    def test_reactivated_target_gets_grace(self):
        self.assertIsNone(self.check(next_run_at=NOW-timedelta(hours=2), updated_at=NOW))

    def test_empty_runs_need_prior_positive_results(self):
        self.assertIn('posible rotura', self.check(found=[0]*3))
        self.assertIsNone(self.check(found=[0]*3, had_results=False))
        self.assertIsNone(self.check(found=[None]*3))
        self.assertIsNone(health.collector_checks([target(found=[0]*3)], NOW, empty_runs=0)['collector:kavak'])

    def test_recovery_requires_a_successful_completed_run(self):
        for status in ('running', 'failed'):
            checks = health.collector_checks([target(latest_status=status, statuses=['failed','ok','ok'])], NOW,
                                             previous={'collector:kavak':'falló'})
            self.assertIn('confirmar', checks['collector:kavak'])
        self.assertIsNone(health.collector_checks([target()], NOW,
                         previous={'collector:kavak':'falló'})['collector:kavak'])

    def test_custom_threshold(self):
        self.assertIn('2 corridas', health.collector_checks([target(statuses=['failed']*2)], NOW, failures=2)['collector:kavak'])

    def test_errors_are_sanitized(self):
        text = health.safe_error('Traceback\nError: https://user:password@example.test/path?token=secret api_key=hidden')
        self.assertNotIn('password', text)
        self.assertNotIn('secret', text)
        self.assertNotIn('hidden', text)
        self.assertIn('https://example.test/path', text)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'state.json'
        self.sent = []
        for name, value in [('PLATFORM_HEALTH_EMAIL','owner@example.test'), ('RESEND_API_KEY','re_test'), ('EMAIL_FROM','sender@example.test')]:
            patched = patch.object(health.config, name, value)
            patched.start()
            self.addCleanup(patched.stop)

    def sender(self, pending):
        self.sent.append(pending)
        return f'email-{len(self.sent)}'

    def test_only_transition_emails_and_recovery(self):
        up = {'base':None,'worker':None,'collector:kavak':None}
        down = {**up,'collector:kavak':'tres fallas'}
        health.notify_changes(up,self.path,self.sender)
        self.assertEqual(self.sent,[])
        health.notify_changes(down,self.path,self.sender)
        health.notify_changes(down,self.path,self.sender)
        health.notify_changes({**down,'collector:kavak':'cuatro fallas'},self.path,self.sender)
        self.assertEqual(len(self.sent),1)
        health.notify_changes(up,self.path,self.sender)
        self.assertEqual(len(self.sent),2)
        self.assertIn('recuperado',self.sent[-1]['email']['subject'])

    def test_timeout_retries_same_key_and_exact_email(self):
        down={'base':None,'collector:kavak':'falló'}
        def timeout(pending):
            self.sent.append(pending)
            raise RuntimeError('timeout')
        with self.assertRaisesRegex(RuntimeError,'timeout'):
            health.notify_changes(down,self.path,timeout)
        pending=json.loads(self.path.read_text(encoding='utf-8'))['pending']
        health.notify_changes(down,self.path,self.sender)
        self.assertEqual(self.sent[0]['key'],self.sent[1]['key'])
        self.assertEqual(pending['email'],self.sent[1]['email'])
        self.assertNotIn('pending',json.loads(self.path.read_text(encoding='utf-8')))

    def test_recovery_during_send_failure_is_delivered_after_pending_alert(self):
        down={'collector:kavak':'falló'}
        with self.assertRaises(RuntimeError):
            health.notify_changes(down,self.path,lambda _: (_ for _ in ()).throw(RuntimeError('offline')))
        health.notify_changes({'collector:kavak':None},self.path,self.sender)
        self.assertEqual(len(self.sent),2)
        self.assertIn('falla',self.sent[0]['email']['subject'])
        self.assertIn('recuperado',self.sent[1]['email']['subject'])

    def test_unknown_db_does_not_recover_collectors_or_worker(self):
        down={'base':None,'worker':'no late','collector:kavak':'falló'}
        health.notify_changes(down,self.path,self.sender)
        health.notify_changes({'base':'no conecta','web':None},self.path,self.sender)
        self.assertNotIn('volvió a funcionar',self.sent[-1]['email']['text'])
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['checks']['collector:kavak'],'falló')

    def test_disabled_collector_is_removed_silently(self):
        health.notify_changes({'collector:kavak':'falló'},self.path,self.sender)
        health.notify_changes({},self.path,self.sender)
        self.assertEqual(len(self.sent),1)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['checks'],{})

    def test_corrupt_state_does_not_send_duplicates(self):
        self.path.write_text('broken')
        with self.assertRaises(ValueError):
            health.notify_changes({'base':'failed'},self.path,self.sender)
        self.assertEqual(self.sent,[])

    def test_resend_payload_and_failure_preserve_safe_errors(self):
        pending={'key':'health-key','email':{'from':'sender@example.test','to':['owner@example.test'],'subject':'Falla','text':'test'}}
        with patch.object(health.config,'PLATFORM_HEALTH_EMAIL','owner@example.test'), patch.object(health.config,'RESEND_API_KEY','re_test'), patch.object(health.config,'EMAIL_FROM','sender@example.test'), patch.object(health.httpx,'post',return_value=httpx.Response(200,json={'id':'provider-id'})) as post:
            self.assertEqual(health.send_email(pending),'provider-id')
            self.assertEqual(post.call_args.kwargs['json'],pending['email'])
            self.assertEqual(post.call_args.kwargs['headers']['Idempotency-Key'],'health-key')
            post.return_value=httpx.Response(401,text='secret credential data')
            with self.assertRaisesRegex(RuntimeError,'HTTP 401') as raised:
                health.send_email(pending)
            self.assertNotIn('secret',str(raised.exception))

    def test_missing_configuration_does_not_persist_an_unusable_email(self):
        with patch.object(health.config, 'PLATFORM_HEALTH_EMAIL', ''):
            with self.assertRaisesRegex(RuntimeError, 'faltan'):
                health.notify_changes({'base':'failed'},self.path,self.sender)
        self.assertFalse(self.path.exists())
        health.notify_changes({'base':'failed'},self.path,self.sender)
        self.assertEqual(self.sent[0]['email']['to'], ['owner@example.test'])

    def test_concurrent_checks_are_locked(self):
        with health.exclusive_check(self.path):
            with self.assertRaises(OSError):
                with health.exclusive_check(self.path):
                    self.fail('second check acquired the lock')
