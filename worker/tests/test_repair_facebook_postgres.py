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
        await self.store("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 1_990_000, "USD", moneda="ARS")
        result = await ingest([fb("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 1_990_000)], geocode=None)
        self.assertNotIn("price_drop", [e.kind for e in result.events])
        row = await self.listing("21327")
        self.assertEqual((float(row["price"]), row["currency"], row["price_published_currency"]),
                         (1_990_000, "ARS", "ARS"))
        self.assertAlmostEqual(float(row["price_usd"]), 1_990_000 / TEST_FX_RATE)
        self.assertEqual(row["attributes"]["moneda"], "ARS")

    async def test_a_peso_card_on_a_misread_stored_price_is_no_price_drop(self):
        # Still unrepaired and the seller lowered the price: USD 1.990.000
        # against $ 1.950.000 (ARS) is no 99% drop.
        await self.store("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 1_990_000, "USD", moneda="ARS")
        result = await ingest([fb("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 1_950_000)], geocode=None)
        kinds = [e.kind for e in result.events]
        self.assertIn("listing_updated", kinds)
        self.assertNotIn("price_drop", kinds)
        row = await self.listing("21327")
        self.assertEqual((float(row["price"]), row["currency"]), (1_950_000, "ARS"))

    async def test_a_new_listing_with_an_unreadable_price_is_stored_without_one(self):
        result = await ingest([fb("30", "Ford ecosport porton trasero", 600_000)], geocode=None)
        self.assertEqual((result.new, result.not_vehicle), (1, 0))
        row = await self.listing("30")
        self.assertEqual((row["price"], row["currency"], row["price_usd"], row["price_published"]),
                         (None, None, None, None))
        self.assertEqual((row["price_partial"], row["price_partial_reason"]),
                         (True, "precio de Facebook no interpretable: $ 600.000"))
        self.assertEqual(row["attributes"]["_currency_read"]["amount"], 600_000)
        self.assertNotIn("moneda", row["attributes"])

    async def test_a_stored_listing_read_with_an_unreadable_price_then_a_credible_one(self):
        # 21327 as stored before #73 (USD 990.000, attributes.moneda ARS).
        await self.store("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "USD", moneda="ARS")
        result = await ingest([fb("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 990_000)], geocode=None)
        self.assertNotIn("price_drop", [e.kind for e in result.events])
        row = await self.listing("21327")
        self.assertEqual((row["price"], row["currency"], row["price_usd"], row["price_partial"]),
                         (None, None, None, True))
        self.assertNotIn("moneda", row["attributes"])
        # The same card again: nothing changes.
        again = await ingest([fb("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 990_000)], geocode=None)
        self.assertEqual((again.updated, again.events), (0, []))
        # The seller writes a credible price: it stands, unflagged, and is no price drop.
        result = await ingest([fb("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 9_900)], geocode=None)
        kinds = [e.kind for e in result.events]
        self.assertIn("listing_updated", kinds)
        self.assertNotIn("price_drop", kinds)
        row = await self.listing("21327")
        self.assertEqual((float(row["price"]), row["currency"], float(row["price_usd"]), row["price_partial"],
                          row["price_partial_reason"], row["attributes"]["moneda"]),
                         (9_900, "USD", 9_900, False, None, "USD"))
        self.assertNotIn("_currency_read", row["attributes"])
        # ... and a lower one afterwards is a real drop again.
        result = await ingest([fb("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 9_000)], geocode=None)
        self.assertIn("price_drop", [e.kind for e in result.events])

    async def test_an_unreadable_card_over_a_credible_price_is_no_drop(self):
        await self.store("8", "Ford ecosport porton trasero", 9_500, "USD")
        result = await ingest([fb("8", "Ford ecosport porton trasero", 600_000)], geocode=None)
        self.assertNotIn("price_drop", [e.kind for e in result.events])
        row = await self.listing("8")
        self.assertEqual((row["price"], row["price_partial"]), (None, True))

    async def test_a_real_price_drop_is_still_one(self):
        await self.store("8", "FORD ECOSPORT 1.4 XLS 2008", 10_000, "USD", year=2008, km=150_000)
        result = await ingest([fb("8", "FORD ECOSPORT 1.4 XLS 2008", 8_000, anio=2008, km=150_000)],
                              geocode=None)
        self.assertIn("price_drop", [e.kind for e in result.events])

    async def test_an_enriched_car_read_again_by_card_is_not_ended(self):
        # The card has neither description nor mileage; the stored listing does.
        lid = await self.store("9", "Frente impecable Peugeot 206 XT", 5_000, "USD", make="Peugeot",
                               model="206", year=2010)
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET description = 'Vendo mi auto, titular, VTV al día', "
                             "       enriched_at = now() WHERE id = %s", (lid,))
        await self.match(lid)
        result = await ingest([fb("9", "Frente impecable Peugeot 206 XT", 5_000, anio=2010)], geocode=None)
        self.assertEqual(result.not_vehicle, 0)
        row = await self.listing("9")
        self.assertEqual((row["status"], row["price_partial"]), ("active", False))
        self.assertNotIn("_not_vehicle", row["attributes"])
        self.assertEqual(len(await self.rows("SELECT * FROM matches")), 1)

    async def test_a_stored_part_leaves_the_count_after_expiry(self):
        lid = await self.store("1", "Butacas Ford Ecosport", 350_000, "USD")
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Ecosport",
                                      filters={"marcas": ["Ford"], "modelos": ["EcoSport"]})
        async with db.connection() as cx:
            await cx.execute("INSERT INTO expired_search_matches (search_profile_id, listing_id, access_ended_at, "
                             "  level) VALUES (%s, %s, now() - interval '8 days', 'good')", (aid, lid))
        await ingest([fb("1", "Butacas Ford Ecosport", 350_000)], geocode=None)
        self.assertEqual(await self.rows("SELECT * FROM expired_search_matches"), [])


@requires_db
class RepairToolTests(Case):
    async def seed(self) -> dict[str, int]:
        ids = {
            "part": await self.store("1", "Butacas Ford Ecosport", 350_000, "USD"),
            "part_gone": await self.store("2", "Paragolpe trasero de Ford Ecosport", 100_000, "USD"),
            "car_usd": await self.store("3", "FORD ECOSPORT 1.4 XLS 2008", 6_400, "USD", year=2008, km=150_000),
            "car_ars": await self.store("4", "FORD ECOSPORT XLS 1.6 GNC FULL", 1_990_000, "USD", moneda="ARS"),
            "car_no_price": await self.store("5", "2027 Volkswagen Polo", 285_000, "USD",
                                             make="Volkswagen", model="Polo"),
            "21327": await self.store("21327", "FORD ECOSPORT XLS 1.6 GNC FULL", 990_000, "USD", moneda="ARS"),
            "porton": await self.store("12", "Ford ecosport porton trasero", 600_000, "USD"),
            "retiralo": await self.store("13", "FORD ECOSPORT 1.4 XLS 2008 ‼️RETÍRALO CON $900.000 Y CUOTAS FIJAS‼️",
                                         900_000, "USD", year=2008),
            # Left without a price by #73's ingest, not flagged, still matching.
            "legacy": await self.store("14", "OPORTUNIDAD TAPA DE CILINDROS FORD 1.6", None, None),
            "moneda": await self.store("6", "Ford Ecosport 2.0 4x2 XLT Plus", 10_000, "USD", moneda="ARS"),
            "porsche": await self.store("7", "Porsche 911 Carrera S", 180_000, "USD",
                                        make="Porsche", model="911"),
            "bmw": await self.store("10", "BMW X5 xDrive40i M Sport", 130_000, "USD", make="BMW", model="X5"),
            "explicit": await self.store("11", "Ford Ecosport Titanium", 130_000, "USD"),
        }
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET attributes = attributes || '{\"_price_sign\": \"US$\"}' "
                             " WHERE id = %s", (ids["explicit"],))
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (ids["part_gone"],))
            await cx.execute("UPDATE listings SET attributes = attributes || %s WHERE id = %s",
                             (db_json({"_currency_read": {"amount": 220_000, "currency": "USD", "as": None}}),
                              ids["legacy"]))
        for key in ("part", "porton", "retiralo", "legacy", "car_usd"):
            await self.match(ids[key])
        return ids

    async def test_dry_run_counts_and_writes_nothing(self):
        await self.seed()
        before = await self.rows("SELECT * FROM listings ORDER BY id")
        p = await repair_facebook.repair(write=False, sources=["facebook"])
        self.assertEqual(dict(p.counts), {
            ("facebook", repair_facebook.PART): 1,              # the gone one is left alone
            ("facebook", repair_facebook.PART_MATCHES): 1,
            ("facebook", repair_facebook.TO_ARS): 1,
            ("facebook", repair_facebook.DOUBTFUL): 5,          # Polo, 21327, portón, retiralo, legacy
            ("facebook", repair_facebook.DOUBTFUL_MATCHES): 3,
            ("facebook", repair_facebook.MONEDA): 1,
        })
        self.assertIn("Butacas", p.examples[("facebook", repair_facebook.PART)][0])
        doubtful = "\n".join(p.examples[("facebook", repair_facebook.DOUBTFUL)])
        self.assertIn("«Ford ecosport porton trasero» USD 600.000 leído -> sin precio "
                      "(precio de Facebook no interpretable: $ 600.000; 1 matches)", doubtful)
        report = "\n".join(repair_facebook.report(p, write=False))
        self.assertIn(repair_facebook.DOUBTFUL, report)
        self.assertEqual(await self.rows("SELECT * FROM listings ORDER BY id"), before)
        self.assertEqual(len(await self.rows("SELECT * FROM matches")), 5)
        self.assertEqual(await self.rows("SELECT * FROM fx_rates"), [])
        self.assertIn("simulación", repair_facebook.report(p, write=False)[-1])

    async def test_write_applies_and_a_second_run_finds_nothing(self):
        ids = await self.seed()
        p = await repair_facebook.repair(write=True, sources=["facebook"])
        self.assertEqual(p.counts[("*", repair_facebook.DELETED)], 3)

        part = await self.listing("1")
        self.assertEqual((part["status"], part["price_partial"]), ("gone", True))
        self.assertEqual(part["attributes"]["_not_vehicle"]["reason"], "título: «butacas»")
        # Only the dollar car keeps its match; nobody was notified.
        self.assertEqual([r["listing_id"] for r in await self.rows("SELECT listing_id FROM matches")],
                         [ids["car_usd"]])
        self.assertEqual(await self.rows("SELECT * FROM notifications"), [])
        self.assertEqual((await self.listing("2"))["attributes"].get("_not_vehicle"), None)

        car = await self.listing("4")
        self.assertEqual((float(car["price"]), car["currency"], float(car["price_published"]),
                          car["price_published_currency"], car["attributes"]["moneda"]),
                         (1_990_000, "ARS", 1_990_000, "ARS", "ARS"))
        self.assertAlmostEqual(float(car["price_usd"]), 1_990_000 / TEST_FX_RATE)
        self.assertEqual(car["attributes"]["_currency_read"]["currency"], "USD")

        for external_id, amount in (("5", "285.000"), ("21327", "990.000"), ("12", "600.000"),
                                    ("13", "900.000"), ("14", "220.000")):
            row = await self.listing(external_id)
            self.assertEqual((row["price"], row["currency"], row["price_usd"], row["price_published"],
                              row["price_published_currency"], row["status"]),
                             (None, None, None, None, None, "active"), external_id)
            self.assertEqual((row["price_partial"], row["price_partial_reason"]),
                             (True, f"precio de Facebook no interpretable: $ {amount}"), external_id)
            self.assertNotIn("moneda", row["attributes"], external_id)
            self.assertEqual(row["attributes"]["_currency_read"]["as"], None, external_id)

        self.assertEqual((await self.listing("6"))["attributes"]["moneda"], "USD")
        for untouched in ("3", "7", "10", "11"):
            row = await self.listing(untouched)
            self.assertEqual((row["currency"], row["attributes"]["moneda"]), ("USD", "USD"), untouched)
        self.assertEqual(ids["car_usd"], (await self.listing("3"))["id"])

        again = await repair_facebook.repair(write=False, sources=["facebook"])
        self.assertEqual(dict(again.counts), {})
        self.assertEqual((await repair_facebook.repair(write=True, sources=["facebook"])).counts, {})
        self.assertEqual(await self.rows("SELECT * FROM notifications"), [])

    async def test_a_repaired_listing_read_again_keeps_its_flag_then_clears_it(self):
        await self.seed()
        await repair_facebook.repair(write=True, sources=["facebook"])
        result = await ingest([fb("12", "Ford ecosport porton trasero", 600_000)], geocode=None)
        self.assertEqual((result.updated, result.events), (0, []))
        result = await ingest([fb("12", "Ford ecosport porton trasero", 7_500)], geocode=None)
        self.assertNotIn("price_drop", [e.kind for e in result.events])
        row = await self.listing("12")
        self.assertEqual((float(row["price"]), row["currency"], row["price_partial"]), (7_500, "USD", False))

    async def test_a_peso_reading_of_73_is_left_without_a_price(self):
        # #73's crawl stored «Ford ecosport porton trasero» as ARS 600.000 (a
        # car at ~USD 430) and the 1.990.000 one as ARS: only the first changes.
        porton = await self.store("12", "Ford ecosport porton trasero", 600_000, "ARS")
        ars = await self.store("4", "FORD ECOSPORT XLS 1.6 GNC FULL", 1_990_000, "ARS")
        bmw = await self.store("10", "BMW X5 xDrive40i M Sport", 600_000, "ARS", make="BMW", model="X5")
        async with db.connection() as cx:
            for lid, amount in ((porton, 600_000), (ars, 1_990_000), (bmw, 600_000)):
                await cx.execute("UPDATE listings SET attributes = attributes || %s WHERE id = %s",
                                 (db_json({"_currency_read": {"amount": amount, "currency": "USD", "as": "ARS"}}),
                                  lid))
        await self.match(porton)
        p = await repair_facebook.repair(write=False, sources=["facebook"])
        self.assertEqual(dict(p.counts), {("facebook", repair_facebook.DOUBTFUL): 1,
                                          ("facebook", repair_facebook.DOUBTFUL_MATCHES): 1})
        p = await repair_facebook.repair(write=True, sources=["facebook"])
        self.assertEqual(p.counts[("*", repair_facebook.DELETED)], 1)
        row = await self.listing("12")
        self.assertEqual((row["price"], row["currency"], row["price_usd"], row["price_partial"]),
                         (None, None, None, True))
        self.assertEqual(row["attributes"]["_currency_read"]["as"], None)
        self.assertEqual((float((await self.listing("4"))["price"]), (await self.listing("4"))["currency"]),
                         (1_990_000, "ARS"))
        self.assertEqual((await self.listing("10"))["currency"], "ARS")
        self.assertEqual(await self.rows("SELECT * FROM matches"), [])
        self.assertEqual(await self.rows("SELECT * FROM notifications"), [])
        self.assertEqual(dict((await repair_facebook.repair(write=True, sources=["facebook"])).counts), {})

    async def test_the_matches_of_a_listing_the_crawl_flagged_are_deleted(self):
        # The crawl flags it; its match would stay until the nightly re-score.
        lid = await self.store("12", "Ford ecosport porton trasero", 9_500, "USD")
        await self.match(lid)
        await ingest([fb("12", "Ford ecosport porton trasero", 600_000)], geocode=None)
        self.assertEqual(((await self.listing("12"))["price_partial"], len(await self.rows("SELECT * FROM matches"))),
                         (True, 1))
        p = await repair_facebook.repair(write=False, sources=["facebook"])
        self.assertEqual(dict(p.counts), {("facebook", repair_facebook.DOUBTFUL_MATCHES): 1})
        self.assertEqual(len(await self.rows("SELECT * FROM matches")), 1)
        p = await repair_facebook.repair(write=True, sources=["facebook"])
        self.assertEqual(p.counts[("*", repair_facebook.DELETED)], 1)
        self.assertEqual(await self.rows("SELECT * FROM matches"), [])
        self.assertEqual(await self.rows("SELECT * FROM notifications"), [])
        self.assertEqual(dict((await repair_facebook.repair(write=False, sources=["facebook"])).counts), {})

    async def test_a_flagged_listing_whose_detail_shows_no_price_stays_flagged(self):
        await ingest([fb("30", "Ford ecosport porton trasero", 600_000)], geocode=None)
        result = await ingest([fb("30", "Ford ecosport porton trasero", None, None,
                                  descripcion="Portón trasero completo")], geocode=None, detail=True)
        self.assertNotIn("price_drop", [e.kind for e in result.events])
        row = await self.listing("30")
        self.assertEqual((row["price"], row["price_partial"], row["price_partial_reason"]),
                         (None, True, "precio de Facebook no interpretable: $ 600.000"))

    async def test_only_the_named_sources(self):
        await self.seed()
        p = await repair_facebook.repair(write=False, sources=["mercadolibre"])
        self.assertEqual(dict(p.counts), {})
