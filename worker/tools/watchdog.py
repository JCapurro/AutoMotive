"""
Watchdog (F7, punto 8): is the pilot up? Runs outside the worker, every few
minutes, as a Windows scheduled task (ops/install-tasks.ps1).

Checks:
  * worker — its heartbeat (worker_heartbeat) is newer than WATCHDOG_STALE_MINUTES;
  * base   — Postgres answers;
  * web    — WEB_BASE_URL answers (through the tunnel, when it is public).

Includes collector failures, stalled/overdue/empty runs and sends email to
PLATFORM_HEALTH_EMAIL on failure/recovery. State: logs/platform_health_state.json.

Usage (from worker/):
    python -m tools.watchdog          # check and alert
    python -m tools.watchdog --dry    # check and print, no email, no state
"""
from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Callable

import httpx

import db
from aio import run
from config import ROOT
from pipeline.heartbeat import last_beat

STATE_FILE = ROOT / "logs" / "watchdog_state.json"


def worker_problem(beat: dict | None, stale: timedelta) -> str | None:
    if beat is None:
        return "el worker nunca latió (¿no arrancó?)"
    if beat["age"] > stale:
        return f"el worker no late hace {int(beat['age'].total_seconds() // 60)} min (host {beat['host']})"
    return None


async def check_db_and_worker(stale: timedelta) -> dict[str, str | None]:
    try:
        await db.open_pool(max_size=1)
    except Exception as e:  # noqa: BLE001 - any failure means "down"
        return {"base": f"no conecta: {type(e).__name__}", "worker": None}
    try:
        return {"base": None, "worker": worker_problem(await last_beat(), stale)}
    finally:
        await db.close_pool()


def check_web(base_url: str, get: Callable[[str], httpx.Response] | None = None) -> str | None:
    if not base_url:
        return None
    get = get or (lambda url: httpx.get(url, timeout=15, follow_redirects=False))
    try:
        r = get(f"{base_url}/robots.txt")
    except httpx.HTTPError as e:
        return f"{base_url} no responde: {type(e).__name__}"
    return None if r.status_code < 500 else f"{base_url} responde {r.status_code}"


def transitions(previous: dict[str, str | None], current: dict[str, str | None]) -> list[str]:
    """The messages to send: what started failing and what recovered."""
    out = []
    for name, problem in current.items():
        before = previous.get(name)
        if problem and not before:
            out.append(f"🔴 AutoMotive · {name}: {problem}")
        elif not problem and before:
            out.append(f"🟢 AutoMotive · {name}: volvió a funcionar")
    return out


def load_state(path: Path) -> dict[str, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    # Keep the registered Windows task compatible with the platform health CLI.
    from tools.platform_health import main as health_main
    return health_main()


if __name__ == "__main__":
    sys.exit(main())
