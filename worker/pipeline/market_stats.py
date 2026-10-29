"""Weekly market stats (F-03 fase 0,
docs/superpowers/specs/2026-10-29-f03-market-stats-fase0-design.md).

One market_stats row per ISO week (Monday 00:00 to Sunday, Argentina time),
group (make + model, or body type), 2-year band (year_from = year - year % 2)
and zone (each region of app_config.market_zones, and 'todas', which also
counts the listings without a region). SQL only brings flat rows, one per
listing; the aggregation below is pure Python.

What each column counts (reposts never count):

* active_count: listings on sale at the end of the week: first seen before
  it, seen in the last comparables.max_age_days, and not gone by then (a
  later complete read no longer saw it, or mark_gone). active_confirmed_count:
  how many of those come from confirm_sources; the others may be inflating it
  for up to max_age_days, and that is said, not corrected.
* new_count: first seen during the week, without attributes._not_news.
* gone_count and the days: only sources in confirm_sources whose listing a
  later complete read no longer saw (listing_unconfirmed). The end is
  estimated as the later of last_seen_at and last_full_seen_at, a lower
  bound. Days = that end - coalesce(published_at, first_seen_at); old stock
  without published_at (_not_news) and negatives are left out. Mercado Libre
  only since app_config.market_stats.confirm_since. A listing that stopped
  being published is never said to be sold.
* prices: over the active ones with price_usd > 0 and not price_partial.

Below app_config.market_stats.min_n (price 8, days 5) the percentiles stay
null and the counts are kept.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from normalization.zone import DEFAULT_ZONE_MAP, resolve_region

# America/Argentina/Buenos_Aires (no DST since 2009).
_AR = timezone(timedelta(hours=-3))

ALL_ZONES = "todas"
DAYS_SOURCE = "confirm_sources"
BASIS = "weekly"

DEFAULT_MARKET_STATS: dict[str, Any] = {
    "mode": "off", "write_enabled": False, "min_n": {"price": 8, "days": 5}, "year_band": 2,
    "recompute_weeks": 2, "confirm_since": {"mercadolibre": "2026-10-24"},
    "schedule": {"weekday": 1, "hour": "06:00"},
}

# Rough size of a stored row with its share of the indexes, for the projection
# the dry run prints against the 100 MB budget (decision 8). Not measured.
_ROW_BYTES = 300
_KEEP_WEEKS = 26


@dataclass(frozen=True)
class StatRow:
    week_start: date
    group_kind: str
    make: str | None
    model: str | None
    body_type: str | None
    year_from: int
    zone: str
    active_count: int
    active_confirmed_count: int
    new_count: int
    gone_count: int
    price_n: int
    median_price_usd: float | None
    p25_price_usd: float | None
    p75_price_usd: float | None
    days_n: int
    median_days_to_gone: float | None
    p25_days_to_gone: float | None
    p75_days_to_gone: float | None
    days_source: str
    zone_map_version: int | None


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------

def _monday(week: str | date) -> date:
    if isinstance(week, str):
        year, num = week.upper().split("-W")
        return date.fromisocalendar(int(year), int(num), 1)
    return week - timedelta(days=week.weekday())


def week_bounds(week: str | date) -> tuple[datetime, datetime]:
    """Monday 00:00 and the next Monday 00:00, Argentina time, of an ISO week
    ("2026-W44") or of the week a date falls in."""
    start = datetime.combine(_monday(week), datetime.min.time(), tzinfo=_AR)
    return start, start + timedelta(days=7)


def week_label(week: str | date) -> str:
    year, num, _ = _monday(week).isocalendar()
    return f"{year}-W{num:02d}"


def last_closed_week(now: datetime) -> str:
    """The ISO week before the one `now` falls in, in Argentina."""
    return week_label(now.astimezone(_AR).date() - timedelta(days=7))


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def percentile(values: Iterable[float], p: float) -> float | None:
    """Linear interpolation between the closest ranks, like percentile_cont."""
    v = sorted(values)
    if not v:
        return None
    pos = p * (len(v) - 1)
    lo, hi = math.floor(pos), math.ceil(pos)
    return float(v[lo] + (v[hi] - v[lo]) * (pos - lo))


def _since(cfg: dict[str, Any]) -> dict[str, datetime]:
    out = {}
    for source, day in (cfg.get("confirm_since") or {}).items():
        out[source] = datetime.combine(date.fromisoformat(str(day)), datetime.min.time(), tzinfo=_AR)
    return out


def _norm(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    return value or None


@dataclass
class _Facts:
    active: bool
    confirmed: bool
    new: bool
    gone: bool
    price: float | None
    days: float | None


def _facts(r: dict[str, Any], start: datetime, end: datetime, max_age: timedelta,
           since: dict[str, datetime]) -> _Facts:
    seen = r["seen_at"]
    ended = (r["status"] == "gone" or r["unconfirmed"]) and seen < end
    active = r["first_seen_at"] < end and seen >= end - max_age and not ended
    gone = (bool(r["confirm_source"]) and bool(r["unconfirmed"]) and start <= seen < end
            and (r["source"] not in since or seen >= since[r["source"]]))
    days = None
    if gone and not (r["published_at"] is None and r["not_news"]):
        d = (seen - (r["published_at"] or r["first_seen_at"])).total_seconds() / 86400
        days = d if d >= 0 else None
    price = r["price_usd"]
    ok_price = active and price is not None and float(price) > 0 and not r["price_partial"]
    return _Facts(active=active, confirmed=active and bool(r["confirm_source"]),
                  new=start <= r["first_seen_at"] < end and not r["not_news"],
                  gone=gone, price=float(price) if ok_price else None, days=days)


def _groups(r: dict[str, Any], band: int) -> list[tuple[str, str | None, str | None, str | None, int]]:
    year = r["year"]
    if year is None:
        return []
    year_from = int(year) - int(year) % band
    make, model, body = _norm(r["make"]), _norm(r["model"]), _norm(r["body_type"])
    out = []
    if make and model:
        out.append(("model", make, model, None, year_from))
    if body:
        out.append(("body_type", None, None, body, year_from))
    return out


def _sort_key(key: tuple) -> tuple:
    return tuple((v is None, v if v is not None else "") for v in key)


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def aggregate(rows: Iterable[dict[str, Any]], *, week: str | date, zone_map: dict[str, Any],
              cfg: dict[str, Any]) -> list[StatRow]:
    """The market_stats rows of a week from flat listing rows (fetch_rows).
    `cfg` is app_config.market_stats plus comparables.max_age_days."""
    start, end = week_bounds(week)
    max_age = timedelta(days=int(cfg.get("max_age_days", 30)))
    min_n = {**DEFAULT_MARKET_STATS["min_n"], **(cfg.get("min_n") or {})}
    band = int(cfg.get("year_band", 2)) or 1
    since = _since(cfg)
    version = (zone_map or {}).get("version")

    acc: dict[tuple, dict[str, Any]] = defaultdict(lambda: {"active": 0, "confirmed": 0, "new": 0, "gone": 0,
                                                            "prices": [], "days": []})
    for r in rows:
        if r["probable_repost_of"] is not None:
            continue
        f = _facts(r, start, end, max_age, since)
        if not (f.active or f.new or f.gone):
            continue
        region = resolve_region(zone_map, r["province_id"], r["department"], r["precision"])
        zones = [ALL_ZONES] + ([region] if region else [])
        for group in _groups(r, band):
            for zone in zones:
                a = acc[(*group, zone)]
                a["active"] += f.active
                a["confirmed"] += f.confirmed
                a["new"] += f.new
                a["gone"] += f.gone
                if f.price is not None:
                    a["prices"].append(f.price)
                if f.days is not None:
                    a["days"].append(f.days)

    out = []
    for key in sorted(acc, key=_sort_key):
        kind, make, model, body, year_from, zone = key
        a = acc[key]
        prices = a["prices"] if len(a["prices"]) >= int(min_n["price"]) else []
        days = a["days"] if len(a["days"]) >= int(min_n["days"]) else []
        out.append(StatRow(
            week_start=start.date(), group_kind=kind, make=make, model=model, body_type=body,
            year_from=year_from, zone=zone, active_count=a["active"], active_confirmed_count=a["confirmed"],
            new_count=a["new"], gone_count=a["gone"], price_n=len(a["prices"]),
            median_price_usd=_round(percentile(prices, 0.5), 2),
            p25_price_usd=_round(percentile(prices, 0.25), 2),
            p75_price_usd=_round(percentile(prices, 0.75), 2),
            days_n=len(a["days"]),
            median_days_to_gone=_round(percentile(days, 0.5), 2),
            p25_days_to_gone=_round(percentile(days, 0.25), 2),
            p75_days_to_gone=_round(percentile(days, 0.75), 2),
            days_source=DAYS_SOURCE, zone_map_version=version))
    return out


def report(stats: list[StatRow], rows: list[dict[str, Any]], *, week: str | date,
           cfg: dict[str, Any], zone_map: dict[str, Any] | None = None) -> dict[str, Any]:
    """What the dry run prints: rows, how many have a price sample, the
    distribution of price_n, the listings on sale without a zone per source,
    and the size 26 weeks like this one would take."""
    zone_map = zone_map or DEFAULT_ZONE_MAP
    start, end = week_bounds(week)
    max_age = timedelta(days=int(cfg.get("max_age_days", 30)))
    min_price = int({**DEFAULT_MARKET_STATS["min_n"], **(cfg.get("min_n") or {})}["price"])
    since = _since(cfg)
    by_source: dict[str, dict[str, int]] = {}
    for r in rows:
        if r["probable_repost_of"] is not None or not _facts(r, start, end, max_age, since).active:
            continue
        s = by_source.setdefault(r["source"], {"total": 0, "no_zone": 0})
        s["total"] += 1
        if not resolve_region(zone_map, r["province_id"], r["department"], r["precision"]):
            s["no_zone"] += 1
    buckets = Counter(_price_bucket(s.price_n, min_price) for s in stats)
    return {
        "week": week_label(week),
        "rows": len(stats),
        "rows_with_price_sample": sum(1 for s in stats if s.price_n >= min_price),
        "price_n": dict(buckets),
        "no_zone_by_source": dict(sorted(by_source.items())),
        "listings_read": len(rows),
        "projected_mb_26_weeks": round(len(stats) * _ROW_BYTES * _KEEP_WEEKS / 1_000_000, 3),
    }


def _price_bucket(n: int, min_price: int) -> str:
    if n == 0:
        return "0"
    if n < min_price:
        return f"1-{min_price - 1}"
    return f"{min_price}-19" if n < 20 else "20+"


def report_lines(rep: dict[str, Any]) -> list[str]:
    lines = [f"semana {rep['week']}: {rep['rows']} filas, {rep['rows_with_price_sample']} con muestra de precio, "
             f"{rep['listings_read']} avisos leídos",
             "price_n: " + ", ".join(f"{k}: {v}" for k, v in sorted(rep["price_n"].items())),
             f"proyección a {_KEEP_WEEKS} semanas: ~{rep['projected_mb_26_weeks']} MB (presupuesto: 100 MB)"]
    for source, s in rep["no_zone_by_source"].items():
        pct = 100 * s["no_zone"] / s["total"] if s["total"] else 0
        lines.append(f"  {source:<14} sin zona {s['no_zone']:>6} de {s['total']:>6} ({pct:.0f} %)")
    return lines
