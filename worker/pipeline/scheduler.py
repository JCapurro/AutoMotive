"""The worker's crawl loop and the Telegram alerts it still sends (F2).

Each tick:
  1. crawl_targets are re-derived from the enabled profiles (pipeline/crawl.py);
  2. new or edited profiles are bootstrapped silently (pipeline/rematch.py);
  3. due targets are crawled and ingested;
  4. each target's batch is matched and scored against every enabled profile
     of that make/model (intelligence/, sección 6): new and updated listings
     get a match row with reasons, 0–100 score, level, price_ref and red flags.
     Telegram-linked profiles are alerted for new, recent, non-backfill 🔥 high
     matches (the `opportunity` kind of sección 7.1), once per listing per user.
     The notification engine replaces this last step in F3.

Scraping no longer happens per alert: two users searching the same model
share one crawl.
"""
from __future__ import annotations
import asyncio
import logging
import time
import traceback
from datetime import datetime

from html import escape as _html_escape

from telegram import Bot
from telegram.constants import ParseMode

import db
from config import TICK_INTERVAL_SECONDS, RECOMMENDED_MAX_AGE_DAYS, CRAWL_JITTER_SECONDS
from db.repos import matches as matches_repo
from db.repos.runs import log_error
from intelligence import copy
from intelligence.engine import Evaluation
from intelligence.levels import at_least
from pipeline import crawl, rematch
from pipeline.scoring import Scorer

log = logging.getLogger("scheduler")

# Level that triggers a Telegram alert until F3's engine.decide (sección 7.1).
ALERT_LEVEL = "high"
# Red flags shown in the Telegram message, warnings first.
_ALERT_FLAGS = 2


def _format_notification(alert_name: str, row: dict, ev: Evaluation) -> str:
    """Build an HTML-formatted notification.

    HTML parse mode is used (not Markdown) because Mercado Libre URLs end in
    underscores like `_JM` which break legacy Markdown italics parsing.
    """
    e = _html_escape  # only <, >, & need escaping in HTML mode
    parts = [f"{copy.LEVEL_LABEL[ev.level]} · <b>{ev.score.score}</b> — <i>{e(alert_name)}</i>", ""]
    parts.append(f"<b>{e(row['title'])}</b>")
    if row.get("price"):
        parts.append(f"💰 {e(copy.money(row['price'], row.get('currency')))} (precio publicado)")
    if row.get("year"):
        parts.append(f"📅 {row['year']}")
    if row.get("mileage_km") is not None:
        parts.append(f"🛣 {copy.number(row['mileage_km'])} km")
    if row.get("location_text"):
        parts.append(f"📍 {e(row['location_text'])}")
    parts.append(f"🏷 {e(row['source'])}")
    if ev.score.extra.get("diff_pct") is not None:
        parts.append(f"📉 {e(ev.score.components['price'].explanation)}")
    for flag in sorted(ev.red_flags, key=lambda f: f.severity != "warning")[:_ALERT_FLAGS]:
        parts.append(f"⚠️ {e(flag.text)}")
    parts.append("")
    parts.append(f'🔗 <a href="{e(row["url"])}">{e(row["url"])}</a>')
    return "\n".join(parts)


def _is_recent(row: dict, max_age_days: int) -> bool:
    """Drop listings published more than `max_age_days` ago.
    If the source doesn't say when, accept it — the matches table and the
    bootstrap flag handle freshness for those."""
    published: datetime | None = row.get("published_at")
    if published is None:
        return True
    return (time.time() - published.timestamp()) <= max_age_days * 86_400


def _key(row: dict) -> tuple[str, str]:
    return row["source"], row["external_id"]


async def notify_alert(bot: Bot, alert: dict, listing_ids: list[int], scorer: Scorer, *,
                       first_run: bool) -> int:
    """Match and score one target batch for one profile; alert what deserves it.
    Returns alerts sent."""
    profile, rows = alert["profile"], scorer.rows
    evaluations: dict[int, Evaluation] = {}
    for lid in listing_ids:
        if (ev := scorer.evaluate(lid, profile)) is not None:
            evaluations[lid] = ev
    items = [{"source": rows[lid]["source"], "listing_id": rows[lid]["external_id"]} for lid in evaluations]
    fresh_keys = {(x["source"], x["listing_id"]) for x in await db.filter_unseen(alert["id"], items)}
    fresh = [lid for lid in evaluations if _key(rows[lid]) in fresh_keys]

    async def store(ids: list[int], *, backfill: bool) -> None:
        async with db.connection() as cx:
            await matches_repo.upsert_scored(cx, alert["id"], [(i, evaluations[i].row()) for i in ids],
                                             backfill=backfill)

    # Listings this profile already matched are re-scored (listing_updated);
    # upsert_scored keeps their is_backfill.
    await store([lid for lid in evaluations if lid not in fresh], backfill=True)

    # A target's first run, or an alert not bootstrapped yet: everything is
    # backfill, nothing is notified (sección 5.7).
    if first_run or not alert.get("bootstrapped"):
        await store(fresh, backfill=True)
        if not alert.get("bootstrapped"):
            await db.mark_bootstrapped(alert["id"])
        log.info("profile=%s %s: %d backfill, no notifications", alert["id"],
                 "first target run" if first_run else "bootstrap", len(fresh))
        return 0

    max_age_days = int(await db.get_config("recommended_max_age_days", RECOMMENDED_MAX_AGE_DAYS))
    wants_alerts = (alert.get("chat_id") is not None
                    and at_least(ALERT_LEVEL, profile.get("notify_min_level") or "good"))
    candidates = [lid for lid in fresh if wants_alerts and evaluations[lid].level == ALERT_LEVEL
                  and not rows[lid].get("probable_repost_of") and _is_recent(rows[lid], max_age_days)]
    # A listing another profile of this user already has (the same wizard
    # alert split per model) is not notified twice.
    already_matched = await db.matched_by_other_profiles(
        alert["id"], [{"source": rows[l]["source"], "listing_id": rows[l]["external_id"]} for l in candidates])
    sent = 0
    failed: set[int] = set()
    for lid in candidates:
        if _key(rows[lid]) in already_matched:
            continue
        try:
            await bot.send_message(
                chat_id=alert["chat_id"],
                text=_format_notification(alert["name"], rows[lid], evaluations[lid]),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            sent += 1
        except Exception as e:
            log.warning("send_message failed: %s", e)
            failed.add(lid)

    # Every fresh match is stored, so it isn't new again, except failed
    # deliveries: the target's next run retries them, so a transient Telegram
    # outage doesn't drop a hit.
    await store([lid for lid in fresh if lid not in failed], backfill=False)
    if failed:
        log.warning("profile=%s delivery failed for %d listing(s); retried next run",
                    alert["id"], len(failed))
    log.info("profile=%s matched=%d fresh=%d notified=%d",
             alert["id"], len(evaluations), len(fresh), sent)
    return sent


def batch_handler(bot: Bot) -> crawl.BatchHandler:
    async def handle(run: crawl.TargetRun) -> None:
        t = run.target
        listing_ids = list(dict.fromkeys(run.result.ids.values()))
        if not listing_ids:
            return
        scorer = await Scorer.create()
        await scorer.prepare(listing_ids)
        for alert in await db.alerts_for_target(t["source"], t.get("make"), t.get("model"),
                                                telegram_only=False):
            try:
                await notify_alert(bot, alert, listing_ids, scorer, first_run=run.first_run)
            except Exception:
                await log_error("match", f"profile:{alert['id']}", traceback.format_exc())
    return handle


async def tick(bot: Bot, stop: asyncio.Event | None = None) -> None:
    await crawl.sync_targets(await db.enabled_profiles())
    await rematch.run_pending()
    due = await crawl.crawl_due(batch_handler(bot), jitter_seconds=CRAWL_JITTER_SECONDS, stop=stop)
    log.info("crawl tick: %d due targets", due)


async def run_loop(bot: Bot, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            await tick(bot, stop_event)
        except Exception:
            log.error("scheduler tick failed: %s", traceback.format_exc())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
