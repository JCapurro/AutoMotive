"""One tick of the repair bot (docs/COLLECTOR_REPAIR.md).

Claude only diagnoses and edits the clone. Everything with an effect outside it (the queue,
git, the VPS, email) happens here, through Deps, after deterministic gates. Each step saves
the incident's local state before the next one, so a tick killed halfway resumes or reports.

state.deploy['stage'] while the phase is 'deployed': pushing (the commit may or may not be on
main: landed() decides) -> pushed (on main, the deploy not confirmed) -> live (deployed, under
verification); reverting (the revert may or may not be on main) -> reverted (on main). 'blocked':
a person has it. A later tick resumes any of them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
import os
from pathlib import Path
import subprocess
import time
from typing import Any
import uuid

from repairbot import gitops, state as st
from repairbot.gitops import GitError
from repairbot.settings import THREAD_PREFIX, Settings, child_env
from repairbot.vps import VpsError

log = logging.getLogger(__name__)

TICK_BUDGET_S = 80 * 60          # the scheduled task is stopped at 90 minutes
GATES_RESERVE_S = 30 * 60        # after Claude: suite (15), deploy (7), idle wait (5), restart (3)
IN_TICK_VERIFY_S = 10 * 60       # verification goes on in later ticks
VERIFY_POLL_S = 30
IDLE_POLL_S = 15
TESTS_TIMEOUT_S = 900
REOPEN_AFTER_S = 3600            # 'done' but the monitor still reports the source
EXTERNAL_RETRY_S = (15 * 60, 24 * 3600)
RATE_LIMIT_PAUSE_S = (15 * 60, 6 * 3600)
FALLBACK_TARGETS = 5
BLOCKING_DEPLOY = ('dirty', 'pending_changes', 'wrong_host')   # deploy refusals a person must look at
NOTE_LIMIT = 1500


# --------------------------------------------------------------------------------------
# What the tick acts through. Tests replace every one of these with fakes.
# --------------------------------------------------------------------------------------

class Clock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class Database:
    """repairbot.queue, one connection and one transaction per call: a kick is visible to the
    worker as soon as the call returns."""

    def __init__(self, url: str):
        self.url = url

    def _call(self, name: str, *args):
        from aio import run

        if not self.url:
            raise RuntimeError('DATABASE_URL no está en el .env del checkout principal')
        return run(self._run(name, args))

    async def _run(self, name: str, args: tuple):
        from psycopg import AsyncConnection

        from db.pool import connection_kwargs
        from repairbot import queue

        connection = await AsyncConnection.connect(self.url, connect_timeout=30, **connection_kwargs(self.url))
        async with connection as cx:
            return await getattr(queue, name)(cx, *args)

    def active_incidents(self) -> list[dict]:
        return self._call('active_incidents')

    def claim(self, owner: str) -> dict | None:
        return self._call('claim', owner)

    def attach(self, incident_id, token, thread: str) -> bool:
        return self._call('attach', incident_id, token, thread)

    def needs_input(self, incident_id, note: str) -> bool:
        return self._call('needs_input', incident_id, note)

    def incident_context(self, incident: dict) -> dict:
        return self._call('incident_context', incident)

    def failing_targets(self, source: str) -> list[int]:
        return self._call('failing_targets', source)

    def running_runs(self, source: str) -> int:
        return self._call('running_runs', source)

    def kick(self, source: str, target_ids: list[int]) -> list[int]:
        return self._call('kick', source, target_ids)

    def runs_since(self, source: str, target_ids: list[int], since: datetime) -> list[dict]:
        return self._call('runs_since', source, target_ids, since)

    def now(self) -> datetime:
        return self._call('db_now')


class Claude:
    def __init__(self, settings: Settings):
        self.settings = settings

    def preflight(self) -> str | None:
        from repairbot import claude_runner

        return claude_runner.preflight(self.settings)

    def run(self, **options):
        from repairbot import claude_runner

        return claude_runner.run_claude(self.settings, **options)


def _python(settings: Settings, args: list[str], cwd: Path, run_id: str, timeout: int, runner) -> str | None:
    """Run the configured interpreter with the Claude child's environment (no secrets: the code
    it runs was partly written by the model). None when it exits 0, else why not."""
    try:
        done = runner([str(settings.python), *args], cwd=str(cwd), env=child_env(settings, run_id),
                      capture_output=True, timeout=timeout, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired:
        return f'no terminó en {timeout} s'
    except OSError as error:
        return f'no se pudo ejecutar python ({type(error).__name__})'
    if done.returncode == 0:
        return None
    output = ((done.stdout or b'') + (done.stderr or b'')).decode('utf-8', errors='replace').strip()
    return f'salió con código {done.returncode}: {output[-1500:]}'


def run_tests(settings: Settings, run_id: str, *, runner=gitops.run, timeout: int = TESTS_TIMEOUT_S) -> str | None:
    """The full suite without database, from <repo>/worker, run by the launcher itself."""
    problem = _python(settings, ['-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-m', 'not db'],
                      Path(settings.repo) / 'worker', run_id, timeout, runner)
    return f'la suite de tests falló: {problem}' if problem else None


def compile_paths(repo: Path, paths: list[str]) -> str | None:
    """py_compile of every changed .py that still exists, in process: nothing is executed."""
    for path in paths:
        file = Path(repo) / path
        if not path.endswith('.py') or not file.is_file():
            continue
        try:
            compile(file.read_bytes(), path, 'exec', dont_inherit=True)
        except (SyntaxError, ValueError) as error:
            return f'{path} no compila: {type(error).__name__}: {error}'
    return None


class Git:
    def __init__(self, settings: Settings, runner=gitops.run):
        self.settings, self.repo, self.runner = settings, settings.repo, runner

    def sync(self) -> str:
        return gitops.sync(self.repo, settings=self.settings, runner=self.runner)

    def changed_paths(self) -> list[str]:
        return gitops.changed_paths(self.repo, runner=self.runner)

    def diff_lines(self) -> int:
        return gitops.diff_lines(self.repo, runner=self.runner)

    def compile(self, paths: list[str]) -> str | None:
        return compile_paths(self.repo, paths)

    def tests(self, run_id: str) -> str | None:
        return run_tests(self.settings, run_id, runner=self.runner)

    def commit(self, message: str) -> str:
        return gitops.commit(self.repo, message, runner=self.runner)

    def push(self) -> str:
        return gitops.push(self.repo, runner=self.runner)

    def revert(self, sha: str, message: str) -> str:
        return gitops.revert(self.repo, sha, message, runner=self.runner)

    def landed(self, run_id: str, reverts: str | None = None) -> str | None:
        return gitops.landed(self.repo, run_id, reverts=reverts, runner=self.runner)

    def parent(self, sha: str) -> str:
        return gitops.parent(self.repo, sha, runner=self.runner)

    def update_launcher(self) -> str:
        return gitops.update_launcher(self.settings.launcher, settings=self.settings, runner=self.runner)


class Vps:
    def __init__(self, settings: Settings, runner=gitops.run):
        self.settings, self.runner = settings, runner

    def status(self) -> dict:
        from repairbot import vps
        return vps.status(self.settings, runner=self.runner)

    def logs(self, source: str) -> str:
        from repairbot import vps
        return vps.logs(self.settings, source, runner=self.runner)

    def deploy(self, sha: str, base: str) -> dict:
        from repairbot import vps
        return vps.deploy(self.settings, sha, base, runner=self.runner)

    def restart(self) -> dict:
        from repairbot import vps
        return vps.restart_worker(self.settings, runner=self.runner)

    def cleanup(self, run_id: str) -> None:
        from repairbot import vps
        vps.cleanup(self.settings, run_id, runner=self.runner)


class Mail:
    def __init__(self, settings: Settings):
        self.settings = settings

    def send(self, **email) -> bool:
        from repairbot import notify
        return notify.send(self.settings, **email)


@dataclass
class Deps:
    db: Any
    claude: Any
    git: Any
    vps: Any
    notify: Any
    clock: Any = field(default_factory=Clock)
    store: st.Store | None = None     # None: <home>/state on the same clock


def default_deps(settings: Settings) -> Deps:
    from repairbot.settings import load_env

    load_env(settings)   # before anything imports config (db, tools.*): it reads the environment once
    return Deps(db=Database(os.environ.get('DATABASE_URL', '')), claude=Claude(settings), git=Git(settings),
                vps=Vps(settings), notify=Mail(settings))


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

class Unsettled(RuntimeError):
    """origin did not say whether a push landed: the stage stays and a later tick asks again."""


def new_run_id(now: datetime) -> str:
    return f'{now.astimezone(timezone.utc):%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}'


def counted(state: st.IncidentState) -> int:
    return state.counted()


def _clip(value, limit: int = NOTE_LIMIT) -> str:
    text = str(value or '').strip()
    return text if len(text) <= limit else text[:limit] + '…'


def _bounded(seconds: float, bounds: tuple[int, int]) -> float:
    return min(max(seconds, bounds[0]), bounds[1])


def _reset_at(rate_limit: dict | None) -> datetime | None:
    """resetsAt of a rate_limit_event, as epoch seconds (or ms) or ISO text."""
    value = (rate_limit or {}).get('resetsAt') or (rate_limit or {}).get('resets_at')
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc)
        if isinstance(value, str) and value:
            return st.parse_ts(value)
    except (ValueError, OverflowError, OSError):
        pass
    return None


def _verdict(runs: list[dict], targets: list[int], require_found: bool) -> tuple[str | None, str]:
    """('failed', why) on any failed run, ('ok', '') once every target ran well, else (None, '')."""
    for run in runs:
        if run.get('status') == 'failed':
            return 'failed', f"la corrida {run.get('id')} del target {run.get('target_id')} falló: {run.get('error') or 'sin detalle'}"
    good = {run.get('target_id') for run in runs
            if run.get('status') == 'ok' and (not require_found or (run.get('found') or 0) > 0)}
    if targets and set(targets) <= good:
        return 'ok', ''
    return None, ''


# --------------------------------------------------------------------------------------
# The tick
# --------------------------------------------------------------------------------------

def tick(settings: Settings, deps: Deps | None = None, *, dry_run: bool = False) -> dict:
    """Run one tick; returns its JSON summary. Never raises."""
    summary: dict[str, Any] = {'ok': True, 'dry_run': dry_run, 'actions': [], 'claude_runs': 0, 'errors': []}
    lock = None
    if not dry_run:   # a dry run only reads: it may run next to a real tick
        lock = st.Lock(settings.state_dir / 'bot.lock')
        if not lock.acquire():
            summary['skipped'] = 'otra instancia del bot está corriendo'
            return summary
    try:
        if not settings.enabled:
            summary['skipped'] = 'el bot está pausado (enabled=false en config.json)'
        else:
            deps = deps or default_deps(settings)
            run = _Tick(settings, deps, summary)
            run.plan() if dry_run else run.run()
    except Exception as error:   # the per-incident handler missed it: setup, listing, claim
        _Tick.fail(settings, None if dry_run else deps, summary, error)   # a dry run neither mails nor writes
    finally:
        if lock:   # never in a dry run: it changes nothing, the launcher's clone included
            try:
                update_launcher(settings, deps, summary)
            finally:
                lock.release()
    summary['ok'] = not summary['errors']
    return summary


def update_launcher(settings: Settings, deps: Deps | None, summary: dict) -> None:
    """Fast-forward the clone the scheduled task runs from, last in every tick: the next tick runs
    main's launcher. On failure the current code keeps running; it is mailed once a day."""
    try:
        (deps.git if deps else Git(settings)).update_launcher()
    except Exception as error:
        _Tick.fail(settings, deps, summary, error, 'actualización del lanzador', topic='launcher')


class _Tick:
    def __init__(self, settings: Settings, deps: Deps, summary: dict):
        self.settings, self.deps, self.summary = settings, deps, summary
        self.db, self.git, self.vps = deps.db, deps.git, deps.vps
        self.clock = deps.clock
        self.store = deps.store or st.Store(settings.state_dir, clock=deps.clock.now)
        self.started = self.clock.now()
        self.claude_used = False

    # -- bookkeeping ---------------------------------------------------------------------

    def now(self) -> datetime:
        return self.clock.now()

    def iso(self, moment: datetime | None = None) -> str:
        return st.now_iso(moment or self.now())

    def act(self, state_or_incident, action: str, detail: str = '') -> None:
        if isinstance(state_or_incident, st.IncidentState):
            incident, source = state_or_incident.incident_id, state_or_incident.source
        else:
            incident, source = str(state_or_incident.get('id')), state_or_incident.get('source')
        entry = {'incident': incident, 'source': source, 'action': action}
        if detail:
            entry['detail'] = _clip(detail, 300)
        self.summary['actions'].append(entry)
        log.info('%s %s: %s %s', source, incident, action, entry.get('detail', ''))

    def save(self, state: st.IncidentState) -> None:
        self.store.save(state)

    def mail(self, state: st.IncidentState, kind: str, subject: str, lines: list[str], n: int = 0) -> bool:
        history = [' · '.join(filter(None, (
                       f'- intento {item.n}: {item.outcome or "sin terminar"}', _clip(item.summary, 300),
                       item.detail and f'lanzador: {_clip(item.detail, 300)}',
                       item.commit and f'commit {item.commit[:12]}')))
                   for item in state.attempts]
        text = '\n'.join([*lines, '', f'Incidente: {state.incident_id}', f'Fuente: {state.source}',
                          *(['', 'Intentos:', *history] if history else [])])
        return self.deps.notify.send(incident_id=state.incident_id, source=state.source, kind=kind,
                                     subject=f'Bot de reparación: {subject}', text=text, n=n)

    @staticmethod
    def fail(settings: Settings, deps: Deps | None, summary: dict, error: Exception, where: str = 'tick',
             *, topic: str = 'bot') -> None:
        """Log it, keep it in the summary and mail it at most once a day per topic ('bot', or
        'launcher' for its own updates). Never raises."""
        detail = f'{where}: {type(error).__name__}: {_clip(error, 600)}'
        summary['errors'].append(detail)
        log.error('error en %s', where, exc_info=error)
        if deps is None:
            return
        try:
            store = deps.store or st.Store(settings.state_dir, clock=deps.clock.now)
            day = deps.clock.now().astimezone().strftime('%Y%m%d')
            kind = f'{topic}_error'
            mailed = any(event.get('kind') == kind and event.get('day') == day and event.get('mailed')
                         for event in store.events())
            sent = False
            if not mailed:
                subject, intro = (
                    ('no se actualizó el lanzador',
                     f'El bot no pudo actualizar el clon desde el que corre ({settings.launcher}) y sigue con el '
                     'código que ya tenía. Lo vuelve a intentar al final de cada tick.') if topic == 'launcher' else
                    ('error interno', 'El bot de reparación tuvo un error y lo va a reintentar en el próximo tick.'))
                sent = deps.notify.send(
                    incident_id=topic, source='repairbot', kind='bot_error', n=int(day),
                    subject=f'Bot de reparación: {subject}',
                    text=f'{intro}\n\n{detail}\n\nDetalle en state\\bot.log. No se manda otro aviso de este tipo hasta mañana.')
            store.event(kind, day=day, mailed=bool(mailed or sent), detail=detail)
        except Exception:
            log.exception('no se pudo registrar el error')

    def guarded(self, where: str, function, *args) -> None:
        try:
            function(*args)
        except Exception as error:
            self.fail(self.settings, self.deps, self.summary, error, where)

    # -- the cycle -----------------------------------------------------------------------

    def run(self) -> None:
        incidents = self.db.active_incidents()
        active = {str(row['id']): row for row in incidents}
        for state in self.store.all_open():
            if state.incident_id not in active:
                self.guarded(f'cierre de {state.incident_id}', self.closed, state)
        due = []
        for incident in incidents:
            if not str(incident.get('thread_id') or '').startswith(THREAD_PREFIX):
                continue
            try:
                state = self.reconcile(incident)
            except Exception as error:
                self.fail(self.settings, self.deps, self.summary, error, f'incidente {incident.get("id")}')
                continue
            if state and self.is_due(state):
                due.append((incident, state))
        if not self.may_start_session():
            return
        if due:
            incident, state = due[0]
            self.guarded(f'intento sobre {incident["id"]}', self.attempt, incident, state)
        else:
            self.claim()

    def is_due(self, state: st.IncidentState) -> bool:
        return (state.phase in ('new', 'waiting') and counted(state) < self.settings.max_attempts
                and (not state.retry_after or st.parse_ts(state.retry_after) <= self.now()))

    def paused_until(self) -> datetime | None:
        for event in reversed(self.store.events()):
            if event.get('kind') == 'rate_limited' and event.get('until'):
                try:
                    return st.parse_ts(event['until'])
                except (TypeError, ValueError):
                    return None
        return None

    def may_start_session(self) -> bool:
        reason = None
        paused = self.paused_until()
        if self.claude_used:
            reason = 'ya hubo una sesión de Claude en este tick'
        elif self.store.sessions_today() >= self.settings.max_sessions_per_day:
            reason = f'se alcanzó el tope de {self.settings.max_sessions_per_day} sesiones de Claude por día'
        elif paused and paused > self.now():
            reason = f'límite de uso de Claude hasta {self.iso(paused)}'
        if reason:
            self.summary.setdefault('skipped', reason)
        return reason is None

    def closed(self, state: st.IncidentState) -> None:
        """The monitor resolved or cancelled the incident. What the bot had in flight is settled and
        reported first; an error leaves the state as it was, for the next tick."""
        deploy = state.deploy or {}
        last = state.attempts[-1] if state.attempts else None
        stage = deploy.get('stage') if state.phase == 'deployed' and last else None
        if stage == 'pushing':
            stage = self.closed_push(state, last)
        if stage == 'pushed':
            if not last.outcome:
                last.outcome, last.finished_at = 'deploy_blocked', self.iso()
                last.detail = 'el incidente se cerró con el commit en main sin un deploy confirmado'
            self.mail(state, 'deploy_blocked', f'{state.source} tiene un commit sin desplegar', [
                f'El incidente se cerró solo, pero el commit {deploy.get("commit")} quedó en main sin un deploy '
                'confirmado (el bot se cortó entre el push y el deploy, o el VPS no confirmó el deploy).',
                'Desplegalo a mano o revertilo (docs/COLLECTOR_REPAIR.md, "Desplegar main a mano").'], n=last.n)
        elif stage in ('reverting', 'reverted'):   # never 'fixed': the bot had decided to undo it
            self.finish_revert(state, resumed=True, closing=True)
        elif stage == 'live':
            self.closed_live(state, last)
        state.phase, state.retry_after = 'done', None
        self.save(state)
        self.act(state, 'cerrado', 'el monitor cerró el incidente')

    def closed_push(self, state: st.IncidentState, last: st.Attempt) -> str | None:
        """The stage a push cut short really reached: 'pushed' when it is on main, else None."""
        landed = self.landed(state, 'el tick se cortó durante el push')
        if not landed:
            last.outcome, last.detail, last.finished_at = 'publish_failed', 'el push no llegó a main', self.iso()
            state.deploy = None
            return None
        last.commit = landed
        state.deploy.update(commit=landed, stage='pushed')
        return 'pushed'

    def closed_live(self, state: st.IncidentState, last: st.Attempt) -> None:
        """A closure alone verifies nothing (a kick resets an overdue search's clock): 'fixed'
        needs a good run of every kicked target after the deploy, as in verify()."""
        deploy = state.deploy
        targets = deploy.get('targets') or []
        runs = (self.db.runs_since(state.source, targets, st.parse_ts(deploy['deployed_at']))
                if targets and deploy.get('deployed_at') else [])
        good = sorted({run.get('target_id') for run in runs if run.get('status') == 'ok' and
                       (not deploy.get('require_found') or (run.get('found') or 0) > 0)})
        if targets and set(targets) <= set(good):
            if last.outcome == 'deployed':
                last.outcome, last.finished_at = 'verified', self.iso()
            self.mail(state, 'fixed', f'{state.source} funciona otra vez', [
                'El monitor cerró el incidente con el arreglo del bot desplegado, y los targets '
                f'{good} tuvieron una corrida exitosa después del deploy.', f'Commit: {deploy.get("commit")}.'],
                n=last.n)
            return
        if last.outcome == 'deployed':
            last.outcome, last.finished_at = 'unverified', self.iso()
            last.detail = 'el monitor cerró el incidente sin una corrida posterior al deploy de cada target'
        missing = [target for target in targets if target not in good]
        self.mail(state, 'unverified', f'{state.source}: incidente cerrado sin verificar el arreglo', [
            f'El monitor cerró el incidente, pero no todos los targets pateados ({targets}) tuvieron una '
            f'corrida exitosa después del deploy del arreglo {deploy.get("commit")}: faltan {missing}.',
            'El cierre no prueba el arreglo: una búsqueda vencida, por ejemplo, deja de figurar apenas el bot '
            'la vuelve a programar, aunque todavía no haya corrido.',
            'El arreglo queda desplegado; si la fuente vuelve a fallar, el monitor abre otro incidente.'], n=last.n)

    def reconcile(self, incident: dict) -> st.IncidentState | None:
        """Bring the local state of a bot-owned incident up to date. Returns it when it may need a session."""
        state = self.store.load(incident['id'])
        if state is None:
            state = self.adopt(incident)
        if incident.get('status') == 'needs_input':
            return None   # a person has it
        if state.phase == 'needs_input':
            # Someone set the incident back to 'open': a fresh budget of attempts. The history
            # stays (the next session reads it, and email keys keep counting from it).
            self.store.event('handed_back', incident=state.incident_id, attempts=len(state.attempts))
            state.budget_from, state.phase, state.retry_after, state.deploy = len(state.attempts), 'waiting', None, None
            self.save(state)
            self.act(state, 'devuelto', 'el incidente volvió a open: nuevo presupuesto de intentos')
        if state.phase == 'deployed':
            self.verify(incident, state)
        elif state.phase == 'done':
            last = state.attempts[-1] if state.attempts else None
            finished = st.parse_ts(last.finished_at) if last and last.finished_at else None
            if finished and self.now() - finished >= timedelta(seconds=REOPEN_AFTER_S):
                state.phase, state.retry_after = 'waiting', None
                self.save(state)
                self.act(state, 'reabierto', 'el monitor sigue informando la fuente')
        if state.phase in ('new', 'waiting') and counted(state) >= self.settings.max_attempts:
            self.give_up(state)
        return state

    def adopt(self, incident: dict) -> st.IncidentState:
        """A bot-owned incident with no local state: lost state counts as one attempt."""
        thread = str(incident.get('thread_id'))[len(THREAD_PREFIX):]
        lost = st.Attempt(n=1, run_id=thread[:64], started_at=self.iso(), finished_at=self.iso(), outcome='lost',
                          detail='estado local perdido: el incidente se adoptó con un intento consumido')
        phase = 'needs_input' if incident.get('status') == 'needs_input' else 'waiting'
        state = st.IncidentState(str(incident['id']), incident['source'], phase=phase, attempts=[lost])
        self.save(state)
        self.act(state, 'adoptado', lost.detail)
        return state

    def claim(self) -> None:
        incident = self.db.claim(self.settings.owner)
        if not incident:
            return
        run_id = new_run_id(self.now())
        thread = THREAD_PREFIX + run_id
        if not self.db.attach(incident['id'], incident['claim_token'], thread):
            self.act(incident, 'sin asociar', 'attach devolvió false: la reserva venció o el incidente cambió')
            return
        incident = {**incident, 'thread_id': thread, 'status': 'open'}
        state = st.IncidentState(str(incident['id']), incident['source'])
        self.save(state)
        self.store.event('claimed', incident=state.incident_id, run_id=run_id)
        self.act(state, 'reclamado', thread)
        self.guarded(f'intento sobre {incident["id"]}', self.attempt, incident, state, run_id)

    # -- an attempt ----------------------------------------------------------------------

    def attempt(self, incident: dict, state: st.IncidentState, run_id: str | None = None) -> None:
        from repairbot import prompt

        self.claude_used = True   # one session per tick, also when this one does not get to start
        problem = self.deps.claude.preflight()
        if problem:
            raise RuntimeError(f'Claude Code no está listo: {problem}')
        run_id = run_id or new_run_id(self.now())
        self.git.sync()
        try:
            self.vps.status()
            reachable = True
        except VpsError as error:
            log.warning('VPS no disponible al empezar %s: %s', run_id, error)
            reachable = False
        journal = ''
        if reachable:
            try:
                journal = self.vps.logs(state.source)
            except VpsError as error:
                log.warning('sin journal para %s: %s', state.source, error)
        context = self.db.incident_context(incident)
        system, task = prompt.system_prompt(self.settings), prompt.task_prompt(context, state, journal, self.settings)
        attempt = st.Attempt(n=len(state.attempts) + 1, run_id=run_id, started_at=self.iso())
        state.attempts.append(attempt)
        self.save(state)
        self.store.event('claude_run', incident=state.incident_id, run_id=run_id)
        self.summary['claude_runs'] += 1
        self.act(state, 'sesión de Claude', run_id)
        try:
            try:
                result = self.deps.claude.run(prompt=task, system_prompt=system, session_id=str(uuid.uuid4()),
                                              run_dir=self.settings.runs_dir / run_id,
                                              deadline_s=self.claude_deadline())
            finally:
                try:
                    self.vps.cleanup(run_id)
                except Exception:
                    log.warning('no se limpió el staging de %s', run_id, exc_info=True)
            self.outcome(incident, state, attempt, result)
        finally:
            if not attempt.commit:   # nothing reached main: the session's edits leave the clone now
                self.discard(run_id)

    def discard(self, run_id: str) -> None:
        try:
            self.git.sync()
        except Exception:
            log.warning('el clon quedó con los cambios de %s: no se pudo sincronizar', run_id, exc_info=True)

    def claude_deadline(self) -> int:
        left = TICK_BUDGET_S - (self.now() - self.started).total_seconds() - GATES_RESERVE_S
        return int(max(300, min(self.settings.claude_timeout_s, left)))

    def outcome(self, incident: dict, state: st.IncidentState, attempt: st.Attempt, result) -> None:
        output = result.output or {}
        attempt.root_cause, attempt.summary = _clip(output.get('root_cause')), _clip(output.get('summary'))
        if not result.ok:
            attempt.detail = _clip(f'{result.reason}: {result.detail}')
            if result.reason == 'rate_limited':
                return self.rate_limited(state, attempt, result)
            attempt.outcome = result.reason
            if result.reason in ('guard_inactive', 'init_mismatch'):   # configuration, not the collector
                self.fail(self.settings, self.deps, self.summary,
                          RuntimeError(f'la sesión de Claude no arrancó con el guard: {result.detail}'), 'guard')
            return self.failed(state, attempt)
        kind = output['outcome']
        if kind == 'fixed':
            return self.publish(incident, state, attempt, output)
        attempt.outcome, attempt.finished_at = kind, self.iso()
        if kind == 'external':
            minutes = output.get('retry_in_minutes')
            delay = (_bounded(minutes * 60, EXTERNAL_RETRY_S) if isinstance(minutes, int) and minutes > 0
                     else self.retry_delay(state))
            return self.wait(state, delay, 'externo')
        if kind == 'needs_human':
            action = _clip(output.get('human_action') or attempt.summary or attempt.root_cause)
            return self.to_person(state, 'needs_input', f'{state.source} necesita una persona', action, [
                f'La sesión diagnosticó algo que el bot no puede resolver solo: {attempt.root_cause}',
                f'Qué hacer: {action}'], n=attempt.n)
        if kind == 'recovered':
            state.phase, state.retry_after = 'done', None
            self.save(state)
            return self.act(state, 'recuperado', attempt.summary)
        return self.failed(state, attempt)   # no_fix

    def retry_delay(self, state: st.IncidentState) -> int:
        delays = self.settings.retry_delays_s or (1800,)
        return delays[min(max(counted(state), 1), len(delays)) - 1]

    def wait(self, state: st.IncidentState, seconds: float, why: str) -> None:
        state.phase, state.retry_after = 'waiting', self.iso(self.now() + timedelta(seconds=seconds))
        self.save(state)
        self.act(state, f'espera ({why})', f'reintento desde {state.retry_after}')
        if counted(state) >= self.settings.max_attempts:
            self.give_up(state)

    def failed(self, state: st.IncidentState, attempt: st.Attempt) -> None:
        attempt.finished_at = attempt.finished_at or self.iso()
        self.wait(state, self.retry_delay(state), attempt.outcome or 'falló')

    def rate_limited(self, state: st.IncidentState, attempt: st.Attempt, result) -> None:
        now = self.now()
        reset = _reset_at(result.rate_limit)
        pause = _bounded(((reset - now).total_seconds() if reset else 0) + 60, RATE_LIMIT_PAUSE_S)
        until = self.iso(now + timedelta(seconds=pause))
        attempt.outcome, attempt.finished_at = 'rate_limited', self.iso(now)
        state.phase, state.retry_after = 'waiting', until
        self.save(state)
        self.store.event('rate_limited', incident=state.incident_id, until=until)
        self.act(state, 'límite de uso', f'sin sesiones nuevas hasta {until}')

    def give_up(self, state: st.IncidentState) -> None:
        last = state.attempts[-1] if state.attempts else None
        note = f'El bot se rindió después de {counted(state)} intentos. Último: {last.outcome if last else "-"}. ' \
               f'{_clip(last.summary if last else "", 500)}'
        self.to_person(state, 'gave_up', f'me rendí con {state.source}', note, [
            f'El bot hizo {counted(state)} intentos sin arreglar {state.source} y lo deja para una persona.',
            'Cuando esté resuelto, el monitor cierra el incidente solo. Para que el bot lo vuelva a intentar, '
            'poné el incidente otra vez en open (docs/COLLECTOR_REPAIR.md).'], n=len(state.attempts))

    def to_person(self, state: st.IncidentState, kind: str, subject: str, note: str, lines: list[str],
                  n: int = 0) -> None:
        """needs_input in the queue first, then locally, then the email."""
        if not self.db.needs_input(state.incident_id, note or 'requiere intervención'):
            log.warning('needs_input no cambió el incidente %s (ya no estaba abierto)', state.incident_id)
        state.phase, state.retry_after = 'needs_input', None
        self.save(state)
        self.mail(state, kind, subject, lines, n=n)
        self.act(state, 'necesita una persona', note)

    # -- gates and publication -----------------------------------------------------------

    def gates(self, run_id: str) -> str | None:
        paths = self.git.changed_paths()
        if not paths:
            return 'la sesión informó un arreglo pero no hay cambios en el clon'
        outside = gitops.scope_violations(paths, self.settings.allowed_paths)
        if outside:
            return 'cambios fuera del alcance permitido: ' + ', '.join(outside[:10])
        if any(not path.startswith('worker/tests/') for path in paths) and \
                not any(path.startswith('worker/tests/') for path in paths):
            return 'falta la prueba de regresión (ningún cambio en worker/tests/)'
        lines = self.git.diff_lines()
        if lines > self.settings.max_diff_lines:
            return f'el diff tiene {lines} líneas (tope {self.settings.max_diff_lines})'
        problem = self.git.compile(paths) or self.git.tests(run_id)
        if problem:
            return problem
        if self.git.changed_paths() != paths:
            return 'la suite de tests dejó archivos nuevos o modificados en el clon'
        return None

    def publish(self, incident: dict, state: st.IncidentState, attempt: st.Attempt, output: dict) -> None:
        problem = self.gates(attempt.run_id)
        if problem:
            attempt.outcome, attempt.detail = 'gate_failed', _clip(problem)
            return self.failed(state, attempt)
        try:   # a fresh look: nothing is pushed that could not be deployed right away
            status = self.vps.status()
        except VpsError as error:
            attempt.outcome, attempt.detail = 'publish_failed', _clip(f'el VPS no responde, no se publica: {error}')
            return self.failed(state, attempt)
        if status.get('hostname') != self.settings.vps_hostname or status.get('dirty'):
            why = (f'el VPS respondió como {status.get("hostname")!r}' if status.get('hostname') != self.settings.vps_hostname
                   else 'el checkout del VPS tiene cambios sin commitear: ' + ', '.join(status['dirty'][:10]))
            attempt.outcome, attempt.detail, attempt.finished_at = 'deploy_blocked', _clip(why), self.iso()
            return self.to_person(state, 'deploy_blocked', f'deploy bloqueado para {state.source}', why, [
                f'El arreglo de {state.source} pasó las compuertas pero no se publicó: {why}.',
                f'Causa diagnosticada: {attempt.root_cause}', 'Nada se pusheó.'], n=attempt.n)
        try:
            message = gitops.commit_message(state.source, attempt.summary, attempt.root_cause,
                                            state.incident_id, attempt.run_id)
            local = self.git.commit(message)
        except GitError as error:
            attempt.outcome, attempt.detail = 'publish_failed', _clip(f'commit: {error}')
            return self.failed(state, attempt)
        # From here on main can get the commit without push() saying so (its answer lost, the tick
        # killed): the stage goes to disk first and landed() settles it.
        state.phase = 'deployed'
        state.deploy = {'stage': 'pushing', 'run_id': attempt.run_id, 'local': local}
        self.save(state)
        try:
            pushed = self.git.push()
        except GitError as error:
            return self.settle_push(incident, state, f'push: {error}')
        self.pushed(incident, state, pushed)

    def landed(self, state: st.IncidentState, why: str, *, reverts: str | None = None) -> str | None:
        """The attempt's commit on origin/main (its revert, with `reverts`), or None. When origin does
        not answer it raises Unsettled: the stage stays and a later tick asks again."""
        try:
            return self.git.landed(state.attempts[-1].run_id, reverts=reverts)
        except GitError as error:
            what = 'el revert' if reverts else 'el arreglo'
            raise Unsettled(f'no se sabe si {what} llegó a main ({why}); se vuelve a mirar en el próximo '
                            f'tick: {error}') from None

    def settle_push(self, incident: dict, state: st.IncidentState, why: str, *, in_tick: bool = True) -> None:
        """push() raised, or a tick was cut during it: a fix on main goes live, else nothing was published."""
        attempt = state.attempts[-1]
        landed = self.landed(state, why)
        if landed:
            self.act(state, 'push confirmado', f'{why}; el arreglo está en main')
            return self.pushed(incident, state, landed, in_tick=in_tick)
        attempt.outcome, attempt.detail = 'publish_failed', _clip(why)
        state.deploy = None
        return self.failed(state, attempt)

    def pushed(self, incident: dict, state: st.IncidentState, sha: str, *, in_tick: bool = True) -> None:
        attempt = state.attempts[-1]
        attempt.commit = sha
        state.phase = 'deployed'
        state.deploy = {'commit': sha, 'run_id': attempt.run_id, 'stage': 'pushed'}
        self.save(state)
        self.act(state, 'pusheado', sha)
        self.go_live(incident, state, in_tick=in_tick)

    def go_live(self, incident: dict, state: st.IncidentState, *, in_tick: bool = True) -> None:
        """Deploy the pushed fix, restart the worker and kick the targets. Resumes a cut tick too
        (in_tick False): an earlier tick may have changed the VPS already."""
        deploy, attempt = state.deploy, state.attempts[-1]
        sha = deploy['commit']
        try:
            deploy['base'] = deploy.get('base') or self.git.parent(sha)
        except GitError as error:
            return self.unpublish(state, f'no se pudo calcular la base del deploy: {error}', vps_has_it=False)
        result = self.vps.deploy(sha, deploy['base'])
        if not result.get('ok'):
            code, head = result.get('code'), result.get('head')
            reason = f'{code}: {result.get("reason")}'
            if code == 'unknown_state' or (head is None and not in_tick):
                return self.deploy_unknown(state, reason)
            return self.unpublish(state, reason, vps_has_it=head == sha or bool(result.get('contains')),
                                  blocked=code in BLOCKING_DEPLOY)
        deploy['prev_head'] = result.get('prev_head')
        # After the wait: a failing target whose retry was running is the one to follow.
        self.wait_idle(state.source)
        targets = self.db.failing_targets(state.source)
        require_found = not targets
        if not targets:   # parser without results or an overdue search: no failed run to follow
            context = self.db.incident_context(incident)
            targets = [row['id'] for row in context.get('targets', [])][:FALLBACK_TARGETS]
        restart = self.vps.restart()
        if not restart.get('ok'):
            return self.rollback(state, f'el worker no quedó estable después del deploy: {restart.get("reason")}',
                                 label='worker inestable')
        deployed_at = self.db.now()   # runs started after this one ran the new code
        kicked = self.db.kick(state.source, targets)
        deploy.update(stage='live', deployed_at=self.iso(deployed_at), targets=kicked, require_found=require_found,
                      verify_until=self.iso(self.now() + timedelta(seconds=self.settings.verify_timeout_s)))
        attempt.outcome = 'deployed'
        self.save(state)
        self.act(state, 'desplegado', f'{sha[:12]}; targets {kicked}')
        if in_tick:
            limit = min(self.now() + timedelta(seconds=IN_TICK_VERIFY_S),
                        self.started + timedelta(seconds=TICK_BUDGET_S))
            self.verify(incident, state, poll_until=limit)

    def deploy_unknown(self, state: st.IncidentState, reason: str) -> None:
        """The VPS may or may not have the fix: never revert blind. Later ticks deploy again ('already'
        when it is there); once the verification time is spent, a person looks."""
        deploy, attempt = state.deploy, state.attempts[-1]
        since = st.parse_ts(deploy.setdefault('unknown_since', self.iso()))
        deploy['stage'] = 'pushed'
        if self.now() < since + timedelta(seconds=self.settings.verify_timeout_s):
            self.save(state)
            return self.act(state, 'deploy sin confirmar', f'{reason}; se reintenta en el próximo tick')
        deploy['stage'] = 'blocked'
        attempt.outcome, attempt.finished_at = 'deploy_blocked', self.iso()
        attempt.detail = _clip(f'deploy sin confirmar: {reason}')
        self.to_person(state, 'deploy_blocked', f'deploy sin confirmar para {state.source}', attempt.detail, [
            f'El arreglo {deploy["commit"]} de {state.source} está en main, pero en '
            f'{self.settings.verify_timeout_s // 60} minutos no se pudo confirmar si el VPS lo tiene: {reason}.',
            'El bot no lo revirtió (el VPS podría tenerlo) ni reinició el worker. Mirá en qué commit está el VPS '
            'y desplegá main o revertí el commit a mano (docs/COLLECTOR_REPAIR.md, "Desplegar main a mano").',
            f'Causa diagnosticada: {attempt.root_cause}'], n=attempt.n)

    def wait_idle(self, source: str) -> None:
        """Up to wait_idle_s for the source's runs in progress: a restart would cut them."""
        deadline = self.now() + timedelta(seconds=self.settings.wait_idle_s)
        while self.db.running_runs(source) > 0 and self.now() < deadline:
            self.clock.sleep(IDLE_POLL_S)

    def verify(self, incident: dict, state: st.IncidentState, poll_until: datetime | None = None) -> None:
        deploy, attempt = state.deploy or {}, state.attempts[-1]
        stage = deploy.get('stage')
        if stage == 'pushing':   # the tick was cut during the push
            self.act(state, 'comprobando el push', deploy.get('local', ''))
            return self.settle_push(incident, state, 'el tick se cortó durante el push', in_tick=False)
        if stage == 'pushed':   # cut before the deploy finished, or the VPS did not confirm it
            self.act(state, 'retomando el deploy', deploy.get('commit', ''))
            return self.go_live(incident, state, in_tick=False)
        if stage in ('reverting', 'reverted'):   # cut while undoing the fix
            self.act(state, 'retomando el revert', deploy.get('commit', ''))
            return self.finish_revert(state, resumed=True)
        if stage != 'live' or not deploy.get('deployed_at') or not deploy.get('verify_until'):
            attempt.outcome, attempt.detail = 'unverified', 'el registro del deploy está incompleto'
            return self.failed(state, attempt)
        targets = deploy.get('targets') or []
        since = st.parse_ts(deploy['deployed_at'])
        while True:
            verdict, why = _verdict(self.db.runs_since(state.source, targets, since), targets,
                                    bool(deploy.get('require_found')))
            if verdict == 'failed':
                return self.rollback(state, why)
            if verdict == 'ok':
                attempt.outcome, attempt.finished_at = 'verified', self.iso()
                state.phase, state.retry_after = 'done', None
                self.save(state)
                self.mail(state, 'fixed', f'{state.source} reparado', [
                    f'El arreglo del bot está desplegado y verificado: cada target pateado ({targets}) tuvo una '
                    'corrida exitosa después del deploy.', f'Resumen: {attempt.summary}',
                    f'Causa: {attempt.root_cause}', f'Commit: {deploy.get("commit")}.'], n=attempt.n)
                return self.act(state, 'verificado', deploy.get('commit', ''))
            if self.now() >= st.parse_ts(deploy['verify_until']):
                attempt.outcome, attempt.detail = 'unverified', 'sin corridas concluyentes dentro del tiempo de verificación'
                # Every deploy ends in one email; this fix stays deployed and the next attempt sees it.
                self.mail(state, 'unverified', f'{state.source}: arreglo desplegado sin verificar', [
                    f'El arreglo {deploy.get("commit")} está desplegado, pero en '
                    f'{self.settings.verify_timeout_s // 60} minutos no hubo corridas concluyentes de los targets {targets}.',
                    'Queda puesto; el bot vuelve a intentar más tarde.', f'Resumen: {attempt.summary}'], n=attempt.n)
                return self.failed(state, attempt)
            if poll_until is None or self.now() + timedelta(seconds=VERIFY_POLL_S) > poll_until:
                return
            self.clock.sleep(VERIFY_POLL_S)

    # -- undoing a published fix ---------------------------------------------------------

    def revert_message(self, state: st.IncidentState, sha: str, label: str) -> str:
        # Only fixed text: run errors and VPS output never leave the machine in a commit.
        # Its Repair-Run is the attempt's: landed(reverts=...) finds the revert by it.
        attempt = state.attempts[-1]
        return (f'revert({state.source}): deshacer {sha[:12]} ({label})\n\n'
                f'Repair-Incident: {state.incident_id}\nRepair-Run: {attempt.run_id}\n{gitops.CO_AUTHOR}\n')

    def rollback(self, state: st.IncidentState, why: str, label: str = 'verificación fallida') -> None:
        """The fix is live and made things worse: revert, push, deploy the revert, restart."""
        self.start_revert(state, 'rollback', why, label, deploy_it=True)

    def unpublish(self, state: st.IncidentState, why: str, *, vps_has_it: bool, blocked: bool = False) -> None:
        """The deploy did not happen (or did not finish): main must not stay ahead of the VPS."""
        if blocked and vps_has_it:
            return self.blocked_with_fix(state, why)
        self.start_revert(state, 'unpublish', why, 'deploy fallido', deploy_it=vps_has_it, blocked=blocked)

    def blocked_with_fix(self, state: st.IncidentState, why: str) -> None:
        """A refusal for a person (a dirty checkout) from a VPS that already has the fix: main is not
        ahead of it, so nothing is reverted and the worker is not restarted."""
        deploy, attempt = state.deploy, state.attempts[-1]
        deploy['stage'] = 'blocked'
        attempt.outcome, attempt.finished_at = 'deploy_blocked', self.iso()
        attempt.detail = _clip(f'deploy bloqueado con el arreglo ya en el VPS: {why}')
        self.to_person(state, 'deploy_blocked', f'deploy bloqueado para {state.source}', why, [
            f'El VPS ya tiene el arreglo {deploy["commit"]} de {state.source}, pero el deploy no terminó: {why}.',
            'El bot no lo revirtió (main no quedó adelantado al VPS) ni reinició el worker, que sigue con el '
            'código anterior hasta el próximo reinicio. Resolvé el VPS y reiniciá o desplegá main a mano '
            '(docs/COLLECTOR_REPAIR.md, "Desplegar main a mano").',
            f'Causa diagnosticada: {attempt.root_cause}'], n=attempt.n)

    def start_revert(self, state: st.IncidentState, kind: str, why: str, label: str, *, deploy_it: bool,
                     blocked: bool = False) -> None:
        """Record what the revert is for before git is touched: a cut tick finishes it (verify)."""
        state.deploy.update(stage='reverting', undo={'kind': kind, 'why': _clip(why), 'label': label,
                                                     'deploy_it': deploy_it, 'blocked': blocked})
        self.save(state)
        self.finish_revert(state)

    def push_revert(self, state: st.IncidentState, label: str, *, resumed: bool) -> str:
        """The fix's revert on origin/main, pushed now unless it is there already. Returns its sha."""
        deploy = state.deploy
        sha = deploy['commit']
        if deploy.get('stage') == 'reverted':
            return deploy['revert']
        pushed = self.landed(state, 'el tick se cortó durante el revert', reverts=sha) if resumed else None
        if not pushed:
            self.git.sync()
            self.git.revert(sha, self.revert_message(state, sha, label))
            try:
                pushed = self.git.push()
            except GitError as error:
                pushed = self.landed(state, f'push: {error}', reverts=sha)
                if not pushed:
                    raise
        deploy.update(stage='reverted', revert=pushed)
        self.save(state)
        return pushed

    def finish_revert(self, state: st.IncidentState, *, resumed: bool = False, closing: bool = False) -> None:
        """Push and deploy the revert, restart when the fix had been live, report and end the attempt.
        `resumed`: a cut tick left it halfway. `closing`: the monitor closed the incident meanwhile,
        so the attempt ends without a retry."""
        deploy, attempt = state.deploy, state.attempts[-1]
        undo = deploy.get('undo') or {'kind': 'rollback' if deploy.get('deployed_at') else 'unpublish',
                                      'why': 'un revert quedó a medias', 'label': 'revert retomado',
                                      'deploy_it': True, 'blocked': False}
        why = undo['why'] if undo['kind'] == 'rollback' else f'deploy fallido: {undo["why"]}'
        try:
            revert = self.push_revert(state, undo['label'], resumed=resumed)
            if undo['deploy_it']:   # 'already' when an earlier tick deployed it
                result = self.vps.deploy(revert, self.git.parent(revert))
                if not result.get('ok'):
                    raise VpsError(f'el VPS no aceptó el revert {revert[:12]}: {result.get("code")}: {result.get("reason")}')
        except (GitError, VpsError) as error:
            return self.stuck(state, attempt, why, error)
        retry = 'El monitor ya cerró el incidente.' if closing else \
            'El intento cuenta como fallido; el bot vuelve a intentar más tarde.'
        if undo['kind'] == 'rollback':
            restart = self.vps.restart()
            attempt.outcome = 'rolled_back'
            attempt.detail = _clip(f'{why}; revert {revert[:12]} desplegado'
                                   + ('' if restart.get('ok') else f'; el worker no quedó estable: {restart.get("reason")}'))
            self.mail(state, 'rollback', f'{state.source}: arreglo revertido', [
                f'El arreglo {deploy.get("commit")} se revirtió: {why}.',
                f'Revert {revert} desplegado; worker {"reiniciado" if restart.get("ok") else "con problemas: " + str(restart.get("reason"))}.',
                retry], n=attempt.n)
            self.act(state, 'revertido', why)
            return self.end(state, attempt, closing)
        attempt.detail = _clip(f'{why}; revert {revert[:12]} pusheado')
        if undo['blocked']:
            attempt.outcome, attempt.finished_at = 'deploy_blocked', self.iso()
            subject = f'deploy bloqueado para {state.source}'
            lines = [f'El arreglo de {state.source} se pusheó pero el VPS no lo aceptó: {undo["why"]}.',
                     f'El bot lo revirtió en main ({revert}); el VPS no cambió.',
                     f'Causa diagnosticada: {attempt.root_cause}']
            if closing:
                self.mail(state, 'deploy_blocked', subject, lines, n=attempt.n)
                return
            return self.to_person(state, 'deploy_blocked', subject, undo['why'], lines, n=attempt.n)
        attempt.outcome = 'publish_failed'
        if undo['deploy_it']:
            self.mail(state, 'rollback', f'{state.source}: deploy revertido', [
                f'El deploy del arreglo no terminó bien ({undo["why"]}) y se revirtió en main y en el VPS ({revert}).',
                retry], n=attempt.n)
        self.end(state, attempt, closing)

    def end(self, state: st.IncidentState, attempt: st.Attempt, closing: bool) -> None:
        if closing:
            attempt.finished_at = attempt.finished_at or self.iso()
        else:
            self.failed(state, attempt)

    def stuck(self, state: st.IncidentState, attempt: st.Attempt, why: str, error: Exception) -> None:
        deploy = state.deploy
        sha = deploy.get('commit', '')
        attempt.outcome, attempt.finished_at = 'deploy_blocked', self.iso()
        attempt.detail = _clip(f'{why}; además no se pudo revertir: {error}')
        if deploy.get('stage') == 'reverted':
            lines = [f'El commit {sha} del bot se revirtió en main ({deploy.get("revert")}), pero el revert no se '
                     f'pudo desplegar: {error}.', f'Motivo del revert: {why}.',
                     'Desplegá main a mano (docs/COLLECTOR_REPAIR.md, "Desplegar main a mano").']
        else:
            lines = [f'El commit {sha} del bot está en main y no se pudo revertir solo: {error}.',
                     f'Motivo del revert: {why}.',
                     'Revertilo y desplegá a mano (docs/COLLECTOR_REPAIR.md, "Desplegar main a mano").']
        self.to_person(state, 'deploy_blocked', f'{state.source} necesita un revert a mano', attempt.detail, lines,
                       n=attempt.n)

    # -- dry run -------------------------------------------------------------------------

    def plan(self) -> None:
        """What run() would do, reading only: no claim, no write, no Claude, no git, no VPS."""
        incidents = self.db.active_incidents()
        active = {str(row['id']) for row in incidents}
        for state in self.store.all_open():
            if state.incident_id not in active:
                self.act(state, 'cerraría', 'el monitor cerró el incidente')
        due = False
        for incident in incidents:
            if not str(incident.get('thread_id') or '').startswith(THREAD_PREFIX):
                continue
            state = self.store.load(incident['id'])
            if state is None:
                self.act(incident, 'adoptaría', 'incidente del bot sin estado local')
                due = due or incident.get('status') != 'needs_input'
            elif incident.get('status') == 'needs_input':
                self.act(state, 'esperaría a una persona')
            elif state.phase == 'deployed':
                self.act(state, 'verificaría', (state.deploy or {}).get('commit', ''))
            elif state.phase in ('new', 'waiting') and counted(state) >= self.settings.max_attempts:
                self.act(state, 'se rendiría', f'{counted(state)} intentos')
            elif self.is_due(state):
                self.act(state, 'intentaría', f'intento {counted(state) + 1} de {self.settings.max_attempts}')
                due = True
            else:
                self.act(state, 'esperaría', state.retry_after or state.phase)
        if self.may_start_session() and not due:
            pending = [row for row in incidents if row.get('status') == 'pending' and not row.get('thread_id')]
            for row in pending[:1]:
                self.act(row, 'reclamaría', 'el incidente pendiente más viejo, si el snapshot de salud es fresco')


def status(settings: Settings, deps: Deps | None = None) -> dict:
    """Active incidents (sanitized) and the bot's local state, for --status."""
    from dataclasses import asdict

    from tools.collector_repairs import safe_text

    deps = deps or default_deps(settings)
    store = deps.store or st.Store(settings.state_dir, clock=deps.clock.now)
    incidents = [{key: row.get(key) for key in ('id', 'source', 'status', 'created_at', 'thread_id', 'resolved_at')}
                 | {'problem': safe_text(row.get('problem'), 500), 'note': safe_text(row.get('note'), 500)}
                 for row in deps.db.active_incidents()]
    return {'incidents': incidents, 'local': [asdict(item) for item in store.all_open()],
            'sessions_today': store.sessions_today(), 'enabled': settings.enabled}
