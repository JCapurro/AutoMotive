"""«Valor justo», the pure part (intelligence/fair_value.py; spec 2026-11-20-valor-justo-design.md §3, §5, §10)."""
from __future__ import annotations

import json
import math
import random
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from intelligence import fair_value as fv
from intelligence.comparables import PriceRef
from intelligence.config import IntelligenceConfig, fair_value_config

P = fair_value_config({"mode": "shadow"})
COMPARABLES = {"min_n": 5, "year_tol": 1, "km_tol_pct": 25}

A = {2015: 9.0, 2016: 9.07, 2017: 9.14, 2018: 9.21, 2019: 9.28}
G = {"base": -0.10, "full": 0.15, "mid": 0.0}
H = {"manual": -0.03, "automatic": 0.05}
B = -0.12


def synthetic(n=2000, seed=1, noise=0.03, slope=B):
    rng = random.Random(seed)
    rows = []
    for i in range(1, n + 1):
        y, t, tr = rng.choice(list(A)), rng.choice(list(G)), rng.choice(list(H))
        typical = math.log(100_000) + (2019 - y) * 0.15
        km = math.exp(typical + rng.gauss(0, 0.4))
        lp = A[y] + G[t] + H[tr] + slope * (math.log(km) - typical) + rng.gauss(0, noise)
        rows.append({"id": i, "probable_repost_of": None, "year": y, "trim": t.title(), "transmission": tr,
                     "mileage_km": int(km), "price_usd": Decimal(str(round(math.exp(lp), 2)))})
    return rows


def true_log(y, t, tr, km):
    typical = math.log(100_000) + (2019 - y) * 0.15
    return A[y] + G[t] + H[tr] + B * (math.log(km) - typical)


class FitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = synthetic()
        cls.curve = fv.fit(cls.rows, P, make="X", model="Y")

    def test_recovers_known_coefficients(self):
        c = self.curve
        self.assertAlmostEqual(c.km_slope, B, delta=0.02)
        # G and H are relative to the typical trim / transmission: the differences are what is identified.
        self.assertAlmostEqual(c.trims["full"]["g"] - c.trims["base"]["g"], 0.25, delta=0.02)
        self.assertAlmostEqual(c.transmissions["automatic"]["h"] - c.transmissions["manual"]["h"], 0.08, delta=0.02)
        self.assertAlmostEqual(c.years[2019]["a"] - c.years[2015]["a"], 0.28, delta=0.02)
        for y, t, tr, km in ((2017, "full", "automatic", 80_000), (2015, "base", "manual", 150_000)):
            got = fv.fair_value({"year": y, "trim": t.upper(), "transmission": tr, "mileage_km": km}, c)
            self.assertAlmostEqual(got.log_value, true_log(y, t, tr, km), delta=0.02)
        self.assertLess(c.resid["q25"], 0)
        self.assertGreater(c.resid["q75"], 0)

    def test_trims_absurd_prices(self):
        rows = synthetic(600, seed=2) + [
            {"id": 9000 + i, "year": 2017, "trim": "Full", "transmission": "manual", "mileage_km": 80_000,
             "price_usd": price} for i, price in enumerate([100, 150, 200, 900_000, 1_000_000] * 3)]
        clean = fv.fit(synthetic(600, seed=2), P)
        dirty = fv.fit(rows, P)
        self.assertEqual(dirty.n, clean.n)
        self.assertAlmostEqual(dirty.years[2017]["a"], clean.years[2017]["a"], delta=0.01)

    def test_a_rare_trim_gets_no_premium_and_a_rare_year_no_value(self):
        rows = synthetic(800, seed=3)
        rows += [{"id": 5000 + i, "year": 2017, "trim": "Raro", "transmission": "manual", "mileage_km": 90_000,
                  "price_usd": 20_000} for i in range(P["min_trim_n"] - 1)]
        rows += [{"id": 6000 + i, "year": 2010, "trim": "Base", "transmission": "manual", "mileage_km": 90_000,
                  "price_usd": 5_000} for i in range(P["min_year_n"] - 1)]
        c = fv.fit(rows, P)
        self.assertNotIn("raro", c.trims)
        self.assertNotIn(2010, c.years)
        self.assertIsNone(fv.fair_value({"year": 2010, "trim": "Base"}, c))
        got = fv.fair_value({"year": 2017, "trim": "Raro", "price_usd": 10_000}, c)
        self.assertEqual((got.level, got.known["trim"]), (fv.CURVE_NOVERSION, False))

    def test_a_positive_km_slope_is_clipped_to_zero(self):
        c = fv.fit(synthetic(800, seed=4, slope=0.2), P)
        self.assertEqual(c.km_slope, 0.0)

    def test_slope_never_below_km_slope_min(self):
        c = fv.fit(synthetic(800, seed=5, slope=-0.9), P)
        self.assertEqual(c.km_slope, P["km_slope_min"])

    def test_without_km_transmission_or_trim(self):
        c = self.curve
        bare = fv.fair_value({"year": 2017, "price_usd": 9000}, c)
        self.assertEqual(bare.known, {"trim": False, "transmission": False, "km": False})
        self.assertEqual(bare.level, fv.CURVE_NOVERSION)
        self.assertAlmostEqual(bare.value, math.exp(c.years[2017]["a"]))
        self.assertAlmostEqual(bare.d, (1 - 9000 / bare.value) * 100)
        self.assertEqual(bare.n, c.years[2017]["n"])
        self.assertAlmostEqual(bare.p25, bare.value * math.exp(c.resid["q25"]))
        out_of_range = fv.fair_value({"year": 2017, "mileage_km": 1_000_000}, c)
        self.assertFalse(out_of_range.known["km"])
        self.assertIsNone(fv.fair_value({"year": 2017}, c).d)
        self.assertIsNone(fv.fair_value({"year": None}, c))
        self.assertIsNone(fv.fair_value({"year": 2017}, None))

    def test_zero_rows_and_rows_without_year_or_price(self):
        self.assertIsNone(fv.fit([], P))
        self.assertIsNone(fv.fit([{"id": 1, "year": None, "price_usd": 1000}, {"id": 2, "year": 2017, "price_usd": 0}], P))

    def test_stored_and_loaded_curve_values_the_same(self):
        row = {"make": "x", "model": "y", "curve": json.loads(json.dumps(self.curve.curve_json())), "n": 2000,
               "enabled": True, "params_hash": "abc", "fitted_at": None, "cv_err": 0.05, "cohort_err": 0.07}
        back = fv.Curve.from_row(row)
        listing = {"year": 2018, "trim": "Mid", "transmission": "automatic", "mileage_km": 70_000}
        self.assertAlmostEqual(fv.fair_value(listing, back).value, fv.fair_value(listing, self.curve).value, places=2)
        self.assertIsNone(fv.Curve.from_row({"make": "x", "model": "y", "curve": {"years": {"x": {}}}}))


class EvaluateTests(unittest.TestCase):
    def gate(self, rows, *, was_enabled=False, params=P):
        curve = fv.fit(rows, params)
        return fv.evaluate(curve, rows, params, comparables=COMPARABLES, partial_pct=65, was_enabled=was_enabled)

    def test_a_curve_better_than_the_cohort_is_enabled(self):
        g = self.gate(synthetic(1000, seed=6))
        self.assertTrue(g.enabled)
        self.assertLess(g.cv_err, g.cohort_err)
        self.assertGreater(g.sample, 200)
        self.assertEqual(g.n, 1000)

    def test_too_few_listings_is_never_enabled(self):
        g = self.gate(synthetic(140, seed=7))
        self.assertFalse(g.enabled)

    def test_a_curve_worse_than_the_cohort_is_disabled(self):
        # Prices that only depend on the km band the cohort reads (±25 %), not on the year or trim it fits.
        rng = random.Random(8)
        rows = []
        for i in range(1, 900):
            km = rng.choice([30_000, 300_000]) * rng.uniform(0.95, 1.05)
            rows.append({"id": i, "year": rng.choice([2016, 2017, 2018]), "trim": rng.choice(["A", "B"]),
                         "transmission": "manual", "mileage_km": km,
                         "price_usd": (20_000 if km < 100_000 else 5_000) * rng.uniform(0.97, 1.03)})
        g = self.gate(rows, params={**P, "km_slope_min": 0.0})
        self.assertGreater(g.cv_err, g.cohort_err)
        self.assertFalse(g.enabled)

    def test_the_disable_margin(self):
        # 3 % worse than today's: a new curve is not enabled, an enabled one stays (margin 1.05) until 5 %.
        self.assertTrue(fv.enabled_by(500, 0.0618, 0.06, P, was_enabled=False) is False)
        self.assertTrue(fv.enabled_by(500, 0.0618, 0.06, P, was_enabled=True))
        self.assertFalse(fv.enabled_by(500, 0.0636, 0.06, P, was_enabled=True))
        self.assertTrue(fv.enabled_by(500, 0.06, 0.06, P, was_enabled=False))
        self.assertFalse(fv.enabled_by(500, 0.0618, 0.06, {**P, "disable_margin": 1.0}, was_enabled=True))
        self.assertFalse(fv.enabled_by(149, 0.01, 0.06, P, was_enabled=True))
        self.assertFalse(fv.enabled_by(500, 0.01, None, P, was_enabled=False))
        self.assertFalse(fv.enabled_by(500, None, 0.06, P, was_enabled=True))

    def test_evaluate_reads_was_enabled(self):
        rows = synthetic(1000, seed=10)
        curve = fv.fit(rows, P)
        g = fv.evaluate(curve, rows, P, comparables=COMPARABLES, partial_pct=65, was_enabled=True)
        self.assertEqual(g.enabled, fv.enabled_by(g.n, g.cv_err, g.cohort_err, P, was_enabled=True))
        self.assertFalse(fv.evaluate(None, rows, P, comparables=COMPARABLES, partial_pct=65).enabled)

    def test_guard_flips_count_listings_across_the_65_pct(self):
        rows = synthetic(1000, seed=11)
        # A dealer's anticipos: a quarter of the price, below 65 % of the value; the cohort sees them too.
        for r in rows[::40]:
            r["price_usd"] = float(r["price_usd"]) * 0.32
        g = self.gate(rows)
        # 0.32 of the price is ~68 % below both the value and the cohort median: no flip for those...
        self.assertIsInstance(g.guard_flips, int)
        # ...but a curve that values the car 2.5x higher crosses 65 % on every sample listing the cohort does not.
        from dataclasses import replace
        curve = fv.fit(rows, P)
        rich = replace(curve, years={y: {**v, "a": v["a"] + math.log(3)} for y, v in curve.years.items()})
        flips = fv.evaluate(rich, rows, P, comparables=COMPARABLES, partial_pct=65).guard_flips
        self.assertGreater(flips, 100)


class RuleHTests(unittest.TestCase):
    VALUE = fv.FairValue(10_000, 9_000, 11_000, 30, fv.CURVE, {"trim": True, "transmission": True, "km": True}, 5.0, 9.2)

    def test_twins_keep_todays_reference(self):
        twins = PriceRef(n=8, level_used="trim_transmission", median=11_000, diff_pct=9)
        self.assertFalse(fv.rule_h(twins, True, self.VALUE, min_n=5))

    def test_without_twins_the_fair_value(self):
        for ref in (PriceRef(n=40, level_used="model", median=11_000), PriceRef(n=12, level_used="transmission", median=1),
                    PriceRef(n=3, level_used="trim_transmission", median=11_000), None):
            self.assertTrue(fv.rule_h(ref, True, self.VALUE, min_n=5), ref)

    def test_a_reference_not_fetched_takes_the_fair_value(self):
        self.assertTrue(fv.rule_h(None, False, self.VALUE, min_n=5))

    def test_no_value_or_a_disabled_curve_keeps_todays(self):
        self.assertFalse(fv.rule_h(None, False, None, min_n=5))
        self.assertFalse(fv.rule_h(None, True, self.VALUE, min_n=5, enabled=False))


class JsonSafeTests(unittest.TestCase):
    """shadow() travels in f2's row JSON: a NaN, an infinity, a Decimal or a date would fail the batch's write."""

    def setUp(self):
        from test_fair_value_shadow_engine import SHADOW, curve_for, fiesta_case
        self.cfg, self.curve = SHADOW, curve_for()
        self.listing, self.profile, self.result, self.ref, self.score = fiesta_case()

    def block(self, listing=None, curve=None, **kw):
        return fv.shadow(listing or self.listing, kw.get("profile", self.profile), self.result, self.ref, self.score,
                         self.cfg, curve=curve or self.curve, fetched=True, now=datetime(2026, 11, 21, tzinfo=timezone.utc),
                         fx_rate=kw.get("fx_rate", 1000.0))

    def assert_json(self, block):
        if block is not None:
            json.dumps(block, allow_nan=False)

    def test_decimal_prices_nan_infinity_and_dates(self):
        for price in (Decimal("9100.50"), float("nan"), float("inf"), Decimal("NaN"), -1, 0, None, "9000",
                      date(2026, 1, 1)):
            b = self.block({**self.listing, "price_usd": price, "price": price})
            self.assert_json(b)
        b = self.block({**self.listing, "price_usd": Decimal("9100.50")})
        self.assertIsInstance(b["d"], float)
        for km in (float("nan"), float("inf"), Decimal("80000"), "80.000"):
            self.assert_json(self.block({**self.listing, "mileage_km": km}))

    def test_a_date_fitted_at_and_a_nan_curve(self):
        from dataclasses import replace
        self.assertEqual(self.block(curve=replace(self.curve, fitted_at=date(2026, 11, 21)))["fitted_at"], "2026-11-21")
        bad = replace(self.curve, years={2017: {"a": float("nan"), "n": 30, "km": None}})
        self.assertIsNone(self.block({**self.listing, "year": 2017}, curve=bad))
        huge = replace(self.curve, years={2017: {"a": 1e6, "n": 30, "km": None}})
        self.assertIsNone(self.block({**self.listing, "year": 2017}, curve=huge))

    def test_budget_in_both_currencies(self):
        b = self.block(profile={**self.profile, "filters": {**self.profile["filters"], "price_max": 12_000,
                                                             "currency": "USD"}})
        self.assertEqual(b["budget"]["usd"], 12_000)
        ars = self.block(profile={**self.profile, "filters": {**self.profile["filters"], "price_max": 12_000_000,
                                                               "currency": "ARS"}})
        self.assertAlmostEqual(ars["budget"]["value_ratio"], b["budget"]["value_ratio"], places=3)
        none = self.block(profile={**self.profile, "filters": {**self.profile["filters"], "price_max": 12_000}},
                          fx_rate=None)
        self.assertNotIn("budget", none)
        self.assert_json(b)


if __name__ == "__main__":
    unittest.main()
