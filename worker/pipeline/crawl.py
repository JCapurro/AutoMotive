"""Crawl targets and their cadence (sección 5.1).

Each tick `crawl_targets` is re-derived from the enabled search profiles,
grouped by (source, make, model) with the widest query: lowest year_min,
highest year_max, highest km_max (or none) and **no price filter** (prices
are compared after currency conversion). Scraping cost depends on how many
models are searched, not on how many users search them.
Small catalogs/feeds opt into INVENTORY_TARGET: one unfiltered source target,
without make/model hints, shared by every eligible profile that selects it.
The searches whose access ended in the last 3 weeks are only counted (2.5,
docs/MAILS_DE_PLAN.md): they ride the targets above as they are, and a model
nobody else searches gets a `count_only` target crawled once a day.

Sources run in parallel; the targets of one source run one after the other,
with jitter. The next run is scheduled after the source's interval. For recent
publications, last_run_at records the successful scan's start to preserve coverage.
"""
from __future__ import annotations

import asyncio
import logging
import random
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from collectors import REGISTRY, Listing
from collectors._loop import run_collector
from collectors._recency import POLICY_VERSION, SOURCES as RECENT_SOURCES, target_window
from db.repos import runs, targets as targets_repo
from db.repos.runs import SourceHealth
from normalization.listing import Target
from normalization.normalize import normalize_brand, normalize_text
from pipeline.ingest import IngestResult, ingest


log = logging.getLogger("crawl")

# A failed target retries after its interval, but never later than this.
FAILURE_RETRY_SECONDS = 900
# A failed count-only target (2.5) waits longer: nobody waits for it, and a
# source that is blocking requests shouldn't get extra ones.
COUNT_ONLY_RETRY_SECONDS = 6 * 3600


@dataclass(frozen=True)
class TargetSpec:
    source: str
    make: str | None
    model: str | None
    query: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass
class TargetRun:
    """One target crawled: what the collector returned and what ingest made of it."""
    target: dict[str, Any]
    items: list[Listing]
    result: IngestResult
    first_run: bool
    complete: bool = True
    covered_until: datetime | None = None


BatchHandler = Callable[[TargetRun], Awaitable[None]]
# Called with the source's failure streak after every run (the admin alert, sección 10).
HealthHandler = Callable[[SourceHealth | None], Awaitable[Any]]


def _widest(values: list[Any], pick) -> Any:
    """min/max over the profiles, or None as soon as one of them has no bound."""
    if not values or any(v is None for v in values):
        return None
    return pick(values)


_Key = tuple[str, str, str]


def _group(profiles: list[dict[str, Any]], sources: list[str]
           ) -> tuple[dict[_Key, list[dict[str, Any]]], dict[_Key, tuple[str | None, str | None]]]:
    groups: dict[_Key, list[dict[str, Any]]] = {}
    names: dict[_Key, tuple[str | None, str | None]] = {}
    for p in profiles:
        f = p.get("filters") or {}
        make, model = f.get("make"), f.get("model")
        wanted = f.get("sources") or sources
        for source in (s for s in wanted if s in sources):
            if getattr(REGISTRY.get(source), "INVENTORY_TARGET", False):
                key = (source, "", "")
                groups.setdefault(key, []).append(p)
                names.setdefault(key, (None, None))
                continue
            if not make and not model:
                continue    # large search sites still need a vehicle
            key = (source, normalize_brand(make), normalize_text(model))
            groups.setdefault(key, []).append(p)
            names.setdefault(key, (make, model))
    return groups, names


def _spec(key: _Key, members: list[dict[str, Any]], names: tuple[str | None, str | None], *,
          count_only: bool = False) -> TargetSpec:
    # A count-only target lists its searches apart: profile_ids are the active
    # members (the web reads them).
    members_ids = sorted(m["id"] for m in members)
    ids = ({"count_only": True, "count_profile_ids": members_ids} if count_only
           else {"profile_ids": members_ids})
    if getattr(REGISTRY.get(key[0]), "INVENTORY_TARGET", False):
        return TargetSpec(key[0], None, None, {"inventory": True, **ids})
    filters = [m.get("filters") or {} for m in members]
    query: dict[str, Any] = {
        "year_min": _widest([f.get("year_min") for f in filters], min),
        "year_max": _widest([f.get("year_max") for f in filters], max),
        "km_max": _widest([f.get("km_max") for f in filters], max),
    }
    if key[0] in RECENT_SOURCES:
        query["publication_policy"] = POLICY_VERSION
    # Facebook searches around a city: the oldest profile with a location picks it.
    located = next((m for m in sorted(members, key=lambda m: m["id"])
                    if m.get("origin_lat") is not None), None)
    if located:
        query["origin_lat"], query["origin_lon"] = located["origin_lat"], located["origin_lon"]
    query.update(ids)
    make, model = names
    return TargetSpec(key[0], make, model, {k: v for k, v in query.items() if v is not None})


def derive_targets(profiles: list[dict[str, Any]], sources: list[str],
                   counting: list[dict[str, Any]] = ()) -> list[TargetSpec]:
    """Group profiles by vehicle, or once per inventory source without filters.

    `sources` are the enabled sources with a collector; a profile that names
    its sources only contributes to those. `counting` are the searches 2.5
    counts after their access ended: they never change a target of the active
    profiles (its query, its cadence or the city Facebook searches around) and
    only add the vehicles none of those cover, as count-only targets.
    """
    groups, names = _group(profiles, sources)
    specs = [_spec(key, members, names[key]) for key, members in sorted(groups.items())]
    counted, counted_names = _group(list(counting), sources)
    specs += [_spec(key, members, counted_names[key], count_only=True)
              for key, members in sorted(counted.items()) if key not in groups]
    return specs


def retry_seconds(target: dict[str, Any]) -> int:
    """When a failed or incomplete run of this target is tried again."""
    if (target.get("query") or {}).get("count_only") is True:
        return COUNT_ONLY_RETRY_SECONDS
    return min(int(target.get("crawl_interval_seconds") or FAILURE_RETRY_SECONDS), FAILURE_RETRY_SECONDS)


def scraper_filters(target: dict[str, Any]) -> dict[str, Any]:
    """A target's query in the collectors' filter vocabulary."""
    q = target.get("query") or {}
    f: dict[str, Any] = {"marca": target.get("make"), "modelo": target.get("model"),
                         "anio_min": q.get("year_min"), "anio_max": q.get("year_max"),
                         "km_max": q.get("km_max"),
                         "origin_lat": q.get("origin_lat"), "origin_lon": q.get("origin_lon"),
                         # Only searches with ended access want it (2.5): a collector may read less.
                         "count_only": True if q.get("count_only") is True else None}
    f.update(target_window(target))
    return {k: v for k, v in f.items() if v is not None}


async def run_target(target: dict[str, Any], on_health: HealthHandler | None = None) -> TargetRun | None:
    """Scrape and ingest one target, recording a collector_runs row. None if it failed."""
    source = target["source"]
    run_id = await runs.start_run(source, target["id"])
    retry = retry_seconds(target)
    try:
        scraper = REGISTRY[source]()
        filters = scraper_filters(target)
        if source in RECENT_SOURCES:
            filters["known_publication_dates"] = await targets_repo.publication_dates(target)
        items = await run_collector(scraper.search(filters))
    except Exception as exc:
        log.warning("target=%s %s %s/%s failed: %s", target["id"], source, target.get("make"),
                    target.get("model"), exc)
        health = await runs.finish_run(run_id, ok=False, error=traceback.format_exc())
        await targets_repo.finish_target(target["id"], ok=False, retry_seconds=retry)
        await _report(on_health, health)
        return None
    try:
        result = await ingest(items, target=Target(target.get("make"), target.get("model")))
    except Exception:
        err = traceback.format_exc()
        await runs.log_error("ingest", f"target:{target['id']}", err)
        health = await runs.finish_run(run_id, ok=False, found=len(items), error=err)
        await targets_repo.finish_target(target["id"], ok=False, retry_seconds=retry)
        await _report(on_health, health)
        return None
    complete = getattr(items, "complete", True)
    error = getattr(items, "reason", None) if not complete else None
    health = await runs.finish_run(run_id, ok=complete, found=result.found, new=result.new,
                                   updated=result.updated, error=error)
    await _report(on_health, health)
    log.info("target=%s %s %s/%s found=%d new=%d updated=%d events=%d", target["id"], source,
             target.get("make") or "*", target.get("model") or "*", result.found, result.new,
             result.updated, len(result.events))
    covered_until = (datetime.fromtimestamp(filters["publication_until"], timezone.utc)
                     if "publication_until" in filters else None)
    return TargetRun(target, items, result, first_run=not target["first_run_done"],
                     complete=complete, covered_until=covered_until)


async def _report(on_health: HealthHandler | None, health: SourceHealth | None) -> None:
    if on_health is None:
        return
    try:
        await on_health(health)
    except Exception:
        log.exception("source health handler failed")


async def _run_source(targets: list[dict[str, Any]], on_batch: BatchHandler | None,
                      jitter_seconds: float, stop: asyncio.Event | None,
                      on_health: HealthHandler | None = None) -> None:
    for i, target in enumerate(targets):
        if stop is not None and stop.is_set():
            return
        if i and jitter_seconds > 0:
            await asyncio.sleep(random.uniform(jitter_seconds / 2, jitter_seconds))
        run = await run_target(target, on_health)
        if run is None:
            continue
        if on_batch is not None:
            try:
                await on_batch(run)
            except Exception:
                await runs.log_error("notify", f"target:{target['id']}", traceback.format_exc())
                await targets_repo.finish_target(target["id"], ok=False, retry_seconds=retry_seconds(target))
                continue
        # Only now is the first run over: its batch was handled as backfill.
        await targets_repo.finish_target(target["id"], ok=run.complete,
                                        retry_seconds=0 if run.complete else retry_seconds(target),
                                        covered_until=run.covered_until)


async def crawl_due(on_batch: BatchHandler | None = None, *, jitter_seconds: float = 5.0,
                    stop: asyncio.Event | None = None, on_health: HealthHandler | None = None) -> int:
    """Run every due target: sources in parallel, targets of a source in series.
    Returns how many targets were due."""
    due = await targets_repo.due_targets()
    by_source: dict[str, list[dict[str, Any]]] = {}
    for t in due:
        if t["source"] in REGISTRY:
            by_source.setdefault(t["source"], []).append(t)
    if by_source:
        await asyncio.gather(*(_run_source(ts, on_batch, jitter_seconds, stop, on_health)
                               for ts in by_source.values()))
    return len(due)


async def sync_targets(profiles: list[dict[str, Any]],
                       counting: list[dict[str, Any]] = ()) -> list[TargetSpec]:
    sources = [s for s in await targets_repo.enabled_sources() if s in REGISTRY]
    specs = derive_targets(profiles, sources, counting)
    await targets_repo.sync_targets(specs)
    return specs
