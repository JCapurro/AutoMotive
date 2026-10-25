"""Publication windows for high-volume sources; detection time is not publication."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import time
from typing import Iterable

from .base import Listing

DAY = 86_400
ARGENTINA = timezone(timedelta(hours=-3))
SOURCES = frozenset({"mercadolibre", "facebook"})
POLICY_VERSION = 1
# What Mercado Libre's "Publicados hoy" covers with a run's overlap: the last 24
# hours, plus an hour for the window's 10-minute overlap and scheduling delays
# (mercadolibre.py). A window up to it is read through that filter (one_request_read).
TODAY_SPAN = 25 * 3600
# The widest window of a target by body type: what "Publicados hoy" covers.
BODY_TYPE_SPAN = TODAY_SPAN

# Facebook's date memory: the item pages a target by model already read for
# their date, kept in crawl_targets.prefilter_rejected (pipeline/crawl.py
# run_target). An item page is what a scan spends (RECENT_FB_DETAIL_SECONDS
# apart, RECENT_FB_MAX_DATE_FETCHES per scan), and without it every scan read
# the same pages again (Corolla, 2026-10-22: 30 pages and nothing new).
# - "id": dated before the window. `since` never moves back while the
#   publication policy holds (target_window), so it never gets in: its page is
#   not read again. sync_targets empties the memory with a new policy.
# - "id@epoch#n": its page loaded without a date, n times, the first at epoch.
#   Read again DATE_RETRY_SECONDS after epoch, all within the day the window
#   then covered, and skipped after the last. Once dated it gets in if
#   published within that day, even before today's `since`.
DATE_RETRY_SECONDS = (30 * 60, 2 * 3600, 6 * 3600)
# The memory a target keeps at most; past it the oldest IDs go (and are read once more).
DATE_MEMORY_CAP = 3000


@dataclass(frozen=True)
class DateSkip:
    """One remembered item page: dated out of the window (epoch None) or read
    `reads` times without a date, the first at `epoch`."""
    epoch: int | None = None
    reads: int = 0

    def skips(self, now: int) -> bool:
        """Whether a scan at `now` leaves the page unread."""
        if self.epoch is None or self.reads > len(DATE_RETRY_SECONDS):
            return True
        return now < self.epoch + DATE_RETRY_SECONDS[max(1, self.reads) - 1]

    @staticmethod
    def undated(previous: "DateSkip | None", now: int) -> "DateSkip":
        """The entry after a read without a date at `now`."""
        if previous is None or previous.epoch is None:
            return DateSkip(now, 1)
        return DateSkip(previous.epoch, previous.reads + 1)


def parse_date_skips(entries: Iterable[str] | None) -> dict[str, DateSkip]:
    """prefilter_rejected as a date memory. A malformed entry is forgotten:
    its page is read again."""
    out: dict[str, DateSkip] = {}
    for entry in entries or ():
        ident, sep, rest = str(entry).partition("@")
        if not ident:
            continue
        if not sep:
            out[ident] = DateSkip()
            continue
        stamp, _, reads = rest.partition("#")
        try:
            out[ident] = DateSkip(int(stamp), max(1, int(reads or 1)))
        except ValueError:
            continue
    return out


def encode_date_skips(memory: dict[str, DateSkip]) -> list[str]:
    """The memory as prefilter_rejected, the newest DATE_MEMORY_CAP IDs."""
    def newest(ident: str) -> tuple[int, str]:
        return len(ident), ident             # numeric IDs, by length first

    kept = sorted(memory, key=newest)[-DATE_MEMORY_CAP:]
    return sorted(i if memory[i].epoch is None else f"{i}@{memory[i].epoch}#{memory[i].reads}"
                  for i in kept)


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

    def admits(self, item: Listing, remembered: DateSkip | None = None) -> bool:
        """contains, or, for an ad whose page had no date at `remembered.epoch`,
        published within the day before it: the window it was seen in."""
        if self.contains(item):
            return True
        return (remembered is not None and remembered.epoch is not None and item.published_at is not None
                and remembered.epoch - DAY <= item.published_at <= max(self.until, int(time.time())))

    @property
    def facebook_days(self) -> int:
        # Facebook only offers these buckets. Exact dates are checked locally too.
        span = self.until - self.since
        return next((d for d in (1, 7, 30) if span <= d * DAY), 30)


def one_request_read(source: str, filters: dict, window: PublicationWindow | None = None) -> bool:
    """Whether this read of `source` goes through Mercado Libre's "Publicados
    hoy": a window up to TODAY_SPAN, today's, or a count-only target's (2.5).
    One request for the day's cards, dated by the filter, while a longer
    window (a first run, a gap) dates every card, one ad page each
    (mercadolibre._search_recent). pipeline/crawl.py reads the reference year
    band only then, so the two never disagree. `window`: the one already
    parsed from `filters`."""
    if source != "mercadolibre":
        return False
    window = window or PublicationWindow.from_filters(filters)
    if window is None:
        return False
    return window.today_only or filters.get("count_only") is True or window.until - window.since <= TODAY_SPAN


def target_window(target: dict, *, now: int | None = None) -> dict:
    """30-day bootstrap; then daily reads, widened after a gap (maximum 30 days).

    A target by body type (docs/CARROCERIA.md) reads the last day, widened to
    BODY_TYPE_SPAN at most after a gap, also on its first run: Mercado Libre's
    "Publicados hoy". A body type is too many listings for 30 days; its
    searches are backfilled from the stored listings (pipeline/rematch.py)."""
    if target.get("source") not in SOURCES:
        return {}
    now = int(time.time()) if now is None else now
    if target.get("body_type"):
        previous = target.get("last_run_at") if target.get("first_run_done") else None
        since = now - DAY if previous is None else min(now - DAY, int(previous.timestamp()) - 600)
        since = max(now - BODY_TYPE_SPAN, since)
        return {"publication_days": max(1, (now - since + DAY - 1) // DAY), "published_since": since,
                "publication_until": now, "published_today_only": target["source"] == "mercadolibre"}
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
