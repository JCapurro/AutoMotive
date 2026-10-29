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

import asyncio
import logging
import math
import traceback
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Iterable

from psycopg.types.json import Jsonb

import db
from db.repos.runs import log_error
from normalization.zone import DEFAULT_ZONE_MAP, derive_zone, resolve_region
from pipeline.market_zones import sync_zones
from pipeline.retention import purge_market_stats

log = logging.getLogger("market_stats")

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


# ---------------------------------------------------------------------------
# Database: flat rows in, stats out
# ---------------------------------------------------------------------------

# listing_unconfirmed() only for the sources in confirm_sources, behind a CASE:
# the planner is sensitive there (migration 20261106120000, comparable_listings).
_FETCH = """
SELECT l.id, l.source, l.make, l.model, l.body_type, l.year, l.status::text AS status,
       l.price_usd::float8 AS price_usd, l.price_partial, l.probable_repost_of, l.first_seen_at,
       greatest(l.last_seen_at, l.last_full_seen_at) AS seen_at, l.published_at,
       l.attributes ? '_not_news' AS not_news, l.location_text, l.lat, l.lon,
       z.province_id, z.department, z.precision, z.lat AS zone_lat, z.lon AS zone_lon,
       %(confirm)s::jsonb ? l.source AS confirm_source,
       CASE WHEN %(confirm)s::jsonb ? l.source
            THEN EXISTS (SELECT 1 FROM public.listing_unconfirmed(
                   l.source, l.make, l.model, l.year, l.mileage_km,
                   greatest(l.last_seen_at, l.last_full_seen_at), %(confirm)s::jsonb,
                   %(grace)s::numeric * interval '1 hour'))
            ELSE false END AS unconfirmed
  FROM listings l
  LEFT JOIN listing_zones z ON z.listing_id = l.id
 WHERE l.year IS NOT NULL
   AND l.first_seen_at < %(end)s
   AND greatest(l.last_seen_at, l.last_full_seen_at) >= %(since)s
 ORDER BY l.id
"""

_COLUMNS = [f for f in StatRow.__dataclass_fields__]
_UPSERT = (
    f"INSERT INTO market_stats ({', '.join(_COLUMNS)}, as_of, run_id, basis, computed_at) "
    f"VALUES ({', '.join(['%s'] * len(_COLUMNS))}, %s, %s, %s, now()) "
    "ON CONFLICT ON CONSTRAINT market_stats_unique DO UPDATE SET "
    + ", ".join(f"{c} = excluded.{c}" for c in _COLUMNS + ["as_of", "run_id", "basis", "computed_at"]))


class WriteDisabled(RuntimeError):
    """Writing market_stats needs app_config.market_stats.write_enabled (Juan turns it on)."""


class WeekRejected(ValueError):
    """A week not closed yet, or older than recompute_weeks (no --retro)."""


async def fetch_rows(week: str | date, comparables: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per listing that may count in the week: first seen before its
    end and seen in the max_age_days before its start. `comparables` is
    app_config.comparables as read for this run (confirm_sources,
    confirm_grace_hours, max_age_days). A listing whose zone row is missing or
    stale gets its zone derived here, in memory."""
    start, end = week_bounds(week)
    params = {"confirm": Jsonb(list(comparables.get("confirm_sources") or [])),
              "grace": float(comparables.get("confirm_grace_hours", 36)),
              "end": end, "since": start - timedelta(days=int(comparables.get("max_age_days", 30)))}
    async with db.connection() as cx:
        rows = await (await cx.execute(_FETCH, params)).fetchall()
    await asyncio.to_thread(_derive_missing_zones, rows)
    return rows


def _derive_missing_zones(rows: list[dict[str, Any]]) -> None:
    for r in rows:
        if (r["zone_lat"], r["zone_lon"]) != (r["lat"], r["lon"]):
            facts = derive_zone(r["lat"], r["lon"], r["location_text"], r["source"])
            r["province_id"], r["department"], r["precision"] = (
                (facts.province_id, facts.department, facts.precision) if facts else (None, None, None))


async def upsert_rows(stats: list[StatRow], *, weeks: list[date], run_id: int | None, as_of: datetime) -> int:
    """Write the stats of `weeks`, replacing what those weeks had: rows of
    groups that no longer appear are deleted. Idempotent."""
    async with db.connection() as cx:
        async with cx.cursor() as cur:
            if stats:
                await cur.executemany(_UPSERT, [(*asdict(s).values(), as_of, run_id, BASIS) for s in stats])
            # now() is the transaction's: what this call wrote has it.
            await cur.execute("DELETE FROM market_stats WHERE week_start = ANY(%s) AND computed_at < now()",
                              (list(weeks),))
    return len(stats)


# ---------------------------------------------------------------------------
# A run
# ---------------------------------------------------------------------------

async def _configs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cfg = {**DEFAULT_MARKET_STATS, **(await db.get_config("market_stats", {}) or {})}
    comparables = await db.get_config("comparables", {}) or {}
    zone_map = await db.get_config("market_zones", None) or DEFAULT_ZONE_MAP
    return cfg, comparables, zone_map


def weeks_to_compute(week: str | date | None, now: datetime, recompute_weeks: int) -> list[str]:
    """The asked week (default: the last closed one) and the recompute_weeks
    before it, never older than recompute_weeks before the last closed week."""
    latest = _monday(last_closed_week(now))
    oldest = latest - timedelta(weeks=recompute_weeks)
    target = _monday(week) if week is not None else latest
    if target > latest:
        raise WeekRejected(f"la semana {week_label(target)} todavía no cerró")
    if target < oldest:
        raise WeekRejected(f"la semana {week_label(target)} es anterior a {week_label(oldest)}: "
                           "las semanas pasadas no se reconstruyen")
    return [week_label(target - timedelta(weeks=k)) for k in range(recompute_weeks + 1)
            if target - timedelta(weeks=k) >= oldest]


async def _start_run(week: str, mode: str, params: dict[str, Any]) -> int:
    async with db.connection() as cx:
        row = await (await cx.execute(
            "INSERT INTO market_stats_runs (week_start, mode, params) VALUES (%s, %s, %s) RETURNING id",
            (_monday(week), mode, Jsonb(params)))).fetchone()
    return row["id"]


async def _finish_run(run_id: int, *, status: str, error: str | None = None, **counts: Any) -> None:
    async with db.connection() as cx:
        await cx.execute(
            "UPDATE market_stats_runs SET status = %s, finished_at = now(), error = %s, "
            "  rows_computed = %s, rows_written = %s, listings_read = %s, no_zone_by_source = %s "
            " WHERE id = %s",
            (status, error, counts.get("rows_computed"), counts.get("rows_written"), counts.get("listings_read"),
             Jsonb(counts["no_zone_by_source"]) if counts.get("no_zone_by_source") is not None else None,
             run_id))


def _target_week(week: str | date | None, now: datetime) -> str:
    """The week a run is about, for its records even when the asked one is
    not valid."""
    try:
        return week_label(week) if week is not None else last_closed_week(now)
    except (ValueError, TypeError):
        return last_closed_week(now)


async def run_market_stats(week: str | date | None = None, *, mode: str, write_enabled: bool,
                           now: datetime | None = None) -> dict[str, Any]:
    """Compute the week (default: the last closed one) and the recompute_weeks
    before it.

    * preview (the CLI's --dry-run): writes nothing at all, zones included;
      the report is the output.
    * dry_run (scheduled): zones are synced and the run is recorded, with no
      stats written.
    * write: also writes market_stats and then purges the old weeks. Needs
      write_enabled (WriteDisabled otherwise).

    A failure, reading the config, a rejected week (status 'rejected', the
    WeekRejected message as error) and WriteDisabled included, is recorded
    (pipeline_errors, and market_stats_runs.error unless preview) and
    returned, never raised: it must not stop the worker. Only an unknown mode,
    a programming error, raises."""
    if mode not in ("preview", "dry_run", "write"):
        raise ValueError(f"modo desconocido: {mode!r}")
    now = now or datetime.now(_AR)
    target = _target_week(week, now)
    params: dict[str, Any] = {"week": target}
    result: dict[str, Any] = {"status": "ok", "run_id": None, "weeks": [], "rows_computed": 0,
                              "rows_written": 0, "report": None}
    try:
        if mode == "write" and not write_enabled:
            raise WriteDisabled("app_config.market_stats.write_enabled es false: no se escribe market_stats")
        cfg, comparables, zone_map = await _configs()
        weeks = weeks_to_compute(week, now, int(cfg.get("recompute_weeks", 2)))
        target = weeks[0]
        agg_cfg = {**cfg, "max_age_days": int(comparables.get("max_age_days", 30))}
        params = {"weeks": weeks, "min_n": cfg.get("min_n"), "year_band": cfg.get("year_band"),
                  "confirm_since": cfg.get("confirm_since"), "zone_map_version": zone_map.get("version"),
                  "confirm_sources": comparables.get("confirm_sources"),
                  "confirm_grace_hours": comparables.get("confirm_grace_hours"),
                  "max_age_days": agg_cfg["max_age_days"]}
        result["weeks"] = weeks
        if mode != "preview":
            result["run_id"] = await _start_run(target, mode, params)
        await sync_zones(dry_run=mode == "preview")
        for w in weeks:
            rows = await fetch_rows(w, comparables)
            # CPU-bound over every listing: off the event loop, so the
            # scrapers' heartbeats and leases keep running meanwhile.
            stats = await asyncio.to_thread(aggregate, rows, week=w, zone_map=zone_map, cfg=agg_cfg)
            result["rows_computed"] += len(stats)
            if w == target:
                result["report"] = await asyncio.to_thread(report, stats, rows, week=w, cfg=agg_cfg,
                                                           zone_map=zone_map)
            if mode == "write":
                result["rows_written"] += await upsert_rows(stats, weeks=[_monday(w)],
                                                            run_id=result["run_id"], as_of=now)
        if mode == "write":
            await purge_market_stats()
        if result["run_id"] is not None:
            await _finish_run(result["run_id"], status="ok", rows_computed=result["rows_computed"],
                              rows_written=result["rows_written"],
                              listings_read=result["report"]["listings_read"],
                              no_zone_by_source=result["report"]["no_zone_by_source"])
        log.info("market_stats %s %s: %d filas calculadas, %d escritas", mode, target,
                 result["rows_computed"], result["rows_written"])
    except Exception as exc:
        rejected = isinstance(exc, WeekRejected)
        error = str(exc) if rejected else traceback.format_exc()
        result.update(status="rejected" if rejected else "failed", error=error)
        await log_error("market_stats", target, error)
        if mode != "preview":
            try:
                if result["run_id"] is None:
                    result["run_id"] = await _start_run(target, mode, params)
                await _finish_run(result["run_id"], status="failed", error=error[-4000:],
                                  rows_computed=result["rows_computed"], rows_written=result["rows_written"])
            except Exception:
                log.exception("could not record the failed market_stats run of %s", target)
    return result


# ---------------------------------------------------------------------------
# Weekly schedule
# ---------------------------------------------------------------------------

def next_run(now: datetime, cfg: dict[str, Any]) -> datetime:
    """The next market_stats.schedule slot (ISO weekday, "HH:MM" in Argentina)
    strictly after `now`."""
    schedule = {**DEFAULT_MARKET_STATS["schedule"], **((cfg or {}).get("schedule") or {})}
    hh, mm = (int(x) for x in str(schedule["hour"]).split(":"))
    local = now.astimezone(_AR)
    days = (int(schedule["weekday"]) - local.isoweekday()) % 7
    slot = (local + timedelta(days=days)).replace(hour=hh, minute=mm, second=0, microsecond=0)
    return slot if slot > local else slot + timedelta(days=7)


async def scheduled_run(cfg: dict[str, Any], *,
                        run: Callable[..., Awaitable[dict[str, Any]]] | None = None) -> dict[str, Any] | None:
    """What a slot does with app_config.market_stats.mode: off nothing,
    dry_run or write the run of that mode."""
    mode = (cfg or {}).get("mode", "off")
    if mode not in ("dry_run", "write"):
        return None
    return await (run or run_market_stats)(mode=mode, write_enabled=bool(cfg.get("write_enabled")))


# The loop looks at the schedule at least this often, so a slot moved in
# /admin/config is honoured within the hour, without a deploy.
LOOP_CHECK_SECONDS = 3600.0


async def _market_cfg() -> dict[str, Any]:
    return {**DEFAULT_MARKET_STATS, **(await db.get_config("market_stats", {}) or {})}


async def _has_run(week: str, mode: str) -> bool:
    """Whether market_stats_runs has a finished run of `mode` for the ISO week:
    a failed or interrupted one is retried on the next start."""
    async with db.connection() as cx:
        row = await (await cx.execute(
            "SELECT EXISTS (SELECT 1 FROM market_stats_runs WHERE week_start = %s AND mode = %s AND status = 'ok') AS hit",
            (_monday(week), mode))).fetchone()
    return bool(row["hit"])


async def _sleep(stop: asyncio.Event, seconds: float) -> bool:
    """Wait `seconds` or until `stop`; True when stopped."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=max(seconds, 0.0))
        return True
    except asyncio.TimeoutError:
        return False


async def market_stats_loop(stop: asyncio.Event, *, clock: Callable[[], datetime] | None = None,
                            check_every: float = LOOP_CHECK_SECONDS,
                            run: Callable[..., Awaitable[dict[str, Any]]] | None = None) -> None:
    """Run the job at each market_stats.schedule slot, as its mode says (born
    off). The config and the next slot are read again at least every
    `check_every` seconds, so a schedule or mode changed in /admin/config
    applies without a deploy: a slot is due when it falls between the
    previous look and this one.

    A slot lost while the worker was down (a restart across Monday 06:00): at
    start, when the most recent slot already passed and market_stats_runs has
    no run of the current mode for the week that slot computes, the job runs
    right away. It recomputes recompute_weeks back, so it covers that week.
    `clock` is injectable for the tests."""
    clock = clock or (lambda: datetime.now(_AR))
    last: datetime | None = None
    while not stop.is_set():
        wait = check_every
        try:
            cfg = await _market_cfg()
            now = clock()
            if last is None:
                lost = next_run(now - timedelta(days=7), cfg)           # the most recent slot, <= now
                due = (cfg.get("mode") in ("dry_run", "write")
                       and not await _has_run(last_closed_week(lost), cfg["mode"]))
            else:
                due = next_run(last, cfg) <= now
            last = now
            if due:
                await scheduled_run(cfg, run=run)
                now = last = clock()
            wait = min(check_every, (next_run(now, cfg) - now).total_seconds())
        except Exception:
            await log_error("market_stats", "loop", traceback.format_exc())
        if await _sleep(stop, wait):
            return
