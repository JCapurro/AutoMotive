"""Entry-point helper: run the worker's coroutines on a loop psycopg supports.

psycopg's async mode needs a selector event loop and Windows defaults to the
proactor one. Collectors, which need proactor on Windows, get their own loop
(collectors/_loop.py).
"""
from __future__ import annotations

import asyncio
import selectors
import sys
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def selector_loop() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop(selectors.SelectSelector())


def run(coro: Coroutine[Any, Any, T]) -> T:
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=selector_loop)
    return asyncio.run(coro)
