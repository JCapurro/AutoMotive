"""Platform and collector health, run by the existing five-minute watchdog.

python -m tools.platform_health [--dry] [--json]
Email only on failure/recovery transitions; failed sends retry the same payload.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from aio import run
from collectors._recency import POLICY_VERSION, SOURCES as RECENT_SOURCES
import config
import db
from notifications.ops import last_error_line
from pipeline.heartbeat import last_beat
from tools.watchdog import check_web, transitions, worker_problem

STATE_FILE = config.ROOT / "logs" / "platform_health_state.json"

COLLECTORS_SQL = """
with eligible as (
  select t.*, s.name, s.crawl_interval_seconds
  from crawl_targets t join sources s on s.id=t.source
  where t.active and s.enabled and exists (
    select 1 from search_profiles sp where public.search_access_active(sp.id)
      and lower(sp.filters->>'make') is not distinct from lower(t.make)
      and lower(sp.filters->>'model') is not distinct from lower(t.model)
      and (not sp.filters ? 'sources' or sp.filters->'sources' ? t.source)
  )
)
select t.id, t.source, t.name, t.make, t.model, t.query, t.created_at, t.updated_at, t.next_run_at,
  t.crawl_interval_seconds, latest.started_at, latest.status as latest_status,
  latest.error as latest_error, coalesce(history.statuses, '{}') as statuses,
  coalesce(history.found, '{}') as found,
  exists(select 1 from collector_runs r where r.target_id=t.id and r.status='ok'
    and r.found>0 and r.started_at>now()-interval '7 days') as had_results
from eligible t
left join lateral (
  select started_at, status, error from collector_runs where target_id=t.id
  order by started_at desc, id desc limit 1
) latest on true
left join lateral (
  select array_agg(status::text order by started_at desc, id desc) as statuses,
    array_agg(found order by started_at desc, id desc) as found
  from (select id, status, found, started_at from collector_runs
    where target_id=t.id and status in ('ok','failed')
    order by started_at desc, id desc limit %(history)s) recent
) history on true
order by t.source, t.id
"""


def safe_error(error: str | None) -> str:
    text = last_error_line(error) or "sin detalle de error"
    for secret in (config.RESEND_API_KEY, config.DATABASE_URL, config.TELEGRAM_TOKEN):
        if secret:
            text = text.replace(secret, "[redactado]")
    def clean_url(match):
        try:
            url = urlsplit(match[0])
            return f"{url.scheme}://{url.hostname}{url.path}"
        except ValueError:
            return "[URL redactada]"
    text = re.sub(r"[a-z]+://\S+", clean_url, text, flags=re.I)
    return re.sub(r"(?i)(token|api[_-]?key|password|authorization|cookie)\s*[:=]\s*[^,;]+",
                  r"\1=[redactado]", text)


def collector_checks(rows: list[dict], now: datetime, *, failures: int = 3,
                     timeout_minutes: int = 30, empty_runs: int = 3,
                     previous: dict[str, str | None] | None = None) -> dict[str, str | None]:
    checks: dict[str, str | None] = {}
    for row in rows:
        key = f"collector:{row['source']}"
        checks.setdefault(key, None)
        statuses = row['statuses']
        target = " ".join(p for p in (row.get('make'), row.get('model')) if p) or f"target {row['id']}"
        reason = None
        if len(statuses) >= failures and all(s == 'failed' for s in statuses[:failures]):
            reason = f"{failures} corridas fallidas consecutivas. {safe_error(row['latest_error'])}"
        elif row['latest_status'] == 'running':
            if now - row['started_at'] > timedelta(minutes=timeout_minutes):
                reason = f"corrida trabada por más de {timeout_minutes} minutos"
        # With a publication window, an empty successful scan means no recent
        # listings qualified. It is not evidence that the inventory parser broke.
        # Failed/incomplete scans, stalled runs and missed cadence still alert.
        elif (empty_runs > 0
              and not (row['source'] in RECENT_SOURCES
                       and (row.get('query') or {}).get('publication_policy') == POLICY_VERSION)
              and row['had_results'] and len(statuses) >= empty_runs
              and all(s == 'ok' for s in statuses[:empty_runs])
              and all(n == 0 for n in row['found'][:empty_runs])):
            reason = f"{empty_runs} corridas sin avisos después de obtener resultados; posible rotura del parser"
        else:
            due = max(row['next_run_at'] or row['created_at'], row.get('updated_at', row['created_at']))
            grace = timedelta(seconds=max(timeout_minutes * 60, row['crawl_interval_seconds'] * 2))
            if now - due > grace:
                reason = "búsqueda vencida que dejó de ejecutarse"
        if not reason and (previous or {}).get(key) and row['latest_status'] != 'ok':
            reason = "esperando una corrida exitosa para confirmar la recuperación"
        if reason:
            detail = f"{row['name']} · {target}: {reason}"
            checks[key] = f"{checks[key]}\n{detail}" if checks[key] else detail
    return checks


async def inspect_database(previous: dict[str, str | None] | None = None) -> dict[str, str | None]:
    try:
        await db.open_pool(max_size=1)
        async with db.connection() as cx:
            threshold_row = await (await cx.execute(
                "SELECT value FROM app_config WHERE key='collector_failure_alert_after'")).fetchone()
            threshold = max(1, min(100, int(threshold_row['value'] if threshold_row else 3)))
            rows = await (await cx.execute(COLLECTORS_SQL, {
                'history': max(threshold, config.PLATFORM_HEALTH_EMPTY_RUNS)})).fetchall()
        checks = collector_checks(rows, datetime.now(timezone.utc), failures=threshold,
                                  timeout_minutes=config.PLATFORM_HEALTH_RUN_TIMEOUT_MINUTES,
                                  empty_runs=config.PLATFORM_HEALTH_EMPTY_RUNS, previous=previous)
        checks.update(base=None, worker=worker_problem(await last_beat(), timedelta(minutes=config.WATCHDOG_STALE_MINUTES)))
        return checks
    except Exception as error:
        # A failed query is unknown health, never a collector/worker recovery.
        return {'base': f"no se pudo comprobar la base o los collectors: {type(error).__name__}"}
    finally:
        await db.close_pool()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {'checks': {}}
    state = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(state.get('checks'), dict):
        raise ValueError("estado de health inválido")
    return state


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def send_email(pending: dict) -> str:
    if not (config.PLATFORM_HEALTH_EMAIL and config.RESEND_API_KEY and config.EMAIL_FROM):
        raise RuntimeError('faltan PLATFORM_HEALTH_EMAIL / RESEND_API_KEY / EMAIL_FROM')
    try:
        response = httpx.post('https://api.resend.com/emails', timeout=20,
            headers={'Authorization': f'Bearer {config.RESEND_API_KEY}',
                     'Idempotency-Key': pending['key']}, json=pending['email'])
    except httpx.HTTPError as error:
        raise RuntimeError(f'no se pudo enviar el aviso: {type(error).__name__}') from None
    if not response.is_success:
        raise RuntimeError(f'Resend respondió HTTP {response.status_code}')
    return response.json()['id']


def notify_changes(current: dict[str, str | None], path: Path = STATE_FILE,
                   sender=send_email) -> list[str]:
    state = load_state(path)
    sent = []
    # Keep the exact email/recipient/key across a timeout and subsequent retries.
    if pending := state.get('pending'):
        sent.append(sender(pending))
        state = {'checks': pending['checks'], 'last_email_id': sent[-1], 'last_email_at': datetime.now(timezone.utc).isoformat()}
        save_state(path, state)
    previous = state['checks']
    if current.get('base'):
        current = {**{k: v for k, v in previous.items() if k != 'base' and k != 'web'}, **current}
    messages = transitions(previous, current)
    if messages:
        if not (config.PLATFORM_HEALTH_EMAIL and config.RESEND_API_KEY and config.EMAIL_FROM):
            raise RuntimeError('faltan PLATFORM_HEALTH_EMAIL / RESEND_API_KEY / EMAIL_FROM')
        stamp = datetime.now(timezone(timedelta(hours=-3))).strftime('%d/%m/%Y %H:%M ART')
        failing = any(message.startswith('🔴') for message in messages)
        subject = 'Ese Auto: falla en la plataforma de scraping' if failing else 'Ese Auto: scraping recuperado'
        text = f"Chequeo de salud · {stamp}\n\n" + '\n'.join(messages)
        if config.WEB_BASE_URL:
            text += f"\n\nRevisar fuentes: {config.WEB_BASE_URL}/app/health"
        pending = {'key': f'platform-health-{uuid4()}', 'checks': current,
                   'email': {'from': config.EMAIL_FROM, 'to': [config.PLATFORM_HEALTH_EMAIL],
                             'subject': subject, 'text': text}}
        state['pending'] = pending
        save_state(path, state)
        sent.append(sender(pending))
        state = {'checks': current, 'last_email_id': sent[-1], 'last_email_at': datetime.now(timezone.utc).isoformat()}
    else:
        state['checks'] = current
    save_state(path, state)
    return sent


async def publish_snapshot(checks: dict[str, str | None]) -> None:
    if checks.get('base'):
        return  # The page will show that the previous snapshot is stale.
    state = load_state(STATE_FILE)
    from psycopg.types.json import Jsonb
    try:
        await db.open_pool(max_size=1)
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO platform_health_checks(id, checked_at, checks, email_pending, last_email_at) "
                "VALUES (1,now(),%s,%s,%s) ON CONFLICT(id) DO UPDATE SET "
                "checked_at=excluded.checked_at,checks=excluded.checks,email_pending=excluded.email_pending,"
                "last_email_at=excluded.last_email_at",
                (Jsonb(checks), bool(state.get('pending')) or not (config.PLATFORM_HEALTH_EMAIL and config.RESEND_API_KEY and config.EMAIL_FROM), state.get('last_email_at')))
    finally:
        await db.close_pool()


@contextmanager
def exclusive_check(path: Path):
    """OS lock releases on process exit, including an interrupted/crashed check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        if sys.platform == 'win32':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if sys.platform == 'win32':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


def main() -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry', action='store_true', help='mostrar sin enviar ni guardar estado')
    parser.add_argument('--json', action='store_true', help='mostrar checks como JSON')
    args = parser.parse_args()
    try:
        with exclusive_check(STATE_FILE):
            state = load_state(STATE_FILE)
            previous = (state.get('pending') or {}).get('checks', state['checks'])
            checks = run(inspect_database(previous))
            checks['web'] = check_web(config.WEB_BASE_URL)
            if args.json:
                print(json.dumps(checks, ensure_ascii=False))
            else:
                for name, problem in checks.items():
                    print(f"{name:24} {problem or 'OK'}")
            if not args.dry:
                try:
                    for provider_id in notify_changes(checks):
                        print(f'Email enviado: {provider_id}')
                finally:
                    run(publish_snapshot(checks))
            return 1 if any(checks.values()) else 0
    except (BlockingIOError, PermissionError):
        print('Otro chequeo está en curso o no se pudo abrir su estado.', file=sys.stderr)
        return 2
    except Exception as error:
        print(f'Health falló: {type(error).__name__}: {safe_error(str(error))}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
