from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx

from tools import platform_health as health
from collectors._recency import POLICY_VERSION

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

    def test_recent_publication_windows_can_legitimately_be_empty(self):
        for source in ('mercadolibre', 'facebook'):
            row = target(source=source, query={'publication_policy': POLICY_VERSION}, found=[0]*3)
            self.assertIsNone(health.collector_checks([row], NOW)[f'collector:{source}'])
            row['query'] = {}
            self.assertIn('posible rotura', health.collector_checks([row], NOW)[f'collector:{source}'])

    def test_publication_window_still_alerts_failures_stalls_and_missed_cadence(self):
        for changes in (
            dict(statuses=['failed']*3, latest_status='failed'),
            dict(latest_status='running', started_at=NOW-timedelta(hours=1)),
            dict(found=[0]*3, next_run_at=NOW-timedelta(hours=2)),
        ):
            row = target(source='mercadolibre', query={'publication_policy': POLICY_VERSION}, **changes)
            self.assertIsNotNone(health.collector_checks([row], NOW)['collector:mercadolibre'])

    def test_recovery_requires_a_successful_completed_run(self):
        for status in ('running', 'failed'):
            checks = health.collector_checks([target(latest_status=status, statuses=['failed','ok','ok'])], NOW,
                                             previous={'collector:kavak':'falló'})
            self.assertIn('confirmar', checks['collector:kavak'])
        self.assertIsNone(health.collector_checks([target()], NOW,
                         previous={'collector:kavak':'falló'})['collector:kavak'])

    def test_publication_windows_allow_successful_empty_scans(self):
        for source in ('facebook', 'mercadolibre'):
            with self.subTest(source=source):
                row = target(source=source, query={'publication_policy': health.POLICY_VERSION}, found=[0]*3)
                checks = health.collector_checks([row], NOW,
                    previous={f'collector:{source}': 'empty scans'})
                self.assertIsNone(checks[f'collector:{source}'])

    def test_legacy_recent_sources_still_detect_empty_inventory(self):
        for source in ('facebook', 'mercadolibre'):
            with self.subTest(source=source):
                row = target(source=source, query={}, found=[0]*3)
                self.assertIn('posible rotura', health.collector_checks([row], NOW)[f'collector:{source}'])

    def test_publication_windows_keep_real_health_failures(self):
        for source in ('facebook', 'mercadolibre'):
            for changes, reason in (
                ({'latest_status': 'failed', 'statuses': ['failed']*3}, 'corridas fallidas'),
                ({'latest_status': 'running', 'started_at': NOW-timedelta(hours=1)}, 'trabada'),
                ({'next_run_at': NOW-timedelta(hours=2)}, 'vencida'),
            ):
                with self.subTest(source=source, reason=reason):
                    row = target(source=source, query={'publication_policy': health.POLICY_VERSION}, **changes)
                    self.assertIn(reason, health.collector_checks([row], NOW)[f'collector:{source}'])

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

    def test_quota_emails_have_their_own_subject_and_recovery(self):
        up = {'base': None, 'collector:kavak': None, 'resend:hoy': None}
        health.notify_changes(up, self.path, self.sender)
        health.notify_changes({**up, 'resend:hoy': '85 de 100 emails de hoy'}, self.path, self.sender)
        self.assertEqual(self.sent[-1]['email']['subject'], 'Ese Auto: aviso de la cuota de emails (Resend)')
        self.assertIn('resend:hoy: 85 de 100 emails de hoy', self.sent[-1]['email']['text'])
        health.notify_changes(up, self.path, self.sender)
        self.assertEqual(self.sent[-1]['email']['subject'], 'Ese Auto: la cuota de emails (Resend) volvió a la normalidad')
        self.assertIn('resend:hoy: el uso del día ya no está cerca del límite', self.sent[-1]['email']['text'])

    def test_an_unreadable_key_alerts_once_and_its_fix_is_announced(self):
        restricted = httpx.Response(401, json={'name': 'restricted_api_key'})
        def offline():
            raise httpx.ConnectTimeout('timeout')
        def run(get):
            previous = health.load_state(self.path)['checks']
            health.notify_changes({'base': None, **health.email_quota(previous, get)}, self.path, self.sender)
        with patch.object(health.config, 'PLATFORM_HEALTH_EMAIL_QUOTA_PCT', 80):
            for get in (lambda: httpx.Response(200, json=usage()), lambda: restricted, offline, lambda: restricted):
                run(get)
            self.assertEqual(len(self.sent), 1)
            self.assertIn('resend:uso: no se puede leer', self.sent[0]['email']['text'])
            run(lambda: httpx.Response(200, json=usage()))
            self.assertEqual(len(self.sent), 2)
            self.assertIn('resend:uso: ya se puede leer el uso de Resend', self.sent[1]['email']['text'])
            run(lambda: httpx.Response(200, json=usage()))
        self.assertEqual(len(self.sent), 2)
        self.assertNotIn('resend:uso', health.load_state(self.path)['checks'])

    def test_a_recovered_window_does_not_announce_normal_while_the_other_warns(self):
        health.notify_changes({'resend:hoy': '85 de 100', 'resend:mes': '2.500 de 3.000'}, self.path, self.sender)
        health.notify_changes({'resend:hoy': None, 'resend:mes': '2.500 de 3.000'}, self.path, self.sender)
        self.assertEqual(self.sent[-1]['email']['subject'], 'Ese Auto: novedades de la cuota de emails (Resend)')

    def test_a_quota_warning_with_a_scraping_recovery_is_about_the_quota(self):
        health.notify_changes({'collector:kavak': 'falló', 'resend:hoy': None}, self.path, self.sender)
        health.notify_changes({'collector:kavak': None, 'resend:hoy': '85 de 100'}, self.path, self.sender)
        self.assertEqual(self.sent[-1]['email']['subject'], 'Ese Auto: aviso de la cuota de emails (Resend)')
        self.assertIn('collector:kavak: volvió a funcionar', self.sent[-1]['email']['text'])

    def test_a_collector_failure_alongside_keeps_the_scraping_subject(self):
        health.notify_changes({'collector:kavak': None, 'resend:hoy': None}, self.path, self.sender)
        health.notify_changes({'collector:kavak': 'falló', 'resend:hoy': '85 de 100'}, self.path, self.sender)
        self.assertIn('falla en la plataforma', self.sent[-1]['email']['subject'])


def usage(daily=2, monthly=159, *, daily_limit=100, monthly_limit=3000):
    """GET /usage as Resend answered it on 2026-10-16 (the parts we read)."""
    return {'object': 'usage', 'emails': {
        'daily': {'used': daily, 'limit': daily_limit, 'sent': daily, 'received': 0, 'resets_at': '2026-10-16T23:59:59.999Z'},
        'monthly': {'used': monthly, 'limit': monthly_limit, 'sent': monthly, 'received': 0, 'resets_at': '2026-11-04T14:33:32.454Z'}}}


class EmailQuotaTests(unittest.TestCase):
    def setUp(self):
        for name, value in [('RESEND_API_KEY', 're_test'), ('PLATFORM_HEALTH_EMAIL_QUOTA_PCT', 80)]:
            patched = patch.object(health.config, name, value)
            patched.start()
            self.addCleanup(patched.stop)

    def check(self, body=None, previous=None, status=200, now=datetime(2026, 10, 16, 15, tzinfo=timezone.utc)):
        response = httpx.Response(status, json=usage() if body is None else body)
        return health.email_quota(previous or {}, lambda: response, now)

    def test_quiet_below_the_threshold(self):
        self.assertEqual(self.check(usage(79, 2399)), {'resend:hoy': None, 'resend:mes': None})

    def test_daily_warning_says_how_many_and_when_it_renews(self):
        problem = self.check(usage(85))['resend:hoy']
        self.assertIn('85 de 100 emails de hoy (85%)', problem)
        self.assertIn('hoy a las 21:00 (hora argentina)', problem)
        self.assertIn('links para entrar', problem)

    def test_after_21_the_daily_renewal_carries_its_date(self):
        body = usage(85)
        body['emails']['daily']['resets_at'] = '2026-10-17T23:59:59.999Z'
        problem = self.check(body, now=datetime(2026, 10, 17, 1, 30, tzinfo=timezone.utc))['resend:hoy']
        self.assertIn('el 17/10 a las 21:00 (hora argentina)', problem)

    def test_monthly_warning_uses_thousands_and_the_renewal_day(self):
        checks = self.check(usage(10, 2450))
        self.assertIsNone(checks['resend:hoy'])
        self.assertIn('2.450 de 3.000 emails del mes (81%)', checks['resend:mes'])
        self.assertIn('el 04/11', checks['resend:mes'])
        self.assertIn('plan pago', checks['resend:mes'])

    def test_exhausted_quota_says_emails_bounce(self):
        problem = self.check(usage(100))['resend:hoy']
        self.assertIn('se agotaron los 100 emails de hoy', problem)
        self.assertIn('rechaza', problem)

    def test_threshold_is_configurable_and_zero_turns_it_off(self):
        with patch.object(health.config, 'PLATFORM_HEALTH_EMAIL_QUOTA_PCT', 50):
            self.assertIsNotNone(self.check(usage(50))['resend:hoy'])
        with patch.object(health.config, 'PLATFORM_HEALTH_EMAIL_QUOTA_PCT', 0):
            self.assertEqual(self.check(usage(100, 3000)), {})

    def test_paid_plan_has_no_daily_limit(self):
        self.assertIsNone(self.check(usage(5000, 10, daily_limit=None, monthly_limit=50000))['resend:hoy'])

    def test_paid_plan_does_not_advise_a_paid_plan(self):
        for used in (40000, 50000):
            with self.subTest(used=used):
                problem = self.check(usage(10, used, daily_limit=None, monthly_limit=50000))['resend:mes']
                self.assertIn('50.000', problem)
                self.assertIn('Revisá en Resend', problem)
                self.assertNotIn('plan pago', problem)
                self.assertNotIn('rechaza', problem)

    def test_no_key_means_no_email_at_all_and_nothing_to_check(self):
        with patch.object(health.config, 'RESEND_API_KEY', ''):
            self.assertEqual(health.email_quota({}, lambda: self.fail('called Resend without a key')), {})

    def test_asks_resend_with_the_key(self):
        with patch.object(health.httpx, 'get', return_value=httpx.Response(200, json=usage())) as get:
            health.email_quota({})
        self.assertEqual(get.call_args.args[0], 'https://api.resend.com/usage')
        self.assertEqual(get.call_args.kwargs['headers']['Authorization'], 'Bearer re_test')

    def test_an_unanswered_check_keeps_the_previous_verdict(self):
        previous = {'resend:hoy': '85 de 100', 'resend:mes': None, 'collector:kavak': None}
        def offline():
            raise httpx.ConnectTimeout('timeout')
        self.assertEqual(health.email_quota(previous, offline), {'resend:hoy': '85 de 100', 'resend:mes': None})
        for status in (503, 429):
            with self.subTest(status=status):
                self.assertEqual(self.check({}, previous, status), {'resend:hoy': '85 de 100', 'resend:mes': None})
        self.assertEqual(self.check({}, {}, 503), {})
        self.assertEqual(self.check({}, {'resend:uso': 'key'}, 503), {'resend:uso': 'key'})

    def test_a_sending_only_key_is_reported_not_ignored(self):
        body = {'statusCode': 401, 'message': 'This API key is restricted to only send emails', 'name': 'restricted_api_key'}
        checks = self.check(body, {'resend:hoy': None}, 401)
        self.assertIn('solo tiene permiso de envío', checks['resend:uso'])
        self.assertIn('Full access', checks['resend:uso'])
        self.assertNotIn('resend:hoy', checks)  # unread: no OK row
        self.assertNotIn('re_test', checks['resend:uso'])

    def test_a_rejected_key_says_no_email_goes_out(self):
        for status, name in ((400, 'validation_error'), (403, 'suspended_api_key'), (401, 'validation_error')):
            with self.subTest(status=status, name=name):
                problem = self.check({'statusCode': status, 'message': 'API key is invalid', 'name': name}, {}, status)['resend:uso']
                self.assertIn(f'Resend rechaza la API key (HTTP {status}, {name})', problem)
                self.assertIn('no sale ningún email', problem)
        self.assertNotIn('<b>', self.check({'name': '<b>x</b>'}, {}, 403)['resend:uso'])

    def test_an_unreadable_answer_is_reported_not_shown_as_ok(self):
        for body in ({'object': 'usage'}, {'emails': {'daily': {}}}, {'emails': []}):
            with self.subTest(body=body):
                self.assertIn('formato desconocido', self.check(body, {'resend:hoy': None})['resend:uso'])
        self.assertIn('HTTP 404', self.check({'name': 'not_found'}, {}, 404)['resend:uso'])
        for daily, monthly in (({'used': 100, 'max': 100}, {'used': 3000, 'max': 3000}),
                               ({'used': 100, 'limit': '100'}, {'used': 3000, 'limit': 3000}),
                               ({'used': 1, 'limit': None}, {'used': 3000, 'limit': None}),
                               ({'used': 1, 'limit': 100}, {'used': 3000, 'limit': 0}),
                               ({'used': True, 'limit': 100}, {'used': 1, 'limit': 3000})):
            with self.subTest(daily=daily, monthly=monthly):
                self.assertIn('formato desconocido', self.check({'emails': {'daily': daily, 'monthly': monthly}})['resend:uso'])

    def test_while_unreadable_only_open_warnings_stay(self):
        checks = self.check({'name': 'restricted_api_key'}, {'resend:hoy': '85 de 100', 'resend:mes': None}, 401)
        self.assertEqual(set(checks), {'resend:hoy', 'resend:uso'})
        self.assertEqual(checks['resend:hoy'], '85 de 100')

    def test_renewal_rounds_resends_last_millisecond(self):
        self.assertEqual(health.renewal('2026-10-16T23:59:59.999Z'), datetime(2026, 10, 16, 21, 0, tzinfo=health.ART))
        self.assertIsNone(health.renewal(None))
        self.assertIsNone(health.renewal('2026-10-16T23:59:59'))
        self.assertIn('hasta que se renueve la cuota.', self.check({'emails': {
            'daily': {'used': 90, 'limit': 100}, 'monthly': {'used': 90, 'limit': 3000}}})['resend:hoy'])
