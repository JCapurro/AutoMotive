"""Trim blando (docs/TRIM_BLANDO.md): with app_config.trim_soft_cap on, a car of another version than the one a
non-strict search names never goes above `match` (no alert), in f2 and in what f3 records. Pure."""
from __future__ import annotations

import unittest

from intelligence import matching
from intelligence.config import IntelligenceConfig, switch_enabled
from intelligence.engine import assess, evaluate
from notifications.engine import Audience, Event, Rules, classify
from test_intelligence import FX, MARKET, NOW, fiesta_listing, fiesta_profile

OFF = IntelligenceConfig()
ON = IntelligenceConfig.from_app_config({"trim_soft_cap": {"enabled": True}})
ON_SHADOW = IntelligenceConfig.from_app_config({"trim_soft_cap": {"enabled": True},
                                                "score_model_f3": {"mode": "shadow"}})
OFF_SHADOW = IntelligenceConfig.from_app_config({"score_model_f3": {"mode": "shadow"}})


def ev(cfg, listing=None, profile=None):
    return evaluate(listing or fiesta_listing(), profile or fiesta_profile(), price_ref=MARKET, cfg=cfg, now=NOW,
                    fx_rate=FX)


OTHER = fiesta_listing(trim="SE Plus", title="Ford Fiesta SE Plus 1.6 2017")


class SwitchTests(unittest.TestCase):
    def test_off_unless_a_real_true(self):
        self.assertFalse(OFF.trim_soft_cap)
        for raw in (None, {}, {"enabled": False}, {"enabled": "true"}, {"enabled": 1}, "on", True):
            self.assertFalse(switch_enabled(raw), raw)
        self.assertTrue(switch_enabled({"enabled": True}))
        self.assertTrue(ON.trim_soft_cap)


class OtherTrimSoftTests(unittest.TestCase):
    def check(self, listing, profile):
        return matching.other_trim_soft(matching.evaluate(listing, profile, fx_rate=FX), profile)

    def test_other_version_in_a_soft_search(self):
        self.assertTrue(self.check(OTHER, fiesta_profile()))

    def test_the_asked_version_is_not(self):
        self.assertFalse(self.check(fiesta_listing(), fiesta_profile()))
        self.assertFalse(self.check(fiesta_listing(trim="1.6 Titanium"), fiesta_profile()))

    def test_unknown_version_is_untouched(self):
        self.assertFalse(self.check(fiesta_listing(trim=None), fiesta_profile()))

    def test_strict_search_is_untouched(self):
        # trim_strict filters the car out already: the cap has nothing to do.
        self.assertFalse(self.check(OTHER, fiesta_profile(trim_strict=True)))

    def test_a_taste_without_filters_trims_is_not_a_version_asked_for(self):
        profile = fiesta_profile(trims=[])
        self.assertFalse(self.check(OTHER, profile))
        profile = fiesta_profile()
        del profile["filters"]["trims"]
        self.assertFalse(self.check(OTHER, profile))


class F2CapTests(unittest.TestCase):
    def test_other_version_is_high_without_the_switch(self):
        # The problem: a good price makes the other version an opportunity.
        e = ev(OFF, OTHER)
        self.assertIn(e.level, ("high", "good"))
        self.assertNotIn("trim_cap", e.score.breakdown())

    def test_switch_on_caps_at_match_and_keeps_the_score(self):
        e0, e1 = ev(OFF, OTHER), ev(ON, OTHER)
        self.assertEqual(e1.level, "match")
        self.assertEqual(e1.score.score, e0.score.score)        # the order of the list uses the score; the cap is the level
        self.assertTrue(e1.score.breakdown()["trim_cap"])
        self.assertTrue(e1.row()["score_breakdown"]["trim_cap"])

    def test_the_version_asked_for_is_untouched(self):
        self.assertEqual(ev(ON).level, ev(OFF).level)
        self.assertEqual(ev(ON).row()["score"], ev(OFF).row()["score"])
        self.assertNotIn("trim_cap", ev(ON).row()["score_breakdown"])

    def test_unknown_version_is_untouched(self):
        l = fiesta_listing(trim=None)
        self.assertEqual(ev(ON, l).level, ev(OFF, l).level)
        self.assertNotIn("trim_cap", ev(ON, l).row()["score_breakdown"])

    def test_strict_search_is_untouched(self):
        p = fiesta_profile(trim_strict=True)
        self.assertIsNone(ev(ON, OTHER, p))          # hard filter: not a match at all, as before
        self.assertIsNone(ev(OFF, OTHER, p))

    def test_it_never_raises_a_lower_level(self):
        # A listing already below match stays where it was (cap only lowers).
        low = fiesta_listing(trim="SE Plus", price=40_000.0, price_usd=40_000.0)
        e = evaluate(low, fiesta_profile(price_max=50_000), price_ref=MARKET, cfg=ON, now=NOW, fx_rate=FX)
        self.assertIn(e.level, ("low", "match"))

    def test_the_other_guards_still_apply(self):
        # No year: capped at good by its own guard; the trim cap brings it to match.
        l = fiesta_listing(trim="SE Plus", year=None)
        p = fiesta_profile(year_min=None, year_max=None)
        self.assertEqual(evaluate(l, p, price_ref=MARKET, cfg=ON, now=NOW, fx_rate=FX).level, "match")


class AlertTests(unittest.TestCase):
    """What the cap is for: the engine gives no alert to a `match` under the default notify_min_level."""

    def event(self, level):
        return Event("match", 1, Audience("u", channels=("email",), min_level="good"), level=level, score=80)

    def test_a_capped_car_does_not_alert(self):
        self.assertIsNone(classify(self.event(ev(ON, OTHER).level), Rules()))
        self.assertIsNotNone(classify(self.event(ev(OFF, OTHER).level), Rules()))


class F3ShadowTests(unittest.TestCase):
    def js(self, cfg, listing=OTHER):
        return ev(cfg, listing).row()["score_breakdown"]["shadow_f3"]

    def test_f3_level_is_capped_and_says_so(self):
        off = self.js(OFF_SHADOW)
        self.assertIn(off["level"], ("high", "good"))          # the fixture: a good price on another version
        on = self.js(ON_SHADOW)
        self.assertEqual(on["trim"], {"capped": off["level"] in ("high", "good")})
        self.assertEqual(on["level"], "match" if off["level"] in ("high", "good") else off["level"])
        self.assertEqual(on["level_uncapped"], off["level_uncapped"])
        self.assertEqual(on["mode"], "shadow")                     # its mode is never touched
        self.assertEqual(on["params"], off["params"])

    def test_f3_is_untouched_for_the_version_asked_for(self):
        self.assertEqual(self.js(ON_SHADOW, fiesta_listing()), self.js(OFF_SHADOW, fiesta_listing()))

    def test_f3_off_stays_off(self):
        self.assertNotIn("shadow_f3", ev(ON, OTHER).row()["score_breakdown"])


if __name__ == "__main__":
    unittest.main()
