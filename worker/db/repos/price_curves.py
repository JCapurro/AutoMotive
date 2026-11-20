"""model_price_curves and fair_value_runs: the «valor justo» curves and the daily runs.

Spec docs/superpowers/specs/2026-11-20-valor-justo-design.md §4, migration 20270107120000_fair_value_shadow.
Only the worker reads and writes them (RLS without policies). Every function takes the caller's connection
and raises: pipeline/fair_value.py holds a connection only around these calls, never while fitting.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Iterable, Mapping

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from intelligence.fair_value import Curve

KEEP_RUNS_DAYS = 90


async def models_to_fit(cx: AsyncConnection, *, min_listings: int, max_age_days: int) -> list[dict[str, Any]]:
    """The cheap pass (§4.1): (make, model, count) with min_listings priced listings seen within max_age_days,
    without 'directo', biggest first. The pool's own rules come later, in price_pool."""
    rows = await (await cx.execute(
        "SELECT lower(make) AS make, lower(model) AS model, count(*)::int AS n FROM listings "
        " WHERE make IS NOT NULL AND model IS NOT NULL AND source <> 'directo' AND price_usd > 0 "
        "   AND NOT price_partial AND last_seen_at >= now() - make_interval(days => %s) "
        " GROUP BY 1, 2 HAVING count(*) >= %s ORDER BY 3 DESC, 1, 2",
        (int(max_age_days), int(min_listings)))).fetchall()
    return [dict(r) for r in rows]


async def pool(cx: AsyncConnection, make: str, model: str) -> list[dict[str, Any]]:
    """public.price_pool(make, model): what the fit and cohort_err read."""
    rows = await (await cx.execute(
        'SELECT id, probable_repost_of, year, "trim", transmission, mileage_km, price_usd '
        "  FROM public.price_pool(%s, %s)", (make, model))).fetchall()
    return [dict(r) for r in rows]


async def enabled_before(cx: AsyncConnection) -> set[tuple[str, str]]:
    """The models whose curve is enabled now: the gate keeps them until the disable margin."""
    rows = await (await cx.execute("SELECT make, model FROM model_price_curves WHERE enabled")).fetchall()
    return {(r["make"], r["model"]) for r in rows}


def _real(x: float | None) -> float | None:
    return x if x is not None and math.isfinite(x) else None


async def save_curve(cx: AsyncConnection, curve: Curve, *, run_id: int | None) -> None:
    """Upsert one model's row (every run overwrites it)."""
    await cx.execute(
        "INSERT INTO model_price_curves (make, model, curve, n, cv_err, cohort_err, enabled, params_hash, "
        "                                fitted_at, run_id) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()), %s) "
        "ON CONFLICT (make, model) DO UPDATE SET curve = excluded.curve, n = excluded.n, "
        "  cv_err = excluded.cv_err, cohort_err = excluded.cohort_err, enabled = excluded.enabled, "
        "  params_hash = excluded.params_hash, fitted_at = excluded.fitted_at, run_id = excluded.run_id",
        (curve.make.lower(), curve.model.lower(), Jsonb(curve.curve_json()), curve.n, _real(curve.cv_err),
         _real(curve.cohort_err), curve.enabled, curve.params, curve.fitted_at, run_id))


async def disable_unseen(cx: AsyncConnection, *, run_id: int) -> int:
    """A finished run disables the curves it did not fit (the model fell under min_listings): a stale
    curve must not keep valuing listings."""
    cur = await cx.execute(
        "UPDATE model_price_curves SET enabled = false WHERE enabled AND run_id IS DISTINCT FROM %s", (run_id,))
    return cur.rowcount or 0


async def load_enabled(cx: AsyncConnection) -> dict[tuple[str, str], Curve]:
    """The enabled curves by (make, model), for the scorer's cache."""
    rows = await (await cx.execute(
        "SELECT make, model, curve, n, cv_err, cohort_err, enabled, params_hash, fitted_at "
        "  FROM model_price_curves WHERE enabled")).fetchall()
    out: dict[tuple[str, str], Curve] = {}
    for r in rows:
        c = Curve.from_row(r)
        if c is not None:
            out[(c.make, c.model)] = c
    return out


async def load_curves(cx: AsyncConnection) -> list[dict[str, Any]]:
    """Every stored row (the report and the dry run read it)."""
    rows = await (await cx.execute(
        "SELECT make, model, n, cv_err, cohort_err, enabled, params_hash, fitted_at, run_id, curve "
        "  FROM model_price_curves ORDER BY n DESC, make, model")).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

async def start_run(cx: AsyncConnection, *, trigger: str, params: Mapping[str, Any]) -> int:
    row = await (await cx.execute(
        "INSERT INTO fair_value_runs (trigger, params, params_hash) VALUES (%s, %s, %s) RETURNING id",
        (trigger, Jsonb(dict(params)), params.get("params")))).fetchone()
    return int(row["id"])


async def finish_run(cx: AsyncConnection, run_id: int, *, status: str, error: str | None = None,
                     models_seen: int | None = None, models_fitted: int | None = None,
                     models_enabled: int | None = None, stats: Mapping[str, Any] | None = None) -> None:
    await cx.execute(
        "UPDATE fair_value_runs SET status = %s, finished_at = now(), error = %s, models_seen = %s, "
        "  models_fitted = %s, models_enabled = %s, stats = %s WHERE id = %s",
        (status, error, models_seen, models_fitted, models_enabled,
         Jsonb(dict(stats)) if stats is not None else None, run_id))


async def last_ok_started_at(cx: AsyncConnection) -> datetime | None:
    """When the latest run with status 'ok' started (the catch-up reads it)."""
    row = await (await cx.execute(
        "SELECT max(started_at) AS at FROM fair_value_runs WHERE status = 'ok'")).fetchone()
    return row["at"] if row else None


async def last_started_at(cx: AsyncConnection) -> datetime | None:
    """When the latest run started, whatever its status (the catch-up backs off after a failure)."""
    row = await (await cx.execute("SELECT max(started_at) AS at FROM fair_value_runs")).fetchone()
    return row["at"] if row else None


async def purge_runs(cx: AsyncConnection, *, days: int = KEEP_RUNS_DAYS) -> int:
    cur = await cx.execute("DELETE FROM fair_value_runs WHERE started_at < now() - make_interval(days => %s)",
                           (int(days),))
    return cur.rowcount or 0


async def runs(cx: AsyncConnection, *, since_days: int = 30) -> list[dict[str, Any]]:
    rows = await (await cx.execute(
        "SELECT id, started_at, finished_at, status, trigger, params_hash, models_seen, models_fitted, "
        "       models_enabled, stats FROM fair_value_runs "
        " WHERE started_at >= now() - make_interval(days => %s) ORDER BY started_at",
        (int(since_days),))).fetchall()
    return [dict(r) for r in rows]


def model_keys(rows: Iterable[Mapping[str, Any]]) -> list[tuple[str, str]]:
    return [(str(r["make"]), str(r["model"])) for r in rows]
