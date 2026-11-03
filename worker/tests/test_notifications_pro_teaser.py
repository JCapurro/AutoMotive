"""Juan, 03/11: Pro in view in the other plans' alert emails, never Pro's
data. The margin line and the «Mensaje listo para mandar» block show locked,
with a fixed placeholder and «Ver planes» (service.margin_teaser,
templates.email; snapshots opportunity_pro_teaser, new_match_margin_teaser
and price_drop_margin_teaser in test_notifications_templates.py)."""
from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, patch

from intelligence import copy
from notification_fixtures import (LINKS, NEW_MATCH, NEW_MATCH_MARGIN_TEASER, NOW, OPPORTUNITY,
                                   OPPORTUNITY_CONTACT_MESSAGE, OPPORTUNITY_MARGIN, OPPORTUNITY_PRO_TEASER,
                                   PRICE_DROP, PRICE_DROP_MARGIN, PRICE_DROP_MARGIN_TEASER, notification)
from notifications import service, templates
from notifications.links import Links
from test_margin import POOL, MarginCopyLint, compute
from test_notifications_margin import listing

PLANS = "https://automotive.app/planes"


class MarginTeaserTests(unittest.TestCase):
    def test_only_when_locked_and_pro_would_see_a_figure(self):
        self.assertIs(service.margin_teaser(compute(), {"margin_locked": True}), True)
        for extra in ({"margin_locked": False}, {}):
            with self.subTest(extra=extra):
                self.assertIsNone(service.margin_teaser(compute(), extra))

    def test_no_figure_for_pro_no_teaser(self):
        from intelligence.comparables import PriceRef
        few = compute(ref=PriceRef(**{**POOL.__dict__, "dealer_n": 2}))
        implausible = {**compute(), "dealer_median": 100000.0}
        for ref in (None, {}, few, implausible, "x"):
            with self.subTest(ref=ref):
                self.assertIsNone(service.margin_teaser(ref, {"margin_locked": True}))


class PayloadTests(unittest.IsolatedAsyncioTestCase):
    async def payload(self, audience_extra, *, level="high", repost=False):
        notifier = service.Notifier({})
        a = {"user_id": "u1", "profile_id": 7, "profile_name": "Corolla", "channels": ["email"], "email": "a@b.test",
             **audience_extra}
        cand = service.MatchCandidate(profile_id=7, listing_id=501, match_id=501, repost=repost,
                                      evaluation={"level": level, "score": 88, "price_ref": None, "red_flags": [],
                                                  "margin_ref": compute()})
        with patch.object(service.repo, "profile_audiences", AsyncMock(return_value={7: a})), \
             patch.object(service.repo, "interactions", AsyncMock(return_value={})), \
             patch.object(service.repo, "price_tracks", AsyncMock(return_value={})), \
             patch.object(service, "_min_n", AsyncMock(return_value=5)), \
             patch.object(service, "flag_order", AsyncMock(return_value=service.config.DEFAULT_FLAG_ORDER)), \
             patch.object(service, "_cost_config", AsyncMock(return_value=None)), \
             patch.object(notifier, "_commit", AsyncMock(return_value=[])) as commit:
            await notifier.on_matches([cand], {501: listing(501)}, now=NOW)
        [e] = commit.await_args.args[0]
        return e.payload

    async def test_the_other_plans_get_flags_and_no_margin_data(self):
        p = await self.payload({"margin_locked": True, "contact_locked": True})
        self.assertIs(p["margin_teaser"], True)
        self.assertIs(p["contact_teaser"], True)
        self.assertNotIn("margin", p)
        self.assertNotIn("contact_message", p)
        dumped = json.dumps(p)
        for leak in ("1210", "1230", "usd_min", "dealer_median", "gross_margin"):
            self.assertNotIn(leak, dumped)

    async def test_pro_keeps_the_real_thing_and_no_teaser(self):
        p = await self.payload({"dealer_margin": True, "contact_email": True})
        self.assertEqual(p["margin"]["usd_min"], 1210)
        self.assertIn("contact_message", p)
        self.assertNotIn("margin_teaser", p)
        self.assertNotIn("contact_teaser", p)

    async def test_the_contact_block_only_on_opportunities(self):
        for kw in ({"level": "good"}, {"repost": True}):
            with self.subTest(kw=kw):
                p = await self.payload({"margin_locked": True, "contact_locked": True}, **kw)
                self.assertIs(p["margin_teaser"], True)
                self.assertNotIn("contact_teaser", p)

    async def test_nothing_without_the_flags(self):
        p = await self.payload({})
        self.assertNotIn("margin_teaser", p)
        self.assertNotIn("contact_teaser", p)


class RenderTests(unittest.TestCase):
    def test_opportunity_email(self):
        m = templates.email(OPPORTUNITY_PRO_TEASER, LINKS, NOW)
        self.assertIn("Margen bruto estimado: USD X.XXX (Pro)", m.text)
        self.assertIn("Mensaje listo para mandar (Pro)", m.text)
        self.assertEqual(m.text.count(f"Ver planes: {PLANS}"), 2)
        self.assertEqual(m.html.count(f'href="{PLANS}"'), 2)
        self.assertIn("USD X.XXX", m.html)

    def test_new_match_and_price_drop_get_the_margin_only(self):
        for n in (NEW_MATCH_MARGIN_TEASER, PRICE_DROP_MARGIN_TEASER):
            with self.subTest(kind=n.kind):
                m = templates.email(n, LINKS, NOW)
                self.assertIn("USD X.XXX (Pro)", m.text)
                self.assertNotIn(copy.CONTACT_MESSAGE["email_title"], m.text)
                self.assertEqual(m.html.count(f'href="{PLANS}"'), 1)

    def test_without_web_base_url_no_link(self):
        m = templates.email(OPPORTUNITY_PRO_TEASER, Links(), NOW)
        self.assertIn("USD X.XXX (Pro)", m.text)
        self.assertNotIn("Ver planes", m.text)
        self.assertNotIn("Ver planes", m.html)

    def test_the_real_thing_wins(self):
        for n in (notification("opportunity", {**OPPORTUNITY_MARGIN.payload, "margin_teaser": True}),
                  notification("opportunity", {**OPPORTUNITY_CONTACT_MESSAGE.payload, "contact_teaser": True}),
                  notification("price_drop", {**PRICE_DROP_MARGIN.payload, "margin_teaser": True})):
            with self.subTest(kind=n.kind):
                self.assertNotIn("(Pro)", templates.email(n, LINKS, NOW).text)

    def test_only_a_true_flag_counts(self):
        for value in ("true", 1, None, {"x": 1}):
            n = notification("opportunity", {**OPPORTUNITY.payload, "margin_teaser": value, "contact_teaser": value})
            with self.subTest(value=value):
                self.assertEqual(templates.email(n, LINKS, NOW).text, templates.email(OPPORTUNITY, LINKS, NOW).text)

    def test_telegram_and_the_web_inbox_do_not_change(self):
        plain = notification("opportunity", {k: v for k, v in OPPORTUNITY_PRO_TEASER.payload.items()
                                             if k not in ("margin_teaser", "contact_teaser")})
        for teaser, base in ((OPPORTUNITY_PRO_TEASER, plain), (NEW_MATCH_MARGIN_TEASER, NEW_MATCH),
                             (PRICE_DROP_MARGIN_TEASER, PRICE_DROP)):
            with self.subTest(kind=teaser.kind):
                self.assertEqual(templates.telegram(teaser, LINKS, NOW), templates.telegram(base, LINKS, NOW))
                self.assertEqual(templates.web(teaser, LINKS, NOW), templates.web(base, LINKS, NOW))


class CopyLint(unittest.TestCase):
    def test_the_teaser_copy(self):
        for text in copy.PRO_TEASER.values():
            with self.subTest(text=text):
                self.assertEqual(MarginCopyLint.offenders(text), [])

    def test_the_placeholder_has_no_digits(self):
        self.assertFalse(any(ch.isdigit() for ch in copy.PRO_TEASER["margin_figure"]))
