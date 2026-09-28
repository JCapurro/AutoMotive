"""The llm_jobs loop (sección 8.4, pasos 3–4).

    claim (FOR UPDATE SKIP LOCKED) → provider → normalize against the catalog
    → output + latency_ms, or error

The claim commits before the provider runs, so a slow `claude -p` holds no
transaction or row lock; the row's 'running' status is the lease. Jobs
nobody will read anymore expire (db/repos/llm_jobs.expire).

Only 'parse_search' is consumed today: the optional kinds of sección 8.1
wait for a consumer.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import config
import db
from db.repos import catalog as catalog_repo
from db.repos import llm_jobs as jobs_repo
from llm.provider import LLMError, LLMProvider
from normalization.drafts import normalize_drafts

log = logging.getLogger(__name__)

KINDS = ["parse_search"]

# The web shows the fallback form after ~75 s (web/lib/assisted.ts); a queued
# job older than that has no reader. A running one gets its budget and margin.
QUEUED_TTL_SECONDS = 75.0
RUNNING_GRACE_SECONDS = 60.0
EXPIRE_EVERY_SECONDS = 30.0


class BadInput(LLMError):
    pass


async def _parse_search(provider: LLMProvider, job: dict[str, Any]) -> dict[str, Any]:
    text = (job["input"] or {}).get("text")
    if not isinstance(text, str) or not text.strip():
        raise BadInput("falta el texto")
    async with db.connection() as cx:
        models = await catalog_repo.load_models(cx)
    drafts = await provider.parse_search(text, models)
    return normalize_drafts(models, drafts)


_HANDLERS = {"parse_search": _parse_search}


async def process_next(provider: LLMProvider) -> bool:
    """Run one queued job; False when the queue is empty."""
    async with db.connection() as cx:
        job = await jobs_repo.claim(cx, KINDS, provider.name)
    if job is None:
        return False

    started = time.monotonic()
    output: dict[str, Any] | None = None
    error: str | None = None
    try:
        output = await _HANDLERS[job["kind"]](provider, job)
    except LLMError as e:
        error = str(e) or type(e).__name__
    except Exception:
        log.exception("llm job %s failed", job["id"])
        error = "error interno del worker"
    latency_ms = round((time.monotonic() - started) * 1000)

    async with db.connection() as cx:
        await jobs_repo.finish(cx, job["id"], output=output, error=error, latency_ms=latency_ms)
    if error:
        log.info("llm job %s (%s) failed in %d ms: %s", job["id"], job["kind"], latency_ms, error)
    else:
        log.info("llm job %s (%s) done in %d ms", job["id"], job["kind"], latency_ms)
    return True


async def expire_stale() -> int:
    async with db.connection() as cx:
        n = await jobs_repo.expire(cx, queued_seconds=QUEUED_TTL_SECONDS,
                                   running_seconds=config.LLM_TIMEOUT_SECONDS + RUNNING_GRACE_SECONDS)
    if n:
        log.info("llm_jobs: %d vencidos", n)
    return n


async def drain(provider: LLMProvider) -> int:
    """Process every queued job, then return how many ran (tools, tests)."""
    await expire_stale()
    n = 0
    while await process_next(provider):
        n += 1
    return n


async def _consume(provider: LLMProvider, stop: asyncio.Event, poll: float) -> None:
    while not stop.is_set():
        try:
            worked = await process_next(provider)
        except Exception:
            log.exception("llm_jobs loop")
            worked = False
        if worked:
            continue
        try:
            await asyncio.wait_for(stop.wait(), timeout=poll)
        except asyncio.TimeoutError:
            pass


async def _expirer(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await expire_stale()
        except Exception:
            log.exception("llm_jobs expire")
        try:
            await asyncio.wait_for(stop.wait(), timeout=EXPIRE_EVERY_SECONDS)
        except asyncio.TimeoutError:
            pass


async def llm_jobs_loop(provider: LLMProvider, stop: asyncio.Event, *,
                        concurrency: int | None = None, poll: float | None = None) -> None:
    """`concurrency` consumers share the queue (SKIP LOCKED keeps them apart)."""
    n = max(1, concurrency or config.LLM_CONCURRENCY)
    log.info("llm_jobs: %s, %d a la vez", provider.name, n)
    await asyncio.gather(_expirer(stop),
                         *(_consume(provider, stop, poll or config.LLM_POLL_SECONDS) for _ in range(n)))
