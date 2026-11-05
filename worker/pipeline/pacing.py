"""How fast a source may be read (Facebook, 2026-11-05).

Facebook's session died sooner the harder it was read: 5 searches an hour
lasted 48 h, ~100 an hour lasted 2 h (docs/FACEBOOK_RITMO.md). Two brakes, per
source, from the .env:

- SOURCE_RUNS_PER_HOUR («facebook=25»): at most that many targets an hour,
  spread evenly (one every 3600/n seconds), so a backlog after a renewal or a
  night drains slowly instead of all at once.
- SOURCE_QUIET_HOURS («facebook=1-7»): no reads from 1:00 to 6:59, Argentina
  time, when almost nothing new is listed.

A lane asks `ready` before claiming its next target and `mark`s each claim. The
spacing lives in memory: after a restart the first read goes at once.
"""
from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from config import PACING_TZ, SOURCE_QUIET_HOURS, SOURCE_RUNS_PER_HOUR

_last: dict[str, float] = {}


def _hour(now: float) -> int:
    return datetime.fromtimestamp(now, ZoneInfo(PACING_TZ)).hour


def quiet(source: str, now: float | None = None) -> bool:
    """Inside the source's quiet hours ([start, end), local time; may wrap midnight)."""
    window = SOURCE_QUIET_HOURS.get(source)
    if window is None:
        return False
    start, end = window
    hour = _hour(time.time() if now is None else now)
    return start <= hour < end if start <= end else hour >= start or hour < end


def wait_seconds(source: str, now: float | None = None) -> float:
    """Seconds until the source may claim another target (0 = now)."""
    per_hour = SOURCE_RUNS_PER_HOUR.get(source)
    last = _last.get(source)
    if not per_hour or last is None:
        return 0.0
    now = time.time() if now is None else now
    return max(0.0, last + 3600 / per_hour - now)


def ready(source: str, now: float | None = None) -> bool:
    return not quiet(source, now) and wait_seconds(source, now) == 0


def mark(source: str, now: float | None = None) -> None:
    """A target of `source` was just claimed."""
    if source in SOURCE_RUNS_PER_HOUR:
        _last[source] = time.time() if now is None else now


def clear() -> None:
    _last.clear()
