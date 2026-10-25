from __future__ import annotations

import asyncio
import os
import sys

# No test reads a real source's whole stock (pipeline/crawl.full_read): the
# ones that run real collectors' targets would hit Mercado Libre. Tests of it
# turn it on.
os.environ.setdefault("FULL_READ", "0")

# psycopg's async mode needs a selector loop (Windows defaults to proactor).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
