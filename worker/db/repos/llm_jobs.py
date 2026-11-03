"""llm_jobs: the queue between the web and the LLM layer (sección 8.4).

The web inserts 'queued' rows (RLS: its own, with kind and input only). The
worker claims one at a time with FOR UPDATE SKIP LOCKED, so several loops or
worker processes never take the same job, and writes the result back.
"""
from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb


async def claim(cx: AsyncConnection, kinds: list[str], provider: str) -> dict[str, Any] | None:
    """The oldest queued job of `kinds`, now 'running'; None if there is none."""
    return await (await cx.execute(
        "UPDATE llm_jobs SET status = 'running', started_at = now(), provider = %s "
        " WHERE id = (SELECT id FROM llm_jobs "
        "              WHERE status = 'queued' AND kind = ANY(%s) "
        "              ORDER BY created_at, id "
        "              FOR UPDATE SKIP LOCKED LIMIT 1) "
        "RETURNING id, user_id, kind, input, created_at",
        (provider, kinds))).fetchone()


_KEEP = object()


async def finish(cx: AsyncConnection, job_id: int, *, output: dict | None = None,
                 error: str | None = None, latency_ms: int | None = None,
                 provider: Any = _KEEP) -> None:
    """'done' with its output, or 'failed' with the error (never both).
    `provider` replaces the one claim wrote: 'cache' for a cache hit, None for
    a job that never reached the provider (PAR-04: neither counts for a cap)."""
    sets = "status = %s, output = %s, error = %s, latency_ms = %s, finished_at = now()"
    params: list[Any] = ["failed" if error else "done", None if error else Jsonb(output),
                         error[:500] if error else None, latency_ms]
    if provider is not _KEEP:
        sets += ", provider = %s"
        params.append(provider)
    await cx.execute(f"UPDATE llm_jobs SET {sets} WHERE id = %s AND status = 'running'", (*params, job_id))


async def expire(cx: AsyncConnection, *, queued_seconds: float, running_seconds: float,
                 guide_queued_seconds: float | None = None, guide_running_seconds: float | None = None) -> int:
    """Fail what nobody will read anymore: queued jobs older than
    `queued_seconds` (the web already fell back to the form) and running ones
    older than `running_seconds` (their worker died mid-job). PAR-04: guide
    jobs ('model_guide') have their own bounds (nobody waits on a screen)."""
    guide_queued = queued_seconds if guide_queued_seconds is None else guide_queued_seconds
    guide_running = running_seconds if guide_running_seconds is None else guide_running_seconds
    cur = await cx.execute(
        "UPDATE llm_jobs SET status = 'failed', finished_at = now(), "
        "       error = CASE status WHEN 'queued' THEN 'vencido en la cola' "
        "                           ELSE 'interrumpido' END "
        " WHERE (status = 'queued' AND created_at < now() - make_interval(secs => "
        "          CASE WHEN kind = 'model_guide' THEN %s ELSE %s END)) "
        "    OR (status = 'running' AND started_at < now() - make_interval(secs => "
        "          CASE WHEN kind = 'model_guide' THEN %s ELSE %s END))",
        (guide_queued, queued_seconds, guide_running, running_seconds))
    return cur.rowcount
