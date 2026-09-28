"""The worker's heartbeat (F7, punto 8): one row in worker_heartbeat, updated
every HEARTBEAT_SECONDS. /admin/sources shows it and tools/watchdog.py, which
runs outside the worker, alerts when it goes stale."""
from __future__ import annotations

import os
import socket
from datetime import datetime, timezone

import db


async def beat(started_at: datetime) -> None:
    async with db.connection() as cx:
        await cx.execute(
            "INSERT INTO worker_heartbeat (id, started_at, beat_at, host, pid) VALUES (1, %s, now(), %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET started_at = excluded.started_at, beat_at = now(), "
            "  host = excluded.host, pid = excluded.pid",
            (started_at, socket.gethostname(), os.getpid()))


async def last_beat() -> dict | None:
    async with db.connection() as cx:
        return await (await cx.execute(
            "SELECT started_at, beat_at, host, pid, now() - beat_at AS age FROM worker_heartbeat WHERE id = 1"
        )).fetchone()


def started_now() -> datetime:
    return datetime.now(timezone.utc)
