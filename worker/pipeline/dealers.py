"""Agencias (docs/superpowers/specs/2026-11-18-agencias-design.md §4.4): the dealers loop.

Every DEALER_TICK_SECONDS (main.py), each step in its own try, never raising:

1. Sweep (always): public.dealer_sweep() deletes the matches and the
   expired_search_matches rows of every hidden dealer car, and skips its
   queued notifications (an expired confirmation, a paused dealer, the
   channel turned off). A no-op without dealer rows.
2. With dealer_program.enabled false, stop there.
3. Approved sources: the portal listings of an approved (source, seller_key)
   get the dealer's id and a 'sync' item; they are confirmed by every read
   of them (C3). Ended ones are archived; unapproved ones unmarked.
4. Manual and sheet items: the dealer's own duplicate is linked (no copy,
   C8), a foreign look-alike waits for the dealer's answer ('review'), and
   the rest become 'directo' listings through the same ingest as any listing
   (catalog, USD at the day's quote, snapshots, seller classification).
   Sold or archived items end their listing.
5. Daily touch of the 'directo' listings still on sale.
6. Matching (channel on only): the visible items not matched while visible
   go through scheduler.process_batch, as a new listing of a crawl would:
   same matching, score, daily cap and thresholds (C1).
7. New leads → an email to the dealer (channel on only), without the
   buyer's data (notifications/dealer_leads.py).
8. Fase 1, alerts to the agency (dealer_program.alerts_enabled, channel or
   not): for each dealer that wants them and was not checked in
   alerts_every_hours, dealer_alert_scan() → intelligence/dealer_alerts.decide
   → one summary email of what is new (notifications/dealer_alerts.py), each
   alert once. Plus: the bytes of stock-read files nobody read are deleted.

Errors are logged with ids only (no person's data).
"""
from __future__ import annotations

import logging
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import db
from collectors.base import Listing
from config import WEB_BASE_URL
from db.repos import dealers as repo
from db.repos import listings as listings_repo
from db.repos.runs import log_error
from intelligence.config import dealer_program
from intelligence import dealer_alerts as alerts_logic
from intelligence.dealer import DEALER_SOURCE
from notifications import dealer_alerts as alerts_mail
from notifications.dealer_leads import notify_new_leads
from notifications.links import Links
from notifications.service import Notifier
from pipeline import ingest as ingest_mod
from pipeline.scheduler import process_batch

log = logging.getLogger("dealers")

SYNC_LIMIT = 200
MATCH_LIMIT = 200

# (source id, listing id) conflicts already recorded by this process: one
# pipeline_errors row each, not one every tick.
_conflicts_logged: set[tuple[int, int]] = set()


@dataclass
class DealerTick:
    swept_matches: int = 0
    skipped_notifications: int = 0
    swept_expired: int = 0
    linked: int = 0
    unlinked: int = 0
    created: int = 0
    updated: int = 0
    gone: int = 0
    review: int = 0
    matched: int = 0
    lead_notices: int = 0
    alerts_added: int = 0
    alert_emails: int = 0


def listing_for(item: dict[str, Any], *, base_url: str = WEB_BASE_URL) -> Listing:
    """A manual or sheet item as a collector would have read it."""
    title = item.get("title") or " ".join(str(x) for x in (item.get("make"), item.get("model"), item.get("trim"),
                                                            item.get("year")) if x)
    created = item.get("created_at")
    images = item.get("images") if isinstance(item.get("images"), list) else []
    return Listing(
        source=DEALER_SOURCE, listing_id=str(item["id"]), titulo=title,
        url=f"{base_url}/app/listings/{DEALER_SOURCE}/{item['id']}",
        precio=float(item["price"]) if item.get("price") is not None else None, moneda=item.get("currency"),
        marca=item.get("make"), modelo=item.get("model"), version=item.get("trim"), anio=item.get("year"),
        km=item.get("mileage_km"), ubicacion=item.get("locality_label"),
        transmision=item.get("transmission"), combustible=item.get("fuel"), carroceria=item.get("body_type"),
        vendedor="dealer", vendedor_nombre=item.get("dealer_name"), descripcion=item.get("description"),
        imagenes=[u for u in images if isinstance(u, str)],
        published_at=int(created.timestamp()) if isinstance(created, datetime) else None,
        atributos={"Color": item["color"]} if item.get("color") else {},
    )


async def _step(name: str, ref: str, coro) -> Any:
    try:
        return await coro
    except Exception:
        await log_error("dealers", f"{name}:{ref}", traceback.format_exc())
        return None


async def sync_linked(tick: DealerTick) -> None:
    for s in await repo.approved_sources():
        res = await _step("link", f"source:{s['id']}",
                          repo.link_source_listings(s["dealer_id"], s["source"], s["seller_key"]))
        if not res:
            continue
        tick.linked += res["linked"]
        for lid in res["conflicts"]:
            if (s["id"], lid) not in _conflicts_logged:
                _conflicts_logged.add((s["id"], lid))
                await log_error("dealers", f"link:source:{s['id']}:listing:{lid}", "listing held by another dealer")
    tick.gone += await _step("archive", "sync", repo.archive_gone_sync_items()) or 0
    tick.unlinked += await _step("unlink", "sync", repo.unlink_unapproved()) or 0
    await _step("confirm", "sync", repo.refresh_sync_confirmations())
    await _step("reviews", "sync", resolve_own_reviews(tick))


async def resolve_own_reviews(tick: DealerTick) -> None:
    """«¿Es este aviso tuyo? → Sí»: once Juan approved that source, the
    look-alike is the dealer's listing and got a 'sync' item. The dealer's own
    item takes the listing and that 'sync' item goes (one car, one item, C8).
    A look-alike that ended leaves nothing to ask: the item gets its listing."""
    for item in await repo.own_reviews():
        try:
            await repo.link_own_duplicate(item, item.get("sync_item_id"), item["own_listing_id"])
        except Exception:
            await log_error("dealers", f"review:item:{item['id']}", traceback.format_exc())
            continue
        tick.linked += 1
    await _step("review", "stale", repo.release_stale_reviews())


async def _end(listing_ids: list[int], events: list) -> int:
    n = 0
    async with db.connection() as cx:
        for lid in listing_ids:
            if await listings_repo.mark_gone(cx, lid):
                n += 1
                events.append(ingest_mod.ListingEvent("listing_gone", lid, DEALER_SOURCE, ""))
    return n


async def sync_manual(tick: DealerTick, events: list) -> None:
    """Step 4. `events` gets the ingest events of the listings it wrote."""
    # Linked to its own portal listing and that one ended: back to pending, it gets a 'directo'.
    await _step("release", "linked", repo.release_gone_links())
    items = await repo.pending_items(SYNC_LIMIT)
    to_ingest: list[dict[str, Any]] = []
    for item in items:
        try:
            if item.get("listing_id") is not None and item.get("listing_source") not in (None, DEALER_SOURCE):
                # Edited while linked to the dealer's own portal listing: that one stays the car
                # (its data comes from the portal's reads); never a 'directo' copy (C8).
                await repo.mark_item(item["id"], sync_state="linked")
                continue
            own = await repo.own_sync_duplicate(item)
            if own:
                old = await repo.link_own_duplicate(item, own["item_id"], own["listing_id"])
                tick.linked += 1
                if old is not None:
                    tick.gone += await _end([old], events)
                continue
            # Only before it is published: an edit of a listed car never takes it off the channel.
            foreign = await repo.foreign_duplicate(item) if item.get("listing_id") is None else None
            if foreign:
                await repo.mark_item(item["id"], sync_state="review", duplicate_listing_id=foreign["id"])
                tick.review += 1
                continue
            to_ingest.append(item)
        except Exception:
            await log_error("dealers", f"item:{item['id']}", traceback.format_exc())
    if to_ingest:
        try:
            result = await ingest_mod.ingest([listing_for(i) for i in to_ingest], seen=True, geocode=None)
        except Exception:
            await log_error("dealers", "ingest", traceback.format_exc())
            for item in to_ingest:
                await _step("mark", f"item:{item['id']}",
                            repo.mark_item(item["id"], sync_state="error", sync_error="ingest_failed"))
            result = None
        if result is not None:
            events += result.events
            for item in to_ingest:
                lid = result.ids.get((DEALER_SOURCE, str(item["id"])))
                if lid is None:
                    # Not stored: normalization failed or it is not a car (normalization/not_vehicle.py).
                    await _step("mark", f"item:{item['id']}",
                                repo.mark_item(item["id"], sync_state="error", sync_error="not_stored"))
                    continue
                if not await _step("attach", f"item:{item['id']}", repo.attach_listing(item, lid)):
                    continue
                if item.get("listing_id") == lid:
                    tick.updated += 1
                else:
                    tick.created += 1
    ended = await _step("end", "directo", repo.directo_to_end()) or []
    if ended:
        tick.gone += await _end(ended, events)


async def match_visible(notifier: Notifier, tick: DealerTick, events: list) -> None:
    """Step 6: as a crawl batch of new listings, grouped by (source, make, model)."""
    rows = await repo.to_match(MATCH_LIMIT)
    groups: dict[tuple[str, str | None, str | None], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["source"], r["make"], r["model"])].append(r)
    for (source, make, model), group in groups.items():
        ids = [r["listing_id"] for r in group]
        wanted = set(ids)
        evs = [e for e in events if e.listing_id in wanted]
        target = {"id": None, "source": source, "make": make, "model": model, "query": {}}
        try:
            await process_batch(notifier, target, ids, first_run=False, events=evs)
        except Exception:
            await log_error("dealers", f"match:{source}:{make}:{model}", traceback.format_exc())
            continue
        await repo.set_matched(r["item_id"] for r in group)
        tick.matched += len(group)


ALERT_DEALERS_PER_TICK = 20
ALERT_RETRY_HOURS = 1.0


async def scan_dealer_alerts(dealer_id: int, program: dict[str, Any], now: datetime) -> int:
    """Decide and queue one dealer's alerts; returns how many are new."""
    rows = await repo.alert_scan(dealer_id, cheaper_pct=alerts_logic.CHEAPER_PCT,
                                 radius_km=alerts_logic.CHEAPER_RADIUS_KM)
    states, found = [], []
    for row in rows:
        new_alerts, state = alerts_logic.decide(row, min_count=program["demand_min_count"], now=now)
        states.append((row["item_id"], state))
        found += new_alerts
    return await repo.save_alerts(dealer_id, states, found)


async def send_alerts(channel, links: Links | None, program: dict[str, Any], tick: DealerTick,
                      *, now: datetime | None = None) -> None:
    """Step 8: the dealers due get their scan and, if anything is new, one email."""
    now = now or datetime.now(timezone.utc)
    every = program["alerts_every_hours"]
    for d in await repo.dealers_due_for_alerts(every, ALERT_DEALERS_PER_TICK):
        dealer_id = d["dealer_id"]
        try:
            tick.alerts_added += await scan_dealer_alerts(dealer_id, program, now)
            pending = await repo.pending_alerts(dealer_id)
            if not pending:
                await repo.mark_alerts_sent(dealer_id, [])
                await repo.set_alerts_checked(dealer_id)
                continue
            if channel is None or not d.get("email"):
                # Nowhere to send it: the alerts wait (a dealer without an email can add one in Datos).
                log.info("dealer %s: %d alerts, no email channel or address", dealer_id, len(pending))
                await repo.set_alerts_checked(dealer_id)
                continue
            ids = [a["id"] for a in pending]
            key = f"dealer-alerts-{dealer_id}-{min(ids)}-{max(ids)}"
            result = await channel.send_message(d["email"], alerts_mail.message(pending, links),
                                                idempotency_key=key, unsubscribe_token=None)
            if result.ok:
                await repo.mark_alerts_sent(dealer_id, ids)
                await repo.set_alerts_checked(dealer_id)
                tick.alert_emails += 1
                log.info("dealer %s: alerts %s sent", dealer_id, ids)
            else:
                await repo.set_alerts_checked(dealer_id, retry_in_hours=ALERT_RETRY_HOURS, every_hours=every)
                log.warning("dealer %s: alerts email failed (%s), alerts %s", dealer_id, result.error, ids)
        except Exception:
            await log_error("dealers", f"alerts:dealer:{dealer_id}", traceback.format_exc())


async def run_dealers(notifier: Notifier, links: Links, *, now: datetime | None = None) -> DealerTick:
    tick = DealerTick()
    try:
        async with db.connection() as cx:
            ready = await repo.schema_ready(cx)
    except Exception:
        await log_error("dealers", "schema", traceback.format_exc())
        return tick
    if not ready:
        return tick
    swept = await _step("sweep", "all", repo.sweep())
    if swept:
        tick.swept_matches, tick.skipped_notifications, tick.swept_expired = (
            swept["matches_deleted"], swept["notifications_skipped"], swept["expired_deleted"])
    phase1 = await _step("phase1", "schema", repo.phase1_ready())
    if phase1:
        # Stock-read files nobody read: their bytes go, whatever the switches say.
        await _step("reads", "purge", repo.purge_stock_reads())
    program = dealer_program(await db.get_config("dealer_program"))
    if not program["enabled"]:
        return tick
    events: list = []
    await _step("sync_linked", "all", sync_linked(tick))
    await _step("sync_manual", "all", sync_manual(tick, events))
    await _step("touch", "directo", repo.touch_directo())
    if program["channel"]:
        await _step("match", "all", match_visible(notifier, tick, events))
        tick.lead_notices = await _step("leads", "all",
                                        notify_new_leads(notifier.channels.get("email"), links)) or 0
    if phase1 and program["alerts_enabled"]:
        await _step("alerts", "all", send_alerts(notifier.channels.get("email"), links, program, tick, now=now))
    if any(vars(tick).values()):
        log.info("dealers: %s", {k: v for k, v in vars(tick).items() if v})
    return tick
