"""AutoCosmos search: every page of the model, `?pidx=N`, retried on 503 (no network)."""
from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlparse

import httpx

from collectors.autocosmos import AutoCosmosScraper

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

    async def test_a_later_page_down_keeps_what_was_read(self):
        site = Site({1: page(range(1, 3), more=True)},
                    fail={2: [httpx.ConnectError("down")] * 3})

        found = await scraper(site).search(FILTERS)

        self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()
