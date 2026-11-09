"""Facebook: parts taken for cars, and peso prices taken for dollars.

The titles and prices are the production ones of 02/11/2026."""
from __future__ import annotations

import unittest

from collectors.base import Listing
from normalization import not_vehicle
from normalization.fx import FxQuote
from normalization.listing import Target, doubtful_price, facebook_price, normalize_listing
from collectors.facebook import _parse_price_sign, parse_card
from normalization.money import explicit_usd, facebook_currency, high_end
from normalization.vehicle import CatalogModel
from pipeline.ingest import merge, misread_currency, price_drop_pct, published_partial, published_view

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

# Parts matched to searches as cars in production (09/11/2026), several sent in
# a daily digest as «low» matches; most with no price or year, the others with
# pesos read as dollars under the ceiling («Comando calefacción Peugeot 207»,
# USD 40.000). Kept out of PARTS: facebook_currency can't tell those prices.
MATCHED_PARTS = [
    "Comando calefacción Peugeot 207",
    "Comando Climatizador Volkswagen Vento original",
    "Comando levantavidrios pasajero original Peugeot 208 13/20",
    "SE VENDE COMANDO DE AIRE FIAT UNO WAY",
    "Depósito de líquido de freno de Ford Focus 2",
    "Depósito de agua de limpiaparabrisas Chevrolet onix prisma",
    "Sold · Encendido de Chevrolet corsa completo con cables",
    "SOPORTE PARA LLAVES VOLKSWAGEN GOLF GTI 🚗🔑",
    "Soporte de P4t4 De Motor Ford Focus 1 Diesel Lado Derecho $$$40000!!!",
    "Polea Chevrolet Corsa motor 1.4",
    "Vendo polea cigüeñal Chevrolet prisma",
    "Vendo parqgolpe delantero de chevrolet corsa classic del modelo 2010al2016 generico es",
    "Alma paragolpe delantero Ford Focus 2 y Ford Kuga 04/13 original",
    "Caja completa evaporadora de aire acondicionado de Chevrolet Corsa classic 2010",
    "Caja de Volkswagen Gol",
    "Caja filtrera de Peugeot 206",
    "Cuerpo marisopa Chevrolet corsa 1.6",
    "Pedal de Acelerador Ford Fiesta Kinetic Ecosport 8V219F836AB ID:278",
    "Pata de motor de Chevrolet onix prisma",
    "P4t4 De Motor Ford Focus 1 Diesel Lado Derecho $50000!!!",
    "Torpedo y centro de volante Volkswagen gol trend",
    "Torpedo y centro de volante Chevrolet tracker sin detalles",
    "Porta filtro de aire original Chevrolet Corsa",
    "Porta masa tracero Chevrolet Tracker 13-19",
    "Portalámpara delantero Peugeot 207.c4.cronos",
    "Maquina Levanta Cristal Peugeot 207 08/15 3p manual derecha",
    "Vendo alza cristal eléctrico Volkswagen gol gl,lado izquierdo.",
    "Tecla Levantavidrios Peugeot 207 #352",
    "Servo de freno de Ford Focus",
    "Tubo Retorno A/C Ford Focus 2 C-Max 1.6 TDCi FOMOCO Original 1581992",
    "Manguera aire acondicionado Peugeot 208",
    "Cables de bujias para ford fiesta kinetic ecosport kinetic",
    "Kit Cables + Bujias NGK Chevrolet Prisma Onix 1.4",
    "Kit precaps Renault Kangoo",
    "Caños de bomba inyectora diesel volkswagen senda gol Saveiro gacel",
    "Vendo+columna+dirección+Chevrolet+prisma",
    "Llave tambor Peugeot 207",
    "LUZ STOP TRASERA PEUGEOT 207 SEDAN (SOLO SEDAN )",
    "Led Cree H1 Luz Alta Peugeot 207",
    "Marco de espejo Chevrolet Corsa",
    "Motor calefacción original Peugeot 308 408 Citroen C4 lounge",
    "Motor y caja de Ford fiesta gasoil con papeles",
    "Octicas+de+Peugeot+307+y+de+Peugeot+208",
    "GUARDAPLAS DELANTERO DERECHO VOLKSWAGEN  GOL VOYAGE 2012 /15",
    "Masas delanteras completas Peugeot 207-206 y demás muy buen estado",
    "Baúl Peugeot 408",
    "Arranque honda Accord",
    "Bielas de ford maverick/bronco 2.0 ecoboost",
    "Vendo araña Chevrolet prisma",
    "Vendo caballete con leva.chevrolet.prisma",
    "Chapon cubre carter Peugeot 207",
    "CARCASA CUBRE VOLANTE PEUGEOT 207 ORIGINAL",
    "Cenicero de Ford Focus 1 $$$18000!!!",
    "Centro llanta Ford fiesta Ka original",
    "CONSOLA ORIGINAL FRENO DE MANO PEUGEOT 207",
    "Difusor de circulacion aire Ford Focus 1 $$$40000!!!",
    "Forzador de calefacción Peugeot 207",
    "Vendo resonador de aire Chevrolet prisma",
    "Limitador (rienda) Puerta delantera Derecha Chevrolet ONIX/PRISMA ORIGINAL 100% USADO",
    "lateral derecho peugeot 408 sin zocalo",
    "Logo Insignia de Peugeot 207 en muy buen estado",
    "Lona marítima Ford maverick",
    "Manual de Propietario Original Honda Accord",
    "Pomo y cofia palanca cambios Volkswagen vento variant golf mk6",
    "Progresivos nuevos de Peugeot 207/06",
    "RAMPA DE INYECTORES PARA GAS 5TA GENERACIÓN PEUGEOT 207",
    "Resortes de suspensión de Renault Kangoo nuevos",
    "Selectora De Cambios Automática DSG 6v Audi A3/TT Original Nuevo",
    "Tazas chevrolet corsa",
    "VISERA DE TABLERO ORIGINAL PEUGEOT 207",
    "BAJADA MOTOR ESCAPE VOLKSWAGEN VOYAGE GOL TREND FOX SAVEIRO",
    # Equipment and ambiguous words, with no single model year.
    "Rueda de auxilio temporal ford fiesta",
    "Ruedas de Chevrolet Astra",
    "Sterio chevrolet corsa",
    "Display Peugeot 207",
    "Insignia Peugeot 207 grande",
    "Campana Ford Ecosport kinetic",
    "Asesorío de Chevrolet Corsa 3 puertas ay todo de interio",
]

# Cars whose titles name one of those parts, or open with a word they share.
MATCHED_PARTS_CARS = [
    "Corsa con paragolpes nuevo",
    "Chevrolet Corsa Classic 1.4 con comando de climatizador",
    "Vendo Chevrolet Corsa, polea y distribución nuevas",
    "Peugeot 207 compact soporte de motor nuevo",
    "Gol Trend 2015 depósito de agua y mangueras nuevas",
    "Vendo Peugeot 207 con llave de repuesto",
    "Llave en mano Peugeot 208 Allure",
    "Llaves en mano Fiat Cronos Drive",
    "Rueda de auxilio sin uso, Gol Trend 2014 full",
    "Caja manual 5ta, Peugeot 208 Active 2019",
    "Insignia 2.0 turbo 2012 impecable",
    "Campana: Ford Ka 2016 impecable",
    "Luz vende su Fiat Palio 1.4",
    "Marco vende Volkswagen Gol Trend",
    "Sold · 2018 Toyota Etios",
    # Real titles of cars in the vehicle classifieds.
    "Distribución recién hecha en Taller Renault Oficial Carlos Trabucco",
    "Motor: 1.4 Litros Turbo (ecotec), 4 Cilindros, 16 Válvulas D",
]


class NotVehicleTests(unittest.TestCase):
    def test_every_part_in_production_is_a_part(self):
        missed = [t for t, _, _ in PARTS if not_vehicle.classify(t) is None]
        self.assertEqual(missed, [])

    def test_no_car_is_a_part(self):
        wrong = [(t, not_vehicle.classify(t)) for t, _, _ in CARS if not_vehicle.classify(t)]
        self.assertEqual(wrong, [])

    def test_every_part_matched_in_production_is_a_part(self):
        missed = [t for t in MATCHED_PARTS if not_vehicle.classify(t) is None]
        self.assertEqual(missed, [])

    def test_no_car_naming_those_parts_is_a_part(self):
        wrong = [(t, not_vehicle.classify(t)) for t in MATCHED_PARTS_CARS if not_vehicle.classify(t)]
        self.assertEqual(wrong, [])

    def test_the_digest_rows_are_flagged_as_stored(self):
        # As stored: no year or mileage, pesos read as dollars or no price at all.
        for title, price in (("Comando calefacción Peugeot 207", 40_000),
                             ("Depósito de líquido de freno Peugeot/ citroen 208/ c3", 40_000),
                             ("Polea Chevrolet Corsa motor 1.4", None),
                             ("Vendo parqgolpe delantero de chevrolet corsa classic del modelo 2010al2016 "
                              "generico es", None)):
            row = {"source": "facebook", "title": title, "description": None, "year": None,
                   "mileage_km": None, "price": price, "currency": "USD" if price else None, "attributes": {}}
            self.assertIsNotNone(not_vehicle.classify_row(row), title)

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
        self.assertIsNone(not_vehicle.classify("Comando calefacción Peugeot 207", year=2012, mileage_km=150_000))
        self.assertIsNone(not_vehicle.classify("Polea Chevrolet Corsa", "Vendo mi auto, papeles al día"))
        self.assertIsNone(not_vehicle.classify("Soporte de motor nuevo, Corsa con 98.000 km"))
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
    def test_usd_from_the_ceiling_is_unreadable_below_a_million_and_ars_above(self):
        for title, price, currency in PARTS + CARS:
            if currency != "USD":
                continue
            expected = "USD" if price < 100_000 else None
            self.assertEqual(facebook_currency(price, currency), expected, title)
        self.assertEqual(facebook_currency(1_500_000, "ARS"), "ARS")
        self.assertEqual(facebook_currency(1_000_000, "USD"), "ARS")
        self.assertIsNone(facebook_currency(999_999, "USD"))
        self.assertIsNone(facebook_currency(100_000, "USD"))
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
        # A mainstream car's bare «$ 130.000» is neither dollars nor a car's pesos.
        self.assertIsNone(facebook_currency(130_000, "USD", make="Ford", model="EcoSport"))
        self.assertEqual(facebook_currency(1_300_000, "USD", make="Ford", model="EcoSport"), "ARS")

    def test_a_sign_that_names_the_dollar_is_never_reinterpreted(self):
        for sign in ("US$", "u$s", "USD", " U$S "):
            self.assertTrue(explicit_usd(sign), sign)
            self.assertEqual(facebook_currency(180_000, "USD", sign=sign), "USD", sign)
        for sign in ("$", None, "ARS"):
            self.assertFalse(explicit_usd(sign), sign)
        self.assertIsNone(facebook_currency(180_000, "USD", sign="$"))
        self.assertEqual(facebook_price("facebook", 180_000, "USD", sign="US$"), (180_000, "USD", None))

    def test_the_collector_keeps_the_sign(self):
        self.assertEqual(_parse_price_sign("US$ 180.000"), (180_000.0, "USD", "US$"))
        self.assertEqual(_parse_price_sign("$ 11.900"), (11_900.0, "USD", "$"))
        self.assertEqual(_parse_price_sign("$12"), (None, None, None))
        card = parse_card("/marketplace/item/42/", "US$ 130.000\nLexus LX 570 2019\nNordelta")
        self.assertEqual((card.precio, card.moneda, card.extra), (130_000, "USD", {"price_sign": "US$"}))

    def test_facebook_price(self):
        # Below a million a bare «$» from the ceiling up is no price: neither
        # dollars nor pesos make it a car's.
        self.assertEqual(facebook_price("facebook", 350_000, "USD"),
                         (None, None, {"amount": 350_000, "currency": "USD", "as": None,
                                       "reason": "precio de Facebook no interpretable: $ 350.000"}))
        self.assertEqual(facebook_price("facebook", 990_000, "USD")[:2], (None, None))
        self.assertEqual(facebook_price("facebook", 1_990_000, "USD"),
                         (1_990_000, "ARS", {"amount": 1_990_000, "currency": "USD", "as": "ARS"}))
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
        # «$ 990.000»: no EcoSport costs USD 990.000 nor ARS 990.000 (USD 990).
        row = self.normalize("FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "USD", atributos={"moneda": "ARS"})
        self.assertEqual((row["price_published"], row["price_published_currency"]), (None, None))
        self.assertEqual((row["price"], row["currency"], row["price_usd"]), (None, None, None))
        self.assertEqual((row["price_partial"], row["price_partial_reason"]),
                         (True, "precio de Facebook no interpretable: $ 990.000"))
        self.assertNotIn("moneda", row["attributes"])
        self.assertEqual(row["attributes"]["_currency_read"]["currency"], "USD")
        self.assertIsNone(row["not_vehicle"])

    def test_a_peso_price_of_a_million_or_more_stored_as_dollars_is_ars(self):
        row = self.normalize("FORD ECOSPORT XLS 1.6 GNC FULL", 9_900_000, "USD")
        self.assertEqual((row["price"], row["currency"], row["price_usd"], row["price_partial"]),
                         (9_900_000, "ARS", 9_900.0, False))
        self.assertEqual(row["attributes"]["moneda"], "ARS")

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
        existing = self.stored(1_990_000, "USD")
        incoming = normalize_listing(item("FORD ECOSPORT XLS 1.6 GNC FULL", 1_990_000, "USD"),
                                     catalog=CATALOG, fx=FX)
        out, changes = merge(existing, incoming, detail=False)
        self.assertEqual((out["price_published"], out["price_published_currency"]), (1_990_000, "ARS"))
        self.assertEqual((out["price"], out["currency"], out["price_usd"]), (1_990_000, "ARS", 1_990.0))
        self.assertEqual(out["attributes"]["moneda"], "ARS")
        self.assertNotIn("price", changes)          # no snapshot 'price', no price_drop
        self.assertIn("description", changes)

    def test_an_unreadable_amount_clears_the_price_and_flags_it(self):
        existing = self.stored(285_000, "USD", attributes={"moneda": "USD"})
        incoming = normalize_listing(item("2027 Volkswagen Polo", 285_000, "USD"), catalog=CATALOG, fx=FX)
        out, changes = merge(existing, incoming, detail=False)
        self.assertEqual((out["price"], out["currency"], out["price_usd"], out["price_published"]),
                         (None, None, None, None))
        self.assertEqual((out["price_partial"], out["price_partial_reason"]),
                         (True, "precio de Facebook no interpretable: $ 285.000"))
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


# The ones tools.repair_facebook's dry run of 02/11/2026 would have turned
# into peso «cars» (or left without a price but still matching): bare «$»,
# FB_USD_CEILING <= amount < 1.000.000, none of them a part by its title.
# («Torpedo y centro de volante Chevrolet tracker sin detalles», $ 750.000, was
# one too; a part by its title since 11/2026, in MATCHED_PARTS.)
DOUBTFUL = [
    ("Ford ecosport porton trasero", 600_000, "Ford", "EcoSport"),
    ("FORD ECOSPORT 1.4 XLS 2008 ‼️RETÍRALO CON $900.000 Y CUOTAS FIJAS‼️", 900_000, "Ford", "EcoSport"),
    ("Chevrolet Onix tracker 1.0 1.2 tapa de cilindro", 500_000, "Chevrolet", "Onix"),
    ("4 Llantas Ford 16 pulgadas", 800_000, "Ford", None),
    ("TURBO COMPRSOR FORD", 650_000, "Ford", None),
    ("FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "Ford", "EcoSport"),           # 21327
    ("OPORTUNIDAD TAPA DE CILINDROS FORD 1.6", 220_000, "Ford", None),
    ("You", 111_111, None, None),
    ("2027 Volkswagen Polo", 285_000, "Volkswagen", "Polo"),
]
WIDE_CATALOG = CATALOG + [CatalogModel(make="Chevrolet", model="Onix", body_types=("hatchback",)),
                          CatalogModel(make="Chevrolet", model="Tracker", body_types=("suv",)),
                          CatalogModel(make="Volkswagen", model="Polo", body_types=("hatchback",))]


class DoubtfulFacebookPriceTests(unittest.TestCase):
    def normalize(self, title, price, *, make=None, model=None, **kw):
        return normalize_listing(item(title, price, "USD", **kw), catalog=WIDE_CATALOG,
                                 target=Target(make, model), fx=FX)

    def test_every_real_example_is_left_without_a_price_and_flagged(self):
        for title, price, make, model in DOUBTFUL:
            with self.subTest(title):
                row = self.normalize(title, price, make=make, model=model, atributos={"moneda": "ARS"})
                self.assertIsNone(row["not_vehicle"])                    # a «car» by its title...
                self.assertEqual((row["price"], row["currency"], row["price_usd"], row["price_published"],
                                  row["price_published_currency"], row["fx_rate"]),
                                 (None, None, None, None, None, None))
                reason = "precio de Facebook no interpretable: $ " + f"{price:,}".replace(",", ".")
                self.assertEqual((row["price_partial"], row["price_partial_reason"]), (True, reason))
                self.assertEqual(row["attributes"]["_currency_read"],
                                 {"amount": price, "currency": "USD", "as": None, "reason": reason})
                self.assertNotIn("moneda", row["attributes"])
                self.assertEqual(doubtful_price(row["attributes"]["_currency_read"]), reason)

    def test_the_reason_wins_over_the_titles(self):
        # «CUOTAS» in the title would say installment; the number is unreadable anyway.
        row = self.normalize(DOUBTFUL[1][0], 900_000, make="Ford", model="EcoSport")
        self.assertEqual(row["price_partial_reason"], "precio de Facebook no interpretable: $ 900.000")

    def test_premium_and_explicit_dollars_keep_their_usd(self):
        for title, price, kw in (("Porsche 911 Carrera S", 180_000, {"make": "Porsche", "model": "911"}),
                                 ("BMW X5 xDrive40i", 130_000, {"make": "BMW", "model": "X5"}),
                                 ("Ford Ecosport Titanium 2024", 600_000, {"extra": {"price_sign": "US$"}}),
                                 ("Ford Ecosport Titanium 2024", 130_000, {"extra": {"price_sign": "U$S"}}),
                                 ("Ford Ecosport Titanium 2024", 130_000, {"extra": {"price_sign": "USD"}})):
            with self.subTest(title, price=price, **kw):
                row = normalize_listing(item(title, price, "USD", **{k: v for k, v in kw.items() if k == "extra"}),
                                        catalog=CATALOG, target=Target(kw.get("make"), kw.get("model")), fx=FX)
                self.assertEqual((row["price"], row["currency"], row["price_partial"]), (price, "USD", False))
                self.assertNotIn("_currency_read", row["attributes"])

    def test_below_the_ceiling_is_a_dollar_price(self):
        row = self.normalize("Ford Ecosport 2.0 4x2 XLT Plus", 10_000, make="Ford", model="EcoSport")
        self.assertEqual((row["price"], row["currency"], row["price_partial"]), (10_000, "USD", False))

    def test_other_sources_are_untouched(self):
        row = normalize_listing(Listing(source="mercadolibre", listing_id="1", titulo="Ford Ecosport",
                                        url="https://x/1", precio=600_000, moneda="USD"),
                                catalog=CATALOG, fx=FX)
        self.assertEqual((row["price"], row["currency"], row["price_partial"]), (600_000, "USD", False))


class MergeDoubtfulTests(unittest.TestCase):
    """A stored listing read with an unreadable price, and the other way round."""

    def stored(self, **kw):
        return {**MergeReinterpretedCurrencyTests.stored(None, 9_500, "USD"),
                "attributes": {"moneda": "USD"}, "price_partial": False, **kw}

    def card(self, price, **kw):
        return normalize_listing(item("Ford ecosport porton trasero", price, "USD", **kw), catalog=CATALOG,
                                 target=Target("Ford", "EcoSport"), fx=FX)

    def test_an_unreadable_card_over_a_stored_price_leaves_no_price(self):
        out, changes = merge(self.stored(), self.card(600_000), detail=False)
        self.assertEqual((out["price"], out["currency"], out["price_usd"], out["price_published"]),
                         (None, None, None, None))
        self.assertEqual((out["price_partial"], out["price_partial_reason"]),
                         (True, "precio de Facebook no interpretable: $ 600.000"))
        self.assertNotIn("price", changes)          # no 'price' snapshot, no price_drop
        self.assertNotIn("moneda", out["attributes"])

    def test_a_flagged_listing_read_again_the_same_does_not_change(self):
        first, _ = merge(self.stored(), self.card(600_000), detail=False)
        stored = {**self.stored(), **first}
        out, changes = merge(stored, self.card(600_000), detail=False)
        self.assertEqual((out["price"], out["price_partial"]), (None, True))
        self.assertEqual(changes, [])

    def test_a_credible_price_clears_the_flag_without_a_drop(self):
        first, _ = merge(self.stored(), self.card(600_000), detail=False)
        stored = {**self.stored(), **first}
        out, changes = merge(stored, self.card(8_500), detail=False)
        self.assertEqual((out["price"], out["currency"], out["price_usd"], out["price_partial"],
                          out["price_partial_reason"]), (8_500, "USD", 8_500, False, None))
        self.assertEqual(out["attributes"]["moneda"], "USD")
        self.assertNotIn("_currency_read", out["attributes"])
        self.assertIn("price", changes)
        # ingest: no price drop from a listing without a price, and it was partial.
        self.assertIsNone(price_drop_pct(published_view(stored), published_view(out)))
        self.assertTrue(published_partial(stored))

    def test_no_price_read_after_an_unreadable_one_keeps_the_flag(self):
        # A detail page or a card that shows no price: the listing stays out of matching.
        first, _ = merge(self.stored(), self.card(600_000), detail=False)
        stored = {**self.stored(), **first}
        for detail in (False, True):
            with self.subTest(detail=detail):
                out, changes = merge(stored, self.card(None), detail=detail)
                self.assertEqual((out["price"], out["price_partial"], out["price_partial_reason"]),
                                 (None, True, "precio de Facebook no interpretable: $ 600.000"))
                self.assertNotIn("price", changes)

    def test_an_enriched_row_keeps_the_latest_unreadable_read(self):
        # Non-authoritative merge: the stored attributes win, but not an older read's note.
        stored = self.stored(enriched_at="2026-11-01",
                             attributes={"moneda": "USD", "_currency_read": {"amount": 1_990_000, "currency": "USD",
                                                                             "as": "ARS"}})
        out, _ = merge(stored, self.card(600_000), detail=False)
        self.assertEqual(out["attributes"]["_currency_read"]["as"], None)
        self.assertEqual(doubtful_price(out["attributes"]["_currency_read"]),
                         "precio de Facebook no interpretable: $ 600.000")
        again, _ = merge({**stored, **out}, self.card(None), detail=True)
        self.assertEqual((again["price"], again["price_partial"]), (None, True))


if __name__ == "__main__":
    unittest.main()
