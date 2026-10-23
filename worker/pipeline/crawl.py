"""Crawl targets and their cadence (sección 5.1).

Each tick `crawl_targets` is re-derived from the enabled search profiles,
grouped by (source, make, model) with the widest query: lowest year_min,
highest year_max, highest km_max (or none) and **no price filter** (prices
are compared after currency conversion). Scraping cost depends on how many
models are searched, not on how many users search them.
Small catalogs/feeds opt into INVENTORY_TARGET: one unfiltered source target,
without make/model hints, shared by every eligible profile that selects it.
A search without a model, only by body type (docs/CARROCERIA.md), gets one
target per (source, body type) on the sources app_config.body_type_targets
names whose collector can search that body type (BODY_TYPES). Those targets
run every body_type_targets.interval_seconds, and before ingesting they drop
what none of their searches could want: above the highest price cap in USD,
below the lowest year, above the highest km.
The searches whose access ended in the last 3 weeks are only counted (2.5,
docs/MAILS_DE_PLAN.md): they ride the targets above as they are, and a model
nobody else searches gets a `count_only` target crawled once a day.

Each source runs in its own lane (Lanes): the targets of one source run one
after the other, with jitter, and a source that is slow or hung never holds up
the others. A target that never ran goes first, then the due targets that
notify, then the first-run retries and the count-only targets
(targets.claim_next): a long bootstrap never makes them wait more than one
of its scans. A lane claims each target before crawling it
(targets.claim_next, a lease of LEASE_SECONDS), so crawl_targets is a queue
that several workers can share and that heals itself when one dies; a source
is crawled by one lane at a time across all of them. A
collector search is cancelled after COLLECTOR_TIMEOUT_SECONDS; an ISOLATED
collector (Facebook, Instagram) runs in a child process that is killed then
(collectors/_isolated.py). The next run is scheduled after the source's
interval. For recent publications, last_run_at records the successful scan's
start to preserve coverage. On a source without publication dates,
pipeline/news.py tells which new listings are old stock (backfill), and a
first run that read nothing holds the bootstrap for a couple of runs.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from collectors import REGISTRY, Listing
from collectors.base import CollectorBlocked
from collectors.facebook import DATE_FETCH_LIMIT as FB_DATE_FETCH_LIMIT
from collectors._isolated import call as isolated_call, isolated
from collectors._loop import run_collector
import config
from config import COLLECTOR_TIMEOUT_SECONDS
from collectors._recency import POLICY_VERSION, SOURCES as RECENT_SOURCES, target_window
from db.pool import connection
from db.repos import runs, targets as targets_repo
from db.repos.config import get_config
from db.repos.fx import quote_for_today
from db.repos.runs import SourceHealth
from intelligence.matching import filter_currency, malformed_vehicle, model_less, wanted_body_types
from normalization.listing import Target
from normalization.normalize import normalize_brand, normalize_text
from pipeline import breaker, news
from pipeline.ingest import IngestResult, ingest


log = logging.getLogger("crawl")

# How long a lane holds the target it claimed (targets.claim_next): its
# search's timeout plus time for the batch. A worker that dies mid-run frees
# it when this runs out.
LEASE_SECONDS = COLLECTOR_TIMEOUT_SECONDS + 900
# A failed target retries after its interval, but never later than this.
FAILURE_RETRY_SECONDS = 900
# A failed count-only target (2.5) waits longer: nobody waits for it, and a
# source that is blocking requests shouldn't get extra ones.
COUNT_ONLY_RETRY_SECONDS = 6 * 3600
# A Facebook scan that stopped at its item-page cap (facebook.DATE_FETCH_LIMIT)
# goes on soon: it kept what it read, and the due targets go before it anyway.
DATE_FETCH_RETRY_SECONDS = 180

# app_config.body_type_targets when the row is missing (the migration's value).
DEFAULT_BODY_TYPE_TARGETS = {"sources": ["mercadolibre", "kavak"], "interval_seconds": 1800}
# A body-type target's price ceiling lets this much more through: it was
# converted when the targets were synced, and a stored listing keeps the
# USD price of the day it was first seen.
PRICE_CEILING_MARGIN = 0.05


@dataclass(frozen=True)
class TargetSpec:
    source: str
    make: str | None
    model: str | None
    query: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)
    body_type: str | None = None


@dataclass(frozen=True)
class BodyTypeTargets:
    """app_config.body_type_targets, plus today's USD/ARS rate to turn the
    searches' ARS price caps into the USD ceiling a target keeps."""
    sources: frozenset[str] = frozenset()
    interval_seconds: int = DEFAULT_BODY_TYPE_TARGETS["interval_seconds"]
    fx_rate: float | None = None


@dataclass
class TargetRun:
    """One target crawled: what the collector returned and what ingest made of it."""
    target: dict[str, Any]
    items: list[Listing]
    result: IngestResult
    first_run: bool
    complete: bool = True
    covered_until: datetime | None = None
    # A first run of a source without dates (news.UNDATED_SOURCES): how many
    # ok runs in a row before it read nothing and held the bootstrap.
    empty_runs: int = 0
    # Listings stored for the first time that are old stock, matched as
    # backfill: the ones pipeline/news.py says are not news, and the ones
    # this target's prefilter had dropped before (prefilter_rejected).
    backfill_ids: frozenset[int] = frozenset()


class SourceBlocked(Exception):
    """run_target: the source blocked us and is paused (pipeline/breaker.py);
    its lane stops instead of trying its other targets."""


BatchHandler = Callable[[TargetRun], Awaitable[None]]
# Called with the source's failure streak after every run (the admin alert, sección 10).
HealthHandler = Callable[[SourceHealth | None], Awaitable[Any]]


def _widest(values: list[Any], pick) -> Any:
    """min/max over the profiles, or None as soon as one of them has no bound."""
    if not values or any(v is None for v in values):
        return None
    return pick(values)


# (source, make, model, body type), "" for none.
_Key = tuple[str, str, str, str]
_Names = tuple[str | None, str | None, str | None]


def _group(profiles: list[dict[str, Any]], sources: list[str], body: BodyTypeTargets | None = None
           ) -> tuple[dict[_Key, list[dict[str, Any]]], dict[_Key, _Names]]:
    """Profiles by target key. A search without a model only gets targets
    with `body` (the active searches, never the ones 2.5 counts)."""
    groups: dict[_Key, list[dict[str, Any]]] = {}
    names: dict[_Key, _Names] = {}
    for p in profiles:
        f = p.get("filters") or {}
        if malformed_vehicle(f):
            continue                        # it matches nothing (intelligence/matching.py)
        make, model = f.get("make"), f.get("model")
        wanted = f.get("sources") or sources
        for source in (s for s in wanted if s in sources):
            if getattr(REGISTRY.get(source), "INVENTORY_TARGET", False):
                key = (source, "", "", "")
                groups.setdefault(key, []).append(p)
                names.setdefault(key, (None, None, None))
                continue
            if model_less(f):
                # Large search sites still need a vehicle, or a body type they can search.
                if body is None or source not in body.sources:
                    continue
                searchable = getattr(REGISTRY.get(source), "BODY_TYPES", frozenset())
                for code in dict.fromkeys(wanted_body_types(f)):
                    if code in searchable:
                        key = (source, "", "", code)
                        groups.setdefault(key, []).append(p)
                        names.setdefault(key, (None, None, code))
                continue
            key = (source, normalize_brand(make), normalize_text(model), "")
            groups.setdefault(key, []).append(p)
            names.setdefault(key, (make, model, None))
    return groups, names


def _usd_cap(f: dict[str, Any], fx_rate: float | None) -> int | None:
    """A search's price cap in USD, rounded up. None without a cap, or for an
    ARS cap without a rate: no ceiling then."""
    try:
        cap = float(f["price_max"])
    except (KeyError, TypeError, ValueError):
        return None
    if cap <= 0:
        return None
    currency = filter_currency(cap, f.get("currency"))
    if currency == "USD":
        return math.ceil(cap)
    return math.ceil(cap / fx_rate) if currency == "ARS" and fx_rate else None


def _spec(key: _Key, members: list[dict[str, Any]], names: _Names, *,
          count_only: bool = False, body: BodyTypeTargets | None = None) -> TargetSpec:
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
    if key[3]:
        # By body type: what ingest keeps (prefilter) and its own cadence.
        body = body or BodyTypeTargets()
        query["price_usd_max"] = _widest([_usd_cap(f, body.fx_rate) for f in filters], max)
        query["interval_seconds"] = body.interval_seconds
    if key[0] in RECENT_SOURCES:
        query["publication_policy"] = POLICY_VERSION
    # Facebook searches around a city: the oldest profile with a location picks it.
    located = next((m for m in sorted(members, key=lambda m: m["id"])
                    if m.get("origin_lat") is not None), None)
    if located:
        query["origin_lat"], query["origin_lon"] = located["origin_lat"], located["origin_lon"]
    query.update(ids)
    make, model, body_type = names
    return TargetSpec(key[0], make, model, {k: v for k, v in query.items() if v is not None},
                      body_type=body_type)


def derive_targets(profiles: list[dict[str, Any]], sources: list[str],
                   counting: list[dict[str, Any]] = (), *,
                   body_types: BodyTypeTargets | None = None) -> list[TargetSpec]:
    """Group profiles by vehicle, by body type, or once per inventory source without filters.

    `sources` are the enabled sources with a collector; a profile that names
    its sources only contributes to those. A search without a model gets
    targets by body type only with `body_types` (app_config.body_type_targets).
    `counting` are the searches 2.5 counts after their access ended: they
    never change a target of the active profiles (its query, its cadence or
    the city Facebook searches around) and only add the vehicles none of
    those cover, as count-only targets; never a body type.
    """
    groups, names = _group(profiles, sources, body_types)
    specs = [_spec(key, members, names[key], body=body_types) for key, members in sorted(groups.items())]
    counted, counted_names = _group(list(counting), sources)
    specs += [_spec(key, members, counted_names[key], count_only=True)
              for key, members in sorted(counted.items()) if key not in groups]
    return specs


def retry_seconds(target: dict[str, Any], *, reason: str | None = None, partial: bool = False) -> int:
    """When a failed or incomplete run of this target is tried again: a
    count-only target in 6 hours, a Facebook scan cut by its item-page cap
    (`reason`) in 180 s, any other one after its interval, 15 minutes at
    most. `partial`: the run read part of the source (SearchResults.complete
    is False). A partial read past the first one, on a source without
    publication dates, waits for the whole interval (config.NEWS_PARTIAL_RETRY):
    a source that cut the read short (a 503, a Retry-After) isn't hammered
    every 15 minutes, and what it read is stored."""
    interval = int(target.get("crawl_interval_seconds") or FAILURE_RETRY_SECONDS)
    if (target.get("query") or {}).get("count_only") is True:
        return COUNT_ONLY_RETRY_SECONDS
    if reason == FB_DATE_FETCH_LIMIT:
        return DATE_FETCH_RETRY_SECONDS
    if (partial and config.NEWS_PARTIAL_RETRY and target.get("first_run_done")
            and target.get("source") not in RECENT_SOURCES):
        return interval
    return min(interval, FAILURE_RETRY_SECONDS)


def scraper_filters(target: dict[str, Any]) -> dict[str, Any]:
    """A target's query in the collectors' filter vocabulary."""
    q = target.get("query") or {}
    f: dict[str, Any] = {"marca": target.get("make"), "modelo": target.get("model"),
                         # A target by body type has no marca/modelo (BaseScraper.BODY_TYPES).
                         "carroceria": target.get("body_type"),
                         "anio_min": q.get("year_min"), "anio_max": q.get("year_max"),
                         "km_max": q.get("km_max"),
                         "origin_lat": q.get("origin_lat"), "origin_lon": q.get("origin_lon"),
                         # Only searches with ended access want it (2.5): a collector may read less.
                         "count_only": True if q.get("count_only") is True else None}
    f.update(target_window(target))
    return {k: v for k, v in f.items() if v is not None}


def prefilter(target: dict[str, Any]) -> Callable[[dict[str, Any]], bool] | None:
    """For a target by body type, the normalized rows worth storing: those one
    of its searches could want (docs/CARROCERIA.md), so the database grows
    with what is searched and not with every SUV in the country. A row goes
    when its USD price is above the highest cap (price_usd_max, plus
    PRICE_CEILING_MARGIN), its year below the lowest year_min or its km above
    the highest km_max. Unknown values and partial prices pass. None (keep
    everything) for any other target.

    On a source without publication dates (Kavak) a body type's whole stock
    is read on every run, so what the prefilter drops is remembered
    (crawl_targets.prefilter_rejected, run_target): a wider search, a price
    cut or the quote can let it in later, and then it is not news. A
    Facebook target by model keeps its date memory in that column instead
    (_date_memory); no target uses it both ways."""
    if not target.get("body_type"):
        return None
    q = target.get("query") or {}
    year_min, km_max, usd_max = q.get("year_min"), q.get("km_max"), q.get("price_usd_max")
    ceiling = usd_max * (1 + PRICE_CEILING_MARGIN) if usd_max is not None else None

    def keep(row: dict[str, Any]) -> bool:
        if year_min is not None and row.get("year") is not None and row["year"] < year_min:
            return False
        if km_max is not None and row.get("mileage_km") is not None and row["mileage_km"] > km_max:
            return False
        usd = row.get("price_usd")
        return ceiling is None or usd is None or bool(row.get("price_partial")) or usd <= ceiling
    return keep


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
        if _date_memory(target):
            filters["date_skips"] = list(target.get("prefilter_rejected") or ())
        if isolated(scraper):
            items = await run_collector(isolated_call(scraper, "search", filters, timeout=COLLECTOR_TIMEOUT_SECONDS))
        else:
            items = await run_collector(scraper.search(filters), timeout=COLLECTOR_TIMEOUT_SECONDS)
    except Exception as exc:
        log.warning("target=%s %s %s failed: %s", target["id"], source, _label(target), exc)
        health = await runs.finish_run(run_id, ok=False, error=traceback.format_exc())
        await targets_repo.finish_target(target["id"], ok=False, retry_seconds=retry)
        await _report(on_health, health)
        if isinstance(exc, CollectorBlocked):
            breaker.pause(source, str(exc))
            raise SourceBlocked(source) from exc
        return None
    keep, rejected = prefilter(target), set()
    if keep is not None and source not in RECENT_SOURCES:
        def keep(row: dict[str, Any], _keep=keep) -> bool:
            if _keep(row):
                return True
            if row.get("external_id") is not None:
                rejected.add(str(row["external_id"]))
            return False
    try:
        result = await ingest(items, target=Target(target.get("make"), target.get("model"),
                                                   target.get("body_type")),
                              keep=keep)
    except Exception:
        err = traceback.format_exc()
        await runs.log_error("ingest", f"target:{target['id']}", err)
        health = await runs.finish_run(run_id, ok=False, found=len(items), error=err)
        await targets_repo.finish_target(target["id"], ok=False, retry_seconds=retry)
        await _report(on_health, health)
        return None
    complete = getattr(items, "complete", True)
    first_run = not target["first_run_done"]
    remembers = keep is not None and source not in RECENT_SOURCES
    # Right after the ingest, so that little can stop the run before the marks.
    backfill_ids = await news.classify(target, items, result, run_id=run_id, first_run=first_run,
                                       complete=complete,
                                       readmitted=_readmitted(target, result) if remembers else ())
    error = getattr(items, "reason", None) if not complete else None
    health = await runs.finish_run(run_id, ok=complete, found=result.found, new=result.new,
                                   updated=result.updated, error=error)
    await _report(on_health, health)
    probe = getattr(items, "probe", None)
    log.info("target=%s %s %s found=%d new=%d updated=%d events=%d%s", target["id"], source,
             _label(target), result.found, result.new, result.updated, len(result.events),
             f" probe={json.dumps(probe, separators=(',', ':'))}" if probe else "")
    covered_until = (datetime.fromtimestamp(filters["publication_until"], timezone.utc)
                     if "publication_until" in filters else None)
    if _date_memory(target):
        await _remember_dates(target, getattr(items, "date_skips", None))
    if remembers:
        backfill_ids |= await _remember_rejected(target, result, rejected, complete=complete)
    empty_runs = (await runs.empty_ok_streak(target["id"], exclude_run=run_id)
                  if first_run and config.NEWS_GUARD_EMPTY_FIRST and source in news.UNDATED_SOURCES else 0)
    return TargetRun(target, items, result, first_run=first_run, complete=complete,
                     covered_until=covered_until, empty_runs=empty_runs, backfill_ids=backfill_ids)


def _date_memory(target: dict[str, Any]) -> bool:
    """Whether the target keeps Facebook's date memory (collectors/_recency.py)
    in prefilter_rejected: a Facebook target by model. A target by body type
    keeps what its prefilter dropped there."""
    return target["source"] == "facebook" and not target.get("body_type")


async def _remember_dates(target: dict[str, Any], date_skips: list[str] | None) -> None:
    """Store the date memory the scan left (the collector merges it with the
    previous one), unless it kept none or it didn't change."""
    if date_skips is None or sorted(set(date_skips)) == sorted(set(target.get("prefilter_rejected") or ())):
        return
    try:
        await targets_repo.set_prefilter_rejected(target["id"], date_skips)
    except Exception:
        await runs.log_error("crawl", f"target:{target['id']}", traceback.format_exc())


def _readmitted(target: dict[str, Any], result: IngestResult) -> frozenset[int]:
    """The listings of this read that this target's prefilter had dropped on
    an earlier run (prefilter_rejected): old stock a wider search or a price
    cut let in. Stored now, or by a run cut before it updated
    prefilter_rejected (pipeline/news.py catches that run up)."""
    before = set(target.get("prefilter_rejected") or ())
    return frozenset(lid for (_, external_id), lid in result.ids.items() if external_id in before)


async def _remember_rejected(target: dict[str, Any], result: IngestResult, rejected: set[str], *,
                             complete: bool) -> frozenset[int]:
    """The listings of this read the prefilter had dropped on an earlier run
    (_readmitted), and the ones it dropped now for the next run: all of them
    after a complete run, added to the last ones after a partial one."""
    before = set(target.get("prefilter_rejected") or ())
    backfill = _readmitted(target, result)
    try:
        await targets_repo.set_prefilter_rejected(target["id"], rejected if complete else rejected | before)
    except Exception:
        await runs.log_error("crawl", f"target:{target['id']}", traceback.format_exc())
    if backfill:
        log.info("target=%s %s: %d listings the prefilter had dropped are backfill",
                 target["id"], _label(target), len(backfill))
    return backfill


def _label(target: dict[str, Any]) -> str:
    if target.get("body_type"):
        return f"body_type={target['body_type']}"
    return f"{target.get('make') or '*'}/{target.get('model') or '*'}"


async def _report(on_health: HealthHandler | None, health: SourceHealth | None) -> None:
    if on_health is None:
        return
    try:
        await on_health(health)
    except Exception:
        log.exception("source health handler failed")


async def _run_one(target: dict[str, Any], on_batch: BatchHandler | None,
                   on_health: HealthHandler | None = None) -> None:
    """Crawl one target, handle its batch and schedule its next run (which
    also frees its claim)."""
    run = await run_target(target, on_health)
    if run is None:
        return
    if on_batch is not None:
        try:
            await on_batch(run)
        except Exception:
            await runs.log_error("notify", f"target:{target['id']}", traceback.format_exc())
            await targets_repo.finish_target(target["id"], ok=False, retry_seconds=retry_seconds(target))
            return
    # Only now is the first run over: its batch was handled as backfill. A
    # source without publication dates that read nothing may not be loaded
    # yet: the stock its next read finds is that first run's, for
    # news.EMPTY_FIRST_RUNS empty reads in a row at most.
    bootstrap = not (config.NEWS_GUARD_EMPTY_FIRST and run.first_run and run.result.found == 0
                     and target.get("source") in news.UNDATED_SOURCES and run.empty_runs < news.EMPTY_FIRST_RUNS)
    retry = 0 if run.complete else retry_seconds(target, reason=getattr(run.items, "reason", None), partial=True)
    await targets_repo.finish_target(target["id"], ok=run.complete, retry_seconds=retry,
                                    covered_until=run.covered_until, bootstrap=bootstrap)


async def _run_source(targets: list[dict[str, Any]], on_batch: BatchHandler | None,
                      jitter_seconds: float, stop: asyncio.Event | None,
                      on_health: HealthHandler | None = None) -> None:
    """These targets one after the other, with jitter, without claiming them."""
    for i, target in enumerate(targets):
        if stop is not None and stop.is_set():
            return
        if i and jitter_seconds > 0:
            await asyncio.sleep(random.uniform(jitter_seconds / 2, jitter_seconds))
        try:
            await _run_one(target, on_batch, on_health)
        except SourceBlocked:
            return


async def _drain(source: str, on_batch: BatchHandler | None, jitter_seconds: float,
                 stop: asyncio.Event | None, on_health: HealthHandler | None = None) -> int:
    """Claim and crawl `source`'s due targets one at a time, in claim_next's
    order, with jitter, until none is left or another worker is crawling the
    source. Returns how many it crawled."""
    done = 0
    while (stop is None or not stop.is_set()) and not breaker.paused(source):
        target = await targets_repo.claim_next(source, runs.worker_id(), LEASE_SECONDS)
        if target is None:
            break
        if done and jitter_seconds > 0:
            await asyncio.sleep(random.uniform(jitter_seconds / 2, jitter_seconds))
        try:
            await _run_one(target, on_batch, on_health)
        except SourceBlocked:
            return done + 1
        except Exception:
            await runs.log_error("crawl", f"target:{target['id']}", traceback.format_exc())
            # Free it: a held claim keeps the whole source waiting (claim_next).
            try:
                await targets_repo.finish_target(target["id"], ok=False, retry_seconds=retry_seconds(target))
            except Exception:
                log.exception("target=%s keeps its claim until the lease ends", target["id"])
        done += 1
    return done


def _due_sources(due: list[dict[str, Any]]) -> list[str]:
    """The sources with a collector among these due targets, in their order."""
    return list(dict.fromkeys(t["source"] for t in due if t["source"] in REGISTRY))


async def crawl_due(on_batch: BatchHandler | None = None, *, jitter_seconds: float = 5.0,
                    stop: asyncio.Event | None = None, on_health: HealthHandler | None = None) -> int:
    """Crawl every due target and wait for all of them: sources in parallel,
    targets of a source in series (tests and tools; the worker uses Lanes).
    Returns how many targets were crawled."""
    sources = _due_sources(await targets_repo.due_targets())
    done = await asyncio.gather(*(_drain(s, on_batch, jitter_seconds, stop, on_health) for s in sources))
    return sum(done)


class Lanes:
    """One crawl task per source (_drain), started without waiting for it. A
    source whose lane is still running is left alone until it ends, so a slow
    or hung source only delays itself, and new searches keep being crawled
    elsewhere. The claims (targets.claim_next) keep two lanes, of this worker
    or another one, from ever crawling the same source at once."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[int]] = {}

    def running(self) -> set[str]:
        return {s for s, t in self._tasks.items() if not t.done()}

    async def start_due(self, on_batch: BatchHandler | None = None, *, jitter_seconds: float = 5.0,
                        stop: asyncio.Event | None = None, on_health: HealthHandler | None = None) -> list[str]:
        """Start a lane for every idle source with due targets. Returns those sources."""
        busy = self.running()
        started = [s for s in _due_sources(await targets_repo.due_targets())
                   if s not in busy and not breaker.paused(s)]
        for source in started:
            task = asyncio.create_task(_drain(source, on_batch, jitter_seconds, stop, on_health),
                                       name=f"lane:{source}")
            task.add_done_callback(_lane_done)
            self._tasks[source] = task
        return started

    async def close(self) -> None:
        """Cancel the running lanes and wait for them."""
        tasks = [t for t in self._tasks.values() if not t.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


def _lane_done(task: asyncio.Task[int]) -> None:
    if not task.cancelled() and task.exception() is not None:
        log.error("%s failed", task.get_name(), exc_info=task.exception())


async def body_type_targets(profiles: list[dict[str, Any]]) -> BodyTypeTargets:
    """app_config.body_type_targets. Today's quote is read only when some
    search by body type alone is enabled: its ARS cap becomes a USD ceiling."""
    cfg = await get_config("body_type_targets", DEFAULT_BODY_TYPE_TARGETS)
    cfg = cfg if isinstance(cfg, dict) else DEFAULT_BODY_TYPE_TARGETS
    sources = cfg.get("sources") if isinstance(cfg.get("sources"), list) else []
    try:
        interval = max(60, int(cfg.get("interval_seconds") or DEFAULT_BODY_TYPE_TARGETS["interval_seconds"]))
    except (TypeError, ValueError):
        interval = DEFAULT_BODY_TYPE_TARGETS["interval_seconds"]
    fx_rate = None
    if any(model_less(p.get("filters") or {}) and wanted_body_types(p.get("filters") or {})
           for p in profiles):
        async with connection() as cx:
            fx_rate = (await quote_for_today(cx)).rate
    return BodyTypeTargets(frozenset(s for s in sources if isinstance(s, str)), interval, fx_rate)


async def sync_targets(profiles: list[dict[str, Any]],
                       counting: list[dict[str, Any]] = ()) -> list[TargetSpec]:
    sources = [s for s in await targets_repo.enabled_sources() if s in REGISTRY]
    specs = derive_targets(profiles, sources, counting, body_types=await body_type_targets(profiles))
    await targets_repo.sync_targets(specs)
    return specs
