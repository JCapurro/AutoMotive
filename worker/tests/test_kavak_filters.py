from __future__ import annotations

import unittest
from unittest.mock import patch

from collectors.base import Listing
from collectors.kavak import KavakScraper


class KavakFilterTests(unittest.TestCase):
    def _listing(self) -> Listing:
        return Listing(
            source="kavak",
            listing_id="kavak-1",
            titulo="Ford Fiesta",
            url="https://www.kavak.com/ar/venta/ford-fiesta",
            precio=10_000,
            moneda="USD",
            vendedor="concesionaria",
        )

    def test_kavak_ignores_seller_filter(self):
        self.assertTrue(
            KavakScraper.matches_filters(self._listing(), {"vendedor": "particular"})
        )

    def test_kavak_still_applies_other_filters(self):
        self.assertFalse(
            KavakScraper.matches_filters(self._listing(), {"precio_max": 9_000})
        )

    def test_kavak_converts_ars_price_for_usd_thresholds(self):
        listing = self._listing()
        listing.precio = 13_200_000
        listing.moneda = "ARS"

        with patch("collectors.kavak.usd_ars_rate", return_value=1_200):
            self.assertTrue(
                KavakScraper.matches_filters(
                    listing,
                    {"moneda": "USD", "precio_min": 7_000, "precio_max": 12_000},
                )
            )

            listing.precio = 15_600_000
            self.assertFalse(
                KavakScraper.matches_filters(
                    listing,
                    {"moneda": "USD", "precio_min": 7_000, "precio_max": 12_000},
                )
            )


if __name__ == "__main__":
    unittest.main()
