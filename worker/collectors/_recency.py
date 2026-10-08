"""Publication windows for high-volume sources; detection time is not publication."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time

from .base import Listing

DAY = 86_400
ARGENTINA = timezone(timedelta(hours=-3))
SOURCES = frozenset({"mercadolibre", "facebook"})
POLICY_VERSION = 1


@dataclass(frozen=True)
class PublicationWindow:
    since: int
    until: int
    days: int
    today_only: bool = False

    @classmethod
    def from_filters(cls, filters: dict) -> "PublicationWindow | None":
        if "publication_days" not in filters:
            return None  # CLI/other collectors retain their explicit legacy behavior.
        days = int(filters["publication_days"])
        if not 1 <= days <= 30:
            raise ValueError("publication_days must be between 1 and 30")
        now = int(filters.get("publication_until", time.time()))
        since = int(filters.get("published_since", now - days * DAY))
        return cls(since, now, days, bool(filters.get("published_today_only")))

    def contains(self, item: Listing) -> bool:
        return (item.published_at is not None
                and self.since <= item.published_at <= max(self.until, int(time.time())))

    @property
    def facebook_days(self) -> int:
        # Facebook only offers these buckets. Exact dates are checked locally too.
        span = self.until - self.since
        return next((d for d in (1, 7, 30) if span <= d * DAY), 30)


def target_window(target: dict, *, now: int | None = None) -> dict:
    """30-day bootstrap; then daily reads, widened after a gap (maximum 30 days)."""
    if target.get("source") not in SOURCES:
        return {}
    now = int(time.time()) if now is None else now
    if not target.get("first_run_done"):
        since, days, today = now - 30 * DAY, 30, False
    else:
        midnight = int(datetime.fromtimestamp(now, ARGENTINA).replace(
            hour=0, minute=0, second=0, microsecond=0).timestamp())
        daily = midnight if target["source"] == "mercadolibre" else now - DAY
        previous = target.get("last_run_at")
        previous = int(previous.timestamp()) if previous is not None else daily
        # Overlap prevents boundary gaps; IDs handle duplicate results.
        since = max(now - 30 * DAY, min(daily, previous - 600))
        days = min(30, max(1, (now - since + DAY - 1) // DAY))
        today = target["source"] == "mercadolibre" and since >= midnight
    return {"publication_days": days, "published_since": since,
            "publication_until": now, "published_today_only": today}
