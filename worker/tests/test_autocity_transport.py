from pathlib import Path
import unittest

import httpx
import pytest

from collectors._http import HEADERS
from collectors.autocity import AutocityScraper
from collectors.base import CollectorBlocked
from collectors.mardelusados import MardelUsadosScraper


FIXTURES = Path(__file__).parent / "fixtures" / "html"


def accepted_response(request, fixture):
    # The live site rejects the shared Chrome/124 header before parsing.
    if request.headers["User-Agent"] == HEADERS["User-Agent"]:
        return httpx.Response(403, text="403 - Forbidden")
    assert request.headers["User-Agent"] == "EseAuto/1.0"
    assert request.headers["Accept-Language"] == HEADERS["Accept-Language"]
    return httpx.Response(200, text=(FIXTURES / fixture).read_text(encoding="utf-8"))


class AutocityTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_catalog_identifies_autocity_client_before_fetching_inventory(self):
        scraper = AutocityScraper(transport=httpx.MockTransport(
            lambda request: accepted_response(request, "autocity_search.html")))
        items = await scraper.search({})
        assert {item.listing_id for item in items} == {"95276", "95281"}

    async def test_detail_uses_same_identification_and_preserves_vehicle_identity(self):
        scraper = AutocityScraper(transport=httpx.MockTransport(
            lambda request: accepted_response(request, "autocity_detail.html")))
        page = await scraper.fetch_detail_page("https://autocity.com.ar/?p=95281")
        detail = scraper.parse_detail(page.html, page.url, page.status)
        assert detail.listing.listing_id == "95281"

    async def test_other_regional_collectors_keep_their_existing_headers(self):
        def respond(request):
            assert request.headers["User-Agent"] == HEADERS["User-Agent"]
            return httpx.Response(200, text="Public page")

        scraper = MardelUsadosScraper(transport=httpx.MockTransport(respond))
        assert (await scraper._get(scraper.BASE)).status == 200

    async def test_actual_http_403_is_still_reported_as_blocked(self):
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(403, text="403 - Forbidden")

        scraper = AutocityScraper(transport=httpx.MockTransport(respond))
        with pytest.raises(CollectorBlocked, match="autocity: HTTP 403"):
            await scraper.search({})
        assert len(requests) == 1
