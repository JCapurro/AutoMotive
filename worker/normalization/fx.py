"""USD/ARS rate fetcher with TTL cache.

For pricing used cars in AR, the "blue" (informal) market rate is the
de-facto reference for private sellers. We fall back to the official rate
if the API is unreachable, and finally to a hardcoded constant.
"""
from __future__ import annotations
import time
import threading
import logging
from typing import NamedTuple

import httpx


log = logging.getLogger("fx")

_BLUE_URL = "https://dolarapi.com/v1/dolares/blue"
_OFICIAL_URL = "https://dolarapi.com/v1/dolares/oficial"
_FALLBACK_RATE = 1100.0       # used if everything fails — keeps the system working
_TTL_SECONDS = 3600           # refresh at most once per hour

_cache: dict = {"quote": None, "fetched_at": 0.0}
_lock = threading.Lock()


class FxQuote(NamedTuple):
    rate: float
    # 'blue' | 'oficial'; None for the hardcoded fallback, which is never persisted.
    kind: str | None
    source: str | None


def _fetch_quote() -> FxQuote | None:
    """Try blue first, then oficial. The rate is the average of buy/sell."""
    for kind, url in (("blue", _BLUE_URL), ("oficial", _OFICIAL_URL)):
        try:
            r = httpx.get(url, timeout=8, headers={"User-Agent": "AutoMotive/1.0"})
            r.raise_for_status()
            data = r.json()
            buy = float(data.get("compra") or 0)
            sell = float(data.get("venta") or 0)
            if buy > 0 and sell > 0:
                return FxQuote((buy + sell) / 2, kind, "dolarapi")
            if sell > 0:
                return FxQuote(sell, kind, "dolarapi")
        except Exception as e:
            log.warning("FX %s failed: %s", url, e)
    return None


def usd_ars_quote() -> FxQuote:
    """The current USD→ARS quote, cached for `_TTL_SECONDS`. Always returns a
    positive rate (a hardcoded constant, kind=None, on total failure)."""
    now = time.time()
    with _lock:
        if _cache["quote"] and (now - _cache["fetched_at"]) < _TTL_SECONDS:
            return _cache["quote"]
        quote = _fetch_quote()
        if quote and quote.rate > 0:
            _cache["quote"] = quote
            _cache["fetched_at"] = now
            return quote
        # API failed — keep last known value if any
        if _cache["quote"]:
            log.warning("FX refresh failed; using stale rate %.2f", _cache["quote"].rate)
            return _cache["quote"]
        log.warning("FX refresh failed and no cache; using fallback %.0f", _FALLBACK_RATE)
        return FxQuote(_FALLBACK_RATE, None, None)


def usd_ars_rate() -> float:
    """Return the current USD→ARS rate (see `usd_ars_quote`)."""
    return usd_ars_quote().rate
