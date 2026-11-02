"""Facebook parts and peso prices against Postgres: the ingest from now on,
and tools/repair_facebook.py for what was stored before."""
from __future__ import annotations

import pytest

import db
from collectors.base import Listing
from intelligence.config import SCORING_VERSION
from pgcase import TEST_FX_RATE, PostgresTestCase, requires_db
from pipeline.ingest import ingest
from tools import repair_facebook

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866


def fb(listing_id: str, title: str, price: float | None, currency: str | None = "USD", **kw) -> Listing:
    return Listing(source="facebook", listing_id=listing_id, titulo=title,
                   url=f"https://www.facebook.com/marketplace/item/{listing_id}/", precio=price,
                   moneda=currency, **kw)


class Case(PostgresTestCase):
    async def rows(self, sql: str, *params) -> list[dict]:
        async with db.connection() as cx:
            return await (await cx.execute(sql, params)).fetchall()

    async def listing(self, external_id: str) -> dict:
        [row] = await self.rows("SELECT * FROM listings WHERE external_id = %s", external_id)
        return row

    async def store(self, external_id: str, title: str, price: float | None, currency: str | None,
                    *, make: str = "Ford", model: str = "EcoSport", year: int | None = None,
                    km: int | None = None, moneda: str | None = None) -> int:
        """A row as the worker stored it before the fix: the price as read."""
        [row] = await self.rows(
            "INSERT INTO listings (source, external_id, url, title, make, model, year, mileage_km, "
            "  price, currency, price_usd, price_published, price_published_currency, attributes) "
            "VALUES ('facebook', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            external_id, f"https://www.facebook.com/marketplace/item/{external_id}/", title, make, model,
            year, km, price, currency, price if currency == "USD" else None, price, currency,
            db_json({"moneda": moneda or currency} if (moneda or currency) else {}))
        return row["id"]

    async def match(self, listing_id: int) -> None:
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Ecosport",
                                      filters={"marcas": ["Ford"], "modelos": ["EcoSport"],
                                               "sources": ["facebook"]})
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO matches (search_profile_id, listing_id, score, level, score_breakdown, "
                "                     match_reasons, scoring_version) "
                "VALUES (%s, %s, 75, 'good', '{}', '[]', %s)", (aid, listing_id, SCORING_VERSION))


def db_json(value):
    from psycopg.types.json import Jsonb
    return Jsonb(value)


@requires_db
class IngestTests(Case):
    async def test_a_part_is_never_stored(self):
        result = await ingest([fb("1", "Butacas Ford Ecosport", 350_000),
                               fb("2", "FORD ECOSPORT 1.4 XLS 2008", 6_400, anio=2008)], geocode=None)
        self.assertEqual((result.found, result.new, result.not_vehicle), (2, 1, 1))
        self.assertEqual([r["external_id"] for r in await self.rows("SELECT external_id FROM listings")], ["2"])

    async def test_a_stored_part_ends_without_an_event_and_loses_its_matches(self):
        lid = await self.store("1", "Butacas Ford Ecosport", 350_000, "USD")
        await self.match(lid)
        result = await ingest([fb("1", "Butacas Ford Ecosport", 350_000)], geocode=None)
        self.assertEqual(result.events, [])
        row = await self.listing("1")
        self.assertEqual((row["status"], row["price_partial"]), ("gone", True))
        self.assertIn("_not_vehicle", row["attributes"])
        self.assertEqual(await self.rows("SELECT * FROM matches"), [])

    async def test_a_peso_price_read_as_dollars_is_ars_and_no_price_drop(self):
        await self.store("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "USD", moneda="ARS")
        result = await ingest([fb("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 990_000)], geocode=None)
        self.assertNotIn("price_drop", [e.kind for e in result.events])
        row = await self.listing("21327")
        self.assertEqual((float(row["price"]), row["currency"], row["price_published_currency"]),
                         (990_000, "ARS", "ARS"))
        self.assertAlmostEqual(float(row["price_usd"]), 990_000 / TEST_FX_RATE)
        self.assertEqual(row["attributes"]["moneda"], "ARS")


@requires_db
class RepairToolTests(Case):
    async def seed(self) -> dict[str, int]:
        ids = {
            "part": await self.store("1", "Butacas Ford Ecosport", 350_000, "USD"),
            "part_gone": await self.store("2", "Paragolpe trasero de Ford Ecosport", 100_000, "USD"),
            "car_usd": await self.store("3", "FORD ECOSPORT 1.4 XLS 2008", 6_400, "USD", year=2008, km=150_000),
            "car_ars": await self.store("4", "FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "USD", moneda="ARS"),
            "car_no_price": await self.store("5", "2027 Volkswagen Polo", 285_000, "USD",
                                             make="Volkswagen", model="Polo"),
            "moneda": await self.store("6", "Ford Ecosport 2.0 4x2 XLT Plus", 10_000, "USD", moneda="ARS"),
            "porsche": await self.store("7", "Porsche 911 Carrera S", 180_000, "USD",
                                        make="Porsche", model="911"),
        }
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (ids["part_gone"],))
        await self.match(ids["part"])
        return ids

    async def test_dry_run_counts_and_writes_nothing(self):
        await self.seed()
        before = await self.rows("SELECT * FROM listings ORDER BY id")
        p = await repair_facebook.repair(write=False, sources=["facebook"])
        self.assertEqual(dict(p.counts), {
            ("facebook", repair_facebook.PART): 1,              # the gone one is left alone
            ("facebook", repair_facebook.PART_MATCHES): 1,
            ("facebook", repair_facebook.TO_ARS): 1,
            ("facebook", repair_facebook.NO_PRICE): 1,
            ("facebook", repair_facebook.MONEDA): 1,
        })
        self.assertIn("Butacas", p.examples[("facebook", repair_facebook.PART)][0])
        self.assertEqual(await self.rows("SELECT * FROM listings ORDER BY id"), before)
        self.assertEqual(len(await self.rows("SELECT * FROM matches")), 1)
        self.assertEqual(await self.rows("SELECT * FROM fx_rates"), [])
        self.assertIn("simulación", repair_facebook.report(p, write=False)[-1])

    async def test_write_applies_and_a_second_run_finds_nothing(self):
        ids = await self.seed()
        await repair_facebook.repair(write=True, sources=["facebook"])

        part = await self.listing("1")
        self.assertEqual((part["status"], part["price_partial"]), ("gone", True))
        self.assertEqual(part["attributes"]["_not_vehicle"]["reason"], "título: «butacas»")
        self.assertEqual(await self.rows("SELECT * FROM matches"), [])
        self.assertEqual((await self.listing("2"))["attributes"].get("_not_vehicle"), None)

        car = await self.listing("4")
        self.assertEqual((float(car["price"]), car["currency"], float(car["price_published"]),
                          car["price_published_currency"], car["attributes"]["moneda"]),
                         (990_000, "ARS", 990_000, "ARS", "ARS"))
        self.assertAlmostEqual(float(car["price_usd"]), 990_000 / TEST_FX_RATE)
        self.assertEqual(car["attributes"]["_currency_read"]["currency"], "USD")

        polo = await self.listing("5")
        self.assertEqual((polo["price"], polo["currency"], polo["price_usd"], polo["price_published"]),
                         (None, None, None, None))
        self.assertNotIn("moneda", polo["attributes"])
        self.assertEqual(polo["status"], "active")

        self.assertEqual((await self.listing("6"))["attributes"]["moneda"], "USD")
        for untouched in ("3", "7"):
            row = await self.listing(untouched)
            self.assertEqual((row["currency"], row["attributes"]["moneda"]), ("USD", "USD"), untouched)
        self.assertEqual(ids["car_usd"], (await self.listing("3"))["id"])

        again = await repair_facebook.repair(write=False, sources=["facebook"])
        self.assertEqual(dict(again.counts), {})

    async def test_only_the_named_sources(self):
        await self.seed()
        p = await repair_facebook.repair(write=False, sources=["mercadolibre"])
        self.assertEqual(dict(p.counts), {})
