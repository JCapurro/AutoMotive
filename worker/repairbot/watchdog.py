"""Hard stop for a tick that hangs.

A tick that only does bookkeeping (list the queue, claim, update the launcher) takes seconds;
a hung one (a DNS lookup or a socket with no timeout on a saturated PC) used to hold the
scheduled task until its 90-minute limit, and every tick in between was refused. __main__ arms
the watchdog with IDLE_LIMIT_S; bot.py extends it to LONG_LIMIT_S when real work starts (a
Claude session, verifying, finishing or undoing a deploy). Without arm() every call is a no-op,
so tests and the CLIs are unaffected.

Ending the process is safe: state files are written atomically and the OS releases bot.lock.
"""
from __future__ import annotations

import os
import threading
import time

IDLE_LIMIT_S = 10 * 60
LONG_LIMIT_S = 85 * 60   # bot.TICK_BUDGET_S plus margin; the task itself stops at 90
_POLL_S = 5.0

_guard = threading.Lock()
_deadline: float | None = None


def arm(seconds: float, on_expire, *, clock=time.monotonic, poll: float = _POLL_S, exit=os._exit) -> threading.Thread:
    """Start the watch: past the deadline, on_expire(elapsed) runs and the process exits with 3."""
    global _deadline
    started = clock()
    with _guard:
        _deadline = started + seconds

    def watch():
        while True:
            time.sleep(poll)
            with _guard:
                deadline = _deadline
            if deadline is None:
                return
            if clock() >= deadline:
                try:
                    on_expire(clock() - started)
                except Exception:   # a broken log must not keep a hung tick alive
                    pass
                exit(3)
                return

    thread = threading.Thread(target=watch, name='repairbot-watchdog', daemon=True)
    thread.start()
    return thread


def extend(seconds: float, *, clock=time.monotonic) -> None:
    """Allow at least `seconds` more from now. No-op when the watchdog is not armed."""
    global _deadline
    with _guard:
        if _deadline is not None:
            _deadline = max(_deadline, clock() + seconds)


def disarm() -> None:
    global _deadline
    with _guard:
        _deadline = None
