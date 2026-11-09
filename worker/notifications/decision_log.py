"""The f3 shadow's decision log (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §4.4, §11.3).

    Notifier.on_matches ─────▶ record_card       'card':     f2's real decision, f3's hypothetical one
    enrich.rescore_changed ──▶ record_deferred   'deferred': again, after the enrichment re-score
    main.py, every minute ───▶ sweep             'sweeper':  20 min after a card that waits for the detail

One public.match_decisions row per fresh alert candidate per phase (db/repos/match_decisions.py:
insert-only, unique (match_id, model, phase), so a retried batch adds nothing). During the shadow the
model that decides is f2 (DECIDER): the f2 columns hold the decision it took (notifications.engine's
Outcome trace), the f3 columns the one f3 would have taken for the same audience, through the same
engine.classify with f3's level and score: a pure hypothesis (no daily cap, no batch dedupe). The
later phases re-read the match as the re-score left it (matches.score_breakdown.shadow_f3) and only
f3 decides there; `f3_decides` marks the row that is f3's decision in live semantics (the card, unless
the decision would wait for the detail; then the deferred row, or the sweeper's).

Nothing here may touch f2. Every entry point is a side channel that never raises (a failure is logged
at most every 10 minutes and swallowed), runs after f2 is done (the card rows after the notifications
transaction committed), in its own transaction, bounded as a whole (config reads, pool wait and
statements) by LOG_TIMEOUT_SECONDS (and the repo's 2 s statement timeout), and does no work at all
while app_config.score_model_f3.mode is 'off' (the code default: an un-migrated database behaves as
before) or the table is missing (cached for UNAVAILABLE_SECONDS). The card log does nothing at all (not even a config read) unless the batch's
evaluations carry score_breakdown.shadow_f3, which they only do with the mode on.

This module must not import notifications.service (which imports it).
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

import psycopg

import db
from db.repos import match_decisions as repo
from intelligence.config import DEFAULT_COMPARABLES, SCORING_VERSION, score_model_f3
from intelligence.f3 import LEVELS as F3_LEVELS, warn_limited
from intelligence.levels import ORDER
from notifications.engine import (DIGEST, MATCH, NONE, R_DEDUPE_EXISTING, R_DISCARDED, R_FREQUENCY,
                                  R_HIDDEN_TRIAL, R_NO_AUDIENCE, R_NO_CHANNELS, R_THRESHOLD,
                                  R_THRESHOLD_NOT_REACHED, Audience, Event, Outcome, Rules, classify,
                                  margin_low, why_not)

if TYPE_CHECKING:
    from notifications.service import MatchCandidate

log = logging.getLogger("decision_log")

SWEEP_TICK_SECONDS = 60                    # main.py runs sweep() this often (the live sweeper's minute)
SWEEP_AFTER = timedelta(minutes=20)        # a card that waits for the detail is decided by then (§4.1)
DEFERRED_WINDOW = timedelta(hours=24)      # later phases only for cards this recent (late re-reads stay out)
SWEEP_LIMIT = 200
DECIDER = "f2"                             # the model that decides during the shadow
CARD, DEFERRED, SWEEPER = "card", "deferred", "sweeper"
LOGGING_MODES = ("shadow", "live")         # 'live' behaves as 'shadow' until the live PR

LOG_TIMEOUT_SECONDS = 3.0                  # a whole log write: config reads, pool wait and statements
UNAVAILABLE_SECONDS = 600.0                # table missing (or not ours): look again after this
BACKOFF_SECONDS = 60.0                     # a slow or unreachable database: leave it alone this long
WARN_EVERY_SECONDS = 600.0

# Reasons of the log's own (the others are notifications.engine's R_*).
R_F2_CARD_ONLY = "f2_card_only"            # a later phase: f2 decided at the card and never again
R_F3_UNAVAILABLE = "f3_unavailable"        # no usable shadow_f3 (f3 failed, or an excluded level)
R_MATCH_DELETED = "match_deleted"          # the re-score deleted the match: it no longer fits

# f2 exits that do not depend on the level: f3 would have taken them too, with the same reason.
LEVEL_INDEPENDENT = frozenset({R_NO_AUDIENCE, R_HIDDEN_TRIAL, R_DEDUPE_EXISTING, R_NO_CHANNELS, R_DISCARDED})

# The decision's price reference (match_decisions.price_ref, and the notification payload's).
PRICE_REF_KEYS = ("n", "level_used", "median", "p25", "p75", "diff_pct")


@dataclass(frozen=True)
class CardItem:
    """One fresh candidate as Notifier.on_matches saw it: its event (None without an audience or a
    listing row), the listing row and the audience row (profile_audiences)."""
    candidate: "MatchCandidate"
    event: Event | None
    listing: Mapping[str, Any] | None
    audience: Mapping[str, Any] | None


# ---------------------------------------------------------------------------
# Pure builders
# ---------------------------------------------------------------------------

def shadow_of(evaluation: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """score_breakdown.shadow_f3 of a match row or an Evaluation.row(), or None."""
    breakdown = (evaluation or {}).get("score_breakdown") if isinstance(evaluation, Mapping) else None
    shadow = breakdown.get("shadow_f3") if isinstance(breakdown, Mapping) else None
    return dict(shadow) if isinstance(shadow, Mapping) else None


def price_ref_json(ref: Any) -> dict[str, Any] | None:
    """The decision's reference: n, level_used, median, p25, p75, diff_pct."""
    if not isinstance(ref, Mapping) or not ref:
        return None
    return {k: ref.get(k) for k in PRICE_REF_KEYS}


def payload_diff(ref: Any, min_n: int) -> float | None:
    """payload.match.diff_pct as notifications.service.match_payload writes it: only with enough
    comparables (the Pro threshold compares it)."""
    if not isinstance(ref, Mapping):
        return None
    diff = ref.get("diff_pct")
    if int(ref.get("n") or 0) < min_n or not ref.get("median") or diff is None:
        return None
    return _num(diff)


def audience_json(event: Event) -> dict[str, Any]:
    """What f3_plan needs to decide again in a later phase, as the card saw it."""
    a = event.audience
    return {"min_level": a.min_level, "frequency": a.frequency, "threshold_pct": a.threshold_pct,
            "threshold_usd": a.threshold_usd, "channels": list(a.channels), "repost": event.repost,
            "saved": event.saved, "status": event.status, "margin_usd_low": margin_low(event)}


def event_from(card: Mapping[str, Any], audience: Mapping[str, Any], *, level: str | None, score: Any,
               diff_pct: float | None) -> Event:
    """The card's MATCH event rebuilt from its logged audience (a later phase)."""
    a = Audience(user_id=str(card.get("user_id") or ""), channels=tuple(audience.get("channels") or ()),
                 frequency=audience.get("frequency") or "immediate", min_level=audience.get("min_level") or "good",
                 profile_id=card.get("search_profile_id"), threshold_pct=audience.get("threshold_pct"),
                 threshold_usd=audience.get("threshold_usd"))
    payload: dict[str, Any] = {"match": {"score": score, "level": level, "diff_pct": diff_pct}}
    if audience.get("margin_usd_low") is not None:
        payload["margin"] = {"usd_low": audience["margin_usd_low"]}
    return Event(MATCH, int(card["listing_id"]), a, level=level, score=score if isinstance(score, int) else None,
                 match_id=card.get("match_id"), repost=bool(audience.get("repost")),
                 saved=bool(audience.get("saved")), status=audience.get("status"), payload=payload)


def _plan_reason(event: Event, plan: Any) -> str | None:
    """notifications.engine._decided without the daily cap (f3 is never capped)."""
    a = event.audience
    if plan.threshold:
        return R_THRESHOLD
    if plan.status == DIGEST and (a.threshold_pct is not None or a.threshold_usd is not None):
        return R_THRESHOLD_NOT_REACHED
    if plan.status == DIGEST and a.frequency != "immediate":
        return R_FREQUENCY
    return None


def f3_plan(event: Event, f3: Mapping[str, Any] | None, rules: Rules | None = None, *,
            pro_deal_d: bool = True) -> tuple[str, str | None, str | None]:
    """(decision, reason, kind) engine.classify gives the same event with f3's level and score. No cap,
    no batch dedupe. With pro_deal_d (spec decision 4a) the Pro threshold reads f3's deal.d_eff instead
    of payload.match.diff_pct. f2's event is never modified (a replaced copy)."""
    level = f3.get("level") if isinstance(f3, Mapping) else None
    if level not in ORDER:
        return NONE, R_F3_UNAVAILABLE, None
    score = f3.get("score")
    score = score if isinstance(score, int) and not isinstance(score, bool) else None
    match = {**(event.payload.get("match") or {}), "level": level, "score": score}
    if pro_deal_d:
        deal = f3.get("deal")
        match["diff_pct"] = _num(deal.get("d_eff")) if isinstance(deal, Mapping) else None
    e3 = dataclasses.replace(event, level=level, score=score, payload={**event.payload, "match": match})
    rules = rules or Rules()
    plan = classify(e3, rules)
    if plan is None:
        return NONE, why_not(e3, rules), None
    return plan.status, _plan_reason(e3, plan), plan.kind


def f2_fields(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    """The f2 match as it stands: version, score, level, breakdown (without shadow_f3), flag ids."""
    breakdown = evaluation.get("score_breakdown")
    if isinstance(breakdown, Mapping):
        breakdown = {k: v for k, v in breakdown.items() if k != "shadow_f3"}
    flags = [f.get("id") if isinstance(f, Mapping) else f for f in evaluation.get("red_flags") or []]
    return {"f2_version": evaluation.get("scoring_version") or SCORING_VERSION,
            "f2_score": _score(evaluation.get("score")), "f2_level": _level(evaluation.get("level"), ORDER),
            "f2_breakdown": breakdown, "red_flags": [str(f) for f in flags if f is not None]}


def f3_fields(f3: Mapping[str, Any] | None) -> dict[str, Any]:
    """Every f3 intermediate the report recomputes alternatives from, plus the whole shadow_f3."""
    if not isinstance(f3, Mapping):
        return {"f3": None}
    deal = f3.get("deal") if isinstance(f3.get("deal"), Mapping) else {}
    fit = f3.get("fit") if isinstance(f3.get("fit"), Mapping) else {}
    seller = f3.get("seller") if isinstance(f3.get("seller"), Mapping) else {}
    return {"f3_version": _text(f3.get("v")), "f3_params": _text(f3.get("params")),
            "f3_score": _score(f3.get("score")), "f3_level": _level(f3.get("level"), F3_LEVELS),
            "f3_level_uncapped": _level(f3.get("level_uncapped"), F3_LEVELS),
            "f3_deal_raw": _num(deal.get("raw")), "f3_r": _num(deal.get("r")), "f3_deal": _num(deal.get("value")),
            "f3_d": _num(deal.get("d")), "f3_d_eff": _num(deal.get("d_eff")),
            "f3_fit_level": _num(fit.get("level")), "f3_fit_score": _num(fit.get("score")),
            "f3_flags": [str(x) for x in f3.get("flags") or []],
            "f3_a_verificar": [str(x) for x in f3.get("a_verificar") or []],
            "f3_seller_capped": _bool(seller.get("capped")), "agency_voice": _text(seller.get("agency_voice")),
            "placeholder": _bool(deal.get("placeholder")), "would_defer": _bool(f3.get("would_defer")),
            "f3": dict(f3)}


def listing_fields(listing: Mapping[str, Any] | None) -> dict[str, Any]:
    """What was known of the listing when deciding (a rows_for_scoring row, or current_state's)."""
    if not isinstance(listing, Mapping):
        return {}
    year = listing.get("year")
    return {"price": _num(listing.get("price")), "currency": _text(listing.get("currency")),
            "price_usd": _num(listing.get("price_usd")), "price_partial": _bool(listing.get("price_partial")),
            "title": _text(listing.get("title")), "source": _text(listing.get("source")),
            "year": year if isinstance(year, int) and not isinstance(year, bool) else None,
            "seller_type": _text(listing.get("seller_type")), "dealer_inferred": _bool(listing.get("dealer_inferred")),
            "enriched": listing.get("enriched_at") is not None, "listing_status": _text(listing.get("status"))}


def _f3_decision(event: Event | None, f3: Mapping[str, Any] | None, f2_reason: str | None, *,
                 pro_deal_d: bool) -> dict[str, Any]:
    """f3's columns of the decision: a level-independent f2 exit is copied (same reason, so the ratios
    compare like with like); otherwise f3_plan."""
    if event is None:
        return {"f3_decision": NONE, "f3_reason": R_NO_AUDIENCE, "f3_kind": None}
    decision, reason, kind = f3_plan(event, f3, pro_deal_d=pro_deal_d)
    if f2_reason in LEVEL_INDEPENDENT:
        decision, reason = NONE, f2_reason
    return {"f3_decision": decision, "f3_reason": reason, "f3_kind": kind}


def card_row(item: CardItem, outcome: Outcome | None, *, pro_deal_d: bool = True) -> dict[str, Any] | None:
    """The 'card' row of one candidate, or None (no match id, or no listing row: nothing to log)."""
    c = item.candidate
    if c.match_id is None or item.listing is None:
        return None
    ev = c.evaluation or {}
    f3 = shadow_of(ev)
    if item.event is None:
        outcome = Outcome(NONE, R_NO_AUDIENCE)
    f2 = ({"f2_decision": outcome.result, "f2_reason": outcome.reason, "f2_kind": outcome.kind}
          if outcome is not None else {"f2_decision": None, "f2_reason": "untraced", "f2_kind": None})
    return {
        "match_id": c.match_id, "search_profile_id": c.profile_id, "listing_id": c.listing_id,
        "user_id": str(item.audience["user_id"]) if item.audience and item.audience.get("user_id") else None,
        "model": DECIDER, "phase": CARD,
        # f3 decides at the card unless it would wait for the detail (spec §4.1).
        "f3_decides": not bool((f3 or {}).get("would_defer")),
        **f2_fields(ev), **f2, **f3_fields(f3),
        **_f3_decision(item.event, f3, f2["f2_reason"], pro_deal_d=pro_deal_d),
        "price_ref": price_ref_json(ev.get("price_ref")), **listing_fields(item.listing),
        "audience": audience_json(item.event) if item.event is not None else None,
    }


def card_rows(items: Iterable[CardItem], outcomes: Mapping[int, Outcome], *,
              pro_deal_d: bool = True) -> list[dict[str, Any]]:
    """One row per candidate (and per match: the first one wins). A candidate whose row can't be built
    is left out (logged), not the batch."""
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items:
        outcome = outcomes.get(id(item.event)) if item.event is not None else None
        row = _guarded(CARD, card_row, item, outcome, pro_deal_d=pro_deal_d)
        if row is None or row["match_id"] in seen:
            continue
        seen.add(row["match_id"])
        out.append(row)
    return out


def later_rows(phase: str, cards: Iterable[Mapping[str, Any]], states: Mapping[int, Mapping[str, Any]], *,
               min_n: int = DEFAULT_COMPARABLES["min_n"], pro_deal_d: bool = True) -> list[dict[str, Any]]:
    """'deferred' or 'sweeper' rows for card rows, from the matches as they are now (current_state).
    f2 does not decide again (f2_reason f2_card_only); f3 decides with the current shadow_f3 and the
    card's audience. A deferred row is f3's decision when the card waited and no sweeper decided
    first; a sweeper row always is. A match the re-score deleted: no levels, f3_reason match_deleted."""
    rows = (_guarded(phase, _later_row, phase, card, states, min_n=min_n, pro_deal_d=pro_deal_d) for card in cards)
    return [row for row in rows if row is not None]


def _guarded(phase: str, build: Any, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
    """build(...) checked against the table's contract (repo.prepare), or None, logged: one odd row
    never costs the batch its other rows."""
    try:
        row = build(*args, **kwargs)
        if row is not None:
            repo.prepare(row)
        return row
    except Exception as exc:
        warn_limited(log, f"decision_log.row.{phase}", "f3 decision log (%s): a row could not be built: %s: %s",
                     phase, type(exc).__name__, exc, every=WARN_EVERY_SECONDS, exc_info=exc)
        return None


def _later_row(phase: str, card: Mapping[str, Any], states: Mapping[int, Mapping[str, Any]], *,
               min_n: int, pro_deal_d: bool) -> dict[str, Any]:
    audience = card.get("audience") if isinstance(card.get("audience"), Mapping) else None
    decides = (bool(card.get("would_defer")) and not card.get("has_sweeper")) if phase == DEFERRED else True
    row: dict[str, Any] = {
        "match_id": card["match_id"], "search_profile_id": card["search_profile_id"],
        "listing_id": card["listing_id"], "user_id": card.get("user_id"), "model": DECIDER, "phase": phase,
        "f3_decides": decides, "f2_decision": None, "f2_kind": None, "f2_reason": R_F2_CARD_ONLY,
        "audience": dict(audience) if audience is not None else None,
    }
    state = states.get(card["match_id"])
    if state is None:
        row.update(f2_version=card.get("f2_version") or SCORING_VERSION, f3_decision=NONE,
                   f3_reason=R_MATCH_DELETED, f3_kind=None, f3_version=card.get("f3_version"),
                   f3_params=card.get("f3_params"))
        return row
    f3 = shadow_of(state)
    event = (event_from(card, audience, level=state.get("level"), score=state.get("score"),
                        diff_pct=payload_diff(state.get("price_ref"), min_n))
             if audience is not None else None)
    row.update(**f2_fields(state), **f3_fields(f3),
               **_f3_decision(event, f3, card.get("f2_reason"), pro_deal_d=pro_deal_d),
               price_ref=price_ref_json(state.get("price_ref")), **listing_fields(state))
    return row


# ---------------------------------------------------------------------------
# Never-raising entry points
# ---------------------------------------------------------------------------

_table: dict[str, Any] = {"ok": None, "until": 0.0}     # match_decisions there? (cached)
_paused_until = 0.0                                      # backoff after a slow or unreachable database


def reset() -> None:
    """Forget the cached table state and any backoff (tests)."""
    global _paused_until
    _table.update(ok=None, until=0.0)
    _paused_until = 0.0


def _closed() -> bool:
    now = time.monotonic()
    return now < _paused_until or (_table["ok"] is False and now < _table["until"])


async def _table_ok(cx: Any) -> bool:
    if _table["ok"] is not None and time.monotonic() < _table["until"]:
        return bool(_table["ok"])
    ok = await repo.available(cx)
    _table.update(ok=ok, until=time.monotonic() + UNAVAILABLE_SECONDS)
    if not ok:
        warn_limited(log, "decision_log.missing", "match_decisions is missing (migration 20261212120000 not "
                     "applied): the f3 shadow log is off; f2 is unaffected", every=WARN_EVERY_SECONDS)
    return ok


def _failed(phase: str, exc: BaseException) -> None:
    """Log (rate-limited) and back off where retrying soon would only cost time."""
    global _paused_until
    try:
        if isinstance(exc, (psycopg.errors.UndefinedTable, psycopg.errors.InsufficientPrivilege)):
            _table.update(ok=False, until=time.monotonic() + UNAVAILABLE_SECONDS)
        elif isinstance(exc, (TimeoutError, psycopg.errors.QueryCanceled, psycopg.OperationalError)):
            _paused_until = time.monotonic() + BACKOFF_SECONDS
    finally:
        warn_limited(log, f"decision_log.{phase}", "f3 decision log (%s) failed: %s: %s; f2 is unaffected",
                     phase, type(exc).__name__, exc, every=WARN_EVERY_SECONDS, exc_info=exc)


async def _settings() -> tuple[str, bool]:
    """(score_model_f3.mode, rules.pro_deal_d) from the cached app_config."""
    p = score_model_f3(await db.get_config("score_model_f3"))
    return p["mode"], bool(p["rules"]["pro_deal_d"])


async def _pro_deal_d() -> bool:
    try:
        return (await _settings())[1]
    except Exception:
        return True


async def _min_n() -> int:
    """comparables.min_n, as notifications.service._min_n reads it."""
    try:
        cfg = await db.get_config("comparables", {}) or {}
        return int(cfg.get("min_n", DEFAULT_COMPARABLES["min_n"]))
    except Exception:
        return int(DEFAULT_COMPARABLES["min_n"])


async def _insert(rows: Sequence[Mapping[str, Any]]) -> int:
    async with db.connection() as cx:
        if not await _table_ok(cx):
            return 0
        return await repo.insert(cx, rows)


async def _card(items: Sequence[CardItem], outcomes: Mapping[int, Outcome]) -> int:
    rows = card_rows(items, outcomes, pro_deal_d=await _pro_deal_d())
    if not rows:
        return 0
    n = await _insert(rows)
    if n:
        log.info("f3 shadow: %d card decision rows", n)
    return n


async def record_card(items: Sequence[CardItem], outcomes: Mapping[int, Outcome]) -> int:
    """The 'card' rows of a Notifier.on_matches batch, after its notifications committed. Rows
    inserted; never raises. No database work at all unless some evaluation carries shadow_f3.
    Everything that can wait on the database (the config read too) is inside one
    LOG_TIMEOUT_SECONDS bound: on_matches, and the crawl loop behind it, wait no longer."""
    try:
        if not any(shadow_of(i.candidate.evaluation) is not None for i in items) or _closed():
            return 0
        return await asyncio.wait_for(_card(items, outcomes), LOG_TIMEOUT_SECONDS)
    except Exception as exc:
        _failed(CARD, exc)
        return 0


async def _later(phase: str, now: datetime, listing_ids: Sequence[int], pro_deal_d: bool, min_n: int) -> int:
    async with db.connection() as cx:
        if not await _table_ok(cx):
            return 0
        if phase == DEFERRED:
            cards = await repo.cards_for_listings(cx, listing_ids, since=now - DEFERRED_WINDOW, model=DECIDER)
        else:
            cards = await repo.due_sweeps(cx, before=now - SWEEP_AFTER, since=now - DEFERRED_WINDOW,
                                          limit=SWEEP_LIMIT, model=DECIDER)
        if not cards:
            return 0
        states = await repo.current_state(cx, [c["match_id"] for c in cards])
        rows = later_rows(phase, cards, states, min_n=min_n, pro_deal_d=pro_deal_d)
        n = await repo.insert(cx, rows)
    if n:
        log.info("f3 shadow: %d %s decision rows", n, phase)
    return n


async def _later_phase(phase: str, now: datetime, listing_ids: Sequence[int]) -> int:
    mode, pro_deal_d = await _settings()
    if mode not in LOGGING_MODES:
        return 0
    return await _later(phase, now, listing_ids, pro_deal_d, await _min_n())


async def _run_later(phase: str, now: datetime | None, listing_ids: Sequence[int] = ()) -> int:
    """One bound for the whole phase, config reads included (enrich.rescore_changed waits on it)."""
    try:
        if _closed():
            return 0
        now = now or datetime.now(timezone.utc)
        return await asyncio.wait_for(_later_phase(phase, now, listing_ids), LOG_TIMEOUT_SECONDS)
    except Exception as exc:
        _failed(phase, exc)
        return 0


async def record_deferred(listing_ids: Iterable[int], *, now: datetime | None = None) -> int:
    """The 'deferred' rows after the enrichment re-score of these listings (pipeline/enrich.py
    rescore_changed): their card rows of the last 24 h without one yet. Rows inserted; never raises."""
    try:
        ids = sorted({int(i) for i in listing_ids or ()})
    except Exception as exc:
        _failed(DEFERRED, exc)
        return 0
    if not ids:
        return 0
    return await _run_later(DEFERRED, now, ids)


async def sweep(*, now: datetime | None = None) -> int:
    """The 'sweeper' rows: cards that wait for the detail, decided 20 min ago or more (and within
    24 h), with neither a deferred nor a sweeper row. Rows inserted; never raises."""
    return await _run_later(SWEEPER, now)


# ---------------------------------------------------------------------------
# Small coercions (a row must never fail a check constraint because of one odd value)
# ---------------------------------------------------------------------------

def _num(x: Any) -> float | None:
    if isinstance(x, bool) or not isinstance(x, (int, float, Decimal)):
        return None
    try:
        value = float(x)
    except (ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _score(x: Any) -> int | None:
    value = _num(x)
    return int(round(value)) if value is not None and 0 <= value <= 100 else None


def _level(x: Any, allowed: Sequence[str]) -> str | None:
    return x if isinstance(x, str) and x in allowed else None


def _bool(x: Any) -> bool | None:
    return x if isinstance(x, bool) else None


def _text(x: Any) -> str | None:
    return None if x is None else str(x)


__all__ = ["CARD", "DECIDER", "DEFERRED", "DEFERRED_WINDOW", "SWEEPER", "SWEEP_AFTER", "SWEEP_TICK_SECONDS",
           "CardItem", "audience_json", "card_row", "card_rows", "event_from", "f2_fields", "f3_fields",
           "f3_plan", "later_rows", "listing_fields", "payload_diff", "price_ref_json", "record_card",
           "record_deferred", "reset", "shadow_of", "sweep"]
