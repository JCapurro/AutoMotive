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
from normalization.description_claims import claim


@dataclass(frozen=True)
class RedFlag:
    id: str
    text: str
    severity: str        # 'info' | 'warning'
    # PAR-02 resto: the other listing of a duplicate flag, {listing_id, url,
    # source_name, kind} (kind: the pair's, for duplicate_link_clicked); left
    # out of the JSON when None.
    link: dict[str, Any] | None = None

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        if out["link"] is None:
            del out["link"]
        return out


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


def _shown_pct(diff_pct: float) -> str:
    """The percentage as the much_cheaper text prints it."""
    return f"{diff_pct:.0f}"


def _much_cheaper_text_key(diff_pct: float, rules: Mapping[str, Any]) -> str:
    """Which text the much_cheaper flag carries (PAR-02). The middle band only
    exists when much_cheaper_pct < much_cheaper_verify_pct <= anticipo_pct;
    otherwise the two original bands apply. Id and severity never change.
    The band is chosen from the percentage the text shows, so the same shown
    number always carries the same text (34.6 reads 35% and gets the 35 band)."""
    shown = float(_shown_pct(diff_pct))
    if shown >= rules["anticipo_pct"]:
        return "much_cheaper_anticipo"
    verify = rules.get("much_cheaper_verify_pct")
    coherent = verify is not None and rules["much_cheaper_pct"] < verify <= rules["anticipo_pct"]
    if coherent and shown >= verify:
        return "much_cheaper_verify"
    return "much_cheaper"


def red_flags(listing: Mapping[str, Any], *, diff_pct: float | None, guard: str | None,
              timing_belt: bool | None, cfg: IntelligenceConfig, now: datetime) -> list[RedFlag]:
    """`diff_pct`: % below the comparables' median (None without enough of them).
    `guard`: the scoring guard ('suspicious' → partial_price_suspect).
    `timing_belt`: the catalog says the model has a belt (None = unknown)."""
    rules = cfg.red_flags
    flags: list[RedFlag] = []
    text = normalize_text(listing.get("description"))
    facts = listing.get("description_facts") or {}

    if description_known(listing):
        if claim(facts, "single_owner") is not True and not _OWNERS.search(text):
            flags.append(RedFlag("no_owners", copy.RED_FLAG["no_owners"], "info"))
        if claim(facts, "service_history") is False:
            flags.append(RedFlag("service_unavailable", copy.RED_FLAG["service_unavailable"], "info"))
        elif claim(facts, "service_history") is None and not _SERVICE.search(text):
            flags.append(RedFlag("no_service", copy.RED_FLAG["no_service"], "info"))
        if claim(facts, "timing_belt_changed") is False:
            flags.append(RedFlag("timing_pending", copy.RED_FLAG["timing_pending"], "info"))
        elif timing_belt and claim(facts, "timing_belt_changed") is None and not _TIMING_BELT.search(text):
            flags.append(RedFlag("no_timing_belt", copy.RED_FLAG["no_timing_belt"], "info"))
        if len(text) < rules["min_description_chars"]:
            flags.append(RedFlag("short_description", copy.RED_FLAG["short_description"], "info"))
        for field, key in (("damage_mentioned", "damage_mentioned"), ("commercial_use", "commercial_use")):
            if claim(facts, field) is True:
                flags.append(RedFlag(key, copy.RED_FLAG[key], "info"))
        if claim(facts, "vtv_current") is False:
            flags.append(RedFlag("vtv_pending", copy.RED_FLAG["vtv_pending"], "info"))

    if diff_pct is not None and diff_pct >= rules["much_cheaper_pct"]:
        key = _much_cheaper_text_key(diff_pct, rules)
        flags.append(RedFlag("much_cheaper", copy.RED_FLAG[key].format(pct=_shown_pct(diff_pct)), "warning"))

    km, age = listing.get("mileage_km"), _age_years(listing, now)
    if km is not None and age is not None and km / age < rules["min_km_per_year"]:
        flags.append(RedFlag("low_km_for_age", copy.RED_FLAG["low_km_for_age"].format(
            km_per_year=copy.number(km / age)), "info"))

    if guard == "suspicious" or listing.get("price_partial"):
        flags.append(RedFlag("partial_price_suspect", copy.RED_FLAG["partial_price_suspect"], "warning"))

    if listing.get("probable_repost_of"):
        flags.append(RedFlag("repost", copy.RED_FLAG["repost"], "info"))
    flags += description_mismatches(listing)
    if flag := private_many_listings(listing, cfg.risk):
        flags.append(flag)
    flags += duplicate_flags(listing.get("risk_duplicates"), cfg.risk)
    return ordered(flags, cfg.flag_order)


def ordered(flags: list[RedFlag], order: tuple[str, ...]) -> list[RedFlag]:
    """By app_config.red_flags.order (PAR-02 resto, decision 8); ids it does
    not list go last, in the order they were emitted."""
    rank = {flag_id: i for i, flag_id in enumerate(order)}
    return sorted(flags, key=lambda f: rank.get(f.id, len(rank)))


def private_many_listings(listing: Mapping[str, Any], risk: Mapping[str, Any]) -> RedFlag | None:
    """The source says «particular» and F-02 infers a «posible agencia»
    (dealer_inferred: the same seller has seller_classification.min_listings or
    more cars active in the source; the job's switch clears it). Not when the
    source does not say what the seller is, nor when it says dealer."""
    if risk["signals"]["private_many_listings"] != "on":
        return None
    n = listing.get("seller_listing_count")
    if listing.get("seller_type") != "private" or not listing.get("dealer_inferred") or n is None:
        return None
    return RedFlag("private_many_listings",
                   copy.RED_FLAG["private_many_listings"].format(n=copy.number(n)), "info")


# A pair's kind → (flag id, text key, severity). A pair never yields both flags
# (pipeline/risk_duplicates.py picks one kind per pair).
_DUPLICATE_FLAG = {
    "duplicate_photos": ("duplicate_photos", "duplicate_photos", "warning"),
    "cross_source_photos": ("cross_source_duplicate", "cross_source_photos", "info"),
    "cross_source_data": ("cross_source_duplicate", "cross_source_data", "info"),
}


def duplicate_flags(pairs: Any, risk: Mapping[str, Any]) -> list[RedFlag]:
    """listing["risk_duplicates"] (db/repos/listings.rows_for_scoring: the shown
    pairs, best first) as at most one flag per id, linked to its best pair and
    «y N más» when there are more. A kind whose signal is not "on" is skipped
    here too, so turning it off works on the next re-score."""
    by_flag: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for pair in pairs or ():
        if not isinstance(pair, Mapping) or pair.get("kind") not in _DUPLICATE_FLAG:
            continue
        if risk["signals"].get(pair["kind"]) != "on":
            continue
        flag_id, text_key, _ = _DUPLICATE_FLAG[pair["kind"]]
        if text_key == "duplicate_photos" and pair.get("reason") == "other_zone":
            text_key = "duplicate_photos_zone"   # the data do not differ: say what does
        by_flag.setdefault(flag_id, []).append((text_key, pair))
    out = []
    for flag_id, found in by_flag.items():
        # The photos level first: it is the stronger evidence.
        found.sort(key=lambda kp: kp[0] != "cross_source_photos")
        text_key, best = found[0]
        name = best.get("source_name") or best.get("source") or ""
        more = len(found) - 1
        source = (copy.RED_FLAG_SOURCE["more"].format(source=name, k=more) if more
                  else copy.RED_FLAG_SOURCE["one"].format(source=name))
        link = {"listing_id": best.get("other_id"), "url": best.get("url"), "source_name": name,
                "kind": best["kind"]}
        out.append(RedFlag(flag_id, copy.RED_FLAG[text_key].format(source=source),
                           _DUPLICATE_FLAG[best["kind"]][2], link=link))
    return out


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
