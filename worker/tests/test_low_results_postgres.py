"""Bot de pocos resultados against Postgres: which searches it picks, the
diagnosis it stores, one notice per set of filters, RLS and the cleanup."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import low_results as repo
from llm.schemas import LowResultsExplanation
from notifications.links import Links
from pgcase import PostgresTestCase, requires_db
from pipeline import low_results as job

pytestmark = [pytest.mark.db, requires_db]

FILTERS = {"make": "Ford", "model": "Focus", "year_min": 2015, "year_max": 2015}


class Provider:
    name = "fake:test"

    def __init__(self):
        self.calls = 0

    async def explain_low_results(self, context):
        self.calls += 1
        return LowResultsExplanation(explanation=f"Hubo {context['embudo']['market']} Focus en el mes.",
                                     suggestions=["Sumá 2014 y 2016"])


class Bot:
    def __init__(self):
        self.sent = []

    async def send_message(self, **kw):
        self.sent.append(kw)


class Telegram:
    def __init__(self):
        self.bot = Bot()


class LowResultsTests(PostgresTestCase):
    async def rows(self, sql, *params, actor=False):
        async with db.connection() as cx:
            if actor:
                await cx.execute("SELECT set_config('request.jwt.claim.sub',%s,true)", (self.user,))
                await cx.execute("SET LOCAL ROLE authenticated")
            cur = await cx.execute(sql, params)
            return await cur.fetchall() if cur.description else []

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.user = (await self.rows(
            "INSERT INTO auth.users(instance_id,id,aud,role,email,created_at,updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000000',gen_random_uuid(),"
            "'authenticated','authenticated',%s,now(),now()) RETURNING id::text AS id",
            f"{uuid4()}@automotive.test"))[0]['id']
        await self.rows("UPDATE profiles SET telegram_chat_id = 42 WHERE id = %s", self.user)
        self.profile = await self.search(FILTERS)
        for year in (2014, 2015, 2016, 2016):
            await self.listing(year)
        self.telegram = Telegram()
        self.links = Links("https://ese.auto", "")

    async def search(self, filters, age="2 days"):
        return (await self.rows(
            "INSERT INTO search_profiles(user_id,name,filters,channels,bootstrapped_at,created_at) "
            "VALUES (%s,'Focus',%s,'{telegram,web}',now(),now() - %s::interval) RETURNING id",
            self.user, Jsonb(filters), age))[0]['id']

    async def listing(self, year, match_profile=None):
        lid = (await self.rows(
            "INSERT INTO listings(source,external_id,url,title,make,model,year,price,price_usd,currency,status) "
            "VALUES ('mercadolibre',%s,'https://example.test/focus','Focus','Ford','Focus',%s,"
            "10000,10000,'USD','active') RETURNING id", str(uuid4()), year))[0]['id']
        if match_profile:
            await self.rows(
                "INSERT INTO matches(search_profile_id,listing_id,score,level,score_breakdown,"
                "match_reasons,scoring_version) VALUES (%s,%s,50,'low','{}','{}','test')", match_profile, lid)
        return lid

    async def tick(self, provider):
        return await job.run_low_results(provider, {"telegram": self.telegram}, self.links,
                                         now=datetime.now(timezone.utc))

    async def test_diagnoses_and_notifies_once(self):
        provider = Provider()
        self.assertEqual(await self.tick(provider), 1)
        d = (await self.rows("SELECT * FROM search_diagnoses WHERE search_profile_id = %s", self.profile))[0]
        self.assertEqual(d["result_count"], 0)
        self.assertEqual(d["explanation"], "Hubo 4 Focus en el mes.")
        self.assertEqual(d["suggestions"], ["Sumá 2014 y 2016"])
        self.assertEqual(d["funnel"]["only"], {"year": 3})
        self.assertEqual(d["provider"], "fake:test")
        self.assertIsNotNone(d["notified_at"])
        self.assertEqual(len(self.telegram.bot.sent), 1)
        self.assertEqual(self.telegram.bot.sent[0]["chat_id"], 42)

        # Same filters, recent diagnosis: nothing to do.
        self.assertEqual(await self.tick(provider), 0)
        self.assertEqual(provider.calls, 1)

        # Old diagnosis, same filters: redone, not notified again.
        await self.rows("UPDATE search_diagnoses SET created_at = now() - interval '8 days'")
        self.assertEqual(await self.tick(provider), 1)
        self.assertEqual(len(self.telegram.bot.sent), 1)

        # New filters: diagnosed and notified again.
        await self.rows("UPDATE search_profiles SET filters = %s WHERE id = %s",
                        Jsonb({**FILTERS, "year_min": 2014}), self.profile)
        self.assertEqual(await self.tick(provider), 1)
        self.assertEqual(len(self.telegram.bot.sent), 2)

    async def test_skips_young_full_and_pending_searches(self):
        await self.rows("DELETE FROM search_profiles")
        await self.search(FILTERS, age="1 hour")
        full = await self.search({**FILTERS, "km_max": 200_000})
        for _ in range(4):
            await self.listing(2015, match_profile=full)
        pending = await self.search({**FILTERS, "km_max": 100_000})
        await self.rows("UPDATE search_profiles SET rematch_requested_at = now() WHERE id = %s", pending)
        await self.search({"body_types": ["suv"], "price_max": 20000, "currency": "USD"})
        self.assertEqual(await self.tick(Provider()), 0)

    async def test_discarded_and_gone_results_count_as_missing(self):
        lid = await self.listing(2015, match_profile=self.profile)
        for _ in range(3):
            await self.listing(2015, match_profile=self.profile)
        self.assertEqual(await repo.candidates(max_results=3, min_age_hours=24), [])
        await self.rows("INSERT INTO user_listing_interactions(user_id,listing_id,status) VALUES (%s,%s,'discarded')",
                        self.user, lid)
        self.assertEqual([r["result_count"] for r in await repo.candidates(max_results=3, min_age_hours=24)], [3])

    async def test_fallback_text_without_llm(self):
        self.assertEqual(await self.tick(None), 1)
        d = (await self.rows("SELECT provider, llm_error, explanation FROM search_diagnoses"))[0]
        self.assertIsNone(d["provider"])
        self.assertEqual(d["llm_error"], "sin proveedor LLM")
        self.assertIn("Elegiste un solo año (2015)", d["explanation"])

    async def test_resolved_search_loses_its_diagnosis(self):
        await self.tick(Provider())
        for _ in range(4):
            await self.listing(2015, match_profile=self.profile)
        self.assertEqual(await repo.clear_resolved(), 1)
        self.assertEqual(await self.rows("SELECT 1 FROM search_diagnoses"), [])

    async def test_owner_reads_and_dismisses_only(self):
        await self.tick(Provider())
        rows = await self.rows("SELECT explanation FROM search_diagnoses", actor=True)
        self.assertEqual(len(rows), 1)
        await self.rows("UPDATE search_diagnoses SET dismissed_at = now()", actor=True)
        self.assertIsNotNone((await self.rows("SELECT dismissed_at FROM search_diagnoses"))[0]["dismissed_at"])
        with self.assertRaises(Exception):
            await self.rows("UPDATE search_diagnoses SET explanation = 'x'", actor=True)
