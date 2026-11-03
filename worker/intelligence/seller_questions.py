"""Questions for the seller (§25, sección 6.6). Deterministic templates.

Always: greeting, "¿lo seguís teniendo?", "¿sos titular?". Then, depending on
the red flags and the missing data: owners, timing belt, services, VTV,
crashes or repairs, km, transmission, whether the price is the total.
The web only copies the text; Automotive never contacts the seller (§6).
F5 may polish the wording with the LLM (llm.polish_questions).

PAR-04: with a published guide of the listing's model and generation
(intelligence/guides.pick), up to `guide_limit` of its questions go after
the ones this listing raises (red flags, what the description says) and
before the generic ones (age or missing data: VTV, crashes, services without
a description, km, transmission, trim). `question_items` says where each one
came from (matches.question_origins). Without a guide the order is the same
as before.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from intelligence.copy import QUESTION
from intelligence.guides import DEFAULT_MAX_QUESTIONS_IN_LISTING, MAX_QUESTIONS_IN_LISTING, GuideEntry, same_question
from intelligence.red_flags import RedFlag
from normalization.description_claims import claim


@dataclass(frozen=True)
class QuestionItem:
    key: str
    text: str
    # "template" (copy.QUESTION) or "guide" (a published model guide).
    origin: str = "template"
    guide_id: int | None = None

    def origin_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {"key": self.key, "origin": self.origin}
        if self.guide_id is not None:
            # The text too: unpublishing the guide removes exactly what was
            # written (public.model_guide_withdraw_questions).
            out["guide_id"] = self.guide_id
            out["text"] = self.text
        return out


# VTV is mandatory from the third year on in most jurisdictions.
_VTV_FROM_AGE = 3


def question_keys(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                  timing_belt: bool | None, now: datetime) -> list[str]:
    return [key for key, _ in _classified(listing, flags, timing_belt=timing_belt, now=now)]


# What each key is about: "base" (asked of every seller), "listing" (this
# listing's flags or description) or "generic" (age or a missing field).
def _classified(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                timing_belt: bool | None, now: datetime) -> list[tuple[str, str]]:
    ids = {f.id for f in flags}
    kinds: dict[str, str] = {}

    def generic(key: str) -> str:
        kinds[key] = "generic"
        return key

    facts = listing.get("description_facts") or {}
    # PAR-02 resto: a «particular» with many listings gets the holder question in full.
    keys = ["greeting", "available", "holder_detail" if "private_many_listings" in ids else "holder"]
    for key in keys:
        kinds[key] = "base"
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
        keys.append(generic("vtv"))
    if claim(facts, "damage_mentioned") is True:
        keys.append("damage_scope")
    elif claim(facts, "damage_mentioned") is False:
        keys.append("condition_photos")
    elif ids & {"much_cheaper", "partial_price_suspect"}:
        keys.append("crashes")
    elif year and now.year - int(year) >= _VTV_FROM_AGE:
        keys.append(generic("crashes"))
    if claim(facts, "service_history") is True:
        keys.append("service_proof")
    elif claim(facts, "service_history") is False:
        keys.append("maintenance_details")
    elif ids & {"no_service", "service_unavailable"}:
        keys.append("services")
    elif not listing.get("description"):
        keys.append(generic("services"))
    if "year_mismatch" in ids:
        keys.append("year_confirm")
    if listing.get("mileage_km") is None:
        keys.append(generic("km_unknown"))
    elif "km_mismatch" in ids:
        keys.append("km_confirm")
    elif "low_km_for_age" in ids:
        keys.append("km_original")
    if not listing.get("transmission"):
        keys.append(generic("transmission"))
    if not listing.get("trim"):
        keys.append(generic("trim"))
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
    return [(key, kinds.get(key, "listing")) for key in keys]


def question_items(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                   timing_belt: bool | None, now: datetime, guide: GuideEntry | None = None,
                   guide_limit: int = DEFAULT_MAX_QUESTIONS_IN_LISTING) -> list[QuestionItem]:
    """Every question, in order, with its origin. With a guide: base → this
    listing's → up to `guide_limit` of the guide's (not repeating a template
    one) → generic. Without one: question_keys' order."""
    classified = _classified(listing, flags, timing_belt=timing_belt, now=now)
    template = [QuestionItem(key, QUESTION[key]) for key, _ in classified]
    guide_limit = min(guide_limit, MAX_QUESTIONS_IN_LISTING)
    if guide is None or guide_limit <= 0:
        return template
    kind = {key: k for key, k in classified}
    head = [q for q in template if kind[q.key] != "generic"]
    tail = [q for q in template if kind[q.key] == "generic"]
    extra: list[QuestionItem] = []
    for n, text in enumerate(guide.questions):
        if len(extra) >= guide_limit:
            break
        if any(same_question(text, q.text) for q in template + extra):
            continue
        extra.append(QuestionItem(f"guide:{guide.guide_id}:{n}", text, "guide", guide.guide_id))
    return head + extra + tail


def seller_questions(listing: Mapping[str, Any], flags: Iterable[RedFlag], *,
                     timing_belt: bool | None, now: datetime, guide: GuideEntry | None = None,
                     guide_limit: int = DEFAULT_MAX_QUESTIONS_IN_LISTING) -> str:
    """One message ready to copy: "Hola, ¿cómo estás? ¿Lo seguís teniendo? …"."""
    return " ".join(q.text for q in question_items(listing, flags, timing_belt=timing_belt, now=now,
                                                   guide=guide, guide_limit=guide_limit))


# Asked of every seller, so they say nothing about this listing in a short summary.
GENERIC_KEYS = frozenset({"greeting", "available", "holder"})


def question_texts(listing: Mapping[str, Any], flags: Iterable[RedFlag | Mapping[str, Any]], *,
                   timing_belt: bool | None, now: datetime, limit: int = 3, guide: GuideEntry | None = None,
                   guide_limit: int = DEFAULT_MAX_QUESTIONS_IN_LISTING) -> list[str]:
    """The questions specific to this listing, in `question_items` order, without
    the greeting and the ones every seller gets (the alert email, H-01)."""
    flags = [f if isinstance(f, RedFlag) else RedFlag(**f) for f in flags]
    items = question_items(listing, flags, timing_belt=timing_belt, now=now, guide=guide, guide_limit=guide_limit)
    return [q.text for q in items if q.key not in GENERIC_KEYS][:limit]
