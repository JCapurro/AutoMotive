"""Agencias, fase 1, against Postgres: the agency's alerts through the dealers
loop and the stock read job (photo or PDF) with a simulated model.

Needs migrations 20261228120000_dealer_program.sql and
20261229120000_dealer_phase1_extras.sql (skipped without them). Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/<clone>_test pytest -m db
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import db
from db.repos import dealers as dealers_repo
from llm.provider import LLMError
from llm.schemas import StockSheetRead
from pgcase import requires_db
from pipeline import llm_jobs
from test_dealers_postgres import ON, DealersCase

pytestmark = [pytest.mark.db, requires_db]

ALERTS = {**ON, "channel_enabled": False, "alerts_enabled": True, "alerts_every_hours": 24}
NEAR = (-34.73, -58.26)


class Phase1Case(DealersCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        dealers_repo.reset_schema_cache()
        if not await dealers_repo.phase1_ready():
            self.skipTest("migration 20261229120000_dealer_phase1_extras.sql not applied")

    async def market(self, n: int = 6, *, price: int = 20_000, **kw) -> list[int]:
        return [await self.listing(make="Toyota", model="Corolla", trim="XEI", year=2019, price=price + i * 200,
                                   price_usd=price + i * 200, mileage_km=60_000, lat=NEAR[0], lon=NEAR[1], **kw)
                for i in range(n)]

    async def alert_emails(self) -> list[dict]:
        return [e for e in self.emails if "stock" in e.get("subject", "")]


class AlertsTests(Phase1Case):
    async def corolla(self, d: int, *, days: int = 0) -> int:
        return await self.item(d, make="Toyota", model="Corolla", trim="XEI", year=2019, mileage_km=60_000,
                               price=21_000, currency="USD", in_stock_since=date.today() - timedelta(days=days))

    async def test_off_by_default_nothing_is_scanned(self):
        await self.program({**ALERTS, "alerts_enabled": False})
        d = await self.dealer()
        await self.corolla(d, days=90)
        await self.tick()
        self.assertEqual(await self.rows("SELECT * FROM dealer_alerts"), [])
        self.assertEqual(await self.rows("SELECT * FROM dealer_alert_state"), [])
        self.assertEqual(await self.alert_emails(), [])

    async def test_summary_once_then_only_whats_new(self):
        await self.program(ALERTS)
        d = await self.dealer()
        i = await self.corolla(d, days=90)
        await self.market()
        tick = await self.tick()
        # 1st pass: no reference to compare yet, but the car is slow (90 days, no model history: 60).
        [mail] = await self.alert_emails()
        self.assertEqual(mail["to"], ["tt@agencia.test"])
        self.assertEqual(mail["subject"], "Una novedad de tu stock en Ese Auto")
        self.assertIn("Tu Toyota Corolla 2019 lleva 90 días en stock.", mail["text"])
        self.assertIn("/agencia/datos", mail["text"])
        self.assertEqual((tick.alerts_added, tick.alert_emails), (1, 1))
        [state] = await self.rows("SELECT * FROM dealer_alert_state WHERE item_id = %s", i)
        self.assertIsNotNone(state["market_median_usd"])
        self.assertIsNotNone(state["cheaper_since"])
        self.assertEqual(await self.rows("SELECT id FROM dealer_alerts WHERE sent_at IS NULL"), [])

        # Not due yet: no scan, no email.
        cheap = await self.listing(make="Toyota", model="Corolla", year=2019, price=17_000, price_usd=17_000,
                                   mileage_km=55_000, lat=NEAR[0], lon=NEAR[1])
        await self.tick()
        self.assertEqual(len(await self.alert_emails()), 1)

        # Due again: only the cheaper car that appeared (the slow one was told already).
        await self.rows("UPDATE dealers SET alerts_checked_at = now() - interval '25 hours' WHERE id = %s RETURNING id", d)
        await self.tick()
        emails = await self.alert_emails()
        self.assertEqual(len(emails), 2)
        self.assertIn("más barato", emails[1]["text"])
        self.assertNotIn("lleva 90 días", emails[1]["text"])
        [a] = await self.rows("SELECT payload FROM dealer_alerts WHERE kind = 'cheaper_nearby'")
        self.assertEqual(a["payload"]["listing_id"], cheap)

        # Due again with nothing new: no email.
        await self.rows("UPDATE dealers SET alerts_checked_at = now() - interval '25 hours' WHERE id = %s RETURNING id", d)
        await self.tick()
        self.assertEqual(len(await self.alert_emails()), 2)

    async def test_market_drop_is_told(self):
        await self.program(ALERTS)
        d = await self.dealer()
        i = await self.corolla(d)
        ids = await self.market()
        await self.tick()
        self.assertEqual(await self.alert_emails(), [])           # first pass: only the reference
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET price_usd = price_usd * 0.85 WHERE id = ANY(%s)", (ids,))
            await cx.execute("UPDATE dealers SET alerts_checked_at = now() - interval '25 hours' WHERE id = %s", (d,))
        await self.tick()
        [mail] = await self.alert_emails()
        self.assertIn("Bajó el mercado del Toyota Corolla 2019", mail["text"])
        [st] = await self.rows("SELECT market_median_usd FROM dealer_alert_state WHERE item_id = %s", i)
        self.assertLess(float(st["market_median_usd"]), 18_000)

    async def test_the_agency_can_say_no(self):
        await self.program(ALERTS)
        d = await self.dealer()
        await self.corolla(d, days=90)
        await self.rows("UPDATE dealers SET alerts_email = false WHERE id = %s RETURNING id", d)
        await self.tick()
        self.assertEqual(await self.alert_emails(), [])
        self.assertEqual(await self.rows("SELECT * FROM dealer_alerts"), [])

    async def test_a_car_sold_before_the_summary_is_not_told(self):
        await self.program(ALERTS)
        d = await self.dealer()
        i = await self.corolla(d, days=90)
        await self.rows("INSERT INTO dealer_alerts (dealer_id, item_id, kind, dedup_key, payload) "
                        "VALUES (%s, %s, 'slow', 'slow:old', '{\"car\": \"X\", \"days\": 1}') RETURNING id", d, i)
        await self.rows("UPDATE dealer_stock_items SET status = 'sold' WHERE id = %s RETURNING id", i)
        await self.tick()
        self.assertEqual(await self.alert_emails(), [])
        [a] = await self.rows("SELECT sent_at FROM dealer_alerts WHERE dedup_key = 'slow:old'")
        self.assertIsNotNone(a["sent_at"])                        # closed, never sent later

    async def test_demand_is_never_told_under_three_people(self):
        await self.program(ALERTS)
        d = await self.dealer()
        i = await self.corolla(d)
        await self.market()
        await self.tick()                                          # reference: the fixture's searches
        await self.rows("UPDATE dealers SET alerts_checked_at = now() - interval '25 hours' WHERE id = %s RETURNING id", d)
        # Two new people searching a Corolla 2019: not told.
        for user in (9101, 9102):
            [pid] = await db.create_alert(user_id=user, chat_id=user, name="Corolla",
                                          filters={"marcas": ["Toyota"], "modelos": ["Corolla"]})
        await self.tick()
        self.assertEqual(await self.rows("SELECT * FROM dealer_alerts WHERE kind = 'new_demand'"), [])
        [st] = await self.rows("SELECT demand_people FROM dealer_alert_state WHERE item_id = %s", i)
        before = st["demand_people"]
        # A third one: told, as a count.
        [pid] = await db.create_alert(user_id=9103, chat_id=9103, name="Corolla",
                                      filters={"marcas": ["Toyota"], "modelos": ["Corolla"]})
        await self.rows("UPDATE dealers SET alerts_checked_at = now() - interval '25 hours' WHERE id = %s RETURNING id", d)
        await self.tick()
        [a] = await self.rows("SELECT payload FROM dealer_alerts WHERE kind = 'new_demand'")
        self.assertEqual(a["payload"]["searches"], 3)
        self.assertEqual(before, 0)
        mail = (await self.alert_emails())[-1]
        self.assertIn("Entraron 3 búsquedas nuevas", mail["text"])
        for secret in ("9101", "9102", "9103", "@"):
            self.assertNotIn(secret, mail["text"].split("—")[0])


class FakeReader:
    name = "fake:stock"

    def __init__(self, answer: dict | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[bytes, str]] = []

    async def stock_sheet(self, data: bytes, media_type: str) -> StockSheetRead:
        self.calls.append((data, media_type))
        if isinstance(self.answer, Exception):
            raise self.answer
        return StockSheetRead.model_validate(self.answer)


ANSWER = {"readable": True, "rows": [
    {"make": "Ford", "model": "Focus", "trim": "SE", "year": 2017, "mileage_km": 98000, "price": 14500000,
     "currency": "ARS", "color": None}]}


class StockReadTests(Phase1Case):
    async def queue(self, dealer_id: int, data: bytes = b"\xff\xd8 foto", media: str = "image/jpeg") -> tuple[int, int]:
        [r] = await self.rows("INSERT INTO dealer_stock_reads (dealer_id, media_type, filename, bytes, data, created_by) "
                              "VALUES (%s, %s, 'lista.jpg', %s, %s, %s::uuid) RETURNING id",
                              dealer_id, media, len(data), data, self.user)
        [j] = await self.rows("INSERT INTO llm_jobs (user_id, kind, input) VALUES (%s::uuid, 'dealer_stock_read', "
                              "jsonb_build_object('read_id', %s::bigint, 'dealer_id', %s::bigint)) RETURNING id",
                              self.user, r["id"], dealer_id)
        await self.rows("UPDATE dealer_stock_reads SET job_id = %s WHERE id = %s RETURNING id", j["id"], r["id"])
        return r["id"], j["id"]

    async def job(self, job_id: int) -> dict:
        [j] = await self.rows("SELECT * FROM llm_jobs WHERE id = %s", job_id)
        return j

    async def test_read_becomes_the_table_and_the_bytes_go(self):
        await self.program({**ON, "photo_import_enabled": True})
        d = await self.dealer()
        read_id, job_id = await self.queue(d)
        reader = FakeReader(ANSWER)
        self.assertTrue(await llm_jobs.process_next(reader, ["dealer_stock_read"]))
        self.assertEqual(reader.calls, [(b"\xff\xd8 foto", "image/jpeg")])
        job = await self.job(job_id)
        self.assertEqual((job["status"], job["provider"]), ("done", "fake:stock"))
        out = job["output"]
        self.assertEqual(out["headers"][:3], ["Marca", "Modelo", "Versión"])
        self.assertEqual(out["rows"], [["Ford", "Focus", "SE", "2017", "98000", "14500000", "ARS", ""]])
        self.assertTrue(out["readable"])
        [r] = await self.rows("SELECT data, read_at FROM dealer_stock_reads WHERE id = %s", read_id)
        self.assertIsNone(r["data"])
        self.assertIsNotNone(r["read_at"])

    async def test_switch_off_when_taken_never_calls_the_model(self):
        await self.program({**ON, "photo_import_enabled": False})
        d = await self.dealer()
        read_id, job_id = await self.queue(d)
        reader = FakeReader(ANSWER)
        await llm_jobs.process_next(reader, ["dealer_stock_read"])
        self.assertEqual(reader.calls, [])
        job = await self.job(job_id)
        self.assertEqual((job["status"], job["provider"]), ("failed", None))   # counts for no cost
        [r] = await self.rows("SELECT data FROM dealer_stock_reads WHERE id = %s", read_id)
        self.assertIsNone(r["data"])

    async def test_model_error_fails_the_job_and_the_bytes_still_go(self):
        await self.program({**ON, "photo_import_enabled": True})
        d = await self.dealer()
        read_id, job_id = await self.queue(d)
        await llm_jobs.process_next(FakeReader(LLMError("la API devolvió 500")), ["dealer_stock_read"])
        job = await self.job(job_id)
        self.assertEqual(job["status"], "failed")
        self.assertIn("500", job["error"])
        [r] = await self.rows("SELECT data FROM dealer_stock_reads WHERE id = %s", read_id)
        self.assertIsNone(r["data"])

    async def test_unread_files_are_purged_by_the_dealers_loop(self):
        await self.program(ON)
        d = await self.dealer()
        read_id, _ = await self.queue(d)
        await self.rows("UPDATE dealer_stock_reads SET created_at = now() - interval '2 hours' WHERE id = %s RETURNING id",
                        read_id)
        await self.program({**ON, "enabled": False})                # even with the program off
        await self.tick()
        [r] = await self.rows("SELECT data FROM dealer_stock_reads WHERE id = %s", read_id)
        self.assertIsNone(r["data"])
