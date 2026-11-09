"""Facebook: parts taken for cars, and peso prices taken for dollars.

The titles and prices are the production ones of 02/11/2026."""
from __future__ import annotations

import asyncio
import unittest

from collectors.base import Listing
from normalization import not_vehicle
from normalization.fx import FxQuote
from normalization.listing import Target, doubtful_price, facebook_price, normalize_listing
from collectors.facebook import _parse_price_sign, card_status, parse_card
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


# Matched as cars in the week of 02/11/2026 (the audit of 07/11/2026): the
# production titles, with the source's year when it gave one.
PARTS_1107 = [
    ("Comandos Golf mk3 full Volkswagen", None), ("Comando Climatizador Volkswagen gol original", None),
    ("SE VENDE COMANDO DE AIRE FIAT UNO WAY", None), ("Torpedo y centro de volante Chevrolet tracker", None),
    ("cuerpo mariposa Ford fiesta kinetic Ecosport kinetic", None), ("Vendo cuerpo mariposa Chevrolet prisma", None),
    ("Porta Filtro de Aire Original Chevrolet Corsa", None), ("Portamasa Chevrolet Astra 99-05", None),
    ("Porta masa tracero Chevrolet Tracker 13-19", None), ("Portafiltro Peugeot 308 / 408 thp", None),
    ("Soporte motor delantero Volkswagen Gol G1, Senda, Saveiro", None),
    ("SOPORTE PARA LLAVES VOLKSWAGEN GOLF GTI 🚗🔑", None),
    ("Pedal de Acelerador Ford Fiesta Kinetic Ecosport 8V219F836AB ID:278", None),
    ("Pedal Embrague Original Peugeot 208/2008 Año 13 A 19", 2008),
    ("Llave desde 0 Ford fiesta max ecosport linea vieja", None), ("Pata de motor Ford fiesta kinetic, Ecosport", None),
    ("Cables de bujias para ford fiesta kinetic ecosport kinetic", None),
    ("Panel trasero interno derecho Nissan Chevrolet Cruze - Cod 717", None),
    ("Caja de Volkswagen Gol", None), ("Vendo caja de Chevrolet prisma", None),
    ("Cilindro Puerta Volkswagen Senda Saveiro Gol 1991 1992 1994 1994 1995", 1991),
    ("Depósito de líquido de freno Peugeot 208 2025", 2025), ("Manguera aire acondicionado Peugeot 208", None),
    ("Caños de aire acondicionado Peugeot 208 2025", 2025), ("Marco de espejo Chevrolet Corsa", None),
    ("Ruedas de Chevrolet Astra", None), ("Rueda entera para Renault kangoo R14 175/70 cargo", None),
    ("Taza Citroën C4 R15", None), ("Resortes de suspensión de Renault Kangoo nuevos", None),
    ("Pomo y cofia palanca cambios Volkswagen vento variant golf mk6", None),
    ("BAJADA MOTOR ESCAPE VOLKSWAGEN VOYAGE GOL TREND FOX SAVEIRO", None),
    ("Vendo electro originales Peugeot 208 2014 valeo", 2014),
    ("Tecla Levantavidrios Cuadruple Chevrolet Corsa classic NUEVAS", None), ("LUZ AUXILIAR CHEVROLET CORSA", None),
    ("Bielas de ford maverick/bronco 2.0 ecoboost", None), ("Lona marítima Ford maverick", None),
    ("Asesorío de Chevrolet Corsa 3 puertas ay todo de interio", None), ("Baúl Volkswagen gol trend", None),
    ("Baúl paragolpe Volkswagen Vento Tsi 2017", 2017), ("4 Llantas 15 Toyota Corolla (5 tuercas)", None),
    ("1 llanta de Volkswagen Gol trend rodado 15 original", None),
    ("Tengo 2 puertas traseras izquierd y derecha y bomba inyectora de Peugeot 307 HDI diesel", None),
    ("Todo de Peugeot 307 HDI diesel modelo 2006", 2006), ("Octicas+de+Peugeot+307+y+de+Peugeot+208", None),
    ("Volkswagen gol power 2006/14 óptica derecha con detalle cod 787", 2006),
    ("Chevrolet prisma onix puerta trasera izquierda", None),
    ("Ford ecosport kinetic fiesta kinetic design pata soporte de motor p703", None),
    ("Estereo impecable para Ford focus 2012 2.0 l ....zona alta Córdoba", 2012),
    ("Estereo Peugeot 208 2021 en adelante", 2021),
    # Toys, scale models, collections.
    ("HONDA CIVIC CUSTOM HOTWHEELS", None), ("AUTO HONDA CIVIC CUSTON HOTWHEELS ( DE COLECCION )", None),
    ("FASCICULOS DE FORD MAVERICK,14, 17,18,19,20", None),
    ("Ford Maverick Salvat Entrega N° 34 Escala 1:8 Nuevo Cerrado", None),
    ("Honda civic coleccion rápido y furioso", None), ("Audi TT Coupé Motormax — Escala 1:18", None),
    ("Solido 1:43 Peugeot 207 Spider CUP #30 Dino Lunardi 2008. NUEVO", 2008),
    # A wanted post.
    ("2012 Busco Tapa Ciega Auxiliar honda city 2012", 2012),
]

# Cars the new words must not take for parts.
CARS_1107 = [
    "Ford Falcon de colección 1978", "Llave en mano Volkswagen Gol Trend 2015", "5 puertas Gol Trend 2012",
    "7 asientos Chevrolet Spin LTZ 2016", "2019 Volkswagen golf comfortline", "Volkswagen Gol Trend 5 puertas",
    "Toyota Etios Cross 2017", "Renault Kangoo Stepway 2014 doble portón", "Chevrolet Corsa Classic 2010 GNC",
    "Peugeot 208 GT 2020 impecable", "Fiat Palio Essence 1.6 2013", "Ford Ka Viral 2004",
    # The cases the review of 07/11/2026 raised.
    "Caja automática Peugeot 208 Allure 2020 listo para transferir", "Fiat 600 de colección",
    "Busco permuta Ford Ka 2014 por camioneta", "Compro, vendo, permuto Volkswagen Amarok 2018",
    "Vendo Peugeot 207 con detalle en puerta delantera izquierda", "Gol 2008 faro izquierdo roto",
    "Panel Fiat Fiorino 2014 1.4", "Comandos al volante Fiat Cronos 2021 drive",
    "Llave x llave Chevrolet Corsa 2009", "Caja de 6 marchas Ford Focus 2015", "Todo de serie Ford Fiesta 2012",
    "Luces led Volkswagen Amarok 2017 full", "Marco Polo Volkswagen T5 California",
    "3 cilindros Volkswagen up 2016",
]


class ProductionPartsOf0711Tests(unittest.TestCase):
    def test_every_part_is_a_part(self):
        missed = [t for t, year in PARTS_1107 if not_vehicle.classify(t, year=year) is None]
        self.assertEqual(missed, [])

    def test_no_car_is_a_part(self):
        wrong = [(t, r) for t in CARS_1107 + [t for t, _, _ in CARS] if (r := not_vehicle.classify(t))]
        self.assertEqual(wrong, [])

    def test_the_sources_year_and_mileage_still_say_car(self):
        self.assertIsNone(not_vehicle.classify("Comandos Golf mk3 full Volkswagen", year=1998, mileage_km=250_000))
        self.assertIsNone(not_vehicle.classify("Busco permuta Gol Trend 2012", year=2012, mileage_km=120_000))

    def test_a_wanted_post_is_no_car_whatever_its_title_says(self):
        for title in ("Busco Gol Trend 2012", "Compro Ford Ka", "2012 Busco Tapa Ciega Auxiliar honda city 2012"):
            self.assertTrue(not_vehicle.classify(title, year=2012).startswith("pedido de compra"), title)

    def test_the_reasons_say_what_it_is(self):
        self.assertEqual(not_vehicle.classify("HONDA CIVIC CUSTOM HOTWHEELS"), "juguete o colección: «hotwheels»")
        self.assertEqual(not_vehicle.classify("Comando calefacción Peugeot 207"), "título: «comando»")


class SoldCardTests(unittest.TestCase):
    def test_the_status_leaves_the_title(self):
        self.assertEqual(card_status("Sold · 2019 Volkswagen golf comfortline"),
                         ("2019 Volkswagen golf comfortline", "sold"))
        self.assertEqual(card_status("Vendido · 2017 Volkswagen gol trend"), ("2017 Volkswagen gol trend", "sold"))
        self.assertEqual(card_status("Pending · 2014 Ford fiesta kinetic"), ("2014 Ford fiesta kinetic", "pending"))
        self.assertEqual(card_status("2014 Ford fiesta kinetic"), ("2014 Ford fiesta kinetic", None))
        # Only as a prefix: «Vendido» in a title is no status.
        self.assertEqual(card_status("Gol Trend 2012 vendido · consultar")[1], None)

    def test_a_sold_card_says_so_and_normalizes_as_gone(self):
        card = parse_card("/marketplace/item/42/",
                          "US$ 12.500\nSold · 2019 Volkswagen golf comfortline\nRosario, SF",
                          label="Sold · 2019 Volkswagen golf comfortline, US$ 12.500, Rosario, SF")
        self.assertEqual((card.titulo, card.extra.get("card_status")), ("2019 Volkswagen golf comfortline", "sold"))
        # The line after the title is still the place, not the title itself.
        self.assertEqual(card.ubicacion, "Rosario, SF")
        row = normalize_listing(card, catalog=CATALOG, fx=FX)
        self.assertEqual((row["title"], row["card_gone"]), ("2019 Volkswagen golf comfortline", "sold"))
        live = parse_card("/marketplace/item/43/", "US$ 12.500\n2019 Volkswagen golf comfortline\nRosario")
        self.assertEqual(normalize_listing(live, catalog=CATALOG, fx=FX)["card_gone"], None)

    def test_a_batch_of_only_sold_cards_still_notifies(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock

        from pipeline import scheduler
        from pipeline.ingest import IngestResult, ListingEvent

        events = [ListingEvent("listing_gone", 7, "facebook", "42", changes=("sold",))]
        # On any run: an ended listing reaches only who saved or follows it.
        for first_run, last_run_at, called in ((False, None, True), (True, None, True), (True, "ayer", True)):
            notifier = MagicMock(on_matches=AsyncMock(), on_listing_events=AsyncMock(), deliver=AsyncMock())
            run = SimpleNamespace(target={"id": 1, "last_run_at": last_run_at}, first_run=first_run,
                                  result=IngestResult(events=list(events)))
            asyncio.run(scheduler.batch_handler(notifier)(run))
            self.assertEqual(notifier.on_listing_events.await_count, int(called), (first_run, last_run_at))
            notifier.on_matches.assert_not_awaited()
            notifier.deliver.assert_awaited_once()
        # A first run with nothing before still silences the price drops.
        drop = ListingEvent("price_drop", 8, "facebook", "43")
        notifier = MagicMock(on_matches=AsyncMock(), on_listing_events=AsyncMock(), deliver=AsyncMock())
        asyncio.run(scheduler.deliver_events(notifier, {"id": 1, "last_run_at": None}, [drop, *events],
                                             first_run=True))
        notifier.on_listing_events.assert_awaited_once_with(events)

    def test_the_repair_plan_of_marked_titles(self):
        from tools import repair_facebook as rf

        def row(i, title, price=12_500, **kw):
            return {"id": i, "source": "facebook", "external_id": str(i), "title": title, "description": None,
                    "make": "Ford", "model": "Ka", "year": 2015, "mileage_km": 90_000, "price": price,
                    "currency": "USD", "price_usd": price, "price_published": price,
                    "price_published_currency": "USD", "price_partial": False, "price_partial_reason": None,
                    "description_facts": None, "attributes": {"moneda": "USD"}, "n_matches": 0,
                    "watched": False, **kw}
        p = rf.plan([row(1, "Sold · 2015 Ford Ka SE"),
                     row(2, "Sold · 2015 Ford Ka SE", watched=True),
                     # A doubtful bare-"$" price: fixed before it ends (comparables count gone ones).
                     row(3, "Sold · 2015 Ford Ka SE", 600_000),
                     row(4, "Pending · Paragolpe delantero Ford Ka", year=None, mileage_km=None),
                     row(5, "Pending · 2014 Ford Ka SE"),
                     row(6, "Sold · Butacas Ford Ka", year=None, mileage_km=None)], FX)
        self.assertEqual(p.card_gone, [1, 3])
        self.assertEqual([lid for lid, _ in p.parts], [4, 6])
        self.assertEqual(p.doubtful, [3])
        self.assertEqual(p.titles, [(5, "Pending · 2014 Ford Ka SE", "2014 Ford Ka SE")])
        self.assertEqual(p.counts[("facebook", rf.CARD_WATCHED)], 1)

    def test_a_pending_card_stays_a_listing(self):
        card = parse_card("/marketplace/item/44/", "US$ 8.000\nPending · 2014 Ford fiesta kinetic\nRosario, SF")
        self.assertEqual((card.titulo, card.ubicacion), ("2014 Ford fiesta kinetic", "Rosario, SF"))
        self.assertEqual(normalize_listing(card, catalog=CATALOG, fx=FX)["card_gone"], None)


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
DOUBTFUL = [
    ("Ford ecosport porton trasero", 600_000, "Ford", "EcoSport"),
    ("FORD ECOSPORT 1.4 XLS 2008 ‼️RETÍRALO CON $900.000 Y CUOTAS FIJAS‼️", 900_000, "Ford", "EcoSport"),
    ("Chevrolet Onix tracker 1.0 1.2 tapa de cilindro", 500_000, "Chevrolet", "Onix"),
    ("Torpedo y centro de volante Chevrolet tracker sin detalles", 750_000, "Chevrolet", "Tracker"),
    ("4 Llantas Ford 16 pulgadas", 800_000, "Ford", None),
    ("TURBO COMPRSOR FORD", 650_000, "Ford", None),
    ("FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "Ford", "EcoSport"),           # 21327
    ("OPORTUNIDAD TAPA DE CILINDROS FORD 1.6", 220_000, "Ford", None),
    ("You", 111_111, None, None),
    ("2027 Volkswagen Polo", 285_000, "Volkswagen", "Polo"),
]
PARTS_BY_TITLE_SINCE_1107 = {"Torpedo y centro de volante Chevrolet tracker sin detalles",
                             "4 Llantas Ford 16 pulgadas"}
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
                # A «car» by its title, but for the two the words of 07/11/2026 know...
                self.assertEqual(row["not_vehicle"] is not None, title in PARTS_BY_TITLE_SINCE_1107)
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
