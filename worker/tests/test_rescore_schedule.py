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


# ---------------------------------------------------------------------------
# F-02: seller classification before the startup and the anchor-slot rescore
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, patch

from pipeline import rescore


def _run_loop(*, anchor: bool, classify_error: Exception | None = None):
    """One pass of nightly_loop: startup, then a single slot (anchor or not).
    Returns the calls in order and the log_error mock."""
    calls: list[str] = []
    stop = asyncio.Event()

    async def classify(trigger):
        calls.append(f"classify:{trigger}")
        if classify_error is not None:
            raise classify_error

    async def outdated():
        calls.append("rescore_outdated")

    async def recent():
        calls.append("rescore_recent")
        stop.set()

    async def purge():
        calls.append("purge")

    log_error = AsyncMock()
    with patch.object(rescore, "classify_sellers", side_effect=classify), \
            patch.object(rescore, "rescore_outdated", side_effect=outdated), \
            patch.object(rescore, "rescore_recent", side_effect=recent), \
            patch.object(rescore, "purge_stale_listings", side_effect=purge), \
            patch.object(rescore, "purge_raw_pages", AsyncMock()), \
            patch.object(rescore, "log_error", log_error), \
            patch.object(rescore, "next_slot", return_value=(0, anchor)), \
            patch.object(rescore.db, "get_config", AsyncMock(return_value={})):
        asyncio.run(rescore.nightly_loop(stop))
    return calls, log_error


def test_startup_classifies_sellers_before_rescore_outdated():
    calls, _ = _run_loop(anchor=False)
    assert calls[:2] == ["classify:startup", "rescore_outdated"]


def test_a_startup_classification_error_is_logged_and_the_rescore_runs():
    calls, log_error = _run_loop(anchor=False, classify_error=RuntimeError("boom"))
    assert calls[:2] == ["classify:startup", "rescore_outdated"]
    stage, ref, error = log_error.await_args_list[0].args
    assert (stage, ref) == ("seller_classification", "startup") and "boom" in error


def test_the_anchor_slot_classifies_before_rescore_recent():
    calls, _ = _run_loop(anchor=True)
    assert calls == ["classify:startup", "rescore_outdated", "classify:nightly", "rescore_recent", "purge"]


def test_an_anchor_classification_error_is_logged_and_the_rescore_runs():
    calls, log_error = _run_loop(anchor=True, classify_error=RuntimeError("boom"))
    assert calls == ["classify:startup", "rescore_outdated", "classify:nightly", "rescore_recent", "purge"]
    assert [c.args[:2] for c in log_error.await_args_list] == [
        ("seller_classification", "startup"), ("seller_classification", "nightly")]


def test_other_slots_do_not_classify():
    calls, _ = _run_loop(anchor=False)
    assert calls == ["classify:startup", "rescore_outdated", "rescore_recent"]
