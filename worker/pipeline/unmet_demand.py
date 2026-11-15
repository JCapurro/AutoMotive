"""Demanda insatisfecha (/admin/demand): the nightly job.

    searches with ≤ max_results results (db/repos/low_results.candidates, the
    low_results bot's own pick), by model
      → their make/model's market of the last 30 days through the hard filters
        (intelligence/low_results.funnel: the matching's own evaluate)
      → one admin_unmet_demand row each: results now, listings with each single
        filter relaxed, the cause
      → one admin_unmet_demand_run row: when, how long, and what the free
        plan's cap hides by level (admin_cap_hidden)

Runs every UNMET_DEMAND_TICK_SECONDS but works once a day, after
app_config.unmet_demand.hour (Argentina); the key ships off. Searches go in
batches of batch_size with a pause between batches, and a market is read once
per model and batch, so the collection lanes keep their connections.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

import db
from db.repos import low_results as candidates_repo
from db.repos import unmet_demand as repo
from db.repos.config import get_config
from db.repos.fx import quote_for_today
from db.repos.listings import recent_active
from intelligence import low_results as lr
from intelligence import unmet_demand as ud
from notifications.service import AR
from pipeline.low_results import MARKET_DAYS, _profile

log = logging.getLogger("unmet_demand")


def due(cfg: dict[str, Any], last: datetime | None, now: datetime) -> bool:
    """Today's slot has passed (Argentine time) and the last run was before it."""
    local = now.astimezone(AR)
    at_time = ud.slot(cfg["hour"])
    at = local.replace(hour=at_time.hour, minute=at_time.minute, second=0, microsecond=0)
    return local >= at and (last is None or last < at)


async def run_unmet_demand(*, now: datetime | None = None, force: bool = False) -> int:
    """One pass. Returns how many searches got a row; 0 when off or not due.
    `force` (tools, tests) ignores the switch and the hour."""
    cfg = ud.settings(await get_config("unmet_demand", {}))
    now = now or datetime.now(timezone.utc)
    if not force and not (cfg["enabled"] and due(cfg, await repo.last_run_at(), now)):
        return 0
    started, t0 = datetime.now(timezone.utc), time.monotonic()
    candidates = await candidates_repo.candidates(max_results=cfg["max_results"], min_age_hours=cfg["min_age_hours"])
    todo = [r for r in candidates if lr.eligible(r.get("filters") or {})]
    async with db.connection() as cx:
        fx_rate = (await quote_for_today(cx)).rate
    done = 0
    for i in range(0, len(todo), cfg["batch_size"]):
        if i:
            await asyncio.sleep(cfg["pause_seconds"])
        markets: dict[tuple[Any, Any], list[dict]] = {}
        rows = []
        for search in todo[i:i + cfg["batch_size"]]:
            try:
                f = search["filters"] or {}
                key = (f.get("make"), f.get("model"))
                if key not in markets:
                    markets[key] = await recent_active(*key, days=MARKET_DAYS)
                rows.append(ud.row(search, lr.funnel(markets[key], _profile(search), fx_rate=fx_rate)))
            except Exception:
                log.exception("unmet_demand: profile=%s", search["id"])
        await repo.upsert(rows, started)
        done += len(rows)
    removed = await repo.delete_older(started)
    hidden = await repo.cap_hidden()
    plan = await get_config("plan_limits", {}) or {}
    total = next((r for r in hidden if r["level"] is None), None)
    await repo.save_run(computed_at=started, duration_ms=int((time.monotonic() - t0) * 1000), searches=done,
                        skipped_model_less=len(candidates) - len(todo), max_results=cfg["max_results"],
                        min_age_hours=cfg["min_age_hours"], cap_enforced=bool(plan.get("enforced")),
                        hidden_by_level={r["level"]: int(r["matches"]) for r in hidden if r["level"]},
                        hidden_accounts=int(total["accounts"]) if total else 0)
    log.info("unmet_demand: %d búsquedas en %.1f s (%d filas viejas fuera, %d sin modelo)", done,
             time.monotonic() - t0, removed, len(candidates) - len(todo))
    return done
