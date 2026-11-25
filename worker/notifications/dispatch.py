"""Queued notifications → channels.

A row is sent once: 'sent' (with an alert_sent event) or, after
MAX_ATTEMPTS transient failures or one permanent failure, 'failed' (and a
pipeline_errors row, stage 'notify'). One drain at a time per process: the
crawl batches, the notification tick and the digest all call it.

Before the access check (prepare_delivery), the pre-send check
(docs/PLAN_DELISTADOS.md, A; app_config.availability_presend, off by
default) reads the detail page of the cars a price_drop or a digest is about
to tell when no source proved them alive in max_age_hours: one that ended is
marked gone there, so prepare_delivery skips the alert or drops the item, as
it already does with what it knows. Each check has its time limit
(timeout_s) and the whole pass too (batch_timeout_s); a check that fails or
runs out of time never holds the alert back: it goes out as it would have.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Mapping

import db

from db.repos import notifications as repo
from db.repos.runs import log_error
from notifications.channels.base import Channel, Notification, SendResult


log = logging.getLogger("dispatch")

MAX_ATTEMPTS = 3
_lock = asyncio.Lock()

PRESEND_DEFAULTS: dict[str, Any] = {
    "enabled": False, "max_age_hours": 6, "kinds": ["price_drop", "digest"], "sources": None,
    "timeout_s": 20, "batch_timeout_s": 120, "max_per_pass": 40, "on_error": "send"}


async def presend_config() -> dict[str, Any]:
    cfg = await db.get_config("availability_presend", {}) or {}
    return {**PRESEND_DEFAULTS, **(cfg if isinstance(cfg, dict) else {})}


def presend_candidates(rows: list[Mapping], kinds: list[str]) -> list[int]:
    """The cars these queued rows would tell: a price_drop's, and a digest's
    items but the ones already told as over (section 'gone')."""
    ids: list[int] = []
    for row in rows:
        if row["kind"] not in kinds:
            continue
        if row["kind"] == "digest":
            for item in (row.get("payload") or {}).get("items") or []:
                if isinstance(item, Mapping) and item.get("section") != "gone" and item.get("listing_id"):
                    try:
                        ids.append(int(item["listing_id"]))
                    except (TypeError, ValueError):
                        pass
        elif row.get("listing_id") is not None:
            ids.append(int(row["listing_id"]))
    return list(dict.fromkeys(ids))


async def presend_check(rows: list[Mapping]):
    """Read the pages of the stale cars these rows are about to tell. Returns
    the checks' IngestResult (listing_gone, price_drop… for the engine), or
    None when the switch is off or nothing is stale. Never raises."""
    from pipeline.enrich import drain, refresh_listing, source_intervals
    from pipeline.ingest import IngestResult

    try:
        cfg = await presend_config()
        if not cfg.get("enabled"):
            return None
        ids = presend_candidates(rows, list(cfg.get("kinds") or []))
        if not ids:
            return None
        from db.repos import listings as listings_repo
        stale = await listings_repo.presend_stale(ids, max_age_hours=float(cfg["max_age_hours"]),
                                                  sources=cfg.get("sources") or None)
        intervals = await source_intervals()
        stale = [r for r in stale if r["source"] in intervals][:max(0, int(cfg["max_per_pass"]))]
        if not stale:
            return None
        timeout = float(cfg["timeout_s"])

        async def check(row: dict) -> IngestResult:
            try:
                return await asyncio.wait_for(refresh_listing(row, stage="presend"), timeout=timeout)
            except Exception as e:          # TimeoutError included: the alert goes out as it is
                log.info("presend: listing %s not checked (%s), sent as it is", row["id"], type(e).__name__)
                return IngestResult()

        deadline = asyncio.Event()
        timer = asyncio.get_running_loop().call_later(float(cfg["batch_timeout_s"]), deadline.set)
        try:
            result = await drain(stale, check, intervals=intervals, stop=deadline)
        finally:
            timer.cancel()
        gone = sum(e.kind == "listing_gone" for e in result.events)
        log.info("presend: %d of %d cars checked before sending, %d over", len(stale), len(ids), gone)
        return result
    except Exception:
        log.exception("presend check failed; alerts go out as they are")
        return None


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


async def deliver_pending(channels: Mapping[str, Channel], *, limit: int = 200,
                          on_presend: Callable[[Any], Awaitable[None]] | None = None) -> int:
    """Send what is queued. Returns how many were sent. `on_presend` gets
    what the pre-send check found (events for the engine), after the queue
    is released."""
    async with _lock:
        sent = 0
        rows = await repo.queued(limit)
        checked = await presend_check(rows) if rows else None
        for row in rows:
            if not await repo.prepare_delivery(row["id"]):
                continue
            if row["kind"] == "digest":
                prepared = await repo.delivery_payload(row["id"])
                if prepared is None:
                    continue
                row["payload"] = prepared
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
    if checked is not None and on_presend is not None:
        try:
            await on_presend(checked)
        except Exception:
            log.exception("presend: the checks' events were not handled")
    return sent
