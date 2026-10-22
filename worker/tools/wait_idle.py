"""Wait until no target of these sources is being crawled, before restarting
the worker (docs/COLLECTOR_REPAIR.md, «Desplegar main a mano»). A restart
kills the scan in progress and throws away what it read: a Facebook scan
reads up to RECENT_FB_MAX_DATE_FETCHES item pages, 30 s apart.

Read-only: it looks at the claims (crawl_targets.claimed_until, targets.claim_next).

Usage (from worker/, with the .env's DATABASE_URL):
    python -m tools.wait_idle facebook mercadolibre --max-wait 1200 --poll 5

Exit code 0 once none of their targets is claimed, 2 when --max-wait runs
out first, 1 when the database can't be read.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from typing import Any, Awaitable, Callable, Iterable

from aio import run

HELD_SQL = ("SELECT source, id, claimed_until FROM crawl_targets "
            "WHERE source = ANY(%s) AND claimed_until > now() ORDER BY source, id")


async def held_claims(cx, sources: Iterable[str]) -> list[dict[str, Any]]:
    """The live claims on those sources' targets: what a restart would cut.
    The connection must be in autocommit, or now() stays at the first poll."""
    return await (await cx.execute(HELD_SQL, (sorted(set(sources)),))).fetchall()


async def wait_idle(held: Callable[[], Awaitable[list[dict[str, Any]]]], *, max_wait: float, poll: float,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                    say: Callable[[str], Any] = print) -> bool:
    """Poll `held` until it is empty (True) or `max_wait` seconds go by (False)."""
    deadline = clock() + max_wait
    last = None
    while rows := await held():
        now = {(r["source"], r["id"]) for r in rows}
        if now != last:
            say("esperando: " + ", ".join(f"{r['source']} target {r['id']} (hasta {r['claimed_until']:%H:%M:%S})"
                                          for r in rows))
            last = now
        if clock() >= deadline:
            say(f"siguen ocupados después de {max_wait:g} s")
            return False
        await sleep(poll)
    return True


async def _main(args: argparse.Namespace, connect=None) -> int:
    import config
    from db.pool import connection_kwargs

    if connect is None:
        if not config.DATABASE_URL:
            print("falta DATABASE_URL en el .env", file=sys.stderr)
            return 1
        from psycopg import AsyncConnection

        def connect():
            return AsyncConnection.connect(config.DATABASE_URL, connect_timeout=30, autocommit=True,
                                           **connection_kwargs(config.DATABASE_URL))
    try:
        async with await connect() as cx:
            free = await wait_idle(lambda: held_claims(cx, args.sources), max_wait=args.max_wait, poll=args.poll)
    except Exception as error:
        print(f"no se pudo leer crawl_targets: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0 if free else 2


def main(argv: list[str] | None = None, *, connect=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="+", help="fuentes, p. ej. facebook mercadolibre")
    parser.add_argument("--max-wait", type=float, default=1200, help="segundos como máximo (1200)")
    parser.add_argument("--poll", type=float, default=5, help="segundos entre lecturas (5)")
    return run(_main(parser.parse_args(argv), connect))


if __name__ == "__main__":
    sys.exit(main())
