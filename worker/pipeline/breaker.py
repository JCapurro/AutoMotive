"""A source that blocks us is paused, not hammered (incident 2026-10-21).

When a collector raises CollectorBlocked (an expired Facebook session, a
login wall, a challenge), every other request to that source fails the same
way until a person fixes it, and each one adds a failed run or a
pipeline_errors row. The source is paused for SOURCE_BLOCKED_PAUSE_SECONDS:
its crawl lane stops and doesn't start again, and enrichment and the
watchlist skip its pages, until the pause ends; then one request tries it
again and pauses it once more if it is still blocked.

An empty answer the source doesn't confirm (FeedUnconfirmed) is only a
suspicion: a rare model or a page that didn't render looks the same as a
block. The source is paused after SOURCE_SUSPECT_STREAK of them in a row; a
good run in between clears the streak (suspect, vouch).

The pause lives in this process (a restart tries again at once).
"""
from __future__ import annotations

import logging
import time

from config import SOURCE_BLOCKED_PAUSE_SECONDS, SOURCE_SUSPECT_STREAK

log = logging.getLogger("breaker")

_paused: dict[str, float] = {}
_suspicions: dict[str, int] = {}


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


def suspect(source: str, reason: str, *, streak: int = SOURCE_SUSPECT_STREAK) -> bool:
    """One more unconfirmed empty answer in a row; pauses the source at
    `streak` of them. Whether it is paused now."""
    count = _suspicions[source] = _suspicions.get(source, 0) + 1
    if count < streak:
        log.info("source %s suspect %d/%d: %s", source, count, streak, reason)
        return False
    _suspicions.pop(source, None)
    pause(source, f"{reason} ({count} in a row)")
    return True


def vouch(source: str) -> None:
    """A good run of the source: its suspicions start over."""
    _suspicions.pop(source, None)


def clear() -> None:
    """Tests."""
    _paused.clear()
    _suspicions.clear()
