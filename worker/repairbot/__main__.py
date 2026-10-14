"""python -m repairbot [--dry-run] [--status] [--config PATH]

One tick of the repair bot, run every 5 minutes by the \\AutoMotive\\RepairBot task with cwd
<home>/repo/worker. Prints a one-line JSON summary; exit 0, or 2 on an internal error.
The log rotates in <home>/state/bot.log.
"""
from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys

from repairbot.settings import load, load_env

LOG_BYTES = 2_000_000
LOG_BACKUPS = 5


def _print(value: dict, indent: int | None = None) -> None:
    if sys.stdout is None:   # pythonw (the scheduled task): no console
        return
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print(json.dumps(value, ensure_ascii=False, default=str, indent=indent))


def setup_logging(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    path = os.path.abspath(state_dir / 'bot.log')
    root = logging.getLogger()
    if any(getattr(handler, 'baseFilename', None) == path for handler in root.handlers):
        return
    handler = RotatingFileHandler(path, maxBytes=LOG_BYTES, backupCount=LOG_BACKUPS, encoding='utf-8', delay=True)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for noisy in ('httpx', 'httpcore', 'psycopg', 'psycopg.pool'):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: list[str] | None = None, *, tick=None, status=None) -> int:
    parser = argparse.ArgumentParser(prog='python -m repairbot', description='Bot de reparación de collectors.')
    parser.add_argument('--dry-run', action='store_true', help='informa qué haría, sin reclamar, escribir ni correr nada')
    parser.add_argument('--status', action='store_true', help='incidentes activos y estado local del bot')
    parser.add_argument('--once', action='store_true', help=argparse.SUPPRESS)   # every run is one tick
    parser.add_argument('--config', type=Path, help='config.json (por defecto REPAIRBOT_CONFIG o C:/automotive-bot/config.json)')
    args = parser.parse_args(argv)
    if args.config:
        # The Claude child and the CLIs it runs (repairbot.vps) find the same file through the environment.
        os.environ['REPAIRBOT_CONFIG'] = str(args.config.resolve())
    try:
        settings = load(args.config)
    except Exception as error:
        _print({'ok': False, 'error': f'config: {type(error).__name__}: {error}'})
        return 2
    setup_logging(settings.state_dir)
    log = logging.getLogger('repairbot')
    try:
        load_env(settings)   # before anything imports config, db or tools
    except Exception as error:
        log.exception('no se pudo leer %s', settings.env_file)
        _print({'ok': False, 'error': f'.env: {type(error).__name__}'})
        return 2
    from repairbot import bot

    if args.status:
        try:
            _print((status or bot.status)(settings), indent=2)
            return 0
        except Exception as error:
            log.exception('--status falló')
            _print({'ok': False, 'error': f'{type(error).__name__}: {error}'})
            return 2
    summary = (tick or bot.tick)(settings, dry_run=args.dry_run)
    log.info('tick: %s', json.dumps(summary, ensure_ascii=False, default=str))
    _print(summary)
    return 2 if summary.get('errors') else 0


if __name__ == '__main__':
    sys.exit(main())
