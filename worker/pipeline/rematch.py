"""Bootstrap of new or edited profiles (sección 5.7).

A profile that was never bootstrapped, or whose filters changed
(`rematch_requested_at`), is matched against the active listings of the
last 30 days already stored. Those matches are backfill: the user sees them
in the web right away ("first value", §36), and they are never notified.

Until F2 brings matching with reasons, "matching" here is the Telegram bot's
filter check (BaseScraper.matches_filters + radius), the same one the crawl
applies to new listings.
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime
from typing import Any

import db
from collectors.base import Listing
from db.repos.listings import recent_active
from db.repos.runs import log_error
from pipeline.legacy_match import candidates_for


log = logging.getLogger("rematch")

BACKFILL_DAYS = 30

# Canonical column values → the wizard's spelling, which matches_filters compares.
_TRANSMISSION = {"manual": "Manual", "automatic": "Automática"}
_SELLER = {"private": "particular", "dealer": "concesionaria"}


def listing_from_row(row: dict[str, Any]) -> Listing:
    """A stored listing in the shape the legacy filters and opportunity engine read."""
    published: datetime | None = row.get("published_at")
    return Listing(
        source=row["source"],
        listing_id=row["external_id"],
        titulo=row["title"],
        url=row["url"],
        precio=row.get("price"),
        moneda=row.get("currency"),
        marca=row.get("make"),
        modelo=row.get("model"),
        anio=row.get("year"),
        km=row.get("mileage_km"),
        ubicacion=row.get("location_text"),
        combustible=row.get("fuel"),
        transmision=_TRANSMISSION.get(row.get("transmission") or ""),
        vendedor=_SELLER.get(row.get("seller_type") or ""),
        published_at=int(published.timestamp()) if published else None,
        price_partial=bool(row.get("price_partial")),
        price_partial_reason=row.get("price_partial_reason"),
        version=row.get("trim"),
        descripcion=row.get("description"),
        imagenes=list(row.get("images") or []),
    )


async def rematch_profile(alert: dict) -> int:
    """Backfill one profile. Returns how many listings it matched."""
    rows = await recent_active(alert.get("make"), alert.get("model"), days=BACKFILL_DAYS,
                               sources=alert["filters"].get("sources"))
    by_source: dict[str, list[Listing]] = {}
    for r in rows:
        by_source.setdefault(r["source"], []).append(listing_from_row(r))
    matched: list[Listing] = []
    for source, items in by_source.items():
        matched += await candidates_for(alert, items, source)
    if matched:
        await db.mark_seen(alert["id"], [l.to_dict() for l in matched], backfill=True)
    await db.mark_bootstrapped(alert["id"])
    return len(matched)


async def run_pending() -> int:
    """Bootstrap every profile that needs it. Returns how many were processed."""
    done = 0
    for alert in await db.pending_rematch():
        try:
            n = await rematch_profile(alert)
            log.info("profile=%s rematch: %d backfill matches", alert["id"], n)
            done += 1
        except Exception:
            await log_error("rematch", f"profile:{alert['id']}", traceback.format_exc())
    return done
