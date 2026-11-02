"""PRO-02: the estimated gross margin of a match against the median price at
which dealers publish the model (docs/superpowers/specs/2026-11-02-pro02-margen-design.md).

    asking_usd          = listings.price_usd (the effective price)
    reconditioning_usd  = max(asking_usd x pct / 100, min_usd)             (app_config.dealer_margin)
    transfer_usd        = (arancel + sellos + formularios) / dollar        (PAR-01, intelligence/cost_estimator.py)
    est_costs_usd       = reconditioning_usd + transfer_usd
    gross_margin_usd    = dealer_median - asking_usd - est_costs_usd       (min uses the max costs)
    gross_margin_pct    = gross_margin_usd / dealer_median x 100

Every amount is a range {min, max}. dealer_median is price_ref's (F-02 paso
3, the same pool and level as the median); the margin is None when dealer_n
< comparables.min_n, when price_ref predates the seller split, for a partial
price or without price_usd.

The transfer is all or nothing and never borrowed from another zone: without
the search's jurisdiction (or the dollar, or the parameters) it is not
subtracted and `transfer.status` says why; the copy tells it. The patente is
annual, not part of the transfer: it is never subtracted.

Pure: no network, no database, no clock. The words are in intelligence/copy.py
(MARGIN); web/lib/margin-view.ts formats the same stored shape.
"""
from __future__ import annotations

import math
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Sequence

from intelligence import copy
from intelligence import cost_estimator
from intelligence.comparables import PriceRef

VERSION = 1
# The PAR-01 terms the transfer is made of.
TRANSFER_TERMS = ("arancel", "sellos", "formularios")
TRANSFER_STATUS = ("ok", "no_zone", "no_fx", "params", "base", "no_price", "disabled")


def _num(x: Any) -> float | None:
    if isinstance(x, Decimal):
        x = float(x)
    if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x):
        return float(x)
    return None


def _r2(x: float) -> float:
    return round(x, 2)


def _range(lo: float, hi: float) -> dict[str, float]:
    return {"min": _r2(lo), "max": _r2(hi)}


# ---------------------------------------------------------------------------
# app_config.dealer_margin
# ---------------------------------------------------------------------------

def parse_config(raw: Any) -> dict[str, Any]:
    """{as_of, reconditioning: {pct, min_usd} | None, transfer: bool}. Tolerant
    and without numeric defaults: an invalid or missing reconditioning block is
    None (the margin says it subtracts no reconditioning); the transfer is
    subtracted only with transfer.enabled = true."""
    raw = raw if isinstance(raw, dict) else {}
    as_of = raw.get("as_of") if cost_estimator._date(raw.get("as_of")) else None
    rec = raw.get("reconditioning")
    reconditioning = None
    if isinstance(rec, dict):
        pct, min_usd = _num(rec.get("pct")), _num(rec.get("min_usd"))
        if pct is not None and 0 <= pct <= 100 and min_usd is not None and min_usd >= 0:
            reconditioning = {"pct": pct, "min_usd": min_usd}
    transfer = raw.get("transfer")
    return {"as_of": as_of, "reconditioning": reconditioning,
            "transfer": isinstance(transfer, dict) and transfer.get("enabled") is True}


# ---------------------------------------------------------------------------
# The calculation
# ---------------------------------------------------------------------------

def _price_label(row: Mapping[str, Any]) -> str:
    facts = row.get("description_facts")
    check = (facts.get("price_check") if isinstance(facts, dict) else None) or {}
    return "cash" if isinstance(check, dict) and check.get("effective_kind") == "cash" else "published"


def _transfer(row: Mapping[str, Any], zones: Sequence[Mapping[str, Any]], dealer_cfg: Mapping[str, Any],
              cost_cfg: Mapping[str, Any] | None, fx_latest: Mapping[str, Any] | None,
              today: date) -> dict[str, Any]:
    out: dict[str, Any] = {"status": "disabled", "usd": None, "terms": list(TRANSFER_TERMS),
                           "jurisdiction": None, "seller": None}
    if not dealer_cfg.get("transfer"):
        return out
    if cost_cfg is None:
        return {**out, "status": "params"}
    built = cost_estimator.build_input(row, zones, fx_latest, cost_cfg, today)
    if built is None:
        return {**out, "status": "no_price"}
    out.update(jurisdiction=built["jurisdiction"], seller=built["seller"])
    if not built["jurisdiction"]:
        return {**out, "status": "no_zone"}
    est = cost_estimator.estimate(built["listing"], built["jurisdiction"], built["seller"], built["fx_latest"], cost_cfg)
    if est is None:
        return {**out, "status": "no_price"}
    rate = (est.get("rate") or {}).get("value")
    if not rate:
        return {**out, "status": "no_fx"}
    missing = {m["code"]: m["reason"] for m in est["missing"]}
    for code in TRANSFER_TERMS:
        if code in missing:
            reason = missing[code]
            return {**out, "status": reason if reason in TRANSFER_STATUS else "params"}
    terms = [t for t in est["terms"] if t["code"] in TRANSFER_TERMS]
    lo = sum(t["min"] for t in terms) / rate
    hi = sum(t["max"] for t in terms) / rate
    out.update(status="ok", usd=_range(lo, hi),
               fx={"rate": round(rate, 4), "kind": est["rate"].get("kind"), "date": est["rate"].get("date")},
               as_of=cost_cfg["as_of"])
    return out


def compute(row: Mapping[str, Any], price_ref: PriceRef | None, zones: Sequence[Mapping[str, Any]],
            dealer_cfg: Mapping[str, Any] | None, cost_cfg: Mapping[str, Any] | None,
            fx_latest: Mapping[str, Any] | None, min_n: int, today: date) -> dict[str, Any] | None:
    """matches.margin_ref for a listing row (rows_for_scoring) and its
    price_ref, with the zones of the match's search (cost_estimator.search_zones).
    `cost_cfg` is cost_estimator.parse_config's; `fx_latest` the latest stored
    quote (USD listings only)."""
    from pipeline.ingest import published_partial   # pipeline imports intelligence

    if price_ref is None or price_ref.dealer_n is None or price_ref.dealer_n < min_n:
        return None
    median = _num(price_ref.dealer_median)
    if median is None or median <= 0:
        return None
    if published_partial(dict(row)):
        return None
    asking = _num(row.get("price_usd"))
    if asking is None or asking <= 0:
        return None
    dealer_cfg = dealer_cfg if dealer_cfg is not None else parse_config(None)

    rec_cfg = dealer_cfg.get("reconditioning")
    reconditioning = None
    if rec_cfg:
        reconditioning = {"pct": rec_cfg["pct"], "min_usd": rec_cfg["min_usd"],
                          "usd": _r2(max(asking * rec_cfg["pct"] / 100, rec_cfg["min_usd"]))}
    transfer = _transfer(row, zones, dealer_cfg, cost_cfg, fx_latest, today)

    rec_usd = reconditioning["usd"] if reconditioning else 0.0
    t = transfer["usd"] or {"min": 0.0, "max": 0.0}
    costs = (rec_usd + t["min"], rec_usd + t["max"])
    gross = (median - asking - costs[1], median - asking - costs[0])
    as_of = {"dealer_margin": dealer_cfg.get("as_of")}
    if transfer.get("as_of"):
        as_of["cost_estimator"] = transfer.pop("as_of")
    fx = transfer.pop("fx", None)
    return {
        "v": VERSION,
        "dealer_median": _r2(median),
        "dealer_n": int(price_ref.dealer_n),
        "n": int(price_ref.n),
        "level_used": price_ref.level_used,
        "asking_usd": _r2(asking),
        "price_label": _price_label(row),
        "currency": row.get("currency"),
        "fx": fx,
        "reconditioning": reconditioning,
        "transfer": transfer,
        "est_costs_usd": _range(*costs),
        "gross_margin_usd": _range(*gross),
        "gross_margin_pct": _range(gross[0] / median * 100, gross[1] / median * 100),
        "as_of": as_of,
    }


# ---------------------------------------------------------------------------
# Showing it: outward rounding, the line
# ---------------------------------------------------------------------------

def signed(n: int) -> str:
    """-300 -> "-300", 1400 -> "1.400" (cost_estimator.thousands has no sign)."""
    return ("-" if n < 0 else "") + cost_estimator.thousands(abs(int(n)))


def round10(x: float) -> int:
    """The median shown, to the nearest 10 (floor(x/10 + 0.5), the same in JS)."""
    return 10 * math.floor(x / 10 + 0.5)


def pct_text(pct: float) -> str:
    """5 -> "5", 5.5 -> "5,5"."""
    return str(int(pct)) if float(pct).is_integer() else f"{pct:.2f}".rstrip("0").replace(".", ",")


def threshold_low(ref: Mapping[str, Any] | None) -> float | None:
    """What the USD threshold compares: the estimated margin's low end as
    computed, never the shown number. email_payload rounds a single value to
    the nearest 10, so a USD 495 margin shows as USD 500 but must not reach a
    USD 500 threshold (the low end, conservative)."""
    g = ref.get("gross_margin_usd") if isinstance(ref, Mapping) else None
    low = _num(g.get("min")) if isinstance(g, Mapping) else None
    return _r2(low) if low is not None else None


def email_payload(ref: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """What an alert keeps (notifications.payload['margin']): the margin
    rounded outward to USD 10 and the words' inputs, frozen when the row is
    created. The USD threshold compares threshold_low, not usd_min."""
    if not ref or not isinstance(ref.get("gross_margin_usd"), dict):
        return None
    g, p = ref["gross_margin_usd"], ref.get("gross_margin_pct") or {}
    rec = ref.get("reconditioning")
    transfer = ref.get("transfer") or {}
    as_of = ref.get("as_of") or {}
    dates = sorted(d for d in (as_of.get("dealer_margin"), as_of.get("cost_estimator")) if isinstance(d, str))
    if abs(g["max"] - g["min"]) < cost_estimator.EPS:
        lo = hi = round10(g["min"])            # one number: to the nearest 10, not a range
    else:
        lo, hi = cost_estimator.floor_to(g["min"], 10), cost_estimator.ceil_to(g["max"], 10)
    return {"usd_min": lo, "usd_max": hi,
            "pct_min": math.floor(p["min"] + cost_estimator.EPS) if _num(p.get("min")) is not None else None,
            "pct_max": math.ceil(p["max"] - cost_estimator.EPS) if _num(p.get("max")) is not None else None,
            "dealer_median": round10(ref["dealer_median"]), "dealer_n": ref.get("dealer_n"),
            "reconditioning_pct": rec.get("pct") if isinstance(rec, dict) else None,
            "transfer_status": transfer.get("status"), "jurisdiction": transfer.get("jurisdiction"),
            "as_of": dates[0] if dates else None}


def costs_text(reconditioning_pct: float | None, transfer_status: str | None) -> str:
    why = copy.MARGIN["why"].get(transfer_status or "", copy.MARGIN["why"]["params"])
    if reconditioning_pct is not None:
        if transfer_status == "ok":
            return copy.MARGIN["costs_both"].format(pct=pct_text(reconditioning_pct))
        return copy.MARGIN["costs_no_transfer"].format(pct=pct_text(reconditioning_pct), why=why)
    if transfer_status == "ok":
        return copy.MARGIN["costs_no_reconditioning"]
    return copy.MARGIN["costs_none"].format(why=why)


def usd_text(lo: int, hi: int) -> str:
    if lo == hi:
        return copy.MARGIN["single"].format(v=signed(lo))
    return copy.MARGIN["range"].format(lo=signed(lo), hi=signed(hi))


def headline(p: Mapping[str, Any]) -> str:
    """The line from email_payload's rounded numbers (cards, the listing page and alerts say the same)."""
    return copy.MARGIN["line"].format(
        usd=usd_text(p["usd_min"], p["usd_max"]), median=copy.MARGIN["single"].format(v=signed(p["dealer_median"])),
        n=p.get("dealer_n"), costs=costs_text(p.get("reconditioning_pct"), p.get("transfer_status")))


def line(ref: Mapping[str, Any] | None) -> str | None:
    p = email_payload(ref)
    return headline(p) if p else None
