"""gitops against real temporary repositories: a bare 'origin', the bot's clone and a second
clone that plays everyone else pushing to main. Nothing leaves tmp_path."""
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
from types import SimpleNamespace

import pytest

from repairbot import gitops
from repairbot.gitops import GitError
from repairbot.settings import Settings

ALLOWED = ('worker/collectors/', 'worker/tests/', 'worker/http_clients.py')
SEED = {
    '.gitignore': '__pycache__/\n*.log\n.env\n',
    'docs/a.md': 'doc\n',
    'worker/collectors/kavak.py': 'PRICE = "old"\nYEAR = 1\n',
    'worker/collectors/old.py': 'legacy = True\nmore = True\n',
    'worker/http_clients.py': 'TIMEOUT = 20\n',
    'worker/pipeline/crawl.py': 'def run():\n    return 1\n',
    'worker/tests/test_kavak.py': 'def test_ok():\n    assert True\n',
    'worker/tools/repro_target.py': 'print("{}")\n',
}


def git(repo, *args) -> str:
    result = subprocess.run(['git', *args], cwd=repo, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr.decode('utf-8', 'replace')
    return result.stdout.decode('utf-8', 'replace').strip()


def clone(origin: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    git(target.parent, 'clone', '--quiet', '--template=',                     # no sample hooks: quicker copies
        '--config', 'core.autocrlf=true',                                     # CRLF checkouts, as on the PC
        '--config', 'user.name=Test', '--config', 'user.email=test@example.test',
        '--config', 'commit.gpgsign=false', str(origin), str(target))
    return target


def write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode('utf-8'))


def publish(repo: Path, message: str, **files) -> str:
    for name, text in files.items():
        write(repo, name, text)
    git(repo, 'add', '-A')
    git(repo, 'commit', '--quiet', '-m', message)
    git(repo, 'push', '--quiet', 'origin', 'HEAD:main')
    return git(repo, 'rev-parse', 'HEAD')


@pytest.fixture(scope='module')
def template(tmp_path_factory):
    """origin + both clones, built once: every test works on its own copy."""
    root = tmp_path_factory.mktemp('gitops')
    (root / 'gitconfig').write_text('', encoding='utf-8')
    with pytest.MonkeyPatch.context() as patch:
        isolate(patch, root / 'gitconfig')
        origin = root / 'w' / 'origin.git'
        origin.parent.mkdir()
        git(root, 'init', '--quiet', '--template=', '--bare', '--initial-branch=main', str(origin))
        other = clone(origin, root / 'w' / 'other')
        git(other, 'checkout', '--quiet', '-B', 'main')
        base = publish(other, 'base', **SEED)
        clone(origin, root / 'w' / 'bot home' / 'repo')   # a path with a space, like many on Windows
    return SimpleNamespace(root=root, base=base)


def isolate(patch, blank: Path) -> None:
    patch.setenv('GIT_CONFIG_GLOBAL', str(blank))   # the developer's own git config stays out
    patch.setenv('GIT_CONFIG_NOSYSTEM', '1')
    patch.delenv('REPAIRBOT_CONFIG', raising=False)


def repoint(checkout: Path, old: Path, new: Path) -> None:
    """`git remote set-url origin` for a copied clone, without a git process: its config names
    origin by absolute path, with backslashes escaped."""
    config = checkout / '.git' / 'config'
    escaped = [str(path).replace('\\', '\\\\') for path in (old, new)]
    text = config.read_text(encoding='utf-8')
    assert escaped[0] in text
    config.write_text(text.replace(*escaped), encoding='utf-8')


@pytest.fixture
def env(template, tmp_path, monkeypatch):
    isolate(monkeypatch, template.root / 'gitconfig')
    shutil.copytree(template.root / 'w', tmp_path / 'w')
    origin, other, repo = (tmp_path / 'w' / name for name in ('origin.git', 'other', 'bot home/repo'))
    for checkout in (other, repo):
        repoint(checkout, template.root / 'w' / 'origin.git', origin)
    settings = Settings(home=repo.parent, repo=repo, env_file=tmp_path / 'main checkout' / '.env',
                        python=Path(sys.executable), claude=Path('claude'), git_bash=Path('bash'))
    return SimpleNamespace(tmp=tmp_path, origin=origin, other=other, repo=repo, base=template.base,
                           settings=settings,
                           sync=lambda path=repo, **kw: gitops.sync(
                               path, **{'settings': settings, 'origin_url': str(origin), **kw}))


def text(path: Path) -> str:
    return path.read_bytes().decode('utf-8').replace('\r\n', '\n')


def dirty(repo: Path) -> None:
    """Local work of every kind: edited, deleted, untracked, ignored, staged and a local commit."""
    write(repo, 'worker/collectors/kavak.py', 'PRICE = "local"\n')
    git(repo, 'commit', '--quiet', '-am', 'local commit')
    write(repo, 'worker/collectors/kavak.py', 'PRICE = "edited"\n')
    (repo / 'docs/a.md').unlink()
    write(repo, 'worker/collectors/nuevo.py', 'x = 1\n')
    write(repo, 'worker/staged.py', 'y = 1\n')
    git(repo, 'add', 'worker/staged.py')
    write(repo, 'debug.log', 'ignored\n')
    write(repo, 'worker/__pycache__/kavak.cpython-312.pyc', 'bytecode')


def test_sync_discards_local_edits_commits_and_untracked_files(env):
    dirty(env.repo)
    newest = publish(env.other, 'upstream', **{'docs/b.md': 'nuevo\n'})
    assert env.sync() == newest
    assert git(env.repo, 'rev-parse', 'HEAD') == git(env.repo, 'rev-parse', 'origin/main') == newest
    assert git(env.repo, 'branch', '--show-current') == 'main'
    assert git(env.repo, 'status', '--porcelain', '--ignored') == ''
    assert text(env.repo / 'worker/collectors/kavak.py') == SEED['worker/collectors/kavak.py']
    assert (env.repo / 'docs/a.md').exists() and (env.repo / 'docs/b.md').exists()
    for gone in ('worker/collectors/nuevo.py', 'worker/staged.py', 'debug.log', 'worker/__pycache__'):
        assert not (env.repo / gone).exists()
    assert gitops.changed_paths(env.repo) == []
    assert env.sync() == newest   # idempotent


def test_sync_recovers_from_a_rebase_left_in_progress(env):
    publish(env.other, 'upstream', **{'worker/collectors/kavak.py': 'PRICE = "upstream"\nYEAR = 1\n'})
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "bot"\nYEAR = 1\n')
    git(env.repo, 'commit', '--quiet', '-am', 'bot')
    git(env.repo, 'fetch', '--quiet', 'origin')
    assert subprocess.run(['git', 'rebase', 'origin/main'], cwd=env.repo, capture_output=True).returncode != 0
    assert (env.repo / '.git' / 'rebase-merge').exists()
    env.sync()
    assert not (env.repo / '.git' / 'rebase-merge').exists()
    assert 'upstream' in text(env.repo / 'worker/collectors/kavak.py')
    assert git(env.repo, 'status', '--porcelain') == ''


def test_sync_clears_the_locks_of_a_git_that_was_killed(env):
    for name in ('index.lock', 'HEAD.lock', 'refs/heads/main.lock', 'refs/remotes/origin/main.lock'):
        (env.repo / '.git' / name).write_bytes(b'')
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "edited"\n')
    with pytest.raises(GitError):
        gitops.commit(env.repo, 'bloqueado')   # what every command does while the lock is there
    assert env.sync() == env.base
    assert not list((env.repo / '.git').rglob('*.lock'))
    assert text(env.repo / 'worker/collectors/kavak.py') == SEED['worker/collectors/kavak.py']


def assert_untouched(repo: Path, head: str) -> None:
    assert git(repo, 'rev-parse', 'HEAD') == head
    assert text(repo / 'worker/collectors/kavak.py') == 'PRICE = "edited"\n'
    assert (repo / 'worker/collectors/nuevo.py').exists() and (repo / 'debug.log').exists()
    assert not (repo / 'docs/a.md').exists()


def test_sync_refuses_any_directory_other_than_the_bot_clone(env):
    user_checkout = clone(env.origin, env.tmp / 'user checkout')
    dirty(user_checkout)
    head = git(user_checkout, 'rev-parse', 'HEAD')
    with pytest.raises(GitError, match='no es el clon del bot'):
        env.sync(user_checkout)
    assert_untouched(user_checkout, head)
    with pytest.raises(GitError, match='no es el clon del bot'):
        env.sync(env.repo / 'worker')
    with pytest.raises(GitError):
        env.sync(env.repo.parent)


def test_sync_refuses_an_unexpected_origin(env):
    dirty(env.repo)
    head = git(env.repo, 'rev-parse', 'HEAD')
    with pytest.raises(GitError, match='origin'):
        gitops.sync(env.repo, settings=env.settings)   # the default is the GitHub repository
    with pytest.raises(GitError, match='origin'):
        env.sync(origin_url=str(env.tmp / 'another.git'))
    git(env.repo, 'remote', 'set-url', '--push', 'origin', str(env.tmp / 'elsewhere.git'))
    with pytest.raises(GitError, match='origin'):
        env.sync()
    assert_untouched(env.repo, head)


def test_sync_refuses_a_subdirectory_configured_as_the_clone(env):
    dirty(env.repo)
    head = git(env.repo, 'rev-parse', 'HEAD')
    nested = Settings(**{**env.settings.__dict__, 'repo': env.repo / 'worker'})
    with pytest.raises(GitError, match='raíz'):
        env.sync(env.repo / 'worker', settings=nested)
    assert_untouched(env.repo, head)


def test_sync_refuses_a_clone_that_holds_the_launcher_env_file(env):
    dirty(env.repo)
    head = git(env.repo, 'rev-parse', 'HEAD')
    main_checkout = Settings(**{**env.settings.__dict__, 'env_file': env.repo / '.env'})
    with pytest.raises(GitError, match='.env'):
        env.sync(settings=main_checkout)
    assert_untouched(env.repo, head)


def test_sync_without_settings_reads_the_bot_configuration(env, monkeypatch):
    monkeypatch.setenv('REPAIRBOT_CONFIG', str(env.tmp / 'missing.json'))
    with pytest.raises(GitError, match='configuración'):
        gitops.sync(env.repo, origin_url=str(env.origin))
    config = env.tmp / 'config.json'
    config.write_text(json.dumps({key: str(getattr(env.settings, key)) for key in (
        'home', 'repo', 'env_file', 'python', 'claude', 'git_bash')}), encoding='utf-8')
    monkeypatch.setenv('REPAIRBOT_CONFIG', str(config))
    write(env.repo, 'worker/collectors/nuevo.py', 'x = 1\n')
    assert gitops.sync(env.repo, origin_url=str(env.origin)) == env.base
    assert not (env.repo / 'worker/collectors/nuevo.py').exists()
    with pytest.raises(GitError, match='no es el clon del bot'):
        gitops.sync(env.other, origin_url=str(env.origin))


def test_changed_paths_lists_new_modified_deleted_and_renamed_with_forward_slashes(env):
    repo = env.repo
    assert gitops.changed_paths(repo) == []
    write(repo, 'worker/collectors/kavak.py', 'PRICE = "new"\r\nYEAR = 1\r\n')
    os.makedirs(os.path.join(repo, 'worker', 'collectors', 'sub dir'))
    with open(os.path.join(repo, 'worker', 'collectors', 'sub dir', 'año nuevo.py'), 'w', encoding='utf-8') as handle:
        handle.write('x = 1\n')
    (repo / 'docs/a.md').unlink()
    git(repo, 'mv', 'worker/collectors/old.py', 'worker/collectors/renamed.py')
    os.rename(repo / 'worker/pipeline/crawl.py', repo / 'worker/collectors/moved.py')
    write(repo, 'worker/staged.py', 'y = 1\n')
    git(repo, 'add', 'worker/staged.py')
    write(repo, 'debug.log', 'ignored\n')
    write(repo, 'worker/__pycache__/x.pyc', 'ignored')
    before = git(repo, 'status', '--porcelain')
    assert gitops.changed_paths(repo) == [
        'docs/a.md',
        'worker/collectors/kavak.py',
        'worker/collectors/moved.py',
        'worker/collectors/old.py',
        'worker/collectors/renamed.py',
        'worker/collectors/sub dir/año nuevo.py',
        'worker/pipeline/crawl.py',
        'worker/staged.py',
    ]
    assert git(repo, 'status', '--porcelain') == before   # the real index was not touched


def test_line_ending_noise_is_not_a_change(env):
    path = env.repo / 'worker/collectors/kavak.py'
    assert b'\r\n' in path.read_bytes()   # autocrlf checkout
    path.write_bytes(SEED['worker/collectors/kavak.py'].encode())   # an editor that writes LF
    assert gitops.changed_paths(env.repo) == []
    assert gitops.diff_lines(env.repo) == 0


def test_same_size_edit_in_the_tick_of_the_index_write_is_still_seen(env):
    """Racy git: the snapshot index has to keep the real index's mtime, or git trusts the stat cache."""
    path, index = env.repo / 'worker/collectors/kavak.py', env.repo / '.git' / 'index'
    past = (time.time_ns() // 10**9 - 3600) * 10**9
    os.utime(path, ns=(past, past))
    git(env.repo, 'update-index', '--refresh')          # the entry now records `past`
    path.write_bytes(path.read_bytes().replace(b'old', b'new'))
    os.utime(path, ns=(past, past))                      # same size, same timestamp as the entry...
    os.utime(index, ns=(past, past))                     # ...written in the tick of the index itself
    for _ in range(2):
        assert gitops.changed_paths(env.repo) == ['worker/collectors/kavak.py']
        assert gitops.diff_lines(env.repo) == 2
    assert index.stat().st_mtime_ns == past              # and the real index was left alone


def test_diff_lines_counts_added_removed_and_new_files(env):
    repo = env.repo
    assert gitops.diff_lines(repo) == 0
    write(repo, 'worker/collectors/kavak.py', 'PRICE = "new"\r\nYEAR = 1\r\n')   # 1 added + 1 removed
    assert gitops.diff_lines(repo) == 2
    write(repo, 'worker/collectors/nuevo.py', 'a = 1\nb = 2\nc = 3\n')            # 3 added, untracked
    assert gitops.diff_lines(repo) == 5
    (repo / 'worker/collectors/old.py').unlink()                                   # 2 removed
    assert gitops.diff_lines(repo) == 7
    git(repo, 'add', '-A')                                                         # staged counts the same
    assert gitops.diff_lines(repo) == 7
    write(repo, 'debug.log', 'ignored\n' * 50)
    assert gitops.diff_lines(repo) == 7
    (repo / 'worker/tests/captura.bin').write_bytes(b'\x00\x01\x02' * 100)
    assert gitops.diff_lines(repo) == 7 + gitops.BINARY_LINES


def test_scope_violations():
    inside = ['worker/collectors/kavak.py', 'worker/collectors/sub/x.py', 'worker\\collectors\\kavak.py',
              './worker/tests/test_kavak.py', 'worker/tests/fixtures/html/kavak.html', 'worker/http_clients.py']
    assert gitops.scope_violations(inside, ALLOWED) == []
    outside = ['worker/pipeline/crawl.py', 'worker\\tools\\repro_target.py', 'worker/http_clients.py.bak',
               'worker/http_clients.py/x', 'worker/collectors', 'worker/collectors/../config.py',
               'worker/tests/../../.github/workflows/ci.yml', 'Worker/Collectors/kavak.py',
               '/worker/collectors/kavak.py', 'C:/automotive-bot/repo/worker/collectors/kavak.py',
               'supabase/migrations/1.sql', '.gitignore', 'docs/a.md', '']
    assert gitops.scope_violations(outside, ALLOWED) == [path.replace('\\', '/') for path in outside]
    assert gitops.scope_violations(inside[:1] + outside[:1] + inside[1:2], ALLOWED) == ['worker/pipeline/crawl.py']
    assert gitops.scope_violations(inside, ()) == [path.replace('\\', '/').removeprefix('./') for path in inside]


def test_scope_check_sees_the_old_name_of_a_file_moved_into_the_allowed_tree(env):
    os.rename(env.repo / 'worker/pipeline/crawl.py', env.repo / 'worker/collectors/crawl.py')
    assert gitops.scope_violations(gitops.changed_paths(env.repo), ALLOWED) == ['worker/pipeline/crawl.py']


def test_commit_records_everything_and_returns_the_sha(env):
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\r\nYEAR = 1\r\n')
    write(env.repo, 'worker/tests/test_nuevo.py', 'def test_x():\n    assert 1\n')
    (env.repo / 'worker/collectors/old.py').unlink()
    message = gitops.commit_message('kavak', 'Lee el precio nuevo', 'Cambió el atributo.', 'inc-1', 'run-1')
    sha = gitops.commit(env.repo, message)
    assert sha == git(env.repo, 'rev-parse', 'HEAD') and len(sha) == 40
    assert git(env.repo, 'rev-parse', 'HEAD~1') == env.base
    assert git(env.repo, 'status', '--porcelain') == ''
    assert git(env.repo, 'log', '-1', '--format=%B') == message.strip()
    assert git(env.repo, 'show', '--name-status', '--format=', 'HEAD').split('\n') == [
        'M\tworker/collectors/kavak.py', 'D\tworker/collectors/old.py', 'A\tworker/tests/test_nuevo.py']
    assert git(env.repo, 'show', 'HEAD:worker/collectors/kavak.py') == 'PRICE = "new"\nYEAR = 1'   # stored with LF
    assert git(env.repo, 'log', '-1', '--format=%(trailers:key=Repair-Incident,valueonly)').strip() == 'inc-1'
    with pytest.raises(GitError, match='commit'):
        gitops.commit(env.repo, 'nada que commitear')


def test_push_fast_path(env):
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\nYEAR = 1\n')
    sha = gitops.commit(env.repo, 'fix(kavak): precio')
    assert gitops.push(env.repo) == sha
    assert git(env.origin, 'rev-parse', 'main') == sha
    assert gitops.push(env.repo) == sha   # nothing left to publish


def test_push_rebases_when_origin_moved(env):
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\nYEAR = 1\n')
    local = gitops.commit(env.repo, 'fix(kavak): precio')
    upstream = publish(env.other, 'upstream', **{'docs/b.md': 'nuevo\n', 'worker/http_clients.py': 'TIMEOUT = 30\n'})
    sha = gitops.push(env.repo)
    assert sha != local and sha == git(env.repo, 'rev-parse', 'HEAD') == git(env.origin, 'rev-parse', 'main')
    assert gitops.parent(env.repo, sha) == upstream   # the base a deploy has to compare against
    assert gitops.parent(env.repo, upstream) == env.base
    for bad in ('HEAD', '--all', 'abc', None, 7):
        with pytest.raises(GitError, match='sha inválido'):
            gitops.parent(env.repo, bad)
    with pytest.raises(GitError):
        gitops.parent(env.repo, env.base)                  # the first commit has no parent
    assert git(env.repo, 'log', '-1', '--format=%s') == 'fix(kavak): precio'
    assert git(env.repo, 'show', 'HEAD:worker/collectors/kavak.py').startswith('PRICE = "new"')
    assert git(env.repo, 'show', 'HEAD:worker/http_clients.py') == 'TIMEOUT = 30'
    assert git(env.repo, 'status', '--porcelain') == ''
    assert not (env.repo / '.git' / 'rebase-merge').exists()


def test_push_conflict_aborts_the_rebase_and_publishes_nothing(env):
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "bot"\nYEAR = 1\n')
    local = gitops.commit(env.repo, 'fix(kavak): precio')
    upstream = publish(env.other, 'upstream', **{'worker/collectors/kavak.py': 'PRICE = "upstream"\nYEAR = 1\n'})
    with pytest.raises(GitError, match='conflicto'):
        gitops.push(env.repo)
    assert git(env.origin, 'rev-parse', 'main') == upstream
    assert git(env.repo, 'rev-parse', 'HEAD') == local
    assert git(env.repo, 'branch', '--show-current') == 'main'
    assert git(env.repo, 'status', '--porcelain') == ''
    for leftover in ('rebase-merge', 'rebase-apply', 'MERGE_HEAD'):
        assert not (env.repo / '.git' / leftover).exists()
    assert 'bot' in text(env.repo / 'worker/collectors/kavak.py')


def test_push_retries_once_when_main_moves_between_fetch_and_push(env):
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\nYEAR = 1\n')
    gitops.commit(env.repo, 'fix(kavak): precio')
    raced = []

    def racing(argv, **kw):
        if argv[1] == 'push' and not raced:   # someone else lands a commit right before our first push
            raced.append(publish(env.other, 'carrera', **{'docs/c.md': 'x\n'}))
        return subprocess.run(argv, **kw)
    sha = gitops.push(env.repo, runner=racing)
    assert git(env.origin, 'rev-parse', 'main') == sha
    assert git(env.repo, 'rev-parse', 'HEAD~1') == raced[0]


def test_push_failure_is_a_git_error(env):
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\nYEAR = 1\n')
    gitops.commit(env.repo, 'fix(kavak): precio')
    git(env.repo, 'remote', 'set-url', 'origin', str(env.tmp / 'gone.git'))
    with pytest.raises(GitError, match='fetch'):
        gitops.push(env.repo)


def test_revert_undoes_a_published_fix(env):
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\nYEAR = 1\n')
    write(env.repo, 'worker/tests/test_nuevo.py', 'def test_x():\n    assert 1\n')
    gitops.commit(env.repo, 'fix(kavak): precio')
    fix = gitops.push(env.repo)
    sha = gitops.revert(env.repo, fix, 'revert(kavak): el arreglo no recuperó la fuente\n\nRepair-Incident: inc-1\n')
    assert sha == git(env.repo, 'rev-parse', 'HEAD') != fix
    assert git(env.repo, 'rev-parse', 'HEAD~1') == fix
    assert git(env.repo, 'log', '-1', '--format=%s') == 'revert(kavak): el arreglo no recuperó la fuente'
    assert git(env.repo, 'diff', '--stat', env.base, 'HEAD') == ''   # same tree as before the fix
    assert not (env.repo / 'worker/tests/test_nuevo.py').exists()
    assert git(env.repo, 'status', '--porcelain') == ''
    assert gitops.push(env.repo) == sha


def test_revert_rejects_bad_shas_and_cleans_up_after_a_conflict(env):
    for bad in ('', 'HEAD', '--abort', 'main', 'abc', 'g' * 40, None):
        with pytest.raises(GitError, match='sha'):
            gitops.revert(env.repo, bad, 'x')
    with pytest.raises(GitError):
        gitops.revert(env.repo, 'f' * 40, 'x')   # well formed, unknown
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\nYEAR = 1\n')
    fix = gitops.commit(env.repo, 'fix')
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "newer"\nYEAR = 1\n')
    later = gitops.commit(env.repo, 'later')
    with pytest.raises(GitError):
        gitops.revert(env.repo, fix, 'x')
    assert git(env.repo, 'rev-parse', 'HEAD') == later
    assert git(env.repo, 'status', '--porcelain') == ''
    assert not (env.repo / '.git' / 'REVERT_HEAD').exists()


def test_commit_message_format():
    message = gitops.commit_message(
        'kavak', '  Lee el precio\ndel nuevo atributo data-price. ',
        'El sitio renombró el atributo.\n\nSe ajustó el selector.',
        'a183b3b6-ae12-4bf1-add2-c2569ad64fa2', 'run-20261013-1')
    assert message == ('fix(kavak): Lee el precio del nuevo atributo data-price\n\n'
                       'El sitio renombró el atributo.\n\nSe ajustó el selector.\n\n'
                       'Repair-Incident: a183b3b6-ae12-4bf1-add2-c2569ad64fa2\n'
                       'Repair-Run: run-20261013-1\n'
                       'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n')
    bare = gitops.commit_message('sc_clasificados', '', '', 'inc-1', 'run-1')
    assert bare.startswith('fix(sc_clasificados): reparación automática del collector\n\nRepair-Incident: inc-1\n')
    assert len(gitops.commit_message('kavak', 'x' * 500, '', 'inc-1', 'run-1').split('\n')[0]) <= 140


def test_commit_message_drops_secrets_and_rejects_malformed_ids():
    message = gitops.commit_message(
        'kavak', 'Arregla https://user:pwd@example.test/api?token=abc123',
        'Fallaba con Authorization: Bearer hidden-value', 'inc-1', 'run-1')
    for secret in ('pwd', 'abc123', 'hidden-value'):
        assert secret not in message
    assert message.endswith('Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n')
    for bad in (dict(source='kavak\nRepair-Incident: otro'), dict(source=''), dict(source='-x'),
                dict(incident_id='inc 1'), dict(incident_id='a\nb'), dict(run_id='../x'), dict(run_id=None),
                dict(run_id=7)):
        values = {'source': 'kavak', 'incident_id': 'inc-1', 'run_id': 'run-1', **bad}
        with pytest.raises(GitError, match='inválido'):
            gitops.commit_message(values['source'], 's', 'c', values['incident_id'], values['run_id'])


def test_worktree_tar_is_what_a_commit_would_record(env):
    repo = env.repo
    write(repo, 'worker/collectors/kavak.py', 'PRICE = "candidate"\r\nYEAR = 1\r\n')
    write(repo, 'worker/collectors/nuevo.py', 'x = 1\r\n')
    (repo / 'worker/collectors/old.py').unlink()
    write(repo, 'worker/debug.log', 'ignored\n')
    write(repo, 'worker/.env', 'DATABASE_URL=x\n')
    write(repo, 'worker/collectors/__pycache__/kavak.cpython-312.pyc', 'bytecode')
    before = git(repo, 'status', '--porcelain')
    with tarfile.open(fileobj=io.BytesIO(gitops.worktree_tar(repo, 'worker'))) as archive:
        files = {member.name: archive.extractfile(member).read() for member in archive if member.isfile()}
    assert sorted(files) == ['worker/collectors/kavak.py', 'worker/collectors/nuevo.py', 'worker/http_clients.py',
                             'worker/pipeline/crawl.py', 'worker/tests/test_kavak.py', 'worker/tools/repro_target.py']
    assert files['worker/collectors/kavak.py'] == b'PRICE = "candidate"\nYEAR = 1\n'   # LF, as Linux checks it out
    assert files['worker/collectors/nuevo.py'] == b'x = 1\n'
    assert files['worker/pipeline/crawl.py'] == SEED['worker/pipeline/crawl.py'].encode()
    assert git(repo, 'status', '--porcelain') == before
    with pytest.raises(GitError):
        gitops.worktree_tar(repo, 'no-such-dir')


def test_every_git_call_is_bounded_non_interactive_and_free_of_launcher_secrets(env, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://bot:secret@db/app')
    monkeypatch.setenv('RESEND_API_KEY', 're_secret')
    monkeypatch.setenv('GIT_TERMINAL_PROMPT', '1')
    calls = []

    def recording(argv, **kw):
        calls.append((argv, kw))
        return subprocess.run(argv, **kw)
    write(env.repo, 'worker/collectors/kavak.py', 'PRICE = "new"\nYEAR = 1\n')
    assert gitops.changed_paths(env.repo, runner=recording) == ['worker/collectors/kavak.py']
    assert gitops.diff_lines(env.repo, runner=recording) == 2
    fix = gitops.commit(env.repo, 'fix', runner=recording)
    publish(env.other, 'upstream', **{'docs/b.md': 'nuevo\n'})
    pushed = gitops.push(env.repo, runner=recording)
    gitops.revert(env.repo, pushed, 'revert', runner=recording)
    env.sync(runner=recording)
    gitops.worktree_tar(env.repo, runner=recording)
    assert fix != pushed and len(calls) > 25
    assert {argv[1] for argv, _ in calls} >= {'fetch', 'push', 'rebase', 'reset', 'clean', 'commit', 'revert', 'add'}
    for argv, kw in calls:
        assert argv[0] == 'git' and isinstance(argv, list) and not kw.get('shell')
        assert 0 < kw['timeout'] <= 180
        assert kw['env']['GIT_TERMINAL_PROMPT'] == '0' and kw['env']['GCM_INTERACTIVE'] == 'never'
        assert not {'DATABASE_URL', 'RESEND_API_KEY'} & set(kw['env'])
        assert kw['capture_output'] is True and Path(kw['cwd']) == env.repo


def test_timeout_and_missing_git_become_git_errors(env):
    def slow(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw['timeout'])
    with pytest.raises(GitError, match='sin respuesta'):
        gitops.head(env.repo, runner=slow)

    def missing(argv, **kw):
        raise FileNotFoundError(2, 'git')
    with pytest.raises(GitError, match='FileNotFoundError'):
        gitops.changed_paths(env.repo, runner=missing)


def alive(pid: int) -> bool:
    if os.name == 'nt':
        listing = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, timeout=30)
        return str(pid).encode() in listing.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_run_captures_output_and_feeds_stdin():
    echo = [sys.executable, '-c', 'import sys; data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data[::-1]); '
                                  'sys.stderr.write("err"); sys.exit(3 if data else 4)']
    result = gitops.run(echo, input=b'abc\x00\xff', timeout=30)
    assert (result.returncode, result.stdout, result.stderr) == (3, b'\xff\x00cba', b'err')
    assert gitops.run(echo, timeout=30).returncode == 4   # without input stdin is closed, not inherited
    with pytest.raises(FileNotFoundError):
        gitops.run(['no-such-program-repairbot'], timeout=5)


def test_run_timeout_ends_the_children_that_hold_the_pipes(tmp_path):
    """git fetch leaves git-remote-https holding git's stdout: killing only git would block forever."""
    marker = tmp_path / 'grandchild.pid'
    parent = ('import subprocess, sys, time\n'
              'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdout=sys.stdout)\n'
              f'open(r"{marker}", "w").write(str(child.pid))\n'
              'time.sleep(120)\n')
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        gitops.run([sys.executable, '-c', parent], timeout=2)   # the marker is written within ~0.2 s
    assert time.monotonic() - started < 40
    grandchild = int(marker.read_text())
    deadline = time.monotonic() + 10
    while alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.2)
    assert not alive(grandchild)
