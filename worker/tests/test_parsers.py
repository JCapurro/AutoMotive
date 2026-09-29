"""Search and detail parsers against saved HTML (tests/fixtures/html).

The fixtures are real pages captured on 2026-09-27, trimmed to the markup the
parsers read, except facebook_detail.html, which is synthetic (see its header).
"""
from __future__ import annotations

import unittest
from pathlib import Path

from collectors import autocosmos, facebook, kavak, mercadolibre, v6
from collectors._http import Page
from db.repos import raw_pages

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class MercadoLibreParserTests(unittest.TestCase):
    def test_search_cards(self):
        cards = mercadolibre.parse_search(html("mercadolibre_search.html"))

        self.assertEqual(len(cards), 3)
        c = cards[0]
        self.assertEqual((c.listing_id, c.titulo), ("MLA1772799859", "Toyota Corolla Cross 1.8 Hev Xei Ecvt"))
        self.assertEqual((c.precio, c.moneda, c.anio, c.km), (48_300_000.0, "ARS", 2025, 12_500))
        self.assertEqual(c.ubicacion, "Del Viso - Bs.As. G.B.A. Norte")
        self.assertTrue(c.url.startswith("https://auto.mercadolibre.com.ar/MLA-1772799859"))
        self.assertNotIn("#", c.url)
        self.assertEqual(len(c.imagenes), 1)
        # The card doesn't state make/model: normalization resolves them from the title.
        self.assertIsNone(c.marca)

    def test_detail(self):
        url = "https://auto.mercadolibre.com.ar/MLA-1675249827-toyota-corolla-cross-18-hev-seg-ecvt-_JM"
        d = mercadolibre.parse_detail(html("mercadolibre_detail.html"), url)

        self.assertFalse(d.gone)
        l = d.listing
        self.assertEqual(l.listing_id, "MLA1675249827")
        self.assertEqual((l.marca, l.modelo, l.version), ("Toyota", "Corolla Cross", "1.8 Hev Seg Ecvt"))
        self.assertEqual((l.anio, l.km, l.precio, l.moneda), (2026, 0, 59_862_960.0, "ARS"))
        self.assertEqual((l.transmision, l.combustible), ("Automática", "Híbrido"))
        self.assertEqual(l.vendedor, "concesionaria")
        self.assertEqual(l.vendedor_nombre, "Toyota Jorge Ferro")
        self.assertGreater(len(l.imagenes), 3)
        self.assertIn("TOYOTA COROLLA SEG HIBRIDO", l.descripcion)
        self.assertEqual(l.atributos["Tipo de carrocería"], "SUV")
        self.assertIsNotNone(l.published_at)       # "Publicado hace 7 meses"

    def test_detail_gone(self):
        self.assertEqual(mercadolibre.parse_detail("", "u", status=404).gone_reason, "404")
        paused = "<html><body><p>Publicación pausada</p></body></html>"
        self.assertTrue(mercadolibre.parse_detail(paused, "u").gone)

    def test_security_challenge_is_a_wall(self):
        self.assertTrue(mercadolibre._looks_like_login_wall(
            "https://www.mercadolibre.com.ar/gz/x",
            "Por seguridad, completá este paso. Continuar. No puedo resolver el desafío"))


class V6ParserTests(unittest.TestCase):
    def test_search_cards(self):
        cards = v6.parse_search(html("v6_search.html"))

        self.assertEqual([c.listing_id for c in cards], ["8IAYEN5khz", "piXYZWZtXh"])
        c = cards[0]
        self.assertEqual((c.titulo, c.version), ("Ford Fiesta Kinetic S 1.6 Mt 5p", "S 1.6 Mt 5p"))
        self.assertEqual((c.precio, c.moneda, c.anio, c.km), (11_490_000.0, "ARS", 2015, 206_500))
        self.assertEqual((c.transmision, c.combustible), ("Manual", "Nafta"))
        self.assertEqual(c.ubicacion, "Parque Chas, Capital Federal")
        self.assertIsNotNone(c.published_at)

    def test_detail(self):
        url = "https://www.v6.com.ar/auto/ford-fiesta-kinetic-s-1-6-mt-5p-2015-8IAYEN5khz"
        l = v6.parse_detail(html("v6_detail.html"), url).listing

        self.assertEqual(l.listing_id, "8IAYEN5khz")
        self.assertEqual((l.marca, l.modelo, l.version), ("Ford", "Fiesta Kinetic", "S 1.6 MT 5P"))
        self.assertEqual((l.anio, l.km, l.precio, l.moneda), (2015, 206_500, 11_490_000.0, "ARS"))
        self.assertEqual((l.transmision, l.combustible, l.vendedor), ("MT", "Nafta", "Particular"))
        self.assertIn("distribución completa", l.descripcion)
        self.assertEqual(len(l.imagenes), 5)

    def test_missing_vehicle_is_gone(self):
        self.assertTrue(v6.parse_detail(html("v6_missing.html"), "u").gone)


class KavakParserTests(unittest.TestCase):
    def test_search_cards_use_the_car_id(self):
        cards = kavak.parse_search(html("kavak_search.html"))

        self.assertEqual(len(cards), 3)
        c = cards[0]
        self.assertEqual(c.listing_id, "549997")
        self.assertTrue(c.url.endswith("/ar/venta/ford-fiesta_kinetic_design-16_se-hatchback-2018?id=549997"))
        self.assertEqual((c.marca, c.modelo, c.version, c.transmision),
                         ("Ford", "Fiesta Kinetic Design", "1.6 SE", "Manual"))
        self.assertEqual((c.anio, c.km, c.precio, c.moneda), (2018, 106_000, 16_110_000.0, "ARS"))
        self.assertEqual((c.vendedor, c.ubicacion), ("concesionaria", "Buenos Aires"))

    def test_promotion_cards_take_the_current_price(self):
        # Text of a live card (2026-09-27): struck-through "desde" price, then the current one.
        promo = ('<a data-testid="card-product-547027" href="https://www.kavak.com/ar/venta/'
                 'ford-fiesta_kinetic_design-16_titanium-sedan-2016"><span>Precio financiando 50%</span>'
                 '<h3>Ford • Fiesta Kinetic Design</h3><p>2016 • 80.000 km • 1.6 TITANIUM • Manual</p>'
                 '<span>Precio desde</span><s>$\xa015.100.000</s><span>$</span><span>14.791.000</span>'
                 '<span>Buenos Aires</span></a>')
        [c] = kavak.parse_search(promo)
        self.assertEqual((c.precio, c.moneda, c.ubicacion), (14_791_000.0, "ARS", "Buenos Aires"))

    def test_detail(self):
        url = "https://www.kavak.com/ar/venta/ford-fiesta_kinetic_design-16_se-hatchback-2018?id=549997"
        d = kavak.parse_detail(html("kavak_detail.html"), url)

        self.assertFalse(d.gone)
        l = d.listing
        self.assertEqual((l.listing_id, l.version, l.transmision, l.combustible),
                         ("549997", "SE", "Manual", "Nafta"))
        self.assertEqual((l.km, l.precio, l.ubicacion), (106_000, 16_110_000.0, "Buenos Aires"))
        self.assertTrue(l.imagenes)
        self.assertFalse(any("BANNER" in i.upper() for i in l.imagenes))

    def test_sold_car_serves_another_one(self):
        url = "https://www.kavak.com/ar/venta/ford-fiesta_kinetic_design-16_se-hatchback-2018?id=549997"
        d = kavak.parse_detail(html("kavak_other_car.html"), url)
        self.assertTrue(d.gone)
        # Same slug but another car id on the page is also a different car.
        other = url.replace("549997", "549998")
        self.assertTrue(kavak.parse_detail(html("kavak_detail.html"), other).gone)


class AutoCosmosParserTests(unittest.TestCase):
    def test_search_cards_flag_down_payment_prices(self):
        cards = autocosmos.AutoCosmosScraper.parse_search(html("autocosmos_search.html"))

        self.assertEqual(len(cards), 3)
        full, anticipo = cards[0], cards[2]
        self.assertFalse(full.price_partial)
        self.assertTrue(full.marca and full.modelo and full.anio and full.precio)
        self.assertNotIn("  ", full.titulo)
        self.assertTrue(anticipo.price_partial)
        self.assertEqual(anticipo.price_partial_reason, "anticipo (autocosmos)")

    def test_detail(self):
        url = ("https://www.autocosmos.com.ar/auto/usado/ford/ecosport/s-15l/"
               "ba86b1d019c849fc9f8c07b0d5e1de16")
        l = autocosmos.AutoCosmosScraper.parse_detail(html("autocosmos_detail.html"), url).listing

        self.assertEqual(l.listing_id, "ba86b1d019c849fc9f8c07b0d5e1de16")
        self.assertEqual((l.marca, l.modelo, l.version), ("Ford", "EcoSport", "S 1.5L"))
        self.assertEqual((l.anio, l.km), (2018, 101_000))
        self.assertEqual((l.transmision, l.combustible), ("manual 5 velocidades", "nafta"))
        self.assertEqual((l.vendedor, l.vendedor_nombre), ("concesionaria", "San Vicente Automotores"))
        self.assertEqual(l.ubicacion, "Banfield, Buenos Aires (A.M.B.A.)")
        self.assertTrue(l.price_partial)          # only "Anticipo" is published
        self.assertIn("Test Drive", l.descripcion)
        self.assertTrue(all("/Large/" in i for i in l.imagenes))

    def test_404_is_gone(self):
        self.assertTrue(autocosmos.AutoCosmosScraper.parse_detail("", "u", 404).gone)


class FacebookParserTests(unittest.TestCase):
    def test_card(self):
        c = facebook.parse_card("/marketplace/item/123456789/?ref=search",
                                "$10.300\n2017 Ford Fiesta Titanium\nVicente López, BA\n112 mil km")

        self.assertEqual((c.listing_id, c.url), ("123456789", "https://www.facebook.com/marketplace/item/123456789/"))
        self.assertEqual((c.precio, c.moneda, c.anio, c.km), (10_300.0, "USD", 2017, 112_000))
        self.assertEqual(c.ubicacion, "Vicente López, BA")
        self.assertIsNone(c.marca)

    def test_detail(self):
        url = "https://www.facebook.com/marketplace/item/123456789/"
        l = facebook.parse_detail(html("facebook_detail.html"), url).listing

        self.assertEqual((l.listing_id, l.titulo), ("123456789", "2017 Ford Fiesta Titanium"))
        self.assertEqual((l.precio, l.moneda, l.anio, l.km), (10_300.0, "USD", 2017, 112_000))
        self.assertEqual((l.transmision, l.combustible), ("manual", "Nafta"))
        self.assertEqual((l.ubicacion, l.vendedor, l.vendedor_nombre),
                         ("Vicente López, BA", "particular", "Vendedor Ejemplo"))
        self.assertEqual(l.descripcion.splitlines()[1], "Distribución hecha a los 100.000 km. VTV vigente.")
        self.assertEqual(len(l.imagenes), 3)
        self.assertIsNotNone(l.published_at)

    def test_detail_gone(self):
        page = "<div role='main'><span>Este artículo ya no está disponible</span></div>"
        self.assertTrue(facebook.parse_detail(page, "https://www.facebook.com/marketplace/item/1/").gone)

    def test_description_stops_before_the_page_around_it(self):
        # Not expanded ("Ver más"), then the map and the ads Facebook suggests, with their prices.
        page = """<div role='main'><h1><span>2018 Ford Fiesta Kinetic</span></h1><span>$10.900</span>
          <h2><span>Descripción del vendedor</span></h2>
          <span>-PROMOCION DE CONTADO U$s10.900</span><span>-PRECIO DE PERMUTA U$s11.500</span>
          <span>Ver más fotos en Instagram</span>
          <span>Ver más</span><span>Ciudad de Buenos Aires, CF</span><span>· La ubicación es aproximada</span>
          <span>Enviar mensaje</span><span>Sugerencias de hoy</span><span>$6.900.000</span>
          <span>2001 Peugeot 306 1.9 xrd</span></div>"""
        l = facebook.parse_detail(page, "https://www.facebook.com/marketplace/item/9/").listing
        self.assertEqual(l.descripcion, "-PROMOCION DE CONTADO U$s10.900\n-PRECIO DE PERMUTA U$s11.500\n"
                                        "Ver más fotos en Instagram")


    def test_suggested_ads_never_lend_their_price_or_words(self):
        page = """<div role='main'><h1><span>2020 Ford Ka S</span></h1><span>Consultá precio</span>
          <h2><span>Descripción del vendedor</span></h2><span>Consultá precio y coordinamos.</span>
          <img src="https://scontent.example.fbcdn.net/own.jpg">
          <span>Sugerencias de hoy</span><span>$6.900.000</span><span>2001 Peugeot 306 1.9 xrd</span>
          <img src="https://scontent.example.fbcdn.net/peugeot.jpg"><span>Concesionaria Ejemplo</span></div>"""
        l = facebook.parse_detail(page, "https://www.facebook.com/marketplace/item/9/").listing
        self.assertEqual((l.precio, l.moneda, l.vendedor), (None, None, "particular"))
        self.assertEqual(l.imagenes, ["https://scontent.example.fbcdn.net/own.jpg"])


class RawPageTests(unittest.TestCase):
    """raw_pages keep a slimmed page: every parser reads the same from it."""

    CASES = [
        (mercadolibre.MercadoLibreScraper, "mercadolibre_detail.html",
         "https://auto.mercadolibre.com.ar/MLA-1675249827-toyota-corolla-cross-18-hev-seg-ecvt-_JM"),
        (v6.V6Scraper, "v6_detail.html", "https://www.v6.com.ar/auto/ford-fiesta-kinetic-s-1-6-mt-5p-2015-8IAYEN5khz"),
        (kavak.KavakScraper, "kavak_detail.html",
         "https://www.kavak.com/ar/venta/ford-fiesta_kinetic_design-16_se-hatchback-2018?id=549997"),
        (autocosmos.AutoCosmosScraper, "autocosmos_detail.html",
         "https://www.autocosmos.com.ar/auto/usado/ford/ecosport/s-15l/ba86b1d019c849fc9f8c07b0d5e1de16"),
        (facebook.FacebookMarketplaceScraper, "facebook_detail.html",
         "https://www.facebook.com/marketplace/item/123456789/"),
    ]

    def test_the_slimmed_page_parses_the_same(self):
        for cls, name, url in self.CASES:
            with self.subTest(cls.name):
                scraper = cls()
                full = html(name)
                slim = scraper.slim_page(Page(200, url, full))
                self.assertLessEqual(len(slim), len(full))
                a, b = scraper.parse_detail(full, url), scraper.parse_detail(slim, url)
                self.assertEqual(a.gone, b.gone)
                da, db = a.listing.to_dict(), b.listing.to_dict()
                da.pop("published_at"), db.pop("published_at")      # "hace 2 días" is relative to now
                self.assertEqual(da, db)
                self.assertEqual(raw_pages.decompress(raw_pages.compress(slim)), slim)


if __name__ == "__main__":
    unittest.main()
