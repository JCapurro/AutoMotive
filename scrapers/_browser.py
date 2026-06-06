"""Shared Playwright helpers — reuse a single browser instance across scrapers."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright


_pw: Playwright | None = None
_browser: Browser | None = None
_lock = asyncio.Lock()


async def _ensure_browser() -> Browser:
    global _pw, _browser
    if _browser and _browser.is_connected():
        return _browser
    async with _lock:
        if _browser and _browser.is_connected():
            return _browser
        _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(headless=True)
        return _browser


@asynccontextmanager
async def browser_context(
    *,
    storage_state: str | None = None,
    locale: str = "es-AR",
    user_agent: str | None = None,
) -> AsyncIterator[BrowserContext]:
    """Yield a fresh browser context. Closes context on exit; browser is reused."""
    b = await _ensure_browser()
    ctx = await b.new_context(
        storage_state=storage_state,
        locale=locale,
        user_agent=user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        viewport={"width": 1366, "height": 900},
    )
    try:
        yield ctx
    finally:
        try:
            await ctx.close()
        except Exception:
            pass


async def shutdown() -> None:
    global _pw, _browser
    if _browser:
        try:
            await _browser.close()
        except Exception:
            pass
    if _pw:
        try:
            await _pw.stop()
        except Exception:
            pass
    _pw = _browser = None
