"""The incident queue and the run history the launcher acts on (async, over db).

Every function takes an open connection: the caller owns the pool and the
transaction. db, config and the tools are imported on first use, so importing
this module reads nothing and the launcher can load its .env before they do.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

# A run left 'running' this long is stuck (the health check's default timeout):
# its target counts as failing and the run no longer counts as activity.
STALLED_MINUTES = 30

_RUNS_SINCE_SQL = (
    'SELECT id, target_id, status, started_at, finished_at, found, new, updated, error '
    'FROM collector_runs WHERE source = %s AND target_id = ANY(%s::bigint[]) AND started_at > %s '
    'ORDER BY started_at, id')


async def active_incidents(cx) -> list[dict[str, Any]]:
    """Unresolved incidents, oldest first. problem and note are raw, untrusted text."""
    return await (await cx.execute(
        'SELECT * FROM collector_repair_incidents WHERE resolved_at IS NULL '
        'ORDER BY created_at, id')).fetchall()


async def claim(cx, owner: str) -> dict[str, Any] | None:
    from db.repos import collector_repairs as repository
    return await repository.claim(cx, owner)


async def attach(cx, incident_id: UUID | str, token: UUID | str, thread: str) -> bool:
    from db.repos import collector_repairs as repository
    return await repository.attach(cx, incident_id, token, thread)


async def needs_input(cx, incident_id: UUID | str, note: str) -> bool:
    from db.repos import collector_repairs as repository
    from tools.collector_repairs import safe_text
    return await repository.needs_input(cx, incident_id, safe_text(note))


async def incident_context(cx, incident: dict[str, Any]) -> dict[str, Any]:
    """Sanitized evidence for the prompt: health snapshot, active targets, recent runs."""
    from tools.collector_repairs import build_context, context_rows
    return build_context(incident, *await context_rows(cx, incident))


async def failing_targets(cx, source: str, limit: int = 5) -> list[int]:
    """Monitored targets whose latest finished run failed, also while a retry of it is running,
    or whose latest run is stuck, lowest id first.

    The health check's own query is the subquery, so "monitored" and "latest
    run" (started_at desc, id desc) mean here exactly what they mean there.
    statuses[1] is its latest 'ok' or 'failed' run.
    """
    from tools.platform_health import COLLECTORS_SQL
    rows = await (await cx.execute(
        'select id from (' + COLLECTORS_SQL + ') health where source = %(source)s and ('
        " statuses[1] = 'failed' or (latest_status = 'running'"
        '   and started_at < now() - make_interval(mins => %(stalled)s)))'
        ' order by id limit %(limit)s',
        {'history': 1, 'source': source, 'stalled': STALLED_MINUTES, 'limit': limit})).fetchall()
    return [row['id'] for row in rows]


async def running_runs(cx, source: str) -> int:
    """Runs of the source in progress; stuck ones (see STALLED_MINUTES) are not waited for."""
    row = await (await cx.execute(
        "SELECT count(*) AS running FROM collector_runs WHERE source = %s AND status = 'running' "
        'AND started_at > now() - make_interval(mins => %s)', (source, STALLED_MINUTES))).fetchone()
    return row['running']


async def kick(cx, source: str, target_ids: list[int]) -> list[int]:
    """Make active targets of the source due now. Returns the ids actually updated."""
    ids = _ids(target_ids)
    if not ids:
        return []
    rows = await (await cx.execute(
        'UPDATE crawl_targets SET next_run_at = now() '
        'WHERE source = %s AND active AND id = ANY(%s::bigint[]) RETURNING id', (source, ids))).fetchall()
    return sorted(row['id'] for row in rows)


async def runs_since(cx, source: str, target_ids: list[int], since: datetime) -> list[dict[str, Any]]:
    """Runs of those targets started after `since`, oldest first, with a sanitized error."""
    if not isinstance(since, datetime) or since.tzinfo is None:
        raise ValueError('since must be a timezone-aware datetime')
    ids = _ids(target_ids)
    if not ids:
        return []
    from tools.collector_repairs import safe_text
    rows = await (await cx.execute(_RUNS_SINCE_SQL, (source, ids, since))).fetchall()
    return [{**row, 'error': safe_text(row['error']) or None} for row in rows]


async def db_now(cx) -> datetime:
    """The database clock, the one collector_runs.started_at is compared against."""
    return (await (await cx.execute('SELECT clock_timestamp() AS now')).fetchone())['now']


def _ids(target_ids: list[int]) -> list[int]:
    if any(isinstance(item, bool) or not isinstance(item, int) for item in target_ids):
        raise ValueError('target ids must be integers')
    return sorted(set(target_ids))
