"""Platform and collector health, run by the existing five-minute watchdog.
Also warns before Resend's email quota runs out (resend:hoy / resend:mes).

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
from collectors.facebook import DATE_FETCH_LIMIT as FB_DATE_FETCH_LIMIT
from collectors.mercadolibre import DATE_FETCH_LIMIT
import config
import db
from db.repos.targets import INTERVAL_SECONDS, PROFILE_WANTS_TARGET
from normalization.body_type import LABELS as BODY_TYPE_LABELS
from notifications.ops import last_error_line
from pipeline.heartbeat import last_beat
from tools.watchdog import check_web, transitions, worker_problem

STATE_FILE = config.ROOT / "logs" / "platform_health_state.json"
ART = timezone(timedelta(hours=-3))
# How long a new Mercado Libre target may take to date its first 30 days.
FIRST_LOAD_GRACE = timedelta(days=1)

RESEND_USAGE_URL = 'https://api.resend.com/usage'
QUOTA_KEYS = {'daily': 'resend:hoy', 'monthly': 'resend:mes'}
QUOTA_BLIND = 'resend:uso'
QUOTA_RECOVERED = {'resend:hoy': 'el uso del día ya no está cerca del límite',
                   'resend:mes': 'el uso del mes ya no está cerca del límite',
                   'resend:uso': 'ya se puede leer el uso de Resend'}
UNREADABLE = ("Resend devolvió el uso en un formato desconocido: el aviso de cuota no funciona "
              "hasta adaptar tools/platform_health.py.")

# The targets the worker runs (db/repos/targets.py: the same profile predicate
# and cadence as due_targets).
COLLECTORS_SQL = f"""
with eligible as (
  select t.*, s.name, {INTERVAL_SECONDS} as crawl_interval_seconds
  from crawl_targets t join sources s on s.id=t.source
  where t.active and s.enabled and exists (
    select 1 from search_profiles sp where public.search_access_active(sp.id)
      and {PROFILE_WANTS_TARGET}
  )
)
select t.id, t.source, t.name, t.make, t.model, t.body_type, t.query, t.first_run_done, t.created_at, t.updated_at, t.next_run_at,
  t.crawl_interval_seconds, latest.started_at, latest.status as latest_status,
  latest.error as latest_error, coalesce(history.statuses, '{{}}') as statuses,
  coalesce(history.found, '{{}}') as found, history.errors[1] as last_error,
  exists(select 1 from collector_runs r where r.target_id=t.id and r.status='ok'
    and r.found>0 and r.started_at>now()-interval '7 days') as had_results
from eligible t
left join lateral (
  select started_at, status, error from collector_runs where target_id=t.id
  order by started_at desc, id desc limit 1
) latest on true
left join lateral (
  select array_agg(status::text order by started_at desc, id desc) as statuses,
    array_agg(found order by started_at desc, id desc) as found,
    array_agg(error order by started_at desc, id desc) as errors
  from (select id, status, found, error, started_at from collector_runs
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


def first_load(row: dict, now: datetime) -> bool:
    """A new Mercado Libre target dating its first 30 days, 200 ads per scan
    (config.RECENT_ML_MAX_DATE_FETCHES): each scan ends incomplete, so failed,
    while it stores what it read (target 445406, incident f9a58b7f). Facebook
    does the same 30 item pages at a time (config.RECENT_FB_MAX_DATE_FETCHES). Past
    FIRST_LOAD_GRACE it alerts like any failure. The last finished run
    decides: the next scan is often running."""
    return (row.get('first_run_done') is False and row['statuses'][:1] == ['failed']
            and last_error_line(row.get('last_error')) in (DATE_FETCH_LIMIT, FB_DATE_FETCH_LIMIT)
            and now - row['created_at'] < FIRST_LOAD_GRACE)


def collector_checks(rows: list[dict], now: datetime, *, failures: int = 3,
                     timeout_minutes: int = 30, empty_runs: int = 3,
                     previous: dict[str, str | None] | None = None) -> dict[str, str | None]:
    checks: dict[str, str | None] = {}
    # A parser break empties every search of the source. When another target
    # of the same source just read listings, an empty one is a narrow search
    # with nothing listed (v6 Gol Trend 2021, incident db7a233d), not a break.
    reading = {row['source'] for row in rows
               if row['statuses'][:1] == ['ok'] and (row['found'][:1] or [0])[0]}
    for row in rows:
        key = f"collector:{row['source']}"
        checks.setdefault(key, None)
        statuses = row['statuses']
        target = (BODY_TYPE_LABELS.get(row['body_type'], row['body_type']) if row.get('body_type') else
                  " ".join(p for p in (row.get('make'), row.get('model')) if p) or f"target {row['id']}")
        reason = None
        loading = first_load(row, now)
        if (not loading and len(statuses) >= failures
                and all(s == 'failed' for s in statuses[:failures])):
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
              and row['source'] not in reading
              and row['had_results'] and len(statuses) >= empty_runs
              and all(s == 'ok' for s in statuses[:empty_runs])
              and all(n == 0 for n in row['found'][:empty_runs])):
            reason = f"{empty_runs} corridas sin avisos después de obtener resultados; posible rotura del parser"
        else:
            due = max(row['next_run_at'] or row['created_at'], row.get('updated_at', row['created_at']))
            grace = timedelta(seconds=max(timeout_minutes * 60, row['crawl_interval_seconds'] * 2))
            if now - due > grace:
                reason = "búsqueda vencida que dejó de ejecutarse"
        if not reason and not loading and (previous or {}).get(key) and row['latest_status'] != 'ok':
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


class QuotaUnknown(Exception):
    """Resend didn't answer this time (network, 5xx, 429): keep the previous verdict."""


class QuotaBlind(Exception):
    """The usage can't be read until someone acts; the message says what to fix."""


def key_problem(response: httpx.Response) -> str:
    """What a 4xx from /usage means for the owner. The same key sends every email."""
    try:
        name = response.json().get('name')
    except (ValueError, AttributeError):
        name = None
    name = name if isinstance(name, str) and re.fullmatch(r'[a-z_]{1,40}', name) else None
    status = response.status_code
    if status == 401 and name == 'restricted_api_key':
        return ("no se puede leer el uso de Resend (HTTP 401): la API key solo tiene permiso de envío. "
                "Los emails salen, pero no hay aviso de cuota hasta usar una key con Full access.")
    if status in (400, 401, 403):
        return (f"Resend rechaza la API key (HTTP {status}{', ' + name if name else ''}): está mal, revocada "
                "o suspendida. Mientras no se cambie no sale ningún email: alertas, mails de plan ni estos avisos.")
    return f"no se pudo leer el uso de Resend (HTTP {status}): el aviso de cuota no funciona."


def resend_usage(get=None) -> dict:
    """Resend's own count for the whole account: the worker's emails, Auth's
    links (SMTP), these warnings and received emails. Needs a full-access key."""
    get = get or (lambda: httpx.get(RESEND_USAGE_URL, timeout=15,
                                    headers={'Authorization': f'Bearer {config.RESEND_API_KEY}'}))
    try:
        response = get()
    except httpx.HTTPError as error:
        raise QuotaUnknown(type(error).__name__) from None
    if response.status_code == 429 or response.status_code >= 500:
        raise QuotaUnknown(f'HTTP {response.status_code}')
    if not response.is_success:
        raise QuotaBlind(key_problem(response))
    try:
        emails = response.json()['emails']
    except (ValueError, KeyError, TypeError):
        emails = None
    if not isinstance(emails, dict):
        raise QuotaBlind(UNREADABLE)
    return emails


def renewal(resets_at) -> datetime | None:
    try:
        at = datetime.fromisoformat(str(resets_at).replace('Z', '+00:00'))
    except ValueError:
        return None
    if at.tzinfo is None:
        return None
    # Resend reports a window's last millisecond (23:59:59.999Z): show the minute it renews.
    if at.second or at.microsecond:
        at = at.replace(second=0, microsecond=0) + timedelta(minutes=1)
    return at.astimezone(ART)


def thousands(n: int) -> str:
    return f'{n:,}'.replace(',', '.')


def quota_checks(emails: dict, pct: int, now: datetime | None = None) -> dict[str, str | None]:
    today = (now or datetime.now(ART)).astimezone(ART).date()
    windows = {window: emails.get(window) for window in QUOTA_KEYS}

    def counts(quota, limitless: bool) -> bool:
        number = lambda n: type(n) is int and n >= 0
        return (isinstance(quota, dict) and number(quota.get('used')) and 'limit' in quota
                and ((limitless and quota['limit'] is None) or (number(quota['limit']) and quota['limit'] > 0)))

    # A paid plan has no daily limit (null), and past its monthly one it bills or pauses instead.
    if not (counts(windows['daily'], True) and counts(windows['monthly'], False)):
        raise QuotaBlind(UNREADABLE)
    paid = windows['daily']['limit'] is None
    checks: dict[str, str | None] = {}
    for window, key in QUOTA_KEYS.items():
        used, limit = windows[window]['used'], windows[window]['limit']
        if limit is None or used * 100 < limit * pct:
            checks[key] = None
            continue
        at = renewal(windows[window].get('resets_at'))
        if window == 'daily':
            period = 'de hoy'
            when = at and f"{'hoy' if at.date() == today else f'el {at:%d/%m}'} a las {at:%H:%M} (hora argentina)"
        else:
            period, when = 'del mes', at and f"el {at:%d/%m}"
        if paid:
            renews = f" La cuota se renueva {when}." if when else ""
            checks[key] = (f"se superaron los {thousands(limit)} emails del mes del plan de Resend.{renews} "
                           "Revisá en Resend si está cobrando los emails extra o si frenó los envíos."
                           if used >= limit else
                           f"{thousands(used)} de {thousands(limit)} emails del mes ({used * 100 // limit}%).{renews} "
                           "Revisá en Resend qué hace tu plan al superar la cuota: cobrar los emails extra o frenar los envíos.")
            continue
        rejects = (f"Resend rechaza los emails nuevos (alertas, mails de plan y links para entrar) "
                   f"hasta que se renueve la cuota{', ' + when if when else ''}.")
        if used >= limit:
            checks[key] = (f"se agotaron los {thousands(limit)} emails {period}: {rejects} "
                           "Para no cortar los envíos, hay que pasar a un plan pago de Resend.")
        else:
            checks[key] = (f"{thousands(used)} de {thousands(limit)} emails {period} ({used * 100 // limit}%). "
                           f"Al llegar a {thousands(limit)}, {rejects} "
                           "Si pasa seguido, conviene pasar a un plan pago de Resend.")
    return checks


def email_quota(previous: dict[str, str | None], get=None, now: datetime | None = None) -> dict[str, str | None]:
    """Warns before Resend's quota runs out: past it, every email bounces with 429."""
    pct = config.PLATFORM_HEALTH_EMAIL_QUOTA_PCT
    if pct <= 0 or not config.RESEND_API_KEY:
        return {}
    keep = {key: previous[key] for key in (*QUOTA_KEYS.values(), QUOTA_BLIND) if key in previous}
    try:
        checks = quota_checks(resend_usage(get), pct, now)
    except QuotaBlind as error:
        # Open warnings stay open until a reading closes them; nothing unread shows as OK.
        return {**{key: problem for key, problem in keep.items() if problem}, QUOTA_BLIND: str(error)}
    except QuotaUnknown as error:
        print(f'No se pudo leer el uso de Resend: {error}', file=sys.stderr)
        return keep
    # Readable again: this run closes the warning with its own email; the next one drops the key.
    if previous.get(QUOTA_BLIND):
        checks[QUOTA_BLIND] = None
    return checks


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
    messages = transitions(previous, current, QUOTA_RECOVERED)
    if messages:
        if not (config.PLATFORM_HEALTH_EMAIL and config.RESEND_API_KEY and config.EMAIL_FROM):
            raise RuntimeError('faltan PLATFORM_HEALTH_EMAIL / RESEND_API_KEY / EMAIL_FROM')
        stamp = datetime.now(ART).strftime('%d/%m/%Y %H:%M ART')
        quota = {*QUOTA_KEYS.values(), QUOTA_BLIND}
        red = {name for name, problem in current.items() if problem and not previous.get(name)}
        green = {name for name, problem in current.items() if not problem and previous.get(name)}
        if red:
            subject = 'Ese Auto: aviso de la cuota de emails (Resend)' if red <= quota else 'Ese Auto: falla en la plataforma de scraping'
        elif green <= quota:
            subject = ('Ese Auto: novedades de la cuota de emails (Resend)' if any(current.get(key) for key in quota)
                       else 'Ese Auto: la cuota de emails (Resend) volvió a la normalidad')
        else:
            subject = 'Ese Auto: scraping recuperado'
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
            checks.update(email_quota(previous))
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
