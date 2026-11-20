"""The daily «valor justo» fit and the scorer's curve cache.

Spec docs/superpowers/specs/2026-11-20-valor-justo-design.md §4.3, §4.4. The math is pure
(intelligence/fair_value.py); this module does the I/O around it:

* `fit_all(trigger=…)`: lists the models with min_listings priced listings, reads each model's
  public.price_pool, fits and gates it (§3.2, §3.5) and stores the curve (model_price_curves) and the run
  (fair_value_runs). It reads app_config.fair_value.mode before any other SQL: with 'off' (the code
  default) it touches neither table, since the worker deploys before the migrations. No pool connection
  is held while fitting (the pool has 5): read the rows, release, fit in asyncio.to_thread (CPU only:
  on the loop it would stall the heartbeat), take one again to write. A failure is logged
  (log_error("fair_value", …)) and closes the run with status 'failed'; the previous curves stay. A failure
  of one model is caught there: it goes to that model's stats entry and to log_error("fair_value",
  "<make> <model>", …), the others go on, the failed model keeps yesterday's curve, and the run closes
  'ok' unless every model failed.
* `fair_value_loop(stop)`: its own daily loop, modelled on market_stats_loop, at
  fair_value.schedule.hour (ART, 03:30 by default, before the 04:00 re-score). It catches up: at start
  and on every turn, when the last 'ok' run is older than 26 h it runs (trigger 'catchup'), so a restart
  with a fresh run does not fit again, and no catch-up runs while any run (ok or failed) started less than
  6 h ago, so a failing run does not retry every hour. Not inside nightly_loop, which runs its steps on every start, does
  not catch up a lost slot and would delay the re-score and the retention.
* `cached_curves(params)`: the enabled curves for Scorer.create (every crawl, rematch and re-score
  batch), kept in the process for 10 minutes. Nothing is read unless the mode is 'shadow' or 'live'.
"""
from __future__ import annotations

import asyncio
import logging
import time
import traceback
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Mapping

import db
from db.repos import price_curves as repo
from db.repos.runs import log_error
from intelligence import fair_value as fv
from intelligence.config import IntelligenceConfig, fair_value_config
from intelligence.f3 import warn_limited

log = logging.getLogger(__name__)

_AR = timezone(timedelta(hours=-3))
ON = ("shadow", "live")
STALE_AFTER = timedelta(hours=26)
RETRY_AFTER = timedelta(hours=6)    # no catch-up while any run (whatever its status) is younger than this
LOOP_CHECK_SECONDS = 3600.0
CACHE_SECONDS = 600.0

_cache: dict[str, Any] = {"at": None, "curves": {}}


def model_key(row: Mapping[str, Any]) -> tuple[str, str] | None:
    make, model = row.get("make"), row.get("model")
    if not isinstance(make, str) or not isinstance(model, str):
        return None
    return make.lower(), model.lower()


def invalidate_cache() -> None:
    _cache["at"] = None


async def cached_curves(params: Mapping[str, Any], *,
                        clock: Callable[[], float] = time.monotonic) -> dict[tuple[str, str], fv.Curve]:
    """The enabled curves, reloaded once CACHE_SECONDS passed; {} with mode 'off'. Never raises: a failed
    load keeps the previous curves and is retried after CACHE_SECONDS."""
    if not isinstance(params, Mapping) or params.get("mode") not in ON:
        return {}
    now = clock()
    if _cache["at"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["curves"]
    try:
        async with db.connection() as cx:
            curves = await repo.load_enabled(cx)
        _cache.update(at=now, curves=curves)
    except Exception:
        _cache["at"] = now
        warn_limited(log, "fair_value.cache", "could not load the fair value curves", exc_info=True)
    return _cache["curves"]


def fit_model(rows: list[dict[str, Any]], params: Mapping[str, Any], *, make: str, model: str,
              comparables: Mapping[str, Any], partial_pct: float, was_enabled: bool,
              fitted_at: datetime) -> tuple[fv.Curve | None, fv.Gate]:
    """Fit and gate one model (CPU only: run it in a thread)."""
    obs = fv.observations(rows)
    curve = fv.fit(obs, params, make=make, model=model)
    gate = fv.evaluate(curve, obs, params, comparables=comparables, partial_pct=partial_pct,
                       was_enabled=was_enabled)
    if curve is not None:
        curve = replace(curve, n=gate.n, enabled=gate.enabled, cv_err=gate.cv_err, cohort_err=gate.cohort_err,
                        fitted_at=fitted_at, params=str(params.get("params", "")))
    return curve, gate


def model_stats(make: str, model: str, curve: fv.Curve | None, gate: fv.Gate) -> dict[str, Any]:
    """One model of fair_value_runs.stats (§4.2)."""
    r = fv._r
    return {"make": make, "model": model, "n": gate.n, "sample": gate.sample, "cv_err": r(gate.cv_err),
            "cohort_err": r(gate.cohort_err), "enabled": gate.enabled, "guard_flips": gate.guard_flips,
            "fitted": curve is not None,
            "km_slope": r(curve.km_slope) if curve is not None else None,
            "a": {str(y): r(v["a"]) for y, v in sorted(curve.years.items())} if curve is not None else {}}


async def fit_all(*, trigger: str, dry_run: bool = False, only: tuple[str, str] | None = None) -> dict[str, Any]:
    """Fit every model (or `only` (make, model)). dry_run (tools/fair_value.py) writes nothing and runs
    whatever the mode. Never raises: a failure is returned and (unless dry_run) recorded."""
    params = fair_value_config(await db.get_config("fair_value"))
    result: dict[str, Any] = {"status": "ok", "run_id": None, "trigger": trigger, "params": params,
                              "models": [], "curves": {}, "error": None}
    if params["mode"] not in ON and not dry_run:
        result["status"] = "off"
        return result
    run_id: int | None = None
    try:
        cfg = await IntelligenceConfig.load()
        comparables = dict(cfg.comparables)
        partial_pct = float(cfg.curve("guards")["partial_pct"])
        fitted_at = datetime.now(timezone.utc)
        async with db.connection() as cx:
            if not dry_run:
                run_id = await repo.start_run(cx, trigger=trigger, params=params)
                result["run_id"] = run_id
            if only is not None:
                models = [{"make": only[0].lower(), "model": only[1].lower()}]
            else:
                models = await repo.models_to_fit(cx, min_listings=int(params["min_listings"]),
                                                  max_age_days=int(comparables["max_age_days"]))
            before = await repo.enabled_before(cx)
        fitted = enabled = failed = 0
        failed_keys: list[tuple[str, str]] = []
        for m in models:
            make, model = m["make"], m["model"]
            try:
                async with db.connection() as cx:
                    rows = await repo.pool(cx, make, model)
                curve, gate = await asyncio.to_thread(
                    fit_model, rows, params, make=make, model=model, comparables=comparables,
                    partial_pct=partial_pct, was_enabled=(make, model) in before, fitted_at=fitted_at)
                if curve is not None and not dry_run:
                    async with db.connection() as cx:
                        await repo.save_curve(cx, curve, run_id=run_id)
            except Exception:
                # One model must not sink the run: record it in its stats entry and go on.
                failed += 1
                failed_keys.append((make, model))
                error = traceback.format_exc()
                result["models"].append({"make": make, "model": model, "fitted": False, "enabled": False,
                                         "error": error[-2000:]})
                if not dry_run:
                    await log_error("fair_value", f"{make} {model}", error)
                continue
            result["models"].append(model_stats(make, model, curve, gate))
            if curve is None:
                continue
            fitted += 1
            enabled += int(curve.enabled)
            result["curves"][(make, model)] = curve
        result.update(models_seen=len(models), models_fitted=fitted, models_enabled=enabled, models_failed=failed)
        all_failed = bool(models) and failed == len(models)
        if all_failed:
            result.update(status="failed", error=f"every model failed ({failed})")
        if not dry_run and run_id is not None:
            async with db.connection() as cx:
                if only is None and not all_failed:
                    await repo.disable_unseen(cx, run_id=run_id, keep=failed_keys)
                await repo.finish_run(cx, run_id, status="failed" if all_failed else "ok",
                                      error=result["error"], models_seen=len(models), models_fitted=fitted,
                                      models_enabled=enabled, stats={"models": result["models"], "failed": failed})
                await repo.purge_runs(cx)
            invalidate_cache()
        log.info("fair_value %s: %d modelos, %d ajustados, %d habilitados, %d fallidos",
                 trigger, len(models), fitted, enabled, failed)
    except Exception:
        error = traceback.format_exc()
        result.update(status="failed", error=error)
        if not dry_run:
            await log_error("fair_value", trigger, error)
        if run_id is not None:
            try:
                async with db.connection() as cx:
                    await repo.finish_run(cx, run_id, status="failed", error=error[-4000:],
                                          stats={"models": result["models"]})
            except Exception:
                log.exception("could not record the failed fair_value run %s", run_id)
    return result


# ---------------------------------------------------------------------------
# The daily schedule
# ---------------------------------------------------------------------------

def next_slot(now: datetime, params: Mapping[str, Any]) -> datetime:
    """The next fair_value.schedule.hour ("HH:MM", Argentina) strictly after `now`."""
    hh, mm = (int(x) for x in str(params["schedule"]["hour"]).split(":"))
    local = now.astimezone(_AR)
    slot = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    return slot if slot > local else slot + timedelta(days=1)


async def _sleep(stop: asyncio.Event, seconds: float) -> bool:
    """Wait `seconds` or until `stop`; True when stopped."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(seconds, 0.0))
        return True
    except asyncio.TimeoutError:
        return False


async def due_trigger(params: Mapping[str, Any], now: datetime, last: datetime | None) -> str | None:
    """'schedule' when a slot fell between the previous look and now; else 'catchup' when the last ok run
    is older than 26 h (or there is none); else None. Reads the runs table only with the mode on."""
    if params.get("mode") not in ON:
        return None
    if last is not None and next_slot(last, params) <= now:
        return "schedule"
    async with db.connection() as cx:
        ok_at = await repo.last_ok_started_at(cx)
        any_at = await repo.last_started_at(cx)
    if any_at is not None and now - any_at < RETRY_AFTER:
        return None     # a failing run must not retry on every hourly wake-up; the daily slot still runs
    if ok_at is None or now - ok_at > STALE_AFTER:
        return "catchup"
    return None


async def fair_value_loop(stop: asyncio.Event, *, clock: Callable[[], datetime] | None = None,
                          check_every: float = LOOP_CHECK_SECONDS,
                          run: Callable[..., Awaitable[dict[str, Any]]] | None = None) -> None:
    """Fit at each daily slot and catch up a stale run. The config is read again at least every
    `check_every` seconds, so a mode or hour changed in /admin/config applies without a deploy.
    `clock` and `run` are injectable for the tests."""
    clock = clock or (lambda: datetime.now(_AR))
    last: datetime | None = None
    while not stop.is_set():
        wait = check_every
        try:
            params = fair_value_config(await db.get_config("fair_value"))
            now = clock()
            trigger = await due_trigger(params, now, last)
            if trigger is not None:
                await (run or fit_all)(trigger=trigger)
                now = clock()
            last = now
            if params["mode"] in ON:
                wait = min(check_every, (next_slot(now, params) - now).total_seconds())
        except Exception:
            await log_error("fair_value", "loop", traceback.format_exc())
        if await _sleep(stop, wait):
            return
