"""Re-scoring existing matches (sección 6.1).

* After enrichment: transmission or version may go from unknown to a value,
  and the description feeds the red flags (`rescore_listings`).
* Periodic: the matches of active listings seen in the last 14 days, because
  the comparables' median moves and a listing may stop fitting its search
  (`nightly_loop`, every app_config.rescore.every_hours from rescore.hour ART).
* When SCORING_VERSION changes, every match (`rescore_outdated`, at startup).

Before the startup pass and the one at rescore.hour, the seller
classification (F-02, pipeline/seller_classification.py) refreshes
listings.seller_listing_count and dealer_inferred («posible agencia») and
re-scores the matches of the listings whose inference flipped, so a rescore
(and the one of a SCORING_VERSION bump) sees today's counts. A failure there is
logged and the rescore runs anyway.

The pass at rescore.hour also runs the retention (pipeline/retention.py).

A match whose listing no longer passes the search (a detail page placed it
outside the radius, the price went over the cap...) is deleted: the user
sees only listings that fit. The row is also the bot's "already seen"
record, so if the listing fits again later it is a new match and alerts.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import db
from db.repos import matches as matches_repo
from db.repos.profiles import profiles_by_ids
from db.repos.runs import log_error
from intelligence.config import DEFAULT_RESCORE, SCORING_VERSION
from pipeline.retention import purge_raw_pages, purge_stale_listings
from pipeline.scoring import Scorer
from pipeline.seller_classification import classify_sellers


log = logging.getLogger("rescore")

# America/Argentina/Buenos_Aires (no DST since 2009).
_AR = timezone(timedelta(hours=-3))


async def rescore(queue: list[dict[str, Any]], scorer: Scorer | None = None) -> int:
    """Re-score (search_profile_id, listing_id) pairs. Returns rows updated."""
    if not queue:
        return 0
    scorer = scorer or await Scorer.create()
    await scorer.prepare(q["listing_id"] for q in queue)
    profiles = {a["id"]: a["profile"] for a in await profiles_by_ids(
        list({q["search_profile_id"] for q in queue}))}
    by_profile: dict[int, list[tuple[int, dict]]] = {}
    gone: dict[int, list[int]] = {}
    for q in queue:
        profile = profiles.get(q["search_profile_id"])
        if profile is None or q["listing_id"] not in scorer.rows:
            continue
        ev = scorer.evaluate(q["listing_id"], profile)
        if ev is None:
            gone.setdefault(q["search_profile_id"], []).append(q["listing_id"])
        else:
            by_profile.setdefault(q["search_profile_id"], []).append((q["listing_id"], ev.row()))
    updated = 0
    for profile_id, rows in by_profile.items():
        try:
            async with db.connection() as cx:
                await matches_repo.upsert_scored(cx, profile_id, rows, backfill=True)
            updated += len(rows)
        except Exception:
            await log_error("rescore", f"profile:{profile_id}", traceback.format_exc())
    for profile_id, listing_ids in gone.items():
        try:
            async with db.connection() as cx:
                n = await matches_repo.delete_matches(cx, profile_id, listing_ids)
            if n:
                log.info("profile %s: %d matches no longer fit, deleted", profile_id, n)
        except Exception:
            await log_error("rescore", f"profile:{profile_id}:delete", traceback.format_exc())
    return updated


async def rescore_listings(listing_ids: Iterable[int]) -> int:
    return await rescore(await matches_repo.matches_of_listings(listing_ids))


async def rescore_recent(*, outdated_only: bool = False) -> int:
    cfg = {**DEFAULT_RESCORE, **(await db.get_config("rescore", {}) or {})}
    queue = await matches_repo.rescore_queue(days=int(cfg["days"]), scoring_version=SCORING_VERSION,
                                             outdated_only=outdated_only)
    n = await rescore(queue)
    log.info("re-score (%s): %d/%d matches", "outdated" if outdated_only else "nightly", n, len(queue))
    return n


async def rescore_outdated() -> int:
    return await rescore_recent(outdated_only=True)


def seconds_until(hour: str, now: datetime) -> float:
    """Seconds from `now` to the next `hour` ("HH:MM", ART)."""
    hh, mm = (int(x) for x in hour.split(":"))
    local = now.astimezone(_AR)
    nxt = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if nxt <= local:
        nxt += timedelta(days=1)
    return (nxt - local).total_seconds()


def next_slot(hour: str, every_hours: int, now: datetime) -> tuple[float, bool]:
    """Seconds to the next re-score and whether it is the one at `hour`
    (the one that also runs the retention). Slots are `hour` + k * every_hours,
    wrapped in the day; an every_hours that does not divide 24 counts as 24."""
    every = every_hours if 0 < every_hours < 24 and 24 % every_hours == 0 else 24
    hh, mm = hour.split(":")
    slots = [f"{(int(hh) + k * every) % 24:02d}:{mm}" for k in range(24 // every)]
    wait, slot = min((seconds_until(t, now), t) for t in slots)
    return wait, slot == slots[0]


async def nightly_loop(stop: asyncio.Event) -> None:
    """Re-score matches every `every_hours` (anchored at `hour`); at `hour`, also
    purge stale listings. Once at startup, whatever an older SCORING_VERSION
    scored. The seller classification runs before both (F-02)."""
    try:
        await classify_sellers("startup")
    except Exception:
        await log_error("seller_classification", "startup", traceback.format_exc())
    try:
        await rescore_outdated()
    except Exception:
        await log_error("rescore", "outdated", traceback.format_exc())
    while not stop.is_set():
        cfg = {**DEFAULT_RESCORE, **(await db.get_config("rescore", {}) or {})}
        wait, is_anchor = next_slot(str(cfg["hour"]), int(cfg["every_hours"]), datetime.now(_AR))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
            return
        except asyncio.TimeoutError:
            pass
        if is_anchor:
            try:
                await classify_sellers("nightly")
            except Exception:
                await log_error("seller_classification", "nightly", traceback.format_exc())
        try:
            await rescore_recent()
        except Exception:
            await log_error("rescore", "nightly", traceback.format_exc())
        if not is_anchor:
            continue
        try:
            await purge_stale_listings()
            await purge_raw_pages()
        except Exception:
            await log_error("retention", "nightly", traceback.format_exc())
