"""The llm_jobs loop (sección 8.4, pasos 3–4).

    claim (FOR UPDATE SKIP LOCKED) → provider → normalize against the catalog
    → output + latency_ms, or error

The claim commits before the provider runs, so a slow `claude -p` holds no
transaction or row lock; the row's 'running' status is the lease. Jobs
nobody will read anymore expire (db/repos/llm_jobs.expire).

'parse_search' (the assisted mode) and, since PAR-04, 'model_guide' (a
guide draft the admin asked for, docs/superpowers/specs/2026-11-03-par04-guias-design.md)
are consumed; the other optional kinds of sección 8.1 wait for a consumer.
Guides have a consumer of their own (one, no concurrency), so a two-minute
guide never delays an assisted search, their own expiry
(llm_limits.model_guide.queued_ttl_minutes: nobody waits on a screen) and
their own switch: the worker reads llm_limits.model_guide.enabled again when
it takes the job, and a job queued before the generation was turned off
fails without calling the provider.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import config
import db
from db.repos import catalog as catalog_repo
from db.repos import catalog_misses as misses_repo
from db.repos import guides as guides_repo
from db.repos import llm_jobs as jobs_repo
from intelligence import guides
from llm.prompts import MODEL_GUIDE_PROMPT_VERSION
from llm.provider import LLMError, LLMProvider
from normalization.drafts import catalog_misses, normalize_drafts

log = logging.getLogger(__name__)

KINDS = ["parse_search"]
GUIDE_KINDS = ["model_guide"]

# llm_limits.model_guide without the key (the migration adds them all).
GUIDE_DEFAULTS = {"enabled": False, "queued_ttl_minutes": 60, "timeout_seconds": 180}

# The web shows the fallback form after ~75 s (web/lib/assisted.ts); a queued
# job older than that has no reader. A running one gets its budget and margin.
QUEUED_TTL_SECONDS = 75.0
RUNNING_GRACE_SECONDS = 60.0
EXPIRE_EVERY_SECONDS = 30.0


class BadInput(LLMError):
    pass


class NotCalled(LLMError):
    """The job fails before reaching the provider (llm_jobs.provider stays null,
    so it counts for no cap and no latency stats)."""


async def guide_config() -> dict[str, Any]:
    """llm_limits.model_guide, read now (not db.get_config's cache): turning the
    generation off must stop the next job."""
    async with db.connection() as cx:
        row = await (await cx.execute(
            "SELECT value -> 'model_guide' AS cfg FROM app_config WHERE key = 'llm_limits'")).fetchone()
    cfg = row["cfg"] if row and isinstance(row["cfg"], dict) else {}
    return {**GUIDE_DEFAULTS, **cfg}


def _positive(value: Any, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return default
    return float(value)


async def _parse_search(provider: LLMProvider, job: dict[str, Any]) -> dict[str, Any]:
    text = (job["input"] or {}).get("text")
    if not isinstance(text, str) or not text.strip():
        raise BadInput("falta el texto")
    async with db.connection() as cx:
        models = await catalog_repo.load_models(cx)
        market = await catalog_repo.load_market(cx)
    drafts = await provider.parse_search(text, models)
    output = normalize_drafts(models, drafts, market=market)
    if misses := catalog_misses(models, drafts):
        # Bookkeeping for /admin: a failure here never fails the user's job.
        try:
            async with db.connection() as cx:
                await misses_repo.record(cx, misses, job["id"])
        except Exception:
            log.exception("llm job %s: catalog_misses", job["id"])
    return output


async def _model_guide(provider: LLMProvider, job: dict[str, Any]) -> dict[str, Any]:
    """PAR-04: a guide draft. Cache by (make, model, generation, prompt
    version) unless `force` («Regenerar»); otherwise the provider, then
    intelligence/guides.validate_draft. The draft goes into the guide only if
    it is still a draft nobody edited after the request; the output keeps it
    either way (applied: false)."""
    data = job["input"] or {}
    guide_id, make, model = data.get("guide_id"), data.get("make"), data.get("model")
    if not isinstance(guide_id, int) or not isinstance(make, str) or not isinstance(model, str):
        raise NotCalled("faltan la guía, la marca o el modelo")
    cfg = await guide_config()
    if cfg.get("enabled") is not True:
        raise NotCalled("la generación de guías está apagada (llm_limits.model_guide.enabled)")
    async with db.connection() as cx:
        guide = await guides_repo.get(cx, guide_id)
    if guide is None:
        raise NotCalled("la guía ya no existe")
    if guide["status"] != "draft":
        raise NotCalled("la guía está publicada: la IA no toca una guía publicada")

    generation = data.get("generation_label")
    key = guides.cache_key(make, model, generation if isinstance(generation, str) else None,
                           MODEL_GUIDE_PROMPT_VERSION)
    cached = None
    if not data.get("force"):
        async with db.connection() as cx:
            cached = await guides_repo.cached_output(cx, key, exclude_job=job["id"])
    if cached is not None:
        draft, llm_version = cached["guide"], cached.get("llm_version") or "cache"
        output = {"cache_key": key, "cached": True, "cached_from_job": cached["job_id"],
                  "llm_version": llm_version, "guide": draft}
    else:
        async with db.connection() as cx:
            catalog = await guides_repo.catalog_context(cx, make, model)
        years = catalog["years"]
        context = {
            "marca": make, "modelo": model,
            "generacion": generation if isinstance(generation, str) else None,
            "anio_desde": data.get("year_from") or years[0],
            "anio_hasta": data.get("year_to") or years[1],
            "versiones": catalog["trims"],
        }
        timeout = _positive(cfg.get("timeout_seconds"), GUIDE_DEFAULTS["timeout_seconds"])
        draft = guides.validate_draft(await provider.model_guide(context, timeout=timeout))
        llm_version = f"{provider.name}|{MODEL_GUIDE_PROMPT_VERSION}"
        output = {"cache_key": key, "cached": False, "llm_version": llm_version, "guide": draft}
    async with db.connection() as cx:
        output["applied"] = await guides_repo.apply_draft(cx, guide_id, draft, job_id=job["id"],
                                                          llm_version=llm_version, requested_at=job["created_at"])
    return output


_HANDLERS = {"parse_search": _parse_search, "model_guide": _model_guide}


async def process_next(provider: LLMProvider, kinds: list[str] | None = None) -> bool:
    """Run one queued job of `kinds` (KINDS by default); False when there is none."""
    async with db.connection() as cx:
        job = await jobs_repo.claim(cx, kinds or KINDS, provider.name)
    if job is None:
        return False

    started = time.monotonic()
    output: dict[str, Any] | None = None
    error: str | None = None
    used: str | None = provider.name
    try:
        output = await _HANDLERS[job["kind"]](provider, job)
        if output.get("cached") is True:
            used = "cache"
    except NotCalled as e:
        error, used = str(e), None
    except LLMError as e:
        error = str(e) or type(e).__name__
    except Exception:
        log.exception("llm job %s failed", job["id"])
        error = "error interno del worker"
    latency_ms = round((time.monotonic() - started) * 1000)

    async with db.connection() as cx:
        await jobs_repo.finish(cx, job["id"], output=output, error=error, latency_ms=latency_ms,
                               provider=used)
    if error:
        log.info("llm job %s (%s) failed in %d ms: %s", job["id"], job["kind"], latency_ms, error)
    else:
        log.info("llm job %s (%s) done in %d ms", job["id"], job["kind"], latency_ms)
    return True


async def expire_stale() -> int:
    cfg = await guide_config()
    async with db.connection() as cx:
        n = await jobs_repo.expire(
            cx, queued_seconds=QUEUED_TTL_SECONDS,
            running_seconds=config.LLM_TIMEOUT_SECONDS + RUNNING_GRACE_SECONDS,
            guide_queued_seconds=_positive(cfg.get("queued_ttl_minutes"), GUIDE_DEFAULTS["queued_ttl_minutes"]) * 60,
            guide_running_seconds=_positive(cfg.get("timeout_seconds"), GUIDE_DEFAULTS["timeout_seconds"])
            + RUNNING_GRACE_SECONDS)
    if n:
        log.info("llm_jobs: %d vencidos", n)
    return n


async def drain(provider: LLMProvider) -> int:
    """Process every queued job, then return how many ran (tools, tests)."""
    await expire_stale()
    n = 0
    while await process_next(provider, KINDS + GUIDE_KINDS):
        n += 1
    return n


async def _consume(provider: LLMProvider, stop: asyncio.Event, poll: float,
                   kinds: list[str] | None = None) -> None:
    while not stop.is_set():
        try:
            worked = await process_next(provider, kinds)
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
    """`concurrency` consumers share the assisted-mode queue (SKIP LOCKED keeps
    them apart); one more takes the guides (PAR-04), one at a time."""
    n = max(1, concurrency or config.LLM_CONCURRENCY)
    log.info("llm_jobs: %s, %d a la vez (+1 para guías)", provider.name, n)
    every = poll or config.LLM_POLL_SECONDS
    await asyncio.gather(_expirer(stop),
                         *(_consume(provider, stop, every) for _ in range(n)),
                         _consume(provider, stop, every, GUIDE_KINDS))
