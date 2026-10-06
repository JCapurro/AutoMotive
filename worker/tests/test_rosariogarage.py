"""RosarioGarage parsers and public finder traversal, entirely offline."""
from __future__ import annotations

from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlparse

import httpx

from collectors._http import soup
from collectors.base import CollectorBlocked
from collectors.rosariogarage import RosarioGarageScraper

FIXTURES = Path(__file__).parent / "fixtures" / "html"
DETAIL_URL = "https://www.rosariogarage.com/index.php?action=carro/showProduct&itmId=5645199&rbrId=107"
FILTERS = {"marca": "Ford", "modelo": "Fiesta"}


def fixture(kind: str) -> str:
    return (FIXTURES / f"rosariogarage_{kind}.html").read_text(encoding="utf-8")


def results(ids: list[int], offsets: list[int] = ()) -> str:
    cards = "".join(
        f'<div class="box_aviso_base"><div class="box_aviso_tit">'
        f'<a href="/index.php?action=carro/showProduct&itmId={n}&rbrId=107">'
        '<strong class="list_type_anuncio">Ford Fiesta SE</strong>'
        '<span>MT</span><span>2018</span><span>Nafta</span><span>102.000 km.</span></a></div>'
        '<div class="precio">$ 17.700.000</div></div>' for n in ids
    )
    pager = '<select name="pagerTo">' + "".join(f'<option value="{n}">{n}</option>' for n in offsets) + '</select>'
    return f'<html><body><div id="item_results">{cards}</div>{pager}</body></html>'


class Site:
    rubros = {"Autos": "107", "Camionetas": "109", "Utilitarios": "108"}

    def __init__(self, pages=None, fail=None):
        self.pages, self.fail, self.asked, self.bootstraps = pages or {}, fail or {}, [], []

    def __call__(self, request):
        url = urlparse(str(request.url))
        category = url.path.lstrip("/")
        if category in self.rubros:
            self.bootstraps.append(category)
            doc = soup(fixture("search"))
            doc.select_one('#frm_buscador [name="rbrId"]')["value"] = self.rubros[category]
            # The enum can change; every query must use the form's current value.
            for option in doc.select('select[name="mrkId"] option[value="1037"]'):
                option["value"] = "777"
            return httpx.Response(200, text=str(doc))
        qs = parse_qs(url.query)
        key = (qs.get("rbrId", [""])[0], int(qs.get("o", ["0"])[0]))
        self.asked.append(qs)
        if self.fail.get(key):
            outcome = self.fail[key].pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return httpx.Response(outcome, text="")
        return httpx.Response(200, text=self.pages.get(key, results([])))


def scraper(site, categories=("Autos",)):
    collector = RosarioGarageScraper(transport=httpx.MockTransport(site))
    collector.CATEGORIES = categories
    collector.PAGE_PAUSE_SECONDS = collector.RETRY_PAUSE_SECONDS = 0
    return collector


class RosarioGarageParserTests(unittest.TestCase):
    def test_real_cards_keep_ars_usd_zero_km_and_consultation(self):
        cards = RosarioGarageScraper.parse_search(fixture("search"))
        self.assertEqual(len(cards), 3)
        ars, usd, consultation = cards
        self.assertEqual((ars.listing_id, ars.precio, ars.moneda, ars.anio, ars.km),
                         ("5645199", 17_700_000.0, "ARS", 2018, 102_000))
        self.assertEqual((ars.titulo, ars.transmision, ars.combustible), ("Ford Fiesta Se", "MT", "Nafta"))
        self.assertEqual((usd.precio, usd.moneda, usd.km), (23_900.0, "USD", 0))
        self.assertEqual((consultation.precio, consultation.moneda), (None, None))
        self.assertIn("resources_production", ars.imagenes[0])
        self.assertNotIn("default-", ars.imagenes[0])
        self.assertIsNone(ars.marca)  # Combined title is resolved by normalization.
        self.assertIsNone(ars.modelo)
        self.assertIsNone(ars.ubicacion)
        self.assertIsNone(ars.published_at)

    def test_zero_price_is_preserved(self):
        item = RosarioGarageScraper.parse_search(results([1]).replace("$ 17.700.000", "U$S 0"))[0]
        self.assertEqual((item.precio, item.moneda), (0.0, "USD"))

    def test_global_featured_cards_do_not_leak_into_filtered_results(self):
        outside = results([99]).replace('id="item_results"', 'class="premium"')
        html = str(soup(outside).select_one('.premium')) + str(soup(results([1, 1])).select_one('#item_results'))
        items = RosarioGarageScraper.parse_search(html)
        self.assertEqual([item.listing_id for item in items], ["1"])

    def test_pager_follows_advertised_offsets_and_ignores_last_shortcut(self):
        self.assertEqual(RosarioGarageScraper._next_offset(results([1], [0, 47, 94]), 0), 47)
        self.assertEqual(RosarioGarageScraper._next_offset(results([1], [0, 47, 94]), 47), 94)
        html = '<div class="paginador"><a class="next" href="javascript:jumpToPage(95)"></a><a class="next last" href="javascript:jumpToPage(950)"></a></div>'
        self.assertEqual(RosarioGarageScraper._next_offset(html, 0), 95)

    def test_real_detail_is_requested_vehicle_without_recommendation_data(self):
        detail = RosarioGarageScraper.parse_detail(fixture("detail"), DETAIL_URL)
        self.assertFalse(detail.gone)
        item = detail.listing
        self.assertEqual((item.listing_id, item.marca, item.version), ("5645199", "Ford", "Fiesta SE"))
        self.assertEqual((item.anio, item.km, item.precio, item.moneda), (2018, 102_000, 17_700_000.0, "ARS"))
        self.assertEqual((item.vendedor, item.ubicacion), ("particular", "Rosario, Santa Fe"))
        self.assertEqual((item.transmision, item.combustible), ("Manual (MT)", "Nafta"))
        self.assertIn("Impecable estado", item.descripcion)
        self.assertEqual(len(item.imagenes), 10)
        self.assertTrue(all("/big/" in url and "/5645199/" in url for url in item.imagenes))
        self.assertIsNone(item.modelo)
        self.assertIsNone(item.published_at)
        self.assertEqual(item.atributos["Versión"], "Fiesta SE")

    def test_detail_usd_zero_km_and_unstated_values(self):
        html = fixture("detail").replace("$ 17.700.000", "U$S 11.000").replace("102.000", "0")
        item = RosarioGarageScraper.parse_detail(html, DETAIL_URL).listing
        self.assertEqual((item.precio, item.moneda, item.km), (11_000.0, "USD", 0))
        doc = soup(html)
        for span in doc.select('.box-data span'):
            if span.get_text(strip=True).rstrip(":") == "Kilometraje":
                span.next_sibling.extract()
        self.assertIsNone(RosarioGarageScraper.parse_detail(str(doc), DETAIL_URL).listing.km)

    def test_404_and_410_are_gone(self):
        for status in (404, 410):
            with self.subTest(status=status):
                detail = RosarioGarageScraper.parse_detail("", DETAIL_URL, status)
                self.assertTrue(detail.gone)
                self.assertEqual(detail.gone_reason, str(status))

    def test_replaced_vehicle_requires_explicit_different_identity(self):
        html = fixture("detail").replace('itmId=5645199', 'itmId=123')
        detail = RosarioGarageScraper.parse_detail(html, DETAIL_URL)
        self.assertTrue(detail.gone)
        self.assertEqual(detail.gone_reason, "different listing")

    def test_missing_identity_is_a_parse_failure_not_a_removal(self):
        doc = soup(fixture("detail"))
        doc.select_one('link[rel="canonical"]').decompose()
        with self.assertRaisesRegex(RuntimeError, "identity missing"):
            RosarioGarageScraper.parse_detail(str(doc), DETAIL_URL)

    def test_failed_detail_never_means_gone(self):
        for status in (401, 403, 429):
            with self.subTest(status=status), self.assertRaises(CollectorBlocked):
                RosarioGarageScraper.parse_detail("", DETAIL_URL, status)
        for status in (500, 502):
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                RosarioGarageScraper.parse_detail("", DETAIL_URL, status)
        for html in ('<title>Just a moment...</title>', '<input type="password">'):
            with self.subTest(html=html), self.assertRaises(CollectorBlocked):
                RosarioGarageScraper.parse_detail(html, DETAIL_URL)
        for html in ('<h1>Vehículo vendido</h1>', '<div id="item_results">recommendations</div>'):
            with self.subTest(html=html), self.assertRaises(RuntimeError):
                RosarioGarageScraper.parse_detail(html, DETAIL_URL)

    def test_ordinary_contact_captcha_is_not_a_wall(self):
        html = fixture("detail") + '<div class="g-recaptcha"></div><script src="https://www.google.com/recaptcha/api.js"></script>'
        self.assertIsNotNone(RosarioGarageScraper.parse_detail(html, DETAIL_URL).listing)

    def test_fixtures_do_not_keep_contact_channels(self):
        for kind in ("search", "detail"):
            html = fixture(kind)
            for marker in ("wa.me", "tel:", "mailto:", "156617932", "hernan"):
                self.assertNotIn(marker, html)


class RosarioGarageSearchTests(unittest.IsolatedAsyncioTestCase):
    async def test_filters_use_live_form_ids_and_actual_offset_options(self):
        site = Site({("107", 0): results([1], [0, 95, 190]),
                     ("107", 95): results([2], [0, 95, 190]),
                     ("107", 190): results([3])})
        filters = {**FILTERS, "anio_min": 2018, "anio_max": 2019, "km_max": 150_000,
                   "moneda": "ARS", "precio_max": 20_000_000}
        items = await scraper(site).search(filters)
        self.assertEqual([item.listing_id for item in items], ["1", "2", "3"])
        self.assertEqual([q["o"] for q in site.asked], [["0"], ["95"], ["190"]])
        for qs in site.asked:
            self.assertEqual(qs["action"], ["finder/search"])
            self.assertEqual(qs["mrkId"], ["777"])
            self.assertEqual(qs["itmModelDesc"], ["Fiesta"])
            self.assertEqual(qs["optKm"], ["usados"])
            self.assertEqual(qs["year[from]"], ["2018"])
            self.assertEqual(qs["year[to]"], ["2019"])
            self.assertEqual(qs["km[to]"], ["150000"])
            self.assertEqual(qs["precio[to]"], ["20000000"])
        self.assertEqual(site.bootstraps, ["Autos"])

    async def test_three_vehicle_categories_and_cross_category_deduplication(self):
        site = Site({("107", 0): results([1]), ("109", 0): results([2, 1]), ("108", 0): results([3])})
        items = await scraper(site, RosarioGarageScraper.CATEGORIES).search(FILTERS)
        self.assertEqual([item.listing_id for item in items], ["1", "2", "3"])
        self.assertEqual([q["rbrId"] for q in site.asked], [["107"], ["109"], ["108"]])

    async def test_repeated_page_with_more_results_reports_incomplete_pagination(self):
        site = Site({("107", 0): results([1], [0, 95, 190]), ("107", 95): results([1], [0, 95, 190])})
        with self.assertRaisesRegex(RuntimeError, "pagination repeated"):
            await scraper(site).search(FILTERS)
        self.assertEqual(len(site.asked), 2)

    async def test_retry_server_failures_and_network_failures(self):
        site = Site({("107", 0): results([1])},
                    {("107", 0): [503, httpx.ReadTimeout("slow")]})
        self.assertEqual(len(await scraper(site).search(FILTERS)), 1)
        self.assertEqual(len(site.asked), 3)

    async def test_first_page_failure_is_reported(self):
        site = Site(fail={("107", 0): [503, 503, 503]})
        with self.assertRaises(RuntimeError):
            await scraper(site).search(FILTERS)

    async def test_later_page_failure_is_not_reported_as_a_healthy_complete_read(self):
        for outcomes in ([503] * 3, [httpx.ConnectError("down")] * 3):
            with self.subTest(outcomes=outcomes):
                site = Site({("107", 0): results([1], [0, 95])}, {("107", 95): list(outcomes)})
                with self.assertRaises((RuntimeError, httpx.HTTPError)):
                    await scraper(site).search(FILTERS)

    async def test_unknown_brand_never_falls_back_to_all_ads(self):
        site = Site()
        self.assertEqual(await scraper(site).search({"marca": "Brand Not Listed", "modelo": "Fiesta"}), [])
        self.assertEqual(site.asked, [])

    async def test_invalid_layout_or_block_is_reported(self):
        for html, error in (("<h1>New site</h1>", RuntimeError),
                            ("<input type='password'>", CollectorBlocked),
                            ("<title>Just a moment...</title>", CollectorBlocked)):
            with self.subTest(html=html), self.assertRaises(error):
                await scraper(Site({("107", 0): html})).search(FILTERS)

    async def test_later_block_is_reported_instead_of_empty_success(self):
        site = Site({("107", 0): results([1], [0, 95])}, {("107", 95): [403]})
        with self.assertRaises(CollectorBlocked):
            await scraper(site).search(FILTERS)

    async def test_detail_fetch_uses_own_mockable_client_and_retries(self):
        asked = []

        def handler(request):
            asked.append(str(request.url))
            return httpx.Response(503 if len(asked) == 1 else 200, text=fixture("detail"))

        collector = scraper(handler)
        detail = await collector.fetch_detail(DETAIL_URL)
        self.assertEqual(detail.listing.listing_id, "5645199")
        self.assertEqual(asked, [DETAIL_URL, DETAIL_URL])

    async def test_detail_http_not_found_stays_gone_and_forbidden_is_blocked(self):
        for status in (404, 410):
            collector = scraper(lambda request: httpx.Response(status, text=""))
            self.assertTrue((await collector.fetch_detail(DETAIL_URL)).gone)
        collector = scraper(lambda request: httpx.Response(403, text=""))
        with self.assertRaises(CollectorBlocked):
            await collector.fetch_detail(DETAIL_URL)


if __name__ == "__main__":
    unittest.main()
