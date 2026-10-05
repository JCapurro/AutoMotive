"""Tecc's Mercado Libre transport: installed Chrome with a dedicated profile.

The profile carries live browser state across searches, detail reads and manual
verification. It is separate from both Tecc and the user's everyday Chrome.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from playwright.async_api import BrowserContext, async_playwright

import config


# Crawl and enrichment run concurrently on the collectors loop. Chrome only
# permits one context/process to own a persistent profile at a time.
_lock = asyncio.Lock()


@asynccontextmanager
async def mercadolibre_context() -> AsyncIterator[BrowserContext]:
    async with _lock:
        profile = Path(config.ML_BROWSER_PROFILE_DIR).resolve()
        profile.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(
                str(profile), channel="chrome", headless=False,
            )
            try:
                yield ctx
            finally:
                # Closing flushes the live profile and releases Chrome's lock.
                await ctx.close()
