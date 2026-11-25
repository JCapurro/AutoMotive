"""Oportunidad creible (docs/OPORTUNIDAD_CREIBLE.md): with app_config.opportunity_gate on, `opportunity` asks for
diff_pct >= min_pct over n >= min_n comparables; a high that does not reach it is still alerted, as new_match. Pure."""
from __future__ import annotations

import unittest

from intelligence.config import DEFAULT_OPPORTUNITY_GATE, opportunity_gate
from notifications.engine import (MATCH, PRICE_DROP, Audience, Event, Rules, classify, credible_opportunity,
                                  decide, decide_all)

OFF = Rules()
ON = Rules(opportunity_gate=True, opportunity_min_pct=15.0, opportunity_min_n=10)


def payload(diff, n=23):
    match = {"score": 90, "level": "high", "diff_pct": diff}
    if n is not None:
        match["price_ref"] = {"n": n, "level_used": "model", "median": 11200.0, "diff_pct": diff}
    return {"match": match}


def high(diff, n=23, *, level="high", min_level="good", repost=False, audience=None, listing=10, frequency="immediate"):
    a = audience or Audience("u1", ("email",), frequency, min_level, 1)
    return Event(MATCH, listing, a, level=level, score=90, match_id=100 + listing, repost=repost,
                 payload=payload(diff, n))


def shape(decisions):
    return sorted({(d.kind, d.status, d.dedupe_key) for d in decisions})


class ConfigTests(unittest.TestCase):
    def test_off_by_default_and_ten_comparables_fifteen_percent(self):
        self.assertEqual(DEFAULT_OPPORTUNITY_GATE, {"enabled": False, "min_pct": 15, "min_n": 10})
        self.assertFalse(Rules().opportunity_gate)
        self.assertEqual((Rules().opportunity_min_pct, Rules().opportunity_min_n), (15.0, 10))

    def test_reads_the_row_key_by_key(self):
        self.assertEqual(opportunity_gate(None), DEFAULT_OPPORTUNITY_GATE)
        self.assertEqual(opportunity_gate({"enabled": True}), {"enabled": True, "min_pct": 15, "min_n": 10})
        self.assertEqual(opportunity_gate({"enabled": True, "min_pct": 20, "min_n": 12}),
                         {"enabled": True, "min_pct": 20, "min_n": 12})

    def test_bad_values_fall_back(self):
        for raw in ({"enabled": "true"}, {"enabled": 1}, "on", []):
            self.assertFalse(opportunity_gate(raw)["enabled"], raw)
        bad = opportunity_gate({"enabled": True, "min_pct": "15", "min_n": 0})
        self.assertEqual((bad["min_pct"], bad["min_n"]), (15, 10))
        bad = opportunity_gate({"enabled": True, "min_pct": 101, "min_n": 2.5})
        self.assertEqual((bad["min_pct"], bad["min_n"]), (15, 10))


class GateTests(unittest.TestCase):
    def test_gate_off_every_high_is_an_opportunity_as_before(self):
        for diff, n in ((3, 4), (None, None), (40, 23)):
            self.assertEqual(shape(decide(high(diff, n), OFF)), [("opportunity", "queued", "match:10")])

    def test_credible_discount_is_an_opportunity(self):
        self.assertEqual(shape(decide(high(15, 10), ON)), [("opportunity", "queued", "match:10")])
        self.assertEqual(shape(decide(high(32.5, 40), ON)), [("opportunity", "queued", "match:10")])

    def test_a_short_discount_is_a_new_match_with_the_same_key_and_delivery(self):
        out = decide(high(14.9, 23), ON)
        self.assertEqual(shape(out), [("new_match", "queued", "match:10")])
        same = decide(high(14.9, 23), OFF)
        self.assertEqual([(d.channel, d.status, d.dedupe_key, d.payload) for d in out],
                         [(d.channel, d.status, d.dedupe_key, d.payload) for d in same])

    def test_few_comparables_is_a_new_match(self):
        self.assertEqual(shape(decide(high(30, 9), ON)), [("new_match", "queued", "match:10")])

    def test_without_the_numbers_it_cannot_be_proved(self):
        self.assertEqual(shape(decide(high(None, None), ON)), [("new_match", "queued", "match:10")])
        self.assertEqual(shape(decide(high(30, None), ON)), [("new_match", "queued", "match:10")])
        self.assertEqual(shape(decide(high(None, 30), ON)), [("new_match", "queued", "match:10")])
        self.assertFalse(credible_opportunity(Event(MATCH, 1, Audience("u"), level="high"), ON))

    def test_thresholds_come_from_the_rules(self):
        strict = Rules(opportunity_gate=True, opportunity_min_pct=20.0, opportunity_min_n=12)
        self.assertEqual(shape(decide(high(19, 23), strict))[0][0], "new_match")
        self.assertEqual(shape(decide(high(20, 11), strict))[0][0], "new_match")
        self.assertEqual(shape(decide(high(20, 12), strict))[0][0], "opportunity")

    def test_only_a_high_can_be_an_opportunity(self):
        self.assertEqual(shape(decide(high(40, 40, level="good"), ON))[0][0], "new_match")

    def test_a_repost_stays_a_new_match(self):
        self.assertEqual(shape(decide(high(40, 40, repost=True), ON))[0][0], "new_match")

    def test_nobody_loses_an_alert(self):
        """Gate on or off, the same events get the same decisions but for the kind."""
        cases = [(3, 4), (14, 30), (15, 9), (16, 10), (None, None), (50, 50)]
        events = [high(d, n, listing=i) for i, (d, n) in enumerate(cases)]
        on = decide_all(events, ON)
        off = decide_all(events, OFF)

        def strip(ds):
            return sorted((d.user_id, d.channel, d.status, d.dedupe_key, d.listing_id) for d in ds)

        self.assertEqual(strip(on), strip(off))
        self.assertEqual({d.kind for d in off}, {"opportunity"})
        self.assertEqual(sorted(d.listing_id for d in on if d.kind == "opportunity"), [3, 5])

    def test_the_cap_and_the_digest_do_not_change(self):
        out = decide(high(5, 3), ON, sent_today=10, cap=10)
        self.assertEqual([(d.kind, d.status, d.payload.get("degraded")) for d in out],
                         [("new_match", "digest", "daily_cap")])
        out = decide(high(5, 3, frequency="daily"), ON)
        self.assertEqual([(d.kind, d.status) for d in out], [("new_match", "digest")])

    def test_below_the_minimum_level_still_nothing(self):
        self.assertIsNone(classify(high(40, 40, level="match"), ON))

    def test_price_drops_are_untouched(self):
        e = Event(PRICE_DROP, 10, Audience("u1", ("email",), "immediate", "good", 1), level="high", saved=True,
                  drop_pct=8.0, snapshot_id=3, payload=payload(5, 3))
        self.assertEqual(classify(e, ON).kind, "price_drop")


class ProThresholdTests(unittest.TestCase):
    """The Pro thresholds do not change: an event that reaches one keeps its kind and its delivery."""

    def pro(self, pct=None, usd=None):
        return Audience("u1", ("email",), "immediate", "good", 1, pct, usd)

    def test_reaching_the_users_own_threshold_keeps_opportunity_outside_the_cap(self):
        e = high(11, 3, audience=self.pro(10))
        on, off = classify(e, ON), classify(e, OFF)
        self.assertEqual((on.kind, on.status, on.capped, on.threshold),
                         (off.kind, off.status, off.capped, off.threshold))
        self.assertEqual((on.kind, on.threshold), ("opportunity", True))

    def test_a_high_below_the_users_threshold_goes_to_the_digest_as_before(self):
        e = high(11, 30, audience=self.pro(12))
        on, off = classify(e, ON), classify(e, OFF)
        self.assertEqual((on.status, on.capped, on.threshold), (off.status, off.capped, off.threshold))
        self.assertEqual((on.status, on.kind, off.kind), ("digest", "new_match", "opportunity"))

    def test_usd_threshold_is_untouched(self):
        e = Event(MATCH, 10, self.pro(None, 500), level="high", score=90,
                  payload={**payload(11, 3), "margin": {"usd_low": 800.0}})
        on = classify(e, ON)
        self.assertEqual((on.kind, on.status, on.threshold), ("opportunity", "queued", True))


if __name__ == "__main__":
    unittest.main()
