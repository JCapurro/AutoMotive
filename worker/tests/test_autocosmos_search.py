"""AutoCosmos search: every page of the model, `?pidx=N`, retried on 503 (no network)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx

from collectors.autocosmos import AutoCosmosScraper
from collectors.base import CollectorBlocked
from pipeline import breaker, crawl

FILTERS = {"marca": "Ford", "modelo": "Fiesta"}


def card(n: int) -> str:
    return (f'<article class="listing-card">'
            f'<a itemprop="url" href="/auto/usado/ford/fiesta/s/{n:032x}"></a>'
            f'<span class="listing-card__brand">Ford</span>'
            f'<span class="listing-card__model">Fiesta</span>'
            f'<span class="listing-card__year">2017</span></article>')


def page(ids: range, *, more: bool) -> str:
    head = '<link rel="next" href="/auto/usado/ford/fiesta?pidx=9" />' if more else ""
    return f"<html><head>{head}</head><body>{''.join(card(n) for n in ids)}</body></html>"


class Site:
    """Serves `pages[pidx]`; `fail[pidx]` is a list of statuses (or exceptions) to give first."""

    def __init__(self, pages: dict[int, str], fail: dict[int, list] | None = None) -> None:
        self.pages, self.fail, self.asked = pages, fail or {}, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        pidx = int(parse_qs(urlparse(str(request.url)).query).get("pidx", ["1"])[0])
        self.asked.append(pidx)
        if self.fail.get(pidx):
            outcome = self.fail[pidx].pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return httpx.Response(outcome, text="")
        return httpx.Response(200, text=self.pages.get(pidx, page(range(0), more=False)))


def scraper(site: Site) -> AutoCosmosScraper:
    s = AutoCosmosScraper()
    s.transport = httpx.MockTransport(site)
    s.PAGE_PAUSE_SECONDS = s.RETRY_PAUSE_SECONDS = 0
    return s


class AutoCosmosSearchTests(unittest.IsolatedAsyncioTestCase):
    def test_pages_go_by_pidx(self):
        s = AutoCosmosScraper()
        self.assertEqual(s._build_url(FILTERS), "https://www.autocosmos.com.ar/auto/usado/ford/fiesta")
        self.assertEqual(parse_qs(urlparse(s._build_url(FILTERS, page=3)).query), {"pidx": ["3"]})

    async def test_walks_every_page_while_there_is_a_next_one(self):
        site = Site({1: page(range(1, 49), more=True), 2: page(range(49, 97), more=True),
                     3: page(range(97, 99), more=False)})

        found = await scraper(site).search(FILTERS)

        self.assertEqual(len(found), 98)
        self.assertEqual(site.asked, [1, 2, 3])

    async def test_a_page_repeating_the_last_one_ends_the_walk(self):
        same = page(range(1, 49), more=True)
        site = Site({1: same, 2: same})

        found = await scraper(site).search(FILTERS)

        self.assertEqual((len(found), site.asked), (48, [1, 2]))

    async def test_503_and_timeouts_are_retried(self):
        site = Site({1: page(range(1, 3), more=True), 2: page(range(3, 5), more=False)},
                    fail={1: [503, httpx.ReadTimeout("slow")], 2: [502]})

        found = await scraper(site).search(FILTERS)

        self.assertEqual(len(found), 4)
        self.assertEqual(site.asked, [1, 1, 1, 2, 2])

    async def test_first_page_down_fails_the_run(self):
        site = Site({}, fail={1: [503, 503, 503]})

        with self.assertRaises(httpx.HTTPStatusError):
            await scraper(site).search(FILTERS)

    async def test_503_respects_the_site_retry_after_before_retrying(self):
        responses = [httpx.Response(503, headers={"Retry-After": "30"}),
                     httpx.Response(200, text=page(range(1, 3), more=False))]
        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(lambda request: responses.pop(0))
        with patch("collectors.autocosmos.asyncio.sleep", new_callable=AsyncMock) as sleep:
            found = await s.search(FILTERS)
        self.assertEqual(len(found), 2)
        sleep.assert_awaited_once_with(30)

    async def test_retry_after_http_date_uses_utc(self):
        responses = [httpx.Response(503, headers={"Retry-After": "Fri, 09 Oct 2026 13:00:45 GMT"}),
                     httpx.Response(200, text=page(range(1, 3), more=False))]
        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(lambda request: responses.pop(0))
        with patch("collectors.autocosmos.datetime") as clock, \
                patch("collectors.autocosmos.asyncio.sleep", new_callable=AsyncMock) as sleep:
            clock.now.return_value = datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc)
            found = await s.search(FILTERS)
        self.assertEqual(len(found), 2)
        sleep.assert_awaited_once_with(45)

    async def test_invalid_retry_after_keeps_existing_backoff(self):
        responses = [httpx.Response(503, headers={"Retry-After": "not-a-date"}),
                     httpx.Response(200, text=page(range(1, 3), more=False))]
        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(lambda request: responses.pop(0))
        with patch("collectors.autocosmos.asyncio.sleep", new_callable=AsyncMock) as sleep:
            found = await s.search(FILTERS)
        self.assertEqual(len(found), 2)
        sleep.assert_awaited_once_with(10)

    async def test_long_retry_after_stops_without_retrying_too_early(self):
        responses = [httpx.Response(503, headers={"Retry-After": "3600"})]
        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(lambda request: responses.pop(0))
        with patch("collectors.autocosmos.asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(httpx.HTTPStatusError):
                await s.search(FILTERS)
        sleep.assert_not_awaited()

    async def test_a_later_page_down_keeps_what_was_read_as_a_partial_read(self):
        site = Site({1: page(range(1, 3), more=True)},
                    fail={2: [httpx.ConnectError("down")] * 3})

        found = await scraper(site).search(FILTERS)

        self.assertEqual(len(found), 2)
        self.assertEqual((found.complete, found.reason), (False, "autocosmos: página 2 falló (ConnectError)"))

    async def test_a_later_page_answering_anything_but_200_makes_the_read_partial(self):
        for status in (403, 429, 404, 503):
            site = Site({1: page(range(1, 3), more=True)}, fail={2: [status] * 3})

            found = await scraper(site).search(FILTERS)

            self.assertEqual((len(found), found.complete), (2, False), status)
            self.assertEqual(found.reason, f"autocosmos: página 2 respondió {status}")

    async def test_the_end_of_the_list_is_a_complete_read(self):
        same = page(range(1, 49), more=True)
        for pages in ({1: page(range(1, 3), more=False)}, {1: same, 2: same}):
            found = await scraper(Site(pages)).search(FILTERS)
            self.assertTrue(found.complete)

    async def test_a_first_page_turned_away_blocks_the_source_and_a_404_is_no_stock(self):
        # A 401, 403 or 429 is the site turning us away, not "0 results".
        for status in (401, 403, 429):
            with self.assertRaises(CollectorBlocked):
                await scraper(Site({}, fail={1: [status]})).search(FILTERS)
        # Any other answer but 200 fails the run.
        with self.assertRaises(httpx.HTTPStatusError):
            await scraper(Site({}, fail={1: [400]})).search(FILTERS)
        for status in (404, 410):
            found = await scraper(Site({}, fail={1: [status]})).search(FILTERS)
            self.assertEqual((list(found), found.complete), ([], True))

    async def test_the_page_cap_ends_a_read_taken_as_complete_and_says_so(self):
        s = scraper(Site({1: page(range(1, 3), more=True), 2: page(range(3, 5), more=True)}))
        s.MAX_PAGES = 2

        with self.assertLogs("collectors.autocosmos", "WARNING") as logs:
            found = await s.search(FILTERS)

        self.assertEqual((len(found), found.complete), (4, True))
        self.assertIn("stops at 2 pages", logs.output[0])


class BlockedCrawlTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_429_on_the_first_page_pauses_autocosmos_before_its_next_target(self):
        breaker.clear()
        self.addCleanup(breaker.clear)
        site = Site({}, fail={1: [429]})
        due = [{"id": i, "source": "autocosmos", "make": "Ford", "model": "Fiesta", "query": {},
                "first_run_done": True, "crawl_interval_seconds": 1800} for i in (1, 2)]

        async def claim_next(source, worker, lease_seconds):
            return due.pop(0) if due else None

        async def on_collector(coroutine, timeout=None):
            return await coroutine

        with patch.dict(crawl.REGISTRY, {"autocosmos": lambda: scraper(site)}), \
                patch.object(crawl.targets_repo, "claim_next", claim_next), \
                patch.object(crawl.runs, "start_run", AsyncMock(return_value=1)), \
                patch.object(crawl.runs, "finish_run", AsyncMock(return_value=None)) as finish_run, \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish_target, \
                patch.object(crawl, "run_collector", on_collector):
            self.assertEqual(await crawl._drain("autocosmos", None, 0, None), 1)

        self.assertTrue(breaker.paused("autocosmos"))
        self.assertEqual([t["id"] for t in due], [2])        # never claimed
        self.assertFalse(finish_run.await_args.kwargs["ok"])
        finish_target.assert_awaited_once_with(1, ok=False, retry_seconds=ANY)
        self.assertEqual(site.asked, [1])


if __name__ == "__main__":
    unittest.main()
