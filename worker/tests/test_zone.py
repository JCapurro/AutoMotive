"""F-03 fase 0 (docs/superpowers/specs/2026-10-29-f03-market-stats-fase0-design.md):
the region of a listing from its coordinates (normalization/zone.py)."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from normalization import zone
from normalization.zone import DEFAULT_ZONE_MAP, derive_zone, nearest_locality, resolve_region

ROOT = Path(__file__).resolve().parents[2]


def region(lat, lon, text="Somewhere", source="mercadolibre"):
    facts = derive_zone(lat, lon, text, source)
    return resolve_region(DEFAULT_ZONE_MAP, facts.province_id, facts.department, facts.precision)


class LocalitiesDataTests(unittest.TestCase):
    def test_the_worker_copy_is_the_web_file(self):
        web = ROOT / "web" / "lib" / "data" / "argentina-locations.json"
        worker = ROOT / "worker" / "normalization" / "data" / "ar_localities.json"
        self.assertEqual(worker.read_bytes(), web.read_bytes())

    def test_shape(self):
        data = zone.load_localities()
        self.assertEqual(len(data.provinces), 24)
        self.assertEqual(len(data.cities), 4022)


class NearestLocalityTests(unittest.TestCase):
    def test_known_places(self):
        for (lat, lon), (name, province) in {
                (-32.9442, -60.6505): ("Rosario", "82"),
                (-34.9205, -57.9536): ("La Plata", "06"),
                (-31.4201, -64.1888): ("Córdoba", "14"),
                (-54.8019, -68.3030): ("Ushuaia", "94")}.items():
            with self.subTest(name):
                loc = nearest_locality(lat, lon)
                self.assertEqual((loc.name, loc.province_id), (name, province))
                self.assertLess(loc.dist_km, 10)

    def test_cached_by_coordinate(self):
        nearest_locality.cache_clear()
        with patch("normalization.zone.haversine_km", wraps=zone.haversine_km) as hv:
            first = nearest_locality(-34.4708, -58.5286)
            calls = hv.call_count
            second = nearest_locality(-34.4708, -58.5286)
        self.assertGreater(calls, 0)
        self.assertEqual(hv.call_count, calls)
        self.assertEqual(first, second)


class DeriveZoneTests(unittest.TestCase):
    def test_without_coordinates_there_is_no_zone(self):
        self.assertIsNone(derive_zone(None, None, "Rosario, Santa Fe", "mercadolibre"))
        self.assertIsNone(derive_zone(-32.9, None, "Rosario, Santa Fe", "mercadolibre"))

    def test_a_locality(self):
        facts = derive_zone(-32.9442, -60.6505, "Rosario, Santa Fe", "mercadolibre")
        self.assertEqual((facts.province_id, facts.department, facts.precision), ("82", "Rosario", "locality"))
        self.assertEqual(facts.locality_id, "82084270")
        self.assertEqual((facts.lat, facts.lon), (-32.9442, -60.6505))

    def test_a_province_name_alone_is_province_precision(self):
        # geo.py places "Buenos Aires" alone on CABA: it must not inflate AMBA.
        facts = derive_zone(-34.6037, -58.3816, "Buenos Aires", "facebook")
        self.assertEqual((facts.province_id, facts.precision), ("06", "province"))
        self.assertIsNone(resolve_region(DEFAULT_ZONE_MAP, facts.province_id, facts.department, facts.precision))
        # A province that is all in one region still gets it.
        facts = derive_zone(-31.4201, -64.1888, "Córdoba", "facebook")
        self.assertEqual((facts.province_id, facts.precision), ("14", "province"))
        self.assertEqual(resolve_region(DEFAULT_ZONE_MAP, "14", None, "province"), "cordoba")

    def test_argentina_has_no_province(self):
        facts = derive_zone(-38.4161, -63.6167, "Argentina", "facebook")
        self.assertEqual((facts.province_id, facts.precision), (None, "province"))
        self.assertIsNone(resolve_region(DEFAULT_ZONE_MAP, None, None, "province"))

    def test_source_default(self):
        facts = derive_zone(-32.9442, -60.6505, None, "rosariogarage")
        self.assertEqual((facts.province_id, facts.precision), ("82", "source_default"))
        self.assertEqual(resolve_region(DEFAULT_ZONE_MAP, "82", facts.department, facts.precision), "litoral")

    def test_one_case_per_region(self):
        for (lat, lon), expected in {
                (-34.6037, -58.3816): "amba",                 # CABA
                (-38.0055, -57.5426): "buenos_aires_resto",   # Mar del Plata
                (-31.4201, -64.1888): "cordoba",
                (-31.7413, -60.5115): "litoral",              # Paraná
                (-27.3621, -55.9009): "nea",                  # Posadas
                (-32.8895, -68.8458): "cuyo",                 # Mendoza
                (-26.8083, -65.2176): "noa",                  # Tucumán
                (-38.9516, -68.0591): "patagonia",            # Neuquén
                (-36.6208, -64.2906): "patagonia"}.items():   # Santa Rosa, La Pampa
            with self.subTest(expected, lat=lat):
                self.assertEqual(region(lat, lon), expected)

    def test_amba_limits(self):
        for (lat, lon), expected in {
                (-34.4708, -58.5286): "amba",                 # San Isidro
                (-34.4587, -58.9142): "buenos_aires_resto",   # Pilar
                (-34.9205, -57.9536): "buenos_aires_resto",   # La Plata
                (-34.3494, -58.7916): "buenos_aires_resto"}.items():  # Escobar
            with self.subTest(expected, lat=lat):
                self.assertEqual(region(lat, lon), expected)


if __name__ == "__main__":
    unittest.main()
