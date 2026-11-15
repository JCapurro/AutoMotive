"""Demanda insatisfecha against Postgres: which searches get a row, the counts, the cleanup,
the batches and what the free cap hides (pipeline/unmet_demand.py, migration 20261222120000)."""
from datetime import datetime, timedelta, timezone
from unittest import mock
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos.config import clear_config_cache
from pgcase import PostgresTestCase, requires_db
from pipeline import unmet_demand as job

pytestmark = [pytest.mark.db, requires_db]

FOCUS = {"make": "Ford", "model": "Focus", "year_min": 2015, "year_max": 2015}


class UnmetDemandTests(PostgresTestCase):
    async def rows(self, sql, *params):
        async with db.connection() as cx:
            cur = await cx.execute(sql, params)
            return await cur.fetchall() if cur.description else []

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.user = (await self.rows(
            "INSERT INTO auth.users(instance_id,id,aud,role,email,created_at,updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000000',gen_random_uuid(),"
            "'authenticated','authenticated',%s,now(),now()) RETURNING id::text AS id",
            f"{uuid4()}@automotive.test"))[0]['id']
        await self.rows("DELETE FROM admin_unmet_demand_run")                     # not truncated between tests
        await self.config({"enabled": True, "pause_seconds": 0})

    async def config(self, value):
        await self.rows("INSERT INTO app_config(key,value) VALUES ('unmet_demand',%s) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", Jsonb(value))
        clear_config_cache()

    async def search(self, filters, age="2 days"):
        return (await self.rows(
            "INSERT INTO search_profiles(user_id,name,filters,channels,bootstrapped_at,created_at) "
            "VALUES (%s,'Busqueda',%s,'{web}',now(),now() - %s::interval) RETURNING id",
            self.user, Jsonb(filters), age))[0]['id']

    async def listing(self, year, model="Focus", status="active"):
        return (await self.rows(
            "INSERT INTO listings(source,external_id,url,title,make,model,year,price,price_usd,currency,status) "
            "VALUES ('mercadolibre',%s,'https://example.test/x','Auto','Ford',%s,%s,10000,10000,'USD',%s) RETURNING id",
            str(uuid4()), model, year, status))[0]['id']

    async def go(self, **kw):
        return await job.run_unmet_demand(now=datetime.now(timezone.utc), **kw)

    async def test_counts_the_year_that_would_unlock_listings(self):
        profile = await self.search(FOCUS)
        for year in (2014, 2016, 2016, 2013):
            await self.listing(year)
        await self.listing(2016, status="gone")
        self.assertEqual(await self.go(force=True), 1)
        row = (await self.rows("SELECT * FROM admin_unmet_demand WHERE search_profile_id = %s", profile))[0]
        self.assertEqual((row["result_count"], row["market"], row["cause"]), (0, 4, "year"))
        self.assertEqual((row["relaxed_year"], row["relaxed_zone"], row["relaxed_price"]), (4, 0, 0))
        run = (await self.rows("SELECT * FROM admin_unmet_demand_run"))[0]
        self.assertEqual((run["searches"], run["skipped_model_less"], run["cap_enforced"]), (1, 0, False))
        self.assertEqual(run["hidden_by_level"], {})

    async def test_only_few_result_model_searches_old_enough(self):
        await self.search(FOCUS, age="2 hours")                                   # too new
        await self.search({"body_types": ["suv"], "price_max": 20000})                                 # no model
        enough = await self.search({**FOCUS, "year_min": 2014})
        many = await self.search({"make": "Ford", "model": "Ka"})
        for _ in range(4):
            await self.rows(
                "INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,"
                "scoring_version) VALUES (%s,%s,50,'low','{}','{}','test')", many, await self.listing(2015, "Ka"))
        self.assertEqual(await self.go(force=True), 1)
        ids = [r["search_profile_id"] for r in await self.rows("SELECT search_profile_id FROM admin_unmet_demand")]
        self.assertEqual(ids, [enough])
        run = (await self.rows("SELECT * FROM admin_unmet_demand_run"))[0]
        self.assertEqual(run["skipped_model_less"], 1)

    async def test_a_search_that_recovers_loses_its_row_and_the_job_is_off_by_default(self):
        profile = await self.search(FOCUS)
        await self.listing(2016)
        self.assertEqual(await self.go(), 1)
        self.assertEqual(await self.go(), 0)                                      # already ran today
        await self.rows("UPDATE admin_unmet_demand_run SET computed_at = now() - interval '2 days'")
        await self.config({"enabled": False})
        self.assertEqual(await self.go(), 0)
        await self.config({"enabled": True, "pause_seconds": 0})
        for _ in range(4):
            await self.rows(
                "INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,"
                "scoring_version) VALUES (%s,%s,50,'low','{}','{}','test')", profile, await self.listing(2015))
        await self.go(force=True)
        self.assertEqual(await self.rows("SELECT 1 FROM admin_unmet_demand"), [])

    async def test_batches_pause_between_them_and_share_the_market_read(self):
        for n in range(5):
            await self.search({**FOCUS, "year_min": 2000 + n})
        await self.listing(2016)
        await self.config({"enabled": True, "batch_size": 2, "pause_seconds": 3})
        with mock.patch("pipeline.unmet_demand.asyncio.sleep", new=mock.AsyncMock()) as sleep, \
                mock.patch("pipeline.unmet_demand.recent_active", wraps=job.recent_active) as market:
            self.assertEqual(await self.go(force=True), 5)
        self.assertEqual(sleep.await_count, 2)                                     # 3 batches, 2 pauses
        self.assertEqual(market.await_count, 3)                                    # one read per model and batch
        self.assertEqual(len(await self.rows("SELECT 1 FROM admin_unmet_demand")), 5)

    async def test_what_the_cap_hides_goes_in_the_run(self):
        # A free account's match the quota never admitted (the cap off while it is created, as in the pgTAP test).
        profile = await self.search(FOCUS)
        lid = await self.listing(2015)
        await self.rows("INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,match_reasons,"
                        "scoring_version) VALUES (%s,%s,90,'high','{}','{}','test')", profile, lid)
        await self.rows("UPDATE app_config SET value = jsonb_set(value,'{enforced}','true') WHERE key = 'plan_limits'")
        await self.rows("DELETE FROM free_trial_results")
        try:
            clear_config_cache()
            await self.go(force=True)
        finally:
            await self.rows("UPDATE app_config SET value = jsonb_set(value,'{enforced}','false') WHERE key = 'plan_limits'")
            clear_config_cache()
        run = (await self.rows("SELECT * FROM admin_unmet_demand_run"))[0]
        self.assertEqual((run["cap_enforced"], run["hidden_by_level"], run["hidden_accounts"]), (True, {"high": 1}, 1))
