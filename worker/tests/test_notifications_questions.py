"""H-01: seller questions in the alert email (docs/superpowers/specs/2026-10-29-email-seller-questions-design.md)."""
from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from intelligence import copy
from notification_fixtures import FIESTA, LINKS, NEW_MATCH, NOW, OPPORTUNITY, PRICE_DROP, notification
from notifications import service, templates


def mail(n):
    return templates.email(n, LINKS, NOW)


class EmailQuestionsTests(unittest.TestCase):
    def test_text_lists_the_questions_before_the_link(self):
        lines = mail(OPPORTUNITY).text.splitlines()
        i = lines.index(copy.QUESTIONS_TITLE)
        self.assertEqual(lines[i + 1:i + 4], ["- ¿Cuántos dueños tuvo?", "- ¿Tiene VTV vigente?", copy.QUESTIONS_FOOTER])
        self.assertLess(i, next(k for k, x in enumerate(lines) if x.startswith("Ver auto en Ese Auto")))

    def test_html_has_the_block_before_the_button(self):
        html = mail(OPPORTUNITY).html
        for text in (copy.QUESTIONS_TITLE, "• ¿Cuántos dueños tuvo?", "• ¿Tiene VTV vigente?", copy.QUESTIONS_FOOTER):
            self.assertIn(text, html)
        self.assertLess(html.index(copy.QUESTIONS_TITLE), html.index("Ver auto en Ese Auto"))

    def test_telegram_and_inbox_do_not_change(self):
        bare = notification("opportunity", {k: v for k, v in OPPORTUNITY.payload.items() if k != "questions"})
        self.assertEqual(templates.telegram(OPPORTUNITY, LINKS, NOW).text, templates.telegram(bare, LINKS, NOW).text)
        self.assertEqual(templates.web(OPPORTUNITY, LINKS, NOW), templates.web(bare, LINKS, NOW))

    def test_an_old_payload_renders_without_the_block(self):
        for n in (NEW_MATCH, PRICE_DROP):
            self.assertNotIn(copy.QUESTIONS_TITLE, mail(n).text)
            self.assertNotIn(copy.QUESTIONS_TITLE, mail(n).html)

    def test_price_drop_ignores_questions(self):
        n = notification("price_drop", {**PRICE_DROP.payload, "questions": ["¿Cuántos dueños tuvo?"]})
        self.assertNotIn(copy.QUESTIONS_TITLE, mail(n).text)

    def test_copy_passes_the_forbidden_terms(self):
        from normalization.normalize import normalize_text
        for text in (copy.QUESTIONS_TITLE, copy.QUESTIONS_FOOTER):
            for term in copy.FORBIDDEN_TERMS:
                self.assertNotIn(normalize_text(term), normalize_text(text).split())


class PayloadTests(unittest.IsolatedAsyncioTestCase):
    async def payloads(self, listing, red_flags):
        cand = service.MatchCandidate(profile_id=7, listing_id=listing["id"], match_id=1,
                                      evaluation={"level": "high", "score": 88, "price_ref": None, "red_flags": red_flags})
        audience = {7: {"user_id": "u1", "profile_name": "Fiesta", "channels": ["email"], "email": "a@b.test"}}
        notifier = service.Notifier({})
        with patch.object(service.repo, "profile_audiences", AsyncMock(return_value=audience)), \
             patch.object(service.repo, "interactions", AsyncMock(return_value={})), \
             patch.object(service, "_min_n", AsyncMock(return_value=5)), \
             patch.object(notifier, "_commit", AsyncMock(return_value=[])) as commit:
            await notifier.on_matches([cand], {listing["id"]: listing}, now=NOW)
        return [e.payload for e in commit.await_args.args[0]]

    def row(self, **kw):
        return {**FIESTA, "year": 2025, "transmission": "manual", "price_partial": False, "timing_belt": False,
                "description": "x" * 200, "description_facts": {}, **kw}

    async def test_specific_questions_go_in_the_payload(self):
        [p] = await self.payloads(self.row(trim=None), [{"id": "no_owners", "text": "x", "severity": "info"}])
        self.assertEqual(p["questions"], [copy.QUESTION["owners"], copy.QUESTION["trim"]])

    async def test_no_specific_question_no_key(self):
        [p] = await self.payloads(self.row(), [])
        self.assertNotIn("questions", p)


if __name__ == "__main__":
    unittest.main()
