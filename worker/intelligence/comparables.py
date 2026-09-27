"""Price Intelligence (§19, sección 6.2).

The statistics come from the SQL function `public.comparables(listing_id)`
(migration 20260929120000_f2_intelligence.sql): same make and model, year ±1,
km ±25%, seen in the last 30 days, no partial prices, no reposts, the listing
itself excluded, everything in price_usd. It walks the specificity cascade

    1. same trim and same transmission   (level_used = 'trim_transmission')
    2. same transmission                 (level_used = 'transmission')
    3. the model only                    (level_used = 'model')

and returns the first level with n ≥ app_config.comparables.min_n (or the
model level, with its small n, when none gets there).

This module holds the shape of that result (`PriceRef`, stored in
matches.price_ref) and the database call.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


LEVELS = ("trim_transmission", "transmission", "model")


@dataclass(frozen=True)
class PriceRef:
    n: int
    level_used: str
    median: float | None = None       # USD
    p25: float | None = None
    p75: float | None = None
    median_km: float | None = None
    diff_pct: float | None = None     # % below the median (positive = cheaper)

    def enough(self, min_n: int) -> bool:
        return self.n >= min_n and bool(self.median)

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        for k in ("median", "p25", "p75", "median_km", "diff_pct"):
            if out[k] is not None:
                out[k] = round(float(out[k]), 2)
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> "PriceRef | None":
        if not data or "level_used" not in data:
            return None
        def num(k):
            return float(data[k]) if data.get(k) is not None else None
        return cls(n=int(data.get("n") or 0), level_used=data["level_used"], median=num("median"),
                   p25=num("p25"), p75=num("p75"), median_km=num("median_km"),
                   diff_pct=num("diff_pct"))


def diff_pct(price_usd: float | None, median: float | None) -> float | None:
    """How far below the median the published price is, in % (negative = above)."""
    if not price_usd or not median or median <= 0:
        return None
    return (1 - price_usd / median) * 100


async def fetch(cx, listing_id: int, cfg: Mapping[str, Any] | None = None) -> PriceRef | None:
    """public.comparables() for one listing. `cfg` overrides app_config.comparables."""
    cfg = cfg or {}
    row = await (await cx.execute(
        "SELECT comparables(%s, %s, %s, %s, %s) AS ref",
        (listing_id, cfg.get("min_n"), cfg.get("year_tol"), cfg.get("km_tol_pct"),
         cfg.get("max_age_days")))).fetchone()
    return PriceRef.from_json(row["ref"] if row else None)
