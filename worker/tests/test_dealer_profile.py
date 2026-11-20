"""Agencias: a seller's whole Mercado Libre profile (collectors/mercadolibre.py
seller_profile, migration 20270105120000) — the link, the pages and the name."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from collectors import mercadolibre as ml
from collectors._http import Page
from collectors.base import CollectorBlocked, Listing

CUST = "145347970"


class FakeProfile:
    """Profile pages by URL: (ids, page count shown on the first page). The
    page's html is its URL, so the patched parsers know which page it is."""

    def __init__(self, pages: dict[str, object], name: str | None = "BUSTELO AUTOMOTORES"):
        self.pages, self.name, self.asked = pages, name, []

    async def get(self, url, what, *, allow_404=False):
        self.asked.append(url)
        page = self.pages[url]
        if isinstance(page, BaseException):
            raise page
        return Page(200, url, url)

    def results(self, html):
        return [Listing("mercadolibre", i, f"Peugeot 308 {i}", f"https://auto.mercadolibre.com.ar/{i}")
                for i in self.pages[html][0]]

    def state(self, html):
        return ml.SearchState(frozenset(), None, self.pages[html][1])

    async def read(self, max_pages: int = 12) -> ml.SellerProfile:
        with patch.object(ml, "_get", self.get), patch.object(ml, "_results", self.results), \
                patch.object(ml, "search_state", self.state), patch.object(ml, "_page_pause", AsyncMock()), \
                patch.object(ml, "_profile_name", lambda html: self.name), patch.object(ml, "PAGE_SIZE", 3), \
                patch.object(ml, "PROFILE_MAX_PAGES", max_pages):
            return await ml.MercadoLibreScraper().seller_profile(CUST)


def url(page: int = 1) -> str:
    with patch.object(ml, "PAGE_SIZE", 3):
        return ml.profile_url(CUST, page)


class LinkTests(unittest.TestCase):
    def test_the_seller_id_of_a_profile_link(self):
        self.assertEqual(ml.seller_cust_id("https://vehiculos.mercadolibre.com.ar/_CustId_145347970"), "145347970")
        self.assertEqual(ml.seller_cust_id(" https://autos.mercadolibre.com.ar/_Desde_49_CustId_56604376_NoIndex_True "), "56604376")
        self.assertEqual(ml.seller_cust_id("https://listado.mercadolibre.com.ar/autos/_CustId_145347970?x=1"), "145347970")

    def test_anything_else_is_not_a_profile(self):
        for bad in (None, "", "https://evil.test/_CustId_145347970", "http://vehiculos.mercadolibre.com.ar/_CustId_145347970",
                    "https://mercadolibre.com.ar.evil.test/_CustId_145347970", "https://www.mercadolibre.com.ar/perfil/BUSTELO",
                    "https://vehiculos.mercadolibre.com.ar/_CustId_12", "https://vehiculos.mercadolibre.com.ar/_CustId_1234567890123456",
                    "https://vehiculos.mercadolibre.com.ar/?q=_CustId_145347970"):
            with self.subTest(bad=bad):
                self.assertIsNone(ml.seller_cust_id(bad))

    def test_the_offset_goes_first_as_in_mercado_libres_own_pagination(self):
        self.assertEqual(ml.profile_url("145347970"), "https://vehiculos.mercadolibre.com.ar/_CustId_145347970")
        self.assertEqual(ml.profile_url("145347970", 2), "https://vehiculos.mercadolibre.com.ar/_Desde_49_CustId_145347970")
        self.assertEqual(ml.profile_url("145347970", 3), "https://vehiculos.mercadolibre.com.ar/_Desde_97_CustId_145347970")

    def test_the_sellers_name_is_the_pages_title(self):
        self.assertEqual(ml._profile_name("<h1>Publicaciones de BUSTELO AUTOMOTORES</h1><h2>Filtros</h2>"), "BUSTELO AUTOMOTORES")
        self.assertEqual(ml._profile_name("<h2>Filtros</h2><h1> publicaciones de  Gralpaz 13124 </h1>"), "Gralpaz 13124")
        self.assertIsNone(ml._profile_name("<h1>Autos usados</h1>"))


class ProfileReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_page_and_every_car_carries_the_sellers_name(self):
        site = FakeProfile({url(): (["a", "b", "c"], 3), url(2): (["d", "e", "f"], 3), url(3): (["g"], 3)})
        read = await site.read()
        self.assertEqual([c.listing_id for c in read.cards], list("abcdefg"))
        self.assertEqual((read.name, read.complete, read.pages), ("BUSTELO AUTOMOTORES", True, 3))
        self.assertEqual({c.vendedor_nombre for c in read.cards}, {"BUSTELO AUTOMOTORES"})
        self.assertEqual(site.asked, [url(), url(2), url(3)])

    async def test_one_short_page_is_the_whole_profile(self):
        read = await FakeProfile({url(): (["a", "b"], 0)}).read()
        self.assertEqual(([c.listing_id for c in read.cards], read.complete, read.pages), (["a", "b"], True, 1))

    async def test_a_full_last_page_stops_at_the_page_count(self):
        site = FakeProfile({url(): (["a", "b", "c"], 2), url(2): (["d", "e", "f"], 2)})
        read = await site.read()
        self.assertEqual((len(read.cards), read.complete), (6, True))
        self.assertEqual(site.asked, [url(), url(2)])

    async def test_an_empty_profile_is_complete_and_empty(self):
        read = await FakeProfile({url(): ([], None)}).read()
        self.assertEqual((read.cards, read.complete), ([], True))

    async def test_a_repeated_page_or_too_many_pages_is_incomplete(self):
        repeated = await FakeProfile({url(): (["a", "b", "c"], 3), url(2): (["a", "b", "c"], 3)}).read()
        self.assertEqual((len(repeated.cards), repeated.complete), (3, False))
        long = await FakeProfile({url(): (["a", "b", "c"], 9), url(2): (["d", "e", "f"], 9)}).read(max_pages=2)
        self.assertEqual((len(long.cards), long.complete), (6, False))
        self.assertIn("more than 2 pages", long.reason)

    async def test_a_wall_fails_the_read_and_a_bad_id_never_asks(self):
        with self.assertRaises(CollectorBlocked):
            await FakeProfile({url(): CollectorBlocked("mercadolibre seller profile: login wall")}).read()
        site = FakeProfile({})
        with patch.object(ml, "_get", site.get), self.assertRaises(ValueError):
            await ml.MercadoLibreScraper().seller_profile("../x")
        self.assertEqual(site.asked, [])
