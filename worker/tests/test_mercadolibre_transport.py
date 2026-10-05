"""Tecc transport contract: persistent Chrome, shared search/detail state, real walls."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from bs4 import BeautifulSoup

import config
from collectors import mercadolibre as ml
from collectors import _mercadolibre_browser as transport
from collectors.base import CollectorBlocked


FIXTURES = Path(__file__).parent / "fixtures" / "html"


class PersistentChromeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # IsolatedAsyncioTestCase gives each test a different loop.
        self.lock = patch.object(transport, "_lock", asyncio.Lock())
        self.lock.start()
        self.addCleanup(self.lock.stop)

    async def test_uses_installed_visible_chrome_and_a_persistent_profile(self):
        ctx = MagicMock(close=AsyncMock())
        pw = MagicMock()
        pw.chromium.launch_persistent_context = AsyncMock(return_value=ctx)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=pw)
        manager.__aexit__ = AsyncMock(return_value=False)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(config, "ML_BROWSER_PROFILE_DIR", tmp), \
                patch.object(transport, "async_playwright", return_value=manager):
            async with transport.mercadolibre_context() as actual:
                self.assertIs(actual, ctx)
            pw.chromium.launch_persistent_context.assert_awaited_once_with(
                str(Path(tmp).resolve()), channel="chrome", headless=False,
            )
        ctx.close.assert_awaited_once()

    async def test_closes_profile_when_the_collector_fails(self):
        ctx = MagicMock(close=AsyncMock())
        pw = MagicMock()
        pw.chromium.launch_persistent_context = AsyncMock(return_value=ctx)
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=pw)
        manager.__aexit__ = AsyncMock(return_value=False)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(config, "ML_BROWSER_PROFILE_DIR", tmp), \
                patch.object(transport, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "collector failed"):
                async with transport.mercadolibre_context():
                    raise RuntimeError("collector failed")
        ctx.close.assert_awaited_once()

    async def test_search_and_enrichment_cannot_open_the_same_profile_concurrently(self):
        active = 0
        peak = 0

        async def launch(*args, **kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            ctx = MagicMock()

            async def close():
                nonlocal active
                active -= 1

            ctx.close = close
            return ctx

        pw = MagicMock()
        pw.chromium.launch_persistent_context = launch
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=pw)
        manager.__aexit__ = AsyncMock(return_value=False)

        async def use_profile():
            async with transport.mercadolibre_context():
                await asyncio.sleep(0)

        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(config, "ML_BROWSER_PROFILE_DIR", tmp), \
                patch.object(transport, "async_playwright", return_value=manager):
            await asyncio.gather(use_profile(), use_profile())
        self.assertEqual((peak, active), (1, 0))

    async def test_failed_launch_releases_the_profile_for_the_next_attempt(self):
        ctx = MagicMock(close=AsyncMock())
        pw = MagicMock()
        pw.chromium.launch_persistent_context = AsyncMock(side_effect=[RuntimeError("launch failed"), ctx])
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=pw)
        manager.__aexit__ = AsyncMock(return_value=False)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(config, "ML_BROWSER_PROFILE_DIR", tmp), \
                patch.object(transport, "async_playwright", return_value=manager):
            with self.assertRaisesRegex(RuntimeError, "launch failed"):
                async with transport.mercadolibre_context():
                    self.fail("A failed launch must not yield a context")
            async with transport.mercadolibre_context() as actual:
                self.assertIs(actual, ctx)
        self.assertEqual(manager.__aexit__.await_count, 2)
        ctx.close.assert_awaited_once()


class Page:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.url = "about:blank"
        self.html = ""
        self.close = AsyncMock()
        self.asked = []

    async def goto(self, url, **kwargs):
        self.asked.append(url)
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        self.url, self.html, status = outcome
        return MagicMock(status=status)

    def locator(self, selector):
        doc = BeautifulSoup(self.html, "lxml")
        return MagicMock(
            inner_text=AsyncMock(return_value=doc.get_text(" ", strip=True)),
            count=AsyncMock(return_value=len(doc.select(selector))),
        )

    async def wait_for_selector(self, selector, **kwargs):
        if not BeautifulSoup(self.html, "lxml").select(selector):
            raise ml.PlaywrightTimeoutError("selector missing")

    async def content(self):
        return self.html


class CollectorTransportTests(unittest.IsolatedAsyncioTestCase):
    def context(self, page):
        @asynccontextmanager
        async def context():
            yield MagicMock(new_page=AsyncMock(return_value=page))
        return patch.object(ml, "mercadolibre_context", context)

    async def test_search_keeps_parsing_cards_with_the_tecc_transport(self):
        html = (FIXTURES / "mercadolibre_search.html").read_text(encoding="utf-8")
        page = Page([
            ("https://listado.mercadolibre.com.ar/autos/toyota-corolla", html, 200),
            ("https://listado.mercadolibre.com.ar/autos/toyota-corolla", '<div class="ui-search-rescue"></div>', 200),
        ])
        with self.context(page), patch.object(ml, "_page_pause", AsyncMock()):
            found = await ml.MercadoLibreScraper().search({"marca": "Toyota", "modelo": "Corolla"})
        self.assertEqual(len(found), 3)
        page.close.assert_awaited_once()

    async def test_captcha_url_is_reported_as_security_challenge_even_without_body(self):
        page = Page([("https://www.mercadolibre.com.ar/captcha/wall/logged", "", 200)])
        with self.context(page):
            with self.assertRaisesRegex(CollectorBlocked, "security challenge"):
                await ml.MercadoLibreScraper().search({})
        page.close.assert_awaited_once()

    async def test_later_wall_preserves_already_read_cards(self):
        html = (FIXTURES / "mercadolibre_search.html").read_text(encoding="utf-8")
        page = Page([
            ("https://listado.mercadolibre.com.ar/autos", html, 200),
            ("https://www.mercadolibre.com.ar/captcha/wall/logged", "", 200),
        ])
        with self.context(page), patch.object(ml, "_page_pause", AsyncMock()):
            found = await ml.MercadoLibreScraper().search({})
        self.assertEqual(len(found), 3)

    async def test_detail_uses_chrome_and_returns_final_url_and_http_status(self):
        url = "https://auto.mercadolibre.com.ar/MLA-1675249827-toyota-_JM"
        html = (FIXTURES / "mercadolibre_detail.html").read_text(encoding="utf-8")
        page = Page([(url, html, 200)])
        with self.context(page):
            result = await ml.MercadoLibreScraper().fetch_detail_page(url)
        self.assertEqual((result.url, result.status, result.html), (url, 200, html))
        page.close.assert_awaited_once()

    async def test_blocked_detail_is_not_parsed_as_missing_or_delisted(self):
        page = Page([("https://www.mercadolibre.com.ar/gz/account-verification", "Ingresá", 200)])
        with self.context(page):
            with self.assertRaisesRegex(CollectorBlocked, "login required"):
                await ml.MercadoLibreScraper().fetch_detail_page("https://auto.mercadolibre.com.ar/MLA-1-x")

    async def test_search_http_error_does_not_silently_return_zero_results(self):
        page = Page([("https://listado.mercadolibre.com.ar/autos", "error", 503)])
        with self.context(page):
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                await ml.MercadoLibreScraper().search({})

    async def test_gone_detail_survives_404_or_missing_pdp_selector(self):
        url = "https://auto.mercadolibre.com.ar/MLA-1-x"
        for status, html in [(404, ""), (200, "<body>Publicación finalizada</body>")]:
            with self.subTest(status=status):
                page = Page([(url, html, status)])
                with self.context(page):
                    detail = await ml.MercadoLibreScraper().fetch_detail(url)
                self.assertTrue(detail.gone)
                page.close.assert_awaited_once()

    async def test_detail_http_error_is_not_a_gone_listing(self):
        page = Page([("https://auto.mercadolibre.com.ar/MLA-1-x", "error", 503)])
        with self.context(page):
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                await ml.MercadoLibreScraper().fetch_detail("https://auto.mercadolibre.com.ar/MLA-1-x")
        page.close.assert_awaited_once()

    async def test_detail_challenge_after_selector_wait_still_fails(self):
        url = "https://auto.mercadolibre.com.ar/MLA-1-x"
        page = Page([(url, "<body>Loading</body>", 200)])

        async def delayed_challenge(*args, **kwargs):
            page.url = "https://www.mercadolibre.com.ar/captcha/wall/logged"
            raise ml.PlaywrightTimeoutError("verification appeared")

        page.wait_for_selector = delayed_challenge
        with self.context(page):
            with self.assertRaisesRegex(CollectorBlocked, "security challenge"):
                await ml.MercadoLibreScraper().fetch_detail(url)
        page.close.assert_awaited_once()

    async def test_first_page_failures_propagate_but_later_failures_keep_cards(self):
        html = (FIXTURES / "mercadolibre_search.html").read_text(encoding="utf-8")
        first = ("https://listado.mercadolibre.com.ar/autos", html, 200)
        failures = [ml.PlaywrightTimeoutError("navigation failed"),
                    ("https://listado.mercadolibre.com.ar/autos", "missing selector", 200),
                    ("https://listado.mercadolibre.com.ar/autos", "server error", 503)]
        for failure in failures:
            with self.subTest(failure=str(failure)):
                page = Page([failure])
                with self.context(page):
                    with self.assertRaises((ml.PlaywrightTimeoutError, RuntimeError)):
                        await ml.MercadoLibreScraper().search({})
                page.close.assert_awaited_once()
                page = Page([first, failure])
                with self.context(page), patch.object(ml, "_page_pause", AsyncMock()):
                    found = await ml.MercadoLibreScraper().search({})
                self.assertEqual(len(found), 3)
                page.close.assert_awaited_once()

    async def test_legitimate_no_results_is_successful(self):
        page = Page([("https://listado.mercadolibre.com.ar/autos", '<div class="ui-search-rescue"></div>', 200)])
        with self.context(page):
            found = await ml.MercadoLibreScraper().search({})
        self.assertEqual(found, [])
        page.close.assert_awaited_once()

    async def test_manual_setup_keeps_waiting_on_non_200_despite_cards(self):
        html = '<li class="ui-search-layout__item"></li>'
        url = "https://listado.mercadolibre.com.ar/autos"
        page = Page([(url, html, 503), (url, html, 200)])
        with self.context(page), patch.object(ml, "_wait_for_enter", AsyncMock()) as enter:
            await ml._login_and_save()
        self.assertEqual(enter.await_count, 1)
        page.close.assert_awaited_once()

    async def test_manual_setup_does_not_succeed_until_a_search_is_readable(self):
        wall = ("https://www.mercadolibre.com.ar/captcha/wall/logged", "", 200)
        readable = ("https://listado.mercadolibre.com.ar/autos", '<li class="ui-search-layout__item"></li>', 200)
        page = Page([wall, readable])
        with self.context(page), patch.object(ml, "_wait_for_enter", AsyncMock()) as enter:
            await ml._login_and_save()
        self.assertEqual(enter.await_count, 1)
        self.assertEqual(len(page.asked), 2)
        page.close.assert_awaited_once()
