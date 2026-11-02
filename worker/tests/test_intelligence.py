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
from intelligence.red_flags import RedFlag
from intelligence.seller_questions import question_texts, seller_questions


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
        bare = fiesta_listing(year=None, mileage_km=None, transmission=None,
                              price=None, price_usd=None)
        result = match(bare, fiesta_profile())
        self.assertIsNotNone(result)
        self.assertEqual(set(result.unknown), {"year", "km", "transmission", "price"})

    def test_a_listing_that_cannot_be_placed_fails_a_search_with_a_radius(self):
        unplaced = fiesta_listing(lat=None, lon=None)
        self.assertIsNone(match(unplaced, fiesta_profile()))
        # Without a radius the zone was never asked for.
        self.assertIsNotNone(match(unplaced, {**fiesta_profile(), "radius_km": None}))

    def test_a_fail_discards(self):
        self.assertIsNone(match(fiesta_listing(transmission="automatic"), fiesta_profile()))
        self.assertIsNone(match(fiesta_listing(year=2014), fiesta_profile()))
        self.assertIsNone(match(fiesta_listing(model="Focus"), fiesta_profile()))
        self.assertIsNone(match(fiesta_listing(mileage_km=180_000), fiesta_profile()))

    def test_a_band_listing_never_matches_its_model_search(self):
        """The reference year band (pipeline/crawl.py) reads a Ka 2009 for a search from 2010: no match."""
        ka = fiesta_listing(model="Ka", title="Ford Ka 1.5 SE 2009", trim="SE", year=2009, price=5_000.0,
                            price_usd=5_000.0)
        profile = fiesta_profile(model="Ka", trims=[], year_min=2010, year_max=None, price_max=None)
        self.assertIsNone(evaluate(ka, profile, price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX))
        self.assertIsNotNone(evaluate(dict(ka, year=2010), profile, price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX))

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

    def test_unknown_publication_uses_first_detection(self):
        from intelligence.scoring import recency_component
        for detected in (NOW, NOW - timedelta(days=30)):
            component = recency_component(fiesta_listing(published_at=None, first_seen_at=detected), CFG, NOW)
            expected = 0.5 ** ((NOW - detected).total_seconds() / 3600 / 24)
            self.assertAlmostEqual(component.c, expected)
            self.assertIn("detectado por primera vez", component.explanation)

    def test_without_either_date_recency_is_unknown(self):
        from intelligence.scoring import recency_component
        component = recency_component(fiesta_listing(published_at=None, first_seen_at=None), CFG, NOW)
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
        # PAR-02: much_cheaper_verify says "motivo para verificar", not "conviene".
        for text in copy.RED_FLAG.values():
            self.assertTrue("conviene" in text.lower() or "verificar" in text.lower(), text)


class MuchCheaperBandTests(unittest.TestCase):
    """PAR-02 tramo 1: three texts for the same much_cheaper flag (25 / 35 / 50)."""

    def text(self, diff_pct: float, cfg: IntelligenceConfig = CFG) -> str | None:
        flags = red_flags(fiesta_listing(), diff_pct=diff_pct, guard=None,
                          timing_belt=True, cfg=cfg, now=NOW)
        return next((f.text for f in flags if f.id == "much_cheaper"), None)

    @staticmethod
    def expected(key: str, diff_pct: float) -> str:
        return copy.RED_FLAG[key].format(pct=f"{diff_pct:.0f}")

    def test_the_band_for_each_edge(self):
        self.assertIsNone(self.text(24.9))
        for diff, key in ((25.0, "much_cheaper"), (34.4, "much_cheaper"),
                          (35.0, "much_cheaper_verify"), (49.4, "much_cheaper_verify"),
                          (50.0, "much_cheaper_anticipo")):
            with self.subTest(diff=diff):
                self.assertEqual(self.text(diff), self.expected(key, diff))

    def test_the_band_follows_the_shown_percentage(self):
        """A shown 35% or 50% always carries that band's text, whatever the decimals."""
        for diff, shown, key in ((34.6, "35", "much_cheaper_verify"), (34.9, "35", "much_cheaper_verify"),
                                 (34.5, "34", "much_cheaper"), (49.6, "50", "much_cheaper_anticipo"),
                                 (49.9, "50", "much_cheaper_anticipo"), (49.5, "50", "much_cheaper_anticipo"),
                                 (49.4, "49", "much_cheaper_verify")):
            with self.subTest(diff=diff):
                text = self.text(diff)
                self.assertEqual(text, copy.RED_FLAG[key].format(pct=shown))
        for a, b in ((34.6, 35.0), (49.6, 50.0)):
            with self.subTest(pair=(a, b)):
                self.assertEqual(self.text(a), self.text(b))

    def test_the_flag_keeps_its_id_and_severity(self):
        flags = red_flags(fiesta_listing(), diff_pct=40.0, guard=None, timing_belt=True, cfg=CFG, now=NOW)
        self.assertEqual([(f.id, f.severity) for f in flags], [("much_cheaper", "warning")])

    def test_incoherent_thresholds_fall_back_to_two_bands(self):
        for verify in (20, 25, 50, 60):
            cfg = IntelligenceConfig.from_app_config({"red_flags": {"much_cheaper_verify_pct": verify}})
            with self.subTest(verify=verify):
                self.assertEqual(self.text(40.0, cfg), self.expected("much_cheaper", 40.0))
                self.assertEqual(self.text(55.0, cfg), self.expected("much_cheaper_anticipo", 55.0))

    def test_only_the_text_changes(self):
        """Same score, level, flag ids, severities and questions as without the middle band."""
        two_bands = IntelligenceConfig.from_app_config({"red_flags": {"much_cheaper_verify_pct": 50}})
        for diff in (25.0, 34.9, 35.0, 49.9, 50.0):
            price = 11_200 * (1 - diff / 100)
            listing = fiesta_listing(price=price, price_usd=price)
            ref = PriceRef(n=23, level_used="model", median=11_200.0, median_km=125_000.0, diff_pct=diff)
            with self.subTest(diff=diff):
                _, s1, ev1 = assess(listing, fiesta_profile(), price_ref=ref, cfg=CFG, now=NOW)
                _, s2, ev2 = assess(listing, fiesta_profile(), price_ref=ref, cfg=two_bands, now=NOW)
                self.assertEqual((s1.score, s1.level), (s2.score, s2.level))
                self.assertEqual([(f.id, f.severity) for f in ev1.red_flags],
                                 [(f.id, f.severity) for f in ev2.red_flags])
                self.assertEqual(ev1.questions, ev2.questions)


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


class QuestionTextsTests(unittest.TestCase):
    """H-01: the questions specific to a listing, for the alert email."""

    def texts(self, flags=(), **kw):
        listing = fiesta_listing(description=LONG_DESCRIPTION, year=2025, **kw)
        return question_texts(listing, flags, timing_belt=False, now=NOW)

    def test_a_complete_listing_has_none(self):
        self.assertEqual(self.texts(), [])

    def test_never_includes_the_generic_questions(self):
        out = question_texts(fiesta_listing(), [], timing_belt=True, now=NOW)
        for key in ("greeting", "available", "holder"):
            self.assertNotIn(copy.QUESTION[key], out)
        self.assertEqual(out[0], copy.QUESTION["timing_belt"])

    def test_one_specific_question(self):
        self.assertEqual(self.texts(trim=None), [copy.QUESTION["trim"]])

    def test_cuts_at_three_keeping_the_order(self):
        out = self.texts(mileage_km=None, transmission=None, trim=None)
        self.assertEqual(out, [copy.QUESTION[k] for k in ("km_unknown", "transmission", "trim")])
        self.assertEqual(len(self.texts(mileage_km=None, transmission=None, trim=None, price_partial=True)), 3)

    def test_flags_as_objects_or_dicts_give_the_same_questions(self):
        flag = RedFlag("no_owners", "x", "info")
        self.assertEqual(self.texts([flag]), self.texts([flag.to_json()]))
        self.assertIn(copy.QUESTION["owners"], self.texts([flag]))


class PriceRefBySellerTests(unittest.TestCase):
    """F-02 paso 3: comparables() adds dealer/private n and median; nothing scores them."""

    SQL_V2 = {"n": 11, "p25": 9750.00, "p75": 13500.00, "median": 11000.00, "diff_pct": 9.09,
              "median_km": 100000, "level_used": "trim_transmission",
              "dealer_n": 5, "private_n": 4, "dealer_median": 12000.00, "private_median": 10000.00}
    OLD_KEYS = ("n", "p25", "p75", "median", "diff_pct", "median_km", "level_used")

    def test_reads_the_four_new_keys(self):
        ref = PriceRef.from_json(self.SQL_V2)
        self.assertEqual((ref.dealer_n, ref.dealer_median, ref.private_n, ref.private_median),
                         (5, 12_000.0, 4, 10_000.0))
        self.assertIsInstance(ref.dealer_n, int)
        self.assertEqual(ref.to_json(), self.SQL_V2)

    def test_a_ref_from_before_step_3_has_none_and_round_trips_with_its_seven_keys(self):
        old = {k: self.SQL_V2[k] for k in self.OLD_KEYS}
        ref = PriceRef.from_json(old)
        self.assertEqual((ref.dealer_n, ref.dealer_median, ref.private_n, ref.private_median),
                         (None, None, None, None))
        self.assertEqual(ref.to_json(), old)

    def test_no_dealers_keeps_n_zero_and_a_null_median(self):
        data = dict(self.SQL_V2, dealer_n=0, dealer_median=None)
        ref = PriceRef.from_json(data)
        self.assertEqual((ref.dealer_n, ref.dealer_median), (0, None))
        self.assertEqual(ref.to_json(), data)

    def test_to_json_rounds_the_medians_to_two_decimals(self):
        ref = PriceRef(n=11, level_used="model", median=11_000.0, dealer_n=5, dealer_median=12_000.456,
                       private_n=4, private_median=9_999.994)
        out = ref.to_json()
        self.assertEqual((out["dealer_median"], out["private_median"]), (12_000.46, 9_999.99))
        self.assertEqual((out["dealer_n"], out["private_n"]), (5, 4))

    def test_the_score_does_not_read_them(self):
        old = PriceRef.from_json({k: self.SQL_V2[k] for k in self.OLD_KEYS})
        new = PriceRef.from_json(self.SQL_V2)
        far = PriceRef.from_json(dict(self.SQL_V2, dealer_n=40, dealer_median=1.0, private_n=0, private_median=None))
        listing = fiesta_listing(price_usd=10_000.0, price=10_000.0)
        rows = []
        for ref in (old, new, far):
            _, _, ev = assess(listing, fiesta_profile(), price_ref=ref, cfg=CFG, now=NOW)
            row = ev.row()
            row.pop("price_ref")
            rows.append(row)
        self.assertEqual(rows[0], rows[1])
        self.assertEqual(rows[0], rows[2])


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

    def test_the_verify_threshold_defaults_to_35(self):
        production = {"much_cheaper_pct": 25, "anticipo_pct": 50, "min_km_per_year": 5000,
                      "min_description_chars": 150}
        self.assertEqual(IntelligenceConfig.from_app_config({"red_flags": production})
                         .red_flags["much_cheaper_verify_pct"], 35)
        tuned = IntelligenceConfig.from_app_config({"red_flags": {**production, "much_cheaper_verify_pct": 40}})
        self.assertEqual(tuned.red_flags["much_cheaper_verify_pct"], 40)


if __name__ == "__main__":
    unittest.main()


class SellerPreferencePinTests(unittest.TestCase):
    """PRO-01: the scores of today's seller preference, fixed against the code
    before the strict filter existed. They must not change (no SCORING_VERSION
    bump): a search without filters.seller_types scores exactly as before."""

    LISTINGS = {
        "none": {},
        "private": {"seller_type": "private"},
        "dealer": {"seller_type": "dealer"},
        "inferred": {"seller_type": "private", "dealer_inferred": True, "seller_listing_count": 6},
    }
    UNKNOWN = {"result": "unknown", "detail": "la publicación no lo informa", "kind": "soft"}
    # (preference, listing) → (score, level, c_match, c_completeness, match explanation, seller_type reason)
    PINNED = {
        (None, "none"): (89, "high", 1.0, 0.7, "cumple 2/2 preferencias", None),
        (None, "private"): (90, "high", 1.0, 0.8, "cumple 2/2 preferencias", None),
        (None, "dealer"): (90, "high", 1.0, 0.8, "cumple 2/2 preferencias", None),
        (None, "inferred"): (90, "high", 1.0, 0.8, "cumple 2/2 preferencias", None),
        ("private", "none"): (81, "good", 0.6667, 0.7, "cumple 2/3 preferencias", UNKNOWN),
        ("private", "private"): (90, "high", 1.0, 0.8, "cumple 3/3 preferencias",
                                 {"result": "ok", "detail": "vendedor particular", "kind": "soft"}),
        ("private", "dealer"): (82, "good", 0.6667, 0.8, "cumple 2/3 preferencias",
                                {"result": "fail", "detail": "vendedor concesionaria, se prefiere particular",
                                 "kind": "soft"}),
        ("private", "inferred"): (82, "good", 0.6667, 0.8, "cumple 2/3 preferencias",
                                  {"result": "fail",
                                   "detail": "vendedor posible agencia (publica 6 autos), se prefiere particular",
                                   "kind": "soft"}),
        ("dealer", "none"): (81, "good", 0.6667, 0.7, "cumple 2/3 preferencias", UNKNOWN),
        ("dealer", "private"): (82, "good", 0.6667, 0.8, "cumple 2/3 preferencias",
                                {"result": "fail", "detail": "vendedor particular, se prefiere concesionaria",
                                 "kind": "soft"}),
        ("dealer", "dealer"): (90, "high", 1.0, 0.8, "cumple 3/3 preferencias",
                               {"result": "ok", "detail": "vendedor concesionaria", "kind": "soft"}),
        ("dealer", "inferred"): (90, "high", 1.0, 0.8, "cumple 3/3 preferencias",
                                 {"result": "ok", "detail": "vendedor posible agencia (publica 6 autos)",
                                  "kind": "soft"}),
    }

    def _evaluate(self, pref, name, profile=None):
        p = profile or fiesta_profile()
        if pref:
            p["preferences"]["seller_type"] = pref
        return evaluate(fiesta_listing(**self.LISTINGS[name]), p, price_ref=MARKET, cfg=CFG, now=NOW, fx_rate=FX)

    def test_seller_preference_scores_are_pinned(self):
        for (pref, name), (score, level, c_match, c_comp, explanation, reason) in self.PINNED.items():
            with self.subTest(pref=pref, listing=name):
                ev = self._evaluate(pref, name)
                b = ev.row()["score_breakdown"]
                reasons = ev.row()["match_reasons"]
                self.assertEqual(ev.score.score, score)
                self.assertEqual(ev.level, level)
                self.assertAlmostEqual(b["match"]["c"], c_match, places=4)
                self.assertAlmostEqual(b["price"]["c"], 0.9018, places=4)
                self.assertAlmostEqual(b["km"]["c"], 0.63, places=4)
                self.assertEqual(b["trim"]["c"], 1.0)
                self.assertAlmostEqual(b["recency"]["c"], 0.9981, places=4)
                self.assertEqual(b["completeness"]["c"], c_comp)
                self.assertEqual(b["match"]["explanation"], explanation)
                self.assertEqual(reasons.get("seller_type"), reason)
                self.assertEqual(set(reasons), {"model", "year", "price", "km", "transmission", "location",
                                                "trim", "km_target", "price_target"}
                                 | ({"seller_type"} if pref else set()))
