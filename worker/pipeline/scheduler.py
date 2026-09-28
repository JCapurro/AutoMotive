"""The worker's crawl loop.

Each tick:
  1. crawl_targets are re-derived from the enabled profiles (pipeline/crawl.py);
  2. new or edited profiles are bootstrapped silently (pipeline/rematch.py);
  3. due targets are crawled and ingested;
  4. each target's batch is matched and scored against every enabled profile
     of that make/model (intelligence/, sección 6): new and updated listings
     get a match row with reasons, 0–100 score, level, price_ref and red flags;
  5. the batch's new matches and price drops go to the notification engine
     (notifications/, sección 7), which decides, queues and sends them.

Scraping no longer happens per alert: two users searching the same model
share one crawl.
"""
from __future__ import annotations
import asyncio
import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime

import db
from config import TICK_INTERVAL_SECONDS, RECOMMENDED_MAX_AGE_DAYS, CRAWL_JITTER_SECONDS
from db.repos import matches as matches_repo
from db.repos.runs import log_error
from intelligence.engine import Evaluation
from notifications.service import MatchCandidate, Notifier
from pipeline import crawl, rematch
from pipeline.scoring import Scorer

log = logging.getLogger("scheduler")


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


@dataclass
class _Staged:
    """One profile's view of a batch, read before any profile stores anything,
    so "another profile of this user already had it" means before this batch."""
    alert: dict
    evaluations: dict[int, Evaluation]
    fresh: list[int]
    matched_elsewhere: set[tuple[str, str]]


async def _stage(alert: dict, listing_ids: list[int], scorer: Scorer) -> _Staged:
    rows = scorer.rows
    evaluations: dict[int, Evaluation] = {}
    for lid in listing_ids:
        if (ev := scorer.evaluate(lid, alert["profile"])) is not None:
            evaluations[lid] = ev
    items = [{"source": rows[lid]["source"], "listing_id": rows[lid]["external_id"]} for lid in evaluations]
    fresh_keys = {(x["source"], x["listing_id"]) for x in await db.filter_unseen(alert["id"], items)}
    fresh = [lid for lid in evaluations if _key(rows[lid]) in fresh_keys]
    elsewhere = await db.matched_by_other_profiles(
        alert["id"], [{"source": rows[l]["source"], "listing_id": rows[l]["external_id"]} for l in fresh])
    return _Staged(alert, evaluations, fresh, elsewhere)


async def match_alert(staged: _Staged, scorer: Scorer, *, first_run: bool,
                      max_age_days: int) -> list[MatchCandidate]:
    """Store one profile's matches for a batch. Returns the new matches the
    notification engine should consider."""
    alert, evaluations, fresh, rows = staged.alert, staged.evaluations, staged.fresh, scorer.rows

    async def store(ids: list[int], *, backfill: bool) -> dict[int, int]:
        async with db.connection() as cx:
            return await matches_repo.upsert_scored(cx, alert["id"], [(i, evaluations[i].row()) for i in ids],
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
        return []

    match_ids = await store(fresh, backfill=False)
    # Old listings aren't news, and one another profile of this user already
    # had (the same wizard alert split per model) isn't new to the user.
    candidates = [
        MatchCandidate(alert["id"], lid, match_ids.get(lid), evaluations[lid].row(),
                       repost=bool(rows[lid].get("probable_repost_of")))
        for lid in fresh
        if _is_recent(rows[lid], max_age_days) and _key(rows[lid]) not in staged.matched_elsewhere
    ]
    log.info("profile=%s matched=%d fresh=%d candidates=%d",
             alert["id"], len(evaluations), len(fresh), len(candidates))
    return candidates


async def process_batch(notifier: Notifier, target: dict, listing_ids: list[int], *,
                        first_run: bool, events: list = ()) -> None:
    """Steps 4–5 for one batch of a target's listings: match and score them
    against the target's profiles, then notify. tools/simulate_alert.py runs
    it for a single listing."""
    scorer = await Scorer.create()
    await scorer.prepare(listing_ids)
    max_age_days = int(await db.get_config("recommended_max_age_days", RECOMMENDED_MAX_AGE_DAYS))
    staged: list[_Staged] = []
    for alert in await db.alerts_for_target(target["source"], target.get("make"), target.get("model"),
                                            telegram_only=False):
        try:
            staged.append(await _stage(alert, listing_ids, scorer))
        except Exception:
            await log_error("match", f"profile:{alert['id']}", traceback.format_exc())
    candidates: list[MatchCandidate] = []
    for s in staged:
        try:
            candidates += await match_alert(s, scorer, first_run=first_run, max_age_days=max_age_days)
        except Exception:
            await log_error("match", f"profile:{s.alert['id']}", traceback.format_exc())
    # Matches are stored and re-scored: price drops carry the new score.
    try:
        await notifier.on_matches(candidates, scorer.rows)
        if not first_run:
            await notifier.on_listing_events(events)
    except Exception:
        await log_error("notify", f"target:{target.get('id')}", traceback.format_exc())
    await notifier.deliver()


def batch_handler(notifier: Notifier) -> crawl.BatchHandler:
    async def handle(run: crawl.TargetRun) -> None:
        listing_ids = list(dict.fromkeys(run.result.ids.values()))
        if listing_ids:
            await process_batch(notifier, run.target, listing_ids, first_run=run.first_run,
                                events=run.result.events)
    return handle


async def tick(notifier: Notifier, stop: asyncio.Event | None = None,
               on_health: crawl.HealthHandler | None = None) -> None:
    await crawl.sync_targets(await db.enabled_profiles())
    await rematch.run_pending()
    due = await crawl.crawl_due(batch_handler(notifier), jitter_seconds=CRAWL_JITTER_SECONDS, stop=stop,
                                on_health=on_health)
    log.info("crawl tick: %d due targets", due)


async def run_loop(notifier: Notifier, stop_event: asyncio.Event,
                   on_health: crawl.HealthHandler | None = None) -> None:
    while not stop_event.is_set():
        try:
            await tick(notifier, stop_event, on_health)
        except Exception:
            log.error("scheduler tick failed: %s", traceback.format_exc())
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
