"""f2 invariance of the «valor justo» shadow (spec 2026-11-20-valor-justo-design.md §4.4, §5, §10). Pure.

The block is added by pipeline/scoring.Scorer.evaluate after f2 is complete. With app_config.fair_value.mode
'off' the stored match row is exactly today's; with 'shadow' f2's score, level and price_ref do not change and
the only difference is score_breakdown.shadow_fair_value.
"""
from __future__ import annotations

import copy
import json
import logging
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

from intelligence import fair_value as fv
from intelligence.comparables import PriceRef
from intelligence.config import IntelligenceConfig
from intelligence.engine import assess, evaluate
from pipeline.scoring import Scorer
from test_f3_shadow_engine import matrix
from test_intelligence import FX, MARKET, NOW, fiesta_listing, fiesta_profile

OFF = IntelligenceConfig()
F3_ONLY = IntelligenceConfig.from_app_config({"score_model_f3": {"mode": "shadow"}})
SHADOW = IntelligenceConfig.from_app_config({"fair_value": {"mode": "shadow"}, "score_model_f3": {"mode": "shadow"}})
MODEL_REF = PriceRef(n=40, level_used="model", median=11_200.0, p25=10_400.0, p75=12_000.0, median_km=125_000.0,
                     diff_pct=(1 - 10_300 / 11_200) * 100)


def curve_for(a=9.30, enabled=True, **kw) -> fv.Curve:
    """A Ford Fiesta curve: about USD 11.000 for a 2017 Titanium with 110.000 km."""
    return fv.Curve(make="ford", model="fiesta",
                    years={2016: {"a": a - 0.07, "n": 40, "km": 125_000.0}, 2017: {"a": a, "n": 52, "km": 110_000.0},
                           2018: {"a": a + 0.07, "n": 31, "km": 95_000.0}},
                    trims={"titanium": {"g": 0.02, "n": 60}}, transmissions={"manual": {"h": -0.01, "n": 90}},
                    km_slope=-0.1, resid={"q25": -0.06, "q75": 0.06}, n=400, params="p", enabled=enabled,
                    fitted_at=datetime(2026, 11, 21, 6, 31, 2, tzinfo=timezone.utc), **kw)


def fiesta_case():
    listing, profile = fiesta_listing(), fiesta_profile()
    result, score, _ = assess(listing, profile, price_ref=MODEL_REF, cfg=SHADOW, now=NOW, fx_rate=FX)
    return listing, profile, result, MODEL_REF, score


def scorer(cfg, listing, ref, *, curve=None, fetched=True) -> Scorer:
    s = Scorer(cfg, FX, NOW, rows={listing["id"]: copy.deepcopy(listing)})
    if fetched:
        s.refs[listing["id"]] = ref
    if curve is not None:
        s.curves = {("ford", "fiesta"): curve}
    return s


def row_of(cfg, listing, profile, ref, **kw):
    ev = scorer(cfg, listing, ref, **kw).evaluate(listing["id"], copy.deepcopy(profile))
    return None if ev is None else ev.row()


def without(row, key="shadow_fair_value"):
    row = copy.deepcopy(row)
    row["score_breakdown"].pop(key, None)
    return row


class ModeOffTests(unittest.TestCase):
    def test_the_stored_row_is_todays(self):
        for name, listing, profile, ref in matrix():
            with self.subTest(name):
                today = evaluate(copy.deepcopy(listing), copy.deepcopy(profile), price_ref=ref, cfg=OFF, now=NOW,
                                 fx_rate=FX)
                today = None if today is None else today.row()
                self.assertEqual(row_of(OFF, listing, profile, ref), today)
                # A curve in the cache does nothing with the mode off.
                self.assertEqual(row_of(OFF, listing, profile, ref, curve=curve_for()), today)

    def test_mode_off_reads_no_curve(self):
        from pipeline import fair_value as job
        import asyncio

        async def go():
            with patch("db.connection", side_effect=AssertionError("no SQL with mode off")):
                return await job.cached_curves(OFF.fair_value)
        self.assertEqual(asyncio.run(go()), {})


class ShadowInvarianceTests(unittest.TestCase):
    def test_f2_score_level_and_price_ref_do_not_change(self):
        added = 0
        for name, listing, profile, ref in matrix():
            for fetched in (True, False):
                with self.subTest(name, fetched=fetched):
                    base = row_of(F3_ONLY, listing, profile, ref, fetched=fetched)
                    got = row_of(SHADOW, listing, profile, ref, curve=curve_for(), fetched=fetched)
                    if base is None:
                        self.assertIsNone(got)
                        continue
                    self.assertEqual(without(got), base)
                    self.assertEqual((got["score"], got["level"], got["price_ref"]),
                                     (base["score"], base["level"], base["price_ref"]))
                    block = got["score_breakdown"].get("shadow_fair_value")
                    if block is not None:
                        added += 1
                        json.dumps(got, allow_nan=False, default=str)
                        self.assertEqual(block["ref"]["fetched"], fetched)
        self.assertGreater(added, 10)

    def test_the_block(self):
        got = row_of(SHADOW, fiesta_listing(), fiesta_profile(), MODEL_REF, curve=curve_for())
        b = got["score_breakdown"]["shadow_fair_value"]
        self.assertEqual((b["v"], b["level"], b["n"], b["rule_h"]), ("fv1", "curve", 52, True))
        self.assertEqual(b["params"], SHADOW.fair_value["params"])
        self.assertEqual(b["fitted_at"], "2026-11-21T06:31:02Z")
        self.assertEqual(b["known"], {"trim": True, "transmission": True, "km": True})
        self.assertEqual(b["ref"], {"fetched": True, "d": round(MODEL_REF.diff_pct, 2), "level_used": "model", "n": 40})
        self.assertEqual(set(b["f2"]), {"score", "level", "guard", "excluded"})
        self.assertEqual(set(b["f3"]), {"score", "level"})
        self.assertAlmostEqual(b["d"], (1 - 10_300 / b["value"]) * 100, places=1)
        self.assertEqual(b["budget"]["usd"], 11_500)
        self.assertAlmostEqual(b["budget"]["price_ratio"], round(10_300 / 11_500, 4))

    def test_twins_keep_todays_reference_and_carry_no_alternative(self):
        b = row_of(SHADOW, fiesta_listing(), fiesta_profile(), MARKET, curve=curve_for())["score_breakdown"]["shadow_fair_value"]
        self.assertFalse(b["rule_h"])
        self.assertNotIn("f2", b)
        self.assertNotIn("f3", b)

    def test_no_curve_for_the_model_or_the_year_no_block(self):
        self.assertNotIn("shadow_fair_value",
                         row_of(SHADOW, fiesta_listing(), fiesta_profile(), MODEL_REF)["score_breakdown"])
        self.assertNotIn("shadow_fair_value",
                         row_of(SHADOW, fiesta_listing(year=2016), fiesta_profile(), MODEL_REF,
                                curve=replace(curve_for(), years={2018: {"a": 9.3, "n": 9, "km": None}}))["score_breakdown"])

    def test_the_alternative_uses_a_new_price_ref(self):
        # Today's d is 8 %; the curve values the car at ~USD 33.000: d ~69 %, an anticipo for f2's guard.
        b = row_of(SHADOW, fiesta_listing(), fiesta_profile(), MODEL_REF, curve=curve_for(a=10.4))["score_breakdown"]["shadow_fair_value"]
        self.assertGreater(b["d"], 65)
        self.assertEqual((b["f2"]["guard"], b["f2"]["excluded"]), ("partial", True))
        self.assertEqual(b["f3"]["level"], "excluded")
        sus = row_of(SHADOW, fiesta_listing(), fiesta_profile(), MODEL_REF, curve=curve_for(a=10.15))["score_breakdown"]["shadow_fair_value"]
        self.assertTrue(50 <= sus["d"] < 65, sus["d"])
        self.assertEqual((sus["f2"]["guard"], sus["f2"]["excluded"]), ("suspicious", False))
        self.assertNotEqual(sus["f2"]["level"], "high")


class FailureTests(unittest.TestCase):
    def test_a_failure_leaves_the_evaluation_without_the_block(self):
        base = row_of(F3_ONLY, fiesta_listing(), fiesta_profile(), MODEL_REF)
        for target in ("intelligence.fair_value.fair_value", "intelligence.fair_value.compute_score",
                       "intelligence.fair_value.budget"):
            with self.subTest(target), patch(target, side_effect=RuntimeError("boom")), \
                    self.assertLogs("intelligence.fair_value", logging.WARNING):
                from intelligence import f3
                f3._WARNED.clear()
                got = row_of(SHADOW, fiesta_listing(), fiesta_profile(), MODEL_REF, curve=curve_for())
                self.assertEqual(got, base)

    def test_the_scorer_guards_a_raising_shadow(self):
        base = row_of(F3_ONLY, fiesta_listing(), fiesta_profile(), MODEL_REF)
        from intelligence import f3
        f3._WARNED.clear()
        with patch("intelligence.fair_value.shadow", side_effect=RuntimeError("boom")), \
                self.assertLogs("pipeline.scoring", logging.WARNING):
            got = row_of(SHADOW, fiesta_listing(), fiesta_profile(), MODEL_REF, curve=curve_for())
        self.assertEqual(got, base)

    def test_an_f3_failure_keeps_the_rest(self):
        from intelligence import f3
        f3._WARNED.clear()
        with patch("intelligence.f3.assess_f3", side_effect=RuntimeError("boom")), \
                self.assertLogs("intelligence.fair_value", logging.WARNING):
            b = row_of(SHADOW, fiesta_listing(), fiesta_profile(), MODEL_REF, curve=curve_for())["score_breakdown"]["shadow_fair_value"]
        self.assertIsNone(b["f3"])
        self.assertIn("f2", b)


if __name__ == "__main__":
    unittest.main()
