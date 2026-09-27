from __future__ import annotations

import asyncio
import sys

# psycopg's async mode needs a selector loop (Windows defaults to proactor).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
