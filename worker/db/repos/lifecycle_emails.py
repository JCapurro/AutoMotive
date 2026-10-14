"""lifecycle_emails: the send ledger of the plan emails (docs/MAILS_DE_PLAN.md).
One row per (account, kind, event), so each email goes out once.

    claim ──> 'pending' ──> 'sent'      (+ a lifecycle_email_sent event)
                 │ └──────> 'failed'    (MAX_ATTEMPTS transient failures, or one permanent)
                 └────────> 'skipped'   (no longer eligible when it was its turn)

Who is due and what the email says are decided by the database
(public.claim_lifecycle_emails and public.lifecycle_email_eligible, with its
clock); notifications/lifecycle.py decides when to run and sends.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from db.pool import connection


async def claim(kind: str, window_hours: float, limit: int) -> list[dict[str, Any]]:
    """Claim up to `limit` due events of one kind (new 'pending' rows), oldest first."""
    if limit <= 0:
        return []
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT id, user_id::text AS user_id, kind, payload "
            "  FROM public.claim_lifecycle_emails(%s, make_interval(secs => %s), %s)",
            (kind, window_hours * 3600, limit))).fetchall()


async def claimed_today(since: datetime) -> int:
    """Rows claimed since `since` (the start of the day, ART), whatever their kind or status."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT count(*) AS n FROM public.lifecycle_emails WHERE created_at >= %s", (since,))).fetchone()
    return row["n"] if row else 0


async def pending(limit: int) -> list[dict[str, Any]]:
    """Rows waiting to be sent, with the contact data and the database clock."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT e.id, e.user_id::text AS user_id, e.kind, e.payload, e.attempts, e.created_at, "
            "       p.email, p.email_unsubscribe_token::text AS unsubscribe_token, now() AS db_now "
            "  FROM public.lifecycle_emails e JOIN public.profiles p ON p.id = e.user_id "
            " WHERE e.status = 'pending' ORDER BY e.created_at, e.id LIMIT %s", (limit,))).fetchall()


async def still_eligible(email_id: int) -> bool:
    """public.lifecycle_email_eligible: they may have paid or opted out since the claim."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT public.lifecycle_email_eligible(%s) AS ok", (email_id,))).fetchone()
    return bool(row and row["ok"])


async def mark_sent(email_id: int, provider_id: str | None) -> None:
    async with connection() as cx:
        row = await (await cx.execute(
            "UPDATE public.lifecycle_emails SET status = 'sent', sent_at = now(), provider_id = %s, "
            "       error = NULL, attempts = attempts + 1 "
            " WHERE id = %s AND status = 'pending' "
            "RETURNING user_id, kind, search_profile_id", (provider_id, email_id))).fetchone()
        if row:
            await cx.execute("INSERT INTO public.events (user_id, name, props) VALUES (%s, 'lifecycle_email_sent', %s)",
                             (row["user_id"], Jsonb({"email_id": email_id, "kind": row["kind"],
                                                     "search_profile_id": row["search_profile_id"]})))


async def mark_retry(email_id: int, error: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE public.lifecycle_emails SET attempts = attempts + 1, error = %s "
            " WHERE id = %s AND status = 'pending'", (error, email_id))


async def mark_failed(email_id: int, error: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE public.lifecycle_emails SET status = 'failed', attempts = attempts + 1, error = %s "
            " WHERE id = %s AND status = 'pending'", (error, email_id))


async def mark_skipped(email_id: int, reason: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE public.lifecycle_emails SET status = 'skipped', error = %s "
            " WHERE id = %s AND status = 'pending'", (reason, email_id))


async def record_trial_ends() -> int:
    """trial_ended events for the trials that are over (public.record_trial_ends)."""
    async with connection() as cx:
        row = await (await cx.execute("SELECT public.record_trial_ends() AS n")).fetchone()
    return row["n"] if row else 0
