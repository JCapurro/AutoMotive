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
from normalization.description_facts import PARTIAL_KINDS


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
              "seller_questions", "contact_questions", "scoring_version", "margin_ref")
# PAR-04: written only where the migration added the column (checked once per process).
_QUESTION_ORIGINS = "question_origins"
_has_question_origins: bool | None = None


async def _evaluated_columns(cx: AsyncConnection) -> tuple[str, ...]:
    global _has_question_origins
    if _has_question_origins is None:
        row = await (await cx.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' "
            "  AND table_name = 'matches' AND column_name = %s) AS ok", (_QUESTION_ORIGINS,))).fetchone()
        _has_question_origins = bool(row and row["ok"])
    return _EVALUATED + ((_QUESTION_ORIGINS,) if _has_question_origins else ())


def forget_columns() -> None:
    """Tests: check the columns again."""
    global _has_question_origins
    _has_question_origins = None


async def upsert_scored(cx: AsyncConnection, profile_id: int,
                        rows: list[tuple[int, dict[str, Any]]], *, backfill: bool) -> dict[int, int]:
    """Write (listing_id, Evaluation.row()) pairs. New rows get `backfill`;
    existing ones are re-scored and keep is_backfill and generated_at.
    Returns {listing_id: match_id} of the rows that were inserted (new matches)."""
    if not rows:
        return {}
    inserted: dict[int, int] = {}
    columns = await _evaluated_columns(cx)
    for listing_id, row in rows:
        # seller_questions, contact_questions (PRO-01), margin_ref (PRO-02) and
        # question_origins (PAR-04) are optional.
        values = [Jsonb(row[c]) if c in ("score_breakdown", "match_reasons", "red_flags")
                  or (c in ("price_ref", "margin_ref", _QUESTION_ORIGINS) and row.get(c) is not None) else row.get(c)
                  for c in columns]
        rec = await (await cx.execute(
            "INSERT INTO matches (search_profile_id, listing_id, is_backfill, "
            f"                     {', '.join(columns)}) "
            f"VALUES (%s, %s, %s, {', '.join(['%s'] * len(columns))}) "
            "ON CONFLICT (search_profile_id, listing_id) DO UPDATE SET "
            + ", ".join(f"{c} = excluded.{c}" for c in columns) +
            " RETURNING id, (xmax = 0) AS inserted",
            (profile_id, listing_id, backfill, *values))).fetchone()
        if rec and rec["inserted"]:
            inserted[listing_id] = rec["id"]
    return inserted


async def delete_matches(cx: AsyncConnection, profile_id: int, listing_ids: list[int]) -> int:
    """Delete this profile's matches of these listings (they no longer fit it).
    Their notifications keep the row with match_id null (ON DELETE SET NULL)."""
    if not listing_ids:
        return 0
    cur = await cx.execute(
        "DELETE FROM matches WHERE search_profile_id = %s AND listing_id = ANY(%s)",
        (profile_id, listing_ids))
    return cur.rowcount


# PRO-02: a match that should have a margin_ref and has none (stored before
# margin_ref existed; SCORING_VERSION was not bumped). It mirrors every case
# where intelligence/margin.compute returns None: a price_ref without
# dealer_n (before the seller split), enough dealers but a median <= 0 or a
# price outside plausible_ratio x the median (margin.plausible_price, the
# same bounds and slack), no price in USD, and a published price that is a down payment or an
# installment (pipeline.ingest.published_partial: such a listing still
# matches when the description gave its cash price). Fewer dealers than
# min_n do get one ({status: few_dealers}). Re-scoring a row that passes
# either fills margin_ref or writes a price_ref that fails it, so the fill
# converges and re-scoring sends no alert.
WITHOUT_MARGIN = ("(m.margin_ref IS NULL AND l.price_usd > 0 "
                  " AND (m.price_ref->>'dealer_n')::int IS NOT NULL "
                  " AND ((m.price_ref->>'dealer_n')::int < %(min_n)s "
                  "      OR ((m.price_ref->>'dealer_median')::numeric > 0 "
                  "          AND round(l.price_usd, 2) BETWEEN "
                  "              %(ratio_min)s * (m.price_ref->>'dealer_median')::numeric - %(eps)s "
                  "          AND %(ratio_max)s * (m.price_ref->>'dealer_median')::numeric + %(eps)s)) "
                  " AND NOT coalesce(l.price_partial, false) "
                  " AND l.description_facts #> '{price_check,published_partial}' IS DISTINCT FROM 'true'::jsonb "
                  " AND NOT coalesce(l.description_facts #>> '{price_check,published_kind}' = ANY(%(partial_kinds)s),"
                  "                  false))")

# PRO-02: a stored margin whose price is implausible (margin.plausible): the
# rows written before the guard (185 in production, almost all Facebook) and
# any written under looser bounds. Re-scoring writes margin_ref = null (or a
# plausible one if the price or the median moved), which then fails both
# this and WITHOUT_MARGIN: the queue converges and, as every re-score, sends
# no alert. Until then the worker's alerts and the web hide them.
#
# Outside either of two bounds: the config's (a tighter config drops it) and
# the ref's own, or PLAUSIBLE_RATIO for a ref from before the guard, which is
# what margin.plausible and the web hide by (with a looser config, a hidden
# old ref would otherwise stay hidden and never be recomputed). A recomputed
# ref stores the config's bounds as its own, so it fails both and leaves.
_OWN = "coalesce((m.margin_ref #>> '{plausible_ratio,%s}')::numeric, %%(default_%s)s)"
IMPLAUSIBLE_MARGIN = ("(coalesce(m.margin_ref->>'status', 'ok') = 'ok' "
                      " AND (m.margin_ref->>'dealer_median')::numeric > 0 "
                      " AND ((m.margin_ref->>'asking_usd')::numeric NOT BETWEEN "
                      "      %(ratio_min)s * (m.margin_ref->>'dealer_median')::numeric - %(eps)s "
                      "  AND %(ratio_max)s * (m.margin_ref->>'dealer_median')::numeric + %(eps)s "
                      "   OR (m.margin_ref->>'asking_usd')::numeric NOT BETWEEN "
                      f"     {_OWN % ('min', 'min')} * (m.margin_ref->>'dealer_median')::numeric - %(eps)s "
                      f" AND {_OWN % ('max', 'max')} * (m.margin_ref->>'dealer_median')::numeric + %(eps)s))")


async def rescore_queue(*, days: int, scoring_version: str, min_n: int | None = None,
                        plausible_ratio: dict[str, float] | None = None,
                        outdated_only: bool = False) -> list[dict[str, Any]]:
    """(match_id, search_profile_id, listing_id) to re-score (sección 6.1): the
    matches of active listings seen in the last `days` (the median moves),
    every match scored by another scoring_version, and (PRO-02) those with
    dealer comparables counted and no margin_ref yet (WITHOUT_MARGIN) or a
    margin for an implausible price (IMPLAUSIBLE_MARGIN). `plausible_ratio`:
    app_config.dealer_margin's (margin.parse_config), the default without it."""
    from intelligence import margin
    if min_n is None:
        from intelligence.config import DEFAULT_COMPARABLES
        min_n = int(DEFAULT_COMPARABLES["min_n"])
    ratio = margin.parse_ratio(plausible_ratio)
    recent = "" if outdated_only else (
        " OR l.last_seen_at >= now() - make_interval(days => %(days)s)")
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT m.id, m.search_profile_id, m.listing_id FROM matches m "
            "  JOIN listings l ON l.id = m.listing_id "
            "  JOIN search_profiles sp ON sp.id = m.search_profile_id "
            " WHERE l.status = 'active' AND public.search_access_active(sp.id) "
            f"  AND (m.scoring_version <> %(version)s OR {WITHOUT_MARGIN} OR {IMPLAUSIBLE_MARGIN}{recent}) "
            " ORDER BY m.search_profile_id, m.listing_id",
            {"days": days, "version": scoring_version, "min_n": min_n,
             "partial_kinds": sorted(PARTIAL_KINDS), "ratio_min": ratio["min"], "ratio_max": ratio["max"],
             "default_min": margin.PLAUSIBLE_RATIO["min"], "default_max": margin.PLAUSIBLE_RATIO["max"],
             "eps": margin.PLAUSIBLE_EPS})).fetchall()


async def matches_of_profile(profile_id: int) -> list[dict[str, Any]]:
    """(match_id, search_profile_id, listing_id) of this profile's active listings
    (an edited search re-checks the ones its backfill didn't score again)."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT m.id, m.search_profile_id, m.listing_id FROM matches m "
            "  JOIN listings l ON l.id = m.listing_id "
            " WHERE m.search_profile_id = %s AND l.status = 'active' "
            " ORDER BY m.listing_id", (profile_id,))).fetchall()


async def matches_of_listings(listing_ids: Iterable[int]) -> list[dict[str, Any]]:
    """(match_id, search_profile_id, listing_id) of these listings (re-score after enrichment)."""
    ids = list(dict.fromkeys(listing_ids))
    if not ids:
        return []
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT m.id, m.search_profile_id, m.listing_id FROM matches m "
            "  JOIN search_profiles sp ON sp.id = m.search_profile_id "
            " WHERE m.listing_id = ANY(%s) AND public.search_access_active(sp.id) "
            " ORDER BY m.search_profile_id, m.listing_id", (ids,))).fetchall()
