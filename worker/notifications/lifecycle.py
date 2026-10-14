"""The plan emails (docs/MAILS_DE_PLAN.md): one ledger row per (account,
kind, event) in lifecycle_emails, so each email goes out once even if the
worker runs again or restarts.

Every TRIAL_REMINDER_TICK_SECONDS (main.py), with app_config.lifecycle_emails:

    record_trial_ends()                           trial_ended events, any hour
    expired_matches.prune()                       2.5's old counts
          │
    enabled? email channel? WEB_BASE_URL (unsubscribe link)?   no ──> nothing more
          │
    inside send_from..send_until, Argentina?                   no ──> next tick
          │
    each enabled kind: claim_lifecycle_emails(kind, window, room left today)
          │                          (the database decides who is due)
    each 'pending' row ── still eligible? ── no ──> 'skipped'
                              │
                       Resend, Idempotency-Key lifecycle-<id>
                              │
         'sent' + lifecycle_email_sent · retry (attempts < 3) · 'failed' + pipeline_errors

An event that becomes due at night waits for send_from; the window keeps a
rollout or a long outage from mailing stale events. Not a notifications row:
see the migration 20261020120000_lifecycle_emails.sql.
"""
from __future__ import annotations

import logging
import math
import traceback
from datetime import datetime, time, timedelta, timezone
from typing import Any, Mapping

import db
from db.repos import expired_matches
from db.repos import lifecycle_emails as repo
from db.repos.runs import log_error
from notifications import templates
from notifications.channels.base import SendResult
from notifications.dispatch import MAX_ATTEMPTS
from notifications.links import Links
from notifications.service import AR


log = logging.getLogger("lifecycle")

# The kinds this worker sends, claimed in this order (the daily cap is shared):
# the ones with a deadline today first.
KINDS = ("pass_expires_today", "trial_ended", "pass_expiring", "trial_no_matches", "count_after_expiry")
DEFAULTS: dict[str, Any] = {"enabled": True, "send_from": "09:00", "send_until": "21:00",
                            "window_hours": 48, "max_per_day": 30,
                            "kinds": {"trial_no_matches": True, "trial_ended": True,
                                      "pass_expiring": True, "pass_expires_today": True,
                                      "count_after_expiry": True}}
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
    """app_config.lifecycle_emails over DEFAULTS; a bad value falls back to its default."""
    cfg = {**DEFAULTS, **(raw if isinstance(raw, Mapping) else {})}
    out: dict[str, Any] = {"enabled": _bool(cfg["enabled"], DEFAULTS["enabled"])}
    start, end = _clock(cfg["send_from"]), _clock(cfg["send_until"])
    if start is None or end is None or start >= end:
        start, end = _clock(DEFAULTS["send_from"]), _clock(DEFAULTS["send_until"])
    out["send_from"], out["send_until"] = start, end
    # The window must outlast the night, or an event due after send_until is
    # never sent: it would leave the window before the next send_from.
    night = 24 - (end.hour + end.minute / 60 - start.hour - start.minute / 60)
    window = _hours(cfg["window_hours"], DEFAULTS["window_hours"])
    out["window_hours"] = window if window > night else max(float(DEFAULTS["window_hours"]), night + 1)
    per_day = cfg["max_per_day"]
    out["max_per_day"] = (per_day if isinstance(per_day, int) and not isinstance(per_day, bool)
                          and per_day >= 0 else DEFAULTS["max_per_day"])
    kinds = cfg["kinds"] if isinstance(cfg["kinds"], Mapping) else {}
    out["kinds"] = {kind: _bool(kinds.get(kind), DEFAULTS["kinds"][kind]) for kind in KINDS}
    return out


def _skip(reason: str) -> int:
    global _skipped_reason
    if reason != _skipped_reason:
        log.info("plan emails off: %s", reason)
        _skipped_reason = reason
    return 0


async def _send(channel: Any, row: Mapping[str, Any], links: Links, now: datetime,
                context: Mapping[str, Any]) -> SendResult:
    msg = templates.lifecycle_email(row, links, now, offer=context.get("offer"), limits=context.get("limits"))
    try:
        return await channel.send_message(row["email"], msg, idempotency_key=f"lifecycle-{row['id']}",
                                          unsubscribe_token=row["unsubscribe_token"])
    except Exception as e:  # an adapter bug is retried, like dispatch.send_one
        return SendResult(False, f"{type(e).__name__}: {e}", retry=True)


async def run_lifecycle_emails(channel: Any, links: Links, *, now: datetime | None = None) -> int:
    """Record trial ends, claim the emails that are due and send them. Returns
    how many were sent. `channel` is the email channel (ResendEmailChannel) or None."""
    global _skipped_reason
    now = now or datetime.now(timezone.utc)
    try:
        await repo.record_trial_ends()
    except Exception:
        log.exception("record_trial_ends failed")
        await log_error("lifecycle_email", "record_trial_ends", traceback.format_exc())
    try:
        await expired_matches.prune()
    except Exception:
        log.exception("expired_matches.prune failed")
        await log_error("lifecycle_email", "expired_matches_prune", traceback.format_exc())
    cfg = settings(await db.get_config("lifecycle_emails", {}))
    if not cfg["enabled"]:
        return _skip("app_config.lifecycle_emails.enabled = false")
    if channel is None or not hasattr(channel, "send_message"):
        return _skip("no email channel (RESEND_API_KEY / EMAIL_FROM)")
    if not links.tracked:
        return _skip("no WEB_BASE_URL: no unsubscribe link, no plan emails")
    _skipped_reason = None
    local = now.astimezone(AR)
    if not cfg["send_from"] <= local.time() < cfg["send_until"]:
        return 0

    day_start = datetime.combine(local.date(), time(0), tzinfo=AR)
    remaining = cfg["max_per_day"] - await repo.claimed_today(day_start)
    for kind in KINDS:
        if remaining <= 0:
            break
        if cfg["kinds"][kind]:
            claimed = await repo.claim(kind, cfg["window_hours"], remaining)
            remaining -= len(claimed)
            if claimed:
                log.info("plan emails: %d %s claimed", len(claimed), kind)

    rows = await repo.pending(cfg["max_per_day"]) if cfg["max_per_day"] > 0 else []
    context = ({"offer": await db.get_config("pro_offer", None),
                "limits": await db.get_config("plan_limits", None)} if rows else {})
    window = timedelta(hours=cfg["window_hours"])
    sent = 0
    for row in rows:
        email_id = row["id"]
        try:
            # Left pending by a crash or an outage longer than the window: too old now.
            if row["created_at"] + window <= row["db_now"]:
                await repo.mark_skipped(email_id, "outside_window")
                continue
            if not await repo.still_eligible(email_id):
                await repo.mark_skipped(email_id, "not_eligible")
                continue
            if not row["email"] or not row["unsubscribe_token"]:
                await repo.mark_skipped(email_id, "no_contact")
                continue
            result = await _send(channel, row, links, now, context)
            if result.ok:
                await repo.mark_sent(email_id, result.provider_id)
                sent += 1
            elif result.retry and row["attempts"] + 1 < MAX_ATTEMPTS:
                await repo.mark_retry(email_id, result.error or "")
                log.warning("plan email %s failed, will retry: %s", email_id, result.error)
            else:
                await repo.mark_failed(email_id, result.error or "")
                await log_error("lifecycle_email", f"lifecycle:{email_id}", result.error or "")
        except Exception:
            log.exception("plan email %s failed", email_id)
            await log_error("lifecycle_email", f"lifecycle:{email_id}", traceback.format_exc())
    if sent:
        log.info("plan emails: %d sent", sent)
    return sent
