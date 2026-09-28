"""Snapshots of the three alert types of §22 (+ the digest) on every channel.

The snapshots live in tests/snapshots/notifications/. After an intended copy
change, regenerate them with UPDATE_SNAPSHOTS=1 pytest and review the diff.
"""
from __future__ import annotations

import os
import unittest
from datetime import timedelta
from pathlib import Path

from intelligence.copy import FORBIDDEN_TERMS
from notification_fixtures import CASES, FIESTA, LINKS, NEW_MATCH, NOW, OPPORTUNITY, notification
from notifications import templates
from notifications.channels.base import Notification
from notifications.links import Links
from normalization.normalize import normalize_text


SNAPSHOTS = Path(__file__).parent / "snapshots" / "notifications"


def render_all(n: Notification) -> str:
    tg = templates.telegram(n, LINKS, NOW)
    mail = templates.email(n, LINKS, NOW)
    buttons = "\n".join(" | ".join(f"{b.text} [{b.callback_data or b.url}]" for b in row) for row in tg.buttons)
    return "\n".join([
        "=== telegram ===", tg.text,
        "=== telegram buttons ===", buttons or "(none)",
        "=== email subject ===", mail.subject,
        "=== email text ===", mail.text,
        "=== email html ===", mail.html, "",
    ])


class TemplateSnapshotTests(unittest.TestCase):
    maxDiff = None

    def check(self, name: str, text: str) -> None:
        path = SNAPSHOTS / f"{name}.txt"
        if os.getenv("UPDATE_SNAPSHOTS") or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_snapshots(self):
        for name, n in CASES.items():
            with self.subTest(name):
                self.check(name, render_all(n))


class PRDCopyTests(unittest.TestCase):
    """The §22 lines, in order, at the top of the Telegram message and the email text."""

    PRD = {
        "new_match": ["🚗 Nuevo vehículo encontrado", "Ford Fiesta Titanium 2017", "128.000 km", "USD 11.000"],
        "opportunity": ["🔥 Nueva oportunidad", "Ford Fiesta Titanium 2017", "112.000 km", "USD 10.300",
                        "Opportunity Score 88/100", "8% debajo de publicaciones comparables.",
                        "Publicado hace 4 minutos."],
        "price_drop": ["📉 Bajó de precio", "Ford Fiesta Titanium 2017", "Antes: USD 11.500",
                       "Ahora: USD 10.800", "-6,1%"],
    }

    def test_telegram_and_email_start_with_the_prd_copy(self):
        import re
        for kind, lines in self.PRD.items():
            n = CASES[kind]
            tg = [re.sub(r"<[^>]+>", "", x) for x in templates.telegram(n, LINKS, NOW).text.splitlines()]
            mail = templates.email(n, LINKS, NOW).text.splitlines()
            with self.subTest(kind):
                self.assertEqual(tg[:len(lines)], lines)
                self.assertEqual(mail[:len(lines)], lines)

    def test_opportunity_links_to_the_listing(self):
        tg = templates.telegram(OPPORTUNITY, LINKS, NOW).text
        self.assertIn('<a href="https://automotive.app/r/42?to=listing">Ver publicación</a>', tg)

    def test_without_published_at_it_says_detected(self):
        n = notification("opportunity", {**OPPORTUNITY.payload,
                                          "listing": {**FIESTA, "published_at": None}})
        text = templates.email(n, LINKS, NOW).text
        self.assertIn("Detectado hace 2 minutos.", text)
        self.assertNotIn("Publicado", text)

    def test_few_comparables_no_percentage(self):
        n = notification("opportunity", {**OPPORTUNITY.payload,
                                          "match": {"score": 86, "level": "high", "diff_pct": None}})
        self.assertNotIn("debajo", templates.telegram(n, LINKS, NOW).text)

    def test_repost_label(self):
        n = notification("new_match", {**NEW_MATCH.payload, "repost": True})
        self.assertIn("🔁 Re-publicado", templates.telegram(n, LINKS, NOW).text)

    def test_untracked_links_go_to_the_listing_and_no_app_button(self):
        tg = templates.telegram(OPPORTUNITY, Links(), NOW)
        self.assertIn(FIESTA["url"], tg.text)
        self.assertEqual([b.text for row in tg.buttons for b in row], ["⭐ Me interesa", "✖ Descartar"])

    def test_html_is_escaped(self):
        n = notification("new_match", {**NEW_MATCH.payload, "profile_name": "<b>x</b> & y",
                                       "listing": {**FIESTA, "make": None, "title": "Fiesta <1.6>"}})
        text = templates.telegram(n, LINKS, NOW).text
        self.assertIn("Fiesta &lt;1.6&gt;", text)
        self.assertIn("&lt;b&gt;x&lt;/b&gt; &amp; y", text)

    def test_ago_long(self):
        self.assertEqual(templates.ago_long(NOW - timedelta(seconds=10), NOW), "1 minuto")
        self.assertEqual(templates.ago_long(NOW - timedelta(minutes=59), NOW), "59 minutos")
        self.assertEqual(templates.ago_long(NOW - timedelta(hours=1), NOW), "1 hora")
        self.assertEqual(templates.ago_long(NOW - timedelta(days=3), NOW), "3 días")


class CopyLintTests(unittest.TestCase):
    """§19: no "vale", "precio real", "tasación" in any alert."""

    def test_no_forbidden_terms(self):
        rendered = normalize_text("\n".join(render_all(n) for n in CASES.values()))
        constants = normalize_text(" ".join(str(v) for k, v in vars(templates).items()
                                            if k.isupper() and isinstance(v, (str, dict))))
        for term in FORBIDDEN_TERMS:
            t = normalize_text(term)
            with self.subTest(term):
                self.assertNotRegex(rendered, rf"\b{t}\b")
                self.assertNotRegex(constants, rf"\b{t}\b")


if __name__ == "__main__":
    unittest.main()
