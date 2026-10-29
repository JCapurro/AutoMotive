"""Retention (F7, punto 10; sección 14): once a night, active listings not seen
for app_config.retention.listing_days (180) that no user touched are deleted
with their snapshots and matches (SQL: public.purge_stale_listings). Ended
listings and their price history stay as historical references. Stored detail
pages (raw_pages) go after app_config.retention.raw_page_days (90), and the
weekly market stats after app_config.retention.market_stats_weeks (26).

Keeps the database small — the free tier of a hosted Supabase is 500 MB — and
never loses what the metrics or a user's history point at.
"""
from __future__ import annotations

import logging

import db
from db.repos import raw_pages

log = logging.getLogger("retention")


async def purge_stale_listings() -> int:
    async with db.connection() as cx:
        row = await (await cx.execute("SELECT public.purge_stale_listings() AS n")).fetchone()
    deleted = int(row["n"])
    if deleted:
        log.info("retención: %d publicaciones borradas", deleted)
    return deleted


async def purge_raw_pages() -> int:
    """Stored detail pages (raw_pages) older than app_config.retention.raw_page_days (90)."""
    cfg = await db.get_config("retention", {}) or {}
    deleted = await raw_pages.purge_older_than(int(cfg.get("raw_page_days", 90)))
    if deleted:
        log.info("retención: %d páginas guardadas borradas", deleted)
    return deleted


async def purge_market_stats() -> int:
    """market_stats weeks (and their runs) older than
    app_config.retention.market_stats_weeks (26). Called at the end of every
    market_stats write run (pipeline/market_stats.py), not from nightly_loop."""
    cfg = await db.get_config("retention", {}) or {}
    weeks = int(cfg.get("market_stats_weeks", 26))
    cutoff = "(now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date - %s::int * 7"
    async with db.connection() as cx:
        deleted = (await cx.execute(f"DELETE FROM market_stats WHERE week_start < {cutoff}", (weeks,))).rowcount
        runs = (await cx.execute(f"DELETE FROM market_stats_runs WHERE week_start < {cutoff}", (weeks,))).rowcount
    if deleted or runs:
        log.info("retención: %d filas de market_stats y %d corridas borradas", deleted, runs)
    return deleted
