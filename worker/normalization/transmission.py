"""Transmission and fuel from free text (sección 5.2, paso 2).

Sources rarely agree on how they spell these: "Manual", "MT", "6MT", "caja
manual", "AT", "Automática", "CVT", "Tiptronic"… Structured attributes (a
detail page's spec table) are trusted before the title, and a text that
mentions both kinds of gearbox resolves to None rather than a guess.
"""
from __future__ import annotations

import re

from normalization.normalize import normalize_text


# "mecánico" alone is not a gearbox ("estado mecánico impecable"); "caja mecánica" is.
_MANUAL = re.compile(
    r"\b(manual|caja mecanica|\d?\s?mt|m/t)\b"
)
_AUTOMATIC = re.compile(
    r"\b(automatic[oa]?|autom|aut|\d?\s?at|a/t|e?cvt|tiptronic|steptronic|multitronic|"
    r"powershift|s-?tronic|dsg|dct|edct|secuencial|xtronic|easytronic|dualogic)\b"
)

_FUELS = (
    # Order matters: "nafta/gnc" is a GNC car, "turbo diesel" is diesel.
    ("electrico", re.compile(r"\b(electrico|100% electrico|ev)\b")),
    ("hibrido", re.compile(r"\b(hibrido|hybrid|hev|phev|mhev)\b")),
    ("gnc", re.compile(r"\b(gnc|gas natural)\b")),
    ("diesel", re.compile(r"\b(diesel|gasoil|tdi|hdi|tdci|crdi|dci|jtd|multijet|turbo ?diesel)\b")),
    ("nafta", re.compile(r"\b(nafta|naftero|gasolina|flex)\b")),
)


def _classify(text: str) -> str | None:
    manual = bool(_MANUAL.search(text))
    automatic = bool(_AUTOMATIC.search(text))
    if manual == automatic:
        return None
    return "manual" if manual else "automatic"


def transmission(*texts: str | None) -> str | None:
    """'manual' | 'automatic' | None, from the first text that settles it.

    Pass the most structured value first (a spec table's "Transmisión"),
    then the title and description.
    """
    for raw in texts:
        text = normalize_text(raw)
        if text and (kind := _classify(text)):
            return kind
    return None


def fuel(*texts: str | None) -> str | None:
    """Canonical fuel ('nafta', 'diesel', 'gnc', 'hibrido', 'electrico') or None,
    using the same catalog spelling as vehicle_catalog.fuels."""
    for raw in texts:
        text = normalize_text(raw)
        if not text:
            continue
        for name, pattern in _FUELS:
            if pattern.search(text):
                return name
    return None


_SELLER_TYPES = {
    "particular": "private", "dueno directo": "private", "privado": "private",
    "private": "private",
    "concesionaria": "dealer", "concesionario": "dealer", "agencia": "dealer",
    "dealer": "dealer", "tienda oficial": "dealer", "profesional": "dealer",
}


def seller_type(raw: str | None) -> str | None:
    """'private' | 'dealer' | None."""
    text = normalize_text(raw)
    if not text:
        return None
    if text in _SELLER_TYPES:
        return _SELLER_TYPES[text]
    for word, kind in _SELLER_TYPES.items():
        if re.search(rf"\b{word}\b", text):
            return kind
    return None
