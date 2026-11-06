"""AutoCosmos search: every page of the model, `?pidx=N`, retried on 503 (no network)."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx

from collectors._http import Page
from collectors import autocosmos
from collectors.autocosmos import AutoCosmosScraper
from collectors.base import CollectorBlocked
from pipeline import breaker, crawl, enrich

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


def is_model_list(request: httpx.Request) -> bool:
    """/auto/usado/<make>: the make's model pages, read before the model."""
    return len(request.url.path.strip("/").split("/")) == 3


def models_first(handler):
    """`handler` for the model's pages; an empty model list for the make."""
    return lambda request: (httpx.Response(200, text="") if is_model_list(request)
                            else handler(request))


class Site:
    """Serves `pages[pidx]`; `fail[pidx]` is a list of statuses (or exceptions) to give first."""

    def __init__(self, pages: dict[int, str], fail: dict[int, list] | None = None,
                 model_list: str = "") -> None:
        self.pages, self.fail, self.asked = pages, fail or {}, []
        self.model_list = model_list

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if is_model_list(request):
            return httpx.Response(200, text=self.model_list)
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
        s.transport = httpx.MockTransport(models_first(lambda request: responses.pop(0)))
        with patch("collectors.autocosmos.asyncio.sleep", new_callable=AsyncMock) as sleep:
            found = await s.search(FILTERS)
        self.assertEqual(len(found), 2)
        sleep.assert_awaited_once_with(30)

    async def test_retry_after_http_date_uses_utc(self):
        responses = [httpx.Response(503, headers={"Retry-After": "Fri, 09 Oct 2026 13:00:45 GMT"}),
                     httpx.Response(200, text=page(range(1, 3), more=False))]
        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(models_first(lambda request: responses.pop(0)))
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
        s.transport = httpx.MockTransport(models_first(lambda request: responses.pop(0)))
        with patch("collectors.autocosmos.asyncio.sleep", new_callable=AsyncMock) as sleep:
            found = await s.search(FILTERS)
        self.assertEqual(len(found), 2)
        sleep.assert_awaited_once_with(10)

    async def test_long_retry_after_stops_without_retrying_too_early(self):
        responses = [httpx.Response(503, headers={"Retry-After": "3600"})]
        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(models_first(lambda request: responses.pop(0)))
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
        # Any other answer but 200 fails the run, another 2xx too.
        for status in (400, 202, 204):
            with self.assertRaises(httpx.HTTPStatusError):
                await scraper(Site({}, fail={1: [status]})).search(FILTERS)
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


CITROEN_MODELS = "".join(f'<a href="/auto/usado/citroen/{m}">x</a>' for m in (
    "c3", "c4", "c4-aircross", "c4-cactus", "c4-grand-picasso", "c4-hatchback", "c4-lounge",
    "c4-mhev", "c4-picasso", "c4-spacetourer"))


class ModelPagesTests(unittest.IsolatedAsyncioTestCase):
    """The site's make and model pages aren't always our slug (06/11/2026)."""

    def setUp(self):
        autocosmos._model_pages.clear()
        self.addCleanup(autocosmos._model_pages.clear)

    def test_makes_lose_every_accent_and_take_the_site_slug(self):
        s = AutoCosmosScraper()
        self.assertEqual(s._build_url({"marca": "Citroën", "modelo": "C4"}),
                         "https://www.autocosmos.com.ar/auto/usado/citroen/c4")
        self.assertEqual(s._build_url({"marca": "Mercedes-Benz", "modelo": "Clase C"}),
                         "https://www.autocosmos.com.ar/auto/usado/mercedes/clase-c")

    def test_a_model_takes_its_body_and_version_pages_and_no_other_model(self):
        def slugs(model, *pages, make="x"):
            return autocosmos.model_slugs(make, model, frozenset(pages))

        self.assertEqual(slugs("C4", "c4", "c4-cactus", "c4-hatchback", "c4-lounge", "c4-mhev"),
                         ["c4", "c4-hatchback", "c4-mhev"])
        self.assertEqual(slugs("Polo", "polo", "polo-5p"), ["polo", "polo-5p"])
        self.assertEqual(slugs("S10", "s-10", "spin"), ["s-10"])
        self.assertEqual(slugs("Serie 3", "serie-1", "serie-3-coupe", "serie-3-sedan"),
                         ["serie-3-coupe", "serie-3-sedan"])
        self.assertEqual(slugs("Clase C", "clase-c-sedan", "clase-c-sedan-amg", "clase-clk-coupe"),
                         ["clase-c-sedan", "clase-c-sedan-amg"])
        self.assertEqual(slugs("Gol", "gol", "gol-country", "gol-trend"), ["gol"])
        self.assertEqual(slugs("Corolla", "corolla", "corolla-cross", "corolla-cross-hybrid", "corolla-hybrid"),
                         ["corolla", "corolla-hybrid"])
        self.assertEqual(slugs("Bronco", "bronco", "bronco-sport"), ["bronco"])
        self.assertEqual(slugs("Megane", "megane", "megane-ii", "megane-iii", "megane-iii-rs"),
                         ["megane", "megane-ii", "megane-iii", "megane-iii-rs"])
        self.assertEqual(slugs("Corsa", "corsa", "corsa-classic", "corsa-wagon"),
                         ["corsa", "corsa-classic", "corsa-wagon"])
        self.assertEqual(slugs("Fox", "fox", "crossfox", make="volkswagen"), ["fox", "crossfox"])
        self.assertEqual(slugs("Stepway", "sandero", "sandero-stepway", "stepway", make="renault"),
                         ["stepway", "sandero-stepway"])
        # No list, or nothing in it for the model: its own slug, as before.
        self.assertEqual(slugs("Fiesta"), ["fiesta"])
        self.assertEqual(slugs("Serie 4", "serie-1", "x5"), ["serie-4"])

    async def test_search_reads_every_page_of_the_model_once(self):
        asked = []

        def site(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.path)
            if request.url.path == "/auto/usado/citroen":
                return httpx.Response(200, text=CITROEN_MODELS)
            n = {"/auto/usado/citroen/c4": range(1, 3), "/auto/usado/citroen/c4-hatchback": range(2, 5),
                 "/auto/usado/citroen/c4-mhev": range(5, 6)}.get(request.url.path, range(0))
            return httpx.Response(200, text=page(n, more=False))

        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(site)
        s.PAGE_PAUSE_SECONDS = 0
        filters = {"marca": "Citroën", "modelo": "C4"}

        found = await s.search(filters)
        again = await s.search(filters)

        self.assertEqual((len(found), found.complete, len(again)), (5, True, 5))
        self.assertEqual(asked.count("/auto/usado/citroen"), 1)      # kept for the day
        self.assertEqual([p for p in asked if p != "/auto/usado/citroen"][:3],
                         ["/auto/usado/citroen/c4", "/auto/usado/citroen/c4-hatchback",
                          "/auto/usado/citroen/c4-mhev"])

    async def test_a_variant_down_keeps_what_was_read_as_a_partial_read(self):
        def site(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auto/usado/citroen":
                return httpx.Response(200, text=CITROEN_MODELS)
            if request.url.path == "/auto/usado/citroen/c4-hatchback":
                return httpx.Response(503, text="")
            if request.url.path == "/auto/usado/citroen/c4-mhev":
                return httpx.Response(404, text="")
            return httpx.Response(200, text=page(range(1, 3), more=False))

        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(site)
        s.PAGE_PAUSE_SECONDS = s.RETRY_PAUSE_SECONDS = 0

        found = await s.search({"marca": "Citroën", "modelo": "C4"})

        self.assertEqual((len(found), found.complete), (2, False))
        self.assertEqual(found.reason, "autocosmos: página 1 de c4-hatchback respondió 503")

    async def test_a_failed_model_list_falls_back_to_the_model_slug(self):
        asked = []

        def site(request: httpx.Request) -> httpx.Response:
            asked.append(request.url.path)
            if request.url.path == "/auto/usado/citroen":
                return httpx.Response(503, text="")
            return httpx.Response(200, text=page(range(1, 3), more=False))

        s = AutoCosmosScraper()
        s.transport = httpx.MockTransport(site)

        found = await s.search({"marca": "Citroën", "modelo": "C4"})

        self.assertEqual((len(found), found.complete), (2, True))
        self.assertEqual(asked, ["/auto/usado/citroen", "/auto/usado/citroen/c4"])
        self.assertNotIn("citroen", autocosmos._model_pages)      # tried again next run


class DetailPageTests(unittest.IsolatedAsyncioTestCase):
    """An ad's page that turns us away is no ad gone (enrich, watchlist)."""
    ROW = {"id": 9, "source": "autocosmos", "url": f"https://www.autocosmos.com.ar/auto/usado/ford/fiesta/s/{1:032x}",
           "status": "active"}

    def setUp(self):
        breaker.clear()
        self.addCleanup(breaker.clear)

    def page(self, status: int):
        return patch("collectors.autocosmos.fetch_page",
                     AsyncMock(return_value=Page(status, self.ROW["url"], "<html>Too Many Requests</html>")))

    async def test_only_200_404_and_410_reach_the_parser(self):
        for status, error in ((401, CollectorBlocked), (403, CollectorBlocked), (429, CollectorBlocked),
                              (400, RuntimeError), (202, RuntimeError), (503, RuntimeError)):
            with self.page(status), self.assertRaises(error, msg=status):
                await AutoCosmosScraper().fetch_detail_page(self.ROW["url"])
        for status in (200, 404, 410):
            with self.page(status):
                self.assertEqual((await AutoCosmosScraper().fetch_detail_page(self.ROW["url"])).status, status)

    async def refresh(self, status: int):
        async def on_collector(coroutine, timeout=None):
            return await coroutine

        self.checked, self.ingested, self.saved = AsyncMock(), AsyncMock(), AsyncMock()
        with self.page(status), \
                patch.object(enrich, "run_collector", on_collector), \
                patch.object(enrich, "log_error", AsyncMock()), \
                patch.object(enrich.repo, "mark_detail_checked", self.checked), \
                patch.object(enrich.raw_pages, "save", self.saved), \
                patch.object(enrich, "ingest_detail", self.ingested):
            return await enrich.refresh_listing(dict(self.ROW), stage="watchlist")

    async def test_a_429_pauses_the_source_and_leaves_the_ad_alone(self):
        result = await self.refresh(429)

        self.assertEqual(result.events, [])
        self.ingested.assert_not_awaited()       # never parsed into a listing_gone
        self.saved.assert_not_awaited()
        self.checked.assert_not_awaited()        # tried again after the pause
        self.assertTrue(breaker.paused("autocosmos"))

    async def test_an_unexpected_4xx_is_retried_not_taken_for_gone(self):
        result = await self.refresh(400)

        self.assertEqual(result.events, [])
        self.ingested.assert_not_awaited()
        self.checked.assert_awaited_once_with([9])
        self.assertFalse(breaker.paused("autocosmos"))


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
