"""f3 «precio × encaje» in shadow, pure (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §3, §10).

Synthetic fixtures only: the PRD Fiesta of test_intelligence and variations of it. Each test of the spec's
§10 «Nuevos» list says so in its docstring.
"""
from __future__ import annotations

import json
import logging
import math
import unittest
from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

from intelligence import f3, matching, scoring
from intelligence.comparables import PriceRef
from intelligence.config import IntelligenceConfig, score_model_f3
from intelligence.f3 import (FAR_BELOW, FEW_COMPARABLES, NO_COMPARABLES, NO_PRICE, NO_YEAR, PLACEHOLDER_PRICE,
                             SELLER_MISMATCH, SELLER_UNKNOWN, SUSPICIOUS, assess_f3, band_score, deal_curve,
                             level_f3, placeholder_price, shrink)
from test_intelligence import FX, MARKET, NOW, fiesta_listing, fiesta_profile


SHADOW = IntelligenceConfig.from_app_config({"score_model_f3": {"mode": "shadow"}})
P = SHADOW.f3
LV = P["levels"]
AGENCY_TEXT = "Recibimos tu usado y te lo compramos. Solo DNI, cuotas fijas."


def ref_at(d: float, *, n: int = 23, level_used: str = "trim_transmission", p25: float | None = 10_600.0,
           median: float = 11_200.0) -> PriceRef:
    """A reference with the listing d % below its median (positive = cheaper)."""
    return PriceRef(n=n, level_used=level_used, median=median, p25=p25, p75=11_900.0, median_km=125_000.0,
                    diff_pct=d)


def listing_at(d: float, median: float = 11_200.0, **kw) -> dict:
    usd = round(median * (1 - d / 100), 2)
    return fiesta_listing(**{"price": usd, "price_usd": usd, **kw})


def run(listing=None, profile=None, ref=MARKET, *, cfg=SHADOW, fx=FX, f3cfg=None, with_json=False):
    """matching + f2 score + f3, as engine.assess does."""
    listing = listing if listing is not None else fiesta_listing()
    profile = profile if profile is not None else fiesta_profile()
    result = matching.evaluate(listing, profile, fx_rate=fx)
    s = scoring.score(listing, profile, result, ref, cfg, now=NOW)
    out = assess_f3(listing, profile, result, ref, s.extra.get("diff_pct"), cfg, fx_rate=fx, f3cfg=f3cfg)
    if with_json:
        return out, f3.shadow(listing, profile, result, ref, s, cfg, fx_rate=fx)
    return out


def with_prefs(**prefs) -> dict:
    """The Fiesta search with only these preferences (and no preferred trim)."""
    p = fiesta_profile(trims=[])
    p["preferences"] = prefs
    return p


def rules(**changes) -> dict:
    return {**P, "rules": {**P["rules"], **changes}}


class PrdExampleTests(unittest.TestCase):
    """§9.5 / §10: the PRD Fiesta, 8 % below 23 comparables → 🔥 88 by trim, 86 by model."""

    def test_trim_level_reference_is_high_88(self):
        r = run()
        self.assertEqual((r.level, r.score), ("high", 88))
        self.assertAlmostEqual(r.d, 8.0357, places=4)
        self.assertAlmostEqual(r.s_lo, 5.3571, places=4)
        self.assertAlmostEqual(r.d_full, 13.3929, places=4)
        self.assertAlmostEqual(r.deal, 0.76, places=4)
        self.assertEqual((r.fit_level, r.fit_score), (1.0, 1.0))
        self.assertAlmostEqual(r.raw, 85.6, places=4)
        self.assertEqual(r.flags, ())
        self.assertTrue(r.credible)
        self.assertEqual(r.tier, "strong")

    def test_model_level_reference_is_high_86(self):
        r = run(ref=replace(MARKET, level_used="model"))
        self.assertEqual((r.level, r.score), ("high", 86))
        self.assertAlmostEqual(r.r, 0.9)
        self.assertAlmostEqual(r.deal, 0.724, places=4)

    def test_the_f2_score_of_the_example_is_unchanged(self):
        ev = run()
        self.assertEqual(ev.level, "high")
        f2 = scoring.score(fiesta_listing(), fiesta_profile(),
                           matching.evaluate(fiesta_listing(), fiesta_profile(), fx_rate=FX), MARKET, SHADOW, now=NOW)
        self.assertEqual((f2.score, f2.level), (89, "high"))


class DealCurveTests(unittest.TestCase):
    """§3.1 and §10 «curva y referencia»."""

    def curve(self, d, d_eff=None, d_full=13.3929):
        return deal_curve(d, d if d_eff is None else d_eff, d_full=d_full, cred_max=35, susp=50)

    def test_anchors(self):
        self.assertEqual(self.curve(-25), 0.0)
        self.assertEqual(self.curve(-20), 0.0)
        self.assertAlmostEqual(self.curve(-10), 0.2)
        self.assertAlmostEqual(self.curve(0), 0.4)
        self.assertAlmostEqual(self.curve(13.3929), 1.0)
        self.assertEqual(self.curve(20), 1.0)
        self.assertEqual(self.curve(35), 1.0)
        self.assertAlmostEqual(self.curve(42.5), 0.85)
        self.assertAlmostEqual(self.curve(49.999), 0.7, places=3)
        self.assertEqual(self.curve(50), 0.6)
        self.assertEqual(self.curve(64), 0.6)
        self.assertIsNone(self.curve(None))

    def test_monotone_up_to_35_then_down(self):
        """La curva de precio es monótona hasta 35 % y baja después."""
        ds = [x / 2 for x in range(-60, 130)]          # −30 … 64.5
        values = [self.curve(d) for d in ds]
        rising = [v for d, v in zip(ds, values) if d <= 35]
        falling = [v for d, v in zip(ds, values) if d >= 35]
        self.assertEqual(rising, sorted(rising))
        self.assertEqual(falling, sorted(falling, reverse=True))
        self.assertTrue(all(0 <= v <= 1 for v in values))

    def test_the_suspicious_band_reads_the_published_d(self):
        # Kavak at 55 % published (46 % adjusted): 0.6 by d, as the spec's text says.
        self.assertEqual(self.curve(55, 46), 0.6)

    def test_d_full_from_the_spread_with_its_clamps(self):
        for p25, d_full in ((10_600.0, 13.3929), (10_976.0, 12.0), (10_080.0, 20.0), (None, 16.0)):
            with self.subTest(p25=p25):
                r = run(ref=ref_at(8.0357, p25=p25))
                self.assertAlmostEqual(r.d_full, d_full, places=4)
        self.assertIsNone(run(ref=ref_at(8.0357, p25=None)).s_lo)

    def test_a_weaker_reference_gives_less_deal_only_on_the_cheap_side(self):
        """Con el mismo d, una referencia más débil da menos precio, pero nunca por encima de su
        valor crudo cuando es cara."""
        for d in (3.0, 8.0, 15.0, 30.0):
            with self.subTest(d=d):
                strong = run(listing_at(d), ref=ref_at(d, n=23)).deal
                few = run(listing_at(d), ref=ref_at(d, n=10)).deal
                model = run(listing_at(d), ref=ref_at(d, n=23, level_used="model")).deal
                no_year = run(listing_at(d, year=None), fiesta_profile(year_min=None, year_max=None),
                              ref=ref_at(d, n=23)).deal
                self.assertGreater(strong, few)
                self.assertGreater(strong, model)
                self.assertGreater(strong, no_year)
                self.assertGreater(no_year, 0.4)
        for d in (-15.0, -5.0, 0.0):
            with self.subTest(d=d):
                raw = run(listing_at(d), ref=ref_at(d)).deal_raw
                for ref in (ref_at(d, n=6), ref_at(d, n=6, level_used="model")):
                    self.assertAlmostEqual(run(listing_at(d), ref=ref).deal, raw)
        self.assertEqual(shrink(0.3, 0.2), 0.3)
        self.assertAlmostEqual(shrink(1.0, 0.5), 0.7)

    def test_reliability_by_n_pool_and_year(self):
        self.assertAlmostEqual(run(ref=ref_at(8, n=5)).r, 0.5)
        self.assertAlmostEqual(run(ref=ref_at(8, n=12)).r, 0.5 + 0.5 * 7 / 15)
        self.assertAlmostEqual(run(ref=ref_at(8, n=40)).r, 1.0)
        self.assertAlmostEqual(run(ref=ref_at(8, n=40, level_used="model")).r, 0.9)
        no_year = run(fiesta_listing(year=None), fiesta_profile(year_min=None, year_max=None), ref=ref_at(8, n=40))
        self.assertAlmostEqual(no_year.r, 0.3)

    def test_kavak_compares_9_points_lower(self):
        """El ajuste de Kavak: un Kavak a −9 % es un Kavak típico."""
        kavak = run(listing_at(9, source="kavak"), ref=ref_at(9))
        self.assertAlmostEqual(kavak.diff_pct, 9)
        self.assertAlmostEqual(kavak.d, 9)
        self.assertAlmostEqual(kavak.d_eff, 0)
        self.assertTrue(kavak.kavak)
        self.assertAlmostEqual(kavak.deal, 0.4)
        self.assertNotEqual(kavak.level, "high")
        other = run(listing_at(9), ref=ref_at(9))
        self.assertEqual(other.level, "high")
        self.assertAlmostEqual(run(listing_at(9, source="kavak"), ref=ref_at(9),
                                   f3cfg={**P, "deal": {**P["deal"], "kavak_offset": 0}}).deal, other.deal)

    def test_deal_is_unknown_without_price_placeholder_or_comparables(self):
        no_price = run(fiesta_listing(price=None, price_usd=None), ref=ref_at(None))
        self.assertIsNone(no_price.deal)
        self.assertIn(NO_PRICE, no_price.flags)
        self.assertFalse(no_price.has_price)

        filler = run(listing_at(0.79, price=11_111.0, price_usd=11_111.0), ref=ref_at(0.79))
        self.assertIsNone(filler.deal)
        self.assertIsNone(filler.d)
        self.assertAlmostEqual(filler.diff_pct, 0.79)
        self.assertTrue(filler.placeholder)
        self.assertIn(PLACEHOLDER_PRICE, filler.flags)
        self.assertNotIn(NO_PRICE, filler.flags)

        few = PriceRef(n=4, level_used="model", median=11_200.0, p25=10_600.0, median_km=125_000.0, diff_pct=8.0)
        r = run(ref=few)
        self.assertIsNone(r.d)
        self.assertIsNone(r.deal)
        self.assertIn(NO_COMPARABLES, r.flags)
        self.assertEqual(run(ref=None).flags, (NO_COMPARABLES,))


class LevelTests(unittest.TestCase):
    """§3.3 and §10 «niveles»."""

    def test_combined_rule(self):
        """Precio 0,72 con encaje 1 es 🔥 (0,83); precio 0,80 con encaje 0,70 no lo es (0,76)."""
        self.assertEqual(level_f3(0.72, 1.0, LV), "high")
        self.assertEqual(level_f3(0.80, 0.70, LV), "good")
        self.assertEqual(level_f3(0.69, 1.0, LV, credible=True), "good")       # under the deal floor
        self.assertEqual(level_f3(1.0, 0.69, LV), "good")                       # under the fit floor

    def test_combined_rule_end_to_end(self):
        r = run(listing_at(7.1429), ref=ref_at(7.1429))
        self.assertAlmostEqual(r.deal, 0.72, places=4)
        self.assertEqual(r.level, "high")
        # price_target met, the distance failed (Vicente López is ~12 km away): fit (1 + 0.4) / 2 = 0.70.
        p = with_prefs(price_target=10_500, max_distance_km=10)
        r = run(listing_at(8.9286), p, ref=ref_at(8.9286))
        self.assertAlmostEqual(r.deal, 0.80, places=4)
        self.assertAlmostEqual(r.fit_level, 0.70)
        self.assertEqual(r.level, "good")

    def test_each_branch(self):
        self.assertEqual(level_f3(0.9, 1.0, LV, excluded=True), "excluded")
        self.assertEqual(level_f3(0.9, 1.0, LV, flags=[FEW_COMPARABLES]), "good")
        self.assertEqual(level_f3(0.66, 0.45, LV, d_eff=10), "good")             # «buen precio»
        self.assertEqual(level_f3(0.5, 0.45, LV, credible=True, d_eff=6), "good")   # credible discount
        self.assertEqual(level_f3(0.66, 0.44, LV, d_eff=10), "match")
        self.assertEqual(level_f3(0.36, 0.85, LV, d_eff=-2), "good")             # «coincide, precio en línea»
        self.assertEqual(level_f3(0.35, 0.85, LV, d_eff=-2.5), "match")
        self.assertEqual(level_f3(None, 0.85, LV, d_eff=None), "good")           # no comparables
        self.assertEqual(level_f3(None, 0.9, LV, has_price=False), "match")
        self.assertEqual(level_f3(0.9, 1.0, LV, year_known=False, flags=[NO_YEAR]), "match")
        self.assertEqual(level_f3(0.6, 1.0, LV, suspicious=True, d_eff=55, flags=[SUSPICIOUS]), "match")
        self.assertEqual(level_f3(0.2, 1.0, LV, d_eff=-10), "match")
        self.assertEqual(level_f3(0.19, 1.0, LV, d_eff=-10.5), "low")             # clearly above the market
        self.assertEqual(level_f3(0.9, 0.29, LV, d_eff=10), "low")                # fit < y_min

    def test_score_at_least_85_iff_high(self):
        """score ≥ 85 ⇔ 🔥, with the bands anchored at c_high."""
        seen = set()
        for d in [x / 2 for x in range(-50, 130)]:
            for listing_kw, profile in (({}, fiesta_profile()), ({"transmission": None, "mileage_km": None},
                                                                 fiesta_profile()),
                                        ({}, with_prefs(price_target=8_000, max_distance_km=10)),
                                        ({"year": None}, fiesta_profile(year_min=None, year_max=None))):
                for n in (6, 12, 40):
                    r = run(listing_at(d, **listing_kw), profile, ref=ref_at(d, n=n))
                    if r.level == "excluded":
                        continue
                    seen.add(r.level)
                    self.assertEqual(r.score >= 85, r.level == "high", (d, listing_kw, n, r.level, r.score))
                    lo, hi = {"high": (85, 99), "good": (70, 84), "match": (50, 69), "low": (0, 49)}[r.level]
                    self.assertTrue(lo <= r.score <= hi, (r.level, r.score))
        self.assertEqual(seen, {"high", "good", "match", "low"})

    def test_band_edges(self):
        self.assertEqual(band_score("high", 82, 0.82), 85)
        self.assertEqual(band_score("high", 100, 0.82), 99)
        self.assertEqual(band_score("high", 70, 0.82), 85)
        self.assertEqual(band_score("good", 95, 0.82), 84)
        self.assertEqual(band_score("good", 40, 0.82), 70)
        self.assertEqual(band_score("match", 85, 0.82), 69)
        self.assertEqual(band_score("match", 10, 0.82), 50)
        self.assertEqual(band_score("low", 70, 0.82), 49)
        self.assertEqual(band_score("low", 0, 0.82), 0)

    def test_highs_with_raw_below_c_high_tie_at_85(self):
        """Como el nivel lee encaje_nivel y el score encaje_score, una 🔥 puede tener un crudo menor que
        82: queda en 85 (empatan)."""
        p = with_prefs(price_target=10_500)
        two = run(listing_at(7.1429, transmission=None, mileage_km=None), p, ref=ref_at(7.1429))
        three = run(listing_at(7.1429, transmission=None, mileage_km=None, fuel=None),
                    fiesta_profile(fuel="nafta") | {"preferences": {"price_target": 10_500}}, ref=ref_at(7.1429))
        self.assertEqual(len(three.unknown_hard), 3)
        for r in (two, three):
            self.assertEqual(r.level, "high")
            self.assertLess(r.raw, 82)
            self.assertEqual(r.score, 85)

    def test_a_hard_unknown_moves_the_score_not_the_level(self):
        """Un filtro duro sin dato no cambia el nivel, solo el score (−0,03 en encaje_score)."""
        known = run()
        unknown = run(fiesta_listing(transmission=None))
        self.assertEqual(unknown.unknown_hard, ("transmission",))
        self.assertEqual(unknown.level, known.level)
        self.assertEqual(unknown.fit_level, known.fit_level)
        self.assertAlmostEqual(unknown.fit_score, known.fit_score - 0.03)
        self.assertLess(unknown.score, known.score)
        self.assertEqual(unknown.a_verificar, ("transmission",))

    def test_far_below_is_good_with_the_flag(self):
        """47 % debajo: «buena» con «muy por debajo», nunca 🔥."""
        r = run(listing_at(47), ref=ref_at(47))
        self.assertEqual(r.level, "good")
        self.assertIn(FAR_BELOW, r.flags)
        self.assertAlmostEqual(r.deal_raw, 0.76)
        self.assertEqual(r.tier, "verify")

    def test_55_below_is_at_most_match(self):
        """55 % debajo pasa a «coincidencia» (f2: ≥ 85 topeado en «buena»)."""
        r = run(listing_at(55), ref=ref_at(55))
        self.assertEqual(r.level, "match")
        self.assertIn(SUSPICIOUS, r.flags)
        self.assertEqual(r.deal_raw, 0.6)

    def test_73_below_is_excluded_like_f2(self):
        r = run(listing_at(73), ref=ref_at(73))
        self.assertEqual(r.level, "excluded")
        self.assertEqual(run(fiesta_listing(price_partial=True)).level, "excluded")

    def test_no_year_is_at_most_match(self):
        r = run(fiesta_listing(year=None))
        self.assertEqual(r.level, "match")
        self.assertIn(NO_YEAR, r.flags)
        self.assertEqual(r.unknown_hard, ("year",))

    def test_fewer_than_10_comparables_is_never_high(self):
        r = run(ref=ref_at(8.0357, n=9))
        self.assertIn(FEW_COMPARABLES, r.flags)
        self.assertEqual(r.level, "good")
        self.assertFalse(r.credible)
        self.assertEqual(run(ref=ref_at(15, n=10)).level, "high")

    def test_above_the_market(self):
        self.assertEqual(run(listing_at(-5), ref=ref_at(-5)).level, "match")
        self.assertEqual(run(listing_at(-5), ref=ref_at(-5)).tier, "pricey")
        self.assertEqual(run(listing_at(-15), ref=ref_at(-15)).level, "low")
        self.assertEqual(run(listing_at(-15), ref=ref_at(-15)).tier, "expensive")
        self.assertEqual(run(listing_at(-1), ref=ref_at(-1)).tier, "fair")
        self.assertEqual(run(listing_at(5), ref=ref_at(5)).tier, "good")       # credible, deal 0.62
        self.assertEqual(run(ref=None).tier, "unknown")

    def test_placeholder_price_is_at_most_match(self):
        """Precio de relleno: como sin precio, como mucho «coincidencia»; con la regla apagada, el precio."""
        listing = fiesta_listing(price=11_111.0, price_usd=11_111.0)
        on = run(listing, ref=ref_at(0.79))
        self.assertEqual(on.level, "match")
        self.assertFalse(on.has_price)
        self.assertIn("price_target", on.a_verificar)        # sin dato, not a fail
        self.assertEqual(on.prefs["price_target"], 0.75)
        off = run(listing, ref=ref_at(0.79), f3cfg=rules(placeholder=False))
        self.assertTrue(off.has_price)
        self.assertTrue(off.placeholder)
        self.assertNotIn(PLACEHOLDER_PRICE, off.flags)
        self.assertEqual(off.level, "good")


class FitTests(unittest.TestCase):
    """§3.2 and §10 «encaje»."""

    def test_an_unknown_preference_never_scores_below_a_failed_one(self):
        """Una preferencia sin dato nunca puntúa por debajo de una fallida."""
        p = with_prefs(km_target=100_000)
        unknown = run(fiesta_listing(mileage_km=None), p)
        failed = run(fiesta_listing(mileage_km=200_000), fiesta_profile(km_max=None) | {"preferences": {"km_target": 100_000}})
        self.assertEqual(unknown.prefs["km_target"], 0.75)
        self.assertEqual(failed.prefs["km_target"], 0.4)
        self.assertGreater(unknown.fit_level, failed.fit_level)
        self.assertEqual(unknown.a_verificar, ("km", "km_target"))

    def test_price_target_inside_price_max_never_below_0_6(self):
        """price_target dentro de price_max nunca baja de 0,6 (graduado 1 → 0,6)."""
        p = with_prefs(price_target=10_000)            # price_max 11.500
        values = []
        for usd in range(9_500, 11_501, 100):
            r = run(fiesta_listing(price=float(usd), price_usd=float(usd)), p, ref=ref_at(5))
            values.append(r.prefs["price_target"])
        self.assertTrue(all(0.6 <= v <= 1 for v in values))
        self.assertEqual(values, sorted(values, reverse=True))
        at_max = run(fiesta_listing(price=11_500.0, price_usd=11_500.0), p, ref=ref_at(5)).prefs["price_target"]
        self.assertAlmostEqual(at_max, 0.6)
        mid = run(fiesta_listing(price=10_750.0, price_usd=10_750.0), p, ref=ref_at(5)).prefs["price_target"]
        self.assertAlmostEqual(mid, 0.8)

    def test_price_target_without_price_max_reaches_fail_at_15_pct(self):
        p = fiesta_profile(price_max=None) | {"preferences": {"price_target": 10_000}}
        at_15 = run(fiesta_listing(price=11_500.0, price_usd=11_500.0), p, ref=ref_at(5)).prefs["price_target"]
        half = run(fiesta_listing(price=10_750.0, price_usd=10_750.0), p, ref=ref_at(5)).prefs["price_target"]
        self.assertAlmostEqual(at_15, 0.4)
        self.assertAlmostEqual(half, 0.7)

    def test_price_target_in_pesos_against_a_usd_max(self):
        # Target ARS 10.000.000, price_max USD 11.500 = ARS 11.500.000 at FX 1.000.
        p = fiesta_profile() | {"preferences": {"price_target": 10_000_000, "price_target_currency": "ARS"}}
        r = run(fiesta_listing(price=10_750.0, price_usd=10_750.0), p, ref=ref_at(5))
        self.assertAlmostEqual(r.prefs["price_target"], 0.8)
        # Without a quote neither the price nor the max can be compared: sin dato.
        self.assertEqual(run(fiesta_listing(price=10_750.0, price_usd=10_750.0), p, ref=ref_at(5), fx=None)
                         .prefs["price_target"], 0.75)

    def test_km_target_reaches_fail_at_30_pct(self):
        p = fiesta_profile(km_max=None) | {"preferences": {"km_target": 100_000}}
        self.assertAlmostEqual(run(fiesta_listing(mileage_km=130_000), p).prefs["km_target"], 0.4)
        self.assertAlmostEqual(run(fiesta_listing(mileage_km=115_000), p).prefs["km_target"], 0.7)
        self.assertEqual(run(fiesta_listing(mileage_km=90_000), p).prefs["km_target"], 1.0)

    def test_trim_and_distance(self):
        other = run(fiesta_listing(trim="S"))
        self.assertEqual(other.prefs["trim"], 0.5)
        self.assertEqual(run(fiesta_listing(trim=None)).prefs["trim"], 0.75)
        p = with_prefs(max_distance_km=10)
        r = run(fiesta_listing(attributes={"color": "Rojo"}), p)
        self.assertEqual(r.prefs, {"max_distance_km": 0.4})                       # Vicente López is ~12 km away
        self.assertEqual(run(fiesta_listing(), with_prefs()).fit_level, 1.0)       # no preferences
        # The soft preferences.colors is gone (filters.colors is a hard filter now).
        self.assertEqual(run(fiesta_listing(), with_prefs(colors=["Rojo"])).prefs, {})


class SellerTests(unittest.TestCase):
    """§3.2/§3.3 and §10 «vendedor»."""

    def pref(self, seller: str) -> dict:
        p = fiesta_profile()
        p["preferences"]["seller_type"] = seller
        return p

    def test_a_confirmed_other_seller_is_capped_at_match(self):
        """Tope de vendedor: confirmado distinto, como mucho «coincidencia»."""
        for listing in (fiesta_listing(seller_type="dealer"),
                        fiesta_listing(seller_type="private", dealer_inferred=True, seller_listing_count=6)):
            with self.subTest(listing=listing["seller_type"]):
                r, js = run(listing, self.pref("private"), with_json=True)
                self.assertTrue(r.seller_mismatch)
                self.assertIn(SELLER_MISMATCH, r.flags)
                self.assertEqual(r.level_uncapped, "good")
                self.assertEqual(r.level, "match")
                self.assertTrue(r.seller_capped)
                self.assertEqual(r.prefs["seller_type"], 0.4)
                # Without the cap the failed preference still weighs (fit 0.85): «buena», not 🔥.
                self.assertEqual(js["alternatives"]["seller_cap_off"]["level"], "good")
        off = run(fiesta_listing(seller_type="dealer"), self.pref("private"), f3cfg=rules(seller_cap=False))
        self.assertEqual(off.level, "good")
        self.assertFalse(off.seller_capped)
        self.assertNotIn(SELLER_MISMATCH, off.flags)
        # A strong price and the other preferences met (fit 0.80): the cap is what keeps it out of 🔥.
        p = with_prefs(seller_type="private", price_target=10_500, km_target=120_000)
        capped = run(listing_at(20, seller_type="dealer"), p, ref=ref_at(20))
        self.assertAlmostEqual(capped.fit_level, 0.8)
        self.assertEqual((capped.level_uncapped, capped.level), ("good", "match"))
        self.assertEqual(run(listing_at(20, seller_type="dealer"), p, ref=ref_at(20),
                             f3cfg=rules(seller_cap=False)).level, "high")

    def test_an_unknown_seller_is_not_capped_but_never_high(self):
        """Sin dato: sin tope, pero sin 🔥; vale 0,75 y la decisión esperaría al detalle."""
        r = run(fiesta_listing(seller_type=None), self.pref("private"))
        self.assertFalse(r.seller_mismatch)
        self.assertFalse(r.seller_capped)
        self.assertIn(SELLER_UNKNOWN, r.flags)
        self.assertEqual(r.level, "good")
        self.assertEqual(r.prefs["seller_type"], 0.75)
        self.assertIn("seller_type", r.a_verificar)
        self.assertTrue(r.would_defer)

    def test_the_wanted_seller(self):
        r = run(fiesta_listing(seller_type="private"), self.pref("private"))
        self.assertEqual((r.level, r.seller_wanted, r.seller_strict), ("high", ("private",), False))
        self.assertEqual(run().seller_wanted, None)

    def test_strict_filter_with_an_unknown_seller(self):
        """PRO-01: sin dato con el filtro estricto resta 0,03 en el score y no puede ser 🔥."""
        p = fiesta_profile(seller_types=["private"]) | {"seller_filter": True}
        r = run(fiesta_listing(seller_type=None), p)
        self.assertEqual(r.unknown_hard, ("seller",))
        self.assertAlmostEqual(r.fit_score, r.fit_level - 0.03)
        self.assertIn(SELLER_UNKNOWN, r.flags)
        self.assertEqual(r.level, "good")
        self.assertEqual((r.seller_wanted, r.seller_strict), (("private",), True))
        self.assertTrue(r.would_defer)

    def test_agency_voice_counts_as_an_agency_for_the_preference(self):
        """Voz de agencia: un «particular» que escribe como agencia, con preferencia de particular →
        tope; la frase queda guardada."""
        listing = fiesta_listing(seller_type="private", description=AGENCY_TEXT, enriched_at=NOW)
        r, js = run(listing, self.pref("private"), with_json=True)
        self.assertEqual(r.agency_voice, "recibimos tu usado")
        self.assertEqual((r.seller_effective, r.seller_for_preference), ("private", "dealer"))
        self.assertEqual(r.level, "match")
        self.assertTrue(r.seller_capped)
        self.assertEqual(js["seller"]["agency_voice"], "recibimos tu usado")
        self.assertEqual(js["alternatives"]["agency_voice_off"]["level"], "high")
        off = run(listing, self.pref("private"), f3cfg=rules(agency_voice=False))
        self.assertEqual((off.level, off.seller_for_preference, off.agency_voice), ("high", "private",
                                                                                   "recibimos tu usado"))
        # A search that prefers agencies gets it as one.
        self.assertEqual(run(listing, self.pref("dealer")).level, "high")

    def test_agency_voice_without_a_seller_preference_changes_nothing(self):
        listing = fiesta_listing(seller_type="private", description=AGENCY_TEXT)
        r, js = run(listing, with_json=True)
        self.assertEqual(r.level, "high")
        self.assertEqual(r.agency_voice, "recibimos tu usado")
        self.assertEqual(js["alternatives"], {})

    def test_the_card_has_no_description_so_no_voice(self):
        r = run(fiesta_listing(seller_type="private", description=None), self.pref("private"))
        self.assertIsNone(r.agency_voice)
        self.assertEqual(r.level, "high")

    def test_would_defer(self):
        pref = self.pref("private")
        self.assertTrue(run(fiesta_listing(seller_type=None, enriched_at=None), pref).would_defer)
        self.assertFalse(run(fiesta_listing(seller_type=None, enriched_at=NOW), pref).would_defer)
        self.assertFalse(run(fiesta_listing(seller_type="private", enriched_at=None), pref).would_defer)
        self.assertFalse(run(fiesta_listing(seller_type=None, enriched_at=None)).would_defer)

    def test_only_an_fb_or_ml_card_would_defer(self):
        """§4.1: «si su tarjeta de FB o ML no trae vendedor». Elsewhere the card decides; the broader rule
        (any source) is logged next to it."""
        pref = self.pref("private")
        for source, defers in (("facebook", True), ("mercadolibre", True), ("deruedas", False),
                               ("rosariogarage", False), ("autocosmos", False), ("kavak", False)):
            with self.subTest(source=source):
                r, js = run(fiesta_listing(source=source, seller_type=None, enriched_at=None), pref, with_json=True)
                self.assertEqual(r.would_defer, defers)
                self.assertTrue(r.would_defer_any_source)
                self.assertEqual((js["would_defer"], js["would_defer_any_source"]), (defers, True))
        enriched = run(fiesta_listing(source="deruedas", seller_type=None, enriched_at=NOW), pref)
        self.assertEqual((enriched.would_defer, enriched.would_defer_any_source), (False, False))


class PlaceholderTests(unittest.TestCase):
    """§3.5 and §10 «precio de relleno»."""

    def test_repeated_digits_1_to_8(self):
        for price in (1_111, 11_111, 11_111.0, 1_111_111, 22_222, 88_888_888):
            self.assertTrue(placeholder_price(price), price)
        for price in (9_999, 99_999, 999_999, 111, 11_112, 10_000, 0, -11_111, None, True, "11111", math.nan):
            self.assertFalse(placeholder_price(price), price)

    def test_ars_and_usd_fillers(self):
        """USD 11.111 y ARS 1.111.111 son relleno; USD 9.999 no lo es."""
        self.assertTrue(run(fiesta_listing(price=11_111.0, price_usd=11_111.0), ref=ref_at(0.8)).placeholder)
        ars = fiesta_listing(price=1_111_111.0, currency="ARS", price_usd=1_111.11)
        self.assertTrue(run(ars, fiesta_profile(price_max=None), ref=ref_at(None)).placeholder)
        shop = run(fiesta_listing(price=9_999.0, price_usd=9_999.0), ref=ref_at(10.7))
        self.assertFalse(shop.placeholder)
        self.assertTrue(shop.has_price)

    def test_the_flag_does_not_change_the_matches(self):
        """La bandera no cambia el conjunto de matches (matching no la lee)."""
        def results(price):
            r = matching.evaluate(fiesta_listing(price=price, price_usd=price), fiesta_profile(), fx_rate=FX)
            return r.is_match, {k: v.result for k, v in r.reasons.items()}
        self.assertEqual(results(11_111.0), results(11_112.0))
        self.assertEqual(results(11_111.0)[0], True)


class ShadowJsonTests(unittest.TestCase):
    """The shadow_f3 JSON the decision log reads, and shadow()'s guards."""

    def test_contract_keys(self):
        _, js = run(with_json=True)
        self.assertEqual(set(js), {"v", "mode", "params", "level", "level_uncapped", "score", "raw", "deal", "fit",
                                   "flags", "a_verificar", "seller", "would_defer", "would_defer_any_source",
                                   "alternatives"})
        self.assertEqual(set(js["deal"]), {"value", "raw", "r", "diff_pct", "d", "d_eff", "d_full", "s_lo", "n",
                                           "level_used", "kavak", "placeholder", "has_price", "credible", "tier"})
        self.assertEqual(set(js["fit"]), {"level", "score", "unknown_hard", "prefs"})
        self.assertEqual(set(js["seller"]), {"wanted", "strict", "effective", "for_preference", "agency_voice",
                                             "mismatch", "capped"})
        self.assertEqual((js["v"], js["mode"], js["params"]), (f3.F3_VERSION, "shadow", P["params"]))
        self.assertEqual(js["fit"]["prefs"], {"price_target": 1.0, "km_target": 1.0, "trim": 1.0})

    def test_json_is_plain_finite_and_deterministic(self):
        cases = [(fiesta_listing(), fiesta_profile(), MARKET),
                 (fiesta_listing(price=11_111.0, price_usd=11_111.0, source="kavak", seller_type="private",
                                 description=AGENCY_TEXT), fiesta_profile() | {"preferences": {"seller_type": "private"}},
                  ref_at(0.8)),
                 (fiesta_listing(year=None, transmission=None, price=None, price_usd=None), fiesta_profile(), None)]
        for listing, profile, ref in cases:
            result = matching.evaluate(listing, profile, fx_rate=FX)
            outs = []
            for now in (NOW, NOW + timedelta(days=3)):
                s = scoring.score(listing, profile, result, ref, SHADOW, now=now)
                outs.append(f3.shadow(listing, profile, result, ref, s, SHADOW, fx_rate=FX))
            self.assertEqual(outs[0], outs[1])
            text = json.dumps(outs[0], allow_nan=False, sort_keys=True)
            self.assertEqual(json.loads(text), outs[0])

    def test_alternatives_only_when_relevant(self):
        self.assertEqual(run(with_json=True)[1]["alternatives"], {})
        kavak = run(listing_at(9, source="kavak"), ref=ref_at(9), with_json=True)[1]
        self.assertEqual(set(kavak["alternatives"]), {"kavak_offset_0"})
        self.assertEqual(kavak["alternatives"]["kavak_offset_0"]["level"], "high")
        filler = run(fiesta_listing(price=11_111.0, price_usd=11_111.0), ref=ref_at(0.8), with_json=True)[1]
        self.assertEqual(set(filler["alternatives"]), {"placeholder_off"})
        self.assertEqual(filler["alternatives"]["placeholder_off"]["level"], "good")
        self.assertEqual(filler["alternatives"]["placeholder_off"]["score"],
                         run(fiesta_listing(price=11_111.0, price_usd=11_111.0), ref=ref_at(0.8),
                             f3cfg=rules(placeholder=False)).score)
        flipped = run(fiesta_listing(price=11_111.0, price_usd=11_111.0), ref=ref_at(0.8),
                      cfg=IntelligenceConfig.from_app_config(
                          {"score_model_f3": {"mode": "shadow", "rules": {"placeholder": False}}}), with_json=True)[1]
        self.assertEqual(set(flipped["alternatives"]), {"placeholder_on"})

    def test_mode_off_does_no_work(self):
        off = IntelligenceConfig()
        self.assertEqual(off.f3["mode"], "off")
        listing, profile = fiesta_listing(), fiesta_profile()
        result = matching.evaluate(listing, profile, fx_rate=FX)
        s = scoring.score(listing, profile, result, MARKET, off, now=NOW)
        with patch.object(f3, "assess_f3", side_effect=AssertionError("computed")) as spy:
            self.assertIsNone(f3.shadow(listing, profile, result, MARKET, s, off, fx_rate=FX))
        spy.assert_not_called()

    def test_live_behaves_as_shadow(self):
        live = IntelligenceConfig.from_app_config({"score_model_f3": {"mode": "live"}})
        _, js = run(cfg=live, with_json=True)
        self.assertEqual((js["mode"], js["level"], js["score"]), ("live", "high", 88))

    def test_a_failure_is_none_and_logged_once(self):
        listing, profile = fiesta_listing(), fiesta_profile()
        result = matching.evaluate(listing, profile, fx_rate=FX)
        s = scoring.score(listing, profile, result, MARKET, SHADOW, now=NOW)
        f3._WARNED.clear()
        with patch.object(f3, "assess_f3", side_effect=ZeroDivisionError("boom")), \
                self.assertLogs("intelligence.f3", logging.WARNING) as logs:
            for _ in range(3):
                self.assertIsNone(f3.shadow(listing, profile, result, MARKET, s, SHADOW, fx_rate=FX))
        self.assertEqual(len(logs.records), 1)
        f3._WARNED.clear()


class WarnLimitedTests(unittest.TestCase):
    def test_once_per_window_then_with_the_suppressed_count(self):
        logger = logging.getLogger("test_f3.warn")
        f3._WARNED.clear()
        clock = [1000.0]
        with patch.object(f3.time, "monotonic", lambda: clock[0]), self.assertLogs(logger, logging.WARNING) as logs:
            self.assertTrue(f3.warn_limited(logger, "k", "failed %s", 1))
            self.assertFalse(f3.warn_limited(logger, "k", "failed %s", 2))
            self.assertFalse(f3.warn_limited(logger, "k", "failed %s", 3))
            self.assertTrue(f3.warn_limited(logger, "other", "other key"))
            clock[0] += 601
            self.assertTrue(f3.warn_limited(logger, "k", "failed %s", 4))
        self.assertEqual([r.getMessage() for r in logs.records],
                         ["failed 1", "other key", "failed 4 (2 similar suppressed)"])
        f3._WARNED.clear()


class ConfigWiringTests(unittest.TestCase):
    def test_f3_reads_the_parsed_parameters(self):
        tuned = IntelligenceConfig.from_app_config({"score_model_f3": {"mode": "shadow", "levels": {"c_high": 0.86}}})
        self.assertEqual(run(cfg=tuned).level, "good")                     # 0.856 < 0.86
        self.assertNotEqual(tuned.f3["params"], P["params"])

    def test_n_min_high_is_at_least_comparables_min_n(self):
        cfg = IntelligenceConfig.from_app_config({"score_model_f3": {"mode": "shadow", "levels": {"n_min_high": 5}},
                                                  "comparables": {"min_n": 8}})
        self.assertEqual(cfg.f3["levels"]["n_min_high"], 8)
        self.assertEqual(run(ref=ref_at(8.0357, n=9), cfg=cfg).flags, ())
        self.assertEqual(run(ref=ref_at(8.0357, n=7), cfg=cfg).flags, (NO_COMPARABLES,))   # f2: n < min_n
        self.assertEqual(score_model_f3(None)["levels"]["n_min_high"], 10)


if __name__ == "__main__":
    unittest.main()
