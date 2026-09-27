"""Enrichment of listings with a match (sección 5.5).

Cards don't carry description, version, transmission, seller type or every
image; fetch_detail() does. It is only worth its cost (and the sources'
patience) for listings that matched at least one profile and were never
enriched. Each source has its own queue, rate-limited by
sources.detail_interval_seconds; sources drain in parallel.

The re-evaluation of the match after enrichment (transmission or version going
from unknown to a value, red flags) belongs to F2's matching: the
listing_updated events returned here are its input.
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, Awaitable, Callable

import db
from collectors import REGISTRY
from collectors._loop import run_collector
from db.repos import listings as repo
from db.repos.runs import log_error
from db.repos.targets import enabled_sources
from normalization.listing import Target
from pipeline.ingest import IngestResult, ListingEvent, ingest


log = logging.getLogger("enrich")


async def refresh_listing(row: dict[str, Any], *, stage: str) -> IngestResult:
    """fetch_detail() one stored listing and ingest what it says.

    A page that proves the ad is over marks it 'gone' (event listing_gone);
    a fetch that fails is recorded in pipeline_errors and retried later.
    """
    result = IngestResult()
    scraper = REGISTRY[row["source"]]()
    try:
        detail = await run_collector(scraper.fetch_detail(row["url"]))
    except Exception:
        await log_error(stage, f"listing:{row['id']}", traceback.format_exc())
        await repo.mark_detail_checked([row["id"]])
        return result

    if detail.gone:
        async with db.connection() as cx:
            was_active = await repo.mark_gone(cx, row["id"])
        if was_active:
            result.events.append(ListingEvent("listing_gone", row["id"], row["source"],
                                              row["external_id"], changes=(detail.gone_reason or "",)))
        return result

    item = detail.listing
    # The stored identity wins over whatever the page says its id is.
    item.source, item.listing_id = row["source"], row["external_id"]
    item.url = row["url"]
    try:
        return await ingest([item], target=Target(row.get("make"), row.get("model")), detail=True)
    except Exception:
        await log_error(stage, f"listing:{row['id']}", traceback.format_exc())
        await repo.mark_detail_checked([row["id"]])
        return result


Refresher = Callable[[dict[str, Any]], Awaitable[IngestResult]]


async def drain(rows: list[dict[str, Any]], refresh: Refresher, *,
                intervals: dict[str, float], stop: asyncio.Event | None = None) -> IngestResult:
    """Run `refresh` over rows: sources in parallel, each source at most one
    detail page every `intervals[source]` seconds."""
    by_source: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r["source"] in REGISTRY:
            by_source.setdefault(r["source"], []).append(r)

    async def one_source(source: str, queue: list[dict[str, Any]]) -> IngestResult:
        out = IngestResult()
        for i, row in enumerate(queue):
            if stop is not None and stop.is_set():
                break
            if i and intervals.get(source, 0) > 0:
                await asyncio.sleep(intervals[source])
            out.extend(await refresh(row))
        return out

    total = IngestResult()
    for part in await asyncio.gather(*(one_source(s, q) for s, q in by_source.items())):
        total.extend(part)
    return total


async def source_intervals() -> dict[str, float]:
    return {s: float(r["detail_interval_seconds"]) for s, r in (await enabled_sources()).items()}


async def enrich_pass(stop: asyncio.Event | None = None) -> IngestResult:
    cfg = await db.get_config("enrichment", {}) or {}
    rows = await repo.enrichment_queue(per_source=int(cfg.get("batch_per_source", 20)),
                                       max_age_days=int(cfg.get("max_age_days", 30)))
    intervals = await source_intervals()
    rows = [r for r in rows if r["source"] in intervals]     # disabled sources wait
    result = await drain(rows, lambda r: refresh_listing(r, stage="enrich"),
                         intervals=intervals, stop=stop)
    if rows:
        log.info("enrichment: %d listings, %d updated, %d events",
                 len(rows), result.updated, len(result.events))
    return result
