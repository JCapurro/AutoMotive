"""The VPS, only through fixed scripts.

Every remote operation is a bash script piped to `ssh <host> bash -s`. A value enters a
script through render(), after strict validation; free text (collector filters) travels as
base64 JSON and is decoded on the server. There git and python run as `automotive`: root
would break file ownership and git refuses the tree as dubious.

Claude reaches status, logs and probe through main(). Deploy, restart and cleanup belong to
the launcher: python -m repairbot.vps (status | logs <source> | probe <source> [--target-id N] [k=v ...])
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile

from repairbot import gitops
from repairbot.settings import ENV_KEYS, load
from repairbot.state import Lock

SSH = 'ssh'
WORKER_UNIT = 'automotive-worker.service'
WATCHDOG_UNIT = 'automotive-watchdog.timer'
UNSUPPORTED = {
    'mercadolibre': 'Mercado Libre no se reproduce en el VPS: el worker tiene tomado su perfil de Chrome. '
                    'Diagnosticá con el journal y las corridas; el arreglo se verifica con la corrida real '
                    'después del deploy.',
}
_NAME = re.compile(r'(?!-)[A-Za-z0-9_-]{1,64}')          # sources and run ids
_SHA = re.compile(r'[0-9a-f]{40}')
_KEY = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}')        # filter names
_HOST = re.compile(r'[A-Za-z0-9][A-Za-z0-9._@-]{0,252}')
_ROOT = re.compile(r'(?:/[A-Za-z0-9_][A-Za-z0-9._-]*)+')
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

log = logging.getLogger(__name__)

# Scripts print facts as key=value lines; anything free-form comes back as base64.
STATUS = r'''
cd __ROOT__
host=$(hostname)
head=$(sudo -u automotive -H git rev-parse HEAD)
worker=$(systemctl is-active __WORKER__ || true)
watchdog=$(systemctl is-active __WATCHDOG__ || true)
printf '%s\n' "hostname=$host" "head=$head" "worker=$worker" "watchdog=$watchdog"
sudo -u automotive -H git status --porcelain --untracked-files=no | sed 's/^/dirty=/'
'''

# The patterns are validated names, so they are literal as regular expressions too.
# grep's exit status 1 only means that nothing matched.
LOGS = r'''
{ journalctl -u __WORKER__ --since=__SINCE__ --no-pager -o short-iso || true; } \
  | { grep -a -i __PATTERNS__ || [ $? -eq 1 ]; } | tail -n __LINES__
'''

# Facts only: the launcher decides. Nothing in the working tree changes here.
# contains=1: HEAD is the commit or descends from it (a commit the VPS lacks is in no history of it).
DEPLOY_INSPECT = r'''
host=$(hostname)
printf 'hostname=%s\n' "$host"
[ "$host" = __HOSTNAME__ ] || exit 0
cd __ROOT__
head=$(sudo -u automotive -H git rev-parse HEAD)
printf 'head=%s\n' "$head"
contains=0
if sudo -u automotive -H git merge-base --is-ancestor __SHA__ "$head" 2>/dev/null; then contains=1; fi
printf 'contains=%s\n' "$contains"
dirty=$(sudo -u automotive -H git status --porcelain --untracked-files=no)
if [ -n "$dirty" ]; then printf '%s\n' "$dirty" | sed 's/^/dirty=/'; exit 0; fi
[ "$contains" = 0 ] || exit 0
sudo -u automotive -H env GIT_TERMINAL_PROMPT=0 timeout 120 git fetch --quiet origin
for commit in __SHA__ __BASE__; do
  sudo -u automotive -H git cat-file -e "$commit^{commit}" 2>/dev/null || { echo missing=1; exit 0; }
done
if sudo -u automotive -H git merge-base --is-ancestor __SHA__ origin/main; then echo on_main=1; else echo on_main=0; fi
sudo -u automotive -H git -c core.quotePath=false diff --name-only "$head" __BASE__ | sed 's/^/pending=/'
'''

# Fast-forward only, from the exact state the launcher inspected.
DEPLOY_APPLY = r'''
[ "$(hostname)" = __HOSTNAME__ ] || { echo fail=wrong_host; exit 0; }
cd __ROOT__
[ "$(sudo -u automotive -H git rev-parse HEAD)" = __PREV__ ] || { echo fail=moved; exit 0; }
[ -z "$(sudo -u automotive -H git status --porcelain --untracked-files=no)" ] || { echo fail=dirty; exit 0; }
detail() { printf 'detail=%s\n' "$(printf %s "$1" | tail -c 1500 | base64 -w0)"; }
if ! output=$(sudo -u automotive -H git merge --ff-only __SHA__ 2>&1); then
  printf 'head=%s\n' "$(sudo -u automotive -H git rev-parse HEAD)"
  echo fail=ff_failed; detail "$output"; exit 0
fi
head=$(sudo -u automotive -H git rev-parse HEAD)
printf 'head=%s\n' "$head"
[ "$head" = __SHA__ ] || { echo fail=head_mismatch; exit 0; }
if ! output=$(sudo -u automotive -H git diff --name-only --diff-filter=ACMR -z __PREV__ __SHA__ -- '*.py' \
    | xargs -0 -r sudo -u automotive -H __PYTHON__ -m py_compile 2>&1); then
  echo fail=py_compile; detail "$output"; exit 0
fi
echo done=1
'''

# Where the checkout is after an apply whose answer was lost or said nothing about it.
DEPLOY_HEAD = r'''
[ "$(hostname)" = __HOSTNAME__ ] || { echo fail=wrong_host; exit 0; }
cd __ROOT__
head=$(sudo -u automotive -H git rev-parse HEAD)
contains=0
if sudo -u automotive -H git merge-base --is-ancestor __SHA__ "$head" 2>/dev/null; then contains=1; fi
printf '%s\n' "head=$head" "contains=$contains"
'''

RESTART = r'''
[ "$(hostname)" = __HOSTNAME__ ] || { echo fail=wrong_host; exit 0; }
systemctl restart __WORKER__
sleep 3
pid=$(systemctl show -p MainPID --value __WORKER__)
sleep 7
state=$(systemctl is-active __WORKER__ || true)
[ "$pid" != 0 ] && [ "$pid" = "$(systemctl show -p MainPID --value __WORKER__)" ] && stable=1 || stable=0
printf '%s\n' "state=$state" "stable=$stable"
'''

# The staged tree arrives in "$payload" (see _wire). ROOT moves with the staged config.py, so
# the session files are named by absolute path; the .env is still found by the upward search.
PROBE = r'''
[ "$(hostname)" = __HOSTNAME__ ] || { echo fail=wrong_host; exit 0; }
stage=__ROOT__/.repairbot/__RUN_ID__
sudo -u automotive -H mkdir -p __ROOT__/.repairbot "$stage"
sudo -u automotive -H chmod 0700 __ROOT__/.repairbot "$stage"
sudo -u automotive -H rm -rf -- "$stage/worker"
sudo -u automotive -H tar -xzf - -C "$stage" --no-same-owner <"$payload"
sudo -u automotive -H chmod 0700 "$stage/worker"
filters=()
while IFS= read -r -d '' item; do filters+=("$item"); done < <(
  sudo -u automotive -H __PYTHON__ -c 'import base64, json, sys
for key, value in json.loads(base64.b64decode(sys.argv[1])).items():
    sys.stdout.buffer.write(f"{key}={value}\0".encode())' __BLOB__)
[ "${#filters[@]}" -eq __COUNT__ ] || { echo fail=filters; exit 0; }
cd "$stage/worker"
code=0
sudo -u automotive -H env DISPLAY=:99 XAUTHORITY=/home/automotive/.Xauthority \
  FB_STORAGE_STATE=__ROOT__/fb_state.json INSTAGRAM_STORAGE_STATE=__ROOT__/ig_state.json \
  ML_BROWSER_PROFILE_DIR=__ROOT__/.ml_chrome_profile PYTHONDONTWRITEBYTECODE=1 \
  timeout --kill-after=20 __SECONDS__ __PYTHON__ -m tools.repro_target __ARGS__ ${filters[@]+"${filters[@]}"} \
  >"$work/out" 2>"$work/err" || code=$?
printf 'exit=%s\n' "$code"
printf 'stdout=%s\n' "$(tail -c 262144 "$work/out" | base64 -w0)"
printf 'stderr=%s\n' "$(tail -c 8192 "$work/err" | base64 -w0)"
'''

CLEANUP = r'''
[ "$(hostname)" = __HOSTNAME__ ] || { echo fail=wrong_host; exit 0; }
sudo -u automotive -H rm -rf -- __ROOT__/.repairbot/__RUN_ID__
echo done=1
'''

_DEPLOY_FAILURES = {
    'wrong_host': 'el servidor no es el VPS esperado',
    'moved': 'el checkout del VPS cambió mientras se desplegaba',
    'dirty': 'el checkout del VPS tiene cambios sin commitear',
    'ff_failed': 'el VPS no pudo avanzar al commit (no es fast-forward)',
    'head_mismatch': 'después del merge el VPS no quedó en el commit esperado',
    'py_compile': 'el código desplegado no compila',
}


class VpsError(RuntimeError):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code   # ssh exit status: 255 means the VPS was not reachable


def _checked(pattern: re.Pattern, value, name: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise VpsError(f'{name} inválido: {str(value)[:60]!r}')
    return value


def _number(value, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise VpsError(f'{name} inválido: {str(value)[:60]!r}')
    return value


def _safe(text: str, limit: int = 20000) -> str:
    """safe_text line by line (it keeps only the end of what it gets), newest lines last."""
    from tools.collector_repairs import safe_text

    return '\n'.join(filter(None, (safe_text(line) for line in text.splitlines())))[-limit:]


def render(template: str, **values) -> str:
    """Fill the __NAME__ placeholders. Every value is shell-quoted; a list becomes separate words."""
    def fill(match: re.Match) -> str:
        value = values[match[1].lower()]
        items = value if isinstance(value, (list, tuple)) else [value]
        return ' '.join(shlex.quote(str(item)) for item in items)
    return re.sub(r'__([A-Z]+(?:_[A-Z]+)*)__', fill, template)


def _wire(script: str, payload: bytes | None) -> bytes:
    """What bash reads from stdin. The script runs as one function with stdin closed: a transfer
    cut short runs nothing, and no command can swallow the lines that follow it. A payload goes
    after the last line and is read back by exact length into "$payload", checked by sha256."""
    body = script.replace('\r\n', '\n').strip('\n')
    if payload is None:
        return f'set -euo pipefail\nmain() {{\n{body}\n}}\nmain </dev/null\n'.encode('utf-8')
    digest = hashlib.sha256(payload).hexdigest()
    return (f'set -euo pipefail\nwork=$(mktemp -d)\ntrap \'rm -rf "$work"\' EXIT\npayload=$work/payload\n'
            f'main() {{\n{body}\n}}\n'
            f'{{ head -c {len(payload)} >"$payload"; echo "{digest}  $payload" | sha256sum --check --status'
            f' || {{ echo "repairbot: payload corrupto" >&2; exit 97; }}; main </dev/null; }}\n'
            ).encode('utf-8') + payload


def ssh(settings, script: str, *, timeout: int = 60, stdin: bytes | None = None, runner=gitops.run) -> str:
    """Run a bash script on the VPS and return its stdout. A non-zero exit raises a sanitized VpsError."""
    argv = [SSH, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
            _checked(_HOST, settings.ssh_host, 'ssh_host'), 'bash', '-s']
    env = {key: value for key, value in os.environ.items() if key not in ENV_KEYS}
    try:
        result = runner(argv, input=_wire(script, stdin), capture_output=True, timeout=timeout, env=env,
                        creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise VpsError(f'el VPS no respondió en {timeout}s') from None
    except OSError as error:
        raise VpsError(f'no se pudo ejecutar ssh: {type(error).__name__}') from None
    if result.returncode:
        detail = _safe((result.stderr or b'').decode('utf-8', errors='replace'), 600) or 'sin detalle'
        raise VpsError(f'ssh terminó con código {result.returncode}: {detail}', result.returncode)
    return (result.stdout or b'').decode('utf-8', errors='replace')


def _call(settings, template: str, kw: dict, *, timeout: int = 60, stdin: bytes | None = None, **values) -> str:
    root = _checked(_ROOT, settings.vps_root, 'vps_root')
    script = render(template, root=root, python=f'{root}/.venv/bin/python', worker=WORKER_UNIT,
                    watchdog=WATCHDOG_UNIT, hostname=_checked(_HOST, settings.vps_hostname, 'vps_hostname'),
                    **values)
    return ssh(settings, script, **{'timeout': timeout, 'stdin': stdin, **kw})


def _facts(out: str) -> dict[str, list[str]]:
    facts: dict[str, list[str]] = {}
    for line in out.splitlines():
        key, separator, value = line.partition('=')
        if separator and re.fullmatch(r'[a-z_]+', key):
            facts.setdefault(key, []).append(value)
    return facts


def _one(facts: dict[str, list[str]], key: str) -> str:
    return (facts.get(key) or [''])[0].strip()


def _decoded(facts: dict[str, list[str]], key: str) -> str:
    return base64.b64decode(_one(facts, key), validate=True).decode('utf-8', errors='replace')


def status(settings, **kw) -> dict:
    facts = _facts(_call(settings, STATUS, kw))
    hostname, head = _one(facts, 'hostname'), _one(facts, 'head')
    if not hostname or not _SHA.fullmatch(head):
        raise VpsError('el VPS devolvió un estado incompleto')
    return {'hostname': hostname, 'head': head, 'dirty': [line[3:] for line in facts.get('dirty', [])],
            'worker_active': _one(facts, 'worker') == 'active',
            'watchdog_active': _one(facts, 'watchdog') == 'active'}


def logs(settings, source: str, minutes: int = 180, max_lines: int = 150, **kw) -> str:
    """Recent worker journal lines that mention the source (or the collector file it shares)."""
    from tools.collector_repairs import COLLECTOR_FILES

    names = dict.fromkeys((_checked(_NAME, source, 'source'),
                           _checked(_NAME, COLLECTOR_FILES.get(source, source), 'collector')))
    return _safe(_call(settings, LOGS, kw, since=f'-{_number(minutes, "minutes", 1, 10080)}min',
                       lines=_number(max_lines, 'max_lines', 1, 2000),
                       patterns=[word for name in names for word in ('-e', name)]))


def _filters_blob(filters: dict | None) -> tuple[str, int]:
    """Collector filters as base64 JSON of strings, the form tools.repro_target reads as k=v."""
    if filters is None:
        filters = {}
    if not isinstance(filters, dict) or len(filters) > 24:
        raise VpsError('filters inválido: se espera un objeto de hasta 24 claves')
    items = {}
    for key, value in filters.items():
        _checked(_KEY, key, 'filtro')
        if value is None:
            continue
        if isinstance(value, bool):
            value = int(value)
        if not isinstance(value, (str, int, float)):
            raise VpsError(f'filtro {key}: solo texto o números')
        text = str(value)
        if len(text) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise VpsError(f'filtro {key}: valor inválido')
        items[key] = text
    blob = base64.b64encode(json.dumps(items, ensure_ascii=False).encode('utf-8')).decode('ascii')
    return blob, len(items)


def _stage_archive(raw: bytes) -> bytes:
    """git's tar of worker/ as the gzip the probe extracts: no tests, no bytecode, plain modes."""
    out = io.BytesIO()
    names = set()
    with tarfile.open(fileobj=io.BytesIO(raw)) as source, tarfile.open(fileobj=out, mode='w:gz') as target:
        for member in source:
            parts = member.name.split('/')
            if (not member.isfile() or parts[1:2] == ['tests'] or '__pycache__' in parts
                    or member.name.endswith('.pyc')):
                continue
            member.mode = 0o755 if member.mode & 0o100 else 0o644
            member.uid = member.gid = 0
            member.uname = member.gname = ''
            target.addfile(member, source.extractfile(member))
            names.add(member.name)
    if 'worker/tools/repro_target.py' not in names:
        raise VpsError('el clon no tiene worker/tools/repro_target.py: no hay nada que reproducir')
    return out.getvalue()


def _take_probe(settings, run_dir: Path) -> int:
    counter = run_dir / 'probes'
    try:
        used = int(counter.read_text(encoding='ascii').strip() or 0)
    except FileNotFoundError:
        used = 0
    except ValueError:
        used = settings.max_probes   # an unreadable counter cannot grant more probes
    if used >= settings.max_probes:
        raise VpsError(f'se alcanzó el tope de {settings.max_probes} probes de este intento')
    counter.write_text(str(used + 1), encoding='ascii')
    return used + 1


def _last_json(text: str) -> dict | None:
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith('{')]
    for candidate in (text.strip(), *reversed(lines)):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _probe_result(out: str) -> dict:
    facts = _facts(out)
    if failure := _one(facts, 'fail'):
        raise VpsError({'wrong_host': 'el servidor no es el VPS esperado',
                        'filters': 'el VPS no pudo leer los filtros'}.get(failure, f'el probe no corrió: {failure}'))
    try:
        code = int(_one(facts, 'exit'))
        stdout, stderr = _decoded(facts, 'stdout'), _decoded(facts, 'stderr')
    except ValueError:
        raise VpsError('el VPS devolvió una respuesta ilegible al probe') from None
    result = _last_json(stdout)
    if result is None:
        result = {'error': 'la reproducción no devolvió JSON', 'stdout_tail': _safe(stdout, 1500)}
    result.update(supported=True, exit_code=code, stderr_tail=_safe(stderr, 3000))
    if code in (124, 137):
        result['timed_out'] = True
    return result


def probe(settings, repo: Path, source: str, *, target_id: int | None, filters: dict | None,
          run_id: str, timeout: int = 420, git_runner=gitops.run, **kw) -> dict:
    """Reproduce one search on the VPS with the clone's code, without ingesting anything.
    Returns tools.repro_target's JSON plus exit_code and stderr_tail."""
    args = [_checked(_NAME, source, 'source')]
    run_id = _checked(_NAME, run_id, 'run_id')
    if target_id is None:
        args.append('--no-db')
    else:
        args += ['--target-id', str(_number(target_id, 'target_id', 1, 2**62))]
    seconds = _number(timeout, 'timeout', 10, 1800)
    blob, count = _filters_blob(filters)
    if source in UNSUPPORTED:
        return {'supported': False, 'reason': UNSUPPORTED[source]}
    run_dir = settings.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with Lock(run_dir / 'probe.lock') as lock:   # one staging tree per run: probes do not overlap
        if not lock.acquired:
            raise VpsError('ya hay un probe en curso para este intento')
        try:
            outside = gitops.scope_violations(gitops.changed_paths(repo, runner=git_runner), settings.allowed_paths)
            if outside:
                raise VpsError('el probe no lleva al VPS cambios fuera del alcance permitido: '
                               + ', '.join(outside[:10]))
            archive = _stage_archive(gitops.worktree_tar(repo, 'worker', runner=git_runner))
        except gitops.GitError as error:
            raise VpsError(str(error)) from None
        used = _take_probe(settings, run_dir)
        result = _probe_result(_call(settings, PROBE, kw, timeout=seconds + 90, stdin=archive, run_id=run_id,
                                     args=[*args, '--json'], blob=blob, count=count, seconds=seconds))
        result['probes_left'] = settings.max_probes - used
        (run_dir / f'probe-{used}.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result


def deploy(settings, sha: str, base: str, **kw) -> dict:
    """Fast-forward the VPS checkout from `base` to `sha` (already pushed). No restart here.
    Returns {ok, code, reason, prev_head, head, contains}; a refusal or an unreachable VPS is ok=False.
    head is the VPS HEAD as last read and contains says whether it is sha or descends from it, so
    `head == sha or contains` tells whether the VPS has the fix, whatever the code. A VPS that
    already contains sha is 'already' (ok). With head None the HEAD is unknown: 'ssh_error' and
    'wrong_host' changed nothing, while 'unknown_state' means the merge was sent but neither its
    answer nor a second read came back: the VPS may or may not be on sha (contains False then
    means unknown, not no)."""
    sha, base = _checked(_SHA, sha, 'sha'), _checked(_SHA, base, 'base')
    result = {'ok': False, 'prev_head': None, 'head': None, 'contains': False, 'reason': '', 'code': ''}

    def done(code: str, reason: str, ok: bool = False) -> dict:
        result.update(ok=ok, code=code, reason=reason)
        return result

    def settle(code: str, reason: str, *, lost: bool = False) -> dict:
        """The apply's answer does not say where the checkout ended up: ask again. With `lost`
        the apply may still be running on the VPS (ssh gave up, the remote script did not), so
        a HEAD still at prev proves nothing: that is 'unknown_state', never a failure."""
        try:
            facts = _facts(_call(settings, DEPLOY_HEAD, kw, sha=sha))
            why = _one(facts, 'fail') or ('' if _SHA.fullmatch(_one(facts, 'head')) else 'respuesta sin HEAD')
        except VpsError as error:
            why = str(error) or type(error).__name__
        if why:
            result.update(head=None, contains=False)
            return done('unknown_state', f'{reason}; no se pudo releer el HEAD del VPS ({why}): '
                                         f'puede haber quedado o no en {sha[:12]}')
        head = _one(facts, 'head')
        result.update(head=head, contains=head == sha or _one(facts, 'contains') == '1')
        if lost and not result['contains']:
            return done('unknown_state', f'{reason}; el VPS sigue en {head[:12]}, pero el merge pudo '
                                         'quedar en curso: puede terminar o no en ' + sha[:12])
        return done(code, f'{reason} (el VPS está en {head[:12]})')

    try:
        facts = _facts(_call(settings, DEPLOY_INSPECT, kw, timeout=240, sha=sha, base=base))
    except VpsError as error:
        return done('ssh_error', str(error) or type(error).__name__)
    host, prev = _one(facts, 'hostname'), _one(facts, 'head')
    if host != settings.vps_hostname:
        return done('wrong_host', f'el servidor respondió como {host[:60]!r}, no como {settings.vps_hostname}')
    if not _SHA.fullmatch(prev):
        return done('ssh_error', 'el VPS no informó su HEAD')
    result.update(prev_head=prev, head=prev, contains=prev == sha or _one(facts, 'contains') == '1')
    if dirty := facts.get('dirty'):
        return done('dirty', 'el checkout del VPS tiene cambios sin commitear: '
                    + ', '.join(line[3:] for line in dirty[:10]))
    if result['contains']:
        return done('already', 'el commit ya estaba desplegado' if prev == sha
                    else f'el VPS ya contiene el commit (está en {prev[:12]})', ok=True)
    if 'missing' in facts:
        return done('missing_commit', 'el VPS no encuentra el commit en origin (¿falta el push?)')
    if _one(facts, 'on_main') != '1':
        return done('not_on_main', 'el commit no está en origin/main')
    blocking = [name for name in (line.strip('"') for line in facts.get('pending', []))
                if name.startswith(('worker/', 'supabase/'))]
    if prev != base and blocking:
        return done('pending_changes', 'hay cambios sin desplegar que requieren a una persona: '
                    + ', '.join(blocking[:10]))
    try:
        facts = _facts(_call(settings, DEPLOY_APPLY, kw, timeout=180, sha=sha, prev=prev))
    except VpsError as error:   # the merge may have run before the answer was lost
        return settle('ssh_error', str(error) or type(error).__name__, lost=True)
    failure, head = _one(facts, 'fail'), _one(facts, 'head')
    reason = _DEPLOY_FAILURES.get(failure, f'el deploy falló: {failure}')
    if failure in ('wrong_host', 'dirty'):   # stopped before the merge: the checkout is still at prev
        return done(failure, reason)
    if not _SHA.fullmatch(head):
        return settle(failure or 'ssh_error', reason if failure else 'el VPS no confirmó el deploy')
    result.update(head=head, contains=head == sha)   # the merge only ever moves HEAD from prev to sha
    if failure:
        try:
            detail = _safe(_decoded(facts, 'detail'), 600) if 'detail' in facts else ''
        except ValueError:
            return done('ssh_error', f'{reason}; el detalle llegó ilegible')
        return done(failure, f'{reason}: {detail}' if detail else reason)
    if 'done' not in facts or head != sha:
        return done('ssh_error', 'el VPS no confirmó el deploy')
    return done('deployed', '', ok=True)


def restart_worker(settings, **kw) -> dict:
    """Restart the worker and check it stays up: {ok, active, reason}."""
    try:
        facts = _facts(_call(settings, RESTART, kw, timeout=180))
    except VpsError as error:
        return {'ok': False, 'active': False, 'reason': str(error)}
    if _one(facts, 'fail'):
        return {'ok': False, 'active': False, 'reason': 'el servidor no es el VPS esperado'}
    state = _one(facts, 'state')
    active = state == 'active'
    stable = _one(facts, 'stable') == '1'
    reason = '' if active and stable else (f'el worker quedó {state or "sin estado"}' if not active
                                           else 'el worker se reinició solo después de arrancar')
    return {'ok': active and stable, 'active': active, 'reason': reason}


def cleanup(settings, run_id: str, **kw) -> None:
    """Remove the run's staging tree. Best effort: an unreachable VPS is logged, not raised."""
    run_id = _checked(_NAME, run_id, 'run_id')
    try:
        if 'done' not in _facts(_call(settings, CLEANUP, kw, run_id=run_id)):
            raise VpsError('el VPS no confirmó la limpieza')
    except VpsError as error:
        log.warning('no se limpió el staging de %s: %s', run_id, error)


def _parse_filters(items: list[str]) -> dict[str, str]:
    filters = {}
    for item in items:
        key, separator, value = item.partition('=')
        if not separator:
            raise VpsError(f'filtro inválido (se espera clave=valor): {item[:60]!r}')
        filters[key.strip()] = value.strip()
    return filters


def main(argv: list[str] | None = None, *, runner=gitops.run) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(prog='python -m repairbot.vps', description='Consultas al VPS del worker.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='commit desplegado y estado de los servicios')
    journal = commands.add_parser('logs', help='journal reciente del worker para una fuente')
    journal.add_argument('source')
    journal.add_argument('--minutes', type=int, default=180)
    journal.add_argument('--lines', type=int, default=150)
    repro = commands.add_parser('probe', help='reproducir una búsqueda en el VPS con el código del clon, sin ingesta')
    repro.add_argument('source')
    repro.add_argument('--target-id', type=int)
    repro.add_argument('filters', nargs='*', metavar='clave=valor')
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:   # unknown command (deploy, restart, ...) or bad arguments
        return stop.code if isinstance(stop.code, int) else 2
    try:
        settings = load()
        if args.command == 'status':
            result = status(settings, runner=runner)
        elif args.command == 'logs':
            lines = logs(settings, args.source, args.minutes, args.lines, runner=runner).splitlines()
            result = {'source': args.source, 'minutes': args.minutes, 'lines': lines}
        else:
            run_id = os.environ.get('REPAIRBOT_RUN_ID', '')
            if not run_id:
                raise VpsError('falta REPAIRBOT_RUN_ID: probe solo corre dentro de un intento del bot')
            result = probe(settings, settings.repo, args.source, target_id=args.target_id,
                           filters=_parse_filters(args.filters), run_id=run_id, runner=runner)
    except Exception as error:
        print(json.dumps({'error': f'{type(error).__name__}: {error}'}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
