"""docs/PLAN_DELISTADOS.md without a database: the shapes of the config and what the pre-send check reads."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from notifications import dispatch
from pipeline.watchlist import DEFAULT_PER_SOURCE, per_source_limits


class PerSourceTests(unittest.TestCase):
    def test_one_number_is_every_sources_and_a_map_keeps_a_default(self):
        self.assertEqual(per_source_limits(None), {"default": DEFAULT_PER_SOURCE})
        self.assertEqual(per_source_limits(20), {"default": 20})
        self.assertEqual(per_source_limits({"mercadolibre": 150, "facebook": 5, "default": 40}),
                         {"mercadolibre": 150, "facebook": 5, "default": 40})
        self.assertEqual(per_source_limits({"facebook": 5}), {"facebook": 5, "default": DEFAULT_PER_SOURCE})

    def test_a_value_that_is_not_a_count_falls_back(self):
        self.assertEqual(per_source_limits("mucho"), {"default": DEFAULT_PER_SOURCE})
        self.assertEqual(per_source_limits({"facebook": "x", "kavak": -3}),
                         {"facebook": DEFAULT_PER_SOURCE, "kavak": 0, "default": DEFAULT_PER_SOURCE})


class PresendCandidatesTests(unittest.TestCase):
    def test_price_drops_and_digest_items_but_the_ones_told_as_over(self):
        rows = [
            {"kind": "price_drop", "listing_id": 1, "payload": {}},
            {"kind": "new_match", "listing_id": 2, "payload": {}},
            {"kind": "digest", "listing_id": None, "payload": {"items": [
                {"section": "matches", "listing_id": 3}, {"section": "gone", "listing_id": 4},
                {"section": "price_drops", "listing_id": "5"}, {"section": "matches", "listing_id": 1},
                "basura", {"section": "matches"}]}},
        ]
        self.assertEqual(dispatch.presend_candidates(rows, ["price_drop", "digest"]), [1, 3, 5])
        self.assertEqual(dispatch.presend_candidates(rows, ["price_drop"]), [1])
        self.assertEqual(dispatch.presend_candidates(rows, []), [])


class PresendSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_by_default_reads_nothing(self):
        with patch("db.get_config", AsyncMock(return_value={})), \
                patch("db.repos.listings.presend_stale", AsyncMock()) as stale:
            self.assertIsNone(await dispatch.presend_check([{"kind": "price_drop", "listing_id": 1}]))
        stale.assert_not_called()

    async def test_a_failure_never_holds_the_alerts(self):
        with patch("db.get_config", AsyncMock(return_value={"enabled": True})), \
                patch("db.repos.listings.presend_stale", AsyncMock(side_effect=RuntimeError("db down"))):
            self.assertIsNone(await dispatch.presend_check([{"kind": "price_drop", "listing_id": 1}]))


if __name__ == "__main__":
    unittest.main()
