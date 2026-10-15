"""python -m repairbot around its tick: the trace a failure leaves before bot.log exists (pythonw has
no console) and the PC kept from idle-sleeping while the tick runs. No real power calls."""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import sys
import types

import pytest

from repairbot import __main__ as cli, watchdog

AWAKE = cli.ES_CONTINUOUS | cli.ES_SYSTEM_REQUIRED


@pytest.fixture
def config(tmp_path, monkeypatch) -> Path:
    """A valid config.json in its own folder; REPAIRBOT_CONFIG and LOCALAPPDATA point into tmp_path."""
    monkeypatch.setattr(cli, 'setup_logging', lambda state_dir: None)
    monkeypatch.setenv('REPAIRBOT_CONFIG', str(tmp_path / 'absent.json'))   # main overwrites it; restored after
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    env = tmp_path / '.env'
    env.write_text('UNRELATED=1\n', encoding='utf-8')
    path = tmp_path / 'bot' / 'config.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'home': str(tmp_path / 'home'), 'repo': str(tmp_path / 'repo'),
                                'env_file': str(env), 'python': sys.executable, 'claude': 'claude.exe',
                                'git_bash': 'bash.exe'}), encoding='utf-8')
    return path


@pytest.fixture
def pythonw(monkeypatch):
    """No console, as under the scheduled task."""
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)


def bootstrap(config: Path) -> list[str]:
    return (config.parent / 'state' / cli.BOOTSTRAP_LOG).read_text(encoding='utf-8').splitlines()


def ok_tick(settings, dry_run):
    return {'ok': True, 'actions': [], 'errors': []}


# --------------------------------------------------------------------------------------
# Before bot.log: bot-bootstrap.log
# --------------------------------------------------------------------------------------

def test_a_broken_config_leaves_a_timestamped_line_next_to_it_under_pythonw(config, pythonw):
    config.write_text('{"enabled": False}', encoding='utf-8')   # Python's spelling, not JSON
    assert cli.main(['--config', str(config)], tick=ok_tick) == 2
    line, = bootstrap(config)
    stamp, message = line.split(' ', 1)
    assert datetime.fromisoformat(stamp).tzinfo is not None
    assert message.startswith('config: JSONDecodeError: ')


def test_every_tick_with_an_unknown_key_says_which(config, pythonw):
    raw = json.loads(config.read_text(encoding='utf-8'))
    config.write_text(json.dumps({**raw, 'max_sessions_per_dia': 4}), encoding='utf-8')
    assert cli.main(['--config', str(config)]) == 2
    assert cli.main(['--config', str(config)]) == 2
    lines = bootstrap(config)
    assert len(lines) == 2
    assert all(line.endswith('config: ValueError: config.json: claves desconocidas: max_sessions_per_dia')
               for line in lines)


def test_without_config_it_looks_where_load_looks(tmp_path, monkeypatch, pythonw):
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('REPAIRBOT_CONFIG', str(tmp_path / 'elsewhere' / 'config.json'))
    assert cli.main([]) == 2
    assert 'config: FileNotFoundError' in bootstrap(tmp_path / 'elsewhere' / 'config.json')[0]


def test_it_falls_back_to_localappdata(config, pythonw):
    (config.parent / 'state').write_text('un archivo, no una carpeta', encoding='utf-8')
    config.write_text('{', encoding='utf-8')
    assert cli.main(['--config', str(config)]) == 2
    written = Path(os.environ['LOCALAPPDATA']) / 'repairbot' / cli.BOOTSTRAP_LOG
    assert 'config: JSONDecodeError' in written.read_text(encoding='utf-8')


def test_the_fallback_never_raises(config, monkeypatch, pythonw):
    (config.parent / 'state').write_text('x', encoding='utf-8')
    monkeypatch.delenv('LOCALAPPDATA')
    config.write_text('{', encoding='utf-8')
    assert cli.main(['--config', str(config)]) == 2
    assert cli.bootstrap_log('x', config) is None


def test_a_log_that_cannot_be_opened_is_reported_there_too(config, monkeypatch, pythonw):
    def broken(state_dir):
        raise PermissionError('acceso denegado')
    monkeypatch.setattr(cli, 'setup_logging', broken)
    assert cli.main(['--config', str(config)], tick=ok_tick) == 2
    assert bootstrap(config)[0].endswith('log: PermissionError: acceso denegado')


def test_bad_arguments_are_reported_there_too(tmp_path, config, pythonw):
    with pytest.raises(SystemExit) as stopped:
        cli.main(['--nope'])
    assert stopped.value.code == 2
    assert bootstrap(tmp_path / 'absent.json')[0].endswith("argumentos inválidos: ['--nope']")


def test_the_bootstrap_log_keeps_one_line_per_failure_and_does_not_grow_forever(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'LOG_BYTES', 40)
    config = tmp_path / 'config.json'
    path = cli.bootstrap_log('uno\n  dos', config)
    assert path == tmp_path / 'state' / cli.BOOTSTRAP_LOG
    assert path.read_text(encoding='utf-8').endswith(' uno dos\n')
    cli.bootstrap_log('tres', config)
    assert cli.bootstrap_log('cuatro', config) == path
    assert [line.split(' ', 1)[1] for line in path.read_text(encoding='utf-8').splitlines()] == ['cuatro']
    assert 'tres' in (tmp_path / 'state' / f'{cli.BOOTSTRAP_LOG}.1').read_text(encoding='utf-8')


# --------------------------------------------------------------------------------------
# Around the tick: no idle sleep
# --------------------------------------------------------------------------------------

def test_the_tick_runs_with_idle_sleep_held_off(config):
    calls = []

    def tick(settings, dry_run):
        calls.append('tick')
        return {'ok': True, 'actions': [], 'errors': []}

    assert cli.main(['--config', str(config)], tick=tick, awake=calls.append) == 0
    assert calls == [AWAKE, 'tick', cli.ES_CONTINUOUS]


def test_idle_sleep_is_released_even_when_the_tick_blows_up(config):
    calls = []

    def tick(settings, dry_run):
        raise RuntimeError('boom')

    healed = []
    assert cli.main(['--config', str(config)], tick=tick, awake=calls.append,
                    healer=lambda settings: healed.append(settings) or 'lanzador actualizado') == 2
    assert calls == [AWAKE, cli.ES_CONTINUOUS]
    assert len(healed) == 1


def test_a_bot_that_cannot_be_imported_leaves_a_trace_and_heals_the_launcher(config, monkeypatch):
    # A broken commit on main must not stop the bot silently, nor forever: the launcher is
    # fast-forwarded anyway, so the next fix on main brings it back.
    import repairbot

    monkeypatch.delattr(repairbot, 'bot', raising=False)
    monkeypatch.setitem(sys.modules, 'repairbot.bot', None)   # import fails
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)
    healed = []
    rc = cli.main(['--config', str(config)], awake=lambda state: None,
                  healer=lambda settings: healed.append(settings) or 'lanzador actualizado')
    assert rc == 2 and len(healed) == 1
    text = (config.parent / 'state' / cli.BOOTSTRAP_LOG).read_text(encoding='utf-8')
    assert 'tick: ' in text and 'lanzador actualizado' in text


def test_a_dry_run_that_crashes_does_not_touch_the_launcher(config):
    def tick(settings, dry_run):
        raise RuntimeError('boom')

    healed = []
    assert cli.main(['--config', str(config), '--dry-run'], tick=tick, awake=lambda state: None,
                    healer=healed.append) == 2
    assert healed == []


def test_heal_falls_back_to_plain_git_and_refuses_the_workspace(tmp_path, monkeypatch):
    from repairbot import gitops

    def broken(*args, **kwargs):
        raise RuntimeError('rota')

    monkeypatch.setattr(gitops, 'update_launcher', broken)
    launcher = tmp_path / 'launcher'
    (launcher / '.git').mkdir(parents=True)
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv[3:])
        return types.SimpleNamespace(returncode=0, stdout='', stderr='')

    settings = types.SimpleNamespace(launcher=launcher, repo=tmp_path / 'repo')
    assert 'actualizado con git' in cli.heal(settings, runner=runner)
    assert calls == [['status', '--porcelain'], ['fetch', '-q', 'origin'], ['merge', '--ff-only', '-q', 'origin/main']]
    same = types.SimpleNamespace(launcher=launcher, repo=launcher)
    calls.clear()
    assert 'sin actualizar' in cli.heal(same, runner=runner) and calls == []


def test_status_does_not_hold_the_pc_awake(config):
    calls = []
    assert cli.main(['--config', str(config), '--status'], status=lambda settings: {}, awake=calls.append) == 0
    assert calls == []


def test_a_failing_power_call_never_stops_the_tick(config):
    calls = []

    def broken(state):
        calls.append(state)
        raise OSError('sin kernel32')

    assert cli.main(['--config', str(config)], tick=ok_tick, awake=broken) == 0
    assert calls == [AWAKE]          # nothing to undo when it was never set


def test_off_windows_there_is_nothing_to_call(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    assert cli._execution_state() is None
    with cli.keep_awake():
        pass


@pytest.mark.skipif(sys.platform != 'win32', reason='kernel32 solo existe en Windows')
def test_on_windows_it_is_kernel32s_function():
    function = cli._execution_state()    # looked up, never called here
    assert function.__name__ == 'SetThreadExecutionState'


def test_every_tick_runs_under_the_idle_watchdog_and_disarms_after(config):
    armed = []

    def arm(seconds, on_expire):
        armed.append((seconds, on_expire))
        watchdog._deadline = float('inf')           # as if armed

    def tick(settings, dry_run):
        assert watchdog._deadline is not None       # watched while it runs
        return {'errors': []}

    assert cli.main(['--config', str(config)], tick=tick, awake=lambda state: None, arm=arm) == 0
    assert [seconds for seconds, _ in armed] == [watchdog.IDLE_LIMIT_S]
    assert watchdog._deadline is None


def test_a_crashing_tick_still_disarms(config):
    def tick(settings, dry_run):
        raise RuntimeError('boom')

    cli.main(['--config', str(config)], tick=tick, awake=lambda state: None,
             arm=lambda seconds, on_expire: None, healer=lambda settings: 'ok')
    assert watchdog._deadline is None


def test_a_hung_tick_leaves_a_trace(config, pythonw):
    hooks = []
    cli.main(['--config', str(config)], tick=lambda settings, dry_run: {'errors': []},
             awake=lambda state: None, arm=lambda seconds, on_expire: hooks.append(on_expire))
    hooks[0](660.0)
    text = (config.parent / 'state' / cli.BOOTSTRAP_LOG).read_text(encoding='utf-8')
    assert 'tick colgado' in text and '11 min' in text


def test_status_is_not_watched(config):
    armed = []
    cli.main(['--config', str(config), '--status'], status=lambda settings: {},
             arm=lambda seconds, on_expire: armed.append(seconds))
    assert armed == []
