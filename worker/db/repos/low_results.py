"""search_diagnoses: the bot de pocos resultados (pipeline/low_results.py)."""
from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from db.pool import connection

# What a search shows today, whatever the level: matches of active listings
# the user didn't discard (search_result_counts' «Todos» minus the gone ones).
_RESULTS = ("(SELECT count(*) FROM matches m JOIN listings l ON l.id = m.listing_id "
            "   LEFT JOIN user_listing_interactions i ON i.user_id = sp.user_id AND i.listing_id = m.listing_id "
            "  WHERE m.search_profile_id = sp.id AND l.status = 'active' "
            "    AND coalesce(i.status::text, 'new') <> 'discarded')::int")


async def candidates(*, max_results: int, min_age_hours: float) -> list[dict[str, Any]]:
    """Enabled searches with access, prepared (bootstrapped, no rematch pending),
    older than `min_age_hours`, with `max_results` results or fewer; never
    diagnosed first, then the oldest diagnoses."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM ("
            " SELECT sp.id, sp.user_id::text AS user_id, sp.name, sp.filters, sp.preferences, "
            "        sp.origin_lat, sp.origin_lon, sp.radius_km, sp.channels, "
            "        p.telegram_chat_id, p.email, p.email_unsubscribe_token::text AS unsubscribe_token, "
            "        " + _RESULTS + " AS result_count, "
            "        d.fingerprint, d.created_at AS diagnosed_at, d.notified_fingerprint "
            "   FROM search_profiles sp JOIN profiles p ON p.id = sp.user_id "
            "   LEFT JOIN search_diagnoses d ON d.search_profile_id = sp.id "
            "  WHERE sp.enabled AND public.search_access_active(sp.id) "
            "    AND sp.bootstrapped_at IS NOT NULL AND sp.rematch_requested_at IS NULL "
            "    AND sp.created_at <= now() - make_interval(secs => %s)"
            ") x WHERE result_count <= %s "
            "ORDER BY diagnosed_at NULLS FIRST, id",
            (min_age_hours * 3600, max_results))).fetchall()


async def clear_resolved() -> int:
    """Diagnoses of searches that now show more than their threshold."""
    async with connection() as cx:
        cur = await cx.execute(
            "DELETE FROM search_diagnoses d USING search_profiles sp "
            " WHERE sp.id = d.search_profile_id AND " + _RESULTS + " > d.max_results")
        return cur.rowcount


async def save(row: dict[str, Any]) -> None:
    """Insert or replace a search's diagnosis. A new fingerprint shows the
    card again (dismissed_at cleared); the same one keeps the notice state."""
    async with connection() as cx:
        await cx.execute(
            "INSERT INTO search_diagnoses (search_profile_id, user_id, fingerprint, result_count, max_results, "
            "  funnel, explanation, suggestions, provider, llm_error) "
            "VALUES (%(id)s, %(user_id)s, %(fingerprint)s, %(result_count)s, %(max_results)s, %(funnel)s, "
            "  %(explanation)s, %(suggestions)s, %(provider)s, %(llm_error)s) "
            "ON CONFLICT (search_profile_id) DO UPDATE SET "
            "  fingerprint = EXCLUDED.fingerprint, result_count = EXCLUDED.result_count, "
            "  max_results = EXCLUDED.max_results, funnel = EXCLUDED.funnel, "
            "  explanation = EXCLUDED.explanation, suggestions = EXCLUDED.suggestions, "
            "  provider = EXCLUDED.provider, llm_error = EXCLUDED.llm_error, created_at = now(), "
            "  dismissed_at = CASE WHEN search_diagnoses.fingerprint = EXCLUDED.fingerprint "
            "                      THEN search_diagnoses.dismissed_at END",
            {**row, "funnel": Jsonb(row["funnel"]), "suggestions": Jsonb(row["suggestions"])})


async def mark_notified(profile_id: int, fingerprint: str) -> None:
    async with connection() as cx:
        await cx.execute("UPDATE search_diagnoses SET notified_at = now(), notified_fingerprint = %s "
                         " WHERE search_profile_id = %s", (fingerprint, profile_id))
