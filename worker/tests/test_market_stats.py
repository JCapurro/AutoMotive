"""F-03 fase 0: the weekly market aggregation (pipeline/market_stats.py), on
flat rows made up by hand. No database."""
from __future__ import annotations

import asyncio
import io
import threading
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from normalization.zone import DEFAULT_ZONE_MAP
from pipeline import market_stats as ms
from pipeline.market_stats import (aggregate, last_closed_week, next_run, percentile, report, scheduled_run,
                                   week_bounds)
from tools.market_stats import main as cli_main

_AR = timezone(timedelta(hours=-3))
WEEK = "2026-W44"                                   # Monday 26/10 to Sunday 1/11/2026
START = datetime(2026, 10, 26, tzinfo=_AR)
END = datetime(2026, 11, 2, tzinfo=_AR)
CFG = {"min_n": {"price": 8, "days": 5}, "year_band": 2, "max_age_days": 30,
       "confirm_since": {"mercadolibre": "2026-10-24"}}


def at(days: float) -> datetime:
    """`days` after the week starts (negative: before)."""
    return START + timedelta(days=days)


def row(**kw) -> dict:
    """An active Ford Fiesta 2018 of San Isidro, seen at the end of the week,
    first seen well before it, from a source that is not in confirm_sources."""
    r = dict(id=kw.pop("id", 1), source="facebook", make="Ford", model="Fiesta", body_type="hatchback",
             year=2018, status="active", price_usd=10_000.0, price_partial=False, probable_repost_of=None,
             first_seen_at=at(-20), seen_at=at(6.5), published_at=None, not_news=False,
             province_id="06", department="San Isidro", precision="locality",
             confirm_source=False, unconfirmed=False)
    r.update(kw)
    return r


def stats(rows, **cfg):
    return aggregate(rows, week=WEEK, zone_map=DEFAULT_ZONE_MAP, cfg={**CFG, **cfg})


def find(out, *, kind="model", zone="todas", year_from=2018, **key):
    hits = [s for s in out if s.group_kind == kind and s.zone == zone and s.year_from == year_from
            and all(getattr(s, k) == v for k, v in key.items())]
    assert len(hits) <= 1, hits
    return hits[0] if hits else None


class WeekTests(unittest.TestCase):
    def test_week_bounds_are_monday_to_monday_in_argentina(self):
        self.assertEqual(week_bounds(WEEK), (START, END))
        self.assertEqual(week_bounds(date(2026, 10, 28)), (START, END))     # any day of it

    def test_last_closed_week(self):
        self.assertEqual(last_closed_week(datetime(2026, 11, 2, 6, 0, tzinfo=_AR)), "2026-W44")
        # Monday 01:00 UTC is still Sunday in Argentina.
        self.assertEqual(last_closed_week(datetime(2026, 11, 2, 1, 0, tzinfo=timezone.utc)), "2026-W43")
        self.assertEqual(last_closed_week(datetime(2026, 10, 29, 12, 0, tzinfo=_AR)), "2026-W43")


class PercentileTests(unittest.TestCase):
    def test_linear_interpolation_like_percentile_cont(self):
        values = [10, 20, 30, 40]
        self.assertEqual(percentile(values, 0.5), 25.0)
        self.assertEqual(percentile(values, 0.25), 17.5)
        self.assertEqual(percentile(values, 0.75), 32.5)
        self.assertEqual(percentile([7], 0.5), 7.0)
        self.assertIsNone(percentile([], 0.5))
        self.assertEqual(percentile([40, 10, 30, 20], 0.5), 25.0)           # unsorted input


class AggregateTests(unittest.TestCase):
    def test_price_percentiles_need_min_n(self):
        rows = [row(id=i, price_usd=10_000.0 + 1_000 * i) for i in range(7)]
        s = find(stats(rows), make="ford", model="fiesta")
        self.assertEqual((s.active_count, s.price_n), (7, 7))
        self.assertIsNone(s.median_price_usd)
        rows.append(row(id=7, price_usd=17_000.0))
        s = find(stats(rows), make="ford", model="fiesta")
        self.assertEqual(s.price_n, 8)
        self.assertEqual((s.p25_price_usd, s.median_price_usd, s.p75_price_usd), (11_750.0, 13_500.0, 15_250.0))

    def test_prices_skip_partial_and_unknown(self):
        rows = [row(id=1), row(id=2, price_partial=True), row(id=3, price_usd=None), row(id=4, price_usd=0)]
        s = find(stats(rows), make="ford", model="fiesta")
        self.assertEqual((s.active_count, s.price_n), (4, 1))

    def test_days_need_min_n(self):
        gone = [row(id=i, source="autocity", confirm_source=True, unconfirmed=True, status="active",
                    first_seen_at=at(-10 - i), seen_at=at(2)) for i in range(4)]
        s = find(stats(gone), make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (4, 4))
        self.assertIsNone(s.median_days_to_gone)
        gone.append(row(id=4, source="autocity", confirm_source=True, unconfirmed=True,
                        first_seen_at=at(-14), seen_at=at(2)))
        s = find(stats(gone), make="ford", model="fiesta")
        self.assertEqual(s.days_n, 5)
        self.assertEqual((s.p25_days_to_gone, s.median_days_to_gone, s.p75_days_to_gone), (13.0, 14.0, 15.0))
        self.assertEqual(s.days_source, "confirm_sources")

    def test_year_bands(self):
        out = stats([row(id=1, year=2018), row(id=2, year=2019), row(id=3, year=2020), row(id=4, year=None)])
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 2)
        self.assertEqual(find(out, make="ford", model="fiesta", year_from=2020).active_count, 1)
        self.assertEqual(sum(s.active_count for s in out if s.group_kind == "model" and s.zone == "todas"), 3)

    def test_reposts_and_unknown_body_types_are_left_out(self):
        out = stats([row(id=1), row(id=2, probable_repost_of=1), row(id=3, body_type=None)])
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 2)
        self.assertEqual(find(out, kind="body_type", body_type="hatchback").active_count, 1)
        self.assertEqual({s.body_type for s in out if s.group_kind == "body_type"}, {"hatchback"})

    def test_todas_counts_the_listings_without_a_region(self):
        out = stats([row(id=1), row(id=2, province_id="82", department="Rosario"),
                     row(id=3, province_id="06", department=None, precision="province"),
                     row(id=4, province_id=None, department=None, precision=None)])
        regions = [s for s in out if s.group_kind == "model" and s.zone != "todas"]
        self.assertEqual({s.zone: s.active_count for s in regions}, {"amba": 1, "litoral": 1})
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 4)
        self.assertGreaterEqual(4, sum(s.active_count for s in regions))

    def test_new_count_ignores_not_news(self):
        out = stats([row(id=1, first_seen_at=at(1)), row(id=2, first_seen_at=at(2), not_news=True),
                     row(id=3, first_seen_at=at(-1)), row(id=4, first_seen_at=at(7.5))])
        s = find(out, make="ford", model="fiesta")
        self.assertEqual(s.new_count, 1)
        self.assertEqual(s.active_count, 3)                                  # first seen after the week: not yet

    def test_gone_only_from_confirm_sources_with_evidence(self):
        out = stats([
            row(id=1, source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(3)),
            row(id=2, source="autocity", confirm_source=True, unconfirmed=False, seen_at=at(3)),
            row(id=3, source="facebook", status="gone", seen_at=at(3)),       # mark_gone, not a full read
            row(id=4, source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(-2)),  # last week
        ])
        s = find(out, make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (1, 1))
        self.assertEqual((s.active_count, s.active_confirmed_count), (1, 1))  # 2 still counts; 1, 3, 4 do not

    def test_mercadolibre_before_confirm_since_is_left_out(self):
        early = datetime(2026, 10, 23, 12, tzinfo=_AR)
        out = aggregate([
            row(id=1, source="mercadolibre", confirm_source=True, unconfirmed=True, seen_at=early),
            row(id=2, source="mercadolibre", confirm_source=True, unconfirmed=True,
                seen_at=datetime(2026, 10, 24, 12, tzinfo=_AR)),
        ], week="2026-W43", zone_map=DEFAULT_ZONE_MAP, cfg=CFG)
        s = find(out, make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (1, 1))

    def test_days_skip_unknown_publication_of_old_stock_and_negatives(self):
        gone = dict(source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(3))
        out = stats([
            row(id=1, **gone, first_seen_at=at(-7)),                               # 10 days
            row(id=2, **gone, first_seen_at=at(-7), not_news=True),                # first crawl, not a publication
            row(id=3, **gone, first_seen_at=at(-7), not_news=True, published_at=at(-27)),  # 30 days
            row(id=4, **gone, first_seen_at=at(-7), published_at=at(5)),           # negative
        ])
        s = find(out, make="ford", model="fiesta")
        self.assertEqual((s.gone_count, s.days_n), (4, 2))
        self.assertEqual(percentile([10.0, 30.0], 0.5), 20.0)

    def test_active_confirmed_never_exceeds_active(self):
        out = stats([row(id=1), row(id=2, source="autocity", confirm_source=True),
                     row(id=3, source="autocity", confirm_source=True, unconfirmed=True, seen_at=at(1))])
        for s in out:
            self.assertLessEqual(s.active_confirmed_count, s.active_count)
        self.assertEqual(find(out, make="ford", model="fiesta").active_confirmed_count, 1)

    def test_seen_too_long_ago_is_not_active(self):
        out = stats([row(id=1), row(id=2, seen_at=at(-25))])                    # 32 days before the end
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 1)

    def test_make_and_model_group_case_insensitively(self):
        out = stats([row(id=1), row(id=2, make="FORD", model="fiesta "), row(id=3, make=None)])
        self.assertEqual(find(out, make="ford", model="fiesta").active_count, 2)

    def test_same_input_same_rows(self):
        rows = [row(id=i, year=2016 + i % 4, province_id=("06", "82", "14")[i % 3],
                    department=("San Isidro", "Rosario", "Capital")[i % 3]) for i in range(30)]
        self.assertEqual(stats(rows), stats(list(reversed(rows))))

    def test_every_row_carries_the_week_and_the_map_version(self):
        for s in stats([row()]):
            self.assertEqual((s.week_start, s.zone_map_version), (date(2026, 10, 26), 1))


class ReportTests(unittest.TestCase):
    def test_report(self):
        rows = [row(id=i) for i in range(8)] + [row(id=8, source="gruporandazzo", province_id=None,
                                                    department=None, precision=None)]
        out = stats(rows)
        rep = report(out, rows, week=WEEK, cfg=CFG)
        self.assertEqual(rep["rows"], len(out))
        self.assertEqual(rep["no_zone_by_source"]["gruporandazzo"], {"total": 1, "no_zone": 1})
        self.assertEqual(rep["no_zone_by_source"]["facebook"], {"total": 8, "no_zone": 0})
        self.assertEqual(rep["rows_with_price_sample"], 4)                    # model and body type, amba and todas
        self.assertEqual(sum(rep["price_n"].values()), len(out))
        self.assertGreater(rep["projected_mb_26_weeks"], 0)


class ScheduleTests(unittest.IsolatedAsyncioTestCase):
    SCHEDULE = {"schedule": {"weekday": 1, "hour": "06:00"}}

    def test_next_run_is_the_next_monday_at_six_in_argentina(self):
        thursday = datetime(2026, 10, 29, 12, 0, tzinfo=_AR)
        self.assertEqual(next_run(thursday, self.SCHEDULE), datetime(2026, 11, 2, 6, 0, tzinfo=_AR))
        monday_early = datetime(2026, 11, 2, 5, 59, tzinfo=_AR)
        self.assertEqual(next_run(monday_early, self.SCHEDULE), datetime(2026, 11, 2, 6, 0, tzinfo=_AR))
        monday_late = datetime(2026, 11, 2, 6, 0, tzinfo=_AR)
        self.assertEqual(next_run(monday_late, self.SCHEDULE), datetime(2026, 11, 9, 6, 0, tzinfo=_AR))
        utc = datetime(2026, 11, 2, 8, 0, tzinfo=timezone.utc)                # 05:00 in Argentina
        self.assertEqual(next_run(utc, self.SCHEDULE), datetime(2026, 11, 2, 6, 0, tzinfo=_AR))
        self.assertEqual(next_run(thursday, {"schedule": {"weekday": 3, "hour": "22:30"}}),
                         datetime(2026, 11, 4, 22, 30, tzinfo=_AR))
        self.assertEqual(next_run(thursday, {}), datetime(2026, 11, 2, 6, 0, tzinfo=_AR))   # the default

    async def test_off_runs_nothing(self):
        run = AsyncMock()
        self.assertIsNone(await scheduled_run({"mode": "off", "write_enabled": True}, run=run))
        self.assertIsNone(await scheduled_run({}, run=run))
        run.assert_not_called()

    async def test_dry_run_and_write_call_the_job_with_their_mode(self):
        run = AsyncMock(return_value={"status": "ok"})
        await scheduled_run({"mode": "dry_run", "write_enabled": False}, run=run)
        run.assert_awaited_with(mode="dry_run", write_enabled=False)
        await scheduled_run({"mode": "write", "write_enabled": True}, run=run)
        run.assert_awaited_with(mode="write", write_enabled=True)


class RunFailureTests(unittest.IsolatedAsyncioTestCase):
    """Every failure of run_market_stats is recorded and returned, never raised."""
    NOW = datetime(2026, 11, 4, 12, 0, tzinfo=_AR)                     # W45: last closed is W44

    async def job(self, week=None, *, mode="dry_run", write_enabled=False, configs=None):
        configs = configs or AsyncMock(return_value=({"recompute_weeks": 2}, {}, DEFAULT_ZONE_MAP))
        with patch.object(ms, "_configs", configs), \
             patch.object(ms, "_start_run", AsyncMock(return_value=7)) as start, \
             patch.object(ms, "_finish_run", AsyncMock()) as finish, \
             patch.object(ms, "log_error", AsyncMock()) as log_error, \
             patch.object(ms, "sync_zones", AsyncMock()), \
             patch.object(ms, "fetch_rows", AsyncMock(return_value=[row()])), \
             patch.object(ms, "purge_market_stats", AsyncMock()):
            result = await ms.run_market_stats(week, mode=mode, write_enabled=write_enabled, now=self.NOW)
        return result, start, finish, log_error

    async def test_write_disabled_is_a_recorded_failed_run(self):
        result, start, finish, log_error = await self.job(mode="write", write_enabled=False)
        self.assertEqual((result["status"], result["run_id"]), ("failed", 7))
        self.assertIn("WriteDisabled", result["error"])
        start.assert_awaited_once()
        self.assertEqual(start.await_args.args[:2], ("2026-W44", "write"))
        self.assertEqual(finish.await_args.kwargs["status"], "failed")
        log_error.assert_awaited_once()
        self.assertEqual(log_error.await_args.args[:2], ("market_stats", "2026-W44"))

    async def test_a_config_that_cannot_be_read_is_recorded(self):
        result, start, finish, log_error = await self.job(configs=AsyncMock(side_effect=RuntimeError("db down")))
        self.assertEqual(result["status"], "failed")
        self.assertIn("db down", log_error.await_args.args[2])
        start.assert_awaited_once()
        self.assertIn("db down", finish.await_args.kwargs["error"])

    async def test_a_rejected_week_is_recorded_with_its_message(self):
        result, start, finish, log_error = await self.job("2026-W30")
        self.assertEqual(result["status"], "rejected")
        self.assertIn("2026-W30", result["error"])
        self.assertNotIn("Traceback", result["error"])
        self.assertEqual(log_error.await_args.args[:2], ("market_stats", "2026-W30"))
        self.assertEqual(finish.await_args.kwargs["status"], "failed")

    async def test_a_preview_failure_logs_it_and_writes_no_run(self):
        result, start, finish, log_error = await self.job("not a week", mode="preview")
        self.assertEqual(result["status"], "failed")
        log_error.assert_awaited_once()
        start.assert_not_awaited()
        finish.assert_not_awaited()

    async def test_an_unknown_mode_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            await ms.run_market_stats(mode="sometimes", write_enabled=False, now=self.NOW)

    async def test_the_aggregation_runs_off_the_event_loop(self):
        loop_thread = threading.get_ident()
        threads = []

        def spy(fn):
            def wrapper(*args, **kwargs):
                threads.append((fn.__name__, threading.get_ident()))
                return fn(*args, **kwargs)
            return wrapper

        with patch.object(ms, "aggregate", spy(ms.aggregate)), patch.object(ms, "report", spy(ms.report)):
            result, *_ = await self.job()
        self.assertEqual(result["status"], "ok")
        self.assertEqual({name for name, _ in threads}, {"aggregate", "report"})
        self.assertNotIn(loop_thread, {t for _, t in threads})


class SyncZonesThreadTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_zones_runs_off_the_event_loop(self):
        from pipeline import market_zones
        seen = []
        real = market_zones.plan_zones

        def spy(*args, **kwargs):
            seen.append(threading.get_ident())
            return real(*args, **kwargs)

        rows = [dict(id=1, source="facebook", location_text="Rosario, Santa Fe", lat=-32.9442, lon=-60.6505,
                     status="active", zone_lat=None, zone_lon=None)]
        with patch.object(market_zones, "plan_zones", spy), \
             patch.object(market_zones, "_fetch", AsyncMock(return_value=rows)), \
             patch.object(market_zones, "_zone_map", AsyncMock(return_value=DEFAULT_ZONE_MAP)), \
             patch.object(market_zones, "_write", AsyncMock()) as write:
            counts = await market_zones.sync_zones()
        self.assertEqual(len(seen), 1)
        self.assertNotEqual(seen[0], threading.get_ident())
        write.assert_awaited_once()
        self.assertEqual(counts[("facebook", "con región")], 1)


class FakeClock:
    def __init__(self, now: datetime, until: datetime):
        self.now, self.until, self.waits = now, until, []

    def __call__(self) -> datetime:
        return self.now

    async def sleep(self, stop, seconds):
        self.waits.append(seconds)
        self.now += timedelta(seconds=seconds)
        if self.now >= self.until:
            stop.set()
            return True
        return False


class LoopTests(unittest.IsolatedAsyncioTestCase):
    async def loop(self, clock, cfgs, *, has_run=False):
        """Run market_stats_loop on the fake clock; `cfgs` is what each read of
        app_config.market_stats returns (the last one repeats)."""
        cfgs = list(cfgs)

        async def get_config(key, default=None):
            return cfgs.pop(0) if len(cfgs) > 1 else cfgs[0]

        ran = []

        async def run(**kwargs):
            ran.append((clock.now, kwargs["mode"]))
            return {"status": "ok"}

        with patch.object(ms.db, "get_config", get_config), \
             patch.object(ms, "_has_run", AsyncMock(return_value=has_run)) as has, \
             patch.object(ms, "_sleep", clock.sleep), \
             patch.object(ms, "log_error", AsyncMock()) as log_error:
            await ms.market_stats_loop(asyncio.Event(), clock=clock, run=run)
        log_error.assert_not_awaited()
        return ran, has

    async def test_runs_at_the_slot_looking_at_least_every_hour(self):
        clock = FakeClock(datetime(2026, 10, 29, 12, 0, tzinfo=_AR), datetime(2026, 11, 10, tzinfo=_AR))
        ran, has = await self.loop(clock, [{"mode": "dry_run"}], has_run=True)
        self.assertEqual(ran, [(datetime(2026, 11, 2, 6, 0, tzinfo=_AR), "dry_run"),
                               (datetime(2026, 11, 9, 6, 0, tzinfo=_AR), "dry_run")])
        self.assertLessEqual(max(clock.waits), ms.LOOP_CHECK_SECONDS)
        has.assert_awaited_once_with("2026-W43", "dry_run")                # the slot of Monday 26/10 ran

    async def test_a_schedule_changed_in_admin_config_applies_without_a_restart(self):
        clock = FakeClock(datetime(2026, 10, 29, 9, 0, tzinfo=_AR), datetime(2026, 10, 30, tzinfo=_AR))
        monday = {"mode": "dry_run", "schedule": {"weekday": 1, "hour": "06:00"}}
        thursday = {"mode": "dry_run", "schedule": {"weekday": 4, "hour": "13:30"}}
        ran, _ = await self.loop(clock, [monday, monday, thursday], has_run=True)
        self.assertEqual(ran, [(datetime(2026, 10, 29, 13, 30, tzinfo=_AR), "dry_run")])

    async def test_off_runs_nothing(self):
        clock = FakeClock(datetime(2026, 10, 29, 12, 0, tzinfo=_AR), datetime(2026, 11, 10, tzinfo=_AR))
        ran, has = await self.loop(clock, [{"mode": "off"}])
        self.assertEqual(ran, [])
        has.assert_not_awaited()

    async def test_a_slot_lost_while_down_runs_at_start(self):
        # Restarted Monday 09:00: the 06:00 slot passed with the worker down.
        clock = FakeClock(datetime(2026, 11, 2, 9, 0, tzinfo=_AR), datetime(2026, 11, 2, 12, 0, tzinfo=_AR))
        ran, has = await self.loop(clock, [{"mode": "write", "write_enabled": True}], has_run=False)
        self.assertEqual(ran, [(datetime(2026, 11, 2, 9, 0, tzinfo=_AR), "write")])
        has.assert_awaited_once_with("2026-W44", "write")

    async def test_a_slot_already_run_does_not_run_again_at_start(self):
        clock = FakeClock(datetime(2026, 11, 2, 9, 0, tzinfo=_AR), datetime(2026, 11, 2, 12, 0, tzinfo=_AR))
        ran, _ = await self.loop(clock, [{"mode": "dry_run"}], has_run=True)
        self.assertEqual(ran, [])


class CliTests(unittest.IsolatedAsyncioTestCase):
    async def cli(self, argv, *, cfg=None, result=None):
        run = AsyncMock(return_value=result or {"status": "ok", "weeks": [WEEK], "rows_computed": 0,
                                                "rows_written": 0, "report": None})
        with patch("tools.market_stats.db.open_pool", AsyncMock()), \
             patch("tools.market_stats.db.close_pool", AsyncMock()), \
             patch("tools.market_stats.db.get_config", AsyncMock(return_value=cfg or {})), \
             patch("tools.market_stats.run_market_stats", run), \
             patch("sys.stdout", new_callable=io.StringIO) as out:
            code = await cli_main(argv)
        return code, out.getvalue(), run

    async def test_dry_run_or_write_must_be_said(self):
        with patch("sys.stderr", new_callable=io.StringIO), self.assertRaises(SystemExit):
            await cli_main(["--week", WEEK])

    async def test_dry_run(self):
        code, _, run = await self.cli(["--week", WEEK, "--dry-run"])
        self.assertEqual(code, 0)
        run.assert_awaited_once_with("2026-W44", mode="preview", write_enabled=False)
        code, _, run = await self.cli(["--week", "--dry-run"])                 # the last closed week
        run.assert_awaited_once_with(None, mode="preview", write_enabled=False)

    async def test_write_needs_write_enabled(self):
        code, out, run = await self.cli(["--write"], cfg={"write_enabled": False})
        self.assertEqual(code, 2)
        self.assertIn("write_enabled", out)
        run.assert_not_called()
        code, _, run = await self.cli(["--write"], cfg={"write_enabled": True})
        self.assertEqual(code, 0)
        run.assert_awaited_once_with(None, mode="write", write_enabled=True)

    async def test_a_failed_run_exits_1(self):
        code, _, _ = await self.cli(["--dry-run"], result={"status": "failed", "error": "boom", "weeks": [],
                                                           "rows_computed": 0, "rows_written": 0,
                                                           "report": None})
        self.assertEqual(code, 1)

    async def test_a_rejected_week_exits_2_with_its_message(self):
        code, out, _ = await self.cli(["--week", "2026-W30", "--dry-run"],
                                      result={"status": "rejected", "error": "la semana 2026-W30 es anterior",
                                              "weeks": [], "rows_computed": 0, "rows_written": 0,
                                              "report": None})
        self.assertEqual(code, 2)
        self.assertIn("la semana 2026-W30 es anterior", out)


if __name__ == "__main__":
    unittest.main()
