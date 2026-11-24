"""Car One's sold cars: the page answers 200 with Next.js's not-found, or the URL
now shows another vehicle. Fixtures are the real pages of 2026-11-22, trimmed to
their Flight data (carone_detail_sold: a sold Ranger; carone_detail_live: a Logan
on sale, whose URL our listing 64238 had before Car One gave it to 69616)."""
from __future__ import annotations

import json
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from collectors._http import Page
from collectors.carone import CarOneScraper as CarOne
from pipeline import enrich
from pipeline.ingest import IngestResult

FIXTURES = Path(__file__).parent / "fixtures" / "html"
SOLD_URL = "https://carone.com.ar/comprar/usados/ford-ranger-2-2-tdi-4x4-dc-xl-l19-1"
LIVE_URL = "https://carone.com.ar/comprar/usados/renault-logan-ii-1-6-16v-life-1"
# What Car One's GraphQL answered on 2026-11-22 for those two url_keys.
SOLD_LOOKUP = {"data": {"products": {"total_count": 0, "items": []}}}
LIVE_LOOKUP = {"data": {"products": {"total_count": 1, "items": [
    {"id": 69616, "url_key": "renault-logan-ii-1-6-16v-life-1", "stock_status": "IN_STOCK"}]}}}


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def with_lookup(html, slug, response):
    products = response["data"]["products"]
    return CarOne._script(CarOne.LOOKUP_ID, {"url_key": slug, **products}) + html


SOLD = fixture("carone_detail_sold.html")
LIVE = fixture("carone_detail_live.html")
SOLD_SLUG = CarOne._slug(SOLD_URL)


class SoldPageTests(unittest.TestCase):
    def test_sold_page_and_empty_catalog_lookup_is_gone(self):
        detail = CarOne.parse_detail(with_lookup(SOLD, SOLD_SLUG, SOLD_LOOKUP), SOLD_URL)
        self.assertTrue(detail.gone)
        self.assertEqual(detail.gone_reason, "página del auto no encontrada y fuera del catálogo")

    def test_out_of_stock_in_the_lookup_is_gone_too(self):
        lookup = {"data": {"products": {"total_count": 1, "items": [
            {"id": 67837, "url_key": SOLD_SLUG, "stock_status": "OUT_OF_STOCK"}]}}}
        self.assertTrue(CarOne.parse_detail(with_lookup(SOLD, SOLD_SLUG, lookup), SOLD_URL).gone)

    def test_the_page_alone_never_proves_it(self):
        with self.assertRaisesRegex(RuntimeError, "catalog not asked"):
            CarOne.parse_detail(SOLD, SOLD_URL)
        other_slug = {"data": {"products": {"total_count": 0, "items": []}}}
        with self.assertRaisesRegex(RuntimeError, "catalog not asked"):
            CarOne.parse_detail(with_lookup(SOLD, "another-slug", other_slug), SOLD_URL)

    def test_a_catalog_that_still_lists_it_keeps_failing(self):
        lookup = {"data": {"products": {"total_count": 1, "items": [
            {"id": 67837, "url_key": SOLD_SLUG, "stock_status": "IN_STOCK"}]}}}
        with self.assertRaisesRegex(RuntimeError, "still lists it"):
            CarOne.parse_detail(with_lookup(SOLD, SOLD_SLUG, lookup), SOLD_URL)
        incomplete = {"data": {"products": {"total_count": 3, "items": []}}}
        with self.assertRaisesRegex(RuntimeError, "malformed catalog lookup"):
            CarOne.parse_detail(with_lookup(SOLD, SOLD_SLUG, incomplete), SOLD_URL)

    def test_broken_pages_are_not_sold_pages(self):
        broken = {
            # A server error streams another digest, not the not-found fallback.
            "server error": SOLD.replace("NEXT_HTTP_ERROR_FALLBACK;404", "2851764023"),
            # The same not-found on a different route is not this vehicle.
            "another route": SOLD.replace(SOLD_SLUG, "toyota-hilux-l22"),
            "challenge": "<html><title>Just a moment...</title><body>Checking your browser</body></html>",
            "empty": "",
        }
        for name, html in broken.items():
            with self.subTest(page=name):
                self.assertFalse(CarOne._page_not_found(html, SOLD_SLUG))
                with self.assertRaises(RuntimeError):
                    CarOne.parse_detail(with_lookup(html, SOLD_SLUG, SOLD_LOOKUP), SOLD_URL)

    def test_a_live_page_is_never_gone(self):
        self.assertFalse(CarOne._page_not_found(LIVE, CarOne._slug(LIVE_URL)))
        for html in (LIVE, with_lookup(LIVE, CarOne._slug(LIVE_URL), SOLD_LOOKUP)):
            detail = CarOne.parse_detail(html, LIVE_URL)
            self.assertFalse(detail.gone)
            self.assertEqual((detail.listing.listing_id, detail.listing.titulo, detail.listing.precio),
                             ("69616", "RENAULT LOGAN II 1.6 16V LIFE", 22800000.0))

    def test_stored_page_replays_the_same_answer(self):
        page = Page(200, SOLD_URL, with_lookup(SOLD, SOLD_SLUG, SOLD_LOOKUP))
        slim = CarOne().slim_page(page)
        self.assertLess(len(slim), 300)
        self.assertTrue(CarOne.parse_detail(slim, SOLD_URL).gone)
        with self.assertRaises(RuntimeError):     # stored for one URL, read for another
            CarOne.parse_detail(slim, LIVE_URL)
        slim = CarOne().slim_page(Page(200, SOLD_URL, SOLD))
        with self.assertRaisesRegex(RuntimeError, "catalog not asked"):
            CarOne.parse_detail(slim, SOLD_URL)
        live = CarOne().slim_page(Page(200, LIVE_URL, LIVE))
        self.assertEqual(CarOne.parse_detail(live, LIVE_URL).listing.listing_id, "69616")


class FetchTests(unittest.IsolatedAsyncioTestCase):
    def collector(self, page, lookup):
        self.lookups = []

        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, text=page)
            self.assertEqual(request.url.path, "/api/graphql")
            body = json.loads(request.content)
            self.lookups.append(body["variables"])
            self.assertNotIn("stock_status", body["query"].split("items")[0])   # any stock state
            return httpx.Response(200, json=lookup)
        return CarOne(transport=httpx.MockTransport(handler))

    async def test_sold_page_asks_the_catalog_and_ends(self):
        collector = self.collector(SOLD, SOLD_LOOKUP)
        self.assertTrue((await collector.fetch_detail(SOLD_URL)).gone)
        self.assertEqual(self.lookups, [{"key": SOLD_SLUG}])

    async def test_live_page_never_asks(self):
        collector = self.collector(LIVE, SOLD_LOOKUP)
        self.assertEqual((await collector.fetch_detail(LIVE_URL)).listing.listing_id, "69616")
        self.assertEqual(self.lookups, [])

    async def test_catalog_disagreeing_or_failing_keeps_the_error(self):
        listed = {"data": {"products": {"total_count": 1, "items": [
            {"id": 67837, "url_key": SOLD_SLUG, "stock_status": "IN_STOCK"}]}}}
        with self.assertRaisesRegex(RuntimeError, "still lists it"):
            await self.collector(SOLD, listed).fetch_detail(SOLD_URL)
        for answer in ({"errors": [{"message": "upstream"}], **SOLD_LOOKUP}, {"data": None}):
            with self.subTest(answer=answer), self.assertRaises(RuntimeError):
                await self.collector(SOLD, answer).fetch_detail_page(SOLD_URL)


@asynccontextmanager
async def no_db():
    yield None


class ReusedUrlTests(unittest.IsolatedAsyncioTestCase):
    """Our listing 64238 still points at the Logan's URL, which shows 69616 now."""
    ROW = {"id": 1846, "source": "carone", "external_id": "64238", "url": LIVE_URL}

    async def run_ingest(self, *, unseen, seen=True):
        detail = CarOne.parse_detail(LIVE, LIVE_URL)
        with patch.object(enrich.db, "connection", no_db), \
                patch.object(enrich.repo, "unseen_for", AsyncMock(return_value=unseen)) as unseen_for, \
                patch.object(enrich.repo, "mark_gone", AsyncMock(return_value=True)) as gone, \
                patch.object(enrich.repo, "mark_detail_checked", AsyncMock()) as checked, \
                patch.object(enrich, "log_error", AsyncMock()) as errors, \
                patch.object(enrich, "ingest", AsyncMock(return_value=IngestResult(found=1))) as ingest:
            result = await enrich.ingest_detail(dict(self.ROW), detail, stage="watchlist", seen=seen)
        return result, unseen_for, gone, checked, errors, ingest

    async def test_unseen_by_the_crawl_ends_the_stored_listing(self):
        result, unseen_for, gone, checked, errors, ingest = await self.run_ingest(unseen=True)
        unseen_for.assert_awaited_once_with(None, 1846, CarOne.REUSED_URL_GONE_AFTER_HOURS)
        gone.assert_awaited_once_with(None, 1846)
        self.assertEqual([(e.kind, e.listing_id, e.changes) for e in result.events],
                         [("listing_gone", 1846, ("la URL ahora es de otro auto (69616)",))])
        self.assertEqual((errors.await_count, checked.await_count, ingest.await_count), (0, 0, 0))

    async def test_seen_recently_stays_an_error(self):
        result, _, gone, checked, errors, ingest = await self.run_ingest(unseen=False)
        self.assertEqual((gone.await_count, errors.await_count, checked.await_count, ingest.await_count),
                         (0, 1, 1, 0))
        self.assertIn("identity mismatch", errors.await_args.args[2])
        self.assertEqual(result.events, [])

    async def test_a_stored_page_read_again_never_ends_it(self):
        result, unseen_for, gone, _, errors, _ = await self.run_ingest(unseen=True, seen=False)
        self.assertEqual((unseen_for.await_count, gone.await_count, errors.await_count), (0, 0, 1))
        self.assertEqual(result.events, [])

    async def test_the_own_listing_is_still_ingested(self):
        row = {**self.ROW, "external_id": "69616"}
        detail = CarOne.parse_detail(LIVE, LIVE_URL)
        with patch.object(enrich.repo, "unseen_for", AsyncMock()) as unseen_for, \
                patch.object(enrich, "ingest", AsyncMock(return_value=IngestResult(found=1))) as ingest:
            await enrich.ingest_detail(row, detail, stage="enrich")
        self.assertEqual((unseen_for.await_count, ingest.await_count), (0, 1))


if __name__ == "__main__":
    unittest.main()
