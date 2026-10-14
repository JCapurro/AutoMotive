"""Git for the bot's dedicated clone, and for the launcher's own clone.

`sync` is the only destructive function (reset --hard + clean) and refuses to run anywhere
but Settings.repo with the expected origin. The rest reads the clone or publishes one commit;
`update_launcher` only fast-forwards the separate clone the scheduled task runs from.
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
_FULL_SHA = re.compile(r'[0-9a-f]{40}')
_TRAILER = re.compile(r'[A-Za-z0-9-]+: \S.*')
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


def _checked_name(value, what: str, name: str) -> str:
    if not isinstance(value, str) or not _NAME.fullmatch(value):
        raise GitError(f'{what}: {name} inválido: {str(value)[:60]!r}')
    return value


def parent(repo: Path, sha: str, *, runner=run) -> str:
    """The commit `sha` sits on: the `base` that vps.deploy compares with what the VPS runs."""
    return _git(repo, 'rev-parse', '--verify', f'{_checked_sha(sha, "parent")}~1', runner=runner).strip()


def _same_path(a, b) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _inside(path, folder) -> bool:
    return os.path.normcase(os.path.abspath(path)).startswith(os.path.normcase(os.path.abspath(folder)) + os.sep)


def _remote(url: str) -> str:
    return url.strip().rstrip('/').removesuffix('.git').lower()


def _settings(settings: Settings | None, what: str) -> Settings:
    try:
        return settings or load()
    except Exception as error:
        raise GitError(f'{what}: no se pudo leer la configuración del bot ({type(error).__name__})') from None


def _require_clone_of_origin(repo: Path, origin_url: str, runner, what: str) -> None:
    top = _git(repo, 'rev-parse', '--show-toplevel', runner=runner).strip()
    if not os.path.samefile(top, repo):
        raise GitError(f'{what}: {repo} no es la raíz de un repositorio')
    for direction in ((), ('--push',)):
        urls = _git(repo, 'remote', 'get-url', '--all', *direction, 'origin', runner=runner).split('\n')
        if [_remote(url) for url in urls if url.strip()] != [_remote(origin_url)]:
            raise GitError(f'{what}: el remoto origin no es el repositorio esperado')


def _require_bot_clone(repo: Path, settings: Settings | None, origin_url: str, runner) -> None:
    settings = _settings(settings, 'sync')
    if not _same_path(repo, settings.repo):
        raise GitError(f'sync: {repo} no es el clon del bot ({settings.repo})')
    if _inside(settings.env_file, repo):
        raise GitError('sync: el clon del bot no puede contener el .env del lanzador')
    _require_clone_of_origin(repo, origin_url, runner, 'sync')


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


def update_launcher(path: Path, *, settings: Settings | None = None, origin_url: str = ORIGIN_URL,
                    runner=run) -> str:
    """Fast-forward the clone the scheduled task runs from to origin/main and return its HEAD.
    It is a clone of its own that Claude never works in, so it is never reset or cleaned:
    local changes, local commits or a clone that is not the expected one stop the update."""
    path = Path(path)
    settings = _settings(settings, 'lanzador')
    if _same_path(path, settings.repo) or _inside(path, settings.repo):
        raise GitError(f'lanzador: {path} no puede ser el clon de trabajo del bot ni estar dentro de él')
    if _inside(settings.env_file, path):
        raise GitError('lanzador: el clon del lanzador no puede contener el .env')
    if not (path / '.git').is_dir():   # a worktree would share refs and objects with another checkout
        raise GitError(f'lanzador: {path} no es la raíz de un clon propio')
    _require_clone_of_origin(path, origin_url, runner, 'lanzador')
    if _git(path, 'status', '--porcelain', runner=runner).strip():
        raise GitError(f'lanzador: {path} tiene cambios locales; no se actualiza')
    _run(path, 'fetch', 'origin', runner=runner, timeout=NETWORK_TIMEOUT)
    if not _is_ancestor(path, 'HEAD', 'origin/main', runner, 'lanzador'):
        raise GitError(f'lanzador: {path} tiene commits que no están en origin/main; no se actualiza')
    _run(path, 'merge', '--ff-only', '--quiet', 'origin/main', runner=runner, timeout=NETWORK_TIMEOUT)
    return head(path, runner=runner)


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


def _is_ancestor(repo: Path, older: str, newer: str, runner, what: str) -> bool:
    code = _run(repo, 'merge-base', '--is-ancestor', older, newer, runner=runner, check=False).returncode
    if code not in (0, 1):
        raise GitError(f'{what}: no se pudo comparar {older} con {newer}')
    return code == 0


def push(repo: Path, *, runner=run) -> str:
    """Publish HEAD, exactly one commit on top of origin/main, as origin/main (rebased first when
    main moved). Returns the published sha.
    A GitError does NOT mean that nothing landed: a push can reach origin and still fail here (its
    answer lost, then the retry's fetch failing too). The caller asks landed() before deciding."""
    failure = None
    for _ in range(2):   # the second round covers a push that landed between our fetch and our push
        try:
            _run(repo, 'fetch', 'origin', runner=runner, timeout=NETWORK_TIMEOUT)
        except GitError as error:
            if failure is None:
                raise
            raise GitError(f'push sin confirmar ({failure}); después {error}') from None
        if failure is not None and _is_ancestor(repo, 'HEAD', 'origin/main', runner, 'push'):
            return head(repo, runner=runner)   # the first push landed: only its answer was lost
        rebased = not _is_ancestor(repo, 'origin/main', 'HEAD', runner, 'push')
        if rebased and _run(repo, 'rebase', 'origin/main', runner=runner, check=False,
                            timeout=NETWORK_TIMEOUT).returncode:
            _run(repo, 'rebase', '--abort', runner=runner, check=False)
            raise GitError('push: origin/main avanzó y el arreglo no se pudo reaplicar encima (conflicto)')
        # A rebase drops a commit whose change main already has: HEAD would be someone else's commit.
        _commit, *parents = _git(repo, 'rev-list', '--parents', '-n', '1', 'HEAD', runner=runner).split()
        if parents != [_git(repo, 'rev-parse', 'origin/main', runner=runner).strip()]:
            raise GitError('push: el arreglo quedó vacío al rebasar: main ya lo contiene' if rebased
                           else 'push: HEAD no es un único commit nuevo encima de origin/main')
        try:
            _run(repo, 'push', 'origin', 'HEAD:main', runner=runner, timeout=NETWORK_TIMEOUT)
            return head(repo, runner=runner)
        except GitError as error:
            failure = error
    raise failure


def _with_trailers(message: str, trailers: list[str]) -> str:
    """The message plus the trailer lines it lacks, ahead of the co-author line when it has one."""
    lines = message.replace('\r\n', '\n').rstrip('\n').split('\n')
    missing = [line for line in trailers if line not in lines]
    if CO_AUTHOR in lines:
        at = lines.index(CO_AUTHOR)
    else:
        if missing and not (len(lines) > 2 and _TRAILER.fullmatch(lines[-1])):
            lines.append('')
        at = len(lines)
    lines[at:at] = missing
    return '\n'.join(lines) + '\n'


def revert(repo: Path, sha: str, message: str, *, run_id: str | None = None, runner=run) -> str:
    """Commit the inverse of `sha` on top of HEAD (the rollback of a deployed fix). The message
    gains 'Repair-Revert: <sha>' and, with run_id, 'Repair-Run: <run_id>': landed() finds it by them."""
    _checked_sha(sha, 'revert')
    trailers = []
    if run_id is not None:
        run_id = _checked_name(run_id, 'revert', 'run_id')
        if any(line.startswith('Repair-Run:') and line.strip() != f'Repair-Run: {run_id}'
               for line in message.splitlines()):
            raise GitError('revert: el mensaje ya nombra otro Repair-Run')
        trailers.append(f'Repair-Run: {run_id}')
    full = _git(repo, 'rev-parse', '--verify', '--quiet', f'{sha}^{{commit}}', runner=runner).strip()
    message = _with_trailers(message, [*trailers, f'Repair-Revert: {full}'])
    try:
        _run(repo, 'revert', '--no-commit', full, runner=runner)
        _run(repo, 'commit', '--quiet', '-F', '-', runner=runner, stdin=message.encode('utf-8'))
    except GitError:
        _run(repo, 'revert', '--abort', runner=runner, check=False)
        raise
    return head(repo, runner=runner)


def landed(repo: Path, run_id: str, *, reverts: str | None = None, runner=run) -> str | None:
    """After a fetch, the sha of run_id's commit on origin/main, or None: its fix (the commit with
    'Repair-Run: <run_id>' and no Repair-Revert), or with `reverts` (a full sha) the revert of it.
    How the caller settles a push that raised: push() failing does not mean nothing landed."""
    wanted = {f'Repair-Run: {_checked_name(run_id, "landed", "run_id")}'}
    if reverts is not None:
        if not isinstance(reverts, str) or not _FULL_SHA.fullmatch(reverts):
            raise GitError(f'landed: sha inválido: {str(reverts)[:60]!r}')
        wanted.add(f'Repair-Revert: {reverts}')
    _run(repo, 'fetch', 'origin', runner=runner, timeout=NETWORK_TIMEOUT)
    out = _git(repo, 'log', '-z', '--format=%H%n%B', '--fixed-strings', f'--grep=Repair-Run: {run_id}',
               'origin/main', runner=runner, timeout=NETWORK_TIMEOUT)
    for record in out.split('\0'):
        sha, _, body = record.strip('\n').partition('\n')
        lines = {line.strip() for line in body.splitlines()}
        is_revert = any(line.startswith('Repair-Revert:') for line in lines)
        if wanted <= lines and is_revert == (reverts is not None):
            return sha
    return None


def commit_message(source: str, summary: str, root_cause: str, incident_id: str, run_id: str) -> str:
    """fix(<source>): <summary> + cause + trailers. The free text comes from the model: it is
    sanitized here because this is where it leaves the machine."""
    from tools.collector_repairs import safe_text

    incident_id = str(incident_id)
    for name, value in (('source', source), ('incident_id', incident_id), ('run_id', run_id)):
        _checked_name(value, 'commit_message', name)
    subject = ' '.join(safe_text(summary).split())[:120].rstrip(' .') or 'reparación automática del collector'
    cause = '\n'.join(safe_text(line) for line in str(root_cause or '').strip().splitlines())[:1500].strip()
    body = f'{cause}\n\n' if cause else ''
    return (f'fix({source}): {subject}\n\n{body}'
            f'Repair-Incident: {incident_id}\nRepair-Run: {run_id}\n{CO_AUTHOR}\n')
