from __future__ import annotations

import unittest

from collectors.mercadolibre import _build_url, _looks_like_login_wall


class MercadoLibreUrlTests(unittest.TestCase):
    def test_price_filters_are_not_encoded_in_search_url(self):
        url = _build_url({
            "marca": "Ford",
            "modelo": "Fiesta",
            "anio_min": 2015,
            "anio_max": 2024,
            "km_max": 120000,
            "precio_min": 3000,
            "precio_max": 12000,
            "moneda": "USD",
        })

        self.assertIn("_VEHICLE*YEAR_2015-2024", url)
        self.assertIn("_KILOMETERS_0-120000km", url)
        self.assertNotIn("_PriceRange_", url)

    def test_detects_mercadolibre_account_verification_wall(self):
        self.assertTrue(
            _looks_like_login_wall(
                "https://www.mercadolibre.com.ar/gz/account-verification",
                "Hola! Para continuar, ingresa a tu cuenta.",
            )
        )
        self.assertFalse(
            _looks_like_login_wall(
                "https://listado.mercadolibre.com.ar/autos/ford-fiesta",
                "Ford Fiesta Kinetic 2018",
            )
        )


if __name__ == "__main__":
    unittest.main()
