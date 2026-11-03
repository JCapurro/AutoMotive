"""PAR-04: model guides. Pure.

* `validate_draft`: what the LLM proposed, checked before it reaches
  model_guides as a draft: the five sections with at least one line, 3 to 8
  questions of 10 to 200 characters ending in «?», the copy lint
  (copy.FORBIDDEN_TERMS as words, copy.RISK_FORBIDDEN as stems: no promises,
  no «vale» or «tasación») and no amount of money anywhere. Every source is
  stored unverified: Juan checks it or deletes it before publishing.
* `cache_key`: (make, model, generation, prompt version), the worker's cache.
* `GuideEntry` / `pick`: the published guide whose questions a listing gets
  (seller_questions.question_items): same make and catalog model, the year
  inside the guide's range (null = no bound), the narrowest range wins; a
  listing without a year only crosses the guide without generation.

A guide's text is a statement of the guide, never a check of a car.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from intelligence import copy
from llm.provider import LLMError
from llm.schemas import ModelGuideDraft

SECTIONS = ("known_issues", "visit_checklist", "versions_equipment", "maintenance_costs", "generations")
SECTION_NAMES = {
    "known_issues": "Fallas conocidas",
    "visit_checklist": "Qué revisar en la visita",
    "versions_equipment": "Versiones y equipamiento",
    "maintenance_costs": "Mantenimiento y costos típicos",
    "generations": "Generaciones",
}
MIN_QUESTIONS, MAX_QUESTIONS = 3, 8
QUESTION_MIN_CHARS, QUESTION_MAX_CHARS = 10, 200
DEFAULT_MAX_QUESTIONS_IN_LISTING = 3
# PAR-04 backlog: a listing gets «hasta 3» questions of its guide, whatever the config says.
MAX_QUESTIONS_IN_LISTING = 3

_MONEY_WORDS = r"(?:\$|(?<![a-z])(?:u\$s|u\$d|usd|us\$|ars|pesos?|dolares?|lucas|palos))"
_NUMBER = r"\d[\d.,]*(?:\s*(?:mil|millones?|k))?"
# «$ 300.000», «USD 1.500», «300 mil pesos», «1500 dólares», «$300k». Folded text.
_MONEY = re.compile(rf"{_MONEY_WORDS}\s*{_NUMBER}|{_NUMBER}\s*{_MONEY_WORDS}(?![a-z])")


class GuideInvalid(LLMError):
    """The draft breaks a rule: the job fails with the reason, the guide stays as it was."""


def fold(text: str) -> str:
    """Lowercase without accents, as the copy lint reads text."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def copy_problem(text: str) -> str | None:
    """The forbidden term or promise in `text`, or None."""
    folded = fold(text)
    for phrase in copy.ALLOWED_PHRASES:
        folded = folded.replace(fold(phrase), " ")
    for term in sorted({fold(t) for t in copy.FORBIDDEN_TERMS}):
        if re.search(r"(?:^|[^\w])" + re.escape(term) + r"(?:[^\w]|$)", folded):
            return term
    for stem in copy.RISK_FORBIDDEN:
        if re.search(r"(?:^|[^\w])" + re.escape(fold(stem)), folded):
            return stem
    return None


def has_money(text: str) -> bool:
    return bool(_MONEY.search(fold(text)))


def _check_text(where: str, text: str) -> None:
    if (term := copy_problem(text)) is not None:
        raise GuideInvalid(f"{where}: usa «{term}», que el copy no permite")
    if has_money(text):
        raise GuideInvalid(f"{where}: tiene una cifra de dinero")


def validate_draft(draft: ModelGuideDraft) -> dict[str, Any]:
    """{body, questions, sources} ready for model_guides, or GuideInvalid."""
    body: dict[str, list[dict[str, Any]]] = {}
    for key in SECTIONS:
        lines = [line.model_dump() for line in getattr(draft.body, key)]
        lines = [{k: (v.strip() if isinstance(v, str) else v) for k, v in line.items()} for line in lines]
        lines = [line for line in lines if line.get("text")]
        if not lines:
            raise GuideInvalid(f"falta la sección «{SECTION_NAMES[key]}»")
        for n, line in enumerate(lines, 1):
            for field in ("text", "applies_to", "label"):
                if isinstance(line.get(field), str):
                    _check_text(f"{SECTION_NAMES[key]}, renglón {n}", line[field])
            if key != "generations" and not line.get("applies_to"):
                line["applies_to"] = None
        body[key] = lines

    questions = []
    for n, q in enumerate(draft.questions, 1):
        text, why = q.text.strip(), q.why.strip()
        if not QUESTION_MIN_CHARS <= len(text) <= QUESTION_MAX_CHARS or not text.endswith("?"):
            raise GuideInvalid(f"la pregunta {n} tiene que tener de {QUESTION_MIN_CHARS} a "
                               f"{QUESTION_MAX_CHARS} caracteres y terminar en «?»")
        _check_text(f"pregunta {n}", f"{text} {why}")
        questions.append({"text": text, "why": why})
    if not MIN_QUESTIONS <= len(questions) <= MAX_QUESTIONS:
        raise GuideInvalid(f"tiene {len(questions)} preguntas: van de {MIN_QUESTIONS} a {MAX_QUESTIONS}")

    sources = []
    for n, s in enumerate(draft.sources, 1):
        url = s.url.strip()
        if not url.startswith("https://"):
            raise GuideInvalid(f"la fuente {n} no es una URL https")
        _check_text(f"fuente {n}", s.title)
        # The LLM may suggest a source that doesn't exist: never verified here.
        sources.append({"title": s.title.strip(), "url": url, "kind": s.kind, "verified": False})
    return {"body": body, "questions": questions, "sources": sources}


def cache_key(make: str, model: str, generation_label: str | None, prompt_version: str) -> str:
    return "|".join((make.strip(), model.strip(), (generation_label or "").strip(), prompt_version)).lower()


# ---------------------------------------------------------------------------
# The published guides' questions in a listing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GuideEntry:
    guide_id: int
    generation_label: str | None
    year_from: int | None
    year_to: int | None
    questions: tuple[str, ...]

    def covers(self, year: int | None) -> bool:
        if year is None:
            return self.generation_label is None
        return ((self.year_from is None or year >= self.year_from)
                and (self.year_to is None or year <= self.year_to))

    def span(self) -> float:
        if self.year_from is None or self.year_to is None:
            return float("inf")
        return self.year_to - self.year_from


GuideIndex = Mapping[tuple[str, str], Sequence[GuideEntry]]


def build_index(rows: Iterable[Mapping[str, Any]]) -> dict[tuple[str, str], list[GuideEntry]]:
    """Rows of published guides (id, make, model, generation_label, year_from,
    year_to, questions) → {(make, model) lowercased: entries}."""
    index: dict[tuple[str, str], list[GuideEntry]] = {}
    for r in rows:
        texts = tuple(q["text"].strip() for q in (r.get("questions") or [])
                      if isinstance(q, Mapping) and isinstance(q.get("text"), str) and q["text"].strip())
        if not texts:
            continue
        index.setdefault((r["make"].lower(), r["model"].lower()), []).append(GuideEntry(
            int(r["id"]), r.get("generation_label"), r.get("year_from"), r.get("year_to"), texts))
    return index


def pick(index: GuideIndex | None, listing: Mapping[str, Any]) -> GuideEntry | None:
    """The guide whose questions this listing gets, or None."""
    if not index:
        return None
    make = listing.get("make")
    model = listing.get("catalog_model") or listing.get("model")
    if not make or not model:
        return None
    entries = index.get((str(make).lower(), str(model).lower())) or ()
    year = listing.get("year")
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    covering = [e for e in entries if e.covers(year)]
    if not covering:
        return None
    return min(covering, key=lambda e: (e.span(), e.generation_label is None, e.guide_id))


def same_question(a: str, b: str) -> bool:
    """Equal after folding accents, case, punctuation and spaces."""
    norm = lambda t: re.sub(r"[^\w]+", " ", fold(t)).strip()  # noqa: E731
    return norm(a) == norm(b)
