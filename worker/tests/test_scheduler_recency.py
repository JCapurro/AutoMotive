from __future__ import annotations

import unittest
from unittest.mock import patch

from pipeline.scheduler import _is_recent
from collectors.base import Listing


class SchedulerRecencyTests(unittest.TestCase):
    def _listing(self, published_at: int | None) -> Listing:
        return Listing(
            source="test",
            listing_id=str(published_at),
            titulo="Ford Fiesta",
            url="https://example.test/listing",
            published_at=published_at,
        )

    def test_recommendations_keep_listings_younger_than_15_days(self):
        now = 1_700_000_000
        fourteen_days_ago = now - 14 * 86_400

        with patch("pipeline.scheduler.time.time", return_value=now):
            self.assertTrue(_is_recent(self._listing(fourteen_days_ago), max_age_days=15))

    def test_recommendations_drop_listings_older_than_15_days(self):
        now = 1_700_000_000
        sixteen_days_ago = now - 16 * 86_400

        with patch("pipeline.scheduler.time.time", return_value=now):
            self.assertFalse(_is_recent(self._listing(sixteen_days_ago), max_age_days=15))

    def test_sources_without_publication_date_remain_eligible(self):
        with patch("pipeline.scheduler.time.time", return_value=1_700_000_000):
            self.assertTrue(_is_recent(self._listing(None), max_age_days=15))


if __name__ == "__main__":
    unittest.main()
