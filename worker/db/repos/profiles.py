"""The bot's alerts, stored as search_profiles.

The Telegram handlers and the scheduler keep working with the dicts they
always used ("alerts"); this module maps them onto profiles/search_profiles.
Alert ids are search_profile ids. A wizard alert with several marcas/modelos
becomes one profile per (marca, modelo), as sección 4.3 asks.

Since F1 profiles no longer have a scrape cadence of their own: they are
grouped into crawl_targets (pipeline/crawl.py) and a new or edited profile is
bootstrapped against the listings already stored (pipeline/rematch.py).
"""
from __future__ import annotations

from typing import Any

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from db.legacy_filters import split_vehicles, to_legacy, to_profile
from db.pool import connection
from db.repos.catalog import resolve_make_model


_SELECT = """
SELECT sp.id, sp.name, sp.filters, sp.preferences, sp.origin_lat, sp.origin_lon,
       sp.radius_km, sp.enabled, sp.created_at, sp.bootstrapped_at, sp.rematch_requested_at,
       sp.notify_min_level, p.telegram_user_id, p.telegram_chat_id
  FROM search_profiles sp
  JOIN profiles p ON p.id = sp.user_id
"""


def _epoch(ts) -> int | None:
    return int(ts.timestamp()) if ts else None


def _to_alert(r: dict) -> dict[str, Any]:
    return {
        "id": r["id"],
        "user_id": r["telegram_user_id"],
        "chat_id": r["telegram_chat_id"],
        "name": r["name"],
        "filters": to_legacy(r["filters"], r["preferences"], r["origin_lat"],
                             r["origin_lon"], r["radius_km"]),
        "active": 1 if r["enabled"] else 0,
        "created_at": _epoch(r["created_at"]),
        "bootstrapped": 1 if r["bootstrapped_at"] else 0,
        "rematch_requested": bool(r["rematch_requested_at"]),
        "make": r["filters"].get("make"),
        "model": r["filters"].get("model"),
        # The search_profiles row as intelligence/ reads it (sección 4.3).
        "profile": {
            "id": r["id"],
            "filters": r["filters"],
            "preferences": r["preferences"],
            "origin_lat": r["origin_lat"],
            "origin_lon": r["origin_lon"],
            "radius_km": r["radius_km"],
            "notify_min_level": r["notify_min_level"],
        },
    }


async def ensure_telegram_profile(cx: AsyncConnection, telegram_user_id: int, chat_id: int) -> str:
    row = await (await cx.execute(
        "SELECT ensure_telegram_profile(%s, %s) AS id", (telegram_user_id, chat_id),
    )).fetchone()
    return row["id"]


async def _canonical(cx: AsyncConnection, make: str | None,
                     model: str | None) -> tuple[str | None, str | None] | None:
    return await resolve_make_model(cx, make, model) if (make or model) else None


def _profile_name(name: str, vehicles: list[tuple], make: str | None, model: str | None) -> str:
    if len(vehicles) == 1:
        return name
    return f"{make or ''} {model or ''}".strip() or name


# preferences keys written from the wizard dict; any other key (e.g. the
# migration's sqlite_alert_id) survives an edit.
_WIZARD_PREFERENCES = {"seller_type", "legacy_opportunity", "legacy_extra"}


async def insert_profiles(cx: AsyncConnection, user_uuid: str, name: str, filters: dict, *,
                          catalog_only: bool = False, enabled: bool = True,
                          bootstrapped: bool = False,
                          extra_preferences: dict | None = None,
                          vehicles: list[tuple] | None = None) -> tuple[list[int], list[tuple]]:
    """Insert one search profile per (marca, modelo) of a wizard filter.

    Names are canonicalized through vehicle_catalog when they resolve. With
    `catalog_only`, combinations missing from the catalog are skipped and
    returned instead (the SQLite migration does this, sección 4.5).
    `vehicles` restricts which combinations are inserted (default: all).
    """
    all_vehicles = split_vehicles(filters)
    ids: list[int] = []
    skipped: list[tuple] = []
    for make, model in (all_vehicles if vehicles is None else vehicles):
        resolved = await _canonical(cx, make, model)
        if resolved:
            make, model = resolved
        elif catalog_only:
            skipped.append((make, model))
            continue
        values = to_profile(filters, make, model)
        values["preferences"].update(extra_preferences or {})
        profile_name = _profile_name(name, all_vehicles, make, model)
        row = await (await cx.execute(
            "INSERT INTO search_profiles (user_id, name, filters, preferences, origin_lat, "
            "  origin_lon, radius_km, enabled, bootstrapped_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CASE WHEN %s THEN now() END) RETURNING id",
            (user_uuid, profile_name, Jsonb(values["filters"]), Jsonb(values["preferences"]),
             values["origin_lat"], values["origin_lon"], values["radius_km"], enabled,
             bootstrapped),
        )).fetchone()
        ids.append(row["id"])
    return ids, skipped


async def create_alert(user_id: int, chat_id: int, name: str, filters: dict) -> list[int]:
    """Create the alert for a Telegram user. Returns the new profile ids."""
    async with connection() as cx:
        user_uuid = await ensure_telegram_profile(cx, user_id, chat_id)
        ids, _ = await insert_profiles(cx, user_uuid, name, filters)
    return ids


async def update_alert(alert_id: int, name: str, filters: dict) -> list[int]:
    """Apply an edited wizard filter to an existing alert.

    Keeps its matches (the "already seen" history), bootstrapped_at and
    created_at; requests a rematch so listings the new filters now match are
    added silently as backfill (sección 5.7).
    The alert keeps the first (marca, modelo); extra ones added while editing
    become new alerts, which bootstrap silently. Returns their ids.
    """
    vehicles = split_vehicles(filters)
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT user_id, preferences FROM search_profiles WHERE id = %s", (alert_id,),
        )).fetchone()
        if not row:
            return []
        make, model = vehicles[0]
        resolved = await _canonical(cx, make, model)
        if resolved:
            make, model = resolved
        values = to_profile(filters, make, model)
        kept = {k: v for k, v in row["preferences"].items() if k not in _WIZARD_PREFERENCES}
        values["preferences"].update(kept)
        await cx.execute(
            "UPDATE search_profiles SET name = %s, filters = %s, preferences = %s, "
            "  origin_lat = %s, origin_lon = %s, radius_km = %s, rematch_requested_at = now() "
            "WHERE id = %s",
            (_profile_name(name, vehicles, make, model), Jsonb(values["filters"]),
             Jsonb(values["preferences"]), values["origin_lat"], values["origin_lon"],
             values["radius_km"], alert_id),
        )
        new_ids, _ = await insert_profiles(cx, row["user_id"], name, filters, vehicles=vehicles[1:])
    return new_ids


async def list_alerts(user_id: int | None = None, only_active: bool = False) -> list[dict]:
    """Alerts of a Telegram user, or of every Telegram-linked user when
    `user_id` is None (the scheduler can only notify through Telegram)."""
    where = ["p.telegram_chat_id IS NOT NULL"]
    params: list[Any] = []
    if user_id is not None:
        where.append("p.telegram_user_id = %s")
        params.append(user_id)
    if only_active:
        where.append("sp.enabled")
    sql = _SELECT + " WHERE " + " AND ".join(where) + " ORDER BY sp.id DESC"
    async with connection() as cx:
        rows = await (await cx.execute(sql, params)).fetchall()
    return [_to_alert(r) for r in rows]


async def profiles_by_ids(ids: list[int]) -> list[dict]:
    """Profiles (alert dicts with their "profile" row) by id, enabled or not."""
    if not ids:
        return []
    async with connection() as cx:
        rows = await (await cx.execute(_SELECT + " WHERE sp.id = ANY(%s) ORDER BY sp.id",
                                       (list(ids),))).fetchall()
    return [_to_alert(r) for r in rows]


async def get_alert(alert_id: int) -> dict | None:
    async with connection() as cx:
        row = await (await cx.execute(_SELECT + " WHERE sp.id = %s", (alert_id,))).fetchone()
    return _to_alert(row) if row else None


async def set_alert_active(alert_id: int, active: bool) -> None:
    async with connection() as cx:
        await cx.execute("UPDATE search_profiles SET enabled = %s WHERE id = %s", (active, alert_id))


async def delete_alert(alert_id: int) -> None:
    # matches go with it (on delete cascade), like seen_listings did.
    async with connection() as cx:
        await cx.execute("DELETE FROM search_profiles WHERE id = %s", (alert_id,))


async def mark_bootstrapped(alert_id: int) -> None:
    """The profile's backfill is done: later listings may notify."""
    async with connection() as cx:
        await cx.execute(
            "UPDATE search_profiles SET bootstrapped_at = coalesce(bootstrapped_at, now()), "
            "  rematch_requested_at = NULL WHERE id = %s", (alert_id,))


async def enabled_profiles() -> list[dict[str, Any]]:
    """Every enabled profile, web or Telegram: what crawl targets are derived from."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT id, filters, origin_lat, origin_lon FROM search_profiles "
            " WHERE enabled ORDER BY id")).fetchall()


async def pending_rematch() -> list[dict]:
    """Enabled profiles never bootstrapped, or edited since (sección 5.7)."""
    async with connection() as cx:
        rows = await (await cx.execute(
            _SELECT + " WHERE sp.enabled AND (sp.bootstrapped_at IS NULL "
                      "   OR sp.rematch_requested_at IS NOT NULL) ORDER BY sp.id")).fetchall()
    return [_to_alert(r) for r in rows]


async def alerts_for_target(source: str, make: str | None, model: str | None, *,
                            telegram_only: bool = True) -> list[dict]:
    """Enabled profiles a crawl target's batch is for: same make/model, and the
    source among the profile's sources (all of them when it has none). By
    default only the Telegram-linked ones; matching (F2) takes every profile."""
    telegram = " AND p.telegram_chat_id IS NOT NULL" if telegram_only else ""
    async with connection() as cx:
        rows = await (await cx.execute(
            _SELECT + " WHERE sp.enabled" + telegram +
                      "   AND lower(sp.filters->>'make') IS NOT DISTINCT FROM lower(%s) "
                      "   AND lower(sp.filters->>'model') IS NOT DISTINCT FROM lower(%s) "
                      "   AND (NOT sp.filters ? 'sources' OR sp.filters->'sources' ? %s) "
                      " ORDER BY sp.id",
            (make, model, source))).fetchall()
    return [_to_alert(r) for r in rows]
