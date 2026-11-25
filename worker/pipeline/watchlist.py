"""Watchlist refresher (sección 5.6, §30).

A listing missing from the search results doesn't prove it's gone: only the
first 96 results, newest first, are read. So listings a user saved or follows
(interested, contacted, visit scheduled) are checked once a day through
fetch_detail():

  * 404, paused or sold → status 'gone' and a listing_gone event;
  * otherwise the page is ingested with the change detection of sección 5.3
    (snapshots, listing_updated, price_drop) and its matches re-scored;
  * a listing published more than app_config.watchlist_stale_days ago yields
    an informational listing_stale event ("lleva X días").

A pass of its own, every config.MATCHED_TICK_SECONDS (15 min), re-checks the
listings with a match (above 'low') in an enabled search that the crawl
stopped seeing for app_config.watchlist_matched.unseen_hours
(docs/PLAN_DELISTADOS.md, B): a price drop past the pages a search reads, or
the end of the ad, reaches the users that match it, and the panel stops
showing a car that is over. per_source is one number for all sources or a
map ({"mercadolibre": 150, "facebook": 5, "default": 40}); what the users
have most in view goes first, and a car found alive again and again while
the searches don't show it is spaced out (12 h, 24 h, 48 h, then 72 h). Only
the saved or followed ones yield listing_stale. The two passes never read
detail pages at the same time.

The cadence lives in listings.detail_checked_at, so a restart of the
worker doesn't check the same listings again.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Mapping

import db
from db.repos import listings as repo
from pipeline.enrich import drain, refresh_listing, rescore_changed, source_intervals
from pipeline.ingest import IngestResult, ListingEvent


log = logging.getLogger("watchlist")


def stale_days(row: dict[str, Any], now: datetime | None = None) -> int:
    """Days since publication (or since first seen, when the source hides the date)."""
    since = row.get("published_at") or row["first_seen_at"]
    return ((now or datetime.now(timezone.utc)) - since).days


# Without app_config.watchlist_matched: 5 a pass per source, every 15 min,
# the 20 an hour the hourly pass read before its own tick.
DEFAULT_PER_SOURCE = 5
# The saved/followed pass and the matched one share the sources' patience.
_lane = asyncio.Lock()


def per_source_limits(value: Any) -> dict[str, int]:
    """app_config.watchlist_matched.per_source as {source: n, 'default': n}:
    one number (the old shape) is every source's; a map by source keeps its
    'default', or DEFAULT_PER_SOURCE. A value that isn't a count falls back."""
    def count(v: Any, fallback: int) -> int:
        try:
            return max(0, int(v))
        except (TypeError, ValueError):
            return fallback
    if isinstance(value, Mapping):
        limits = {str(k): count(v, DEFAULT_PER_SOURCE) for k, v in value.items()}
        limits.setdefault("default", DEFAULT_PER_SOURCE)
        return limits
    return {"default": count(value, DEFAULT_PER_SOURCE) if value is not None else DEFAULT_PER_SOURCE}


async def matched_queue() -> list[dict[str, Any]]:
    cfg = await db.get_config("watchlist_matched", {}) or {}
    if not cfg.get("enabled", True):
        return []
    band = cfg.get("prefer_unseen_hours") or [24, 120]
    return await repo.matched_recheck_queue(
        unseen_hours=int(cfg.get("unseen_hours", 6)), recheck_hours=int(cfg.get("recheck_hours", 12)),
        max_age_days=int(cfg.get("max_age_days", 60)), per_source=per_source_limits(cfg.get("per_source")),
        backoff_max_hours=int(cfg.get("backoff_max_hours", 72)), prefer_unseen=(int(band[0]), int(band[1])))


async def refresh_watchlist(stop: asyncio.Event | None = None) -> IngestResult:
    """Saved or followed listings, once a day (the hourly tick)."""
    async with _lane:
        rows = await repo.watchlist_queue()
        intervals = await source_intervals()
        rows = [r for r in rows if r["source"] in intervals]
        result = await drain(rows, lambda r: refresh_listing(r, stage="watchlist"),
                             intervals=intervals, stop=stop)

    await rescore_changed(result)

    threshold = int(await db.get_config("watchlist_stale_days", 30))
    gone = {e.listing_id for e in result.events if e.kind == "listing_gone"}
    for r in rows:
        if r["id"] not in gone and (days := stale_days(r)) >= threshold:
            result.events.append(ListingEvent("listing_stale", r["id"], r["source"],
                                              r["external_id"], changes=(f"{days}d",)))
    if rows:
        log.info("watchlist: %d saved/followed checked, %d gone, %d updated, %d stale",
                 len(rows), len(gone), result.updated, sum(e.kind == "listing_stale" for e in result.events))
    return result


async def refresh_matched(stop: asyncio.Event | None = None) -> IngestResult:
    """Matched listings the crawl stopped seeing (the 15-minute tick)."""
    async with _lane:
        intervals = await source_intervals()
        rows = [r for r in await matched_queue() if r["source"] in intervals]
        result = await drain(rows, lambda r: refresh_listing(r, stage="watchlist"),
                             intervals=intervals, stop=stop)
    await rescore_changed(result)
    if rows:
        by_source: dict[str, int] = {}
        for r in rows:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        log.info("watchlist matched: %d checked (%s), %d gone, %d updated", len(rows),
                 ", ".join(f"{s} {n}" for s, n in sorted(by_source.items())),
                 sum(e.kind == "listing_gone" for e in result.events), result.updated)
    return result
