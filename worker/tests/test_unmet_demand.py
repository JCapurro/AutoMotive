"""Demanda insatisfecha: the settings, the cause and the row, and when the nightly job is due
(intelligence/unmet_demand.py, pipeline/unmet_demand.py)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from intelligence import low_results as lr
from intelligence import unmet_demand as ud
from pipeline import unmet_demand as job

SEARCH = {"id": 7, "user_id": "u-1", "result_count": 1,
          "filters": {"make": "Ford", "model": "Focus", "location_label": "Córdoba"}}


class SettingsTests(unittest.TestCase):
    def test_ships_off_and_a_bad_value_keeps_the_default(self):
        self.assertFalse(ud.settings(None)["enabled"])
        out = ud.settings({"enabled": True, "max_results": -1, "batch_size": 0, "pause_seconds": "x", "hour": "25:99"})
        self.assertTrue(out["enabled"])
        self.assertEqual(out["max_results"], 3)
        self.assertEqual(out["batch_size"], 1)          # at least one search per batch
        self.assertEqual(out["pause_seconds"], 2.0)
        self.assertEqual(out["hour"], "04:30")
        self.assertEqual(ud.settings({"hour": "03:15", "pause_seconds": 0})["hour"], "03:15")


class CauseTests(unittest.TestCase):
    def test_the_relaxation_that_adds_the_most(self):
        self.assertEqual(ud.cause({"zone": 2, "price": 9, "trim": 0, "year": 4}), "price")

    def test_nothing_helps_is_none(self):
        self.assertEqual(ud.cause({"zone": 0, "price": 0, "trim": 0, "year": 0}), "none")

    def test_a_tie_keeps_the_dashboard_order(self):
        self.assertEqual(ud.cause({"zone": 0, "price": 3, "trim": 3, "year": 3}), "price")


class RowTests(unittest.TestCase):
    def test_counts_come_from_the_funnel(self):
        fun = lr.Funnel(market=20, matched=1, fails={"location": 12, "year": 4}, only={"location": 9, "year": 2, "km": 5})
        row = ud.row(SEARCH, fun)
        self.assertEqual((row["relaxed_zone"], row["relaxed_year"], row["relaxed_price"], row["relaxed_trim"]),
                         (10, 3, 1, 1))
        self.assertEqual(row["cause"], "zone")
        self.assertEqual((row["market"], row["market_in_zone"]), (20, 8))
        self.assertEqual((row["make"], row["model"], row["zone_label"]), ("Ford", "Focus", "Córdoba"))
        self.assertEqual(row["result_count"], 1)

    def test_no_supply_is_none_even_with_other_filters_failing(self):
        # Only the km filter would help: not one of the four the dashboard names.
        row = ud.row(SEARCH, lr.Funnel(market=5, matched=0, fails={"km": 5}, only={"km": 5}))
        self.assertEqual(row["cause"], "none")
        self.assertEqual(row["relaxed_zone"], 0)

    def test_an_empty_market(self):
        row = ud.row(SEARCH, lr.Funnel())
        self.assertEqual((row["market"], row["market_in_zone"], row["cause"]), (0, 0, "none"))


class DueTests(unittest.TestCase):
    CFG = ud.settings({"enabled": True, "hour": "04:30"})
    # 2026-11-14 12:00 UTC is 09:00 in Argentina.
    NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)

    def test_after_the_hour_and_never_run(self):
        self.assertTrue(job.due(self.CFG, None, self.NOW))

    def test_before_the_hour(self):
        self.assertFalse(job.due(self.CFG, None, self.NOW.replace(hour=5)))      # 02:00 in Argentina

    def test_once_a_day(self):
        self.assertFalse(job.due(self.CFG, self.NOW - timedelta(hours=1), self.NOW))
        self.assertTrue(job.due(self.CFG, self.NOW - timedelta(days=1), self.NOW))


if __name__ == "__main__":
    unittest.main()
