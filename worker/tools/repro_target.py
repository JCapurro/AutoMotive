"""Reproduce one collector search without ingesting it.

    python -m tools.repro_target <source> [--target-id N] [--no-db] [--json] [--limit-sample 5] [k=v ...]

Nothing is written: no collector_runs row, no listings, no geocode_cache. The
database is only read (two SELECTs) and only with --target-id, to build the
filters the scheduler would use; the pool is closed before the collector runs.
k=v pairs are the collector's filters (tools.scraper_cli); with --target-id
they override the target's. --timeout S (default 270, 0 = none) cancels a
search that hangs, so the browsers are always closed.

Exit codes: 0 ok, 2 incomplete scan, 3 blocked (login/captcha/session),
4 network / HTTP 5xx / timeout, 1 anything else (usage errors included).
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import redirect_stdout
import re
import socket
import sys
import time
import traceback
from typing import Any

import httpx
from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout

from aio import run
from collectors import REGISTRY, CollectorBlocked
from collectors._browser import shutdown as browser_shutdown
from collectors._loop import run_collector
from collectors._recency import SOURCES as RECENT_SOURCES
import db
from db.repos import targets as targets_repo
from pipeline.crawl import scraper_filters
from tools.collector_repairs import json_text, safe_text
from tools.scraper_cli import _parse_kv

OK, ERROR, INCOMPLETE, BLOCKED, NETWORK = 0, 1, 2, 3, 4
# Below the callers' own limits (Claude's default Bash timeout, the VPS probe),
# so a hung search still ends here, with its browsers closed.
DEFAULT_TIMEOUT_S = 270

TARGET_SQL = ('SELECT id, source, make, model, query, first_run_done, last_run_at '
              'FROM crawl_targets WHERE id = %s')
_HTTP_5XX = re.compile(r'\bHTTP 5\d\d\b')


class ReproTimeout(TimeoutError):
    """The search outlived --timeout; says nothing about the site."""


async def target_filters(source: str, target_id: int) -> dict[str, Any]:
    """The filters pipeline.crawl.run_target would hand the collector for this target."""
    try:
        await db.open_pool(max_size=1)
        async with db.connection() as cx:
            await cx.execute('SET TRANSACTION READ ONLY')
            target = await (await cx.execute(TARGET_SQL, (target_id,))).fetchone()
        if target is None:
            raise ValueError(f'no existe el target {target_id}')
        if target['source'] != source:
            raise ValueError(f"el target {target_id} es de {target['source']}, no de {source}")
        filters = scraper_filters(target)
        if source in RECENT_SOURCES:
            filters['known_publication_dates'] = await targets_repo.publication_dates(target)
        return filters
    finally:
        await db.close_pool()


def _network(error: BaseException) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    if isinstance(error, (httpx.TransportError, TimeoutError, ConnectionError, socket.gaierror,
                          PlaywrightTimeout)):
        return True
    if isinstance(error, PlaywrightError) and 'net::ERR_' in str(error):
        return True
    return bool(_HTTP_5XX.search(str(error)))   # collectors raise RuntimeError('<source>: HTTP 503')


def exit_code(error: BaseException) -> int:
    """Blocked wins over network; an explicit cause (raise ... from) counts like the error."""
    seen: set[int] = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if isinstance(error, CollectorBlocked):
            return BLOCKED
        if _network(error):
            return NETWORK
        error = error.__cause__
    return ERROR


async def _search(source: str, filters: dict[str, Any], timeout: float):
    try:
        async with asyncio.timeout(timeout or None) as deadline:
            return await run_collector(REGISTRY[source]().search(filters))
    except TimeoutError:
        if deadline.expired():
            raise ReproTimeout(f'la búsqueda superó {timeout:g} s (--timeout); no prueba que el sitio '
                               'esté caído: acotá los filtros o subí --timeout') from None
        raise


async def _close_browsers() -> None:
    try:
        await run_collector(browser_shutdown())
    except Exception as error:
        print(f'repro_target: no se pudieron cerrar los navegadores: {type(error).__name__}', file=sys.stderr)


async def reproduce(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {
        'source': args.source, 'target_id': args.target_id, 'found': None, 'complete': False,
        'reason': None, 'unknown_dates': 0, 'seconds': 0.0, 'error_type': None, 'error': None, 'sample': []}
    started = time.monotonic()
    try:
        filters = await target_filters(args.source, args.target_id) if args.target_id is not None else {}
        filters.update(_parse_kv(args.filters))
        items = await _search(args.source, filters, args.timeout)
        complete = bool(getattr(items, 'complete', True))
        result.update(
            found=len(items), complete=complete,
            reason=None if complete else safe_text(getattr(items, 'reason', None)) or None,
            unknown_dates=getattr(items, 'unknown_dates', 0),
            sample=[{'id': item.listing_id, 'title': (item.titulo or '')[:120], 'price': item.precio,
                     'url': (item.url or '')[:300]} for item in list(items)[:args.limit_sample]])
        code = OK if complete else INCOMPLETE
    except Exception as error:
        code = exit_code(error)
        # Without the ^^^^ markers: they would eat the frames out of safe_text's budget.
        trace = '\n'.join(line for line in traceback.format_exc().splitlines() if line.strip(' ~^'))
        result.update(error_type=type(error).__name__, error=safe_text(trace))
    finally:
        result['seconds'] = round(time.monotonic() - started, 1)
        await _close_browsers()
    return result, code


def render(result: dict[str, Any]) -> str:
    head = result['source'] + (f" · target {result['target_id']}" if result['target_id'] is not None else '')
    if result['error_type']:
        return f"{head}: falló con {result['error_type']} a los {result['seconds']} s\n{result['error']}"
    state = 'recorrido completo' if result['complete'] else f"recorrido incompleto: {result['reason']}"
    lines = [f"{head}: {result['found']} avisos, {state} ({result['seconds']} s)"]
    if result['unknown_dates']:
        lines.append(f"{result['unknown_dates']} avisos excluidos por fecha de publicación desconocida")
    lines += [f"  {row['id']}  {'-' if row['price'] is None else row['price']}  {row['title']}  {row['url']}"
              for row in result['sample']]
    return '\n'.join(lines)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):   # argparse would exit 2, which here means "incomplete"
        self.print_usage(sys.stderr)
        self.exit(ERROR, f'{self.prog}: {message}\n')


def _pair(value: str) -> str:
    if not value.partition('=')[0].strip() or '=' not in value:
        raise argparse.ArgumentTypeError(f'se esperaba clave=valor, no {value!r}')
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog='python -m tools.repro_target', description=__doc__,
                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('source', choices=sorted(REGISTRY), metavar='source', help=', '.join(sorted(REGISTRY)))
    parser.add_argument('filters', nargs='*', type=_pair, metavar='k=v', help='filtros del collector')
    parser.add_argument('--target-id', type=int, help='armar los filtros de este crawl_target (solo lectura)')
    parser.add_argument('--no-db', action='store_true', help='no abrir la base (incompatible con --target-id)')
    parser.add_argument('--json', action='store_true', help='imprimir el resultado como JSON')
    parser.add_argument('--limit-sample', type=int, default=5, help='avisos de muestra (por defecto 5)')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT_S,
                        help=f'segundos máximos de búsqueda (por defecto {DEFAULT_TIMEOUT_S}; 0 = sin tope)')
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = build_parser()
    args = parser.parse_intermixed_args(argv)
    if args.no_db and args.target_id is not None:
        parser.error('--no-db es incompatible con --target-id')
    if args.limit_sample < 0 or args.timeout < 0:
        parser.error('--limit-sample y --timeout no pueden ser negativos')
    with redirect_stdout(sys.stderr):   # whatever a collector prints stays out of the result
        result, code = run(reproduce(args))
    print(json_text(result) if args.json else render(result))
    return code


if __name__ == '__main__':
    sys.exit(main())
