from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from pipeline.scheduler import _is_recent


class SchedulerRecencyTests(unittest.TestCase):
    """_is_recent reads stored listing rows (published_at is a timestamptz)."""

    def _row(self, published_at: int | None) -> dict:
        return {"source": "test", "external_id": str(published_at),
                "published_at": (datetime.fromtimestamp(published_at, timezone.utc)
                                 if published_at is not None else None)}

    def test_recommendations_keep_listings_younger_than_15_days(self):
        now = 1_700_000_000
        fourteen_days_ago = now - 14 * 86_400

        with patch("pipeline.scheduler.time.time", return_value=now):
            self.assertTrue(_is_recent(self._row(fourteen_days_ago), max_age_days=15))

    def test_recommendations_drop_listings_older_than_15_days(self):
        now = 1_700_000_000
        sixteen_days_ago = now - 16 * 86_400

        with patch("pipeline.scheduler.time.time", return_value=now):
            self.assertFalse(_is_recent(self._row(sixteen_days_ago), max_age_days=15))

    def test_sources_without_publication_date_remain_eligible(self):
        with patch("pipeline.scheduler.time.time", return_value=1_700_000_000):
            self.assertTrue(_is_recent(self._row(None), max_age_days=15))


if __name__ == "__main__":
    unittest.main()
