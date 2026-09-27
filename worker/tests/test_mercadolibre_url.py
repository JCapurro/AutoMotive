from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import config
from scrapers.mercadolibre import _browser_storage_state, _build_url, _looks_like_login_wall


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

    def test_browser_storage_state_uses_existing_ml_session_file(self):
        original = config.ML_STORAGE_STATE
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "ml_state.json"
            config.ML_STORAGE_STATE = str(state)
            self.assertIsNone(_browser_storage_state())

            state.write_text("{}", encoding="utf-8")
            self.assertEqual(_browser_storage_state(), str(state))
        config.ML_STORAGE_STATE = original

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
