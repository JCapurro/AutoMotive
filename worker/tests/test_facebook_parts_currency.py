"""Facebook: parts taken for cars, and peso prices taken for dollars.

The titles and prices are the production ones of 02/11/2026."""
from __future__ import annotations

import unittest

from collectors.base import Listing
from normalization import not_vehicle
from normalization.fx import FxQuote
from normalization.listing import Target, facebook_price, normalize_listing
from collectors.facebook import _parse_price_sign, parse_card
from normalization.money import explicit_usd, facebook_currency, high_end
from normalization.vehicle import CatalogModel
from pipeline.ingest import merge, misread_currency

# (title, price, currency as stored)
PARTS = [
    ("Cremallera Peugeot 206-207-307-408", 270000, "USD"),
    ("Paragolpe trasero de Ford Ecosport", 100000, "USD"),
    ("Butacas Ford Ecosport", 350000, "USD"),
    ("Caja de Velocidades Peugeot 307 1.6 HDI", 350000, "USD"),
    ("Faro auxiliar led derecho Chevrolet tracker 2025", 110000, "USD"),
    ("Bomba de Agua Volkswagen Vento 2.5", 380000, "USD"),
    ("Burro de Arranque Ford Focus", 200000, "USD"),
    ("Tapa de Cilindro Volkswagen 1.6 Nafta Gol Trend", 450000, "USD"),
    ("TABLERO INSTRUMENTAL ORIGINAL FORD FIESTA / ECOSPORT", 180000, "USD"),
    ("Puertas peugeot 408", 800000, "USD"),
    ("Kit faros auxiliares Chevrolet onix", 450000, "USD"),
    ("Kit Embrague Valeo Peugeot 206", 200000, "USD"),
    ("TAPA DE PEUGEOT 206", 250000, "USD"),
    ("Optica Izquierda Chevrolet Tracker", 350000, "USD"),
    ("llantas Fiat uno scr", 200000, "USD"),
    ("Espejo Peugeot 308 /408 derecho eléctrico", 550000, "USD"),
    ("Embrague Peugeot 207 ( Nuevo )", 180000, "USD"),
    ("Cigüeñal original Chevrolet prisma", 100000, "USD"),
    ("ECU/MODULO INYECCION FORD ECOSPORT", 170000, "USD"),
    ("Estéreo pantalla Chevrolet Ónix", 200000, "USD"),
    ("Capot Original Ford Ecosport 2008 al 2012.", 350000, "USD"),
    ("Módulo confort alarma Ford Ecosport", 120000, "USD"),
    ("Alero Fiat Argo", 100000, "USD"),
    ("SUSPENSIÓN REGULABLE PEUGEOT 206", 450000, "USD"),
    ("Puesta Punto Citroen Peugeot Berlingo 206 307 Eurotech", 115000, "USD"),
    ("Parrilla original de Chevrolet Tracker GM 2021 al 2025", 145000, "USD"),
    ("Moldura Zocalo Ford Ecosport", 150000, "USD"),
    ("Guardaplast Trasero Izquierdo Audi Tt", 100000, "USD"),
    ("LLANTA FORD FOCUS 3", 350000, "USD"),
    ("COMPRESOR DE AIRE ACONDICIONADO Ford Ka", 360000, "USD"),
    ("Barra de inyección de Ford fiesta kinetic", 110000, "USD"),
    ("Sensor de Oxigeno Peugeot 207/208", 90000, "USD"),
    ("Barras antirobo techo solar peugeot 206/207", 80000, "USD"),
    ("Spoiler / deflector original paragolpe", 80000, "USD"),
    ("Parrilla frontal Peugeot 207 Compact", 80000, "USD"),
    ("Guia Paragolpe Trasero Chevrolet Tracker", 35000, "USD"),
    ("Motor limpiaparabrisas y varillas de Peugeot", 80000, "USD"),
    ("Lente para óptica para Peugeot 207", 49000, "USD"),
    ("CAJA DE CAMBIO DE PEUGEOT 206/207", 1500000, "ARS"),
    ("PUERTA DELANTERA IZQUIERDA PEUGEOT 308 / 408", 1100000, "ARS"),
    ("Desarme de Chevrolet prisma 2017", None, None),
    ("Volante peugeot 206 207", None, None),
    ("Radiador de agua Chevrolet tracker 2015", None, None),
    ("Vendo frente de Chevrolet prisma", None, None),
    ("Cosas de Peugeot 206", None, None),
    ("Base Moldura Honda Accord 2006/2007", None, None),
]

CARS = [
    ("OPORTUNIDAD PEUGEOT 207 IMPECABLE", 6400, "USD"),
    ("FORD ECOSPORT 1.4 XLS 2008 ‼️SE PUEDE FINANCIAR", 6400, "USD"),
    ("Volkswagen Tiguan 2.0 TDI Highline Dsg 2019", 26500, "USD"),
    ("Ford Ecosport 2.0 4x2 XLT Plus", 10000, "USD"),
    ("2013 Volkswagen scirocco 1.4 tsi dsg", 18500, "USD"),
    ("2017 Ford ka se", 10500, "USD"),
    ("Peugeot 207 1.4 Allure 2015", 9000, "USD"),
    ("2016 Volkswagen golf gti mk7", 28300, "USD"),
    ("Hyundai hb20 confort plus automatico", 32500, "USD"),
    ("2027 Volkswagen Polo", 285000, "USD"),
    ("FORD ECOSPORT XLS 1.6 GNC FULL", 990000, "USD"),
    ("You", 111111, "USD"),
    # Car titles that mention a part.
    ("Peugeot 206 con llantas nuevas", 7000, "USD"),
    ("Chevrolet Onix 1.4 LTZ caja automática", 12000, "USD"),
    ("Volkswagen Gol Trend 5 puertas", 8000, "USD"),
    ("Vendo Peugeot 208 Feline", 15000, "USD"),
    ("Nuevo Peugeot 208 0km", 25000, "USD"),
    # Car titles that open with a piece of equipment, slang or a negated «desarme».
    ("BOMBA Gol Trend 2012 full", 7000, "USD"),
    ("Bomba!! Peugeot 208 impecable", 15000, "USD"),
    ("Caja automática Peugeot 208 Allure 2020", 18000, "USD"),
    ("Techo solar Jeep Compass Limited 2018", 25000, "USD"),
    ("Radio taxi Chevrolet Spin con licencia", 9000, "USD"),
    ("Llantas de aleación, Gol Trend 2013 full", 8000, "USD"),
    ("Alarma Chevrolet Onix 2018", 11000, "USD"),
    ("Accesorios incluidos Toyota Hilux 2019", 30000, "USD"),
    ("Ford Ka 2012 no es desarme", 6000, "USD"),
]


class NotVehicleTests(unittest.TestCase):
    def test_every_part_in_production_is_a_part(self):
        missed = [t for t, _, _ in PARTS if not_vehicle.classify(t) is None]
        self.assertEqual(missed, [])

    def test_no_car_is_a_part(self):
        wrong = [(t, not_vehicle.classify(t)) for t, _, _ in CARS if not_vehicle.classify(t)]
        self.assertEqual(wrong, [])

    def test_equipment_without_a_single_year_is_still_a_part(self):
        for title in ("Llantas Peugeot 206 2008 al 2012", "Radio Peugeot 206", "Caja automatica Peugeot 208",
                      "Techo solar Peugeot 206/207", "Alarma Ford Ka 2010-2014", "Bomba nafta Gol Trend",
                      "Bomba inyectora Hilux 2012", "Desarme Ford Ka 2012"):
            self.assertIsNotNone(not_vehicle.classify(title), title)

    def test_whole_car_evidence_wins(self):
        # The source's own year and mileage: Facebook only shows km on vehicles.
        self.assertIsNone(not_vehicle.classify("Puertas peugeot 408", year=2015, mileage_km=90_000))
        self.assertIsNone(not_vehicle.classify("Volante peugeot 206", "Vendo mi auto, titular"))
        self.assertIsNone(not_vehicle.classify("Faro Peugeot 206 con 120.000 km"))
        self.assertIsNone(not_vehicle.classify("Frente impecable 206", "Papeles al día, VTV"))
        self.assertIsNone(not_vehicle.classify("2015 Llantas Peugeot"))
        # A year alone is no car: «Faro ... tracker 2025».
        self.assertIsNotNone(not_vehicle.classify("Faro auxiliar led Chevrolet tracker 2025", year=2025))

    def test_rows_only_from_facebook_and_only_with_the_sources_own_mileage(self):
        row = {"source": "facebook", "title": "Puertas peugeot 408", "year": 2015, "mileage_km": 90_000,
               "attributes": {"_description_filled": ["mileage_km"]}}
        self.assertIsNotNone(not_vehicle.classify_row(row))
        self.assertIsNone(not_vehicle.classify_row({**row, "attributes": {}}))
        self.assertIsNone(not_vehicle.classify_row({**row, "source": "mercadolibre", "attributes": {}}))


class ClassifyUpdateTests(unittest.TestCase):
    """A card on a stored listing is judged with what the listing already knows."""

    card = {"source": "facebook", "title": "Frente impecable Peugeot 206 XT", "description": None,
            "year": 2010, "mileage_km": None, "attributes": {}}

    def test_the_stored_description_says_car(self):
        card = {**self.card, "not_vehicle": not_vehicle.classify_row(self.card)}
        self.assertIsNotNone(card["not_vehicle"])
        stored = {**self.card, "description": "Vendo mi auto, titular, VTV al día"}
        self.assertIsNone(not_vehicle.classify_row(stored))
        self.assertIsNone(not_vehicle.classify_update(card, stored))

    def test_the_stored_mileage_says_car(self):
        card = {**self.card, "not_vehicle": not_vehicle.classify_row(self.card)}
        self.assertIsNone(not_vehicle.classify_update(card, {**self.card, "mileage_km": 150_000}))
        # ... unless the description filled it.
        stored = {**self.card, "mileage_km": 150_000, "attributes": {"_description_filled": ["mileage_km"]}}
        self.assertIsNotNone(not_vehicle.classify_update(card, stored))

    def test_without_stored_evidence_it_is_a_part(self):
        card = {**self.card, "not_vehicle": not_vehicle.classify_row(self.card)}
        self.assertEqual(not_vehicle.classify_update(card, None), card["not_vehicle"])
        self.assertEqual(not_vehicle.classify_update(card, {**self.card, "description": "Impecable"}),
                         card["not_vehicle"])
        self.assertIsNone(not_vehicle.classify_update({**self.card, "title": "Peugeot 206", "not_vehicle": None},
                                                      None))


class FacebookCurrencyTests(unittest.TestCase):
    def test_usd_from_the_ceiling_up_is_ars(self):
        for title, price, currency in PARTS + CARS:
            if currency != "USD":
                continue
            expected = "ARS" if price >= 100_000 else "USD"
            self.assertEqual(facebook_currency(price, currency), expected, title)
        self.assertEqual(facebook_currency(1_500_000, "ARS"), "ARS")
        self.assertIsNone(facebook_currency(None, None))
        self.assertEqual(facebook_currency(99_999, "USD"), "USD")
        self.assertEqual(facebook_currency(150_000, "USD", ceiling=200_000), "USD")

    def test_high_end_cars_keep_their_dollars(self):
        self.assertEqual(facebook_currency(180_000, "USD", make="Porsche", model="911"), "USD")
        self.assertEqual(facebook_currency(160_000, "USD", make="Land Rover", model="Range Rover Sport"), "USD")
        self.assertTrue(high_end("Mercedes-Benz", "AMG GT"))
        self.assertFalse(high_end("Peugeot", "208"))
        # Cars that cost more than USD 100.000 in Argentina (seed.sql names).
        for make, model, price in (("Land Rover", "Defender", 140_000), ("BMW", "X5", 130_000),
                                   ("BMW", "M4", 130_000), ("Mercedes-Benz", "GLE", 115_000),
                                   ("Mercedes-Benz", "Clase S", 150_000), ("Ford", "F-150", 150_000),
                                   ("Audi", "Q8", 140_000), ("Volvo", "XC90", 120_000),
                                   ("Ram", "2500", 120_000), ("Chevrolet", "Tahoe", 140_000),
                                   ("Chevrolet", "Silverado", 120_000), ("Jeep", "Grand Cherokee", 110_000),
                                   ("Lexus", "RX", 180_000)):
            self.assertEqual(facebook_currency(price, "USD", make=make, model=model), "USD", (make, model))
        # A mainstream car's bare «$ 130.000» is still pesos.
        self.assertEqual(facebook_currency(130_000, "USD", make="Ford", model="EcoSport"), "ARS")

    def test_a_sign_that_names_the_dollar_is_never_reinterpreted(self):
        for sign in ("US$", "u$s", "USD", " U$S "):
            self.assertTrue(explicit_usd(sign), sign)
            self.assertEqual(facebook_currency(180_000, "USD", sign=sign), "USD", sign)
        for sign in ("$", None, "ARS"):
            self.assertFalse(explicit_usd(sign), sign)
        self.assertEqual(facebook_currency(180_000, "USD", sign="$"), "ARS")
        self.assertEqual(facebook_price("facebook", 180_000, "USD", sign="US$"), (180_000, "USD", None))

    def test_the_collector_keeps_the_sign(self):
        self.assertEqual(_parse_price_sign("US$ 180.000"), (180_000.0, "USD", "US$"))
        self.assertEqual(_parse_price_sign("$ 11.900"), (11_900.0, "USD", "$"))
        self.assertEqual(_parse_price_sign("$12"), (None, None, None))
        card = parse_card("/marketplace/item/42/", "US$ 130.000\nLexus LX 570 2019\nNordelta")
        self.assertEqual((card.precio, card.moneda, card.extra), (130_000, "USD", {"price_sign": "US$"}))

    def test_facebook_price(self):
        # A peso amount too small for a car is no price, as the collector drops it.
        self.assertEqual(facebook_price("facebook", 350_000, "USD"),
                         (None, None, {"amount": 350_000, "currency": "USD", "as": None}))
        self.assertEqual(facebook_price("facebook", 990_000, "USD"),
                         (990_000, "ARS", {"amount": 990_000, "currency": "USD", "as": "ARS"}))
        self.assertEqual(facebook_price("facebook", 6_400, "USD"), (6_400, "USD", None))
        self.assertEqual(facebook_price("mercadolibre", 350_000, "USD"), (350_000, "USD", None))


CATALOG = [CatalogModel(make="Ford", model="EcoSport", body_types=("suv",))]
FX = FxQuote(1_000.0, "blue", "test")


def item(title: str, price: float | None, currency: str | None, **kw) -> Listing:
    return Listing(source="facebook", listing_id=kw.pop("listing_id", "1"), titulo=title,
                   url="https://www.facebook.com/marketplace/item/1/", precio=price, moneda=currency, **kw)


class NormalizeFacebookTests(unittest.TestCase):
    def normalize(self, *args, **kw):
        return normalize_listing(item(*args, **kw), catalog=CATALOG, target=Target("Ford", "EcoSport"), fx=FX)

    def test_ecosport_21327(self):
        # «$ 990.000»: ARS, and attributes.moneda says the same as the columns.
        row = self.normalize("FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "USD")
        self.assertEqual((row["price_published"], row["price_published_currency"]), (990_000, "ARS"))
        self.assertEqual((row["price"], row["currency"], row["price_usd"]), (990_000, "ARS", 990.0))
        self.assertEqual(row["attributes"]["moneda"], "ARS")
        self.assertEqual(row["attributes"]["_currency_read"]["currency"], "USD")
        self.assertIsNone(row["not_vehicle"])

    def test_a_part_is_flagged_and_its_peso_price_dropped(self):
        row = self.normalize("Butacas Ford Ecosport", 350_000, "USD")
        self.assertIsNotNone(row["not_vehicle"])
        self.assertIsNone(row["price"])
        self.assertIsNone(row["price_published"])
        self.assertNotIn("moneda", row["attributes"])

    def test_an_explicit_dollar_sign_keeps_the_dollars_and_is_stored(self):
        row = self.normalize("Ford Ecosport Titanium 2024", 130_000, "USD", extra={"price_sign": "US$"})
        self.assertEqual((row["price"], row["currency"]), (130_000, "USD"))
        self.assertEqual(row["attributes"]["_price_sign"], "US$")
        self.assertNotIn("_currency_read", row["attributes"])

    def test_a_dollar_car_stays(self):
        row = self.normalize("FORD ECOSPORT 1.4 XLS 2008 ‼️SE PUEDE FINANCIAR", 6_400, "USD", anio=2008)
        self.assertEqual((row["price"], row["currency"], row["attributes"]["moneda"]), (6_400, "USD", "USD"))
        self.assertIsNone(row["not_vehicle"])
        self.assertNotIn("_currency_read", row["attributes"])


class MergeReinterpretedCurrencyTests(unittest.TestCase):
    """A stored «USD 990.000» read again as ARS is no price drop."""

    def stored(self, price, currency, **kw):
        return {"id": 1, "source": "facebook", "external_id": "1", "url": "u", "title": "FORD ECOSPORT XLS",
                "price": price, "currency": currency, "price_usd": price if currency == "USD" else None,
                "price_published": price, "price_published_currency": currency, "price_source": "published",
                "attributes": {"moneda": "ARS"}, "enriched_at": "2026-10-01", **kw}

    def test_same_amount_new_currency_is_no_price_change(self):
        existing = self.stored(990_000, "USD")
        incoming = normalize_listing(item("FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "USD"),
                                     catalog=CATALOG, fx=FX)
        out, changes = merge(existing, incoming, detail=False)
        self.assertEqual((out["price_published"], out["price_published_currency"]), (990_000, "ARS"))
        self.assertEqual((out["price"], out["currency"], out["price_usd"]), (990_000, "ARS", 990.0))
        self.assertEqual(out["attributes"]["moneda"], "ARS")
        self.assertNotIn("price", changes)          # no snapshot 'price', no price_drop
        self.assertIn("description", changes)

    def test_a_peso_amount_too_small_clears_the_price(self):
        existing = self.stored(285_000, "USD", attributes={"moneda": "USD"})
        incoming = normalize_listing(item("2027 Volkswagen Polo", 285_000, "USD"), catalog=CATALOG, fx=FX)
        out, changes = merge(existing, incoming, detail=False)
        self.assertEqual((out["price"], out["currency"], out["price_usd"], out["price_published"]),
                         (None, None, None, None))
        self.assertNotIn("moneda", out["attributes"])
        self.assertNotIn("price", changes)

    def test_moneda_follows_the_published_price_on_a_card(self):
        # 21327: the card (not authoritative) used to keep the stored moneda.
        existing = self.stored(9_900_000, "ARS", attributes={"moneda": "ARS"})
        incoming = normalize_listing(item("FORD ECOSPORT XLS 1.6 GNC FULL", 9_500, "USD"), catalog=CATALOG, fx=FX)
        out, changes = merge(existing, incoming, detail=False)
        self.assertEqual((out["price_published_currency"], out["attributes"]["moneda"]), ("USD", "USD"))
        self.assertIn("price", changes)

    def test_a_misread_stored_price_is_known(self):
        self.assertTrue(misread_currency(self.stored(990_000, "USD")))
        self.assertFalse(misread_currency(self.stored(990_000, "ARS")))
        self.assertFalse(misread_currency(self.stored(9_900, "USD")))
        self.assertFalse(misread_currency(self.stored(990_000, "USD", attributes={"_price_sign": "US$"})))
        self.assertFalse(misread_currency(self.stored(130_000, "USD", make="BMW", model="X5")))
        self.assertFalse(misread_currency(self.stored(990_000, "USD", source="mercadolibre")))

    def test_a_listing_read_as_a_car_again_loses_the_mark(self):
        existing = self.stored(9_500, "USD", attributes={"moneda": "USD", "_not_vehicle": {"reason": "x"}})
        incoming = normalize_listing(item("FORD ECOSPORT XLS 1.6 GNC FULL", 9_500, "USD"), catalog=CATALOG, fx=FX)
        out, _ = merge(existing, incoming, detail=True)
        self.assertNotIn("_not_vehicle", out["attributes"])


if __name__ == "__main__":
    unittest.main()
