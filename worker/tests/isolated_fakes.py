"""Collectors for test_crawl_lanes' child-process tests (collectors/_isolated.py
imports them by name in the child)."""
from __future__ import annotations

import asyncio
import os

from collectors.base import BaseScraper, CollectorBlocked, Listing, SearchResults


class Echo(BaseScraper):
    ISOLATED = True

    async def search(self, filters: dict):
        return SearchResults([Listing(source="facebook", listing_id="1", titulo=filters["q"], url="https://x/1")],
                             complete=False, reason="scroll cap", date_skips=filters.get("date_skips"),
                             probe={"cards": 1})


class Blocked(BaseScraper):
    ISOLATED = True

    async def search(self, filters: dict):
        raise CollectorBlocked("facebook: session expired")


class Hang(BaseScraper):
    ISOLATED = True

    async def search(self, filters: dict):
        with open(filters["pidfile"], "w") as f:
            f.write(str(os.getpid()))
        await asyncio.Event().wait()


class Crash(BaseScraper):
    ISOLATED = True

    async def search(self, filters: dict):
        os._exit(3)
