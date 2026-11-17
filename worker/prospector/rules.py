"""Hard rules every message must pass before a person sees it. Pure.

The reviewer model checks tone and meaning; these are the checks a program
does better: length, links, banned words, emojis, and that every number in
the text comes from the prospect's facts.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable

MAX_CHARS = 450
MAX_PARAGRAPHS = 3
MAX_EMOJIS = 1

_LINK = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|ar|net|org|io|app)\b)", re.IGNORECASE)
# Whole words, accents folded. «vendido» (sold) is never known: «dejó de publicarse».
_BANNED = (
    (re.compile(r"\bia\b|inteligencia artificial|\bai\b", re.IGNORECASE), "menciona IA"),
    (re.compile(r"\bvendid[oa]s?\b|\bse vendio\b|\bse vendieron\b|\bvendio\b", re.IGNORECASE), "dice vendido"),
    (re.compile(r"\bganancias?\b|\bganar plata\b|\bgarantiz|\bseguro que ganas\b|\brentabilidad asegurada\b",
                re.IGNORECASE), "promete ganancias"),
    (re.compile(r"\b(plan pro|precio fundador|\$ ?100\.000|\$ ?50\.000|por mes|mensual(es)?)\b", re.IGNORECASE),
     "menciona el precio del plan"),
    (re.compile(r"\b(darte de baja|darse de baja|no te escribo mas|responde baja|stop)\b", re.IGNORECASE),
     "tiene línea de baja"),
    (re.compile(r"\b(usted|vosotros)\b", re.IGNORECASE), "no usa voseo"),
)
_TUTEO = re.compile(r"\b(tienes|puedes|quieres|sabes|eres|buscas|vendes|compras)\b", re.IGNORECASE)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
_NUMBER = re.compile(r"(?<![\w])(?:US\$|U\$S|\$)?\s?\d[\d.,]*(?:\s?%)?")


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn").lower()


def _digits(token: str) -> str:
    """The number a token says, as plain digits ('$14.500.000' → '14500000', '14 %' → '14')."""
    t = token.strip().rstrip("%").strip()
    t = re.sub(r"^(US\$|U\$S|\$)\s?", "", t, flags=re.IGNORECASE)
    t = t.rstrip(".,")
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
        return t.replace(".", "")
    if re.fullmatch(r"\d+,\d+", t):
        return t.replace(",", ".")
    return t.replace(".", "").replace(",", "")


_NOT_SAYABLE = frozenset({"url", "listing_id", "id", "telefono"})


def allowed_numbers(facts: Any) -> set[str]:
    """Every number that appears anywhere in the facts, in the forms a message may write it."""
    out: set[str] = set()

    def add(value: Any) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            if float(value).is_integer():
                out.add(str(int(value)))
            else:
                out.add(f"{value:.1f}".rstrip("0").rstrip("."))
                out.add(str(round(value)))
            return
        if isinstance(value, str):
            for m in _NUMBER.finditer(value):
                out.add(_digits(m.group(0)))
            return
        if isinstance(value, dict):
            for k, v in value.items():
                if k not in _NOT_SAYABLE:
                    add(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                add(v)

    add(facts)
    out.discard("")
    return out


def numbers_in(text: str) -> list[str]:
    found = []
    for m in _NUMBER.finditer(text):
        d = _digits(m.group(0))
        if d and any(ch.isdigit() for ch in d):
            found.append(d)
    return found


# «Vi que tenés un Gol Trend»: weak for a dealer with 8 to 60 cars.
_ONE_CAR = re.compile(r"\b(vi|veo) que (tenes|tienen)( publicad[oa]s?)? (un|una|1) ")


def check(text: str, facts: Any, *, extra_numbers: Iterable[str] = ()) -> list[str]:
    """What is wrong with a message, in Spanish for the log and the page; [] when it passes."""
    problems: list[str] = []
    body = (text or "").strip()
    if not body:
        return ["mensaje vacío"]
    full = body
    hello = facts.get("saludo") if isinstance(facts, dict) else None
    if hello:
        if not fold(body).startswith(fold(hello)):
            problems.append(f"no arranca con el saludo de los hechos («{hello}»)")
        else:
            body = body[len(hello):].strip()      # the «¿cómo andan?» of the greeting is not the question
    if len(full) > MAX_CHARS:
        problems.append(f"tiene {len(full)} caracteres (máximo {MAX_CHARS})")
    paragraphs = [p for p in re.split(r"\n\s*\n", full) if p.strip()]
    if len(paragraphs) > MAX_PARAGRAPHS:
        problems.append(f"tiene {len(paragraphs)} párrafos (máximo {MAX_PARAGRAPHS})")
    if _LINK.search(body):
        problems.append("tiene un link")
    folded = fold(body)
    for pattern, problem in _BANNED:
        if pattern.search(folded):
            problems.append(problem)
    if _TUTEO.search(body.lower()):     # accents kept: «comprás» is voseo, «compras» is not
        problems.append("usa tuteo en vez de voseo")
    if len(_EMOJI.findall(body)) > MAX_EMOJIS:
        problems.append("tiene más de un emoji")
    if body.count("?") < 1:
        problems.append("no termina con una pregunta")
    elif body.count("¿") > 1 or body.count("?") > 1:
        problems.append("hace más de una pregunta")
    elif not body.rstrip().endswith("?"):
        problems.append("la pregunta no va al final")
    if "soy juan" not in folded:
        problems.append("Juan no se presenta")
    if _ONE_CAR.search(folded):
        problems.append("el dato de su stock es un solo auto: usá el total o un modelo del que tiene varios")
    allowed = allowed_numbers(facts) | set(extra_numbers)
    stray = [n for n in numbers_in(body) if n not in allowed]
    if stray:
        problems.append("números que no están en los hechos: " + ", ".join(sorted(set(stray))))
    return problems
