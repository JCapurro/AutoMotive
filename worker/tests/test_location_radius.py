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

    def test_cuyo_departments_do_not_resolve_to_their_namesakes(self):
        # deRuedas locates ads as "<departamento>, <provincia>". Luján, Junín,
        # San Martín and Santa Rosa are also towns about 1000 km from Cuyo.
        mendoza, san_juan = (-32.8895, -68.8458), (-31.5375, -68.5364)
        for name in ("Luján De Cuyo, Mendoza", "Junín, Mendoza", "San Martín, Mendoza",
                     "Santa Rosa, Mendoza", "Maipú, Mendoza", "Las Heras, Mendoza",
                     "Rivadavia, Mendoza", "Godoy Cruz, Mendoza", "Capital, Mendoza"):
            coords = _lookup_known_location(name)
            self.assertIsNotNone(coords, name)
            self.assertLess(haversine_km(*coords, *mendoza), 100, name)
        for name in ("San Martín, San Juan", "Rawson, San Juan", "Rivadavia, San Juan",
                     "Capital, San Juan"):
            coords = _lookup_known_location(name)
            self.assertIsNotNone(coords, name)
            self.assertLess(haversine_km(*coords, *san_juan), 30, name)
        self.assertEqual(_lookup_known_location("Capital, San Luis"), _lookup_known_location("San Luis"))
        self.assertEqual(_lookup_known_location("Capital, Córdoba"), _lookup_known_location("Córdoba"))
        self.assertLess(haversine_km(*_lookup_known_location("Junín, San Luis"), -33.3017, -66.3378), 160)
        san_martin_sl = _lookup_known_location("San Martín, San Luis")
        self.assertLess(haversine_km(*san_martin_sl, -33.3017, -66.3378), 150)
        self.assertGreater(haversine_km(*san_martin_sl, -34.5763, -58.5364), 500)

    def test_cordoba_and_santa_fe_departments_named_like_gba_towns(self):
        # Department seats: San Francisco, Villa María, San Justo and Sastre.
        for name, seat in (("San Justo, Córdoba", (-31.4278, -62.0828)),
                           ("General San Martín, Córdoba", (-32.4075, -63.2402)),
                           ("San Justo, Santa Fe", (-30.7891, -60.5919)),
                           ("San Martín, Santa Fe", (-31.7676, -61.8285))):
            coords = _lookup_known_location(name)
            self.assertIsNotNone(coords, name)
            self.assertLess(haversine_km(*coords, *seat), 20, name)
        self.assertEqual(_lookup_known_location("San Justo - GBA Oeste"), (-34.6764, -58.5614))
        self.assertEqual(_lookup_known_location("San Martín - GBA Norte"), (-34.5763, -58.5364))

    def test_namesakes_outside_cuyo_keep_their_coordinates(self):
        self.assertEqual(_lookup_known_location("Luján, Buenos Aires"), (-34.5703, -59.1051))
        self.assertEqual(_lookup_known_location("Junín - Bs.As. Interior"), (-34.5934, -60.9486))
        self.assertEqual(_lookup_known_location("San Martín - GBA Norte"), (-34.5763, -58.5364))
        self.assertEqual(_lookup_known_location("Santa Rosa, La Pampa"), (-36.6208, -64.2906))
        self.assertEqual(_lookup_known_location("Mendoza"), (-32.8895, -68.8458))
        # Ambiguous or unknown places still go to the geocoder instead of a guess.
        self.assertIsNone(_lookup_known_location("General Las Heras, Buenos Aires"))
        self.assertIsNone(_lookup_known_location("Capital, Buenos Aires"))


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
