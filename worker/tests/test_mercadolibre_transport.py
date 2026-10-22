"""Mercado Libre transport: plain HTTP on the public hosts, real walls never passed."""
from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from collectors import mercadolibre as ml
from collectors._http import Page
from collectors.base import CollectorBlocked


FIXTURES = Path(__file__).parent / "fixtures" / "html"
CAPTCHA = ("https://www.mercadolibre.com.ar/captcha/wall/logged", "", 200)


class FakeHttp:
    """Stands in for collectors._http.fetch_page: each GET takes the next
    outcome, a (final_url, html, status) or an exception, and is recorded."""

    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.asked: list[str] = []

    async def __call__(self, url, **kwargs):
        self.asked.append(url)
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        final, html, status = outcome
        return Page(status, final, html)

    def patch(self):
        return patch.object(ml, "fetch_page", self)


class CollectorTransportTests(unittest.IsolatedAsyncioTestCase):
    async def search(self, outcomes, filters=None):
        http = FakeHttp(outcomes)
        with http.patch(), patch.object(ml, "_page_pause", AsyncMock()):
            found = await ml.MercadoLibreScraper().search(filters or {})
        return found, http

    async def test_search_reads_the_public_host_and_parses_cards(self):
        html = (FIXTURES / "mercadolibre_search.html").read_text(encoding="utf-8")
        found, http = await self.search(
            [("https://autos.mercadolibre.com.ar/toyota/corolla/_NoIndex_True", html, 200)],
            {"marca": "Toyota", "modelo": "Corolla"})
        self.assertEqual(len(found), 3)
        self.assertEqual(http.asked, ["https://autos.mercadolibre.com.ar/toyota/corolla/_NoIndex_True"])

    async def test_a_full_page_reads_the_next_one(self):
        html = (FIXTURES / "mercadolibre_search.html").read_text(encoding="utf-8")
        with patch.object(ml, "PAGE_SIZE", 3):
            found, http = await self.search([
                ("https://autos.mercadolibre.com.ar/_NoIndex_True", html, 200),
                ("https://autos.mercadolibre.com.ar/_Desde_4_NoIndex_True", '<div class="ui-search-rescue"></div>', 200),
            ])
        self.assertEqual(len(found), 3)
        self.assertEqual(http.asked[1], "https://autos.mercadolibre.com.ar/_Desde_4_NoIndex_True")

    async def test_captcha_url_is_reported_as_security_challenge_even_without_body(self):
        with self.assertRaisesRegex(CollectorBlocked, "security challenge"):
            await self.search([CAPTCHA])

    async def test_an_account_wall_is_login_required(self):
        wall = ("https://www.mercadolibre.com.ar/gz/account-verification?go=x", "Hola! Para continuar, ingresá a tu cuenta.", 200)
        with self.assertRaisesRegex(CollectorBlocked, "login required"):
            await self.search([wall])

    async def test_rate_limits_and_forbidden_are_blocks(self):
        for status in (403, 429):
            with self.subTest(status=status):
                with self.assertRaisesRegex(CollectorBlocked, f"HTTP {status}"):
                    await self.search([("https://autos.mercadolibre.com.ar/_NoIndex_True", "nope", status)])

    async def test_later_wall_preserves_already_read_cards(self):
        html = (FIXTURES / "mercadolibre_search.html").read_text(encoding="utf-8")
        with patch.object(ml, "PAGE_SIZE", 3):
            found, _ = await self.search([("https://autos.mercadolibre.com.ar/_NoIndex_True", html, 200), CAPTCHA])
        self.assertEqual(len(found), 3)

    async def test_search_http_error_does_not_silently_return_zero_results(self):
        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            await self.search([("https://autos.mercadolibre.com.ar/_NoIndex_True", "error", 503)])

    async def test_a_page_without_a_results_list_is_an_error_not_zero_results(self):
        with self.assertRaisesRegex(RuntimeError, "no results list"):
            await self.search([("https://autos.mercadolibre.com.ar/_NoIndex_True", "<html>otra cosa</html>", 200)])

    async def test_first_page_failures_propagate_but_later_failures_keep_cards(self):
        html = (FIXTURES / "mercadolibre_search.html").read_text(encoding="utf-8")
        first = ("https://autos.mercadolibre.com.ar/_NoIndex_True", html, 200)
        failures = [OSError("connection reset"),
                    ("https://autos.mercadolibre.com.ar/_Desde_4_NoIndex_True", "missing list", 200),
                    ("https://autos.mercadolibre.com.ar/_Desde_4_NoIndex_True", "server error", 503)]
        for failure in failures:
            with self.subTest(failure=str(failure)):
                with self.assertRaises((OSError, RuntimeError)):
                    await self.search([failure])
                with patch.object(ml, "PAGE_SIZE", 3):
                    found, _ = await self.search([first, failure])
                self.assertEqual(len(found), 3)

    async def test_legitimate_no_results_is_successful(self):
        found, _ = await self.search([("https://autos.mercadolibre.com.ar/_NoIndex_True", '<div class="ui-search-rescue"></div>', 200)])
        self.assertEqual(found, [])

    async def test_detail_returns_final_url_and_http_status(self):
        url = "https://auto.mercadolibre.com.ar/MLA-1675249827-toyota-_JM"
        html = (FIXTURES / "mercadolibre_detail.html").read_text(encoding="utf-8")
        http = FakeHttp([(url, html, 200)])
        with http.patch():
            result = await ml.MercadoLibreScraper().fetch_detail_page(url)
        self.assertEqual((result.url, result.status, result.html), (url, 200, html))

    async def test_blocked_detail_is_not_parsed_as_missing_or_delisted(self):
        http = FakeHttp([("https://www.mercadolibre.com.ar/gz/account-verification", "Para continuar, ingresá", 200)])
        with http.patch():
            with self.assertRaisesRegex(CollectorBlocked, "login required"):
                await ml.MercadoLibreScraper().fetch_detail_page("https://auto.mercadolibre.com.ar/MLA-1-x")

    async def test_an_ad_saying_para_continuar_is_not_a_login_wall(self):
        # MLA-3770582028 (22/10/2026): "lista para continuar en uso" in the description
        # plus the header's "Ingresá" failed the Ford Ka scan as blocked.
        url = "https://auto.mercadolibre.com.ar/MLA-3770582028-ford-ka-15-se-_JM"
        html = (FIXTURES / "mercadolibre_detail_para_continuar.html").read_text(encoding="utf-8")
        http = FakeHttp([(url, html, 200)])
        with http.patch():
            published = await ml.MercadoLibreScraper()._publication_date(ml.Listing(
                source="mercadolibre", listing_id="MLA3770582028", titulo="Ford Ka 1.5 Se", url=url))
        self.assertIsNotNone(published)

        wall = (url, "<body>Ingresá. Hola! Para continuar, ingresá a tu cuenta.</body>", 200)
        with FakeHttp([wall]).patch(), self.assertRaisesRegex(CollectorBlocked, "login required"):
            await ml.MercadoLibreScraper().fetch_detail_page(url)

    async def test_gone_detail_survives_404_or_finished_text(self):
        url = "https://auto.mercadolibre.com.ar/MLA-1-x"
        for status, html in [(404, ""), (200, "<body>Publicación finalizada</body>")]:
            with self.subTest(status=status):
                http = FakeHttp([(url, html, status)])
                with http.patch():
                    detail = await ml.MercadoLibreScraper().fetch_detail(url)
                self.assertTrue(detail.gone)

    async def test_detail_http_error_is_not_a_gone_listing(self):
        http = FakeHttp([("https://auto.mercadolibre.com.ar/MLA-1-x", "error", 503)])
        with http.patch():
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                await ml.MercadoLibreScraper().fetch_detail("https://auto.mercadolibre.com.ar/MLA-1-x")


if __name__ == "__main__":
    unittest.main()
