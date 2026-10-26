"""expired_search_matches: what 2.5 counts (docs/MAILS_DE_PLAN.md).

The listings that matched a search after its access ended, scored like a
match by pipeline/scheduler.py. Only the count email reads them
(public.claim_lifecycle_emails); the web never sees them and nothing is
notified, so they are not matches.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from db.pool import connection

# Rows are useless once their 3 weeks of emails are over; a margin for checks.
KEEP_DAYS = 60


async def store(rows: Iterable[tuple[int, int, datetime, str, int | None, float | None]]) -> None:
    """Record (search_profile_id, listing_id, access_ended_at, level, score,
    diff_pct) rows; one already counted keeps its first sighting and takes the
    latest evaluation. score and diff_pct (% below comparables) pick the car
    the email shows (public.missed_car)."""
    rows = list(rows)
    if not rows:
        return
    async with connection() as cx:
        async with cx.cursor() as cur:
            await cur.executemany(
                "INSERT INTO expired_search_matches "
                "(search_profile_id, listing_id, access_ended_at, level, score, diff_pct) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (search_profile_id, listing_id) DO UPDATE "
                "SET level = excluded.level, score = excluded.score, diff_pct = excluded.diff_pct "
                " WHERE expired_search_matches.access_ended_at = excluded.access_ended_at", rows)


async def prune() -> int:
    """Drop the rows of ends older than KEEP_DAYS. Returns how many."""
    async with connection() as cx:
        cur = await cx.execute(
            "DELETE FROM expired_search_matches WHERE access_ended_at < now() - make_interval(days => %s)",
            (KEEP_DAYS,))
        return cur.rowcount
