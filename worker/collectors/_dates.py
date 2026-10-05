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
from datetime import datetime, timedelta, timezone
from typing import Any


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
    if "anteayer" in s:
        return now - 2 * 86_400
    if "ayer" in s:
        return now - 86_400

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


_AR_TZ = timezone(timedelta(hours=-3))
_MONTHS = {name: i for i, name in enumerate((
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre"), 1)}


def parse_publication_date(value: Any) -> int | None:
    """Explicit publication date (ISO, Argentine calendar date or relative).

    Date-only values and naive times belong to Argentina, never the worker's
    host timezone. Invalid/future dates remain unknown.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    s = _strip_accents(value).lower().strip()
    s = re.sub(r"^(?:fecha de publicacion|publicad[oa])\s*:?\s*(?:el\s+)?", "", s)
    s = re.sub(r"^el\s+", "", s)
    parsed = None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[t ].+)?", s):
            dt = datetime.fromisoformat(s.replace("z", "+00:00"))
        elif re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", s):
            dt = datetime.strptime(s.replace("-", "/"), "%d/%m/%Y")
        elif m := re.fullmatch(r"(\d{1,2}) de ([a-z]+) (?:de |del )?(\d{4})", s):
            dt = datetime(int(m[3]), _MONTHS[m[2]], int(m[1]))
        elif re.fullmatch(r"(?:hace\s+)?\d+\s*(?:minutos?|horas?|h|dias?|semanas?|mes(?:es)?|anos?)|hoy|ayer|anteayer|ahora|recien publicado|publicado ahora", s):
            parsed = parse_relative_date(s)
            dt = None
        else:
            return None
        if dt is not None:
            parsed = int((dt if dt.tzinfo else dt.replace(tzinfo=_AR_TZ)).timestamp())
    except (ValueError, KeyError, OverflowError):
        return None
    return parsed if parsed is not None and 0 < parsed <= int(time.time()) else None


def publication_date(container, *, structured: dict | None = None,
                     text: str | None = None) -> int | None:
    """Read only publication-specific fields of the current ad/card.

    The caller supplies its own JSON-LD vehicle, so related ads, model year,
    price validity and dateModified cannot become the publication date.
    """
    data = structured or {}
    offer = data.get("offers") or {}
    candidates = [data.get("datePublished")]
    if isinstance(offer, dict):
        candidates.append(offer.get("datePublished"))
    primary = next((scope for scope in container.select(
        '[itemscope][itemtype*="Car"], [itemscope][itemtype*="Vehicle"]')
        if scope.select_one("h1") is not None), None)
    for el in container.select('[itemprop="datePublished"], meta[property="article:published_time"], meta[name="datePublished"]'):
        # Ignore publication metadata nested inside another vehicle/card.
        owner = el.find_parent(lambda tag: tag.has_attr("itemscope") and
                               any(kind in str(tag.get("itemtype", "")) for kind in ("Car", "Vehicle")))
        if owner is not None and owner is not container and owner is not primary:
            continue
        candidates.append(el.get("content") or el.get("datetime") or el.get_text(" ", strip=True))
    candidates.append(text)
    return next((ts for value in candidates if (ts := parse_publication_date(value)) is not None), None)
