"""PAR-01: the estimated total cost of buying a listing (price, DNRPA fee,
stamp tax, forms and the annual patente), as a range
(docs/superpowers/specs/2026-10-30-par01-costo-total-design.md).

No number lives here: every figure comes from app_config.cost_estimator, each
block with its source and as_of. parse_config is tolerant: a block that fails
its rule is None and the terms that need it are told as missing; there are no
numeric defaults. web/lib/cost-estimator.ts is the same calculator, written
twice on purpose; both pass tests/fixtures/cost_estimator/golden.json, so the
formulas, the order of the operations and the rounding are the same and so
are the IEEE doubles. Rounding is only floor/ceil with a fixed margin (EPS),
never round(): Python and JS round halves differently.

Pure: no network, no database, no clock (the age of a model is measured
against patente.values_year). The words are in intelligence/copy.py
(TOTAL_COST); this module returns codes.
"""
from __future__ import annotations

import math
import re
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Mapping, Sequence

from intelligence import copy
from intelligence.seller import effective_seller
from normalization.geo import haversine_km, normalize_location_query
from normalization.zone import nearest_locality

JURISDICTIONS = ("caba", "ba", "rest")
# The terms of the total, in the order of the header's "(sin …)".
TERMS = ("arancel", "sellos", "formularios", "patente")
# One cent of the currency shown: arithmetic tolerance, not a cost parameter.
EPS = 0.01
# Georef province codes (normalization/zone.py): CABA, Buenos Aires; any other is "rest".
_PROVINCE = {"02": "caba", "06": "ba"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

BLOCKS = ("review", "fx", "buyer_zone", "vf_from_price_k", "transfer_base", "mrpa_ars", "dnrpa",
          "fixed_ars.form_08", "fixed_ars.form_12", "domain_report",
          "stamp_tax_pct.caba", "stamp_tax_pct.ba", "stamp_tax_pct.rest",
          "patente.caba", "patente.ba", "patente.rest", "patente.values_year", "gestoria")


# ---------------------------------------------------------------------------
# Tolerant parser
# ---------------------------------------------------------------------------

def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _int(x: Any) -> bool:
    return _num(x) and float(x).is_integer()


def _pct(x: Any) -> bool:
    return _num(x) and 0 <= x <= 100


def _date(x: Any) -> bool:
    if not isinstance(x, str) or not _DATE.match(x):
        return False
    try:
        date.fromisoformat(x)
    except ValueError:
        return False
    return True


def _range(v: Any, pct: bool = False) -> bool:
    return (isinstance(v, dict) and _num(v.get("min")) and _num(v.get("max"))
            and 0 <= v["min"] <= v["max"] and (not pct or v["max"] <= 100))


def _brackets(b: Any) -> bool:
    if not isinstance(b, list) or not b or not all(isinstance(r, dict) for r in b):
        return False
    if not all(_num(r.get("from")) and _num(r.get("fixed")) and r["fixed"] >= 0 and _pct(r.get("pct")) for r in b):
        return False
    return b[0]["from"] == 0 and all(a["from"] < c["from"] for a, c in zip(b, b[1:]))


def _bands(b: Any) -> bool:
    if not isinstance(b, list) or not b or not all(isinstance(r, dict) and _pct(r.get("pct")) for r in b):
        return False
    if b[-1].get("vf_upto", 0) is not None:
        return False
    ups = [r.get("vf_upto") for r in b[:-1]]
    return all(_num(u) and u > 0 for u in ups) and all(a < c for a, c in zip(ups, ups[1:]))


def _caba(v: dict) -> bool:
    old = v.get("old_model_min_zero")
    types = v.get("pickup_body_types")
    return (_brackets(v.get("brackets")) and _pct(v.get("cap_pct_of_vf")) and _num(v.get("min_ars"))
            and v["min_ars"] >= 0 and _pct(v.get("pickup_flat_pct"))
            and isinstance(types, list) and all(isinstance(t, str) for t in types)
            and _range(v.get("subte_factor")) and isinstance(old, dict) and _int(old.get("age_years"))
            and old["age_years"] >= 0)


def _ba(v: dict) -> bool:
    return (_brackets(v.get("brackets")) and _range(v.get("ipc_factor")) and _pct(v.get("discount_pct"))
            and _int(v.get("min_model_year")))


def _rest(v: dict) -> bool:
    old = v.get("old_model")
    return (_pct(v.get("min_pct")) and isinstance(old, dict) and _int(old.get("max_year"))
            and _pct(old.get("min_pct")) and _bands(v.get("max_pct_bands")))


_CHECKS: dict[str, Callable[[dict], bool]] = {
    "review": lambda v: (_int(v.get("max_age_days")) and v["max_age_days"] > 0 and isinstance(v.get("months"), list)
                         and bool(v["months"]) and all(_int(m) and 1 <= m <= 12 for m in v["months"])),
    "fx": lambda v: _int(v.get("max_age_days")) and v["max_age_days"] > 0,
    "buyer_zone": lambda v: _num(v.get("max_locality_km")) and v["max_locality_km"] > 0,
    "vf_from_price_k": lambda v: (_num(v.get("min")) and _num(v.get("max"))
                                  and 0 < v["min"] <= v["max"] <= 1),
    "transfer_base": lambda v: isinstance(v.get("value"), str) and bool(v["value"].strip()),
    "mrpa_ars": _range,
    "dnrpa": lambda v: (_range(v.get("pct"), True) and _range(v.get("dealer_pct"), True)
                        and _num(v.get("min_mrpa")) and v["min_mrpa"] >= 0),
    "fixed_ars.form_08": _range,
    "fixed_ars.form_12": _range,
    "domain_report": lambda v: _num(v.get("mrpa")) and v["mrpa"] >= 0 and v.get("in_total") is False,
    "stamp_tax_pct.caba": lambda v: _range(v.get("private"), True) and _range(v.get("dealer"), True),
    "stamp_tax_pct.ba": lambda v: _range(v.get("private"), True) and _range(v.get("dealer"), True),
    "stamp_tax_pct.rest": lambda v: _range(v.get("private"), True) and _range(v.get("dealer"), True),
    "patente.caba": _caba,
    "patente.ba": _ba,
    "patente.rest": _rest,
    "gestoria": lambda v: v.get("in_total") is False and "official_value" in v and v["official_value"] is None,
}


def _get(raw: Mapping[str, Any], path: str) -> Any:
    node: Any = raw
    for key in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def _block(value: Any, check: Callable[[dict], bool]) -> dict | None:
    if not isinstance(value, dict):
        return None
    source = value.get("source")
    if not isinstance(source, str) or not source.strip() or not _date(value.get("as_of")):
        return None
    return value if check(value) else None


def parse_config(raw: Any) -> dict[str, Any] | None:
    """{as_of, blocks: {path: block | None}}; None without a valid root as_of
    (no estimate at all). Never raises, never fills a default."""
    if not isinstance(raw, dict) or not _date(raw.get("as_of")):
        return None
    blocks: dict[str, Any] = {}
    for path in BLOCKS:
        value = _get(raw, path)
        if path == "patente.values_year":
            blocks[path] = int(value) if _int(value) else None
        else:
            blocks[path] = _block(value, _CHECKS[path])
    return {"as_of": raw["as_of"], "blocks": blocks}


# ---------------------------------------------------------------------------
# The buyer's jurisdiction
# ---------------------------------------------------------------------------

def _to_num(x: Any) -> float | None:
    if isinstance(x, Decimal):
        x = float(x)
    return float(x) if _num(x) else None


def search_zones(search: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The zones of a search as {lat, lon, label}: its origin (origin_lat/lon,
    filters.location_label) and each filters.extra_locations[]. `search` is
    {lat, lon, label, extra_locations}; a search without an origin has none."""
    if not search:
        return []
    zones = []
    if search.get("lat") is not None and search.get("lon") is not None:
        zones.append({"lat": _to_num(search["lat"]), "lon": _to_num(search["lon"]), "label": search.get("label")})
    for z in search.get("extra_locations") or []:
        if isinstance(z, dict):
            zones.append({"lat": _to_num(z.get("lat")), "lon": _to_num(z.get("lon")), "label": z.get("label")})
    return zones


def buyer_jurisdiction(zones: Sequence[Mapping[str, Any]], cfg: Mapping[str, Any] | None) -> list[str] | None:
    """The set of {caba, ba, rest} the search covers, or None (missing): a zone
    without coordinates, or farther than buyer_zone.max_locality_km from the
    nearest Argentine locality, voids it. AMBA covers CABA and Buenos Aires
    (its preset stores CABA's center)."""
    if cfg is None or not zones:
        return None
    zone_cfg = cfg["blocks"]["buyer_zone"]
    if zone_cfg is None:
        return None
    out: set[str] = set()
    for z in zones:
        lat, lon = z.get("lat"), z.get("lon")
        if not _num(lat) or not _num(lon):
            return None
        if normalize_location_query(z.get("label")) == "amba":
            out |= {"caba", "ba"}
            continue
        loc = nearest_locality(lat, lon)
        if haversine_km(lat, lon, loc.lat, loc.lon) > zone_cfg["max_locality_km"]:
            return None
        out.add(_PROVINCE.get(loc.province_id, "rest"))
    return [j for j in JURISDICTIONS if j in out]


# ---------------------------------------------------------------------------
# From the listing row to the calculator's input
# ---------------------------------------------------------------------------

def _day(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if _date(value):
        return date.fromisoformat(value)
    return None


def build_input(row: Mapping[str, Any], zones: Sequence[Mapping[str, Any]], fx_latest: Mapping[str, Any] | None,
                cfg: Mapping[str, Any] | None, today: date) -> dict[str, Any] | None:
    """{listing, jurisdiction, seller, fx_latest} from a listings row, or None
    when there is nothing to estimate: no config, no price, a partial price
    (the ingest's own rule) or an unknown currency. An ARS listing's dollar is
    the one its price_usd was computed with; a USD listing's is the latest
    stored quote, only while it is at most fx.max_age_days old."""
    from pipeline.ingest import published_partial   # pipeline imports intelligence

    if cfg is None:
        return None
    price = _to_num(row.get("price"))
    if price is None or price <= 0 or published_partial(row):
        return None
    currency = row.get("currency")
    if currency not in ("ARS", "USD"):
        return None
    usd = _to_num(row.get("price_usd"))
    facts = row.get("description_facts")
    check = (facts.get("price_check") if isinstance(facts, dict) else None) or {}
    year = row.get("year")
    listing = {"price": price, "currency": currency,
               "fx_rate": price / usd if currency == "ARS" and usd and usd > 0 else None,
               "cash": isinstance(check, dict) and check.get("effective_kind") == "cash",
               "year": int(year) if _int(year) else None, "body_type": row.get("body_type") or None}
    fx = None
    fx_cfg = cfg["blocks"]["fx"]
    if currency == "USD" and fx_latest and fx_cfg:
        rate, day = _to_num(fx_latest.get("rate")), _day(fx_latest.get("date"))
        if rate and rate > 0 and day and (today - day).days <= fx_cfg["max_age_days"]:
            fx = {"rate": rate, "kind": fx_latest.get("kind"), "date": day.isoformat()}
    return {"listing": listing, "jurisdiction": buyer_jurisdiction(zones, cfg),
            "seller": effective_seller(row), "fx_latest": fx}


# ---------------------------------------------------------------------------
# The calculator
# ---------------------------------------------------------------------------

def _seller_range(block: Mapping[str, Any], seller: str | None, private: str, dealer: str) -> tuple[float, float]:
    """The pair for the seller; without one, the union of both."""
    pairs = [block[private]] if seller == "private" else [block[dealer]] if seller == "dealer" \
        else [block[private], block[dealer]]
    return min(p["min"] for p in pairs), max(p["max"] for p in pairs)


def _scale(brackets: Sequence[Mapping[str, Any]], vf: float) -> float:
    row = [r for r in brackets if r["from"] <= vf][-1]
    return row["fixed"] + (vf - row["from"]) * row["pct"] / 100


Result = tuple  # ("ok", min, max, blocks) | ("missing", reason)


def _arancel(p: float, seller: str | None, b: Mapping[str, Any]) -> Result:
    dnrpa, mrpa, base = b["dnrpa"], b["mrpa_ars"], b["transfer_base"]
    if dnrpa is None or mrpa is None or base is None:
        return ("missing", "params")
    if base["value"] != "price":
        return ("missing", "base")
    lo, hi = _seller_range(dnrpa, seller, "pct", "dealer_pct")
    return ("ok", max(p * lo / 100, dnrpa["min_mrpa"] * mrpa["min"]),
            max(p * hi / 100, dnrpa["min_mrpa"] * mrpa["max"]), ["dnrpa", "mrpa_ars", "transfer_base"])


def _sellos(p: float, jurisdiction: Sequence[str] | None, seller: str | None, b: Mapping[str, Any]) -> Result:
    base = b["transfer_base"]
    if base is None:
        return ("missing", "params")
    if base["value"] != "price":
        return ("missing", "base")
    if not jurisdiction:
        return ("missing", "no_zone")
    names = [f"stamp_tax_pct.{j}" for j in jurisdiction]
    if any(b[n] is None for n in names):
        return ("missing", "params")
    ranges = [_seller_range(b[n], seller, "private", "dealer") for n in names]
    return ("ok", min(p * lo / 100 for lo, _ in ranges), max(p * hi / 100 for _, hi in ranges), names)


def _formularios(b: Mapping[str, Any]) -> Result:
    f08, f12 = b["fixed_ars.form_08"], b["fixed_ars.form_12"]
    if f08 is None or f12 is None:
        return ("missing", "params")
    return ("ok", f08["min"] + f12["min"], f08["max"] + f12["max"], ["fixed_ars.form_08", "fixed_ars.form_12"])


def _patente_caba(c: Mapping[str, Any], vf_lo: float, vf_hi: float, year: int, values_year: int,
                  body_type: str | None) -> tuple[float, float]:
    # Inciso a) the scale with its cap; b) the pick-up's flat rate. No body
    # type: the union of both. The minimum and the Subte factor apply to both.
    incisos = ["b"] if body_type in c["pickup_body_types"] else ["a", "b"] if body_type is None else ["a"]
    floor_ = 0 if year <= values_year - c["old_model_min_zero"]["age_years"] else c["min_ars"]

    def t(vf: float, inciso: str, factor: float) -> float:
        base = (min(_scale(c["brackets"], vf), vf * c["cap_pct_of_vf"] / 100) if inciso == "a"
                else vf * c["pickup_flat_pct"] / 100)
        return max(base, floor_) * factor

    return (min(t(vf_lo, i, c["subte_factor"]["min"]) for i in incisos),
            max(t(vf_hi, i, c["subte_factor"]["max"]) for i in incisos))


def _patente_ba(c: Mapping[str, Any], vf_lo: float, vf_hi: float) -> tuple[float, float]:
    return (_scale(c["brackets"], vf_lo) * c["ipc_factor"]["min"] * (100 - c["discount_pct"]) / 100,
            _scale(c["brackets"], vf_hi) * c["ipc_factor"]["max"] * (100 - c["discount_pct"]) / 100)


def _patente_rest(c: Mapping[str, Any], vf_lo: float, vf_hi: float, year: int) -> tuple[float, float]:
    old = c["old_model"]
    lo_pct = old["min_pct"] if year <= old["max_year"] else c["min_pct"]
    band = next(r for r in c["max_pct_bands"] if r["vf_upto"] is None or vf_hi <= r["vf_upto"])
    return vf_lo * lo_pct / 100, vf_hi * band["pct"] / 100


def _patente(p: float, listing: Mapping[str, Any], jurisdiction: Sequence[str] | None,
             b: Mapping[str, Any]) -> Result:
    k, values_year = b["vf_from_price_k"], b["patente.values_year"]
    if k is None or values_year is None:
        return ("missing", "params")
    if not jurisdiction:
        return ("missing", "no_zone")
    year = listing.get("year")
    if year is None:
        return ("missing", "no_year")
    names = [f"patente.{j}" for j in jurisdiction]
    if any(b[n] is None for n in names):
        return ("missing", "params")
    vf_lo, vf_hi = p * k["min"], p * k["max"]
    ranges = []
    for j, n in zip(jurisdiction, names):
        c = b[n]
        if j == "caba":
            ranges.append(_patente_caba(c, vf_lo, vf_hi, year, values_year, listing.get("body_type")))
        elif j == "ba":
            if year < c["min_model_year"]:
                return ("missing", "pre_min_year")
            ranges.append(_patente_ba(c, vf_lo, vf_hi))
        else:
            ranges.append(_patente_rest(c, vf_lo, vf_hi, year))
    return ("ok", min(lo for lo, _ in ranges), max(hi for _, hi in ranges), ["vf_from_price_k", *names])


def estimate(listing: Mapping[str, Any], jurisdiction: Sequence[str] | None, seller: str | None,
             fx_latest: Mapping[str, Any] | None, cfg: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The estimate, or None without a config (no root as_of) or a price. A USD
    listing without a dollar gets an empty estimate (missing fx): the scales
    are in pesos, nothing can be computed."""
    if cfg is None:
        return None
    price = _to_num(listing.get("price"))
    currency = listing.get("currency")
    if price is None or price <= 0 or currency not in ("ARS", "USD"):
        return None
    b = cfg["blocks"]
    out: dict[str, Any] = {"p_orig": {"amount": price, "currency": currency},
                           "price_label": "cash" if listing.get("cash") else "published",
                           "jurisdiction": list(jurisdiction) if jurisdiction else None, "seller": seller,
                           "as_of": cfg["as_of"]}
    if currency == "USD":
        rate = _to_num((fx_latest or {}).get("rate"))
        if not rate or rate <= 0:
            return {**out, "p_ars": None, "rate": None, "terms": [], "extras": [],
                    "missing": [{"code": "fx", "reason": "no_fx"}], "total_ars": None, "total_usd": None}
        p = price * rate
        rate_info = {"value": rate, "kind": fx_latest.get("kind"), "date": fx_latest.get("date")}
    else:
        p = price
        r = _to_num(listing.get("fx_rate"))
        rate_info = {"value": r, "kind": "listing", "date": None} if r and r > 0 else None
    terms: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    results = {"arancel": _arancel(p, seller, b), "sellos": _sellos(p, jurisdiction, seller, b),
               "formularios": _formularios(b), "patente": _patente(p, listing, jurisdiction, b)}
    for code in TERMS:
        res = results[code]
        if res[0] == "ok":
            terms.append({"code": code, "min": res[1], "max": res[2], "blocks": res[3]})
        else:
            missing.append({"code": code, "reason": res[1]})
    extras = []
    if b["domain_report"] is not None and b["mrpa_ars"] is not None:
        n = b["domain_report"]["mrpa"]
        extras.append({"code": "domain_report", "min": n * b["mrpa_ars"]["min"], "max": n * b["mrpa_ars"]["max"],
                       "blocks": ["domain_report", "mrpa_ars"]})
    if b["gestoria"] is not None:
        extras.append({"code": "gestoria", "min": None, "max": None, "blocks": ["gestoria"]})
    lo, hi = p, p
    for t in terms:
        lo += t["min"]
        hi += t["max"]
    total_usd = None
    if rate_info:
        total_usd = {"min": lo / rate_info["value"], "max": hi / rate_info["value"]}
    else:
        missing.append({"code": "fx", "reason": "no_fx"})
    return {**out, "p_ars": p, "rate": rate_info, "terms": terms, "extras": extras, "missing": missing,
            "total_ars": {"min": lo, "max": hi}, "total_usd": total_usd}


# ---------------------------------------------------------------------------
# Showing it: outward rounding, thousands by hand, the header
# ---------------------------------------------------------------------------

def floor_to(x: float, step: int) -> int:
    return step * math.floor((x + EPS) / step)


def ceil_to(x: float, step: int) -> int:
    return step * math.ceil((x - EPS) / step)


def thousands(n: int) -> str:
    """16290 -> "16.290", built by hand like the web (no locale)."""
    digits = str(int(n))
    groups = []
    while len(digits) > 3:
        groups.insert(0, digits[-3:])
        digits = digits[:-3]
    return ".".join([digits, *groups])


def format_range(lo: int, hi: int, currency: str) -> str:
    if lo == hi:
        return f"{currency} {thousands(lo)}"
    return f"{currency} {thousands(lo)} – {thousands(hi)}"


def term_amount(term: Mapping[str, Any]) -> str:
    """A detail line: rounded outward to $100."""
    return format_range(floor_to(term["min"], 100), ceil_to(term["max"], 100), "ARS")


def rounded(est: Mapping[str, Any]) -> dict[str, Any]:
    """The totals as shown: ARS to $1.000, USD to 10, outward."""
    ars, usd = est.get("total_ars"), est.get("total_usd")
    return {"ars": {"min": floor_to(ars["min"], 1000), "max": ceil_to(ars["max"], 1000)} if ars else None,
            "usd": {"min": floor_to(usd["min"], 10), "max": ceil_to(usd["max"], 10)} if usd else None}


def missing_suffix(codes: Sequence[str]) -> str:
    """" (sin patente)", " (sin sellos ni patente)", " (sin arancel, sellos ni
    patente)": the missing terms in TERMS' order; fx never goes here."""
    names = [copy.TOTAL_COST["names"][c] for c in TERMS if c in codes]
    if not names:
        return ""
    items = names[0] if len(names) == 1 else ", ".join(names[:-1]) + copy.TOTAL_COST["last"] + names[-1]
    return copy.TOTAL_COST["suffix"].format(items=items)


def headline(ars: Mapping[str, int] | None, usd: Mapping[str, int] | None, codes: Sequence[str]) -> str:
    """The header from already rounded totals (the email keeps those)."""
    if ars is None:
        return copy.TOTAL_COST["line_no_fx"]
    suffix = missing_suffix(codes)
    ars_text = format_range(ars["min"], ars["max"], "ARS")
    if usd is None:
        return copy.TOTAL_COST["line_no_usd"].format(suffix=suffix, ars=ars_text)
    return copy.TOTAL_COST["line"].format(suffix=suffix, usd=format_range(usd["min"], usd["max"], "USD"), ars=ars_text)


def format_line(est: Mapping[str, Any]) -> str:
    r = rounded(est)
    return headline(r["ars"], r["usd"], [m["code"] for m in est["missing"]])


def day_month(iso: str) -> str:
    """"2026-10-30" -> "30/10", without a time zone."""
    return f"{iso[8:10]}/{iso[5:7]}"


def email_payload(est: Mapping[str, Any]) -> dict[str, Any]:
    """What an alert keeps (notifications.payload['total_cost']): the rounded
    totals, frozen when the row is created."""
    r = rounded(est)
    return {"ars_min": r["ars"]["min"] if r["ars"] else None, "ars_max": r["ars"]["max"] if r["ars"] else None,
            "usd_min": r["usd"]["min"] if r["usd"] else None, "usd_max": r["usd"]["max"] if r["usd"] else None,
            "missing": [m["code"] for m in est["missing"]], "jurisdiction": est.get("jurisdiction"),
            "as_of": est.get("as_of")}


# ---------------------------------------------------------------------------
# /admin: when the parameters need a review
# ---------------------------------------------------------------------------

def review_status(cfg: Mapping[str, Any] | None, today: date) -> str | None:
    """'stale' (older than review.max_age_days), 'due' (a review month, and
    as_of before the current window of consecutive review months, across the
    year end), 'missing' (no review block or config) or None."""
    review = cfg["blocks"]["review"] if cfg else None
    if not review:
        return "missing"
    as_of = date.fromisoformat(cfg["as_of"])
    if (today - as_of).days > review["max_age_days"]:
        return "stale"
    months = set(int(m) for m in review["months"])
    if today.month not in months:
        return None
    year, month = today.year, today.month
    for _ in range(11):
        prev = 12 if month == 1 else month - 1
        if prev not in months:
            break
        if month == 1:
            year -= 1
        month = prev
    return "due" if as_of < date(year, month, 1) else None
