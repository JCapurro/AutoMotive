"""Bootstrap of new or edited profiles (sección 5.7).

A profile that was never bootstrapped, or whose filters changed
(`rematch_requested_at`), is matched against the active listings of the
last 30 days already stored. Those matches are backfill: the user sees them
in the web right away ("first value", §36), and they are never notified.
An edited profile's earlier matches the backfill didn't score again are
re-checked like the nightly re-score does: the ones that no longer fit (a
place added, a lower price cap) are deleted at once, not hours later.

Matching and scoring are intelligence/'s (sección 6), the same the crawl
applies to new listings.

A search without a model, only by body type (docs/CARROCERIA.md), is matched
against the stored listings of its body types, from every source, with the
year, km and price it can't want left out in SQL (recent_active_by_body).
A listing a detail page gives the body type it lacked is matched against
those searches the same way, as backfill (match_model_less).
"""
from __future__ import annotations

import logging
import traceback
from typing import Iterable

import db
from db.repos import matches as matches_repo
from db.repos.listings import recent_active, recent_active_by_body
from db.repos.profiles import model_less_alerts
from db.repos.runs import log_error
from intelligence.matching import filter_currency, model_less, wanted_body_types
from pipeline.rescore import rescore
from pipeline.scoring import Scorer


log = logging.getLogger("rematch")

BACKFILL_DAYS = 30
# A search without a model can match thousands of stored listings: only the
# newest this many that pass its filters get comparables (one SQL call each,
# while the crawl tick waits); the rest are backfill without a price
# reference until the nightly re-score.
MODEL_LESS_COMPARABLES = 300


def _number(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


async def _candidates(filters: dict, scorer: Scorer) -> list[dict]:
    """The stored listings a profile's backfill scores."""
    if not model_less(filters):
        return await recent_active(filters.get("make"), filters.get("model"), days=BACKFILL_DAYS,
                                   sources=filters.get("sources"))
    body_types = wanted_body_types(filters)
    if not body_types:
        return []       # without a vehicle and a body type, it matches nothing
    price_max = _number(filters.get("price_max"))
    year_min, year_max, km_max = (_number(filters.get(k)) for k in ("year_min", "year_max", "km_max"))
    return await recent_active_by_body(
        body_types, days=BACKFILL_DAYS, sources=filters.get("sources"),
        year_min=int(year_min) if year_min is not None else None,
        year_max=int(year_max) if year_max is not None else None,
        km_max=int(km_max) if km_max is not None else None,
        price_max=price_max,
        currency=filter_currency(price_max, filters.get("currency")) if price_max is not None else "USD",
        fx_rate=scorer.fx_rate)


async def rematch_profile(alert: dict, scorer: Scorer | None = None) -> int:
    """Backfill one profile. Returns how many listings it matched."""
    scorer = scorer or await Scorer.create()
    filters = alert["profile"]["filters"]
    rows = await _candidates(filters, scorer)
    ids = [r["id"] for r in rows]                     # newest first
    if model_less(filters):
        # The hard filters don't need comparables: run them first.
        await scorer.prepare(ids, refs_limit=0)
        ids = [i for i in ids if scorer.evaluate(i, alert["profile"]) is not None]
        await scorer.prepare(ids, refs_limit=MODEL_LESS_COMPARABLES)
    else:
        await scorer.prepare(ids)
    scored = [(i, ev.row()) for i in ids if (ev := scorer.evaluate(i, alert["profile"])) is not None]
    async with db.connection() as cx:
        await matches_repo.upsert_scored(cx, alert["id"], scored, backfill=True)
    kept = {i for i, _ in scored}
    await rescore([q for q in await matches_repo.matches_of_profile(alert["id"]) if q["listing_id"] not in kept],
                  scorer)
    await db.mark_bootstrapped(alert["id"])
    return len(scored)


async def match_model_less(listing_ids: Iterable[int], scorer: Scorer | None = None) -> int:
    """Match listings against every search without a model, as backfill: the
    ones a detail page gave the body type they lacked (pipeline/enrich.py). An
    unknown body type fails those searches, so their batch never matched them.
    Like the re-score of an enrichment pass, nothing is notified and a search
    is never marked bootstrapped here. Returns how many matches were written."""
    ids = list(dict.fromkeys(listing_ids))
    alerts = await model_less_alerts() if ids else []
    if not alerts:
        return 0
    scorer = scorer or await Scorer.create()
    await scorer.prepare(ids)
    written = 0
    for alert in alerts:
        scored = [(i, ev.row()) for i in ids if (ev := scorer.evaluate(i, alert["profile"])) is not None]
        if not scored:
            continue
        try:
            async with db.connection() as cx:
                await matches_repo.upsert_scored(cx, alert["id"], scored, backfill=True)
            written += len(scored)
        except Exception:
            await log_error("rematch", f"profile:{alert['id']}", traceback.format_exc())
    if written:
        log.info("%d listings with a new body type: %d backfill matches without a model", len(ids), written)
    return written


async def run_pending() -> int:
    """Bootstrap every profile that needs it. Returns how many were processed."""
    pending = await db.pending_rematch()
    if not pending:
        return 0
    scorer = await Scorer.create()
    done = 0
    for alert in pending:
        try:
            n = await rematch_profile(alert, scorer)
            log.info("profile=%s rematch: %d backfill matches", alert["id"], n)
            done += 1
        except Exception:
            await log_error("rematch", f"profile:{alert['id']}", traceback.format_exc())
    return done
