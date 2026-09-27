"""Resolve free-text make/model against vehicle_catalog.

The catalog is small (a few hundred rows), so the model-level rows are kept in
memory and matched in Python with the same normalization the scrapers use.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from psycopg import AsyncConnection

from normalization.normalize import normalize_brand, normalize_text


_TTL_SECONDS = 600.0


@dataclass(frozen=True)
class CatalogModel:
    make: str
    model: str
    aliases: tuple[str, ...]

    def names(self) -> list[str]:
        return [normalize_text(self.model), *(normalize_text(a) for a in self.aliases)]


_models: list[CatalogModel] = []
_fetched_at = 0.0


async def load_models(cx: AsyncConnection) -> list[CatalogModel]:
    global _models, _fetched_at
    if not _models or time.monotonic() - _fetched_at > _TTL_SECONDS:
        rows = await (await cx.execute(
            "SELECT make, model, aliases FROM vehicle_catalog WHERE trim IS NULL"
        )).fetchall()
        _models = [CatalogModel(r["make"], r["model"], tuple(r["aliases"])) for r in rows]
        _fetched_at = time.monotonic()
    return _models


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
