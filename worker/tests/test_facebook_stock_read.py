"""Facebook's stock read (stock_read): the whole feed of a model, any age,
dated only by the feed. No network, no browser: the fakes of test_recent_crawls."""
from __future__ import annotations

from contextlib import asynccontextmanager
import os
import pickle
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from collectors import facebook as fb
from collectors.base import SearchResults
from collectors._recency import DAY
from test_recent_crawls import FIXTURES, NOW, RESTRICTED_HTML, FacebookPage

FILTERS = {"marca": "Ford", "modelo": "Fiesta", "anio_min": 2012, "anio_max": 2016, "km_max": 150_000,
           "origin_lat": -31.42, "origin_lon": -64.18}                # Córdoba


class FacebookStockReadTests(unittest.IsolatedAsyncioTestCase):
    HTML = (FIXTURES / "facebook_search_feed.html").read_text(encoding="utf-8")        # 1001, 1002 dated; 1003 not

    async def read(self, *pages, cookies=({"name": "c_user"},), **filters):
        """stock_read over `pages` (one per browser context opened); never an item page."""
        pages = list(pages)
        self.opened = []

        @asynccontextmanager
        async def context(**kwargs):
            self.opened.append(kwargs.get("storage_state"))
            yield MagicMock(new_page=AsyncMock(return_value=pages.pop(0)),
                            cookies=AsyncMock(return_value=list(cookies) if kwargs.get("storage_state") else []))

        no_item_page = AsyncMock(side_effect=AssertionError("a stock read opened an item page"))
        with patch.object(fb, "browser_context", context), \
                patch.object(fb.Path, "exists", return_value=True), \
                patch.object(fb.FacebookMarketplaceScraper, "_publication_date", no_item_page), \
                patch("collectors._recency.time.time", return_value=NOW):
            return await fb.FacebookMarketplaceScraper().stock_read({**FILTERS, **filters})

    async def test_the_url_has_the_target_s_years_and_km_and_no_publication_window(self):
        page = FacebookPage([[("1", 2)]])
        # A window slipped into the filters is still left out.
        await self.read(page, publication_days=30, publication_until=NOW, count_only=True)
        url = urlparse(page.url)
        params = parse_qs(url.query)
        self.assertEqual(url.path, "/marketplace/cordoba/search/")
        self.assertNotIn("daysSinceListed", params)
        self.assertEqual({k: params[k] for k in ("sortBy", "query", "minYear", "maxYear", "maxMileage")},
                         {"sortBy": ["creation_time_descend"], "query": ["Ford Fiesta"], "minYear": ["2012"],
                          "maxYear": ["2016"], "maxMileage": ["150000"]})

    async def test_old_feed_dated_and_undated_cards_are_all_kept(self):
        # 1001/1002 dated by the page's data, 1003 not (no item page opened),
        # 9 a card «Hace 400 días»: older than any publication window.
        page = FacebookPage([[("1001", None), ("1002", None)], [("1003", None), ("9", 400)]], html=self.HTML)
        with self.assertLogs("collectors.facebook", "INFO") as logs:
            results = await self.read(page)
        dates = {l.listing_id: l.published_at for l in results}
        self.assertEqual(set(dates), {"1001", "1002", "1003", "9"})
        self.assertEqual((dates["1001"], dates["1002"], dates["1003"]), (1_699_900_000, 1_699_800_000, None))
        self.assertAlmostEqual(dates["9"], NOW - 400 * DAY, delta=DAY)
        self.assertEqual((results.complete, results.reason, results.unknown_dates), (True, None, 1))
        self.assertEqual(results.date_skips, None)                                # no date memory
        self.assertEqual(results.probe["dated"], {"feed": 2, "card": 1, "none": 1})
        self.assertIn("facebook stock read: scrolls=", logs.output[-1])
        self.assertIn("feed_dates=2 unknown_dates=1 complete=True", logs.output[-1])
        page.close.assert_awaited_once()

    async def test_without_feed_dates_every_undated_card_is_kept_undated(self):
        page = FacebookPage([[("1001", None), ("1003", None)]], html=self.HTML)
        with patch.object(fb.config, "FB_FEED_DATES", False):
            results = await self.read(page)
        self.assertEqual([(l.listing_id, l.published_at) for l in results], [("1001", None), ("1003", None)])
        self.assertEqual(results.unknown_dates, 2)

    async def test_the_card_hygiene_of_a_scan_holds(self):
        # A year outside the target's (matches_filters) and another model's
        # card (_matches_query_text) are left out; a sold card is kept for ingest.
        page = FacebookPage([[("1", 2), ("2", 2)]])
        rows = [["/marketplace/item/1", "$10.000\nFord Fiesta 2010", "", None],
                ["/marketplace/item/2", "$10.000\nFord Ka 2014", "", None],
                ["/marketplace/item/3", "$10.000\nSold · Ford Fiesta 2014", "", None],
                ["/marketplace/item/4", "$10.000\nFord Fiesta 2014", "", None]]
        page.locator = lambda selector: (MagicMock(inner_text=AsyncMock(return_value="Marketplace"))
                                         if selector == "body" else
                                         MagicMock(evaluate_all=AsyncMock(return_value=rows)))
        results = await self.read(page)
        self.assertEqual([(l.listing_id, l.extra.get("card_status")) for l in results], [("3", "sold"), ("4", None)])

    async def test_it_scrolls_until_the_feed_stops_growing(self):
        page = FacebookPage([[(str(i), 2)] for i in range(1, 8)])
        results = await self.read(page)
        self.assertEqual([l.listing_id for l in results], [str(i) for i in range(1, 8)])
        self.assertTrue(results.complete)
        # Six scrolls that brought a card, then three that didn't: the third read without one ends it.
        self.assertEqual(page.mouse.wheel.await_count, 6 + 3)

    async def test_the_scroll_cap_ends_the_read_partial_keeping_what_it_read(self):
        page = FacebookPage([[("1", 2)], [("2", 2)], [("3", 2)]])
        with patch.dict(os.environ, {"STOCK_FB_MAX_SCROLLS": "1"}):
            results = await self.read(page)
        self.assertEqual([l.listing_id for l in results], ["1", "2"])
        self.assertEqual((results.complete, results.reason), (False, fb.STOCK_SCROLL_LIMIT))

    def test_the_scroll_cap_defaults_to_the_publication_scan_s(self):
        with patch.dict(os.environ, {"STOCK_FB_MAX_SCROLLS": ""}):
            self.assertEqual(fb.stock_max_scrolls(), fb.config.RECENT_FB_MAX_SCROLLS)
        with patch.dict(os.environ, {"STOCK_FB_MAX_SCROLLS": "many"}):
            self.assertEqual(fb.stock_max_scrolls(), fb.config.RECENT_FB_MAX_SCROLLS)
        with patch.dict(os.environ, {"STOCK_FB_MAX_SCROLLS": "500"}):
            self.assertEqual(fb.stock_max_scrolls(), 500)

    async def test_a_login_wall_raises_as_a_scan_does(self):
        page = FacebookPage([[]], expire_after=1)
        with self.assertRaisesRegex(fb.CollectorBlocked, "session expired"):
            await self.read(page)
        page.close.assert_awaited_once()

    async def test_a_logged_out_page_raises_as_a_scan_does(self):
        with self.assertRaisesRegex(fb.CollectorBlocked, "logged out"):
            await self.read(FacebookPage([[("1", None)]]), cookies=({"name": "datr"},))

    async def test_no_stored_session_raises_before_opening_a_browser(self):
        with patch.object(fb.Path, "exists", return_value=False), \
                self.assertRaisesRegex(fb.CollectorBlocked, "no session"):
            await fb.FacebookMarketplaceScraper().stock_read(dict(FILTERS))

    async def test_a_wall_after_some_cards_keeps_them_partial_as_a_scan_does(self):
        results = await self.read(FacebookPage([[("1", 0)]], expire_after=1))
        self.assertEqual([l.listing_id for l in results], ["1"])
        self.assertFalse(results.complete)
        self.assertIn("session expired", results.reason)

    async def test_an_unconfirmed_empty_feed_raises_as_a_scan_does(self):
        page = FacebookPage([[]])
        with patch.object(fb.config, "FB_NO_SESSION_FALLBACK", False), \
                self.assertRaisesRegex(fb.FeedUnconfirmed, "empty feed without") as caught:
            await self.read(page)
        self.assertNotIsInstance(caught.exception, fb.CollectorBlocked)
        self.assertEqual(page.reloads, 1)

    async def test_a_confirmed_empty_feed_is_a_complete_empty_read(self):
        results = await self.read(FacebookPage([[]], body="Marketplace\nNo listings found for \"Ford Fiesta\""))
        self.assertEqual((list(results), results.complete), ([], True))

    async def test_a_restricted_search_is_read_again_without_the_session(self):
        restricted = FacebookPage([[]], html=RESTRICTED_HTML)
        public = FacebookPage([[("1", 2), ("2", 40)]])
        with patch.object(fb, "_keep_session", AsyncMock(return_value=False)):
            results = await self.read(restricted, public)
        self.assertEqual([l.listing_id for l in results], ["1", "2"])
        self.assertEqual(self.opened, [fb.FB_STORAGE_STATE, None])
        self.assertEqual(results.probe["no_session"], 1)
        self.assertNotIn("daysSinceListed", public.url)

    async def test_without_the_fallback_a_restricted_search_raises_search_restricted(self):
        with patch.object(fb.config, "FB_NO_SESSION_FALLBACK", False), \
                self.assertRaises(fb.SearchRestricted):
            await self.read(FacebookPage([[]], html=RESTRICTED_HTML))

    async def test_the_result_survives_the_isolated_child_s_pickle(self):
        # collectors/_isolated.py returns the child's result pickled.
        results = await self.read(FacebookPage([[("1001", None), ("1003", None)]], html=self.HTML))
        with patch.dict(os.environ, {"STOCK_FB_MAX_SCROLLS": "1"}):
            partial = await self.read(FacebookPage([[("1", 2)], [("2", 2)], [("3", 2)]]))
        for original in (results, partial):
            copy = pickle.loads(pickle.dumps((True, original)))[1]
            self.assertIsInstance(copy, SearchResults)
            self.assertEqual([(l.listing_id, l.published_at) for l in copy],
                             [(l.listing_id, l.published_at) for l in original])
            self.assertEqual((copy.complete, copy.reason, copy.unknown_dates, copy.probe),
                             (original.complete, original.reason, original.unknown_dates, original.probe))
        # And so does its argument: the filters, as pipeline/crawl.py passes them.
        self.assertEqual(pickle.loads(pickle.dumps(("collectors.facebook", "FacebookMarketplaceScraper",
                                                    "stock_read", (FILTERS,))))[3], (FILTERS,))


if __name__ == "__main__":
    unittest.main()
