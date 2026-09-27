"""USD/ARS rate fetcher with TTL cache.

For pricing used cars in AR, the "blue" (informal) market rate is the
de-facto reference for private sellers. We fall back to the official rate
if the API is unreachable, and finally to a hardcoded constant.
"""
from __future__ import annotations
import time
import threading
import logging

import httpx


log = logging.getLogger("fx")

_BLUE_URL = "https://dolarapi.com/v1/dolares/blue"
_OFICIAL_URL = "https://dolarapi.com/v1/dolares/oficial"
_FALLBACK_RATE = 1100.0       # used if everything fails — keeps the system working
_TTL_SECONDS = 3600           # refresh at most once per hour

_cache: dict = {"rate": None, "fetched_at": 0.0}
_lock = threading.Lock()


def _fetch_rate() -> float | None:
    """Try blue first, then oficial. Returns the average of buy/sell."""
    for url in (_BLUE_URL, _OFICIAL_URL):
        try:
            r = httpx.get(url, timeout=8, headers={"User-Agent": "AutoMotive/1.0"})
            r.raise_for_status()
            data = r.json()
            buy = float(data.get("compra") or 0)
            sell = float(data.get("venta") or 0)
            if buy > 0 and sell > 0:
                return (buy + sell) / 2
            if sell > 0:
                return sell
        except Exception as e:
            log.warning("FX %s failed: %s", url, e)
    return None


def usd_ars_rate() -> float:
    """Return the current USD→ARS rate, cached for `_TTL_SECONDS`.
    Always returns a positive float (falls back to a hardcoded constant
    on total failure)."""
    now = time.time()
    with _lock:
        if _cache["rate"] and (now - _cache["fetched_at"]) < _TTL_SECONDS:
            return _cache["rate"]
        rate = _fetch_rate()
        if rate and rate > 0:
            _cache["rate"] = rate
            _cache["fetched_at"] = now
            return rate
        # API failed — keep last known value if any
        if _cache["rate"]:
            log.warning("FX refresh failed; using stale rate %.2f", _cache["rate"])
            return _cache["rate"]
        log.warning("FX refresh failed and no cache; using fallback %.0f", _FALLBACK_RATE)
        return _FALLBACK_RATE
