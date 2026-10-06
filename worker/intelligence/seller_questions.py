"""Questions for the seller (§25, sección 6.6). Deterministic templates.

Always: greeting, "¿lo seguís teniendo?", "¿sos titular?". Then, depending on
the red flags and the missing data: owners, timing belt, services, VTV,
crashes or repairs, km, transmission, whether the price is the total.
The web only copies the text; Automotive never contacts the seller (§6).
F5 may polish the wording with the LLM (llm.polish_questions).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping

from intelligence.copy import QUESTION
from intelligence.red_flags import RedFlag
from normalization.description_claims import claim


# VTV is mandatory from the third year on in most jurisdictions.
_VTV_FROM_AGE = 3


def question_keys(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                  timing_belt: bool | None, now: datetime) -> list[str]:
    ids = {f.id for f in flags}
    facts = listing.get("description_facts") or {}
    keys = ["greeting", "available", "holder"]
    if "no_owners" in ids or claim(facts, "single_owner") is False:
        keys.append("owners")
    if claim(facts, "timing_belt_changed") is True:
        keys.append("timing_proof")
    elif claim(facts, "timing_belt_changed") is False:
        keys.append("timing_pending")
    elif ids & {"no_timing_belt", "timing_pending"} or (timing_belt and not listing.get("description")):
        keys.append("timing_belt")
    year = listing.get("year")
    if claim(facts, "vtv_current") is False:
        keys.append("vtv_pending")
    elif claim(facts, "vtv_current") is None and year and now.year - int(year) >= _VTV_FROM_AGE:
        keys.append("vtv")
    if claim(facts, "damage_mentioned") is True:
        keys.append("damage_scope")
    elif claim(facts, "damage_mentioned") is False:
        keys.append("condition_photos")
    elif ids & {"much_cheaper", "partial_price_suspect"} or (year and now.year - int(year) >= _VTV_FROM_AGE):
        keys.append("crashes")
    if claim(facts, "service_history") is True:
        keys.append("service_proof")
    elif claim(facts, "service_history") is False:
        keys.append("maintenance_details")
    elif ids & {"no_service", "service_unavailable"} or not listing.get("description"):
        keys.append("services")
    if "year_mismatch" in ids:
        keys.append("year_confirm")
    if listing.get("mileage_km") is None:
        keys.append("km_unknown")
    elif "km_mismatch" in ids:
        keys.append("km_confirm")
    elif "low_km_for_age" in ids:
        keys.append("km_original")
    if not listing.get("transmission"):
        keys.append("transmission")
    if not listing.get("trim"):
        keys.append("trim")
    if claim(facts, "commercial_use") is True:
        keys.append("commercial_history")
    if claim(facts, "documentation") is not None:
        keys.append("documentation")
    if claim(facts, "negotiable") is True:
        keys.append("cash_offer")
    if ids & {"partial_price_suspect"} or listing.get("price_partial"):
        keys.append("total_price")
    elif "price_mismatch" in ids:
        keys.append("price_confirm")
    return keys


def seller_questions(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                     timing_belt: bool | None, now: datetime) -> str:
    """One message ready to copy: "Hola, ¿cómo estás? ¿Lo seguís teniendo? …"."""
    return " ".join(QUESTION[k] for k in question_keys(listing, flags, timing_belt=timing_belt, now=now))
