"""
Bootstrap the searches that need it now, without waiting for the crawl tick.

A search created or edited in the web gets its backfill (sección 5.7) on the
worker's next tick. This runs that step alone: every enabled profile never
bootstrapped, or edited since, is matched against the active listings of the
last 30 days. Handy while developing the web and used by its e2e tests.

Usage (from worker/):
    python -m tools.rematch
"""
from __future__ import annotations

import logging
import sys

import db
from aio import run
from pipeline import rematch


async def main() -> int:
    await db.open_pool()
    try:
        done = await rematch.run_pending()
    finally:
        await db.close_pool()
    print(f"{done} búsqueda(s) procesada(s)")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run(main()))
