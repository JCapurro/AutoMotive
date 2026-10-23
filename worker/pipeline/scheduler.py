"""The worker's crawl loop.

Each tick:
  1. crawl_targets are re-derived from the enabled profiles, plus the searches
     2.5 counts after their access ended (pipeline/crawl.py);
  2. new or edited profiles are bootstrapped silently (pipeline/rematch.py);
  3. due targets are crawled and ingested, each source in its own lane
     (crawl.Lanes) that the tick starts and doesn't wait for, so a hung
     source never stops the loop nor the bootstrap of new searches;
  4. each target's batch is matched and scored against every enabled profile
     of that make/model, and against the searches without a model, only by
     body type (docs/CARROCERIA.md), whatever target brought it
     (intelligence/, sección 6): new and updated listings get a match row
     with reasons, 0–100 score, level, price_ref and red flags;
  5. the batch's new matches and price drops go to the notification engine
     (notifications/, sección 7), which decides, queues and sends them;
  6. the searches whose access ended in the last 3 weeks only count the new
     listings they would have matched (expired_search_matches, 2.5): no
     match, no notification (docs/MAILS_DE_PLAN.md).

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
from typing import Iterable

import db
from config import TICK_INTERVAL_SECONDS, RECOMMENDED_MAX_AGE_DAYS, CRAWL_JITTER_SECONDS
from db.repos import expired_matches
from db.repos import matches as matches_repo
from db.repos.runs import bootstrapped_at, log_error
from intelligence.engine import Evaluation
from intelligence.matching import model_less
from notifications.service import MatchCandidate, Notifier
from pipeline import crawl, news, rematch
from pipeline.scoring import Scorer

log = logging.getLogger("scheduler")


def _is_recent(row: dict, max_age_days: int) -> bool:
    """Drop old listings, using first detection when publication is unknown."""
    since: datetime | None = row.get("published_at") or row.get("first_seen_at")
    if since is None:
        return True
    return (time.time() - since.timestamp()) <= max_age_days * 86_400


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
                      max_age_days: int, foreign_first_run: bool = False, held_first_run: bool = False,
                      backfill_ids: Iterable[int] = ()) -> list[MatchCandidate]:
    """Store one profile's matches for a batch. Returns the new matches the
    notification engine should consider.

    `foreign_first_run`: the first run of a target that doesn't exist for this
    profile (a model, inventory or Facebook target reaching a search without
    a model, docs/CARROCERIA.md). That search is not new, so the target's
    30-day first pass must not mute it: a listing published recently goes the
    usual way (stored as news, notified while it is recent); an old one, or
    one without a publication date (it can't be told from old stock), is
    backfill. Muting the recent ones would lose them for good: the search's
    target by body type reads only the last day, and this target's next
    runs only what was published since. `held_first_run`: a first run that
    follows an empty one (crawl._run_one held the bootstrap): the searches
    already waited a run, so it goes the same way for every profile.
    `backfill_ids`: listings of the batch
    that are not news for this profile (a body type the crawl just filled in,
    a listing the prefilter had dropped, old stock pipeline/news.py found):
    stored as backfill, never notified. What news.py marked as old stock
    stays backfill on every run that finds it, so a batch retried after a
    failure (or a restart) doesn't notify it."""
    alert, evaluations, fresh, rows = staged.alert, staged.evaluations, staged.fresh, scorer.rows

    async def store(ids: list[int], *, backfill: bool) -> dict[int, int]:
        async with db.connection() as cx:
            return await matches_repo.upsert_scored(cx, alert["id"], [(i, evaluations[i].row()) for i in ids],
                                                    backfill=backfill)

    # Listings this profile already matched are re-scored (listing_updated);
    # upsert_scored keeps their is_backfill.
    await store([lid for lid in evaluations if lid not in fresh], backfill=True)

    if first_run and (foreign_first_run or held_first_run) and alert.get("bootstrapped"):
        dated = {lid for lid in fresh
                 if rows[lid].get("published_at") is not None and _is_recent(rows[lid], max_age_days)}
        backfill_ids = {*backfill_ids, *(lid for lid in fresh if lid not in dated)}
        log.info("profile=%s %s first run: %d recent publications, %d backfill", alert["id"],
                 "another target's" if foreign_first_run else "a held", len(dated), len(fresh) - len(dated))
    # A target's first run, or an alert not bootstrapped yet: everything is
    # backfill, nothing is notified (sección 5.7).
    elif first_run or not alert.get("bootstrapped"):
        await store(fresh, backfill=True)
        if not alert.get("bootstrapped"):
            await db.mark_bootstrapped(alert["id"])
        log.info("profile=%s %s: %d backfill, no notifications", alert["id"],
                 "first target run" if first_run else "bootstrap", len(fresh))
        return []

    quiet = {*backfill_ids, *(lid for lid in fresh if news.muted(rows[lid]))} & set(fresh)
    if quiet:
        await store([lid for lid in fresh if lid in quiet], backfill=True)
        fresh = [lid for lid in fresh if lid not in quiet]
    match_ids = await store(fresh, backfill=False)
    # Old listings aren't news, and one another profile of this user already
    # had (the same wizard alert split per model) isn't new to the user.
    candidates = [
        MatchCandidate(alert["id"], lid, match_ids.get(lid), evaluations[lid].row(),
                       repost=bool(rows[lid].get("probable_repost_of")) or news.republished(rows[lid]))
        for lid in fresh
        if _is_recent(rows[lid], max_age_days) and _key(rows[lid]) not in staged.matched_elsewhere
    ]
    log.info("profile=%s matched=%d fresh=%d candidates=%d",
             alert["id"], len(evaluations), len(fresh), len(candidates))
    return candidates


async def count_after_expiry(target: dict, listing_ids: list[int], scorer: Scorer, *,
                             first_run: bool, max_age_days: int, exclude: Iterable[int] = ()) -> int:
    """Step 6: the listings first seen after a counted search's access ended,
    recent by the notification rule, that the search would have matched. A
    target's first run is backfill, not news, also on the next runs that find
    it again: a portal enabled after the end loads its stock then. Old stock
    is never counted either: `exclude` (the batch's backfill_ids) and what
    pipeline/news.py marked, also when a later run finds it again. Returns
    how many were counted."""
    if first_run:
        return 0
    alerts = await db.counting_alerts_for_target(
        target["source"], target.get("make"), target.get("model"),
        inventory=(target.get("query") or {}).get("inventory") is True, body_type=target.get("body_type"))
    if not alerts:
        return 0
    history = await bootstrapped_at(target["id"]) if target.get("id") is not None else None
    rows, exclude = scorer.rows, frozenset(exclude)
    counted = []
    for alert in alerts:
        for lid in listing_ids:
            row = rows.get(lid)
            seen = row.get("first_seen_at") if row else None
            if (seen is None or seen < alert["ended_at"] or (history is not None and seen <= history)
                    or not _is_recent(row, max_age_days) or lid in exclude
                    or news.uncounted(row, target.get("id"))):
                continue
            if (ev := scorer.evaluate(lid, alert["profile"])) is not None:
                counted.append((alert["id"], lid, alert["ended_at"], ev.level))
    await expired_matches.store(counted)
    return len(counted)


async def process_batch(notifier: Notifier, target: dict, listing_ids: list[int], *,
                        first_run: bool, events: list = (), backfill_ids: Iterable[int] = (),
                        body_type_filled: Iterable[int] = (), held_first_run: bool = False) -> None:
    """Steps 4–6 for one batch of a target's listings: match and score them
    against the target's profiles, then notify, and count for the searches
    with ended access. tools/simulate_alert.py runs it for a single listing.

    `backfill_ids` are old stock for every profile (TargetRun.backfill_ids),
    and so is what only the target's reference year band brought, told here
    from the scored rows so that it never depends on classify (news.band_ids).
    `body_type_filled`, listings stored before whose body type this batch
    filled in or corrected, are old news for the searches without a model:
    their batches couldn't match them, and a body-type backfill
    (tools.backfill_body_type) or a better reading is not a new listing."""
    backfill_ids, body_type_filled = frozenset(backfill_ids), frozenset(body_type_filled)
    body_target = target.get("body_type") is not None
    scorer = await Scorer.create()
    await scorer.prepare(listing_ids)
    max_age_days = int(await db.get_config("recommended_max_age_days", RECOMMENDED_MAX_AGE_DAYS))
    backfill_ids |= news.band_ids(target, (scorer.rows[lid] for lid in listing_ids if lid in scorer.rows),
                                  max_age_days=max_age_days)
    staged: list[_Staged] = []
    for alert in await db.alerts_for_target(target["source"], target.get("make"), target.get("model"),
                                            telegram_only=False,
                                            inventory=(target.get("query") or {}).get("inventory") is True,
                                            body_type=target.get("body_type")):
        try:
            staged.append(await _stage(alert, listing_ids, scorer))
        except Exception:
            await log_error("match", f"profile:{alert['id']}", traceback.format_exc())
    candidates: list[MatchCandidate] = []
    for s in staged:
        without_model = model_less(s.alert["profile"].get("filters") or {})
        try:
            candidates += await match_alert(
                s, scorer, first_run=first_run, max_age_days=max_age_days,
                foreign_first_run=without_model and not body_target, held_first_run=held_first_run,
                backfill_ids=backfill_ids | body_type_filled if without_model else backfill_ids)
        except Exception:
            await log_error("match", f"profile:{s.alert['id']}", traceback.format_exc())
    # Matches are stored and re-scored: price drops carry the new score.
    try:
        await notifier.on_matches(candidates, scorer.rows)
        # A first run silences new listings. One of a target that ran before
        # (back after a day inactive, a new coverage or publication policy)
        # still tells the price drops of what it had read.
        if not first_run or target.get("last_run_at") is not None:
            await notifier.on_listing_events(events)
    except Exception:
        await log_error("notify", f"target:{target.get('id')}", traceback.format_exc())
    await notifier.deliver()
    try:
        await count_after_expiry(target, listing_ids, scorer, first_run=first_run, max_age_days=max_age_days,
                                 exclude=backfill_ids)
    except Exception:
        await log_error("count_after_expiry", f"target:{target.get('id')}", traceback.format_exc())


def batch_handler(notifier: Notifier) -> crawl.BatchHandler:
    async def handle(run: crawl.TargetRun) -> None:
        listing_ids = list(dict.fromkeys(run.result.ids.values()))
        if listing_ids:
            await process_batch(notifier, run.target, listing_ids, first_run=run.first_run,
                                events=run.result.events, backfill_ids=run.backfill_ids,
                                body_type_filled=run.result.body_type_filled,
                                held_first_run=run.first_run and run.empty_runs > 0)
    return handle


async def _counting_profiles() -> list[dict] | None:
    """The searches 2.5 counts. None if reading them fails: active searches
    still crawl, and the count-only targets stay as they are (crawl.sync_targets)."""
    try:
        return await db.counting_profiles()
    except Exception:
        await log_error("count_after_expiry", "counting_profiles", traceback.format_exc())
        return None


async def tick(notifier: Notifier, lanes: crawl.Lanes, stop: asyncio.Event | None = None,
               on_health: crawl.HealthHandler | None = None) -> None:
    """Sync targets, bootstrap new searches and start the idle sources' lanes.
    It never waits for a crawl: the next tick comes TICK_INTERVAL_SECONDS
    later whatever a source is doing."""
    await crawl.sync_targets(await db.enabled_profiles(), await _counting_profiles())
    await rematch.run_pending()
    started = await lanes.start_due(batch_handler(notifier), jitter_seconds=CRAWL_JITTER_SECONDS, stop=stop,
                                    on_health=on_health)
    if started:
        log.info("crawl tick: lanes started: %s; running: %s", ", ".join(started),
                 ", ".join(sorted(lanes.running())))


# When the loop last came round (time.monotonic()), for loop_stale.
_last_round: float = time.monotonic()


def loop_stale(max_age_seconds: float) -> bool:
    """Whether the crawl loop hasn't come round for `max_age_seconds`: a tick
    stuck in the database or in a bootstrap. The heartbeat stops then, so the
    watchdog alerts (main.py)."""
    return time.monotonic() - _last_round > max_age_seconds


async def run_loop(notifier: Notifier, stop_event: asyncio.Event,
                   on_health: crawl.HealthHandler | None = None) -> None:
    global _last_round
    lanes = crawl.Lanes()
    try:
        while not stop_event.is_set():
            try:
                await tick(notifier, lanes, stop_event, on_health)
            except Exception:
                log.error("scheduler tick failed: %s", traceback.format_exc())
            _last_round = time.monotonic()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TICK_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    finally:
        await lanes.close()
