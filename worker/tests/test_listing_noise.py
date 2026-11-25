"""Ruido de avisos (docs/FB_DUPLICADOS_PLACEHOLDER_TERMINADOS.md). Pure: no database.

placeholder_f2: f2 scores a filler price as «sin precio» and caps at `match`; f3's shadow is the same either way.
repost_groups: one alert per car (notifications/repost_groups.py). ended_guard: service.active().
"""
from __future__ import annotations

import unittest
from dataclasses import replace

from intelligence.config import IntelligenceConfig, listing_noise
from intelligence.engine import evaluate
from notifications import repost_groups as rg
from notifications.engine import MATCH, NONE, PRICE_DROP, Audience, Event, Rules, decide_all
from notifications.service import active

from test_intelligence import CFG, FX, MARKET, NOW, fiesta_listing, fiesta_profile

ON = IntelligenceConfig.from_app_config({"listing_noise": {"placeholder_f2": True}})
RULES = Rules(alerts_max_per_user_day=10, price_drop_min_pct=3)


def placeholder_listing(**kw):
    return fiesta_listing(price=11_111.0, price_usd=11_111.0, **kw)


class SwitchTests(unittest.TestCase):
    def test_every_switch_is_off_by_default_and_for_garbage(self):
        off = {"placeholder_f2": False, "repost_groups": False, "ended_guard": False}
        for raw in (None, {}, [], "x", {"placeholder_f2": "true"}, {"repost_groups": 1}, {"ended_guard": None}):
            self.assertEqual(listing_noise(raw), off, raw)
        self.assertEqual(IntelligenceConfig().noise, off)

    def test_only_json_true_turns_one_on(self):
        self.assertEqual(listing_noise({"repost_groups": True, "other": True}),
                         {"placeholder_f2": False, "repost_groups": True, "ended_guard": False})


class PlaceholderF2Tests(unittest.TestCase):
    def ev(self, cfg, listing=None):
        return evaluate(listing or placeholder_listing(), fiesta_profile(), price_ref=MARKET, cfg=cfg, now=NOW,
                        fx_rate=FX)

    def test_off_is_the_same_as_before(self):
        a = self.ev(CFG)
        b = self.ev(IntelligenceConfig.from_app_config({"listing_noise": {"placeholder_f2": False}}))
        self.assertEqual(a.row(), b.row())
        self.assertIsNotNone(a.price_ref)

    def test_on_caps_at_match_with_no_price_credit(self):
        plain, capped = self.ev(CFG), self.ev(ON)
        self.assertIn(plain.level, ("good", "high"))            # the bug: a filler price alerts as a deal
        self.assertEqual(capped.level, "match")
        self.assertLess(capped.score.score, plain.score.score + 1)
        row = capped.row()
        self.assertEqual(row["score_breakdown"]["guard"], "placeholder")
        self.assertIsNone(row["price_ref"])                       # «sin precio»: no comparables, no diff for a threshold
        self.assertIsNone(capped.score.extra["diff_pct"])

    def test_a_credible_price_is_untouched(self):
        a = self.ev(CFG, fiesta_listing())
        b = self.ev(ON, fiesta_listing())
        self.assertEqual(a.row(), b.row())

    def test_a_down_payment_stays_excluded(self):
        far = replace(MARKET, diff_pct=80.0)
        ev = evaluate(placeholder_listing(), fiesta_profile(), price_ref=far, cfg=ON, now=NOW, fx_rate=FX)
        self.assertIsNone(ev)

    def test_f3_shadow_is_the_same_with_the_switch_on_or_off(self):
        f3_on = {"score_model_f3": {"mode": "shadow"}}
        off = IntelligenceConfig.from_app_config(f3_on)
        on = IntelligenceConfig.from_app_config({**f3_on, "listing_noise": {"placeholder_f2": True}})
        a, b = self.ev(off), self.ev(on)
        self.assertIsNotNone(a.shadow_f3)
        self.assertEqual(a.shadow_f3, b.shadow_f3)


def aud(user="u1"):
    return Audience(user, ("web",), "immediate", "good", 1)


def ev(listing, level="good", score=75, user="u1", **kw):
    return Event(MATCH, listing, aud(user), level=level, score=score, match_id=100 + listing, **kw)


class RepostGroupsTests(unittest.TestCase):
    def test_groups_are_connected_components(self):
        g = rg.groups([5, 3, 9, 7], [(3, 5), (5, 9)])
        self.assertEqual({g[3], g[5], g[9]}, {3})
        self.assertEqual(g[7], 7)

    def test_the_best_twin_of_a_batch_is_the_only_alert(self):
        events = [ev(1, "good", 72), ev(2, "high", 90), ev(3, "good", 80)]
        kept, dropped = rg.collapse(events, [(1, 2), (2, 3)], set())
        self.assertEqual([e.listing_id for e in kept], [2])
        self.assertEqual({o.reason for o in dropped.values()}, {rg.R_REPOST_GROUP})
        self.assertEqual(len(dropped), 2)
        self.assertTrue(all(o.result == NONE for o in dropped.values()))

    def test_ties_keep_the_lowest_listing_id(self):
        kept, _ = rg.collapse([ev(4), ev(2)], [(2, 4)], set())
        self.assertEqual([e.listing_id for e in kept], [2])

    def test_each_user_keeps_their_own_alert(self):
        events = [ev(1, user="a"), ev(2, user="b")]
        kept, dropped = rg.collapse(events, [(1, 2)], set())
        self.assertEqual(len(kept), 2)
        self.assertEqual(dropped, {})

    def test_two_profiles_of_the_same_listing_both_stay_for_decide_all_to_pick(self):
        events = [ev(1, "good", 70), ev(1, "high", 90), ev(2, "high", 95)]
        kept, _ = rg.collapse(events, [(1, 2)], set())
        self.assertEqual({e.listing_id for e in kept}, {2})
        kept, _ = rg.collapse(events[:2], [], set())
        self.assertEqual(len(kept), 2)

    def test_a_twin_already_alerted_to_that_user_gets_nothing(self):
        events = [ev(1, user="a"), ev(2, user="b")]
        kept, dropped = rg.collapse(events, [], {("a", 1)})
        self.assertEqual([e.audience.user_id for e in kept], ["b"])
        self.assertEqual(next(iter(dropped.values())).reason, rg.R_REPOST_ALERTED)

    def test_an_alerted_listing_does_not_block_a_twin_of_a_different_user_event(self):
        # user a was alerted about twin of 1; their event for 2 (same group, not alerted-twin) still competes alone.
        events = [ev(1, "high", 95, user="a"), ev(2, "good", 70, user="a")]
        kept, dropped = rg.collapse(events, [(1, 2)], {("a", 1)})
        self.assertEqual([e.listing_id for e in kept], [2])
        self.assertEqual(dropped[id(events[0])].reason, rg.R_REPOST_ALERTED)

    def test_price_drops_and_other_events_pass_untouched(self):
        drop = Event(PRICE_DROP, 1, aud(), level="good", score=75, drop_pct=10.0, snapshot_id=1)
        kept, dropped = rg.collapse([drop, ev(1)], [], {("u1", 1)})
        self.assertEqual(kept, [drop])
        self.assertEqual(len(dropped), 1)

    def test_with_decide_all_one_alert_per_car(self):
        events = [ev(1, "good", 72), ev(2, "high", 90), ev(3, "good", 80)]
        kept, _ = rg.collapse(events, [(1, 2), (2, 3)], set())
        out = decide_all(kept, RULES)
        self.assertEqual({d.listing_id for d in out}, {2})

    def test_the_repost_rule_of_the_engine_still_alerts_a_car_never_sent(self):
        # The original was never alerted to the user: its repost alerts, labelled re-publicado.
        events = [ev(2, "good", 75, repost=True)]
        kept, dropped = rg.collapse(events, [], set())
        out = decide_all(kept, RULES)
        self.assertEqual(dropped, {})
        self.assertTrue(all(d.payload.get("repost") for d in out) and out)


class EndedGuardTests(unittest.TestCase):
    def test_active_rows(self):
        self.assertTrue(active(None))
        self.assertTrue(active({"status": "active"}))
        self.assertTrue(active({}))
        self.assertFalse(active({"status": "gone"}))


if __name__ == "__main__":
    unittest.main()
