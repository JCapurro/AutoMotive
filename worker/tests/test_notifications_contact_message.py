"""PRO-01 paso 2: the «Mensaje listo para mandar» block of Pro's opportunity
email (docs/superpowers/specs/2026-10-31-pro01-contacto-design.md, decisión 20).
on_matches renders the text (intelligence/contact_message.render) only for an
opportunity whose plan has contact_email; the email shows it after the
questions and before the button; Telegram and the web inbox don't."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from intelligence import copy
from notification_fixtures import (CONTACT_MESSAGE, LINKS, NOW, OPPORTUNITY, OPPORTUNITY_CONTACT_MESSAGE,
                                   notification)
from notifications import service, templates
from test_contact_message import GOLDEN


class EmailBlockTests(unittest.TestCase):
    def test_after_the_questions_and_before_the_button_without_the_footer(self):
        lines = templates.email(OPPORTUNITY_CONTACT_MESSAGE, LINKS, NOW).text.splitlines()
        i = lines.index(copy.CONTACT_MESSAGE["email_title"])
        self.assertEqual(lines[i + 1:i + 6], [*CONTACT_MESSAGE.splitlines(), copy.CONTACT_MESSAGE["email_note"]])
        self.assertLess(lines.index("- ¿Tiene VTV vigente?"), i)
        self.assertTrue(next(l for l in lines[i:] if ": https://" in l).startswith("Ver auto en Ese Auto"))
        self.assertNotIn(copy.QUESTIONS_FOOTER, lines)
        html = templates.email(OPPORTUNITY_CONTACT_MESSAGE, LINKS, NOW).html
        self.assertLess(html.index("¿Tiene VTV vigente?"), html.index(copy.CONTACT_MESSAGE["email_title"]))
        self.assertLess(html.index(copy.CONTACT_MESSAGE["email_title"]), html.index("Ver auto en Ese Auto"))
        self.assertNotIn(copy.QUESTIONS_FOOTER, html)
        self.assertNotIn("mailto:", html)

    def test_the_text_is_escaped_line_by_line(self):
        n = notification("opportunity", {**OPPORTUNITY.payload, "contact_message": "Hola <b>&\n¿Sigue?"})
        html = templates.email(n, LINKS, NOW).html
        self.assertIn("Hola &lt;b&gt;&amp;", html)
        self.assertNotIn("<b>&", html)
        self.assertIn("¿Sigue?", html)

    def test_telegram_and_inbox_do_not_change(self):
        self.assertEqual(templates.telegram(OPPORTUNITY_CONTACT_MESSAGE, LINKS, NOW), templates.telegram(OPPORTUNITY, LINKS, NOW))
        self.assertEqual(templates.web(OPPORTUNITY_CONTACT_MESSAGE, LINKS, NOW), templates.web(OPPORTUNITY, LINKS, NOW))

    def test_an_old_payload_renders_as_before(self):
        n = notification("opportunity", {**OPPORTUNITY.payload, "contact_message": None})
        self.assertEqual(templates.email(n, LINKS, NOW), templates.email(OPPORTUNITY, LINKS, NOW))

    def test_new_match_ignores_it(self):
        base = notification("new_match", {"listing": OPPORTUNITY.payload["listing"], "match": {"score": 74, "level": "good"}})
        n = notification("new_match", {**base.payload, "contact_message": CONTACT_MESSAGE})
        self.assertEqual(templates.email(n, LINKS, NOW), templates.email(base, LINKS, NOW))


def listing(listing_id, **kw):
    """A rows_for_scoring() row, with the catalog's model (PRO-01)."""
    return {"id": listing_id, "title": "FIESTA KINETIC wa.me/5491155555555", "make": "Ford", "model": "Fiesta",
            "catalog_model": "Fiesta", "trim": "Titanium", "year": 2017, "mileage_km": 90000, "price": 10300.0,
            "currency": "USD", "price_usd": 10300.0, "url": "https://example.test/f", "source": "mercadolibre",
            "transmission": "manual", "price_partial": False, "timing_belt": False, "description": "x" * 200,
            "description_facts": {}, "seller_type": "private", "dealer_inferred": False, **kw}


def cand(listing_id, profile_id=7, level="high", repost=False):
    return service.MatchCandidate(profile_id=profile_id, listing_id=listing_id, match_id=listing_id, repost=repost,
                                  evaluation={"level": level, "score": 88, "price_ref": None, "red_flags": []})


class OnMatchesContactTests(unittest.IsolatedAsyncioTestCase):
    async def payloads(self, candidates, rows, audiences):
        notifier = service.Notifier({})
        base = {"user_id": "u1", "profile_name": "Fiesta", "channels": ["email"], "email": "a@b.test",
                "total_cost": False, "contact_template": None}
        audiences = {pid: {**base, "profile_id": pid, **a} for pid, a in audiences.items()}
        with patch.object(service.repo, "profile_audiences", AsyncMock(return_value=audiences)), \
             patch.object(service.repo, "interactions", AsyncMock(return_value={})), \
             patch.object(service.repo, "price_tracks", AsyncMock(return_value={})), \
             patch.object(service, "_min_n", AsyncMock(return_value=5)), \
             patch.object(notifier, "_commit", AsyncMock(return_value=[])) as commit:
            await notifier.on_matches(candidates, rows, now=NOW)
        return {(e.audience.profile_id, e.listing_id): e.payload for e in commit.await_args.args[0]}

    async def test_pro_opportunity_carries_the_rendered_text(self):
        got = await self.payloads([cand(501)], {501: listing(501)}, {7: {"contact_email": True}})
        text = got[(7, 501)]["contact_message"]
        self.assertTrue(text.startswith("Hola, vi tu Fiesta 2017 publicado.\n¿Lo seguís teniendo?\n"))
        self.assertTrue(text.endswith("\n¿Cuándo se puede ver?"))
        self.assertNotIn("wa.me", text)                          # never the title
        self.assertEqual(got[(7, 501)]["questions"][0], text.splitlines()[2])

    async def test_the_users_template(self):
        got = await self.payloads([cand(501)], {501: listing(501)},
                                  {7: {"contact_email": True, "contact_template": "Buenas, ¿tu {auto} sigue?"}})
        self.assertEqual(got[(7, 501)]["contact_message"], "Buenas, ¿tu Fiesta 2017 sigue?")

    async def test_a_template_written_by_sql_that_fails_the_lint_is_the_default_and_the_batch_goes_on(self):
        hostile = [c["template"] for c in GOLDEN["cases"] if c["name"].startswith("hostile")]
        audiences = {i: {"contact_email": True, "contact_template": t} for i, t in enumerate(hostile, start=10)}
        cands = [cand(501, profile_id=i) for i in audiences]
        with self.assertLogs("contact_message", "WARNING"):
            got = await self.payloads(cands, {501: listing(501)}, audiences)
        self.assertEqual(len(got), len(hostile))
        for i in audiences:
            self.assertTrue(got[(i, 501)]["contact_message"].startswith("Hola, vi tu Fiesta 2017 publicado."))

    async def test_no_block_for_new_match_other_plans_or_reposts(self):
        got = await self.payloads([cand(501, level="good"), cand(502, profile_id=8), cand(503, repost=True)],
                                  {501: listing(501), 502: listing(502), 503: listing(503)},
                                  {7: {"contact_email": True}, 8: {"contact_email": False}})
        for key in ((7, 501), (8, 502), (7, 503)):
            self.assertNotIn("contact_message", got[key])

    async def test_without_a_catalog_model_it_says_auto(self):
        got = await self.payloads([cand(501)], {501: listing(501, catalog_model=None)}, {7: {"contact_email": True}})
        self.assertTrue(got[(7, 501)]["contact_message"].startswith("Hola, vi tu auto publicado."))


if __name__ == "__main__":
    unittest.main()
