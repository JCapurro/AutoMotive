from __future__ import annotations

import unittest

from intelligence import matching
from intelligence.matching import FAIL, OK

CORRIENTES = {"label": "Corrientes", "lat": -27.4698, "lon": -58.8306, "radius_km": 30}
RESISTENCIA = {"label": "Resistencia", "lat": -27.4519, "lon": -58.9867, "radius_km": 40}
SAENZ_PENA = {"label": "Presidencia Roque Sáenz Peña", "lat": -26.7852, "lon": -60.4388, "radius_km": 30}
CORDOBA = (-31.4201, -64.1888)


def _profile(*extra, primary=CORRIENTES):
    return {
        "origin_lat": primary["lat"], "origin_lon": primary["lon"], "radius_km": primary["radius_km"],
        "filters": {"extra_locations": list(extra)} if extra else {},
    }


def _listing(lat, lon, text="Algún lugar"):
    return {"lat": lat, "lon": lon, "location_text": text}


class SearchZonesTests(unittest.TestCase):
    def test_a_search_without_extras_has_its_own_zone_only(self):
        self.assertEqual(len(matching.search_zones(_profile())), 1)

    def test_extras_add_zones_and_malformed_ones_are_ignored(self):
        profile = _profile(SAENZ_PENA, {"label": "roto"}, {**RESISTENCIA, "radius_km": 0})
        self.assertEqual(len(matching.search_zones(profile)), 2)

    def test_no_place_no_zones(self):
        self.assertEqual(matching.search_zones({"filters": {}}), [])
        self.assertIsNone(matching._location(_listing(*CORDOBA), {"filters": {}}))


class LocationAnyOfTests(unittest.TestCase):
    def test_a_listing_in_an_extra_zone_qualifies(self):
        profile = _profile(SAENZ_PENA)
        # Corrientes is 250 km from Sáenz Peña: only the added zone has it.
        reason = matching._location(_listing(SAENZ_PENA["lat"], SAENZ_PENA["lon"]), profile)
        self.assertEqual(reason.result, OK)

    def test_the_same_listing_fails_without_the_extra_zone(self):
        reason = matching._location(_listing(SAENZ_PENA["lat"], SAENZ_PENA["lon"]), _profile())
        self.assertEqual(reason.result, FAIL)

    def test_a_listing_outside_every_zone_fails_against_the_nearest(self):
        profile = _profile(SAENZ_PENA)
        reason = matching._location(_listing(*CORDOBA), profile)
        self.assertEqual(reason.result, FAIL)

    def test_a_listing_without_coordinates_fails_when_the_search_has_zones(self):
        reason = matching._location(_listing(None, None), _profile(SAENZ_PENA))
        self.assertEqual(reason.result, FAIL)

    def test_distance_is_to_the_closest_zone(self):
        near = matching.distance_km(_listing(SAENZ_PENA["lat"], SAENZ_PENA["lon"]), _profile(SAENZ_PENA))
        self.assertLess(near, 1)


if __name__ == "__main__":
    unittest.main()
