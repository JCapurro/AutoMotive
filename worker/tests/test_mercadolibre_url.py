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
        self.assertIn("_KILOMETERS_*-120000km", url)
        self.assertNotIn("_PriceRange_", url)

    def test_searches_the_public_autos_host_by_make_and_model(self):
        self.assertEqual(_build_url({"marca": "Volkswagen", "modelo": "Gol Trend", "version": "Pack II"}),
                         "https://autos.mercadolibre.com.ar/volkswagen/gol-trend/_NoIndex_True")
        self.assertEqual(_build_url({"marca": "Mercedes-Benz", "modelo": "Clase A"}, page=3, today=True),
                         "https://autos.mercadolibre.com.ar/mercedes-benz/clase-a/_PublishedToday_YES_Desde_97_NoIndex_True")
        self.assertNotIn("listado.mercadolibre", _build_url({}))
        self.assertNotIn("_OrderId_", _build_url({"marca": "Ford", "modelo": "Fiesta"}))

    def test_strips_every_accent_from_make_and_model(self):
        # "Citroën" as /citro-n/ answered 404 (01/11/2026)
        self.assertEqual(_build_url({"marca": "Citroën", "modelo": "Basalt", "anio_min": 2017, "anio_max": 2017}),
                         "https://autos.mercadolibre.com.ar/citroen/basalt/_VEHICLE*YEAR_2017-2017_NoIndex_True")
        self.assertEqual(_build_url({"marca": "Peugeot", "modelo": "Partner Patagónica"}),
                         "https://autos.mercadolibre.com.ar/peugeot/partner-patagonica/_NoIndex_True")

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
