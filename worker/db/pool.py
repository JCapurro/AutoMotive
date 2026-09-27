"""Async Postgres connection pool (psycopg 3), one per worker process.

The worker connects with a privileged role, so RLS does not apply to it.
Each `async with connection()` block is one transaction: it commits on exit
and rolls back if the block raises.

psycopg's async mode needs a selector event loop. On Windows that is not the
default, so the worker's entry points create one explicitly (see main.py).
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urlparse

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

import config


# Supabase's transaction pooler: connections are shared between clients, so
# server-side prepared statements can't be reused.
_TRANSACTION_POOLER_PORT = 6543

_pool: AsyncConnectionPool | None = None


def connection_kwargs(url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"row_factory": dict_row}
    if urlparse(url).port == _TRANSACTION_POOLER_PORT:
        kwargs["prepare_threshold"] = None
    return kwargs


async def open_pool(url: str | None = None, *, min_size: int = 1,
                    max_size: int | None = None) -> AsyncConnectionPool:
    """Open the process-wide pool (idempotent)."""
    global _pool
    if _pool is not None:
        return _pool
    url = url or config.DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL no está seteado en .env")
    pool = AsyncConnectionPool(
        url,
        min_size=min_size,
        max_size=max_size or config.DB_POOL_MAX_SIZE,
        kwargs=connection_kwargs(url),
        open=False,
        name="automotive",
    )
    await pool.open(wait=True, timeout=30)
    _pool = pool
    return pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def connection() -> AsyncIterator[AsyncConnection]:
    if _pool is None:
        raise RuntimeError("DB pool is not open; call db.open_pool() first")
    async with _pool.connection() as cx:
        yield cx
