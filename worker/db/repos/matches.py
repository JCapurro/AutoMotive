"""matches, used in F0 as the bot's "already seen" set.

A match row means the profile already considered that listing. Until the
0–100 score exists (F2) rows carry placeholder scoring with
scoring_version = 'legacy-v0'; a new scoring_version re-scores everything
(sección 6.1). Bootstrap and migrated rows are is_backfill = true.
"""
from __future__ import annotations

from typing import Any, Iterable

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from db.pool import connection


LEGACY_SCORING_VERSION = "legacy-v0"

Key = tuple[str, str]


def _keys(items: Iterable[dict]) -> list[Key]:
    return list(dict.fromkeys((it["source"], str(it["listing_id"])) for it in items))


async def _existing(profile_id: int, keys: list[Key], *, other_profiles: bool) -> set[Key]:
    if not keys:
        return set()
    if other_profiles:
        scope = ("m.search_profile_id IN (SELECT o.id FROM search_profiles o "
                 "  JOIN search_profiles me ON me.user_id = o.user_id "
                 "  WHERE me.id = %s AND o.id <> me.id)")
    else:
        scope = "m.search_profile_id = %s"
    sql = (
        "SELECT l.source, l.external_id FROM matches m "
        "  JOIN listings l ON l.id = m.listing_id "
        f"WHERE {scope} "
        "  AND (l.source, l.external_id) IN (SELECT * FROM unnest(%s::text[], %s::text[]))"
    )
    async with connection() as cx:
        rows = await (await cx.execute(
            sql, (profile_id, [k[0] for k in keys], [k[1] for k in keys]),
        )).fetchall()
    return {(r["source"], r["external_id"]) for r in rows}


async def filter_unseen(alert_id: int, items: Iterable[dict]) -> list[dict]:
    """Items this profile has no match for yet."""
    items = list(items)
    seen = await _existing(alert_id, _keys(items), other_profiles=False)
    return [it for it in items if (it["source"], str(it["listing_id"])) not in seen]


async def matched_by_other_profiles(alert_id: int, items: Iterable[dict]) -> set[Key]:
    """(source, listing_id) keys another profile of the same user already has.
    A wizard alert for two models becomes two profiles; this keeps a listing
    that both return from alerting twice (one notification per user, sección 7.1)."""
    return await _existing(alert_id, _keys(items), other_profiles=True)


async def insert_legacy_matches(cx: AsyncConnection, profile_id: int, keys: list[Key], *,
                                backfill: bool,
                                price_refs: dict[Key, dict] | None = None) -> int:
    if not keys:
        return 0
    refs = [Jsonb(price_refs[k]) if price_refs and k in price_refs else None for k in keys]
    cur = await cx.execute(
        "INSERT INTO matches (search_profile_id, listing_id, score, level, score_breakdown, "
        "                     match_reasons, price_ref, is_backfill, scoring_version) "
        "SELECT %s, l.id, 0, 'low', '{}', '{}', v.price_ref, %s, %s "
        "  FROM unnest(%s::text[], %s::text[], %s::jsonb[]) AS v (source, external_id, price_ref) "
        "  JOIN listings l ON l.source = v.source AND l.external_id = v.external_id "
        "ON CONFLICT (search_profile_id, listing_id) DO NOTHING",
        (profile_id, backfill, LEGACY_SCORING_VERSION,
         [k[0] for k in keys], [k[1] for k in keys], refs),
    )
    return cur.rowcount


async def mark_seen(alert_id: int, items: Iterable[dict], *, backfill: bool = False,
                    price_refs: dict[Key, dict[str, Any]] | None = None) -> None:
    """Record that the profile considered these listings. They must already
    be in `listings` (the scheduler upserts before marking)."""
    keys = _keys(items)
    if not keys:
        return
    async with connection() as cx:
        await insert_legacy_matches(cx, alert_id, keys, backfill=backfill, price_refs=price_refs)
