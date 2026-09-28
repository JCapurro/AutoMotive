"""
Watchdog (F7, punto 8): is the pilot up? Runs outside the worker, every few
minutes, as a Windows scheduled task (ops/install-tasks.ps1).

Checks:
  * worker — its heartbeat (worker_heartbeat) is newer than WATCHDOG_STALE_MINUTES;
  * base   — Postgres answers;
  * web    — WEB_BASE_URL answers (through the tunnel, when it is public).

Sends a Telegram to TELEGRAM_ADMIN_CHAT_ID when a check starts failing and
when it recovers — not on every run: the last state lives in
logs/watchdog_state.json.

Usage (from worker/):
    python -m tools.watchdog          # check and alert
    python -m tools.watchdog --dry    # check and print, no Telegram, no state
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Callable

import httpx

import db
from aio import run
from config import ROOT, TELEGRAM_ADMIN_CHAT_ID, TELEGRAM_TOKEN, WATCHDOG_STALE_MINUTES, WEB_BASE_URL
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


def send_telegram(text: str) -> None:
    # The URL carries the bot token: never log it.
    httpx.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
               json={"chat_id": TELEGRAM_ADMIN_CHAT_ID, "text": text}, timeout=15).raise_for_status()


def load_state(path: Path) -> dict[str, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dry", action="store_true", help="solo mostrar, sin Telegram ni estado")
    args = parser.parse_args()

    current = run(check_db_and_worker(timedelta(minutes=WATCHDOG_STALE_MINUTES)))
    current["web"] = check_web(WEB_BASE_URL)
    for name, problem in current.items():
        print(f"{name:7} {'OK' if not problem else problem}")
    if args.dry:
        return 0 if not any(current.values()) else 1

    messages = transitions(load_state(STATE_FILE), current)
    if messages and TELEGRAM_TOKEN and TELEGRAM_ADMIN_CHAT_ID:
        try:
            send_telegram("\n".join(messages))
        except httpx.HTTPError as e:
            print(f"no pude avisar por Telegram: {type(e).__name__}", file=sys.stderr)
            return 2  # keep the old state: try again next run
    elif messages:
        print("hay cambios pero falta TELEGRAM_ADMIN_CHAT_ID: no aviso", file=sys.stderr)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(current, ensure_ascii=False), encoding="utf-8")
    return 0 if not any(current.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
