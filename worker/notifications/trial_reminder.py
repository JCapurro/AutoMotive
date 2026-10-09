"""Free-trial reminder (docs/RECORDATORIO_PRUEBA.md): one email per account,
ever, to accounts whose 72 h free trial ended without buying a plan.

Every TRIAL_REMINDER_TICK_SECONDS (main.py), with app_config.trial_reminder:

    enabled? email channel? WEB_BASE_URL (unsubscribe link)?   no ──> nothing
          │
    inside send_from..send_until, Argentina?                   no ──> next tick
          │
    claim_trial_reminders(delay, window, max_per_day - claimed today)
          │                          (the database decides who is due)
    each 'pending' row ── still eligible? ── no ──> 'skipped'
                              │
                       Resend, Idempotency-Key trial-reminder-<user_id>
                              │
                'sent' · retry (attempts < 3) · 'failed' + pipeline_errors

A trial that ends at night is due at once but waits for send_from; the
window (> the night gap) keeps a rollout or a long outage from mailing
long-expired trials. Not a notifications row: see the migration
20261017120000_free_trial_reminder.sql.
"""
from __future__ import annotations

import logging
import math
import traceback
from datetime import datetime, time, timedelta, timezone
from typing import Any, Mapping

import db
from db.repos import trial_reminders as repo
from db.repos.runs import log_error
from notifications import templates
from notifications.channels.base import SendResult
from notifications.dispatch import MAX_ATTEMPTS
from notifications.links import Links
from notifications.service import AR


log = logging.getLogger("trial_reminder")

DEFAULTS: dict[str, Any] = {"enabled": True, "delay_hours": 0, "window_hours": 48,
                            "send_from": "09:00", "send_until": "21:00", "max_per_day": 30}
# Why the last tick did nothing without config (logged once, not every tick).
_skipped_reason: str | None = None


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    return default


def _hours(value: Any, default: float, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return default
    return hours if math.isfinite(hours) and hours >= minimum else default


def _clock(value: Any) -> time | None:
    """'09:00' → 09:00; None if it isn't HH:MM."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value.strip(), "%H:%M")
    except ValueError:
        return None
    return parsed.time()


def settings(raw: Any) -> dict[str, Any]:
    """app_config.trial_reminder over DEFAULTS; a bad value falls back to its default."""
    cfg = {**DEFAULTS, **(raw if isinstance(raw, Mapping) else {})}
    out: dict[str, Any] = {"enabled": _bool(cfg["enabled"], DEFAULTS["enabled"]),
                           "delay_hours": _hours(cfg["delay_hours"], DEFAULTS["delay_hours"])}
    start, end = _clock(cfg["send_from"]), _clock(cfg["send_until"])
    if start is None or end is None or start >= end:
        start, end = _clock(DEFAULTS["send_from"]), _clock(DEFAULTS["send_until"])
    out["send_from"], out["send_until"] = start, end
    # The window must outlast the night, or a trial ending after send_until is
    # never sent: it would leave the window before the next send_from.
    night = 24 - (end.hour + end.minute / 60 - start.hour - start.minute / 60)
    window = _hours(cfg["window_hours"], DEFAULTS["window_hours"])
    out["window_hours"] = window if window > night else max(float(DEFAULTS["window_hours"]), night + 1)
    per_day = cfg["max_per_day"]
    out["max_per_day"] = (per_day if isinstance(per_day, int) and not isinstance(per_day, bool)
                          and per_day >= 0 else DEFAULTS["max_per_day"])
    return out


def _skip(reason: str) -> int:
    global _skipped_reason
    if reason != _skipped_reason:
        log.info("trial reminders off: %s", reason)
        _skipped_reason = reason
    return 0


async def _send(channel: Any, row: Mapping[str, Any], links: Links, now: datetime,
                offer: Mapping[str, Any] | None) -> SendResult:
    msg = templates.trial_reminder_email(row["trial_expires_at"], links, row["unsubscribe_token"], now, offer)
    try:
        return await channel.send_message(row["email"], msg,
                                          idempotency_key=f"trial-reminder-{row['user_id']}",
                                          unsubscribe_token=row["unsubscribe_token"])
    except Exception as e:  # an adapter bug is retried, like dispatch.send_one
        return SendResult(False, f"{type(e).__name__}: {e}", retry=True)


async def run_trial_reminders(channel: Any, links: Links, *, now: datetime | None = None) -> int:
    """Claim the accounts that are due and send their reminder. Returns how many were sent.
    `channel` is the email channel (ResendEmailChannel) or None."""
    global _skipped_reason
    now = now or datetime.now(timezone.utc)
    cfg = settings(await db.get_config("trial_reminder", {}))
    if not cfg["enabled"]:
        return _skip("app_config.trial_reminder.enabled = false")
    if channel is None or not hasattr(channel, "send_message"):
        return _skip("no email channel (RESEND_API_KEY / EMAIL_FROM)")
    if not links.tracked:
        return _skip("no WEB_BASE_URL: no unsubscribe link, no commercial email")
    _skipped_reason = None
    local = now.astimezone(AR)
    if not cfg["send_from"] <= local.time() < cfg["send_until"]:
        return 0

    day_start = datetime.combine(local.date(), time(0), tzinfo=AR)
    remaining = cfg["max_per_day"] - await repo.claimed_today(day_start)
    if remaining > 0:
        claimed = await repo.claim(cfg["delay_hours"], cfg["window_hours"], remaining)
        if claimed:
            log.info("trial reminders: %d claimed", len(claimed))

    batch = cfg["max_per_day"]
    rows = await repo.pending(batch) if batch > 0 else []
    offer = await db.get_config("pro_offer", None) if rows else None
    window = timedelta(hours=cfg["delay_hours"] + cfg["window_hours"])
    sent = 0
    for row in rows:
        user = row["user_id"]
        try:
            # Left pending by a crash or an outage longer than the window: too old now.
            if row["trial_expires_at"] + window <= row["db_now"]:
                await repo.mark_skipped(user, "outside_window")
                continue
            if not await repo.still_eligible(user):
                await repo.mark_skipped(user, "not_eligible")
                continue
            if not row["email"] or not row["unsubscribe_token"]:
                await repo.mark_skipped(user, "no_contact")
                continue
            result = await _send(channel, row, links, now, offer)
            if result.ok:
                await repo.mark_sent(user, result.provider_id)
                sent += 1
            elif result.retry and row["attempts"] + 1 < MAX_ATTEMPTS:
                await repo.mark_retry(user, result.error or "")
                log.warning("trial reminder for %s failed, will retry: %s", user, result.error)
            else:
                await repo.mark_failed(user, result.error or "")
                await log_error("trial_reminder", f"user:{user}", result.error or "")
        except Exception:
            log.exception("trial reminder for %s failed", user)
            await log_error("trial_reminder", f"user:{user}", traceback.format_exc())
    if sent:
        log.info("trial reminders: %d sent", sent)
    return sent
