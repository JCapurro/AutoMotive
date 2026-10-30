"""The effective seller (F-02 paso 2, docs/superpowers/specs/2026-10-30-f02-vendedor-design.md,
decisión 6): 'dealer' when the source says so or the listing is a «posible
agencia» (listings.dealer_inferred: its seller published min_listings or more
cars in the same source, see db/repos/sellers.py); otherwise seller_type.

Every consumer that treats a seller as an agency reads it from here, never
seller_type alone: the seller preference in matching today, PRO-01's hard
filter and PAR-01's costs tomorrow. The web has the twin, web/lib/seller.ts.
The inference wins even over a listing that says «particular» (Juan,
30/10/2026); seller_type itself is never rewritten.
"""
from __future__ import annotations

from typing import Any, Mapping

from intelligence import copy


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
