"""Agencias (docs/superpowers/specs/2026-11-18-agencias-design.md §2 and §4.2): pure rules.

A dealer's car is a row of `listings` like any other: either a listing of the
new source 'directo' (stock the agency loaded by hand or with a sheet, which
pipeline/dealers.py turns into a listing through the same ingest) or a portal
listing we already read, marked with listings.dealer_id. Nothing here scores:
the send gate only ever *excludes* (hidden_reason), and the label only names
the dealer. Same algorithm, same daily cap and thresholds as any listing (C1).

`hidden_reason` is the exact twin of public.dealer_listing_hidden() (migration
20261228120000_dealer_program.sql): the first case that applies wins.

    1  dealer_id null, source not 'directo'           → None (a listing like any other)
    8  synced (dealer_id, not 'directo'), reserved/sold → 'not_available'
    9  synced                                           → None
    2  'directo' without dealer_id                    → 'no_dealer'
    3  'directo', channel off                         → 'channel_off'
    4  'directo', dealer not approved or not active   → 'not_approved'
    5  'directo', dealer_status not 'available'       → 'not_available'
    6  'directo', unconfirmed for manual_confirm_days → 'unconfirmed'
    7  'directo'                                      → None (sent)

The listing row carries dealer_approved and dealer_active from
db/repos/listings.rows_for_scoring (LEFT JOIN dealers).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from intelligence import copy

DEALER_SOURCE = "directo"
HIDDEN_REASONS = ("no_dealer", "channel_off", "not_approved", "not_available", "unconfirmed")


def is_dealer_listing(listing: Mapping[str, Any]) -> bool:
    """A listing of a dealer's stock: marked with a dealer or loaded directly."""
    return listing.get("dealer_id") is not None or listing.get("source") == DEALER_SOURCE


def _aware(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def hidden_reason(listing: Mapping[str, Any], program: Mapping[str, Any], *, now: datetime) -> str | None:
    """Why this listing is not sent to buyers (§2), or None."""
    source, dealer_id = listing.get("source"), listing.get("dealer_id")
    if dealer_id is None and source != DEALER_SOURCE:
        return None
    if source != DEALER_SOURCE:
        return "not_available" if listing.get("dealer_status") in ("reserved", "sold") else None
    if dealer_id is None:
        return "no_dealer"
    if not (program.get("enabled") is True and program.get("channel_enabled") is True):
        return "channel_off"
    if not (listing.get("dealer_approved") is True and listing.get("dealer_active") is True):
        return "not_approved"
    if listing.get("dealer_status") != "available":
        return "not_available"
    confirmed = _aware(listing.get("dealer_confirmed_at"))
    days = program.get("manual_confirm_days")
    days = days if isinstance(days, int) and not isinstance(days, bool) else 7
    if confirmed is None or confirmed < now - timedelta(days=days):
        return "unconfirmed"
    return None


def label(listing: Mapping[str, Any], program: Mapping[str, Any], *, now: datetime) -> dict[str, str] | None:
    """The «Agencia» label buyers see on an alert: {"label": "Agencia", "name": …}
    with the channel on, the dealer approved and active, its name known and the
    listing not hidden; otherwise None (an ordinary listing never has one)."""
    if listing.get("dealer_id") is None:
        return None
    if not (program.get("enabled") is True and program.get("channel_enabled") is True):
        return None
    if listing.get("dealer_approved") is not True or listing.get("dealer_active") is not True:
        return None
    name = listing.get("dealer_name")
    if not isinstance(name, str) or not name.strip():
        return None
    if hidden_reason(listing, program, now=now) is not None:
        return None
    return {"label": copy.DEALER_LABEL, "name": name.strip()}


def private_only(filters: Mapping[str, Any]) -> bool:
    """filters.seller_types has valid values and none is 'dealer': the search
    never gets a dealer's car (C4), whatever its plan."""
    from intelligence.matching import seller_types   # matching imports this module

    wanted = seller_types(filters or {})
    return bool(wanted) and "dealer" not in wanted
