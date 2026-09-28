from __future__ import annotations

import unittest
from unittest import mock

from normalization.geo import (
    filter_listings_by_radius,
    geocode_location,
    haversine_km,
    _lookup_known_location,
)
from collectors.base import Listing


class LocationRadiusTests(unittest.IsolatedAsyncioTestCase):
    def test_haversine_distance_is_in_kilometers(self):
        buenos_aires = (-34.6037, -58.3816)
        la_plata = (-34.9205, -57.9536)

        self.assertAlmostEqual(haversine_km(*buenos_aires, *buenos_aires), 0.0, places=3)
        self.assertTrue(45 <= haversine_km(*buenos_aires, *la_plata) <= 70)

    async def test_filter_by_radius_keeps_only_geocoded_listings_inside_radius(self):
        listings = [
            Listing(source="test", listing_id="1", titulo="Auto en La Plata", url="u1", ubicacion="La Plata"),
            Listing(source="test", listing_id="2", titulo="Auto en Cordoba", url="u2", ubicacion="Cordoba"),
            Listing(source="test", listing_id="3", titulo="Auto sin ubicacion", url="u3", ubicacion=None),
            Listing(source="test", listing_id="4", titulo="Auto desconocido", url="u4", ubicacion="Villa Inventada"),
        ]
        filters = {
            "origin_lat": -34.6037,
            "origin_lon": -58.3816,
            "radio_km": 75,
        }
        coords = {
            "La Plata": (-34.9205, -57.9536),
            "Cordoba": (-31.4201, -64.1888),
        }

        async def fake_geocode(location: str):
            return coords.get(location)

        kept = await filter_listings_by_radius(listings, filters, geocode_fn=fake_geocode)

        self.assertEqual([item.listing_id for item in kept], ["1"])

    async def test_filter_by_radius_keeps_kavak_listings_without_location(self):
        listings = [
            Listing(source="kavak", listing_id="k1", titulo="Kavak sin ubicacion", url="u1", ubicacion=None),
            Listing(source="test", listing_id="x1", titulo="Otro sin ubicacion", url="u2", ubicacion=None),
        ]
        filters = {
            "origin_lat": -34.6037,
            "origin_lon": -58.3816,
            "radio_km": 75,
        }

        kept = await filter_listings_by_radius(listings, filters)

        self.assertEqual([item.listing_id for item in kept], ["k1"])


class LocationLookupTests(unittest.TestCase):
    def test_unknown_buenos_aires_interior_city_does_not_fallback_to_caba(self):
        self.assertIsNone(_lookup_known_location("General Villegas - Bs.As. Interior"))

    def test_caba_aliases_resolve_to_caba(self):
        caba = (-34.6037, -58.3816)

        self.assertEqual(_lookup_known_location("Capital Federal"), caba)
        self.assertEqual(_lookup_known_location("CABA"), caba)

    def test_specific_city_beats_province_fallback(self):
        # "Munro - Bs.As." normalizes to "munro buenos aires"; both keys
        # match but the specific Munro coords should win over CABA's.
        coords = _lookup_known_location("Munro - Bs.As.")
        assert coords is not None
        # Munro is around (-34.527, -58.522); CABA is (-34.604, -58.382).
        self.assertAlmostEqual(coords[0], -34.5273, places=2)
        self.assertAlmostEqual(coords[1], -58.5224, places=2)

    def test_gba_cities_resolve_locally_without_nominatim(self):
        # These are the cities that previously fell to Nominatim and got
        # 429-rate-limited.
        for name in ("ituzaingo", "castelar", "adrogue", "bernal",
                     "munro", "bella vista", "rafaela"):
            self.assertIsNotNone(_lookup_known_location(name),
                                 f"{name!r} should resolve locally")


class GeocodeNegativeCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_vehicle_noise_is_not_sent_to_nominatim(self):
        for value in ("115 mil km", "2021 Chevrolet Onix LT economico oportunidad"):
            with self.subTest(value=value), \
                 mock.patch("normalization.geo._lookup_known_location", return_value=None), \
                 mock.patch("normalization.geo.db.get_geocode_cache", return_value=None) as get_pos, \
                 mock.patch("normalization.geo.db.has_fresh_geocode_failure", return_value=False) as neg_check, \
                 mock.patch("normalization.geo._geocode_nominatim", return_value=None) as nominatim:
                result = await geocode_location(value)

                self.assertIsNone(result)
                get_pos.assert_not_called()
                neg_check.assert_not_called()
                nominatim.assert_not_called()

    async def test_negative_cache_prevents_repeated_nominatim_calls(self):
        with mock.patch("normalization.geo._lookup_known_location", return_value=None), \
             mock.patch("normalization.geo.db.get_geocode_cache", return_value=None) as get_pos, \
             mock.patch("normalization.geo.db.has_fresh_geocode_failure", return_value=True) as neg_check, \
             mock.patch("normalization.geo._geocode_nominatim") as nominatim:
            result = await geocode_location("villa inventada xyz")
            self.assertIsNone(result)
            neg_check.assert_called_once()
            nominatim.assert_not_called()
            get_pos.assert_called_once()


if __name__ == "__main__":
    unittest.main()
