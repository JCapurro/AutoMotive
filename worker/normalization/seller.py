"""The seller key (F-02, docs/superpowers/specs/2026-10-30-f02-vendedor-design.md,
decision 2): the seller name normalized so that the same seller written two
ways groups together within a source.

* normalize_text (no accents, lower case, spaces collapsed); then `.` and `'`
  are dropped and every other symbol, punctuation mark or emoji becomes a
  space, leaving `[a-z0-9 ]`: «Autos S.A.» and «Autos SA» → `autos sa`.
  Runs of single letters are then joined, so spaced initials group with
  the written-together ones: «Autos S. A.» and «Motors S. R. L.» →
  `autos sa`, `motors srl`.
* Only digits (a phone): Argentine formats are brought to the 10-digit
  national number (no +54, no 9 after it, no leading 0 of the area code, no
  15 after the area code), so «0341 15 555-1234» and «+54 9 341 555-1234»
  are both `tel:3415551234`. Fewer than 8 digits: no key.
* Generic labels (STOPLIST, an exact match after normalizing) and anything
  shorter than 3 characters: no key.

Written by db/repos/listings.py from the merged seller_name; it is not one of
the KEY_ATTRS (no snapshot) and the fingerprint does not use it.
"""
from __future__ import annotations

import re

from normalization.normalize import normalize_text

# Extend with what `python -m tools.seller_classification --dry-run` shows.
STOPLIST = frozenset({
    "particular", "dueno", "dueno directo", "vendedor", "concesionaria", "agencia", "whatsapp",
    "instagram", "facebook", "ver perfil", "contacto", "consultar", "informacion del vendedor",
})

_DROPPED = re.compile(r"[.'’`´]")
_OTHER = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")
_DIGITS_ONLY = re.compile(r"[0-9 ]+")
_INITIALS = re.compile(r"\b([a-z]) (?=[a-z]\b)")   # «s a» → «sa»

_NATIONAL = 10       # area code + number, without the 0 and the 15
_MIN_PHONE = 8


def _national_number(digits: str) -> str:
    """An Argentine phone written in any of the usual ways, as its 10-digit
    national number when it can be told; otherwise the digits as given."""
    if digits.startswith("00"):                        # 0054 ...
        digits = digits[2:]
    if digits.startswith("54") and len(digits) > _NATIONAL:
        digits = digits[2:]
        if digits.startswith("9") and len(digits) > _NATIONAL:   # mobile marker after +54
            digits = digits[1:]
    if digits.startswith("0"):                         # the trunk prefix of the area code
        digits = digits[1:]
    if len(digits) == _NATIONAL + 2:
        # Area codes have 2 to 4 digits; a mobile written locally puts 15 after it.
        for at in (2, 3, 4):
            if digits[at:at + 2] == "15":
                return digits[:at] + digits[at + 2:]
    return digits


def seller_key(name: str | None) -> str | None:
    """The normalized key of a seller name, or None when there is nothing to
    group by (missing, generic or too short)."""
    text = _DROPPED.sub("", normalize_text(name))
    text = _SPACES.sub(" ", _OTHER.sub(" ", text)).strip()
    text = _INITIALS.sub(r"\1", text)
    if not text:
        return None
    if _DIGITS_ONLY.fullmatch(text):
        digits = _national_number(text.replace(" ", ""))
        return f"tel:{digits[-_NATIONAL:]}" if len(digits) >= _MIN_PHONE else None
    if len(text) < 3 or text in STOPLIST:
        return None
    return text
