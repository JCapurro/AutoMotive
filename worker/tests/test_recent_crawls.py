"""Publication windows and coverage, without live accounts or external requests."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

from collectors import facebook as fb, mercadolibre as ml
from collectors.base import Listing, SearchResults
from collectors._recency import DAY, PublicationWindow, target_window
from pipeline import crawl
from pipeline.ingest import IngestResult
from test_mercadolibre_transport import Page

NOW = 1_700_000_000


def listing(identifier="1", published=NOW):
    return Listing("mercadolibre", identifier, "Ford Fiesta 2016",
                   f"https://auto.mercadolibre.com.ar/MLA-{identifier}-fiesta", published_at=published)


def card(identifier, age=None):
    date = (f'<meta itemprop="datePublished" content="{datetime.fromtimestamp(NOW - age * DAY, timezone.utc).isoformat()}">'
            if age is not None else "")
    return (f'<li class="ui-search-layout__item">{date}'
            f'<a class="poly-component__title" href="https://auto.mercadolibre.com.ar/MLA-{identifier}-fiesta">Ford Fiesta 2016</a></li>')


def next_link(n):
    return f'<a rel="next" href="https://listado.mercadolibre.com.ar/autos/ford-fiesta_Desde_{n}">Siguiente</a>'


class WindowTests(unittest.TestCase):
    def test_first_run_is_thirty_days_for_both_sources(self):
        for source in ("mercadolibre", "facebook"):
            window = target_window({"source": source, "first_run_done": False}, now=NOW)
            self.assertEqual(window["publication_days"], 30)
            self.assertEqual(window["published_since"], NOW - 30 * DAY)
            self.assertFalse(window["published_today_only"])

    def test_daily_facebook_and_downtime_use_the_correct_native_buckets(self):
        for gap, bucket in ((3600, 1), (2 * DAY, 7), (10 * DAY, 30), (40 * DAY, 30)):
            f = target_window({"source": "facebook", "first_run_done": True,
                               "last_run_at": datetime.fromtimestamp(NOW - gap, timezone.utc)}, now=NOW)
            parsed = PublicationWindow.from_filters(f)
            self.assertEqual(parsed.facebook_days, bucket)
            if gap > DAY:
                self.assertLessEqual(f["published_since"], NOW - min(gap, 30 * DAY))

    def test_ml_uses_today_but_recovers_previous_day_across_argentina_midnight(self):
        for hour, native in ((15, True), (3, False)):
            now = int(datetime(2026, 10, 8, hour, 2, tzinfo=timezone.utc).timestamp())
            f = target_window({"source": "mercadolibre", "first_run_done": True,
                               "last_run_at": datetime.fromtimestamp(now - 600, timezone.utc)}, now=now)
            self.assertEqual(f["published_today_only"], native)
            if not native:
                self.assertLess(f["published_since"], now - 120)

    def test_date_unknown_is_never_replaced_by_detection_time(self):
        w = PublicationWindow(NOW - DAY, NOW, 1)
        with patch("collectors._recency.time.time", return_value=NOW):
            self.assertFalse(w.contains(listing(published=None)))
            self.assertFalse(w.contains(listing(published=NOW - DAY - 1)))
            self.assertFalse(w.contains(listing(published=NOW + 1)))
            self.assertTrue(w.contains(listing(published=NOW - DAY)))

    def test_other_sources_and_explicit_legacy_cli_are_unchanged(self):
        self.assertEqual(target_window({"source": "kavak"}, now=NOW), {})
        self.assertIsNone(PublicationWindow.from_filters({"marca": "Ford"}))

    def test_facebook_url_always_sorts_and_initializes_thirty_days(self):
        for days in (1, 30):
            params = parse_qs(urlparse(fb.FacebookMarketplaceScraper()._build_url(
                {"marca": "Ford", "modelo": "Fiesta", "publication_days": days})).query)
            self.assertEqual(params["daysSinceListed"], [str(days)])
            self.assertEqual(params["sortBy"], ["creation_time_descend"])


class MercadoLibreWindowTests(unittest.IsolatedAsyncioTestCase):
    def context(self, page):
        @asynccontextmanager
        async def context():
            yield MagicMock(new_page=AsyncMock(return_value=page))
        return patch.object(ml, "mercadolibre_context", context)

    async def search(self, outcomes, **filters):
        page = Page(outcomes)
        with self.context(page), patch.object(ml, "_page_pause", AsyncMock()):
            results = await ml.MercadoLibreScraper().search(
                {"publication_days": 30, "publication_until": NOW, **filters})
        page.close.assert_awaited_once()
        return results, page

    async def test_bootstrap_reads_beyond_two_pages_and_does_not_stop_on_an_old_card(self):
        results, page = await self.search([
            ("https://listado.mercadolibre.com.ar/autos", card("1", 45) + next_link(49), 200),
            ("https://listado.mercadolibre.com.ar/autos/ford-fiesta_Desde_49", card("2", 29) + next_link(97), 200),
            ("https://listado.mercadolibre.com.ar/autos/ford-fiesta_Desde_97", card("3", 1), 200),
        ])
        self.assertEqual([l.listing_id for l in results], ["MLA2", "MLA3"])
        self.assertTrue(results.complete)
        self.assertEqual(len(page.asked), 3)

    async def test_daily_scan_follows_the_real_today_filter_link(self):
        today_url = "https://autos.mercadolibre.com.ar/ford/fiesta/_PublishedToday_YES"
        results, page = await self.search([
            ("https://listado.mercadolibre.com.ar/autos", card("1", 20) + f'<a href="{today_url}">Publicados hoy (2)</a>', 200),
            (today_url, card("2", 0), 200),
        ], publication_days=1, published_today_only=True)
        self.assertEqual(page.asked[1], today_url)
        self.assertEqual([l.listing_id for l in results], ["MLA2"])

    async def test_page_limit_and_late_wall_are_partial_not_successful_bootstraps(self):
        first = ("https://listado.mercadolibre.com.ar/autos", card("1", 2) + next_link(49), 200)
        with patch.object(ml.config, "RECENT_ML_MAX_PAGES", 1):
            results, _ = await self.search([first])
        self.assertFalse(results.complete)
        self.assertEqual(len(results), 1)
        results, _ = await self.search([first, ("https://www.mercadolibre.com.ar/captcha/wall/logged", "", 200)])
        self.assertFalse(results.complete)
        self.assertIn("security challenge", results.reason)
        self.assertEqual(len(results), 1)

    async def test_date_cache_avoids_detail_and_missing_date_never_becomes_recent(self):
        detail = AsyncMock(return_value=None)
        with patch.object(ml.MercadoLibreScraper, "_publication_date", detail), \
                patch.object(ml.config, "RECENT_ML_DETAIL_SECONDS", 0):
            results, _ = await self.search([
                ("https://listado.mercadolibre.com.ar/autos", card("1") + card("2"), 200)
            ], known_publication_dates={"MLA1": NOW - DAY})
        self.assertEqual([l.listing_id for l in results], ["MLA1"])
        self.assertEqual(results.unknown_dates, 1)
        detail.assert_awaited_once()

    def test_pagination_preserves_filters_and_rejects_foreign_or_disabled_links(self):
        current = "https://autos.mercadolibre.com.ar/ford/fiesta/_PublishedToday_YES"
        url = current + "_Desde_49"
        self.assertEqual(ml._search_link(f'<a rel="next" href="{url}">Siguiente</a>', current), url)
        self.assertIsNone(ml._search_link('<a rel="next" href="https://example.com/next">Next</a>', current))
        self.assertIsNone(ml._search_link(f'<a rel="next" aria-disabled="true" href="{url}">Next</a>', current))


class FacebookPage:
    """A virtualized feed: each scroll replaces, rather than appends, cards."""
    def __init__(self, batches, *, expire_after=None):
        self.batches, self.index = batches, 0
        self.url = ""
        self.expire_after = expire_after
        self.close = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.mouse = MagicMock(wheel=AsyncMock(side_effect=self.scroll))

    async def goto(self, url, **kwargs):
        self.url = url
        return MagicMock(status=200)

    async def scroll(self, *args):
        self.index = min(self.index + 1, len(self.batches) - 1)
        if self.expire_after is not None:
            self.expire_after -= 1
            if self.expire_after <= 0:
                self.url = "https://www.facebook.com/checkpoint/"

    def locator(self, selector):
        if selector == "body":
            return MagicMock(inner_text=AsyncMock(return_value="Marketplace"))
        anchors = []
        for identifier, age in self.batches[self.index]:
            a = MagicMock(inner_text=AsyncMock(return_value=(
                "$10.000\nFord Fiesta 2016" + (f"\nHace {age} días" if age is not None else ""))))
            attributes = {"href": f"/marketplace/item/{identifier}", "aria-label": ""}
            a.get_attribute = AsyncMock(side_effect=lambda key, values=attributes: values.get(key))
            a.locator.return_value.first = MagicMock(count=AsyncMock(return_value=0))
            anchors.append(a)
        return MagicMock(all=AsyncMock(return_value=anchors))


class FacebookWindowTests(unittest.IsolatedAsyncioTestCase):
    async def search(self, page, **filters):
        @asynccontextmanager
        async def context(**kwargs):
            yield MagicMock(new_page=AsyncMock(return_value=page))

        with patch.object(fb, "browser_context", context), \
                patch.object(fb.Path, "exists", return_value=True), \
                patch("collectors._recency.time.time", return_value=NOW):
            results = await fb.FacebookMarketplaceScraper().search(
                {"marca": "Ford", "modelo": "Fiesta", "publication_days": 30,
                 "publication_until": NOW, **filters})
        page.close.assert_awaited_once()
        return results

    async def test_scans_past_three_scrolls_and_keeps_virtualized_cards(self):
        page = FacebookPage([[(str(i), 2)] for i in range(1, 7)])
        results = await self.search(page)
        self.assertEqual([l.listing_id for l in results], [str(i) for i in range(1, 7)])
        self.assertTrue(results.complete)
        self.assertGreater(page.mouse.wheel.await_count, 3)
        self.assertIn("daysSinceListed=30", page.url)
        self.assertIn("sortBy=creation_time_descend", page.url)

    async def test_daily_filter_still_checks_dates_when_platform_returns_old_suggestions(self):
        page = FacebookPage([[('1', 12), ('2', 0), ('2', 0)]])
        results = await self.search(page, publication_days=1)
        self.assertEqual([l.listing_id for l in results], ['2'])
        self.assertIn("daysSinceListed=1", page.url)

    async def test_scroll_cap_and_expired_session_preserve_partial_results(self):
        with patch.object(fb.config, "RECENT_FB_MAX_SCROLLS", 1):
            results = await self.search(FacebookPage([[('1', 0)], [('2', 0)], [('3', 0)]]))
        self.assertFalse(results.complete)
        self.assertEqual([l.listing_id for l in results], ['1', '2'])
        results = await self.search(FacebookPage([[('1', 0)]], expire_after=1))
        self.assertFalse(results.complete)
        self.assertIn("session expired", results.reason)
        self.assertEqual([l.listing_id for l in results], ['1'])

    async def test_unknown_date_is_not_promoted_to_today_and_cached_date_avoids_fetch(self):
        detail = AsyncMock(return_value=None)
        with patch.object(fb.FacebookMarketplaceScraper, "_publication_date", detail), \
                patch.object(fb.config, "RECENT_FB_DETAIL_SECONDS", 0):
            results = await self.search(FacebookPage([[('1', None), ('2', None)]]),
                                        known_publication_dates={'1': NOW - DAY})
        self.assertEqual([l.listing_id for l in results], ['1'])
        self.assertEqual(results.unknown_dates, 1)
        detail.assert_awaited_once()


class PipelineCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def test_handler_failure_keeps_the_coverage_checkpoint_for_retry(self):
        target = {"id": 1, "crawl_interval_seconds": 600}
        batch = crawl.TargetRun(target, [], IngestResult(), first_run=True)
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.runs, "log_error", AsyncMock()), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], AsyncMock(side_effect=RuntimeError("match failed")), 0, None)
        finish.assert_awaited_once_with(1, ok=False, retry_seconds=600)

    async def test_success_records_the_scan_start_as_coverage(self):
        target = {"id": 1, "crawl_interval_seconds": 600}
        stamp = datetime.fromtimestamp(NOW, timezone.utc)
        batch = crawl.TargetRun(target, [], IngestResult(), first_run=True, covered_until=stamp)
        handler = AsyncMock()
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], handler, 0, None)
        handler.assert_awaited_once_with(batch)
        finish.assert_awaited_once_with(1, ok=True, retry_seconds=0, covered_until=stamp)

    async def test_partial_batch_is_ingested_but_not_reported_successful(self):
        items = SearchResults([listing()], complete=False, reason="scroll cap")
        scraper = MagicMock(search=AsyncMock(return_value=items))
        target = {"id": 1, "source": "facebook", "make": "Ford", "model": "Fiesta",
                  "first_run_done": False, "crawl_interval_seconds": 3600}

        async def on_collector(coroutine):
            return await coroutine

        with patch.dict(crawl.REGISTRY, {"facebook": lambda: scraper}), \
                patch.object(crawl.runs, "start_run", AsyncMock(return_value=1)), \
                patch.object(crawl.runs, "finish_run", AsyncMock()) as finish, \
                patch.object(crawl.targets_repo, "publication_dates", AsyncMock(return_value={})), \
                patch.object(crawl, "run_collector", on_collector), \
                patch.object(crawl, "ingest", AsyncMock(return_value=IngestResult(found=1))) as ingest:
            result = await crawl.run_target(target)
        self.assertFalse(result.complete)
        self.assertTrue(result.first_run)
        ingest.assert_awaited_once()
        self.assertFalse(finish.call_args.kwargs["ok"])
        self.assertEqual(finish.call_args.kwargs["error"], "scroll cap")
        self.assertEqual(scraper.search.call_args.args[0]["publication_days"], 30)

    async def test_partial_target_does_not_advance_first_run_or_last_success(self):
        target = {"id": 1, "crawl_interval_seconds": 3600}
        batch = crawl.TargetRun(target, [], IngestResult(), first_run=True, complete=False)
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], None, 0, None)
        self.assertFalse(finish.call_args.kwargs["ok"])
        self.assertEqual(finish.call_args.kwargs["retry_seconds"], 900)
