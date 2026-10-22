"""Observability (sección 10, §46): collector_runs, pipeline_errors and source health."""
from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass
from datetime import datetime

from db.pool import connection


log = logging.getLogger("runs")

_MAX_ERROR = 4_000


def worker_id() -> str:
    """This process as "host:pid": who holds a crawl target's claim and ran a run."""
    return f"{socket.gethostname()}:{os.getpid()}"


def pid_alive(pid: int) -> bool:
    """Whether a process with this pid runs on this host. On Windows (the old
    PC worker) any other pid counts as gone: os.kill(pid, 0) sends Ctrl+C there."""
    if os.name == "nt":
        return pid == os.getpid()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def dead_workers(workers: list[str], host: str) -> list[str]:
    """The `workers` ("host:pid") of `host` whose process is gone."""
    dead = []
    for w in workers:
        h, _, pid = w.rpartition(":")
        if h == host and pid.isdigit() and not pid_alive(int(pid)):
            dead.append(w)
    return dead


async def start_run(source: str, target_id: int | None) -> int:
    async with connection() as cx:
        row = await (await cx.execute(
            "INSERT INTO collector_runs (source, target_id, worker) VALUES (%s, %s, %s) RETURNING id",
            (source, target_id, worker_id()))).fetchone()
    return row["id"]


@dataclass(frozen=True)
class SourceHealth:
    """A source's failure streak after a run (the admin alert reads it)."""
    source: str
    name: str
    failures: int               # consecutive failures after this run
    previous: int               # ... and before it
    last_ok_at: datetime | None
    error: str | None = None


async def finish_run(run_id: int, *, ok: bool, found: int | None = None, new: int | None = None,
                     updated: int | None = None, error: str | None = None) -> SourceHealth | None:
    """Close a run and keep the source's health counters in step. Returns the
    source's streak (None for an unknown run)."""
    async with connection() as cx:
        row = await (await cx.execute(
            "UPDATE collector_runs SET finished_at = now(), status = %s, found = %s, new = %s, "
            "  updated = %s, error = %s WHERE id = %s RETURNING source",
            ("ok" if ok else "failed", found, new, updated,
             error[:_MAX_ERROR] if error else None, run_id))).fetchone()
        if row is None:
            return None
        if ok:
            # `old` is the row as it was before this statement.
            src = await (await cx.execute(
                "UPDATE sources s SET last_ok_at = now(), consecutive_failures = 0 "
                "  FROM sources old WHERE s.id = %s AND old.id = s.id "
                "RETURNING s.name, 0 AS failures, old.consecutive_failures AS previous, s.last_ok_at",
                (row["source"],))).fetchone()
        else:
            src = await (await cx.execute(
                "UPDATE sources SET consecutive_failures = consecutive_failures + 1 WHERE id = %s "
                "RETURNING name, consecutive_failures AS failures, "
                "  consecutive_failures - 1 AS previous, last_ok_at",
                (row["source"],))).fetchone()
    if src is None:
        return None
    return SourceHealth(row["source"], src["name"], src["failures"], src["previous"], src["last_ok_at"],
                        None if ok else error)


async def fail_orphan_runs(started_before: datetime) -> int:
    """Close the runs a dead worker of this host left 'running' (it died or
    was restarted mid-run), and those from before runs had a worker. Another
    host's runs are its own. The source's failure streak is left alone.
    Returns how many."""
    host = socket.gethostname()
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT DISTINCT worker FROM collector_runs WHERE status = 'running' "
            "  AND split_part(worker, ':', 1) = %s", (host,))).fetchall()
        dead = dead_workers([r["worker"] for r in rows], host)
        cur = await cx.execute(
            "UPDATE collector_runs SET status = 'failed', finished_at = now(), "
            "  error = 'worker restarted mid-run' WHERE status = 'running' "
            "  AND (worker = ANY(%s) OR (worker IS NULL AND started_at < %s))",
            (dead, started_before))
        return cur.rowcount


async def bootstrapped_at(target_id: int) -> datetime | None:
    """When the target's first successful run ended: what it had found by
    then is history, not news (2.5). None until it has one."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT min(finished_at) AS at FROM collector_runs WHERE target_id = %s AND status = 'ok'",
            (target_id,))).fetchone()
    return row["at"] if row else None


async def recent_ok_found(target_id: int, *, exclude_run: int | None = None, n: int = 3) -> int | None:
    """The most one of the target's last `n` ok runs found, `exclude_run`
    left out (pipeline/news.py, the step). None without an ok run."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT max(found) AS found FROM (SELECT found FROM collector_runs "
            "  WHERE target_id = %s AND status = 'ok' AND id IS DISTINCT FROM %s::bigint "
            "  ORDER BY id DESC LIMIT %s) r",
            (target_id, exclude_run, n))).fetchone()
    return row["found"] if row else None


async def log_error(stage: str, ref: str | None, error: str) -> None:
    """Record a pipeline error. Never raises: observability must not break the pipeline."""
    try:
        async with connection() as cx:
            await cx.execute("INSERT INTO pipeline_errors (stage, ref, error) VALUES (%s, %s, %s)",
                             (stage, ref, error[:_MAX_ERROR]))
    except Exception:
        log.exception("could not record pipeline error stage=%s ref=%s", stage, ref)
