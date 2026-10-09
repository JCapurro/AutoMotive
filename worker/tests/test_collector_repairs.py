from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from tools import collector_repairs as repairs


class RepairContextTests(unittest.TestCase):
    def context(self, **changes):
        incident = dict(id=uuid4(), source='autocosmos', problem='tres fallos',
                        status='dispatching', health_checked_at=datetime.now(timezone.utc))
        return repairs.build_dispatch(incident, {'checks': {'collector:autocosmos': 'falló'}},
            [dict(id=1, make='Ford', model='Fiesta', query={
                'year_min': 2014, 'profile_ids': ['private-user'], 'origin_lat': -34.5,
                'password': 'private-value'})],
            [dict(id=40, target_id=1, status='failed', error='HTTP 503', found=None)], **changes)

    def test_prompt_contains_incident_and_target_evidence(self):
        result = self.context()
        self.assertIn('Ford', result['prompt'])
        self.assertIn('Fiesta', result['prompt'])
        self.assertIn('HTTP 503', result['prompt'])
        self.assertIn('2014', result['prompt'])
        self.assertIn(str(result['incident']['id']), result['title'])
        self.assertIn('worker/collectors/autocosmos.py', result['prompt'])
        self.assertIn('corrida exitosa', result['prompt'])
        self.assertIn('datos no confiables', result['prompt'])

    def test_context_does_not_copy_private_profile_or_location(self):
        text = json.dumps(self.context(), default=str)
        for private in ('private-user', 'profile_ids', 'origin_lat', '-34.5', 'private-value'):
            self.assertNotIn(private, text)

    def test_secrets_urls_and_authorization_are_redacted(self):
        with patch.object(repairs.config, 'DATABASE_URL', 'postgresql://private-dsn'):
            text = repairs.safe_text('Traceback\nError postgresql://private-dsn '
                'https://user:pwd@example.test/path?token=secret '
                'Authorization: Bearer hidden')
        for secret in ('private-dsn', 'pwd', 'token=secret', 'hidden'):
            self.assertNotIn(secret, text)
        self.assertIn('example.test/path', text)

    def test_shared_instagram_collector_is_identified(self):
        incident = dict(id=uuid4(), source='sc_clasificados', problem='login wall', status='open')
        result = repairs.build_dispatch(incident, {}, [], [])
        self.assertIn('worker/collectors/instagram.py', result['prompt'])
        self.assertIn('Only Cars', result['prompt'])
        self.assertIn('captcha', result['prompt'])

    def test_entire_cookie_header_is_removed(self):
        text = repairs.safe_text('Cookie: sessionid=example_session; other_session=example_other')
        self.assertNotIn('example_session', text)
        self.assertNotIn('example_other', text)

    def test_quoted_headers_and_storage_state_are_removed(self):
        examples = [
            'headers={"Authorization": "Bearer example_bearer", "Cookie": "sessionid=example_cookie"}',
            "{'cookies': [{'name': 'sessionid', 'value': 'example_cookie'}]}",
            '{"session": {"value": "example_session"}}',
        ]
        for value in examples:
            text = repairs.safe_text(value)
            for secret in ('example_bearer', 'example_cookie', 'example_session'):
                self.assertNotIn(secret, text)

    def test_context_is_bounded(self):
        self.assertLessEqual(len(repairs.safe_text('x' * 10000)), 2000)

    def test_long_trace_keeps_the_final_exception(self):
        text = repairs.safe_text('stack frame\n' * 500 + 'RuntimeError: HTTP 503')
        self.assertIn('RuntimeError: HTTP 503', text)

    def test_json_handles_timestamps_and_uuid(self):
        encoded = repairs.json_text(self.context())
        self.assertIsInstance(json.loads(encoded)['incident']['id'], str)
