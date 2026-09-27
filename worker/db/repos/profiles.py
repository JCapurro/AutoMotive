"""The bot's alerts, stored as search_profiles.

The Telegram handlers and the scheduler keep working with the dicts they
always used ("alerts"); this module maps them onto profiles/search_profiles.
Alert ids are search_profile ids. A wizard alert with several marcas/modelos
becomes one profile per (marca, modelo), as sección 4.3 asks.
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
       sp.radius_km, sp.enabled, sp.created_at, sp.bootstrapped_at, sp.last_scraped_at,
       p.telegram_user_id, p.telegram_chat_id
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
        "last_scraped_at": _epoch(r["last_scraped_at"]),
    }


async def ensure_telegram_profile(cx: AsyncConnection, telegram_user_id: int, chat_id: int) -> str:
    row = await (await cx.execute(
        "SELECT ensure_telegram_profile(%s, %s) AS id", (telegram_user_id, chat_id),
    )).fetchone()
    return row["id"]


async def insert_profiles(cx: AsyncConnection, user_uuid: str, name: str, filters: dict, *,
                          catalog_only: bool = False, enabled: bool = True,
                          bootstrapped: bool = False) -> tuple[list[int], list[tuple]]:
    """Insert one search profile per (marca, modelo) of a wizard filter.

    Names are canonicalized through vehicle_catalog when they resolve. With
    `catalog_only`, combinations missing from the catalog are skipped and
    returned instead (the SQLite migration does this, sección 4.5).
    """
    vehicles = split_vehicles(filters)
    ids: list[int] = []
    skipped: list[tuple] = []
    for make, model in vehicles:
        resolved = await resolve_make_model(cx, make, model) if (make or model) else None
        if resolved:
            make, model = resolved
        elif catalog_only:
            skipped.append((make, model))
            continue
        values = to_profile(filters, make, model)
        profile_name = name if len(vehicles) == 1 else (f"{make or ''} {model or ''}".strip() or name)
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


async def mark_scraped(alert_id: int, *, bootstrapped: bool | None = None) -> None:
    """Stamp last_scraped_at; optionally flip bootstrapped after the first silent run."""
    async with connection() as cx:
        if bootstrapped is None:
            await cx.execute(
                "UPDATE search_profiles SET last_scraped_at = now() WHERE id = %s", (alert_id,),
            )
        else:
            await cx.execute(
                "UPDATE search_profiles SET last_scraped_at = now(), "
                "  bootstrapped_at = CASE WHEN %s THEN coalesce(bootstrapped_at, now()) END "
                "WHERE id = %s",
                (bootstrapped, alert_id),
            )
