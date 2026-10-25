"""Run collector coroutines on an event loop that can start subprocesses.

Playwright launches its driver as a subprocess, which on Windows needs the
ProactorEventLoop, while psycopg's async mode needs a SelectorEventLoop. On
Windows the worker runs on a selector loop and hands collector work to a
proactor loop in a dedicated thread; everywhere else collectors run inline.

Everything a collector touches (the shared browser in _browser.py) stays on
that one loop, so always go through `run_collector`.
"""
from __future__ import annotations

import asyncio
import sys
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _collector_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None:
            loop = asyncio.ProactorEventLoop()
            threading.Thread(target=loop.run_forever, name="collectors", daemon=True).start()
            _loop = loop
    return _loop


class CollectorTimeout(TimeoutError):
    """A collector call ran past its `timeout` and was cancelled."""


async def run_collector(coro: Coroutine[Any, Any, T], *, timeout: float | None = None) -> T:
    """Await `coro` on the collectors' loop. With `timeout`, cancel it after
    that many seconds and raise CollectorTimeout: a hung page must fail its
    own run, never stall the loop that awaits it."""
    if sys.platform != "win32" or isinstance(asyncio.get_running_loop(), asyncio.ProactorEventLoop):
        work = coro
    else:
        work = asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro, _collector_loop()))
    if timeout is None:
        return await work
    try:
        return await asyncio.wait_for(work, timeout)
    except TimeoutError as exc:
        raise CollectorTimeout(f"collector timed out after {timeout:g}s") from exc
