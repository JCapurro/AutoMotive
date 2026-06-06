from __future__ import annotations
import statistics
from dataclasses import dataclass

from db import comparables
from config import OPPORTUNITY_MIN_COMPARABLES, DEFAULT_DISCOUNT_PCT
from scrapers.base import Listing
from price_check import statistical_partial, is_suspicious_discount
from fx import usd_ars_rate


@dataclass
class OpportunityScore:
    is_opportunity: bool
    median: float | None
    sample_size: int
    discount_pct: float | None  # how much below median (positive = cheaper)
    reason: str
    # When the listing's price looks too good to be true (anticipo / plan).
    # If True, we never auto-flag as opportunity even if the math says so.
    suspect_partial: bool = False


def _normalize_to_usd(precio: float, moneda: str | None) -> float:
    """Normalize a price to USD using the live USD/ARS rate (cached)."""
    if not moneda or moneda.upper() == "USD":
        return precio
    return precio / usd_ars_rate()


def evaluate(listing: Listing, alert_filters: dict) -> OpportunityScore:
    """
    Evaluate whether a listing is a real opportunity.

    Pipeline:
      1) Skip listings already flagged as partial-price (anticipo/plan/cuota
         keyword in title) — never an opportunity, just a misleading ad.
      2) Compute median of comparables (cache excludes partial-price entries).
      3) If price is implausibly low vs median (>=65% off), treat as partial
         price — don't notify.
      4) Otherwise check the user's discount threshold.
    """
    if not listing.precio or listing.precio <= 0:
        return OpportunityScore(False, None, 0, None, "sin precio")

    if listing.price_partial:
        return OpportunityScore(
            False, None, 0, None,
            f"precio parcial detectado ({listing.price_partial_reason})",
            suspect_partial=True,
        )

    min_disc = float(alert_filters.get("descuento_pct", DEFAULT_DISCOUNT_PCT))

    comps = comparables(
        marca=listing.marca or alert_filters.get("marca", ""),
        modelo=listing.modelo or alert_filters.get("modelo", ""),
        anio=listing.anio,
        km=listing.km,
    )
    # Normalize all comps + the listing to a common currency before comparing
    prices = []
    for c in comps:
        if c["precio"] and c["precio"] > 0:
            prices.append(_normalize_to_usd(c["precio"], c.get("moneda")))

    listing_usd = _normalize_to_usd(listing.precio, listing.moneda)

    if len(prices) < OPPORTUNITY_MIN_COMPARABLES:
        # Not enough data — fall back: only consider it a hit if user set a hard
        # discount target via "precio_max_oportunidad"
        cap = alert_filters.get("precio_max_oportunidad")
        if cap and listing.precio <= cap:
            return OpportunityScore(True, None, len(prices), None,
                                    f"precio bajo el techo ({listing.precio} ≤ {cap})")
        return OpportunityScore(False, None, len(prices), None,
                                f"comparables insuficientes ({len(prices)})")

    median = statistics.median(prices)
    if median <= 0:
        return OpportunityScore(False, median, len(prices), None, "mediana inválida")

    discount = (1 - listing_usd / median) * 100

    # Statistical anti-anticipo gate: if the price is so low it can't be
    # the real total, treat as partial even though no keyword caught it.
    stat_reason = statistical_partial(listing_usd, median)
    if stat_reason:
        return OpportunityScore(
            False, median, len(prices), discount,
            f"sospechoso de anticipo: {stat_reason}",
            suspect_partial=True,
        )

    if discount >= min_disc:
        # Mark borderline-suspect opportunities so the notification can warn.
        warn = is_suspicious_discount(listing_usd, median)
        return OpportunityScore(
            True, median, len(prices), discount,
            (warn or f"{discount:.1f}% bajo mediana de mercado"),
            suspect_partial=bool(warn),
        )
    return OpportunityScore(False, median, len(prices), discount,
                            f"solo {discount:.1f}% bajo mediana (umbral {min_disc:.0f}%)")
