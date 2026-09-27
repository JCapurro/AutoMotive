"""The Telegram bot's boolean filter check, shared by the crawl batches and rematch.

F2 replaces it with intelligence/matching.py (reasons, soft preferences,
currency conversion instead of discarding).
"""
from __future__ import annotations

from collectors import REGISTRY
from collectors.base import BaseScraper, Listing
from normalization.geo import filter_listings_by_radius
from normalization.normalize import normalize_brand, normalize_text


def same_vehicle(item: Listing, alert: dict) -> bool:
    """The listing's normalized make/model agree with the alert's. A search for
    "Ford Fiesta" also returns other models; those aren't this alert's."""
    if alert.get("make") and item.marca and normalize_brand(item.marca) != normalize_brand(alert["make"]):
        return False
    if alert.get("model") and item.modelo and normalize_text(item.modelo) != normalize_text(alert["model"]):
        return False
    return True


async def candidates_for(alert: dict, items: list[Listing], source: str) -> list[Listing]:
    """The items this alert's own filters (and radius) accept."""
    f = alert["filters"]
    matcher = REGISTRY[source].matches_filters if source in REGISTRY else BaseScraper.matches_filters
    kept = [l for l in items if same_vehicle(l, alert) and matcher(l, f)]
    return await filter_listings_by_radius(kept, f)
