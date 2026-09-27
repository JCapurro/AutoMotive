"""Brand/model normalization so comparables match across sources.

Used both at scrape time (when caching listings) and at compare time
(when looking up comparables for opportunity scoring).
"""
from __future__ import annotations
import re
import unicodedata


_BRAND_ALIAS = {
    "vw":            "volkswagen",
    "volks":         "volkswagen",
    "chevy":         "chevrolet",
    "merc":          "mercedes-benz",
    "mercedes":      "mercedes-benz",
    "mercedes benz": "mercedes-benz",
    "mb":            "mercedes-benz",
    "citroën":       "citroen",
    "peugeut":       "peugeot",
    "land-rover":    "land rover",
    "alfa":          "alfa romeo",
}


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    s = _strip_accents(s).lower().strip()
    return re.sub(r"\s+", " ", s)


def normalize_brand(s: str | None) -> str:
    n = normalize_text(s)
    return _BRAND_ALIAS.get(n, n)


def normalize_model(s: str | None) -> str:
    """Model names — strip extra trim qualifiers leaving only the base model."""
    n = normalize_text(s)
    # collapse "corolla cross" / "corolla xei" → keep first 2 words max
    parts = n.split()
    return " ".join(parts[:2]) if parts else ""
