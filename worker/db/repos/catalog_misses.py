"""catalog_misses: what people ask the assisted mode for that vehicle_catalog
doesn't have, counted by normalized text (/admin/catalog-misses)."""
from __future__ import annotations

from collections.abc import Iterable

from psycopg import AsyncConnection


async def record(cx: AsyncConnection, misses: Iterable[tuple[str, str | None]], job_id: int | None) -> None:
    """One more ask for each (said, make); the make keeps the last one recognized."""
    for said, make in misses:
        await cx.execute(
            "INSERT INTO catalog_misses (said, make, last_llm_job_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (said) DO UPDATE SET count = catalog_misses.count + 1, last_seen_at = now(), "
            "       make = coalesce(excluded.make, catalog_misses.make), "
            "       last_llm_job_id = excluded.last_llm_job_id",
            (said, make, job_id))
