"""Body type (docs/CARROCERIA.md): mapping, inference, matching and backfill. Pure: no network or DB."""
from __future__ import annotations

import asyncio
import unittest
from collections import Counter
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from collectors.base import BaseScraper, Listing
from db.repos.listings import COLUMNS
from intelligence import copy
from intelligence.matching import evaluate, malformed_vehicle, match, model_less
from normalization import body_type as bt
from normalization.listing import KEY_ATTRS, Target, attrs_hash, normalize_listing, stored_body_type
from normalization.vehicle import CatalogModel
from pipeline import ingest as ingest_module
from pipeline.ingest import _DESCRIPTIVE, IngestConfig, IngestResult, merge
from tools import backfill_body_type as backfill
from tools.reprocess import recompute


CATALOG = [
    CatalogModel("Toyota", "Etios", ("etios cross",), ("X", "XS", "XLS"), body_types=("sedan", "hatchback")),
    CatalogModel("Toyota", "Corolla", (), ("XEI", "SEG"), body_types=("sedan",)),
    CatalogModel("Toyota", "Corolla Cross", (), ("XEI", "SEG"), body_types=("suv",)),
    CatalogModel("Toyota", "Hilux", (), ("SR", "SRX"), body_types=("pickup",)),
    CatalogModel("Toyota", "SW4", ("sw 4", "hilux sw4"), ("SRX",), body_types=("suv",)),
    CatalogModel("Chevrolet", "Spin", (), ("LTZ",), body_types=("monovolumen",)),
    CatalogModel("Renault", "Sandero", (), (), body_types=("hatchback",)),
    CatalogModel("Renault", "Duster", ("duster oroch",), (), body_types=("suv", "pickup")),
    CatalogModel("Fiat", "Palio", ("palio weekend",), (), body_types=("hatchback", "rural")),
    CatalogModel("Volkswagen", "Gol", (), (), body_types=("hatchback", "rural")),
    CatalogModel("Hyundai", "HB20", ("hb 20",), (), body_types=("hatchback", "sedan")),
    CatalogModel("Ford", "Ka", ("ka+", "ka plus"), ("S", "SE", "SEL"), body_types=("hatchback", "sedan")),
    CatalogModel("Ford", "Fiesta", (), ("S", "SE", "Titanium"), body_types=("hatchback", "sedan")),
    CatalogModel("Citroën", "C4", (), (), body_types=("hatchback", "sedan")),
    CatalogModel("Ford", "Focus", (), ()),                         # body types not loaded yet
]


def _entry(make: str, model: str) -> tuple[str, ...]:
    return next(m.body_types for m in CATALOG if (m.make, m.model) == (make, model))


def resolve(make, model, title=None, *, source=None, trim=None, url=None, doors=None, site=None):
    return bt.resolve(make, model, _entry(make, model) if make else (), source, trim, title, url,
                      doors_value=doors, listing_source=site)


class ContractTests(unittest.TestCase):
    def test_codes_and_labels(self):
        self.assertEqual(bt.CODES, ("sedan", "hatchback", "suv", "pickup", "rural", "monovolumen",
                                    "coupe", "convertible", "utilitario"))
        self.assertEqual(list(bt.LABELS), list(bt.CODES))
        self.assertEqual([bt.LABELS[c] for c in bt.CODES],
                         ["Sedán", "Hatchback", "SUV", "Pick-up", "Rural", "Monovolumen", "Coupé",
                          "Convertible", "Utilitario"])
        self.assertEqual(copy.BODY_TYPE, bt.LABELS)

    def test_no_code_is_part_of_another(self):
        for a in bt.CODES:
            for b in bt.CODES:
                if a != b:
                    self.assertNotIn(a, b)

    def test_listing_and_target_carry_it(self):
        item = Listing("kavak", "1", "Ford Fiesta", "u", carroceria="hatchback")
        self.assertEqual(item.to_dict()["carroceria"], "hatchback")
        self.assertIsNone(Listing("kavak", "1", "Ford Fiesta", "u").carroceria)
        self.assertEqual(Target("Ford", "Fiesta"), Target("Ford", "Fiesta", None))
        self.assertEqual(Target(body_type="suv").body_type, "suv")
        self.assertEqual(BaseScraper.BODY_TYPES, frozenset())


class FromSourceTests(unittest.TestCase):
    def test_mercadolibre_names_and_ids(self):
        names = {"Sedán": "sedan", "Hatchback": "hatchback", "SUV": "suv", "Crossover": "suv",
                 "Off-Road": "suv", "Pick-Up": "pickup", "Rural": "rural", "Monovolumen": "monovolumen",
                 "Minivan": "monovolumen", "Coupé": "coupe", "Cabriolet": "convertible",
                 "Roadster": "convertible", "Furgón": "utilitario", "Van": "utilitario"}
        for raw, code in names.items():
            self.assertEqual(bt.from_source(raw), code, raw)
        ids = {"452758": "sedan", "479344": "hatchback", "452759": "suv", "452761": "suv",
               "452754": "suv", "452756": "pickup", "452760": "rural", "452752": "monovolumen",
               "452753": "monovolumen", "452749": "coupe", "452748": "convertible",
               "452757": "convertible", "452750": "utilitario", "452755": "utilitario"}
        for raw, code in ids.items():
            self.assertEqual(bt.from_source(raw), code, raw)
        self.assertEqual(bt.from_source(452759), "suv")
        self.assertIsNone(bt.from_source("Light Truck"))
        self.assertIsNone(bt.from_source("452751"))

    def test_kavak_slugs(self):
        slugs = {"sedan": "sedan", "hatchback": "hatchback", "suv": "suv", "pickup": "pickup",
                 "pick-up": "pickup", "minivan": "monovolumen", "monovolumen": "monovolumen",
                 "wagon": "rural", "rural": "rural", "coupe": "coupe", "cabriolet": "convertible",
                 "convertible": "convertible", "furgon": "utilitario", "van": "utilitario"}
        for raw, code in slugs.items():
            self.assertEqual(bt.from_source(raw), code, raw)
        for raw in ("camioneta", "comercial-todoterreno", "lado-de-caida", "light-truck", "algo-nuevo"):
            self.assertIsNone(bt.from_source(raw), raw)

    def test_autocosmos_segments(self):
        segments = ["hatchback", "sedan", "utilitario", "monovolumen", "convertible", "suv",
                    "pickup", "coupe", "rural"]
        for n, code in enumerate(segments, start=1):
            self.assertEqual(bt.from_source(str(n)), code)
        self.assertEqual(bt.from_source("pick-up"), "pickup")         # dfp_segmentoNick
        # "Familiar" is a rural only on Autocosmos (segment 9).
        self.assertEqual(bt.from_source("Familiar", "autocosmos"), "rural")
        self.assertIsNone(bt.from_source("Familiar"))

    def test_agency_labels(self):
        self.assertEqual(bt.from_source("SEDAN"), "sedan")             # Car One
        self.assertEqual(bt.from_source("Pick-up B"), "pickup")        # Randazzo, segment suffix
        self.assertEqual(bt.from_source("Sedan C"), "sedan")
        self.assertEqual(bt.from_source("1.5 Hatchback"), "hatchback")  # Autocity's .firstOne
        self.assertEqual(bt.from_source("Pickup"), "pickup")           # Usados Santa Fe
        self.assertEqual(bt.from_source("Utilitario"), "utilitario")   # Santa Fe, Mardel
        for raw in ("Auto", "Camioneta", "Moto", "", None, "   "):
            self.assertIsNone(bt.from_source(raw), raw)

    def test_codes_pass_through(self):
        for code in bt.CODES:
            self.assertEqual(bt.from_source(code), code)

    def test_raw_attributes(self):
        self.assertEqual(bt.raw_from_attributes({"Tipo de carrocería": "SUV", "Puertas": "5"}), "SUV")
        self.assertEqual(bt.raw_from_attributes({"bodyType": "Hatchback"}), "Hatchback")
        self.assertEqual(bt.raw_from_attributes({"Categoría": "Sedán"}), "Sedán")
        self.assertEqual(bt.raw_from_attributes({"Tipo de vehículo": "Pick-up B"}), "Pick-up B")
        self.assertIsNone(bt.raw_from_attributes({"Segmento": "Autos"}))
        self.assertIsNone(bt.raw_from_attributes(None))


class KeywordTests(unittest.TestCase):
    def explicit(self, text, make=None, model=None):
        hit = bt.explicit(make, model, text)
        return hit[0] if hit else None

    def test_body_words(self):
        cases = {
            "Etios 1.5 Sedán XLS": "sedan", "Cruze 1.4 LTZ Hatch": "hatchback",
            "A3 Sportback 1.4": "hatchback", "Ranger XLT 3.2 D/C 4x4": "pickup",
            "Strada Adventure Cabina Doble": "pickup", "S10 cabina simple": "pickup",
            "Saveiro Pick-Up": "pickup", "Kangoo Furgón 1.6": "utilitario",
            "Berlingo Multispace": "monovolumen", "Partner Patagónica": "monovolumen",
            "Peugeot 206 SW 1.6": "rural", "Palio Weekend": "rural", "Vento Variant": "rural",
            "Golf Sportwagen": "rural", "Corsa Wagon": "rural", "Civic Coupé": "coupe",
            "Mini Cooper Cabrio": "convertible", "Nivus SUV Coupé": "suv",
            "Duster Oroch 2.0": "pickup", "C4 Grand Picasso": "monovolumen",
            "Ranger XLT 3.2 C/D 4x4": "pickup", "Hilux 2.4 C/S DX": "pickup",
            "Etios Sedán 4p": "sedan", "Audi A5 Sportback": "hatchback",
            # The coupé versions of SUVs are SUVs.
            "Mercedes-Benz GLC 300 Coupé": "suv", "BMW X6 xDrive35i M-Sport Coupé": "suv",
            "Audi Q3 Sportback 35 TFSI": "suv",
        }
        for text, code in cases.items():
            self.assertEqual(self.explicit(text), code, text)

    def test_traps(self):
        for text in ("Toyota Hilux SW4 2.8 SRX", "Hilux SW 4 SRX",       # SW4 is not an SW
                     "Hyundai HB20 1.6", "Hyundai HB 20 1.6",              # HB inside HB20
                     "Hilux 2.8 CD radio", "Gol Trend CD",                 # CD is the radio
                     "Etios Cross 1.5", "Suran Cross", "Corolla Cross XEI",  # Cross is not an SUV
                     "Amarok 4x4", "Jeep Compass", "camioneta impecable",  # say nothing
                     "Kangoo familiar", "Hilux uso rural", "Suzuki Wagon R",
                     "Fiesta 1.6 5p",                                      # doors are not a keyword
                     "Gol 1.6 Sedán 5p", "Uno 3 puertas sedan",            # old Argentine for a hatch
                     "Gol Trend c/service oficiales"):
            self.assertIsNone(self.explicit(text), text)

    def test_submodels(self):
        cases = [
            (("Renault", "Duster"), "Renault Duster Oroch", "pickup"),
            (("Fiat", "Palio"), "Fiat Palio Weekend Adventure", "rural"),
            (("Fiat", "Palio"), "Fiat Palio 1.6 Adventure Pack Seguridad", "rural"),
            (("Ford", "Ka"), "Ford Ka 2021 1.5 S Plus 4p", "sedan"),
            (("Peugeot", "206"), "Peugeot 206 2.0 CC", "convertible"),
            (("Volkswagen", "Gol"), "VW Gol Country 1.6", "rural"),
            (("Citroën", "C4"), "Citroen C4 Grand Picasso", "monovolumen"),
            (("Chevrolet", "Onix"), "Chevrolet Onix Joy Plus", "sedan"),
            (("Ford", "Ka"), "Ford Ka+ 1.5 SEL", "sedan"),
            (("Ford", "Ka"), "Ford Ka Plus SE", "sedan"),
            (("Toyota", "Etios"), "Toyota Etios Cross 1.5", "hatchback"),
            (("Toyota", "Hilux"), "Toyota Hilux SW4", "suv"),
            (("Hyundai", "HB20"), "Hyundai HB20S 1.6", "sedan"),
            (("Fiat", "Uno"), "Fiat Uno Cargo 1.4", "utilitario"),
            (("BMW", "Serie 3"), "BMW 320i Touring", "rural"),
            (("Audi", "A4"), "Audi A4 Avant", "rural"),
        ]
        for (make, model), text, code in cases:
            self.assertEqual(self.explicit(text, make, model), code, text)
        # A submodel word only means it for its own model.
        self.assertIsNone(self.explicit("Honda CR-V Touring", "Honda", "CR-V"))
        self.assertIsNone(self.explicit("Corolla Cross", "Toyota", "Corolla Cross"))
        self.assertIsNone(self.explicit("Chevrolet Tracker Plus", "Chevrolet", "Tracker"))
        self.assertIsNone(self.explicit("Fiat Strada Adventure", "Fiat", "Strada"))
        self.assertIsNone(self.explicit("Peugeot 206 XR 1600 cc", "Peugeot", "206"))

    def test_doors(self):
        self.assertEqual(bt.doors("Etios 1.5 4ptas XLS"), 4)
        self.assertEqual(bt.doors("S 1.6 MT 5P"), 5)
        self.assertEqual(bt.doors("1.6 16v 3 puertas"), 3)
        self.assertEqual(bt.doors(None, "Gol 1.4 5 pts"), 5)
        self.assertIsNone(bt.doors("7 plazas, 5 pasajeros"))
        self.assertIsNone(bt.doors("1.5p"))

    def test_url_words(self):
        self.assertEqual(bt.url_words("https://www.kavak.com/ar/venta/ford-fiesta_kinetic_design-16_se-hatchback-2018"),
                         "ar venta ford fiesta kinetic design 16 se hatchback 2018")
        self.assertEqual(bt.url_words(None), "")


class ResolveTests(unittest.TestCase):
    def test_explicit_words_win_over_everything(self):
        self.assertEqual(resolve("Renault", "Duster", "Renault Duster Oroch 2.0", source="SUV"),
                         ("pickup", "keyword", "oroch"))
        self.assertEqual(resolve("Toyota", "Corolla", "Toyota Corolla Sedán"),
                         ("sedan", "keyword", "sedan"))
        self.assertEqual(resolve("Ford", "Ka", "Ford Ka+ 1.5 SEL", source="Hatchback"),
                         ("sedan", "submodel", "ka+"))
        # The version is read before the title.
        self.assertEqual(resolve("Fiat", "Palio", "Fiat Palio 1.4", trim="Weekend Adventure")[0], "rural")

    def test_source_value_within_the_catalog(self):
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios XLS", source="Hatchback"),
                         ("hatchback", "source", "Hatchback"))
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios XLS", source="452758"),
                         ("sedan", "source", "452758"))

    def test_single_body_type_catalog_beats_noisy_sources(self):
        # Mercado Libre labels the Spin an SUV; Randazzo a Sandero "Sedan".
        self.assertEqual(resolve("Chevrolet", "Spin", "Chevrolet Spin 1.8 LTZ", source="SUV"),
                         ("monovolumen", "catalog", "SUV"))
        self.assertEqual(resolve("Renault", "Sandero", "Renault Sandero Stepway", source="Sedan"),
                         ("hatchback", "catalog", "Sedan"))
        self.assertEqual(resolve("Toyota", "Hilux", "Toyota Hilux SRX", source="Pick-up B"),
                         ("pickup", "source", "Pick-up B"))

    def test_source_outside_a_multi_body_catalog_is_set_aside(self):
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios XLS", source="SUV"),
                         (None, "none", "SUV"))
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios XLS 5p", source="SUV"),
                         ("hatchback", "doors", "5p"))

    def test_unknown_model_keeps_the_source_value(self):
        self.assertEqual(bt.resolve("Chery", "Tiggo 4", (), "SUV", None, "Chery Tiggo 4 Pro"),
                         ("suv", "source", "SUV"))
        self.assertEqual(bt.resolve(None, None, (), "452756", None, "Oportunidad"),
                         ("pickup", "source", "452756"))
        self.assertEqual(bt.resolve(None, None, (), "Camioneta", None, "Jeep Compass"),
                         (None, "none", "Camioneta"))
        # A catalog model whose body types aren't loaded counts as unknown.
        self.assertEqual(resolve("Ford", "Focus", "Ford Focus", source="Sedán")[0], "sedan")

    def test_doors_only_choose_within_the_catalog(self):
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios 1.5 XLS 4ptas"), ("sedan", "doors", "4p"))
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios 1.5 XLS 5p"), ("hatchback", "doors", "5p"))
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios 1.5", doors="5"), ("hatchback", "doors", "5p"))
        # The spec table's "Puertas" is read before the title.
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios 1.5 5p", doors="4"), ("sedan", "doors", "4p"))
        # "Sedán 5p" is a hatch: the doors decide, within the catalog.
        self.assertEqual(resolve("Volkswagen", "Gol", "Volkswagen Gol 1.6 Sedán 5p"), ("hatchback", "doors", "5p"))
        # 4p on a Duster (SUV or pick-up) says nothing; a single body type doesn't need doors.
        self.assertEqual(resolve("Renault", "Duster", "Renault Duster 4p"), (None, "none", None))
        self.assertEqual(resolve("Toyota", "Hilux", "Toyota Hilux 4p"), ("pickup", "catalog", None))
        # Without a catalog, doors decide nothing.
        self.assertEqual(bt.resolve("Chery", "QQ", (), None, None, "Chery QQ 5p"), (None, "none", None))

    def test_catalog_with_one_body_type(self):
        self.assertEqual(resolve("Toyota", "Corolla Cross", "Toyota Corolla Cross XEI"),
                         ("suv", "catalog", None))
        self.assertEqual(resolve("Toyota", "SW4", "Toyota Hilux SW4 2.8 SRX"), ("suv", "catalog", None))
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios XLS"), (None, "none", None))

    def test_url_slug_is_a_source_value(self):
        kavak = "https://www.kavak.com/ar/venta/ford-fiesta_kinetic_design-16_se-hatchback-2018"
        self.assertEqual(resolve("Ford", "Fiesta", "Ford Fiesta Kinetic Design 1.6 SE", url=kavak, site="kavak"),
                         ("hatchback", "url", "hatchback"))
        # Like a source value, it doesn't override a single-body-type catalog.
        spin = "https://www.kavak.com/ar/venta/chevrolet-spin-18_ltz-suv-2018"
        self.assertEqual(resolve("Chevrolet", "Spin", "Chevrolet Spin 1.8 LTZ", url=spin, site="kavak")[0],
                         "monovolumen")
        # A coarse source value ("Auto") says nothing, so the slug still counts; a real one wins.
        self.assertEqual(resolve("Ford", "Fiesta", "Ford Fiesta", source="Auto", url=kavak, site="kavak"),
                         ("hatchback", "url", "hatchback"))
        self.assertEqual(resolve("Ford", "Fiesta", "Ford Fiesta", source="Sedán", url=kavak, site="kavak")[0],
                         "sedan")
        # Autocity's slug carries the doors.
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios", url="https://autocity.test/etios-15-xls-4p",
                                 site="autocity")[0], "sedan")

    def test_other_urls_are_seo_keyword_lists(self):
        # Mercado Libre's slug lists other models: "q5 q8 a7 sportback" is no SUV coupé.
        ml = "https://auto.mercadolibre.com.ar/MLA-1-audi-a6-allroad-0km-q7-sq5-nueva-q5-q8-a7-sportback-q3-a1-q2-_JM"
        self.assertEqual(bt.resolve("Audi", "A6", (), None, None, "Audi A6 Allroad 3.0 Tfsi", ml,
                                    listing_source="mercadolibre"), (None, "none", None))
        self.assertEqual(bt.resolve("Audi", "A6", (), None, None, "Audi A6 Allroad 3.0 Tfsi", ml),
                         (None, "none", None))
        # Nor in a title: no other model code between the model and "sportback".
        self.assertEqual(self.explicit("Audi A6 Allroad 0km Q7 SQ5 Nueva Q5 Q8 A7 Sportback"),
                         ("hatchback", "keyword", "sportback"))
        etios = "https://auto.mercadolibre.com.ar/MLA-2-toyota-etios-xls-4p-_JM"
        self.assertEqual(resolve("Toyota", "Etios", "Toyota Etios XLS", url=etios, site="mercadolibre"),
                         (None, "none", None))

    @staticmethod
    def explicit(title):
        return bt.explicit(None, None, title)

    def test_kavak_title_label_is_the_source_value(self):
        # Kavak ends every title in its own label: a single-body catalog still wins.
        self.assertEqual(resolve("Chevrolet", "Spin", "Chevrolet Spin 18 Activ 7S Auto Hatchback 2023", site="kavak"),
                         ("monovolumen", "catalog", "Hatchback"))
        self.assertEqual(resolve("Chevrolet", "Spin", "Chevrolet Spin 18 Ltz 5S Hatchback 2016", site="kavak"),
                         ("monovolumen", "catalog", "Hatchback"))
        self.assertEqual(bt.resolve("Volkswagen", "Suran", ("monovolumen",), None, None,
                                    "Volkswagen Suran 16 16V Highline I Motion Wagon 2017", listing_source="kavak"),
                         ("monovolumen", "catalog", "Wagon"))
        # Within the catalog, or without one, the label is the source's value.
        self.assertEqual(resolve("Ford", "Fiesta", "Ford Fiesta 16 Se Hatchback 2018", site="kavak"),
                         ("hatchback", "source", "Hatchback"))
        self.assertEqual(bt.resolve("Chery", "Tiggo 4", (), None, None, "Chery Tiggo 4 15 Pro Suv 2022",
                                    listing_source="kavak"), ("suv", "source", "Suv"))
        # A seller's own "Hatchback" elsewhere is still a keyword.
        self.assertEqual(resolve("Chevrolet", "Spin", "Chevrolet Spin Hatchback 2023", site="mercadolibre"),
                         ("hatchback", "keyword", "hatchback"))
        self.assertEqual(bt.source_label("Ford Ka Sedan 2019", "kavak"), ("Ford Ka 2019", "Sedan"))
        self.assertEqual(bt.source_label("Ford Ka Sedan 2019", "carone"), ("Ford Ka Sedan 2019", None))

    def test_peugeot_cc_is_the_coupe_cabriolet_not_the_engine(self):
        for title in ("Peugeot 207 CC 1.6 16v", "Peugeot 307 CC 2.0", "Peugeot 206 CC 2.0"):
            with self.subTest(title):
                self.assertEqual(bt.resolve("Peugeot", "207", ("hatchback", "sedan"), None, None, title)[0],
                                 "convertible")
        for title in ("Peugeot 206 XR 1600 cc", "Peugeot 206 XR 1600cc"):
            with self.subTest(title):
                self.assertIsNone(bt.explicit("Peugeot", "206", title))

    def test_coupe_versions_of_suvs(self):
        self.assertEqual(self.explicit("Audi Q4 e-tron Sportback 45")[0], "suv")
        self.assertEqual(self.explicit("Porsche Cayenne Coupe 3.0")[0], "suv")
        self.assertEqual(self.explicit("Mercedes-Benz GLC 300 Coupe 4Matic")[0], "suv")
        self.assertEqual(self.explicit("Audi Q3 Sportback 35 TFSI")[0], "suv")
        self.assertEqual(self.explicit("Audi A5 Sportback 2.0")[0], "hatchback")


class NormalizeListingTests(unittest.TestCase):
    def item(self, **kw) -> Listing:
        base = dict(source="mercadolibre", listing_id="MLA1", titulo="Toyota Etios XLS 1.5",
                    url="https://example.test/MLA1", precio=10_000.0, moneda="USD", anio=2018)
        base.update(kw)
        return Listing(**base)

    def test_row_and_provenance(self):
        row = normalize_listing(self.item(carroceria="452759", titulo="Chery Tiggo 4 Pro"), catalog=CATALOG)
        self.assertEqual(row["body_type"], "suv")
        self.assertEqual(row["attributes"]["_body_type"], {"method": "source", "raw": "452759"})
        self.assertEqual(row["attributes"]["carroceria"], "452759")

        row = normalize_listing(self.item(titulo="Chevrolet Spin 1.8 LTZ",
                                          atributos={"Tipo de carrocería": "SUV"}), catalog=CATALOG)
        self.assertEqual((row["model"], row["body_type"]), ("Spin", "monovolumen"))
        self.assertEqual(row["attributes"]["_body_type"], {"method": "catalog", "raw": "SUV"})

    def test_raw_attributes_and_doors_attribute(self):
        row = normalize_listing(self.item(atributos={"bodyType": "Sedán"}), catalog=CATALOG)
        self.assertEqual(row["body_type"], "sedan")
        row = normalize_listing(self.item(atributos={"Puertas": "5"}), catalog=CATALOG)
        self.assertEqual((row["body_type"], row["attributes"]["_body_type"]["method"]), ("hatchback", "doors"))
        row = normalize_listing(self.item(), catalog=CATALOG)
        self.assertEqual((row["body_type"], row["attributes"]["_body_type"]),
                         (None, {"method": "none", "raw": None}))

    def test_the_catalog_resolves_submodels_but_the_title_decides(self):
        row = normalize_listing(self.item(titulo="Renault Duster Oroch 2.0 Dynamique"), catalog=CATALOG)
        self.assertEqual((row["model"], row["body_type"]), ("Duster", "pickup"))
        row = normalize_listing(self.item(titulo="Fiat Palio Weekend 1.4"), catalog=CATALOG)
        self.assertEqual((row["model"], row["body_type"]), ("Palio", "rural"))

    def test_the_description_never_sets_it(self):
        row = normalize_listing(self.item(descripcion="Hermoso sedán, ideal familia, uso rural"),
                                catalog=CATALOG)
        self.assertIsNone(row["body_type"])

    def test_the_target_alone_never_sets_it(self):
        row = normalize_listing(self.item(), catalog=CATALOG, target=Target(body_type="suv"))
        self.assertIsNone(row["body_type"])

    def test_not_a_key_attribute(self):
        self.assertNotIn("body_type", KEY_ATTRS)
        row = normalize_listing(self.item(), catalog=CATALOG)
        self.assertEqual(attrs_hash(row), attrs_hash(dict(row, body_type="sedan")))


def _stored(**kw) -> dict:
    row = {"id": 1, "source": "mercadolibre", "external_id": "MLA1", "url": "https://example.test/MLA1",
           "title": "Toyota Etios XLS", "description": None, "make": "Toyota", "model": "Etios",
           "trim": "XLS", "year": 2018, "price": 10_000.0, "currency": "USD", "price_usd": 10_000.0,
           "mileage_km": 50_000, "transmission": None, "fuel": None, "body_type": None,
           "location_text": None, "lat": None, "lon": None, "seller_name": None, "seller_type": None,
           "images": [], "attributes": {}, "published_at": None, "price_partial": False,
           "price_partial_reason": None, "normalization_confidence": 0.9, "enriched_at": None,
           "probable_repost_of": None}
    row.update(kw)
    return row


class IngestTests(unittest.TestCase):
    def test_columns(self):
        self.assertIn("body_type", COLUMNS)
        self.assertIn("body_type", _DESCRIPTIVE)

    def test_filling_it_is_no_news(self):
        old = _stored()
        new = dict(_stored(body_type="sedan", attributes={"_body_type": {"method": "doors", "raw": "4p"}}))
        values, changes = merge(old, new, detail=False)
        self.assertEqual((values["body_type"], changes), ("sedan", []))
        self.assertEqual(values["attributes"]["_body_type"], {"method": "doors", "raw": "4p"})
        self.assertEqual(values["attributes"]["_description_filled"], [])

    def test_the_detail_is_authoritative_and_cards_only_fill_it(self):
        enriched = _stored(enriched_at="2026-10-01", body_type="sedan",
                           attributes={"_body_type": {"method": "source", "raw": "Sedán"}})
        card = _stored(body_type="hatchback", attributes={"_body_type": {"method": "doors", "raw": "5p"}})
        values, _ = merge(enriched, card, detail=False)
        self.assertEqual(values["body_type"], "sedan")
        self.assertEqual(values["attributes"]["_body_type"], {"method": "source", "raw": "Sedán"})

        detail = _stored(body_type="hatchback", attributes={"_body_type": {"method": "source", "raw": "Hatchback"}})
        values, _ = merge(enriched, detail, detail=True)
        self.assertEqual(values["body_type"], "hatchback")
        self.assertEqual(values["attributes"]["_body_type"]["raw"], "Hatchback")

    def test_a_detail_without_it_keeps_the_stored_one_and_its_provenance(self):
        old = _stored(body_type="suv", attributes={"_body_type": {"method": "source", "raw": "452759"}})
        detail = _stored(attributes={"_body_type": {"method": "none", "raw": None}})
        values, _ = merge(old, detail, detail=True)
        self.assertEqual(values["body_type"], "suv")
        self.assertEqual(values["attributes"]["_body_type"], {"method": "source", "raw": "452759"})

    def test_the_batch_lists_listings_whose_body_type_got_filled(self):
        async def run(old, row):
            result = IngestResult()
            with patch.object(ingest_module.repo, "update_listing", AsyncMock()), \
                    patch.object(ingest_module.repo, "insert_snapshot", AsyncMock(return_value=9)):
                await ingest_module._on_update(None, old, row, result, IngestConfig(), detail=True)
            return result

        filled = asyncio.run(run(_stored(id=7), _stored(body_type="sedan")))
        self.assertEqual((filled.body_type_filled, filled.events), ([7], []))
        corrected = asyncio.run(run(_stored(id=7, body_type="sedan"), _stored(body_type="hatchback")))
        self.assertEqual(corrected.body_type_filled, [7])               # sedan → hatchback
        again = asyncio.run(run(_stored(id=7, body_type="hatchback"), _stored(body_type="hatchback")))
        self.assertEqual(again.body_type_filled, [])
        lost = asyncio.run(run(_stored(id=7, body_type="hatchback"), _stored()))
        self.assertEqual(lost.body_type_filled, [])                     # a pass without it keeps it
        total = IngestResult()
        total.extend(filled)
        self.assertEqual(total.body_type_filled, [7])


def _listing(**kw) -> dict:
    row = dict(id=1, source="mercadolibre", title="Toyota Corolla Cross XEI", make="Toyota",
               model="Corolla Cross", trim="XEI", year=2022, price=19_000.0, currency="USD",
               price_usd=19_000.0, mileage_km=40_000, transmission="automatic", fuel="nafta",
               body_type="suv", price_partial=False, attributes={})
    row.update(kw)
    return row


def _profile(**filters) -> dict:
    return {"id": 1, "filters": filters, "preferences": {}}


class MatchingTests(unittest.TestCase):
    def test_no_filter_no_reason(self):
        result = evaluate(_listing(), _profile(make="Toyota", model="Corolla Cross"))
        self.assertNotIn("body_type", result.reasons)

    def test_within_a_model_unknown_does_not_discard(self):
        profile = _profile(make="Toyota", model="Corolla Cross", body_types=["suv"])
        result = match(_listing(body_type=None), profile)
        self.assertIsNotNone(result)
        self.assertEqual(result.reasons["body_type"].to_json(),
                         {"result": "unknown", "detail": copy.NOT_INFORMED, "kind": "hard"})
        self.assertEqual(result.unknown, ["body_type"])

    def test_model_less_unknown_fails(self):
        profile = _profile(body_types=["suv"], price_max=20_000, currency="USD")
        result = evaluate(_listing(body_type=None), profile)
        self.assertEqual(result.failed, ["body_type"])
        self.assertEqual(result.reasons["body_type"].detail, copy.REASON["body_type_unknown"])
        self.assertIsNone(match(_listing(body_type=None), profile))
        # A blank make or model is none, as in the database's search_is_model_less.
        blank = _profile(make=" ", model="", body_types=["suv"], price_max=20_000, currency="USD")
        self.assertEqual(evaluate(_listing(body_type=None), blank).failed, ["body_type"])

    def test_ok_and_mismatch(self):
        profile = _profile(body_types=["suv", "pickup"], price_max=20_000, currency="USD")
        ok = match(_listing(), profile)
        self.assertEqual(ok.reasons["body_type"].to_json(), {"result": "ok", "detail": "SUV", "kind": "hard"})
        self.assertNotIn("model", ok.reasons)
        result = evaluate(_listing(body_type="sedan", model="Corolla"), profile)
        self.assertEqual(result.reasons["body_type"].detail, "es Sedán, se busca SUV o Pick-up")
        self.assertEqual(result.failed, ["body_type"])

    def test_exact_membership_not_substring(self):
        profile = _profile(body_types=["suv"], price_max=20_000, currency="USD")
        self.assertIsNone(match(_listing(body_type="suvx"), profile))
        # A lone code instead of a list is still one code, not its letters.
        self.assertIsNotNone(match(_listing(), _profile(body_types="suv", price_max=20_000)))
        self.assertIsNone(match(_listing(body_type="sedan"), _profile(body_types="suv", price_max=20_000)))

    def test_reason_order_puts_body_type_after_fuel(self):
        profile = _profile(make="Toyota", model="Corolla Cross", transmission="automatic", fuel="nafta",
                           body_types=["suv"], sources=["mercadolibre"])
        keys = list(evaluate(_listing(), profile).reasons)
        self.assertEqual(keys[keys.index("fuel") + 1], "body_type")

    def test_a_search_without_vehicle_nor_body_type_matches_nothing(self):
        for filters in ({}, {"price_max": 20_000}, {"body_types": []}):
            result = evaluate(_listing(), _profile(**filters))
            self.assertEqual(result.failed, ["model"], filters)
            self.assertEqual(result.reasons["model"].detail, copy.REASON["no_vehicle"])
        # A make alone keeps working as before.
        self.assertIsNotNone(match(_listing(), _profile(make="Toyota")))

    def test_unknown_names_it_in_the_score(self):
        self.assertEqual(copy.FILTER_NAMES["body_type"], "carrocería")

    def test_model_less_is_the_database_rule(self):
        # The same table test_body_type_postgres checks against search_is_model_less.
        for filters, expected in MODEL_LESS_CASES:
            with self.subTest(filters):
                self.assertIs(model_less(filters), expected)

    def test_a_malformed_vehicle_matches_nothing(self):
        # The database rejects these (invalid_filters); a row from before matches nothing.
        for filters in ({"make": False, "body_types": ["suv"]}, {"make": ["Toyota"]}, {"model": 0}):
            with self.subTest(filters):
                self.assertTrue(malformed_vehicle(filters))
                result = evaluate(_listing(), _profile(price_max=20_000, **filters))
                self.assertEqual(result.reasons["model"].detail, copy.REASON["no_vehicle"])
                self.assertFalse(result.is_match)
        self.assertFalse(malformed_vehicle({"make": "Toyota", "model": None}))

    def test_a_partial_price_is_never_a_match_without_a_model(self):
        # recent_active_by_body leaves partial prices out of the backfill: a batch
        # never matches them either (scoring excludes them), so they can't come back as news.
        from datetime import datetime, timezone
        from intelligence.config import IntelligenceConfig
        from intelligence.engine import evaluate as engine_evaluate
        profile = _profile(body_types=["suv"], price_max=20_000, currency="USD")
        partial = _listing(price_partial=True, price_partial_reason="anticipo")
        self.assertTrue(match(partial, profile) is not None)              # the hard filters: price unknown
        self.assertIsNone(engine_evaluate(partial, profile, price_ref=None, cfg=IntelligenceConfig(),
                                          now=datetime.now(timezone.utc)))
        self.assertIsNotNone(engine_evaluate(_listing(), profile, price_ref=None, cfg=IntelligenceConfig(),
                                             now=datetime.now(timezone.utc)))


# (filters, model-less?) for intelligence.matching.model_less and public.search_is_model_less.
MODEL_LESS_CASES = [
    ({}, True),
    ({"make": None, "model": None}, True),
    ({"make": "", "model": "  "}, True),
    ({"make": "\t", "model": "\n"}, True),
    ({"make": " \t\r\n\f\v "}, True),
    ({"make": "Ford"}, False),
    ({"model": "Ka"}, False),
    ({"make": " Ford "}, False),
    ({"make": False}, False),
    ({"make": 0}, False),
    ({"make": []}, False),
    ({"make": {}}, False),
    ({"model": True}, False),
    ({"make": " "}, False),       # a no-break space is no POSIX space
]


class CliFilterTests(unittest.TestCase):
    def test_matches_filters_follows_matching(self):
        suv = Listing("kavak", "1", "Chery Tiggo 4", "u", carroceria="suv")
        unknown = Listing("kavak", "2", "Chery Tiggo 4", "u")
        sedan = Listing("kavak", "3", "Algo", "u", atributos={"bodyType": "Sedán"})
        f = {"carroceria": "suv"}
        self.assertTrue(BaseScraper.matches_filters(suv, f))
        self.assertFalse(BaseScraper.matches_filters(unknown, f))
        self.assertFalse(BaseScraper.matches_filters(sedan, f))
        within = {"carroceria": "suv", "marca": "Chery", "modelo": "Tiggo 4"}
        self.assertTrue(BaseScraper.matches_filters(unknown, within))
        self.assertFalse(BaseScraper.matches_filters(sedan, within))
        self.assertTrue(BaseScraper.matches_filters(sedan, {"carroceria": ["suv", "sedan"]}))
        self.assertTrue(BaseScraper.matches_filters(unknown, {}))


class StoredRowTests(unittest.TestCase):
    def test_stored_row_reads_what_normalization_kept(self):
        row = normalize_listing(Listing("mercadolibre", "MLA1", "Toyota Etios XLS", "https://example.test/MLA1",
                                        version="1.5 XLS 4ptas", carroceria=None), catalog=CATALOG)
        self.assertEqual(stored_body_type(row, CATALOG), (row["body_type"], row["attributes"]["_body_type"]))
        self.assertEqual(row["body_type"], "sedan")

        row = _stored(title="Chevrolet Spin LTZ", make="Chevrolet", model="Spin",
                      attributes={"carroceria": "SUV"})
        self.assertEqual(stored_body_type(row, CATALOG), ("monovolumen", {"method": "catalog", "raw": "SUV"}))

    def test_backfill_plans_only_changes(self):
        rows = [
            _stored(id=1, title="Toyota Etios XLS 4p"),                               # fills sedan
            _stored(id=2, title="Toyota Etios XLS", attributes={"bodyType": "Hatchback"}),
            _stored(id=3, title="Toyota Etios XLS"),                                  # stays unknown
            _stored(id=4, title="Toyota Corolla XEI", model="Corolla", body_type="sedan"),  # already right
            _stored(id=5, title="Chevrolet Spin", make="Chevrolet", model="Spin", body_type="suv"),  # fixed
            _stored(id=6, title="Toyota Etios XLS", body_type="sedan"),             # not knowing never erases
        ]
        counts = Counter()
        updates = backfill.plan(rows, CATALOG, counts)
        self.assertEqual([(lid, code) for lid, code, _ in updates],
                         [(1, "sedan"), (2, "hatchback"), (5, "monovolumen")])
        self.assertEqual(updates[1][2], {"method": "source", "raw": "Hatchback"})
        self.assertEqual(counts, Counter({("sedan", "doors"): 1, ("hatchback", "source"): 1,
                                          ("monovolumen", "catalog"): 1, ("=", ""): 3}))
        lines = backfill.report(counts, dry_run=True)
        self.assertEqual(lines[-1], "3 publicación(es) cambiarían; 3 sin cambios")

    def test_backfill_goes_by_id_and_dry_run_writes_nothing(self):
        table = [_stored(id=i, title="Toyota Etios XLS 4p" if i % 2 else "Toyota Etios XLS") for i in range(1, 6)]
        writes: list = []

        class Cursor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def executemany(self, sql, params):
                assert sql.startswith("UPDATE listings SET body_type")
                writes.extend((lid, code, how.obj) for code, how, lid in params)

        class Cx:
            async def execute(self, sql, params):
                assert "snapshot" not in sql and "events" not in sql
                last_id, batch = params
                rows = [r for r in table if r["id"] > last_id][:batch]
                return type("R", (), {"fetchall": AsyncMock(return_value=rows)})()

            def cursor(self):
                return Cursor()

        @asynccontextmanager
        async def connection():
            yield Cx()

        with patch.object(backfill.db, "connection", connection), \
                patch.object(backfill, "load_models", AsyncMock(return_value=CATALOG)):
            counts = asyncio.run(backfill.backfill(dry_run=True, batch=2))
            self.assertEqual((counts[("sedan", "doors")], counts[("=", "")], writes), (3, 2, []))
            asyncio.run(backfill.backfill(dry_run=False, batch=2))
        self.assertEqual(writes, [(1, "sedan", {"method": "doors", "raw": "4p"}),
                                  (3, "sedan", {"method": "doors", "raw": "4p"}),
                                  (5, "sedan", {"method": "doors", "raw": "4p"})])

    def test_reprocess_fills_a_missing_body_type(self):
        row = _stored(title="Toyota Etios XLS 4p")
        changed = recompute(row, None, today_rate=None, catalog=CATALOG)
        self.assertEqual(changed["body_type"], "sedan")
        self.assertEqual(changed["attributes"]["_body_type"], {"method": "doors", "raw": "4p"})
        # A stored one stays: reprocess fills, the backfill corrects.
        self.assertNotIn("body_type", recompute(_stored(title="Toyota Etios XLS 4p", body_type="hatchback"),
                                                None, today_rate=None, catalog=CATALOG))


if __name__ == "__main__":
    unittest.main()
