"""Body type in the Mercado Libre and Kavak collectors (docs/CARROCERIA.md).

The *_bodytype_* fixtures are live pages captured on 2026-10-15, trimmed to
three cards and the embedded state the collectors read: Mercado Libre's SUV
"Publicados hoy" (pages 1 and 2 of 13) and Kavak's /ar/usados/suv (pages 1
and 2 of 15).
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest
from unittest.mock import AsyncMock, patch

from collectors import kavak as kv
from collectors import mercadolibre as ml
from collectors._http import Page
from collectors.base import CollectorBlocked
from normalization import body_type
from normalization.listing import normalize_listing
from seed_catalog import seed_catalog

FIXTURES = Path(__file__).parent / "fixtures" / "html"
RESCUE = '<div class="ui-search-rescue"></div>'
SUV_URL = ("https://autos.mercadolibre.com.ar/_PublishedToday_YES_KILOMETERS_*-250000km_NoIndex_True"
           "_VEHICLE*BODY*TYPE_452759_VEHICLE*YEAR_2008-2026")
WIDEST = {"carroceria": "suv", "anio_min": 2008, "anio_max": 2026, "km_max": 250_000}
# What pipeline/crawl.py adds on a body-type target's first run.
FIRST_RUN = {"publication_days": 30, "published_since": 1_700_000_000, "publication_until": 1_760_000_000}


def html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def ml_page(name: str = "mercadolibre_bodytype_suv.html", *, page_count: int | None = None,
            total: int | None = None, body_id: str | None = None, since: str | None = None) -> str:
    """A Mercado Libre fixture with its embedded state changed."""
    text = html(name)
    if page_count is not None:
        text = re.sub(r'"page_count":\d+', f'"page_count":{page_count}', text)
    if total is not None:
        text = re.sub(r'"total":\d+', f'"total":{total}', text)
    if body_id is not None:
        text = text.replace('"value":"452759"', f'"value":"{body_id}"')
    if since is not None:
        text = text.replace('"value":"today"', f'"value":"{since}"')
    return text


class FakeHttp:
    """Stands in for collectors._http.fetch_page: each GET takes the next
    outcome, an html (200 at the asked URL), a (status, html) or an exception."""

    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.asked: list[str] = []

    async def __call__(self, url, **kwargs):
        self.asked.append(url)
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        status, body = outcome if isinstance(outcome, tuple) else (200, outcome)
        return Page(status, url, body)


# ---------------------------------------------------------------------------
# Mercado Libre
# ---------------------------------------------------------------------------

class MercadoLibreBodyTypeTests(unittest.TestCase):
    def test_each_code_searches_its_ids_and_light_truck_none(self):
        self.assertEqual(ml.IDS_BY_BODY_TYPE["suv"], ("452759", "452754", "452761"))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["sedan"], ("452758",))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["hatchback"], ("479344",))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["pickup"], ("452756",))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["rural"], ("452760",))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["monovolumen"], ("452752", "452753"))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["coupe"], ("452749",))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["convertible"], ("452748", "452757"))
        self.assertEqual(ml.IDS_BY_BODY_TYPE["utilitario"], ("452750", "452755"))
        searched = [i for ids in ml.IDS_BY_BODY_TYPE.values() for i in ids]
        self.assertNotIn("452751", searched)        # Light Truck
        self.assertEqual(len(searched), len(set(searched)))
        self.assertEqual(ml.MercadoLibreScraper.BODY_TYPES, frozenset(body_type.CODES))

    def test_body_type_url_is_the_order_mercado_libre_links_to(self):
        # Page 1 is the URL the 15/10/2026 redirect answered with; page 2, its "Siguiente" link.
        self.assertEqual(ml._build_url(WIDEST, today=True, body_type_id="452759"), SUV_URL)
        self.assertEqual(
            ml._build_url(WIDEST, page=2, today=True, body_type_id="452759"),
            "https://autos.mercadolibre.com.ar/_Desde_49_PublishedToday_YES_KILOMETERS_*-250000km_NoIndex_True"
            "_VEHICLE*BODY*TYPE_452759_VEHICLE*YEAR_2008-2026")
        self.assertEqual(ml._build_url({"carroceria": "suv"}, today=True, body_type_id="452759"),
                         "https://autos.mercadolibre.com.ar/_PublishedToday_YES_NoIndex_True_VEHICLE*BODY*TYPE_452759")

    def test_model_urls_are_unchanged(self):
        self.assertEqual(
            ml._build_url({"marca": "Ford", "modelo": "Fiesta", "anio_min": 2015, "anio_max": 2024,
                           "km_max": 120_000}, page=2, today=True),
            "https://autos.mercadolibre.com.ar/ford/fiesta/_VEHICLE*YEAR_2015-2024_KILOMETERS_*-120000km"
            "_PublishedToday_YES_Desde_49_NoIndex_True")

    def test_search_state_reads_the_embedded_filters_and_pagination(self):
        state = ml.search_state(html("mercadolibre_bodytype_suv.html"))
        self.assertTrue(state.applies("452759"))
        self.assertFalse(state.applies("452758"))
        self.assertEqual((state.total, state.page_count, state.truncated), (582, 13, False))
        self.assertIn(("VEHICLE_YEAR", "[2008-2026]"), state.applied)

        capped = ml.search_state(ml_page(total=29_263, page_count=42))
        self.assertTrue(capped.truncated)
        self.assertFalse(ml.search_state(ml_page(since="week")).applies("452759"))
        empty = ml.search_state(html("mercadolibre_search.html"))   # no embedded state
        self.assertEqual((empty.applied, empty.total, empty.page_count), (frozenset(), None, None))
        self.assertFalse(empty.applies("452759"))

    def test_detail_reads_the_body_type(self):
        detail = html("mercadolibre_detail.html")
        url = "https://auto.mercadolibre.com.ar/MLA-1675249827-toyota-corolla-cross-18-hev-seg-ecvt-_JM"
        self.assertEqual(ml.parse_detail(detail, url).listing.carroceria, "SUV")
        # Without the spec row, JSON-LD's bodyType.
        without_row = re.sub(r"<tr[^>]*>(?:(?!</tr>).)*Tipo de carrocer(?:(?!</tr>).)*</tr>", "", detail,
                             flags=re.S)
        self.assertNotIn("Tipo de carrocer", without_row)
        self.assertEqual(ml.parse_detail(without_row, url).listing.carroceria, "SUV")
        self.assertEqual(ml.MercadoLibreScraper.DETAIL_PARSER_VERSION, 3)


class MercadoLibreBodyTypeSearchTests(unittest.IsolatedAsyncioTestCase):
    async def search(self, outcomes, filters=None, *, page_size=None):
        http = FakeHttp(outcomes)
        patches = [patch.object(ml, "fetch_page", http), patch.object(ml, "_page_pause", AsyncMock())]
        if page_size:
            patches.append(patch.object(ml, "PAGE_SIZE", page_size))
        for p in patches:
            p.start()
        try:
            found = await ml.MercadoLibreScraper().search(dict(WIDEST, **FIRST_RUN) if filters is None else filters)
        finally:
            for p in reversed(patches):
                p.stop()
        return found, http

    async def test_reads_publicados_hoy_of_each_id_and_seals_every_card(self):
        found, http = await self.search(
            [ml_page(page_count=2, total=6), ml_page("mercadolibre_bodytype_suv_p2.html", page_count=2, total=6),
             RESCUE, RESCUE], page_size=3)

        # "Publicados hoy" on a first run too, whatever the window asked.
        self.assertEqual(http.asked, [
            SUV_URL,
            SUV_URL.replace("/_Publi", "/_Desde_4_Publi"),
            SUV_URL.replace("452759", "452754"),
            SUV_URL.replace("452759", "452761"),
        ])
        self.assertTrue(found.complete, found.reason)
        self.assertEqual(len(found), 6)
        self.assertEqual({c.carroceria for c in found}, {"suv"})
        self.assertEqual(found[0].listing_id, "MLA2192309531")

    async def test_does_not_read_past_the_page_count(self):
        found, http = await self.search([ml_page(page_count=1, total=3), RESCUE, RESCUE], page_size=3)
        self.assertEqual(len(http.asked), 3)    # one page per id
        self.assertEqual(len(found), 3)
        self.assertTrue(found.complete)

    async def test_more_results_than_pages_is_incomplete(self):
        found, http = await self.search([ml_page(total=29_263, page_count=1), RESCUE, RESCUE], page_size=3)
        self.assertEqual(len(found), 3)
        self.assertFalse(found.complete)
        self.assertIn("29263 results", found.reason)

    async def test_a_page_without_the_filter_applied_fails_the_run(self):
        for page in (ml_page(body_id="452758"), ml_page(since="week"), html("mercadolibre_search.html")):
            with self.subTest(page=page[:60]):
                with self.assertRaises(ml.BodyTypeNotApplied):
                    await self.search([page])

    async def test_an_unverified_later_page_fails_the_run_too(self):
        with self.assertRaises(ml.BodyTypeNotApplied):
            await self.search([ml_page(page_count=2),
                               ml_page("mercadolibre_bodytype_suv_p2.html", body_id="479344")], page_size=3)

    async def test_no_results_today_is_not_an_error(self):
        found, http = await self.search([RESCUE, RESCUE, RESCUE])
        self.assertEqual((list(found), found.complete, len(http.asked)), ([], True, 3))

    async def test_later_failures_keep_the_verified_cards(self):
        found, _ = await self.search([ml_page(page_count=2), (503, "error")], page_size=3)
        self.assertEqual(len(found), 3)
        self.assertFalse(found.complete)
        self.assertIn("HTTP 503", found.reason)

    async def test_first_page_walls_and_errors_propagate(self):
        with self.assertRaises(CollectorBlocked):
            await self.search([(429, "too many")])
        with self.assertRaisesRegex(RuntimeError, "no results list"):
            await self.search(["<html>otra cosa</html>"])

    async def test_cards_still_go_through_the_target_filters(self):
        # The page's cards are a 2018 Peugeot 2008 and two 2026 Volkswagen; dates known are kept.
        filters = dict(WIDEST, anio_min=2020, known_publication_dates={"MLA2190593863": 1_760_000_000})
        found, _ = await self.search([ml_page(page_count=1), RESCUE, RESCUE], filters)
        self.assertEqual([c.listing_id for c in found], ["MLA2190593863", "MLA2190641369"])
        self.assertEqual(found[0].published_at, 1_760_000_000)

    async def test_unknown_body_type_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no VEHICLE_BODY_TYPE"):
            await self.search([], {"carroceria": "camioneta"})

    async def test_a_model_target_keeps_its_url_and_lets_unknown_bodies_through(self):
        found, http = await self.search(
            [html("mercadolibre_search.html")], {"marca": "Toyota", "modelo": "Corolla", "carroceria": "sedan"})
        self.assertEqual(http.asked, ["https://autos.mercadolibre.com.ar/toyota/corolla/_NoIndex_True"])
        self.assertEqual(len(found), 3)
        self.assertEqual({c.carroceria for c in found}, {None})

    async def test_sealed_cards_normalize_to_the_code(self):
        found, _ = await self.search([ml_page(page_count=1), RESCUE, RESCUE])
        catalog = seed_catalog()
        rows = [normalize_listing(c, catalog=catalog) for c in found]
        # Peugeot 2008 is an SUV in the catalog; Tera isn't in it, so the source's value stands.
        self.assertEqual([r["body_type"] for r in rows], ["suv", "suv", "suv"])
        self.assertEqual(rows[0]["attributes"]["_body_type"]["method"], "source")


# ---------------------------------------------------------------------------
# Kavak
# ---------------------------------------------------------------------------

def kv_page(name: str = "kavak_bodytype_suv.html", *, pages: int | None = None, body: str | None = None) -> str:
    text = html(name)
    if pages is not None:
        text = re.sub(r'(pagination\\":\{\\"pages\\":)\d+', rf"\g<1>{pages}", text)
    if body is not None:
        text = text.replace('\\"value\\":\\"suv\\"', f'\\"value\\":\\"{body}\\"')
    return text


class KavakBodyTypeTests(unittest.TestCase):
    def test_cards_read_the_body_type_from_their_slug(self):
        cards = kv.parse_search(html("kavak_search.html"))
        self.assertEqual([c.carroceria for c in cards], ["hatchback"] * 3)
        suv = kv.parse_search(html("kavak_bodytype_suv.html"))
        self.assertEqual([c.carroceria for c in suv], ["suv"] * 3)
        self.assertEqual(kv._slug_body("ford-ranger-20_cd_limited_auto_4wd-pickup-2024"), "pickup")
        self.assertEqual(kv._slug_body("volkswagen-suran-16_trendline-wagon-2015"), "wagon")
        self.assertIsNone(kv._slug_body("ford-fiesta-titanium-2018"))      # a version, not a body
        self.assertIsNone(kv._slug_body("ford-fiesta-16_se"))

    def test_detail_reads_the_json_ld_body_type(self):
        url = "https://www.kavak.com/ar/venta/ford-fiesta_kinetic_design-16_se-hatchback-2018?id=549997"
        self.assertEqual(kv.parse_detail(html("kavak_detail.html"), url).listing.carroceria, "Hatchback")

    def test_list_state(self):
        state = kv.list_state(html("kavak_bodytype_suv.html"))
        self.assertEqual((state.body_types, state.pages, state.total), (frozenset({"suv"}), 15, 422))
        self.assertEqual(kv.list_state(html("kavak_search.html")), kv.ListState(frozenset(), None, None))

    def test_each_code_has_a_listing_that_maps_back_to_it(self):
        for code, slug in kv.BODY_TYPE_SLUGS.items():
            with self.subTest(code=code):
                self.assertEqual(body_type.from_source(slug), code)
        self.assertEqual(kv.KavakScraper.BODY_TYPES,
                         frozenset({"sedan", "hatchback", "suv", "pickup", "rural", "monovolumen", "utilitario"}))


class KavakBodyTypeSearchTests(unittest.IsolatedAsyncioTestCase):
    async def search(self, outcomes, filters=None):
        http = FakeHttp(outcomes)
        with patch.object(kv, "fetch_page", http), patch.object(kv, "_page_pause", AsyncMock()):
            found = await kv.KavakScraper().search({"carroceria": "suv"} if filters is None else filters)
        return found, http

    async def test_reads_every_page_with_plain_gets(self):
        found, http = await self.search([kv_page(pages=2), kv_page("kavak_bodytype_suv_p1.html", pages=2)])
        self.assertEqual(http.asked, ["https://www.kavak.com/ar/usados/suv",
                                      "https://www.kavak.com/ar/usados/suv?page=1"])
        self.assertTrue(found.complete, found.reason)
        self.assertEqual(len(found), 6)
        self.assertEqual({c.carroceria for c in found}, {"suv"})

    async def test_stops_at_a_page_without_new_cars(self):
        found, http = await self.search([kv_page(pages=5), kv_page(pages=5)])
        self.assertEqual(len(http.asked), 2)
        self.assertEqual(len(found), 3)
        self.assertFalse(found.complete)
        self.assertIn("repeated", found.reason)

    async def test_the_page_limit_makes_the_run_incomplete(self):
        with patch.object(kv.KavakScraper, "MAX_PAGES", 1):
            found, http = await self.search([kv_page()])
        self.assertEqual(len(http.asked), 1)
        self.assertEqual(len(found), 3)
        self.assertFalse(found.complete)
        self.assertIn("first 1 pages of /ar/usados/suv, of 15", found.reason)

    async def test_a_page_without_the_filter_applied_fails_the_run(self):
        for page in (kv_page(body="wagon"), html("kavak_search.html")):
            with self.assertRaises(kv.BodyTypeNotApplied):
                await self.search([page])
        with self.assertRaises(kv.BodyTypeNotApplied):
            await self.search([kv_page(pages=2), kv_page("kavak_bodytype_suv_p1.html", body="wagon")])

    async def test_cards_without_a_body_in_the_slug_get_the_code_and_others_keep_theirs(self):
        page = kv_page(pages=1)
        page = page.replace("jeep-compass-13_t270_limited_plus_auto-suv-2022",
                            "jeep-compass-13_t270_limited_plus_auto-2022")
        page = page.replace("toyota-corolla_cross-20_seg_cvt-suv-2022", "toyota-corolla_cross-20_seg_cvt-pickup-2022")
        found, _ = await self.search([page])
        by_id = {c.listing_id: c.carroceria for c in found}
        self.assertEqual(by_id["556070"], "suv")         # sealed from the verified page
        self.assertNotIn("555915", by_id)                # its own slug says pick-up

    async def test_rural_searches_wagon(self):
        page = kv_page(pages=1, body="wagon").replace("-suv-", "-wagon-")
        found, http = await self.search([page], {"carroceria": "rural"})
        self.assertEqual(http.asked, ["https://www.kavak.com/ar/usados/wagon"])
        self.assertEqual({c.carroceria for c in found}, {"wagon"})

    async def test_errors(self):
        with self.assertRaises(CollectorBlocked):
            await self.search([(403, "")])
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            await self.search([(404, "")])
        with self.assertRaisesRegex(RuntimeError, "no cars"):
            await self.search(["<html><body>otra cosa</body></html>"])
        empty = '<script>self.__next_f.push([1,"{\\"resultsQuantity\\":\\"0 Resultados\\"}"])</script>'
        found, _ = await self.search([empty])
        self.assertEqual((list(found), found.complete), ([], True))
        with self.assertRaisesRegex(ValueError, "no listing"):
            await self.search([], {"carroceria": "coupe"})

    async def test_later_failures_keep_the_cards(self):
        found, _ = await self.search([kv_page(pages=3), OSError("connection reset")])
        self.assertEqual(len(found), 3)
        self.assertFalse(found.complete)
        self.assertIn("OSError", found.reason)

    async def test_a_model_with_a_body_type_still_reads_its_own_listing(self):
        self.assertIsNone(kv._searched_body_type({"marca": "Ford", "modelo": "Ka", "carroceria": "sedan"}))
        page = html("kavak_model_sandero_p0.html").replace("37 Resultados", "3 Resultados")             .replace('\\"pages\\":2', '\\"pages\\":1')
        found, http = await self.search([page], {"marca": "Ford", "modelo": "Ka", "carroceria": "sedan"})
        self.assertEqual(http.asked, ["https://www.kavak.com/ar/usados/ford-ka"])


class KavakModelSearchTests(unittest.IsolatedAsyncioTestCase):
    """Lives pages of www.kavak.com/ar/usados/renault-sandero captured on 24/10/2026:
    37 cars in 2 pages of 30, the reserved ones (no price) last."""

    async def search(self, outcomes, filters=None):
        http = FakeHttp(outcomes)
        with patch.object(kv, "fetch_page", http), patch.object(kv, "_page_pause", AsyncMock()):
            found = await kv.KavakScraper().search(
                {"marca": "Renault", "modelo": "Sandero"} if filters is None else filters)
        return found, http

    async def test_reads_every_page_of_the_model_with_plain_gets(self):
        found, http = await self.search([html("kavak_model_sandero_p0.html"), html("kavak_model_sandero_p1.html")])
        self.assertEqual(http.asked, ["https://www.kavak.com/ar/usados/renault-sandero",
                                      "https://www.kavak.com/ar/usados/renault-sandero?page=1"])
        self.assertTrue(found.complete, found.reason)
        self.assertEqual([c.listing_id for c in found],
                         ["557305", "554522", "553483", "550663", "557311", "554179"])
        self.assertEqual([c.precio is not None for c in found], [True] * 3 + [False] * 3)
        self.assertEqual({(c.marca, c.modelo.split()[0]) for c in found}, {("Renault", "Sandero")})

    async def test_state_of_the_model_page(self):
        state = kv.list_state(html("kavak_model_sandero_p0.html"))
        self.assertEqual((state.body_types, state.pages, state.total), (frozenset(), 2, 37))

    async def test_a_single_page_model_asks_once_and_no_stock_is_an_empty_complete_read(self):
        one = html("kavak_model_sandero_p0.html").replace('\\"pages\\":2', '\\"pages\\":1')
        found, http = await self.search([one])
        self.assertEqual(len(http.asked), 1)
        self.assertTrue(found.complete)
        empty = '<script>self.__next_f.push([1,"{\\"resultsQuantity\\":\\"0 Resultados\\"}"])</script>'
        found, _ = await self.search([empty])
        self.assertEqual((list(found), found.complete), ([], True))

    async def test_a_make_alone_and_the_whole_catalog(self):
        _, http = await self.search([html("kavak_model_sandero_p0.html").replace('\\"pages\\":2', '\\"pages\\":1')],
                                    {"marca": "Land Rover"})
        self.assertEqual(http.asked, ["https://www.kavak.com/ar/usados/land-rover"])
        _, http = await self.search([html("kavak_model_sandero_p0.html").replace('\\"pages\\":2', '\\"pages\\":1')], {})
        self.assertEqual(http.asked, ["https://www.kavak.com/ar/usados"])

    async def test_a_later_page_that_fails_keeps_the_cards_as_a_partial_read(self):
        found, _ = await self.search([html("kavak_model_sandero_p0.html"), OSError("connection reset")])
        self.assertEqual(len(found), 3)
        self.assertFalse(found.complete)
        self.assertIn("OSError", found.reason)

    async def test_the_page_limit_is_a_partial_read(self):
        with patch.object(kv.KavakScraper, "MAX_PAGES", 1):
            found, http = await self.search([html("kavak_model_sandero_p0.html")])
        self.assertEqual(len(http.asked), 1)
        self.assertFalse(found.complete)
        self.assertIn("first 1 pages of /ar/usados/renault-sandero, of 2", found.reason)

    async def test_the_first_page_failing_fails_the_run(self):
        with self.assertRaises(CollectorBlocked):
            await self.search([(429, "")])
        with self.assertRaises(OSError):
            await self.search([OSError("connection reset")])

    async def test_it_declares_the_wider_read(self):
        self.assertEqual(kv.KavakScraper.COVERAGE_VERSION, 2)


if __name__ == "__main__":
    unittest.main()
