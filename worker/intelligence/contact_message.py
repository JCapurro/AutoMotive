"""The message for the seller, ready to copy (PRO-01 paso 2,
docs/superpowers/specs/2026-10-31-pro01-contacto-design.md, decisiones 13-17). Pure.

    render(template, catalog_model, year, questions) → 3-4 lines, «de vos»

A template (profiles.contact_template, the user's; null = DEFAULT_TEMPLATE)
has two markers, {auto} and {preguntas}, replaced literally in one pass:
never str.format, whose {x} or {auto.__class__} would raise or leak
attributes inside the notification batch. The stored template is linted again
on read (lint_contact_template, the rule the web applies on save) and any
failure, or any error while rendering, falls back to DEFAULT_TEMPLATE.
{auto} is the catalog's model and the year, never the listing's title or any
scraped text. The web has the twin, web/lib/contact-message.ts; both are
fixed by tests/fixtures/contact_message/{golden,lint}.json. Ese Auto never
sends it: the user copies it and sends it from the listing.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable

from intelligence import copy

log = logging.getLogger("contact_message")

DEFAULT_TEMPLATE = copy.CONTACT_MESSAGE["default"]
MAX_CHARS = 500
MAX_LINES = 6

_MARKER = re.compile(r"\{(auto|preguntas)\}")
_PERCENT = re.compile(r"%\(?[a-z]")
_URL = re.compile(
    r"https?://|(?<![\w-])www\.|(?<![\w-])wa\.me(?!\w)|@"
    r"|(?<![\w-])[\w-]+\.(?:com|net|org|ar|io|me|app|co|ly|info|link|site|online|store|shop)(?!\w)")
_PHONE = re.compile(r"\+?\d(?:[\s.\-()/]*\d){6,}")
_YEARS = range(1950, 2101)


def fold(text: str) -> str:
    """Lowercase without accents (NFD without marks), as the copy lint reads text."""
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def _forbidden(folded: str) -> bool:
    for phrase in copy.ALLOWED_PHRASES:
        folded = folded.replace(fold(phrase), " ")
    terms = sorted({fold(t) for t in copy.FORBIDDEN_TERMS})
    return any(re.search(r"(?:^|[^\w])" + re.escape(t) + r"(?:[^\w]|$)", folded) for t in terms)


def lint_contact_template(raw: str | None) -> tuple[str | None, str | None]:
    """(value to store, error code). A null, empty or blank template is
    (None, None): the default one. Errors: too_long, too_many_lines,
    placeholder, forbidden, url, phone."""
    if raw is None:
        return None, None
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return None, None
    if len(text) > MAX_CHARS:
        return None, "too_long"
    if text.count("\n") + 1 > MAX_LINES:
        return None, "too_many_lines"
    if "{" in _MARKER.sub("", text) or "}" in _MARKER.sub("", text) or _PERCENT.search(fold(text)):
        return None, "placeholder"
    folded = fold(text)
    if _forbidden(folded):
        return None, "forbidden"
    if _URL.search(folded):
        return None, "url"
    if _PHONE.search(folded):
        return None, "phone"
    return text, None


def auto_text(catalog_model: str | None, year: int | None) -> str:
    """«Fiesta 2017»: the catalog's model and a reasonable year; «auto»
    without a model or when the result isn't plain letters, digits, spaces,
    dots or dashes of up to 40 characters."""
    model = (catalog_model or "").strip()
    if not model:
        return copy.CONTACT_MESSAGE["auto"]
    value = f"{model} {year}" if isinstance(year, int) and year in _YEARS else model
    if len(value) > 40 or not all(c.isalnum() or c in " .-" for c in value):
        return copy.CONTACT_MESSAGE["auto"]
    return value


def _questions(questions: Iterable[str] | None) -> str:
    first = next(iter(questions or ()), None)
    return "\n".join([copy.QUESTION["available"], first or copy.QUESTION["holder"]])


def _fill(template: str, auto: str, questions: str) -> str:
    values = {"auto": auto, "preguntas": questions}
    return _MARKER.sub(lambda m: values[m.group(1)], template)


def render(template: str | None, catalog_model: str | None, year: int | None,
           questions: Iterable[str] | None) -> str:
    """The message. Never raises: a stored template that fails the lint, or
    anything going wrong, gives the default message."""
    auto, asked = auto_text(catalog_model, year), _questions(questions)
    try:
        value, error = lint_contact_template(template)
        if error:
            log.warning("contact_template rejected on read (%s): default template", error)
        return _fill(value if value and not error else DEFAULT_TEMPLATE, auto, asked)
    except Exception:
        log.warning("contact_template failed to render: default template", exc_info=True)
        return _fill(DEFAULT_TEMPLATE, auto, asked)


def subject(catalog_model: str | None, year: int | None) -> str:
    return copy.CONTACT_MESSAGE["subject"].replace("{auto}", auto_text(catalog_model, year))
