"""Bot de pocos resultados (docs/POCOS_RESULTADOS.md).

    searches with ≤ max_results results (any level)
      → their make/model's market of the last 30 days through the hard filters
        (intelligence/low_results.funnel)
      → LLM: why so few, from the funnel (fixed text if it fails)
      → search_diagnoses + one notice per set of filters (notifications/low_results.py)

Runs every LOW_RESULTS_TICK_SECONDS; app_config.low_results rules the rest.
A search is judged again when its filters change or after recheck_days, and
its diagnosis is deleted once it shows more results than the threshold.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import db
from db.repos import low_results as repo
from db.repos.config import get_config
from db.repos.fx import quote_for_today
from db.repos.listings import recent_active
from intelligence import low_results as lr
from llm.provider import LLMError, LLMProvider
from notifications import low_results as notice
from notifications.links import Links

log = logging.getLogger("low_results")

MARKET_DAYS = 30


def _profile(row: Mapping[str, Any]) -> dict[str, Any]:
    return {k: row.get(k) for k in ("id", "filters", "preferences", "origin_lat", "origin_lon", "radius_km")}


def due(row: Mapping[str, Any], fingerprint: str, cfg: Mapping[str, Any], now: datetime) -> bool:
    """Never diagnosed, filters changed since, or the diagnosis is older than recheck_days."""
    if not lr.eligible(row.get("filters") or {}):
        return False
    if row.get("fingerprint") != fingerprint or row.get("diagnosed_at") is None:
        return True
    return row["diagnosed_at"] <= now - timedelta(days=cfg["recheck_days"])


async def explain(provider: LLMProvider | None, context: dict[str, Any], fun: lr.Funnel,
                  profile: Mapping[str, Any]) -> tuple[str, list[str], str | None, str | None]:
    """(explanation, suggestions, provider name, error). The fixed text when
    the provider fails or has no explain_low_results."""
    if provider is not None and hasattr(provider, "explain_low_results"):
        try:
            out = await provider.explain_low_results(context)
            return out.explanation.strip(), [s.strip() for s in out.suggestions if s.strip()], provider.name, None
        except LLMError as e:
            error = str(e) or type(e).__name__
        except Exception as e:
            log.exception("low_results: LLM")
            error = type(e).__name__
    else:
        error = "sin proveedor LLM"
    return lr.fallback_text(fun, profile), [], None, error


async def diagnose(row: Mapping[str, Any], cfg: Mapping[str, Any], provider: LLMProvider | None,
                   fx_rate: float | None) -> dict[str, Any]:
    profile = _profile(row)
    f = profile["filters"] or {}
    market = await recent_active(f.get("make"), f.get("model"), days=MARKET_DAYS)
    fun = lr.funnel(market, profile, fx_rate=fx_rate)
    context = lr.llm_context(fun, profile, row["result_count"])
    explanation, suggestions, name, error = await explain(provider, context, fun, profile)
    return {"id": row["id"], "user_id": row["user_id"], "fingerprint": lr.fingerprint(profile),
            "result_count": row["result_count"], "max_results": cfg["max_results"], "funnel": fun.to_json(),
            "explanation": explanation[:2000], "suggestions": suggestions, "provider": name,
            "llm_error": error[:300] if error else None}


async def run_low_results(provider: LLMProvider | None, channels: Mapping[str, Any], links: Links, *,
                          now: datetime | None = None) -> int:
    """One pass. Returns how many searches were diagnosed."""
    cfg = lr.settings(await get_config("low_results", {}))
    if not cfg["enabled"]:
        return 0
    now = now or datetime.now(timezone.utc)
    resolved = await repo.clear_resolved()
    if resolved:
        log.info("low_results: %d búsquedas ya tienen más resultados", resolved)
    rows = await repo.candidates(max_results=cfg["max_results"], min_age_hours=cfg["min_age_hours"])
    todo = [(r, fp) for r in rows if due(r, fp := lr.fingerprint(_profile(r)), cfg, now)][:cfg["max_per_tick"]]
    if not todo:
        return 0
    async with db.connection() as cx:
        fx_rate = (await quote_for_today(cx)).rate
    done = 0
    for row, fp in todo:
        try:
            diagnosis = await diagnose(row, cfg, provider, fx_rate)
            await repo.save(diagnosis)
            done += 1
            log.info("low_results: profile=%s, %d resultados, mercado %d, %s", row["id"], row["result_count"],
                     diagnosis["funnel"]["market"], diagnosis["provider"] or "texto fijo")
            if cfg["notify"] and row.get("notified_fingerprint") != fp:
                if await notice.notify(row, diagnosis, channels, links, now):
                    await repo.mark_notified(row["id"], fp)
        except Exception:
            log.exception("low_results: profile=%s", row["id"])
    return done
