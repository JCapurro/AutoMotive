"""Normalization v2, change detection and crawl-target derivation — pure, no network or DB."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone

from collectors.base import Listing
from normalization import transmission as tx
from normalization.fx import FxQuote
from normalization.listing import Target, fingerprint, normalize_listing, price_usd
from normalization.vehicle import CatalogModel, resolve_vehicle
from pipeline.crawl import TargetSpec, derive_targets, scraper_filters
from pipeline.ingest import merge, price_drop_pct

CATALOG = [
    CatalogModel("Ford", "Fiesta", ("fiesta kinetic", "fiesta kinetic design"), ("S", "SE", "SEL", "Titanium", "ST"), None, 2019),
    CatalogModel("Ford", "Ka", ("ka+",), ("S", "SE", "SEL")),
    CatalogModel("Ford", "EcoSport", ("eco sport",), ("S", "SE", "Titanium")),
    CatalogModel("Toyota", "Corolla", (), ("XLI", "XEI", "SEG")),
    CatalogModel("Toyota", "Corolla Cross", ("corollacross",), ("XLI", "XEI", "SEG")),
    CatalogModel("Volkswagen", "Gol", ("gol power",)),
    CatalogModel("Volkswagen", "Gol Trend", ("goltrend",), ("Trendline", "Highline", "Pack I", "Pack II")),
    CatalogModel("Peugeot", "2008", (), ("Allure", "Feline")),
]


class VehicleResolutionTests(unittest.TestCase):
    def test_title_wins_over_the_search_target(self):
        # MercadoLibre returns other models for "Ford Fiesta"; F0 copied the filter.
        m = resolve_vehicle(CATALOG, title="Ford Ka 1.5 SEL 2019", target_make="Ford", target_model="Fiesta")
        self.assertEqual((m.make, m.model, m.trim, m.method), ("Ford", "Ka", "SEL", "title"))

    def test_longest_name_wins_and_trims_resolve(self):
        m = resolve_vehicle(CATALOG, title="Toyota Corolla Cross 1.8 Hev Seg Ecvt")
        self.assertEqual((m.model, m.trim), ("Corolla Cross", "SEG"))
        m = resolve_vehicle(CATALOG, title="VW Gol Trend Pack II 1.6")
        self.assertEqual((m.make, m.model, m.trim), ("Volkswagen", "Gol Trend", "Pack II"))

    def test_alias_and_model_without_brand(self):
        m = resolve_vehicle(CATALOG, title="Fiesta Kinetic Design Titanium 1.6")
        self.assertEqual((m.make, m.model, m.trim, m.method), ("Ford", "Fiesta", "Titanium", "title_model"))

    def test_structured_values_are_trusted_first(self):
        m = resolve_vehicle(CATALOG, title="Auto impecable", source_make="Ford",
                            source_model="Fiesta Kinetic Design", source_version="1.6 S PLUS")
        self.assertEqual((m.make, m.model, m.trim, m.confidence), ("Ford", "Fiesta", "S", 0.95))

    def test_typos_resolve_fuzzily_with_lower_confidence(self):
        m = resolve_vehicle(CATALOG, title="Toyota Corola XEI 2019")
        self.assertEqual((m.model, m.trim, m.method), ("Corolla", "XEI", "fuzzy"))
        self.assertLess(m.confidence, 0.9)

    def test_a_year_is_not_a_peugeot_2008(self):
        m = resolve_vehicle(CATALOG, title="Gol 2008 5 puertas")
        self.assertEqual(m.model, "Gol")
        m = resolve_vehicle(CATALOG, title="Peugeot 2008 Allure 2019")
        self.assertEqual((m.model, m.trim), ("2008", "Allure"))

    def test_unresolved_falls_back_to_the_target_with_low_confidence(self):
        m = resolve_vehicle(CATALOG, title="Oportunidad única, papeles al día",
                            target_make="Ford", target_model="Fiesta")
        self.assertEqual((m.make, m.model, m.method), ("Ford", "Fiesta", "target"))
        self.assertLess(m.confidence, 0.5)

    def test_out_of_production_years_lower_confidence(self):
        ok = resolve_vehicle(CATALOG, title="Ford Fiesta 2017", year=2017)
        odd = resolve_vehicle(CATALOG, title="Ford Fiesta 2024", year=2024)
        self.assertGreater(ok.confidence, odd.confidence)


class TransmissionFuelSellerTests(unittest.TestCase):
    def test_transmission(self):
        for text in ("Manual", "MT", "6MT", "S 1.6 MT 5P", "caja manual 5 velocidades", "m/t"):
            self.assertEqual(tx.transmission(text), "manual", text)
        for text in ("AT", "Automática", "1.8 Hev Xei Ecvt", "CVT", "2.0 Tiptronic", "1.5 SEL Aut",
                     "Titanium 1.6 At 5p", "Powershift", "DSG"):
            self.assertEqual(tx.transmission(text), "automatic", text)
        self.assertIsNone(tx.transmission("Ford Fiesta Titanium"))
        self.assertIsNone(tx.transmission("estado mecánico impecable"))
        self.assertIsNone(tx.transmission("manual o automática"))      # ambiguous: no guess

    def test_structured_value_is_trusted_before_the_title(self):
        self.assertEqual(tx.transmission("Automática", "Fiesta 1.6 MT"), "automatic")
        self.assertEqual(tx.transmission(None, "Fiesta 1.6 MT"), "manual")

    def test_fuel(self):
        cases = {"Nafta": "nafta", "Híbrido": "hibrido", "1.8 HEV": "hibrido", "GNC": "gnc",
                 "nafta/gnc": "gnc", "2.0 TDI": "diesel", "Diésel": "diesel", "Eléctrico": "electrico"}
        for text, expected in cases.items():
            self.assertEqual(tx.fuel(text), expected, text)
        self.assertIsNone(tx.fuel("Ford Fiesta"))

    def test_seller_type(self):
        self.assertEqual(tx.seller_type("Particular"), "private")
        self.assertEqual(tx.seller_type("concesionaria"), "dealer")
        self.assertEqual(tx.seller_type("Tienda oficial"), "dealer")
        self.assertIsNone(tx.seller_type("?"))


def _item(**kw) -> Listing:
    base = dict(source="mercadolibre", listing_id="MLA1", titulo="Ford Fiesta Titanium 1.6 MT",
                url="https://example.test/MLA1", precio=10_300.0, moneda="USD", anio=2017,
                km=112_000, ubicacion="Vicente López")
    base.update(kw)
    return Listing(**base)


class NormalizeListingTests(unittest.TestCase):
    FX = FxQuote(1_000.0, "blue", "test")

    def test_row(self):
        row = normalize_listing(_item(published_at=1_700_000_000), catalog=CATALOG,
                                target=Target("Ford", "Fiesta"), fx=self.FX)
        self.assertEqual((row["make"], row["model"], row["trim"]), ("Ford", "Fiesta", "Titanium"))
        self.assertEqual((row["transmission"], row["price_usd"], row["currency"]), ("manual", 10_300.0, "USD"))
        self.assertEqual(row["published_at"], datetime.fromtimestamp(1_700_000_000, tz=timezone.utc))
        self.assertEqual(row["attributes"]["_normalization"]["method"], "title")
        self.assertIsNotNone(row["fingerprint"])

    def test_ars_prices_convert_and_odd_currencies_stay_in_attributes(self):
        ars = normalize_listing(_item(precio=11_490_000.0, moneda="ARS"), catalog=CATALOG, fx=self.FX)
        self.assertEqual((ars["price_usd"], ars["fx_rate"]), (11_490.0, 1_000.0))
        odd = normalize_listing(_item(moneda="EUR"), catalog=CATALOG, fx=self.FX)
        self.assertEqual((odd["currency"], odd["price_usd"], odd["attributes"]["moneda"]), (None, None, "EUR"))
        self.assertEqual(normalize_listing(_item(moneda="U$S"), catalog=CATALOG)["currency"], "USD")

    def test_price_usd(self):
        self.assertIsNone(price_usd(None, "USD", self.FX))
        self.assertIsNone(price_usd(5_000_000, "ARS", None))

    def test_fingerprint_rounds_km_and_ignores_spelling(self):
        a = {"make": "Ford", "model": "Fiesta", "year": 2017, "mileage_km": 112_300,
             "seller_name": "Juan  Pérez", "location_text": "Vicente López, Bs. As."}
        b = dict(a, mileage_km=111_800, seller_name="juan perez", location_text="vicente lopez bs as")
        self.assertEqual(fingerprint(a), fingerprint(b))
        self.assertNotEqual(fingerprint(a), fingerprint(dict(a, year=2018)))
        self.assertIsNone(fingerprint(dict(a, mileage_km=None)))


def _stored(**kw) -> dict:
    row = {"id": 1, "source": "mercadolibre", "external_id": "MLA1", "url": "u",
           "title": "Ford Fiesta Titanium", "description": None, "make": "Ford", "model": "Fiesta",
           "trim": "Titanium", "year": 2017, "price": 10_300.0, "currency": "USD",
           "price_usd": 10_300.0, "mileage_km": 112_000, "transmission": "manual", "fuel": None,
           "location_text": "Vicente López", "lat": None, "lon": None, "seller_name": None,
           "seller_type": None, "images": ["a.jpg"], "attributes": {}, "published_at": None,
           "price_partial": False, "price_partial_reason": None, "normalization_confidence": 0.9,
           "enriched_at": None, "probable_repost_of": None}
    row.update(kw)
    return row


class MergeTests(unittest.TestCase):
    def test_same_card_again_changes_nothing(self):
        old = _stored()
        new = {k: v for k, v in old.items() if k not in ("id", "enriched_at", "probable_repost_of")}
        _, changes = merge(old, new, detail=False)
        self.assertEqual(changes, [])

    def test_price_and_mileage(self):
        values, changes = merge(_stored(), dict(_stored(), price=9_900.0, price_usd=9_900.0,
                                                 mileage_km=113_000), detail=False)
        self.assertEqual(changes, ["price", "mileage"])
        self.assertEqual((values["price"], values["mileage_km"]), (9_900.0, 113_000))

    def test_missing_values_never_erase_stored_ones(self):
        values, changes = merge(_stored(description="Único dueño"),
                                dict(_stored(), price=None, mileage_km=None, description=None,
                                     transmission=None), detail=False)
        self.assertEqual(changes, [])
        self.assertEqual((values["price"], values["transmission"], values["description"]),
                         (10_300.0, "manual", "Único dueño"))

    def test_price_usd_stays_frozen_while_the_price_does(self):
        old = _stored(price=11_490_000.0, currency="ARS", price_usd=7_660.0)
        values, changes = merge(old, dict(old, price_usd=7_400.0), detail=False)
        self.assertEqual((changes, values["price_usd"]), ([], 7_660.0))

    def test_enrichment_fills_detail_and_cards_dont_undo_it(self):
        old = _stored()
        detail = dict(old, title="Ford Fiesta Titanium Hatchback", description="Services oficiales",
                      images=["1.jpg", "2.jpg", "3.jpg"], seller_type="private")
        values, changes = merge(old, detail, detail=True)
        self.assertEqual(changes, ["description", "images", "attrs"])

        enriched = dict(old, **values, enriched_at=datetime.now(timezone.utc))
        card = dict(old, price=9_800.0, price_usd=9_800.0)       # the card's own title/images
        values, changes = merge(enriched, card, detail=False)
        self.assertEqual(changes, ["price"])
        self.assertEqual((values["title"], len(values["images"])), ("Ford Fiesta Titanium Hatchback", 3))

    def test_better_resolved_make_model_is_kept(self):
        old = _stored(make="Ford", model="Fiesta", normalization_confidence=0.95)
        values, _ = merge(old, dict(old, make="Ford", model="Ka", trim=None,
                                    normalization_confidence=0.4), detail=False)
        self.assertEqual(values["model"], "Fiesta")

    def test_price_drop_in_the_listing_currency(self):
        self.assertEqual(price_drop_pct({"price": 10_000, "currency": "USD"},
                                        {"price": 9_500, "currency": "USD"}), 5.0)
        self.assertIsNone(price_drop_pct({"price": 10_000, "currency": "USD"},
                                         {"price": 10_500, "currency": "USD"}))
        # The dollar moved but the ARS price didn't fall: not a drop.
        self.assertIsNone(price_drop_pct({"price": 11_000_000, "currency": "ARS", "price_usd": 8_000},
                                         {"price": 11_200_000, "currency": "ARS", "price_usd": 7_500}))
        # Currency changed: compared in USD.
        self.assertEqual(price_drop_pct({"price": 11_000_000, "currency": "ARS", "price_usd": 10_000},
                                        {"price": 9_000, "currency": "USD", "price_usd": 9_000}), 10.0)


class CrawlTargetTests(unittest.TestCase):
    SOURCES = ["mercadolibre", "kavak"]

    def _profile(self, pid: int, **filters) -> dict:
        f = {"make": "Ford", "model": "Fiesta"}
        f.update(filters)
        return {"id": pid, "filters": f, "origin_lat": None, "origin_lon": None}

    def test_profiles_of_the_same_model_share_targets_with_the_widest_query(self):
        specs = derive_targets([
            self._profile(1, year_min=2016, year_max=2018, km_max=150_000, price_max=11_500),
            self._profile(2, year_min=2014, year_max=2017, km_max=120_000),
        ], self.SOURCES)

        self.assertEqual([(s.source, s.make, s.model) for s in specs],
                         [("kavak", "Ford", "Fiesta"), ("mercadolibre", "Ford", "Fiesta")])
        self.assertEqual(specs[0].query, {"year_min": 2014, "year_max": 2018, "km_max": 150_000,
                                          "profile_ids": [1, 2]})

    def test_a_repeated_profile_adds_no_target(self):
        one = derive_targets([self._profile(1)], self.SOURCES)
        two = derive_targets([self._profile(1), self._profile(2, model="fiesta")], self.SOURCES)
        self.assertEqual(one, two)          # TargetSpec equality ignores the query

    def test_an_unbounded_profile_widens_to_no_bound_and_sources_are_respected(self):
        specs = derive_targets([self._profile(1, km_max=100_000, sources=["kavak", "facebook"]),
                                self._profile(2, sources=["kavak"])], self.SOURCES)
        self.assertEqual([s.source for s in specs], ["kavak"])
        self.assertNotIn("km_max", specs[0].query)

    def test_profiles_without_a_vehicle_are_not_crawled(self):
        self.assertEqual(derive_targets([{"id": 1, "filters": {"year_min": 2015}}], self.SOURCES), [])

    def test_scraper_filters_carry_no_price(self):
        f = scraper_filters({"make": "Ford", "model": "Fiesta",
                             "query": {"year_min": 2014, "km_max": 150_000, "origin_lat": -34.6,
                                       "origin_lon": -58.4}})
        self.assertEqual(f, {"marca": "Ford", "modelo": "Fiesta", "anio_min": 2014, "km_max": 150_000,
                             "origin_lat": -34.6, "origin_lon": -58.4})
        self.assertEqual(TargetSpec("kavak", "Ford", "Fiesta", {"a": 1}),
                         TargetSpec("kavak", "Ford", "Fiesta", {"b": 2}))


if __name__ == "__main__":
    unittest.main()
