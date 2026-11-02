"""PRO-01 paso 2: the message for the seller and the lint of its template
(intelligence/contact_message.py) against the JSON the web twin reads too
(tests/fixtures/contact_message/{golden,lint}.json)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from intelligence import contact_message as cm
from intelligence import copy

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contact_message"
GOLDEN = json.loads((FIXTURES / "golden.json").read_text(encoding="utf-8"))
LINT = json.loads((FIXTURES / "lint.json").read_text(encoding="utf-8"))


class LintTests(unittest.TestCase):
    def test_the_rule_reads_the_shared_terms(self):
        self.assertEqual(sorted({cm.fold(t) for t in copy.FORBIDDEN_TERMS}), LINT["terms"])
        self.assertEqual(list(copy.ALLOWED_PHRASES), LINT["allowed"])
        self.assertEqual((cm.MAX_CHARS, cm.MAX_LINES), (LINT["max_chars"], LINT["max_lines"]))

    def test_every_case(self):
        for case in LINT["cases"]:
            with self.subTest(case["name"]):
                self.assertEqual(cm.lint_contact_template(case["input"]), (case["value"], case["error"]))

    def test_the_default_template_passes(self):
        self.assertEqual(cm.lint_contact_template(cm.DEFAULT_TEMPLATE), (cm.DEFAULT_TEMPLATE, None))
        self.assertEqual(cm.DEFAULT_TEMPLATE, GOLDEN["default_template"])


class RenderTests(unittest.TestCase):
    def test_golden_cases(self):
        for case in GOLDEN["cases"]:
            with self.subTest(case["name"]):
                self.assertEqual(cm.render(case["template"], case["catalog_model"], case["year"], case["questions"]),
                                 case["text"])
                self.assertEqual(cm.subject(case["catalog_model"], case["year"]), case["subject"])

    def test_the_default_message_is_three_or_four_lines_de_vos(self):
        text = cm.render(None, "Fiesta", 2017, ["¿Tenés historial de services?"])
        self.assertEqual(text.splitlines(), ["Hola, vi tu Fiesta 2017 publicado.", "¿Lo seguís teniendo?",
                                             "¿Tenés historial de services?", "¿Cuándo se puede ver?"])

    def test_a_rejected_template_logs_and_never_raises(self):
        with self.assertLogs("contact_message", "WARNING"):
            self.assertTrue(cm.render("{auto.__class__}", "Fiesta", 2017, []).startswith("Hola, vi tu Fiesta 2017"))

    def test_an_error_while_rendering_gives_the_default_message(self):
        with patch.object(cm, "lint_contact_template", side_effect=RuntimeError("boom")), \
                self.assertLogs("contact_message", "WARNING"):
            self.assertEqual(cm.render("Hola {auto}", "Ka", 2012, []),
                             "Hola, vi tu Ka 2012 publicado.\n¿Lo seguís teniendo?\n¿Sos titular?\n¿Cuándo se puede ver?")

    def test_the_questions_texts_are_unchanged(self):
        self.assertEqual(copy.QUESTION["available"], "¿Lo seguís teniendo?")
        self.assertEqual(copy.QUESTION["holder"], "¿Sos titular?")


if __name__ == "__main__":
    unittest.main()
