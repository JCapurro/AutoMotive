"""vehicle_catalog: canonical make/model/trim names.

The catalog is small (a few hundred rows), so it is kept in memory and matched
in Python: `match_model` for search profiles (make + model as typed), and
normalization/vehicle.py for listing titles.
"""
from __future__ import annotations

import time

from psycopg import AsyncConnection

from normalization.drafts import Market
from normalization.normalize import normalize_brand, normalize_text
from normalization.vehicle import CatalogModel


_TTL_SECONDS = 600.0

_models: list[CatalogModel] = []
_fetched_at = 0.0


async def load_models(cx: AsyncConnection) -> list[CatalogModel]:
    """Model-level rows with their trims, aliases, production years, body types and timing drive."""
    global _models, _fetched_at
    if not _models or time.monotonic() - _fetched_at > _TTL_SECONDS:
        rows = await (await cx.execute(
            "SELECT m.make, m.model, m.aliases, m.year_from, m.year_to, m.body_types, m.timing_belt, "
            "       coalesce(array_agg(t.trim ORDER BY t.trim) FILTER (WHERE t.trim IS NOT NULL), "
            "                '{}') AS trims "
            "  FROM vehicle_catalog m "
            "  LEFT JOIN vehicle_catalog t ON t.make = m.make AND t.model = m.model "
            "                             AND t.trim IS NOT NULL "
            " WHERE m.trim IS NULL "
            " GROUP BY m.make, m.model, m.aliases, m.year_from, m.year_to, m.body_types, m.timing_belt"
        )).fetchall()
        _models = [CatalogModel(r["make"], r["model"], tuple(r["aliases"]), tuple(r["trims"]),
                                r["year_from"], r["year_to"], tuple(r["body_types"] or ()),
                                r["timing_belt"])
                   for r in rows]
        _fetched_at = time.monotonic()
    return _models


# How far back a listing counts for Market (the assisted mode's ranking).
MARKET_DAYS = 30

_market = Market()
_market_fetched_at = 0.0


async def load_market(cx: AsyncConnection) -> Market:
    """Active listings seen in the last MARKET_DAYS per (make, model, year),
    with the 25th percentile of price_usd, and the latest stored USD/ARS rate
    (never fetched here). ~30 ms on ~10k listings; cached like the catalog."""
    global _market, _market_fetched_at
    if not _market.years or time.monotonic() - _market_fetched_at > _TTL_SECONDS:
        rows = await (await cx.execute(
            "SELECT make, model, year, count(*) AS n, "
            "       percentile_cont(0.25) WITHIN GROUP (ORDER BY price_usd) AS p25 "
            "  FROM listings "
            " WHERE status = 'active' AND last_seen_at > now() - make_interval(days => %s) "
            "   AND make IS NOT NULL AND model IS NOT NULL AND year IS NOT NULL "
            " GROUP BY make, model, year", (MARKET_DAYS,))).fetchall()
        fx = await (await cx.execute(
            "SELECT rate FROM fx_rates ORDER BY date DESC, kind = 'blue' DESC LIMIT 1")).fetchone()
        years: dict[tuple[str, str], dict[int, tuple[int, float | None]]] = {}
        for r in rows:
            years.setdefault((r["make"], r["model"]), {})[r["year"]] = (
                r["n"], float(r["p25"]) if r["p25"] is not None else None)
        _market = Market(years, float(fx["rate"]) if fx else None)
        _market_fetched_at = time.monotonic()
    return _market


def clear_catalog_cache() -> None:
    global _fetched_at, _market_fetched_at
    _fetched_at = _market_fetched_at = 0.0


def match_model(models: list[CatalogModel], make: str | None,
                model: str | None) -> tuple[str | None, str | None] | None:
    """Canonical (make, model), or None if it isn't in the catalog.

    The model matches a catalog name or alias exactly or as a prefix of words,
    and the longest name wins: "Gol Trend Highline" → Gol Trend, not Gol.
    """
    brand = normalize_brand(make) if make else None
    candidates = [m for m in models if brand is None or normalize_brand(m.make) == brand]
    if not candidates:
        return None
    if not model:
        return (candidates[0].make, None) if brand else None

    wanted = normalize_text(model)
    best: list[tuple[int, CatalogModel]] = []
    for m in candidates:
        for name in m.names():
            if wanted == name or wanted.startswith(name + " "):
                best.append((len(name), m))
    if not best:
        return None
    top = max(length for length, _ in best)
    winners = {(m.make, m.model) for length, m in best if length == top}
    # Without a make, an ambiguous model name ("Sprinter"?) is not resolved.
    return winners.pop() if len(winners) == 1 else None


async def resolve_make_model(cx: AsyncConnection, make: str | None,
                             model: str | None) -> tuple[str | None, str | None] | None:
    return match_model(await load_models(cx), make, model)
