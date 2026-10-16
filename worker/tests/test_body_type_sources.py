"""Body type as each regional, agency and national source states it (docs/CARROCERIA.md).

Collectors pass the source's own label in Listing.carroceria and
normalization/body_type.py maps it. Coarse groups (deRuedas' segment,
RosarioGarage's rubro, Santa Fe's catalog) stay raw attributes and never
become a body type by themselves. Pure: no network or database.

The *_bodytype_* fixtures were captured on 2026-10-15 and trimmed.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

import httpx

from collectors import facebook, instagram, v6
from collectors._http import Page, soup
from collectors.autocity import AutocityScraper as Autocity
from collectors.autocosmos import AutoCosmosScraper as AutoCosmos
from collectors.carone import CarOneScraper as CarOne
from collectors.deruedas import DeRuedasScraper as DeRuedas
from collectors.gruporandazzo import GrupoRandazzoScraper as Randazzo
from collectors.mardelusados import MardelUsadosScraper as Mardel
from collectors.rosariogarage import RosarioGarageScraper
from collectors.usadossantafe import UsadosSantaFeScraper as SantaFe
from normalization import body_type as bt
from normalization.listing import normalize_listing
from seed_catalog import seed_catalog

FIXTURES = Path(__file__).parent / "fixtures" / "html"
AC_URL = "https://www.autocosmos.com.ar/auto/usado/ford/ecosport/s-15l/ba86b1d019c849fc9f8c07b0d5e1de16"
AUTOCITY_URL = "https://autocity.com.ar/catalogo/usados/m-renault/m-fluence/2-0-luxe-l15/"
CARONE_URL = "https://carone.com.ar/comprar/usados/ford-ka-1-5-s-plus-4p-l18-1"
RANDAZZO_URL = "https://www.gruporandazzo.com/ae074xf_8091-renault-sandero-stepway-ph2-1-6-zen----l19-2020/p"
SANTAFE_URL = "https://usadossantafe.com.ar/aviso/260922-0841-48K68"
V6_URL = "https://www.v6.com.ar/auto/ford-fiesta-kinetic-s-1-6-mt-5p-2015-8IAYEN5khz"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def normalized(item):
    """(body_type, attributes._body_type.method) as normalization stores them."""
    row = normalize_listing(item, catalog=seed_catalog())
    return row["body_type"], row["attributes"]["_body_type"]["method"]


def santafe_flight(records):
    payload = "2d:" + json.dumps(["$", "$L2e", None, {"avisosIniciales": records}])
    return "<script>self.__next_f.push(" + json.dumps([1, payload]) + ")</script>"


class V6Tests(unittest.TestCase):
    def test_detail_category_is_the_body_type(self):
        item = v6.parse_detail(fixture("v6_detail.html"), V6_URL).listing
        self.assertEqual(item.carroceria, "Hatchback")
        self.assertEqual(item.atributos["Categoría"], "Hatchback")
        self.assertEqual(normalized(item), ("hatchback", "source"))

    def test_cards_have_none(self):
        self.assertEqual({c.carroceria for c in v6.parse_search(fixture("v6_search.html"))}, {None})


class AutoCosmosTests(unittest.TestCase):
    def test_detail_reads_the_segment_from_the_head(self):
        item = AutoCosmos.parse_detail(fixture("autocosmos_bodytype_detail.html"), AC_URL).listing
        self.assertEqual(item.carroceria, "suv")
        self.assertEqual(normalized(item), ("suv", "source"))
        # Every other field reads the same as without the head.
        bare = AutoCosmos.parse_detail(fixture("autocosmos_detail.html"), AC_URL).listing
        self.assertIsNone(bare.carroceria)
        self.assertEqual({**item.to_dict(), "carroceria": None, "published_at": None},
                         {**bare.to_dict(), "published_at": None})

    def test_the_slimmed_raw_page_keeps_the_meta(self):
        full = fixture("autocosmos_bodytype_detail.html")
        slim = AutoCosmos().slim_page(Page(200, AC_URL, full))
        self.assertIn('name="dfp_segmentoNick"', slim)
        self.assertEqual(AutoCosmos.parse_detail(slim, AC_URL).listing.carroceria, "suv")

    def test_only_the_named_meta_counts(self):
        html = fixture("autocosmos_bodytype_detail.html")
        for content, expected in (("pick-up", "pick-up"), (" ", None)):
            with self.subTest(content):
                page = html.replace('content="suv"', f'content="{content}"')
                self.assertEqual(AutoCosmos.parse_detail(page, AC_URL).listing.carroceria, expected)
        other = html.replace('name="dfp_segmentoNick"', 'name="dfp_segmento"')
        self.assertIsNone(AutoCosmos.parse_detail(other, AC_URL).listing.carroceria)

    def test_every_site_segment_maps(self):
        # The ?s=N segments of /usados and their dfp_segmentoNick slugs.
        for nick, code in (("hatchback", "hatchback"), ("sedan", "sedan"), ("utilitario", "utilitario"),
                           ("monovolumen", "monovolumen"), ("convertible", "convertible"), ("suv", "suv"),
                           ("pick-up", "pickup"), ("coupe", "coupe")):
            with self.subTest(nick):
                self.assertEqual(bt.from_source(nick), code)
        # Segment 9's nick: a rural on Autocosmos, nothing anywhere else (Car One).
        self.assertEqual(bt.from_source("familiar", "autocosmos"), "rural")
        self.assertEqual(bt.resolve("Chevrolet", "Meriva", (), "familiar", None, "Chevrolet Meriva GL",
                                    listing_source="autocosmos"), ("rural", "source", "familiar"))


class CarOneTests(unittest.TestCase):
    def test_cards_carry_the_vehicle_type(self):
        items = CarOne.parse_search(fixture("carone_bodytype_search.html"))
        self.assertEqual([(i.modelo, i.carroceria) for i in items],
                         [("YARIS", "Hatchback"), ("Amarok", "Pick Up"), ("COMPASS", "SUV Plus"),
                          ("Prisma", "SEDAN")])
        self.assertEqual([normalized(i)[0] for i in items], ["hatchback", "pickup", "suv", "sedan"])

    def test_live_type_vocabulary_maps(self):
        # The catalog's body type facet on 2026-10-15 (all but "Familiar", 9 cars).
        for label, code in (("Hatchback", "hatchback"), ("Pick Up", "pickup"), ("Pick Up Liviana", "pickup"),
                            ("Sedan", "sedan"), ("SEDAN", "sedan"), ("Sedán Plus", "sedan"),
                            ("Suv", "suv"), ("Suv Plus", "suv"), ("Utilitario", "utilitario")):
            with self.subTest(label):
                self.assertEqual(bt.from_source(label), code)
        # "Familiar" (9 cars) is no body type: the docs keep it for Autocosmos only.
        self.assertIsNone(bt.from_source("Familiar", "carone"))
        self.assertEqual(bt.resolve("Chevrolet", "Meriva", (), "Familiar", None, "Chevrolet Meriva GL",
                                    listing_source="carone"), (None, "none", "Familiar"))

    def test_detail_and_its_raw_page(self):
        raw = fixture("carone_detail.html")
        item = CarOne.parse_detail(raw, CARONE_URL).listing
        self.assertEqual(item.carroceria, "SEDAN")
        slim = CarOne().slim_page(Page(200, CARONE_URL, raw))
        self.assertEqual(CarOne.parse_detail(slim, CARONE_URL).listing.carroceria, "SEDAN")
        # "FORD KA 1.5 S PLUS 4P" is the Ka+ sedán either way.
        self.assertEqual(normalized(item)[0], "sedan")

    def test_motorcycles_are_still_left_out(self):
        html = fixture("carone_search.html").replace('\\"label\\": \\"SEDAN\\"', '\\"label\\": \\"Moto\\"')
        self.assertEqual(CarOne.parse_search(html), [])


class RandazzoTests(unittest.TestCase):
    def items(self):
        records = json.loads(fixture("randazzo_bodytype_api.json"))
        return [Randazzo._listing(Randazzo._api_product(r, "ARS")) for r in records]

    def test_segment_letter_is_stripped(self):
        self.assertEqual([(i.modelo, i.carroceria) for i in self.items()],
                         [("KARDIAN", "Wagon (obsoleta)"), ("JEEP COMPASS", "SUV"), ("KANGOO", "Furgon"),
                          ("TITANO", "Pick-up 4x4"), ("STRADA", "Pick-up"), ("KA", "Sedan")])
        # The page's own label stays as it was.
        self.assertEqual(self.items()[3].atributos["Tipo de vehículo"], "Pick-up B 4x4")

    def test_real_body_types_map(self):
        compass, kangoo, titano, strada = self.items()[1:5]
        self.assertEqual([normalized(i)[0] for i in (compass, kangoo, titano, strada)],
                         ["suv", "utilitario", "pickup", "pickup"])

    def test_sedan_and_obsolete_wagon_labels_say_nothing(self):
        # SUVs go under "Wagon (obsoleta)" and hatchbacks under "Sedan": the
        # title, the doors and the catalog decide.
        kardian, ka = self.items()[0], self.items()[5]
        self.assertEqual(normalized(kardian), (None, "none"))
        self.assertNotEqual(normalized(ka)[0], "sedan")
        self.assertIsNone(bt.from_source("Wagon (obsoleta)", "gruporandazzo"))
        self.assertIsNone(bt.from_source("Sedan C", "gruporandazzo"))
        self.assertEqual(bt.from_source("SUV C", "gruporandazzo"), "suv")

    def test_a_sedan_label_on_a_hatchback_yields_to_the_catalog(self):
        # Randazzo files a Sandero Stepway under "Sedan"; the catalog knows only hatchbacks.
        item = Randazzo.parse_detail(fixture("randazzo_detail.html"), RANDAZZO_URL).listing
        self.assertEqual(item.carroceria, "Sedan")
        self.assertEqual(normalized(item), ("hatchback", "catalog"))

    def test_stored_raw_page_reads_the_same(self):
        slim = Randazzo().slim_page(Page(200, RANDAZZO_URL, fixture("randazzo_detail.html")))
        self.assertIn("eseauto-randazzo-product", slim)
        self.assertEqual(Randazzo.parse_detail(slim, RANDAZZO_URL).listing.carroceria, "Sedan")

    def test_without_the_specification(self):
        record = json.loads(fixture("randazzo_api_product.json"))
        record["allSpecifications"].remove("Tipo de vehículo")
        item = Randazzo._listing(Randazzo._api_product(record, "ARS"))
        self.assertIsNone(item.carroceria)
        self.assertEqual(normalized(item)[0], "pickup")         # Hilux: the catalog


class SantaFeTests(unittest.TestCase):
    def test_records_carry_tipo_and_doors(self):
        items = SantaFe.parse_search(fixture("usadossantafe_bodytype_search.html"))
        # The sold S-10 is left out.
        self.assertEqual([(i.modelo, i.carroceria, i.atributos.get("Puertas")) for i in items],
                         [("3008", "SUV", "5"), ("Hilux", "Pick Up", "4"), ("Amarok", "Pick Up", "2"),
                          ("Hilux SW4", "4x4", "5")])
        self.assertEqual([normalized(i) for i in items],
                         [("suv", "source"), ("pickup", "source"), ("pickup", "source"), ("suv", "catalog")])

    def test_every_live_vehicle_type_is_kept(self):
        base = {"id": "261001-0001-AAAA", "marca": "Chevrolet", "modelo": "S-10", "activo": True}
        for tipo, code in (("Pick Up", "pickup"), ("Pick Up de Trabajo", "pickup"), ("4x4", "pickup"),
                           ("Pickup", "pickup"), ("SUV", "pickup"), ("Camioneta", "pickup"),
                           ("Furgón", "pickup"), ("Utilitario", "pickup"), ("Auto", "pickup")):
            with self.subTest(tipo):
                [item] = SantaFe.parse_search(santafe_flight([{**base, "tipo": tipo}]))
                self.assertEqual(item.carroceria, tipo)
                # The S-10 is only a pick-up: the catalog wins over any label.
                self.assertEqual(normalized(item)[0], code)
        for tipo in ("Moto", "Lancha", "Cuatriciclo"):
            with self.subTest(tipo):
                self.assertEqual(SantaFe.parse_search(santafe_flight([{**base, "tipo": tipo}])), [])

    def test_coarse_tipo_is_no_body_type(self):
        record = {"id": "261001-0001-AAAA", "marca": "Fiat", "modelo": "Palio", "activo": True}
        for tipo in ("Auto", "Camioneta"):
            with self.subTest(tipo):
                [item] = SantaFe.parse_search(santafe_flight([{**record, "tipo": tipo}]))
                self.assertEqual(normalized(item), (None, "none"))      # Palio: hatchback or rural
        [doors] = SantaFe.parse_search(santafe_flight([{**record, "tipo": "Auto", "puertas": "5"}]))
        self.assertEqual(normalized(doors), ("hatchback", "doors"))
        [none] = SantaFe.parse_search(santafe_flight([{**record, "tipo": "Auto", "puertas": ""}]))
        self.assertNotIn("Puertas", none.atributos)

    def test_detail_record_and_json_ld(self):
        raw = fixture("usadossantafe_detail.html")
        item = SantaFe.parse_detail(raw, SANTAFE_URL).listing
        self.assertEqual(item.carroceria, "Auto")
        slim = SantaFe().slim_page(Page(200, SANTAFE_URL, raw))
        self.assertEqual(SantaFe.parse_detail(slim, SANTAFE_URL).listing.to_dict(), item.to_dict())
        doc = soup(raw)
        doc.select_one("#eseauto-vehicles").decompose()
        ld = SantaFe.parse_detail(str(doc), SANTAFE_URL).listing
        self.assertEqual(ld.carroceria, "Auto")                  # JSON-LD category
        self.assertEqual(normalized(ld)[0], "hatchback")         # Agile: the catalog

    def test_slim_page_keeps_the_doors(self):
        record = {"id": "260922-0841-48K68", "tipo": "Auto", "marca": "Chevrolet", "modelo": "Agile",
                  "puertas": "5", "activo": True, "userUID": "secret"}
        page = Page(200, SANTAFE_URL, "<html><body>" + santafe_flight([record]) + "</body></html>")
        slim = SantaFe().slim_page(page)
        self.assertIn('"puertas": "5"', slim)
        self.assertNotIn("secret", slim)


class SantaFeCatalogHintTests(unittest.IsolatedAsyncioTestCase):
    async def test_rendered_cards_remember_their_catalog_only_as_a_raw_attribute(self):
        initial = fixture("usadossantafe_search.html").replace("</body>", "<button>Cargar más avisos</button></body>")

        async def render(url):
            # The rendered cards, and one record the page still carries with its tipo.
            record = {"id": "261001-0001-AAAA", "tipo": "Pickup", "marca": "Ford", "modelo": "Ranger"}
            html = fixture("usadossantafe_render.html")
            return Page(200, url, html.replace("</body>", santafe_flight([record]) + "</body>"))

        collector = SantaFe(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=initial)),
                            render_catalog=AsyncMock(side_effect=render))
        items = await collector.search({})
        records = [i for i in items if i.carroceria]
        cards = [i for i in items if not i.carroceria]
        self.assertTrue(records and cards)
        self.assertTrue(all("Catálogo" not in i.atributos for i in records))
        # Both catalogs serve the same page here: the last one listed wins.
        self.assertEqual({i.atributos["Catálogo"] for i in cards}, {"Camionetas"})
        for item in cards:
            body, method = normalized(item)
            self.assertNotEqual(method, "source")
            self.assertNotEqual(body, "pickup")


class MardelTests(unittest.TestCase):
    def test_data_tipo_is_passed_raw(self):
        items = Mardel.parse_search(fixture("mardelusados_search.html"))
        self.assertEqual([i.carroceria for i in items], ["Auto", "Auto", "Auto"])
        # A coarse group: the catalog decides (Gol Trend, Classic, Compass).
        self.assertEqual([normalized(i) for i in items],
                         [("hatchback", "catalog"), ("sedan", "catalog"), ("suv", "catalog")])

    def test_utilitario_is_a_body_type_and_motorcycles_stay_out(self):
        html = fixture("mardelusados_search.html")
        doc = soup(html)
        doc.select("[data-veh]")[0]["data-tipo"] = "Utilitario"
        doc.select("[data-veh]")[1]["data-tipo"] = "Camioneta"
        first, second, _ = Mardel.parse_search(str(doc))
        self.assertEqual((first.carroceria, second.carroceria), ("Utilitario", "Camioneta"))
        self.assertEqual(bt.from_source(first.carroceria), "utilitario")
        self.assertIsNone(bt.from_source(second.carroceria))
        self.assertEqual(len(items := Mardel.parse_search(html)), 3)
        self.assertNotIn("Moto", {i.carroceria for i in items})


class AutocityTests(unittest.TestCase):
    def test_segment_of_the_spec_sheet(self):
        item = Autocity.parse_detail(fixture("autocity_bodytype_detail.html"), AUTOCITY_URL).listing
        self.assertEqual((item.carroceria, item.atributos["Puertas"]), ("Sedán", "4"))
        self.assertEqual(normalized(item)[0], "sedan")

    def test_summary_without_the_engine(self):
        html = fixture("autocity_bodytype_detail.html")
        doc = soup(html)
        for feature in doc.select(".feature-item"):
            if "Segmento" in feature.get_text():
                feature.decompose()
        self.assertEqual(Autocity.parse_detail(str(doc), AUTOCITY_URL).listing.carroceria, "Sedán")
        # The older fixture has no Segmento: "1.5 Hatchback | Usado | Nafta".
        old = Autocity.parse_detail(fixture("autocity_detail.html"), "https://autocity.com.ar/?p=95281").listing
        self.assertEqual(old.carroceria, "Hatchback")

    def test_engine_alone_is_no_body_type(self):
        # "2" alone would read as Autocosmos' segment 2 (sedán).
        doc = soup(fixture("autocity_bodytype_detail.html"))
        for feature in doc.select(".feature-item"):
            if "Segmento" in feature.get_text():
                feature.decompose()
        summary = doc.select_one(".firstOne")
        for text, expected in (("2 | Usado | Nafta", None), ("Usado | Nafta", None),
                               ("1.6 Pick Up | Usado | Diesel", "Pick Up"), ("Nafta", None)):
            with self.subTest(text):
                summary.string = text
                self.assertEqual(Autocity.parse_detail(str(doc), AUTOCITY_URL).listing.carroceria, expected)

    def test_the_slimmed_raw_page_reads_the_same(self):
        full = fixture("autocity_bodytype_detail.html")
        slim = Autocity().slim_page(Page(200, AUTOCITY_URL, full))
        a, b = (Autocity.parse_detail(h, AUTOCITY_URL).listing for h in (full, slim))
        self.assertEqual(a.to_dict(), b.to_dict())

    def test_cards_have_none(self):
        self.assertEqual({i.carroceria for i in Autocity.parse_search(fixture("autocity_search.html"))}, {None})


def rosario_results(ids, title="Ford Fiesta SE"):
    cards = "".join(
        f'<div class="box_aviso_base"><div class="box_aviso_tit">'
        f'<a href="/index.php?action=carro/showProduct&itmId={n}&rbrId=109">'
        f'<strong class="list_type_anuncio">{title}</strong>'
        '<span>MT</span><span>2018</span><span>Nafta</span><span>102.000 km.</span></a></div>'
        '<div class="precio">$ 17.700.000</div></div>' for n in ids)
    return f'<html><body><div id="item_results">{cards}</div></body></html>'


class RosarioGarageTests(unittest.IsolatedAsyncioTestCase):
    async def test_rubro_is_a_raw_attribute_only(self):
        rubros = {"Autos": "107", "Camionetas": "109"}

        def site(request):
            path = request.url.path.lstrip("/")
            if path in rubros:
                doc = soup(fixture("rosariogarage_search.html"))
                doc.select_one('#frm_buscador [name="rbrId"]')["value"] = rubros[path]
                return httpx.Response(200, text=str(doc))
            rubro = request.url.params.get("rbrId")
            if rubro == "107":
                return httpx.Response(200, text=rosario_results([1]))
            return httpx.Response(200, text=rosario_results([2, 1], "Toyota Hilux SRV"))

        collector = RosarioGarageScraper(transport=httpx.MockTransport(site))
        collector.CATEGORIES = ("Autos", "Camionetas")
        collector.PAGE_PAUSE_SECONDS = collector.RETRY_PAUSE_SECONDS = 0
        items = {i.listing_id: i for i in await collector.search({})}
        self.assertEqual({k: (v.atributos["Rubro"], v.carroceria) for k, v in items.items()},
                         {"1": ("Autos", None), "2": ("Camionetas", None)})
        # "Camionetas" says nothing: a Fiesta filed there would still be unknown.
        fiesta = items["1"]
        fiesta.atributos["Rubro"] = "Camionetas"
        self.assertEqual(normalized(fiesta), (None, "none"))
        self.assertEqual(normalized(items["2"]), ("pickup", "catalog"))


class DeRuedasTests(unittest.TestCase):
    def test_segment_is_a_raw_attribute_only(self):
        items = DeRuedas.parse_search(fixture("deruedas_search.html"), 1)
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item.atributos["Segmento"], "Utilitarios y Camionetas")
            self.assertIsNone(item.carroceria)
            self.assertNotEqual(normalized(item)[1], "source")
        self.assertIsNone(bt.raw_from_attributes(items[0].atributos))


class NothingStructuredTests(unittest.TestCase):
    def test_facebook_and_instagram_leave_it_to_the_title_and_catalog(self):
        fb = facebook.parse_detail(fixture("facebook_detail.html"),
                                   "https://www.facebook.com/marketplace/item/123456789/").listing
        sc = instagram.SCClasificadosScraper.parse_detail(
            fixture("instagram_sc_detail.html"), "https://www.instagram.com/sc_clasificados/p/Ddtw2eVlgWL/").listing
        self.assertEqual((fb.carroceria, sc.carroceria), (None, None))
        # "2017 Ford Fiesta Titanium": hatchback or sedán, nothing says which.
        self.assertEqual(normalized(fb), (None, "none"))


class ParserVersionTests(unittest.TestCase):
    def test_changed_detail_parsers_are_reparsed(self):
        # tools.reprocess --raw --outdated re-reads raw pages saved before
        # these collectors read the body type.
        for scraper, version in ((v6.V6Scraper, 3), (AutoCosmos, 3), (CarOne, 2), (Randazzo, 2),
                                 (SantaFe, 2), (Autocity, 2)):
            with self.subTest(scraper.name):
                self.assertGreaterEqual(scraper.DETAIL_PARSER_VERSION, version)


if __name__ == "__main__":
    unittest.main()
