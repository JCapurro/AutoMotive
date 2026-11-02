"""PRO-02: the estimated gross margin against the dealers' median
(intelligence/margin.py; docs/superpowers/specs/2026-11-02-pro02-margen-design.md).
The transfer comes from PAR-01's calculator with golden.json's parameters."""
from __future__ import annotations

import json
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from intelligence import copy, cost_estimator, margin
from intelligence.comparables import PriceRef
from intelligence.config import IntelligenceConfig
from intelligence.engine import Evaluation
from normalization.normalize import normalize_text
from pipeline.scoring import Scorer, profile_zones
from test_intelligence import fiesta_listing, fiesta_profile

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "cost_estimator" / "golden.json").read_text(encoding="utf-8"))
COST = cost_estimator.parse_config(GOLDEN["config"])
DEALER = margin.parse_config({"as_of": "2026-11-02", "source": "Juan", "reconditioning": {"pct": 5, "min_usd": 300},
                              "transfer": {"enabled": True}})
TODAY = date(2026, 11, 2)
PALERMO = cost_estimator.search_zones({"lat": -34.5875, "lon": -58.42, "label": "Palermo, CABA"})
AMBA = cost_estimator.search_zones({"lat": -34.6037, "lon": -58.3816, "label": "AMBA"})
CORDOBA = cost_estimator.search_zones({"lat": -31.4201, "lon": -64.1888, "label": "Córdoba"})
CABA_AND_CORDOBA = cost_estimator.search_zones({"lat": -34.5875, "lon": -58.42, "label": "Palermo, CABA",
                                                "extra_locations": [{"lat": -31.4201, "lon": -64.1888,
                                                                     "label": "Córdoba"}]})
# Pool of 10 comparables: 6 dealers (median 18.000) and 4 private sellers (median 12.000).
POOL = PriceRef(n=10, level_used="transmission", median=13_000.0, p25=12_000.0, p75=17_000.0, median_km=90_000.0,
                diff_pct=-18.3, dealer_median=18_000.0, dealer_n=6, private_median=12_000.0, private_n=4)


def row(**kw):
    """A rows_for_scoring() row: golden case 1 (ARS 20.000.000 at 1.300, private, 2017 sedan)."""
    return {"id": 1, "price": 20_000_000.0, "currency": "ARS", "price_usd": 15_384.62, "price_partial": False,
            "description_facts": {}, "seller_type": "private", "dealer_inferred": False, "year": 2017,
            "body_type": "sedan", **kw}


def compute(r=None, ref=POOL, zones=PALERMO, dealer=DEALER, cost=COST, fx=None, min_n=5):
    return margin.compute(r or row(), ref, zones, dealer, cost, fx, min_n, TODAY)


class ParseConfigTests(unittest.TestCase):
    def test_the_seeded_config(self):
        self.assertEqual(DEALER, {"as_of": "2026-11-02", "reconditioning": {"pct": 5.0, "min_usd": 300.0}, "transfer": True,
                                  "plausible_ratio": {"min": 0.4, "max": 3.0}})

    def test_the_plausible_ratio_defaults_in_code(self):
        """No migration: without plausible_ratio in app_config the guard is {0.4, 3}."""
        for raw in (None, {}, {"plausible_ratio": None}, {"plausible_ratio": {"min": 0.4}},
                    {"plausible_ratio": {"min": 0, "max": 3}}, {"plausible_ratio": {"min": 0.5, "max": 0.9}},
                    {"plausible_ratio": {"min": True, "max": 3}}, {"plausible_ratio": {"min": 1.2, "max": 3}}):
            with self.subTest(raw=raw):
                self.assertEqual(margin.parse_config(raw)["plausible_ratio"], {"min": 0.4, "max": 3.0})
        self.assertEqual(margin.parse_config({"plausible_ratio": {"min": 0.5, "max": 2.5}})["plausible_ratio"],
                         {"min": 0.5, "max": 2.5})

    def test_tolerant_and_without_defaults(self):
        for raw in (None, {}, "x", {"reconditioning": {"pct": 120, "min_usd": 300}},
                    {"reconditioning": {"pct": 5}}, {"reconditioning": {"pct": 5, "min_usd": -1}},
                    {"reconditioning": {"pct": True, "min_usd": 300}}):
            with self.subTest(raw=raw):
                self.assertIsNone(margin.parse_config(raw)["reconditioning"])
        self.assertFalse(margin.parse_config({"transfer": {}})["transfer"])
        self.assertFalse(margin.parse_config({"transfer": {"enabled": "true"}})["transfer"])
        self.assertIsNone(margin.parse_config({"as_of": "02/11/2026"})["as_of"])


class PoolTests(unittest.TestCase):
    def test_six_dealers_and_four_private_sellers_use_the_dealers_median(self):
        m = compute()
        self.assertEqual((m["dealer_median"], m["dealer_n"], m["n"], m["level_used"]), (18_000.0, 6, 10, "transmission"))
        # 18.000 - 15.384,62 - (769,23 + transfer 621,54..629,88)
        self.assertEqual(m["reconditioning"], {"pct": 5.0, "min_usd": 300.0, "usd": 769.23})
        self.assertEqual(m["transfer"]["status"], "ok")
        self.assertEqual(m["transfer"]["usd"], {"min": 621.54, "max": 629.88})
        self.assertEqual(m["est_costs_usd"], {"min": 1390.77, "max": 1399.11})
        self.assertEqual(m["acquisition_usd"], {"min": 16775.39, "max": 16783.73})
        self.assertEqual(m["gross_margin_usd"], {"min": 1216.27, "max": 1224.61})
        self.assertEqual(m["gross_margin_pct"], {"min": 7.25, "max": 7.3})
        self.assertEqual(m["status"], "ok")
        # Not the overall median (13.000) nor the private one (12.000): both would give a negative margin.
        self.assertGreater(m["gross_margin_usd"]["min"], 0)

    def test_the_transfer_is_arancel_sellos_and_formularios_never_the_patente(self):
        m = compute()
        self.assertEqual(m["transfer"]["terms"], ["arancel", "sellos", "formularios"])
        # golden case 1: 200.000 + 600.000 + 8.000..18.840 ARS, at the listing's dollar (1.300).
        self.assertAlmostEqual(m["transfer"]["usd"]["min"], 808_000 / 1300, places=1)
        self.assertAlmostEqual(m["transfer"]["usd"]["max"], 818_840 / 1300, places=1)
        self.assertEqual((m["transfer"]["jurisdiction"], m["transfer"]["seller"]), (["caba"], "private"))
        self.assertEqual(m["as_of"], {"dealer_margin": "2026-11-02", "cost_estimator": "2026-10-30"})

    def test_the_margin_min_uses_the_max_costs(self):
        m = compute()
        self.assertAlmostEqual(m["gross_margin_usd"]["min"],
                               m["dealer_median"] - m["asking_usd"] - m["est_costs_usd"]["max"], places=1)
        self.assertAlmostEqual(m["gross_margin_usd"]["max"],
                               m["dealer_median"] - m["asking_usd"] - m["est_costs_usd"]["min"], places=1)

    def test_the_percentage_is_on_what_buying_the_car_costs(self):
        """Juan, 02/11: on the price plus reconditioning and transfer, not on
        the dealers' median; the low end is the margin's min over the cost's max."""
        m = compute()
        acq, g = m["acquisition_usd"], m["gross_margin_usd"]
        self.assertAlmostEqual(acq["min"], m["asking_usd"] + m["est_costs_usd"]["min"], places=1)
        self.assertAlmostEqual(acq["max"], m["asking_usd"] + m["est_costs_usd"]["max"], places=1)
        self.assertAlmostEqual(m["gross_margin_pct"]["min"], g["min"] / acq["max"] * 100, places=2)
        self.assertAlmostEqual(m["gross_margin_pct"]["max"], g["max"] / acq["min"] * 100, places=2)
        self.assertNotAlmostEqual(m["gross_margin_pct"]["min"], g["min"] / m["dealer_median"] * 100, places=1)
        negative = compute(ref=PriceRef(**{**POOL.__dict__, "dealer_median": 15_000.0}))
        self.assertLess(negative["gross_margin_pct"]["min"], negative["gross_margin_pct"]["max"])


class NullTests(unittest.TestCase):
    def test_not_enough_dealers_says_so(self):
        """Juan, 02/11: with fewer dealers than min_n, no margin but the line
        that says why (n and the minimum); no threshold reached."""
        few = compute(ref=PriceRef(**{**POOL.__dict__, "dealer_n": 4}))
        self.assertEqual(few, {"v": 1, "status": "few_dealers", "dealer_n": 4, "min_n": 5, "n": 10,
                               "level_used": "transmission"})
        self.assertEqual(margin.line(few), "Margen estimado: no hay suficientes agencias publicando este modelo "
                                           "para estimarlo (n = 4, mínimo 5)")
        self.assertEqual(margin.email_payload(few), {"status": "few_dealers", "dealer_n": 4, "min_n": 5})
        self.assertIsNone(margin.threshold_low(few))
        self.assertTrue(margin.few_dealers(few))
        self.assertFalse(margin.few_dealers(compute()))
        self.assertEqual(compute(ref=PriceRef(**{**POOL.__dict__, "dealer_n": 0, "dealer_median": None}))["dealer_n"], 0)
        self.assertEqual(compute(ref=PriceRef(**{**POOL.__dict__, "dealer_n": 4}), min_n=4)["status"], "ok")

    def test_few_dealers_but_a_partial_price_or_no_price_usd_say_nothing(self):
        """The price is what is missing there (the card already says it): no line."""
        ref = PriceRef(**{**POOL.__dict__, "dealer_n": 2})
        for r in (row(price_partial=True), row(description_facts={"price_check": {"published_partial": True}}),
                  row(price_usd=None)):
            with self.subTest(r=r):
                self.assertIsNone(compute(r, ref=ref))

    def test_a_price_ref_before_the_seller_split_or_none(self):
        old = PriceRef.from_json({"n": 10, "level_used": "model", "median": 13_000, "p25": 1, "p75": 2,
                                  "median_km": 1, "diff_pct": 1})
        self.assertIsNone(old.dealer_n)
        for ref in (None, old, PriceRef(**{**POOL.__dict__, "dealer_median": None}),
                    PriceRef(**{**POOL.__dict__, "dealer_median": 0.0})):
            with self.subTest(ref=ref):
                self.assertIsNone(compute(ref=ref))

    def test_a_partial_price_or_no_price_usd(self):
        for r in (row(price_partial=True), row(description_facts={"price_check": {"published_partial": True}}),
                  row(price_usd=None), row(price_usd=0)):
            with self.subTest(r=r):
                self.assertIsNone(compute(r))


class FillQueueTests(unittest.IsolatedAsyncioTestCase):
    """matches_repo.WITHOUT_MARGIN mirrors every case where compute() returns
    None for a match that exists, so the fill converges (the SQL runs in
    test_margin_postgres.py)."""

    async def test_a_published_down_payment_never_gets_a_margin_nor_a_place_in_the_queue(self):
        from unittest.mock import patch
        from db.repos import matches as matches_repo
        from normalization.description_facts import PARTIAL_KINDS
        from pipeline.ingest import published_partial

        # The description gave the cash price: price_partial is false, the match exists.
        for facts in ({"price_check": {"published_partial": True}},
                      {"price_check": {"published_kind": "down_payment"}},
                      {"price_check": {"published_kind": "installment"}}):
            with self.subTest(facts=facts):
                r = row(description_facts=facts, price_partial=False)
                self.assertTrue(published_partial(r))
                self.assertIsNone(compute(r))

        calls = []

        class Cursor:
            async def fetchall(self):
                return []

        class Cx:
            async def execute(self, sql, params):
                calls.append((sql, params))
                return Cursor()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        with patch.object(matches_repo, "connection", lambda: Cx()):
            await matches_repo.rescore_queue(days=14, scoring_version="v", min_n=5, outdated_only=True)
        [(sql, params)] = calls
        self.assertIn("price_partial", sql)
        self.assertIn("{price_check,published_partial}", sql)
        self.assertIn("{price_check,published_kind}", sql)
        self.assertIn("::numeric > 0", sql)            # compute() also needs a positive median
        self.assertEqual(sorted(params["partial_kinds"]), sorted(PARTIAL_KINDS))


class TransferTests(unittest.TestCase):
    def test_without_the_search_s_place_no_transfer_and_no_other_zone(self):
        for zones in ([], [{"lat": None, "lon": None, "label": None}],
                      cost_estimator.search_zones({"lat": -34.9011, "lon": -56.1645, "label": "Montevideo"})):
            with self.subTest(zones=zones):
                m = compute(zones=zones)
                self.assertEqual(m["transfer"]["status"], "no_zone")
                self.assertIsNone(m["transfer"]["usd"])
                self.assertIsNone(m["transfer"]["jurisdiction"])
                self.assertEqual(m["est_costs_usd"], {"min": 769.23, "max": 769.23})
                self.assertNotIn("cost_estimator", m["as_of"])

    def test_amba_covers_caba_and_buenos_aires(self):
        m = compute(zones=AMBA)
        self.assertEqual(m["transfer"]["jurisdiction"], ["caba", "ba"])
        self.assertLess(m["transfer"]["usd"]["min"], m["transfer"]["usd"]["max"])

    def test_outside_caba_and_buenos_aires_no_transfer(self):
        """Juan, 02/11: PAR-01's range for the rest of the country (Córdoba,
        Santa Fe, Mendoza) is not used; the copy says there are no official values."""
        m = compute(zones=CORDOBA)
        self.assertEqual((m["transfer"]["status"], m["transfer"]["jurisdiction"]), ("no_official", ["rest"]))
        self.assertIsNone(m["transfer"]["usd"])
        self.assertEqual(m["est_costs_usd"], {"min": 769.23, "max": 769.23})
        self.assertNotIn("cost_estimator", m["as_of"])
        self.assertIn("no descuenta la transferencia porque no tenemos los valores oficiales de tu provincia",
                      margin.line(m))

    def test_a_search_that_mixes_caba_with_another_province_subtracts_none(self):
        m = compute(zones=CABA_AND_CORDOBA)
        self.assertEqual((m["transfer"]["status"], m["transfer"]["jurisdiction"]), ("no_official_some", ["caba", "rest"]))
        self.assertIsNone(m["transfer"]["usd"])
        self.assertIn("no tenemos los valores oficiales de todas las provincias de tu búsqueda", margin.line(m))

    def test_a_usd_listing_needs_a_fresh_quote(self):
        usd = row(price=15_000.0, currency="USD", price_usd=15_000.0)
        self.assertEqual(compute(usd)["transfer"]["status"], "no_fx")
        stale = {"rate": 1300.0, "kind": "blue", "date": "2026-10-28"}          # 5 days > fx.max_age_days 3
        self.assertEqual(compute(usd, fx=stale)["transfer"]["status"], "no_fx")
        fresh = {**stale, "date": "2026-11-01"}
        m = compute(usd, fx=fresh)
        self.assertEqual(m["transfer"]["status"], "ok")
        self.assertEqual(m["fx"], {"rate": 1300.0, "kind": "blue", "date": "2026-11-01"})

    def test_without_parameters_or_disabled(self):
        self.assertEqual(compute(cost=None)["transfer"]["status"], "params")
        self.assertEqual(compute(dealer={**DEALER, "transfer": False})["transfer"]["status"], "disabled")
        broken = cost_estimator.parse_config({**GOLDEN["config"], "dnrpa": {"source": "x", "as_of": "2026-10-30"}})
        self.assertEqual(compute(cost=broken)["transfer"]["status"], "params")


class ReconditioningTests(unittest.TestCase):
    def test_five_percent_above_the_minimum(self):
        self.assertEqual(compute()["reconditioning"]["usd"], 769.23)

    def test_the_minimum_of_usd_300_below_6000(self):
        cheap = row(price=5_200_000.0, price_usd=4_000.0)                        # 5 % = 200
        ref = PriceRef(**{**POOL.__dict__, "dealer_median": 6_000.0})
        self.assertEqual(compute(cheap, ref=ref)["reconditioning"]["usd"], 300.0)

    def test_without_its_parameters_no_costs_and_says_so(self):
        m = compute(dealer={**DEALER, "reconditioning": None}, zones=[])
        self.assertIsNone(m["reconditioning"])
        self.assertEqual(m["est_costs_usd"], {"min": 0.0, "max": 0.0})
        self.assertIn("sin descontar costos: faltan los parámetros de acondicionamiento", margin.line(m))

    def test_a_negative_margin_is_kept(self):
        m = compute(ref=PriceRef(**{**POOL.__dict__, "dealer_median": 15_000.0}))
        self.assertLess(m["gross_margin_usd"]["max"], 0)
        self.assertIn("Margen bruto estimado: USD -1.790 a -1.770", margin.line(m))


class LineTests(unittest.TestCase):
    def test_the_line(self):
        self.assertEqual(margin.line(compute()),
                         "Margen bruto estimado: USD 1.210 a 1.230 (contra la mediana de USD 18.000 a la que publican "
                         "las agencias este modelo, n = 6; descuenta acondicionamiento del 5 % y transferencia; sin impuestos)")

    def test_without_the_place(self):
        self.assertEqual(margin.line(compute(zones=[])),
                         "Margen bruto estimado: USD 1.850 (contra la mediana de USD 18.000 a la que publican las agencias "
                         "este modelo, n = 6; descuenta acondicionamiento del 5 %; no descuenta la transferencia porque "
                         "tu búsqueda no tiene localidad; sin impuestos)")

    def test_the_payload_rounds_outward(self):
        p = margin.email_payload(compute())
        self.assertEqual(p, {"status": "ok", "usd_min": 1210, "usd_max": 1230, "pct_min": 7, "pct_max": 8,
                             "dealer_median": 18_000,
                             "dealer_n": 6, "reconditioning_pct": 5.0, "transfer_status": "ok", "jurisdiction": ["caba"],
                             "as_of": "2026-10-30"})
        self.assertIsNone(margin.email_payload(None))

    def test_the_threshold_low_end_is_unrounded(self):
        ref = {**compute(), "gross_margin_usd": {"min": 495.0, "max": 495.0}}
        self.assertEqual(margin.email_payload(ref)["usd_min"], 500)       # the copy, to the nearest 10
        self.assertEqual(margin.threshold_low(ref), 495.0)                  # what the threshold compares
        self.assertEqual(margin.threshold_low(compute()), 1216.27)
        self.assertIsNone(margin.threshold_low(None))
        self.assertIsNone(margin.threshold_low({"gross_margin_usd": None}))
        self.assertIsNone(margin.line(None))

    def test_every_variant_is_prudent(self):
        variants = [margin.line(compute()), margin.line(compute(zones=[])),
                    margin.line(compute(row(price=15_000.0, currency="USD", price_usd=15_000.0))),
                    margin.line(compute(cost=None)), margin.line(compute(dealer={**DEALER, "transfer": False})),
                    margin.line(compute(dealer={**DEALER, "reconditioning": None})),
                    margin.line(compute(dealer={**DEALER, "reconditioning": None}, zones=[])),
                    margin.line(compute(zones=CORDOBA)), margin.line(compute(zones=CABA_AND_CORDOBA))]
        self.assertEqual(len(set(variants)), len(variants))
        for text in variants:
            with self.subTest(text=text):
                self.assertTrue(text.startswith("Margen bruto estimado: "))
                self.assertTrue(text.endswith("; sin impuestos)"))
                self.assertIn("la mediana de USD 18.000 a la que publican las agencias este modelo, n = 6", text)
                self.assertEqual(MarginCopyLint.offenders(text), [])


class MarginCopyLint(unittest.TestCase):
    """The margin is an estimate to orient a dealer (docs/BACKLOG_COMERCIAL.md):
    never a guaranteed result, a profit or a sale price."""

    TERMS = (*copy.FORBIDDEN_TERMS, "ganancia", "ganancias", "garantiz", "rentab", "asegur", "seguro que",
             "vas a ganar", "precio de venta")

    @classmethod
    def offenders(cls, text: str) -> list[str]:
        folded = normalize_text(text)
        return [t for t in cls.TERMS if normalize_text(t) in folded]

    def test_the_lint_catches_what_it_should(self):
        self.assertEqual(self.offenders("Ganancia garantizada"), ["ganancia", "garantiz"])
        self.assertEqual(self.offenders("rentabilidad asegurada"), ["rentab", "asegur"])

    def test_the_margin_block(self):
        def flat(v):
            return [v] if isinstance(v, str) else [x for i in v.values() for x in flat(i)]
        for text in flat(copy.MARGIN):
            with self.subTest(text=text):
                self.assertEqual(self.offenders(text), [])


class EvaluationTests(unittest.TestCase):
    def test_row_carries_margin_ref(self):
        self.assertIn("margin_ref", Evaluation.__dataclass_fields__)
        self.assertIsNone(Evaluation.__dataclass_fields__["margin_ref"].default)

    def test_the_scorer_fills_it_with_the_profile_s_zones(self):
        listing = fiesta_listing(price=10_300.0, price_usd=10_300.0, seller_type="private")
        profile = {**fiesta_profile(price_max=20_000), "origin_lat": -34.5875, "origin_lon": -58.42,
                   "filters": {**fiesta_profile()["filters"], "location_label": "Palermo, CABA"}}
        ref = PriceRef(n=10, level_used="model", median=11_200.0, median_km=125_000.0, diff_pct=8.0,
                       dealer_median=12_500.0, dealer_n=6, private_median=11_000.0, private_n=4)
        scorer = Scorer(IntelligenceConfig.from_app_config({}), None, datetime(2026, 11, 2, 15, tzinfo=timezone.utc),
                        rows={1: listing}, refs={1: ref}, margin_cfg=DEALER, cost_cfg=COST,
                        fx_latest={"rate": 1300.0, "kind": "blue", "date": "2026-11-02"})
        ev = scorer.evaluate(1, profile)
        self.assertIsNotNone(ev)
        self.assertEqual(ev.row()["margin_ref"]["dealer_median"], 12_500.0)
        self.assertEqual(ev.row()["margin_ref"]["transfer"]["jurisdiction"], ["caba"])
        self.assertEqual(profile_zones(profile)[0]["label"], "Palermo, CABA")
        # Without enough dealers: the row says so, with the config's min_n.
        scorer.refs[1] = PriceRef(**{**ref.__dict__, "dealer_n": 2})
        self.assertEqual(scorer.evaluate(1, profile).row()["margin_ref"]["status"], "few_dealers")
        self.assertEqual(scorer.evaluate(1, profile).row()["margin_ref"]["min_n"], scorer.cfg.min_n)


def usd_row(price_usd: float):
    return row(price=price_usd, currency="USD", price_usd=price_usd)


# The production case (PRO-02 after deploy): a VW Bora «USD 600.000», ARS loaded as USD.
BORA = PriceRef(**{**POOL.__dict__, "dealer_median": 8_038.0})
# No guard: what compute() stored before it (the refs rescore_queue recomputes).
NO_GUARD = {**DEALER, "plausible_ratio": {"min": 1e-9, "max": 1e9}}


class ImplausibleTests(unittest.TestCase):
    """asking_usd above 3x or below 0.4x the dealers' median: no margin
    (None: no line, no note, no threshold), the bounds inclusive."""

    def test_above_and_below_have_no_margin(self):
        self.assertIsNone(compute(r=usd_row(600_000.0), ref=BORA))
        self.assertIsNone(compute(r=usd_row(54_010.0)))      # 3,0006x
        self.assertIsNone(compute(r=usd_row(7_190.0)))       # 0,399x

    def test_the_bounds_are_plausible(self):
        top, bottom = compute(r=usd_row(54_000.0)), compute(r=usd_row(7_200.0))
        self.assertEqual((top["status"], top["asking_usd"], top["plausible_ratio"]), ("ok", 54_000.0, {"min": 0.4, "max": 3.0}))
        self.assertLess(top["gross_margin_usd"]["min"], 0)
        self.assertEqual(bottom["asking_usd"], 7_200.0)
        self.assertGreater(bottom["gross_margin_usd"]["min"], 0)

    def test_the_config_s_bounds(self):
        tight = {**DEALER, "plausible_ratio": {"min": 0.5, "max": 2}}
        self.assertIsNone(compute(r=usd_row(40_000.0), dealer=tight))
        self.assertIsNone(compute(r=usd_row(8_000.0), dealer=tight))
        self.assertEqual(compute(r=usd_row(36_000.0), dealer=tight)["plausible_ratio"], {"min": 0.5, "max": 2.0})
        # Without plausible_ratio (a dealer_cfg built by hand): the default.
        self.assertIsNone(compute(r=usd_row(600_000.0), ref=BORA,
                                  dealer={k: v for k, v in DEALER.items() if k != "plausible_ratio"}))

    def test_fewer_dealers_still_say_so(self):
        """The few_dealers line is true whatever the price: it stays."""
        few = compute(r=usd_row(600_000.0), ref=PriceRef(**{**BORA.__dict__, "dealer_n": 2}))
        self.assertEqual(few["status"], "few_dealers")

    def test_a_stored_ref_from_before_the_guard_is_not_shown(self):
        """The 185 stored in production: no line, no payload, no threshold,
        until rescore_queue recomputes them."""
        stored = compute(r=usd_row(600_000.0), ref=BORA, dealer=NO_GUARD)
        stored.pop("plausible_ratio")
        self.assertLess(stored["gross_margin_usd"]["min"], -600_000)   # production: USD -645.970
        self.assertFalse(margin.plausible(stored))
        self.assertIsNone(margin.email_payload(stored))
        self.assertIsNone(margin.line(stored))
        self.assertIsNone(margin.threshold_low(stored))
        low = compute(r=usd_row(5_000.0), dealer=NO_GUARD)
        low.pop("plausible_ratio")
        self.assertGreater(low["gross_margin_usd"]["min"], 10_000)
        self.assertIsNone(margin.threshold_low(low))
        self.assertIsNone(margin.email_payload(low))
        # A stored ref with bounds is checked against its own.
        own = {**compute(r=usd_row(36_000.0)), "plausible_ratio": {"min": 0.5, "max": 1.5}}
        self.assertFalse(margin.plausible(own))
        self.assertTrue(margin.plausible(compute()))
        for ref in (None, {}, compute(ref=PriceRef(**{**POOL.__dict__, "dealer_n": 2}))):
            self.assertFalse(margin.plausible(ref))


USD_ROW = usd_row(15_000.0)
# golden.json's cases: name -> compute()'s arguments.
GOLDEN_CASES = {
    "pool CABA": {},
    "sin localidad": {"zones": []},
    "AMBA": {"zones": AMBA},
    "resto del país": {"zones": CORDOBA},
    "CABA y Córdoba": {"zones": CABA_AND_CORDOBA},
    "USD sin dólar": {"r": USD_ROW},
    "sin parámetros de costo": {"cost": None},
    "transferencia desactivada": {"dealer": {**DEALER, "transfer": False}},
    "sin acondicionamiento": {"dealer": {**DEALER, "reconditioning": None}},
    "sin acondicionamiento ni localidad": {"dealer": {**DEALER, "reconditioning": None}, "zones": []},
    "negativo": {"ref": PriceRef(**{**POOL.__dict__, "dealer_median": 15_000.0})},
    "de contado": {"r": row(description_facts={"price_check": {"effective_kind": "cash"}})},
    "pocas agencias": {"ref": PriceRef(**{**POOL.__dict__, "dealer_n": 2})},
    # The bounds are plausible (inclusive).
    "en el borde de arriba (3x)": {"r": usd_row(54_000.0)},
    "en el borde de abajo (0,4x)": {"r": usd_row(7_200.0)},
}
# Implausible prices: compute() gives None; margin_ref is what it stored
# before the guard (no plausible_ratio), which neither the worker nor the web shows.
STORED_CASES = {
    "implausible: ARS cargado como USD": {"r": usd_row(600_000.0), "ref": BORA},
    "implausible: apenas arriba de 3x": {"r": usd_row(54_010.0)},
    "implausible: abajo de 0,4x": {"r": usd_row(7_190.0)},
}


def stored_before_the_guard(kw):
    ref = compute(**{**kw, "dealer": NO_GUARD})
    ref.pop("plausible_ratio")
    return ref
GOLDEN_PATH = Path(__file__).parent / "fixtures" / "margin" / "golden.json"


class GoldenTests(unittest.TestCase):
    """tests/fixtures/margin/golden.json: margin_ref -> payload and line, the
    vectors web/lib/margin-view.test.ts formats too (the web prints the same
    line). After an intended change, regenerate it with
    UPDATE_GOLDEN=1 pytest tests/test_margin.py and review the diff."""

    def test_the_vectors_are_the_calculator_s(self):
        import os
        if os.getenv("UPDATE_GOLDEN"):
            cases = []
            for name, kw in GOLDEN_CASES.items():
                ref = compute(**kw)
                cases.append({"name": name, "margin_ref": ref, "payload": margin.email_payload(ref),
                              "line": margin.line(ref)})
            for name, kw in STORED_CASES.items():
                ref = stored_before_the_guard(kw)
                cases.append({"name": name, "implausible": True, "margin_ref": ref,
                              "payload": margin.email_payload(ref), "line": margin.line(ref)})
            doc = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))["_doc"]
            GOLDEN_PATH.write_text(json.dumps({"_doc": doc, "cases": cases}, ensure_ascii=False, indent=1) + "\n",
                                   encoding="utf-8")
        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assertEqual([c["name"] for c in golden["cases"]], [*GOLDEN_CASES, *STORED_CASES])
        for case in golden["cases"]:
            with self.subTest(case["name"]):
                if case.get("implausible"):
                    kw = STORED_CASES[case["name"]]
                    self.assertIsNone(compute(**kw))
                    self.assertEqual(case["margin_ref"], stored_before_the_guard(kw))
                    self.assertIsNone(case["payload"])
                    self.assertIsNone(case["line"])
                else:
                    self.assertEqual(case["margin_ref"], compute(**GOLDEN_CASES[case["name"]]))
                self.assertEqual(margin.email_payload(case["margin_ref"]), case["payload"])
                self.assertEqual(margin.line(case["margin_ref"]), case["line"])


if __name__ == "__main__":
    unittest.main()
