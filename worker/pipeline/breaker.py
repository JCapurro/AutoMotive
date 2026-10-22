"""A source that blocks us is paused, not hammered (incident 2026-10-21).

When a collector raises CollectorBlocked (an expired Facebook session, a
login wall, a challenge), every other request to that source fails the same
way until a person fixes it, and each one adds a failed run or a
pipeline_errors row. The source is paused for SOURCE_BLOCKED_PAUSE_SECONDS:
its crawl lane stops and doesn't start again, and enrichment and the
watchlist skip its pages, until the pause ends; then one request tries it
again and pauses it once more if it is still blocked.

The pause lives in this process (a restart tries again at once).
"""
from __future__ import annotations

import logging
import time

from config import SOURCE_BLOCKED_PAUSE_SECONDS

log = logging.getLogger("breaker")

_paused: dict[str, float] = {}


def pause(source: str, reason: str, *, seconds: float = SOURCE_BLOCKED_PAUSE_SECONDS) -> None:
    if not paused(source):
        log.warning("source %s paused for %d min: %s", source, seconds // 60, reason)
    _paused[source] = time.monotonic() + seconds


def paused(source: str) -> bool:
    until = _paused.get(source)
    if until is None:
        return False
    if time.monotonic() >= until:
        del _paused[source]
        log.info("source %s pause over, trying it again", source)
        return False
    return True


def clear() -> None:
    """Tests."""
    _paused.clear()
