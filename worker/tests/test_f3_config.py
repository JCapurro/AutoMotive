"""app_config.score_model_f3 as f3 reads it (intelligence/config.score_model_f3; spec §8). Pure."""
from __future__ import annotations

import copy
import math
import unittest
from unittest.mock import AsyncMock, patch

from intelligence import config
from intelligence.config import (DEFAULT_SCORE_MODEL_F3, F3_BOUNDS, F3_MODES, IntelligenceConfig, f3_params_hash,
                                 score_model_f3)


def defaults(mode: str = "off") -> dict:
    out = copy.deepcopy(DEFAULT_SCORE_MODEL_F3)
    out["mode"] = mode
    return out


# What the migration inserts: the defaults with mode shadow.
MIGRATION_VALUE = defaults("shadow")


def without_params(value: dict) -> dict:
    return {k: v for k, v in value.items() if k != "params"}


class DefaultTests(unittest.TestCase):
    def test_none_and_garbage_give_the_defaults_with_mode_off(self):
        for raw in (None, [], "x", 3, True, {"deal": 3}, {"deal": [1, 2]}, {"levels": {"c_high": [0.9]}},
                    {"rules": "on"}, {"mode": None}, {"fit": {"unknown": {"a": 1}}}):
            with self.subTest(raw=raw):
                out = score_model_f3(raw)
                self.assertEqual(without_params(out), defaults("off"))
                self.assertEqual(out["params"], f3_params_hash(defaults()))

    def test_the_code_default_is_off(self):
        self.assertEqual(DEFAULT_SCORE_MODEL_F3["mode"], "off")
        self.assertEqual(IntelligenceConfig().f3["mode"], "off")
        self.assertEqual(IntelligenceConfig.from_app_config({}).f3["mode"], "off")

    def test_the_migration_value_is_kept_whole(self):
        out = score_model_f3(MIGRATION_VALUE)
        self.assertEqual(without_params(out), MIGRATION_VALUE)
        self.assertEqual(out["mode"], "shadow")

    def test_the_spec_values(self):
        d = DEFAULT_SCORE_MODEL_F3
        self.assertEqual(d["deal"], {"d_floor": 12, "d_ceil": 20, "d_mult": 2.5, "cred_min": 5, "cred_max": 35,
                                     "r_model": 0.9, "r_noyear": 0.3, "kavak_offset": 9})
        self.assertEqual(d["levels"]["c_high"], 0.82)
        self.assertEqual(d["rules"], {"seller_cap": True, "agency_voice": True, "placeholder": True,
                                      "pro_deal_d": True})

    def test_the_defaults_are_inside_their_own_bounds(self):
        for group, bounds in F3_BOUNDS.items():
            for key, (lo, hi, open_hi) in bounds.items():
                value = DEFAULT_SCORE_MODEL_F3[group][key]
                self.assertTrue(lo <= value <= hi and not (open_hi and value >= hi), (group, key))


class ModeTests(unittest.TestCase):
    def test_modes(self):
        for mode in F3_MODES:
            self.assertEqual(score_model_f3({"mode": mode})["mode"], mode)
        for bad in ("on", "SHADOW", "", 1, True, None, ["shadow"]):
            self.assertEqual(score_model_f3({"mode": bad})["mode"], "off", bad)

    def test_a_partial_value_keeps_the_rest(self):
        out = score_model_f3({"mode": "shadow", "levels": {"c_high": 0.84}})
        self.assertEqual(out["levels"]["c_high"], 0.84)
        self.assertEqual(out["levels"]["x_high"], 0.70)
        self.assertEqual(out["deal"], DEFAULT_SCORE_MODEL_F3["deal"])


class KeyBoundTests(unittest.TestCase):
    def test_each_key_out_of_bounds_or_not_a_number_falls_back(self):
        for group, bounds in F3_BOUNDS.items():
            for key, (lo, hi, open_hi) in bounds.items():
                default = DEFAULT_SCORE_MODEL_F3[group][key]
                bad = [lo - 1, hi + 1, str(default), True, None, math.nan, math.inf, [default], {"v": default}]
                if open_hi:
                    bad.append(hi)
                for value in bad:
                    with self.subTest(group=group, key=key, value=value):
                        out = score_model_f3({group: {key: value}})
                        self.assertEqual(out[group][key], default)
                        self.assertEqual(out[group], DEFAULT_SCORE_MODEL_F3[group])

    def test_values_inside_their_bounds_are_taken(self):
        cases = {("deal", "d_floor"): 10, ("deal", "d_ceil"): 25, ("deal", "d_mult"): 2.0, ("deal", "cred_min"): 0,
                 ("deal", "cred_max"): 28, ("deal", "r_model"): 1, ("deal", "r_noyear"): 0.1,
                 ("deal", "kavak_offset"): 0, ("fit", "unknown"): 0.6, ("fit", "fail"): 0.0,
                 ("fit", "trim_other"): 0.55, ("fit", "unknown_hard"): 0.0, ("fit", "price_target_at_max"): 0.3,
                 ("levels", "x_high"): 0.75, ("levels", "y_high"): 0.6, ("levels", "c_high"): 0.95,
                 ("levels", "x_good"): 0.3, ("levels", "y_deal"): 0.4, ("levels", "y_good"): 1,
                 ("levels", "y_min"): 0.1, ("levels", "n_min_high"): 100, ("levels", "fair_min_d"): 5,
                 ("levels", "low_d"): -30}
        for (group, key), value in cases.items():
            with self.subTest(group=group, key=key):
                self.assertEqual(score_model_f3({group: {key: value}})[group][key], value)

    def test_cred_max_50_is_refused(self):
        self.assertEqual(score_model_f3({"deal": {"cred_max": 50}})["deal"]["cred_max"], 35)
        self.assertEqual(score_model_f3({"deal": {"cred_max": 49.5}})["deal"]["cred_max"], 49.5)

    def test_n_min_high_is_an_integer(self):
        self.assertEqual(score_model_f3({"levels": {"n_min_high": 10.5}})["levels"]["n_min_high"], 10)
        self.assertEqual(score_model_f3({"levels": {"n_min_high": 4}})["levels"]["n_min_high"], 10)
        twelve = score_model_f3({"levels": {"n_min_high": 12.0}})["levels"]["n_min_high"]
        self.assertEqual((twelve, type(twelve)), (12, int))

    def test_n_min_high_is_at_least_comparables_min_n(self):
        self.assertEqual(score_model_f3({"levels": {"n_min_high": 6}}, min_n=8)["levels"]["n_min_high"], 8)
        self.assertEqual(score_model_f3(None, min_n=12)["levels"]["n_min_high"], 12)
        self.assertEqual(score_model_f3(None, min_n="x")["levels"]["n_min_high"], 10)
        cfg = IntelligenceConfig.from_app_config({"comparables": {"min_n": 15}})
        self.assertEqual(cfg.f3["levels"]["n_min_high"], 15)

    def test_rules_are_booleans(self):
        out = score_model_f3({"rules": {"seller_cap": False, "agency_voice": "false", "placeholder": 0,
                                        "pro_deal_d": None, "other": False}})
        self.assertEqual(out["rules"], {"seller_cap": False, "agency_voice": True, "placeholder": True,
                                        "pro_deal_d": True})


class CrossRuleTests(unittest.TestCase):
    """Each cross-key rule of spec §8: a group that breaks one falls back to its defaults as a whole."""

    def assertGroupDefault(self, group: str, value: dict, **kw):
        out = score_model_f3({group: value}, **kw)
        self.assertEqual(out[group], DEFAULT_SCORE_MODEL_F3[group], value)

    def test_deal(self):
        self.assertGroupDefault("deal", {"d_floor": 20, "d_ceil": 20, "d_mult": 3})
        self.assertGroupDefault("deal", {"d_floor": 25, "d_ceil": 15})
        # cred_min < cred_max always holds inside the bounds ([0, 15] and [20, 50)); the rule stays as a guard.
        self.assertEqual(score_model_f3({"deal": {"cred_min": 15, "cred_max": 20}})["deal"]["cred_max"], 20)
        # cred_max must stay below f2's suspicious guard (f3's «sospechoso»).
        self.assertGroupDefault("deal", {"cred_max": 45, "d_mult": 3}, suspicious_pct=45)
        self.assertEqual(score_model_f3({"deal": {"cred_max": 45}}, suspicious_pct=50)["deal"]["cred_max"], 45)
        self.assertEqual(score_model_f3({"deal": {"cred_max": 45}}, suspicious_pct="80")["deal"]["cred_max"], 45)

    def test_fit(self):
        self.assertGroupDefault("fit", {"fail": 0.8, "unknown": 0.6, "trim_other": 0.7})
        self.assertEqual(score_model_f3({"fit": {"fail": 0.6, "unknown": 0.6}})["fit"]["fail"], 0.6)

    def test_levels(self):
        # A c_high that does nothing: 0.6·0.9 + 0.4·0.9 = 0.9 > 0.85.
        self.assertGroupDefault("levels", {"x_high": 0.9, "y_high": 0.9, "c_high": 0.85})
        self.assertGroupDefault("levels", {"x_good": 0.70})                 # not below x_high
        self.assertGroupDefault("levels", {"y_deal": 0.70})                 # not below y_high
        self.assertGroupDefault("levels", {"y_good": 0.55, "y_min": 0.6})   # 0.55 > 0.6 fails
        self.assertGroupDefault("levels", {"low_d": -2})                    # not below fair_min_d
        out = score_model_f3({"levels": {"x_high": 0.75, "y_high": 0.70, "c_high": 0.73}})
        self.assertEqual(out["levels"]["c_high"], 0.73)                     # 0.45 + 0.28 = 0.73, exactly
        self.assertEqual(score_model_f3({"levels": {"y_min": 0.6, "y_good": 0.85}})["levels"]["y_min"], 0.6)

    def test_one_group_falling_back_leaves_the_others(self):
        out = score_model_f3({"mode": "shadow", "deal": {"d_floor": 25, "d_ceil": 15},
                              "fit": {"unknown": 0.6}, "rules": {"placeholder": False}})
        self.assertEqual(out["deal"], DEFAULT_SCORE_MODEL_F3["deal"])
        self.assertEqual(out["fit"]["unknown"], 0.6)
        self.assertFalse(out["rules"]["placeholder"])
        self.assertEqual(out["mode"], "shadow")


class ParamsHashTests(unittest.TestCase):
    def test_stable_and_independent_of_mode(self):
        a = score_model_f3({"mode": "shadow"})["params"]
        self.assertEqual(a, score_model_f3({"mode": "off"})["params"])
        self.assertEqual(a, score_model_f3(None)["params"])
        self.assertEqual(len(a), 12)
        int(a, 16)

    def test_changes_with_any_value(self):
        base = score_model_f3(None)["params"]
        for raw in ({"levels": {"c_high": 0.84}}, {"deal": {"kavak_offset": 6}}, {"fit": {"unknown": 0.6}},
                    {"rules": {"seller_cap": False}}):
            self.assertNotEqual(score_model_f3(raw)["params"], base, raw)

    def test_an_integer_written_as_a_float_is_the_same_value(self):
        self.assertEqual(score_model_f3({"deal": {"d_floor": 12.0, "cred_max": 35.0}})["params"],
                         score_model_f3(None)["params"])

    def test_it_hashes_the_effective_values(self):
        # A refused value is the default: same hash as without it.
        self.assertEqual(score_model_f3({"levels": {"c_high": "0.9"}})["params"], score_model_f3(None)["params"])


class IntelligenceConfigTests(unittest.TestCase):
    def test_from_app_config_reads_it_and_never_breaks_on_it(self):
        cfg = IntelligenceConfig.from_app_config({"score_model_f3": MIGRATION_VALUE})
        self.assertEqual(cfg.f3["mode"], "shadow")
        with patch.object(config, "score_model_f3", side_effect=[RuntimeError("bad"), score_model_f3(None)]):
            cfg = IntelligenceConfig.from_app_config({"score_model_f3": MIGRATION_VALUE})
        self.assertEqual(cfg.f3["mode"], "off")
        # f2's config is untouched by an f3 row.
        self.assertEqual(IntelligenceConfig.from_app_config({"score_model_f3": MIGRATION_VALUE}).weights,
                         IntelligenceConfig().weights)

    def test_the_suspicious_guard_comes_from_score_curves(self):
        cfg = IntelligenceConfig.from_app_config({"score_curves": {"guards": {"suspicious_pct": 40}},
                                                  "score_model_f3": {"mode": "shadow", "deal": {"cred_max": 38}}})
        self.assertEqual(cfg.f3["deal"]["cred_max"], 38)
        cfg = IntelligenceConfig.from_app_config({"score_curves": {"guards": {"suspicious_pct": 37}},
                                                  "score_model_f3": {"mode": "shadow", "deal": {"cred_max": 38}}})
        self.assertEqual(cfg.f3["deal"]["cred_max"], 35)


class LoadTests(unittest.IsolatedAsyncioTestCase):
    async def test_load_asks_for_score_model_f3(self):
        import db
        asked = []

        async def get_config(key, default=None):
            asked.append(key)
            return MIGRATION_VALUE if key == "score_model_f3" else None

        with patch.object(db, "get_config", get_config):
            cfg = await IntelligenceConfig.load()
        self.assertIn("score_model_f3", asked)
        self.assertEqual(cfg.f3["mode"], "shadow")
        self.assertEqual(cfg.weights, IntelligenceConfig().weights)


if __name__ == "__main__":
    unittest.main()
