"""matches: one row per (profile, listing) that matched, with its score.

A match row also means the profile already considered that listing (the
bot's "already seen" set). Since F2 rows carry the 0–100 score, level,
breakdown, reasons, price_ref and red flags (intelligence/engine.py), and
since F4 the seller questions the web copies (§25). Rows written before F2
(the SQLite migration, `mark_seen`) keep placeholder scoring with
scoring_version = 'legacy-v0'; a scoring_version other than the current one
is re-scored (sección 6.1). Bootstrap and migrated rows are is_backfill = true.
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


_EVALUATED = ("score", "level", "score_breakdown", "match_reasons", "price_ref", "red_flags",
              "seller_questions", "scoring_version")


async def upsert_scored(cx: AsyncConnection, profile_id: int,
                        rows: list[tuple[int, dict[str, Any]]], *, backfill: bool) -> dict[int, int]:
    """Write (listing_id, Evaluation.row()) pairs. New rows get `backfill`;
    existing ones are re-scored and keep is_backfill and generated_at.
    Returns {listing_id: match_id} of the rows that were inserted (new matches)."""
    if not rows:
        return {}
    inserted: dict[int, int] = {}
    for listing_id, row in rows:
        # seller_questions is optional (rows built before F4 stored it).
        values = [Jsonb(row[c]) if c in ("score_breakdown", "match_reasons", "red_flags")
                  or (c == "price_ref" and row[c] is not None) else row.get(c) for c in _EVALUATED]
        rec = await (await cx.execute(
            "INSERT INTO matches (search_profile_id, listing_id, is_backfill, "
            f"                     {', '.join(_EVALUATED)}) "
            f"VALUES (%s, %s, %s, {', '.join(['%s'] * len(_EVALUATED))}) "
            "ON CONFLICT (search_profile_id, listing_id) DO UPDATE SET "
            + ", ".join(f"{c} = excluded.{c}" for c in _EVALUATED) +
            " RETURNING id, (xmax = 0) AS inserted",
            (profile_id, listing_id, backfill, *values))).fetchone()
        if rec["inserted"]:
            inserted[listing_id] = rec["id"]
    return inserted


async def rescore_queue(*, days: int, scoring_version: str,
                        outdated_only: bool = False) -> list[dict[str, Any]]:
    """(match_id, search_profile_id, listing_id) to re-score (sección 6.1): the
    matches of active listings seen in the last `days` (the median moves), and
    every match scored by another scoring_version."""
    recent = "" if outdated_only else (
        " OR l.last_seen_at >= now() - make_interval(days => %(days)s)")
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT m.id, m.search_profile_id, m.listing_id FROM matches m "
            "  JOIN listings l ON l.id = m.listing_id "
            "  JOIN search_profiles sp ON sp.id = m.search_profile_id "
            " WHERE l.status = 'active' AND sp.enabled "
            f"  AND (m.scoring_version <> %(version)s{recent}) "
            " ORDER BY m.search_profile_id, m.listing_id",
            {"days": days, "version": scoring_version})).fetchall()


async def matches_of_listings(listing_ids: Iterable[int]) -> list[dict[str, Any]]:
    """(match_id, search_profile_id, listing_id) of these listings (re-score after enrichment)."""
    ids = list(dict.fromkeys(listing_ids))
    if not ids:
        return []
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT m.id, m.search_profile_id, m.listing_id FROM matches m "
            "  JOIN search_profiles sp ON sp.id = m.search_profile_id "
            " WHERE m.listing_id = ANY(%s) AND sp.enabled "
            " ORDER BY m.search_profile_id, m.listing_id", (ids,))).fetchall()
