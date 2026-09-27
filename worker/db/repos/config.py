"""Business rules from the app_config table (Apéndice A), cached briefly so
edits apply without a deploy but the scheduler doesn't query on every use."""
from __future__ import annotations

import time
from typing import Any

from db.pool import connection


_TTL_SECONDS = 60.0
_cache: dict[str, Any] = {}
_fetched_at = 0.0


async def get_config(key: str, default: Any = None) -> Any:
    global _cache, _fetched_at
    if time.monotonic() - _fetched_at > _TTL_SECONDS:
        async with connection() as cx:
            rows = await (await cx.execute("SELECT key, value FROM app_config")).fetchall()
        _cache = {r["key"]: r["value"] for r in rows}
        _fetched_at = time.monotonic()
    return _cache.get(key, default)


def clear_config_cache() -> None:
    global _fetched_at
    _fetched_at = 0.0
