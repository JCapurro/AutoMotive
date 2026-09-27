"""Parse Spanish relative date strings shown by AR car classifieds.

Examples handled:
    "Hace 2 horas"      → now - 2h
    "Hace 30 minutos"   → now - 30m
    "Hace 1 día"        → now - 1d
    "Hace 7 días"       → now - 7d
    "Publicado hoy"     → now
    "Ayer"              → now - 1d

Returns a unix timestamp (int) or None if the string can't be parsed.
Granularity is good enough for "is this within the last N hours" checks.
"""
from __future__ import annotations
import re
import time
import unicodedata


_NUM_RE = re.compile(r"(\d+)")


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def parse_relative_date(text: str | None) -> int | None:
    """Return a unix timestamp inferred from a Spanish relative-date string."""
    if not text:
        return None
    s = _strip_accents(text).lower().strip()
    now = int(time.time())

    if "hoy" in s or s in ("ahora", "recien publicado", "publicado ahora"):
        return now
    if "ayer" in s:
        return now - 86_400
    if "anteayer" in s:
        return now - 2 * 86_400

    n_match = _NUM_RE.search(s)
    if not n_match:
        return None
    n = int(n_match.group(1))

    # Map a unit token to seconds. Order matters — match the most specific first.
    if "min" in s:                  # "hace 30 minutos"
        return now - n * 60
    if "hora" in s or " h " in f" {s} " or s.endswith(" h"):
        return now - n * 3_600
    if "dia" in s:                  # "hace 7 dias"
        return now - n * 86_400
    if "semana" in s:
        return now - n * 7 * 86_400
    if "mes" in s:                  # "hace 2 meses"
        return now - n * 30 * 86_400
    if "ano" in s:                  # "hace 1 año" → "hace 1 ano" after strip
        return now - n * 365 * 86_400

    return None
