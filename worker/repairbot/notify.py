"""Emails from the bot to the owner, through the platform-health Resend sender.

One email per (incident, kind, n): the idempotency key makes a retried tick harmless.
A mail failure never stops a repair; it is logged and reported as False.
"""
from __future__ import annotations

import logging
import os
import re

KINDS = ('fixed', 'needs_input', 'gave_up', 'rollback', 'deploy_blocked', 'bot_error', 'unverified')
MAX_TEXT = 12000
_EMAIL_ENV = ('RESEND_API_KEY', 'EMAIL_FROM', 'PLATFORM_HEALTH_EMAIL')

log = logging.getLogger(__name__)


def clean(text: str | None, limit: int = MAX_TEXT) -> str:
    """safe_text line by line: it keeps only the end of what it gets, and an email needs its first lines."""
    from tools.collector_repairs import safe_text

    lines = [safe_text(line) for line in str(text or '').strip().splitlines()]
    return '\n'.join(lines)[:limit]


def idempotency_key(incident_id, kind: str, n: int = 0) -> str:
    incident = re.sub(r'[^A-Za-z0-9_-]', '', str(incident_id))[:64]
    return f'repairbot-{incident}-{kind}-{int(n)}'


def _sync_config(config) -> None:
    # config reads the environment when it is imported; settings.load_env may run later.
    for key in _EMAIL_ENV:
        value = os.environ.get(key, '').strip()
        if value:
            setattr(config, key, value)


def send(settings, *, incident_id: str, source: str, kind: str, subject: str, text: str,
         n: int = 0, sender=None) -> bool:
    try:
        if kind not in KINDS:
            raise ValueError(f'tipo de aviso desconocido: {kind!r}')
        from tools import platform_health

        config = platform_health.config
        _sync_config(config)
        if not (config.EMAIL_FROM and config.PLATFORM_HEALTH_EMAIL):
            raise RuntimeError('faltan PLATFORM_HEALTH_EMAIL / EMAIL_FROM')
        pending = {'key': idempotency_key(incident_id, kind, n),
                   'email': {'from': config.EMAIL_FROM, 'to': [config.PLATFORM_HEALTH_EMAIL],
                             'subject': ' '.join(clean(subject, 200).split()) or f'Bot de reparación: {source}',
                             'text': clean(text)}}
        provider_id = (sender or platform_health.send_email)(pending)
        log.info('aviso %s enviado (%s): %s', kind, pending['key'], provider_id)
        return True
    except Exception as error:
        return _failed(kind, source, error)


def _failed(kind: str, source: str, error: Exception) -> bool:
    # Resend answers 409 when the key was already used with another body: the owner
    # already has an email for this (incident, kind, n).
    if 'HTTP 409' in str(error):
        log.info('aviso %s de %s ya enviado (clave repetida)', kind, source)
        return True
    try:
        detail = clean(str(error), 300)
    except Exception:
        detail = ''
    log.warning('aviso %s de %s no enviado: %s: %s', kind, source, type(error).__name__, detail)
    return False
