"""
Demanda insatisfecha by hand (/admin/demand, pipeline/unmet_demand.py).

    python -m tools.unmet_demand

Recomputes admin_unmet_demand and admin_unmet_demand_run now, whatever
app_config.unmet_demand.enabled and the hour say, and prints how many searches
it covered and how long it took. Run from worker/.
"""
from __future__ import annotations

import logging
import sys
import time

import db
from aio import run
from pipeline.unmet_demand import run_unmet_demand


async def main() -> int:
    await db.open_pool()
    try:
        t0 = time.monotonic()
        done = await run_unmet_demand(force=True)
        print(f"{done} búsquedas en {time.monotonic() - t0:.1f} s")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(run(main()))
