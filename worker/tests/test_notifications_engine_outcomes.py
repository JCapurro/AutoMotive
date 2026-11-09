"""decide_all's `outcomes` side channel (the f3 shadow's decision log, spec §4.4). Pure.

The decisions are the same with or without it, over every scenario of test_notifications_engine and
test_notifications_margin; and each exit an event can take records its reason.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import test_notifications_engine as engine_tests
import test_notifications_margin as margin_tests
from notifications import engine
from notifications.engine import (DIGEST, LISTING_GONE, MATCH, NONE, PRICE_DROP, QUEUED, Audience, Event, Outcome,
                                  Rules, classify, decide_all, why_not)


RULES = Rules(alerts_max_per_user_day=10, price_drop_min_pct=3)


def aud(user="u1", *, channels=("telegram", "web"), frequency="immediate", min_level="good", profile_id=1,
        threshold_pct=None, threshold_usd=None) -> Audience:
    return Audience(user, tuple(channels), frequency, min_level, profile_id, threshold_pct, threshold_usd)


def match(level, *, listing=10, audience=None, score=None, **kw) -> Event:
    score = score if score is not None else {"high": 90, "good": 75, "match": 60, "low": 30}.get(level, 0)
    return Event(MATCH, listing, audience or aud(), level=level, score=score, match_id=100 + listing, **kw)


class SameDecisionsTests(unittest.TestCase):
    def test_every_engine_and_margin_scenario_decides_the_same(self):
        calls = []
        real = engine.decide_all

        def both(events, rules, **kw):
            events = list(events)
            plain = real(events, rules, **kw)
            outcomes: dict[int, Outcome] = {}
            traced = real(events, rules, **kw, outcomes=outcomes)
            self.assertEqual(traced, plain)
            self.assertEqual(set(outcomes), {id(e) for e in events})
            queued_or_digest = {id(e) for e in events if outcomes[id(e)].result != NONE}
            self.assertEqual(len(queued_or_digest), len({(d.user_id, d.dedupe_key) for d in plain}))
            calls.append(len(events))
            return plain

        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for module in (engine_tests, margin_tests):
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj.__module__ == module.__name__:
                    suite.addTests(loader.loadTestsFromTestCase(obj))
        with patch.object(engine_tests, "decide_all", both), patch.object(margin_tests, "decide_all", both):
            result = unittest.TestResult()
            suite.run(result)
        self.assertEqual(result.errors + result.failures, [])
        self.assertGreater(len(calls), 15)


class ReasonTests(unittest.TestCase):
    def outcome(self, events, event=None, **kw) -> Outcome:
        outcomes: dict[int, Outcome] = {}
        decide_all(events, kw.pop("rules", RULES), outcomes=outcomes, **kw)
        return outcomes[id(event or events[0])]

    def test_plain_immediate_alerts(self):
        self.assertEqual(self.outcome([match("high")]), Outcome(QUEUED, None, "opportunity", False))
        self.assertEqual(self.outcome([match("good")]), Outcome(QUEUED, None, "new_match", False))
        self.assertEqual(self.outcome([match("high", repost=True)]), Outcome(QUEUED, None, "new_match", False))

    def test_no_plan(self):
        self.assertEqual(self.outcome([match("match")]), Outcome(NONE, "below_min_level"))
        self.assertEqual(self.outcome([match("high", backfill=True)]), Outcome(NONE, "backfill"))
        self.assertEqual(self.outcome([match(None)]), Outcome(NONE, "no_level"))
        self.assertEqual(self.outcome([match("high", status="discarded")]), Outcome(NONE, "discarded"))

    def test_dedupe(self):
        e = match("high")
        self.assertEqual(self.outcome([e], existing={("u1", "match:10")}),
                         Outcome(NONE, "dedupe_existing", "opportunity", False))
        # Two profiles of one user, one listing: the higher level wins, the other is a batch dedupe.
        a, b = match("good", audience=aud(profile_id=1)), match("high", audience=aud(profile_id=2))
        self.assertEqual(self.outcome([a, b], a), Outcome(NONE, "dedupe_batch", "new_match", False))
        self.assertEqual(self.outcome([a, b], b).result, QUEUED)

    def test_no_channels(self):
        self.assertEqual(self.outcome([match("high", audience=aud(channels=()))]),
                         Outcome(NONE, "no_channels", "opportunity", False))

    def test_daily_cap(self):
        events = [match("high", listing=i) for i in range(1, 4)]
        out: dict[int, Outcome] = {}
        decide_all(events, Rules(alerts_max_per_user_day=2), outcomes=out)
        self.assertEqual([out[id(e)].result for e in events], [QUEUED, QUEUED, DIGEST])
        self.assertEqual(out[id(events[2])], Outcome(DIGEST, "daily_cap", "opportunity", False))

    def test_frequency(self):
        self.assertEqual(self.outcome([match("good", audience=aud(frequency="daily"))]),
                         Outcome(DIGEST, "frequency", "new_match", False))

    def test_threshold(self):
        reached = match("match", audience=aud(threshold_pct=20), payload={"match": {"diff_pct": 25.0}})
        self.assertEqual(self.outcome([reached]), Outcome(QUEUED, "threshold", "new_match", True))
        short = match("good", audience=aud(threshold_pct=20), payload={"match": {"diff_pct": 10.0}})
        self.assertEqual(self.outcome([short]), Outcome(DIGEST, "threshold_not_reached", "new_match", False))
        below = match("match", audience=aud(threshold_pct=20), payload={"match": {"diff_pct": 10.0}})
        self.assertEqual(self.outcome([below]), Outcome(NONE, "below_min_level"))

    def test_threshold_alerts_do_not_count_towards_the_cap(self):
        hit = match("high", listing=1, audience=aud(threshold_pct=5), payload={"match": {"diff_pct": 30.0}})
        out: dict[int, Outcome] = {}
        decide_all([hit], Rules(alerts_max_per_user_day=0), outcomes=out)
        self.assertEqual(out[id(hit)], Outcome(QUEUED, "threshold", "opportunity", True))

    def test_other_kinds(self):
        drop = Event(PRICE_DROP, 10, aud(), level="good", drop_pct=1.0)
        self.assertEqual(self.outcome([drop]), Outcome(NONE, "drop_below_min"))
        drop = Event(PRICE_DROP, 10, aud(), level="low", drop_pct=10.0)
        self.assertEqual(self.outcome([drop]), Outcome(NONE, "not_matched"))
        gone = Event(LISTING_GONE, 10, aud())
        self.assertEqual(self.outcome([gone]), Outcome(NONE, "not_followed"))
        saved_drop = Event(PRICE_DROP, 10, aud(), level="low", drop_pct=10.0, saved=True)
        self.assertEqual(self.outcome([saved_drop]).result, QUEUED)


class WhyNotTests(unittest.TestCase):
    def test_why_not_is_set_exactly_when_classify_gives_nothing(self):
        events = []
        for level in ("high", "good", "match", "low", None):
            for min_level in ("high", "good", "match", "low"):
                for kw in ({}, {"backfill": True}, {"repost": True}, {"status": "discarded"},
                           {"status": "discarded", "saved": True}):
                    for threshold, diff in ((None, None), (20, 25.0), (20, 5.0), (20, None)):
                        events.append(match(level, audience=aud(min_level=min_level, threshold_pct=threshold),
                                            payload={"match": {"diff_pct": diff}}, **kw))
        for drop in (None, 1.0, 5.0):
            for level in ("good", "low", None):
                for saved in (False, True):
                    events.append(Event(PRICE_DROP, 10, aud(), level=level, drop_pct=drop, saved=saved))
        for saved, status in ((False, None), (True, None), (False, "contacted")):
            events.append(Event(LISTING_GONE, 10, aud(), saved=saved, status=status))
        events.append(Event("other", 10, aud()))
        for e in events:
            with self.subTest(event=e):
                plan = classify(e, RULES)
                reason = why_not(e, RULES)
                self.assertEqual(reason is None, plan is not None)
                if plan is None:
                    self.assertIsInstance(reason, str)

    def test_match_events_need_no_rules(self):
        self.assertEqual(why_not(match("match")), "below_min_level")
        self.assertIsNone(why_not(match("high")))


if __name__ == "__main__":
    unittest.main()
