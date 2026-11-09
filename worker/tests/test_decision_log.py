"""f3 shadow mode, the wiring (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §4.4, §11.3):
the decision log (notifications/decision_log.py) behind Notifier.on_matches, enrich.rescore_changed and the
sweeper, with fakes for the database.

f2 keeps deciding everything: with score_model_f3 off nothing changes and nothing touches the log; with
shadow the only f2 difference is score_breakdown.shadow_f3 (the decisions, ids and payloads are the same);
the rows are written once per (match, model, phase), and a failing, slow or missing log never reaches the
alerts. The rows go through db.repos.match_decisions.prepare, so they keep its column contract.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
import unittest
from contextlib import asynccontextmanager, contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import psycopg

from db.repos import match_decisions as repo
from intelligence import f3 as f3_module
from intelligence.config import DEFAULT_SCORE_MODEL_F3, SCORING_VERSION
from intelligence.engine import evaluate
from notifications import decision_log, engine, service
from notifications.engine import Audience, Event, Outcome, Rules
from pipeline import enrich
from pipeline.ingest import IngestResult, ListingEvent
from test_f3_shadow_engine import OFF, SHADOW, at, matrix, pref, ref_at
from test_intelligence import FX, MARKET, NOW, fiesta_listing, fiesta_profile
from tools import explain_match

SHADOW_CONFIG = {"score_model_f3": {**DEFAULT_SCORE_MODEL_F3, "mode": "shadow"}}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeStore:
    """public.match_decisions in memory, with the unique (match_id, model, phase) key and the insert's
    two rules (db/repos/match_decisions.insert). Every row goes through repo.prepare."""

    def __init__(self, *, table: bool = True, fail: BaseException | None = None, delay: float = 0.0) -> None:
        self.table, self.fail, self.delay = table, fail, delay
        self.rows: list[dict] = []
        self.states: dict[int, dict] = {}
        self.calls: list[str] = []
        self.connections = 0
        self.clock = NOW

    def _phases(self, match_id: int, model: str = "f2") -> set[str]:
        return {r["phase"] for r in self.rows if r["match_id"] == match_id and r["model"] == model}

    async def available(self, cx) -> bool:
        self.calls.append("available")
        return self.table

    async def insert(self, cx, rows) -> int:
        self.calls.append("insert")
        batch = [repo.prepare(r) for r in rows]
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail is not None:
            raise self.fail
        n = 0
        for r in batch:
            phases = self._phases(r["match_id"], r["model"])
            if r["phase"] in phases or (r["phase"] == "sweeper" and "deferred" in phases):
                continue
            if r["phase"] == "deferred" and "sweeper" in phases:
                r = {**r, "f3_decides": False}
            self.rows.append({**{c: r.get(c) for c in repo.COLUMNS}, "id": len(self.rows) + 1,
                              "decided_at": self.clock})
            n += 1
        return n

    async def cards_for_listings(self, cx, listing_ids, *, since, model="f2"):
        self.calls.append("cards_for_listings")
        ids = set(listing_ids)
        return [{**r, "has_sweeper": "sweeper" in self._phases(r["match_id"])} for r in self.rows
                if r["phase"] == "card" and r["model"] == model and r["listing_id"] in ids
                and r["decided_at"] >= since and "deferred" not in self._phases(r["match_id"])]

    async def due_sweeps(self, cx, *, before, since, limit=200, model="f2"):
        self.calls.append("due_sweeps")
        return [dict(r) for r in self.rows
                if r["phase"] == "card" and r["would_defer"] and r["model"] == model
                and since <= r["decided_at"] < before
                and not self._phases(r["match_id"]) & {"deferred", "sweeper"}][:limit]

    async def current_state(self, cx, match_ids):
        self.calls.append("current_state")
        return {m: s for m, s in self.states.items() if m in set(match_ids)}

    def phase(self, phase: str) -> dict[int, dict]:
        return {r["match_id"]: r for r in self.rows if r["phase"] == phase}


@contextmanager
def logging_to(store: FakeStore, config: dict | None = None):
    """The decision log on `store`, with `config` as app_config (default: score_model_f3 shadow)."""
    config = SHADOW_CONFIG if config is None else config
    reads: list[str] = []

    @asynccontextmanager
    async def connection():
        store.connections += 1
        yield object()

    async def get_config(key, default=None):
        reads.append(key)
        return config.get(key, default)

    decision_log.reset()
    f3_module._WARNED.clear()
    try:
        with patch.object(decision_log.db, "connection", connection), \
                patch.object(decision_log.db, "get_config", get_config), \
                patch.multiple(decision_log.repo, available=store.available, insert=store.insert,
                               cards_for_listings=store.cards_for_listings, due_sweeps=store.due_sweeps,
                               current_state=store.current_state):
            yield reads
    finally:
        decision_log.reset()
        f3_module._WARNED.clear()


AUDIENCE = {"user_id": "u1", "profile_name": "Fiesta", "channels": ["telegram", "web"], "telegram_chat_id": 1,
            "email": None, "frequency": "immediate", "min_level": "good", "threshold_pct": None,
            "threshold_usd": None, "total_cost": False, "contact_template": None, "contact_email": False}


def audiences_for(candidates, **per_profile) -> dict[int, dict]:
    return {c.profile_id: {**AUDIENCE, "profile_id": c.profile_id, **per_profile.get(str(c.profile_id), {})}
            for c in candidates}


async def notify(candidates, rows, *, audiences=None, hidden=(), existing=(), sent=None, caps=None,
                 spy: dict | None = None):
    """Notifier.on_matches with its repo faked and the real _commit / decide_all: (ids, decisions)."""
    notifier = service.Notifier({"telegram": object(), "web": object()})
    inserted: list = []

    async def insert_decisions(decisions):
        inserted.extend(decisions)
        return list(range(1, len(decisions) + 1))

    real = engine.decide_all

    def decide_all(events, rules, **kw):
        if spy is not None:
            spy.update(events=list(events), rules=rules, kw=kw)
        return real(events, rules, **kw)

    with patch.multiple(service.repo,
                        profile_audiences=AsyncMock(return_value=audiences_for(candidates) if audiences is None
                                                    else audiences),
                        interactions=AsyncMock(return_value={}), price_tracks=AsyncMock(return_value={}),
                        hidden_pairs=AsyncMock(return_value=set(hidden)),
                        existing_keys=AsyncMock(return_value=set(existing)),
                        sent_today=AsyncMock(return_value=dict(sent or {})),
                        alert_caps=AsyncMock(return_value=dict(caps or {})), insert_decisions=insert_decisions), \
            patch.object(service, "_min_n", AsyncMock(return_value=5)), \
            patch.object(service, "flag_order", AsyncMock(return_value=service.config.DEFAULT_FLAG_ORDER)), \
            patch.object(service, "_guides", AsyncMock(return_value=({}, 0))), \
            patch.object(service, "load_rules", AsyncMock(return_value=Rules())), \
            patch.object(service, "decide_all", decide_all):
        ids = await notifier.on_matches(candidates, rows, now=NOW)
    return ids, inserted


def candidates(cfg, cases=None):
    """The f3 matrix's matches as a crawl batch: one search per case, one user."""
    out, rows = [], {}
    for i, (name, listing, profile, ref) in enumerate(cases if cases is not None else matrix()):
        ev = evaluate(copy.deepcopy(listing), copy.deepcopy(profile), price_ref=ref, cfg=cfg, now=NOW,
                      fx_rate=FX, timing_belt=True)
        if ev is None:
            continue
        lid = 1000 + i
        out.append(service.MatchCandidate(profile_id=100 + i, listing_id=lid, match_id=5000 + i,
                                          evaluation=ev.row()))
        rows[lid] = {**copy.deepcopy(listing), "id": lid, "status": "active"}
    return out, rows


def fiesta_row(cfg=SHADOW, *, level=None, score=None, **listing):
    ev = evaluate(fiesta_listing(**listing), fiesta_profile(), price_ref=MARKET, cfg=cfg, now=NOW, fx_rate=FX).row()
    if level is not None:
        ev = {**ev, "level": level, "score": score}
    return ev


def cand(profile_id, listing_id, evaluation, *, match_id=None, repost=False):
    return service.MatchCandidate(profile_id=profile_id, listing_id=listing_id,
                                  match_id=match_id if match_id is not None else 10 * listing_id + profile_id,
                                  evaluation=evaluation, repost=repost)


def listing_row(listing_id, **kw):
    return {**fiesta_listing(**kw), "id": listing_id, "status": "active"}


# ---------------------------------------------------------------------------
# (1) mode off: nothing changes, nothing is logged
# (2) mode shadow: f2's outputs are the same but for score_breakdown.shadow_f3
# ---------------------------------------------------------------------------

class InvarianceTests(unittest.IsolatedAsyncioTestCase):
    async def test_mode_off_changes_nothing_and_never_touches_the_log(self):
        off, rows = candidates(OFF)
        self.assertGreater(len(off), 20)
        for c in off:
            # Byte for byte the f2 breakdown (Score.breakdown), as before the shadow.
            self.assertNotIn("shadow_f3", c.evaluation["score_breakdown"])
        store, spy = FakeStore(), {}
        with logging_to(store, {}) as reads:
            ids, decisions = await notify(off, rows, spy=spy)
        self.assertEqual((store.calls, store.connections, reads), ([], 0, []))
        # The same decisions decide_all gives without the trace (the code before the shadow).
        kw = {k: v for k, v in spy["kw"].items() if k != "outcomes"}
        self.assertEqual(engine.decide_all(spy["events"], spy["rules"], **kw), decisions)
        self.assertEqual(ids, list(range(1, len(decisions) + 1)))

    async def test_breakdown_json_is_byte_identical_with_mode_off(self):
        for name, listing, profile, ref in matrix():
            ev = evaluate(copy.deepcopy(listing), copy.deepcopy(profile), price_ref=ref, cfg=OFF, now=NOW, fx_rate=FX)
            if ev is not None:
                with self.subTest(case=name):
                    self.assertEqual(json.dumps(ev.row()["score_breakdown"]), json.dumps(ev.score.breakdown()))

    async def test_mode_shadow_only_adds_shadow_f3_and_decides_the_same(self):
        off, rows_off = candidates(OFF)
        shadow, rows_sh = candidates(SHADOW)
        self.assertEqual([c.match_id for c in shadow], [c.match_id for c in off])
        for a, b in zip(off, shadow):
            breakdown = dict(b.evaluation["score_breakdown"])
            self.assertIn("shadow_f3", breakdown)
            breakdown.pop("shadow_f3")
            self.assertEqual({**b.evaluation, "score_breakdown": breakdown}, a.evaluation)
        store_off, store_sh = FakeStore(), FakeStore()
        with logging_to(store_off, {}):
            ids_off, dec_off = await notify(off, rows_off)
        with logging_to(store_sh):
            ids_sh, dec_sh = await notify(shadow, rows_sh)
        self.assertEqual((ids_sh, dec_sh), (ids_off, dec_off))
        self.assertGreater(len(dec_sh), 10)
        self.assertEqual(store_off.rows, [])
        self.assertEqual(sorted(r["match_id"] for r in store_sh.rows), sorted(c.match_id for c in shadow))

    async def test_the_payload_only_gains_the_version_and_the_decision_reference(self):
        shadow, rows = candidates(SHADOW)
        by_listing = {c.listing_id: c.evaluation for c in shadow}
        with logging_to(FakeStore()):
            _, decisions = await notify(shadow, rows)
        for d in decisions:
            ev = by_listing[d.listing_id]
            match = dict(d.payload["match"])
            self.assertEqual(match.pop("scoring_version"), SCORING_VERSION)
            ref = ev["price_ref"]
            if ref:
                self.assertEqual(match.pop("price_ref"), {k: ref[k] for k in decision_log.PRICE_REF_KEYS})
            # What was there before the shadow: score, level and diff_pct with enough comparables.
            enough = ref and ref["n"] >= 5 and ref["median"]
            self.assertEqual(match, {"score": ev["score"], "level": ev["level"],
                                     "diff_pct": ref["diff_pct"] if enough else None})
            self.assertNotIn("shadow_f3", json.dumps(d.payload))


class MatchPayloadTests(unittest.TestCase):
    REF = {"n": 23, "level_used": "trim_transmission", "median": 11200.0, "p25": 10600.0, "p75": 11900.0,
           "median_km": 125000.0, "diff_pct": 8.04, "dealer_n": 0, "dealer_median": None}

    def test_keys(self):
        self.assertEqual(service.match_payload({"score": 88, "level": "high", "price_ref": self.REF,
                                                "scoring_version": "f2-v5-seller-margin"}, 5),
                         {"score": 88, "level": "high", "diff_pct": 8.04, "scoring_version": "f2-v5-seller-margin",
                          "price_ref": {"n": 23, "level_used": "trim_transmission", "median": 11200.0,
                                        "p25": 10600.0, "p75": 11900.0, "diff_pct": 8.04}})

    def test_only_when_present(self):
        # A price_drop audience row: no scoring_version; no reference at all → the old three keys.
        self.assertEqual(service.match_payload({"score": 81, "level": "good", "price_ref": None}, 5),
                         {"score": 81, "level": "good", "diff_pct": None})
        self.assertEqual(set(service.match_payload({"score": 81, "level": "good", "price_ref": self.REF}, 5)),
                         {"score", "level", "diff_pct", "price_ref"})

    def test_the_pro_threshold_still_reads_diff_pct_only_with_enough_comparables(self):
        few = {**self.REF, "n": 3}
        out = service.match_payload({"score": 88, "level": "high", "price_ref": few}, 5)
        self.assertIsNone(out["diff_pct"])
        self.assertEqual(out["price_ref"]["diff_pct"], 8.04)       # the raw reference is data, not the threshold
        event = Event(engine.MATCH, 1, Audience("u", threshold_pct=5), level="high", score=88, payload={"match": out})
        self.assertIsNone(engine.below_comparables(event))


# ---------------------------------------------------------------------------
# The card rows: f2's real decision, f3's hypothetical one
# ---------------------------------------------------------------------------

class CardRowTests(unittest.IsolatedAsyncioTestCase):
    async def scenario(self):
        high = fiesta_row()                                        # f2 🔥 89, f3 🔥 88
        self.assertEqual((high["level"], high["score_breakdown"]["shadow_f3"]["level"]), ("high", "high"))
        f2_match = fiesta_row(level="match", score=60)              # f2 coincidencia, f3 still 🔥
        cands = [
            cand(1, 1, high),                                       # queued opportunity
            cand(2, 2, f2_match),                                   # f2 below min level, f3 would alert
            cand(3, 3, high),                                       # hidden by the trial
            cand(4, 4, high),                                       # no audience
            cand(5, 5, high),                                       # notified before
            cand(6, 6, high),                                       # no channel
            cand(7, 7, high), cand(8, 7, fiesta_row(level="good", score=75)),   # two searches, one listing
            cand(9, 9, high),                                       # user u2, at the daily cap
            cand(10, 10, high),                                     # user u3, daily digest
            cand(11, 11, high),                                     # no listing row: no row
            cand(12, 12, high, repost=True),                        # a repost: new_match
        ]
        audiences = {c.profile_id: {**AUDIENCE, "profile_id": c.profile_id} for c in cands if c.profile_id != 4}
        audiences[6]["channels"] = []
        audiences[9]["user_id"] = "u2"
        audiences[10].update(user_id="u3", frequency="daily")
        rows = {i: listing_row(i) for i in (1, 2, 3, 4, 5, 6, 7, 9, 10, 12)}
        store = FakeStore()
        with logging_to(store):
            ids, decisions = await notify(cands, rows, audiences=audiences, hidden={("u1", 3)},
                                          existing={("u1", "match:5")}, sent={"u2": 10}, caps={"u2": 10})
        return store, ids, decisions

    async def test_one_row_per_candidate_with_both_decisions(self):
        store, ids, decisions = await self.scenario()
        cards = store.phase("card")
        got = {m: (r["f2_decision"], r["f2_reason"], r["f2_kind"], r["f3_decision"], r["f3_reason"], r["f3_kind"])
               for m, r in cards.items()}
        self.assertEqual(got, {
            11: ("queued", None, "opportunity", "queued", None, "opportunity"),
            22: ("none", "below_min_level", None, "queued", None, "opportunity"),
            33: ("none", "hidden_trial", None, "none", "hidden_trial", "opportunity"),
            44: ("none", "no_audience", None, "none", "no_audience", None),
            55: ("none", "dedupe_existing", "opportunity", "none", "dedupe_existing", "opportunity"),
            66: ("none", "no_channels", "opportunity", "none", "no_channels", "opportunity"),
            77: ("queued", None, "opportunity", "queued", None, "opportunity"),
            78: ("none", "dedupe_batch", "new_match", "queued", None, "opportunity"),     # f3 does not simulate it
            99: ("digest", "daily_cap", "opportunity", "queued", None, "opportunity"),    # f3 is never capped
            110: ("digest", "frequency", "opportunity", "digest", "frequency", "opportunity"),
            132: ("queued", None, "new_match", "queued", None, "new_match"),
        })
        self.assertNotIn(121, cards)                                # no listing row
        self.assertEqual(len(store.rows), 11)
        self.assertEqual(len(ids), len(decisions))

    async def test_what_a_card_row_carries(self):
        store, _, _ = await self.scenario()
        r = store.phase("card")[11]
        shadow = fiesta_row()["score_breakdown"]["shadow_f3"]
        self.assertEqual((r["model"], r["phase"], r["search_profile_id"], r["listing_id"], r["user_id"]),
                         ("f2", "card", 1, 1, "u1"))
        self.assertEqual((r["f2_version"], r["f2_score"], r["f2_level"]), (SCORING_VERSION, 89, "high"))
        self.assertNotIn("shadow_f3", r["f2_breakdown"])
        f2_breakdown = {k: v for k, v in fiesta_row()["score_breakdown"].items() if k != "shadow_f3"}
        self.assertEqual(r["f2_breakdown"], f2_breakdown)
        self.assertEqual(r["f3"], shadow)
        self.assertEqual((r["f3_version"], r["f3_params"], r["f3_level"], r["f3_level_uncapped"], r["f3_score"]),
                         ("f3-precio-encaje", shadow["params"], "high", "high", 88))
        self.assertEqual((r["f3_deal"], r["f3_deal_raw"], r["f3_r"], r["f3_d"], r["f3_d_eff"]),
                         (shadow["deal"]["value"], shadow["deal"]["raw"], shadow["deal"]["r"], shadow["deal"]["d"],
                          shadow["deal"]["d_eff"]))
        self.assertEqual((r["f3_fit_level"], r["f3_fit_score"], r["f3_flags"], r["f3_a_verificar"]),
                         (1.0, 1.0, [], []))
        self.assertEqual((r["f3_seller_capped"], r["agency_voice"], r["placeholder"], r["would_defer"]),
                         (False, None, False, False))
        self.assertTrue(r["f3_decides"])                            # nothing to wait for
        self.assertEqual(r["price_ref"], {k: MARKET.to_json()[k] for k in decision_log.PRICE_REF_KEYS})
        self.assertEqual((r["price"], r["currency"], r["price_usd"], r["price_partial"], r["title"], r["source"],
                          r["year"], r["enriched"], r["listing_status"]),
                         (10300.0, "USD", 10300.0, False, "Ford Fiesta Titanium 1.6 2017", "mercadolibre", 2017,
                          False, "active"))
        self.assertEqual(r["audience"], {"min_level": "good", "frequency": "immediate", "threshold_pct": None,
                                         "threshold_usd": None, "channels": ["telegram", "web"], "repost": False,
                                         "saved": False, "status": None, "margin_usd_low": None})
        self.assertIsNone(store.phase("card")[44]["user_id"])
        self.assertTrue(store.phase("card")[132]["audience"]["repost"])

    async def test_the_commit_gets_the_outcomes_and_the_trial_hidden_ones(self):
        notifier = service.Notifier({"web": object()})
        events = [Event(engine.MATCH, i, Audience("u1", channels=("web",)), level="high", score=88,
                        match_id=i, payload={"match": {}}) for i in (1, 2)]
        outcomes: dict = {}
        with patch.multiple(service.repo, hidden_pairs=AsyncMock(return_value={("u1", 2)}),
                            existing_keys=AsyncMock(return_value=set()), sent_today=AsyncMock(return_value={}),
                            alert_caps=AsyncMock(return_value={}), insert_decisions=AsyncMock(return_value=[7])), \
                patch.object(service, "load_rules", AsyncMock(return_value=Rules())):
            self.assertEqual(await notifier._commit(events, now=NOW, outcomes=outcomes), [7])
        self.assertEqual(outcomes, {id(events[0]): Outcome("queued", None, "opportunity", False),
                                    id(events[1]): Outcome("none", "hidden_trial")})

    async def test_everything_hidden_still_traced(self):
        notifier = service.Notifier({"web": object()})
        [event] = [Event(engine.MATCH, 1, Audience("u1", channels=("web",)), level="high", score=88)]
        outcomes: dict = {}
        with patch.object(service.repo, "hidden_pairs", AsyncMock(return_value={("u1", 1)})):
            self.assertEqual(await notifier._commit([event], outcomes=outcomes), [])
        self.assertEqual(outcomes, {id(event): Outcome("none", "hidden_trial")})

    def test_a_match_without_id_is_not_logged(self):
        c = service.MatchCandidate(1, 1, None, fiesta_row())
        self.assertIsNone(decision_log.card_row(decision_log.CardItem(c, None, listing_row(1), None), None))

    def test_an_odd_shadow_never_breaks_a_check_constraint(self):
        ev = fiesta_row()
        ev["score_breakdown"]["shadow_f3"] = {**ev["score_breakdown"]["shadow_f3"], "level": "top", "score": 140,
                                              "deal": {"value": float("nan"), "d": "8"}}
        event = Event(engine.MATCH, 1, Audience("u1", channels=("web",)), level="high", score=89,
                      payload={"match": {}})
        row = decision_log.card_row(decision_log.CardItem(cand(1, 1, ev), event, listing_row(1), AUDIENCE),
                                    Outcome("queued", None, "opportunity"))
        self.assertEqual((row["f3_level"], row["f3_score"], row["f3_deal"], row["f3_d"]), (None, None, None, None))
        self.assertEqual((row["f3_decision"], row["f3_reason"]), ("none", "f3_unavailable"))
        repo.prepare(row)                                            # still a valid row


class F3PlanTests(unittest.TestCase):
    def shadow(self, level, score, d_eff=8.0):
        return {"level": level, "score": score, "deal": {"d_eff": d_eff}}

    def event(self, **audience):
        kw = {k: audience.pop(k) for k in ("repost", "status", "saved") if k in audience}
        return Event(engine.MATCH, 1, Audience("u1", channels=("web",), **audience), level="good", score=75,
                     payload={"match": {"score": 75, "level": "good", "diff_pct": 25.0}}, **kw)

    def test_by_level(self):
        e = self.event()
        self.assertEqual(decision_log.f3_plan(e, self.shadow("high", 88)), ("queued", None, "opportunity"))
        self.assertEqual(decision_log.f3_plan(e, self.shadow("good", 75)), ("queued", None, "new_match"))
        self.assertEqual(decision_log.f3_plan(e, self.shadow("match", 60)), ("none", "below_min_level", None))
        self.assertEqual(decision_log.f3_plan(self.event(repost=True), self.shadow("high", 88)),
                         ("queued", None, "new_match"))
        self.assertEqual(decision_log.f3_plan(self.event(frequency="daily"), self.shadow("high", 88)),
                         ("digest", "frequency", "opportunity"))
        self.assertEqual(decision_log.f3_plan(self.event(status="discarded"), self.shadow("high", 88)),
                         ("none", "discarded", None))

    def test_without_a_usable_f3(self):
        for f3 in (None, {}, self.shadow("excluded", 0), self.shadow("top", 99), "x"):
            self.assertEqual(decision_log.f3_plan(self.event(), f3), ("none", "f3_unavailable", None))

    def test_the_pro_threshold_reads_d_eff_with_decision_4a(self):
        e = self.event(threshold_pct=20)                             # f2's payload: 25 % below
        kavak = self.shadow("good", 75, d_eff=16.0)                  # f3: 25 − 9
        self.assertEqual(decision_log.f3_plan(e, kavak, pro_deal_d=True),
                         ("digest", "threshold_not_reached", "new_match"))
        self.assertEqual(decision_log.f3_plan(e, kavak, pro_deal_d=False), ("queued", "threshold", "new_match"))
        self.assertEqual(decision_log.f3_plan(e, self.shadow("match", 60, d_eff=16.0)),
                         ("none", "below_min_level", None))
        self.assertEqual(decision_log.f3_plan(e, self.shadow("match", 60, d_eff=21.0)),
                         ("queued", "threshold", "new_match"))

    def test_f2s_event_is_never_touched(self):
        e = self.event(threshold_pct=20)
        before = copy.deepcopy(e.payload)
        decision_log.f3_plan(e, self.shadow("high", 90, d_eff=1.0))
        self.assertEqual((e.payload, e.level, e.score), (before, "good", 75))


# ---------------------------------------------------------------------------
# (3) once per (match, model, phase), and failures never reach the alerts
# ---------------------------------------------------------------------------

class CardFailureTests(unittest.IsolatedAsyncioTestCase):
    def batch(self):
        cands = [cand(1, 1, fiesta_row()), cand(2, 2, fiesta_row(level="good", score=75))]
        return cands, {1: listing_row(1), 2: listing_row(2)}

    async def test_a_retried_batch_adds_nothing(self):
        store = FakeStore()
        with logging_to(store):
            await notify(*self.batch())
            first = copy.deepcopy(store.rows)
            await notify(*self.batch(), existing={("u1", "match:1"), ("u1", "match:2")})
        self.assertEqual(store.rows, first)
        self.assertEqual([r["f2_decision"] for r in first], ["queued", "queued"])

    async def test_without_shadow_no_database_at_all(self):
        store = FakeStore()
        cands = [cand(1, 1, fiesta_row(OFF)), service.MatchCandidate(2, 2, 22, {"level": "high", "score": 88})]
        with logging_to(store) as reads:
            ids, decisions = await notify(cands, {1: listing_row(1), 2: listing_row(2)})
        self.assertEqual((store.calls, store.connections, reads), ([], 0, []))
        self.assertEqual(len(ids), len(decisions))

    async def test_a_failing_insert_is_swallowed_and_logged_once_per_window(self):
        store = FakeStore(fail=RuntimeError("db down"))
        with logging_to(store), self.assertLogs("decision_log", logging.WARNING) as logs:
            for _ in range(3):
                ids, decisions = await notify(*self.batch())
                self.assertEqual(ids, [1, 2, 3, 4])                  # two alerts × two channels
        self.assertEqual(store.calls.count("insert"), 3)             # a fast failure: no backoff
        self.assertEqual(len(logs.records), 1)
        self.assertIn("f2 is unaffected", logs.records[0].getMessage())

    async def test_a_bad_row_is_swallowed(self):
        store = FakeStore()
        with logging_to(store), patch.object(decision_log, "card_rows", side_effect=KeyError("x")), \
                self.assertLogs("decision_log", logging.WARNING):
            ids, _ = await notify(*self.batch())
        self.assertEqual((ids, store.rows), ([1, 2, 3, 4], []))

    async def test_one_odd_row_costs_only_itself(self):
        cands, rows = self.batch()
        cands[0].evaluation["score_breakdown"]["shadow_f3"]["flags"] = 5      # not a list
        store = FakeStore()
        with logging_to(store), self.assertLogs("decision_log", logging.WARNING) as logs:
            ids, _ = await notify(cands, rows)
        self.assertEqual(ids, [1, 2, 3, 4])
        self.assertEqual([r["match_id"] for r in store.rows], [cands[1].match_id])
        self.assertIn("a row could not be built", logs.records[0].getMessage())

    async def test_a_slow_database_never_holds_the_alerts(self):
        store = FakeStore(delay=5.0)
        with logging_to(store), patch.object(decision_log, "LOG_TIMEOUT_SECONDS", 0.05), \
                self.assertLogs("decision_log", logging.WARNING):
            started = time.monotonic()
            ids, _ = await notify(*self.batch())
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertEqual(ids, [1, 2, 3, 4])
            await notify(*self.batch())                              # backing off: not even a connection
        self.assertEqual((store.calls.count("insert"), store.connections), (1, 1))
        self.assertEqual(store.rows, [])

    async def test_a_slow_config_read_never_holds_the_alerts(self):
        """The config read is inside the same bound as the insert (a cold cache on a slow database)."""
        store = FakeStore()

        async def slow_config(key, default=None):
            await asyncio.sleep(5.0)
            return SHADOW_CONFIG.get(key, default)

        with logging_to(store), patch.object(decision_log.db, "get_config", slow_config), \
                patch.object(decision_log, "LOG_TIMEOUT_SECONDS", 0.05), \
                self.assertLogs("decision_log", logging.WARNING) as logs:
            started = time.monotonic()
            ids, _ = await notify(*self.batch())
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertEqual(ids, [1, 2, 3, 4])
        self.assertEqual((store.calls, store.rows), ([], []))
        self.assertIn("TimeoutError", logs.records[0].getMessage())

    async def test_a_missing_table_is_asked_once(self):
        store = FakeStore(table=False)
        with logging_to(store), self.assertLogs("decision_log", logging.WARNING) as logs:
            for _ in range(3):
                ids, _ = await notify(*self.batch())
                self.assertEqual(ids, [1, 2, 3, 4])
        self.assertEqual((store.calls, store.connections), (["available"], 1))
        self.assertIn("migration 20261212120000", logs.records[0].getMessage())

    async def test_undefined_table_turns_the_log_off_for_a_while(self):
        store = FakeStore(fail=psycopg.errors.UndefinedTable("relation \"public.match_decisions\" does not exist"))
        with logging_to(store), self.assertLogs("decision_log", logging.WARNING):
            await notify(*self.batch())
            await notify(*self.batch())
            self.assertEqual(await decision_log.sweep(), 0)
            self.assertEqual(await decision_log.record_deferred([1], now=SOON), 0)
        self.assertEqual(store.calls, ["available", "insert"])


# ---------------------------------------------------------------------------
# The detail phases: deferred (enrichment re-score) and sweeper (20 min)
# ---------------------------------------------------------------------------

def state_of(c: service.MatchCandidate, evaluation: dict, listing: dict, *, user_id="u1") -> dict:
    """A current_state row: the match as the re-score left it, with its listing."""
    return {"match_id": c.match_id, "search_profile_id": c.profile_id, "listing_id": c.listing_id,
            "user_id": user_id, "score": evaluation["score"], "level": evaluation["level"],
            "score_breakdown": evaluation["score_breakdown"], "price_ref": evaluation["price_ref"],
            "red_flags": evaluation["red_flags"], "scoring_version": evaluation["scoring_version"],
            "is_backfill": False, "updated_at": NOW, **{k: listing.get(k) for k in (
                "price", "currency", "price_usd", "price_partial", "title", "source", "year", "seller_type",
                "dealer_inferred", "enriched_at")}, "status": listing.get("status", "active")}


SOON = NOW + timedelta(minutes=5)          # the enrichment re-score, minutes after the card
FB_CARD = at(20, source="facebook", seller_type=None, enriched_at=None, description=None)
FB_DETAIL = {**FB_CARD, "seller_type": "private", "enriched_at": NOW, "description": "Recibimos tu usado, financiamos"}
PRIVATE = pref("private")
FB_REF = ref_at(20)


def fb_eval(listing):
    return evaluate(copy.deepcopy(listing), PRIVATE, price_ref=FB_REF, cfg=SHADOW, now=NOW, fx_rate=FX).row()


class LaterPhaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.store = FakeStore()
        self.card = fb_eval(FB_CARD)
        shadow = self.card["score_breakdown"]["shadow_f3"]
        self.assertTrue(shadow["would_defer"])                         # a seller preference, no seller yet
        self.wait = cand(1, 1, self.card)                              # waits for the detail
        self.wait2 = cand(2, 2, self.card)
        self.now_ = cand(3, 3, fiesta_row())                           # decided at the card
        self.rows = {1: {**FB_CARD, "id": 1, "status": "active"}, 2: {**FB_CARD, "id": 2, "status": "active"},
                     3: listing_row(3)}
        self.enterContext(logging_to(self.store))
        await notify([self.wait, self.wait2, self.now_], self.rows)
        self.cards = self.store.phase("card")
        self.assertEqual({m: r["f3_decides"] for m, r in self.cards.items()}, {11: False, 22: False, 33: True})
        self.assertEqual({m: r["would_defer"] for m, r in self.cards.items()}, {11: True, 22: True, 33: False})

    def detail(self, *cs):
        detail = fb_eval(FB_DETAIL)
        for c in cs:
            self.store.states[c.match_id] = state_of(c, detail, {**FB_DETAIL, "status": "active"})
        return detail

    async def test_the_deferred_row_is_f3s_decision_with_the_detail(self):
        detail = self.detail(self.wait)
        self.store.states[self.now_.match_id] = state_of(self.now_, fiesta_row(), listing_row(3))
        self.assertEqual(await decision_log.record_deferred([1, 3], now=SOON), 2)
        deferred = self.store.phase("deferred")
        d = deferred[11]
        self.assertEqual((d["f2_decision"], d["f2_reason"], d["f2_kind"]), (None, "f2_card_only", None))
        self.assertEqual((d["f2_score"], d["f2_level"]), (detail["score"], detail["level"]))
        self.assertEqual(d["f3"], detail["score_breakdown"]["shadow_f3"])
        self.assertEqual(d["agency_voice"], "recibimos tu usado")          # the detail's text: an agency
        self.assertTrue(d["f3_seller_capped"])
        self.assertEqual((d["f3_level"], d["f3_decision"], d["f3_reason"]), ("match", "none", "below_min_level"))
        self.assertEqual((d["enriched"], d["seller_type"], d["would_defer"]), (True, "private", False))
        self.assertTrue(d["f3_decides"])
        self.assertEqual(d["audience"], self.cards[11]["audience"])
        self.assertFalse(deferred[33]["f3_decides"])                       # the card had decided
        self.assertEqual(await decision_log.record_deferred([1, 3], now=SOON), 0)    # once per (match, model, phase)

    async def test_a_match_the_re_score_deleted(self):
        self.assertEqual(await decision_log.record_deferred([1], now=SOON), 1)
        d = self.store.phase("deferred")[11]
        self.assertEqual((d["f2_version"], d["f2_level"], d["f3_level"], d["f3_decision"], d["f3_reason"]),
                         (SCORING_VERSION, None, None, "none", "match_deleted"))
        self.assertEqual((d["f3_params"], d["f3_decides"]), (self.cards[11]["f3_params"], True))

    async def test_the_sweeper_decides_what_still_waits_after_20_minutes(self):
        self.detail(self.wait)
        self.store.states[self.wait2.match_id] = state_of(self.wait2, self.card, self.rows[2])
        await decision_log.record_deferred([1], now=SOON)
        self.assertEqual(await decision_log.sweep(now=NOW + timedelta(minutes=19)), 0)
        self.assertEqual(await decision_log.sweep(now=NOW + timedelta(minutes=21)), 1)
        [s] = self.store.phase("sweeper").values()
        self.assertEqual((s["match_id"], s["f3_decides"], s["f2_reason"]), (22, True, "f2_card_only"))
        # With what there is: no seller yet, so no 🔥 (seller_unknown), and the search's min level decides.
        self.assertIn("seller_unknown", s["f3_flags"])
        self.assertEqual(await decision_log.sweep(now=NOW + timedelta(minutes=22)), 0)
        # The detail after the sweeper: logged, but it no longer decides.
        self.detail(self.wait2)
        self.assertEqual(await decision_log.record_deferred([2], now=SOON), 1)
        self.assertFalse(self.store.phase("deferred")[22]["f3_decides"])

    async def test_only_cards_of_the_last_24_hours(self):
        self.assertEqual(await decision_log.record_deferred([1], now=NOW + timedelta(hours=25)), 0)
        self.assertEqual(await decision_log.sweep(now=NOW + timedelta(hours=25)), 0)

    async def test_a_failure_is_swallowed(self):
        with patch.object(decision_log.repo, "current_state", AsyncMock(side_effect=RuntimeError("boom"))), \
                self.assertLogs("decision_log", logging.WARNING):
            self.assertEqual(await decision_log.record_deferred([1], now=SOON), 0)
            self.assertEqual(await decision_log.sweep(now=NOW + timedelta(minutes=21)), 0)
        self.assertEqual(self.store.phase("deferred"), {})

    async def test_a_slow_config_read_is_inside_the_bound(self):
        """enrich.rescore_changed and the sweeper loop wait LOG_TIMEOUT_SECONDS at most, config reads included."""
        async def slow_config(key, default=None):
            await asyncio.sleep(5.0)
            return SHADOW_CONFIG.get(key, default)

        with patch.object(decision_log.db, "get_config", slow_config), \
                patch.object(decision_log, "LOG_TIMEOUT_SECONDS", 0.05), \
                self.assertLogs("decision_log", logging.WARNING):
            started = time.monotonic()
            self.assertEqual(await decision_log.record_deferred([1], now=SOON), 0)
            decision_log.reset()                                     # past the backoff, to time the sweep too
            self.assertEqual(await decision_log.sweep(now=NOW + timedelta(minutes=21)), 0)
            self.assertLess(time.monotonic() - started, 2.0)
        self.assertEqual((self.store.phase("deferred"), self.store.phase("sweeper")), ({}, {}))

    async def test_nothing_with_mode_off(self):
        store = FakeStore()
        for config in ({}, {"score_model_f3": {"mode": "off"}}, {"score_model_f3": "garbage"}):
            with logging_to(store, config):
                self.assertEqual(await decision_log.record_deferred([1, 2], now=SOON), 0)
                self.assertEqual(await decision_log.sweep(now=NOW + timedelta(minutes=21)), 0)
        self.assertEqual((store.calls, store.connections), ([], 0))

    async def test_no_listing_no_work(self):
        calls = list(self.store.calls)
        self.assertEqual(await decision_log.record_deferred([]), 0)
        self.assertEqual(self.store.calls, calls)


class LaterRowsTests(unittest.TestCase):
    def test_level_independent_drops_of_the_card_stay(self):
        card = {"match_id": 1, "search_profile_id": 2, "listing_id": 3, "user_id": "u1", "f2_version": "v",
                "f2_reason": "dedupe_existing", "would_defer": True, "has_sweeper": False,
                "audience": {"min_level": "good", "channels": ["web"]}}
        ev = fiesta_row()
        rows = decision_log.later_rows("deferred", [card], {1: {**ev, "match_id": 1, **listing_row(3)}})
        self.assertEqual((rows[0]["f3_decision"], rows[0]["f3_reason"], rows[0]["f3_kind"]),
                         ("none", "dedupe_existing", "opportunity"))
        no_audience = decision_log.later_rows("sweeper", [{**card, "f2_reason": "no_audience", "audience": None}],
                                              {1: {**ev, "match_id": 1}})
        self.assertEqual((no_audience[0]["f3_decision"], no_audience[0]["f3_reason"]), ("none", "no_audience"))
        for row in rows + no_audience:
            repo.prepare(row)


# ---------------------------------------------------------------------------
# The hooks
# ---------------------------------------------------------------------------

class HookTests(unittest.IsolatedAsyncioTestCase):
    async def test_rescore_changed_logs_what_it_re_scored(self):
        result = IngestResult(events=[ListingEvent("listing_updated", 7, "facebook", "a"),
                                      ListingEvent("price_drop", 8, "facebook", "b"),
                                      ListingEvent("listing_updated", 7, "facebook", "a")])
        with patch.object(enrich, "rescore_listings", AsyncMock(return_value=1)) as rescore, \
                patch.object(enrich.decision_log, "record_deferred", AsyncMock(return_value=0)) as record:
            self.assertEqual(await enrich.rescore_changed(result), 1)
        rescore.assert_awaited_once_with([7])
        record.assert_awaited_once_with([7])
        with patch.object(enrich, "rescore_listings", AsyncMock()) as rescore, \
                patch.object(enrich.decision_log, "record_deferred", AsyncMock()) as record:
            self.assertEqual(await enrich.rescore_changed(IngestResult()), 0)
        record.assert_not_awaited()

    async def test_a_failing_log_leaves_rescore_changed_as_it_was(self):
        result = IngestResult(events=[ListingEvent("listing_updated", 7, "facebook", "a")])
        store = FakeStore(fail=RuntimeError("down"))
        store.rows.append({**{c: None for c in repo.COLUMNS}, "id": 1, "match_id": 1, "search_profile_id": 1,
                           "listing_id": 7, "model": "f2", "phase": "card", "decided_at": NOW,
                           "f2_version": SCORING_VERSION, "f3_decides": True})
        with logging_to(store), patch.object(enrich, "rescore_listings", AsyncMock(return_value=3)), \
                patch.object(decision_log.repo, "cards_for_listings", AsyncMock(side_effect=RuntimeError("down"))), \
                self.assertLogs("decision_log", logging.WARNING):
            self.assertEqual(await enrich.rescore_changed(result), 3)

    def test_main_runs_the_sweeper_every_minute(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
        self.assertIn('_every("decision_sweeper", decision_log.SWEEP_TICK_SECONDS', text)
        self.assertEqual(decision_log.SWEEP_TICK_SECONDS, 60)
        self.assertEqual(decision_log.SWEEP_AFTER, timedelta(minutes=20))


class ExplainMatchTests(unittest.TestCase):
    def data(self, cfg):
        listing = {**fiesta_listing(), "external_id": "x", "url": "https://example.test/1"}
        scorer = SimpleNamespace(refs={1: MARKET}, cfg=cfg, now=NOW, fx_rate=FX)
        return explain_match.explain(listing, fiesta_profile(), scorer)

    def test_the_shadow_block(self):
        text = explain_match.render(self.data(SHADOW), None)
        self.assertIn("Sombra f3 (f3-precio-encaje", text)
        self.assertIn("no decide, f2 sigue decidiendo", text)
        self.assertIn("nivel 🔥 Alta oportunidad · score 88", text)
        self.assertIn("Opportunity Score 89", text)                  # f2's, unchanged

    def test_no_block_without_shadow(self):
        off = explain_match.render(self.data(OFF), None)
        self.assertNotIn("Sombra f3", off)
        shadow = explain_match.render(self.data(SHADOW), None)
        # The rest of the output is the same.
        start, end = shadow.index("Sombra f3"), shadow.index("Red flags")
        self.assertEqual(shadow[:start] + shadow[end:], off)

    def test_seller_and_alternatives(self):
        listing = {**FB_DETAIL, "id": 1, "external_id": "x", "url": "u"}
        scorer = SimpleNamespace(refs={1: FB_REF}, cfg=SHADOW, now=NOW, fx_rate=FX)
        lines = "\n".join(explain_match.shadow_lines(
            explain_match.explain(listing, PRIVATE, scorer)["score_breakdown"]["shadow_f3"]))
        self.assertIn("voz de agencia «recibimos tu usado»", lines)
        self.assertIn("tope aplicado", lines)
        self.assertIn("sin el tope de vendedor", lines)
        self.assertIn("alternativas: seller_cap_off", lines)


if __name__ == "__main__":
    unittest.main()
