"""Publication windows and coverage, without live accounts or external requests."""
from __future__ import annotations

from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import pathlib
import unittest
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch
from urllib.parse import parse_qs, urlparse

from collectors import facebook as fb, mercadolibre as ml
from collectors.base import Listing, SearchResults
from collectors._recency import (DATE_MEMORY_CAP, DAY, DateSkip, PublicationWindow, encode_date_skips,
                                 parse_date_skips, target_window)
from pipeline import crawl
from pipeline.ingest import IngestResult
from test_mercadolibre_transport import FakeHttp

NOW = 1_700_000_000


def listing(identifier="1", published=NOW):
    return Listing("mercadolibre", identifier, "Ford Fiesta 2016",
                   f"https://auto.mercadolibre.com.ar/MLA-{identifier}-fiesta", published_at=published)


def card(identifier, age=None):
    date = (f'<meta itemprop="datePublished" content="{datetime.fromtimestamp(NOW - age * DAY, timezone.utc).isoformat()}">'
            if age is not None else "")
    return (f'<li class="ui-search-layout__item">{date}'
            f'<a class="poly-component__title" href="https://auto.mercadolibre.com.ar/MLA-{identifier}-fiesta">Ford Fiesta 2016</a></li>')


BASE = "https://autos.mercadolibre.com.ar"


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

    def test_a_count_only_target_reads_the_last_day_bucket_on_any_run(self):
        """As Mercado Libre's "Publicados hoy" (2.5): Corolla 445400 read 30 days a day."""
        def bucket(**filters):
            url = fb.FacebookMarketplaceScraper()._build_url(
                {"marca": "Toyota", "modelo": "Corolla", "publication_until": NOW, **filters})
            return parse_qs(urlparse(url).query)["daysSinceListed"]

        gap = {"publication_days": 2, "published_since": NOW - 2 * DAY}
        self.assertEqual(bucket(count_only=True, **gap), ["1"])
        self.assertEqual(bucket(count_only=True, publication_days=30), ["1"])      # its first run
        self.assertEqual(bucket(**gap), ["7"])


class DateMemoryTests(unittest.TestCase):
    """Facebook's date memory as prefilter_rejected stores it."""

    def test_entries_round_trip_and_malformed_ones_are_forgotten(self):
        memory = parse_date_skips(["11", f"12@{NOW}#2", f"13@{NOW}", "14@x#1", "@5", ""])
        self.assertEqual(memory, {"11": DateSkip(), "12": DateSkip(NOW, 2), "13": DateSkip(NOW, 1)})
        self.assertEqual(encode_date_skips(memory), ["11", f"12@{NOW}#2", f"13@{NOW}#1"])

    def test_an_undated_page_is_read_again_at_30_minutes_2_hours_and_6_hours_then_skipped(self):
        self.assertTrue(DateSkip().skips(NOW + 400 * DAY))                 # dated out of the window
        for reads, after in ((1, 1800), (2, 7200), (3, 21600)):
            entry = DateSkip(NOW, reads)
            self.assertTrue(entry.skips(NOW + after - 1), reads)
            self.assertFalse(entry.skips(NOW + after), reads)
        self.assertTrue(DateSkip(NOW, 4).skips(NOW + 20 * DAY))             # 3 attempts: skipped
        self.assertEqual(DateSkip.undated(None, NOW), DateSkip(NOW, 1))
        self.assertEqual(DateSkip.undated(DateSkip(NOW, 2), NOW + 7200), DateSkip(NOW, 3))

    def test_the_memory_keeps_the_newest_ids(self):
        memory = {str(i): DateSkip() for i in range(DATE_MEMORY_CAP + 5)}
        kept = encode_date_skips(memory)
        self.assertEqual(len(kept), DATE_MEMORY_CAP)
        self.assertNotIn("4", kept)
        self.assertIn(str(DATE_MEMORY_CAP + 4), kept)


class MercadoLibreWindowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch.dict(ml._dates, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def search(self, outcomes, *, page_size=1, **filters):
        http = FakeHttp(outcomes)
        with http.patch(), patch.object(ml, "_page_pause", AsyncMock()), patch.object(ml, "PAGE_SIZE", page_size):
            results = await ml.MercadoLibreScraper().search(
                {"marca": "Ford", "modelo": "Fiesta", "publication_days": 30, "publication_until": NOW, **filters})
        return results, http

    async def test_bootstrap_reads_every_page_and_does_not_stop_on_an_old_card(self):
        results, http = await self.search([
            (f"{BASE}/ford/fiesta/_NoIndex_True", card("1", 45), 200),
            (f"{BASE}/ford/fiesta/_Desde_2_NoIndex_True", card("2", 29), 200),
            (f"{BASE}/ford/fiesta/_Desde_3_NoIndex_True", card("3", 1), 200),
            (f"{BASE}/ford/fiesta/_Desde_4_NoIndex_True", '<div class="ui-search-rescue"></div>', 200),
        ])
        self.assertEqual([l.listing_id for l in results], ["MLA2", "MLA3"])
        self.assertTrue(results.complete)
        self.assertEqual(http.asked, [f"{BASE}/ford/fiesta/_NoIndex_True", f"{BASE}/ford/fiesta/_Desde_2_NoIndex_True",
                                      f"{BASE}/ford/fiesta/_Desde_3_NoIndex_True", f"{BASE}/ford/fiesta/_Desde_4_NoIndex_True"])

    async def test_a_short_page_is_the_last(self):
        results, http = await self.search([(f"{BASE}/ford/fiesta/_NoIndex_True", card("1", 3), 200)], page_size=48)
        self.assertEqual(([l.listing_id for l in results], len(http.asked)), (["MLA1"], 1))

    async def test_daily_scan_reads_the_today_filter_directly(self):
        today_url = f"{BASE}/ford/fiesta/_PublishedToday_YES_NoIndex_True"
        results, http = await self.search([(today_url, card("2", 0), 200)],
                                          page_size=48, publication_days=1, published_today_only=True)
        self.assertEqual(http.asked, [today_url])
        self.assertEqual([l.listing_id for l in results], ["MLA2"])

    async def test_a_window_of_a_day_or_a_count_only_target_reads_the_today_filter(self):
        today_url = f"{BASE}/ford/fiesta/_PublishedToday_YES_NoIndex_True"
        for filters in ({"publication_days": 2, "published_since": NOW - 24 * 3600 - 600},
                        {"count_only": True}):
            with self.subTest(**filters):
                results, http = await self.search([(today_url, card("5"), 200)], page_size=48, **filters)
                self.assertEqual((http.asked, [l.listing_id for l in results]), ([today_url], ["MLA5"]))

    async def test_an_ad_s_date_is_read_once_and_a_scan_reads_a_limited_number(self):
        detail = AsyncMock(return_value=NOW - 40 * DAY)
        page = (f"{BASE}/ford/fiesta/_NoIndex_True", card("1") + card("2") + card("3"), 200)
        with patch.object(ml.MercadoLibreScraper, "_publication_date", detail), \
                patch.object(ml.config, "RECENT_ML_DETAIL_SECONDS", 0), \
                patch.object(ml.config, "RECENT_ML_MAX_DATE_FETCHES", 2):
            first, _ = await self.search([page], page_size=48)
            second, _ = await self.search([page], page_size=48)
        self.assertEqual((first.complete, first.reason, first.unknown_dates), (False, "mercadolibre: date fetch limit reached", 1))
        self.assertEqual((second.complete, second.unknown_dates), (True, 0))
        self.assertEqual(detail.await_count, 3)          # MLA1 and MLA2 once, MLA3 on the second scan

    async def test_today_s_results_are_kept_without_reading_each_ad(self):
        """The ad's page says "hace 1 día" for an ad Mercado Libre lists as published today."""
        detail = AsyncMock(return_value=NOW - DAY)
        today_url = f"{BASE}/ford/fiesta/_PublishedToday_YES_NoIndex_True"
        with patch.object(ml.MercadoLibreScraper, "_publication_date", detail):
            results, http = await self.search([(today_url, card("3") + card("4"), 200)], page_size=48,
                                              publication_days=1, published_today_only=True,
                                              known_publication_dates={"MLA4": NOW - 3600})
        self.assertEqual([(l.listing_id, l.published_at) for l in results], [("MLA3", None), ("MLA4", NOW - 3600)])
        self.assertEqual((results.unknown_dates, http.asked), (0, [today_url]))
        detail.assert_not_awaited()

    async def test_page_limit_late_wall_and_a_repeated_page_are_partial_not_successful_bootstraps(self):
        first = (f"{BASE}/ford/fiesta/_NoIndex_True", card("1", 2), 200)
        with patch.object(ml.config, "RECENT_ML_MAX_PAGES", 1):
            results, _ = await self.search([first])
        self.assertFalse(results.complete)
        self.assertEqual(len(results), 1)
        results, _ = await self.search([first, ("https://www.mercadolibre.com.ar/captcha/wall/logged", "", 200)])
        self.assertFalse(results.complete)
        self.assertIn("security challenge", results.reason)
        self.assertEqual(len(results), 1)
        results, _ = await self.search([first, first])
        self.assertFalse(results.complete)
        self.assertIn("repeated", results.reason)

    async def test_a_wall_on_the_first_page_fails_the_run(self):
        with self.assertRaisesRegex(ml.CollectorBlocked, "security challenge"):
            await self.search([("https://www.mercadolibre.com.ar/captcha/wall/logged", "", 200)])

    async def test_date_cache_avoids_detail_and_missing_date_never_becomes_recent(self):
        detail = AsyncMock(return_value=None)
        with patch.object(ml.MercadoLibreScraper, "_publication_date", detail), \
                patch.object(ml.config, "RECENT_ML_DETAIL_SECONDS", 0):
            results, _ = await self.search([
                (f"{BASE}/ford/fiesta/_NoIndex_True", card("1") + card("2"), 200)
            ], page_size=48, known_publication_dates={"MLA1": NOW - DAY})
        self.assertEqual([l.listing_id for l in results], ["MLA1"])
        self.assertEqual(results.unknown_dates, 1)
        detail.assert_awaited_once()

    async def test_a_missing_date_is_read_from_the_ad(self):
        html = (pathlib.Path(__file__).parent / "fixtures" / "html" / "mercadolibre_detail.html").read_text(encoding="utf-8")
        with patch.object(ml.config, "RECENT_ML_DETAIL_SECONDS", 0):
            results, http = await self.search([
                (f"{BASE}/ford/fiesta/_NoIndex_True", card("7"), 200),
                ("https://auto.mercadolibre.com.ar/MLA-7-fiesta", html, 200),
            ], page_size=48, publication_days=30, publication_until=2_000_000_000)
        self.assertEqual(http.asked[1], "https://auto.mercadolibre.com.ar/MLA-7-fiesta")
        self.assertEqual(results.unknown_dates, 0)


class FacebookPage:
    """A virtualized feed: each scroll replaces, rather than appends, cards."""
    def __init__(self, batches, *, expire_after=None, body="Marketplace"):
        self.batches, self.index = batches, 0
        self.url = ""
        self.expire_after = expire_after
        self.body = body
        self.close = AsyncMock()
        self.wait_for_timeout = AsyncMock()
        self.mouse = MagicMock(wheel=AsyncMock(side_effect=self.scroll))
        self.on = MagicMock()
        self.remove_listener = MagicMock()

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
            return MagicMock(inner_text=AsyncMock(return_value=self.body))
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
    async def search(self, page, cookies=({"name": "c_user"},), **filters):
        @asynccontextmanager
        async def context(**kwargs):
            yield MagicMock(new_page=AsyncMock(return_value=page),
                            cookies=AsyncMock(return_value=list(cookies)))

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

    async def test_date_fetch_limit_ends_the_scan_and_the_retry_resumes(self):
        # Cards in English show no age: a first run of a popular model read
        # hundreds of item pages 30 s apart and never finished (2026-10-21).
        def feed():
            return FacebookPage([[(str(i), None) for i in range(1, 6)]])
        reads = []

        async def read_date(scraper, ctx, listing):
            reads.append(listing.listing_id)
            return NOW - DAY

        with patch.object(fb.config, "RECENT_FB_MAX_DATE_FETCHES", 2), \
                patch.object(fb.config, "RECENT_FB_DETAIL_SECONDS", 0), \
                patch.object(fb.FacebookMarketplaceScraper, "_publication_date", read_date):
            first = await self.search(feed())
            # The retry finds the kept listings' dates among the stored ones.
            second = await self.search(feed(), known_publication_dates={
                l.listing_id: l.published_at for l in first})
        self.assertEqual((first.complete, first.reason), (False, fb.DATE_FETCH_LIMIT))
        self.assertEqual([l.listing_id for l in first], ["1", "2"])
        self.assertEqual([l.listing_id for l in second], ["1", "2", "3", "4"])
        self.assertEqual(reads, ["1", "2", "3", "4"])

    async def test_daily_filter_still_checks_dates_when_platform_returns_old_suggestions(self):
        page = FacebookPage([[('1', 12), ('2', 0), ('2', 0)]])
        results = await self.search(page, publication_days=1)
        self.assertEqual([l.listing_id for l in results], ['2'])
        self.assertIn("daysSinceListed=1", page.url)

    async def test_confirmed_no_publications_with_login_prompt_is_successful_empty_search(self):
        # Visible text from the VPS: the login invitation accompanies a search,
        # rather than replacing its explicit no-results message.
        body = ('Iniciar sesión\nMarketplace\nResultados de la búsqueda\n'
                'Fecha de publicación: Últimas 24 horas\n'
                'No se encontraron publicaciones para "Hyundai i30" '
                'en un radio de 65 kilómetros\n'
                'Haz una nueva búsqueda.\nVe más en Facebook\n'
                'Correo electrónico o número de teléfono\nContraseña\nIniciar sesión')
        results = await self.search(FacebookPage([[]], body=body),
                                    marca="Hyundai", modelo="i30", publication_days=1)
        self.assertEqual(results, [])
        self.assertTrue(results.complete)
        self.assertIsNone(results.reason)
        self.assertEqual(results.unknown_dates, 0)

    async def test_english_no_listings_message_is_successful_empty_search(self):
        # The VPS account is in English (target 632735, 2026-10-20).
        body = ('Marketplace\nSearch results\nDate listed: Last 30 days\n'
                'No listings found for "Nissan Sentra" within 20 kilometers\n'
                'Try a new search. Check spelling, change your filters, or try a less specific search term.')
        results = await self.search(FacebookPage([[]], body=body), marca="Nissan", modelo="Sentra")
        self.assertEqual(results, [])
        self.assertTrue(results.complete)

    async def test_unconfirmed_empty_feed_is_still_blocked(self):
        for body in ("Marketplace", "Marketplace\nCargando...",
                     "Iniciar sesión\nCorreo electrónico\nContraseña"):
            with self.subTest(body=body):
                page = FacebookPage([[]], body=body)
                with self.assertRaisesRegex(fb.CollectorBlocked, "empty feed"):
                    await self.search(page)
                page.close.assert_awaited_once()

    async def test_expired_session_is_not_mistaken_for_no_publications(self):
        page = FacebookPage([[]], expire_after=1,
                            body='No se encontraron publicaciones para "Hyundai i30"')
        with self.assertRaisesRegex(fb.CollectorBlocked, "session expired"):
            await self.search(page)
        page.close.assert_awaited_once()

    async def test_logged_out_public_marketplace_is_blocked_not_an_empty_success(self):
        # Seen on the VPS since 2026-10-09: no redirect to /login, cards render,
        # every date is unknown, and the run used to finish ok with found=0.
        page = FacebookPage([[('1', None), ('2', None)]])
        with self.assertRaisesRegex(fb.CollectorBlocked, "logged out"):
            await self.search(page, cookies=({"name": "datr"},))
        page.close.assert_awaited_once()

    async def test_scroll_cap_and_expired_session_preserve_partial_results(self):
        with patch.object(fb.config, "RECENT_FB_MAX_SCROLLS", 1):
            results = await self.search(FacebookPage([[('1', 0)], [('2', 0)], [('3', 0)]]))
        self.assertFalse(results.complete)
        self.assertEqual([l.listing_id for l in results], ['1', '2'])
        results = await self.search(FacebookPage([[('1', 0)]], expire_after=1))
        self.assertFalse(results.complete)
        self.assertIn("session expired", results.reason)
        self.assertEqual([l.listing_id for l in results], ['1'])

    async def memory_scan(self, feed, dates, *, cap=30, until=NOW, **filters):
        """One scan of `feed` (ids without a card date) whose item pages say
        dates[id] (an exception is raised). Returns (results, ids read)."""
        reads = []

        async def read_date(scraper, ctx, listing):
            reads.append(listing.listing_id)
            outcome = dates[listing.listing_id]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        page = FacebookPage([[(i, None) for i in feed]])
        with patch.object(fb.config, "RECENT_FB_MAX_DATE_FETCHES", cap), \
                patch.object(fb.config, "RECENT_FB_DETAIL_SECONDS", 0), \
                patch.object(fb.FacebookMarketplaceScraper, "_publication_date", read_date):
            results = await self.search(page, publication_until=until, **filters)
        return results, reads

    async def test_dates_read_out_of_window_are_never_read_again(self):
        """Corolla 445400 (2026-10-22): two scans read 30 pages each and kept nothing new."""
        feed = [str(i) for i in range(1, 41)]
        dates = {i: NOW - DAY if int(i) <= 3 else NOW - 40 * DAY for i in feed}
        first, reads = await self.memory_scan(feed, dates, date_skips=[])
        self.assertEqual((len(reads), first.complete, first.reason), (30, False, fb.DATE_FETCH_LIMIT))
        self.assertEqual([l.listing_id for l in first], ["1", "2", "3"])
        self.assertEqual(sorted(first.date_skips, key=int), [str(i) for i in range(4, 31)])
        known = {l.listing_id: l.published_at for l in first}
        second, reads = await self.memory_scan(feed, dates, date_skips=first.date_skips,
                                               known_publication_dates=known)
        self.assertEqual((reads, second.complete), ([str(i) for i in range(31, 41)], True))
        self.assertEqual(sorted(second.date_skips, key=int), [str(i) for i in range(4, 41)])
        third, reads = await self.memory_scan(feed, dates, date_skips=second.date_skips,
                                              known_publication_dates=known)
        self.assertEqual((reads, third.complete, third.date_skips), ([], True, second.date_skips))
        # A complete scan forgets the ads it no longer sees; a partial one keeps them.
        fourth, _ = await self.memory_scan(feed[:20], dates, date_skips=second.date_skips,
                                           known_publication_dates=known)
        self.assertEqual(sorted(fourth.date_skips, key=int), [str(i) for i in range(4, 21)])

    async def test_an_undated_ad_is_read_again_and_gets_in_once_dated_yesterday(self):
        """In regime the window starts a day back: the 6-hour retry finds an ad
        published 20 hours before it was first seen, before today's `since`."""
        regime = lambda at: {"publication_days": 1, "published_since": at - DAY}
        undated = {"9": None}
        with patch.object(fb.config, "FB_DATE_MEMORY_UNKNOWN", True):
            first, reads = await self.memory_scan(["9"], undated, date_skips=[], **regime(NOW))
            self.assertEqual((reads, first.unknown_dates, first.date_skips), (["9"], 1, [f"9@{NOW}#1"]))
            memory = first.date_skips
            for at, read in ((NOW + 600, False), (NOW + 1800, True), (NOW + 3600, False), (NOW + 7200, True)):
                later, reads = await self.memory_scan(["9"], undated, until=at, date_skips=memory, **regime(at))
                self.assertEqual(reads, ["9"] if read else [], at - NOW)
                memory = later.date_skips
            self.assertEqual(memory, [f"9@{NOW}#3"])
            at = NOW + 6 * 3600
            last, reads = await self.memory_scan(["9"], {"9": NOW - 20 * 3600}, until=at, date_skips=memory,
                                                 **regime(at))
        self.assertEqual((reads, [l.listing_id for l in last], last.date_skips), (["9"], ["9"], []))
        # Without the memory, the same read leaves it out: it is before `since`.
        plain, _ = await self.memory_scan(["9"], {"9": NOW - 20 * 3600}, until=at, **regime(at))
        self.assertEqual(list(plain), [])

    async def test_an_ad_still_undated_after_three_retries_is_skipped(self):
        with patch.object(fb.config, "FB_DATE_MEMORY_UNKNOWN", True):
            results, reads = await self.memory_scan(["9"], {"9": None}, until=NOW + 20 * 3600,
                                                    date_skips=[f"9@{NOW}#3"])
            self.assertEqual((reads, results.date_skips), (["9"], [f"9@{NOW}#4"]))
            results, reads = await self.memory_scan(["9"], {"9": None}, until=NOW + 23 * 3600,
                                                    date_skips=results.date_skips)
        self.assertEqual((reads, results.date_skips, results.complete), ([], [f"9@{NOW}#4"], True))

    async def test_a_read_that_raised_is_never_remembered(self):
        with patch.object(fb.config, "FB_DATE_MEMORY_UNKNOWN", True):
            results, reads = await self.memory_scan(["8", "9"], {"8": RuntimeError("timeout"), "9": RuntimeError("x")},
                                                    date_skips=[f"9@{NOW - 3600}#1"])
        self.assertEqual(reads, ["8", "9"])
        self.assertEqual((results.complete, results.reason), (False, "facebook date fetch failed: RuntimeError"))
        self.assertEqual(results.date_skips, [f"9@{NOW - 3600}#1"])          # as it was, read again next scan

    async def test_undated_ads_are_not_remembered_until_the_flag_is_on(self):
        with self.assertLogs("collectors.facebook", "INFO") as logs:
            results, reads = await self.memory_scan(["8", "9", "10"], {"8": None, "9": None},
                                                    cap=2, date_skips=[f"9@{NOW - 600}#1", "7"])
        self.assertEqual((reads, results.unknown_dates), (["8", "9"], 3))
        # The page reads without a date, apart from the card the cap left unread (FB_DATE_MEMORY_UNKNOWN's measure).
        self.assertIn("undated=2 unknown_dates=3", logs.output[-1])
        self.assertEqual(results.date_skips, ["7"])           # no undated entry; a partial scan keeps the rest
        without, _ = await self.memory_scan(["8"], {"8": None})
        self.assertIsNone(without.date_skips)                                 # no memory asked: none kept

    async def test_the_probe_never_changes_the_results(self):
        batches = [[("1", 2), ("2", None)], [("3", 1)]]
        dates = AsyncMock(return_value=NOW - DAY)
        with patch.object(fb.FacebookMarketplaceScraper, "_publication_date", dates), \
                patch.object(fb.config, "RECENT_FB_DETAIL_SECONDS", 0):
            plain = await self.search(FacebookPage(batches))
            page = FacebookPage(batches)
            broken = MagicMock(status=200, text=AsyncMock(side_effect=RuntimeError("body gone")))
            goto = page.goto

            async def goto_and_answer(url, **kwargs):
                await goto(url, **kwargs)
                handler = page.on.call_args.args[1]
                odd = MagicMock()
                type(odd).url = PropertyMock(side_effect=RuntimeError("no url"))
                handler(odd)                                                   # raises inside: swallowed
                graphql = MagicMock(url="https://www.facebook.com/api/graphql/",
                                    text=AsyncMock(side_effect=RuntimeError("evicted")))
                graphql.request.resource_type = "xhr"
                handler(graphql)
                return broken

            def closing():
                page.remove_listener.assert_called_once_with("response", page.on.call_args.args[1])
            page.goto = goto_and_answer
            page.close = AsyncMock(side_effect=closing)
            probed = await self.search(page)
        self.assertEqual([l.listing_id for l in probed], [l.listing_id for l in plain])
        self.assertEqual((probed.complete, probed.reason, probed.unknown_dates),
                         (plain.complete, plain.reason, plain.unknown_dates))
        self.assertEqual(page.on.call_args.args[0], "response")
        self.assertEqual((probed.probe["cards"], probed.probe["graphql_bodies"], probed.probe["json_docs"]),
                         (3, 0, 0))

    async def test_unknown_date_is_not_promoted_to_today_and_cached_date_avoids_fetch(self):
        detail = AsyncMock(return_value=None)
        with patch.object(fb.FacebookMarketplaceScraper, "_publication_date", detail), \
                patch.object(fb.config, "RECENT_FB_DETAIL_SECONDS", 0):
            results = await self.search(FacebookPage([[('1', None), ('2', None)]]),
                                        known_publication_dates={'1': NOW - DAY})
        self.assertEqual([l.listing_id for l in results], ['1'])
        self.assertEqual(results.unknown_dates, 1)
        detail.assert_awaited_once()


class FeedProbeTests(unittest.TestCase):
    """The passive probe: does the feed's own data date the cards (phase 2)?"""
    FEED = {"data": {"marketplace_search": {"feed_units": {"edges": [
        {"node": {"story_time": NOW - 50, "listing": {"id": "1", "creation_time": NOW - 100,
                                                      "seller": {"id": "u1", "join_time": NOW - 9 * DAY}}}},
        {"node": {"listing": {"id": "2", "creation_time": NOW - 200, "is_live": True}}},
        {"node": {"listing": {"id": "77", "creation_time": NOW - 300}}},          # a suggestion
    ]}}}}

    def texts(self):
        graphql = "for (;;);" + json.dumps(self.FEED) + "\n" + json.dumps({"data": {"id": "3", "creation_time": NOW - 20}})
        html = ('<html><script type="application/json" data-sjs>'
                f'{json.dumps({"require": [{"id": "3", "creation_time": NOW - 10}]})}</script></html>')
        return [html, graphql]

    def test_feed_times_are_tied_to_their_own_listing(self):
        feed = fb._feed_times(self.texts(), ["1", "2", "3"], now=NOW)
        # The seller's own time isn't the ad's, the suggestion isn't a card, and
        # card 3 has two values for one path: it keeps none.
        self.assertEqual(feed.times, {"1": {"own.creation_time": NOW - 100, "edge.story_time": NOW - 50},
                                      "2": {"own.creation_time": NOW - 200}})
        self.assertEqual(feed.paths, Counter({"own.creation_time": 2, "edge.story_time": 1}))
        self.assertEqual((feed.present, feed.documents), ({"1", "2", "3"}, 3))

    def test_the_report_has_counts_and_path_names_never_a_value(self):
        probe = fb._FeedProbe()
        probe.texts = self.texts()
        for ident, text in (("1", "Ford Ka\nJust listed"), ("2", "Ford Ka"), ("3", "Ford Ka")):
            probe.card(ident, text)
        probe.page_times = {"1": NOW - 100 + 60, "2": NOW - 200 + 600}
        probe.dated("1", NOW - 2 * 3600)
        with patch("collectors._recency.time.time", return_value=NOW):
            report = probe.report({"2": NOW - 200})
        self.assertEqual(report["compared"], {"own.creation_time": [1, 1], "edge.story_time": [1, 0]})
        self.assertEqual(report["vs_known"], {"own.creation_time": [1, 0]})
        self.assertEqual((report["cards"], report["ids_in_data"], report["just_listed"],
                          report["just_listed_max_age_h"]), (3, 3, 1, 2.0))
        self.assertNotIn(str(NOW)[:6], json.dumps(report))
        self.assertEqual(probe.texts, [])                                      # dropped after the report


class FacebookCitySlugTests(unittest.TestCase):
    def test_origin_picks_a_slug_facebook_knows(self):
        # Formosa used to map to "santafe", which Facebook does not know: it
        # searched around the account's own location (Acassuso) instead.
        self.assertEqual(fb._city_slug_from_origin({"origin_lat": -26.18, "origin_lon": -58.17}), "formosa")
        self.assertEqual(fb._city_slug("Santa Fe"), "santa-fe")
        self.assertNotIn("santafe", fb.CITY_SLUGS.values())


class NativeUserAgentTests(unittest.TestCase):
    def test_matches_the_real_browser_and_never_says_headless(self):
        from collectors._browser import native_user_agent
        ua = native_user_agent("128.0.6613.18", "linux")
        self.assertEqual(ua, "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")
        self.assertIn("Windows NT 10.0", native_user_agent("128.0", "win32"))
        self.assertNotIn("Headless", native_user_agent("128.0"))


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
        target = {"id": 1, "source": "facebook", "crawl_interval_seconds": 600}
        stamp = datetime.fromtimestamp(NOW, timezone.utc)
        batch = crawl.TargetRun(target, [], IngestResult(), first_run=True, covered_until=stamp)
        handler = AsyncMock()
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], handler, 0, None)
        handler.assert_awaited_once_with(batch)
        finish.assert_awaited_once_with(1, ok=True, retry_seconds=0, covered_until=stamp, bootstrap=True,
                                       read=None)

    async def test_partial_batch_is_ingested_but_not_reported_successful(self):
        items = SearchResults([listing()], complete=False, reason="scroll cap")
        scraper = MagicMock(search=AsyncMock(return_value=items))
        target = {"id": 1, "source": "facebook", "make": "Ford", "model": "Fiesta",
                  "first_run_done": False, "crawl_interval_seconds": 3600}

        async def on_collector(coroutine, timeout=None):
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

    async def run_facebook(self, target, items):
        scraper = MagicMock(search=AsyncMock(return_value=items))

        async def on_collector(coroutine, timeout=None):
            return await coroutine

        with patch.dict(crawl.REGISTRY, {target["source"]: lambda: scraper}), \
                patch.object(crawl.runs, "start_run", AsyncMock(return_value=1)), \
                patch.object(crawl.runs, "finish_run", AsyncMock()), \
                patch.object(crawl.targets_repo, "publication_dates", AsyncMock(return_value={})), \
                patch.object(crawl.targets_repo, "set_prefilter_rejected", AsyncMock()) as remember, \
                patch.object(crawl, "run_collector", on_collector), \
                patch.object(crawl, "ingest", AsyncMock(return_value=IngestResult(found=len(items)))):
            await crawl.run_target(target)
        return scraper.search.call_args.args[0], remember

    async def test_a_facebook_target_by_model_keeps_its_date_memory(self):
        target = {"id": 4, "source": "facebook", "make": "Toyota", "model": "Corolla", "first_run_done": True,
                  "last_run_at": None, "crawl_interval_seconds": 1800, "prefilter_rejected": ["5"]}
        filters, remember = await self.run_facebook(target, SearchResults([listing()], date_skips=["1", "5"]))
        self.assertEqual(filters["date_skips"], ["5"])
        remember.assert_awaited_once_with(4, ["1", "5"])
        # Nothing new: no write. A collector that keeps no memory: no write either.
        for items in (SearchResults(date_skips=["5"]), SearchResults(complete=False, reason="cap")):
            _, remember = await self.run_facebook(target, items)
            remember.assert_not_awaited()

    async def test_only_facebook_targets_by_model_get_a_date_memory(self):
        for changes in ({"source": "facebook", "make": None, "model": None, "body_type": "suv"},
                        {"source": "kavak"}):
            target = {"id": 4, "source": "facebook", "make": "Toyota", "model": "Corolla", "first_run_done": True,
                      "last_run_at": None, "crawl_interval_seconds": 1800, "prefilter_rejected": ["5"], **changes}
            with self.subTest(**changes):
                filters, remember = await self.run_facebook(target, SearchResults(date_skips=["1"]))
                self.assertNotIn("date_skips", filters)
                remember.assert_not_awaited()

    async def test_a_facebook_scan_cut_at_its_page_cap_goes_on_in_three_minutes(self):
        target = {"id": 1, "crawl_interval_seconds": 1800, "query": {}}
        items = SearchResults(complete=False, reason=fb.DATE_FETCH_LIMIT)
        batch = crawl.TargetRun(target, items, IngestResult(), first_run=True, complete=False)
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], None, 0, None)
        self.assertEqual(finish.call_args.kwargs["retry_seconds"], 180)

    async def test_partial_target_does_not_advance_first_run_or_last_success(self):
        target = {"id": 1, "crawl_interval_seconds": 3600}
        batch = crawl.TargetRun(target, [], IngestResult(), first_run=True, complete=False)
        with patch.object(crawl, "run_target", AsyncMock(return_value=batch)), \
                patch.object(crawl.targets_repo, "finish_target", AsyncMock()) as finish:
            await crawl._run_source([target], None, 0, None)
        self.assertFalse(finish.call_args.kwargs["ok"])
        self.assertEqual(finish.call_args.kwargs["retry_seconds"], 900)
