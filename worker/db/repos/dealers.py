"""Agencias (docs/superpowers/specs/2026-11-18-agencias-design.md §4.5): the
worker's SQL for dealers, their stock items and their leads. Service role.

Every SQL of the dealer program lives here, in pipeline/dealers.py and in the
few predicates of §4.3 (rows_for_scoring, recent_active, top_matches,
_DUPLICATES), which take `visible()` from this module.

The schema arrives with migration 20261228120000_dealer_program.sql. A
worker running before it is applied must keep working as today, so
`schema_ready()` (asked once per process, like listings.duplicates_table)
gates every query that names a dealer column or function.

Logs and errors carry ids only: never a buyer's name, phone or message.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from psycopg import AsyncConnection
from psycopg.types.json import Jsonb

from db.pool import connection

DEALER_SOURCE = "directo"

# Whether the dealer schema exists in this database (None: not asked yet).
_ready: bool | None = None


async def schema_ready(cx: AsyncConnection) -> bool:
    global _ready
    if _ready is None:
        row = await (await cx.execute(
            "SELECT to_regclass('public.dealers') IS NOT NULL "
            "   AND to_regprocedure('public.dealer_listing_hidden(text, bigint, text, timestamptz)') IS NOT NULL "
            "   AS ok")).fetchone()
        _ready = bool(row["ok"])
    return _ready


async def ready() -> bool:
    """schema_ready() for callers without a connection at hand (one only the first time)."""
    if _ready is not None:
        return _ready
    async with connection() as cx:
        return await schema_ready(cx)


def reset_schema_cache() -> None:
    """Tests that switch databases ask again."""
    global _ready, _phase1
    _ready = None
    _phase1 = None


# Fase 1 (20261229120000_dealer_phase1_extras.sql): alerts and stock reads.
_phase1: bool | None = None


async def phase1_ready() -> bool:
    """Whether the phase 1 tables exist (a worker can run before that migration)."""
    global _phase1
    if _phase1 is None:
        async with connection() as cx:
            row = await (await cx.execute(
                "SELECT to_regclass('public.dealer_alerts') IS NOT NULL "
                "   AND to_regclass('public.dealer_stock_reads') IS NOT NULL "
                "   AND to_regprocedure('public.dealer_alert_scan(bigint, numeric, numeric)') IS NOT NULL AS ok")
            ).fetchone()
            _phase1 = bool(row["ok"])
    return _phase1


def visible(alias: str) -> str:
    """The SQL twin of intelligence.dealer.hidden_reason(...) is None for the
    listing `alias` (§2, point 4). The `or` short-circuits before calling the
    function for an ordinary listing, so nothing changes without dealer rows."""
    a = alias
    return (f"(({a}.dealer_id IS NULL AND {a}.source <> '{DEALER_SOURCE}') OR public.dealer_listing_hidden("
            f"{a}.source, {a}.dealer_id, {a}.dealer_status, {a}.dealer_confirmed_at) IS NULL)")


# ---------------------------------------------------------------------------
# Step 1: the sweep
# ---------------------------------------------------------------------------

async def sync_approvals() -> int:
    """dealers.approved_at from the plans (20270104120000_dealer_auto_approval.sql): on while a member
    has Pro active, off when none does. 0 before that migration: the approval is then still by hand."""
    async with connection() as cx:
        row = await (await cx.execute(
            "SELECT to_regprocedure('public.dealer_sync_approvals()') IS NOT NULL AS ok")).fetchone()
        if not row["ok"]:
            return 0
        done = await (await cx.execute("SELECT public.dealer_sync_approvals() AS n")).fetchone()
    return int(done["n"] or 0)


async def sweep() -> dict[str, int]:
    async with connection() as cx:
        row = await (await cx.execute("SELECT * FROM public.dealer_sweep()")).fetchone()
    return {k: int(row[k] or 0) for k in ("matches_deleted", "notifications_skipped", "expired_deleted")}


# ---------------------------------------------------------------------------
# Step 3: approved sources (listings we already read)
# ---------------------------------------------------------------------------

async def approved_sources() -> list[dict[str, Any]]:
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT s.id, s.dealer_id, s.source, s.seller_key FROM dealer_sources s "
            "  JOIN dealers d ON d.id = s.dealer_id "
            " WHERE s.status = 'approved' AND s.seller_key IS NOT NULL ORDER BY s.id")).fetchall()


async def link_source_listings(dealer_id: int, source: str, seller_key: str) -> dict[str, Any]:
    """Mark the active listings of (source, seller_key) as the dealer's and
    give each one a 'sync' item. Returns {"linked": n, "conflicts": [ids]}:
    the listings another dealer already holds (left alone)."""
    async with connection() as cx:
        async with cx.transaction():
            conflicts = await (await cx.execute(
                "SELECT l.id FROM listings l WHERE l.source = %s AND l.seller_key = %s AND l.status = 'active' "
                "   AND l.dealer_id IS NOT NULL AND l.dealer_id <> %s ORDER BY l.id",
                (source, seller_key, dealer_id))).fetchall()
            linked = await (await cx.execute(
                "UPDATE listings l SET dealer_id = %(d)s, dealer_status = coalesce(l.dealer_status, 'available'), "
                "       dealer_confirmed_at = greatest(l.last_seen_at, l.last_full_seen_at) "
                " WHERE l.source = %(s)s AND l.seller_key = %(k)s AND l.status = 'active' "
                "   AND l.dealer_id IS NULL RETURNING l.id",
                {"d": dealer_id, "s": source, "k": seller_key})).fetchall()
            # A listing that ended and came back (FB, ML do that) still has the dealer's id: its
            # archived 'sync' item comes back with it, so the dealer sees what buyers get.
            revived = await cx.execute(
                "UPDATE dealer_stock_items i SET sync_state = 'linked', matched_at = NULL, "
                "       status = CASE WHEN i.status = 'sold' THEN 'sold' "
                "                     ELSE coalesce(l.dealer_status, 'available') END, "
                "       confirmed_at = l.dealer_confirmed_at "
                "  FROM listings l "
                " WHERE l.id = i.listing_id AND i.origin = 'sync' AND i.sync_state = 'gone' AND i.dealer_id = %(d)s "
                "   AND l.dealer_id = %(d)s AND l.source = %(s)s AND l.seller_key = %(k)s AND l.status = 'active'",
                {"d": dealer_id, "s": source, "k": seller_key})
            cur = await cx.execute(
                "INSERT INTO dealer_stock_items (dealer_id, origin, listing_id, status, confirmed_at, sync_state, "
                "                                synced_at, matched_at) "
                "SELECT %(d)s, 'sync', l.id, coalesce(l.dealer_status, 'available'), "
                "       greatest(l.last_seen_at, l.last_full_seen_at), 'linked', now(), now() "
                "  FROM listings l "
                " WHERE l.dealer_id = %(d)s AND l.source = %(s)s AND l.seller_key = %(k)s AND l.status = 'active' "
                "   AND NOT EXISTS (SELECT 1 FROM dealer_stock_items i WHERE i.listing_id = l.id) "
                "ON CONFLICT (listing_id) WHERE listing_id IS NOT NULL DO NOTHING",
                {"d": dealer_id, "s": source, "k": seller_key})
    return {"linked": len(linked), "items": cur.rowcount, "revived": revived.rowcount,
            "conflicts": [r["id"] for r in conflicts]}


async def archive_gone_sync_items() -> int:
    """'sync' items whose listing ended (or was purged): archived, unless sold."""
    async with connection() as cx:
        cur = await cx.execute(
            "UPDATE dealer_stock_items i SET sync_state = 'gone', "
            "       status = CASE WHEN i.status = 'sold' THEN 'sold' ELSE 'archived' END "
            " WHERE i.origin = 'sync' AND i.sync_state <> 'gone' "
            "   AND (i.listing_id IS NULL OR EXISTS (SELECT 1 FROM listings l "
            "                                         WHERE l.id = i.listing_id AND l.status <> 'active'))")
    return cur.rowcount


async def unlink_unapproved() -> int:
    """Portal listings marked with a dealer whose (source, seller_key) is no
    longer approved for it: unmarked; their 'sync' items archived, and an
    item of the dealer's own that pointed at one goes back to pending (the
    worker then makes its own 'directo' listing)."""
    async with connection() as cx:
        async with cx.transaction():
            rows = await (await cx.execute(
                "UPDATE listings l SET dealer_id = NULL, dealer_status = NULL, dealer_confirmed_at = NULL "
                " WHERE l.dealer_id IS NOT NULL AND l.source <> %s "
                "   AND NOT EXISTS (SELECT 1 FROM dealer_sources s WHERE s.dealer_id = l.dealer_id "
                "                      AND s.source = l.source AND s.seller_key = l.seller_key "
                "                      AND s.status = 'approved') RETURNING l.id",
                (DEALER_SOURCE,))).fetchall()
            ids = [r["id"] for r in rows]
            if ids:
                await cx.execute(
                    "UPDATE dealer_stock_items SET status = CASE WHEN status = 'sold' THEN 'sold' ELSE 'archived' END, "
                    "       sync_state = 'gone', listing_id = NULL WHERE origin = 'sync' AND listing_id = ANY(%s)",
                    (ids,))
                await cx.execute(
                    "UPDATE dealer_stock_items SET listing_id = NULL, sync_state = 'pending', matched_at = NULL "
                    " WHERE origin <> 'sync' AND listing_id = ANY(%s)", (ids,))
    return len(ids)


async def own_reviews(limit: int = 200) -> list[dict[str, Any]]:
    """Items in 'review' whose look-alike listing is now the dealer's own (it
    said «Sí, es mío» and Juan approved the source): with the 'sync' item
    link_source_listings gave that listing, for link_own_duplicate."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT i.*, l.id AS own_listing_id, s.id AS sync_item_id "
            "  FROM dealer_stock_items i "
            "  JOIN listings l ON l.id = i.duplicate_listing_id AND l.dealer_id = i.dealer_id AND l.status = 'active' "
            "  LEFT JOIN dealer_stock_items s ON s.listing_id = l.id AND s.origin = 'sync' AND s.dealer_id = i.dealer_id "
            " WHERE i.sync_state = 'review' AND i.origin IN ('manual', 'sheet') "
            " ORDER BY i.id LIMIT %s", (limit,))).fetchall()


async def release_stale_reviews() -> int:
    """Items in 'review' whose look-alike is gone (ended, purged): nothing left
    to ask, so they go back to 'pending' and get their own listing."""
    async with connection() as cx:
        cur = await cx.execute(
            "UPDATE dealer_stock_items i SET sync_state = 'pending', duplicate_listing_id = NULL, matched_at = NULL "
            " WHERE i.sync_state = 'review' AND i.origin IN ('manual', 'sheet') "
            "   AND (i.duplicate_listing_id IS NULL "
            "        OR EXISTS (SELECT 1 FROM listings l WHERE l.id = i.duplicate_listing_id AND l.status <> 'active'))")
    return cur.rowcount


async def release_gone_links() -> int:
    """Manual and sheet items on sale linked to the dealer's portal listing
    (link_own_duplicate) whose listing ended: they let it go and go back to
    'pending', so the worker makes their own 'directo' listing."""
    async with connection() as cx:
        cur = await cx.execute(
            "UPDATE dealer_stock_items i SET listing_id = NULL, sync_state = 'pending', matched_at = NULL "
            " WHERE i.origin IN ('manual', 'sheet') AND i.sync_state = 'linked' "
            "   AND i.status IN ('available', 'reserved') "
            "   AND (i.listing_id IS NULL "
            "        OR EXISTS (SELECT 1 FROM listings l WHERE l.id = i.listing_id AND l.status <> 'active'))")
    return cur.rowcount


async def refresh_sync_confirmations() -> int:
    """A synced listing is confirmed by every read of it (C3): its
    dealer_confirmed_at follows greatest(last_seen_at, last_full_seen_at)."""
    async with connection() as cx:
        async with cx.transaction():
            cur = await cx.execute(
                "UPDATE listings l SET dealer_confirmed_at = greatest(l.last_seen_at, l.last_full_seen_at) "
                " WHERE l.dealer_id IS NOT NULL AND l.source <> %s AND l.status = 'active' "
                "   AND l.dealer_confirmed_at IS DISTINCT FROM greatest(l.last_seen_at, l.last_full_seen_at)",
                (DEALER_SOURCE,))
            await cx.execute(
                "UPDATE dealer_stock_items i SET confirmed_at = l.dealer_confirmed_at "
                "  FROM listings l WHERE l.id = i.listing_id AND l.source <> %s AND l.dealer_id = i.dealer_id "
                "   AND i.confirmed_at IS DISTINCT FROM l.dealer_confirmed_at", (DEALER_SOURCE,))
    return cur.rowcount


# ---------------------------------------------------------------------------
# Step 4: manual and sheet items → 'directo' listings
# ---------------------------------------------------------------------------

_ITEM = ("SELECT i.*, d.name AS dealer_name, d.locality_label, d.lat AS dealer_lat, d.lon AS dealer_lon, "
         "       il.source AS listing_source, "
         "       CASE WHEN i.currency = 'USD' THEN i.price::float8 "
         "            WHEN i.currency = 'ARS' THEN i.price::float8 / nullif(public.dealer_blue_rate(), 0)::float8 "
         "       END AS price_usd "
         "  FROM dealer_stock_items i JOIN dealers d ON d.id = i.dealer_id "
         "  LEFT JOIN listings il ON il.id = i.listing_id ")


async def pending_items(limit: int) -> list[dict[str, Any]]:
    """Manual and sheet items to turn into (or refresh as) their listing:
    'pending' and available or reserved (a sold one is never published), the
    'synced' ones put back on sale whose 'directo' listing ended, and those the
    ingest failed on (a transient error) once 30 minutes went by."""
    async with connection() as cx:
        return await (await cx.execute(
            _ITEM + " WHERE i.origin IN ('manual', 'sheet') AND i.status IN ('available', 'reserved') "
            "   AND (i.sync_state = 'pending' "
            "        OR (i.sync_state = 'error' AND i.sync_error = 'ingest_failed' "
            "            AND i.updated_at < now() - interval '30 minutes') "
            "        OR (i.sync_state = 'synced' AND EXISTS (SELECT 1 FROM listings l WHERE l.id = i.listing_id "
            "                                                  AND l.source = %s AND l.status <> 'active'))) "
            " ORDER BY i.id LIMIT %s", (DEALER_SOURCE, limit))).fetchall()


async def own_sync_duplicate(item: dict[str, Any]) -> dict[str, Any] | None:
    """A 'sync' item of the same dealer that is this car (§4.4 4.1): same
    make, model and year, price within 3 % in USD, km within 10 % or unknown."""
    if item.get("price_usd") is None:
        return None
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT s.id AS item_id, s.listing_id FROM dealer_stock_items s JOIN listings l ON l.id = s.listing_id "
            " WHERE s.dealer_id = %(d)s AND s.origin = 'sync' AND s.id <> %(i)s AND l.status = 'active' "
            "   AND lower(l.make) = lower(%(make)s) AND lower(l.model) = lower(%(model)s) AND l.year = %(year)s "
            "   AND l.price_usd > 0 AND abs(l.price_usd - %(usd)s) <= 0.03 * greatest(l.price_usd, %(usd)s) "
            "   AND (l.mileage_km IS NULL OR %(km)s::int IS NULL "
            "        OR abs(l.mileage_km - %(km)s) <= 0.10 * greatest(l.mileage_km, %(km)s, 1)) "
            " ORDER BY abs(l.price_usd - %(usd)s), s.id LIMIT 1",
            {"d": item["dealer_id"], "i": item["id"], "make": item["make"], "model": item["model"],
             "year": item["year"], "usd": item["price_usd"], "km": item.get("mileage_km")})).fetchone()


def _dismissed(item: dict[str, Any]) -> int | None:
    """The foreign listing the dealer said is not theirs (dealer_resolve_duplicate
    false leaves sync_error = 'duplicate_dismissed:<id>')."""
    err = item.get("sync_error") or ""
    if err.startswith("duplicate_dismissed:"):
        try:
            return int(err.split(":", 1)[1])
        except ValueError:
            return None
    return None


async def foreign_duplicate(item: dict[str, Any]) -> dict[str, Any] | None:
    """An active listing of a portal that looks like this car (§4.4 4.2):
    same model and year, km within 3 % (both known) or price within 2 %, at
    30 km or less from the dealer, sold by a dealer (effective_seller). The
    dealer then says whether it is theirs; nothing is created meanwhile."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT l.id FROM listings l "
            " WHERE l.status = 'active' AND l.source <> %(directo)s AND l.dealer_id IS NULL "
            "   AND NOT (l.attributes ? '_not_vehicle') "
            "   AND lower(l.make) = lower(%(make)s) AND lower(l.model) = lower(%(model)s) AND l.year = %(year)s "
            "   AND (l.seller_type = 'dealer' OR l.dealer_inferred) "
            "   AND l.lat IS NOT NULL AND l.lon IS NOT NULL "
            "   AND public.haversine_km(l.lat, l.lon, %(lat)s, %(lon)s) <= 30 "
            "   AND ((l.mileage_km IS NOT NULL AND %(km)s::int IS NOT NULL "
            "         AND abs(l.mileage_km - %(km)s) <= 0.03 * greatest(l.mileage_km, %(km)s, 1)) "
            "        OR (l.price_usd > 0 AND %(usd)s::float8 IS NOT NULL "
            "            AND abs(l.price_usd - %(usd)s) <= 0.02 * greatest(l.price_usd, %(usd)s))) "
            "   AND l.id IS DISTINCT FROM %(dismissed)s::bigint "
            "   AND NOT EXISTS (SELECT 1 FROM dealer_stock_items i WHERE i.listing_id = l.id) "
            " ORDER BY public.haversine_km(l.lat, l.lon, %(lat)s, %(lon)s), l.id LIMIT 1",
            {"directo": DEALER_SOURCE, "make": item["make"], "model": item["model"], "year": item["year"],
             "lat": item["dealer_lat"], "lon": item["dealer_lon"], "km": item.get("mileage_km"),
             "usd": item.get("price_usd"), "dismissed": _dismissed(item)})).fetchone()


async def link_own_duplicate(item: dict[str, Any], sync_item_id: int | None, listing_id: int) -> int | None:
    """The item takes the synced listing; the 'sync' item goes (one car, one
    item). Returns the item's former 'directo' listing, if it had one, for the
    caller to end."""
    async with connection() as cx:
        async with cx.transaction():
            if sync_item_id is not None:
                await cx.execute("UPDATE dealer_leads SET item_id = %s WHERE item_id = %s", (item["id"], sync_item_id))
                await cx.execute("DELETE FROM dealer_stock_items WHERE id = %s AND origin = 'sync'", (sync_item_id,))
            await cx.execute(
                "UPDATE dealer_stock_items SET listing_id = %s, sync_state = 'linked', synced_at = now(), "
                "       sync_error = NULL, duplicate_listing_id = NULL WHERE id = %s", (listing_id, item["id"]))
            await cx.execute(
                "UPDATE listings SET dealer_status = %s WHERE id = %s AND dealer_id = %s",
                (item["status"], listing_id, item["dealer_id"]))
    old = item.get("listing_id")
    return old if old is not None and old != listing_id else None


async def attach_listing(item: dict[str, Any], listing_id: int) -> bool:
    """After ingest stored the item's 'directo' listing: the dealer's place,
    who sells it, its state and confirmation; the item points at it."""
    async with connection() as cx:
        async with cx.transaction():
            await cx.execute(
                "UPDATE listings SET lat = %(lat)s, lon = %(lon)s, dealer_id = %(d)s, dealer_status = %(st)s, "
                "       dealer_confirmed_at = %(c)s WHERE id = %(l)s AND source = %(directo)s",
                {"lat": item["dealer_lat"], "lon": item["dealer_lon"], "d": item["dealer_id"],
                 "st": item["status"], "c": item.get("confirmed_at"), "l": listing_id,
                 "directo": DEALER_SOURCE})
            await cx.execute(
                "UPDATE dealer_stock_items SET listing_id = %s, sync_state = 'synced', synced_at = now(), "
                "       sync_error = NULL WHERE id = %s", (listing_id, item["id"]))
    return True


async def mark_item(item_id: int, **fields: Any) -> None:
    allowed = {"sync_state", "sync_error", "duplicate_listing_id", "matched_at"}
    if not fields or set(fields) - allowed:
        raise ValueError(f"mark_item: {sorted(set(fields) - allowed)}")
    sets = ", ".join(f"{k} = %({k})s" for k in fields)
    async with connection() as cx:
        await cx.execute(f"UPDATE dealer_stock_items SET {sets} WHERE id = %(id)s", {**fields, "id": item_id})


async def directo_to_end() -> list[int]:
    """Active 'directo' listings whose item is sold or archived, or gone
    (its dealer was deleted): nothing on sale points at them."""
    async with connection() as cx:
        rows = await (await cx.execute(
            "SELECT l.id FROM listings l "
            " WHERE l.source = %s AND l.status = 'active' "
            "   AND NOT EXISTS (SELECT 1 FROM dealer_stock_items i "
            "                    WHERE i.listing_id = l.id AND i.status IN ('available', 'reserved')) "
            " ORDER BY l.id", (DEALER_SOURCE,))).fetchall()
    return [r["id"] for r in rows]


# ---------------------------------------------------------------------------
# Step 5: the daily touch
# ---------------------------------------------------------------------------

async def touch_directo() -> int:
    """last_seen_at = now() for the 'directo' listings still on sale, once a
    day, so retention and the recency windows treat them as seen."""
    async with connection() as cx:
        cur = await cx.execute(
            "UPDATE listings l SET last_seen_at = now() "
            " WHERE l.source = %s AND l.status = 'active' AND l.last_seen_at < now() - interval '1 day' "
            "   AND EXISTS (SELECT 1 FROM dealer_stock_items i WHERE i.listing_id = l.id "
            "                  AND i.status IN ('available', 'reserved'))", (DEALER_SOURCE,))
    return cur.rowcount


# ---------------------------------------------------------------------------
# Step 6: matching
# ---------------------------------------------------------------------------

async def to_match(limit: int) -> list[dict[str, Any]]:
    """Items whose listing is visible now and was not matched while visible:
    new, edited, confirmed again, back on sale, or the channel just opened."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT i.id AS item_id, l.id AS listing_id, l.source, l.make, l.model "
            "  FROM dealer_stock_items i JOIN listings l ON l.id = i.listing_id "
            " WHERE i.matched_at IS NULL AND i.status IN ('available', 'reserved') AND l.status = 'active' "
            f"  AND l.dealer_id = i.dealer_id AND {visible('l')} "
            " ORDER BY i.id LIMIT %s", (limit,))).fetchall()


async def set_matched(item_ids: Iterable[int], at: datetime | None = None) -> None:
    ids = list(item_ids)
    if not ids:
        return
    async with connection() as cx:
        await cx.execute("UPDATE dealer_stock_items SET matched_at = coalesce(%s, now()) WHERE id = ANY(%s)",
                         (at, ids))


# ---------------------------------------------------------------------------
# Step 7: new leads → the dealer
# ---------------------------------------------------------------------------

async def unnotified_leads(limit: int) -> list[dict[str, Any]]:
    """Leads the dealer was not told about, with where to tell it: the
    dealer's contact email or its owner's. Only ids and the car, never the
    buyer's data (the dealer reads those in its panel)."""
    async with connection() as cx:
        # A dealer without an address can't hold back the others: its leads are left out
        # (they wait in its panel) instead of filling the batch every tick.
        return await (await cx.execute(
            "SELECT * FROM (SELECT k.id AS lead_id, k.dealer_id, k.listing_id, "
            "       coalesce(d.contact_email, (SELECT p.email FROM dealer_members m JOIN profiles p ON p.id = m.user_id "
            "                                   WHERE m.dealer_id = d.id AND p.email IS NOT NULL "
            "                                   ORDER BY m.created_at LIMIT 1)) AS email, "
            "       l.make, l.model, l.trim, l.year, l.title "
            "  FROM dealer_leads k JOIN dealers d ON d.id = k.dealer_id "
            "  LEFT JOIN listings l ON l.id = k.listing_id "
            " WHERE k.dealer_notified_at IS NULL) x "
            " WHERE x.email IS NOT NULL ORDER BY x.lead_id LIMIT %s", (limit,))).fetchall()


async def mark_lead_notified(ids: Iterable[int]) -> None:
    ids = list(ids)
    if not ids:
        return
    async with connection() as cx:
        await cx.execute("UPDATE dealer_leads SET dealer_notified_at = now() WHERE id = ANY(%s)", (ids,))


# ---------------------------------------------------------------------------
# Fase 1: alerts to the agency (pipeline/dealers.py step 8)
# ---------------------------------------------------------------------------

_EMAIL = ("coalesce(d.contact_email, (SELECT p.email FROM dealer_members m JOIN profiles p ON p.id = m.user_id "
          "                           WHERE m.dealer_id = d.id AND p.email IS NOT NULL "
          "                           ORDER BY m.created_at LIMIT 1))")


async def dealers_due_for_alerts(every_hours: int, limit: int = 50) -> list[dict[str, Any]]:
    """Active dealers that want the alerts and were not checked in `every_hours`."""
    async with connection() as cx:
        return await (await cx.execute(
            f"SELECT d.id AS dealer_id, {_EMAIL} AS email FROM dealers d "
            " WHERE d.status = 'active' AND d.alerts_email "
            "   AND (d.alerts_checked_at IS NULL OR d.alerts_checked_at < now() - make_interval(hours => %s)) "
            " ORDER BY d.alerts_checked_at NULLS FIRST, d.id LIMIT %s", (every_hours, limit))).fetchall()


async def alert_scan(dealer_id: int, *, cheaper_pct: float, radius_km: float) -> list[dict[str, Any]]:
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT * FROM public.dealer_alert_scan(%s::bigint, %s::numeric, %s::numeric)", (dealer_id, cheaper_pct, radius_km))).fetchall()


_STATE_COLS = ("market_median_usd", "market_n", "market_at", "demand_searches", "demand_people", "demand_at",
               "cheaper_since")


async def save_alerts(dealer_id: int, states: list[tuple[int, dict[str, Any]]], alerts: list[Any]) -> int:
    """The new references and the new alerts, in one transaction. An alert
    whose dedup_key the dealer already got is dropped. Returns how many were added."""
    added = 0
    cols = ", ".join(_STATE_COLS)
    vals = ", ".join(["%s"] * len(_STATE_COLS))
    sets = ", ".join(f"{c} = excluded.{c}" for c in _STATE_COLS)
    async with connection() as cx:
        async with cx.transaction():
            for item_id, st in states:
                await cx.execute(
                    f"INSERT INTO dealer_alert_state (item_id, {cols}) VALUES (%s, {vals}) "
                    f"ON CONFLICT (item_id) DO UPDATE SET {sets}",
                    (item_id, *(st.get(c) for c in _STATE_COLS)))
            for a in alerts:
                cur = await cx.execute(
                    "INSERT INTO dealer_alerts (dealer_id, item_id, kind, dedup_key, payload) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (dealer_id, dedup_key) DO NOTHING",
                    (dealer_id, a.item_id, a.kind, a.dedup_key, Jsonb(a.payload)))
                added += cur.rowcount
    return added


async def pending_alerts(dealer_id: int, limit: int = 100) -> list[dict[str, Any]]:
    """Alerts not sent yet, of cars still on sale (a car sold meanwhile drops out)."""
    async with connection() as cx:
        return await (await cx.execute(
            "SELECT a.id, a.kind, a.item_id, a.payload FROM dealer_alerts a "
            "  LEFT JOIN dealer_stock_items i ON i.id = a.item_id "
            " WHERE a.dealer_id = %s AND a.sent_at IS NULL "
            "   AND (a.item_id IS NULL OR i.status = 'available') "
            " ORDER BY a.id LIMIT %s", (dealer_id, limit))).fetchall()


async def mark_alerts_sent(dealer_id: int, ids: Iterable[int]) -> None:
    """These were told; the ones of cars no longer on sale are closed too (never sent later)."""
    ids = list(ids)
    async with connection() as cx:
        await cx.execute(
            "UPDATE dealer_alerts a SET sent_at = now() "
            " WHERE a.dealer_id = %s AND a.sent_at IS NULL "
            "   AND (a.id = ANY(%s::bigint[]) OR NOT EXISTS (SELECT 1 FROM dealer_stock_items i "
            "                                      WHERE i.id = a.item_id AND i.status = 'available'))",
            (dealer_id, ids))


async def set_alerts_checked(dealer_id: int, *, retry_in_hours: float | None = None, every_hours: int = 24) -> None:
    """Checked now; with `retry_in_hours` (the email failed) it comes due again that soon."""
    async with connection() as cx:
        if retry_in_hours is None:
            await cx.execute("UPDATE dealers SET alerts_checked_at = now() WHERE id = %s", (dealer_id,))
        else:
            await cx.execute(
                "UPDATE dealers SET alerts_checked_at = now() - make_interval(hours => %s) "
                "                                     + make_interval(secs => %s) WHERE id = %s",
                (every_hours, retry_in_hours * 3600, dealer_id))


# ---------------------------------------------------------------------------
# Fase 1: stock read from a photo or a PDF (pipeline/llm_jobs.py)
# ---------------------------------------------------------------------------

async def take_stock_read(read_id: int, job_id: int) -> dict[str, Any] | None:
    """The file of a read (of this job), and its bytes leave the database at
    once: the list may show plates or names, and we only keep the cars the
    model reads. None when it is not there (or was already read)."""
    async with connection() as cx:
        async with cx.transaction():
            return await (await cx.execute(
                "UPDATE dealer_stock_reads r SET data = NULL, read_at = now() "
                "  FROM (SELECT id, data FROM dealer_stock_reads "
                "         WHERE id = %s AND job_id = %s AND data IS NOT NULL FOR UPDATE) old "
                " WHERE r.id = old.id "
                "RETURNING r.id, r.dealer_id, r.media_type, r.filename, old.data", (read_id, job_id))).fetchone()


async def purge_stock_reads(older_than_minutes: int = 60) -> int:
    """Files nobody read (the job expired in the queue): their bytes go."""
    async with connection() as cx:
        cur = await cx.execute(
            "UPDATE dealer_stock_reads SET data = NULL "
            " WHERE data IS NOT NULL AND created_at < now() - make_interval(mins => %s)", (older_than_minutes,))
        return cur.rowcount
