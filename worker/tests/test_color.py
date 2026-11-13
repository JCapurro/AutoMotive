"""Color (docs/PLAN_FILTRO_COLOR.md, Fases 1 y 3): mapping, text rule, _color
precedence, Autocosmos, ingest, matching and backfill. Pure: no network or DB."""
from __future__ import annotations

import asyncio
import unittest
from collections import Counter
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

from collectors.autocosmos import AutoCosmosScraper
from collectors.base import Listing
from db.repos.listings import COLUMNS
from intelligence import copy
from intelligence.low_results import FILTERS as LOW_RESULT_FILTERS, LABEL as LOW_RESULT_LABEL
from intelligence.matching import evaluate, match
from normalization import color
from normalization.listing import KEY_ATTRS, normalize_listing, stored_color, stored_color_update
from pipeline.ingest import _DESCRIPTIVE, merge
from tools import backfill_color as backfill
from tools.reprocess import recompute

FIXTURES = Path(__file__).parent / "fixtures" / "html"


def _vision(code: str | None, candidates=None, **kw) -> dict:
    return color.build("vision", None, confidence="media", model="gpt-6-luna", candidates=candidates,
                       photos=4, at="2026-11-12T12:00:00+00:00", **kw)


class CanonicalTests(unittest.TestCase):
    def test_codes_and_labels(self):
        self.assertEqual(color.CODES, ("blanco", "negro", "gris", "azul", "rojo", "verde", "beige", "otro"))
        self.assertEqual(list(color.LABELS), list(color.CODES))
        self.assertEqual(color.LABELS["gris"], "Gris o plata")
        self.assertEqual(color.LABELS["otro"], "Otro color")
        self.assertEqual(color.CANDIDATE_MIN_PROB, 30)

    def test_manufacturer_names(self):
        cases = {
            "Blanco Oxford": "blanco", "Plata Sirius": "gris", "Gris Plata": "gris", "Azul Mónaco": "azul",
            "Bordó": "rojo", "Champagne": "beige", "Grafito": "gris", "Perla": "blanco", "Celeste": "azul",
            "Petróleo": "azul", "Negro Vulcano": "negro", "Blanco Crema": "blanco", "Plateado": "gris",
            "Summit White": "blanco", "Metalizado Gris": "gris", "Perla Nera": "negro",
            "Verde Petróleo": "verde", "Marrón": "beige", "Dorado": "beige", "Amarillo": "otro",
            "ROJO": "rojo", "gris oscuro": "gris", "blanco": "blanco",
        }
        for raw, code in cases.items():
            with self.subTest(raw):
                self.assertEqual(color.canonical(raw), code)

    def test_no_color(self):
        for raw in (None, "", "  ", "Metalizado", "N/D", "-", True, 12):
            with self.subTest(raw):
                self.assertIsNone(color.canonical(raw))

    def test_every_code_maps_to_itself(self):
        for code in color.CODES:
            self.assertEqual(color.canonical(code), code)

    def test_source_color_reads_the_collectors_keys(self):
        self.assertEqual(color.source_color({"Color": "Plata Sirius"}), ("gris", "Plata Sirius"))   # ML, Randazzo
        self.assertEqual(color.source_color({"color": "Blanco"}), ("blanco", "Blanco"))             # Kavak
        self.assertIsNone(color.source_color({"Color interior": "Negro", "Tapizados": "tela"}))
        self.assertIsNone(color.source_color({"Color": "N/D"}))
        self.assertIsNone(color.source_color(None))


class TextTests(unittest.TestCase):
    def test_an_anchor_is_needed(self):
        self.assertEqual(color.from_text("Vendo Gol color blanco impecable"), ("blanco", "color blanco impecable"))
        self.assertEqual(color.from_text("Color: Gris"), ("gris", "color: gris"))
        self.assertEqual(color.from_text("pintura roja original")[0], "rojo")
        self.assertEqual(color.from_text("COLOR EXTERIOR: BLANCO PERLA")[0], "blanco")
        self.assertEqual(color.from_text("pintura original, color gris plata")[0], "gris")
        self.assertEqual(color.from_text(None, "Gol 2015", "Color negro")[0], "negro")

    def test_a_bare_word_or_another_part_says_nothing(self):
        for text in ("Gol blanco", "interior negro, llantas negras", "tapizado color beige",
                     "llantas color negro", "color interior negro", "techo color negro",
                     "Colores disponibles: rojo", "pantalla color de 7 pulgadas", "color a elección", None, ""):
            with self.subTest(text):
                self.assertIsNone(color.from_text(text))

    def test_another_part_next_to_the_paint(self):
        self.assertEqual(color.from_text("color blanco y techo color negro")[0], "blanco")

    def test_two_colors_that_disagree_say_nothing(self):
        self.assertIsNone(color.from_text("color blanco, luego color negro"))
        self.assertIsNone(color.from_text("Color rojo", "pintura gris"))
        self.assertEqual(color.from_text("Color rojo", "pintura roja")[0], "rojo")


class PrecedenceTests(unittest.TestCase):
    def test_build_has_the_contract_shape(self):
        how = color.build("source", "Gris")
        self.assertEqual(set(how), {"method", "raw", "confidence", "model", "v", "candidates", "photos", "at"})
        self.assertEqual((how["method"], how["raw"], how["v"]), ("source", "Gris", 1))
        no = _vision(None, result="no_visible")
        self.assertEqual(no["result"], "no_visible")
        with self.assertRaises(ValueError):
            color.build("photo")

    def test_source_beats_text_beats_vision(self):
        source, text, vision = color.build("source", "Gris"), color.build("text", "color gris"), _vision("gris")
        self.assertIsNone(color.merge_color(source, vision))
        self.assertIsNone(color.merge_color(text, vision))
        self.assertIsNone(color.merge_color(source, text))
        self.assertEqual(color.merge_color(vision, source), source)
        self.assertEqual(color.merge_color(vision, text), text)
        self.assertEqual(color.merge_color(text, source), source)
        self.assertEqual(color.merge_color(None, vision), vision)
        # The same method: the newer reading stands (new photos, the detail over the card).
        self.assertEqual(color.merge_color(vision, _vision("azul")), _vision("azul"))
        self.assertIsNone(color.merge_color(source, None))
        self.assertIsNone(color.merge_color(None, {"method": "guess"}))

    def test_candidates_count_from_30(self):
        how = _vision("gris", [{"color": "gris", "prob": 65}, {"color": "verde", "prob": 30},
                               {"color": "azul", "prob": 5}, {"color": "nope", "prob": 80}])
        self.assertEqual(color.candidates(how), [("gris", 65), ("verde", 30)])
        self.assertEqual(color.candidates(None), [])
        self.assertTrue(color.fits("gris", {"_color": how}, ["verde"]))
        self.assertFalse(color.fits("gris", {"_color": how}, ["azul"]))
        self.assertTrue(color.fits(None, {}, ["azul"]))
        self.assertTrue(color.fits("rojo", {}, []))

    def test_resolve_goes_source_then_text(self):
        code, how = color.resolve({"Color": "Bordó"}, "color blanco")
        self.assertEqual((code, how["method"], how["raw"]), ("rojo", "source", "Bordó"))
        code, how = color.resolve({}, "Gol", "Color: blanco")
        self.assertEqual((code, how["method"]), ("blanco", "text"))
        self.assertEqual(color.resolve({}, "Gol blanco"), (None, None))

    def test_wanted_colors(self):
        self.assertEqual(color.wanted_colors({"colors": ["gris", "blanco"]}), ["blanco", "gris"])
        self.assertEqual(color.wanted_colors({"colors": "rojo"}), ["rojo"])
        self.assertEqual(color.wanted_colors({"colors": []}), [])
        self.assertEqual(color.wanted_colors({"colors": ["Rojo"]}), [])
        self.assertEqual(color.wanted_colors({}), [])


class AutocosmosTests(unittest.TestCase):
    def test_search_cards_state_the_color(self):
        cards = AutoCosmosScraper.parse_search((FIXTURES / "autocosmos_search.html").read_text(encoding="utf-8"))
        self.assertEqual([c.atributos.get("Color") for c in cards], ["Negro Vulcano", "Plata", "Blanco Crema"])
        self.assertEqual([color.source_color(c.atributos)[0] for c in cards], ["negro", "gris", "blanco"])

    def test_a_card_without_color(self):
        html = ('<article class="listing-card"><a itemprop="url" title="Ford Ka usado (2017) precio $1" '
                f'href="/auto/usado/ford/ka/s/{1:032x}"></a></article>')
        self.assertEqual(AutoCosmosScraper.parse_search(html)[0].atributos, {})

    def test_the_detail_reads_itemprop_color(self):
        detail = AutoCosmosScraper.parse_detail(
            (FIXTURES / "autocosmos_detail.html").read_text(encoding="utf-8"),
            "https://www.autocosmos.com.ar/auto/usado/x/y/z/7b0c5ed1262b4223b2de21ea856abf07")
        self.assertEqual(detail.listing.atributos["Color"], "Gris")
        row = normalize_listing(detail.listing, catalog=[])
        self.assertEqual(row["color"], "gris")
        self.assertEqual(row["attributes"]["_color"]["method"], "source")

    def test_the_parser_version_was_bumped(self):
        # tools.reprocess --raw --outdated re-reads the stored pages for the color.
        self.assertGreaterEqual(AutoCosmosScraper.DETAIL_PARSER_VERSION, 5)


def _stored(**kw) -> dict:
    row = {"id": 1, "source": "mercadolibre", "external_id": "MLA1", "url": "https://example.test/MLA1",
           "title": "Volkswagen Gol Trend", "description": None, "make": "Volkswagen", "model": "Gol",
           "trim": None, "year": 2018, "price": 10_000.0, "currency": "USD", "price_usd": 10_000.0,
           "mileage_km": 50_000, "transmission": None, "fuel": None, "body_type": None, "color": None,
           "location_text": None, "lat": None, "lon": None, "seller_name": None, "seller_type": None,
           "images": [], "attributes": {}, "published_at": None, "price_partial": False,
           "price_partial_reason": None, "normalization_confidence": 0.9, "enriched_at": None,
           "probable_repost_of": None}
    row.update(kw)
    return row


def _normalized(**kw) -> dict:
    item = Listing("mercadolibre", "MLA1", kw.pop("titulo", "Volkswagen Gol Trend"), "https://example.test/MLA1",
                   **kw)
    return normalize_listing(item, catalog=[])


class IngestTests(unittest.TestCase):
    def test_columns_and_no_snapshot(self):
        self.assertIn("color", COLUMNS)
        self.assertNotIn("color", KEY_ATTRS)
        self.assertNotIn("color", _DESCRIPTIVE)      # merged by method, not by side

    def test_normalize_takes_the_source_then_the_text(self):
        row = _normalized(atributos={"Color": "Gris Plata"}, descripcion="color blanco")
        self.assertEqual((row["color"], row["attributes"]["_color"]["method"]), ("gris", "source"))
        row = _normalized(descripcion="Excelente estado, color blanco")
        self.assertEqual((row["color"], row["attributes"]["_color"]["method"]), ("blanco", "text"))
        row = _normalized(titulo="Gol blanco")
        self.assertIsNone(row["color"])
        self.assertNotIn("_color", row["attributes"])

    def test_filling_it_is_no_news(self):
        values, changes = merge(_stored(), _normalized(atributos={"Color": "Rojo"}), detail=True)
        self.assertEqual((values["color"], changes), ("rojo", []))
        self.assertEqual(values["attributes"]["_color"]["raw"], "Rojo")

    def test_the_photos_never_overwrite_the_source_and_the_source_overwrites_the_photos(self):
        seen = _stored(color="gris", attributes={"_color": _vision("gris")})
        values, _ = merge(seen, _normalized(atributos={"Color": "Blanco"}), detail=True)
        self.assertEqual((values["color"], values["attributes"]["_color"]["method"]), ("blanco", "source"))
        # A card from before the photos (no color in it) keeps what the photos said.
        values, _ = merge(seen, _normalized(), detail=False)
        self.assertEqual(values["color"], "gris")
        self.assertEqual(values["attributes"]["_color"], _vision("gris"))
        # A text read later never overwrites a source color.
        source = _stored(color="rojo", attributes={"_color": color.build("source", "Rojo")})
        values, _ = merge(source, _normalized(descripcion="color negro"), detail=True)
        self.assertEqual((values["color"], values["attributes"]["_color"]["raw"]), ("rojo", "Rojo"))

    def test_not_knowing_keeps_a_no_visible_result(self):
        no = _vision(None, result="no_visible")
        values, _ = merge(_stored(attributes={"_color": no}), _normalized(), detail=True)
        self.assertIsNone(values["color"])
        self.assertEqual(values["attributes"]["_color"], no)

    def test_a_card_does_not_overwrite_an_enriched_listing_of_the_same_method(self):
        enriched = _stored(enriched_at="2026-10-01", color="blanco",
                           attributes={"_color": color.build("text", "color blanco")})
        values, _ = merge(enriched, _normalized(titulo="Gol color rojo"), detail=False)
        self.assertEqual(values["color"], "blanco")
        values, _ = merge(enriched, _normalized(descripcion="color rojo"), detail=True)
        self.assertEqual(values["color"], "rojo")

    def test_the_same_reading_keeps_its_date(self):
        how = color.build("source", "Rojo", at="2026-11-01T00:00:00+00:00")
        values, _ = merge(_stored(color="rojo", attributes={"_color": how}),
                          _normalized(atributos={"Color": "Rojo"}), detail=True)
        self.assertEqual(values["attributes"]["_color"]["at"], "2026-11-01T00:00:00+00:00")


def _listing(**kw) -> dict:
    row = dict(id=1, source="mercadolibre", title="Volkswagen Gol", make="Volkswagen", model="Gol",
               year=2018, price=10_000.0, currency="USD", price_usd=10_000.0, mileage_km=50_000,
               body_type="hatchback", color=None, price_partial=False, attributes={})
    row.update(kw)
    return row


def _profile(**filters) -> dict:
    return {"id": 1, "filters": {"make": "Volkswagen", "model": "Gol", **filters}, "preferences": {}}


class MatchingTests(unittest.TestCase):
    def test_no_filter_no_reason(self):
        self.assertNotIn("color", evaluate(_listing(color="rojo"), _profile()).reasons)
        self.assertNotIn("color", evaluate(_listing(color="rojo"), _profile(colors=[])).reasons)

    def test_the_wanted_color_is_ok(self):
        listing = _listing(color="blanco", attributes={"_color": color.build("source", "Blanco Oxford")})
        reason = evaluate(listing, _profile(colors=["blanco", "gris"])).reasons["color"]
        self.assertEqual((reason.result, reason.detail, reason.hard), ("ok", "blanco · dato del aviso", True))
        listing = _listing(color="gris", attributes={"_color": _vision("gris")})
        reason = evaluate(listing, _profile(colors=["gris"])).reasons["color"]
        self.assertEqual((reason.result, reason.detail), ("ok", "gris · según la foto"))
        listing = _listing(color="gris", attributes={"_color": color.build("text", "color gris")})
        self.assertEqual(evaluate(listing, _profile(colors=["gris"])).reasons["color"].detail,
                         "gris · dato del aviso")

    def test_a_wanted_candidate_from_30_is_unknown(self):
        how = _vision("gris", [{"color": "gris", "prob": 70}, {"color": "verde", "prob": 30}])
        result = evaluate(_listing(color="gris", attributes={"_color": how}), _profile(colors=["verde"]))
        reason = result.reasons["color"]
        self.assertEqual((reason.result, reason.detail), ("unknown", "color parecido: puede ser verde"))
        self.assertTrue(result.is_match)
        self.assertIn("color", result.unknown)
        # Under 30 it is a fail.
        how = _vision("gris", [{"color": "gris", "prob": 75}, {"color": "verde", "prob": 25}])
        self.assertIsNone(match(_listing(color="gris", attributes={"_color": how}), _profile(colors=["verde"])))

    def test_no_color_is_unknown_in_both_kinds_of_search(self):
        for profile in (_profile(colors=["blanco"]),
                        {"id": 1, "filters": {"body_types": ["hatchback"], "colors": ["blanco"]}, "preferences": {}}):
            with self.subTest(profile["filters"]):
                result = evaluate(_listing(), profile)
                reason = result.reasons["color"]
                self.assertEqual((reason.result, reason.detail), ("unknown", "color sin confirmar"))
                self.assertTrue(result.is_match)
        # No color but a wanted candidate (low confidence keeps only the candidates).
        how = _vision(None, [{"color": "azul", "prob": 55}, {"color": "gris", "prob": 45}])
        reason = evaluate(_listing(attributes={"_color": how}), _profile(colors=["gris"])).reasons["color"]
        self.assertEqual((reason.result, reason.detail), ("unknown", "color parecido: puede ser gris"))

    def test_another_color_fails(self):
        result = evaluate(_listing(color="rojo"), _profile(colors=["blanco", "gris"]))
        reason = result.reasons["color"]
        self.assertEqual((reason.result, reason.detail), ("fail", "es rojo, se busca blanco o gris"))
        self.assertFalse(result.is_match)
        reason = evaluate(_listing(color="otro"), _profile(colors=["blanco"])).reasons["color"]
        self.assertEqual(reason.detail, "es de otro color, se busca blanco")

    def test_the_rule_comes_right_after_the_body_type(self):
        keys = list(evaluate(_listing(color="blanco"), _profile(body_types=["hatchback"], colors=["blanco"])).reasons)
        self.assertEqual(keys[keys.index("body_type") + 1], "color")

    def test_the_old_soft_preference_is_gone(self):
        profile = _profile() | {"preferences": {"colors": ["Rojo"]}}
        result = evaluate(_listing(color="blanco", attributes={"Color": "Blanco"}), profile)
        self.assertNotIn("colors", result.reasons)
        self.assertNotIn("color", result.reasons)
        self.assertFalse(any("se prefiere" in v for k, v in copy.REASON.items() if k.startswith("color")))

    def test_labels(self):
        self.assertEqual(copy.FILTER_NAMES["color"], "color")
        self.assertIn("color", LOW_RESULT_FILTERS)
        self.assertEqual(LOW_RESULT_LABEL["color"], "color")
        self.assertEqual(list(copy.COLOR), list(color.CODES))


class StoredRowTests(unittest.TestCase):
    def test_stored_row_reads_what_normalization_kept(self):
        row = _normalized(atributos={"Color": "Azul Mónaco"})
        self.assertEqual(stored_color(row)[0], "azul")

    def test_backfill_plans_only_changes(self):
        rows = [
            _stored(id=1, attributes={"Color": "Plata Sirius"}),                            # fills gris
            _stored(id=2, source="kavak", attributes={"color": "Blanco"}),                  # fills blanco
            _stored(id=3, description="Impecable, color rojo"),                             # text
            _stored(id=4, title="Gol blanco"),                                              # stays unknown
            _stored(id=5, color="gris", attributes={"Color": "Gris", "_color": color.build("source", "Gris")}),
            _stored(id=6, color="negro", attributes={"_color": color.build("source", "Negro")},
                    description="color rojo"),                                              # text < source
            _stored(id=7, color="gris", attributes={"Color": "Blanco", "_color": _vision("gris")}),  # source > photo
            _stored(id=8, color="gris", attributes={"_color": color.build("text", "color gris")}),  # not erased
        ]
        counts = Counter()
        updates = backfill.plan(rows, counts)
        self.assertEqual([(lid, code) for lid, code, _ in updates],
                         [(1, "gris"), (2, "blanco"), (3, "rojo"), (7, "blanco")])
        self.assertEqual((updates[0][2]["method"], updates[0][2]["raw"]), ("source", "Plata Sirius"))
        self.assertEqual(updates[2][2]["method"], "text")
        self.assertEqual(counts, Counter({("mercadolibre", "gris", "source"): 1, ("kavak", "blanco", "source"): 1,
                                          ("mercadolibre", "rojo", "text"): 1,
                                          ("mercadolibre", "blanco", "source"): 1, ("=", "", ""): 4}))
        self.assertEqual(backfill.report(counts, dry_run=True)[-1], "4 publicación(es) cambiarían; 4 sin cambios")

    def test_backfill_is_a_dry_run_by_default_and_goes_by_id(self):
        table = [_stored(id=i, attributes={"Color": "Rojo"} if i % 2 else {}) for i in range(1, 6)]
        writes: list = []

        class Cursor:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def executemany(self, sql, params):
                assert sql.startswith("UPDATE listings SET color")
                writes.extend((lid, code, how.obj["method"]) for code, how, lid, _ in params)

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

        pool = patch.multiple(backfill.db, open_pool=AsyncMock(), close_pool=AsyncMock())
        with patch.object(backfill.db, "connection", connection), pool:
            self.assertEqual(asyncio.run(backfill.main(["--batch", "2"])), 0)
            self.assertEqual(writes, [])
            counts = asyncio.run(backfill.backfill(dry_run=True, batch=2))
            self.assertEqual((counts[("mercadolibre", "rojo", "source")], counts[("=", "", "")]), (3, 2))
            asyncio.run(backfill.main(["--write", "--batch", "2"]))
        self.assertEqual(writes, [(1, "rojo", "source"), (3, "rojo", "source"), (5, "rojo", "source")])

    def test_reprocess_fills_the_color(self):
        changed = recompute(_stored(description="color: blanco"), None, today_rate=None, catalog=[])
        self.assertEqual(changed["color"], "blanco")
        self.assertEqual(changed["attributes"]["_color"]["method"], "text")
        source = _stored(color="negro", attributes={"_color": color.build("source", "Negro")},
                         description="color blanco")
        self.assertNotIn("color", recompute(source, None, today_rate=None, catalog=[]))


if __name__ == "__main__":
    unittest.main()
