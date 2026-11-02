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
block. The source is paused after SOURCE_SUSPECT_STREAK targets in a row
give one, within SUSPECT_WINDOW_SECONDS; a good run in between clears the
streak (suspect, vouch). A target whose last run was already one is chronic
(really empty, most likely): it doesn't add to the streak again until a
good run, so three empty rare models coming due together don't pause the
source each time.

The pause lives in this process (a restart tries again at once).
"""
from __future__ import annotations

import logging
import time

from config import SOURCE_BLOCKED_PAUSE_SECONDS, SOURCE_SUSPECT_STREAK

log = logging.getLogger("breaker")

# Suspicions older than this don't count toward the streak.
SUSPECT_WINDOW_SECONDS = 3600

_paused: dict[str, float] = {}
_suspicions: dict[str, list[float]] = {}           # when each one of the streak came
_chronic: dict[str, set] = {}                      # targets whose last run was a suspicion


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


def chronic(source: str, target: object) -> bool:
    """Whether the target's last run was already a suspicion."""
    return target in _chronic.get(source, ())


def suspect(source: str, target: object, reason: str, *, streak: int = SOURCE_SUSPECT_STREAK) -> bool:
    """One more unconfirmed empty answer, from `target`; pauses the source at
    `streak` of them in a row, unless the target is chronic. Whether it is
    paused now."""
    if chronic(source, target):
        log.info("source %s: target %s empty again, not counted: %s", source, target, reason)
        return False
    _chronic.setdefault(source, set()).add(target)
    now = time.monotonic()
    times = [t for t in _suspicions.get(source, ()) if now - t < SUSPECT_WINDOW_SECONDS] + [now]
    if len(times) < streak:
        _suspicions[source] = times
        log.info("source %s suspect %d/%d: %s", source, len(times), streak, reason)
        return False
    _suspicions.pop(source, None)
    pause(source, f"{reason} ({len(times)} targets in a row)")
    return True


def vouch(source: str, target: object = None) -> None:
    """A good run of the source (of `target`): its suspicions start over."""
    _suspicions.pop(source, None)
    _chronic.get(source, set()).discard(target)


def clear() -> None:
    """Tests."""
    _paused.clear()
    _suspicions.clear()
    _chronic.clear()
