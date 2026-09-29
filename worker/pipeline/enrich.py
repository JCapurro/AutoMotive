"""Enrichment of listings with a match (sección 5.5).

Cards don't carry description, version, transmission, seller type or every
image; fetch_detail() does. It is only worth its cost (and the sources'
patience) for listings that matched at least one profile and were never
enriched, and for those whose published price looks like a down payment:
only their description can give the total that would let them match (the
next crawl of their target matches them). Each source has its own queue,
rate-limited by sources.detail_interval_seconds; sources drain in parallel.

Each detail page is kept in raw_pages before it's parsed (tools/reprocess.py
re-reads them). The description's facts (normalization/description_facts.py)
come from rules; when the rules can't settle them (several prices, several
km) and app_config.description_facts.llm is on, the LLM reads the text, at
most llm_daily_cap times a day.

After a pass the matches of the listings that changed are re-scored
(pipeline/rescore.py): transmission or version may go from unknown to a
value, and the description feeds the red flags (sección 5.5).
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import config
import db
from collectors import REGISTRY, Listing, ListingDetail
from collectors._loop import run_collector
from db.repos import listings as repo
from db.repos import raw_pages
from db.repos.runs import log_error
from db.repos.targets import enabled_sources
from llm.provider import LLMProvider, build_provider
from normalization.description_facts import from_llm, parse as parse_facts
from normalization.listing import Target
from pipeline.ingest import IngestResult, ListingEvent, ingest
from pipeline.rescore import rescore_listings


log = logging.getLogger("enrich")


class DescriptionLLM:
    """The LLM for the descriptions the rules can't settle."""

    def __init__(self, provider: LLMProvider, *, daily_cap: int) -> None:
        self.provider = provider
        self.daily_cap = daily_cap

    @classmethod
    async def create(cls) -> "DescriptionLLM | None":
        """None when app_config.description_facts.llm is off or no provider is configured."""
        cfg = await db.get_config("description_facts", {}) or {}
        if not cfg.get("llm", False) or int(cfg.get("llm_daily_cap", 50)) <= 0:
            return None
        try:
            provider = build_provider()
        except Exception:
            log.warning("description facts: no LLM provider", exc_info=True)
            return None
        return cls(provider, daily_cap=int(cfg.get("llm_daily_cap", 50)))

    async def refine(self, listing_id: int, item: Listing) -> None:
        """Put the LLM's reading in item.extra["description_facts"] when the
        rules find the text ambiguous. Any failure leaves the rules' reading."""
        if not item.descripcion:
            return
        rules = parse_facts(item.descripcion, item.titulo, now_year=datetime.now(timezone.utc).year)
        if rules is None or not rules.ambiguous:
            return
        stored = await repo.stored_description(listing_id)
        if stored and stored.get("description") == item.descripcion \
                and (stored.get("description_facts") or {}).get("source") == "llm":
            item.extra["description_facts"] = stored["description_facts"]      # already read
            return
        if await repo.llm_facts_last_day() >= self.daily_cap:
            return
        try:
            answer = await asyncio.wait_for(
                self.provider.extract_listing_facts(item.titulo, item.descripcion),
                timeout=config.LLM_TIMEOUT_SECONDS + 5)
        except Exception as e:
            log.info("description facts: LLM failed for listing %s: %s", listing_id, type(e).__name__)
            return
        facts = from_llm(answer, rules, llm_at=datetime.now(timezone.utc).isoformat())
        item.extra["description_facts"] = facts.to_json()


async def refresh_listing(row: dict[str, Any], *, stage: str,
                          llm: DescriptionLLM | None = None) -> IngestResult:
    """Fetch one stored listing's detail page, keep it and ingest what it says.

    A page that proves the ad is over marks it 'gone' (event listing_gone);
    a fetch or a parse that fails is recorded in pipeline_errors and retried later.
    """
    scraper = REGISTRY[row["source"]]()
    try:
        page = await run_collector(scraper.fetch_detail_page(row["url"]))
    except Exception:
        await log_error(stage, f"listing:{row['id']}", traceback.format_exc())
        await repo.mark_detail_checked([row["id"]])
        return IngestResult()
    try:
        await raw_pages.save(row["id"], url=page.url, status=page.status,
                             parser_version=scraper.DETAIL_PARSER_VERSION, html=scraper.slim_page(page))
    except Exception:
        log.warning("raw page of listing %s not kept", row["id"], exc_info=True)
    try:
        detail = scraper.parse_detail(page.html, row["url"], page.status)
    except Exception:
        await log_error(stage, f"listing:{row['id']}", traceback.format_exc())
        await repo.mark_detail_checked([row["id"]])
        return IngestResult()
    return await ingest_detail(row, detail, stage=stage, llm=llm)


async def ingest_detail(row: dict[str, Any], detail: ListingDetail, *, stage: str,
                        llm: DescriptionLLM | None = None, seen: bool = True) -> IngestResult:
    """What a parsed detail page says, into the stored listing. `seen=False`
    (tools/reprocess.py --raw): a stored page read again neither marks the
    listing seen nor gone."""
    result = IngestResult()
    if detail.gone:
        if not seen:
            return result
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
    if llm is not None:
        await llm.refine(row["id"], item)
    try:
        return await ingest([item], target=Target(row.get("make"), row.get("model")), detail=True,
                            seen=seen)
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
    llm = await DescriptionLLM.create() if rows else None
    result = await drain(rows, lambda r: refresh_listing(r, stage="enrich", llm=llm),
                         intervals=intervals, stop=stop)
    if rows:
        log.info("enrichment: %d listings, %d updated, %d events",
                 len(rows), result.updated, len(result.events))
    await rescore_changed(result)
    return result


async def rescore_changed(result: IngestResult) -> int:
    """Re-score the matches of the listings a detail pass updated."""
    changed = [e.listing_id for e in result.events if e.kind == "listing_updated"]
    return await rescore_listings(changed) if changed else 0
