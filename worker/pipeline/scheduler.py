"""The worker's crawl loop and the Telegram alerts it still sends (F1).

Each tick:
  1. crawl_targets are re-derived from the enabled profiles (pipeline/crawl.py);
  2. new or edited profiles are bootstrapped silently (pipeline/rematch.py);
  3. due targets are crawled and ingested;
  4. each target's batch goes to the Telegram alerts of that make/model, which
     keep the pre-F1 behavior: per-profile filters and radius, "already seen"
     via matches, recency, the legacy opportunity engine and one alert per
     listing per user. Matching with reasons and the 0–100 score replace this
     in F2; the notification engine in F3.

Scraping no longer happens per alert: two users searching the same model
share one crawl.
"""
from __future__ import annotations
import asyncio
import logging
import time
import traceback

from html import escape as _html_escape

from telegram import Bot
from telegram.constants import ParseMode

import db
from config import TICK_INTERVAL_SECONDS, RECOMMENDED_MAX_AGE_DAYS, CRAWL_JITTER_SECONDS
from collectors.base import Listing
from db.repos.runs import log_error
from intelligence.opportunity import evaluate
from pipeline import crawl, rematch
from pipeline.legacy_match import candidates_for

log = logging.getLogger("scheduler")


def _format_notification(alert_name: str, listing, score) -> str:
    """Build an HTML-formatted notification.

    HTML parse mode is used (not Markdown) because Mercado Libre URLs end in
    underscores like `_JM` which break legacy Markdown italics parsing.
    """
    e = _html_escape  # only <, >, & need escaping in HTML mode
    header = "⚠️ <b>Oportunidad sospechosa</b>" if score.suspect_partial else "🚨 <b>Oportunidad</b>"
    parts = [f"{header} — <i>{e(alert_name)}</i>", ""]
    if score.suspect_partial:
        parts.append("<i>Verificá que no sea anticipo / plan antes de contactar.</i>")
        parts.append("")
    parts.append(f"<b>{e(listing.titulo)}</b>")
    if listing.precio:
        parts.append(f"💰 {e(listing.moneda or '')} {int(listing.precio):,}".replace(",", "."))
    if listing.anio:
        parts.append(f"📅 {listing.anio}")
    if listing.km:
        parts.append(f"🛣 {listing.km:,} km".replace(",", "."))
    if listing.ubicacion:
        parts.append(f"📍 {e(listing.ubicacion)}")
    parts.append(f"🏷 {e(listing.source)}")
    if score.median and score.discount_pct is not None:
        parts.append(
            f"📉 {score.discount_pct:.1f}% bajo mediana "
            f"(USD {int(score.median):,} · n={score.sample_size})".replace(",", ".")
        )
    parts.append("")
    parts.append(f'🔗 <a href="{e(listing.url)}">{e(listing.url)}</a>')
    return "\n".join(parts)


def _price_ref(score) -> dict:
    """What the legacy engine concluded, kept on the match for later inspection."""
    return {
        "legacy": True,
        "is_opportunity": score.is_opportunity,
        "median_usd": score.median,
        "n": score.sample_size,
        "diff_pct": score.discount_pct,
        "reason": score.reason,
        "suspect_partial": score.suspect_partial,
    }


def _is_recent(listing, max_age_days: int) -> bool:
    """Drop listings published more than `max_age_days` ago.
    If the scraper couldn't infer a date, accept it — the matches
    table + the per-alert bootstrap flag handle freshness for those."""
    if listing.published_at is None:
        return True
    return (int(time.time()) - listing.published_at) <= max_age_days * 86_400


async def notify_alert(bot: Bot, alert: dict, items: list[Listing], *, source: str,
                       first_run: bool) -> int:
    """The pre-F1 per-alert flow over one target batch. Returns alerts sent."""
    listings = await candidates_for(alert, items, source)
    dicts = [l.to_dict() for l in listings]
    fresh = await db.filter_unseen(alert["id"], dicts)
    fresh_keys = {(x["source"], x["listing_id"]) for x in fresh}
    fresh_listings = [l for l in listings if (l.source, l.listing_id) in fresh_keys]

    # A target's first run, or an alert not bootstrapped yet: everything is
    # backfill, nothing is notified (sección 5.7).
    if first_run or not alert.get("bootstrapped"):
        if fresh_listings:
            await db.mark_seen(alert["id"], [l.to_dict() for l in fresh_listings], backfill=True)
        if not alert.get("bootstrapped"):
            await db.mark_bootstrapped(alert["id"])
        log.info("alert=%s %s: %d backfill, no notifications", alert["id"],
                 "first target run" if first_run else "bootstrap", len(fresh_listings))
        return 0

    # Drop listings published outside the freshness window (when known).
    max_age_days = int(await db.get_config("recommended_max_age_days", RECOMMENDED_MAX_AGE_DAYS))
    recent_listings = [l for l in fresh_listings if _is_recent(l, max_age_days)]

    # A listing another profile of this user already has (the same wizard
    # alert split per model) is not notified twice.
    already_matched = await db.matched_by_other_profiles(
        alert["id"], [l.to_dict() for l in recent_listings])
    price_refs: dict[tuple[str, str], dict] = {}
    sent = 0
    failed_delivery_keys: set[tuple[str, str]] = set()
    for l in recent_listings:
        score = await evaluate(l, alert["filters"])
        price_refs[(l.source, l.listing_id)] = _price_ref(score)
        if not score.is_opportunity or (l.source, l.listing_id) in already_matched:
            continue
        try:
            await bot.send_message(
                chat_id=alert["chat_id"],
                text=_format_notification(alert["name"], l, score),
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False,
            )
            sent += 1
        except Exception as e:
            log.warning("send_message failed: %s", e)
            failed_delivery_keys.add((l.source, l.listing_id))

    # Mark all fresh as seen (even non-recent / non-opportunities) so we don't
    # reconsider them. Failed deliveries stay unseen: the target's next run
    # retries them, so a transient Telegram outage doesn't drop a hit.
    markable = [l for l in fresh_listings if (l.source, l.listing_id) not in failed_delivery_keys]
    if markable:
        await db.mark_seen(alert["id"], [l.to_dict() for l in markable], price_refs=price_refs)
    if failed_delivery_keys:
        log.warning("alert=%s delivery failed for %d opportunity listing(s); retried next run",
                    alert["id"], len(failed_delivery_keys))
    log.info("alert=%s fresh=%d recent=%d notified=%d",
             alert["id"], len(fresh_listings), len(recent_listings), sent)
    return sent


def batch_handler(bot: Bot) -> crawl.BatchHandler:
    async def handle(run: crawl.TargetRun) -> None:
        t = run.target
        for alert in await db.alerts_for_target(t["source"], t.get("make"), t.get("model")):
            try:
                await notify_alert(bot, alert, run.items, source=t["source"],
                                   first_run=run.first_run)
            except Exception:
                await log_error("notify", f"profile:{alert['id']}", traceback.format_exc())
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
