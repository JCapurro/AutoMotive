"""claude_runner: the command line, the generated settings and the checks on the stream, with
a Python script standing in for the CLI (it prints canned stream-json, then exits, hangs or
leaves a child behind, as each scenario says)."""
from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time

import pytest

from repairbot import claude_runner as runner
from repairbot import guard
from repairbot.settings import ENV_KEYS, Settings, child_env

RUN_ID = 'run-20261013-1'
SESSION = '0b6f6a0e-1f2d-4c3b-9a8e-5d4c3b2a1f00'
PROMPT = 'Incidente de kavak: "ñandú" $HOME `id` %PATH%\n<incident_context>{}</incident_context>'
TOOLS = ['Bash', 'Read', 'Edit', 'Write', 'Glob', 'Grep']
OUTPUT = {'outcome': 'fixed', 'root_cause': 'Cambió el selector de precio.',
          'summary': 'Kavak vuelve a traer avisos.', 'evidence': 'probe: 24 avisos', 'tests': '12 passed'}

# Reads the prompt, prints the planned events (one JSON object per line) and then does what the
# plan says. It notes what it saw so the test can ask.
FAKE_CLAUDE = r'''
import json, os, subprocess, sys, time

plan = json.load(open(sys.argv[1], encoding='utf-8'))
notes = {'prompt': sys.stdin.buffer.read().decode('utf-8'),      # returns once the launcher closes stdin
         'pid': os.getpid(), 'cwd': os.getcwd(), 'env': dict(os.environ)}
if plan.get('child'):
    notes['child'] = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']).pid
with open(sys.argv[2], 'w', encoding='utf-8') as handle:
    json.dump(notes, handle)
canary = 'REPAIRBOT_GUARD_ACTIVE ' + os.environ.get('REPAIRBOT_RUN_ID', '?')
for event in plan.get('events', []):
    line = event if isinstance(event, str) else json.dumps(event).replace('<canary>', canary)
    sys.stdout.write(line + '\n')
    sys.stdout.flush()
sys.stderr.write(plan.get('stderr', ''))
sys.stderr.flush()
time.sleep(plan.get('sleep', 0))
sys.exit(plan.get('exit', 0))
'''

CANARY = [
    {'type': 'system', 'subtype': 'hook_started', 'hook_event': 'SessionStart', 'hook_name': 'SessionStart:startup'},
    {'type': 'system', 'subtype': 'hook_response', 'hook_event': 'SessionStart', 'stdout': '<canary>\n',
     'stderr': '', 'exit_code': 0},
]
ASSISTANT = {'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Reviso.'}]}}


def init(**changes) -> dict:
    return {'type': 'system', 'subtype': 'init', 'session_id': SESSION, 'cwd': 'C:/automotive-bot/repo',
            'permissionMode': 'dontAsk', 'mcp_servers': [], 'tools': [*TOOLS, 'StructuredOutput'],
            'claude_code_version': '2.1.278', **changes}


def result(**changes) -> dict:
    return {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': json.dumps(OUTPUT),
            'structured_output': OUTPUT, 'session_id': SESSION, 'num_turns': 7, 'total_cost_usd': 1.25,
            'permission_denials': [{'tool_name': 'Bash'}], **changes}


def alive(pid: int) -> bool:
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(0x1000, False, pid)      # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259   # still active
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def gone(pid: int, within: float = 10) -> bool:
    until = time.monotonic() + within
    while alive(pid) and time.monotonic() < until:
        time.sleep(0.1)
    return not alive(pid)


class FakeClaude:
    """The injected popen: starts the stand-in script and keeps how the runner asked for claude."""

    def __init__(self, folder: Path, **plan):
        self.script, self.plan, self.notes_file = folder / 'fake_claude.py', folder / 'plan.json', folder / 'notes.json'
        self.script.write_text(FAKE_CLAUDE, encoding='utf-8')
        self.plan.write_text(json.dumps(plan), encoding='utf-8')
        self.args = self.kwargs = self.proc = None

    def __call__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.proc = subprocess.Popen([sys.executable, str(self.script), str(self.plan), str(self.notes_file)], **kwargs)
        return self.proc

    @property
    def notes(self) -> dict:
        return json.loads(self.notes_file.read_text(encoding='utf-8'))


@pytest.fixture
def settings(tmp_path) -> Settings:
    home = tmp_path / 'bot home'        # a space, as in "Program Files"
    (home / 'repo').mkdir(parents=True)
    return Settings(home=home, repo=home / 'repo', env_file=tmp_path / 'no.env', python=Path(sys.executable),
                    claude=home / 'bin' / 'claude.exe', git_bash=Path('C:/Program Files/Git/bin/bash.exe'),
                    claude_timeout_s=60)


@pytest.fixture
def fake(tmp_path):
    made: list[FakeClaude] = []

    def make(*events, **plan) -> FakeClaude:
        made.append(FakeClaude(tmp_path, events=list(events), **plan))
        return made[-1]
    yield make
    for one in made:        # nothing a failed test started may outlive it
        pids = [one.proc.pid] if one.proc else []
        if one.notes_file.is_file():
            pids.append(one.notes.get('child'))
        for pid in filter(None, pids):
            if alive(pid):
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
                else:
                    os.kill(pid, 9)


def run(settings: Settings, popen, **kwargs) -> runner.RunResult:
    return runner.run_claude(settings, prompt=PROMPT, system_prompt='Política del bot.', session_id=SESSION,
                             run_dir=settings.runs_dir / RUN_ID, popen=popen, **kwargs)


# --------------------------------------------------------------------------------------
# The command line and the settings file
# --------------------------------------------------------------------------------------

def test_build_args(settings):
    args = runner.build_args(settings, SESSION, Path('C:/runs/r 1/settings.json'), Path('C:/runs/r 1/system.md'))
    assert args == [
        str(settings.claude), '-p', '--output-format', 'stream-json', '--verbose', '--include-hook-events',
        '--session-id', SESSION, '--model', 'opus', '--effort', 'high', '--setting-sources', '',
        '--settings', str(Path('C:/runs/r 1/settings.json')), '--strict-mcp-config', '--disable-slash-commands',
        '--tools', 'Bash,Read,Edit,Write,Glob,Grep', '--permission-mode', 'dontAsk',
        '--append-system-prompt-file', str(Path('C:/runs/r 1/system.md')),
        '--json-schema', json.dumps(runner.OUTPUT_SCHEMA, ensure_ascii=False, separators=(',', ':')),
        '--max-turns', '150',
    ]
    assert args[args.index('--setting-sources') + 1] == ''      # an empty value, not a missing one
    assert all(isinstance(arg, str) for arg in args)
    custom = runner.build_args(replace(settings, model='sonnet', effort='medium', max_turns=40), SESSION,
                               Path('s.json'), Path('p.md'))
    assert [custom[custom.index(flag) + 1] for flag in ('--model', '--effort', '--max-turns')] == [
        'sonnet', 'medium', '40']


def test_output_schema():
    schema = runner.OUTPUT_SCHEMA
    assert schema['properties']['outcome']['enum'] == ['fixed', 'external', 'needs_human', 'recovered', 'no_fix']
    assert set(schema['properties']) == {'outcome', 'root_cause', 'summary', 'evidence', 'human_action', 'tests',
                                         'retry_in_minutes'}
    assert set(schema['properties']) - set(schema['required']) == {'human_action', 'retry_in_minutes'}
    assert schema['additionalProperties'] is False
    assert runner._schema_problem(OUTPUT) is None
    assert runner._schema_problem({**OUTPUT, 'human_action': 'Renovar la sesión.', 'retry_in_minutes': 30}) is None
    for bad in ({**OUTPUT, 'outcome': 'done'}, {**OUTPUT, 'extra': 1}, {**OUTPUT, 'retry_in_minutes': True},
                {**OUTPUT, 'retry_in_minutes': -1}, {**OUTPUT, 'tests': None},
                {key: value for key, value in OUTPUT.items() if key != 'evidence'}):
        assert runner._schema_problem(bad)


def test_settings_file(settings):
    run_dir = settings.runs_dir / RUN_ID
    path = runner.build_settings_file(settings, run_dir)
    assert path == run_dir / 'settings.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['permissions']['allow'] == ['Read', 'Glob', 'Grep', 'Edit', 'Write', 'Bash']
    assert data['permissions']['deny'] == ['Bash(git push:*)', 'Bash(ssh:*)', 'Bash(curl:*)', 'PowerShell',
                                           'WebFetch', 'WebSearch', 'Task']
    assert set(data['hooks']) == {'SessionStart', 'PreToolUse'}
    [group] = data['hooks']['PreToolUse']
    assert group['matcher'] == '.*'
    [hook] = group['hooks']
    assert hook['type'] == 'command'
    # Quoted, forward slashes: bash and cmd both read it as this argument list.
    python = Path(sys.executable).as_posix()
    expected = [python, '-I', (run_dir / 'guard.py').as_posix(), '--root', settings.repo.as_posix(),
                '--python', python, '--log', (run_dir / 'guard.log').as_posix(),
                '--allow', 'worker/collectors/', '--allow', 'worker/tests/', '--allow', 'worker/http_clients.py']
    assert shlex.split(hook['command']) == expected
    assert '\\' not in hook['command']
    assert hook['command'].startswith(f'"{python}" -I "{(run_dir / "guard.py").as_posix()}" --root "')
    assert ' ' in settings.repo.as_posix() and f'"{settings.repo.as_posix()}"' in hook['command']
    [[start]] = [group['hooks'] for group in data['hooks']['SessionStart']]
    assert shlex.split(start['command']) == [*expected, '--canary', RUN_ID]
    # The hooks run a copy the session cannot reach, not the file in the clone.
    assert (run_dir / 'guard.py').read_bytes() == Path(guard.__file__).read_bytes()
    assert not (run_dir / 'guard.py').is_relative_to(settings.repo)


def test_generated_hooks_run_the_real_guard(settings):
    run_dir = settings.runs_dir / RUN_ID
    hooks = json.loads(runner.build_settings_file(settings, run_dir).read_text(encoding='utf-8'))['hooks']
    start = hooks['SessionStart'][0]['hooks'][0]['command']
    before = hooks['PreToolUse'][0]['hooks'][0]['command']

    def call(command: str) -> bytes:
        return json.dumps({'hook_event_name': 'PreToolUse', 'cwd': str(settings.repo), 'tool_name': 'Bash',
                           'tool_input': {'command': command}}).encode()

    done = subprocess.run(shlex.split(start), capture_output=True, timeout=60)
    assert (done.returncode, done.stdout.decode().strip()) == (0, f'{guard.CANARY} {RUN_ID}')
    allowed = subprocess.run(shlex.split(before), input=call('git status'), capture_output=True, timeout=60)
    assert allowed.returncode == 0
    blocked = subprocess.run(shlex.split(before), input=call('git push'), capture_output=True, timeout=60)
    assert blocked.returncode == 2 and b'git push' in blocked.stderr
    # The CLI hands the string to a shell. Here: the platform's own (cmd.exe on Windows, sh elsewhere).
    done = subprocess.run(start, shell=True, capture_output=True, timeout=60)
    assert (done.returncode, done.stdout.decode().strip()) == (0, f'{guard.CANARY} {RUN_ID}')
    assert subprocess.run(before, shell=True, input=call('ssh automotive-vps'), capture_output=True,
                          timeout=60).returncode == 2
    verdicts = [json.loads(line)['verdict'] for line in (run_dir / 'guard.log').read_text('utf-8').splitlines()]
    assert verdicts == ['allow', 'allow', 'block', 'allow', 'block']


def test_settings_file_refuses_what_a_hook_command_cannot_carry(settings):
    for name in ('run 1', 'run;1', 'x' * 65):
        with pytest.raises(ValueError, match='run_id'):
            runner.build_settings_file(settings, settings.runs_dir / name)
    with pytest.raises(ValueError, match='dentro del clon'):
        runner.build_settings_file(settings, settings.repo / 'runs' / RUN_ID)
    with pytest.raises(ValueError, match='absolutas'):
        runner.build_settings_file(replace(settings, python=Path('python')), settings.runs_dir / RUN_ID)
    for odd in ('C:/py 100%/python.exe', 'C:/py$HOME/python.exe', 'C:/py`x`/python.exe', 'C:/py"x/python.exe'):
        with pytest.raises(ValueError, match='hook'):
            runner.build_settings_file(replace(settings, python=Path(odd).absolute()), settings.runs_dir / RUN_ID)
    with pytest.raises(ValueError, match='hook'):
        runner.build_settings_file(replace(settings, allowed_paths=('worker/$(id)/',)), settings.runs_dir / RUN_ID)
    assert not (settings.runs_dir / RUN_ID / 'settings.json').exists()


def _valid(settings) -> dict:
    return runner._settings(settings, settings.runs_dir / RUN_ID)


@pytest.mark.parametrize('damage', [
    lambda data: data.pop('hooks'),
    lambda data: data.pop('permissions'),
    lambda data: data.update(model='opus'),
    lambda data: data['permissions'].update(allow='Bash'),
    lambda data: data['permissions'].update(allow=['Bash']),
    lambda data: data['permissions'].update(allow=[*data['permissions']['allow'], 'WebFetch']),
    lambda data: data['permissions'].update(deny=[]),
    lambda data: data['permissions'].update(deny=['Bash(ssh:*']),
    lambda data: data['permissions'].update(deny=[*data['permissions']['deny'], 'Bash']),
    lambda data: data['permissions'].update(defaultMode='bypassPermissions'),
    lambda data: data['hooks'].pop('SessionStart'),
    lambda data: data['hooks'].pop('PreToolUse'),
    lambda data: data['hooks'].update(Stop=[]),
    lambda data: data['hooks'].update(PreToolUse={}),
    lambda data: data['hooks'].update(PreToolUse=[]),
    lambda data: data['hooks']['PreToolUse'][0].update(matcher='Bash'),
    lambda data: data['hooks']['PreToolUse'][0].update(matcher=None),
    lambda data: data['hooks']['PreToolUse'][0].update(hooks=[]),
    lambda data: data['hooks']['PreToolUse'][0].update(hooks='guard'),
    lambda data: data['hooks']['PreToolUse'][0].update(command='guard'),
    lambda data: data['hooks']['PreToolUse'][0]['hooks'][0].update(type='prompt'),
    lambda data: data['hooks']['PreToolUse'][0]['hooks'][0].update(command=''),
    lambda data: data['hooks']['PreToolUse'][0]['hooks'][0].update(command='a\nb'),
    lambda data: data['hooks']['PreToolUse'][0]['hooks'][0].pop('command'),
    lambda data: data['hooks']['SessionStart'][0]['hooks'][0].update(command='echo hola'),
    lambda data: data['hooks']['SessionStart'][0]['hooks'][0].update(command=b'bytes'),
])
def test_settings_are_validated_before_they_are_written(settings, damage):
    data = _valid(settings)
    runner.validate_settings(data)
    damage(data)
    with pytest.raises(ValueError, match='settings de Claude inválidos'):
        runner.validate_settings(data)


def test_preflight(settings, monkeypatch):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-secreto')
    calls = []

    def logged(stdout, code=0):
        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr='')
        return fake_run

    assert runner.preflight(settings, logged('{"loggedIn": true, "authMethod": "claude.ai"}')) is None
    [(argv, kwargs)] = calls
    assert argv == [str(settings.claude), 'auth', 'status', '--json']
    assert kwargs['env'] == child_env(settings, 'preflight') and 'ANTHROPIC_API_KEY' not in kwargs['env']
    assert kwargs.get('shell') is None and kwargs['timeout'] > 0
    assert 'claude auth login' in runner.preflight(settings, logged('{"loggedIn": false}', 1))
    assert 'claude auth login' in runner.preflight(settings, logged('{"loggedIn": "true"}'))
    assert 'JSON' in runner.preflight(settings, logged('Not logged in'))
    assert 'JSON' in runner.preflight(settings, logged(None))

    def missing(argv, **kwargs):
        raise FileNotFoundError(argv[0])

    def slow(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, 60)
    assert 'FileNotFoundError' in runner.preflight(settings, missing)
    assert 'TimeoutExpired' in runner.preflight(settings, slow)


# --------------------------------------------------------------------------------------
# The stream, line by line
# --------------------------------------------------------------------------------------

def watch(*events) -> runner._Stream:
    stream = runner._Stream(RUN_ID)
    for event in events:
        text = event if isinstance(event, str) else json.dumps(event).replace('<canary>', f'{guard.CANARY} {RUN_ID}')
        if stream.feed(text.encode('utf-8') + b'\n'):
            break
    return stream


def test_stream_accepts_the_canary_then_a_matching_init():
    stream = watch('not json', '[1]', '{"type": 7}', *CANARY, init())
    assert (stream.canary_seen, stream.init_seen, stream.stop, stream.session_id) == (True, True, None, SESSION)
    # Field spellings other CLI versions may use; tool order and StructuredOutput do not matter.
    other = {'type': 'system', 'subtype': 'hook_response', 'hook_event_name': 'SessionStart',
             'hook_name': 'SessionStart:startup', 'output': 'aviso\r\n<canary>\r\n', 'exitCode': 0}
    stream = watch(other, init(tools=TOOLS[::-1]))
    assert (stream.init_seen, stream.stop) == (True, None)


@pytest.mark.parametrize('hook', [
    None,                                                                               # no hook ran at all
    {'stdout': ''},
    {'stdout': 'REPAIRBOT_GUARD_ACTIVE otro-run'},
    {'stdout': 'x<canary>x'},                                                           # not the line itself
    {'stdout': '<canary>', 'exit_code': 1},
    {'stdout': '<canary>', 'hook_event': 'PreToolUse'},
    {'stdout': '<canary>', 'subtype': 'hook_started'},
    {'stderr': '<canary>'},
])
def test_stream_without_a_canary_before_init_is_guard_inactive(hook):
    events = [] if hook is None else [{'type': 'system', 'subtype': 'hook_response', 'hook_event': 'SessionStart',
                                       'exit_code': 0, **hook}]
    stream = watch(*events, init(), *CANARY)       # a canary after init is too late
    assert (stream.stop, stream.init_seen) == ('guard_inactive', False)
    assert 'canario' in stream.detail


@pytest.mark.parametrize('changes, shown', [
    ({'permissionMode': 'default'}, "permissionMode='default'"),
    ({'permissionMode': 'bypassPermissions'}, 'bypassPermissions'),
    ({'permissionMode': None}, 'permissionMode=None'),
    ({'tools': [*TOOLS, 'WebFetch']}, 'WebFetch'),
    ({'tools': [*TOOLS, 'StructuredOutput', 'mcp__supabase__execute_sql']}, 'mcp__supabase'),
    ({'tools': TOOLS[1:]}, 'tools='),
    ({'tools': 'Bash,Read,Edit,Write,Glob,Grep'}, 'tools='),
    ({'tools': None}, 'tools=None'),
    ({'mcp_servers': [{'name': 'supabase', 'status': 'connected'}]}, 'supabase'),
    ({'mcp_servers': None}, 'mcp_servers=None'),
    ({'mcp_servers': {}}, 'mcp_servers='),
])
def test_stream_with_an_init_that_is_not_what_was_asked_is_init_mismatch(changes, shown):
    stream = watch(*CANARY, init(**changes), ASSISTANT)
    assert (stream.stop, stream.init_seen) == ('init_mismatch', False)
    assert shown in stream.detail


def test_stream_distrusts_work_before_init_and_a_guard_that_crashes():
    assert watch(ASSISTANT).stop == 'guard_inactive'
    assert watch(*CANARY, ASSISTANT).stop == 'init_mismatch'
    assert watch(*CANARY, {'type': 'user', 'message': {}}).stop == 'init_mismatch'

    def pre_tool(code):
        return {'type': 'system', 'subtype': 'hook_response', 'hook_event': 'PreToolUse', 'exit_code': code}
    assert watch(*CANARY, init(), pre_tool(0), pre_tool(2), ASSISTANT).stop is None
    # Exit 1 is not a block for the CLI: the tool ran with nobody looking.
    crashed = watch(*CANARY, init(), pre_tool(1), ASSISTANT)
    assert crashed.stop == 'guard_inactive' and 'código 1' in crashed.detail


def outcome(*events, timed_out=False, returncode=0, stderr='') -> runner.RunResult:
    return watch(*events).outcome(SESSION, timed_out, 60, returncode, stderr)


def test_outcome_of_a_good_run():
    got = outcome(*CANARY, init(), ASSISTANT, result())
    assert got == runner.RunResult(True, 'success', OUTPUT, SESSION, num_turns=7, cost_usd=1.25, denials=1)
    # Older CLIs put the JSON in `result` only.
    assert outcome(*CANARY, init(), result(structured_output=None)).output == OUTPUT
    assert outcome(*CANARY, init(), result(session_id='otra')).session_id == 'otra'


@pytest.mark.parametrize('events, reason, shown', [
    ([result(subtype='error_max_turns', is_error=True, structured_output=None, result='')], 'max_turns', '7'),
    ([result(subtype='error_during_execution', is_error=True, structured_output=None, result='API Error: 529')],
     'error', 'API Error: 529'),
    ([result(is_error=True, result='Credit balance is too low')], 'error', 'Credit balance'),
    ([result(subtype='otra_cosa')], 'error', ''),
    ([result(structured_output=None, result='Listo, lo arreglé.')], 'no_output', 'structured_output'),
    ([result(structured_output=['fixed'], result='')], 'no_output', 'structured_output'),
    ([result(structured_output={**OUTPUT, 'outcome': 'done'})], 'error', 'esquema'),
    ([result(structured_output={'outcome': 'fixed'})], 'error', 'esquema'),
    ([ASSISTANT], 'no_output', 'código 3'),
    ([], 'no_output', 'boom'),
    ([{'type': 'rate_limit_event', 'rate_limit_info': {'status': 'rejected', 'resetsAt': 1760400000}}],
     'rate_limited', 'límite'),
    ([{'type': 'rate_limit_event', 'status': 'rejected'}], 'rate_limited', 'límite'),
    ([{'type': 'rate_limit_event', 'rate_limit_info': {'status': 'rejected'}},
      result(is_error=True, subtype='error_during_execution', result='Claude usage limit reached')],
     'rate_limited', 'usage limit'),
    ([{'type': 'rate_limit_event', 'rate_limit_info': {'status': 'allowed_warning'}}], 'no_output', 'código 3'),
])
def test_outcome_of_a_run_that_did_not_deliver(events, reason, shown):
    got = outcome(*CANARY, init(), *events, returncode=3, stderr='Error: boom')
    assert (got.ok, got.reason, got.output) == (False, reason, None)
    assert shown in got.detail and len(got.detail) <= 400


def test_outcome_details():
    allowed = {'type': 'rate_limit_event', 'rate_limit_info': {'status': 'allowed', 'resetsAt': 1760400000}}
    got = outcome(*CANARY, init(), allowed, result())
    assert got.ok and got.rate_limit == {'status': 'allowed', 'resetsAt': 1760400000}
    assert outcome(*CANARY, init(), timed_out=True).reason == 'timeout'
    rejected = {'type': 'rate_limit_event', 'rate_limit_info': {'status': 'rejected'}}
    assert outcome(*CANARY, init(), rejected, timed_out=True).reason == 'rate_limited'   # stalled on the limit
    assert outcome(*CANARY, init(), rejected, result()).reason == 'success'              # it went on and finished
    # A result the checks never vouched for is not a success, whatever it says.
    assert outcome(result()).reason == 'guard_inactive'
    assert outcome(*CANARY, result()).reason == 'init_mismatch'
    assert outcome(init(), result()).reason == 'guard_inactive'
    assert outcome(*CANARY, init(tools=[]), result()).reason == 'init_mismatch'
    odd = outcome(*CANARY, init(), result(num_turns='7', total_cost_usd=None, permission_denials=None))
    assert (odd.ok, odd.num_turns, odd.cost_usd, odd.denials) == (True, 0, 0.0, 0)


# --------------------------------------------------------------------------------------
# The process
# --------------------------------------------------------------------------------------

def test_success(settings, fake, monkeypatch):
    for key in (*ENV_KEYS, 'ANTHROPIC_API_KEY', 'CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'TEST_DATABASE_URL'):
        monkeypatch.setenv(key, 'secreto-del-lanzador')
    claude = fake(*CANARY, init(), ASSISTANT, result(), stderr='aviso\n')
    got = run(settings, claude)
    assert got == runner.RunResult(True, 'success', OUTPUT, SESSION, num_turns=7, cost_usd=1.25, denials=1)

    run_dir = settings.runs_dir / RUN_ID
    assert claude.args == runner.build_args(settings, SESSION, run_dir / 'settings.json', run_dir / 'system_prompt.md')
    assert (run_dir / 'system_prompt.md').read_text(encoding='utf-8') == 'Política del bot.'
    assert (run_dir / 'prompt.md').read_text(encoding='utf-8') == PROMPT
    assert (run_dir / 'stderr.log').read_text(encoding='utf-8') == 'aviso\n'
    lines = [json.loads(line) for line in (run_dir / 'stream.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [line.get('subtype', line['type']) for line in lines] == [
        'hook_started', 'hook_response', 'init', 'assistant', 'success']

    # The prompt went in on stdin, as UTF-8, and stdin was closed; nothing of it is an argument.
    assert claude.notes['prompt'] == PROMPT
    assert all(PROMPT not in arg for arg in claude.args)
    assert Path(claude.notes['cwd']).resolve() == settings.repo.resolve()
    assert claude.kwargs['cwd'] == str(settings.repo)

    # The environment is exactly the whitelist: nothing of the launcher's leaks in.
    assert claude.kwargs['env'] == child_env(settings, RUN_ID)
    assert claude.kwargs['env']['REPAIRBOT_RUN_ID'] == RUN_ID
    seen = claude.notes['env']
    assert not {key for key in seen if key.upper().startswith(('ANTHROPIC', 'CLAUDECODE', 'DATABASE', 'RESEND'))}
    assert 'secreto-del-lanzador' not in seen.values() and seen['TEST_DATABASE_URL'] == ''
    assert seen['CLAUDE_CODE_DISABLE_BACKGROUND_TASKS'] == '1'
    assert 'shell' not in claude.kwargs
    if os.name == 'nt':
        assert claude.kwargs['creationflags'] == subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    else:
        assert claude.kwargs['start_new_session'] is True
    assert claude.proc.poll() == 0


@pytest.mark.parametrize('events, reason', [
    ([init(), ASSISTANT], 'guard_inactive'),                                    # settings ignored: no hook ran
    ([*CANARY[:1], init()], 'guard_inactive'),
    ([*CANARY, init(permissionMode='default')], 'init_mismatch'),
    ([*CANARY, init(tools=[*TOOLS, 'StructuredOutput', 'WebFetch'])], 'init_mismatch'),
    ([*CANARY, init(mcp_servers=[{'name': 'supabase', 'status': 'connected'}])], 'init_mismatch'),
])
def test_an_untrusted_session_is_killed_at_once(settings, fake, events, reason):
    claude = fake(*events, sleep=120)       # it would go on working for two minutes
    started = time.monotonic()
    got = run(settings, claude)
    assert (got.ok, got.reason, got.output) == (False, reason, None)
    assert time.monotonic() - started < 30
    assert gone(claude.notes['pid'])
    assert claude.proc.poll() is not None


def test_timeout_kills_the_whole_process_tree(settings, fake):
    spawned = []

    def spy(argv, **kwargs):
        spawned.append(argv)
        return subprocess.run(argv, **kwargs)

    claude = fake(*CANARY, init(), ASSISTANT, child=True, sleep=120)
    started = time.monotonic()
    got = run(settings, claude, deadline_s=2, runner=spy)
    assert (got.ok, got.reason) == (False, 'timeout')
    assert '2 s' in got.detail and got.session_id == SESSION
    assert 1.5 < time.monotonic() - started < 40
    notes = claude.notes
    assert notes['child'] != notes['pid']
    assert gone(notes['pid']) and gone(notes['child'])       # the grandchild too
    if os.name == 'nt':
        assert spawned == [['taskkill', '/PID', str(claude.proc.pid), '/T', '/F']]


def test_the_default_limit_is_the_configured_timeout(settings, fake):
    claude = fake(*CANARY, init(), sleep=120)
    got = run(replace(settings, claude_timeout_s=2), claude)
    assert got.reason == 'timeout' and '2 s' in got.detail
    assert gone(claude.notes['pid'])


@pytest.mark.parametrize('events, plan, reason, shown', [
    ([result(subtype='error_max_turns', is_error=True, structured_output=None, result='')], {}, 'max_turns', '7'),
    ([{'type': 'rate_limit_event', 'rate_limit_info': {'status': 'rejected', 'resetsAt': 1760400000}}],
     {'exit': 1}, 'rate_limited', 'límite'),
    ([ASSISTANT], {'exit': 3, 'stderr': 'Error: boom\n'}, 'no_output', 'código 3) sin evento result. Error: boom'),
])
def test_runs_that_end_without_a_usable_result(settings, fake, events, plan, reason, shown):
    got = run(settings, fake(*CANARY, init(), *events, **plan))
    assert (got.ok, got.reason, got.output) == (False, reason, None)
    assert shown in got.detail
    if reason == 'rate_limited':
        assert got.rate_limit == {'status': 'rejected', 'resetsAt': 1760400000}


def test_a_silent_exit_is_no_output(settings, fake):
    got = run(settings, fake())
    assert (got.reason, got.session_id) == ('no_output', SESSION)
    assert (settings.runs_dir / RUN_ID / 'stream.jsonl').read_bytes() == b''


def test_a_cli_that_lingers_after_its_result_is_not_a_timeout(settings, fake, monkeypatch):
    monkeypatch.setattr(runner, '_EXIT_GRACE_S', 1)
    claude = fake(*CANARY, init(), result(), sleep=120)
    started = time.monotonic()
    got = run(settings, claude)
    assert (got.ok, got.reason, got.output) == (True, 'success', OUTPUT)
    assert time.monotonic() - started < 30 and gone(claude.notes['pid'])


def test_claude_that_cannot_be_started(settings):
    def missing(args, **kwargs):
        raise FileNotFoundError(2, 'No such file or directory', args[0])
    got = run(settings, missing)
    assert (got.ok, got.reason, got.session_id) == (False, 'error', SESSION)
    assert 'no se pudo ejecutar claude' in got.detail


def test_a_run_that_cannot_be_prepared_never_starts_claude(settings):
    def never(args, **kwargs):
        raise AssertionError('no tenía que ejecutarse')
    got = runner.run_claude(settings, prompt=PROMPT, system_prompt='x', session_id=SESSION,
                            run_dir=settings.runs_dir / 'run con espacios', popen=never)
    assert (got.ok, got.reason) == (False, 'error') and 'run_id' in got.detail
