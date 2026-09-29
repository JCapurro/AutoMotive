"""Retention (F7, punto 10; sección 14): once a night, listings not seen for
app_config.retention.listing_days (180) that no user touched are deleted with
their snapshots and matches (SQL: public.purge_stale_listings). Stored detail
pages (raw_pages) go after app_config.retention.raw_page_days (90).

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
