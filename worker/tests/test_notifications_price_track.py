"""PAR-03: a listing's price drops since we first saw it, and its age, in the
opportunity email and the digest (docs/superpowers/specs/2026-10-29-par03-dias-y-bajas-design.md)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from intelligence import copy
from normalization.normalize import normalize_text
from notification_fixtures import (DIGEST, FIESTA, LINKS, NEW_MATCH, NOW, OPPORTUNITY, PRICE_DROP, TRACK_1,
                                   notification)
from notifications import digest, service, templates


def track(**kw):
    return {"drops": 1, "cum_pct": 6.3, "cum_usd": 1500.0, "currency": "USD",
            "first_at": "2026-09-20T12:00:00+00:00", **kw}


def row(listing_id=501, **kw):
    """A listing_price_tracks() row as psycopg returns it."""
    base = {"listing_id": listing_id, "drops": 2, "rises": 0,
            "first_at": datetime(2026, 9, 20, 12, tzinfo=timezone.utc),
            "first_price": Decimal("24000"), "first_currency": "USD",
            "last_price": Decimal("22500"), "last_currency": "USD",
            "cum_pct": Decimal("6.25"), "cum_usd": Decimal("1500.00"),
            "last_drop_at": datetime(2026, 9, 25, 12, tzinfo=timezone.utc)}
    return {**base, **kw}


class PriceTrackLineTests(unittest.TestCase):
    def test_one_drop_in_usd(self):
        self.assertEqual(templates.price_track_line(track()),
                         "Bajó 1 vez desde que la vimos: -USD 1.500 (-6,3%).")

    def test_three_drops(self):
        self.assertEqual(templates.price_track_line(track(drops=3, cum_pct=12.04, cum_usd=2900.4)),
                         "Bajó 3 veces desde que la vimos: -USD 2.900 (-12,0%).")

    def test_pesos_with_dollars(self):
        t = track(drops=2, cum_pct=10, cum_usd=800, cum_ars=1_200_000, currency="ARS")
        self.assertEqual(templates.price_track_line(t),
                         "Bajó 2 veces desde que la vimos: -$ 1.200.000 (-10,0%), unos USD 800.")

    def test_pesos_with_one_drop_and_no_dollars(self):
        t = track(drops=1, cum_pct=4, cum_usd=None, cum_ars=500_000, currency="ARS")
        self.assertEqual(templates.price_track_line(t), "Bajó 1 vez desde que la vimos: -$ 500.000 (-4,0%).")

    def test_nothing_without_a_net_drop(self):
        for t in (None, {}, track(drops=0), track(cum_pct=0), track(cum_pct=-5), track(cum_usd=None)):
            with self.subTest(t):
                self.assertIsNone(templates.price_track_line(t))

    def test_copy_has_no_forbidden_or_closing_price_wording(self):
        texts = [copy.PRICE_TRACK, *copy.PRICE_TRACK_TIMES, copy.PRICE_TRACK_ABOUT_USD,
                 templates.price_track_line(track(drops=3)),
                 templates.price_track_line(track(drops=2, cum_ars=1_000_000, currency="ARS"))]
        for text in texts:
            folded = normalize_text(text)
            for term in (*copy.FORBIDDEN_TERMS, "precio de cierre", "oferta", "equivale"):
                with self.subTest(text=text, term=term):
                    self.assertNotIn(normalize_text(term), folded)


class PayloadTrackTests(unittest.TestCase):
    def test_a_net_drop_in_usd(self):
        self.assertEqual(service.price_track_payload(row()),
                         {"drops": 2, "cum_pct": 6.25, "cum_usd": 1500.0, "currency": "USD",
                          "first_at": "2026-09-20T12:00:00+00:00"})

    def test_pesos_keep_the_peso_amount(self):
        p = service.price_track_payload(row(first_price=Decimal("12000000"), first_currency="ARS",
                                            last_price=Decimal("10800000"), last_currency="ARS",
                                            cum_pct=Decimal("10.00"), cum_usd=Decimal("800.00")))
        self.assertEqual(p["currency"], "ARS")
        self.assertEqual(p["cum_ars"], 1_200_000.0)
        self.assertEqual(p["cum_usd"], 800.0)

    def test_a_currency_change_is_told_in_dollars(self):
        p = service.price_track_payload(row(first_currency="ARS", first_price=Decimal("12000000"),
                                            cum_pct=Decimal("5"), cum_usd=Decimal("500")))
        self.assertEqual(p["currency"], "USD")
        self.assertNotIn("cum_ars", p)

    def test_no_net_drop_no_payload(self):
        for r in (None, row(drops=0), row(cum_pct=Decimal("-10")), row(cum_pct=Decimal("0")), row(cum_pct=None)):
            with self.subTest(r):
                self.assertIsNone(service.price_track_payload(r))


class OpportunityEmailTests(unittest.TestCase):
    def test_the_line_goes_right_after_the_age(self):
        n = notification("opportunity", {**OPPORTUNITY.payload, "price_track": track(drops=2)})
        lines = templates.email(n, LINKS, NOW).text.splitlines()
        i = lines.index("Publicado hace 4 minutos.")
        self.assertEqual(lines[i + 1], "Bajó 2 veces desde que la vimos: -USD 1.500 (-6,3%).")
        self.assertIn("Bajó 2 veces desde que la vimos", templates.email(n, LINKS, NOW).html)
        self.assertIn("Bajó 2 veces desde que la vimos", templates.telegram(n, LINKS, NOW).text)

    def test_an_old_payload_renders_as_before(self):
        n = notification("opportunity", {**OPPORTUNITY.payload, "price_track": None})
        for render in (templates.email, templates.telegram):
            self.assertEqual(render(n, LINKS, NOW), render(OPPORTUNITY, LINKS, NOW))
        self.assertNotIn("desde que la vimos", templates.email(OPPORTUNITY, LINKS, NOW).text)

    def test_new_match_and_price_drop_ignore_it(self):
        for base in (NEW_MATCH, PRICE_DROP):
            n = notification(base.kind, {**base.payload, "price_track": track()})
            with self.subTest(base.kind):
                self.assertEqual(templates.email(n, LINKS, NOW), templates.email(base, LINKS, NOW))


class OnMatchesPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def payloads(self, candidates, tracks):
        audience = {7: {"user_id": "u1", "profile_name": "Fiesta", "channels": ["email"], "email": "a@b.test"}}
        notifier = service.Notifier({})
        rows = {c.listing_id: {**FIESTA, "id": c.listing_id, "year": 2025, "transmission": "manual",
                               "price_partial": False, "timing_belt": False, "description": "x" * 200,
                               "description_facts": {}} for c in candidates}
        with patch.object(service.repo, "profile_audiences", AsyncMock(return_value=audience)), \
             patch.object(service.repo, "interactions", AsyncMock(return_value={})), \
             patch.object(service.repo, "price_tracks", AsyncMock(return_value=tracks)) as price_tracks, \
             patch.object(service, "_min_n", AsyncMock(return_value=5)), \
             patch.object(notifier, "_commit", AsyncMock(return_value=[])) as commit:
            await notifier.on_matches(candidates, rows, now=NOW)
        return [e.payload for e in commit.await_args.args[0]], price_tracks

    @staticmethod
    def cand(listing_id, level="high", repost=False):
        return service.MatchCandidate(profile_id=7, listing_id=listing_id, match_id=listing_id, repost=repost,
                                      evaluation={"level": level, "score": 88, "price_ref": None, "red_flags": []})

    async def test_an_opportunity_with_a_net_drop_carries_it(self):
        [p], calls = await self.payloads([self.cand(501)], {501: row()})
        self.assertEqual(p["price_track"], service.price_track_payload(row()))
        calls.assert_awaited_once_with([501])

    async def test_without_a_net_drop_no_key(self):
        [a, b], _ = await self.payloads([self.cand(501), self.cand(502)], {501: row(drops=0), 502: row(502, cum_pct=Decimal("-3"))})
        self.assertNotIn("price_track", a)
        self.assertNotIn("price_track", b)

    async def test_new_matches_do_not_carry_it(self):
        [good, repost], _ = await self.payloads([self.cand(501, level="good"), self.cand(502, repost=True)],
                                                {501: row(), 502: row(502)})
        self.assertNotIn("price_track", good)
        self.assertNotIn("price_track", repost)

    async def test_one_query_per_batch(self):
        _, calls = await self.payloads([self.cand(501), self.cand(502), self.cand(503, level="good")], {})
        calls.assert_awaited_once_with([501, 502])

    async def test_no_opportunity_no_query(self):
        _, calls = await self.payloads([self.cand(501, level="good")], {})
        calls.assert_not_awaited()


class DigestTemplateTests(unittest.TestCase):
    def test_matches_get_the_age_and_the_drop(self):
        title, matches = templates.content(DIGEST, LINKS, NOW).sections[0]
        self.assertEqual(title, templates.DIGEST_SECTIONS["matches"])
        # 502: published, one drop · 503: no published_at, three drops in pesos · 505: no drop
        self.assertEqual(matches[0].details[-2:], ["Publicado hace 4 minutos.",
                                                   "Bajó 1 vez desde que la vimos: -USD 700 (-6,0%)."])
        self.assertEqual(matches[1].details[-2:], ["Detectado hace 2 días.",
                                                   "Bajó 3 veces desde que la vimos: -$ 1.300.000 (-9,4%), unos USD 1.000."])
        self.assertEqual(matches[2].details[-1], "Publicado hace 4 minutos.")

    def test_other_sections_do_not_change(self):
        content = templates.content(DIGEST, LINKS, NOW)
        for title, rows in content.sections:
            if title == templates.DIGEST_SECTIONS["matches"]:
                continue
            for it in rows:
                self.assertFalse(any("hace" in d or "desde que la vimos" in d for d in it.details))

    def test_a_match_without_a_net_drop_only_gets_the_age(self):
        items = [{"section": "matches", "listing_id": 9, "kind": "match", "listing": FIESTA,
                  "match": {"score": 70, "level": "good"}, "price_track": None}]
        n = notification("digest", {"date": "2026-09-27", "items": items}, listing_id=None)
        [it] = templates.content(n, LINKS, NOW).sections[0][1]
        self.assertEqual(it.details[-1], "Publicado hace 4 minutos.")
        self.assertEqual([d for d in it.details if "vimos" in d], [])

    def test_the_fixture_track_renders(self):
        self.assertEqual(templates.price_track_line(TRACK_1), "Bajó 1 vez desde que la vimos: -USD 700 (-6,0%).")


class RunDigestTests(unittest.IsolatedAsyncioTestCase):
    async def test_recomputes_the_drops_once_per_digest(self):
        stale = {"drops": 5, "cum_pct": 30.0, "cum_usd": 9000.0, "currency": "USD", "first_at": "x"}
        pending = [
            {"id": 1, "kind": "opportunity", "listing_id": 501,
             "payload": {**OPPORTUNITY.payload, "price_track": stale}},
            {"id": 2, "kind": "new_match", "listing_id": 502, "payload": NEW_MATCH.payload},
            {"id": 3, "kind": "price_drop", "listing_id": 503, "payload": PRICE_DROP.payload},
        ]
        user = {"user_id": "u1", "channels": ["email"], "email": "a@b.test"}
        notifier = service.Notifier({"email": object()})
        notifier.deliver = AsyncMock(return_value=0)
        config = {"digest_top_n": 10}
        with patch.object(digest.repo, "digest_users", AsyncMock(return_value=[user])), \
             patch.object(digest.repo, "pending_digest", AsyncMock(return_value=pending)), \
             patch.object(digest.repo, "top_matches", AsyncMock(return_value=[])), \
             patch.object(digest.repo, "price_tracks", AsyncMock(return_value={501: row(drops=1)})) as tracks, \
             patch.object(digest.repo, "insert_digest", AsyncMock(return_value=99)) as insert, \
             patch.object(digest, "_min_n", AsyncMock(return_value=5)), \
             patch.object(digest.db, "get_config", AsyncMock(side_effect=lambda k, d=None: config.get(k, d))):
            self.assertEqual(await digest.run_digest(notifier, now=NOW), 1)
        tracks.assert_awaited_once_with([501, 502])
        items = {i["listing_id"]: i for i in insert.await_args.args[3]["items"]}
        self.assertEqual(items[501]["price_track"], service.price_track_payload(row(drops=1)))
        self.assertNotIn("price_track", items[502])
        self.assertNotIn("price_track", items[503])


if __name__ == "__main__":
    unittest.main()
