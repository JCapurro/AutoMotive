"""trial_reminders: the send ledger of the free-trial reminder email
(docs/RECORDATORIO_PRUEBA.md). One row per account, ever.

    claim ──> 'pending' ──> 'sent'
                 │ └──────> 'failed'   (MAX_ATTEMPTS transient failures, or one permanent)
                 └────────> 'skipped'  (no longer eligible when it was its turn)

Who is due is decided by the database (public.claim_trial_reminders and
public.trial_reminder_eligible, with its clock); notifications/trial_reminder.py
decides when to run and sends. No events rows: the ledger is the funnel record.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from db.pool import connection


async def claim(delay_hours: float, window_hours: float, limit: int) -> list[dict[str, Any]]:
    """Claim up to `limit` due accounts (new 'pending' rows), oldest trial end first."""
    if limit <= 0:
        return []
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT user_id::text AS user_id, trial_expires_at "
            "  FROM public.claim_trial_reminders(make_interval(secs => %s), make_interval(secs => %s), %s)",
            (delay_hours * 3600, window_hours * 3600, limit))).fetchall()


async def claimed_today(since: datetime) -> int:
    """Rows claimed since `since` (the start of the day, ART), whatever their status."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT count(*) AS n FROM public.trial_reminders WHERE created_at >= %s", (since,))).fetchone()
    return row["n"] if row else 0


async def pending(limit: int) -> list[dict[str, Any]]:
    """Rows waiting to be sent, with the contact data and the database clock."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT r.user_id::text AS user_id, r.trial_expires_at, r.attempts, r.created_at, "
            "       p.email, p.email_unsubscribe_token::text AS unsubscribe_token, now() AS db_now "
            "  FROM public.trial_reminders r JOIN public.profiles p ON p.id = r.user_id "
            " WHERE r.status = 'pending' ORDER BY r.created_at, r.trial_expires_at, r.user_id LIMIT %s",
            (limit,))).fetchall()


async def still_eligible(user_id: str) -> bool:
    """public.trial_reminder_eligible: they may have paid or opted out since the claim."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT public.trial_reminder_eligible(%s) AS ok", (user_id,))).fetchone()
    return bool(row and row["ok"])


async def mark_sent(user_id: str, provider_id: str | None) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE public.trial_reminders SET status = 'sent', sent_at = now(), provider_id = %s, "
            "       error = NULL, attempts = attempts + 1 "
            " WHERE user_id = %s AND status = 'pending'", (provider_id, user_id))


async def mark_retry(user_id: str, error: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE public.trial_reminders SET attempts = attempts + 1, error = %s "
            " WHERE user_id = %s AND status = 'pending'", (error, user_id))


async def mark_failed(user_id: str, error: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE public.trial_reminders SET status = 'failed', attempts = attempts + 1, error = %s "
            " WHERE user_id = %s AND status = 'pending'", (error, user_id))


async def mark_skipped(user_id: str, reason: str) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE public.trial_reminders SET status = 'skipped', error = %s "
            " WHERE user_id = %s AND status = 'pending'", (reason, user_id))
