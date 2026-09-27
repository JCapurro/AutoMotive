from __future__ import annotations

import unittest
from unittest.mock import patch

from intelligence.opportunity import OpportunityScore
from pipeline.scheduler import _run_alert
from collectors.base import Listing


class _FakeBot:
    def __init__(self, exc: Exception | None = None) -> None:
        self.exc = exc
        self.messages: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        self.messages.append(kwargs)
        if self.exc:
            raise self.exc


class _SuccessfulScraper:
    async def search(self, filters: dict) -> list[Listing]:
        return [
            Listing(
                source="fake",
                listing_id="listing-1",
                titulo="Ford Fiesta",
                url="https://example.test/listing-1",
                precio=8000,
                moneda="USD",
                marca="Ford",
                modelo="Fiesta",
                anio=2018,
            )
        ]


class _FailingScraper:
    async def search(self, filters: dict) -> list[Listing]:
        raise RuntimeError("network down")


async def _identity_radius_filter(listings, filters):
    return list(listings)


def _alert() -> dict:
    return {
        "id": 42,
        "chat_id": 1001,
        "name": "Ford Fiesta",
        "filters": {"sources": ["fake"], "descuento_pct": 15},
        "bootstrapped": 1,
    }


class SchedulerFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_opportunity_delivery_is_left_unseen_for_retry(self):
        score = OpportunityScore(
            is_opportunity=True,
            median=10_000,
            sample_size=5,
            discount_pct=20.0,
            reason="cheap",
        )

        with self.assertLogs("scheduler", level="WARNING") as logs:
            with patch("pipeline.scheduler.REGISTRY", {"fake": _SuccessfulScraper}), \
                 patch("pipeline.scheduler.filter_listings_by_radius", _identity_radius_filter), \
                 patch("pipeline.scheduler.evaluate", return_value=score), \
                 patch("pipeline.scheduler.db.upsert_listings"), \
                 patch("pipeline.scheduler.db.get_config", return_value=15), \
                 patch("pipeline.scheduler.db.matched_by_other_profiles", return_value=set()), \
                 patch("pipeline.scheduler.db.filter_unseen") as filter_unseen, \
                 patch("pipeline.scheduler.db.mark_seen") as mark_seen, \
                 patch("pipeline.scheduler.db.mark_scraped") as mark_scraped:
                filter_unseen.side_effect = lambda alert_id, items: list(items)

                await _run_alert(_FakeBot(RuntimeError("telegram unavailable")), _alert())

        mark_seen.assert_not_called()
        mark_scraped.assert_not_called()
        self.assertTrue(any("delivery failed" in msg for msg in logs.output))

    async def test_failed_source_run_does_not_advance_scrape_cadence(self):
        with self.assertLogs("scheduler", level="WARNING") as logs:
            with patch("pipeline.scheduler.REGISTRY", {"fake": _FailingScraper}), \
                 patch("pipeline.scheduler.filter_listings_by_radius", _identity_radius_filter), \
                 patch("pipeline.scheduler.db.upsert_listings"), \
                 patch("pipeline.scheduler.db.filter_unseen", return_value=[]), \
                 patch("pipeline.scheduler.db.mark_seen") as mark_seen, \
                 patch("pipeline.scheduler.db.mark_scraped") as mark_scraped:
                await _run_alert(_FakeBot(), _alert())

        mark_seen.assert_not_called()
        mark_scraped.assert_not_called()
        self.assertTrue(any("no scraper source completed" in msg for msg in logs.output))


if __name__ == "__main__":
    unittest.main()
