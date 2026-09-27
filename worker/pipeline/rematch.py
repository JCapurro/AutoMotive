"""Bootstrap of new or edited profiles (sección 5.7).

A profile that was never bootstrapped, or whose filters changed
(`rematch_requested_at`), is matched against the active listings of the
last 30 days already stored. Those matches are backfill: the user sees them
in the web right away ("first value", §36), and they are never notified.

Matching and scoring are intelligence/'s (sección 6), the same the crawl
applies to new listings.
"""
from __future__ import annotations

import logging
import traceback

import db
from db.repos import matches as matches_repo
from db.repos.listings import recent_active
from db.repos.runs import log_error
from pipeline.scoring import Scorer


log = logging.getLogger("rematch")

BACKFILL_DAYS = 30


async def rematch_profile(alert: dict, scorer: Scorer | None = None) -> int:
    """Backfill one profile. Returns how many listings it matched."""
    rows = await recent_active(alert.get("make"), alert.get("model"), days=BACKFILL_DAYS,
                               sources=alert["profile"]["filters"].get("sources"))
    scorer = scorer or await Scorer.create()
    ids = [r["id"] for r in rows]
    await scorer.prepare(ids)
    scored = [(i, ev.row()) for i in ids if (ev := scorer.evaluate(i, alert["profile"])) is not None]
    async with db.connection() as cx:
        await matches_repo.upsert_scored(cx, alert["id"], scored, backfill=True)
    await db.mark_bootstrapped(alert["id"])
    return len(scored)


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
