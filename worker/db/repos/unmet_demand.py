"""admin_unmet_demand and admin_unmet_demand_run: the dashboard's precomputed rows (pipeline/unmet_demand.py)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg.types.json import Jsonb

from db.pool import connection

_COLUMNS = ("search_profile_id", "user_id", "make", "model", "zone_label", "result_count", "market",
            "market_in_zone", "relaxed_zone", "relaxed_price", "relaxed_trim", "relaxed_year", "cause")


async def last_run_at() -> datetime | None:
    async with connection() as cx:
        row = await (await cx.execute("SELECT computed_at FROM admin_unmet_demand_run")).fetchone()
    return row["computed_at"] if row else None


async def upsert(rows: list[dict[str, Any]], computed_at: datetime) -> None:
    """Insert or replace these searches' rows, stamped `computed_at`."""
    if not rows:
        return
    async with connection() as cx:
        async with cx.cursor() as cur:
            await cur.executemany(
                "INSERT INTO admin_unmet_demand (" + ", ".join(_COLUMNS) + ", computed_at) VALUES ("
                + ", ".join(f"%({c})s" for c in _COLUMNS) + ", %(computed_at)s) "
                "ON CONFLICT (search_profile_id) DO UPDATE SET "
                + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COLUMNS[1:]) + ", computed_at = EXCLUDED.computed_at",
                [{**r, "computed_at": computed_at} for r in rows])


async def delete_older(computed_at: datetime) -> int:
    """Rows this run did not refresh: the search no longer qualifies."""
    async with connection() as cx:
        cur = await cx.execute("DELETE FROM admin_unmet_demand WHERE computed_at < %s", (computed_at,))
        return cur.rowcount


async def cap_hidden() -> list[dict[str, Any]]:
    """What the free plan's cap hides: one row per level and a last one with a NULL level (the totals)."""
    async with connection() as cx:
        return await (await cx.execute("SELECT level, matches, accounts FROM public.admin_cap_hidden()")).fetchall()


async def save_run(*, computed_at: datetime, duration_ms: int, searches: int, skipped_model_less: int,
                   max_results: int, min_age_hours: float, cap_enforced: bool,
                   hidden_by_level: dict[str, int], hidden_accounts: int) -> None:
    async with connection() as cx:
        await cx.execute(
            "INSERT INTO admin_unmet_demand_run (singleton, computed_at, duration_ms, searches, skipped_model_less, "
            "  max_results, min_age_hours, cap_enforced, hidden_by_level, hidden_accounts) "
            "VALUES (true, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (singleton) DO UPDATE SET computed_at = EXCLUDED.computed_at, "
            "  duration_ms = EXCLUDED.duration_ms, searches = EXCLUDED.searches, "
            "  skipped_model_less = EXCLUDED.skipped_model_less, max_results = EXCLUDED.max_results, "
            "  min_age_hours = EXCLUDED.min_age_hours, cap_enforced = EXCLUDED.cap_enforced, "
            "  hidden_by_level = EXCLUDED.hidden_by_level, hidden_accounts = EXCLUDED.hidden_accounts",
            (computed_at, duration_ms, searches, skipped_model_less, max_results, min_age_hours, cap_enforced,
             Jsonb(hidden_by_level), hidden_accounts))
