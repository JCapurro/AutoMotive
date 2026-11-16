"""Is the hook car still published? A car Juan offers that is already gone burns the contact.

The listing's own page is read with the collector's parse_detail, the same one the
worker trusts to mark a listing gone. Plain GETs, one at a time, a few seconds apart:
about 60 pages a day. Facebook is never fetched (its pages need the VPS session, which
this bot does not touch): there the proof is the collector having seen the card lately.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

import httpx

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/131.0 Safari/537.36", "Accept-Language": "es-AR,es;q=0.9"}
PAUSE_S = 4.0
# A card the Facebook collector saw this recently counts as published (it re-reads feeds every few hours).
SEEN_MAX_AGE = timedelta(hours=12)


@dataclass(frozen=True)
class Check:
    state: str                 # 'online' | 'gone' | 'unknown'
    how: str                   # 'pagina' (its page) | 'colector' (seen by the collector)
    at: datetime
    reason: str | None = None


def _parser(source: str) -> tuple[Callable[[str, str, int], Any], bool] | None:
    """(parse_detail, follow_redirects) for the sources whose page a plain GET reads."""
    if source == "mercadolibre":
        from collectors.mercadolibre import parse_detail
        return parse_detail, True
    if source == "deruedas":
        from collectors.deruedas import DeRuedasScraper
        return DeRuedasScraper.parse_detail, False       # a removed ad answers 302 to the home page
    if source == "rosariogarage":
        from collectors.rosariogarage import RosarioGarageScraper
        return RosarioGarageScraper.parse_detail, False
    return None


class Checker:
    def __init__(self, *, get: Callable[..., Any] | None = None, now: Callable[[], datetime] | None = None,
                 pause_s: float = PAUSE_S, sleep: Callable[[float], None] = time.sleep):
        self._get = get or (lambda url, follow: httpx.get(url, headers=_HEADERS, timeout=25, follow_redirects=follow))
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._pause, self._sleep = pause_s, sleep
        self._last = 0.0
        self._cache: dict[int, Check] = {}

    def check(self, row: Mapping[str, Any]) -> Check:
        if row["id"] in self._cache:
            return self._cache[row["id"]]
        result = self._check(row)
        self._cache[row["id"]] = result
        return result

    def _check(self, row: Mapping[str, Any]) -> Check:
        now = self._now()
        parser = _parser(row.get("source") or "")
        if parser is None or not row.get("url"):
            seen = row.get("last_seen_at")
            if seen and now - seen <= SEEN_MAX_AGE:
                return Check("online", "colector", seen)
            return Check("unknown", "colector", now, "sin lectura reciente")
        parse, follow = parser
        wait = self._pause - (time.monotonic() - self._last)
        if self._last and wait > 0:
            self._sleep(wait)
        try:
            resp = self._get(row["url"], follow)
            detail = parse(resp.text, str(getattr(resp, "url", row["url"])), resp.status_code)
        except Exception as e:                       # a failed read never proves a removal
            return Check("unknown", "pagina", now, f"{type(e).__name__}: {str(e)[:80]}")
        finally:
            self._last = time.monotonic()
        if getattr(detail, "gone", False):
            return Check("gone", "pagina", now, detail.gone_reason)
        return Check("online", "pagina", now)
