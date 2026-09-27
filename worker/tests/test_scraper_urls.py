from __future__ import annotations

import unittest

from collectors.facebook import FacebookMarketplaceScraper, _matches_query_text, _parse_price
from collectors.v6 import V6Scraper


class ScraperUrlTests(unittest.TestCase):
    def test_facebook_uses_search_route_when_query_is_present(self):
        url = FacebookMarketplaceScraper()._build_url({"marca": "Ford", "modelo": "Fiesta"})

        self.assertIn("/marketplace/buenosaires/search/", url)
        self.assertIn("query=Ford+Fiesta", url)
        self.assertNotIn("/vehicles/", url)

    def test_facebook_requires_query_terms_in_listing_text(self):
        filters = {"marca": "Ford", "modelo": "Fiesta"}

        self.assertTrue(_matches_query_text("2018 Ford Fiesta Kinetic", filters))
        self.assertFalse(_matches_query_text("2011 Audi S3 Quattro", filters))

    def test_facebook_plain_peso_prices_are_usd_unless_they_are_millions(self):
        self.assertEqual(_parse_price("$11,900"), (11900.0, "USD"))
        self.assertEqual(_parse_price("$9.700"), (9700.0, "USD"))
        self.assertEqual(_parse_price("$11,900,000"), (11900000.0, "ARS"))
        self.assertEqual(_parse_price("$11.900.000"), (11900000.0, "ARS"))

    def test_facebook_discards_implausibly_low_vehicle_prices(self):
        self.assertEqual(_parse_price("$12"), (None, None))
        self.assertEqual(_parse_price("ARS 450.000"), (None, None))

    def test_v6_uses_text_search_for_model_because_model_param_drops_results(self):
        url = V6Scraper()._build_url({"marca": "Ford", "modelo": "Fiesta"})

        self.assertIn("brand=ford", url)
        self.assertIn("search=fiesta", url)
        self.assertNotIn("model=fiesta", url)


if __name__ == "__main__":
    unittest.main()
