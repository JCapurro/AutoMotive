"""F-03 fase 0 against the local Supabase Postgres
(docs/superpowers/specs/2026-10-29-f03-market-stats-fase0-design.md): listing
zones, the weekly market_stats job and its retention.
Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from pgcase import PostgresTestCase, requires_db
from pipeline import market_stats
from pipeline.market_stats import (WeekRejected, WriteDisabled, aggregate, fetch_rows, last_closed_week,
                                   run_market_stats, upsert_rows, week_bounds)
from pipeline.market_zones import sync_zones
from pipeline.retention import purge_market_stats
from normalization.zone import DEFAULT_ZONE_MAP

pytestmark = [pytest.mark.db, requires_db]

_AR = timezone(timedelta(hours=-3))
SAN_ISIDRO = (-34.4708, -58.5286)
ROSARIO = (-32.9442, -60.6505)
COMPARABLES = {"confirm_sources": ["autocity", "rosariogarage"], "confirm_grace_hours": 36, "max_age_days": 30}


class MarketCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._n = 0
        self.now = datetime.now(_AR)
        self.week = last_closed_week(self.now)
        self.start, self.end = week_bounds(self.week)
        async with db.connection() as cx:
            saved = await (await cx.execute(
                "SELECT key, value FROM app_config WHERE key IN ('comparables', 'market_stats', 'retention')"
            )).fetchall()
            self._saved = {r["key"]: r["value"] for r in saved}
            await cx.execute("UPDATE app_config SET value = value || %s WHERE key = 'comparables'",
                             (Jsonb(COMPARABLES),))
        app_config.clear_config_cache()

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            for key, value in self._saved.items():
                await cx.execute("UPDATE app_config SET value = %s WHERE key = %s", (Jsonb(value), key))
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def listing(self, **kw) -> int:
        """A listing row inserted directly: a Ford Fiesta 2018 of San Isidro
        first seen 10 days before the last closed week and seen now."""
        self._n += 1
        row = dict(source="mercadolibre", external_id=f"m{self._n}", url=f"https://example.test/m{self._n}",
                   title="Ford Fiesta", make="Ford", model="Fiesta", year=2018, price=11_000, currency="USD",
                   price_usd=11_000, mileage_km=100_000, location_text="San Isidro, Buenos Aires",
                   lat=SAN_ISIDRO[0], lon=SAN_ISIDRO[1], body_type="hatchback",
                   first_seen_at=self.start - timedelta(days=10), last_seen_at=self.now)
        row.update(kw)
        cols = list(row)
        async with db.connection() as cx:
            r = await (await cx.execute(
                f"INSERT INTO listings ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                list(row.values()))).fetchone()
        return r["id"]

    async def target(self, source: str, *, full_read_at: datetime) -> int:
        """An inventory crawl target whose last read of its whole stock was then."""
        async with db.connection() as cx:
            row = await (await cx.execute(
                "INSERT INTO crawl_targets (source, query, last_run_at, last_full_read_at, first_run_done) "
                "VALUES (%s, %s, %s, %s, true) RETURNING id",
                (source, Jsonb({"inventory": True}), full_read_at, full_read_at))).fetchone()
        return row["id"]

    async def zone(self, listing_id: int) -> dict | None:
        async with db.connection() as cx:
            return await (await cx.execute("SELECT * FROM listing_zones WHERE listing_id = %s",
                                            (listing_id,))).fetchone()

    async def count(self, table: str) -> int:
        async with db.connection() as cx:
            return (await (await cx.execute(f"SELECT count(*) AS n FROM {table}")).fetchone())["n"]

    async def stats(self, week_start: date | None = None, **key) -> list[dict]:
        where = " AND ".join(["week_start = %s"] + [f"{k} = %s" for k in key])
        async with db.connection() as cx:
            return await (await cx.execute(f"SELECT * FROM market_stats WHERE {where} ORDER BY zone",
                                           [week_start or self.start.date(), *key.values()])).fetchall()

    async def runs(self) -> list[dict]:
        async with db.connection() as cx:
            return await (await cx.execute("SELECT * FROM market_stats_runs ORDER BY id")).fetchall()


class ZonesTests(MarketCase):
    async def test_sync_writes_a_zone_per_listing_with_coordinates(self):
        active = await self.listing()
        gone = await self.listing(status="gone")
        nowhere = await self.listing(lat=None, lon=None, location_text=None)

        await sync_zones()

        zone = await self.zone(active)
        self.assertEqual((zone["province_id"], zone["department"], zone["precision"]),
                         ("06", "San Isidro", "locality"))
        self.assertIsNotNone(await self.zone(gone))           # the days to gone need them
        self.assertIsNone(await self.zone(nowhere))

    async def test_sync_is_idempotent_and_follows_moved_listings(self):
        lid = await self.listing()
        first = await sync_zones()
        self.assertEqual(first[("mercadolibre", "a escribir")], 1)
        derived = (await self.zone(lid))["derived_at"]
        again = await sync_zones()
        self.assertEqual(again[("mercadolibre", "a escribir")], 0)
        self.assertEqual((await self.zone(lid))["derived_at"], derived)

        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET lat = %s, lon = %s, location_text = 'Rosario, Santa Fe' "
                             " WHERE id = %s", (*ROSARIO, lid))
        await sync_zones()
        zone = await self.zone(lid)
        self.assertEqual((zone["province_id"], zone["lat"], zone["lon"]), ("82", *ROSARIO))

    async def test_dry_run_writes_nothing(self):
        lid = await self.listing()
        counts = await sync_zones(dry_run=True)
        self.assertEqual(counts[("mercadolibre", "con región")], 1)
        self.assertIsNone(await self.zone(lid))


class FetchAndUpsertTests(MarketCase):
    async def test_fetch_rows_flags_confirmation_and_carries_the_zone(self):
        on_sale = await self.listing(source="autocity")
        gone = await self.listing(source="autocity", last_seen_at=self.start + timedelta(days=1))
        fb = await self.listing(source="facebook", last_seen_at=self.start + timedelta(days=1))
        await self.listing(first_seen_at=self.end + timedelta(hours=1))             # after the week
        await self.listing(last_seen_at=self.start - timedelta(days=45))           # long gone
        await self.target("autocity", full_read_at=self.now)
        await self.target("facebook", full_read_at=self.now)
        await sync_zones()

        rows = {r["id"]: r for r in await fetch_rows(self.week, COMPARABLES)}

        self.assertEqual(set(rows), {on_sale, gone, fb})
        self.assertEqual((rows[gone]["confirm_source"], rows[gone]["unconfirmed"]), (True, True))
        self.assertEqual((rows[on_sale]["confirm_source"], rows[on_sale]["unconfirmed"]), (True, False))
        self.assertEqual((rows[fb]["confirm_source"], rows[fb]["unconfirmed"]), (False, False))
        self.assertEqual((rows[on_sale]["province_id"], rows[on_sale]["department"]), ("06", "San Isidro"))

        out = aggregate(rows.values(), week=self.week, zone_map=DEFAULT_ZONE_MAP,
                        cfg={**market_stats.DEFAULT_MARKET_STATS, **COMPARABLES})
        todas = next(s for s in out if s.group_kind == "model" and s.zone == "todas")
        self.assertEqual((todas.gone_count, todas.active_count, todas.active_confirmed_count), (1, 2, 1))

    async def test_fetch_rows_derives_a_missing_zone_in_memory(self):
        lid = await self.listing(lat=ROSARIO[0], lon=ROSARIO[1], location_text="Rosario, Santa Fe")
        rows = await fetch_rows(self.week, COMPARABLES)
        self.assertEqual(rows[0]["province_id"], "82")
        self.assertIsNone(await self.zone(lid))

    async def test_upsert_twice_replaces_the_week(self):
        for _ in range(3):
            await self.listing()
        stats = aggregate(await fetch_rows(self.week, COMPARABLES), week=self.week, zone_map=DEFAULT_ZONE_MAP,
                          cfg={**market_stats.DEFAULT_MARKET_STATS, **COMPARABLES})
        self.assertEqual(await upsert_rows(stats, weeks=[self.start.date()], run_id=None, as_of=self.now),
                         len(stats))
        await upsert_rows(stats, weeks=[self.start.date()], run_id=None, as_of=self.now)
        self.assertEqual(await self.count("market_stats"), len(stats))

        changed = [s for s in stats if s.group_kind == "model"]
        changed = [replace(s, active_count=99) for s in changed]
        await upsert_rows(changed, weeks=[self.start.date()], run_id=None, as_of=self.now)
        self.assertEqual(await self.count("market_stats"), len(changed))        # body_type rows went away
        self.assertEqual({r["active_count"] for r in await self.stats()}, {99})


class RunTests(MarketCase):
    async def test_preview_writes_nothing(self):
        lid = await self.listing()
        result = await run_market_stats(mode="preview", write_enabled=False, now=self.now)
        self.assertEqual(result["status"], "ok")
        self.assertGreater(result["report"]["rows"], 0)
        self.assertEqual((await self.count("market_stats"), await self.count("market_stats_runs")), (0, 0))
        self.assertIsNone(await self.zone(lid))

    async def test_scheduled_dry_run_leaves_one_run_and_no_rows(self):
        lid = await self.listing()
        result = await run_market_stats(mode="dry_run", write_enabled=False, now=self.now)
        [run] = await self.runs()
        self.assertEqual((run["mode"], run["status"], run["rows_written"]), ("dry_run", "ok", 0))
        self.assertGreater(run["rows_computed"], 0)
        self.assertEqual(run["week_start"], self.start.date())
        self.assertEqual(run["no_zone_by_source"], {"mercadolibre": {"total": 1, "no_zone": 0}})
        self.assertEqual(result["run_id"], run["id"])
        self.assertEqual(await self.count("market_stats"), 0)
        self.assertIsNotNone(await self.zone(lid))                                # sync_zones ran first

    async def test_write_needs_write_enabled(self):
        with self.assertRaises(WriteDisabled):
            await run_market_stats(mode="write", write_enabled=False, now=self.now)
        self.assertEqual(await self.count("market_stats_runs"), 0)

    async def test_write_writes_the_week_and_the_ones_before(self):
        await self.listing(first_seen_at=self.start - timedelta(days=30))
        result = await run_market_stats(mode="write", write_enabled=True, now=self.now)
        [run] = await self.runs()
        self.assertEqual((run["mode"], run["status"]), ("write", "ok"))
        self.assertEqual(run["rows_written"], await self.count("market_stats"))
        self.assertEqual(len(result["weeks"]), 3)                               # recompute_weeks: 2
        for week in result["weeks"]:
            rows = await self.stats(week_bounds(week)[0].date(), group_kind="model", zone="todas")
            self.assertEqual(rows[0]["active_count"], 1, week)
            self.assertEqual(rows[0]["run_id"], run["id"])
            self.assertEqual(rows[0]["zone_map_version"], 1)

    async def test_an_error_marks_the_run_failed_and_logs_it(self):
        await self.listing()
        with patch.object(market_stats, "fetch_rows", side_effect=RuntimeError("boom")):
            result = await run_market_stats(mode="dry_run", write_enabled=False, now=self.now)
        self.assertEqual(result["status"], "failed")
        [run] = await self.runs()
        self.assertEqual(run["status"], "failed")
        self.assertIn("boom", run["error"])
        async with db.connection() as cx:
            errors = await (await cx.execute("SELECT stage, error FROM pipeline_errors")).fetchall()
        self.assertEqual([e["stage"] for e in errors], ["market_stats"])
        self.assertIn("boom", errors[0]["error"])

    async def test_weeks_too_old_or_not_closed_are_rejected(self):
        old = (self.start - timedelta(weeks=3)).date()
        with self.assertRaises(WeekRejected):
            await run_market_stats(old, mode="preview", write_enabled=False, now=self.now)
        with self.assertRaises(WeekRejected):
            await run_market_stats(self.end.date(), mode="preview", write_enabled=False, now=self.now)
        result = await run_market_stats((self.start - timedelta(weeks=2)).date(), mode="preview",
                                        write_enabled=False, now=self.now)
        self.assertEqual(len(result["weeks"]), 1)                               # nothing older is recomputed


class RetentionTests(MarketCase):
    async def insert_week(self, weeks_ago: int) -> None:
        start = self.start.date() - timedelta(weeks=weeks_ago)
        async with db.connection() as cx:
            run = await (await cx.execute(
                "INSERT INTO market_stats_runs (week_start, mode, status) VALUES (%s, 'write', 'ok') RETURNING id",
                (start,))).fetchone()
            await cx.execute("INSERT INTO market_stats (week_start, group_kind, make, model, year_from, zone, run_id) "
                             "VALUES (%s, 'model', 'ford', 'fiesta', 2018, 'todas', %s)", (start, run["id"]))

    async def test_purge_market_stats_keeps_26_weeks(self):
        for weeks_ago in (0, 10, 24, 27, 40):
            await self.insert_week(weeks_ago)
        self.assertEqual(await purge_market_stats(), 2)
        self.assertEqual(await self.count("market_stats"), 3)
        self.assertEqual(await self.count("market_stats_runs"), 3)

    async def test_purge_follows_retention_and_defaults_to_26(self):
        for weeks_ago in (0, 5, 27):
            await self.insert_week(weeks_ago)
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = value || '{\"market_stats_weeks\": 4}' "
                             " WHERE key = 'retention'")
        app_config.clear_config_cache()
        self.assertEqual(await purge_market_stats(), 2)
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = value - 'market_stats_weeks' WHERE key = 'retention'")
        app_config.clear_config_cache()
        await self.insert_week(27)
        self.assertEqual(await purge_market_stats(), 1)
        self.assertEqual(await self.count("market_stats"), 1)

    async def test_a_write_run_purges(self):
        await self.insert_week(30)
        await run_market_stats(mode="write", write_enabled=True, now=self.now)
        self.assertEqual(await self.stats((self.start - timedelta(weeks=30)).date()), [])
