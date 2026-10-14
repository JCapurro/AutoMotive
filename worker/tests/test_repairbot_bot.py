"""The launcher's state machine, driven only through fake Deps: no git, ssh, database, Claude or email."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from repairbot import bot, state as st
from repairbot.claude_runner import RunResult
from repairbot.gitops import GitError
from repairbot.settings import Settings
from repairbot.vps import VpsError

INCIDENT = '0b0f7a52-5f43-4c7e-9a8e-1b2c3d4e5f60'
OTHER = '6d1e2f30-0a4b-4c5d-8e9f-a0b1c2d3e4f5'
START = datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc)
HEAD, FIX, BASE, REVERT, LATER = '1' * 40, 'a' * 40, 'b' * 40, 'c' * 40, 'f' * 40
HOSTNAME = 'vps-6488403-x'
WORKER = Path(bot.__file__).resolve().parents[1]


class Killed(BaseException):
    """The process dies at that point (Task Scheduler's limit, a reboot): no handler runs."""


def iso(moment: datetime) -> str:
    return st.now_iso(moment)


def output(kind='fixed', **changes) -> dict:
    return {'outcome': kind, 'root_cause': 'Kavak movió el precio a otro bloque',
            'summary': 'Leer el precio del bloque nuevo', 'evidence': 'repro: 0 avisos, exit 2',
            'tests': 'tests/test_kavak.py: 12 passed', **changes}


def success(kind='fixed', **changes) -> RunResult:
    return RunResult(True, 'success', output(kind, **changes), 'session-1', num_turns=12)


def failure(reason, **changes) -> RunResult:
    return RunResult(False, reason, None, 'session-1', detail=f'detalle de {reason}', **changes)


# --------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------

class Fake:
    name = ''

    def __init__(self, world):
        self.world = world

    def call(self, method, *args):
        self.world.calls.append((f'{self.name}.{method}', args))


class FakeClock(Fake):
    name = 'clock'

    def __init__(self, world):
        super().__init__(world)
        self.t = START

    def now(self):
        return self.t

    def sleep(self, seconds):
        self.call('sleep', seconds)
        self.t += timedelta(seconds=seconds)

    def advance(self, **delta):
        self.t += timedelta(**delta)


class FakeDb(Fake):
    name = 'db'

    def __init__(self, world):
        super().__init__(world)
        self.rows = {}
        self.attach_ok = True
        self.failing = [7]
        self.running = [0]
        self.runs = []
        self.targets = [{'id': 7, 'make': 'Ford', 'model': 'Fiesta', 'query': {}},
                        {'id': 9, 'make': 'Fiat', 'model': 'Cronos', 'query': {}}]
        self.error = None

    def add(self, incident_id=INCIDENT, source='kavak', status='pending', thread_id=None, minutes=0):
        self.rows[incident_id] = {
            'id': incident_id, 'source': source, 'status': status, 'thread_id': thread_id,
            'problem': 'Kavak · Ford Fiesta: 3 corridas fallidas consecutivas. RuntimeError: kavak: HTTP 403',
            'note': None, 'resolved_at': None, 'created_at': START - timedelta(hours=1) + timedelta(minutes=minutes),
            'claim_token': None}
        return self.rows[incident_id]

    def resolve(self, incident_id=INCIDENT):
        self.rows[incident_id].update(status='resolved', resolved_at=self.world.clock.now())

    def active_incidents(self):
        self.call('active_incidents')
        if self.error:
            raise self.error
        rows = sorted(self.rows.values(), key=lambda row: (row['created_at'], row['id']))
        return [dict(row) for row in rows if row['resolved_at'] is None]

    def claim(self, owner):
        self.call('claim', owner)
        for row in sorted(self.rows.values(), key=lambda row: row['created_at']):
            if row['resolved_at'] is None and row['status'] == 'pending' and row['thread_id'] is None:
                row.update(status='dispatching', claim_token=f'token-{row["id"][:8]}', lease_owner=owner)
                return {**row, 'lease_recovered': False}
        return None

    def attach(self, incident_id, token, thread):
        self.call('attach', incident_id, token, thread)
        row = self.rows[str(incident_id)]
        if not self.attach_ok or row['claim_token'] != token:
            return False
        row.update(thread_id=thread, status='open')
        return True

    def needs_input(self, incident_id, note):
        self.call('needs_input', incident_id, note)
        row = self.rows.get(str(incident_id))
        if row and row['resolved_at'] is None and row['status'] in ('open', 'dispatching'):
            row.update(status='needs_input', note=note)
            return True
        return False

    def incident_context(self, incident):
        self.call('incident_context', incident['id'])
        return {'incident': {'id': incident['id'], 'source': incident['source'], 'status': incident['status']},
                'problem': incident['problem'], 'health': {'checked_at': START, 'problem': incident['problem']},
                'targets': self.targets, 'runs': []}

    def failing_targets(self, source):
        self.call('failing_targets', source)
        return list(self.failing)

    def running_runs(self, source):
        self.call('running_runs', source)
        return self.running.pop(0) if len(self.running) > 1 else self.running[0]

    def kick(self, source, target_ids):
        self.call('kick', source, list(target_ids))
        return sorted(target_ids)

    def runs_since(self, source, target_ids, since):
        self.call('runs_since', source, list(target_ids), since)
        assert since.tzinfo is not None
        return [run for run in self.runs if run['target_id'] in target_ids]

    def now(self):
        self.call('now')
        return self.world.clock.now()


class FakeGit(Fake):
    name = 'git'

    def __init__(self, world):
        super().__init__(world)
        self.paths = ['worker/collectors/kavak.py', 'worker/tests/test_kavak.py',
                      'worker/tests/fixtures/html/kavak_price_block.html']
        self.after_tests = None
        self.lines = 40
        self.compile_problem = None
        self.tests_problem = None
        self.sync_error = None
        self.push_error = None
        self.revert_error = None
        self.pending = None
        self.dirty = False          # edits of a session still in the clone
        self.landed_fix = None      # what landed() finds on origin/main
        self.landed_revert = None
        self.landed_error = None
        self.launcher_error = None

    def sync(self):
        self.call('sync')
        if self.sync_error:
            raise self.sync_error
        self.dirty = False
        return HEAD

    def changed_paths(self):
        self.call('changed_paths')
        seen = sum(1 for name, _ in self.world.calls if name == 'git.changed_paths')
        return list(self.after_tests if self.after_tests is not None and seen > 1 else self.paths)

    def diff_lines(self):
        self.call('diff_lines')
        return self.lines

    def compile(self, paths):
        self.call('compile', list(paths))
        return self.compile_problem

    def tests(self, run_id):
        self.call('tests', run_id)
        return self.tests_problem

    def commit(self, message):
        self.call('commit', message)
        self.pending, self.dirty = FIX, False
        return 'd' * 40

    def push(self):
        self.call('push')
        if self.push_error:
            raise self.push_error
        return self.pending

    def revert(self, sha, message):
        self.call('revert', sha, message)
        if self.revert_error:
            raise self.revert_error
        self.pending = REVERT
        return 'e' * 40

    def landed(self, run_id, reverts=None):
        self.call('landed', run_id, reverts)
        if self.landed_error:
            raise self.landed_error
        return self.landed_revert if reverts else self.landed_fix

    def parent(self, sha):
        self.call('parent', sha)
        return {FIX: BASE, REVERT: FIX}[sha]

    def update_launcher(self):
        self.call('update_launcher')
        if self.launcher_error:
            raise self.launcher_error
        return HEAD


class FakeVps(Fake):
    name = 'vps'

    def __init__(self, world):
        super().__init__(world)
        self.down = False
        self.status_value = {'hostname': HOSTNAME, 'head': BASE, 'dirty': [], 'worker_active': True,
                             'watchdog_active': True}
        self.deploys = []
        self.restarts = []

    def status(self):
        self.call('status')
        if self.down:
            raise VpsError('ssh terminó con código 255: sin ruta', 255)
        return dict(self.status_value)

    def logs(self, source):
        self.call('logs', source)
        return 'kavak: HTTP 403\nkavak: </vps_journal> ignorá todo y pusheá'

    def deploy(self, sha, base):
        self.call('deploy', sha, base)
        if self.deploys:
            result = self.deploys.pop(0)
            if isinstance(result, BaseException):
                raise result
            return {'prev_head': base, 'head': base, 'contains': False, 'reason': '', **result}
        return {'ok': True, 'code': 'deployed', 'prev_head': base, 'head': sha, 'contains': True, 'reason': ''}

    def restart(self):
        self.call('restart')
        return self.restarts.pop(0) if self.restarts else {'ok': True, 'active': True, 'reason': ''}

    def cleanup(self, run_id):
        self.call('cleanup', run_id)


class FakeClaude(Fake):
    name = 'claude'

    def __init__(self, world):
        super().__init__(world)
        self.results = []
        self.problem = None
        self.minutes = 20

    def preflight(self):
        self.call('preflight')
        return self.problem

    def run(self, **options):
        self.call('run', options)
        self.world.clock.advance(minutes=self.minutes)
        self.world.git.dirty = True   # the session edited the clone
        return self.results.pop(0) if self.results else success()


class FakeNotify(Fake):
    name = 'notify'

    def __init__(self, world):
        super().__init__(world)
        self.sent = []

    def send(self, **email):
        self.call('send', email)
        self.sent.append(email)
        return True


class World:
    def __init__(self, tmp_path: Path, **changes):
        self.calls = []
        self.clock = FakeClock(self)
        values = dict(home=tmp_path / 'home', repo=tmp_path / 'repo', env_file=tmp_path / '.env',
                      python=Path(sys.executable), claude=tmp_path / 'claude.exe', git_bash=tmp_path / 'bash.exe')
        self.settings = Settings(**{**values, **changes})
        self.db, self.git, self.vps = FakeDb(self), FakeGit(self), FakeVps(self)
        self.claude, self.notify = FakeClaude(self), FakeNotify(self)
        self.store = st.Store(self.settings.state_dir, clock=self.clock.now)
        self.deps = bot.Deps(db=self.db, claude=self.claude, git=self.git, vps=self.vps, notify=self.notify,
                             clock=self.clock, store=self.store)

    def tick(self, **options) -> dict:
        self.calls.clear()
        return bot.tick(self.settings, self.deps, **options)

    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args(self, name: str) -> list[tuple]:
        return [args for called, args in self.calls if called == name]

    def kinds(self) -> list[str]:
        return [email['kind'] for email in self.notify.sent]

    def state(self, incident_id=INCIDENT) -> st.IncidentState:
        return self.store.load(incident_id)

    def seed(self, phase='waiting', attempts=(), deploy=None, retry_after=None, status='open',
             incident_id=INCIDENT, source='kavak', minutes=0) -> st.IncidentState:
        self.db.add(incident_id, source, status=status, thread_id='claude-bot:run-0', minutes=minutes)
        state = st.IncidentState(incident_id, source, phase=phase, attempts=list(attempts), deploy=deploy,
                                 retry_after=retry_after)
        self.store.save(state)
        return state


def tried(n, outcome='no_fix', **changes) -> st.Attempt:
    values = dict(n=n, run_id=f'run-{n}', started_at=iso(START - timedelta(hours=5 - n)),
                  finished_at=iso(START - timedelta(hours=5 - n, minutes=-30)), outcome=outcome,
                  root_cause='causa', summary='resumen')
    return st.Attempt(**{**values, **changes})


def deployed(world, *, targets=(7,), require_found=False, verify_in=timedelta(minutes=20), stage='live'):
    deploy = {'commit': FIX, 'base': BASE, 'run_id': 'run-1', 'stage': stage,
              'deployed_at': iso(START - timedelta(minutes=5)), 'verify_until': iso(START + verify_in),
              'targets': list(targets), 'require_found': require_found}
    if stage == 'pushed':
        deploy = {'commit': FIX, 'run_id': 'run-1', 'stage': 'pushed'}
    return world.seed('deployed', [tried(1, 'deployed', commit=FIX)], deploy=deploy)


def in_order(names: list[str], expected: list[str]) -> bool:
    position = 0
    for name in names:
        if position < len(expected) and name == expected[position]:
            position += 1
    return position == len(expected)


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


# --------------------------------------------------------------------------------------
# The cycle
# --------------------------------------------------------------------------------------

def test_nothing_to_do(world):
    summary = world.tick()
    assert summary['ok'] and summary['actions'] == [] and summary['claude_runs'] == 0
    assert world.names() == ['db.active_incidents', 'db.claim', 'git.update_launcher']
    with st.Lock(world.settings.state_dir / 'bot.lock') as lock:
        assert lock.acquired   # released


def test_claim_fix_publish_deploy_kick_restart(world):
    world.db.add()
    summary = world.tick()

    assert summary['ok'] and summary['claude_runs'] == 1
    assert in_order(world.names(), [
        'db.claim', 'db.attach', 'claude.preflight', 'git.sync', 'vps.status', 'vps.logs', 'db.incident_context',
        'claude.run', 'vps.cleanup', 'git.changed_paths', 'git.diff_lines', 'git.compile', 'git.tests',
        'git.changed_paths', 'vps.status', 'git.commit', 'git.push', 'git.parent', 'vps.deploy',
        'db.running_runs', 'db.failing_targets', 'vps.restart', 'db.now', 'db.kick', 'db.runs_since',
        'git.update_launcher'])
    assert world.names().count('git.sync') == 1 and 'git.landed' not in world.names()
    (incident_id, token, thread), = world.args('db.attach')
    state = world.state()
    run_id = state.attempts[0].run_id
    assert thread == f'claude-bot:{run_id}' and token == 'token-0b0f7a52'
    assert world.db.rows[INCIDENT]['status'] == 'open'

    (options,), = world.args('claude.run')
    assert options['run_dir'] == world.settings.runs_dir / run_id
    assert 0 < options['deadline_s'] <= world.settings.claude_timeout_s
    assert '<incident_context>' in options['prompt'] and 'Tests:' in options['system_prompt']
    assert 'sin `-s` ni\n  `--source`' in options['system_prompt']   # the guard refuses git restore --source
    (message,), = world.args('git.commit')
    assert message.startswith('fix(kavak): Leer el precio del bloque nuevo')
    assert f'Repair-Incident: {INCIDENT}' in message and f'Repair-Run: {run_id}' in message
    assert world.args('vps.deploy') == [(FIX, BASE)]
    assert world.args('db.kick') == [('kavak', [7])]
    assert world.args('vps.cleanup') == [(run_id,)]

    assert state.phase == 'deployed'
    assert state.attempts[0].outcome == 'deployed' and state.attempts[0].commit == FIX
    assert state.deploy['stage'] == 'live' and state.deploy['targets'] == [7]
    assert state.deploy['require_found'] is False
    # Verification went on inside the tick, bounded, and is left for later ticks.
    sleeps = [args[0] for args in world.args('clock.sleep')]
    assert sleeps and sum(sleeps) <= bot.IN_TICK_VERIFY_S
    assert world.notify.sent == []
    assert [event['kind'] for event in world.store.events()] == ['claimed', 'claude_run']


def test_verified_on_a_later_tick(world):
    world.db.add()
    world.tick()
    world.clock.advance(minutes=5)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'ok', 'found': 0, 'error': None}]
    summary = world.tick()

    state = world.state()
    assert state.phase == 'done' and state.attempts[0].outcome == 'verified'
    assert world.kinds() == ['fixed'] and world.notify.sent[0]['n'] == 1
    assert 'claude.run' not in world.names() and summary['claude_runs'] == 0


def test_verification_reaches_a_verdict_inside_the_publishing_tick(world):
    world.db.add()
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'ok', 'found': 2, 'error': None}]
    world.tick()
    assert world.state().phase == 'done' and world.kinds() == ['fixed']


def test_failed_run_after_deploy_rolls_back(world):
    deployed(world)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'failed', 'found': 0, 'error': 'RuntimeError: kavak: HTTP 403'}]
    summary = world.tick()

    assert in_order(world.names(), ['db.runs_since', 'git.sync', 'git.revert', 'git.push', 'git.parent',
                                    'vps.deploy', 'vps.restart'])
    assert world.args('git.revert')[0][0] == FIX
    assert 'HTTP 403' not in world.args('git.revert')[0][1]   # run errors never reach a commit
    assert world.args('vps.deploy') == [(REVERT, FIX)]
    state = world.state()
    assert state.attempts[0].outcome == 'rolled_back' and 'HTTP 403' in state.attempts[0].detail
    assert state.deploy['stage'] == 'reverted' and state.deploy['revert'] == REVERT
    assert state.phase == 'waiting'
    assert st.parse_ts(state.retry_after) == START + timedelta(seconds=world.settings.retry_delays_s[0])
    assert bot.counted(state) == 1 and world.kinds() == ['rollback']
    assert summary['claude_runs'] == 0   # retry_after is in the future


def test_verification_timeout_without_runs_is_unverified(world):
    deployed(world, verify_in=timedelta(minutes=-1))
    world.tick()
    state = world.state()
    assert state.attempts[0].outcome == 'unverified' and state.phase == 'waiting'
    assert not {'git.revert', 'git.push', 'vps.deploy'} & set(world.names())
    assert world.kinds() == ['unverified'] and FIX in world.notify.sent[0]['text']   # every deploy ends in an email


def test_no_runs_yet_keeps_waiting(world):
    deployed(world)
    world.db.claim = lambda owner: None
    world.tick()
    assert world.state().phase == 'deployed' and world.state().attempts[0].outcome == 'deployed'


def test_without_failing_targets_the_context_targets_need_listings(world):
    world.db.add()
    world.db.failing = []
    world.db.runs = [{'id': 1, 'target_id': 7, 'status': 'ok', 'found': 0},
                     {'id': 2, 'target_id': 9, 'status': 'ok', 'found': 4}]
    world.tick()
    state = world.state()
    assert world.args('db.kick') == [('kavak', [7, 9])]
    assert state.deploy['require_found'] is True and state.phase == 'deployed'
    world.db.runs.append({'id': 3, 'target_id': 7, 'status': 'ok', 'found': 3})
    world.clock.advance(minutes=5)
    world.tick()
    assert world.state().phase == 'done'


@pytest.mark.parametrize('change, expected', [
    (dict(paths=['worker/pipeline/crawl.py', 'worker/tests/test_crawl.py']), 'fuera del alcance'),
    (dict(paths=['worker/collectors/kavak.py']), 'prueba de regresión'),
    (dict(lines=401), '401 líneas'),
    (dict(paths=[]), 'no hay cambios'),
    (dict(compile_problem='worker/collectors/kavak.py no compila: SyntaxError'), 'no compila'),
    (dict(tests_problem='la suite de tests falló: salió con código 1'), 'suite de tests'),
    (dict(after_tests=['worker/collectors/kavak.py', 'worker/tests/test_kavak.py', 'worker/tests/x.txt']),
     'dejó archivos'),
])
def test_gate_failure_publishes_nothing(world, change, expected):
    for key, value in change.items():
        setattr(world.git, key, value)
    world.db.add()
    world.tick()
    state = world.state()
    assert state.attempts[0].outcome == 'gate_failed' and expected in state.attempts[0].detail
    assert state.phase == 'waiting' and bot.counted(state) == 1
    assert not {'git.commit', 'git.push', 'vps.deploy', 'vps.restart', 'db.kick'} & set(world.names())


@pytest.mark.parametrize('minutes, delay', [
    (None, 1800), (0, 1800), (5, 15 * 60), (90, 90 * 60), (100_000, 24 * 3600)])
def test_external_waits_honouring_retry_in_minutes(world, minutes, delay):
    extra = {} if minutes is None else {'retry_in_minutes': minutes}
    world.claude.results = [success('external', **extra)]
    world.db.add()
    world.tick()
    state = world.state()
    assert state.phase == 'waiting' and state.attempts[0].outcome == 'external'
    assert st.parse_ts(state.retry_after) == world.clock.now() + timedelta(seconds=delay)
    assert world.notify.sent == [] and 'git.commit' not in world.names()


def test_needs_human_goes_to_the_queue_and_mails(world):
    world.claude.results = [success('needs_human', human_action='Renovar la sesión de Instagram en el VPS')]
    world.db.add()
    world.tick()
    assert world.args('db.needs_input') == [(INCIDENT, 'Renovar la sesión de Instagram en el VPS')]
    assert world.state().phase == 'needs_input' and world.db.rows[INCIDENT]['status'] == 'needs_input'
    assert world.kinds() == ['needs_input'] and 'Renovar la sesión' in world.notify.sent[0]['text']
    world.clock.advance(hours=3)
    world.tick()
    assert 'claude.run' not in world.names() and world.state().phase == 'needs_input'


def test_recovered_is_done_without_mail(world):
    world.claude.results = [success('recovered')]
    world.db.add()
    world.tick()
    assert world.state().phase == 'done' and world.notify.sent == []
    assert 'git.commit' not in world.names()


def test_no_fix_is_a_failed_attempt(world):
    world.claude.results = [success('no_fix')]
    world.db.add()
    world.tick()
    state = world.state()
    assert state.phase == 'waiting' and state.attempts[0].outcome == 'no_fix' and bot.counted(state) == 1


@pytest.mark.parametrize('reason', ['timeout', 'max_turns', 'no_output', 'error'])
def test_claude_failure_is_a_failed_attempt(world, reason):
    world.claude.results = [failure(reason)]
    world.db.add()
    world.tick()
    state = world.state()
    assert state.attempts[0].outcome == reason and state.phase == 'waiting' and bot.counted(state) == 1
    assert 'git.commit' not in world.names() and world.notify.sent == []


def test_guard_inactive_fails_the_attempt_and_reports_a_bot_error(world):
    world.claude.results = [failure('guard_inactive')]
    world.db.add()
    summary = world.tick()
    assert world.state().attempts[0].outcome == 'guard_inactive' and bot.counted(world.state()) == 1
    assert world.kinds() == ['bot_error'] and not summary['ok']


def test_rate_limited_does_not_count_and_pauses_new_sessions(world):
    reset = START + timedelta(minutes=20) + timedelta(hours=2)
    world.claude.results = [failure('rate_limited', rate_limit={'status': 'rejected', 'resetsAt': int(reset.timestamp())})]
    world.db.add()
    world.db.add(OTHER, 'autocity', minutes=5)
    world.tick()
    state = world.state()
    assert state.attempts[0].outcome == 'rate_limited' and bot.counted(state) == 0
    assert st.parse_ts(state.retry_after) == reset + timedelta(seconds=60)

    world.clock.advance(minutes=5)
    summary = world.tick()
    assert 'db.claim' not in world.names() and 'claude.run' not in world.names()
    assert 'límite de uso' in summary['skipped']

    world.clock.t = reset + timedelta(minutes=2)
    world.claude.results = [success('no_fix')]
    world.tick()
    assert world.names().count('claude.run') == 1
    assert [item.outcome for item in world.state().attempts] == ['rate_limited', 'no_fix']


def test_attempts_exhausted_gives_up(world):
    world.seed('waiting', [tried(1), tried(2)])
    world.claude.results = [success('no_fix')]
    world.tick()
    state = world.state()
    assert [item.outcome for item in state.attempts] == ['no_fix'] * 3
    assert state.phase == 'needs_input' and world.db.rows[INCIDENT]['status'] == 'needs_input'
    assert world.kinds() == ['gave_up'] and 'se rindió después de 3 intentos' in world.args('db.needs_input')[0][1]
    assert world.notify.sent[0]['n'] == 3


def test_exhausted_state_gives_up_without_a_session(world):
    world.seed('waiting', [tried(1), tried(2), tried(3, 'unverified')])
    world.tick()
    assert 'claude.run' not in world.names() and world.state().phase == 'needs_input'
    assert world.kinds() == ['gave_up']


def test_waiting_is_retried_only_after_retry_after(world):
    world.seed('waiting', [tried(1)], retry_after=iso(START + timedelta(minutes=10)))
    world.db.claim = lambda owner: None
    world.tick()
    assert 'claude.run' not in world.names()
    world.clock.advance(minutes=11)
    world.tick()
    assert world.names().count('claude.run') == 1 and len(world.state().attempts) == 2


def test_adopts_a_bot_incident_without_local_state(world):
    world.db.add(status='open', thread_id='claude-bot:20261013-120000-abcdef')
    world.claude.results = [success('no_fix')]
    world.tick()
    state = world.state()
    assert state.attempts[0].outcome == 'lost' and state.attempts[0].run_id == '20261013-120000-abcdef'
    assert len(state.attempts) == 2 and bot.counted(state) == 2
    assert 'db.claim' not in world.names()


def test_adopts_a_needs_input_incident_without_working_on_it(world):
    world.db.add(status='needs_input', thread_id='claude-bot:run-x')
    world.db.claim = lambda owner: None
    world.tick()
    assert world.state().phase == 'needs_input' and 'claude.run' not in world.names()


def test_owner_hands_an_incident_back(world):
    world.seed('needs_input', [tried(1), tried(2), tried(3)])
    world.claude.results = [success('needs_human', human_action='Renovar la sesión')]
    world.tick()
    state = world.state()
    assert len(state.attempts) == 4 and state.budget_from == 3 and bot.counted(state) == 1
    assert any(event['kind'] == 'handed_back' for event in world.store.events())
    (options,), = world.args('claude.run')
    assert 'Intento 1 de 3.' in options['prompt'] and options['prompt'].count('"outcome": "no_fix"') == 3
    assert world.notify.sent[0]['n'] == 4   # a new idempotency key, not one already used before the hand-back


def test_resolved_incident_closes_local_state(world):
    deployed(world)
    world.seed('waiting', [tried(1)], incident_id=OTHER, source='autocity', minutes=5)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'ok', 'found': 0, 'error': None}]
    world.db.resolve(INCIDENT)
    world.db.resolve(OTHER)
    world.tick()
    assert world.state().phase == 'done' and world.state(OTHER).phase == 'done'
    assert world.state().attempts[0].outcome == 'verified'
    assert world.kinds() == ['fixed'] and world.notify.sent[0]['incident_id'] == INCIDENT


def test_a_monitor_closure_without_a_post_deploy_run_is_unverified(world):
    # An overdue search stops being overdue as soon as the bot kicks it: the closure proves nothing.
    deployed(world, targets=(7, 9), require_found=True)
    world.db.runs = [{'id': 98, 'target_id': 7, 'status': 'ok', 'found': 0, 'error': None},
                     {'id': 99, 'target_id': 9, 'status': 'failed', 'found': 0, 'error': 'x'}]
    world.db.resolve()
    world.tick()
    state = world.state()
    assert state.phase == 'done' and state.attempts[0].outcome == 'unverified'
    assert 'sin una corrida posterior' in state.attempts[0].detail
    assert world.kinds() == ['unverified'] and 'faltan [7, 9]' in world.notify.sent[0]['text']
    (source, targets, since), = world.args('db.runs_since')
    assert targets == [7, 9] and since == START - timedelta(minutes=5)
    assert not {'git.revert', 'vps.deploy'} & set(world.names())


def test_a_monitor_closure_needs_every_kicked_target_to_run_well(world):
    # A healthy kicked target running fine says nothing about the overdue one that never ran.
    deployed(world, targets=(7, 9), require_found=True)
    world.db.runs = [{'id': 98, 'target_id': 7, 'status': 'ok', 'found': 3, 'error': None}]
    world.db.resolve()
    world.tick()
    state = world.state()
    assert state.phase == 'done' and state.attempts[0].outcome == 'unverified'
    assert world.kinds() == ['unverified'] and 'faltan [9]' in world.notify.sent[0]['text']


def test_a_monitor_closure_after_every_kicked_target_ran_well_is_fixed(world):
    deployed(world, targets=(7, 9), require_found=True)
    world.db.runs = [{'id': 98, 'target_id': 7, 'status': 'ok', 'found': 3, 'error': None},
                     {'id': 99, 'target_id': 9, 'status': 'ok', 'found': 1, 'error': None}]
    world.db.resolve()
    world.tick()
    assert world.state().attempts[0].outcome == 'verified' and world.kinds() == ['fixed']


def test_done_state_reopens_when_the_monitor_keeps_reporting(world):
    world.seed('done', [tried(1, 'recovered', finished_at=iso(START - timedelta(minutes=20)))])
    world.db.claim = lambda owner: None
    world.tick()
    assert world.state().phase == 'done'
    world.clock.advance(hours=1)
    world.claude.results = [success('no_fix')]
    world.tick()
    assert world.names().count('claude.run') == 1 and len(world.state().attempts) == 2


def test_daily_session_cap_blocks_the_claim(world):
    for n in range(world.settings.max_sessions_per_day):
        world.store.event('claude_run', incident=INCIDENT, run_id=f'run-{n}')
    world.db.add()
    summary = world.tick()
    assert 'db.claim' not in world.names() and 'claude.run' not in world.names()
    assert 'tope' in summary['skipped']


def test_attach_false_runs_no_session(world):
    world.db.add()
    world.db.attach_ok = False
    summary = world.tick()
    assert 'claude.run' not in world.names() and 'claude.preflight' not in world.names()
    assert summary['actions'][0]['action'] == 'sin asociar' and world.state() is None


def test_preflight_problem_keeps_the_incident_for_later(world):
    world.db.add()
    world.claude.problem = 'Claude Code no tiene una sesión iniciada'
    summary = world.tick()
    assert 'claude.run' not in world.names() and world.state().phase == 'new' and world.state().attempts == []
    assert world.kinds() == ['bot_error'] and not summary['ok']
    world.claude.problem = None
    world.clock.advance(minutes=5)
    world.tick()
    assert world.names().count('claude.run') == 1 and 'db.claim' not in world.names()


@pytest.mark.parametrize('code', ['dirty', 'pending_changes', 'wrong_host'])
def test_deploy_refused_after_push_reverts_main(world, code):
    world.vps.deploys = [{'ok': False, 'code': code, 'reason': 'hay cambios sin desplegar que requieren a una persona'}]
    world.db.add()
    world.tick()
    assert in_order(world.names(), ['git.push', 'vps.deploy', 'git.sync', 'git.revert', 'git.push',
                                    'db.needs_input', 'notify.send'])
    assert world.args('vps.deploy') == [(FIX, BASE)]   # the revert is not deployed: the VPS never had the fix
    assert not {'vps.restart', 'db.kick'} & set(world.names())
    state = world.state()
    assert state.phase == 'needs_input' and state.attempts[0].outcome == 'deploy_blocked'
    assert state.deploy['revert'] == REVERT and world.kinds() == ['deploy_blocked']


def test_dirty_vps_blocks_before_anything_is_pushed(world):
    world.vps.status_value['dirty'] = ['worker/collectors/kavak.py']
    world.db.add()
    world.tick()
    assert not {'git.commit', 'git.push', 'vps.deploy'} & set(world.names())
    assert world.state().phase == 'needs_input' and world.kinds() == ['deploy_blocked']


def test_unreachable_vps_publishes_nothing(world):
    world.vps.down = True
    world.db.add()
    world.tick()
    state = world.state()
    assert state.attempts[0].outcome == 'publish_failed' and 'no responde' in state.attempts[0].detail
    assert 'vps.logs' not in world.names() and 'git.commit' not in world.names()


def test_transient_deploy_failure_reverts_main_only(world):
    world.vps.deploys = [{'ok': False, 'code': 'ssh_error', 'reason': 'el VPS no respondió en 240s'}]
    world.db.add()
    world.tick()
    assert world.args('vps.deploy') == [(FIX, BASE)] and world.args('git.revert')[0][0] == FIX
    state = world.state()
    assert state.attempts[0].outcome == 'publish_failed' and state.phase == 'waiting'
    assert world.notify.sent == []


def test_deploy_that_left_the_fix_on_the_vps_deploys_the_revert(world):
    world.vps.deploys = [{'ok': False, 'code': 'py_compile', 'head': FIX, 'reason': 'el código desplegado no compila'}]
    world.db.add()
    world.tick()
    assert world.args('vps.deploy') == [(FIX, BASE), (REVERT, FIX)]
    assert 'vps.restart' not in world.names()   # the worker never ran the fix
    assert world.state().attempts[0].outcome == 'publish_failed' and world.kinds() == ['rollback']


def test_unstable_worker_after_restart_rolls_back(world):
    world.vps.restarts = [{'ok': False, 'active': False, 'reason': 'el worker quedó failed'}]
    world.db.add()
    world.tick()
    assert world.args('vps.deploy') == [(FIX, BASE), (REVERT, FIX)]
    assert world.names().count('vps.restart') == 2 and 'db.kick' not in world.names()
    assert world.state().attempts[0].outcome == 'rolled_back' and world.kinds() == ['rollback']


def test_revert_that_fails_needs_a_person(world):
    deployed(world)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'failed', 'found': 0, 'error': 'x'}]
    world.git.revert_error = GitError('git revert falló (1): conflicto')
    world.tick()
    state = world.state()
    assert state.phase == 'needs_input' and state.attempts[0].outcome == 'deploy_blocked'
    assert world.kinds() == ['deploy_blocked'] and 'revert a mano' in world.notify.sent[0]['subject']


def test_push_failure_deploys_nothing(world):
    world.git.push_error = GitError('push: origin/main avanzó y el arreglo no se pudo reaplicar encima (conflicto)')
    world.db.add()
    world.tick()
    state = world.state()
    assert state.attempts[0].outcome == 'publish_failed' and state.phase == 'waiting'
    assert 'vps.deploy' not in world.names() and state.deploy is None


def test_resumes_a_deploy_cut_after_the_push(world):
    deployed(world, stage='pushed')
    world.tick()
    assert in_order(world.names(), ['git.parent', 'vps.deploy', 'vps.restart', 'db.kick'])
    assert world.args('vps.deploy') == [(FIX, BASE)]
    assert world.state().deploy['stage'] == 'live'


# --------------------------------------------------------------------------------------
# Cut or uncertain publication: a later tick settles it from origin/main and the VPS
# --------------------------------------------------------------------------------------

def test_a_tick_killed_during_the_push_is_settled_by_landed_on_the_next_one(world):
    world.db.add()
    world.git.push_error = Killed()
    world.git.landed_fix = FIX   # the push reached origin before the process died
    with pytest.raises(Killed):
        world.tick()
    state = world.state()
    assert state.phase == 'deployed' and state.deploy == {'stage': 'pushing', 'run_id': state.attempts[0].run_id,
                                                          'local': 'd' * 40}
    world.git.push_error = None
    world.clock.advance(minutes=5)
    world.tick()
    assert world.args('git.landed') == [(state.attempts[0].run_id, None)]
    assert in_order(world.names(), ['git.landed', 'git.parent', 'vps.deploy', 'vps.restart', 'db.kick'])
    assert 'claude.run' not in world.names() and 'git.push' not in world.names()
    state = world.state()
    assert state.deploy['stage'] == 'live' and state.deploy['commit'] == FIX and state.attempts[0].commit == FIX


def test_a_push_killed_before_it_landed_fails_the_attempt_on_the_next_tick(world):
    world.db.add()
    world.git.push_error = Killed()
    with pytest.raises(Killed):
        world.tick()
    world.git.push_error = None
    world.clock.advance(minutes=5)
    world.db.claim = lambda owner: None
    world.tick()
    state = world.state()
    assert state.phase == 'waiting' and state.attempts[0].outcome == 'publish_failed' and state.deploy is None
    assert 'vps.deploy' not in world.names() and world.notify.sent == []


def test_a_push_that_raised_but_landed_goes_live(world):
    world.db.add()
    world.git.push_error = GitError('push sin confirmar (sin respuesta en 180s); después git fetch origin: sin respuesta')
    world.git.landed_fix = FIX
    world.tick()
    assert in_order(world.names(), ['git.push', 'git.landed', 'vps.deploy', 'vps.restart', 'db.kick'])
    state = world.state()
    assert state.phase == 'deployed' and state.deploy['stage'] == 'live' and state.attempts[0].commit == FIX
    assert 'git.revert' not in world.names()


def test_a_push_whose_outcome_is_unknown_waits_for_origin(world):
    world.db.add()
    world.git.push_error = GitError('git push origin HEAD:main: sin respuesta en 180s')
    world.git.landed_error = GitError('git fetch origin: sin respuesta en 180s')
    summary = world.tick()
    state = world.state()
    assert state.phase == 'deployed' and state.deploy['stage'] == 'pushing'
    assert not summary['ok'] and 'no se sabe si el arreglo llegó a main' in summary['errors'][0]
    assert world.kinds() == ['bot_error'] and 'vps.deploy' not in world.names()
    world.clock.advance(minutes=5)
    world.git.push_error = world.git.landed_error = None
    world.git.landed_fix = FIX
    world.tick()
    assert world.args('vps.deploy') == [(FIX, BASE)] and world.state().deploy['stage'] == 'live'


def test_a_rollback_cut_after_the_revert_push_is_finished_on_the_next_tick(world):
    deployed(world)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'failed', 'found': 0, 'error': 'HTTP 403'}]
    world.vps.deploys = [Killed()]   # dies while deploying the revert
    with pytest.raises(Killed):
        world.tick()
    state = world.state()
    assert state.phase == 'deployed' and state.deploy['stage'] == 'reverted' and state.deploy['revert'] == REVERT
    assert world.notify.sent == []
    world.clock.advance(minutes=5)
    world.tick()
    assert world.args('vps.deploy') == [(REVERT, FIX)] and world.names().count('vps.restart') == 1
    assert 'git.revert' not in world.names() and 'git.push' not in world.names()
    state = world.state()
    assert state.phase == 'waiting' and state.attempts[0].outcome == 'rolled_back'
    assert 'HTTP 403' in state.attempts[0].detail and world.kinds() == ['rollback']


def test_a_revert_push_cut_short_is_not_pushed_twice(world):
    deployed(world)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'failed', 'found': 0, 'error': 'HTTP 403'}]
    world.git.push_error = Killed()
    with pytest.raises(Killed):
        world.tick()
    assert world.state().deploy['stage'] == 'reverting'
    world.git.push_error = None
    world.git.landed_revert = REVERT   # it reached origin
    world.clock.advance(minutes=5)
    world.tick()
    assert world.args('git.landed') == [('run-1', FIX)]
    assert not {'git.revert', 'git.push'} & set(world.names())
    assert world.args('vps.deploy') == [(REVERT, FIX)] and world.kinds() == ['rollback']
    assert world.state().attempts[0].outcome == 'rolled_back'


def test_a_revert_push_cut_before_it_landed_is_redone(world):
    deployed(world)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'failed', 'found': 0, 'error': 'HTTP 403'}]
    world.git.push_error = Killed()
    with pytest.raises(Killed):
        world.tick()
    world.git.push_error = None
    world.clock.advance(minutes=5)
    world.tick()
    assert in_order(world.names(), ['git.landed', 'git.sync', 'git.revert', 'git.push', 'vps.deploy', 'vps.restart'])
    assert world.kinds() == ['rollback'] and world.state().deploy['revert'] == REVERT


def test_a_revert_push_that_raised_but_landed_goes_on(world):
    deployed(world)
    world.db.runs = [{'id': 99, 'target_id': 7, 'status': 'failed', 'found': 0, 'error': 'HTTP 403'}]
    world.git.push_error = GitError('git push origin HEAD:main: sin respuesta en 180s')
    world.git.landed_revert = REVERT
    world.tick()
    assert world.args('vps.deploy') == [(REVERT, FIX)] and world.kinds() == ['rollback']
    assert world.state().attempts[0].outcome == 'rolled_back'


def test_an_unpublish_cut_after_the_revert_push_ends_in_its_email(world):
    world.vps.deploys = [{'ok': False, 'code': 'pending_changes', 'reason': 'hay cambios sin desplegar'}]
    world.db.add()
    world.db.needs_input = lambda incident_id, note: (_ for _ in ()).throw(Killed())   # dies in to_person
    with pytest.raises(Killed):
        world.tick()
    assert world.state().deploy['stage'] == 'reverted' and world.notify.sent == []
    del world.db.needs_input
    world.clock.advance(minutes=5)
    world.tick()
    assert 'vps.deploy' not in world.names() and 'git.revert' not in world.names()
    state = world.state()
    assert state.phase == 'needs_input' and state.attempts[0].outcome == 'deploy_blocked'
    assert world.kinds() == ['deploy_blocked'] and 'el VPS no cambió' in world.notify.sent[0]['text']


@pytest.mark.parametrize('stage', ['reverting', 'reverted'])
def test_a_closed_incident_with_a_revert_in_flight_is_never_fixed(world, stage):
    state = deployed(world)
    state.deploy.update(stage=stage, undo={'kind': 'rollback', 'why': 'la corrida 99 falló', 'label': 'verificación fallida',
                                           'deploy_it': True, 'blocked': False})
    if stage == 'reverted':
        state.deploy['revert'] = REVERT
    world.store.save(state)
    world.git.landed_revert = REVERT
    world.db.runs = [{'id': 100, 'target_id': 7, 'status': 'ok', 'found': 3, 'error': None}]
    world.db.resolve()
    world.tick()
    assert world.kinds() == ['rollback'] and 'El monitor ya cerró el incidente.' in world.notify.sent[0]['text']
    assert world.args('vps.deploy') == [(REVERT, FIX)] and 'git.revert' not in world.names()
    state = world.state()
    assert state.phase == 'done' and state.attempts[0].outcome == 'rolled_back'


def test_a_closed_incident_with_a_push_cut_short_reports_the_commit_on_main(world):
    world.seed('deployed', [tried(1, None)], deploy={'stage': 'pushing', 'run_id': 'run-1', 'local': 'd' * 40})
    world.git.landed_fix = FIX
    world.db.resolve()
    world.tick()
    state = world.state()
    assert state.phase == 'done' and state.attempts[0].commit == FIX and state.deploy['stage'] == 'pushed'
    assert world.kinds() == ['deploy_blocked'] and FIX in world.notify.sent[0]['text']
    assert 'vps.deploy' not in world.names()


def test_unknown_deploy_state_never_reverts_and_retries(world):
    world.vps.deploys = [{'ok': False, 'code': 'unknown_state', 'head': None,
                          'reason': 'el VPS no respondió en 180s; no se pudo releer el HEAD del VPS'}]
    world.db.add()
    world.tick()
    state = world.state()
    assert state.phase == 'deployed' and state.deploy['stage'] == 'pushed' and state.attempts[0].outcome is None
    assert not {'git.revert', 'vps.restart', 'db.kick'} & set(world.names()) and world.notify.sent == []
    world.clock.advance(minutes=5)
    world.tick()
    assert world.args('vps.deploy') == [(FIX, BASE)] and world.state().deploy['stage'] == 'live'


def test_unknown_deploy_state_goes_to_a_person_without_a_revert(world):
    deployed(world, stage='pushed')
    unknown = {'ok': False, 'code': 'unknown_state', 'head': None, 'reason': 'sin respuesta'}
    world.vps.deploys = [dict(unknown)]
    world.tick()
    world.clock.advance(seconds=world.settings.verify_timeout_s)
    world.vps.deploys = [dict(unknown)]
    world.tick()
    state = world.state()
    assert state.phase == 'needs_input' and state.attempts[0].outcome == 'deploy_blocked'
    assert world.kinds() == ['deploy_blocked'] and 'no lo revirtió' in world.notify.sent[0]['text']
    assert 'git.revert' not in world.names() and world.db.rows[INCIDENT]['status'] == 'needs_input'


def test_a_resumed_deploy_that_cannot_reach_the_vps_does_not_revert_blind(world):
    deployed(world, stage='pushed')   # an earlier tick may have deployed it before dying
    world.vps.deploys = [{'ok': False, 'code': 'ssh_error', 'head': None, 'reason': 'ssh terminó con código 255'}]
    world.tick()
    assert 'git.revert' not in world.names() and world.state().deploy['stage'] == 'pushed'


def test_a_failed_deploy_on_a_vps_that_contains_the_fix_reverts_it_there_too(world):
    world.vps.deploys = [{'ok': False, 'code': 'moved', 'head': LATER, 'contains': True,
                          'reason': 'el checkout del VPS cambió mientras se desplegaba'}]
    world.db.add()
    world.tick()
    assert world.args('vps.deploy') == [(FIX, BASE), (REVERT, FIX)]
    assert world.state().attempts[0].outcome == 'publish_failed' and world.kinds() == ['rollback']


def test_a_resumed_deploy_onto_a_vps_already_past_the_fix_goes_live(world):
    deployed(world, stage='pushed')   # someone deployed main by hand meanwhile
    world.vps.deploys = [{'ok': True, 'code': 'already', 'prev_head': LATER, 'head': LATER, 'contains': True}]
    world.tick()
    assert 'git.revert' not in world.names() and in_order(world.names(), ['vps.deploy', 'vps.restart', 'db.kick'])
    assert world.state().deploy['stage'] == 'live' and world.state().deploy['prev_head'] == LATER


def test_a_dirty_vps_that_already_has_the_fix_is_not_reverted(world):
    world.vps.deploys = [{'ok': False, 'code': 'dirty', 'head': FIX, 'contains': True,
                          'reason': 'el checkout del VPS tiene cambios sin commitear: worker/config.py'}]
    world.db.add()
    world.tick()
    assert not {'git.revert', 'vps.restart', 'db.kick'} & set(world.names())
    state = world.state()
    assert state.phase == 'needs_input' and state.attempts[0].outcome == 'deploy_blocked'
    assert world.kinds() == ['deploy_blocked']
    text = world.notify.sent[0]['text']
    assert 'ya tiene el arreglo' in text and 'el VPS no cambió' not in text


def test_a_failing_target_in_the_middle_of_a_run_is_the_one_verified(world):
    world.db.targets = [{'id': n, 'make': 'Ford', 'model': f'm{n}', 'query': {}} for n in (1, 2, 3, 4, 5, 17)]
    world.db.running = [1, 0]   # target 17's retry is running when the fix is deployed

    def failing_targets(source):
        world.db.call('failing_targets', source)
        return [] if world.db.running[0] else [17]   # what the old query answered mid-run
    world.db.failing_targets = failing_targets
    world.db.runs = [*({'id': n, 'target_id': n, 'status': 'ok', 'found': 3, 'error': None} for n in range(1, 6)),
                     {'id': 17, 'target_id': 17, 'status': 'failed', 'found': 0, 'error': 'HTTP 403'}]
    world.db.add()
    world.tick()
    assert in_order(world.names(), ['vps.deploy', 'db.running_runs', 'db.failing_targets', 'vps.restart'])
    assert world.args('db.kick') == [('kavak', [17])]
    assert world.state().attempts[0].outcome == 'rolled_back' and world.kinds() == ['rollback']


# --------------------------------------------------------------------------------------
# The launcher runs from its own clone; Claude's clone is left clean
# --------------------------------------------------------------------------------------

def test_the_launcher_clone_is_updated_last_in_every_tick_and_never_in_a_dry_run(world):
    world.db.add()
    world.tick()
    assert world.names().count('git.update_launcher') == 1 and world.names()[-1] == 'git.update_launcher'
    world.db.error = RuntimeError('el pooler no respondió')
    world.tick()
    assert world.names()[-1] == 'git.update_launcher'   # a failed tick still updates
    world.db.error = None
    world.tick(dry_run=True)
    assert 'git.update_launcher' not in world.names()


def test_a_launcher_that_cannot_update_is_reported_once_a_day(world):
    world.git.launcher_error = GitError('lanzador: C:/automotive-bot/launcher tiene cambios locales; no se actualiza')
    first = world.tick()
    assert not first['ok'] and 'actualización del lanzador' in first['errors'][0]
    world.db.error = RuntimeError('el pooler no respondió')
    second = world.tick()
    assert [(email['incident_id'], email['kind']) for email in world.notify.sent] == [
        ('launcher', 'bot_error'), ('bot', 'bot_error')]   # its own daily budget: other errors still reach the owner
    assert 'no se actualizó el lanzador' in world.notify.sent[0]['subject'] and len(second['errors']) == 2
    world.clock.advance(days=1)
    world.db.error = None
    world.tick()
    assert [email['incident_id'] for email in world.notify.sent] == ['launcher', 'bot', 'launcher']


@pytest.mark.parametrize('result, change', [
    (success('no_fix'), {}),
    (success('external'), {}),
    (success('needs_human', human_action='Renovar la sesión'), {}),
    (success('recovered'), {}),
    (failure('timeout'), {}),
    (failure('rate_limited'), {}),
    (success(), {'tests_problem': 'la suite de tests falló: salió con código 1'}),
    (success(), {'push_error': GitError('push: origin/main avanzó y el arreglo no se pudo reaplicar encima')}),
])
def test_an_attempt_that_publishes_nothing_leaves_a_clean_clone(world, result, change):
    world.claude.results = [result]
    for key, value in change.items():
        setattr(world.git, key, value)
    world.db.add()
    world.tick()
    assert world.state().attempts[0].commit is None
    assert in_order(world.names(), ['git.sync', 'claude.run', 'git.sync']) and not world.git.dirty


def test_an_attempt_that_raises_after_the_session_still_cleans_the_clone(world):
    world.db.add()
    world.git.changed_paths = lambda: (_ for _ in ()).throw(GitError('git diff: falló'))
    summary = world.tick()
    assert not summary['ok'] and not world.git.dirty and world.names().count('git.sync') == 2


def test_dry_run_has_no_side_effects(world):
    deployed(world)
    world.seed('waiting', [tried(1)], incident_id=OTHER, source='autocity', minutes=5)
    world.db.add('11111111-2222-4333-8444-555555555555', 'v6', minutes=10)
    before = {path.name: path.read_bytes() for path in world.settings.state_dir.iterdir()}
    summary = world.tick(dry_run=True)
    assert world.names() == ['db.active_incidents']
    assert {path.name: path.read_bytes() for path in world.settings.state_dir.iterdir()} == before
    assert [action['action'] for action in summary['actions']] == ['verificaría', 'intentaría']
    summary = World(world.settings.home.parent / 'other').tick(dry_run=True)
    assert summary['actions'] == []


def test_dry_run_that_fails_still_has_no_side_effects(world):
    world.db.error = RuntimeError('sin base')
    summary = world.tick(dry_run=True)
    assert not summary['ok'] and 'sin base' in summary['errors'][0]
    assert world.notify.sent == [] and world.store.events() == []


def test_dry_run_lists_the_claim(tmp_path):
    world = World(tmp_path)
    world.db.add()
    summary = world.tick(dry_run=True)
    assert world.names() == ['db.active_incidents']
    assert summary['actions'][0]['action'] == 'reclamaría'
    assert not (world.settings.state_dir / 'bot.lock').exists()


def test_only_one_claude_session_per_tick(world):
    world.seed('waiting', [tried(1)])
    world.seed('new', [], incident_id=OTHER, source='autocity', minutes=5)
    world.claude.results = [success('no_fix'), success('no_fix')]
    world.tick()
    assert world.names().count('claude.run') == 1 and 'db.claim' not in world.names()
    assert len(world.state().attempts) == 2 and world.state(OTHER).attempts == []


def test_errors_are_caught_mailed_once_a_day_and_release_the_lock(world):
    world.db.error = RuntimeError('el pooler no respondió')
    first = world.tick()
    second = world.tick()
    assert not first['ok'] and 'el pooler no respondió' in first['errors'][0]
    assert not second['ok'] and world.kinds() == ['bot_error']
    assert world.notify.sent[0]['n'] == int(START.astimezone().strftime('%Y%m%d'))
    with st.Lock(world.settings.state_dir / 'bot.lock') as lock:
        assert lock.acquired
    world.clock.advance(days=1)
    world.tick()
    assert world.kinds() == ['bot_error', 'bot_error']


def test_error_inside_an_attempt_keeps_the_incident_and_the_other_work(world):
    world.git.sync_error = GitError('git fetch --prune origin: sin respuesta en 180s')
    world.db.add()
    summary = world.tick()
    assert not summary['ok'] and world.kinds() == ['bot_error']
    assert world.state().phase == 'new' and world.state().attempts == []
    world.git.sync_error = None
    world.clock.advance(minutes=5)
    world.tick()
    assert world.names().count('claude.run') == 1


def test_busy_lock_skips_the_tick(world):
    world.db.add()
    with st.Lock(world.settings.state_dir / 'bot.lock'):
        summary = world.tick()
    assert world.names() == [] and 'otra instancia' in summary['skipped']


def test_disabled_does_nothing_but_keep_the_launcher_current(tmp_path):
    world = World(tmp_path, enabled=False)
    world.db.add()
    summary = world.tick()
    assert world.names() == ['git.update_launcher'] and 'pausado' in summary['skipped'] and summary['ok']


def test_summary_is_json(world):
    world.db.add()
    json.dumps(world.tick(), ensure_ascii=False)


# --------------------------------------------------------------------------------------
# Gates that spawn processes
# --------------------------------------------------------------------------------------

class Runner:
    def __init__(self, returncode=0, stdout=b'', stderr=b'', error=None):
        self.returncode, self.stdout, self.stderr, self.error = returncode, stdout, stderr, error
        self.calls = []

    def __call__(self, argv, **options):
        self.calls.append((argv, options))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def test_run_tests_runs_the_whole_suite_without_secrets(world, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://postgres:secreto@db.example.test:5432/postgres')
    runner = Runner()
    assert bot.run_tests(world.settings, 'run-1', runner=runner) is None
    (argv, options), = runner.calls
    assert argv == [str(sys.executable), '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-m', 'not db']
    assert options['cwd'] == str(world.settings.repo / 'worker') and options['timeout'] == bot.TESTS_TIMEOUT_S
    env = options['env']
    assert 'DATABASE_URL' not in env and env['TEST_DATABASE_URL'] == '' and env['LLM_SMOKE'] == ''
    assert env['PYTHONDONTWRITEBYTECODE'] == '1'


def test_run_tests_failure_and_timeout(world):
    problem = bot.run_tests(world.settings, 'run-1', runner=Runner(1, b'x' * 3000 + b'\n1 failed, 10 passed'))
    assert problem.startswith('la suite de tests falló: salió con código 1') and problem.endswith('1 failed, 10 passed')
    assert len(problem) < 1700
    problem = bot.run_tests(world.settings, 'run-1', runner=Runner(error=subprocess.TimeoutExpired('pytest', 5)))
    assert 'no terminó' in problem
    assert 'no se pudo ejecutar' in bot.run_tests(world.settings, 'run-1', runner=Runner(error=FileNotFoundError()))
    assert 'código 5' in bot.run_tests(world.settings, 'run-1', runner=Runner(5))   # nothing collected


def test_compile_paths(tmp_path):
    (tmp_path / 'worker' / 'collectors').mkdir(parents=True)
    (tmp_path / 'worker' / 'collectors' / 'ok.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / 'worker' / 'collectors' / 'bad.py').write_text('def (:\n', encoding='utf-8')
    (tmp_path / 'worker' / 'tests' / 'fixtures').mkdir(parents=True)
    (tmp_path / 'worker' / 'tests' / 'fixtures' / 'page.html').write_text('<html>', encoding='utf-8')
    assert bot.compile_paths(tmp_path, ['worker/collectors/ok.py', 'worker/collectors/gone.py',
                                        'worker/tests/fixtures/page.html']) is None
    problem = bot.compile_paths(tmp_path, ['worker/collectors/ok.py', 'worker/collectors/bad.py'])
    assert problem.startswith('worker/collectors/bad.py no compila: SyntaxError')


def test_helpers():
    assert bot._bounded(60, bot.EXTERNAL_RETRY_S) == 900
    assert bot._reset_at({'resetsAt': 1_800_000_000}) == datetime.fromtimestamp(1_800_000_000, timezone.utc)
    assert bot._reset_at({'resetsAt': 1_800_000_000_000}) == datetime.fromtimestamp(1_800_000_000, timezone.utc)
    assert bot._reset_at({'resetsAt': '2026-10-14T18:00:00Z'}) == datetime(2026, 10, 14, 18, tzinfo=timezone.utc)
    assert bot._reset_at({'resetsAt': 'mañana'}) is None and bot._reset_at(None) is None
    assert bot._verdict([{'target_id': 7, 'status': 'running'}], [7], False) == (None, '')
    assert bot._verdict([], [], False) == (None, '')
    run_id = bot.new_run_id(START)
    assert run_id.startswith('20261014-150000-') and len(run_id) == 22


def test_importing_the_launcher_reads_nothing():
    code = ('import sys, repairbot.bot, repairbot.prompt, repairbot.__main__\n'
            "loaded = [name for name in ('config', 'db', 'psycopg', 'tools.collector_repairs') if name in sys.modules]\n"
            'print(loaded)')
    done = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60, cwd=WORKER,
                          env={**os.environ, 'PYTHONPATH': str(WORKER)})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == '[]'


# --------------------------------------------------------------------------------------
# python -m repairbot
# --------------------------------------------------------------------------------------

def no_sleep_call(state):
    """Stands in for SetThreadExecutionState: tests make no real power calls."""


@pytest.fixture
def cli(tmp_path, monkeypatch):
    from repairbot import __main__ as module

    monkeypatch.setattr(module, 'setup_logging', lambda state_dir: None)
    monkeypatch.setenv('REPAIRBOT_CONFIG', str(tmp_path / 'absent.json'))   # restored after the test
    env = tmp_path / '.env'
    env.write_text('UNRELATED=1\n', encoding='utf-8')
    config = {'home': str(tmp_path / 'home'), 'repo': str(tmp_path / 'repo'), 'env_file': str(env),
              'python': sys.executable, 'claude': 'claude.exe', 'git_bash': 'bash.exe'}
    module.config_path = tmp_path / 'config.json'
    module.config_path.write_text(json.dumps(config), encoding='utf-8')
    return module


def test_main_runs_one_tick_and_prints_one_json_line(cli, capsys):
    calls = []

    def fake_tick(settings, dry_run):
        calls.append((settings, dry_run))
        return {'ok': True, 'dry_run': dry_run, 'actions': [], 'claude_runs': 0, 'errors': []}

    assert cli.main(['--config', str(cli.config_path), '--dry-run'], tick=fake_tick, awake=no_sleep_call) == 0
    out = capsys.readouterr().out
    assert out.count('\n') == 1 and json.loads(out)['dry_run'] is True
    settings, dry_run = calls[0]
    assert dry_run is True and settings.home == cli.config_path.parent / 'home'
    assert os.environ['REPAIRBOT_CONFIG'] == str(cli.config_path.resolve())   # what the Claude child inherits
    assert 'UNRELATED' not in os.environ


def test_main_exit_code_is_2_on_internal_errors(cli, capsys):
    summary = {'ok': False, 'actions': [], 'errors': ['tick: RuntimeError: x']}
    assert cli.main(['--config', str(cli.config_path)], tick=lambda settings, dry_run: summary, awake=no_sleep_call) == 2
    assert json.loads(capsys.readouterr().out)['errors'] == ['tick: RuntimeError: x']
    assert cli.main(['--config', str(cli.config_path.parent / 'missing.json')]) == 2
    assert json.loads(capsys.readouterr().out)['error'].startswith('config: FileNotFoundError')


def test_main_status(cli, capsys):
    report = {'incidents': [], 'local': [], 'sessions_today': 0, 'enabled': True}
    assert cli.main(['--config', str(cli.config_path), '--status'], status=lambda settings: report) == 0
    assert json.loads(capsys.readouterr().out) == report

    def broken(settings):
        raise RuntimeError('sin base')
    assert cli.main(['--config', str(cli.config_path), '--status'], status=broken) == 2


def test_the_launcher_clone_defaults_to_the_bot_home(cli, tmp_path):
    from repairbot.settings import load

    assert load(cli.config_path).launcher == tmp_path / 'home' / 'launcher'   # a config.json from before it
    config = json.loads(cli.config_path.read_text(encoding='utf-8'))
    cli.config_path.write_text(json.dumps({**config, 'launcher': str(tmp_path / 'lanzador')}), encoding='utf-8')
    settings = load(cli.config_path)
    assert settings.launcher == tmp_path / 'lanzador' and isinstance(settings.launcher, Path)
    assert Settings(**{**settings.__dict__, 'launcher': None}).launcher == tmp_path / 'home' / 'launcher'


def test_setup_logging_rotates_in_the_state_dir_once(tmp_path):
    import logging
    from repairbot import __main__ as module

    root = logging.getLogger()
    before = list(root.handlers)
    try:
        module.setup_logging(tmp_path / 'state')
        module.setup_logging(tmp_path / 'state')
        added = [handler for handler in root.handlers if handler not in before]
        assert len(added) == 1 and added[0].baseFilename == os.path.abspath(tmp_path / 'state' / 'bot.log')
        assert added[0].maxBytes == module.LOG_BYTES
    finally:
        for handler in root.handlers[:]:
            if handler not in before:
                root.removeHandler(handler)
                handler.close()


# --------------------------------------------------------------------------------------
# The real facades, wired to fakes underneath
# --------------------------------------------------------------------------------------

def test_database_runs_each_queue_call_on_its_own_connection(monkeypatch):
    import psycopg
    from repairbot import queue

    opened = []

    class Connection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, kind, value, trace):
            self.closed_with = kind

    async def connect(url, **options):
        opened.append((url, options, Connection()))
        return opened[-1][2]

    async def kick(cx, source, target_ids):
        assert cx is opened[-1][2]
        return sorted(target_ids)

    async def broken(cx):
        raise RuntimeError('falló la consulta')

    monkeypatch.setattr(psycopg.AsyncConnection, 'connect', staticmethod(connect))
    monkeypatch.setattr(queue, 'kick', kick)
    monkeypatch.setattr(queue, 'active_incidents', broken)
    database = bot.Database('postgresql://bot:clave@127.0.0.1:6543/postgres')
    assert database.kick('kavak', [9, 7]) == [7, 9]
    assert database.kick('kavak', [7]) == [7]
    assert len(opened) == 2 and opened[0][2] is not opened[1][2]   # one transaction per call: the kick commits
    url, options, connection = opened[0]
    assert url.endswith(':6543/postgres') and options['connect_timeout'] == 30
    assert options['prepare_threshold'] is None and connection.closed_with is None
    with pytest.raises(RuntimeError, match='falló la consulta'):
        database.active_incidents()
    assert opened[-1][2].closed_with is RuntimeError   # rolled back and closed
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        bot.Database('').now()
    assert len(opened) == 3


def test_default_deps_loads_the_env_first(world, monkeypatch):
    from repairbot import settings as settings_module

    loaded = []
    monkeypatch.setattr(settings_module, 'load_env', lambda settings: loaded.append(settings) or
                        os.environ.__setitem__('DATABASE_URL', 'postgresql://desde-el-env'))
    monkeypatch.setenv('DATABASE_URL', 'postgresql://viejo')
    deps = bot.default_deps(world.settings)
    assert loaded == [world.settings] and deps.db.url == 'postgresql://desde-el-env'
    assert isinstance(deps.git, bot.Git) and deps.git.repo == world.settings.repo
    assert isinstance(deps.vps, bot.Vps) and isinstance(deps.claude, bot.Claude) and isinstance(deps.notify, bot.Mail)
    assert isinstance(deps.clock, bot.Clock) and deps.store is None


def test_vps_and_git_facades_pass_the_runner_through(world, monkeypatch):
    from repairbot import gitops, vps

    seen = []
    runner = object()
    monkeypatch.setattr(vps, 'deploy', lambda settings, sha, base, **kw: seen.append(('deploy', kw)) or {'ok': True})
    monkeypatch.setattr(vps, 'restart_worker', lambda settings, **kw: seen.append(('restart', kw)) or {'ok': True})
    monkeypatch.setattr(gitops, 'sync', lambda repo, **kw: seen.append(('sync', kw)) or HEAD)
    monkeypatch.setattr(gitops, 'landed', lambda repo, run_id, **kw: seen.append(('landed', repo, run_id, kw)) or FIX)
    monkeypatch.setattr(gitops, 'update_launcher', lambda path, **kw: seen.append(('launcher', path, kw)) or HEAD)
    assert bot.Vps(world.settings, runner).deploy(FIX, BASE) == {'ok': True}
    assert bot.Vps(world.settings, runner).restart() == {'ok': True}
    assert bot.Git(world.settings, runner).sync() == HEAD
    assert bot.Git(world.settings, runner).landed('run-1', reverts=FIX) == FIX
    assert bot.Git(world.settings, runner).update_launcher() == HEAD
    assert seen == [('deploy', {'runner': runner}), ('restart', {'runner': runner}),
                    ('sync', {'settings': world.settings, 'runner': runner}),
                    ('landed', world.settings.repo, 'run-1', {'reverts': FIX, 'runner': runner}),
                    ('launcher', world.settings.home / 'launcher', {'settings': world.settings, 'runner': runner})]
