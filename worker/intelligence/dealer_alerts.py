"""Agencias, fase 1: which alerts a dealer gets for one of its cars. Pure.

The input is a row of public.dealer_alert_scan() (one car on sale) and its
saved reference (dealer_alert_state, inside the row as "state"). The output is
the alerts to queue and the new reference. Four kinds, each told once:

* market_moved   the market median (same method as the panel) moved at least
                 MARKET_MOVE_PCT % since we last told the dealer (or first saw
                 it), both readings with enough comparables. The reference
                 moves only when we tell it, so a slow drift adds up.
* cheaper_nearby a look-alike first seen since the last scan, at least
                 CHEAPER_PCT % cheaper, within CHEAPER_RADIUS_KM (SQL does the
                 search: dealer_alert_scan's parameters). One per car and scan.
* slow           days in stock above SLOW_FACTOR x what the model takes to sell
                 (the panel's «Tardan más que su modelo»), or SLOW_DAYS_FALLBACK
                 days when we don't know the model. Once per car.
* new_demand     the searches that accept the car in the dealer's zone grew by
                 at least demand_min_count people since the high-water mark
                 (privacy, C2: never fewer than 3 people; only an approved
                 dealer gets demand at all, the SQL leaves it null otherwise).
                 The mark moves only when we tell, so searches that come and
                 go never repeat the alert.

The first scan of a car only records the reference (no market or demand alert:
there is nothing to compare with yet).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

MARKET_MOVE_PCT = 10.0
CHEAPER_PCT = 8.0
CHEAPER_RADIUS_KM = 30.0
SLOW_FACTOR = 1.5
SLOW_DAYS_FALLBACK = 60
MIN_MODEL_DAYS_N = 5          # dealer_model_days_to_sell's median comes only with 5 cars

KINDS = ("market_moved", "cheaper_nearby", "slow", "new_demand")


@dataclass
class Alert:
    kind: str
    item_id: int
    dedup_key: str
    payload: dict[str, Any] = field(default_factory=dict)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(value)  # Decimal / numeric strings from SQL
        except (TypeError, ValueError):
            return None
    return float(value) if value == value else None  # NaN out


def _int(value: Any) -> int | None:
    n = _num(value)
    return int(n) if n is not None else None


def car_name(row: Mapping[str, Any]) -> str:
    return " ".join(str(x) for x in (row.get("make"), row.get("model"), row.get("year")) if x) or "auto"


def model_days(row: Mapping[str, Any]) -> int | None:
    md = row.get("model_days") if isinstance(row.get("model_days"), Mapping) else {}
    n, median = _int(md.get("n")), _int(md.get("median"))
    return median if median is not None and (n or 0) >= MIN_MODEL_DAYS_N else None


def is_slow(days_in_stock: int | None, median_days: int | None) -> bool:
    """The twin of web/lib/dealer-insights.ts stockFacts().slow, plus the fallback."""
    if days_in_stock is None:
        return False
    if median_days is not None:
        return days_in_stock > median_days * SLOW_FACTOR
    return days_in_stock >= SLOW_DAYS_FALLBACK


def decide(row: Mapping[str, Any], *, min_count: int, now: datetime) -> tuple[list[Alert], dict[str, Any]]:
    """The alerts for this car and its new dealer_alert_state (all columns)."""
    item = int(row["item_id"])
    state = dict(row.get("state") or {})
    new: dict[str, Any] = {
        "market_median_usd": _num(state.get("market_median_usd")),
        "market_n": _int(state.get("market_n")),
        "market_at": state.get("market_at"),
        "demand_searches": _int(state.get("demand_searches")),
        "demand_people": _int(state.get("demand_people")),
        "demand_at": state.get("demand_at"),
        "cheaper_since": now,                     # what appears from now on is new
    }
    alerts: list[Alert] = []
    name = car_name(row)
    day = now.date().isoformat()

    # Market
    market = row.get("market") if isinstance(row.get("market"), Mapping) else {}
    median, n = _num(market.get("median")), _int(market.get("n")) or 0
    if market.get("enough") is True and median and median > 0:
        before = new["market_median_usd"]
        if before is None or before <= 0:
            new.update(market_median_usd=median, market_n=n, market_at=now)
        else:
            pct = round((median / before - 1) * 100, 1)   # as the panel's vs_market_pct (no float noise)
            if abs(pct) >= MARKET_MOVE_PCT:
                direction = "down" if pct < 0 else "up"
                alerts.append(Alert("market_moved", item, f"market:{item}:{direction}:{day}", {
                    "car": name, "direction": direction, "pct": round(abs(pct)),
                    "before_usd": round(before), "now_usd": round(median), "n": n}))
                new.update(market_median_usd=median, market_n=n, market_at=now)

    # A cheaper one nearby (only the ones SQL found new since the last scan)
    cheaper = row.get("cheaper") if isinstance(row.get("cheaper"), Mapping) else None
    own_usd = _num(row.get("price_usd"))
    if cheaper and _int(cheaper.get("listing_id")) and own_usd and own_usd > 0:
        other = _num(cheaper.get("price_usd")) or 0
        pct = round((1 - other / own_usd) * 100)
        if other > 0 and pct >= CHEAPER_PCT:
            lid = _int(cheaper["listing_id"])
            alerts.append(Alert("cheaper_nearby", item, f"cheaper:{item}:{lid}", {
                "car": name, "pct": pct, "price_usd": round(other), "listing_id": lid,
                "distance_km": _int(cheaper.get("distance_km")), "source_name": cheaper.get("source_name"),
                "year": _int(cheaper.get("year"))}))

    # Slow
    days, median_days = _int(row.get("days_in_stock")), model_days(row)
    if is_slow(days, median_days):
        alerts.append(Alert("slow", item, f"slow:{item}", {"car": name, "days": days, "model_days": median_days}))

    # Demand (raw, worker only: told only with at least min_count new people)
    demand = row.get("demand") if isinstance(row.get("demand"), Mapping) else None
    if demand is not None:
        searches, people = _int(demand.get("searches")) or 0, _int(demand.get("people")) or 0
        base_s, base_p = new["demand_searches"], new["demand_people"]
        if base_s is None or base_p is None:
            new.update(demand_searches=searches, demand_people=people, demand_at=now)
        else:
            floor = max(3, int(min_count))
            more_people, more_searches = people - base_p, searches - base_s
            if more_people >= floor and more_searches >= floor:
                alerts.append(Alert("new_demand", item, f"demand:{item}:{searches}:{people}", {
                    "car": name, "searches": more_searches}))
                # The mark moves only when we tell: two people today and two tomorrow add up,
                # and searches that leave never lower it (no repeat when they come back).
                new.update(demand_searches=searches, demand_people=people, demand_at=now)
    return alerts, new
