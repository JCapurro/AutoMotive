"""Copy lint (§19, sección 6.2): the intelligence layer never says a car "vale"
something, a "precio real" or a "tasación". Prices are "publicados" and
compared with the "mercado observado" / "publicaciones comparables".

Checks every string literal of worker/intelligence/ (docstrings aside, and
the FORBIDDEN_TERMS list itself) and the text a full evaluation renders.
"""
from __future__ import annotations

import ast
import re
import unicodedata
import unittest
from pathlib import Path

from intelligence import copy
from intelligence.config import IntelligenceConfig
from intelligence.engine import assess
from intelligence.comparables import PriceRef
from test_intelligence import CFG, MARKET, NOW, fiesta_listing, fiesta_profile


INTELLIGENCE = Path(__file__).resolve().parents[1] / "intelligence"


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower())
                   if unicodedata.category(c) != "Mn")


_FORBIDDEN = re.compile(r"\b(" + "|".join(re.escape(_fold(t)) for t in copy.FORBIDDEN_TERMS) + r")\b")


def forbidden_in(text: str) -> list[str]:
    return _FORBIDDEN.findall(_fold(text))


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _forbidden_terms_node(tree: ast.AST) -> set[int]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "FORBIDDEN_TERMS"
                                                for t in node.targets):
            return {id(n) for n in ast.walk(node.value)}
    return set()


def string_literals(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _docstring_nodes(tree) | _forbidden_terms_node(tree)
    return [(n.lineno, n.value) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip]


class CopyLintTests(unittest.TestCase):
    def test_the_lint_catches_what_it_should(self):
        self.assertEqual(forbidden_in("Este auto vale USD 10.000"), ["vale"])
        self.assertEqual(forbidden_in("Precio REAL"), ["precio real"])
        self.assertEqual(forbidden_in("según la Tasación oficial"), ["tasacion"])
        self.assertEqual(forbidden_in("valen la pena · valores · equivalente · valeria"), [])

    def test_no_template_uses_forbidden_terms(self):
        offenders = []
        for path in sorted(INTELLIGENCE.glob("*.py")):
            for line, text in string_literals(path):
                if hits := forbidden_in(text):
                    offenders.append(f"{path.name}:{line}: {hits} in {text!r}")
        self.assertEqual(offenders, [])

    def test_rendered_output_uses_the_prudent_wording(self):
        cases = [
            fiesta_listing(),
            fiesta_listing(price=5_000.0, price_usd=5_000.0, mileage_km=10_000,
                           enriched_at=NOW, probable_repost_of=3),
            fiesta_listing(price=13_000.0, price_usd=13_000.0, transmission=None, trim="SE"),
        ]
        for listing in cases:
            ref = PriceRef(n=23, level_used="model", median=11_200.0, median_km=125_000.0,
                           diff_pct=(1 - listing["price_usd"] / 11_200) * 100)
            for cfg in (CFG, IntelligenceConfig.from_app_config({})):
                _, _, ev = assess(listing, fiesta_profile(price_max=20_000), price_ref=ref,
                                  cfg=cfg, now=NOW, timing_belt=True)
                texts = [ev.questions, *(f.text for f in ev.red_flags),
                         *(r.detail for r in ev.match.reasons.values()),
                         *(c.explanation for c in ev.score.components.values())]
                for text in texts:
                    self.assertEqual(forbidden_in(text), [], text)

    def test_price_explanations_say_mercado_observado_and_comparables(self):
        _, s, _ = assess(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW)
        text = s.components["price"].explanation
        self.assertIn("mercado observado", text)
        self.assertIn("publicaciones comparables (n=23)", text)


if __name__ == "__main__":
    unittest.main()
