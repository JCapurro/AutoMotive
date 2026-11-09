"""The effective seller (F-02 paso 2, docs/superpowers/specs/2026-10-30-f02-vendedor-design.md,
decisión 6): 'dealer' when the source says so or the listing is a «posible
agencia» (listings.dealer_inferred: its seller published min_listings or more
cars in the same source, see db/repos/sellers.py); otherwise seller_type.

Every consumer that treats a seller as an agency reads it from here, never
seller_type alone: the seller preference in matching today, PRO-01's hard
filter and PAR-01's costs tomorrow. The web has the twin, web/lib/seller.ts.
The inference wins even over a listing that says «particular» (Juan,
30/10/2026); seller_type itself is never rewritten.

The agency voice (f3, docs/superpowers/specs/2026-11-08-recalibracion-score-design.md
§3.2 and §4.7) is a separate predicate on purpose and never enters
effective_seller: that one also feeds PRO-01's strict filter, the total cost,
the duplicates and the comparables split by seller, which the description's
wording must not move. Only f3's seller preference and seller cap read it,
through seller_for_preference (in shadow mode, so nothing visible yet).
"""
from __future__ import annotations

import functools
import re
from typing import Any, Mapping

from intelligence import copy
from normalization.normalize import normalize_text


def effective_seller(listing: Mapping[str, Any]) -> str | None:
    """'dealer', 'private' or None (not informed)."""
    if listing.get("seller_type") == "dealer" or listing.get("dealer_inferred"):
        return "dealer"
    return listing.get("seller_type") or None


def seller_kind(listing: Mapping[str, Any]) -> str | None:
    """How a reason names the seller: «particular», «concesionaria» or
    «posible agencia (publica N autos)»; None when not informed."""
    if listing.get("dealer_inferred") and listing.get("seller_type") != "dealer":
        n = listing.get("seller_listing_count")
        if n is None:
            return copy.SELLER_INFERRED
        return f"{copy.SELLER_INFERRED} ({copy.REASON['seller_inferred'].format(n=n)})"
    have = effective_seller(listing)
    return copy.SELLER.get(have, have) if have else None


# Agency voice (spec §3.2, final regex of §16.7): one first-person plural phrase
# («financiamos», «recibimos tu usado», «tomamos usados», «somos agencia»,
# «nuestros locales»), or two distinct weak signals. Not «services en
# concesionario oficial» or «financio», which a private seller writes too, nor a
# negated phrase («no financiamos», «no tomamos tu auto», «no somos agencia»).
# Whole words, with the plural of the object («usados», «unidades»,
# «concesionarios»), as the measured version (no trailing boundary there) matched
# them; «usadote» and «refinanciamos» still do not. Read on the text through
# normalize_text (lower case, no accents, single spaces; punctuation kept, so
# «no, financiamos» is not a negation).
_STRONG = re.compile(
    r"(?<!\bno )\b(financiamos"
    r"|(tomamos|recibimos|aceptamos) (tus? |sus? )?(usados?|autos?|vehiculos?|unidad(es)?)"
    r"|te lo compramos|compramos tus? (autos?|usados?|vehiculos?)"
    r"|somos (una )?(agencias?|concesionari[ao]s?)"
    r"|nuestr[oa]s? (agencias?|concesionari[ao]s?|local(es)?|salon(es)?|showrooms?))\b")
# Each weak signal once: two phrases of the same kind (two ways of offering
# financing) are one signal.
_WEAK = (
    ("dni", re.compile(r"\bsolo (con )?(el |tu )?dni\b")),
    ("cuotas", re.compile(r"\bcuotas (fijas|en pesos)\b")),
    ("financiacion", re.compile(r"\b(credito prendario|financiacion (propia|accesible|en pesos|bancaria"
                                r"|personalizada|disponible)|(opciones|planes) de financiacion)\b")),
    ("consignacion", re.compile(r"\bconsignacion(es)?\b")),
    ("horario", re.compile(r"\bhorario de atencion\b")),
)
WEAK_JOIN = " · "


@functools.lru_cache(maxsize=4096)
def agency_voice(description: str | None) -> str | None:
    """The phrase that makes a description read like an agency's, or None: the
    first strong phrase, or the first two weak signals joined with « · »."""
    if not description or not isinstance(description, str):
        return None
    text = normalize_text(description)
    strong = _STRONG.search(text)
    if strong:
        return strong.group(0)
    found: list[tuple[int, str]] = []
    for _, pattern in _WEAK:
        m = pattern.search(text)
        if m:
            found.append((m.start(), m.group(0)))
    if len(found) < 2:
        return None
    return WEAK_JOIN.join(phrase for _, phrase in sorted(found)[:2])


def seller_for_preference(listing: Mapping[str, Any]) -> str | None:
    """The seller f3's preference and cap read: 'dealer' when effective_seller
    says so, or when the source says «particular» and the description has the
    agency voice; otherwise effective_seller. Nothing else reads it."""
    have = effective_seller(listing)
    if have != "dealer" and listing.get("seller_type") == "private" and agency_voice(listing.get("description")):
        return "dealer"
    return have
