import logging

import pytest

from repairbot import notify
from tools import platform_health

INCIDENT = 'a183b3b6-ae12-4bf1-add2-c2569ad64fa2'


@pytest.fixture
def mail(monkeypatch):
    """A configured mailbox and a recording sender; the real Resend call is never reachable."""
    for key in ('RESEND_API_KEY', 'EMAIL_FROM', 'PLATFORM_HEALTH_EMAIL', 'WEB_BASE_URL'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(platform_health.config, 'EMAIL_FROM', 'Ese Auto <avisos@example.test>')
    monkeypatch.setattr(platform_health.config, 'PLATFORM_HEALTH_EMAIL', 'owner@example.test')
    monkeypatch.setattr(platform_health.config, 'RESEND_API_KEY', 'test-key')

    def unreachable(pending):
        raise AssertionError('el envío real no se usa en las pruebas')
    monkeypatch.setattr(platform_health, 'send_email', unreachable)
    sent = []

    def sender(pending):
        sent.append(pending)
        return 'provider-1'
    sender.sent = sent
    return sender


def send(sender, **changes):
    values = dict(incident_id=INCIDENT, source='kavak', kind='fixed', subject='Ese Auto: Kavak reparado',
                  text='Causa: cambió el selector.\nCommit abc123 desplegado.', n=2, sender=sender)
    return notify.send(None, **{**values, **changes})


def test_payload_has_the_platform_health_shape_and_the_idempotency_key(mail):
    assert send(mail) is True
    assert mail.sent == [{
        'key': f'repairbot-{INCIDENT}-fixed-2',
        'email': {'from': 'Ese Auto <avisos@example.test>', 'to': ['owner@example.test'],
                  'subject': 'Ese Auto: Kavak reparado',
                  'text': 'Causa: cambió el selector.\nCommit abc123 desplegado.'}}]


def test_key_identifies_incident_kind_and_attempt(mail):
    for kind in notify.KINDS:
        assert send(mail, kind=kind, n=0)
    keys = [pending['key'] for pending in mail.sent]
    assert keys == [f'repairbot-{INCIDENT}-{kind}-0' for kind in notify.KINDS]
    assert notify.idempotency_key('a/b c\r\nX-Evil: 1', 'fixed', 3) == 'repairbot-abcX-Evil1-fixed-3'
    assert send(mail, n=1) and mail.sent[-1]['key'].endswith('-fixed-1')


def test_default_sender_is_the_platform_health_one(mail, monkeypatch):
    calls = []
    monkeypatch.setattr(platform_health, 'send_email', lambda pending: calls.append(pending) or 'id')
    assert send(None) is True
    assert calls[0]['key'] == f'repairbot-{INCIDENT}-fixed-2'


def test_text_and_subject_are_sanitized_but_keep_their_first_lines(mail, monkeypatch):
    monkeypatch.setattr(platform_health.config, 'DATABASE_URL', 'postgresql://bot:hunter2@db.internal/app')
    text = ('Me rendí después de 3 intentos.\n\n'
            'Intento 1: falló postgresql://bot:hunter2@db.internal/app\n'
            'Intento 2: GET https://user:pwd@example.test/path?token=abc123 devolvió 403\n'
            'Authorization: Bearer hidden-value\n' + 'detalle largo\n' * 400 + 'Último renglón.')
    assert send(mail, kind='gave_up', subject='Ese Auto:\r\nBcc: x@evil.test  me rendí', text=text)
    email = mail.sent[0]['email']
    for secret in ('hunter2', 'pwd', 'abc123', 'hidden-value'):
        assert secret not in email['text']
    assert email['text'].startswith('Me rendí después de 3 intentos.\n\nIntento 1: falló')
    assert 'example.test/path' in email['text']
    assert 'Último renglón.' in email['text']
    assert len(email['text']) <= notify.MAX_TEXT
    assert '\n' not in email['subject'] and '\r' not in email['subject']
    assert email['subject'].startswith('Ese Auto: Bcc')


def test_long_text_is_capped_from_the_end(mail):
    assert send(mail, text='primera línea\n' + 'x' * 50 + '\n' + 'relleno\n' * 5000)
    text = mail.sent[0]['email']['text']
    assert len(text) == notify.MAX_TEXT and text.startswith('primera línea\n')


def test_sender_failure_is_logged_and_never_raises(mail, caplog):
    def failing(pending):
        raise RuntimeError('Resend respondió HTTP 500')
    with caplog.at_level(logging.WARNING, logger='repairbot.notify'):
        assert send(failing) is False
    assert 'no enviado' in caplog.text and 'HTTP 500' in caplog.text

    def crashing(pending):
        raise KeyError('id')
    assert send(crashing) is False


def test_repeated_key_with_another_body_counts_as_already_sent(mail):
    def conflict(pending):
        raise RuntimeError('Resend respondió HTTP 409')
    assert send(conflict) is True


def test_unknown_kind_and_bad_arguments_do_not_send(mail):
    assert send(mail, kind='spam') is False
    assert send(mail, n='dos') is False
    assert mail.sent == []


def test_missing_mail_configuration_returns_false(mail, monkeypatch):
    monkeypatch.setattr(platform_health.config, 'PLATFORM_HEALTH_EMAIL', '')
    assert send(mail) is False
    assert mail.sent == []


def test_environment_loaded_after_config_was_imported_is_used(mail, monkeypatch):
    for key in ('RESEND_API_KEY', 'EMAIL_FROM', 'PLATFORM_HEALTH_EMAIL'):
        monkeypatch.setattr(platform_health.config, key, '')
    monkeypatch.setenv('RESEND_API_KEY', ' late-key ')
    monkeypatch.setenv('EMAIL_FROM', 'Bot <bot@example.test>')
    monkeypatch.setenv('PLATFORM_HEALTH_EMAIL', 'late@example.test')
    assert send(mail) is True
    assert mail.sent[0]['email']['from'] == 'Bot <bot@example.test>'
    assert mail.sent[0]['email']['to'] == ['late@example.test']
    assert platform_health.config.RESEND_API_KEY == 'late-key'   # what send_email authenticates with


def test_empty_subject_falls_back_to_the_source(mail):
    assert send(mail, subject='  ')
    assert mail.sent[0]['email']['subject'] == 'Bot de reparación: kavak'
