"""Queued notifications → channels.

A row is sent once: 'sent' (with an alert_sent event) or, after
MAX_ATTEMPTS transient failures or one permanent failure, 'failed' (and a
pipeline_errors row, stage 'notify'). One drain at a time per process: the
crawl batches, the notification tick and the digest all call it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Mapping

from db.repos import notifications as repo
from db.repos.runs import log_error
from notifications.channels.base import Channel, Notification, SendResult


log = logging.getLogger("dispatch")

MAX_ATTEMPTS = 3
_lock = asyncio.Lock()


def to_notification(row: Mapping) -> Notification:
    return Notification(id=row["id"], user_id=str(row["user_id"]), kind=row["kind"],
                        channel=row["channel"], payload=row["payload"] or {},
                        listing_id=row.get("listing_id"), created_at=row.get("created_at"),
                        telegram_chat_id=row.get("telegram_chat_id"), email=row.get("email"),
                        unsubscribe_token=row.get("unsubscribe_token"))


async def send_one(channel: Channel | None, n: Notification) -> SendResult:
    if channel is None:
        return SendResult(False, f"canal {n.channel} no configurado")
    try:
        return await channel.send(n)
    except Exception as e:  # an adapter bug must not stop the queue
        return SendResult(False, f"{type(e).__name__}: {e}", retry=True)


async def deliver_pending(channels: Mapping[str, Channel], *, limit: int = 200) -> int:
    """Send what is queued. Returns how many were sent."""
    async with _lock:
        sent = 0
        for row in await repo.queued(limit):
            n = to_notification(row)
            result = await send_one(channels.get(n.channel), n)
            if result.ok:
                await repo.mark_sent(n.id, provider_id=result.provider_id, extra=dict(result.extra))
                sent += 1
            elif result.retry and row["attempts"] + 1 < MAX_ATTEMPTS:
                await repo.mark_retry(n.id, result.error or "")
                log.warning("notification %s (%s) failed, will retry: %s", n.id, n.channel, result.error)
            else:
                await repo.mark_failed(n.id, result.error or "")
                await log_error("notify", f"notification:{n.id}", result.error or "")
        return sent
