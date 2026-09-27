"""Watchlist refresher (sección 5.6, §30).

A listing missing from the search results doesn't prove it's gone: only the
first 96 results, newest first, are read. So listings a user saved or follows
(interested, contacted, visit scheduled) are checked once a day through
fetch_detail():

  * 404, paused or sold → status 'gone' and a listing_gone event;
  * otherwise the page is ingested with the change detection of sección 5.3
    (snapshots, listing_updated, price_drop);
  * a listing published more than app_config.watchlist_stale_days ago yields
    an informational listing_stale event ("lleva X días").

The daily cadence lives in listings.detail_checked_at, so a restart of the
worker doesn't check the same listings twice in a day.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

import db
from db.repos import listings as repo
from pipeline.enrich import drain, refresh_listing, source_intervals
from pipeline.ingest import IngestResult, ListingEvent


log = logging.getLogger("watchlist")


def stale_days(row: dict[str, Any], now: datetime | None = None) -> int:
    """Days since publication (or since first seen, when the source hides the date)."""
    since = row.get("published_at") or row["first_seen_at"]
    return ((now or datetime.now(timezone.utc)) - since).days


async def refresh_watchlist(stop: asyncio.Event | None = None) -> IngestResult:
    rows = await repo.watchlist_queue()
    intervals = await source_intervals()
    rows = [r for r in rows if r["source"] in intervals]
    result = await drain(rows, lambda r: refresh_listing(r, stage="watchlist"),
                         intervals=intervals, stop=stop)

    threshold = int(await db.get_config("watchlist_stale_days", 30))
    gone = {e.listing_id for e in result.events if e.kind == "listing_gone"}
    for r in rows:
        if r["id"] not in gone and (days := stale_days(r)) >= threshold:
            result.events.append(ListingEvent("listing_stale", r["id"], r["source"],
                                              r["external_id"], changes=(f"{days}d",)))
    if rows:
        log.info("watchlist: %d checked, %d gone, %d updated, %d stale", len(rows), len(gone),
                 result.updated, sum(e.kind == "listing_stale" for e in result.events))
    return result
