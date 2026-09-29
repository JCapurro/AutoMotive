"""Red flags (§24, sección 6.5). Pure, deterministic rules.

Each flag has an id, a text and a severity, and every text reads as
"conviene verificar": a flag never claims fraud or a mechanical problem.

Rules that read the description stay pending (they don't fire) while the
listing has no description and hasn't been enriched yet: the card simply
didn't carry it. After enrichment a missing description is itself a flag.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping

from intelligence import copy
from intelligence.config import IntelligenceConfig
from normalization.normalize import normalize_text


@dataclass(frozen=True)
class RedFlag:
    id: str
    text: str
    severity: str        # 'info' | 'warning'

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


_OWNERS = re.compile(r"\b(duen[oa]s?|titular(es)?|unico dueno|primer dueno|1 dueno|(unica|primera|segunda) mano)\b")
_SERVICE = re.compile(r"\b(services?|servicios? oficial\w*|mantenimiento|service oficial)\b")
_TIMING_BELT = re.compile(r"\b(distribucion|correa|kit de distribucion)\b")
# km the description and the listing may disagree on before it's worth a flag.
_KM_MISMATCH_MIN = 5_000
_KM_MISMATCH_SHARE = 0.10


def description_known(listing: Mapping[str, Any]) -> bool:
    return bool(listing.get("description")) or listing.get("enriched_at") is not None


def _age_years(listing: Mapping[str, Any], now: datetime) -> int | None:
    year = listing.get("year")
    if not year:
        return None
    return max(1, now.year - int(year))


def red_flags(listing: Mapping[str, Any], *, diff_pct: float | None, guard: str | None,
              timing_belt: bool | None, cfg: IntelligenceConfig, now: datetime) -> list[RedFlag]:
    """`diff_pct`: % below the comparables' median (None without enough of them).
    `guard`: the scoring guard ('suspicious' → partial_price_suspect).
    `timing_belt`: the catalog says the model has a belt (None = unknown)."""
    rules = cfg.red_flags
    flags: list[RedFlag] = []
    text = normalize_text(listing.get("description"))

    if description_known(listing):
        if not _OWNERS.search(text):
            flags.append(RedFlag("no_owners", copy.RED_FLAG["no_owners"], "info"))
        if not _SERVICE.search(text):
            flags.append(RedFlag("no_service", copy.RED_FLAG["no_service"], "info"))
        if timing_belt and not _TIMING_BELT.search(text):
            flags.append(RedFlag("no_timing_belt", copy.RED_FLAG["no_timing_belt"], "info"))
        if len(text) < rules["min_description_chars"]:
            flags.append(RedFlag("short_description", copy.RED_FLAG["short_description"], "info"))

    if diff_pct is not None and diff_pct >= rules["much_cheaper_pct"]:
        key = "much_cheaper_anticipo" if diff_pct >= rules["anticipo_pct"] else "much_cheaper"
        flags.append(RedFlag("much_cheaper", copy.RED_FLAG[key].format(pct=f"{diff_pct:.0f}"), "warning"))

    km, age = listing.get("mileage_km"), _age_years(listing, now)
    if km is not None and age is not None and km / age < rules["min_km_per_year"]:
        flags.append(RedFlag("low_km_for_age", copy.RED_FLAG["low_km_for_age"].format(
            km_per_year=copy.number(km / age)), "info"))

    if guard == "suspicious" or listing.get("price_partial"):
        flags.append(RedFlag("partial_price_suspect", copy.RED_FLAG["partial_price_suspect"], "warning"))

    if listing.get("probable_repost_of"):
        flags.append(RedFlag("repost", copy.RED_FLAG["repost"], "info"))
    flags += description_mismatches(listing)
    return flags


def description_mismatches(listing: Mapping[str, Any]) -> list[RedFlag]:
    """What the description states against what the listing publishes
    (normalization/description_facts.py): another price, year or km."""
    facts = listing.get("description_facts") or {}
    out: list[RedFlag] = []
    mismatch = (facts.get("price_check") or {}).get("mismatch")
    if mismatch and mismatch.get("amount"):
        out.append(RedFlag("price_mismatch", copy.RED_FLAG["price_mismatch"].format(
            price=copy.money(mismatch["amount"], mismatch.get("currency"))), "info"))
    year, stated_year = listing.get("year"), facts.get("year")
    if year and stated_year and int(year) != int(stated_year):
        out.append(RedFlag("year_mismatch", copy.RED_FLAG["year_mismatch"].format(year=stated_year), "info"))
    km, stated_km = listing.get("mileage_km"), facts.get("mileage_km")
    if km and stated_km and abs(km - stated_km) > max(_KM_MISMATCH_MIN, _KM_MISMATCH_SHARE * max(km, stated_km)):
        out.append(RedFlag("km_mismatch", copy.RED_FLAG["km_mismatch"].format(km=copy.number(stated_km)), "info"))
    return out
