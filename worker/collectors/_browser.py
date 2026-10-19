"""Shared Playwright helpers — reuse a single browser instance across scrapers."""
from __future__ import annotations
import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright


USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
VIEWPORT = {"width": 1366, "height": 900}
_PLATFORM_TOKENS = {"linux": "X11; Linux x86_64", "win32": "Windows NT 10.0; Win64; x64",
                    "darwin": "Macintosh; Intel Mac OS X 10_15_7"}


def native_user_agent(version: str, platform: str = sys.platform) -> str:
    """What this Chromium sends when it runs visible on this OS: its real
    major version and platform, with no "HeadlessChrome". Facebook revoked
    sessions whose fixed Windows/Chrome 124 agent contradicted the Linux
    Chromium behind it (2026-10-17)."""
    major = version.split(".", 1)[0]
    token = next((t for key, t in _PLATFORM_TOKENS.items() if platform.startswith(key)), _PLATFORM_TOKENS["linux"])
    return (f"Mozilla/5.0 ({token}) AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{major}.0.0.0 Safari/537.36")

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
    native: bool = False,
) -> AsyncIterator[BrowserContext]:
    """Yield a fresh browser context. Closes context on exit; browser is reused.
    `native`: present the browser as itself (native_user_agent) instead of USER_AGENT."""
    b = await _ensure_browser()
    ctx = await b.new_context(
        storage_state=storage_state,
        locale=locale,
        user_agent=user_agent or (native_user_agent(b.version) if native else USER_AGENT),
        viewport=VIEWPORT,
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
