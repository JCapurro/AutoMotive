"""Canonical upsert, snapshots and change detection (secciones 5.2–5.4).

    insert → first_seen_at = last_seen_at = now(); snapshot 'new'; event listing_new
    update → last_seen_at = now(); status = 'active'
             if price, km, description, images or key attributes changed:
                 snapshot with change_kind; event listing_updated
                 if the price dropped ≥ app_config.price_drop_min_pct: event price_drop

One transaction per batch. Events are an in-memory list returned to the
caller (the crawl loop), which feeds them to matching and notifications
without polling (sección 5.3).

Cards and detail pages disagree on details (Kavak's card title has no body
type, the detail's does). So that a listing doesn't flip between the two on
every crawl, once a listing is enriched only fetch_detail() rewrites its
descriptive fields; cards keep refreshing price and mileage.

Prices (normalization v3): cards and detail pages report the *published*
price (price_published); the effective one (price) is re-resolved on every
merge against the stored description facts, so a card showing the list
price doesn't undo the cash price a detail page's description gave. The
'price' change kind, snapshots and price drops follow the published price:
what the seller moved, not how we read the text.
"""
from __future__ import annotations

import logging
import math
import traceback
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

import db
from collectors.base import Listing
from db.repos import listings as repo
from db.repos.catalog import load_models
from db.repos.fx import quote_for_today
from db.repos.runs import log_error
from normalization.description_facts import DescriptionFacts, resolve_price
from normalization.geo import geocode_location
from normalization.listing import Target, attrs_hash, fingerprint, normalize_listing


log = logging.getLogger("ingest")

GeocodeFn = Callable[[str], Awaitable[tuple[float, float] | None]]

# Snapshot change kinds, most important first: a snapshot row carries one.
CHANGE_KINDS = ("price", "mileage", "description", "images", "attrs")

_DESCRIPTIVE = ("title", "description", "year", "transmission", "fuel", "location_text",
                "seller_name", "seller_type", "images")
_VEHICLE = ("make", "model", "trim", "normalization_confidence")


@dataclass
class ListingEvent:
    kind: str                      # listing_new | listing_updated | price_drop | listing_gone | listing_stale
    listing_id: int
    source: str
    external_id: str
    changes: tuple[str, ...] = ()
    snapshot_id: int | None = None
    old_price: float | None = None
    new_price: float | None = None
    currency: str | None = None
    old_currency: str | None = None
    drop_pct: float | None = None
    repost_of: int | None = None


@dataclass
class IngestResult:
    found: int = 0
    new: int = 0
    updated: int = 0
    events: list[ListingEvent] = field(default_factory=list)
    ids: dict[tuple[str, str], int] = field(default_factory=dict)

    def extend(self, other: "IngestResult") -> None:
        self.found += other.found
        self.new += other.new
        self.updated += other.updated
        self.events += other.events
        self.ids.update(other.ids)


@dataclass(frozen=True)
class IngestConfig:
    price_drop_min_pct: float = 3.0
    repost_window_days: int = 60
    repost_price_tol_pct: float = 10.0

    @classmethod
    async def load(cls) -> "IngestConfig":
        repost = await db.get_config("repost", {}) or {}
        return cls(
            price_drop_min_pct=float(await db.get_config("price_drop_min_pct", 3)),
            repost_window_days=int(repost.get("window_days", 60)),
            repost_price_tol_pct=float(repost.get("price_tol_pct", 10)),
        )


# ---------------------------------------------------------------------------
# Pure part: merging and diffing
# ---------------------------------------------------------------------------

def _empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _same_number(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is b
    return math.isclose(float(a), float(b), abs_tol=0.005)


def _published(row: dict[str, Any]) -> tuple[float | None, str | None]:
    """The source's own price. Rows stored before normalization v3 (or by a
    worker that predates it, and tests' hand-made rows) only have price/currency."""
    if row.get("price_published") is not None:
        return row["price_published"], row.get("price_published_currency") or row.get("currency")
    return row.get("price"), row.get("currency")


def _usd_rate(row: dict[str, Any]) -> float | None:
    """ARS per USD: the day's quote normalization used, or the one that
    produced a stored ARS price_usd."""
    if row.get("usd_rate"):
        return float(row["usd_rate"])
    if row.get("currency") == "ARS" and row.get("price") and row.get("price_usd"):
        return float(row["price"]) / float(row["price_usd"])
    return None


def _to_usd(price: float | None, currency: str | None, rate: float | None) -> float | None:
    if not price or price <= 0 or not currency:
        return None
    if currency == "USD":
        return round(float(price), 2)
    return round(float(price) / rate, 2) if currency == "ARS" and rate else None


def _facts(existing: dict[str, Any], incoming: dict[str, Any], *,
           authoritative: bool) -> dict[str, Any] | None:
    """Which reading of the text stands: the authoritative side's, but a
    card's title-only reading never replaces one of the description, and
    the LLM's reading of the same text is kept."""
    new, old = incoming.get("description_facts"), existing.get("description_facts")
    if authoritative and incoming.get("description") and (
            incoming["description"] != existing.get("description")
            or (incoming.get("title") and incoming["title"] != existing.get("title"))):
        return new  # Old evidence is invalidated even when the new text has no facts.
    if new is None or old is None:
        return old if new is None else new
    if not authoritative:
        return old
    if not incoming.get("description") and existing.get("description"):
        return old
    if old.get("source") == "llm" and new.get("source") != "llm"             and (incoming.get("description") or None) == (existing.get("description") or None):
        return old
    return new


def merge(existing: dict[str, Any], incoming: dict[str, Any], *,
          detail: bool) -> tuple[dict[str, Any], list[str]]:
    """Values to write over `existing` and the change kinds they amount to.

    `incoming` is a freshly normalized row; missing values never erase stored
    ones. See the module docstring for which side wins on descriptive fields.
    """
    authoritative = detail or existing.get("enriched_at") is None
    out: dict[str, Any] = {"url": incoming.get("url") or existing.get("url")}
    old_filled = set((existing.get("attributes") or {}).get("_description_filled") or [])
    new_filled = set((incoming.get("attributes") or {}).get("_description_filled") or [])

    def preserve_structured(column: str) -> bool:
        return column in new_filled and column not in old_filled and not _empty(existing.get(column))

    for col in _DESCRIPTIVE:
        new, old = incoming.get(col), existing.get(col)
        out[col] = (new if not _empty(new) else old) if authoritative else \
                   (old if not _empty(old) else new)
        if preserve_structured(col):
            out[col] = old
    # Coordinates follow the location text they were geocoded from.
    loc_from_incoming = out["location_text"] == incoming.get("location_text") \
        and incoming.get("lat") is not None
    out["lat"] = incoming.get("lat") if loc_from_incoming else existing.get("lat")
    out["lon"] = incoming.get("lon") if loc_from_incoming else existing.get("lon")
    if out["location_text"] != existing.get("location_text") and not loc_from_incoming:
        out["lat"] = out["lon"] = None

    # make/model/trim: the better-resolved side wins (ties go to the authoritative one).
    new_conf = incoming.get("normalization_confidence") or 0.0
    old_conf = existing.get("normalization_confidence") or 0.0
    take_new = (new_conf > old_conf or (new_conf == old_conf and authoritative)) \
        and incoming.get("make")
    for col in _VEHICLE:
        out[col] = incoming.get(col) if take_new else existing.get(col)
        if col == "trim" and preserve_structured(col) and all(
                existing.get(k) == incoming.get(k) for k in ("make", "model")):
            out[col] = existing.get(col)

    out["published_at"] = existing.get("published_at") or incoming.get("published_at")
    attrs_old, attrs_new = existing.get("attributes") or {}, incoming.get("attributes") or {}
    out["attributes"] = {**attrs_old, **attrs_new} if authoritative else {**attrs_new, **attrs_old}

    # Price: the newest published value wins (cards are for that); the
    # effective one is resolved again from it and the stored facts.
    old_pub, old_pub_cur = _published(existing)
    new_pub, new_pub_cur = _published(incoming)
    published_changed = new_pub is not None and (
        not _same_number(new_pub, old_pub) or (new_pub_cur or old_pub_cur) != old_pub_cur)
    pub, pub_cur = (new_pub, new_pub_cur or old_pub_cur) if published_changed else (old_pub, old_pub_cur)
    out["price_published"], out["price_published_currency"] = pub, pub_cur
    facts_json = _facts(existing, incoming, authoritative=authoritative)
    out["description_facts"] = facts_json
    facts = DescriptionFacts.from_json(facts_json)
    rate = _usd_rate(incoming) if published_changed else (_usd_rate(existing) or _usd_rate(incoming))
    partial_reason = incoming["published_partial_reason"] if "published_partial_reason" in incoming         else (incoming.get("price_partial_reason") or "parcial" if incoming.get("price_partial") else None)
    if not published_changed and partial_reason is None and "published_partial_reason" not in incoming:
        # A legacy row without the reason: keep what was stored.
        partial_reason = existing.get("price_partial_reason") if existing.get("price_partial") else None
    price = resolve_price(pub, pub_cur, partial_reason=partial_reason, facts=facts, usd_rate=rate)
    if facts is not None:
        out["description_facts"] = {**facts_json, "price_check": price.check()}
    out["price"], out["currency"], out["price_source"] = price.price, price.currency, price.source
    out["price_partial"], out["price_partial_reason"] = price.partial, price.partial_reason
    effective_changed = not _same_number(price.price, existing.get("price"))         or price.currency != existing.get("currency")
    if not effective_changed and existing.get("price_usd") is not None:
        # Frozen at the rate of the day it was first observed (sección 14).
        out["price_usd"] = existing["price_usd"]
    elif published_changed and _same_number(price.price, incoming.get("price"))             and price.currency == incoming.get("currency") and incoming.get("price_usd") is not None:
        out["price_usd"] = incoming["price_usd"]
    else:
        out["price_usd"] = _to_usd(price.price, price.currency, rate)
    new_km = incoming.get("mileage_km")
    out["mileage_km"] = new_km if new_km is not None and not preserve_structured("mileage_km") else existing.get("mileage_km")
    derived = []
    for col in ("year", "mileage_km", "transmission", "fuel", "trim"):
        if not _empty(incoming.get(col)) and col not in new_filled and out[col] == incoming[col] and authoritative:
            continue
        if (col in new_filled and out[col] == incoming.get(col) and
                (_empty(existing.get(col)) or col in old_filled or out[col] != existing.get(col))) \
                or (col in old_filled and out[col] == existing.get(col)):
            derived.append(col)
    out["attributes"]["_description_filled"] = derived
    out["fingerprint"] = fingerprint(out)

    changes: list[str] = []
    if published_changed:
        changes.append("price")
    if out["mileage_km"] is not None and out["mileage_km"] != existing.get("mileage_km"):
        changes.append("mileage")
    old_facts, new_facts = existing.get("description_facts") or {}, out.get("description_facts") or {}
    analysis_changed = any(old_facts.get(key) != new_facts.get(key) for key in ("claims", "evidence"))
    if (not _empty(out["description"]) and out["description"] != existing.get("description")) \
            or (effective_changed and not published_changed) or analysis_changed:
        # The effective price moved because of how the text reads.
        changes.append("description")
    if not _empty(out["images"]) and out["images"] != (existing.get("images") or []):
        changes.append("images")
    if attrs_hash(out) != attrs_hash(existing):
        changes.append("attrs")
    return out, changes


def published_view(row: dict[str, Any]) -> dict[str, Any]:
    """The row with its published price as price/currency/price_usd: what
    snapshots store and price drops compare."""
    pub, cur = _published(row)
    if _same_number(pub, row.get("price")) and cur == row.get("currency"):
        pub_usd = row.get("price_usd")
    else:
        pub_usd = _to_usd(pub, cur, _usd_rate(row))
    return {**row, "price": pub, "currency": cur, "price_usd": pub_usd}


def price_drop_pct(old: dict[str, Any], new: dict[str, Any]) -> float | None:
    """How much the price fell, in %. In the listing's own currency when it
    didn't change (an ARS price that stays put is not a drop just because the
    dollar moved), otherwise in USD."""
    if old.get("currency") and old.get("currency") == new.get("currency"):
        before, after = old.get("price"), new.get("price")
    else:
        before, after = old.get("price_usd"), new.get("price_usd")
    if not before or not after or before <= 0 or after >= before:
        return None
    return round((before - after) / before * 100, 2)


# ---------------------------------------------------------------------------
# Database part
# ---------------------------------------------------------------------------

async def ingest_rows(rows: Iterable[dict[str, Any]], *, detail: bool = False,
                      config: IngestConfig | None = None, seen: bool = True) -> IngestResult:
    """Upsert normalized rows in one transaction. Duplicates in the batch (the
    same ad returned by two search pages) collapse to the last one."""
    config = config or IngestConfig()
    batch: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        batch[(row["source"], row["external_id"])] = row
    result = IngestResult(found=len(batch))
    if not batch:
        return result

    async with db.connection() as cx:
        existing = await repo.lock_existing(cx, list(batch))
        for key, row in batch.items():
            old = existing.get(key)
            if old is None:
                stored = await repo.insert_listing(cx, row, detail=detail)
                if stored is None:
                    # Inserted by a concurrent transaction since we looked: diff against it.
                    old = (await repo.lock_existing(cx, [key]))[key]
                else:
                    await _on_insert(cx, stored, row, result, config)
                    continue
            await _on_update(cx, old, row, result, config, detail=detail, seen=seen)
    return result


async def _on_insert(cx, stored: dict[str, Any], row: dict[str, Any], result: IngestResult,
                     config: IngestConfig) -> None:
    lid = stored["id"]
    snap = await repo.insert_snapshot(cx, lid, published_view(stored), "new", attrs_hash(stored))
    original = await repo.find_repost_of(
        cx, listing_id=lid, fingerprint=stored.get("fingerprint"), price_usd=stored.get("price_usd"),
        window_days=config.repost_window_days, price_tol_pct=config.repost_price_tol_pct)
    if original:
        await repo.set_repost_of(cx, lid, original)
    result.new += 1
    result.ids[(stored["source"], stored["external_id"])] = lid
    result.events.append(ListingEvent(
        "listing_new", lid, stored["source"], stored["external_id"], snapshot_id=snap,
        new_price=stored.get("price"), currency=stored.get("currency"), repost_of=original))


async def _on_update(cx, old: dict[str, Any], row: dict[str, Any], result: IngestResult,
                     config: IngestConfig, *, detail: bool, seen: bool = True) -> None:
    lid = old["id"]
    values, changes = merge(old, row, detail=detail)
    await repo.update_listing(cx, lid, values, detail=detail, seen=seen)
    result.ids[(old["source"], old["external_id"])] = lid
    if not changes:
        return
    before, after = published_view(old), published_view(values)
    snap = await repo.insert_snapshot(cx, lid, after, changes[0], attrs_hash(values))
    result.updated += 1
    base = dict(listing_id=lid, source=old["source"], external_id=old["external_id"],
                changes=tuple(changes), snapshot_id=snap, old_price=before.get("price"),
                new_price=after.get("price"), currency=after.get("currency"),
                old_currency=before.get("currency"), repost_of=old.get("probable_repost_of"))
    result.events.append(ListingEvent("listing_updated", **base))
    if "price" in changes and (drop := price_drop_pct(before, after)) is not None \
            and drop >= config.price_drop_min_pct:
        result.events.append(ListingEvent("price_drop", drop_pct=drop, **base))


# ---------------------------------------------------------------------------
# From collector output to rows
# ---------------------------------------------------------------------------

async def _geocode_rows(rows: list[dict[str, Any]], geocode: GeocodeFn) -> None:
    cache: dict[str, tuple[float, float] | None] = {}
    for row in rows:
        loc = row.get("location_text")
        if not loc:
            continue
        if loc not in cache:
            try:
                cache[loc] = await geocode(loc)
            except Exception:
                log.warning("geocode failed for %r", loc, exc_info=True)
                cache[loc] = None
        if cache[loc]:
            row["lat"], row["lon"] = cache[loc]


async def normalize_items(items: Iterable[Listing], *, target: Target | None = None,
                          geocode: GeocodeFn | None = geocode_location) -> list[dict[str, Any]]:
    """Normalize collector output. An item that fails is recorded in
    pipeline_errors (stage 'normalize') and skipped; the rest go on."""
    async with db.connection() as cx:
        catalog = await load_models(cx)
        fx = await quote_for_today(cx)
    rows: list[dict[str, Any]] = []
    for item in items:
        try:
            rows.append(normalize_listing(item, catalog=catalog, target=target, fx=fx))
        except Exception:
            await log_error("normalize", f"{item.source}:{item.listing_id}", traceback.format_exc())
    if geocode is not None:
        await _geocode_rows(rows, geocode)
    return rows


async def ingest(items: Iterable[Listing], *, target: Target | None = None, detail: bool = False,
                 seen: bool = True,
                 geocode: GeocodeFn | None = geocode_location,
                 config: IngestConfig | None = None) -> IngestResult:
    """normalize → geocode → upsert. The whole batch is one transaction."""
    items = list(items)
    rows = await normalize_items(items, target=target, geocode=geocode)
    result = await ingest_rows(rows, detail=detail, config=config or await IngestConfig.load(), seen=seen)
    # Legacy consumers (the Telegram opportunity engine) read make/model from
    # the Listing: give them the catalog's names instead of the raw ones.
    by_key = {(r["source"], r["external_id"]): r for r in rows}
    for item in items:
        if row := by_key.get((item.source, str(item.listing_id))):
            item.marca, item.modelo = row["make"] or item.marca, row["model"] or item.modelo
    return result
