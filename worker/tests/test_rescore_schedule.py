from datetime import datetime, timedelta, timezone

from pipeline.rescore import next_slot

_AR = timezone(timedelta(hours=-3))


def at(h, m=0):
    return datetime(2026, 10, 25, h, m, tzinfo=_AR)


def test_daily_default_is_the_anchor():
    wait, anchor = next_slot("04:00", 24, at(10))
    assert wait == 18 * 3600 and anchor


def test_every_six_hours_picks_the_nearest_slot():
    wait, anchor = next_slot("04:00", 6, at(11))
    assert wait == 5 * 3600 and not anchor  # 16:00


def test_anchor_slot_runs_retention():
    wait, anchor = next_slot("04:00", 6, at(3))
    assert wait == 3600 and anchor


def test_bad_interval_falls_back_to_daily():
    assert next_slot("04:00", 5, at(10)) == next_slot("04:00", 24, at(10))
