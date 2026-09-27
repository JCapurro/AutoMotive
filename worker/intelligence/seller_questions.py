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


# VTV is mandatory from the third year on in most jurisdictions.
_VTV_FROM_AGE = 3


def question_keys(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                  timing_belt: bool | None, now: datetime) -> list[str]:
    ids = {f.id for f in flags}
    keys = ["greeting", "available", "holder"]
    if "no_owners" in ids:
        keys.append("owners")
    if "no_timing_belt" in ids or (timing_belt and not listing.get("description")):
        keys.append("timing_belt")
    year = listing.get("year")
    if year and now.year - int(year) >= _VTV_FROM_AGE:
        keys.append("vtv")
    if ids & {"much_cheaper", "partial_price_suspect"} or (year and now.year - int(year) >= _VTV_FROM_AGE):
        keys.append("crashes")
    if "no_service" in ids or not listing.get("description"):
        keys.append("services")
    if listing.get("mileage_km") is None:
        keys.append("km_unknown")
    elif "low_km_for_age" in ids:
        keys.append("km_original")
    if not listing.get("transmission"):
        keys.append("transmission")
    if not listing.get("trim"):
        keys.append("trim")
    if ids & {"partial_price_suspect"} or listing.get("price_partial"):
        keys.append("total_price")
    return keys


def seller_questions(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                     timing_belt: bool | None, now: datetime) -> str:
    """One message ready to copy: "Hola, ¿cómo estás? ¿Lo seguís teniendo? …"."""
    return " ".join(QUESTION[k] for k in question_keys(listing, flags, timing_belt=timing_belt, now=now))
