"""notifications: the log of every alert (§21–22, sección 7).

One row per (decision, channel). Status: 'queued' (to send now), 'digest'
(waits for the daily summary), 'sent', 'failed'. The engine decides
(notifications/engine.py); this module reads who to notify and writes rows.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from db.pool import connection


_CONTACT = "p.telegram_chat_id, p.email, p.email_unsubscribe_token::text AS unsubscribe_token "


async def profile_audiences(profile_ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    """Search profiles with their notification settings and the user's contacts."""
    ids = list(dict.fromkeys(profile_ids))
    if not ids:
        return {}
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT sp.id AS profile_id, sp.name AS profile_name, sp.user_id, "
            "       public.effective_search_frequency(sp.user_id, sp.notification_frequency)::text AS frequency, "
            "       sp.notify_min_level::text AS min_level, sp.channels, " + _CONTACT +
            "  FROM search_profiles sp JOIN profiles p ON p.id = sp.user_id "
            " WHERE sp.id = ANY(%s) AND public.search_access_active(sp.id)", (ids,))).fetchall()
    return {r["profile_id"]: r for r in rows}


async def interactions(pairs: Iterable[tuple[str, int]]) -> dict[tuple[str, int], dict[str, Any]]:
    """(user_id, listing_id) → {saved, status}."""
    pairs = list(dict.fromkeys(pairs))
    if not pairs:
        return {}
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT i.user_id::text AS user_id, i.listing_id, i.saved, i.status::text AS status "
            "  FROM user_listing_interactions i "
            "  JOIN unnest(%s::uuid[], %s::bigint[]) AS k (user_id, listing_id) "
            "    ON k.user_id = i.user_id AND k.listing_id = i.listing_id",
            ([p[0] for p in pairs], [p[1] for p in pairs]))).fetchall()
    return {(r["user_id"], r["listing_id"]): r for r in rows}


async def listing_audiences(listing_ids: Iterable[int]) -> list[dict[str, Any]]:
    """Everyone a listing event concerns (price_drop, listing_gone): users with
    an enabled profile that matched it (their best match: highest level, then
    score) and users who saved or follow it. One row per (user, listing)."""
    ids = list(dict.fromkeys(listing_ids))
    if not ids:
        return []
    async with connection() as cx:
        return await (await cx.execute(
            "WITH best AS ( "
            "  SELECT DISTINCT ON (sp.user_id, m.listing_id) sp.user_id, m.listing_id, "
            "         m.id AS match_id, m.level::text AS level, m.score, m.price_ref, m.red_flags, "
            "         sp.id AS profile_id, sp.name AS profile_name, "
            "         public.effective_search_frequency(sp.user_id, sp.notification_frequency)::text AS frequency, "
            "         sp.notify_min_level::text AS min_level, sp.channels "
            "    FROM matches m JOIN search_profiles sp ON sp.id = m.search_profile_id "
            "   WHERE m.listing_id = ANY(%(ids)s) AND public.search_access_active(sp.id) "
            "   ORDER BY sp.user_id, m.listing_id, m.level, m.score DESC "
            "), ix AS ( "
            "  SELECT user_id, listing_id, saved, status::text AS status "
            "    FROM user_listing_interactions WHERE listing_id = ANY(%(ids)s) "
            ") "
            "SELECT coalesce(best.user_id, ix.user_id)::text AS user_id, "
            "       coalesce(best.listing_id, ix.listing_id) AS listing_id, "
            "       best.match_id, best.level, best.score, best.price_ref, best.red_flags, "
            "       best.profile_id, best.profile_name, "
            "       coalesce(best.frequency, public.effective_search_frequency(p.id, 'immediate')::text) AS frequency, "
            "       coalesce(best.min_level, 'good') AS min_level, "
            "       coalesce(best.channels, "
            "                (SELECT array_agg(DISTINCT c) FROM search_profiles o, unnest(o.channels) c "
            "                  WHERE o.user_id = coalesce(best.user_id, ix.user_id) AND public.search_access_active(o.id)), "
            "                '{telegram,web}') AS channels, "
            "       coalesce(ix.saved, false) AS saved, ix.status, " + _CONTACT +
            "  FROM best FULL JOIN ix ON ix.user_id = best.user_id AND ix.listing_id = best.listing_id "
            "  JOIN profiles p ON p.id = coalesce(best.user_id, ix.user_id) "
            " WHERE public.commercial_access_active(p.id)",
            {"ids": ids})).fetchall()


async def existing_keys(user_ids: Iterable[str], listing_ids: Iterable[int]) -> set[tuple[str, str]]:
    """(user_id, dedupe_key) already notified for these users and listings."""
    users, listings = list(dict.fromkeys(user_ids)), list(dict.fromkeys(listing_ids))
    if not users or not listings:
        return set()
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT DISTINCT user_id::text AS user_id, dedupe_key FROM notifications "
            " WHERE user_id = ANY(%s::uuid[]) AND listing_id = ANY(%s)", (users, listings))).fetchall()
    return {(r["user_id"], r["dedupe_key"]) for r in rows}


async def sent_today(user_ids: Iterable[str], since: datetime) -> dict[str, int]:
    """Immediate alerts per user since `since` (the start of the day, ART):
    distinct dedupe keys, so one alert on three channels counts once."""
    users = list(dict.fromkeys(user_ids))
    if not users:
        return {}
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT user_id::text AS user_id, count(DISTINCT dedupe_key) AS n FROM notifications "
            " WHERE user_id = ANY(%s::uuid[]) AND created_at >= %s AND kind <> 'digest' "
            "   AND status IN ('queued', 'sent', 'failed') GROUP BY user_id", (users, since))).fetchall()
    return {r["user_id"]: r["n"] for r in rows}


async def insert_decisions(decisions: Iterable[Any]) -> list[int]:
    """Insert engine Decisions; a (user, channel, dedupe_key) already there is
    skipped (§15). Returns the new ids."""
    ids: list[int] = []
    async with connection() as cx:
        for d in decisions:
            row = await (await cx.execute(
                "INSERT INTO notifications (user_id, match_id, listing_id, search_profile_id, kind, "
                "                           channel, status, dedupe_key, payload) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (user_id, channel, dedupe_key) DO NOTHING RETURNING id",
                (d.user_id, d.match_id, d.listing_id, d.profile_id, d.kind, d.channel, d.status,
                 d.dedupe_key, Jsonb(d.payload)))).fetchone()
            if row:
                ids.append(row["id"])
    return ids


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

async def queued(limit: int = 200) -> list[dict[str, Any]]:
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT n.id, n.user_id::text AS user_id, n.kind::text AS kind, "
            "       n.channel::text AS channel, n.payload, n.listing_id, n.created_at, n.attempts, "
            + _CONTACT +
            "  FROM notifications n JOIN profiles p ON p.id = n.user_id "
            " WHERE n.status = 'queued' ORDER BY n.id LIMIT %s", (limit,))).fetchall()


async def prepare_delivery(notification_id: int) -> bool:
    """Check the current access just before dispatch, including an already queued alert."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT public.prepare_notification_delivery(%s) AS allowed", (notification_id,))).fetchone()
    return bool(row and row["allowed"])


async def mark_sent(notification_id: int, *, provider_id: str | None = None,
                    extra: dict[str, Any] | None = None) -> None:
    delivery = {"provider_id": provider_id} if provider_id else {}
    async with connection() as cx:
        row = await (await cx.execute(
            "UPDATE notifications SET status = 'sent', sent_at = now(), error = NULL, "
            "       attempts = attempts + 1, payload = payload || %s "
            " WHERE id = %s RETURNING user_id, kind::text AS kind, channel::text AS channel, "
            "       listing_id, payload->'match'->>'level' AS level",
            (Jsonb({**(extra or {}), **({"delivery": delivery} if delivery else {})}),
             notification_id))).fetchone()
        if row:
            await insert_event(cx, row["user_id"], "alert_sent", {
                "notification_id": notification_id, "kind": row["kind"], "channel": row["channel"],
                "listing_id": row["listing_id"], "level": row["level"]})


async def mark_retry(notification_id: int, error: str) -> None:
    async with connection() as cx:
        await cx.execute("UPDATE notifications SET attempts = attempts + 1, error = %s WHERE id = %s",
                         (error, notification_id))


async def mark_failed(notification_id: int, error: str) -> None:
    async with connection() as cx:
        await cx.execute("UPDATE notifications SET status = 'failed', attempts = attempts + 1, "
                         "  error = %s WHERE id = %s", (error, notification_id))


async def insert_event(cx: AsyncConnection, user_id: Any, name: str, props: dict[str, Any]) -> None:
    await cx.execute("INSERT INTO events (user_id, name, props) VALUES (%s, %s, %s)",
                     (user_id, name, Jsonb(props)))


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------

async def digest_users(since: datetime) -> list[dict[str, Any]]:
    """Users with something for the digest: rows waiting for it, or new
    (non-backfill) matches since `since`. With their channels (the union over
    their enabled profiles) and contacts."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT p.id::text AS user_id, " + _CONTACT + ", "
            "       coalesce((SELECT array_agg(DISTINCT c) FROM search_profiles sp, unnest(sp.channels) c "
            "                  WHERE sp.user_id = p.id AND public.search_access_active(sp.id)), '{}') AS channels "
            "  FROM profiles p "
            " WHERE public.commercial_access_active(p.id) AND (EXISTS (SELECT 1 FROM notifications n WHERE n.user_id = p.id "
            "                  AND n.status = 'digest' AND n.digested_in IS NULL) "
            "    OR EXISTS (SELECT 1 FROM matches m JOIN search_profiles sp ON sp.id = m.search_profile_id "
            "                WHERE sp.user_id = p.id AND public.search_access_active(sp.id) AND NOT m.is_backfill "
            "                  AND m.generated_at >= %s)) "
            " ORDER BY p.id", (since,))).fetchall()


async def pending_digest(user_id: str, channel: str) -> list[dict[str, Any]]:
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT id, kind::text AS kind, listing_id, match_id, payload FROM notifications "
            " WHERE user_id = %s AND channel::text = %s AND status = 'digest' AND digested_in IS NULL "
            "   AND public.notification_access_active(user_id, search_profile_id, listing_id) "
            "   AND (kind NOT IN ('new_match','opportunity') OR public.search_access_active(search_profile_id)) "
            " ORDER BY id", (user_id, channel))).fetchall()


async def top_matches(user_id: str, channel: str, since: datetime, limit: int) -> list[dict[str, Any]]:
    """The user's best new matches since `since` on profiles that use this
    channel, whatever their level (below notify_min_level they are only seen
    in the web and here, sección 7.1), skipping listings already alerted on
    the channel and the ones the user discarded. One row per listing."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM ( "
            "  SELECT DISTINCT ON (m.listing_id) m.id AS match_id, m.listing_id, m.score, "
            "         m.level::text AS level, m.price_ref, m.red_flags, sp.name AS profile_name "
            "    FROM matches m "
            "    JOIN search_profiles sp ON sp.id = m.search_profile_id "
            "    JOIN listings l ON l.id = m.listing_id "
            "   WHERE sp.user_id = %(user)s AND public.search_access_active(sp.id) AND %(channel)s = ANY(sp.channels) "
            "     AND NOT m.is_backfill AND m.generated_at >= %(since)s AND l.status = 'active' "
            "     AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.user_id = sp.user_id "
            "                        AND n.channel::text = %(channel)s AND n.listing_id = m.listing_id "
            "                        AND n.kind IN ('new_match', 'opportunity')) "
            "     AND NOT EXISTS (SELECT 1 FROM user_listing_interactions i WHERE i.user_id = sp.user_id "
            "                        AND i.listing_id = m.listing_id AND i.status = 'discarded') "
            "   ORDER BY m.listing_id, m.score DESC "
            ") t ORDER BY score DESC, listing_id LIMIT %(limit)s",
            {"user": user_id, "channel": channel, "since": since, "limit": limit})).fetchall()


async def insert_digest(user_id: str, channel: str, day: str, payload: dict[str, Any],
                        attach: list[int]) -> int | None:
    """The day's digest for (user, channel), queued, and the rows it carries
    attached to it. None if that day's digest already exists."""
    async with connection() as cx:
        row = await (await cx.execute(
            "INSERT INTO notifications (user_id, kind, channel, status, dedupe_key, payload) "
            "VALUES (%s, 'digest', %s, 'queued', %s, %s) "
            "ON CONFLICT (user_id, channel, dedupe_key) DO NOTHING RETURNING id",
            (user_id, channel, f"digest:{day}", Jsonb(payload)))).fetchone()
        if row is None:
            return None
        if attach:
            await cx.execute("UPDATE notifications SET digested_in = %s WHERE id = ANY(%s)",
                             (row["id"], attach))
        return row["id"]


# ---------------------------------------------------------------------------
# Telegram inline actions and click tracking
# ---------------------------------------------------------------------------

async def apply_telegram_action(notification_id: int, telegram_user_id: int,
                                action: str) -> dict[str, Any] | None:
    """⭐ Me interesa / ✖ Descartar from a Telegram alert. Only the owner of
    the notification can act on it. Sets the listing's status (never
    downgrading contacted / visit_scheduled / purchased), marks the alert
    opened and records the events. Returns the notification, or None."""
    status = {"interested": "interested", "discarded": "discarded"}[action]
    async with connection() as cx:
        n = await (await cx.execute(
            "SELECT n.id, n.user_id, n.listing_id, n.kind::text AS kind, n.channel::text AS channel "
            "  FROM notifications n JOIN profiles p ON p.id = n.user_id "
            " WHERE n.id = %s AND p.telegram_user_id = %s", (notification_id, telegram_user_id))).fetchone()
        if n is None or n["listing_id"] is None:
            return None
        await cx.execute(
            "INSERT INTO user_listing_interactions (user_id, listing_id, status) VALUES (%s, %s, %s) "
            "ON CONFLICT (user_id, listing_id) DO UPDATE SET status = excluded.status "
            " WHERE user_listing_interactions.status IN ('new', 'seen', 'interested', 'discarded')",
            (n["user_id"], n["listing_id"], status))
        await cx.execute("UPDATE notifications SET opened_at = coalesce(opened_at, now()) WHERE id = %s",
                         (notification_id,))
        props = {"listing_id": n["listing_id"], "status": status, "via": "telegram",
                 "notification_id": notification_id}
        await insert_event(cx, n["user_id"], "listing_status_changed", props)
        if status == "discarded":
            await insert_event(cx, n["user_id"], "listing_discarded", {**props, "reason": None})
    return n


async def track_click(notification_id: int, to: str, listing_id: int | None = None) -> dict[str, Any] | None:
    """public.track_notification_click: records the click, returns {listing_id, url}."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM track_notification_click(%s, %s, %s)",
            (notification_id, to, listing_id))).fetchone()


async def peek_click(notification_id: int, listing_id: int | None = None) -> dict[str, Any] | None:
    """Where /r/<id> leads, without recording a click (HEAD, link previews)."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT l.id AS listing_id, l.url FROM notifications n "
            "  JOIN listings l ON l.id = coalesce(%s, n.listing_id) "
            " WHERE n.id = %s AND (%s::bigint IS NULL OR %s = n.listing_id OR EXISTS ( "
            "   SELECT 1 FROM jsonb_array_elements(coalesce(n.payload->'items', '[]')) i "
            "    WHERE (i->>'listing_id')::bigint = %s))",
            (listing_id, notification_id, listing_id, listing_id, listing_id))).fetchone()
