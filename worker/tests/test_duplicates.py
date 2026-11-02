"""PAR-02 resto: which listings look like the same car (intelligence/duplicates.py),
with built rows: the same photos in two sources, the same photos with other
data, data only (shadow), and every guard."""
from __future__ import annotations

import unittest

from intelligence.config import risk
from intelligence.duplicates import common_hashes, detect, rows_out

CFG = risk(None)
ON = risk({"signals": {"cross_source_data": "on"}})

H1 = "ac53862cd38c73d3"          # the hashes of tests/photo_fixtures.draw("a"/"b"/"c")
H1_NEAR = "ac53862cd38c73d0"     # 2 bits away: a re-compressed copy
H2 = "883ce1877cc17dc5"
H3 = "e0f3d9c27173e842"
ROSARIO = {"province_id": "82", "department": "Rosario", "precision": "locality", "lat": -32.95, "lon": -60.66}
FUNES = {"province_id": "82", "department": "Rosario", "precision": "locality", "lat": -32.92, "lon": -60.81}
CORDOBA = {"province_id": "14", "department": "Capital", "precision": "locality", "lat": -31.42, "lon": -64.18}


def row(id, source, **kw):
    out = {"id": id, "source": source, "year": 2017, "mileage_km": 90_000, "price_usd": 12_000.0,
           "price_partial": False, "probable_repost_of": None, "trim": "Titanium", "transmission": "manual",
           "fuel": "nafta", "seller_type": "private", "dealer_inferred": False, "seller_key": f"seller-{id}",
           "zone": ROSARIO, "hashes": []}
    out.update(kw)
    return out


def kinds(rows, cfg=CFG):
    return {(p.a, p.b): p.kind for p in detect(rows, cfg)}


class PhotoLevelTests(unittest.TestCase):
    def test_same_photos_and_data_in_two_sources_is_the_photos_level_not_duplicate_photos(self):
        got = detect([row(1, "mercadolibre", hashes=[H2, H1]), row(2, "rosariogarage", hashes=[H1_NEAR],
                                                                       mileage_km=91_000, price_usd=12_300.0)], CFG)
        self.assertEqual([(p.a, p.b, p.kind, p.distance) for p in got], [(1, 2, "cross_source_photos", 2)])
        self.assertEqual(got[0].evidence["matched"], [[1, 0, 2]])

    def test_the_photos_level_needs_no_place(self):
        got = kinds([row(1, "mercadolibre", hashes=[H1], zone=None), row(2, "v6", hashes=[H1], zone=CORDOBA)])
        self.assertEqual(got, {(1, 2): "cross_source_photos"})

    def test_same_photos_with_a_price_20_pct_apart_is_duplicate_photos_on_both(self):
        got = detect([row(1, "mercadolibre", hashes=[H1]), row(2, "v6", hashes=[H1], price_usd=9_600.0)], CFG)
        self.assertEqual([(p.a, p.b, p.kind) for p in got], [(1, 2, "duplicate_photos")])
        out = rows_out(got, CFG)
        self.assertEqual(set(out), {(1, 2), (2, 1)})
        self.assertTrue(all(r["shown"] and r["kind"] == "duplicate_photos" for r in out.values()))

    def test_another_year_or_km_is_still_duplicate_photos(self):
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1]), row(2, "v6", hashes=[H1], year=2015)]),
                         {(1, 2): "duplicate_photos"})

    def test_same_source_same_zone_is_a_repost_not_a_duplicate(self):
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1]),
                                row(2, "mercadolibre", hashes=[H1], zone=FUNES, price_usd=9_000.0)]), {})

    def test_same_source_another_zone_is_duplicate_photos(self):
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1]),
                                row(2, "mercadolibre", hashes=[H1], zone=CORDOBA)]), {(1, 2): "duplicate_photos"})

    def test_same_source_without_a_fine_zone_says_nothing(self):
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1]), row(2, "mercadolibre", hashes=[H1], zone=None)]),
                         {})

    def test_a_repost_or_the_same_seller_is_not_a_duplicate(self):
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1]),
                                row(2, "mercadolibre", hashes=[H1], zone=CORDOBA, probable_repost_of=1)]), {})
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1], seller_key="ana"),
                                row(2, "mercadolibre", hashes=[H1], zone=CORDOBA, seller_key="ana")]), {})

    def test_a_photo_three_sellers_share_is_common_and_counts_for_nothing(self):
        rows = [row(1, "mercadolibre", hashes=[H1]), row(2, "v6", hashes=[H1], price_usd=9_000.0),
                row(3, "rosariogarage", hashes=[H1_NEAR], price_usd=8_000.0)]
        self.assertEqual(common_hashes(rows, 6, 3), {H1, H1_NEAR})
        self.assertEqual(kinds(rows), {})
        # With a real shared photo besides the catalog one, the pair is found.
        rows[0]["hashes"], rows[1]["hashes"] = [H1, H3], [H1, H3]
        self.assertEqual(kinds(rows), {(1, 2): "duplicate_photos"})

    def test_different_photos_or_flat_hashes_match_nothing(self):
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1]), row(2, "v6", hashes=[H2], price_usd=9_000.0)]),
                         {})
        flat = "0000000000000001"
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[flat]), row(2, "v6", hashes=[flat],
                                                                          price_usd=9_000.0)]), {})

    def test_a_tighter_distance_drops_the_near_copy(self):
        tight = risk({"phash_max_distance": 1})
        self.assertEqual(kinds([row(1, "mercadolibre", hashes=[H1]), row(2, "v6", hashes=[H1_NEAR],
                                                                         price_usd=9_000.0)], tight), {})


class DataLevelTests(unittest.TestCase):
    def pair(self, **b):
        return [row(1, "mercadolibre"), row(2, "rosariogarage", **{"mileage_km": 91_500, "price_usd": 12_500.0,
                                                                      "zone": FUNES, **b})]

    def test_a_unique_pair_with_a_fine_zone_is_stored_in_shadow(self):
        got = detect(self.pair(), CFG)
        self.assertEqual([(p.a, p.b, p.kind) for p in got], [(1, 2, "cross_source_data")])
        out = rows_out(got, CFG)
        self.assertEqual({r["shown"] for r in out.values()}, {False})
        self.assertEqual(got[0].evidence["zone"]["same_department"], True)
        self.assertLessEqual(got[0].evidence["km_pct"], 3)

    def test_with_the_data_level_on_it_is_shown(self):
        out = rows_out(detect(self.pair(), ON), ON)
        self.assertEqual({r["shown"] for r in out.values()}, {True})

    def test_off_stores_nothing(self):
        off = risk({"signals": {"cross_source_data": "off"}})
        self.assertEqual(rows_out(detect(self.pair(), off), off), {})

    def test_a_third_candidate_means_a_common_configuration(self):
        rows = self.pair() + [row(3, "rosariogarage", mileage_km=90_500, price_usd=12_100.0, zone=FUNES)]
        self.assertEqual(kinds(rows, ON), {})

    def test_a_twin_in_its_own_source_means_a_common_configuration(self):
        rows = self.pair() + [row(3, "mercadolibre", mileage_km=90_200, zone=CORDOBA)]
        self.assertEqual(kinds(rows, ON), {})

    def test_every_guard(self):
        cases = {
            "km under 10.000": dict(mileage_km=9_000),
            "km +4 %": dict(mileage_km=93_800),
            "price +6 %": dict(price_usd=12_800.0),
            "another year": dict(year=2018),
            "a dealer": dict(seller_type="dealer"),
            "a «posible agencia»": dict(dealer_inferred=True),
            "no fine zone": dict(zone={**FUNES, "precision": "province"}),
            "no zone": dict(zone=None),
            "far away": dict(zone=CORDOBA),
            "another version": dict(trim="SE"),
            "another gearbox": dict(transmission="automatic"),
            "a partial price": dict(price_partial=True),
        }
        for name, change in cases.items():
            rows = self.pair(**change)
            if name == "km under 10.000":
                rows[0]["mileage_km"] = 9_100
            with self.subTest(name):
                self.assertEqual(kinds(rows, ON), {})

    def test_an_unstated_version_does_not_block(self):
        self.assertEqual(kinds(self.pair(trim=None, fuel=None), ON), {(1, 2): "cross_source_data"})

    def test_same_province_other_department_within_50_km(self):
        near = {**FUNES, "department": "San Lorenzo", "lat": -32.75, "lon": -60.73}
        self.assertEqual(kinds(self.pair(zone=near), ON), {(1, 2): "cross_source_data"})

    def test_photos_take_precedence_over_data(self):
        rows = self.pair()
        rows[0]["hashes"], rows[1]["hashes"] = [H1], [H1]
        self.assertEqual(kinds(rows, ON), {(1, 2): "cross_source_photos"})

    def test_the_e2e_fixtures_shape_makes_no_pair(self):
        # 12 identical Corolla in one source (half dealers): no cross-source pair, no data pair.
        rows = [row(i, "mercadolibre", seller_type="dealer" if i % 2 else "private") for i in range(1, 13)]
        self.assertEqual(kinds(rows, ON), {})


if __name__ == "__main__":
    unittest.main()
