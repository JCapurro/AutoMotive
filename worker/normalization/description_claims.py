"""Ground seller statements in the actual text before keeping them. No I/O."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping

CLAIM_FIELDS = ("trim", "engine", "equipment", "single_owner", "service_history", "timing_belt_changed",
                "tires_condition", "commercial_use", "repairs", "damage_mentioned", "damage_details",
                "vtv_current", "documentation", "accepts_trade_in", "negotiable", "urgent_sale", "sale_reason")


def folded(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def input_hash(title: str | None, description: str | None) -> str:
    return hashlib.sha256(json.dumps([title or "", description or ""], ensure_ascii=False).encode()).hexdigest()


def quote_contexts(quote: str, text: str) -> list[str]:
    """Include preceding clause context so a quote cannot crop off a negation/service label."""
    whole, needle = folded(text), folded(quote)
    out = []
    for match in re.finditer(re.escape(needle), whole):
        prefix = whole[:match.start()]
        boundaries = [m.end() for m in re.finditer(r"[.!?;]\s+", prefix)]
        start = max(boundaries[-1] if boundaries else 0, match.start() - 60)
        out.append(whole[start:match.end()])
    return out


def _negative(text: str) -> bool:
    return bool(re.search(r"\b(no|sin|nunca|vencid[ao]s?|pendiente|falta|fijo|hay que|a realizar)\b", text))


_BOOL_SUBJECT = {
    "single_owner": r"\b(unico|primer|1|un)\s+(dueno|titular)|\bprimera mano\b",
    "service_history": r"\b(service|services|servicio|servicios|mantenimiento|mantenimientos|historial)\b",
    "timing_belt_changed": r"\b(distribucion|correa)\b",
    "accepts_trade_in": r"\b(permut\w*|canje\w*)\b",
    "financing": r"\b(financi\w*|cuotas?|anticipo)\b",
    "damage_mentioned": r"\b(choqu\w*|choc\w*|granizo|golp\w*|dan\w*|detalles?|ray\w*|aboll\w*)\b",
    "commercial_use": r"\b(taxi|remis|uber|cabify|comercial|trabajo)\b",
    "vtv_current": r"\b(vtv|rto|verificacion tecnica)\b",
    "negotiable": r"\b(negocia\w*|conversa\w*|charla\w*|ofertas?|fijo)\b",
    "urgent_sale": r"\b(urgent\w*|urgencia|apuro)\b",
}


def _bool_supported(field: str, value: bool, quote: str) -> bool:
    plain = "".join(c for c in unicodedata.normalize("NFD", folded(quote)) if unicodedata.category(c) != "Mn")
    return _negative(plain) != value and bool(re.search(_BOOL_SUBJECT.get(field, r"(?!)"), plain))


def grounded_values(answer: Any, text: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Reject missing/invented citations, invented string values and inverted negations.

    Literal evidence is a provenance check, not independent verification of the car.
    The model handles meaning; these guards reject common contradictory responses.
    """
    data = answer.model_dump() if hasattr(answer, "model_dump") else vars(answer)
    quotes: dict[str, list[str]] = {}
    for ev in data.get("evidence") or []:
        field, quote = ev.get("field"), ev.get("quote")
        if isinstance(field, str) and isinstance(quote, str) and quote.strip() and folded(quote) in folded(text):
            quotes.setdefault(field, []).append(quote.strip())
    values: dict[str, Any] = {}
    kept: list[dict[str, str]] = []
    for field, snippets in quotes.items():
        value = data.get(field)
        if value is None or value == []:
            continue
        if isinstance(value, bool):
            snippets = [q for q in snippets if _bool_supported(field, value, q)
                        and all(_bool_supported(field, value, c) for c in quote_contexts(q, text))]
        elif isinstance(value, str) and field in CLAIM_FIELDS:
            snippets = [q for q in snippets if folded(value) in folded(q)
                        and _negative(folded(value)) == _negative(folded(q))
                        and all(_negative(folded(q)) == _negative(c) for c in quote_contexts(q, text))]
        elif isinstance(value, list):
            value = list(dict.fromkeys(v for v in value if isinstance(v, str) and v.strip()
                                      and any(folded(v) in folded(q) and not _negative(folded(q))
                                              and all(not _negative(c) for c in quote_contexts(q, text)) for q in snippets)))
            snippets = [q for q in snippets if any(folded(v) in folded(q) for v in value)]
        if snippets and value != []:
            values[field] = value
            kept.extend({"field": field, "quote": q} for q in dict.fromkeys(snippets))
    return values, kept


def claim(facts: Mapping[str, Any] | None, field: str) -> Any:
    """Only use new claims accompanied by evidence, including explicit false."""
    facts = facts or {}
    if not any(ev.get("field") == field for ev in facts.get("evidence") or [] if isinstance(ev, dict)):
        return None
    return (facts.get("claims") or {}).get(field)
