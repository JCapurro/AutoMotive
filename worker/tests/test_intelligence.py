"""F2 intelligence, pure (docs/TECHNICAL_PLAN.md, sección 6): no network, no database."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from intelligence import copy
from intelligence.comparables import PriceRef
from intelligence.config import SCORING_VERSION, IntelligenceConfig
from intelligence.engine import assess, evaluate
from intelligence.levels import level_for
from intelligence.matching import match
from intelligence.red_flags import red_flags
from intelligence.seller_questions import seller_questions


NOW = datetime(2026, 9, 27, 15, 0, tzinfo=timezone.utc)
CFG = IntelligenceConfig()
FX = 1_000.0       # ARS per USD

LONG_DESCRIPTION = ("Ford Fiesta Titanium 1.6 manual, único dueño, services oficiales al día en "
                    "concesionario, distribución hecha a los 100.000 km. Cubiertas nuevas, "
                    "VTV vigente. Se entrega con manual y duplicado de llave.")


def fiesta_listing(**kw) -> dict:
    """The PRD example (§10, §22): Fiesta Titanium 2017, 112.000 km, USD 10.300,
    published 4 minutes ago, 6 of the 10 key fields informed."""
    row = dict(
        id=1, source="mercadolibre", title="Ford Fiesta Titanium 1.6 2017",
        make="Ford", model="Fiesta", trim="Titanium", year=2017,
        price=10_300.0, currency="USD", price_usd=10_300.0, mileage_km=112_000,
        transmission="manual", fuel="nafta",
        location_text="Vicente López", lat=-34.526, lon=-58.479,
        seller_type=None, images=["1.jpg"], attributes={}, description=None,
        published_at=NOW - timedelta(minutes=4), first_seen_at=NOW - timedelta(minutes=4),
        price_partial=False, probable_repost_of=None, enriched_at=None,
    )
    row.update(kw)
    return row


def fiesta_profile(**filters) -> dict:
    f = {"make": "Ford", "model": "Fiesta", "trims": ["Titanium"], "trim_strict": False,
         "year_min": 2016, "year_max": 2018, "price_max": 11_500, "currency": "USD",
         "km_max": 150_000, "transmission": "manual"}
    f.update(filters)
    return {"id": 7, "filters": f,
            "preferences": {"km_target": 120_000, "price_target": 10_500, "preferred_trims": ["Titanium"]},
            "origin_lat": -34.6037, "origin_lon": -58.3816, "radius_km": 60}


# Median USD 11.200 and median km 125.000 over 23 comparables.
MARKET = PriceRef(n=23, level_used="trim_transmission", median=11_200.0, p25=10_600.0,
                  p75=11_900.0, median_km=125_000.0, diff_pct=(1 - 10_300 / 11_200) * 100)


class GoldenFixtureTests(unittest.TestCase):
    """Sección 6.3: the calibration example must land between 85 and 90."""

    def test_fiesta_2017_scores_85_to_90_and_is_high(self):
        ev = evaluate(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX)

        self.assertIsNotNone(ev)
        self.assertGreaterEqual(ev.score.score, 85)
        self.assertLessEqual(ev.score.score, 90)
        self.assertEqual(ev.score.score, 89)
        self.assertEqual(ev.level, "high")

    def test_breakdown_matches_the_calibration_table(self):
        ev = evaluate(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX)
        b = ev.row()["score_breakdown"]

        self.assertAlmostEqual(b["price"]["c"], 0.90, places=2)
        self.assertEqual(b["match"]["c"], 1.0)
        self.assertAlmostEqual(b["km"]["c"], 0.63, places=2)
        self.assertEqual(b["trim"]["c"], 1.0)
        self.assertAlmostEqual(b["recency"]["c"], 1.0, places=2)
        self.assertEqual(b["completeness"]["c"], 0.7)
        self.assertAlmostEqual(b["price"]["contribution"], 31.6, places=1)
        self.assertEqual(b["scoring_version"], SCORING_VERSION)
        self.assertEqual(b["price"]["explanation"],
                         "8% debajo del mercado observado · publicaciones comparables (n=23)")
        self.assertEqual(b["km"]["explanation"], "10% menos km que publicaciones comparables")
        self.assertEqual(b["recency"]["explanation"], "publicado hace 4 min")
        self.assertEqual(b["completeness"]["explanation"], "7/10 datos informados")

    def test_match_reasons_have_one_entry_per_filter(self):
        ev = evaluate(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX)
        reasons = ev.row()["match_reasons"]

        self.assertEqual(reasons["model"], {"result": "ok", "detail": "Ford Fiesta", "kind": "hard"})
        self.assertEqual(reasons["year"]["detail"], "2017 ∈ 2016–2018")
        self.assertEqual(reasons["price"]["detail"], "USD 10.300 ≤ USD 11.500")
        self.assertEqual(reasons["km"]["detail"], "112.000 ≤ 150.000")
        self.assertTrue(reasons["location"]["detail"].startswith("Vicente López · "))
        self.assertEqual(reasons["trim"], {"result": "ok", "detail": "Titanium (preferida)", "kind": "soft"})
        self.assertEqual({k for k, r in reasons.items() if r["kind"] == "soft"},
                         {"trim", "km_target", "price_target"})

    def test_weights_come_from_app_config(self):
        heavy_price = IntelligenceConfig.from_app_config(
            {"score_weights": {"price": 100, "match": 0, "km": 0, "trim": 0, "recency": 0, "completeness": 0}})
        ev = evaluate(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=heavy_price, now=NOW)
        self.assertEqual(ev.score.score, 90)                      # only c_price = 0.90 counts


class UnknownTests(unittest.TestCase):
    """Sección 6.1: an unknown never discards, but lowers the score."""

    def test_unknown_transmission_matches_with_a_lower_score(self):
        known = evaluate(fiesta_listing(), fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW)
        unknown = evaluate(fiesta_listing(transmission=None), fiesta_profile(),
                           price_ref=MARKET, cfg=CFG, now=NOW)

        self.assertIsNotNone(unknown)
        self.assertEqual(unknown.match.unknown, ["transmission"])
        self.assertEqual(unknown.row()["match_reasons"]["transmission"],
                         {"result": "unknown", "detail": "la publicación no lo informa", "kind": "hard"})
        self.assertLess(unknown.score.score, known.score.score)
        self.assertAlmostEqual(unknown.score.components["match"].c, 0.85)
        self.assertIn("transmisión no informado", unknown.score.components["match"].explanation)

    def test_every_hard_filter_unknown_still_matches(self):
        bare = fiesta_listing(year=None, mileage_km=None, transmission=None, lat=None, lon=None,
                              price=None, price_usd=None)
        result = match(bare, fiesta_profile())
        self.assertIsNotNone(result)
        self.assertEqual(set(result.unknown), {"year", "km", "transmission", "location", "price"})

    def test_a_fail_discards(self):
        self.assertIsNone(match(fiesta_listing(transmission="automatic"), fiesta_profile()))
        self.assertIsNone(match(fiesta_listing(year=2014), fiesta_profile()))
        self.assertIsNone(match(fiesta_listing(model="Focus"), fiesta_profile()))
        self.assertIsNone(match(fiesta_listing(mileage_km=180_000), fiesta_profile()))

    def test_a_non_strict_trim_is_soft_and_a_strict_one_is_hard(self):
        sel = fiesta_listing(trim="SEL")
        self.assertIsNotNone(match(sel, fiesta_profile()))
        self.assertIsNone(match(sel, fiesta_profile(trim_strict=True)))
        ev = evaluate(sel, fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW)
        self.assertEqual(ev.score.components["trim"].c, 0.2)


class CurrencyTests(unittest.TestCase):
    """Sección 6.1: prices are converted with fx, never discarded for their currency."""

    def ars(self, usd: float, **kw) -> dict:
        return fiesta_listing(**{"price": usd * FX, "currency": "ARS", "price_usd": usd, **kw})

    def test_ars_listing_under_a_usd_cap_matches(self):
        result = match(self.ars(10_300), fiesta_profile(), fx_rate=FX)
        self.assertIsNotNone(result)
        self.assertEqual(result.reasons["price"].detail, "ARS 10.300.000 ≈ USD 10.300 ≤ USD 11.500")

    def test_ars_listing_over_a_usd_cap_fails(self):
        result = match(self.ars(12_000), fiesta_profile(), fx_rate=FX)
        self.assertIsNone(result)

    def test_the_frozen_price_usd_wins_over_todays_rate(self):
        # Seen at 1.000 ARS/USD; today's rate doubled. The cap compares the frozen USD.
        self.assertIsNotNone(match(self.ars(10_300), fiesta_profile(), fx_rate=2 * FX))

    def test_without_price_usd_todays_rate_converts(self):
        row = self.ars(12_000, price_usd=None)
        self.assertIsNone(match(row, fiesta_profile(), fx_rate=FX))
        self.assertIsNotNone(match(row, fiesta_profile(), fx_rate=1.5 * FX))    # 8.000 USD

    def test_usd_listing_under_an_ars_cap(self):
        profile = fiesta_profile(price_max=11_000_000, currency="ARS")
        result = match(fiesta_listing(), profile, fx_rate=FX)
        self.assertEqual(result.reasons["price"].detail, "USD 10.300 ≈ ARS 10.300.000 ≤ ARS 11.000.000")
        self.assertIsNone(match(fiesta_listing(price=12_000.0, price_usd=12_000.0), profile, fx_rate=FX))

    def test_no_rate_means_unknown_not_fail(self):
        profile = fiesta_profile(price_max=11_000_000, currency="ARS")
        result = match(fiesta_listing(), profile, fx_rate=None)
        self.assertEqual(result.reasons["price"].result, "unknown")

    def test_a_cap_without_currency_is_read_by_magnitude(self):
        profile = fiesta_profile(price_max=11_500, currency=None)
        self.assertIsNotNone(match(self.ars(10_300), profile, fx_rate=FX))
        self.assertIsNone(match(self.ars(12_000), profile, fx_rate=FX))


class GuardAndLevelTests(unittest.TestCase):
    def ref(self, price_usd: float) -> PriceRef:
        return PriceRef(n=23, level_used="model", median=11_200.0, median_km=125_000.0,
                        diff_pct=(1 - price_usd / 11_200) * 100)

    def test_suspicious_discount_caps_the_level_at_good_and_flags(self):
        listing = fiesta_listing(price=5_000.0, price_usd=5_000.0)        # 55% below
        ev = evaluate(listing, fiesta_profile(), price_ref=self.ref(5_000), cfg=CFG, now=NOW)
        self.assertGreaterEqual(ev.score.score, 85)
        self.assertEqual(ev.level, "good")
        ids = [f.id for f in ev.red_flags]
        self.assertIn("partial_price_suspect", ids)
        self.assertIn("much_cheaper", ids)
        self.assertIn("anticipo", next(f.text for f in ev.red_flags if f.id == "much_cheaper"))
        self.assertIn("¿El precio publicado es el total o es un anticipo?", ev.questions)

    def test_a_price_that_looks_like_a_down_payment_is_excluded(self):
        listing = fiesta_listing(price=3_000.0, price_usd=3_000.0)        # 73% below
        self.assertIsNone(evaluate(listing, fiesta_profile(), price_ref=self.ref(3_000), cfg=CFG, now=NOW))

    def test_price_partial_is_excluded(self):
        listing = fiesta_listing(price_partial=True, price_partial_reason="keyword: anticipo")
        self.assertIsNone(evaluate(listing, fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW))

    def test_too_few_comparables_is_neutral(self):
        few = PriceRef(n=3, level_used="model", median=11_200.0, median_km=125_000.0, diff_pct=8.0)
        ev = evaluate(fiesta_listing(), fiesta_profile(), price_ref=few, cfg=CFG, now=NOW)
        self.assertEqual(ev.score.components["price"].c, 0.5)
        self.assertEqual(ev.score.components["km"].c, 0.5)
        self.assertEqual(ev.score.components["price"].explanation, "sin comparables suficientes (n=3)")

    def test_levels_follow_the_configured_thresholds(self):
        t = {"high": 85, "good": 70, "match": 50}
        self.assertEqual([level_for(s, t) for s in (100, 85, 84, 70, 69, 50, 49, 0)],
                         ["high", "high", "good", "good", "match", "match", "low", "low"])
        self.assertEqual(level_for(90, {"high": 95, "good": 80, "match": 60}), "good")
        self.assertEqual(level_for(90, t, cap="good"), "good")

    def test_unknown_publication_does_not_reward_recent_detection(self):
        from intelligence.scoring import recency_component
        for detected in (NOW, NOW - timedelta(days=30)):
            component = recency_component(fiesta_listing(published_at=None, first_seen_at=detected), CFG, NOW)
            self.assertEqual(component.c, 0)
            self.assertIn("no informada", component.explanation)

    def test_old_publication_detected_today_is_still_old(self):
        from intelligence.scoring import recency_component
        component = recency_component(fiesta_listing(published_at=NOW - timedelta(days=30), first_seen_at=NOW), CFG, NOW)
        self.assertLess(component.c, 0.001)
        self.assertIn("publicado", component.explanation)

    def test_recency_halves_every_24_hours(self):
        day_old = fiesta_listing(published_at=NOW - timedelta(hours=24))
        _, s, _ = assess(day_old, fiesta_profile(), price_ref=MARKET, cfg=CFG, now=NOW)
        self.assertAlmostEqual(s.components["recency"].c, 0.5)
        self.assertEqual(s.components["recency"].explanation, "publicado hace 24 h")


class RedFlagTests(unittest.TestCase):
    def flags(self, **kw):
        timing_belt = kw.pop("timing_belt", True)
        diff = kw.pop("diff_pct", None)
        return [f.id for f in red_flags(fiesta_listing(**kw), diff_pct=diff, guard=None,
                                        timing_belt=timing_belt, cfg=CFG, now=NOW)]

    def test_description_rules_wait_for_the_description(self):
        self.assertEqual(self.flags(), [])

    def test_an_enriched_listing_without_description_is_flagged(self):
        self.assertEqual(self.flags(enriched_at=NOW),
                         ["no_owners", "no_service", "no_timing_belt", "short_description"])

    def test_a_complete_description_raises_nothing(self):
        self.assertEqual(self.flags(description=LONG_DESCRIPTION), [])

    def test_timing_belt_only_for_belt_models(self):
        text = "Único dueño, services oficiales al día. " * 5
        self.assertEqual(self.flags(description=text), ["no_timing_belt"])
        self.assertEqual(self.flags(description=text, timing_belt=False), [])
        self.assertEqual(self.flags(description=text, timing_belt=None), [])

    def test_numbers(self):
        self.assertEqual(self.flags(diff_pct=30.0), ["much_cheaper"])
        self.assertEqual(self.flags(diff_pct=20.0), [])
        self.assertEqual(self.flags(mileage_km=20_000), ["low_km_for_age"])      # 9 years, 2.222/año
        self.assertEqual(self.flags(probable_repost_of=99), ["repost"])

    def test_every_flag_reads_as_something_to_verify(self):
        for text in copy.RED_FLAG.values():
            self.assertIn("conviene", text.lower())


class SellerQuestionTests(unittest.TestCase):
    def test_always_greets_and_asks_availability_and_holder(self):
        text = seller_questions(fiesta_listing(description=LONG_DESCRIPTION, year=2025,
                                               seller_type="private"), [], timing_belt=False, now=NOW)
        self.assertEqual(text, "Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular?")

    def test_the_prd_example_for_an_unenriched_belt_car(self):
        text = seller_questions(fiesta_listing(), [], timing_belt=True, now=NOW)
        self.assertEqual(text, "Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular? "
                               "¿Cuándo se hizo la distribución por última vez? ¿Tiene VTV vigente? "
                               "¿Tuvo choques o reparaciones importantes? ¿Tenés historial de services?")

    def test_missing_data_becomes_questions(self):
        listing = fiesta_listing(mileage_km=None, transmission=None, trim=None,
                                 description=LONG_DESCRIPTION, year=2025)
        text = seller_questions(listing, [], timing_belt=False, now=NOW)
        self.assertIn("¿Cuántos km tiene?", text)
        self.assertIn("¿Es manual o automático?", text)
        self.assertIn("¿Qué versión es?", text)


class ConfigTests(unittest.TestCase):
    def test_partial_app_config_keeps_the_defaults(self):
        cfg = IntelligenceConfig.from_app_config({
            "score_weights": {"price": 50},
            "score_curves": {"recency": {"half_life_hours": 12}},
            "comparables": None,
        })
        self.assertEqual(cfg.weights["price"], 50)
        self.assertEqual(cfg.weights["match"], 25)
        self.assertEqual(cfg.curve("recency")["half_life_hours"], 12)
        self.assertEqual(cfg.curve("price")["pct_per_unit"], 20)
        self.assertEqual(cfg.min_n, 5)


if __name__ == "__main__":
    unittest.main()
