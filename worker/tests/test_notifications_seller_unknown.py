"""PRO-01, option C (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md,
«Respuestas de Juan 02/11», 4): under the strict seller filter a listing
whose effective seller is unknown still passes (the usual penalty), and the
opportunity email says «vendedor sin dato». on_matches sets
payload["seller_unknown"] from match_reasons.seller (unknown and hard, the
same rule as match_cards.seller_unknown); only the email shows it, after the
km and before the score. Nothing changes without the strict filter."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from intelligence import copy
from intelligence.matching import evaluate, strict_seller_unknown
from notification_fixtures import LINKS, NOW, OPPORTUNITY, OPPORTUNITY_SELLER_UNKNOWN, notification
from notifications import service, templates
from test_notifications_contact_message import cand, listing

UNKNOWN_HARD = {"seller": {"result": "unknown", "detail": copy.NOT_INFORMED, "kind": "hard"}}


class CopyTests(unittest.TestCase):
    def test_the_exact_copy(self):
        self.assertEqual(copy.SELLER_UNKNOWN, "vendedor sin dato")


class RuleTests(unittest.TestCase):
    def test_only_the_hard_check_that_did_not_know(self):
        self.assertTrue(strict_seller_unknown(UNKNOWN_HARD))
        self.assertFalse(strict_seller_unknown({"seller": {"result": "ok", "detail": "x", "kind": "hard"}}))
        self.assertFalse(strict_seller_unknown(
            {"seller_type": {"result": "unknown", "detail": copy.NOT_INFORMED, "kind": "soft"}}))
        self.assertFalse(strict_seller_unknown({"seller": {"result": "unknown", "detail": "x", "kind": "soft"}}))
        for empty in ({}, None, "x", {"seller": None}, {"seller": "unknown"}):
            self.assertFalse(strict_seller_unknown(empty))

    def test_from_evaluate(self):
        car = {"make": "Ford", "model": "Fiesta", "year": 2017, "price": 10300, "currency": "USD", "seller_type": None}
        strict = {"filters": {"make": "Ford", "model": "Fiesta", "seller_types": ["private"]}, "seller_filter": True}
        self.assertTrue(strict_seller_unknown(evaluate(car, strict).to_json()))
        # The same search without the plan feature: a soft preference, no label.
        self.assertFalse(strict_seller_unknown(evaluate(car, {**strict, "seller_filter": False}).to_json()))
        self.assertFalse(strict_seller_unknown(evaluate({**car, "seller_type": "private"}, strict).to_json()))
        self.assertFalse(strict_seller_unknown(evaluate(car, {"filters": {"make": "Ford", "model": "Fiesta"}}).to_json()))


class EmailTests(unittest.TestCase):
    def test_after_the_km_and_before_the_score(self):
        lines = templates.email(OPPORTUNITY_SELLER_UNKNOWN, LINKS, NOW).text.splitlines()
        i = lines.index(copy.SELLER_UNKNOWN)
        self.assertEqual(lines[i - 2:i + 2], ["112.000 km", "USD 10.300", copy.SELLER_UNKNOWN, "Opportunity Score 88/100"])
        html = templates.email(OPPORTUNITY_SELLER_UNKNOWN, LINKS, NOW).html
        self.assertLess(html.index("112.000 km"), html.index(copy.SELLER_UNKNOWN))
        self.assertLess(html.index(copy.SELLER_UNKNOWN), html.index("Puntaje de oportunidad"))
        self.assertEqual(html.count(copy.SELLER_UNKNOWN), 1)

    def test_only_the_email(self):
        self.assertEqual(templates.telegram(OPPORTUNITY_SELLER_UNKNOWN, LINKS, NOW), templates.telegram(OPPORTUNITY, LINKS, NOW))
        self.assertEqual(templates.web(OPPORTUNITY_SELLER_UNKNOWN, LINKS, NOW), templates.web(OPPORTUNITY, LINKS, NOW))

    def test_without_the_key_nothing_changes(self):
        n = notification("opportunity", {**OPPORTUNITY.payload, "seller_unknown": False})
        self.assertEqual(templates.email(n, LINKS, NOW), templates.email(OPPORTUNITY, LINKS, NOW))
        self.assertNotIn(copy.SELLER_UNKNOWN, templates.email(OPPORTUNITY, LINKS, NOW).text)

    def test_not_in_a_new_match(self):
        base = notification("new_match", {"listing": OPPORTUNITY.payload["listing"], "match": {"score": 74, "level": "good"}})
        n = notification("new_match", {**base.payload, "seller_unknown": True})
        self.assertEqual(templates.email(n, LINKS, NOW), templates.email(base, LINKS, NOW))


class OnMatchesTests(unittest.IsolatedAsyncioTestCase):
    async def payloads(self, candidates, rows):
        notifier = service.Notifier({})
        base = {"user_id": "u1", "profile_name": "Fiesta", "channels": ["email"], "email": "a@b.test",
                "total_cost": False, "contact_template": None, "contact_email": False}
        audiences = {c.profile_id: {**base, "profile_id": c.profile_id} for c in candidates}
        with patch.object(service.repo, "profile_audiences", AsyncMock(return_value=audiences)), \
             patch.object(service.repo, "interactions", AsyncMock(return_value={})), \
             patch.object(service.repo, "price_tracks", AsyncMock(return_value={})), \
             patch.object(service, "_min_n", AsyncMock(return_value=5)), \
             patch.object(notifier, "_commit", AsyncMock(return_value=[])) as commit:
            await notifier.on_matches(candidates, rows, now=NOW)
        return {(e.audience.profile_id, e.listing_id): e.payload for e in commit.await_args.args[0]}

    def with_reasons(self, c, reasons):
        c.evaluation["match_reasons"] = reasons
        return c

    async def test_an_opportunity_the_strict_filter_let_through_carries_it(self):
        got = await self.payloads([self.with_reasons(cand(501), UNKNOWN_HARD)], {501: listing(501, seller_type=None)})
        self.assertIs(got[(7, 501)]["seller_unknown"], True)

    async def test_no_key_otherwise(self):
        known = {"seller": {"result": "ok", "detail": "x", "kind": "hard"}}
        soft = {"seller_type": {"result": "unknown", "detail": copy.NOT_INFORMED, "kind": "soft"}}
        got = await self.payloads(
            [self.with_reasons(cand(501, profile_id=1), known), self.with_reasons(cand(502, profile_id=2), soft),
             cand(503, profile_id=3),                                              # an evaluation without reasons
             self.with_reasons(cand(504, profile_id=4, level="good"), UNKNOWN_HARD)],   # a new_match, not an opportunity
            {i: listing(i, seller_type=None) for i in (501, 502, 503, 504)})
        for key in ((1, 501), (2, 502), (3, 503), (4, 504)):
            self.assertNotIn("seller_unknown", got[key])


if __name__ == "__main__":
    unittest.main()
