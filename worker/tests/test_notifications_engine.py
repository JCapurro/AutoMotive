"""engine.decide: the decision table of sección 7.1. Pure, no database."""
from __future__ import annotations

import unittest

from notifications.engine import (DEGRADED_CAP, LISTING_GONE, MATCH, PRICE_DROP, Audience, Event, Rules,
                                  decide, decide_all)


RULES = Rules(alerts_max_per_user_day=10, price_drop_min_pct=3)


def aud(user="u1", *, channels=("telegram", "web"), frequency="immediate", min_level="good",
        profile_id=1) -> Audience:
    return Audience(user, tuple(channels), frequency, min_level, profile_id)


def match(level, *, score=None, listing=10, audience=None, **kw) -> Event:
    score = score if score is not None else {"high": 90, "good": 75, "match": 60, "low": 30}[level]
    return Event(MATCH, listing, audience or aud(), level=level, score=score, match_id=100 + listing, **kw)


def kinds(decisions):
    return sorted({(d.kind, d.status) for d in decisions})


class NewMatchTableTests(unittest.TestCase):
    def test_high_is_an_opportunity(self):
        out = decide(match("high"), RULES)
        self.assertEqual(kinds(out), [("opportunity", "queued")])
        self.assertEqual({d.channel for d in out}, {"telegram", "web"})
        self.assertEqual({d.dedupe_key for d in out}, {"match:10"})

    def test_with_min_level_high_only_high_notifies(self):
        # notify_min_level = high: only 🔥 notifies.
        self.assertEqual(decide(match("good", audience=aud(min_level="high")), RULES), [])
        self.assertEqual(kinds(decide(match("high", audience=aud(min_level="high")), RULES)),
                         [("opportunity", "queued")])

    def test_at_or_above_the_minimum_is_a_new_match(self):
        self.assertEqual(kinds(decide(match("good"), RULES)), [("new_match", "queued")])
        self.assertEqual(kinds(decide(match("match", audience=aud(min_level="match")), RULES)),
                         [("new_match", "queued")])

    def test_below_the_minimum_is_only_web_and_digest(self):
        self.assertEqual(decide(match("match"), RULES), [])
        self.assertEqual(decide(match("low", audience=aud(min_level="match")), RULES), [])

    def test_backfill_never_notifies(self):
        self.assertEqual(decide(match("high", backfill=True), RULES), [])

    def test_repost_is_a_new_match_with_the_label(self):
        out = decide(match("high", repost=True), RULES)
        self.assertEqual(kinds(out), [("new_match", "queued")])
        self.assertTrue(all(d.payload.get("repost") for d in out))
        # "según nivel": below the minimum a repost is silent too.
        self.assertEqual(decide(match("match", repost=True), RULES), [])

    def test_daily_frequency_goes_to_the_digest(self):
        self.assertEqual(kinds(decide(match("high", audience=aud(frequency="daily")), RULES)),
                         [("opportunity", "digest")])

    def test_a_discarded_listing_is_not_notified(self):
        self.assertEqual(decide(match("high", status="discarded"), RULES), [])

    def test_no_deliverable_channel_no_notification(self):
        self.assertEqual(decide(match("high", audience=aud(channels=())), RULES), [])


class PriceDropTableTests(unittest.TestCase):
    def drop(self, pct=6.1, **kw) -> Event:
        kw.setdefault("audience", aud())
        return Event(PRICE_DROP, 10, snapshot_id=77, drop_pct=pct, **kw)

    def test_a_saved_listing_is_always_immediate(self):
        out = decide(self.drop(saved=True, audience=aud(frequency="daily")), RULES)
        self.assertEqual(kinds(out), [("price_drop", "queued")])
        self.assertEqual({d.dedupe_key for d in out}, {"price_drop:10:77"})

    def test_a_match_of_level_match_or_more(self):
        self.assertEqual(kinds(decide(self.drop(level="match", score=60), RULES)), [("price_drop", "queued")])
        self.assertEqual(kinds(decide(self.drop(level="good", audience=aud(frequency="daily")), RULES)),
                         [("price_drop", "digest")])

    def test_low_matches_and_strangers_are_not_notified(self):
        self.assertEqual(decide(self.drop(level="low", score=20), RULES), [])
        self.assertEqual(decide(self.drop(), RULES), [])

    def test_below_price_drop_min_pct(self):
        self.assertEqual(decide(self.drop(pct=2.9, saved=True), RULES), [])
        self.assertEqual(kinds(decide(self.drop(pct=3.0, saved=True), RULES)), [("price_drop", "queued")])

    def test_each_snapshot_is_its_own_drop(self):
        a = decide(self.drop(saved=True), RULES)[0].dedupe_key
        b = decide(Event(PRICE_DROP, 10, aud(), snapshot_id=78, drop_pct=5, saved=True), RULES)[0].dedupe_key
        self.assertNotEqual(a, b)


class ListingGoneTableTests(unittest.TestCase):
    def test_saved_or_followed_goes_to_the_digest(self):
        for kw in ({"saved": True}, {"status": "interested"}, {"status": "contacted"},
                   {"status": "visit_scheduled"}):
            with self.subTest(**kw):
                out = decide(Event(LISTING_GONE, 10, aud(), **kw), RULES)
                self.assertEqual(kinds(out), [("listing_gone", "digest")])
                self.assertEqual({d.dedupe_key for d in out}, {"listing_gone:10"})

    def test_a_listing_only_matched_is_not_followed(self):
        self.assertEqual(decide(Event(LISTING_GONE, 10, aud(), level="high", score=90), RULES), [])
        self.assertEqual(decide(Event(LISTING_GONE, 10, aud(), status="seen"), RULES), [])


class DailyCapTests(unittest.TestCase):
    def test_past_the_cap_an_immediate_alert_becomes_digest(self):
        rules = Rules(alerts_max_per_user_day=2)
        out = decide(match("high"), rules, sent_today=2)
        self.assertEqual(kinds(out), [("opportunity", "digest")])
        self.assertTrue(all(d.payload["degraded"] == DEGRADED_CAP for d in out))

    def test_the_third_alert_of_the_day_goes_to_the_digest(self):
        rules = Rules(alerts_max_per_user_day=2)
        events = [match("high", listing=i, score=90 - i) for i in (1, 2, 3)]
        out = decide_all(events, rules)
        by_listing = {d.listing_id: d.status for d in out}
        self.assertEqual(by_listing, {1: "queued", 2: "queued", 3: "digest"})
        # Two channels each, one alert per listing.
        self.assertEqual(len(out), 6)

    def test_counts_per_user(self):
        rules = Rules(alerts_max_per_user_day=1)
        out = decide_all([match("high", listing=1), match("high", listing=2, audience=aud("u2"))], rules)
        self.assertEqual({d.status for d in out}, {"queued"})

    def test_already_sent_today_counts(self):
        out = decide_all([match("high")], Rules(alerts_max_per_user_day=3), sent_today={"u1": 3})
        self.assertEqual({d.status for d in out}, {"digest"})

    def test_a_saved_price_drop_is_not_capped(self):
        out = decide(Event(PRICE_DROP, 10, aud(), snapshot_id=1, drop_pct=10, saved=True),
                     Rules(alerts_max_per_user_day=0), sent_today=5)
        self.assertEqual(kinds(out), [("price_drop", "queued")])

    def test_digest_alerts_do_not_use_the_cap(self):
        rules = Rules(alerts_max_per_user_day=1)
        events = [match("high", listing=1, audience=aud(frequency="daily")), match("high", listing=2)]
        out = decide_all(events, rules)
        self.assertEqual({d.listing_id: d.status for d in out}, {1: "digest", 2: "queued"})


class DedupeAndMultiProfileTests(unittest.TestCase):
    def test_already_notified_keys_are_skipped_and_not_counted(self):
        rules = Rules(alerts_max_per_user_day=1)
        out = decide_all([match("high", listing=1), match("high", listing=2)], rules,
                         existing={("u1", "match:1")})
        self.assertEqual({(d.listing_id, d.status) for d in out}, {(2, "queued")})

    def test_one_alert_per_listing_whatever_the_level(self):
        # new_match and opportunity share the key: a listing is announced once.
        out = decide_all([match("good"), match("high")], RULES, existing={("u1", "match:10")})
        self.assertEqual(out, [])

    def test_several_profiles_one_notification_with_the_highest_level(self):
        a = aud(profile_id=1, channels=("telegram",))
        b = aud(profile_id=2, channels=("telegram",))
        out = decide_all([match("good", audience=a), match("high", audience=b)], RULES)
        self.assertEqual(len(out), 1)
        self.assertEqual((out[0].kind, out[0].profile_id), ("opportunity", 2))

    def test_the_highest_level_that_notifies_wins(self):
        # Profile 1 has the better match but only wants 🔥; profile 2's
        # lower match is the one that notifies.
        silent = aud(profile_id=1, min_level="high", channels=("telegram",))
        loud = aud(profile_id=2, min_level="match", channels=("telegram",))
        out = decide_all([match("good", audience=silent, score=80), match("match", audience=loud)], RULES)
        self.assertEqual([(d.kind, d.profile_id) for d in out], [("new_match", 2)])

    def test_the_same_price_drop_through_two_profiles_is_one(self):
        e1 = Event(PRICE_DROP, 10, aud(profile_id=1), level="good", score=75, snapshot_id=5, drop_pct=6)
        e2 = Event(PRICE_DROP, 10, aud(profile_id=2), level="high", score=88, snapshot_id=5, drop_pct=6)
        out = decide_all([e1, e2], RULES)
        self.assertEqual({(d.profile_id, d.channel) for d in out}, {(2, "telegram"), (2, "web")})


if __name__ == "__main__":
    unittest.main()
