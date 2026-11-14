"""near_zone_notices: the aviso de auto cerca de la zona (pipeline/near_zone.py)."""
from __future__ import annotations

from typing import Any

from db.pool import connection
from db.repos.low_results import _RESULTS
from db.repos.profiles import SELLER_FILTER


async def candidates(*, max_results: int, cooldown_days: float) -> list[dict[str, Any]]:
    """Enabled searches with access, prepared (bootstrapped, no rematch
    pending), with a place and a radius, email among their channels,
    `max_results` results or fewer and no notice in the last `cooldown_days`;
    the ones never told first."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM ("
            " SELECT sp.id, sp.user_id::text AS user_id, sp.filters, sp.preferences, sp.created_at, "
            "        sp.origin_lat, sp.origin_lon, sp.radius_km, " + SELLER_FILTER + ", "
            "        p.email, p.email_unsubscribe_token::text AS unsubscribe_token, "
            "        " + _RESULTS + " AS result_count, "
            "        (SELECT max(n.created_at) FROM near_zone_notices n WHERE n.search_profile_id = sp.id) AS told_at "
            "   FROM search_profiles sp JOIN profiles p ON p.id = sp.user_id "
            "  WHERE sp.enabled AND public.search_access_active(sp.id) "
            "    AND sp.bootstrapped_at IS NOT NULL AND sp.rematch_requested_at IS NULL "
            "    AND sp.radius_km > 0 AND sp.origin_lat IS NOT NULL AND sp.origin_lon IS NOT NULL "
            "    AND 'email' = ANY(sp.channels) AND p.email IS NOT NULL"
            ") x WHERE result_count <= %s "
            "   AND (told_at IS NULL OR told_at <= now() - make_interval(secs => %s)) "
            "ORDER BY told_at NULLS FIRST, id",
            (max_results, cooldown_days * 86400))).fetchall()


async def told(profile_id: int) -> set[int]:
    """The listings this search was already told about."""
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT listing_id FROM near_zone_notices WHERE search_profile_id = %s", (profile_id,))).fetchall()
    return {r["listing_id"] for r in rows}


async def claim(profile_id: int, user_id: str, listing_id: int, distance_km: float, radius_km: float) -> int | None:
    """A 'pending' notice for this search and listing; None if it already has one."""
    async with connection() as cx:
        row = await (await cx.execute(
            "INSERT INTO near_zone_notices (search_profile_id, user_id, listing_id, distance_km, radius_km) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (search_profile_id, listing_id) DO NOTHING RETURNING id",
            (profile_id, user_id, listing_id, distance_km, radius_km))).fetchone()
    return row["id"] if row else None


async def mark(notice_id: int, *, sent: bool, error: str | None = None) -> None:
    async with connection() as cx:
        await cx.execute(
            "UPDATE near_zone_notices SET status = %s, error = %s, sent_at = CASE WHEN %s THEN now() END "
            " WHERE id = %s AND status = 'pending'",
            ("sent" if sent else "failed", None if sent else (error or "")[:300], sent, notice_id))
