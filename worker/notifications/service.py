"""From pipeline events to notifications rows (sección 7).

    new matches (pipeline/scheduler.py)          ─┐
    price_drop / listing_gone (ingest, enrich,    ├─▶ engine.decide_all ─▶ notifications
      watchlist: pipeline/ingest.ListingEvent)   ─┘         (queued | digest)

The `Notifier` owns the channels: an event only becomes rows for the
channels the user can receive (Telegram linked, an email, a configured
adapter). `deliver()` then sends what is queued (notifications/dispatch.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

import db
from db.repos import listings as listings_repo
from db.repos import notifications as repo
from intelligence.config import DEFAULT_COMPARABLES
from notifications import dispatch
from notifications.channels.base import Channel
from notifications.engine import LISTING_GONE, MATCH, PRICE_DROP, Audience, Event, Rules, decide_all
from notifications.templates import MAX_FLAGS


log = logging.getLogger("notifications")

# America/Argentina/Buenos_Aires (no DST since 2009): "today" for the daily cap.
AR = timezone(timedelta(hours=-3))


@dataclass(frozen=True)
class MatchCandidate:
    """A new, non-backfill match the crawl just stored."""
    profile_id: int
    listing_id: int
    match_id: int | None
    evaluation: Mapping[str, Any]        # Evaluation.row(): score, level, price_ref, red_flags
    repost: bool = False


async def load_rules() -> Rules:
    return Rules(alerts_max_per_user_day=int(await db.get_config("alerts_max_per_user_day", 10)),
                 price_drop_min_pct=float(await db.get_config("price_drop_min_pct", 3)))


def start_of_day(now: datetime) -> datetime:
    return now.astimezone(AR).replace(hour=0, minute=0, second=0, microsecond=0)


def deliverable(channels: Iterable[str], contact: Mapping[str, Any], available: Iterable[str]) -> tuple[str, ...]:
    """The profile's channels the user can actually receive."""
    available = set(available)
    out = []
    for ch in channels or ():
        if ch not in available:
            continue
        if ch == "telegram" and not contact.get("telegram_chat_id"):
            continue
        if ch == "email" and not contact.get("email"):
            continue
        out.append(ch)
    return tuple(dict.fromkeys(out))


# ---------------------------------------------------------------------------
# Payloads: what a notification needs to be rendered later, on any channel
# ---------------------------------------------------------------------------

def _iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def listing_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("title", "make", "model", "trim", "year", "mileage_km", "price", "currency", "url",
            "source", "location_text", "published_at", "first_seen_at")
    out = {k: _iso(row.get(k)) for k in keys}
    if out["price"] is not None:
        out["price"] = float(out["price"])
    out["id"] = row.get("id")
    # What the description says (normalization/description_facts.py): the
    # price is the cash one, the car can be financed.
    facts = row.get("description_facts") or {}
    if (facts.get("price_check") or {}).get("effective_kind") == "cash":
        out["price_kind"] = "cash"
    if (facts.get("financing") or {}).get("offered"):
        out["financing"] = True
    return out


def match_payload(match: Mapping[str, Any], min_n: int) -> dict[str, Any]:
    """Score and level; diff_pct only with enough comparables (§19)."""
    ref = match.get("price_ref") or {}
    enough = int(ref.get("n") or 0) >= min_n and ref.get("median")
    diff = ref.get("diff_pct") if enough else None
    return {"score": match.get("score"), "level": match.get("level"),
            "diff_pct": float(diff) if diff is not None else None}


def flag_texts(red_flags: Iterable[Mapping[str, Any]] | None) -> list[str]:
    flags = sorted(red_flags or [], key=lambda f: f.get("severity") != "warning")
    return [f["text"] for f in flags[:MAX_FLAGS]]


def payload(listing: Mapping[str, Any], match: Mapping[str, Any] | None, *, min_n: int,
            profile_name: str | None = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"listing": listing_payload(listing), "profile_name": profile_name}
    if match and match.get("level"):
        out["match"] = match_payload(match, min_n)
        out["red_flags"] = flag_texts(match.get("red_flags"))
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


async def _min_n() -> int:
    cfg = await db.get_config("comparables", {}) or {}
    return int(cfg.get("min_n", DEFAULT_COMPARABLES["min_n"]))


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------

class Notifier:
    def __init__(self, channels: Mapping[str, Channel]) -> None:
        self.channels = dict(channels)

    @property
    def available(self) -> set[str]:
        return set(self.channels)

    def _audience(self, row: Mapping[str, Any]) -> Audience:
        return Audience(user_id=str(row["user_id"]),
                        channels=deliverable(row.get("channels") or (), row, self.available),
                        frequency=row.get("frequency") or "immediate",
                        min_level=row.get("min_level") or "good",
                        profile_id=row.get("profile_id"))

    async def on_matches(self, candidates: list[MatchCandidate], rows: Mapping[int, Mapping[str, Any]], *,
                         now: datetime | None = None) -> list[int]:
        """New matches → notifications. `rows` are the listings by id."""
        if not candidates:
            return []
        audiences = await repo.profile_audiences(c.profile_id for c in candidates)
        pairs = [(str(audiences[c.profile_id]["user_id"]), c.listing_id)
                 for c in candidates if c.profile_id in audiences]
        states = await repo.interactions(pairs)
        min_n = await _min_n()
        events = []
        for c in candidates:
            a = audiences.get(c.profile_id)
            listing = rows.get(c.listing_id)
            if a is None or listing is None:
                continue
            state = states.get((str(a["user_id"]), c.listing_id)) or {}
            ev = c.evaluation
            events.append(Event(
                MATCH, c.listing_id, self._audience(a), level=ev["level"], score=ev["score"],
                match_id=c.match_id, repost=c.repost, saved=bool(state.get("saved")),
                status=state.get("status"),
                payload=payload(listing, ev, min_n=min_n, profile_name=a["profile_name"])))
        return await self._commit(events, now=now)

    async def on_listing_events(self, listing_events: Iterable[Any], *,
                                now: datetime | None = None) -> list[int]:
        """price_drop and listing_gone (pipeline/ingest.ListingEvent) → notifications.
        Run after re-scoring, so a price_drop carries the new score."""
        wanted = [e for e in listing_events if e.kind in (PRICE_DROP, LISTING_GONE)]
        if not wanted:
            return []
        ids = list(dict.fromkeys(e.listing_id for e in wanted))
        async with db.connection() as cx:
            rows = await listings_repo.rows_for_scoring(cx, ids)
        by_listing: dict[int, list[dict[str, Any]]] = {}
        for a in await repo.listing_audiences(ids):
            by_listing.setdefault(a["listing_id"], []).append(a)
        min_n = await _min_n()
        events = []
        for e in wanted:
            listing = rows.get(e.listing_id)
            if listing is None:
                continue
            for a in by_listing.get(e.listing_id, []):
                drop = None
                if e.kind == PRICE_DROP:
                    drop = {"old_price": _num(e.old_price), "new_price": _num(e.new_price),
                            "currency": e.currency, "old_currency": e.old_currency or e.currency,
                            "drop_pct": e.drop_pct}
                events.append(Event(
                    e.kind, e.listing_id, self._audience(a), level=a.get("level"), score=a.get("score"),
                    match_id=a.get("match_id"), saved=bool(a.get("saved")), status=a.get("status"),
                    snapshot_id=e.snapshot_id, drop_pct=e.drop_pct,
                    payload=payload(listing, a, min_n=min_n, profile_name=a.get("profile_name"),
                                    price_drop=drop)))
        return await self._commit(events, now=now)

    async def _commit(self, events: list[Event], *, now: datetime | None = None) -> list[int]:
        if not events:
            return []
        now = now or datetime.now(timezone.utc)
        users = {e.audience.user_id for e in events}
        existing = await repo.existing_keys(users, {e.listing_id for e in events})
        counts = await repo.sent_today(users, start_of_day(now))
        decisions = decide_all(events, await load_rules(), sent_today=counts, existing=existing)
        ids = await repo.insert_decisions(decisions)
        if decisions:
            log.info("notifications: %d events → %d decisions, %d new rows", len(events),
                     len(decisions), len(ids))
        return ids

    async def deliver(self) -> int:
        return await dispatch.deliver_pending(self.channels)


def _num(value: Any) -> float | None:
    return float(value) if value is not None else None
