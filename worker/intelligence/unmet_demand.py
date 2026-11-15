"""Demanda insatisfecha (/admin/demand). Pure: no I/O.

For a search with few or no results, how many listings each single filter
would unlock and which one unlocks the most. The counting is the low_results
funnel's (intelligence/low_results.funnel: every listing of the model goes
through the matching's own hard filters and `only[filter]` counts the ones
that filter alone discards); this module only reads it for the four filters
the dashboard names, so there is no second implementation of the matching.
"""
from __future__ import annotations

from datetime import time
from typing import Any, Mapping

from intelligence.low_results import Funnel

# Dashboard cause -> the funnel's filter. «Sin oferta» is the cause `none`.
FILTER = {"zone": "location", "price": "price", "trim": "trim", "year": "year"}
NONE = "none"

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    # The same idea as app_config.low_results: a search with this many results or fewer, older than min_age_hours.
    "max_results": 3,
    "min_age_hours": 24,
    # Searches per batch and the pause between batches, so the collection lanes keep their share of the pool.
    "batch_size": 100,
    "pause_seconds": 2.0,
    # Argentine time of the nightly run.
    "hour": "04:30",
}


def slot(hour: Any) -> time | None:
    """'HH:MM' as a time, None when it isn't one."""
    try:
        hh, mm = hour.split(":")
        return time(int(hh), int(mm))
    except (ValueError, AttributeError):
        return None


def settings(raw: Any) -> dict[str, Any]:
    """app_config.unmet_demand over DEFAULTS; a bad value keeps the default."""
    out = dict(DEFAULTS)
    if not isinstance(raw, Mapping):
        return out
    for key, default in DEFAULTS.items():
        value = raw.get(key)
        if isinstance(default, bool):
            if isinstance(value, bool):
                out[key] = value
        elif isinstance(default, str):
            if slot(value) is not None:
                out[key] = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            out[key] = max(1, int(value)) if key == "batch_size" else type(default)(value)
    return out


def cause(gains: Mapping[str, int]) -> str:
    """The relaxation that adds the most listings; `none` when none adds any.
    A tie keeps the order zone, price, trim, year."""
    best = max(FILTER, key=lambda k: gains[k])
    return best if gains[best] > 0 else NONE


def row(search: Mapping[str, Any], fun: Funnel) -> dict[str, Any]:
    """One admin_unmet_demand row from a search (a low_results candidate) and its funnel."""
    f = search.get("filters") or {}
    gains = {k: fun.only.get(name, 0) for k, name in FILTER.items()}
    # Listings with only that filter relaxed: what passes everything plus what only that filter discards.
    return {"search_profile_id": search["id"], "user_id": search["user_id"],
            "make": f.get("make"), "model": f.get("model"), "zone_label": f.get("location_label"),
            "result_count": search["result_count"], "market": fun.market,
            "market_in_zone": fun.market - fun.fails.get("location", 0),
            "relaxed_zone": fun.matched + gains["zone"], "relaxed_price": fun.matched + gains["price"],
            "relaxed_trim": fun.matched + gains["trim"], "relaxed_year": fun.matched + gains["year"],
            "cause": cause(gains)}
