"""python -m repairbot [--dry-run] [--status] [--config PATH]

One tick of the repair bot, run every 5 minutes by the \\AutoMotive\\RepairBot task with cwd
<home>/launcher/worker (a clone Claude never works in). Prints a one-line JSON summary; exit 0,
or 2 on an internal error. The log rotates in <home>/state/bot.log. What fails before that log
exists (a broken config.json) goes to <config dir>/state/bot-bootstrap.log, or
%LOCALAPPDATA%/repairbot/. A tick that cannot even import the bot (a broken commit on main)
still fast-forwards the launcher clone, so the next fix on main brings the bot back.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys

from repairbot import watchdog
from repairbot.settings import DEFAULT_CONFIG, load, load_env

LOG_BYTES = 2_000_000
LOG_BACKUPS = 5
BOOTSTRAP_LOG = 'bot-bootstrap.log'
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _print(value: dict, indent: int | None = None) -> None:
    if sys.stdout is None:   # pythonw (the scheduled task): no console
        return
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(json.dumps(value, ensure_ascii=False, default=str, indent=indent))


def bootstrap_log(message: str, config: Path | None = None) -> Path | None:
    """Appends a timestamped line where the owner will find it without a working config.json.

    Under pythonw nothing else would show the error. Returns the file written, or None; never raises.
    """
    line = f'{datetime.now().astimezone().isoformat(timespec="seconds")} {" ".join(message.split())}\n'
    folders = []
    try:
        folders.append(Path(config or os.environ.get('REPAIRBOT_CONFIG') or DEFAULT_CONFIG).absolute().parent / 'state')
    except Exception:
        pass
    if os.environ.get('LOCALAPPDATA'):
        folders.append(Path(os.environ['LOCALAPPDATA']) / 'repairbot')
    for folder in folders:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / BOOTSTRAP_LOG
            if path.is_file() and path.stat().st_size > LOG_BYTES:
                os.replace(path, folder / f'{BOOTSTRAP_LOG}.1')
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(line)
            return path
        except Exception:
            continue
    return None


def setup_logging(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = os.path.abspath(state_dir / 'bot.log')
    root = logging.getLogger()
    if any(getattr(handler, 'baseFilename', None) == path for handler in root.handlers):
        return
    # Not delayed: a bot.log that cannot be opened must fail here, where the bootstrap log reports it.
    handler = RotatingFileHandler(path, maxBytes=LOG_BYTES, backupCount=LOG_BACKUPS, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for noisy in ('httpx', 'httpcore', 'psycopg', 'psycopg.pool'):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _execution_state():
    """kernel32.SetThreadExecutionState, or None off Windows."""
    if sys.platform != 'win32':
        return None
    import ctypes

    function = ctypes.WinDLL('kernel32').SetThreadExecutionState
    function.argtypes, function.restype = [ctypes.c_uint32], ctypes.c_uint32
    return function


@contextmanager
def keep_awake(set_state=None):
    """No idle sleep while a tick runs: a suspend would end the Claude session as a timeout and spend
    an attempt. Closing the lid still sleeps. Best effort: it never stops the tick."""
    log = logging.getLogger('repairbot')
    try:
        set_state = set_state or _execution_state()
        if set_state:
            set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
    except Exception:
        log.warning('no se pudo evitar la suspensión de la PC', exc_info=True)
        set_state = None
    try:
        yield
    finally:
        if set_state:
            try:
                set_state(ES_CONTINUOUS)
            except Exception:
                log.warning('no se pudo devolver la suspensión de la PC', exc_info=True)


def heal(settings, runner=subprocess.run) -> str:
    """Fast-forward the launcher clone after a tick that crashed, without trusting the bot's code:
    gitops when it imports, plain git otherwise. Returns what happened; never raises."""
    try:
        from repairbot import gitops

        return 'lanzador en ' + gitops.update_launcher(settings.launcher, settings=settings)[:12]
    except Exception as error:
        first = f'{type(error).__name__}: {error}'
    launcher = Path(settings.launcher)
    try:
        if launcher.resolve() == Path(settings.repo).resolve() or not (launcher / '.git').is_dir():
            return f'lanzador sin actualizar ({first})'
        env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'never'}
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        for args in (('status', '--porcelain'), ('fetch', '-q', 'origin'), ('merge', '--ff-only', '-q', 'origin/main')):
            done = runner(['git', '-C', str(launcher), *args], capture_output=True, text=True,
                          timeout=180, env=env, creationflags=flags)
            if done.returncode or (args[0] == 'status' and done.stdout.strip()):
                return f'lanzador sin actualizar: git {args[0]} falló ({first})'
        return f'lanzador actualizado con git ({first})'
    except Exception as error:
        return f'lanzador sin actualizar: {type(error).__name__}: {error} ({first})'


def main(argv: list[str] | None = None, *, tick=None, status=None, awake=None, healer=heal,
         arm=None) -> int:
    parser = argparse.ArgumentParser(prog='python -m repairbot', description='Bot de reparación de collectors.')
    parser.add_argument('--dry-run', action='store_true', help='informa qué haría, sin reclamar, escribir ni correr nada')
    parser.add_argument('--status', action='store_true', help='incidentes activos y estado local del bot')
    parser.add_argument('--once', action='store_true', help=argparse.SUPPRESS)   # every run is one tick
    parser.add_argument('--config', type=Path, help='config.json (por defecto REPAIRBOT_CONFIG o C:/automotive-bot/config.json)')
    try:
        args = parser.parse_args(argv)
    except SystemExit as stop:
        if stop.code:   # under pythonw argparse's message goes nowhere
            bootstrap_log(f'argumentos inválidos: {sys.argv[1:] if argv is None else argv}')
        raise
    try:
        if args.config:
            # The Claude child and the CLIs it runs (repairbot.vps) find the same file through the environment.
            os.environ['REPAIRBOT_CONFIG'] = str(args.config.resolve())
        settings = load(args.config)
    except Exception as error:
        message = f'config: {type(error).__name__}: {error}'
        bootstrap_log(message, args.config)
        _print({'ok': False, 'error': message})
        return 2
    try:
        setup_logging(settings.state_dir)
    except Exception as error:
        message = f'log: {type(error).__name__}: {error}'
        bootstrap_log(message, args.config)
        _print({'ok': False, 'error': message})
        return 2
    log = logging.getLogger('repairbot')
    try:
        load_env(settings)   # before anything imports config, db or tools
    except Exception as error:
        log.exception('no se pudo leer %s', settings.env_file)
        _print({'ok': False, 'error': f'.env: {type(error).__name__}'})
        return 2
    if args.status:
        try:
            from repairbot import bot

            _print((status or bot.status)(settings), indent=2)
            return 0
        except Exception as error:
            log.exception('--status falló')
            _print({'ok': False, 'error': f'{type(error).__name__}: {error}'})
            return 2

    def hung(elapsed: float) -> None:
        message = (f'tick colgado: sin terminar después de {elapsed / 60:.0f} min; se corta '
                   'para que el próximo arranque normal')
        log.error(message)
        bootstrap_log(message, args.config)

    (arm or watchdog.arm)(watchdog.IDLE_LIMIT_S, hung)
    try:
        with keep_awake(awake):
            if tick is None:
                from repairbot import bot

                tick = bot.tick
            summary = tick(settings, dry_run=args.dry_run)
    except Exception as error:   # tick() never raises: this is a broken bot (import, lock file...)
        message = f'tick: {type(error).__name__}: {error}'
        log.exception('el tick falló')
        if not args.dry_run:
            message += f'; {healer(settings)}'
        bootstrap_log(message, args.config)
        _print({'ok': False, 'error': message})
        return 2
    finally:
        watchdog.disarm()   # the watch ends with the tick, never with whatever runs this process next
    log.info('tick: %s', json.dumps(summary, ensure_ascii=False, default=str))
    _print(summary)
    return 2 if summary.get('errors') else 0


if __name__ == '__main__':
    sys.exit(main())
