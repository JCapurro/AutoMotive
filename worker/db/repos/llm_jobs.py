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


async def finish(cx: AsyncConnection, job_id: int, *, output: dict | None = None,
                 error: str | None = None, latency_ms: int | None = None) -> None:
    """'done' with its output, or 'failed' with the error (never both)."""
    await cx.execute(
        "UPDATE llm_jobs SET status = %s, output = %s, error = %s, latency_ms = %s, "
        "       finished_at = now() "
        " WHERE id = %s AND status = 'running'",
        ("failed" if error else "done", None if error else Jsonb(output),
         error[:500] if error else None, latency_ms, job_id))


async def expire(cx: AsyncConnection, *, queued_seconds: float, running_seconds: float) -> int:
    """Fail what nobody will read anymore: queued jobs older than
    `queued_seconds` (the web already fell back to the form) and running ones
    older than `running_seconds` (their worker died mid-job)."""
    cur = await cx.execute(
        "UPDATE llm_jobs SET status = 'failed', finished_at = now(), "
        "       error = CASE status WHEN 'queued' THEN 'vencido en la cola' "
        "                           ELSE 'interrumpido' END "
        " WHERE (status = 'queued' AND created_at < now() - make_interval(secs => %s)) "
        "    OR (status = 'running' AND started_at < now() - make_interval(secs => %s))",
        (queued_seconds, running_seconds))
    return cur.rowcount
