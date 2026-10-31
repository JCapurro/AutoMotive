"""PRO-01 paso 1: the strict seller filter (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md,
decisiones 2 y 4). Pure: matching, scoring and the low-results funnel."""
from __future__ import annotations

import unittest

from intelligence import copy
from intelligence import low_results as lr
from intelligence.engine import evaluate
from intelligence.matching import match, seller_types, strict_seller
from pipeline import low_results as job

from test_intelligence import CFG, FX, MARKET, NOW, SellerPreferencePinTests, fiesta_listing, fiesta_profile

LISTINGS = SellerPreferencePinTests.LISTINGS


def strict(types, *, flag=True, **pref):
    p = fiesta_profile(seller_types=types)
    p["seller_filter"] = flag
    p["preferences"].update(pref)
    return p


def run(profile, name):
    return evaluate(fiesta_listing(**LISTINGS[name]), profile, price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX)


class HardSellerTests(unittest.TestCase):
    # (seller_types, listing) → result of the hard check with the flag on.
    EXPECTED = {
        ("private", "private"): "ok", ("private", "dealer"): "fail", ("private", "inferred"): "fail",
        ("private", "none"): "unknown",
        ("dealer", "private"): "fail", ("dealer", "dealer"): "ok", ("dealer", "inferred"): "ok",
        ("dealer", "none"): "unknown",
    }

    def test_hard_check_reads_the_effective_seller(self):
        for (wanted, name), result in self.EXPECTED.items():
            with self.subTest(wanted=wanted, listing=name):
                m = match(fiesta_listing(**LISTINGS[name]), strict([wanted]), fx_rate=FX)
                if result == "fail":
                    self.assertIsNone(m)
                    continue
                self.assertEqual(m.reasons["seller"].result, result)
                self.assertTrue(m.reasons["seller"].hard)
                self.assertNotIn("seller_type", m.reasons)       # no soft preference next to the hard one

    def test_fail_detail_names_the_seller_and_what_is_wanted(self):
        from intelligence.matching import evaluate as filters
        r = filters(fiesta_listing(**LISTINGS["inferred"]), strict(["private"]), fx_rate=FX).reasons["seller"]
        self.assertEqual((r.result, r.detail), ("fail", "vendedor posible agencia (publica 6 autos), se busca solo particulares"))
        r = filters(fiesta_listing(**LISTINGS["private"]), strict(["dealer"]), fx_rate=FX).reasons["seller"]
        self.assertEqual(r.detail, "vendedor particular, se busca solo agencias")
        r = filters(fiesta_listing(**LISTINGS["dealer"]), strict(["dealer"]), fx_rate=FX).reasons["seller"]
        self.assertEqual((r.result, r.detail), ("ok", "vendedor concesionaria"))

    def test_unknown_seller_passes_with_the_unknown_penalty(self):
        ev = run(strict(["private"]), "none")
        self.assertEqual(ev.match.unknown, ["seller"])
        self.assertAlmostEqual(ev.score.components["match"].c, 1.0 - CFG.curve("match")["unknown_penalty"])
        self.assertIn("vendedor no informado", ev.score.components["match"].explanation)
        self.assertEqual(ev.row()["match_reasons"]["seller"],
                         {"result": "unknown", "detail": "la publicación no lo informa", "kind": "hard"})
        self.assertLess(ev.score.score, run(strict(["private"]), "private").score.score)

    def test_strict_ok_scores_like_no_preference(self):
        """With the hard check active the soft one is left out: a private listing
        scores what it scores without any seller preference (2/2, not 3/3)."""
        pinned = SellerPreferencePinTests.PINNED
        ev = run(strict(["private"], seller_type="private"), "private")
        self.assertEqual(ev.score.score, pinned[(None, "private")][0])
        self.assertEqual(ev.score.components["match"].explanation, "cumple 2/2 preferencias")
        self.assertNotIn("seller_type", ev.row()["match_reasons"])

    def test_filter_name(self):
        self.assertEqual(copy.FILTER_NAMES["seller"], "vendedor")


class FlagOffTests(unittest.TestCase):
    """Without plan_feature('seller_filter') (Particular, a downgrade, a write by
    API) seller_types[0] is today's soft preference, byte for byte."""

    def test_flag_off_equals_the_soft_preference(self):
        pinned = SellerPreferencePinTests.PINNED
        for wanted in ("private", "dealer"):
            for name in LISTINGS:
                for flag in (False, None):
                    with self.subTest(wanted=wanted, listing=name, flag=flag):
                        p = strict([wanted], flag=flag)
                        if flag is None:
                            del p["seller_filter"]
                        ev = run(p, name)
                        score, level, c_match, _, explanation, reason = pinned[(wanted, name)]
                        self.assertEqual(ev.score.score, score)
                        self.assertEqual(ev.level, level)
                        self.assertAlmostEqual(ev.score.components["match"].c, c_match, places=4)
                        self.assertEqual(ev.score.components["match"].explanation, explanation)
                        self.assertEqual(ev.row()["match_reasons"].get("seller_type"), reason)
                        self.assertNotIn("seller", ev.row()["match_reasons"])

    def test_stored_preference_wins_over_the_first_type(self):
        ev = run(strict(["dealer"], flag=False, seller_type="private"), "private")
        self.assertEqual(ev.row()["match_reasons"]["seller_type"]["result"], "ok")

    def test_without_seller_types_the_flag_does_nothing(self):
        p = fiesta_profile()
        p["seller_filter"] = True
        self.assertFalse(strict_seller(p))
        self.assertNotIn("seller", run(p, "dealer").row()["match_reasons"])

    def test_malformed_types_are_ignored(self):
        for bad in ("private", ["dealer_inferred"], [], None, [1], {"a": 1}):
            with self.subTest(bad=bad):
                p = strict(bad)
                self.assertEqual(seller_types(p["filters"]), [])
                self.assertFalse(strict_seller(p))
        self.assertEqual(seller_types({"seller_types": ["private", "dealer"]}), ["private", "dealer"])


class LowResultsSellerTests(unittest.TestCase):
    MARKET = [{"make": "Ford", "model": "Focus", "year": 2015, "seller_type": t, "dealer_inferred": i}
              for t, i in (("dealer", False), ("dealer", False), ("private", True), ("private", False))]

    @staticmethod
    def profile(flag, **filters):
        return {"id": 7, "filters": {"make": "Ford", "model": "Focus", **filters}, "preferences": {},
                "origin_lat": None, "origin_lon": None, "radius_km": None, "seller_filter": flag}

    def test_seller_is_a_funnel_filter(self):
        self.assertIn("seller", lr.FILTERS)
        self.assertEqual(lr.LABEL["seller"], "vendedor")

    def test_seller_alone_is_the_main_blocker(self):
        fun = lr.funnel(self.MARKET, self.profile(True, seller_types=["private"]))
        self.assertEqual((fun.market, fun.matched), (4, 1))
        self.assertEqual(fun.only, {"seller": 3})
        self.assertEqual(fun.main_blocker, "seller")
        hints = lr.hints(fun, self.profile(True, seller_types=["private"]))
        self.assertTrue(any("El filtro de vendedor deja afuera 3" in h for h in hints))

    def test_flag_off_does_not_filter(self):
        fun = lr.funnel(self.MARKET, self.profile(False, seller_types=["private"]))
        self.assertEqual((fun.matched, fun.only), (4, {}))

    def test_job_profile_carries_the_flag(self):
        row = {"id": 7, "filters": {"make": "Ford", "model": "Focus", "seller_types": ["private"]},
               "preferences": {}, "origin_lat": None, "origin_lon": None, "radius_km": None,
               "seller_filter": True, "user_id": "u", "result_count": 0}
        self.assertTrue(job._profile(row)["seller_filter"])

    def test_fingerprint_of_todays_searches_is_unchanged(self):
        """Fixed with the code before PRO-01: today's diagnoses are not redone."""
        plain = {"id": 7, "filters": {"make": "Ford", "model": "Focus", "year_min": 2015}, "preferences": {},
                 "origin_lat": None, "origin_lon": None, "radius_km": None}
        self.assertEqual(lr.fingerprint(plain), "d11060828363a987")
        self.assertEqual(lr.fingerprint({**plain, "seller_filter": True}), "d11060828363a987")
        self.assertEqual(lr.fingerprint({**plain, "seller_filter": False}), "d11060828363a987")

    def test_fingerprint_follows_the_flag_with_seller_types(self):
        on = self.profile(True, seller_types=["private"])
        off = self.profile(False, seller_types=["private"])
        self.assertNotEqual(lr.fingerprint(on), lr.fingerprint(off))
        self.assertEqual(lr.fingerprint(on), lr.fingerprint(self.profile(True, seller_types=["private"])))

    def test_llm_context_names_the_strict_seller(self):
        p = self.profile(True, seller_types=["private"])
        ctx = lr.llm_context(lr.funnel(self.MARKET, p), p, 1)
        self.assertEqual(ctx["busqueda"]["vendedor"], "solo particulares")
        p = self.profile(False, seller_types=["private"])
        self.assertNotIn("vendedor", lr.llm_context(lr.funnel(self.MARKET, p), p, 1)["busqueda"])


if __name__ == "__main__":
    unittest.main()
