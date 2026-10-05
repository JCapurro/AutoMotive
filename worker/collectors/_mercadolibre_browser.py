"""Tecc's Mercado Libre transport: installed Chrome with a dedicated profile.

The profile carries live browser state across searches, detail reads and manual
verification. It is separate from both Tecc and the user's everyday Chrome.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import BrowserContext, Playwright, async_playwright

import config


# Crawl and enrichment run concurrently on the collectors loop. Chrome only
# permits one context/process to own a persistent profile at a time.
_lock = asyncio.Lock()
_pw: Playwright | None = None
_ctx: BrowserContext | None = None


async def _ensure_context() -> BrowserContext:
    global _pw, _ctx
    if _ctx is not None:
        return _ctx
    profile = Path(config.ML_BROWSER_PROFILE_DIR).resolve()
    profile.mkdir(parents=True, exist_ok=True)
    if _pw is None:
        _pw = await async_playwright().start()
    try:
        ctx = await _pw.chromium.launch_persistent_context(
            str(profile), channel="chrome", headless=False,
        )
    except BaseException:
        await _pw.stop()
        _pw = None
        raise
    _ctx = ctx

    def closed(*_args) -> None:
        global _ctx
        if _ctx is ctx:
            _ctx = None

    ctx.on("close", closed)
    return ctx


@asynccontextmanager
async def mercadolibre_context() -> AsyncIterator[BrowserContext]:
    """Serialize page operations on one Chrome context for the worker lifetime."""
    async with _lock:
        yield await _ensure_context()


async def shutdown() -> None:
    """Flush the profile and release Chrome when the worker or CLI exits."""
    global _pw, _ctx
    async with _lock:
        ctx, pw = _ctx, _pw
        _ctx = _pw = None
        try:
            if ctx is not None:
                await ctx.close()
        finally:
            if pw is not None:
                await pw.stop()
