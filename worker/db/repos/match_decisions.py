"""match_decisions: the insert-only log of alert decisions (f3 shadow mode).

Spec docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §4.4, migration
20261212120000_score_f3_shadow. One row per fresh alert candidate per (model, phase):
'card' when the Notifier decides, 'deferred' after the enrichment re-score, 'sweeper'
20 minutes later for the ones still waiting for the detail. The model is the formula
that decides (during the shadow, always 'f2'); each row also carries f3's hypothetical
decision. A row is never updated or deleted (a trigger refuses it), so every write is
INSERT … ON CONFLICT DO NOTHING.

Every function takes the caller's connection and raises on any error: the decision
log (notifications/decision_log.py) catches, so a log failure never reaches scoring
or alerting. Read-only reports: tools/shadow_report.py.
"""
from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

TABLE = "public.match_decisions"
PHASES = ("card", "deferred", "sweeper")
MODELS = ("f2", "f3")

# Every column but `id`, in table order. A row for insert() is a dict with these keys
# (a missing key is null; decided_at defaults to now() and the arrays to empty).
COLUMNS: tuple[str, ...] = (
    "match_id", "search_profile_id", "listing_id", "user_id", "model", "phase", "decided_at", "f3_decides",
    # f2
    "f2_version", "f2_score", "f2_level", "f2_decision", "f2_kind", "f2_reason", "f2_breakdown", "red_flags",
    # f3 (hypothetical during the shadow)
    "f3_version", "f3_params", "f3_score", "f3_level", "f3_level_uncapped", "f3_decision", "f3_kind",
    "f3_reason", "f3_deal_raw", "f3_r", "f3_deal", "f3_d", "f3_d_eff", "f3_fit_level", "f3_fit_score",
    "f3_flags", "f3_a_verificar", "f3_seller_capped", "agency_voice", "placeholder", "would_defer", "f3",
    # what was known when deciding
    "price_ref", "price", "currency", "price_usd", "price_partial", "title", "source", "year",
    "seller_type", "dealer_inferred", "enriched", "listing_status", "audience",
)
REQUIRED: tuple[str, ...] = ("match_id", "search_profile_id", "listing_id", "model", "phase",
                             "f3_decides", "f2_version")
_ARRAYS = frozenset({"red_flags", "f3_flags", "f3_a_verificar"})
_INTEGERS = frozenset({"match_id", "search_profile_id", "listing_id", "f2_score", "f3_score", "year"})

# A log write must never hold the batch that called it: the server cancels it after this.
STATEMENT_TIMEOUT = "2s"

# Read columns, with the uuid as text so a row read back is JSON-safe as it comes.
_SELECT = ", ".join("c.user_id::text AS user_id" if c == "user_id" else f"c.{c}" for c in ("id", *COLUMNS))


def _insert_value(column: str) -> str:
    if column == "decided_at":
        return "coalesce(r.decided_at, now())"
    if column in _ARRAYS:
        return f"coalesce(r.{column}, '{{}}')"
    if column == "f3_decides":
        # A deferred row decides for f3 only while no sweeper row did it first (same statement).
        return ("CASE WHEN r.phase = 'deferred' THEN r.f3_decides AND NOT EXISTS ("
                f"SELECT 1 FROM {TABLE} s WHERE s.match_id = r.match_id AND s.model = r.model "
                "AND s.phase = 'sweeper') ELSE r.f3_decides END")
    return f"r.{column}"


_INSERT = (
    f"WITH r AS (SELECT * FROM jsonb_populate_recordset(null::{TABLE}, %s::jsonb)) "
    f"INSERT INTO {TABLE} ({', '.join(COLUMNS)}) "
    f"SELECT {', '.join(_insert_value(c) for c in COLUMNS)} FROM r "
    # The sweeper has nothing to decide once the enrichment re-score did.
    f"WHERE NOT (r.phase = 'sweeper' AND EXISTS (SELECT 1 FROM {TABLE} x WHERE x.match_id = r.match_id "
    "AND x.model = r.model AND x.phase = 'deferred')) "
    "ON CONFLICT (match_id, model, phase) DO NOTHING"
)


# ---------------------------------------------------------------------------
# JSON-safe rows
# ---------------------------------------------------------------------------

def _clean(value: Any) -> Any:
    """Plain JSON values: NaN/inf → null, Decimal → int or float, datetimes → ISO, uuid → str."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_clean(v) for v in value]
    return str(value)


def _array_item(item: Any) -> str:
    # red_flags may come as matches.red_flags objects ({"id": …, "text": …}): keep the id.
    if isinstance(item, Mapping) and item.get("id") is not None:
        return str(item["id"])
    return str(item)


def prepare(row: Mapping[str, Any]) -> dict[str, Any]:
    """One row as the insert sends it. Raises ValueError on an unknown column or a missing
    required one (a bug in the caller: better loud in its tests than a silently thinner log)."""
    unknown = set(row) - set(COLUMNS)
    if unknown:
        raise ValueError(f"match_decisions: unknown columns {sorted(unknown)}")
    missing = [c for c in REQUIRED if row.get(c) is None]
    if missing:
        raise ValueError(f"match_decisions: missing {missing}")
    out: dict[str, Any] = {}
    for column, value in row.items():
        value = _clean(value)
        if column in _ARRAYS and value is not None:
            value = [_array_item(v) for v in (value if isinstance(value, list) else [value])]
        elif column in _INTEGERS and isinstance(value, float) and value.is_integer():
            value = int(value)        # jsonb_populate_recordset refuses "88.0" for a smallint
        out[column] = value
    return out


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

async def _timeout(cx: AsyncConnection) -> None:
    await cx.execute(f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT}'")


async def available(cx: AsyncConnection) -> bool:
    """Whether the migration that creates the table is applied."""
    row = await (await cx.execute(f"SELECT to_regclass('{TABLE}') IS NOT NULL AS ok")).fetchone()
    return bool(row and row["ok"])


async def insert(cx: AsyncConnection, rows: Iterable[Mapping[str, Any]]) -> int:
    """Insert decision rows in one statement; a (match, model, phase) already there is
    skipped. In the same statement, a 'sweeper' row is skipped when the match already has
    a 'deferred' one, and a 'deferred' row's f3_decides turns false when a 'sweeper' row
    decided first. Returns the rows inserted."""
    batch = [prepare(r) for r in rows]
    if not batch:
        return 0
    await _timeout(cx)
    cur = await cx.execute(_INSERT, (Jsonb(batch, dumps=lambda o: json.dumps(o, allow_nan=False)),))
    return cur.rowcount


async def cards_for_listings(cx: AsyncConnection, listing_ids: Iterable[int], *, since: datetime,
                             model: str = "f2") -> list[dict[str, Any]]:
    """Card rows of these listings decided since `since` that have no 'deferred' row yet
    (what the enrichment re-score still has to log), each with `has_sweeper`: whether
    the sweeper already decided it."""
    ids = sorted({int(i) for i in listing_ids})
    if not ids:
        return []
    await _timeout(cx)
    return await (await cx.execute(
        f"SELECT {_SELECT}, EXISTS (SELECT 1 FROM {TABLE} s WHERE s.match_id = c.match_id "
        "         AND s.model = c.model AND s.phase = 'sweeper') AS has_sweeper "
        f"  FROM {TABLE} c "
        " WHERE c.listing_id = ANY(%s::bigint[]) AND c.model = %s AND c.phase = 'card' AND c.decided_at >= %s "
        f"   AND NOT EXISTS (SELECT 1 FROM {TABLE} x WHERE x.match_id = c.match_id AND x.model = c.model "
        "                    AND x.phase = 'deferred') "
        " ORDER BY c.decided_at, c.id",
        (ids, model, since))).fetchall()


async def due_sweeps(cx: AsyncConnection, *, before: datetime, since: datetime, limit: int = 200,
                     model: str = "f2") -> list[dict[str, Any]]:
    """Card rows that wait for the detail (would_defer), decided in [since, before), with
    neither a 'deferred' nor a 'sweeper' row: what the sweeper decides now. Oldest first."""
    await _timeout(cx)
    return await (await cx.execute(
        f"SELECT {_SELECT} FROM {TABLE} c "
        " WHERE c.phase = 'card' AND c.would_defer AND c.model = %s "
        "   AND c.decided_at < %s AND c.decided_at >= %s "
        f"   AND NOT EXISTS (SELECT 1 FROM {TABLE} x WHERE x.match_id = c.match_id AND x.model = c.model "
        "                    AND x.phase IN ('deferred', 'sweeper')) "
        " ORDER BY c.decided_at, c.id LIMIT %s",
        (model, before, since, int(limit)))).fetchall()


async def current_state(cx: AsyncConnection, match_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Each match as it is now, with its listing (listing `status` and `enriched_at` as in
    `listings`): what a later phase logs. A match the re-score deleted (it no longer fits)
    is absent."""
    ids = sorted({int(i) for i in match_ids})
    if not ids:
        return {}
    await _timeout(cx)
    rows = await (await cx.execute(
        "SELECT m.id AS match_id, m.search_profile_id, m.listing_id, sp.user_id::text AS user_id, "
        "       m.score, m.level::text AS level, m.score_breakdown, m.price_ref, m.red_flags, "
        "       m.scoring_version, m.is_backfill, m.updated_at, "
        "       l.price::float8 AS price, l.currency, l.price_usd::float8 AS price_usd, l.price_partial, "
        "       l.title, l.source, l.year, l.seller_type, l.dealer_inferred, l.enriched_at, "
        "       l.status::text AS status "
        "  FROM matches m JOIN listings l ON l.id = m.listing_id "
        "  JOIN search_profiles sp ON sp.id = m.search_profile_id "
        " WHERE m.id = ANY(%s::bigint[])",
        (ids,))).fetchall()
    return {r["match_id"]: r for r in rows}
