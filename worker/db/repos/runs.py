"""Observability (sección 10, §46): collector_runs, pipeline_errors and source health."""
from __future__ import annotations

import logging

from db.pool import connection


log = logging.getLogger("runs")

_MAX_ERROR = 4_000


async def start_run(source: str, target_id: int | None) -> int:
    async with connection() as cx:
        row = await (await cx.execute(
            "INSERT INTO collector_runs (source, target_id) VALUES (%s, %s) RETURNING id",
            (source, target_id))).fetchone()
    return row["id"]


async def finish_run(run_id: int, *, ok: bool, found: int | None = None, new: int | None = None,
                     updated: int | None = None, error: str | None = None) -> None:
    """Close a run and keep the source's health counters in step."""
    async with connection() as cx:
        row = await (await cx.execute(
            "UPDATE collector_runs SET finished_at = now(), status = %s, found = %s, new = %s, "
            "  updated = %s, error = %s WHERE id = %s RETURNING source",
            ("ok" if ok else "failed", found, new, updated,
             error[:_MAX_ERROR] if error else None, run_id))).fetchone()
        if row is None:
            return
        if ok:
            await cx.execute("UPDATE sources SET last_ok_at = now(), consecutive_failures = 0 "
                             "WHERE id = %s", (row["source"],))
        else:
            await cx.execute("UPDATE sources SET consecutive_failures = consecutive_failures + 1 "
                             "WHERE id = %s", (row["source"],))


async def log_error(stage: str, ref: str | None, error: str) -> None:
    """Record a pipeline error. Never raises: observability must not break the pipeline."""
    try:
        async with connection() as cx:
            await cx.execute("INSERT INTO pipeline_errors (stage, ref, error) VALUES (%s, %s, %s)",
                             (stage, ref, error[:_MAX_ERROR]))
    except Exception:
        log.exception("could not record pipeline error stage=%s ref=%s", stage, ref)
