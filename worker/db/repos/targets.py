"""crawl_targets and the source cadence they run on (sección 5.1)."""
from __future__ import annotations

from typing import Any, Iterable

from psycopg.types.json import Jsonb

from db.pool import connection


async def enabled_sources() -> dict[str, dict[str, Any]]:
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT id, crawl_interval_seconds, detail_interval_seconds, priority "
            "  FROM sources WHERE enabled ORDER BY priority, id")).fetchall()
    return {r["id"]: r for r in rows}


async def sync_targets(specs: Iterable[Any]) -> None:
    """Make crawl_targets mirror `specs` (pipeline.crawl.TargetSpec): upsert the
    wanted ones (a reactivated target keeps first_run_done) and deactivate the rest."""
    specs = list(specs)
    async with connection() as cx:
        await cx.execute("CREATE TEMP TABLE wanted (source text, make text, model text, query jsonb) "
                         "ON COMMIT DROP")
        if specs:
            async with cx.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO wanted VALUES (%s, %s, %s, %s)",
                    [(s.source, s.make, s.model, Jsonb(s.query)) for s in specs])
        await cx.execute(
            "INSERT INTO crawl_targets (source, make, model, query, active) "
            "SELECT source, make, model, query, true FROM wanted "
            "ON CONFLICT (source, make, model) DO UPDATE SET query = excluded.query, active = true "
            " WHERE crawl_targets.query IS DISTINCT FROM excluded.query OR NOT crawl_targets.active")
        await cx.execute(
            "UPDATE crawl_targets t SET active = false WHERE active AND NOT EXISTS ("
            "  SELECT 1 FROM wanted w WHERE w.source = t.source "
            "     AND w.make IS NOT DISTINCT FROM t.make AND w.model IS NOT DISTINCT FROM t.model)")


async def due_targets() -> list[dict[str, Any]]:
    """Active targets of enabled sources whose next_run_at has come (or never ran)."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT t.id, t.source, t.make, t.model, t.query, t.first_run_done, t.last_run_at, "
            "       s.crawl_interval_seconds "
            "  FROM crawl_targets t JOIN sources s ON s.id = t.source "
            " WHERE t.active AND s.enabled AND (t.next_run_at IS NULL OR t.next_run_at <= now()) "
            " ORDER BY s.priority, t.next_run_at NULLS FIRST, t.id")).fetchall()


async def finish_target(target_id: int, *, ok: bool, retry_seconds: int) -> None:
    """next_run_at = now + the source's interval (sección 5.1). A failed run
    retries after `retry_seconds` and doesn't count as the first run."""
    async with connection() as cx:
        if ok:
            await cx.execute(
                "UPDATE crawl_targets t SET last_run_at = now(), first_run_done = true, "
                "  next_run_at = now() + make_interval(secs => s.crawl_interval_seconds) "
                "  FROM sources s WHERE s.id = t.source AND t.id = %s", (target_id,))
        else:
            await cx.execute(
                "UPDATE crawl_targets SET next_run_at = now() + make_interval(secs => %s) "
                " WHERE id = %s", (retry_seconds, target_id))
