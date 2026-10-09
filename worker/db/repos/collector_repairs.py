"""Private collector incidents and durable reservations for local repair chats.

Health snapshots create/close incidents in Postgres. Callers commit the claim
before creating a chat, then attach it with the returned reservation token.
On a recovered lease, reconcile the exact incident UUID chat title first: the
previous monitor may have created the chat before losing its reservation.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg import AsyncConnection


async def claim(cx: AsyncConnection, owner: str, lease_seconds: int = 900) -> dict[str, Any] | None:
    """Reserve the oldest pending/expired incident under a fresh known snapshot.

    SKIP LOCKED permits competing monitors without reserving the same incident.
    ``lease_recovered`` requires chat reconciliation before any new creation.
    """
    if not owner.strip() or lease_seconds <= 0:
        raise ValueError('owner and a positive lease_seconds are required')
    return await (await cx.execute(
        "WITH candidate AS ("
        " SELECT r.id, (r.status = 'dispatching') AS lease_recovered"
        " FROM public.collector_repair_incidents r"
        " JOIN public.sources s ON s.id = r.source AND s.enabled"
        " CROSS JOIN public.platform_health_checks h"
        " WHERE h.id = 1 AND h.checked_at > clock_timestamp() - interval '12 minutes'"
        " AND h.checked_at <= clock_timestamp() + interval '1 minute'"
        " AND h.checks ? 'base' AND h.checks->'base' = 'null'::jsonb"
        " AND jsonb_typeof(h.checks->('collector:' || r.source)) = 'string'"
        " AND btrim(h.checks->>('collector:' || r.source)) <> ''"
        " AND r.resolved_at IS NULL AND r.thread_id IS NULL"
        " AND (r.status = 'pending' OR (r.status = 'dispatching'"
        "      AND r.lease_expires_at <= clock_timestamp()))"
        " ORDER BY r.created_at, r.id FOR UPDATE OF r SKIP LOCKED LIMIT 1"
        ") UPDATE public.collector_repair_incidents r"
        " SET status = 'dispatching', claim_token = gen_random_uuid(), lease_owner = %s,"
        " lease_expires_at = clock_timestamp() + make_interval(secs => %s),"
        " updated_at = clock_timestamp()"
        " FROM candidate WHERE r.id = candidate.id RETURNING r.*, candidate.lease_recovered",
        (owner, lease_seconds))).fetchone()


async def attach(cx: AsyncConnection, incident_id: UUID | str, token: UUID | str,
                 thread_id: str) -> bool:
    """Associate exactly one chat using the current reservation token.

    An active dispatching reservation must be unexpired. A terminal incident
    can still record a matching-token chat created before recovery/removal.
    A quarantined needs_input incident can also record its matching-token chat
    after expiry because its token cannot be reclaimed. Both keep their status.
    """
    if not thread_id.strip():
        raise ValueError('thread_id is required')
    result = await cx.execute(
        "UPDATE public.collector_repair_incidents"
        " SET thread_id = %s, status = CASE WHEN status = 'dispatching' THEN 'open' ELSE status END,"
        " lease_expires_at = NULL, updated_at = clock_timestamp()"
        " WHERE id = %s AND claim_token = %s AND ("
        " (thread_id = %s AND status IN ('open', 'needs_input', 'resolved', 'cancelled'))"
        " OR (thread_id IS NULL AND (resolved_at IS NOT NULL OR status = 'needs_input' OR"
        "     (status = 'dispatching' AND lease_expires_at > clock_timestamp()))))",
        (thread_id, incident_id, token, thread_id))
    return result.rowcount == 1


async def needs_input(cx: AsyncConnection, incident_id: UUID | str, note: str) -> bool:
    """Pause an open chat or ambiguous dispatch without permitting another claim."""
    if not note.strip():
        raise ValueError('note is required')
    result = await cx.execute(
        "UPDATE public.collector_repair_incidents"
        " SET status = 'needs_input', note = %s, updated_at = clock_timestamp()"
        " WHERE id = %s AND resolved_at IS NULL AND status IN ('open', 'dispatching')",
        (note, incident_id))
    return result.rowcount == 1
