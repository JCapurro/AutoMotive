"""V6 and AutoCosmos read whole (INVENTORY_TARGET, 06/11/2026), no network.

V6 scrolls its infinite list until it stops growing or shows the total it
states. AutoCosmos reads the makes /auto/usado links to, each one's pages:
/auto/usado itself shifts its order during a long read.
"""
from __future__ import annotations

import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import httpx

from collectors import REGISTRY
from collectors import v6 as v6_module
from collectors.autocosmos import AutoCosmosScraper
from collectors.base import CollectorBlocked
from collectors.v6 import V6Scraper, stated_total
from pipeline.crawl import derive_targets, scraper_filters


def v6_card(n: int) -> str:
    return (f'<a class="tc-v2-link" href="/auto/volkswagen-gol-trend-{n:010d}">'
            f'<span class="tc-v2-title">Volkswagen Gol Trend</span></a>')


class FakeV6Page:
    """Shows `per_scroll` more cards on every wheel, up to `cards`."""

    def __init__(self, cards: int, per_scroll: int, stated: int | None):
        self.cards, self.per_scroll, self.stated, self.shown = cards, per_scroll, stated, per_scroll
        self.wheels = 0
        self.mouse = self

    async def goto(self, url, **_):
        self.url = url

    async def wait_for_timeout(self, _ms):
        pass

    async def inner_text(self, _selector):
        return f"{self.stated} resultados" if self.stated is not None else "Publicaciones"

    async def content(self):
        return "<html>" + "".join(v6_card(n) for n in range(min(self.shown, self.cards))) + "</html>"

    async def wheel(self, _x, _y):
        self.wheels += 1
        self.shown += self.per_scroll

    async def close(self):
        pass


def fake_browser(page: FakeV6Page):
    @asynccontextmanager
    async def browser_context():
        class Ctx:
            async def new_page(self):
                return page
        yield Ctx()
    return browser_context


class V6InventoryTests(unittest.IsolatedAsyncioTestCase):
    async def read(self, page: FakeV6Page, filters=None):
        with patch.object(v6_module, "browser_context", fake_browser(page)):
            return await V6Scraper().search(filters or {})

    async def test_scrolls_to_the_stated_total(self):
        page = FakeV6Page(cards=167, per_scroll=30, stated=167)
        found = await self.read(page)
        self.assertEqual(len(found), 167)
        self.assertTrue(found.complete)
        self.assertEqual(page.wheels, 5)                 # 30 → 180 shown, 167 there
        self.assertEqual(page.url, "https://www.v6.com.ar/publicaciones?sortOrder=publicadoMasNuevo")

    async def test_without_a_total_it_stops_when_the_list_stops_growing(self):
        page = FakeV6Page(cards=50, per_scroll=30, stated=None)
        found = await self.read(page)
        self.assertEqual(len(found), 50)
        self.assertTrue(found.complete)
        self.assertEqual(page.wheels, 3)                 # 30, 50, then two scrolls without a new card

    async def test_the_scroll_cap_short_of_the_total_is_a_partial_read(self):
        page = FakeV6Page(cards=5000, per_scroll=30, stated=5000)
        with patch.object(V6Scraper, "MAX_SCROLLS", 3):
            found = await self.read(page)
        self.assertEqual(len(found), 120)
        self.assertFalse(found.complete)
        self.assertIn("120 of 5000", found.reason)

    def test_the_stated_total(self):
        self.assertEqual(stated_total("Mostrando 1.234 resultados"), 1234)
        self.assertEqual(stated_total("1 resultado"), 1)
        self.assertIsNone(stated_total("Publicaciones"))


def ac_card(make: str, n: int) -> str:
    return (f'<article class="listing-card">'
            f'<a itemprop="url" href="/auto/usado/{make}/x/s/{n:032x}"></a>'
            f'<span class="listing-card__brand">{make.title()}</span>'
            f'<span class="listing-card__model">X</span></article>')


def ac_page(make: str, ids: range, *, more: bool) -> str:
    head = f'<link rel="next" href="/auto/usado/{make}?pidx=9" />' if more else ""
    return f"<html><head>{head}</head><body>{''.join(ac_card(make, n) for n in ids)}</body></html>"


HOME = ('<a href="/auto/usado/ford">Ford</a><a href="/auto/usado/peugeot">Peugeot</a>'
        '<a href="/auto/usado/ford/fiesta">Fiesta</a><a href="/auto/usado/zanella">Zanella</a>'
        + ac_page("mix", range(900, 948), more=True))


class AutoCosmosSite:
    def __init__(self, makes: dict[str, dict[int, str] | int], home: str = HOME, home_status: int = 200):
        self.makes, self.home, self.home_status, self.asked = makes, home, home_status, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        parts = request.url.path.strip("/").split("/")
        pidx = int(parse_qs(urlparse(str(request.url)).query).get("pidx", ["1"])[0])
        self.asked.append((parts[2] if len(parts) > 2 else "", pidx))
        if len(parts) == 2:
            return httpx.Response(self.home_status, text=self.home)
        pages = self.makes.get(parts[2], {})
        if isinstance(pages, int):
            return httpx.Response(pages, text="")
        return httpx.Response(200, text=pages.get(pidx, ac_page(parts[2], range(0), more=False)))


def ac_scraper(site: AutoCosmosSite) -> AutoCosmosScraper:
    s = AutoCosmosScraper()
    s.transport = httpx.MockTransport(site)
    s.PAGE_PAUSE_SECONDS = s.RETRY_PAUSE_SECONDS = 0
    return s


class AutoCosmosInventoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_every_make_page_by_page_not_the_home_list(self):
        site = AutoCosmosSite({
            "ford": {1: ac_page("ford", range(1, 49), more=True), 2: ac_page("ford", range(49, 60), more=False)},
            "peugeot": {1: ac_page("peugeot", range(100, 120), more=False)},
            "zanella": 404,
        })
        found = await ac_scraper(site).search({})
        self.assertTrue(found.complete, found.reason)
        self.assertEqual(len(found), 59 + 20)
        self.assertEqual(site.asked, [("", 1), ("ford", 1), ("ford", 2), ("peugeot", 1), ("zanella", 1)])
        self.assertEqual({c.marca for c in found}, {"Ford", "Peugeot"})

    async def test_a_make_that_fails_makes_the_read_partial_after_the_others(self):
        site = AutoCosmosSite({
            "ford": {1: ac_page("ford", range(1, 49), more=True)},
            "peugeot": {1: ac_page("peugeot", range(100, 120), more=False)},
        })

        def handler(request):
            if request.url.path.endswith("/ford") and "pidx=2" in str(request.url):
                return httpx.Response(503, text="")
            return site(request)

        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(handler)
        s.PAGE_PAUSE_SECONDS = s.RETRY_PAUSE_SECONDS = 0
        found = await s.search({})
        self.assertFalse(found.complete)
        self.assertIn("página 2 de ford", found.reason)
        self.assertEqual(len(found), 48 + 20)          # Peugeot still read

    async def test_the_home_page_must_list_makes(self):
        with self.assertRaises(RuntimeError):
            await ac_scraper(AutoCosmosSite({}, home="<html></html>")).search({})
        with self.assertRaises(CollectorBlocked):
            await ac_scraper(AutoCosmosSite({}, home_status=429)).search({})

    async def test_a_model_search_still_reads_its_own_pages(self):
        site = AutoCosmosSite({"ford": {1: ac_page("ford", range(1, 5), more=False)}})
        found = await ac_scraper(site).search({"marca": "Ford", "modelo": "Fiesta"})
        self.assertNotIn(("", 1), site.asked)


class InventoryTargetTests(unittest.TestCase):
    def test_one_unfiltered_target_each(self):
        self.assertTrue(REGISTRY["v6"].INVENTORY_TARGET and REGISTRY["autocosmos"].INVENTORY_TARGET)
        specs = derive_targets([{"id": 1, "filters": {"make": "Ford", "model": "Fiesta", "year_min": 2015}},
                                {"id": 2, "filters": {"make": "Fiat", "model": "Cronos"}}],
                               ["v6", "autocosmos", "mercadolibre"])
        whole = {s.source: s for s in specs if s.source in ("v6", "autocosmos")}
        self.assertEqual(set(whole), {"v6", "autocosmos"})
        for spec in whole.values():
            self.assertEqual((spec.make, spec.model, spec.query["inventory"], spec.query["profile_ids"]),
                             (None, None, True, [1, 2]))
            self.assertEqual(scraper_filters({"make": None, "model": None, "query": spec.query}), {})
        self.assertEqual(len([s for s in specs if s.source == "mercadolibre"]), 2)


if __name__ == "__main__":
    unittest.main()
