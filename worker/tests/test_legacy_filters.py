from __future__ import annotations

import unittest

from db.legacy_filters import split_vehicles, to_legacy, to_profile
from db.repos.catalog import CatalogModel, match_model


# The shape of a real alert created with the Telegram wizard.
WIZARD_ALERT = {
    "sources": ["facebook", "kavak", "mercadolibre", "v6"],
    "marcas": ["Ford"],
    "modelos": ["Fiesta"],
    "version": "Titanium",
    "anios": [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026],
    "km_min": 70000,
    "km_max": 160000,
    "moneda": "USD",
    "combustible": "Nafta",
    "transmision": "Manual",
    "vendedor": "particular",
    "origin_lat": -34.468321,
    "origin_lon": -58.521686,
    "radio_km": 12.0,
    "descuento_pct": 10.0,
}


def _round_trip(legacy: dict, make: str | None, model: str | None) -> dict:
    values = to_profile(legacy, make, model)
    return to_legacy(values["filters"], values["preferences"], values["origin_lat"],
                     values["origin_lon"], values["radius_km"])


class LegacyFilterTests(unittest.TestCase):
    def test_wizard_alert_round_trips_without_loss(self):
        self.assertEqual(_round_trip(WIZARD_ALERT, "Ford", "Fiesta"), WIZARD_ALERT)

    def test_profile_uses_the_plan_filter_shape(self):
        values = to_profile(WIZARD_ALERT, "Ford", "Fiesta")
        f = values["filters"]

        self.assertEqual((f["make"], f["model"]), ("Ford", "Fiesta"))
        self.assertEqual(f["trims"], ["Titanium"])
        self.assertFalse(f["trim_strict"])
        self.assertEqual((f["year_min"], f["year_max"]), (2018, 2026))
        self.assertEqual(f["transmission"], "manual")
        self.assertEqual(f["currency"], "USD")
        self.assertEqual(values["preferences"]["seller_type"], "private")
        self.assertEqual(values["preferences"]["legacy_opportunity"], {"discount_pct": 10.0})
        self.assertEqual(values["radius_km"], 12.0)

    def test_multi_model_alert_splits_into_one_vehicle_each(self):
        legacy = {"marcas": ["Ford", "Volkswagen"], "modelos": ["Fiesta", "Gol Trend"]}

        self.assertEqual(split_vehicles(legacy), [
            ("Ford", "Fiesta"), ("Ford", "Gol Trend"),
            ("Volkswagen", "Fiesta"), ("Volkswagen", "Gol Trend"),
        ])
        self.assertEqual(split_vehicles({}), [(None, None)])
        self.assertEqual(split_vehicles({"marca": "Toyota"}), [("Toyota", None)])

    def test_unknown_and_free_text_values_are_preserved(self):
        legacy = {"marcas": ["Ford"], "modelos": ["Ka"], "transmision": "CVT",
                  "vendedor": "agencia", "ubicacion": "CABA", "anio_min": 2015,
                  "precio_max_oportunidad": 9000.0}

        self.assertEqual(_round_trip(legacy, "Ford", "Ka"), legacy)

    def test_automatic_transmission_maps_both_ways(self):
        values = to_profile({"transmision": "Automática"}, "Toyota", "Corolla")
        self.assertEqual(values["filters"]["transmission"], "automatic")
        self.assertEqual(to_legacy(values["filters"], values["preferences"])["transmision"], "Automática")


CATALOG = [
    CatalogModel("Volkswagen", "Gol", ("gol power",)),
    CatalogModel("Volkswagen", "Gol Trend", ("goltrend",)),
    CatalogModel("Ford", "Fiesta", ("fiesta kinetic", "fiesta max")),
    CatalogModel("Toyota", "Corolla", ()),
    CatalogModel("Toyota", "Corolla Cross", ()),
    CatalogModel("Mercedes-Benz", "Sprinter", ()),
    CatalogModel("Peugeot", "208", ()),
]


class CatalogMatchTests(unittest.TestCase):
    def test_canonical_names_ignoring_case_accents_and_brand_aliases(self):
        self.assertEqual(match_model(CATALOG, "ford", "FIESTA"), ("Ford", "Fiesta"))
        self.assertEqual(match_model(CATALOG, "VW", "gol trend"), ("Volkswagen", "Gol Trend"))
        self.assertEqual(match_model(CATALOG, "Mercedes", "sprinter"), ("Mercedes-Benz", "Sprinter"))

    def test_longest_name_wins_and_trims_are_ignored(self):
        self.assertEqual(match_model(CATALOG, "Volkswagen", "Gol Trend Highline"),
                         ("Volkswagen", "Gol Trend"))
        self.assertEqual(match_model(CATALOG, "Toyota", "Corolla Cross XEI"), ("Toyota", "Corolla Cross"))
        self.assertEqual(match_model(CATALOG, "Ford", "Fiesta Kinetic Design"), ("Ford", "Fiesta"))

    def test_unknown_vehicles_do_not_resolve(self):
        self.assertIsNone(match_model(CATALOG, "Ford", "Mondeo"))
        self.assertIsNone(match_model(CATALOG, "Tesla", "Model 3"))
        self.assertIsNone(match_model(CATALOG, "Ford", "Fiestas"))

    def test_make_only_and_model_only(self):
        self.assertEqual(match_model(CATALOG, "peugeot", None), ("Peugeot", None))
        self.assertEqual(match_model(CATALOG, None, "208"), ("Peugeot", "208"))


if __name__ == "__main__":
    unittest.main()
