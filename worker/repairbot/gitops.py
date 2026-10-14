"""Git for the bot's dedicated clone.

`sync` is the only destructive function (reset --hard + clean) and refuses to run anywhere
but Settings.repo with the expected origin. The rest reads the clone or publishes one commit.
Git never sees the launcher's secrets and never prompts.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile

from repairbot.settings import ENV_KEYS, ORIGIN_URL, Settings, load

GIT = 'git'
CO_AUTHOR = 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'
BINARY_LINES = 10_000   # a binary file has no line count: it never fits under max_diff_lines
LOCAL_TIMEOUT = 60
NETWORK_TIMEOUT = 180
_NAME = re.compile(r'(?!-)[A-Za-z0-9_-]{1,64}')
_SHA = re.compile(r'[0-9a-f]{7,40}')
_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class GitError(RuntimeError):
    pass


def kill_tree(pid: int) -> None:
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, timeout=30,
                           creationflags=_NO_WINDOW)
        else:
            os.killpg(pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass


def run(argv: list[str], *, timeout: float, input: bytes | None = None, cwd: str | None = None,
        env: dict[str, str] | None = None, capture_output: bool = True,
        creationflags: int = 0) -> subprocess.CompletedProcess:
    """subprocess.run with captured output, except that a timeout ends the whole process tree.
    git-remote-https inherits git's pipes: with only git killed, run() keeps waiting on them."""
    process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               stdin=subprocess.DEVNULL if input is None else subprocess.PIPE,
                               creationflags=creationflags, start_new_session=os.name != 'nt')
    try:
        out, err = process.communicate(input, timeout=timeout)
    except BaseException:
        kill_tree(process.pid)
        try:
            process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            pass
        raise
    return subprocess.CompletedProcess(argv, process.returncode, out, err)


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key not in ENV_KEYS}
    env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    env.update(extra or {})
    return env


def _run(repo: Path, *args: str, runner, timeout: int = LOCAL_TIMEOUT, check: bool = True,
         stdin: bytes | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    label = ' '.join(args)[:80]
    if not os.path.exists(os.path.join(repo, '.git')):   # never let git walk up to a parent repository
        raise GitError(f'{repo} no es la raíz de un repositorio git')
    try:
        result = runner([GIT, *args], cwd=str(repo), env=_env(env), input=stdin, capture_output=True,
                        timeout=timeout, creationflags=_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise GitError(f'git {label}: sin respuesta en {timeout}s') from None
    except OSError as error:
        raise GitError(f'git {label}: {type(error).__name__}') from None
    if check and result.returncode:
        detail = (result.stderr or result.stdout or b'').decode('utf-8', errors='replace').strip()
        raise GitError(f'git {label} falló ({result.returncode}): {" ".join(detail.split())[-400:]}')
    return result


def _git(repo: Path, *args: str, runner, **options) -> str:
    return _run(repo, *args, runner=runner, **options).stdout.decode('utf-8', errors='replace')


def head(repo: Path, *, runner=run) -> str:
    return _git(repo, 'rev-parse', 'HEAD', runner=runner).strip()


def _checked_sha(sha, what: str) -> str:
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise GitError(f'{what}: sha inválido: {str(sha)[:60]!r}')
    return sha


def parent(repo: Path, sha: str, *, runner=run) -> str:
    """The commit `sha` sits on: the `base` that vps.deploy compares with what the VPS runs."""
    return _git(repo, 'rev-parse', '--verify', f'{_checked_sha(sha, "parent")}~1', runner=runner).strip()


def _same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _remote(url: str) -> str:
    return url.strip().rstrip('/').removesuffix('.git').lower()


def _require_bot_clone(repo: Path, settings: Settings | None, origin_url: str, runner) -> None:
    try:
        settings = settings or load()
    except Exception as error:
        raise GitError(f'sync: no se pudo leer la configuración del bot ({type(error).__name__})') from None
    if not _same_path(repo, settings.repo):
        raise GitError(f'sync: {repo} no es el clon del bot ({settings.repo})')
    inside = os.path.normcase(os.path.abspath(repo)) + os.sep
    if os.path.normcase(os.path.abspath(settings.env_file)).startswith(inside):
        raise GitError('sync: el clon del bot no puede contener el .env del lanzador')
    top = _git(repo, 'rev-parse', '--show-toplevel', runner=runner).strip()
    if not os.path.samefile(top, repo):
        raise GitError(f'sync: {repo} no es la raíz de un repositorio')
    for direction in ((), ('--push',)):
        urls = _git(repo, 'remote', 'get-url', '--all', *direction, 'origin', runner=runner).split('\n')
        if [_remote(url) for url in urls if url.strip()] != [_remote(origin_url)]:
            raise GitError('sync: el remoto origin no es el repositorio esperado')


def sync(repo: Path, *, settings: Settings | None = None, origin_url: str = ORIGIN_URL,
         runner=run) -> str:
    """Leave the bot's clone identical to origin/main and return its sha. Discards everything local."""
    repo = Path(repo)
    _require_bot_clone(repo, settings, origin_url, runner)
    # Nothing else uses this clone while the bot holds its lock: a *.lock here is what a git
    # killed on timeout left behind, and it would fail every later command.
    for stale in (repo / '.git').rglob('*.lock'):
        stale.unlink(missing_ok=True)
    _run(repo, 'rebase', '--abort', runner=runner, check=False)   # left behind by a push that crashed
    _run(repo, 'fetch', '--prune', 'origin', runner=runner, timeout=NETWORK_TIMEOUT)
    _run(repo, 'checkout', '--force', '-B', 'main', 'origin/main', runner=runner)
    _run(repo, 'reset', '--hard', 'origin/main', runner=runner)
    _run(repo, 'clean', '-ffdx', runner=runner, timeout=NETWORK_TIMEOUT)
    return head(repo, runner=runner)


@contextmanager
def _snapshot(repo: Path, runner):
    """Environment whose index holds what `commit` would record (add -A); the real index is untouched."""
    with tempfile.TemporaryDirectory(prefix='repairbot-index-') as directory:
        index = Path(directory) / 'index'
        current = Path(repo, _git(repo, 'rev-parse', '--git-path', 'index', runner=runner).strip())
        if current.exists():
            # The copy keeps the stat cache (add -A only hashes what changed) and must keep the
            # file's mtime too: git re-reads entries as old as the index itself, and with a newer
            # index a same-size edit made within that second would go unseen.
            shutil.copy2(current, index)
        env = {'GIT_INDEX_FILE': str(index)}
        _run(repo, 'add', '-A', runner=runner, env=env, timeout=NETWORK_TIMEOUT)
        yield env


def _pending(repo: Path, runner, *options: str) -> list[str]:
    with _snapshot(repo, runner) as env:
        out = _git(repo, 'diff', '--cached', '--no-renames', '-z', *options, 'HEAD', runner=runner, env=env)
    return [record for record in out.split('\0') if record]


def changed_paths(repo: Path, *, runner=run) -> list[str]:
    """Modified, deleted and untracked (not ignored) paths against HEAD, with '/' separators.
    A rename lists both names: the old one counts for the scope check."""
    return sorted(_pending(repo, runner, '--name-only'))


def diff_lines(repo: Path, *, runner=run) -> int:
    """Lines added plus removed against HEAD, new files included."""
    total = 0
    for record in _pending(repo, runner, '--numstat'):
        added, removed, _path = record.split('\t', 2)
        total += BINARY_LINES if added == '-' else int(added) + int(removed)
    return total


def scope_violations(paths: list[str], allowed: tuple[str, ...]) -> list[str]:
    """The paths outside `allowed`; an entry ending in '/' allows a directory, any other one file."""
    violations = []
    for raw in paths:
        path = raw.replace('\\', '/')
        while path.startswith('./'):
            path = path[2:]
        inside = any(path.startswith(entry) if entry.endswith('/') else path == entry for entry in allowed)
        if not inside or '..' in path.split('/'):
            violations.append(path)
    return violations


def worktree_tar(repo: Path, prefix: str = 'worker', *, runner=run) -> bytes:
    """Uncompressed tar of what `commit` would record under prefix, as git stores it (LF endings,
    nothing ignored), so a probe on Linux runs the same bytes a deploy would check out."""
    with _snapshot(repo, runner) as env:
        tree = _git(repo, 'write-tree', runner=runner, env=env).strip()
    # archive converts to the working-tree line endings unless told otherwise.
    return _run(repo, '-c', 'core.autocrlf=false', 'archive', '--format=tar', tree, '--', prefix,
                runner=runner, timeout=NETWORK_TIMEOUT).stdout


def commit(repo: Path, message: str, *, runner=run) -> str:
    _run(repo, 'add', '-A', runner=runner, timeout=NETWORK_TIMEOUT)
    _run(repo, 'commit', '--quiet', '-F', '-', runner=runner, stdin=message.encode('utf-8'))
    return head(repo, runner=runner)


def push(repo: Path, *, runner=run) -> str:
    """Publish HEAD as origin/main, rebasing first when main moved. Returns the published sha."""
    failure = None
    for _ in range(2):   # the second round covers a push that landed between our fetch and our push
        _run(repo, 'fetch', 'origin', runner=runner, timeout=NETWORK_TIMEOUT)
        ancestor = _run(repo, 'merge-base', '--is-ancestor', 'origin/main', 'HEAD', runner=runner, check=False)
        if ancestor.returncode not in (0, 1):
            raise GitError('push: no se pudo comparar HEAD con origin/main')
        if ancestor.returncode and _run(repo, 'rebase', 'origin/main', runner=runner, check=False,
                                        timeout=NETWORK_TIMEOUT).returncode:
            _run(repo, 'rebase', '--abort', runner=runner, check=False)
            raise GitError('push: origin/main avanzó y el arreglo no se pudo reaplicar encima (conflicto)')
        try:
            _run(repo, 'push', 'origin', 'HEAD:main', runner=runner, timeout=NETWORK_TIMEOUT)
            return head(repo, runner=runner)
        except GitError as error:
            failure = error
    raise failure


def revert(repo: Path, sha: str, message: str, *, runner=run) -> str:
    """Commit the inverse of `sha` on top of HEAD (the rollback of a deployed fix)."""
    _checked_sha(sha, 'revert')
    try:
        _run(repo, 'revert', '--no-commit', sha, runner=runner)
        _run(repo, 'commit', '--quiet', '-F', '-', runner=runner, stdin=message.encode('utf-8'))
    except GitError:
        _run(repo, 'revert', '--abort', runner=runner, check=False)
        raise
    return head(repo, runner=runner)


def commit_message(source: str, summary: str, root_cause: str, incident_id: str, run_id: str) -> str:
    """fix(<source>): <summary> + cause + trailers. The free text comes from the model: it is
    sanitized here because this is where it leaves the machine."""
    from tools.collector_repairs import safe_text

    incident_id = str(incident_id)
    for name, value in (('source', source), ('incident_id', incident_id), ('run_id', run_id)):
        if not isinstance(value, str) or not _NAME.fullmatch(value):
            raise GitError(f'commit_message: {name} inválido: {str(value)[:60]!r}')
    subject = ' '.join(safe_text(summary).split())[:120].rstrip(' .') or 'reparación automática del collector'
    cause = '\n'.join(safe_text(line) for line in str(root_cause or '').strip().splitlines())[:1500].strip()
    body = f'{cause}\n\n' if cause else ''
    return (f'fix({source}): {subject}\n\n{body}'
            f'Repair-Incident: {incident_id}\nRepair-Run: {run_id}\n{CO_AUTHOR}\n')
