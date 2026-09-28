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


def merge(existing: dict[str, Any], incoming: dict[str, Any], *,
          detail: bool) -> tuple[dict[str, Any], list[str]]:
    """Values to write over `existing` and the change kinds they amount to.

    `incoming` is a freshly normalized row; missing values never erase stored
    ones. See the module docstring for which side wins on descriptive fields.
    """
    authoritative = detail or existing.get("enriched_at") is None
    out: dict[str, Any] = {"url": incoming.get("url") or existing.get("url")}

    for col in _DESCRIPTIVE:
        new, old = incoming.get(col), existing.get(col)
        out[col] = (new if not _empty(new) else old) if authoritative else \
                   (old if not _empty(old) else new)
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

    out["published_at"] = existing.get("published_at") or incoming.get("published_at")
    attrs_old, attrs_new = existing.get("attributes") or {}, incoming.get("attributes") or {}
    out["attributes"] = {**attrs_old, **attrs_new} if authoritative else {**attrs_new, **attrs_old}

    # Price and mileage are what cards are for: the newest non-empty value wins.
    price_changed = incoming.get("price") is not None and (
        not _same_number(incoming["price"], existing.get("price"))
        or (incoming.get("currency") or existing.get("currency")) != existing.get("currency"))
    if price_changed:
        out["price"] = incoming["price"]
        out["currency"] = incoming.get("currency") or existing.get("currency")
        out["price_usd"] = incoming.get("price_usd")
        out["price_partial"] = bool(incoming.get("price_partial"))
        out["price_partial_reason"] = incoming.get("price_partial_reason")
    else:
        out["price"] = existing.get("price")
        out["currency"] = existing.get("currency")
        # Frozen at the rate of the day it was first observed (sección 14).
        out["price_usd"] = existing.get("price_usd") if existing.get("price_usd") is not None \
            else incoming.get("price_usd")
        partial = bool(incoming.get("price_partial") or existing.get("price_partial"))
        out["price_partial"] = partial
        out["price_partial_reason"] = (incoming.get("price_partial_reason")
                                       or existing.get("price_partial_reason")) if partial else None
    new_km = incoming.get("mileage_km")
    out["mileage_km"] = new_km if new_km is not None else existing.get("mileage_km")
    out["fingerprint"] = fingerprint(out)

    changes: list[str] = []
    if price_changed:
        changes.append("price")
    if new_km is not None and new_km != existing.get("mileage_km"):
        changes.append("mileage")
    if not _empty(out["description"]) and out["description"] != existing.get("description"):
        changes.append("description")
    if not _empty(out["images"]) and out["images"] != (existing.get("images") or []):
        changes.append("images")
    if attrs_hash(out) != attrs_hash(existing):
        changes.append("attrs")
    return out, changes


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
                      config: IngestConfig | None = None) -> IngestResult:
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
            await _on_update(cx, old, row, result, config, detail=detail)
    return result


async def _on_insert(cx, stored: dict[str, Any], row: dict[str, Any], result: IngestResult,
                     config: IngestConfig) -> None:
    lid = stored["id"]
    snap = await repo.insert_snapshot(cx, lid, stored, "new", attrs_hash(stored))
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
                     config: IngestConfig, *, detail: bool) -> None:
    lid = old["id"]
    values, changes = merge(old, row, detail=detail)
    await repo.update_listing(cx, lid, values, detail=detail)
    result.ids[(old["source"], old["external_id"])] = lid
    if not changes:
        return
    snap = await repo.insert_snapshot(cx, lid, values, changes[0], attrs_hash(values))
    result.updated += 1
    base = dict(listing_id=lid, source=old["source"], external_id=old["external_id"],
                changes=tuple(changes), snapshot_id=snap, old_price=old.get("price"),
                new_price=values.get("price"), currency=values.get("currency"),
                old_currency=old.get("currency"), repost_of=old.get("probable_repost_of"))
    result.events.append(ListingEvent("listing_updated", **base))
    if "price" in changes and (drop := price_drop_pct(old, values)) is not None \
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
                 geocode: GeocodeFn | None = geocode_location,
                 config: IngestConfig | None = None) -> IngestResult:
    """normalize → geocode → upsert. The whole batch is one transaction."""
    items = list(items)
    rows = await normalize_items(items, target=target, geocode=geocode)
    result = await ingest_rows(rows, detail=detail, config=config or await IngestConfig.load())
    # Legacy consumers (the Telegram opportunity engine) read make/model from
    # the Listing: give them the catalog's names instead of the raw ones.
    by_key = {(r["source"], r["external_id"]): r for r in rows}
    for item in items:
        if row := by_key.get((item.source, str(item.listing_id))):
            item.marca, item.modelo = row["make"] or item.marca, row["model"] or item.modelo
    return result
