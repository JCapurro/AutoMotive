"""repairbot.vps without a VPS.

The first half uses a fake ssh runner: what is sent, what is refused before sending, and how
the answers are read. The second half runs the very same scripts in a local bash (Git Bash on
Windows) against a temporary git checkout, with sudo/hostname/systemctl/journalctl stubbed.
"""
import base64
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
from types import SimpleNamespace

import pytest

from repairbot import gitops, vps
from repairbot.settings import Settings
from repairbot.state import Lock
from repairbot.vps import VpsError

HOST = 'vps-6488403-x'
SHA, BASE, OTHER = 'a' * 40, 'b' * 40, 'c' * 40
SSH_ARGV = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'automotive-vps', 'bash', '-s']
FORBIDDEN = ('reset --hard', 'checkout --', 'clean')
REPRO = '''import json, os, sys
print("ruido antes del resultado")
print(json.dumps({
    "argv": sys.argv[1:], "cwd": os.getcwd().replace(chr(92), "/"), "has_tests": os.path.exists("tests"),
    "collector": open("collectors/kavak.py", "rb").read().decode(),
    "files": sorted(name for name in os.listdir("collectors")),
    "env": {key: os.environ.get(key) for key in (
        "DISPLAY", "XAUTHORITY", "FB_STORAGE_STATE", "INSTAGRAM_STORAGE_STATE", "ML_BROWSER_PROFILE_DIR",
        "PYTHONDONTWRITEBYTECODE", "DATABASE_URL")}}))
print("CollectorBlocked: login wall token=abc123", file=sys.stderr)
sys.exit(3)
'''
TREE = {
    '.gitignore': '__pycache__/\n*.log\n.env\n',
    'docs/a.md': 'doc\n',
    'worker/collectors/kavak.py': 'PRICE = "deployed"\n',
    'worker/config.py': 'ROOT = 1\n',
    'worker/tests/test_kavak.py': 'def test_ok():\n    assert True\n',
    'worker/tools/repro_target.py': REPRO,
}


def git(repo, *args) -> str:
    result = subprocess.run(['git', *args], cwd=repo, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
    return result.stdout.decode('utf-8', 'replace').strip()


def write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


def commit_all(repo: Path, message: str, **files) -> str:
    for name, text in files.items():
        write(repo, name, text)
    git(repo, 'add', '-A')
    git(repo, 'commit', '--quiet', '-m', message)
    return git(repo, 'rev-parse', 'HEAD')


def isolate(patch, blank: Path) -> None:
    patch.setenv('GIT_CONFIG_GLOBAL', str(blank))
    patch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    for key in ('REPAIRBOT_CONFIG', 'REPAIRBOT_RUN_ID'):
        patch.delenv(key, raising=False)


def repoint(checkout: Path, old: Path, new: Path) -> None:
    """`git remote set-url origin` for a copied clone, without a git process: its config names
    origin by absolute path, with backslashes escaped."""
    config = checkout / '.git' / 'config'
    escaped = [str(path).replace('\\', '\\\\') for path in (old, new)]
    text = config.read_text(encoding='utf-8')
    assert escaped[0] in text
    config.write_text(text.replace(*escaped), encoding='utf-8')


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    """The bot's clone (no remote needed here), built once and copied per test."""
    root = tmp_path_factory.mktemp('vps')
    (root / 'gitconfig').write_text('', encoding='utf-8')
    with pytest.MonkeyPatch.context() as patch:
        isolate(patch, root / 'gitconfig')
        repo = root / 'repo'
        repo.mkdir()
        git(repo, 'init', '--quiet', '--template=', '--initial-branch=main')   # no sample hooks: quicker copies
        for key, value in (('user.name', 'Test'), ('user.email', 'test@example.test'),
                           ('core.autocrlf', 'true'), ('commit.gpgsign', 'false')):
            git(repo, 'config', key, value)
        commit_all(repo, 'base', **TREE)
    return root


@pytest.fixture
def lean(tmp_path, monkeypatch):
    """The bot's settings without a clone: for calls that must be refused before git runs."""
    isolate(monkeypatch, tmp_path / 'gitconfig')
    repo = tmp_path / 'bot home' / 'repo'
    return Settings(home=repo.parent, repo=repo, env_file=tmp_path / '.env', python=Path(sys.executable),
                    claude=Path('claude'), git_bash=Path('bash'), max_probes=2)


@pytest.fixture
def bot(lean, template):
    shutil.copytree(template / 'repo', lean.repo)
    return lean


@pytest.fixture(scope='module')
def template_tar(template):
    with pytest.MonkeyPatch.context() as patch:
        isolate(patch, template / 'gitconfig')
        return gitops.worktree_tar(template / 'repo', 'worker')


@pytest.fixture
def staged(lean, template_tar, monkeypatch):
    """probe with the untouched clone's snapshot, taken once, for cases where git plays no part.
    Staging a real clone is what the tests that ask for `bot` or `local` check."""
    monkeypatch.setattr(gitops, 'changed_paths', lambda repo, **kw: [])
    monkeypatch.setattr(gitops, 'worktree_tar', lambda repo, prefix='worker', **kw: template_tar)
    return lean


def settings(**changes) -> Settings:
    values = dict(home=Path('home'), repo=Path('repo'), env_file=Path('.env'), python=Path('python'),
                  claude=Path('claude'), git_bash=Path('bash'))
    return Settings(**{**values, **changes})


class FakeSsh:
    """Answers each ssh call with the next canned reply: stdout, (code, stdout, stderr) or an exception."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, argv, **kw):
        self.calls.append(SimpleNamespace(argv=argv, **kw))
        reply = self.replies.pop(0) if self.replies else ''
        if isinstance(reply, BaseException):
            raise reply
        code, out, err = reply if isinstance(reply, tuple) else (0, reply, '')
        return subprocess.CompletedProcess(argv, code, out.encode('utf-8'), err.encode('utf-8'))

    @property
    def scripts(self) -> list[str]:
        return [script_of(call.input)[0] for call in self.calls]


def script_of(wire: bytes) -> tuple[str, bytes]:
    """Split what bash receives into the script text and the payload that follows it."""
    match = re.search(rb'\{ head -c (\d+) >"\$payload"; [^\n]*\n', wire)
    if not match:
        return wire.decode('utf-8'), b''
    payload = wire[match.end():]
    assert len(payload) == int(match[1])
    return wire[:match.end()].decode('utf-8'), payload


def b64(text: str) -> str:
    return base64.b64encode(text.encode('utf-8')).decode('ascii')


def probe_reply(stdout: str, code: int = 0, stderr: str = '') -> str:
    return f'exit={code}\nstdout={b64(stdout)}\nstderr={b64(stderr)}\n'


# --- ssh() and the wire format ------------------------------------------------------------

def test_ssh_argv_script_on_stdin_and_no_launcher_secrets(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://bot:secret@db/app')
    monkeypatch.setenv('RESEND_API_KEY', 're_secret')
    runner = FakeSsh('hola\n')
    assert vps.ssh(settings(), 'echo hola\r\necho chau\r\n', timeout=7, runner=runner) == 'hola\n'
    call = runner.calls[0]
    assert call.argv == SSH_ARGV
    assert call.input == b'set -euo pipefail\nmain() {\necho hola\necho chau\n}\nmain </dev/null\n'
    assert call.timeout == 7 and call.capture_output is True and not getattr(call, 'shell', False)
    assert not {'DATABASE_URL', 'RESEND_API_KEY'} & set(call.env) and 'PATH' in call.env


def test_payload_follows_the_script_with_its_length_and_checksum():
    payload = bytes(range(256)) * 3 + b'\nexit 0\n'
    runner = FakeSsh('')
    vps.ssh(settings(), 'tar -tzf "$payload"', stdin=payload, runner=runner)
    script, sent = script_of(runner.calls[0].input)
    assert sent == payload
    assert script.startswith('set -euo pipefail\nwork=$(mktemp -d)\ntrap \'rm -rf "$work"\' EXIT\n')
    assert f'head -c {len(payload)} >"$payload"' in script
    assert hashlib.sha256(payload).hexdigest() in script
    assert script.rstrip().endswith('main </dev/null; }')


@pytest.mark.parametrize('reply, expected, code', [
    ((255, '', 'ssh: connect to host 149.50.157.195 port 5021: Connection timed out\n'), 'código 255', 255),
    ((1, '', 'fatal: Authorization: Bearer hidden-value\n'), 'código 1', 1),
    (subprocess.TimeoutExpired('ssh', 60), 'no respondió en 60s', None),
    (FileNotFoundError(2, 'ssh'), 'FileNotFoundError', None),
])
def test_ssh_failures_become_sanitized_errors(reply, expected, code):
    with pytest.raises(VpsError, match=expected) as error:
        vps.ssh(settings(), 'true', runner=FakeSsh(reply))
    assert error.value.code == code and 'hidden-value' not in str(error.value)


def test_render_quotes_every_value():
    rendered = vps.render('run __ONE__ __TWO_WORDS__ __LIST__ "${a[@]}" $@ __init__x', one='/opt/x',
                          two_words="it's; rm -rf /", list=['a b', '$(id)', 5])
    assert rendered == '''run /opt/x 'it'"'"'s; rm -rf /' 'a b' '$(id)' 5 "${a[@]}" $@ __init__x'''
    with pytest.raises(KeyError):
        vps.render('__MISSING__')


@pytest.mark.parametrize('changes', [
    dict(ssh_host='-oProxyCommand=calc'), dict(ssh_host='host; id'), dict(ssh_host=''),
    dict(vps_root='/opt/automotive; id'), dict(vps_root='opt/automotive'), dict(vps_root='/opt/../etc'),
    dict(vps_root='/opt/auto motive'), dict(vps_root='/'), dict(vps_hostname='x$(id)'), dict(vps_hostname=''),
])
def test_malformed_configuration_never_reaches_ssh(changes):
    runner = FakeSsh()
    with pytest.raises(VpsError, match='inválido'):
        vps.status(settings(**changes), runner=runner)
    assert vps.deploy(settings(**changes), SHA, BASE, runner=runner)['ok'] is False
    assert runner.calls == []


# --- status / logs / restart / cleanup --------------------------------------------------

def test_status_reads_the_facts():
    runner = FakeSsh(f'hostname={HOST}\nhead={SHA}\nworker=active\nwatchdog=inactive\n'
                     'dirty= M worker/collectors/kavak.py\ndirty=M  docs/a b.md\nruido sin clave\n')
    assert vps.status(settings(), runner=runner) == {
        'hostname': HOST, 'head': SHA, 'dirty': ['worker/collectors/kavak.py', 'docs/a b.md'],
        'worker_active': True, 'watchdog_active': False}
    script = runner.scripts[0]
    assert script.startswith('set -euo pipefail\n') and runner.calls[0].argv == SSH_ARGV
    assert 'cd /opt/automotive\n' in script
    assert 'sudo -u automotive -H git status --porcelain --untracked-files=no' in script
    assert 'systemctl is-active automotive-worker.service' in script
    assert 'systemctl is-active automotive-watchdog.timer' in script


def test_status_without_head_or_connection_is_an_error():
    with pytest.raises(VpsError, match='incompleto'):
        vps.status(settings(), runner=FakeSsh(f'hostname={HOST}\nhead=\n'))
    with pytest.raises(VpsError, match='255'):
        vps.status(settings(), runner=FakeSsh((255, '', 'timeout')))


def test_logs_filters_by_source_and_sanitizes_every_line(monkeypatch):
    from tools import collector_repairs
    monkeypatch.setattr(collector_repairs.config, 'DATABASE_URL', 'postgresql://bot:hunter2@db.internal/app')
    journal = ''.join(f'2026-10-13T12:{i % 60:02d}:00-0300 vps main[1]: target={i} kavak Ford/Ka found=3\n'
                      for i in range(150))
    journal += ('2026-10-13T13:00:00-0300 vps main[1]: kavak GET https://u:pwd@kavak.test/x?token=abc123 -> 403\n'
                '2026-10-13T13:00:01-0300 vps main[1]: kavak conectando a postgresql://bot:hunter2@db.internal/app\n'
                '2026-10-13T13:00:02-0300 vps main[1]: target=7 kavak failed: CollectorBlocked: HTTP 403\n')
    runner = FakeSsh(journal)
    text = vps.logs(settings(), 'kavak', runner=runner)
    lines = text.split('\n')
    assert len(lines) == 153 and len(text) > 2000          # not cut down to safe_text's 2000 characters
    assert lines[0].endswith('target=0 kavak Ford/Ka found=3')
    assert lines[-1].endswith('target=7 kavak failed: CollectorBlocked: HTTP 403')
    for secret in ('pwd', 'abc123', 'hunter2'):
        assert secret not in text
    assert 'kavak.test/x' in text
    script = runner.scripts[0]
    assert 'journalctl -u automotive-worker.service --since=-180min --no-pager' in script
    assert 'grep -a -i -e kavak ||' in script and 'tail -n 150' in script


def test_logs_of_an_instagram_backed_source_also_match_the_shared_collector():
    runner = FakeSsh('', '')
    assert vps.logs(settings(), 'sc_clasificados', minutes=30, max_lines=20, runner=runner) == ''
    assert 'grep -a -i -e sc_clasificados -e instagram ||' in runner.scripts[0]
    assert '--since=-30min' in runner.scripts[0] and 'tail -n 20' in runner.scripts[0]
    vps.logs(settings(), 'fuente_nueva', runner=runner)
    assert 'grep -a -i -e fuente_nueva ||' in runner.scripts[1]


@pytest.mark.parametrize('kw', [
    dict(source='kavak; id'), dict(source='$(id)'), dict(source='-e'), dict(source=''), dict(source='a' * 65),
    dict(source='kavak\nid'), dict(source=None), dict(source='kavak', minutes='5; id'),
    dict(source='kavak', minutes=0), dict(source='kavak', minutes=True), dict(source='kavak', max_lines=10**6),
])
def test_logs_rejects_malformed_arguments_before_any_ssh_call(kw):
    runner = FakeSsh()
    with pytest.raises(VpsError, match='inválido'):
        vps.logs(settings(), runner=runner, **kw)
    assert runner.calls == []


def test_restart_worker_reports_whether_the_service_stays_up():
    runner = FakeSsh('state=active\nstable=1\n', 'state=activating\nstable=0\n', 'state=active\nstable=0\n',
                     'fail=wrong_host\n', (255, '', 'sin conexión'))
    assert vps.restart_worker(settings(), runner=runner) == {'ok': True, 'active': True, 'reason': ''}
    crashed = vps.restart_worker(settings(), runner=runner)
    assert (crashed['ok'], crashed['active']) == (False, False) and 'activating' in crashed['reason']
    looping = vps.restart_worker(settings(), runner=runner)
    assert (looping['ok'], looping['active']) == (False, True) and looping['reason']
    assert vps.restart_worker(settings(), runner=runner)['ok'] is False
    unreachable = vps.restart_worker(settings(), runner=runner)
    assert (unreachable['ok'], unreachable['active']) == (False, False) and '255' in unreachable['reason']
    script = runner.scripts[0]
    assert f'[ "$(hostname)" = {HOST} ]' in script
    assert 'systemctl restart automotive-worker.service' in script
    assert 'systemctl is-active automotive-worker.service' in script
    assert runner.calls[0].timeout >= 120   # a restart waits for the stop timeout of the unit


def test_cleanup_removes_only_the_run_staging_and_never_raises_for_the_vps(caplog):
    runner = FakeSsh('done=1\n', (255, '', 'sin conexión'), 'fail=wrong_host\n')
    assert vps.cleanup(settings(), 'run-20261013-1', runner=runner) is None
    assert 'sudo -u automotive -H rm -rf -- /opt/automotive/.repairbot/run-20261013-1\n' in runner.scripts[0]
    assert f'[ "$(hostname)" = {HOST} ]' in runner.scripts[0]
    with caplog.at_level(logging.WARNING, logger='repairbot.vps'):
        vps.cleanup(settings(), 'run-1', runner=runner)
        vps.cleanup(settings(), 'run-1', runner=runner)
    assert caplog.text.count('no se limpió el staging de run-1') == 2
    for bad in ('', '..', '../x', 'a/b', 'run 1', '-rf', 'x' * 65, 'run;id', None):
        with pytest.raises(VpsError, match='run_id'):
            vps.cleanup(settings(), bad, runner=runner)
    assert len(runner.calls) == 3


# --- deploy --------------------------------------------------------------------------------

def facts(head=BASE, *lines, host=HOST) -> str:
    return '\n'.join([f'hostname={host}', f'head={head}', *lines, ''])


APPLIED = f'head={SHA}\ndone=1\n'
LOST = subprocess.TimeoutExpired('ssh', 180)
DEPLOY_CASES = {
    # name: (replies, base, expected ok, code, prev_head, head, contains, ssh calls, reason fragment)
    'wrong hostname': (['hostname=otro-servidor\n'], BASE, False, 'wrong_host', None, None, False, 1, 'otro-servidor'),
    'dirty tree': ([facts(BASE, 'contains=0', 'dirty= M worker/collectors/kavak.py', 'dirty=M  worker/x.py')], BASE,
                   False, 'dirty', BASE, BASE, False, 1, 'worker/collectors/kavak.py, worker/x.py'),
    'dirty tree already on the commit': ([facts(SHA, 'contains=1', 'dirty= M worker/x.py')], BASE,
                                         False, 'dirty', SHA, SHA, True, 1, 'worker/x.py'),
    'dirty tree past the commit': ([facts(OTHER, 'contains=1', 'dirty= M worker/x.py')], BASE,
                                   False, 'dirty', OTHER, OTHER, True, 1, 'worker/x.py'),
    'prev == base': ([facts(BASE, 'on_main=1'), APPLIED], BASE, True, 'deployed', BASE, SHA, True, 2, ''),
    'undeployed docs and web only': ([facts(OTHER, 'on_main=1', 'pending=docs/COLLECTOR_REPAIR.md',
                                            'pending=web/app/page.tsx', 'pending=README.md'), APPLIED], BASE,
                                     True, 'deployed', OTHER, SHA, True, 2, ''),
    'undeployed worker change': ([facts(OTHER, 'on_main=1', 'pending=docs/a.md', 'pending=worker/pipeline/crawl.py')],
                                 BASE, False, 'pending_changes', OTHER, OTHER, False, 1,
                                 'requieren a una persona: worker/pipeline/crawl.py'),
    'undeployed migration': ([facts(OTHER, 'on_main=1', 'pending=supabase/migrations/20261017_x.sql')], BASE,
                             False, 'pending_changes', OTHER, OTHER, False, 1, 'supabase/migrations/20261017_x.sql'),
    'undeployed quoted worker path': ([facts(OTHER, 'on_main=1', 'pending="worker/a\\303\\261o.py"')], BASE,
                                      False, 'pending_changes', OTHER, OTHER, False, 1, 'requieren a una persona'),
    'already deployed': ([facts(SHA, 'contains=1')], BASE, True, 'already', SHA, SHA, True, 1, 'ya estaba'),
    'already contained by a later commit': ([facts(OTHER, 'contains=1', 'pending=worker/collectors/kavak.py')], BASE,
                                            True, 'already', OTHER, OTHER, True, 1, 'ya contiene'),
    'commit not fetched': ([facts(BASE, 'missing=1')], BASE, False, 'missing_commit', BASE, BASE, False, 1, 'push'),
    'commit outside main': ([facts(BASE, 'on_main=0')], BASE, False, 'not_on_main', BASE, BASE, False, 1,
                            'origin/main'),
    'ff failure': ([facts(BASE, 'on_main=1'),
                    f'head={BASE}\nfail=ff_failed\ndetail={b64("fatal: Not possible to fast-forward, aborting.")}\n'],
                   BASE, False, 'ff_failed', BASE, BASE, False, 2, 'Not possible to fast-forward'),
    'HEAD mismatch': ([facts(BASE, 'on_main=1'), f'head={OTHER}\nfail=head_mismatch\n'], BASE,
                      False, 'head_mismatch', BASE, OTHER, False, 2, 'commit esperado'),
    'unconfirmed HEAD': ([facts(BASE, 'on_main=1'), f'head={OTHER}\ndone=1\n'], BASE,
                         False, 'ssh_error', BASE, OTHER, False, 2, 'no confirmó'),
    'checkout moved meanwhile': ([facts(BASE, 'on_main=1'), 'fail=moved\n', f'head={OTHER}\ncontains=0\n'], BASE,
                                 False, 'moved', BASE, OTHER, False, 3, 'cambió'),
    'checkout moved onto the commit': ([facts(BASE, 'on_main=1'), 'fail=moved\n', f'head={OTHER}\ncontains=1\n'],
                                       BASE, False, 'moved', BASE, OTHER, True, 3, 'cambió'),
    'apply answer without HEAD': ([facts(BASE, 'on_main=1'), '', f'head={SHA}\ncontains=1\n'], BASE,
                                  False, 'ssh_error', BASE, SHA, True, 3, 'no confirmó'),
    'py_compile': ([facts(BASE, 'on_main=1'),
                    f'head={SHA}\nfail=py_compile\ndetail={b64("SyntaxError: invalid syntax (kavak.py, line 3)")}\n'],
                   BASE, False, 'py_compile', BASE, SHA, True, 2, 'SyntaxError'),
    'unreachable': ([(255, '', 'ssh: connect to host: Connection timed out')], BASE,
                    False, 'ssh_error', None, None, False, 1, '255'),
    # The merge ran but its answer was lost: the HEAD read afterwards is the truth.
    'connection lost after the merge': ([facts(BASE, 'on_main=1'), LOST, f'head={SHA}\ncontains=1\n'], BASE,
                                        False, 'ssh_error', BASE, SHA, True, 3, 'no respondió'),
    # ...but a HEAD still at base proves nothing: the remote merge may still be running.
    'connection lost before the merge': ([facts(BASE, 'on_main=1'), LOST, f'head={BASE}\ncontains=0\n'], BASE,
                                         False, 'unknown_state', BASE, BASE, False, 3, 'pudo quedar en curso'),
    'connection lost for good': ([facts(BASE, 'on_main=1'), LOST, (255, '', 'Connection timed out')], BASE,
                                 False, 'unknown_state', BASE, None, False, 3, 'puede haber quedado o no'),
    'connection lost, wrong server on the second read': ([facts(BASE, 'on_main=1'), LOST, 'fail=wrong_host\n'],
                                                         BASE, False, 'unknown_state', BASE, None, False, 3,
                                                         'no se pudo releer'),
    'no HEAD reported': ([f'hostname={HOST}\n'], BASE, False, 'ssh_error', None, None, False, 1, 'HEAD'),
    'garbled detail': ([facts(BASE, 'on_main=1'), f'head={BASE}\nfail=ff_failed\ndetail=%%%\n'], BASE,
                       False, 'ssh_error', BASE, BASE, False, 2, 'ilegible'),
}


@pytest.mark.parametrize('name', DEPLOY_CASES)
def test_deploy_decision_table(name):
    replies, base, ok, code, prev_head, head, contains, calls, fragment = DEPLOY_CASES[name]
    runner = FakeSsh(*replies)
    result = vps.deploy(settings(), SHA, base, runner=runner)
    assert set(result) == {'ok', 'prev_head', 'head', 'contains', 'reason', 'code'}
    assert (result['ok'], result['code'], result['prev_head'], result['head'], result['contains']) == (
        ok, code, prev_head, head, contains)
    assert fragment in result['reason'] and bool(result['reason']) == (code != 'deployed')
    assert len(runner.calls) == calls                       # a refusal never sends the merge
    assert all(call.argv == SSH_ARGV for call in runner.calls)
    for script in runner.scripts:
        assert script.startswith('set -euo pipefail\n')
        assert not [word for word in FORBIDDEN if word in script]
        as_automotive(script)
    assert 'merge --ff-only' not in runner.scripts[0]
    for script in runner.scripts[2:]:                       # a second read never merges again
        assert 'merge --ff-only' not in script and 'fetch' not in script
        assert f'sudo -u automotive -H git merge-base --is-ancestor {SHA} "$head"' in script


def as_automotive(script: str) -> None:
    """Every git and python invocation of a script runs through sudo -u automotive -H."""
    for line in script.replace('\\\n', ' ').splitlines():   # a continued line is one command
        for command in re.split(r'\$\(|\||&&|;|\bthen\b|\bif\b|!', line):
            if re.search(r'(^|\s)(git|\S*python)\s', command):
                assert 'sudo -u automotive -H' in command, line


def test_deploy_scripts_follow_the_step_list():
    runner = FakeSsh(facts(OTHER, 'on_main=1', 'pending=docs/a.md'), APPLIED)
    assert vps.deploy(settings(), SHA, BASE, runner=runner)['ok']
    inspect, apply = runner.scripts
    order = [f'[ "$host" = {HOST} ] || exit 0', 'cd /opt/automotive',
             'sudo -u automotive -H git rev-parse HEAD',
             f'sudo -u automotive -H git merge-base --is-ancestor {SHA} "$head"',   # before the dirty exit
             'sudo -u automotive -H git status --porcelain --untracked-files=no',
             '[ "$contains" = 0 ] || exit 0',
             'sudo -u automotive -H env GIT_TERMINAL_PROMPT=0 timeout 120 git fetch --quiet origin',
             f'sudo -u automotive -H git merge-base --is-ancestor {SHA} origin/main',
             f'diff --name-only "$head" {BASE}']
    assert [inspect.index(step) for step in order] == sorted(inspect.index(step) for step in order)
    order = [f'[ "$(hostname)" = {HOST} ]', 'cd /opt/automotive',
             f'[ "$(sudo -u automotive -H git rev-parse HEAD)" = {OTHER} ]',     # the state that was inspected
             '[ -z "$(sudo -u automotive -H git status --porcelain --untracked-files=no)" ]',
             f'sudo -u automotive -H git merge --ff-only {SHA}',
             f'[ "$head" = {SHA} ]',
             f"git diff --name-only --diff-filter=ACMR -z {OTHER} {SHA} -- '*.py'",
             'xargs -0 -r sudo -u automotive -H /opt/automotive/.venv/bin/python -m py_compile']
    assert [apply.index(step) for step in order] == sorted(apply.index(step) for step in order)
    for script in (inspect, apply):
        as_automotive(script)
        assert 'systemctl' not in script                    # restarting is a separate, later step


@pytest.mark.parametrize('sha, base', [
    ('', BASE), ('HEAD', BASE), ('main', BASE), (SHA[:39], BASE), (SHA + 'a', BASE), ('A' * 40, BASE),
    (SHA + '; id', BASE), ('$(id)', BASE), (None, BASE), (SHA, ''), (SHA, 'origin/main'), (SHA, BASE[:7]),
    (SHA, f'{BASE}\nid'), (SHA, None), ('--upload-pack=x', BASE),
])
def test_deploy_rejects_malformed_shas_before_any_ssh_call(sha, base):
    runner = FakeSsh()
    with pytest.raises(VpsError, match='inválido'):
        vps.deploy(settings(), sha, base, runner=runner)
    assert runner.calls == []


# --- probe ---------------------------------------------------------------------------------

def test_probe_stages_the_clone_and_returns_the_parsed_result(bot):
    write(bot.repo, 'worker/collectors/kavak.py', 'PRICE = "candidate"\r\n')
    write(bot.repo, 'worker/collectors/nuevo.py', 'x = 1\r\n')
    write(bot.repo, 'worker/tests/test_nuevo.py', 'def test_x():\n    assert 1\n')
    write(bot.repo, 'worker/collectors/__pycache__/kavak.cpython-312.pyc', 'bytecode')
    write(bot.repo, 'worker/.env', 'DATABASE_URL=x\n')
    write(bot.repo, 'worker/debug.log', 'ignored\n')
    found = {'source': 'kavak', 'target_id': 5, 'found': 12, 'complete': True, 'error': None, 'sample': []}
    runner = FakeSsh(probe_reply('aviso suelto\n' + json.dumps(found) + '\n', 0,
                                 'DeprecationWarning: x\nGET https://u:pwd@kavak.test/x?token=abc123\n'))
    result = vps.probe(bot, bot.repo, 'kavak', target_id=5, filters=None, run_id='run-1', runner=runner)
    assert result == {**found, 'supported': True, 'exit_code': 0, 'probes_left': 1,
                      'stderr_tail': result['stderr_tail']}
    assert 'DeprecationWarning: x' in result['stderr_tail'] and 'kavak.test/x' in result['stderr_tail']
    assert 'pwd' not in result['stderr_tail'] and 'abc123' not in result['stderr_tail']
    assert json.loads((bot.runs_dir / 'run-1' / 'probe-1.json').read_text(encoding='utf-8')) == result
    assert (bot.runs_dir / 'run-1' / 'probes').read_text() == '1'

    call = runner.calls[0]
    script, payload = script_of(call.input)
    assert call.argv == SSH_ARGV and script.startswith('set -euo pipefail\n')
    assert call.timeout == 420 + 90                         # the remote `timeout` fires first
    for expected in (
            f'[ "$(hostname)" = {HOST} ]',
            'stage=/opt/automotive/.repairbot/run-1\n',
            'sudo -u automotive -H mkdir -p /opt/automotive/.repairbot "$stage"\n',
            'sudo -u automotive -H chmod 0700 /opt/automotive/.repairbot "$stage"\n',
            'sudo -u automotive -H rm -rf -- "$stage/worker"\n',
            'sudo -u automotive -H tar -xzf - -C "$stage" --no-same-owner <"$payload"\n',
            'sudo -u automotive -H chmod 0700 "$stage/worker"\n',
            'cd "$stage/worker"\n',
            'sudo -u automotive -H env DISPLAY=:99 XAUTHORITY=/home/automotive/.Xauthority ',
            'FB_STORAGE_STATE=/opt/automotive/fb_state.json ',
            'INSTAGRAM_STORAGE_STATE=/opt/automotive/ig_state.json ',
            'ML_BROWSER_PROFILE_DIR=/opt/automotive/.ml_chrome_profile ',
            'timeout --kill-after=20 420 /opt/automotive/.venv/bin/python -m tools.repro_target '
            'kavak --target-id 5 --json ${filters[@]+"${filters[@]}"}'):
        assert expected in script, expected
    as_automotive(script)
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as archive:
        members = {member.name: member for member in archive}
        contents = {name: archive.extractfile(member).read() for name, member in members.items()}
    assert sorted(members) == ['worker/collectors/kavak.py', 'worker/collectors/nuevo.py', 'worker/config.py',
                               'worker/tools/repro_target.py']   # no tests, bytecode, .env or logs
    assert contents['worker/collectors/kavak.py'] == b'PRICE = "candidate"\n'   # LF for Linux
    assert contents['worker/collectors/nuevo.py'] == b'x = 1\n'
    assert {(member.mode, member.uid, member.gid, member.uname) for member in members.values()} == {(0o644, 0, 0, '')}


def test_probe_filters_travel_as_base64_json_and_are_never_part_of_the_script(staged):
    hostile = {'marca': 'Ford Ka', 'modelo': '\'; touch /tmp/pwned; echo "$(id)" `id` \\', 'anio_min': 2015,
               'km_max': 80000.5, 'inventory': True, 'solo_nuevos': False, 'sin_valor': None, 'texto': 'año ñ'}
    runner = FakeSsh(probe_reply('{"found": 0}'))
    vps.probe(staged, staged.repo, 'kavak', target_id=None, filters=hostile, run_id='run-1', runner=runner)
    script = runner.scripts[0]
    for text in ('Ford Ka', 'touch', 'pwned', '$(id)', '`id`', 'año'):
        assert text not in script
    blob = re.search(r"\.encode\(\)\)' (\S+)\)\n", script)[1]
    assert json.loads(base64.b64decode(blob)) == {
        'marca': 'Ford Ka', 'modelo': hostile['modelo'], 'anio_min': '2015', 'km_max': '80000.5',
        'inventory': '1', 'solo_nuevos': '0', 'texto': 'año ñ'}
    assert '[ "${#filters[@]}" -eq 7 ]' in script
    assert '-m tools.repro_target kavak --no-db --json ${filters' in script   # no target: nothing to read from the base


@pytest.mark.parametrize('kw', [
    dict(source='kavak; id'), dict(source='$(reboot)'), dict(source='../x'), dict(source=''), dict(source='--json'),
    dict(source=None), dict(run_id='../../etc'), dict(run_id='run 1'), dict(run_id=''), dict(run_id='x' * 65),
    dict(run_id='run-1\nid'), dict(run_id='-rf'), dict(target_id='5; id'), dict(target_id=0), dict(target_id=-1),
    dict(target_id=True), dict(target_id=5.0), dict(timeout='420; id'), dict(timeout=5), dict(timeout=10**6),
    dict(filters='marca=Ford'), dict(filters=[('marca', 'Ford')]), dict(filters={'marca; id': 'x'}),
    dict(filters={'--json': 'x'}), dict(filters={'': 'x'}), dict(filters={5: 'x'}), dict(filters={'a b': 'x'}),
    dict(filters={'marca': ['Ford']}), dict(filters={'marca': {'x': 1}}), dict(filters={'marca': 'x' * 201}),
    dict(filters={'marca': 'Ford\nKa'}), dict(filters={'marca': 'Ford\x00'}), dict(filters={'marca': 'a\x1b[0m'}),
    dict(filters={f'k{i}': 1 for i in range(25)}),
])
def test_probe_rejects_malformed_arguments_before_any_ssh_call(lean, kw):
    runner = FakeSsh()
    values = {'source': 'kavak', 'target_id': 5, 'filters': None, 'run_id': 'run-1', **kw}
    with pytest.raises(VpsError, match='inválido|filtro'):   # there is no clone: git never ran
        vps.probe(lean, lean.repo, values.pop('source'), runner=runner, **values)
    assert runner.calls == []
    assert not (lean.runs_dir / 'run-1' / 'probes').exists()   # a rejected call does not use up a probe


def test_probe_counter_caps_the_probes_of_a_run(staged):
    runner = FakeSsh(probe_reply('{"found": 1}'), (255, '', 'sin conexión'), probe_reply('{"found": 1}'))
    probe = lambda run_id='run-1': vps.probe(staged, staged.repo, 'kavak', target_id=5, filters=None,
                                              run_id=run_id, runner=runner)
    assert probe()['probes_left'] == 1
    with pytest.raises(VpsError, match='255'):
        probe()                                             # a failed connection still counts
    counter = staged.runs_dir / 'run-1' / 'probes'
    assert counter.read_text() == '2'
    for _ in range(2):
        with pytest.raises(VpsError, match='tope de 2 probes'):
            probe()
    assert len(runner.calls) == 2 and counter.read_text() == '2'
    assert probe('run-2')['probes_left'] == 1               # the cap is per run
    counter.write_bytes('no es un número'.encode('utf-8'))   # unreadable: it cannot grant more probes
    with pytest.raises(VpsError, match='tope'):
        probe()
    assert len(runner.calls) == 3


def test_probe_declines_an_unsupported_source_without_touching_the_vps(lean, monkeypatch):
    assert vps.UNSUPPORTED == {}                            # Mercado Libre is plain HTTP now
    monkeypatch.setitem(vps.UNSUPPORTED, 'mercadolibre', 'no se reproduce acá')
    runner = FakeSsh()
    result = vps.probe(lean, lean.repo, 'mercadolibre', target_id=5, filters=None, run_id='run-1', runner=runner)
    assert result['supported'] is False and 'no se reproduce' in result['reason']
    assert set(result) == {'supported', 'reason'}
    assert runner.calls == [] and not (lean.runs_dir / 'run-1').exists()
    with pytest.raises(VpsError, match='run_id'):           # still validated
        vps.probe(lean, lean.repo, 'mercadolibre', target_id=5, filters=None, run_id='../x', runner=runner)


@pytest.mark.parametrize('name, text', [
    ('worker/config.py', 'ROOT = 2\n'),                     # modified outside the allowed paths
    ('worker/tools/repro_target.py', 'import os\n'),        # the tool the probe itself runs
    ('worker/pipeline/nuevo.py', 'x = 1\n'),                # new file outside
    ('ops/x.ps1', 'x\n'),
])
def test_probe_refuses_changes_outside_the_allowed_scope(bot, name, text):
    write(bot.repo, 'worker/collectors/kavak.py', 'PRICE = "candidate"\n')
    write(bot.repo, name, text)
    runner = FakeSsh()
    with pytest.raises(VpsError, match=f'fuera del alcance permitido: {name}'):
        vps.probe(bot, bot.repo, 'kavak', target_id=5, filters=None, run_id='run-1', runner=runner)
    assert runner.calls == []
    assert not (bot.runs_dir / 'run-1' / 'probes').exists()


def test_probe_refuses_a_clone_without_the_repro_tool_or_outside_git(bot, tmp_path):
    runner = FakeSsh()
    bare = settings(home=tmp_path / 'h', repo=tmp_path / 'not a repo', allowed_paths=bot.allowed_paths)
    bare.repo.mkdir()
    with pytest.raises(VpsError, match='git'):
        vps.probe(bare, bare.repo, 'kavak', target_id=5, filters=None, run_id='run-1', runner=runner)
    allowed = Settings(**{**bot.__dict__, 'allowed_paths': ('worker/',)})
    (bot.repo / 'worker/tools/repro_target.py').unlink()
    with pytest.raises(VpsError, match='repro_target'):
        vps.probe(allowed, bot.repo, 'kavak', target_id=5, filters=None, run_id='run-1', runner=runner)
    assert runner.calls == []


def test_probe_does_not_overlap_another_probe_of_the_same_run(staged):
    runner = FakeSsh(probe_reply('{"found": 1}'))
    (staged.runs_dir / 'run-1').mkdir(parents=True)
    with Lock(staged.runs_dir / 'run-1' / 'probe.lock') as held:
        assert held.acquired
        with pytest.raises(VpsError, match='probe en curso'):
            vps.probe(staged, staged.repo, 'kavak', target_id=5, filters=None, run_id='run-1', runner=runner)
    assert runner.calls == []
    assert vps.probe(staged, staged.repo, 'kavak', target_id=5, filters=None, run_id='run-1',
                     runner=runner)['found'] == 1


@pytest.mark.parametrize('reply, expected', [
    (probe_reply('{"found": 0, "complete": false, "reason": "tope de páginas"}', 2),
     {'found': 0, 'complete': False, 'reason': 'tope de páginas', 'exit_code': 2}),
    (probe_reply('{"error_type": "CollectorBlocked", "error": "login wall"}', 3, 'Traceback\n'),
     {'error_type': 'CollectorBlocked', 'exit_code': 3, 'stderr_tail': 'Traceback'}),
    (probe_reply('{\n  "found": 3,\n  "sample": [{"id": "1"}]\n}\n', 0), {'found': 3, 'sample': [{'id': '1'}]}),
    (probe_reply('{"found": 1}\n{"found": 2}\n', 0), {'found': 2}),
    (probe_reply('', 124, 'colgado\n'), {'error': 'la reproducción no devolvió JSON', 'exit_code': 124,
                                         'timed_out': True, 'stdout_tail': ''}),
    (probe_reply('Traceback (most recent call last):\nModuleNotFoundError: tools.repro_target\n[1, 2]', 1),
     {'error': 'la reproducción no devolvió JSON', 'exit_code': 1,
      'stdout_tail': 'Traceback (most recent call last):\nModuleNotFoundError: tools.repro_target\n[1, 2]'}),
])
def test_probe_reports_exit_code_and_output_of_the_reproduction(staged, reply, expected):
    result = vps.probe(staged, staged.repo, 'kavak', target_id=5, filters=None, run_id='run-1',
                       runner=FakeSsh(reply))
    assert result['supported'] is True and {key: result[key] for key in expected} == expected


@pytest.mark.parametrize('reply, message', [
    ('fail=wrong_host\n', 'VPS esperado'), ('fail=filters\n', 'filtros'), ('', 'ilegible'),
    ('exit=0\nstdout=%%%\nstderr=\n', 'ilegible'), ('exit=cero\nstdout=\nstderr=\n', 'ilegible'),
    ((97, '', 'repairbot: payload corrupto'), 'payload corrupto'),
])
def test_probe_that_did_not_run_is_an_error(staged, reply, message):
    with pytest.raises(VpsError, match=message):
        vps.probe(staged, staged.repo, 'kavak', target_id=5, filters=None, run_id='run-1', runner=FakeSsh(reply))


def test_stage_archive_drops_tests_bytecode_and_anything_that_is_not_a_file():
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w') as archive:
        def add(name, data=b'x = 1\n', mode=0o664, kind=tarfile.REGTYPE):
            member = tarfile.TarInfo(name)
            member.size, member.mode, member.type = (len(data) if kind == tarfile.REGTYPE else 0), mode, kind
            member.uid, member.uname, member.linkname = 1000, 'juan', '/etc/passwd'
            archive.addfile(member, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
        add('worker', kind=tarfile.DIRTYPE)
        add('worker/tools/repro_target.py')
        add('worker/tools/run.sh', mode=0o775)
        add('worker/tests/test_x.py')
        add('worker/tests/fixtures/html/kavak.html')
        add('worker/collectors/tests/helper.py')            # only the top-level tests/ is test code
        add('worker/collectors/__pycache__/kavak.cpython-312.pyc')
        add('worker/collectors/stale.pyc')
        add('worker/collectors/link.py', kind=tarfile.SYMTYPE)
    with tarfile.open(fileobj=io.BytesIO(vps._stage_archive(raw.getvalue())), mode='r:gz') as archive:
        staged = {member.name: (member.mode, member.uid, member.uname) for member in archive}
    assert staged == {'worker/tools/repro_target.py': (0o644, 0, ''), 'worker/tools/run.sh': (0o755, 0, ''),
                      'worker/collectors/tests/helper.py': (0o644, 0, '')}
    empty = io.BytesIO()
    tarfile.open(fileobj=empty, mode='w').close()
    with pytest.raises(VpsError, match='repro_target'):
        vps._stage_archive(empty.getvalue())


# --- the CLI Claude is allowed to run ------------------------------------------------------

@pytest.fixture
def cli(lean, tmp_path, monkeypatch, capsys):
    """The CLI with the bot's configuration; a test that probes also asks for `bot` (the clone)."""
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({**{key: str(getattr(lean, key)) for key in (
        'home', 'repo', 'env_file', 'python', 'claude', 'git_bash')}, 'max_probes': 2}), encoding='utf-8')
    monkeypatch.setenv('REPAIRBOT_CONFIG', str(config))

    def run(*argv, replies=()):
        runner = FakeSsh(*replies)
        code = vps.main(list(argv), runner=runner)
        captured = capsys.readouterr()
        return SimpleNamespace(code=code, out=captured.out, err=captured.err, runner=runner,
                               json=json.loads(captured.out) if captured.out.strip().startswith('{') else None)
    return run


@pytest.mark.parametrize('argv', [
    ['deploy', SHA, BASE], ['deploy'], ['restart'], ['restart_worker'], ['restart-worker'], ['cleanup', 'run-1'],
    ['ssh', 'id'], ['exec', 'id'], [], ['--deploy'], ['status', 'extra'], ['logs'], ['probe'],
    ['probe', 'kavak', '--run-id', 'otro'], ['logs', 'kavak', '--minutes', 'x'],
])
def test_cli_exposes_only_status_logs_and_probe(cli, argv):
    result = cli(*argv)
    assert result.code == 2 and result.runner.calls == [] and result.out == ''


def test_cli_status_and_logs_print_json(cli):
    result = cli('status', replies=[f'hostname={HOST}\nhead={SHA}\nworker=active\nwatchdog=active\n'])
    assert result.code == 0 and result.json == {'hostname': HOST, 'head': SHA, 'dirty': [],
                                                'worker_active': True, 'watchdog_active': True}
    assert result.runner.calls[0].argv == SSH_ARGV
    result = cli('logs', 'kavak', '--minutes', '45', '--lines', '10',
                 replies=['12:00 kavak falló: añadir sesión\n12:01 kavak ok\n'])
    assert result.code == 0 and result.json == {'source': 'kavak', 'minutes': 45,
                                                'lines': ['12:00 kavak falló: añadir sesión', '12:01 kavak ok']}
    assert '--since=-45min' in result.runner.scripts[0] and 'tail -n 10' in result.runner.scripts[0]


def test_cli_probe_uses_the_run_of_the_environment(cli, bot, monkeypatch):
    result = cli('probe', 'kavak', '--target-id', '5')
    assert result.code == 2 and 'REPAIRBOT_RUN_ID' in result.json['error'] and result.runner.calls == []
    monkeypatch.setenv('REPAIRBOT_RUN_ID', 'run-7')
    result = cli('probe', 'kavak', 'marca=Ford Ka', 'anio_min=2015', 'q=a=b',
                 replies=[probe_reply('{"found": 4}', 0)])
    assert result.code == 0 and result.json['found'] == 4 and result.json['probes_left'] == 1
    script = result.runner.scripts[0]
    assert 'stage=/opt/automotive/.repairbot/run-7\n' in script
    blob = re.search(r"\.encode\(\)\)' (\S+)\)\n", script)[1]
    assert json.loads(base64.b64decode(blob)) == {'marca': 'Ford Ka', 'anio_min': '2015', 'q': 'a=b'}
    assert (bot.runs_dir / 'run-7' / 'probes').read_text() == '1'
    assert cli('probe', 'kavak', 'sin-igual').code == 2
    cli('probe', 'kavak', replies=[probe_reply('{}')])
    result = cli('probe', 'kavak', replies=[probe_reply('{}')])
    assert result.code == 2 and 'tope de 2 probes' in result.json['error'] and result.runner.calls == []


def test_cli_reports_errors_as_json(cli, monkeypatch):
    result = cli('status', replies=[(255, '', 'ssh: connect to host: Connection refused')])
    assert result.code == 2 and '255' in result.json['error']
    assert cli('logs', 'kavak; id').code == 2
    monkeypatch.setenv('REPAIRBOT_CONFIG', 'Z:/no/such/config.json')
    result = cli('status')
    assert result.code == 2 and result.runner.calls == [] and 'error' in result.json


# --- the same scripts in a real bash -----------------------------------------------------

def find_bash() -> str | None:
    if os.name != 'nt':
        return shutil.which('bash')
    git_exe = shutil.which('git')   # never C:\Windows\System32\bash.exe: that one is WSL
    for root in (Path(git_exe).resolve().parents if git_exe else ()):
        if (root / 'bin' / 'bash.exe').exists() and (root / 'usr' / 'bin').exists():
            return str(root / 'bin' / 'bash.exe')
    return None


BASH = find_bash()
needs_bash = pytest.mark.skipif(not BASH, reason='needs bash (Git Bash on Windows)')
# sudo/hostname/systemctl/journalctl/sleep as shell functions, defined ahead of the script.
STUBS = r'''
hostname() { cat "$STUB/hostname"; }
sleep() { echo "sleep $1" >>"$STUB/log"; }
sudo() {
  [ "$1 $2 $3" = "-u automotive -H" ] || { echo "sudo inesperado: $*" >&2; return 99; }
  shift 3; echo "as-automotive $1" >>"$STUB/log"; "$@"
}
systemctl() {
  case "$1" in
    is-active) cat "$STUB/active-$2" 2>/dev/null || echo inactive; [ "$(cat "$STUB/active-$2" 2>/dev/null)" = active ];;
    restart) echo "restart $2" >>"$STUB/log";;
    show) n=$(($(cat "$STUB/shown" 2>/dev/null || echo 0) + 1)); echo "$n" >"$STUB/shown"; sed -n "${n}p" "$STUB/pids";;
  esac
}
journalctl() { echo "journalctl $*" >>"$STUB/log"; cat "$STUB/journal"; }
'''


def posix(path: Path) -> str:
    """The path as bash names it (/c/Users/... under Git Bash)."""
    text = str(path).replace('\\', '/')
    return f'/{text[0].lower()}{text[2:]}' if re.match(r'[A-Za-z]:/', text) else text


class LocalVps:
    """A checkout of 'origin' standing in for /opt/automotive, and a runner that pipes the wire to bash.
    Built once per module and copied for each test."""

    def __init__(self, folder: Path, base: str = ''):
        self.folder, self.base, self.calls = folder, base, []
        self.origin, self.root, self.stub, self.dev = (folder / name for name in ('origin.git', 'opt', 'stub', 'dev'))
        self.settings = settings(vps_root=posix(self.root), vps_hostname='vps-test', home=folder / 'home',
                                 repo=self.dev, max_probes=3)

    def build(self) -> 'LocalVps':
        self.stub.mkdir(parents=True)
        (self.stub / 'hostname').write_text('vps-test\n', encoding='ascii')
        (self.stub / 'sudo').write_bytes(b'#!/bin/sh\nshift 3\nexec "$@"\n')   # for xargs, which sees no functions
        (self.stub / 'sudo').chmod(0o755)
        git(self.folder, 'init', '--quiet', '--template=', '--bare', '--initial-branch=main', str(self.origin))
        self.clone(self.dev)
        git(self.dev, 'checkout', '--quiet', '-B', 'main')
        self.base = self.publish('base', **TREE)
        self.clone(self.root)
        python = self.root / '.venv' / 'bin' / 'python'
        python.parent.mkdir(parents=True)
        python.write_bytes(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n'.encode())
        python.chmod(0o755)
        write(self.root, '.git/info/exclude', '.venv/\n.repairbot/\n')
        return self

    def copy(self, folder: Path) -> 'LocalVps':
        shutil.copytree(self.folder, folder)
        twin = LocalVps(folder, self.base)
        for checkout in (twin.dev, twin.root):
            repoint(checkout, self.origin, twin.origin)
        return twin

    def clone(self, target: Path) -> Path:
        git(target.parent, 'clone', '--quiet', '--template=', '--config', 'user.name=Test', '--config',
            'user.email=test@example.test', '--config', 'core.autocrlf=false', '--config', 'commit.gpgsign=false',
            str(self.origin), str(target))
        return target

    def publish(self, message: str, branch: str = 'main', **files) -> str:
        sha = commit_all(self.dev, message, **files)
        git(self.dev, 'push', '--quiet', 'origin', f'HEAD:{branch}')
        return sha

    def head(self) -> str:
        return git(self.root, 'rev-parse', 'HEAD')

    def log(self) -> list[str]:
        path = self.stub / 'log'
        return path.read_text(encoding='utf-8').splitlines() if path.exists() else []

    def __call__(self, argv, *, input, timeout, **kw):
        assert argv == ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'automotive-vps', 'bash', '-s']
        self.calls.append(input)
        path = os.pathsep.join([str(self.stub), *(str(Path(BASH).parents[1] / part) for part in (
            'usr/bin', 'mingw64/bin') if os.name == 'nt'), os.environ['PATH']])
        return subprocess.run([BASH, '-s'], input=STUBS.encode() + input, capture_output=True, timeout=120,
                              cwd=self.stub, env={**os.environ, 'PATH': path, 'STUB': self.stub.as_posix()})


@pytest.fixture(scope='module')
def local_template(tmp_path_factory):
    folder = tmp_path_factory.mktemp('local-vps')
    (folder / 'gitconfig').write_text('', encoding='utf-8')
    with pytest.MonkeyPatch.context() as patch:
        isolate(patch, folder / 'gitconfig')
        return LocalVps(folder / 'w').build()


@pytest.fixture
def local(local_template, tmp_path, monkeypatch):
    isolate(monkeypatch, local_template.folder.parent / 'gitconfig')
    return local_template.copy(tmp_path / 'w')


@needs_bash
def test_bash_reads_the_payload_exactly_and_runs_nothing_from_a_cut_transfer(local, tmp_path):
    marker = posix(tmp_path / 'ran')
    payload = bytes(range(256)) * 300 + b'\nexit 5\necho INJECTED\n'   # must never be read as script
    body = f'echo "size=$(wc -c <"$payload" | tr -d " ")"\ncat\necho leftover-stdin-is-empty\ntouch {marker}'
    out = vps.ssh(local.settings, body, stdin=payload, runner=local)
    assert out.split() == [f'size={len(payload)}', 'leftover-stdin-is-empty'] and (tmp_path / 'ran').exists()
    (tmp_path / 'ran').unlink()
    wire = local.calls[0]
    for cut, code in ((len(wire) - 10, 97), (wire.index(b'touch') + 3, 2), (wire.index(b'main() {') + 5, 2)):
        result = local(SSH_ARGV, input=wire[:cut], timeout=60)
        assert result.returncode == code and not (tmp_path / 'ran').exists()
        assert b'INJECTED' not in result.stdout
    corrupted = wire[:-20] + bytes(20)
    assert local(SSH_ARGV, input=corrupted, timeout=60).returncode == 97 and not (tmp_path / 'ran').exists()
    with pytest.raises(VpsError, match='código 3'):
        vps.ssh(local.settings, 'echo antes\nfalse_command_that_is_missing || exit 3\necho despues', runner=local)
    with pytest.raises(VpsError, match='código 1'):   # set -e stops at the first failing command
        vps.ssh(local.settings, f'false\ntouch {marker}', runner=local)
    assert not (tmp_path / 'ran').exists()


def no_forbidden_commands(local: LocalVps) -> None:
    for script in (script_of(wire)[0] for wire in local.calls):
        assert not [word for word in FORBIDDEN if word in script]


@needs_bash
def test_bash_deploy_touches_nothing_on_the_wrong_server_or_a_dirty_checkout(local):
    wrong = Settings(**{**local.settings.__dict__, 'vps_hostname': 'vps-6488403-x'})
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    result = vps.deploy(wrong, fix, local.base, runner=local)
    assert (result['code'], result['prev_head']) == ('wrong_host', None) and 'vps-test' in result['reason']
    assert local.log() == [] and local.head() == local.base           # not even a fetch on the wrong server

    write(local.root, 'worker/collectors/kavak.py', 'PRICE = "hot patch"\n')
    write(local.root, 'untracked.txt', 'ignored by the check\n')
    result = vps.deploy(local.settings, fix, local.base, runner=local)
    assert (result['ok'], result['code'], result['head']) == (False, 'dirty', local.base)
    assert 'worker/collectors/kavak.py' in result['reason'] and 'untracked' not in result['reason']
    assert local.head() == local.base
    assert (local.root / 'worker/collectors/kavak.py').read_text() == 'PRICE = "hot patch"\n'   # nothing discarded
    no_forbidden_commands(local)


@needs_bash
def test_bash_deploy_fast_forwards_only_from_a_known_state(local):
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    write(local.root, 'untracked.txt', 'ignored by the check\n')
    result = vps.deploy(local.settings, fix, local.base, runner=local)
    assert result == {'ok': True, 'code': 'deployed', 'prev_head': local.base, 'head': fix, 'contains': True,
                      'reason': ''}
    assert local.head() == fix and (local.root / 'worker/collectors/kavak.py').read_text() == 'PRICE = "fixed"\n'
    assert (local.root / 'untracked.txt').exists()
    assert {'as-automotive git', 'as-automotive env'} <= set(local.log())
    assert vps.deploy(local.settings, fix, local.base, runner=local)['code'] == 'already'
    no_forbidden_commands(local)


@needs_bash
def test_bash_deploy_carries_undeployed_documentation_along(local):
    # main moved with documentation only; the bot's next fix sits on top of it.
    docs = local.publish('docs', **{'docs/b.md': 'nuevo\n', 'web/app/page.tsx': 'export {}\n'})
    second = local.publish('fix 2', **{'worker/collectors/kavak.py': 'PRICE = "fixed twice"\n',
                                       'worker/tests/test_kavak.py': 'def test_ok():\n    assert 1\n'})
    result = vps.deploy(local.settings, second, docs, runner=local)
    assert result == {'ok': True, 'code': 'deployed', 'prev_head': local.base, 'head': second, 'contains': True,
                      'reason': ''}
    assert local.head() == second and (local.root / 'docs/b.md').exists()
    no_forbidden_commands(local)


@needs_bash
def test_bash_deploy_refuses_undeployed_runtime_changes(local):
    runtime = local.publish('pipeline', **{'worker/pipeline/crawl.py': 'def run():\n    return 2\n'})
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    result = vps.deploy(local.settings, fix, runtime, runner=local)
    assert (result['ok'], result['code']) == (False, 'pending_changes') and local.head() == local.base
    assert 'requieren a una persona: worker/pipeline/crawl.py' in result['reason']


@needs_bash
def test_bash_deploy_refuses_a_commit_that_is_not_on_origin_main(local):
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    unpushed = commit_all(local.dev, 'solo local', **{'docs/c.md': 'x\n'})
    assert vps.deploy(local.settings, unpushed, fix, runner=local)['code'] == 'missing_commit'
    git(local.dev, 'reset', '--quiet', '--hard', fix)
    side = local.publish('rama', 'experimento', **{'worker/collectors/kavak.py': 'PRICE = "branch"\n'})
    assert vps.deploy(local.settings, side, fix, runner=local)['code'] == 'not_on_main'
    assert local.head() == local.base


@needs_bash
def test_bash_deploy_reports_a_checkout_that_cannot_fast_forward(local):
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    # A commit made on the server: clean tree, but main cannot fast-forward over it.
    server_only = commit_all(local.root, 'hecho en el servidor', **{'docs/server.md': 'x\n'})
    result = vps.deploy(local.settings, fix, server_only, runner=local)
    assert (result['ok'], result['code'], result['head']) == (False, 'ff_failed', server_only)
    assert 'no es fast-forward' in result['reason'] and local.head() == server_only


@needs_bash
def test_bash_deploy_of_a_commit_the_vps_already_contains(local):
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    later = local.publish('later', **{'docs/b.md': 'nuevo\n'})
    git(local.root, 'fetch', '--quiet', 'origin')
    git(local.root, 'merge', '--quiet', '--ff-only', later)   # main deployed by hand past the fix
    result = vps.deploy(local.settings, fix, local.base, runner=local)
    assert (result['ok'], result['code'], result['prev_head'], result['head'], result['contains']) == (
        True, 'already', later, later, True)
    assert 'ya contiene' in result['reason'] and local.head() == later

    write(local.root, 'worker/config.py', 'ROOT = 2\n')        # dirty: refused, but the head is still told
    result = vps.deploy(local.settings, fix, local.base, runner=local)
    assert (result['ok'], result['code'], result['head'], result['contains']) == (False, 'dirty', later, True)
    other = local.publish('other', **{'worker/collectors/otro.py': 'x = 1\n'})
    result = vps.deploy(local.settings, other, later, runner=local)   # not there yet: not contained
    assert (result['code'], result['head'], result['contains']) == ('dirty', later, False)
    no_forbidden_commands(local)


class LostApply:
    """The real scripts, except that the merge's answer never arrives (and, optionally, nothing after it)."""

    def __init__(self, local: LocalVps, reachable_after: bool):
        self.local, self.reachable_after, self.lost = local, reachable_after, False

    def __call__(self, argv, *, input, timeout, **kw):
        if self.lost and not self.reachable_after:
            raise subprocess.TimeoutExpired(argv, timeout)
        result = self.local(argv, input=input, timeout=timeout, **kw)
        if 'merge --ff-only' in script_of(input)[0]:
            self.lost = True
            raise subprocess.TimeoutExpired(argv, timeout)
        return result


@needs_bash
def test_bash_deploy_whose_answer_is_lost_reads_the_head_again(local):
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    result = vps.deploy(local.settings, fix, local.base, runner=LostApply(local, reachable_after=True))
    assert local.head() == fix                                     # the merge did run
    assert (result['ok'], result['code'], result['prev_head'], result['head'], result['contains']) == (
        False, 'ssh_error', local.base, fix, True)
    assert 'no respondió' in result['reason'] and fix[:12] in result['reason']
    no_forbidden_commands(local)


@needs_bash
def test_bash_deploy_whose_answer_and_second_read_are_lost_is_unknown(local):
    fix = local.publish('fix', **{'worker/collectors/kavak.py': 'PRICE = "fixed"\n'})
    result = vps.deploy(local.settings, fix, local.base, runner=LostApply(local, reachable_after=False))
    assert local.head() == fix
    assert (result['ok'], result['code'], result['prev_head'], result['head'], result['contains']) == (
        False, 'unknown_state', local.base, None, False)
    assert 'puede haber quedado o no' in result['reason']


@needs_bash
def test_bash_deploy_reports_code_that_does_not_compile(local):
    broken = local.publish('roto', **{'worker/collectors/kavak.py': 'PRICE = (\n',
                                      'worker/collectors/otro.py': 'x = 1\n', 'docs/d.md': 'x\n'})
    result = vps.deploy(local.settings, broken, local.base, runner=local)
    assert (result['ok'], result['code'], result['prev_head'], result['head']) == (
        False, 'py_compile', local.base, broken)
    assert 'SyntaxError' in result['reason'] and local.head() == broken   # merged: the launcher has to revert


@needs_bash
def test_bash_probe_runs_the_staged_candidate_as_automotive(local):
    git(local.dev, 'config', 'core.autocrlf', 'true')   # the bot's clone on Windows
    write(local.dev, 'worker/collectors/kavak.py', 'PRICE = "candidate"\r\n')
    write(local.dev, 'worker/collectors/nuevo.py', 'x = 1\n')
    hostile = {'marca': 'Ford Ka', 'modelo': '\'; touch pwned; echo "$(touch pwned)" `touch pwned` \\ * ~',
               'anio_min': 2015, 'inventory': True, 'texto': 'año ñ'}
    result = vps.probe(local.settings, local.dev, 'kavak', target_id=None, filters=hostile, run_id='run-1',
                       timeout=60, runner=local)
    stage = local.root / '.repairbot' / 'run-1' / 'worker'
    assert result['argv'] == ['kavak', '--no-db', '--json', 'marca=Ford Ka', f'modelo={hostile["modelo"]}',
                              'anio_min=2015', 'inventory=1', 'texto=año ñ']
    assert (result['exit_code'], result['supported'], result['probes_left']) == (3, True, 2)
    assert result['cwd'].lower().endswith(stage.as_posix().lower()) and result['has_tests'] is False
    assert result['collector'] == 'PRICE = "candidate"\n' and result['files'] == ['kavak.py', 'nuevo.py']
    env = result['env']
    assert env['DISPLAY'] == ':99' and env['PYTHONDONTWRITEBYTECODE'] == '1'
    assert env['XAUTHORITY'].endswith('/home/automotive/.Xauthority')
    assert env['FB_STORAGE_STATE'].lower().endswith(f'{local.root.as_posix().lower()}/fb_state.json')
    assert env['INSTAGRAM_STORAGE_STATE'].endswith('/opt/ig_state.json')
    assert env['ML_BROWSER_PROFILE_DIR'].endswith('/opt/.ml_chrome_profile')
    assert 'CollectorBlocked: login wall' in result['stderr_tail'] and 'abc123' not in result['stderr_tail']
    assert not list(local.root.rglob('pwned')) and not list(local.dev.rglob('pwned'))
    assert not (stage / 'tests').exists() and (stage / 'tools' / 'repro_target.py').exists()
    assert local.head() == local.base and git(local.root, 'status', '--porcelain') == ''   # deployed tree untouched
    log = local.log()
    for command in ('mkdir', 'chmod', 'rm', 'tar', 'env'):
        assert f'as-automotive {command}' in log

    # The next probe replaces the staged tree; cleanup removes the run.
    (local.dev / 'worker/collectors/nuevo.py').unlink()
    result = vps.probe(local.settings, local.dev, 'kavak', target_id=7, filters=None, run_id='run-1',
                       timeout=60, runner=local)
    assert result['argv'] == ['kavak', '--target-id', '7', '--json'] and result['files'] == ['kavak.py']
    vps.cleanup(local.settings, 'run-1', runner=local)
    assert not (local.root / '.repairbot' / 'run-1').exists() and (local.root / 'worker').exists()

    (local.stub / 'hostname').write_text('otro-servidor\n', encoding='ascii')
    with pytest.raises(VpsError, match='VPS esperado'):
        vps.probe(local.settings, local.dev, 'kavak', target_id=7, filters=None, run_id='run-1', timeout=60,
                  runner=local)
    assert not (local.root / '.repairbot' / 'run-1').exists()


@needs_bash
def test_bash_status_logs_and_restart(local):
    (local.stub / 'active-automotive-worker.service').write_text('active\n', encoding='ascii')
    write(local.root, 'worker/config.py', 'ROOT = 2\n')
    assert vps.status(local.settings, runner=local) == {
        'hostname': 'vps-test', 'head': local.base, 'dirty': ['worker/config.py'],
        'worker_active': True, 'watchdog_active': False}

    (local.stub / 'journal').write_text(
        ''.join(f'2026-10-13T12:00:{i:02d}-0300 vps python[1]: target={i} KAVAK Ford/Ka found=3\n' for i in range(8))
        + '2026-10-13T12:01:00-0300 vps python[1]: target=9 autocity failed: HTTP 403\n'
        + '2026-10-13T12:02:00-0300 vps python[1]: kavak GET https://u:pwd@kavak.test/x?token=abc123\n',
        encoding='utf-8')
    text = vps.logs(local.settings, 'kavak', minutes=30, max_lines=4, runner=local)
    assert len(text.split('\n')) == 4 and 'autocity' not in text and 'pwd' not in text
    assert text.split('\n')[0].endswith('target=5 KAVAK Ford/Ka found=3') and 'kavak.test/x' in text
    assert vps.logs(local.settings, 'gruporandazzo', runner=local) == ''
    assert 'journalctl -u automotive-worker.service --since=-30min --no-pager -o short-iso' in local.log()

    (local.stub / 'pids').write_text('4321\n4321\n', encoding='ascii')
    assert vps.restart_worker(local.settings, runner=local) == {'ok': True, 'active': True, 'reason': ''}
    assert [line for line in local.log() if not line.startswith(('as-automotive', 'journalctl'))] == [
        'restart automotive-worker.service', 'sleep 3', 'sleep 7']
    (local.stub / 'shown').unlink()
    (local.stub / 'pids').write_text('4321\n4399\n', encoding='ascii')   # restarted by systemd on its own
    assert vps.restart_worker(local.settings, runner=local)['ok'] is False
    (local.stub / 'shown').unlink()
    (local.stub / 'active-automotive-worker.service').write_text('failed\n', encoding='ascii')
    assert vps.restart_worker(local.settings, runner=local) == {
        'ok': False, 'active': False, 'reason': 'el worker quedó failed'}
