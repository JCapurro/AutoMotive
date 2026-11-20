"""«Valor justo» against Postgres (spec 2026-11-20-valor-justo-design.md §4, §10): the repo's round trips,
fit_all with the mode off (no query of the new tables) and on, the catch-up, the loop, the scorer's cache and
price_pool's equivalence with comparable_listings. Needs the migration 20270107120000 on TEST_DATABASE_URL."""
from __future__ import annotations

import asyncio
import math
import random
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from db.repos import price_curves as repo
from intelligence import fair_value as fv
from pgcase import PostgresTestCase, requires_db
from pipeline import fair_value as job

_AR = timezone(timedelta(hours=-3))


@requires_db
class FairValuePostgresTests(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            if (await (await cx.execute("SELECT to_regclass('public.model_price_curves') IS NULL AS missing")).fetchone())["missing"]:
                self.skipTest("migration 20270107120000_fair_value_shadow not applied on the test database")
            saved = await (await cx.execute("SELECT key, value FROM app_config WHERE key = 'fair_value'")).fetchone()
            self._saved = saved["value"] if saved else None
        await self.mode("shadow", min_listings=150)
        job.invalidate_cache()

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            if self._saved is None:
                await cx.execute("DELETE FROM app_config WHERE key = 'fair_value'")
            else:
                await cx.execute("UPDATE app_config SET value = %s WHERE key = 'fair_value'", (Jsonb(self._saved),))
        app_config.clear_config_cache()
        job.invalidate_cache()
        await super().asyncTearDown()

    async def mode(self, mode: str, **params) -> None:
        async with db.connection() as cx:
            await cx.execute("INSERT INTO app_config (key, value) VALUES ('fair_value', %s) "
                             "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                             (Jsonb({"mode": mode, **params}),))
        app_config.clear_config_cache()

    async def listings(self, n: int = 240, *, make="Pgfv", model="Modelo", seed=1, start=1) -> list[int]:
        rng = random.Random(seed)
        rows = []
        for i in range(start, start + n):
            year = rng.choice([2016, 2017, 2018])
            trim = rng.choice(["Base", "Full"])
            km = int(math.exp(math.log(90_000) + (2018 - year) * 0.15 + rng.gauss(0, 0.3)))
            price = round(math.exp(9.1 + 0.07 * (year - 2016) + (0.15 if trim == "Full" else -0.1)
                                   - 0.1 * (math.log(km) - math.log(90_000)) + rng.gauss(0, 0.03)), 2)
            rows.append((i, "kavak", f"pgfv-{i}", f"https://example.test/fv{i}", f"{make} {model}", make, model, year,
                         price, "USD", price, km, "manual", trim))
        async with db.connection() as cx:
            async with cx.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO listings (id, source, external_id, url, title, make, model, year, price, currency, "
                    "  price_usd, mileage_km, transmission, trim, last_seen_at) OVERRIDING SYSTEM VALUE "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())", rows)
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ repo

    async def test_curves_and_runs_round_trip(self):
        curve = fv.fit([{"id": i, "year": 2017, "trim": "Base", "price_usd": 10_000 + i} for i in range(1, 20)],
                       job.fair_value_config({"mode": "shadow"}), make="Pgfv", model="Modelo")
        from dataclasses import replace
        curve = replace(curve, enabled=True, cv_err=0.05, cohort_err=0.07, params="abc",
                        fitted_at=datetime(2026, 11, 21, 6, 30, tzinfo=timezone.utc))
        async with db.connection() as cx:
            run_id = await repo.start_run(cx, trigger="cli", params={"params": "abc", "mode": "shadow"})
            await repo.save_curve(cx, curve, run_id=run_id)
            await repo.save_curve(cx, replace(curve, n=99), run_id=run_id)          # overwritten, one row
            await repo.finish_run(cx, run_id, status="ok", models_seen=1, models_fitted=1, models_enabled=1,
                                  stats={"models": [{"make": "pgfv", "model": "modelo", "n": 99}]})
            loaded = await repo.load_enabled(cx)
            rows = await repo.load_curves(cx)
            run = await (await cx.execute("SELECT * FROM fair_value_runs WHERE id = %s", (run_id,))).fetchone()
            ok_at = await repo.last_ok_started_at(cx)
        self.assertEqual(len(rows), 1)
        got = loaded[("pgfv", "modelo")]
        self.assertEqual((got.n, got.enabled, got.params), (99, True, "abc"))
        self.assertAlmostEqual(fv.fair_value({"year": 2017}, got).value, fv.fair_value({"year": 2017}, curve).value, places=1)
        self.assertEqual((run["status"], run["trigger"], run["params_hash"], run["models_enabled"]), ("ok", "cli", "abc", 1))
        self.assertIsNotNone(run["finished_at"])
        self.assertEqual(ok_at, run["started_at"])

    async def test_purge_keeps_90_days(self):
        async with db.connection() as cx:
            await cx.execute("INSERT INTO fair_value_runs (trigger, status, started_at) VALUES "
                             "('schedule', 'ok', now() - interval '91 days'), ('schedule', 'ok', now() - interval '89 days')")
            self.assertEqual(await repo.purge_runs(cx), 1)

    # ------------------------------------------------------------------ fit_all

    async def test_mode_off_touches_neither_table(self):
        await self.mode("off")
        boom = AsyncMock(side_effect=AssertionError("no SQL on the fair value tables with mode off"))
        with patch.multiple(repo, models_to_fit=boom, start_run=boom, enabled_before=boom, pool=boom,
                            last_ok_started_at=boom, load_enabled=boom):
            self.assertEqual((await job.fit_all(trigger="schedule"))["status"], "off")
            self.assertIsNone(await job.due_trigger(job.fair_value_config(await db.get_config("fair_value")),
                                                    datetime.now(_AR), None))
            self.assertEqual(await job.cached_curves(job.fair_value_config(await db.get_config("fair_value"))), {})
        async with db.connection() as cx:
            n = (await (await cx.execute("SELECT count(*) AS n FROM fair_value_runs")).fetchone())["n"]
        self.assertEqual(n, 0)

    async def test_fit_all_fits_gates_and_records_the_run(self):
        await self.listings()
        await self.listings(40, model="Chico", start=5000)            # under min_listings: not fitted
        result = await job.fit_all(trigger="cli")
        self.assertEqual(result["status"], "ok", result.get("error"))
        async with db.connection() as cx:
            curves = await repo.load_curves(cx)
            run = await (await cx.execute("SELECT * FROM fair_value_runs")).fetchone()
        self.assertEqual([(c["make"], c["model"]) for c in curves], [("pgfv", "modelo")])
        c = curves[0]
        self.assertEqual(c["n"], 240)
        self.assertTrue(c["enabled"], (c["cv_err"], c["cohort_err"]))
        self.assertLess(c["cv_err"], c["cohort_err"])
        self.assertEqual(c["params_hash"], result["params"]["params"])
        self.assertEqual((run["status"], run["models_seen"], run["models_fitted"], run["models_enabled"]), ("ok", 1, 1, 1))
        [stats] = run["stats"]["models"]
        self.assertEqual(set(stats["a"]), {"2016", "2017", "2018"})
        self.assertIn("guard_flips", stats)
        # The scorer's cache now has it.
        job.invalidate_cache()
        curves = await job.cached_curves(job.fair_value_config({"mode": "shadow"}))
        self.assertIn(("pgfv", "modelo"), curves)

    async def test_a_dry_run_writes_nothing(self):
        await self.mode("off")
        await self.listings()
        result = await job.fit_all(trigger="cli", dry_run=True, only=("Pgfv", "Modelo"))
        self.assertEqual(result["status"], "ok", result.get("error"))
        self.assertIn(("pgfv", "modelo"), result["curves"])
        async with db.connection() as cx:
            for table in ("model_price_curves", "fair_value_runs", "pipeline_errors"):
                n = (await (await cx.execute(f"SELECT count(*) AS n FROM {table}")).fetchone())["n"]
                self.assertEqual(n, 0, table)

    async def test_a_failure_closes_the_run_failed_and_keeps_the_curves(self):
        await self.listings()
        self.assertEqual((await job.fit_all(trigger="cli"))["status"], "ok")
        with patch.object(job, "fit_model", side_effect=RuntimeError("boom")):
            result = await job.fit_all(trigger="schedule")
        self.assertEqual(result["status"], "failed")
        async with db.connection() as cx:
            runs = await (await cx.execute("SELECT status, error FROM fair_value_runs ORDER BY id")).fetchall()
            curves = await repo.load_enabled(cx)
            errors = await (await cx.execute("SELECT stage FROM pipeline_errors")).fetchall()
        self.assertEqual([r["status"] for r in runs], ["ok", "failed"])     # its only model failed
        self.assertIn("every model failed", runs[1]["error"])
        self.assertIn(("pgfv", "modelo"), curves)
        self.assertEqual([e["stage"] for e in errors], ["fair_value"])

    async def test_one_failing_model_does_not_stop_the_others(self):
        await self.listings()
        await self.listings(200, model="Otro", seed=2, start=5000)
        real = job.fit_model

        def fit(rows, params, *, model, **kw):
            if model == "otro":
                raise RuntimeError("boom otro")
            return real(rows, params, model=model, **kw)

        with patch.object(job, "fit_model", side_effect=fit):
            result = await job.fit_all(trigger="schedule")
        self.assertEqual(result["status"], "ok", result.get("error"))
        self.assertEqual(result["models_failed"], 1)
        async with db.connection() as cx:
            run = await (await cx.execute("SELECT * FROM fair_value_runs")).fetchone()
            curves = await repo.load_curves(cx)
            errors = await (await cx.execute("SELECT stage, ref, error FROM pipeline_errors")).fetchall()
        self.assertEqual((run["status"], run["models_seen"], run["models_fitted"]), ("ok", 2, 1))
        self.assertEqual(run["stats"]["failed"], 1)
        bad = [m for m in run["stats"]["models"] if m["model"] == "otro"]
        self.assertIn("boom otro", bad[0]["error"])
        self.assertEqual([(c["make"], c["model"]) for c in curves], [("pgfv", "modelo")])
        self.assertEqual([(e["stage"], e["ref"]) for e in errors], [("fair_value", "pgfv otro")])

    async def test_a_failing_model_keeps_its_curve_and_a_missing_one_loses_it(self):
        await self.listings()
        await self.listings(200, model="Otro", seed=2, start=5000)
        await self.listings(200, model="Ido", seed=3, start=9000)
        self.assertEqual((await job.fit_all(trigger="cli"))["status"], "ok")
        async with db.connection() as cx:
            self.assertEqual({k[1] for k in await repo.load_enabled(cx)}, {"modelo", "otro", "ido"})
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '400 days' WHERE model = 'Ido'")
        real = job.fit_model

        def fit(rows, params, *, model, **kw):
            if model == "otro":
                raise RuntimeError("transient")
            return real(rows, params, model=model, **kw)

        with patch.object(job, "fit_model", side_effect=fit):
            self.assertEqual((await job.fit_all(trigger="schedule"))["status"], "ok")
        async with db.connection() as cx:
            enabled = {k[1] for k in await repo.load_enabled(cx)}
        self.assertEqual(enabled, {"modelo", "otro"})     # «otro» failed: yesterday's curve; «ido» is gone

    async def test_no_pool_connection_is_held_while_fitting(self):
        await self.listings()
        seen = []
        job_fit = job.fit_model
        held = []
        real = db.connection

        def counting():
            cm = real()

            class Wrap:
                async def __aenter__(self_inner):
                    held.append(1)
                    return await cm.__aenter__()

                async def __aexit__(self_inner, *exc):
                    held.pop()
                    return await cm.__aexit__(*exc)
            return Wrap()

        def fit_checked(*args, **kwargs):
            seen.append(len(held))
            return job_fit(*args, **kwargs)

        with patch.object(job.db, "connection", side_effect=counting), patch.object(job, "fit_model", side_effect=fit_checked), \
                patch.object(job.asyncio, "to_thread", wraps=asyncio.to_thread) as to_thread:
            self.assertEqual((await job.fit_all(trigger="cli"))["status"], "ok")
        self.assertEqual(seen, [0])
        self.assertEqual(to_thread.call_count, 1)

    # ------------------------------------------------------------------ the schedule

    async def run_at(self, hours_ago: float, status: str = "ok") -> None:
        async with db.connection() as cx:
            await cx.execute("INSERT INTO fair_value_runs (trigger, status, started_at) VALUES "
                             "('schedule', %s, now() - make_interval(secs => %s))", (status, hours_ago * 3600))

    async def test_the_catchup_runs_with_an_old_run_and_not_with_a_fresh_one(self):
        params = job.fair_value_config(await db.get_config("fair_value"))
        now = datetime.now(_AR)
        self.assertEqual(await job.due_trigger(params, now, None), "catchup")        # no run at all
        await self.run_at(30)
        self.assertEqual(await job.due_trigger(params, now, None), "catchup")
        await self.run_at(7, status="failed")                                        # failed 7 h ago: retry
        self.assertEqual(await job.due_trigger(params, now, None), "catchup")
        await self.run_at(1, status="failed")                                        # failed 1 h ago: back off
        self.assertIsNone(await job.due_trigger(params, now, None))
        async with db.connection() as cx:
            await cx.execute("DELETE FROM fair_value_runs WHERE status = 'failed'")
        await self.run_at(2)
        self.assertIsNone(await job.due_trigger(params, now, None))
        # A slot between the previous look and now runs even with a fresh run.
        slot = job.next_slot(now - timedelta(days=1), params)
        self.assertEqual(await job.due_trigger(params, slot + timedelta(minutes=1), slot - timedelta(minutes=1)), "schedule")

    async def test_the_loop_catches_up_once_and_a_restart_with_a_fresh_run_does_not(self):
        calls = []

        async def run(**kw):
            calls.append(kw["trigger"])
            await self.run_at(0)
            return {"status": "ok"}

        stop = asyncio.Event()
        task = asyncio.create_task(job.fair_value_loop(stop, check_every=0.05, run=run))
        await asyncio.sleep(0.4)
        stop.set()
        await task
        self.assertEqual(calls, ["catchup"])
        task = asyncio.create_task(job.fair_value_loop(stop := asyncio.Event(), check_every=0.05, run=run))
        await asyncio.sleep(0.2)
        stop.set()
        await task
        self.assertEqual(calls, ["catchup"])

    # ------------------------------------------------------------------ the scorer and the pool

    async def test_the_scorer_loads_the_curves_only_with_the_mode_on(self):
        from pipeline.scoring import Scorer
        await self.listings()
        await job.fit_all(trigger="cli")
        job.invalidate_cache()
        self.assertIn(("pgfv", "modelo"), (await Scorer.create()).curves)
        await self.mode("off")
        job.invalidate_cache()
        self.assertEqual((await Scorer.create()).curves, {})

    async def test_price_pool_with_the_listing_rules_is_comparable_listings(self):
        ids = await self.listings(60)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET year = NULL WHERE id = %s", (ids[1],))
            await cx.execute("UPDATE listings SET mileage_km = NULL WHERE id = ANY(%s)", ([ids[2], ids[3]],))
            await cx.execute("UPDATE listings SET probable_repost_of = %s WHERE id = %s", (ids[0], ids[4]))
            await cx.execute("UPDATE listings SET source = 'directo' WHERE id = %s", (ids[5],))
            pool = await repo.pool(cx, "PGFV", "modelo")
            for target in ids[:4]:
                t = await (await cx.execute("SELECT year, mileage_km FROM listings WHERE id = %s", (target,))).fetchone()
                want = sorted(r["id"] for r in await (await cx.execute(
                    "SELECT id FROM comparable_listings(%s)", (target,))).fetchall())
                got = sorted(p["id"] for p in pool
                             if p["id"] != target and p["probable_repost_of"] != target
                             and (t["year"] is None or (p["year"] is not None and abs(p["year"] - t["year"]) <= 1))
                             and (t["mileage_km"] is None or p["mileage_km"] is None
                                  or 0.75 * t["mileage_km"] <= p["mileage_km"] <= 1.25 * t["mileage_km"]))
                self.assertEqual(got, want, target)
        self.assertNotIn(ids[5], [p["id"] for p in pool])
        self.assertNotIn(ids[4], [p["id"] for p in pool])
