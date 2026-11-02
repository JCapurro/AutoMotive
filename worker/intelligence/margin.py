"""PRO-02: the estimated gross margin of a match against the median price at
which dealers publish the model (docs/superpowers/specs/2026-11-02-pro02-margen-design.md).

    asking_usd          = listings.price_usd (the effective price)
    reconditioning_usd  = max(asking_usd x pct / 100, min_usd)             (app_config.dealer_margin)
    transfer_usd        = (arancel + sellos + formularios) / dollar        (PAR-01, intelligence/cost_estimator.py)
    est_costs_usd       = reconditioning_usd + transfer_usd
    acquisition_usd     = asking_usd + est_costs_usd                       (what buying the car costs)
    gross_margin_usd    = dealer_median - acquisition_usd                  (min uses the max costs)
    gross_margin_pct    = gross_margin_usd / acquisition_usd x 100         (min: margin min / cost max)

Every amount is a range {min, max}. dealer_median is price_ref's (F-02 paso
3, the same pool and level as the median). With fewer dealers than
comparables.min_n the margin is only {status: "few_dealers", dealer_n,
min_n} (Juan, 02/11: say why there is no margin); it is None when price_ref
predates the seller split, for a partial price or without price_usd (the
price is what is missing there, and the card already shows it).

An implausible price has no margin either (None, no line and no note, as a
partial price): asking_usd above plausible_ratio.max x dealer_median (an ARS
price loaded as USD: a VW Bora «USD 600.000» against a median of USD 8.038)
or below plausible_ratio.min x dealer_median (a down payment or installment
the description did not reveal). The bounds are inclusive and come from
app_config.dealer_margin.plausible_ratio, {min: 0.4, max: 3} by default
(PLAUSIBLE_RATIO); the ref stores the bounds it passed. A status would say
something the Pro cannot act on and would still look like a number about the
car; None keeps the rule "no simulated numbers" (Juan). The stored refs from
before the guard are hidden by plausible() (here and in web/lib/margin-view.ts)
and recomputed by rescore_queue (db/repos/matches.py IMPLAUSIBLE_MARGIN).

The transfer is all or nothing and never borrowed from another zone: without
the search's jurisdiction (or the dollar, or the parameters) it is not
subtracted and `transfer.status` says why; the copy tells it. Only CABA and
Buenos Aires have official values loaded: a search elsewhere ("rest") does
not subtract it (no_official), and neither does a search whose zones mix
them with another province (no_official_some; Juan, 02/11). The patente is
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
TRANSFER_STATUS = ("ok", "no_zone", "no_official", "no_official_some", "no_fx", "params", "base", "no_price",
                   "disabled")
# Jurisdictions with official transfer values (PAR-01's "rest" is a range
# built from Córdoba, Santa Fe and Mendoza: not used for the margin).
OFFICIAL_JURISDICTIONS = ("caba", "ba")
# margin_ref.status: a margin, or not enough dealers to estimate one.
OK, FEW_DEALERS = "ok", "few_dealers"
# asking_usd / dealer_median outside [min, max]: no margin (app_config.dealer_margin.plausible_ratio).
PLAUSIBLE_RATIO = {"min": 0.4, "max": 3.0}
# The comparison's slack in USD: the stored amounts are rounded to cents.
PLAUSIBLE_EPS = 0.01


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

def parse_ratio(raw: Any) -> dict[str, float]:
    """plausible_ratio {min, max} with 0 < min < 1 < max, else PLAUSIBLE_RATIO."""
    if isinstance(raw, Mapping):
        lo, hi = _num(raw.get("min")), _num(raw.get("max"))
        if lo is not None and hi is not None and 0 < lo < 1 < hi:
            return {"min": lo, "max": hi}
    return dict(PLAUSIBLE_RATIO)


def parse_config(raw: Any) -> dict[str, Any]:
    """{as_of, reconditioning: {pct, min_usd} | None, transfer: bool,
    plausible_ratio: {min, max}}. Tolerant and without numeric defaults for
    the costs: an invalid or missing reconditioning block is None (the margin
    says it subtracts no reconditioning); the transfer is subtracted only with
    transfer.enabled = true. plausible_ratio does default (PLAUSIBLE_RATIO):
    a missing guard would show absurd margins, not omit a cost."""
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
            "transfer": isinstance(transfer, dict) and transfer.get("enabled") is True,
            "plausible_ratio": parse_ratio(raw.get("plausible_ratio"))}


def plausible_price(asking: float, median: float, ratio: Mapping[str, Any] | None = None) -> bool:
    """min x median <= asking <= max x median (inclusive, with PLAUSIBLE_EPS)."""
    r = parse_ratio(ratio)
    return r["min"] * median - PLAUSIBLE_EPS <= asking <= r["max"] * median + PLAUSIBLE_EPS


def plausible(ref: Mapping[str, Any] | None) -> bool:
    """A stored margin (status ok) whose price is plausible against its own
    median, with its own bounds or, for the refs from before the guard,
    PLAUSIBLE_RATIO. Not a margin (few_dealers, None, an unknown shape): False."""
    if not isinstance(ref, Mapping) or ref.get("status", OK) != OK:
        return False
    asking, median = _num(ref.get("asking_usd")), _num(ref.get("dealer_median"))
    if asking is None or median is None or median <= 0:
        return False
    return plausible_price(asking, median, ref.get("plausible_ratio"))


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
    unofficial = [j for j in built["jurisdiction"] if j not in OFFICIAL_JURISDICTIONS]
    if unofficial:
        return {**out, "status": "no_official" if len(unofficial) == len(built["jurisdiction"]) else "no_official_some"}
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

    if price_ref is None or price_ref.dealer_n is None:
        return None
    if published_partial(dict(row)):
        return None
    asking = _num(row.get("price_usd"))
    if asking is None or asking <= 0:
        return None
    if price_ref.dealer_n < min_n:
        return {"v": VERSION, "status": FEW_DEALERS, "dealer_n": int(price_ref.dealer_n), "min_n": int(min_n),
                "n": int(price_ref.n), "level_used": price_ref.level_used}
    median = _num(price_ref.dealer_median)
    if median is None or median <= 0:
        return None
    dealer_cfg = dealer_cfg if dealer_cfg is not None else parse_config(None)
    # Compared as stored (cents), so the web and rescore_queue's SQL agree.
    ratio = parse_ratio(dealer_cfg.get("plausible_ratio"))
    if not plausible_price(_r2(asking), _r2(median), ratio):
        return None

    rec_cfg = dealer_cfg.get("reconditioning")
    reconditioning = None
    if rec_cfg:
        reconditioning = {"pct": rec_cfg["pct"], "min_usd": rec_cfg["min_usd"],
                          "usd": _r2(max(asking * rec_cfg["pct"] / 100, rec_cfg["min_usd"]))}
    transfer = _transfer(row, zones, dealer_cfg, cost_cfg, fx_latest, today)

    rec_usd = reconditioning["usd"] if reconditioning else 0.0
    t = transfer["usd"] or {"min": 0.0, "max": 0.0}
    costs = (rec_usd + t["min"], rec_usd + t["max"])
    acquisition = (asking + costs[0], asking + costs[1])
    gross = (median - acquisition[1], median - acquisition[0])
    as_of = {"dealer_margin": dealer_cfg.get("as_of")}
    if transfer.get("as_of"):
        as_of["cost_estimator"] = transfer.pop("as_of")
    fx = transfer.pop("fx", None)
    return {
        "v": VERSION,
        "status": OK,
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
        "acquisition_usd": _range(*acquisition),
        "gross_margin_usd": _range(*gross),
        # On what buying the car costs (Juan, 02/11). The margin falls as the
        # cost rises, so the low end pairs the margin's min with the cost's max.
        "gross_margin_pct": _range(gross[0] / acquisition[1] * 100, gross[1] / acquisition[0] * 100),
        "plausible_ratio": ratio,
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
    USD 500 threshold (the low end, conservative). None for an implausible
    price (plausible): it never reaches the threshold."""
    if not plausible(ref):
        return None
    g = ref.get("gross_margin_usd") if isinstance(ref, Mapping) else None
    low = _num(g.get("min")) if isinstance(g, Mapping) else None
    return _r2(low) if low is not None else None


def few_dealers(ref: Mapping[str, Any] | None) -> bool:
    """A margin_ref that says there are not enough dealers to estimate one."""
    return (isinstance(ref, Mapping) and ref.get("status") == FEW_DEALERS
            and all(isinstance(ref.get(k), int) and not isinstance(ref.get(k), bool) for k in ("dealer_n", "min_n")))


def email_payload(ref: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """What an alert keeps (notifications.payload['margin']): the margin
    rounded outward to USD 10 and the words' inputs, frozen when the row is
    created, or {status: few_dealers, dealer_n, min_n}. The USD threshold
    compares threshold_low, not usd_min."""
    if few_dealers(ref):
        return {"status": FEW_DEALERS, "dealer_n": ref["dealer_n"], "min_n": ref["min_n"]}
    if not ref or not isinstance(ref.get("gross_margin_usd"), dict) or not plausible(ref):
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
    pct_lo, pct_hi = _num(p.get("min")), _num(p.get("max"))
    if pct_lo is None or pct_hi is None:
        pct_lo = pct_hi = None
    elif abs(pct_hi - pct_lo) < cost_estimator.EPS:
        pct_lo = pct_hi = math.floor(pct_lo + 0.5)    # one number: the nearest whole %, not a range
    else:
        pct_lo, pct_hi = math.floor(pct_lo + cost_estimator.EPS), math.ceil(pct_hi - cost_estimator.EPS)
    return {"status": OK, "usd_min": lo, "usd_max": hi, "pct_min": pct_lo, "pct_max": pct_hi,
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
    if p.get("status") == FEW_DEALERS:
        return copy.MARGIN["few_dealers"].format(n=p["dealer_n"], min_n=p["min_n"])
    return copy.MARGIN["line"].format(
        usd=usd_text(p["usd_min"], p["usd_max"]), median=copy.MARGIN["single"].format(v=signed(p["dealer_median"])),
        n=p.get("dealer_n"), costs=costs_text(p.get("reconditioning_pct"), p.get("transfer_status")))


def line(ref: Mapping[str, Any] | None) -> str | None:
    p = email_payload(ref)
    return headline(p) if p else None
