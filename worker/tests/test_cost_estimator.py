"""PAR-01: the total cost estimate (docs/superpowers/specs/2026-10-30-par01-costo-total-design.md).

The golden vectors (tests/fixtures/cost_estimator/golden.json) are shared with
web/lib/cost-estimator.test.ts: both calculators, jurisdiction resolvers and
input builders must give the same numbers and the same strings.
"""
from __future__ import annotations

import copy as _copy
import json
import unittest
from datetime import date
from pathlib import Path

from intelligence import copy
from intelligence import cost_estimator as ce
from normalization.normalize import normalize_text

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "cost_estimator" / "golden.json").read_text(encoding="utf-8"))
TOL = 0.01


def patched(raw, patch=()):
    """The golden config with a config_patch applied: path + value, or delete."""
    out = _copy.deepcopy(raw)
    for op in patch or ():
        *parents, last = op["path"]
        node = out
        for key in parents:
            node = node[key]
        if op.get("delete"):
            del node[last]
        else:
            node[last] = op["value"]
    return out


def cfg_for(patch=()):
    return ce.parse_config(patched(GOLDEN["config"], patch))


class Close:
    """Compares the keys an expectation names: numbers within TOL, the rest exactly."""

    def assert_matches(self, actual, expected, where=""):
        if isinstance(expected, dict):
            self.assertIsInstance(actual, dict, where)
            for key, value in expected.items():
                self.assert_matches(actual.get(key), value, f"{where}.{key}")
        elif isinstance(expected, list):
            self.assertIsInstance(actual, list, where)
            self.assertEqual(len(actual), len(expected), f"{where}: {actual}")
            for i, (a, e) in enumerate(zip(actual, expected)):
                self.assert_matches(a, e, f"{where}[{i}]")
        elif isinstance(expected, (int, float)) and not isinstance(expected, bool):
            self.assertIsInstance(actual, (int, float), where)
            self.assertLessEqual(abs(actual - expected), TOL, f"{where}: {actual!r} != {expected!r}")
        else:
            self.assertEqual(actual, expected, where)


class GoldenCalculatorTests(Close, unittest.TestCase):
    def test_cases(self):
        for case in GOLDEN["cases"]:
            with self.subTest(case["name"]):
                i = case["input"]
                est = ce.estimate(i["listing"], i["jurisdiction"], i["seller"], i["fx_latest"],
                                  cfg_for(i.get("config_patch")))
                expect = case["expect"]
                if expect is None:
                    self.assertIsNone(est)
                    continue
                self.assertIsNotNone(est)
                details = expect.get("details") or {}
                rest = {k: v for k, v in expect.items() if k not in ("line", "details", "missing", "terms", "extras")}
                self.assert_matches(est, rest)
                self.assert_matches([{k: t[k] for k in ("code", "min", "max")} for t in est["terms"]], expect["terms"], "terms")
                self.assert_matches([{k: t[k] for k in ("code", "min", "max")} for t in est["extras"]], expect["extras"], "extras")
                self.assertEqual(est["missing"], expect["missing"])
                self.assertEqual(ce.format_line(est), expect["line"])
                lines = {t["code"]: ce.term_amount(t) for t in est["terms"] + est["extras"] if t["min"] is not None}
                for code, text in details.items():
                    self.assertEqual(lines[code], text, code)

    def test_jurisdiction_cases(self):
        cfg = cfg_for()
        for case in GOLDEN["jurisdiction_cases"]:
            with self.subTest(case["name"]):
                self.assertEqual(ce.buyer_jurisdiction(case["zones"], cfg), case["expect"])

    def test_input_cases(self):
        cfg = cfg_for()
        for case in GOLDEN["input_cases"]:
            with self.subTest(case["name"]):
                zones = ce.search_zones(case["search"])
                built = ce.build_input(case["row"], zones, case["fx_latest"], cfg, date.fromisoformat(case["today"]))
                expect = case["expect"]
                if expect is None:
                    self.assertIsNone(built)
                    continue
                if "zones" in expect:
                    self.assertEqual(zones, expect["zones"])
                self.assert_matches(built, {k: v for k, v in expect.items() if k not in ("p_ars", "zones")})
                if "p_ars" in expect:
                    est = ce.estimate(built["listing"], built["jurisdiction"], built["seller"], built["fx_latest"], cfg)
                    self.assert_matches(est["p_ars"], expect["p_ars"], "p_ars")

    def test_config_cases(self):
        for case in GOLDEN["config_cases"]:
            with self.subTest(case["name"]):
                cfg = cfg_for(case["config_patch"])
                if case["expect_null"] is None:
                    self.assertIsNone(cfg)
                    continue
                nulls = sorted(k for k, v in cfg["blocks"].items() if v is None)
                self.assertEqual(nulls, sorted(case["expect_null"]))
                self.assertEqual(sorted(cfg["blocks"]), sorted(ce.BLOCKS))


class ParserTests(unittest.TestCase):
    def test_never_raises_on_garbage(self):
        for raw in (None, [], "x", 3, {"as_of": "2026-10-30", "dnrpa": "x", "patente": [], "fixed_ars": 7,
                                           "stamp_tax_pct": None}):
            with self.subTest(raw):
                cfg = ce.parse_config(raw)
                if cfg is not None:
                    self.assertTrue(all(v is None for v in cfg["blocks"].values()))

    def test_no_numeric_defaults(self):
        # Only the root as_of: every term is missing, nothing is made up.
        est = ce.estimate({"price": 20000000, "currency": "ARS", "fx_rate": 1300, "cash": False, "year": 2017,
                           "body_type": "sedan"}, ["caba"], "private", None, ce.parse_config({"as_of": "2026-10-30"}))
        self.assertEqual(est["terms"], [])
        self.assertEqual(est["extras"], [])
        self.assertEqual([m["code"] for m in est["missing"]], ["arancel", "sellos", "formularios", "patente"])
        self.assertEqual(est["total_ars"], {"min": 20000000, "max": 20000000})
        self.assertIsNone(ce.buyer_jurisdiction([{"lat": -34.6, "lon": -58.4, "label": "CABA"}],
                                                ce.parse_config({"as_of": "2026-10-30"})))


class ReviewTests(unittest.TestCase):
    def cfg(self, as_of, **review):
        raw = patched(GOLDEN["config"], [{"path": ["as_of"], "value": as_of}])
        raw["review"].update(review)
        return ce.parse_config(raw)

    def test_stale_after_max_age_days(self):
        self.assertEqual(ce.review_status(self.cfg("2026-06-01"), date(2026, 9, 30)), "stale")   # 121 days
        self.assertIsNone(ce.review_status(self.cfg("2026-06-02"), date(2026, 9, 30)))           # 120 days
        self.assertIsNone(ce.review_status(self.cfg("2026-06-23"), date(2026, 10, 21)))          # 120, October

    def test_due_in_the_review_months_until_reviewed(self):
        self.assertEqual(ce.review_status(self.cfg("2026-10-30"), date(2026, 12, 20)), "due")
        self.assertIsNone(ce.review_status(self.cfg("2026-12-05"), date(2026, 12, 20)))
        self.assertIsNone(ce.review_status(self.cfg("2026-12-05"), date(2027, 1, 15)))
        self.assertEqual(ce.review_status(self.cfg("2026-11-30"), date(2027, 1, 2)), "due")
        self.assertIsNone(ce.review_status(self.cfg("2026-10-30"), date(2026, 11, 20)))

    def test_stale_wins_over_due(self):
        self.assertEqual(ce.review_status(self.cfg("2026-08-01"), date(2026, 12, 20)), "stale")

    def test_missing_without_review_or_as_of(self):
        raw = patched(GOLDEN["config"], [{"path": ["review"], "delete": True}])
        self.assertEqual(ce.review_status(ce.parse_config(raw), date(2026, 11, 1)), "missing")
        self.assertEqual(ce.review_status(None, date(2026, 11, 1)), "missing")
        raw = patched(GOLDEN["config"], [{"path": ["review", "months"], "value": [0]}])
        self.assertEqual(ce.review_status(ce.parse_config(raw), date(2026, 11, 1)), "missing")


class FormatTests(unittest.TestCase):
    def test_outward_rounding_with_the_margin(self):
        self.assertEqual(ce.floor_to(321999.99999999994, 100), 322000)
        self.assertEqual(ce.ceil_to(506000.00000000006, 100), 506000)
        self.assertEqual(ce.floor_to(321999.98, 100), 321900)
        self.assertEqual(ce.ceil_to(506000.02, 100), 506100)
        self.assertEqual(ce.floor_to(21188950, 1000), 21188000)
        self.assertEqual(ce.ceil_to(21517532.5, 1000), 21518000)

    def test_thousands_by_hand(self):
        self.assertEqual(ce.thousands(0), "0")
        self.assertEqual(ce.thousands(950), "950")
        self.assertEqual(ce.thousands(16290), "16.290")
        self.assertEqual(ce.thousands(110619000), "110.619.000")

    def test_ranges(self):
        self.assertEqual(ce.format_range(16290, 16560, "USD"), "USD 16.290 – 16.560")
        self.assertEqual(ce.format_range(20208000, 20208000, "ARS"), "ARS 20.208.000")

    def test_missing_suffix(self):
        cases = {(): "", ("fx",): "", ("patente",): " (sin patente)",
                 ("patente", "sellos"): " (sin sellos ni patente)", ("formularios",): " (sin formularios)",
                 ("arancel",): " (sin arancel)", ("sellos", "formularios", "patente"): " (sin sellos, formularios ni patente)",
                 ("patente", "arancel", "sellos", "fx"): " (sin arancel, sellos ni patente)",
                 ("arancel", "sellos", "formularios", "patente"): " (sin arancel, sellos, formularios ni patente)",
                 ("arancel", "sellos"): " (sin arancel ni sellos)"}
        for codes, text in cases.items():
            with self.subTest(codes):
                self.assertEqual(ce.missing_suffix(list(codes)), text)

    def test_headline_from_rounded_values(self):
        self.assertEqual(ce.headline({"min": 21188000, "max": 21518000}, {"min": 16290, "max": 16560}, []),
                         "Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)")
        self.assertEqual(ce.headline({"min": 21188000, "max": 21518000}, None, ["fx", "patente"]),
                         "Costo total estimado (sin patente): ARS 21.188.000 – 21.518.000 (sin dólar del día)")
        self.assertEqual(ce.headline(None, None, ["fx"]), "Costo total estimado: sin dólar del día, no se puede estimar")

    def test_day_month(self):
        self.assertEqual(ce.day_month("2026-10-30"), "30/10")
        self.assertEqual(ce.day_month("2026-01-05"), "05/01")


class CopyLintTests(unittest.TestCase):
    EXTRA = ("precio final", "costo real", "costo exacto", "total real")

    def texts(self):
        out = [v for v in copy.TOTAL_COST.values() if isinstance(v, str)]
        out += list(copy.TOTAL_COST["names"].values())
        for case in GOLDEN["cases"]:
            if case["expect"]:
                out.append(case["expect"]["line"])
        return out

    def test_no_forbidden_or_absolute_wording(self):
        for text in self.texts():
            folded = normalize_text(text)
            for term in (*copy.FORBIDDEN_TERMS, *self.EXTRA):
                with self.subTest(text=text, term=term):
                    self.assertNotIn(normalize_text(term), folded)

    def test_always_estimated(self):
        for case in GOLDEN["cases"]:
            if case["expect"]:
                self.assertIn("estimado", case["expect"]["line"])

    def test_the_same_header_as_the_web(self):
        web = (Path(__file__).resolve().parents[2] / "web" / "lib" / "copy.ts").read_text(encoding="utf-8")
        for py, ts in (("line", "line"), ("line_no_usd", "lineNoUsd"), ("line_no_fx", "lineNoFx"),
                       ("suffix", "suffix"), ("last", "last")):
            with self.subTest(py):
                self.assertIn(f"  {ts}: {json.dumps(copy.TOTAL_COST[py], ensure_ascii=False)},", web)
        for code, name in copy.TOTAL_COST["names"].items():
            self.assertIn(f"{code}: {json.dumps(name)}", web)

    def test_the_calculator_returns_codes_not_text(self):
        source = (Path(ce.__file__)).read_text(encoding="utf-8")
        for word in ("Costo", "sin dólar", "patente anual"):
            self.assertNotIn(word, source)


if __name__ == "__main__":
    unittest.main()
