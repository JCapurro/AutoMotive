from __future__ import annotations

import asyncio
import os
import sys

# No test reads a real source's whole stock (pipeline/crawl.full_read): the
# ones that run real collectors' targets would hit Mercado Libre. Tests of it
# turn it on.
os.environ.setdefault("FULL_READ", "0")
# No pace (pipeline/pacing.py) unless a test sets one: lanes read their targets back to back.
os.environ.setdefault("SOURCE_RUNS_PER_HOUR", "")
os.environ.setdefault("SOURCE_QUIET_HOURS", "")

# psycopg's async mode needs a selector loop (Windows defaults to proactor).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
