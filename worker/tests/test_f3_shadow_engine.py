"""f2 invariance of the f3 shadow hook in intelligence.engine.assess (spec §11.3: f2 keeps deciding). Pure.

With app_config.score_model_f3.mode 'shadow', every f2 output of an evaluation is the same as with 'off':
the only difference is score_breakdown.shadow_f3, and only for matches.
"""
from __future__ import annotations

import copy
import logging
import unittest
from datetime import timedelta
from unittest.mock import patch

from intelligence import f3
from intelligence.comparables import PriceRef
from intelligence.config import SCORING_VERSION, IntelligenceConfig
from intelligence.engine import assess, evaluate
from test_intelligence import FX, MARKET, NOW, SellerPreferencePinTests, fiesta_listing, fiesta_profile


OFF = IntelligenceConfig()
SHADOW = IntelligenceConfig.from_app_config({"score_model_f3": {"mode": "shadow"}})


def ref_at(d, n=23, level_used="trim_transmission"):
    return PriceRef(n=n, level_used=level_used, median=11_200.0, p25=10_600.0, p75=11_900.0,
                    median_km=125_000.0, diff_pct=d)


def at(d, **kw):
    usd = round(11_200 * (1 - d / 100), 2)
    return fiesta_listing(**{"price": usd, "price_usd": usd, **kw})


def pref(seller):
    p = fiesta_profile()
    if seller:
        p["preferences"]["seller_type"] = seller
    return p


STRICT = fiesta_profile(seller_types=["private"]) | {"seller_filter": True}


def matrix():
    """(name, listing, profile, ref): every kind of case f3 treats apart, and f2's pinned seller cases."""
    cases = [("fiesta", fiesta_listing(), fiesta_profile(), MARKET),
             ("fiesta model ref", fiesta_listing(), fiesta_profile(), ref_at(8.0357, level_used="model"))]
    for (seller, name) in SellerPreferencePinTests.PINNED:
        cases.append((f"pinned {seller}/{name}", fiesta_listing(**SellerPreferencePinTests.LISTINGS[name]),
                      pref(seller), MARKET))
    cases += [
        ("unknown transmission", fiesta_listing(transmission=None), fiesta_profile(), MARKET),
        ("every hard unknown", fiesta_listing(year=None, mileage_km=None, transmission=None, price=None,
                                              price_usd=None), fiesta_profile(), ref_at(None)),
        ("55 % below", at(55), fiesta_profile(), ref_at(55)),
        ("47 % below", at(47), fiesta_profile(), ref_at(47)),
        ("73 % below (excluded)", at(73), fiesta_profile(), ref_at(73)),
        ("price partial (excluded)", fiesta_listing(price_partial=True, price_partial_reason="anticipo"),
         fiesta_profile(), MARKET),
        ("placeholder USD 11.111", fiesta_listing(price=11_111.0, price_usd=11_111.0), fiesta_profile(), ref_at(0.8)),
        ("kavak", at(9, source="kavak", seller_type="dealer"), fiesta_profile(), ref_at(9)),
        ("fb card without seller", at(20, source="facebook", seller_type=None, enriched_at=None, description=None),
         pref("private"), ref_at(20)),
        ("fb detail with agency voice", at(20, source="facebook", seller_type="private", enriched_at=NOW,
                                           description="Recibimos tu usado, financiamos"), pref("private"), ref_at(20)),
        ("strict seller unknown", fiesta_listing(seller_type=None), STRICT, MARKET),
        ("strict seller other (no match)", fiesta_listing(seller_type="dealer"), STRICT, MARKET),
        ("no year", fiesta_listing(year=None), fiesta_profile(), MARKET),
        ("n 7", fiesta_listing(), fiesta_profile(), ref_at(8.0357, n=7)),
        ("n 3 (no comparables)", fiesta_listing(), fiesta_profile(), ref_at(8.0, n=3)),
        ("no reference", fiesta_listing(), fiesta_profile(), None),
        ("other model (no match)", fiesta_listing(model="Focus"), fiesta_profile(), MARKET),
        ("above the market", at(-15), fiesta_profile(), ref_at(-15)),
    ]
    return cases


def run(listing, profile, ref, cfg):
    return assess(copy.deepcopy(listing), copy.deepcopy(profile), price_ref=ref, cfg=cfg, now=NOW, fx_rate=FX,
                  timing_belt=True)


class InvarianceTests(unittest.TestCase):
    def test_every_f2_output_is_the_same_with_mode_off_and_shadow(self):
        shadowed = 0
        for name, listing, profile, ref in matrix():
            with self.subTest(case=name):
                r_off, s_off, ev_off = run(listing, profile, ref, OFF)
                r_sh, s_sh, ev_sh = run(listing, profile, ref, SHADOW)
                off, sh = ev_off.row(), ev_sh.row()
                self.assertNotIn("shadow_f3", off["score_breakdown"])
                self.assertIsNone(ev_off.shadow_f3)
                if r_sh.is_match and not s_sh.excluded:
                    self.assertIn("shadow_f3", sh["score_breakdown"])
                    shadowed += 1
                else:
                    self.assertNotIn("shadow_f3", sh["score_breakdown"])
                sh["score_breakdown"] = {k: v for k, v in sh["score_breakdown"].items() if k != "shadow_f3"}
                self.assertEqual(sh, off)
                self.assertEqual(s_sh.breakdown(), s_off.breakdown())
                self.assertEqual((s_sh.score, s_sh.level, s_sh.guard, s_sh.excluded, s_sh.extra),
                                 (s_off.score, s_off.level, s_off.guard, s_off.excluded, s_off.extra))
                self.assertEqual(r_sh.to_json(), r_off.to_json())
                self.assertEqual(sh["scoring_version"], SCORING_VERSION)
                self.assertEqual(sh["score_breakdown"]["scoring_version"], SCORING_VERSION)
        self.assertGreater(shadowed, 20)

    def test_evaluate_returns_none_in_exactly_the_same_cases(self):
        for name, listing, profile, ref in matrix():
            with self.subTest(case=name):
                a = evaluate(copy.deepcopy(listing), copy.deepcopy(profile), price_ref=ref, cfg=OFF, now=NOW, fx_rate=FX)
                b = evaluate(copy.deepcopy(listing), copy.deepcopy(profile), price_ref=ref, cfg=SHADOW, now=NOW,
                             fx_rate=FX)
                self.assertEqual(a is None, b is None)

    def test_the_shadow_does_not_touch_its_inputs(self):
        for name, listing, profile, ref in matrix():
            with self.subTest(case=name):
                l2, p2 = copy.deepcopy(listing), copy.deepcopy(profile)
                assess(l2, p2, price_ref=ref, cfg=SHADOW, now=NOW, fx_rate=FX)
                self.assertEqual((l2, p2), (listing, profile))

    def test_an_f3_failure_leaves_the_row_as_without_it(self):
        listing, profile = fiesta_listing(), fiesta_profile()
        off = run(listing, profile, MARKET, OFF)[2].row()
        f3._WARNED.clear()
        with patch.object(f3, "assess_f3", side_effect=KeyError("boom")), \
                self.assertLogs("intelligence.f3", logging.WARNING) as logs:
            rows = [run(listing, profile, MARKET, SHADOW)[2].row() for _ in range(3)]
        for row in rows:
            self.assertEqual(row, off)
            self.assertNotIn("shadow_f3", row["score_breakdown"])
        self.assertEqual(len(logs.records), 1)
        f3._WARNED.clear()

    def test_a_bad_f3_config_never_breaks_f2(self):
        for raw in ("x", [1], {"mode": "shadow", "deal": "x"}, {"mode": "shadow", "levels": {"c_high": "0.9"}}):
            with self.subTest(raw=raw):
                cfg = IntelligenceConfig.from_app_config({"score_model_f3": raw})
                ev = evaluate(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=cfg, now=NOW, fx_rate=FX)
                self.assertEqual((ev.score.score, ev.level), (89, "high"))

    def test_the_stored_shadow_is_the_same_on_a_later_re_score(self):
        """No time in shadow_f3: a re-score with nothing changed stores the same breakdown (the DB tests
        compare it whole)."""
        listing, profile = fiesta_listing(), fiesta_profile()
        a = assess(listing, profile, price_ref=MARKET, cfg=SHADOW, now=NOW, fx_rate=FX)[2]
        b = assess(listing, profile, price_ref=MARKET, cfg=SHADOW, now=NOW + timedelta(hours=6), fx_rate=FX)[2]
        self.assertEqual(a.shadow_f3, b.shadow_f3)

    def test_the_shadow_values(self):
        ev = evaluate(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=SHADOW, now=NOW, fx_rate=FX)
        shadow = ev.row()["score_breakdown"]["shadow_f3"]
        self.assertEqual((shadow["level"], shadow["score"], shadow["mode"]), ("high", 88, "shadow"))
        self.assertEqual((ev.score.score, ev.level), (89, "high"))


if __name__ == "__main__":
    unittest.main()
