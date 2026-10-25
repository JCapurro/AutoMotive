"""Mercado Libre's whole-stock read (comparables fase 2): every id a target's
search lists, and whether it saw them all."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from collectors import mercadolibre as ml
from collectors._http import Page
from collectors.base import CollectorBlocked, Listing

FILTERS = {"marca": "Ford", "modelo": "Ka", "anio_min": 2010, "anio_max": 2012, "km_max": 150_000}


class FakeSite:
    """Search pages by URL: each one a list of ids and the page count its
    first page shows. A URL missing from the map is a test bug; an exception
    in it is raised."""

    def __init__(self, pages: dict[str, object]):
        self.pages = pages
        self.asked: list[str] = []

    async def get(self, url, what, *, allow_404=False):
        self.asked.append(url)
        page = self.pages[url]
        if isinstance(page, BaseException):
            raise page
        return Page(200, url, url)

    def results(self, html):
        return [Listing("mercadolibre", i, f"Ford Ka {i}", f"https://auto.mercadolibre.com.ar/{i}")
                for i in self.pages[html][0]]

    def state(self, html):
        return ml.SearchState(frozenset(), None, self.pages[html][1])

    async def read(self, filters=FILTERS) -> ml.FullRead:
        with patch.object(ml, "_get", self.get), patch.object(ml, "_results", self.results), \
                patch.object(ml, "search_state", self.state), patch.object(ml, "_page_pause", AsyncMock()), \
                patch.object(ml, "PAGE_SIZE", 3):
            return await ml.MercadoLibreScraper().full_read(filters)


def url(filters=FILTERS, page=1, **years):
    with patch.object(ml, "PAGE_SIZE", 3):
        return ml._build_url({**filters, **years}, page)


class FullReadTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_every_page_of_the_search(self):
        site = FakeSite({url(): (["a", "b", "c"], 2), url(page=2): (["d"], 2)})
        read = await site.read()
        self.assertEqual((read.ids, read.complete, read.pages), ({"a", "b", "c", "d"}, True, 2))
        self.assertEqual(site.asked, [url(), url(page=2)])

    async def test_one_page_and_no_results_are_complete(self):
        for pages, ids in (({url(): (["a"], 0)}, {"a"}), ({url(): ([], None)}, set())):
            with self.subTest(ids=ids):
                read = await FakeSite(pages).read()
                self.assertEqual((read.ids, read.complete), (ids, True))

    async def test_more_results_than_pages_reads_a_year_at_a_time(self):
        site = FakeSite({url(): (["a", "b", "c"], ml.MAX_PAGE_COUNT),
                         url(anio_min=2010, anio_max=2010): (["a", "e"], 1),
                         url(anio_min=2011, anio_max=2011): (["b", "c", "f"], 2),
                         url(anio_min=2011, anio_max=2011, page=2): (["g"], 2),
                         url(anio_min=2012, anio_max=2012): ([], None)})
        read = await site.read()
        self.assertEqual(read.ids, {"a", "b", "c", "e", "f", "g"})
        self.assertTrue(read.complete)
        self.assertEqual(len(site.asked), 5)

    async def test_without_a_year_min_the_old_years_go_in_one_search(self):
        buckets = ml._year_buckets({"marca": "Ford", "anio_max": 2020})
        self.assertEqual(buckets[0], {"marca": "Ford", "anio_min": 1900, "anio_max": 2020 - ml.OPEN_YEARS})
        self.assertEqual([b["anio_min"] for b in buckets[1:]], list(range(2021 - ml.OPEN_YEARS, 2021)))
        self.assertTrue(all(b["anio_min"] == b["anio_max"] for b in buckets[1:]))

    async def test_a_year_still_too_big_is_incomplete(self):
        site = FakeSite({url(): (["a", "b", "c"], ml.MAX_PAGE_COUNT),
                         url(anio_min=2010, anio_max=2010): (["a", "d", "e"], ml.MAX_PAGE_COUNT)})
        read = await site.read()
        self.assertFalse(read.complete)
        self.assertIn("2010-2010", read.reason)
        self.assertEqual(read.ids, {"a", "b", "c", "d", "e"})                # what it saw still counts

    async def test_a_short_page_before_the_last_is_incomplete(self):
        site = FakeSite({url(): (["a", "b", "c"], 3), url(page=2): (["d"], 3)})
        read = await site.read()
        self.assertEqual((read.ids, read.complete), ({"a", "b", "c", "d"}, False))

    async def test_a_repeated_page_is_incomplete(self):
        site = FakeSite({url(): (["a", "b", "c"], 2), url(page=2): (["a", "b", "c"], 2)})
        read = await site.read()
        self.assertFalse(read.complete)
        self.assertIn("repeated", read.reason)

    async def test_a_full_first_page_without_a_page_count_is_incomplete(self):
        site = FakeSite({url(): (["a", "b", "c"], None)})
        read = await site.read()
        self.assertEqual((read.ids, read.complete), ({"a", "b", "c"}, False))

    async def test_a_failure_keeps_what_it_saw(self):
        site = FakeSite({url(): (["a", "b", "c"], 2), url(page=2): RuntimeError("HTTP 500")})
        read = await site.read()
        self.assertEqual((read.ids, read.complete), ({"a", "b", "c"}, False))
        self.assertIn("HTTP 500", read.reason)

    async def test_a_wall_raises(self):
        site = FakeSite({url(): (["a", "b", "c"], 2), url(page=2): CollectorBlocked("login required")})
        with self.assertRaises(CollectorBlocked):
            await site.read()

    async def test_reads_only_what_the_target_covers(self):
        site = FakeSite({url({"marca": "Ford", "modelo": "Ka"}): (["a"], 1)})
        await site.read({"marca": "Ford", "modelo": "Ka", "version": "SE", "publication_since": 1, "count_only": True})
        self.assertEqual(site.asked, ["https://autos.mercadolibre.com.ar/ford/ka/_NoIndex_True"])


if __name__ == "__main__":
    unittest.main()
