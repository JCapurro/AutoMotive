"""One `claude -p` session for the repair bot, trusted only while its guard is provably on.

In -p mode the CLI drops a settings file it does not like without saying so, and the session
would then run with no hook at all. So the launcher never assumes: it reads the stream and
kills the process unless, before `system/init`, the SessionStart hook printed the canary (the
guard itself prints it, with the same command line the PreToolUse hook uses), and unless init
shows the permission mode, the tools and the empty MCP list that were asked for.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading
import time

from repairbot import guard
from repairbot.settings import Settings, child_env

TOOLS = ('Bash', 'Read', 'Edit', 'Write', 'Glob', 'Grep')
PERMISSION_MODE = 'dontAsk'
OUTCOMES = ('fixed', 'external', 'needs_human', 'recovered', 'no_fix')
OUTPUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'outcome': {'type': 'string', 'enum': list(OUTCOMES)},
        'root_cause': {'type': 'string'},
        'summary': {'type': 'string', 'description': 'Una oración para el dueño.'},
        'evidence': {'type': 'string'},
        'human_action': {'type': 'string', 'description': 'Qué tiene que hacer una persona (si needs_human).'},
        'tests': {'type': 'string'},
        'retry_in_minutes': {'type': 'integer', 'minimum': 0},
    },
    'required': ['outcome', 'root_cause', 'summary', 'evidence', 'tests'],
    'additionalProperties': False,
}

# dontAsk denies whatever is not allowed, so the tools are allowed wholesale: the guard decides.
_ALLOW = ('Read', 'Glob', 'Grep', 'Edit', 'Write', 'Bash')
_DENY = ('Bash(git push:*)', 'Bash(ssh:*)', 'Bash(curl:*)', 'PowerShell', 'WebFetch', 'WebSearch', 'Task')
_RUN_ID = re.compile(r'[A-Za-z0-9_-]{1,64}')
_RULE = re.compile(r'[A-Za-z][A-Za-z0-9_]*(\([^()\n]+\))?')
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
_EXIT_GRACE_S = 20      # after the result event, or after stdout closes, before the tree is killed
_DETAIL = 400


@dataclass
class RunResult:
    ok: bool
    reason: str     # success | timeout | guard_inactive | init_mismatch | max_turns | error | rate_limited | no_output
    output: dict | None
    session_id: str
    num_turns: int = 0
    cost_usd: float = 0.0
    denials: int = 0
    rate_limit: dict | None = None
    detail: str = ''


def preflight(settings: Settings, runner=subprocess.run) -> str | None:
    """None when the CLI has a session in the environment the bot gives it; otherwise why not."""
    try:
        done = runner([str(settings.claude), 'auth', 'status', '--json'], capture_output=True, encoding='utf-8',
                      errors='replace', timeout=60, stdin=subprocess.DEVNULL,
                      env=child_env(settings, 'preflight'), creationflags=_NO_WINDOW)
        status = json.loads(done.stdout or '')
    except (OSError, subprocess.SubprocessError) as error:
        return f'no se pudo ejecutar claude auth status ({type(error).__name__})'
    except ValueError:
        return 'claude auth status no devolvió JSON'
    if isinstance(status, dict) and status.get('loggedIn') is True:
        return None
    return 'Claude Code no tiene una sesión iniciada: corré claude auth login en esta PC'


# --------------------------------------------------------------------------------------
# Settings file and arguments
# --------------------------------------------------------------------------------------

def _quote(value) -> str:
    """An argument of a hook command. Forward slashes and double quotes read the same in bash and cmd."""
    text = str(value).replace('\\', '/')
    if not text or re.search(r'["$`%!\r\n]', text):
        raise ValueError(f'valor no apto para un comando de hook: {text!r}')
    return f'"{text}"'


def _guard_command(settings: Settings, run_dir: Path) -> str:
    parts = [_quote(settings.python), '-I', _quote(run_dir / 'guard.py'), '--root', _quote(settings.repo),
             '--python', _quote(settings.python), '--log', _quote(run_dir / 'guard.log')]
    for entry in settings.allowed_paths:
        parts += ['--allow', _quote(entry)]
    return ' '.join(parts)


def _settings(settings: Settings, run_dir: Path) -> dict:
    command = _guard_command(settings, run_dir)
    return {
        'permissions': {'allow': list(_ALLOW), 'deny': list(_DENY)},
        'hooks': {
            'SessionStart': [{'hooks': [{'type': 'command', 'command': f'{command} --canary {run_dir.name}'}]}],
            'PreToolUse': [{'matcher': '.*', 'hooks': [{'type': 'command', 'command': command}]}],
        },
    }


def validate_settings(data: dict) -> None:
    """Strict shape check of the generated settings; ValueError names the first problem."""
    def need(condition, problem: str) -> None:
        if not condition:
            raise ValueError(f'settings de Claude inválidos: {problem}')

    need(isinstance(data, dict) and set(data) == {'permissions', 'hooks'}, 'se esperan permissions y hooks')
    permissions, hooks = data['permissions'], data['hooks']
    need(isinstance(permissions, dict) and set(permissions) == {'allow', 'deny'}, 'permissions lleva allow y deny')
    for key in ('allow', 'deny'):
        rules = permissions[key]
        need(isinstance(rules, list) and rules, f'permissions.{key} tiene que ser una lista con reglas')
        need(all(isinstance(rule, str) and _RULE.fullmatch(rule) for rule in rules), f'regla mal formada en {key}')
    need(set(permissions['allow']) == set(TOOLS), 'allow tiene que cubrir exactamente las herramientas pedidas')
    need(not set(permissions['allow']) & set(permissions['deny']), 'una regla está en allow y en deny')
    need(isinstance(hooks, dict) and set(hooks) == {'SessionStart', 'PreToolUse'},
         'hooks lleva SessionStart y PreToolUse')
    for event, groups in hooks.items():
        need(isinstance(groups, list) and groups, f'hooks.{event} tiene que ser una lista con grupos')
        for group in groups:
            need(isinstance(group, dict) and set(group) <= {'matcher', 'hooks'} and 'hooks' in group,
                 f'grupo mal formado en {event}')
            need(isinstance(group.get('matcher', ''), str), f'matcher de {event} tiene que ser texto')
            need(isinstance(group['hooks'], list) and group['hooks'], f'{event} sin comandos')
            for hook in group['hooks']:
                need(isinstance(hook, dict) and set(hook) == {'type', 'command'} and hook['type'] == 'command',
                     f'hook mal formado en {event}')
                command = hook['command']
                need(isinstance(command, str) and command.strip() and '\n' not in command and '\r' not in command,
                     f'comando vacío o de varias líneas en {event}')
    need(any(group.get('matcher') == '.*' for group in hooks['PreToolUse']),
         'PreToolUse tiene que cubrir todas las herramientas (matcher ".*")')
    need(all(' --canary ' in hook['command'] for group in hooks['SessionStart'] for hook in group['hooks']),
         'SessionStart tiene que imprimir el canario')
    need(json.loads(json.dumps(data)) == data, 'no sobrevive a JSON')


def build_settings_file(settings: Settings, run_dir: Path) -> Path:
    """Write <run_dir>/settings.json (permissions + hooks) and the guard copy its hooks run."""
    run_dir = Path(run_dir).absolute()
    if not _RUN_ID.fullmatch(run_dir.name):
        raise ValueError(f'run_id inválido: {run_dir.name!r}')
    if not (Path(settings.python).is_absolute() and Path(settings.repo).is_absolute()):
        raise ValueError('python y repo tienen que ser rutas absolutas')
    if run_dir.is_relative_to(Path(settings.repo).absolute()):
        raise ValueError('run_dir no puede estar dentro del clon que edita Claude')
    data = _settings(settings, run_dir)
    validate_settings(data)
    run_dir.mkdir(parents=True, exist_ok=True)
    # The hooks run a copy outside the clone: the session can change files in the clone
    # (git restore brings back any old version), never this one.
    shutil.copyfile(guard.__file__, run_dir / 'guard.py')
    path = run_dir / 'settings.json'
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    return path


def build_args(settings: Settings, session_id: str, settings_file: Path, system_prompt_file: Path) -> list[str]:
    return [
        str(settings.claude), '-p', '--output-format', 'stream-json', '--verbose', '--include-hook-events',
        '--session-id', session_id, '--model', settings.model, '--effort', settings.effort,
        # No user, project or local settings, no MCP servers, no slash commands: only what is listed here.
        '--setting-sources', '', '--settings', str(settings_file), '--strict-mcp-config',
        '--disable-slash-commands', '--tools', ','.join(TOOLS), '--permission-mode', PERMISSION_MODE,
        '--append-system-prompt-file', str(system_prompt_file),
        '--json-schema', json.dumps(OUTPUT_SCHEMA, ensure_ascii=False, separators=(',', ':')),
        '--max-turns', str(settings.max_turns),
    ]


# --------------------------------------------------------------------------------------
# The stream
# --------------------------------------------------------------------------------------

def _first(event: dict, *keys: str):
    return next((event[key] for key in keys if key in event), None)


def _schema_problem(output: dict) -> str | None:
    properties = OUTPUT_SCHEMA['properties']
    missing = [key for key in OUTPUT_SCHEMA['required'] if key not in output]
    if missing or set(output) - set(properties):
        return f'faltan {missing} o sobran {sorted(set(output) - set(properties))}'
    for key, value in output.items():
        if properties[key]['type'] == 'string' and not isinstance(value, str):
            return f'{key} tiene que ser texto'
        if properties[key]['type'] == 'integer' and (type(value) is not int or value < 0):
            return f'{key} tiene que ser un entero no negativo'
    if output['outcome'] not in OUTCOMES:
        return f'outcome desconocido: {output["outcome"]!r}'
    return None


def _number(value, kind):
    return kind(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else kind(0)


class _Stream:
    """What the stream says, and whether the session it describes can still be trusted."""

    def __init__(self, run_id: str):
        self.canary = f'{guard.CANARY} {run_id}'
        self.canary_seen = self.init_seen = False
        self.stop: str | None = None      # guard_inactive | init_mismatch: the process must die
        self.detail = ''
        self.result: dict | None = None
        self.rate_limit: dict | None = None
        self.session_id = ''

    def feed(self, raw: bytes) -> bool:
        """Take one line of the stream. True when the process has to be killed now."""
        try:
            event = json.loads(raw.decode('utf-8', errors='replace'))
        except ValueError:
            return False
        if not isinstance(event, dict):
            return False
        kind, subtype = event.get('type'), event.get('subtype')
        if kind == 'system' and subtype == 'hook_response':
            self._hook(event)
        elif kind == 'system' and subtype == 'init':
            self._init(event)
        elif kind == 'rate_limit_event':
            info = event.get('rate_limit_info')
            self.rate_limit = info if isinstance(info, dict) else event
        elif kind == 'result':
            self.result = event
        elif kind in ('assistant', 'user') and not self.init_seen:
            self._distrust('la sesión empezó a trabajar antes del evento init')
        return self.stop is not None

    def _distrust(self, detail: str) -> None:
        if not self.stop:
            self.stop = 'init_mismatch' if self.canary_seen else 'guard_inactive'
            self.detail = detail

    def _hook(self, event: dict) -> None:
        name = ' '.join(str(event.get(key) or '') for key in ('hook_event', 'hook_event_name', 'hook_name'))
        code = _first(event, 'exit_code', 'exitCode')
        if 'SessionStart' in name:
            printed = '\n'.join(str(event.get(key) or '') for key in ('stdout', 'output')).splitlines()
            if code in (0, None) and self.canary in (line.strip() for line in printed):
                self.canary_seen = True
        elif 'PreToolUse' in name and type(code) is int and code not in (0, 2):
            # Only 0 and 2 are the guard deciding. With any other code the CLI goes on with the tool.
            self.stop, self.detail = 'guard_inactive', f'el guard terminó con código {code} en un PreToolUse'

    def _init(self, event: dict) -> None:
        if not self.canary_seen:
            self._distrust('el hook SessionStart no imprimió el canario antes de init '
                           '(settings ignorados o guard roto)')
            return
        mode = _first(event, 'permissionMode', 'permission_mode')
        servers = _first(event, 'mcp_servers', 'mcpServers')
        tools = event.get('tools')
        problems = []
        if mode != PERMISSION_MODE:
            problems.append(f'permissionMode={mode!r}')
        if servers != []:
            problems.append(f'mcp_servers={str(servers)[:120]}')
        if not isinstance(tools, list) or {str(tool) for tool in tools} - {'StructuredOutput'} != set(TOOLS):
            problems.append(f'tools={str(tools)[:200]}')
        if problems:
            self._distrust('init distinto de lo pedido: ' + '; '.join(problems))
            return
        self.init_seen = True
        self.session_id = str(event.get('session_id') or '')

    def outcome(self, session_id: str, timed_out: bool, limit: float, returncode, stderr: str) -> RunResult:
        result = self.result or {}
        denials = result.get('permission_denials')
        common = dict(session_id=str(result.get('session_id') or self.session_id or session_id),
                      num_turns=_number(result.get('num_turns'), int),
                      cost_usd=_number(result.get('total_cost_usd'), float),
                      denials=len(denials) if isinstance(denials, list) else 0, rate_limit=self.rate_limit)

        def failed(reason: str, detail: str) -> RunResult:
            return RunResult(False, reason, None, detail=detail[:_DETAIL], **common)

        limited = not str((self.rate_limit or {}).get('status') or 'allowed').startswith('allowed')
        text = str(result.get('result') or result.get('subtype') or '')
        if self.stop:
            return failed(self.stop, self.detail)
        if self.result is None:
            if limited:
                return failed('rate_limited', 'límite de uso de la suscripción alcanzado')
            if timed_out:
                return failed('timeout', f'claude -p superó el tope de {limit:.0f} s; se terminaron sus procesos')
            return failed('no_output', f'claude terminó (código {returncode}) sin evento result. {stderr}'.strip())
        if not (self.canary_seen and self.init_seen):
            return failed('init_mismatch' if self.canary_seen else 'guard_inactive',
                          f'hubo resultado sin canario o sin init: {text}')
        if result.get('subtype') == 'error_max_turns':
            return failed('max_turns', f'se agotaron los turnos ({common["num_turns"]})')
        if result.get('is_error') or result.get('subtype') != 'success':
            return failed('rate_limited' if limited else 'error', text or 'error sin detalle')
        output = result.get('structured_output')
        if output is None and isinstance(result.get('result'), str):
            try:
                output = json.loads(result['result'])
            except ValueError:
                output = None
        if not isinstance(output, dict):
            return failed('no_output', 'el resultado no trae structured_output')
        problem = _schema_problem(output)
        if problem:
            return failed('error', f'la salida no cumple el esquema: {problem}')
        return RunResult(True, 'success', output, **common)


# --------------------------------------------------------------------------------------
# The process
# --------------------------------------------------------------------------------------

def _spawn_options() -> dict:
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | _NO_WINDOW}
    return {'start_new_session': True}


def _close(pipe) -> None:
    try:
        pipe.close()
    except (OSError, ValueError):
        pass


# Each pipe is used and closed by one thread only: closing it from another one would wait
# for a read or a write that may never return.
def _feed(stdin, prompt: str) -> None:
    try:
        stdin.write(prompt.encode('utf-8'))
    except (OSError, ValueError):
        pass
    finally:
        _close(stdin)


def _pump(stdout, lines: queue.Queue) -> None:
    try:
        for raw in stdout:
            lines.put(raw)
    except (OSError, ValueError):
        pass
    finally:
        lines.put(None)
        _close(stdout)


def _kill_tree(proc, runner=subprocess.run) -> None:
    """End the process and everything it started (bash, python, ssh). Windows has no signal for it."""
    try:
        if proc.poll() is None:
            if os.name == 'nt':
                runner(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=30,
                       creationflags=_NO_WINDOW)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def _tail(path: Path, size: int = 300) -> str:
    try:
        return ' '.join(path.read_bytes()[-2000:].decode('utf-8', errors='replace').split())[-size:]
    except OSError:
        return ''


def run_claude(settings: Settings, *, prompt: str, system_prompt: str, session_id: str, run_dir: Path,
               deadline_s: int | None = None, popen=subprocess.Popen, runner=subprocess.run) -> RunResult:
    """Run the session to its result event, or kill it: wall clock (deadline_s, default
    claude_timeout_s), guard not proven active, or an init that is not what was asked for.
    `runner` only runs taskkill."""
    run_dir = Path(run_dir).absolute()
    try:
        settings_file = build_settings_file(settings, run_dir)
        system_file = run_dir / 'system_prompt.md'
        system_file.write_text(system_prompt, encoding='utf-8', newline='\n')
        (run_dir / 'prompt.md').write_text(prompt, encoding='utf-8', newline='\n')
        args = build_args(settings, session_id, settings_file, system_file)
    except (OSError, ValueError) as error:
        return RunResult(False, 'error', None, session_id, detail=f'no se pudo preparar la corrida: {error}'[:_DETAIL])
    limit = settings.claude_timeout_s if deadline_s is None else deadline_s
    watch, timed_out, proc = _Stream(run_dir.name), False, None
    with open(run_dir / 'stream.jsonl', 'wb') as stream, open(run_dir / 'stderr.log', 'wb') as stderr:
        try:
            proc = popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
                         cwd=str(settings.repo), env=child_env(settings, run_dir.name), **_spawn_options())
        except OSError as error:
            return RunResult(False, 'error', None, session_id,
                             detail=f'no se pudo ejecutar claude: {error.strerror or error}'[:_DETAIL])
        lines: queue.Queue = queue.Queue()
        closed = False      # stdout reached its end
        try:
            threading.Thread(target=_feed, args=(proc.stdin, prompt), daemon=True).start()
            threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True).start()
            deadline = time.monotonic() + limit
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    raw = lines.get(timeout=min(remaining, 0.5))
                except queue.Empty:
                    continue
                if raw is None:
                    closed = True
                    break
                stream.write(raw)
                stream.flush()
                finished = watch.result is not None
                if watch.feed(raw):
                    break
                if watch.result is not None and not finished:   # it should exit on its own now
                    deadline = min(deadline, time.monotonic() + _EXIT_GRACE_S)
            if closed:
                try:
                    proc.wait(timeout=_EXIT_GRACE_S)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            _kill_tree(proc, runner)
            give_up = time.monotonic() + 5
            while not closed and time.monotonic() < give_up:   # what it had already printed goes to the file
                try:
                    raw = lines.get(timeout=0.2)
                except queue.Empty:
                    continue
                if raw is None:
                    break
                stream.write(raw)
    return watch.outcome(session_id, timed_out, limit, proc.returncode, _tail(run_dir / 'stderr.log'))
