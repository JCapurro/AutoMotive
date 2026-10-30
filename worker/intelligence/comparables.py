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
from typing import Any, Iterable, Mapping


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
    # F-02 paso 3 (migration 20261125120000): the same pool and level split by
    # seller. dealer = seller_type 'dealer' or dealer_inferred; private =
    # 'private' and not inferred; neither when unknown, so dealer_n + private_n
    # <= n. Data for PRO-02 only: nothing in the score reads them. None on a
    # price_ref stored before step 3 (seven keys).
    dealer_median: float | None = None
    dealer_n: int | None = None
    private_median: float | None = None
    private_n: int | None = None

    _BY_SELLER = ("dealer_median", "dealer_n", "private_median", "private_n")

    def enough(self, min_n: int) -> bool:
        return self.n >= min_n and bool(self.median)

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        for k in ("median", "p25", "p75", "median_km", "diff_pct", "dealer_median", "private_median"):
            if out[k] is not None:
                out[k] = round(float(out[k]), 2)
        if self.dealer_n is None and self.private_n is None:
            # Read from a price_ref without them: write back the same seven keys.
            for k in self._BY_SELLER:
                del out[k]
        return out

    @classmethod
    def from_json(cls, data: Mapping[str, Any] | None) -> "PriceRef | None":
        if not data or "level_used" not in data:
            return None
        def num(k):
            return float(data[k]) if data.get(k) is not None else None
        def count(k):
            return int(data[k]) if data.get(k) is not None else None
        return cls(n=int(data.get("n") or 0), level_used=data["level_used"], median=num("median"),
                   p25=num("p25"), p75=num("p75"), median_km=num("median_km"),
                   diff_pct=num("diff_pct"), dealer_median=num("dealer_median"), dealer_n=count("dealer_n"),
                   private_median=num("private_median"), private_n=count("private_n"))


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


# fetch_many's ids per statement.
_CHUNK = 200


async def fetch_many(cx, listing_ids: Iterable[int], cfg: Mapping[str, Any] | None = None
                     ) -> dict[int, PriceRef | None]:
    """fetch() for many listings, one round trip per _CHUNK ids instead of
    one per listing (the worker on the VPS, the database at Supabase)."""
    cfg = cfg or {}
    ids = list(dict.fromkeys(listing_ids))
    refs: dict[int, PriceRef | None] = {}
    for start in range(0, len(ids), _CHUNK):
        rows = await (await cx.execute(
            "SELECT i AS id, comparables(i, %s, %s, %s, %s) AS ref FROM unnest(%s::bigint[]) AS i",
            (cfg.get("min_n"), cfg.get("year_tol"), cfg.get("km_tol_pct"), cfg.get("max_age_days"),
             ids[start:start + _CHUNK]))).fetchall()
        refs.update({r["id"]: PriceRef.from_json(r["ref"]) for r in rows})
    return refs
