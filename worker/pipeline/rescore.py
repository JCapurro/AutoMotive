"""Re-scoring existing matches (sección 6.1).

* After enrichment: transmission or version may go from unknown to a value,
  and the description feeds the red flags (`rescore_listings`).
* Nightly: the matches of active listings seen in the last 14 days, because
  the comparables' median moves (`nightly_loop`, at app_config.rescore.hour ART).
* When SCORING_VERSION changes, every match (`rescore_outdated`, at startup).

The nightly pass also runs the retention (pipeline/retention.py).

A match that no longer passes its hard filters keeps its last score: the row
is also the bot's "already seen" record, and deleting it would alert again.
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
    for q in queue:
        profile = profiles.get(q["search_profile_id"])
        ev = scorer.evaluate(q["listing_id"], profile) if profile else None
        if ev is not None:
            by_profile.setdefault(q["search_profile_id"], []).append((q["listing_id"], ev.row()))
    updated = 0
    for profile_id, rows in by_profile.items():
        try:
            async with db.connection() as cx:
                await matches_repo.upsert_scored(cx, profile_id, rows, backfill=True)
            updated += len(rows)
        except Exception:
            await log_error("rescore", f"profile:{profile_id}", traceback.format_exc())
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


async def nightly_loop(stop: asyncio.Event) -> None:
    """Re-score matches once a night, then purge stale listings; also, once at
    startup, whatever an older SCORING_VERSION scored."""
    try:
        await rescore_outdated()
    except Exception:
        await log_error("rescore", "outdated", traceback.format_exc())
    while not stop.is_set():
        cfg = {**DEFAULT_RESCORE, **(await db.get_config("rescore", {}) or {})}
        wait = seconds_until(str(cfg["hour"]), datetime.now(_AR))
        try:
            await asyncio.wait_for(stop.wait(), timeout=wait)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await rescore_recent()
        except Exception:
            await log_error("rescore", "nightly", traceback.format_exc())
        try:
            await purge_stale_listings()
            await purge_raw_pages()
        except Exception:
            await log_error("retention", "nightly", traceback.format_exc())
