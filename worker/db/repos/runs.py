"""Observability (sección 10, §46): collector_runs, pipeline_errors and source health."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from db.pool import connection


log = logging.getLogger("runs")

_MAX_ERROR = 4_000


async def start_run(source: str, target_id: int | None) -> int:
    async with connection() as cx:
        row = await (await cx.execute(
            "INSERT INTO collector_runs (source, target_id) VALUES (%s, %s) RETURNING id",
            (source, target_id))).fetchone()
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


async def log_error(stage: str, ref: str | None, error: str) -> None:
    """Record a pipeline error. Never raises: observability must not break the pipeline."""
    try:
        async with connection() as cx:
            await cx.execute("INSERT INTO pipeline_errors (stage, ref, error) VALUES (%s, %s, %s)",
                             (stage, ref, error[:_MAX_ERROR]))
    except Exception:
        log.exception("could not record pipeline error stage=%s ref=%s", stage, ref)
