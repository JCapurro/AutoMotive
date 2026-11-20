"""app_config.fair_value as the worker reads it (intelligence/config.fair_value_config; spec 2026-11-20 §9):
the same bounds as /admin/config (web/lib/admin-config.ts fairValueProblem), key by key back to the default."""
from __future__ import annotations

import unittest

from intelligence.config import (DEFAULT_FAIR_VALUE, FAIR_VALUE_MODES, IntelligenceConfig, fair_value_config,
                                 fair_value_params_hash)


class FairValueConfigTests(unittest.TestCase):
    def test_defaults_and_mode_off(self):
        got = fair_value_config(None)
        self.assertEqual({k: v for k, v in got.items() if k != "params"}, DEFAULT_FAIR_VALUE)
        self.assertEqual(got["mode"], "off")
        for raw in ("shadow", [], 7, {"mode": "on"}, {"mode": True}):
            self.assertEqual(fair_value_config(raw)["mode"], "off", raw)
        for mode in FAIR_VALUE_MODES:
            self.assertEqual(fair_value_config({"mode": mode})["mode"], mode)

    def test_bounds_key_by_key(self):
        ok = {"min_listings": 50, "min_year_n": 200, "min_trim_n": 5, "km_slope_min": -1, "max_passes": 10,
              "cohort_sample": 2000, "disable_margin": 1.5, "price_trim": {"low": 0.2, "high": 5},
              "km_range": {"min": 0, "max": 1_000_000}, "schedule": {"hour": "23:59"}}
        got = fair_value_config(ok)
        for k, v in ok.items():
            self.assertEqual(got[k], v, k)
        bad = {"min_listings": 49, "min_year_n": 8.5, "min_trim_n": "15", "km_slope_min": 0.1, "max_passes": True,
               "cohort_sample": 2001, "disable_margin": float("nan"), "price_trim": {"low": 0.1, "high": 2.0},
               "km_range": {"min": 60_000, "max": 50_000.5}, "schedule": {"hour": "24:00"}}
        got = fair_value_config(bad)
        for k in bad:
            if k == "price_trim":
                self.assertEqual(got[k], {"low": 0.45, "high": 2.0})
            else:
                self.assertEqual(got[k], DEFAULT_FAIR_VALUE[k], k)

    def test_integers_stay_integers_and_unknown_keys_are_dropped(self):
        got = fair_value_config({"min_listings": 200.0, "km_range": {"min": 1000.0, "extra": 1}, "typo": 1})
        self.assertIsInstance(got["min_listings"], int)
        self.assertIsInstance(got["km_range"]["min"], int)
        self.assertNotIn("extra", got["km_range"])
        self.assertNotIn("typo", got)

    def test_the_params_hash_ignores_the_mode_only(self):
        off, shadow = fair_value_config({"mode": "off"}), fair_value_config({"mode": "shadow"})
        self.assertEqual(off["params"], shadow["params"])
        self.assertEqual(len(off["params"]), 12)
        self.assertNotEqual(fair_value_config({"min_listings": 151})["params"], off["params"])
        # 150 and 150.0 are the same parameter.
        self.assertEqual(fair_value_config({"disable_margin": 1})["params"],
                         fair_value_config({"disable_margin": 1.0})["params"])
        self.assertEqual(fair_value_params_hash(off), off["params"])

    def test_intelligence_config_carries_it(self):
        self.assertEqual(IntelligenceConfig().fair_value["mode"], "off")
        self.assertEqual(IntelligenceConfig.from_app_config({"fair_value": {"mode": "shadow"}}).fair_value["mode"], "shadow")
        self.assertEqual(IntelligenceConfig.from_app_config({"fair_value": "x"}).fair_value["mode"], "off")


if __name__ == "__main__":
    unittest.main()
