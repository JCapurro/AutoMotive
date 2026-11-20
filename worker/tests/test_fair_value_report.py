"""tools/fair_value_report: the «valor justo» go-live criteria (spec 2026-11-20-valor-justo-design.md §9). Pure."""
from __future__ import annotations

import math
import unittest
from datetime import datetime, timedelta, timezone

from tools import fair_value_report as rep

T0 = datetime(2026, 11, 21, 6, 30, tzinfo=timezone.utc)      # 03:30 ART
AUDIENCE = {"channels": ["email"], "frequency": "immediate", "min_level": "good"}


def fv(*, d=10.0, rule_h=True, fetched=True, params="p1", known=None, f2=None, budget=None) -> dict:
    block = {"v": "fv1", "params": params, "d": d, "rule_h": rule_h,
             "known": known or {"trim": True, "transmission": True, "km": True},
             "ref": {"fetched": fetched, "d": 8.0, "level_used": "model", "n": 40}}
    if f2 is not None:
        block["f2"] = f2
    if budget is not None:
        block["budget"] = budget
    return block


def match(i: int, *, price_ref=None, block=None, **kw) -> dict:
    row = {"id": i, "search_profile_id": 1, "user_id": "u1", "listing_id": 100 + i, "score": 75,
           "price_ref": price_ref if price_ref is not None else {"level_used": "model", "n": 40},
           "fv": block, "make": "ford", "model": "fiesta", "trim": "Titanium", "year": 2017,
           "mileage_km": 110_000, "price_usd": 10_000}
    row.update(kw)
    return row


def run(day: int, models, *, params="p1", hour=6) -> dict:
    return {"started_at": T0 + timedelta(days=day, hours=hour - 6), "params_hash": params,
            "stats": {"models": models}}


def model(a: dict, *, n=500, make="ford", name="fiesta") -> dict:
    return {"make": make, "model": name, "n": n, "a": a}


def decision(match_id: int, *, phase="card", decides=True, level="good", score=75, d=10.0, block=None,
             minutes=0, rid=None) -> dict:
    breakdown = {} if block is None else {"shadow_fair_value": block}
    return {"id": rid or match_id * 10 + minutes, "match_id": match_id, "search_profile_id": 1,
            "listing_id": 100 + match_id, "user_id": "u1", "phase": phase, "decided_at": T0 + timedelta(minutes=minutes),
            "f3_decides": decides, "f2_score": score, "f2_level": level, "f2_breakdown": breakdown,
            "price_ref": {"diff_pct": d, "level_used": "model", "n": 40}, "audience": AUDIENCE}


class CorrTests(unittest.TestCase):
    def test_pearson(self):
        self.assertAlmostEqual(rep.corr([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)
        self.assertAlmostEqual(rep.corr([1, 2, 3], [3, 2, 1]), -1.0)

    def test_none_under_three_pairs_or_without_variance(self):
        self.assertIsNone(rep.corr([1, 2], [1, 2]))
        self.assertIsNone(rep.corr([1, 1, 1], [1, 2, 3]))


class TwinsAndCoverageTests(unittest.TestCase):
    def test_has_twins(self):
        self.assertTrue(rep.has_twins({"level_used": "trim_transmission", "n": 5}))
        self.assertFalse(rep.has_twins({"level_used": "trim_transmission", "n": 4}))
        self.assertFalse(rep.has_twins({"level_used": "model", "n": 50}))
        self.assertFalse(rep.has_twins(None))

    def test_coverage_leaves_out_twins_and_not_fetched_references(self):
        rows = [match(1, block=fv()),                                                      # counted, covered
                match(2, block=None),                                                      # counted, not covered
                match(3, block=fv(), price_ref={"level_used": "trim_transmission", "n": 9}),  # twins: out
                match(4, block=fv(fetched=False))]                                         # not fetched: out
        self.assertEqual(rep.coverage(rows), (2, 1))


class BiasTests(unittest.TestCase):
    CURVES = {("ford", "fiesta"): {"trims": {"titanium": {"g": 0.1}, "s": {"g": -0.1}, "se": {"g": 0.0}},
                                   "years": {"2017": {"km": 100_000.0}}}}

    def test_correlations_over_the_rule_h_matches_with_known_trim_and_km(self):
        rows = [match(1, block=fv(d=20), trim="Titanium", mileage_km=150_000),
                match(2, block=fv(d=-20), trim="S", mileage_km=60_000),
                match(3, block=fv(d=0), trim="SE", mileage_km=100_000),
                match(4, block=fv(d=50, rule_h=False), trim="S"),                          # twins: out
                match(5, block=fv(d=50, fetched=False), trim="S"),                         # not fetched: out
                match(6, block=fv(d=50, known={"trim": False, "km": False}), trim="S")]    # unknown: out
        (g, ng), (k, nk) = rep.biases(rows, self.CURVES)
        self.assertEqual((ng, nk), (3, 3))
        self.assertAlmostEqual(g, 1.0)
        self.assertGreater(k, 0.9)

    def test_none_without_pairs(self):
        self.assertEqual(rep.biases([], self.CURVES), ((None, 0), (None, 0)))


class StabilityTests(unittest.TestCase):
    def test_median_move_between_consecutive_days(self):
        runs = [run(0, [model({"2017": 9.30, "2018": 9.40})]),
                run(1, [model({"2017": 9.31, "2018": 9.42})])]
        got, pairs = rep.stability(runs)
        self.assertEqual(pairs, 2)
        self.assertAlmostEqual(got, (math.exp(0.01) - 1 + math.exp(0.02) - 1) / 2, places=6)

    def test_only_consecutive_days_and_the_last_run_of_each(self):
        runs = [run(0, [model({"2017": 9.0})]),
                run(2, [model({"2017": 9.5})]),                         # a day skipped: no pair with day 0
                run(3, [model({"2017": 9.9})], hour=5),                 # replaced by the later run of day 3
                run(3, [model({"2017": 9.51})], hour=8)]
        got, pairs = rep.stability(runs)
        self.assertEqual(pairs, 1)
        self.assertAlmostEqual(got, math.exp(0.01) - 1, places=6)

    def test_small_models_and_other_params_left_out(self):
        runs = [run(0, [model({"2017": 9.3}), model({"2017": 9.0}, n=399, name="ka")]),
                run(1, [model({"2017": 9.4}), model({"2017": 9.9}, n=399, name="ka")]),
                run(1, [model({"2017": 1.0})], params="other", hour=9)]
        self.assertEqual(rep.stability(runs, params="p1")[1], 1)
        self.assertAlmostEqual(rep.stability(runs, params="p1")[0], math.exp(0.1) - 1, places=6)
        self.assertEqual(rep.stability([], params="p1"), (None, 0))


class DecideTests(unittest.TestCase):
    def test_deciding_rows(self):
        rows = [decision(1),                                                             # the card decides
                decision(2, decides=False), decision(2, phase="deferred", minutes=30),    # the later row decides
                decision(3, phase="deferred")]                                           # no card: out
        got = rep.deciding_rows(rows)
        self.assertEqual(sorted((r["match_id"], r["phase"]) for r in got), [(1, "card"), (2, "deferred")])

    def test_an_alert_lost_an_alert_gained_and_an_excluded_alternative(self):
        rows = [decision(1, level="good", block=fv(f2={"score": 60, "level": "match", "excluded": False})),
                decision(2, level="match", score=60, block=fv(f2={"score": 80, "level": "good", "excluded": False})),
                decision(3, level="good", block=fv(f2={"score": 80, "level": "good", "excluded": True})),
                decision(4, level="good", block=fv(rule_h=False)),                       # twins: today's
                decision(5, level="good", block=fv(params="other", f2={"level": "match", "score": 60}))]
        got = {d.row["match_id"]: d for d in rep.decide(rows, params="p1")}
        self.assertTrue(got[1].lost and not got[1].gained)
        self.assertTrue(got[2].gained and not got[2].lost)
        self.assertEqual((got[3].today, got[3].hybrid), ("queued", "none"))
        self.assertTrue(got[3].lost)
        self.assertEqual(got[4].today, got[4].hybrid)
        self.assertIsNone(got[5].fv)                                                     # another params: today's
        self.assertEqual(got[5].today, got[5].hybrid)


class BudgetTableTests(unittest.TestCase):
    def test_buckets_compare_inside_the_same_search_and_band(self):
        b = lambda ratio: {"usd": 11_000, "value_ratio": ratio, "price_ratio": ratio}
        rows = [match(1, block=fv(budget=b(0.5))), match(2, block=fv(budget=b(0.9))),
                match(3, block=fv(budget=b(1.2))), match(4, block=fv(budget=b(0.9))),
                match(5, block=fv(budget=b(0.9)), price_usd=12_000),             # over 102 % of the budget: out
                match(6, block=fv()),                                            # no budget: out
                match(7, search_profile_id=2, block=fv(budget=b(0.5)))]          # a search with no open: out
        opens = {("u1", 102), ("u1", 104)}
        table = {label: (opened, expected, ratio)
                 for label, opened, expected, ratio in rep.budget_table(rows, opens, "value_ratio", rep.VALUE_BUCKETS)}
        self.assertEqual(list(table), [label for _, label in rep.VALUE_BUCKETS])
        # Search 1, band c: 2 opens of 4 → 0.5 expected per listing.
        self.assertEqual(table["< 60 %"], (0, 0.5, 0.0))
        self.assertEqual(table["80–95 %"], (2, 1.0, 2.0))
        self.assertEqual(table["> 110 %"], (0, 0.5, 0.0))
        self.assertEqual(table["60–80 %"], (0, 0.0, None))
        price = {label for label, *_ in rep.budget_table(rows, opens, "price_ratio", rep.PRICE_BUCKETS)}
        self.assertEqual(price, {label for _, label in rep.PRICE_BUCKETS})


if __name__ == "__main__":
    unittest.main()
