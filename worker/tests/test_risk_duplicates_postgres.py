"""PAR-02 resto against the local Supabase Postgres
(docs/superpowers/specs/2026-11-02-par02-resto-design.md): the duplicate job
writes listing_duplicates, is idempotent, dry-runs, forgets gone listings,
re-scores only what changed, keeps the data level in shadow; the matches carry
the new flags; the photo budget is atomic. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest -m db
"""
from __future__ import annotations

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from db.repos import duplicates as repo
from db.repos import listings as listings_repo
from pgcase import PostgresTestCase, requires_db
from pipeline import rematch
from pipeline.risk_duplicates import detect_all, detect_for
from pipeline.seller_classification import classify_sellers
from tools import risk_duplicates as tool

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866
H1 = "ac53862cd38c73d3"
H2 = "883ce1877cc17dc5"
ROSARIO = ("82", "Rosario", "locality", -32.95, -60.66)
FUNES = ("82", "Rosario", "locality", -32.92, -60.81)


class DuplicatesCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._n = 0
        async with db.connection() as cx:
            row = await (await cx.execute("SELECT value FROM app_config WHERE key = 'risk'")).fetchone()
        self._saved = row["value"] if row else None
        listings_repo._has_duplicates = None

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            if self._saved is None:
                await cx.execute("DELETE FROM app_config WHERE key = 'risk'")
            else:
                await cx.execute("INSERT INTO app_config (key, value) VALUES ('risk', %s) "
                                 "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (Jsonb(self._saved),))
            await cx.execute("DELETE FROM photo_hash_runs")
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def signals(self, **modes) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = jsonb_set(value, '{signals}', "
                             "  coalesce(value -> 'signals', '{}') || %s) WHERE key = 'risk'", (Jsonb(modes),))
        app_config.clear_config_cache()

    async def listing(self, source="mercadolibre", *, hashes=None, zone=None, **kw) -> int:
        self._n += 1
        row = dict(source=source, external_id=f"d{self._n}", url=f"https://example.test/{source}/d{self._n}",
                   title="Ford Fiesta Titanium", make="Ford", model="Fiesta", trim="Titanium", year=2017,
                   price=12_000, currency="USD", price_usd=12_000, mileage_km=90_000, transmission="manual",
                   location_text="Rosario", seller_name=f"Vendedor {self._n}", seller_key=f"vendedor {self._n}",
                   seller_type="private", fingerprint=f"fp{self._n}", description="Ford Fiesta, único dueño, "
                   "services oficiales, distribución hecha, VTV al día. " * 4,
                   images=Jsonb([f"https://img.example.test/{self._n}.jpg"]))
        if hashes is not None:
            row["attributes"] = Jsonb({"_photo_hashes": {"v": 1, "urls": [], "hashes": hashes, "attempts": 1}})
        row.update(kw)
        cols = list(row)
        async with db.connection() as cx:
            r = await (await cx.execute(
                f"INSERT INTO listings ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                list(row.values()))).fetchone()
            if zone:
                await cx.execute("INSERT INTO listing_zones (listing_id, province_id, department, precision, lat, lon) "
                                 "VALUES (%s, %s, %s, %s, %s, %s)", (r["id"], *zone))
        return r["id"]

    async def pairs(self) -> dict[tuple[int, int], dict]:
        async with db.connection() as cx:
            rows = await (await cx.execute("SELECT * FROM listing_duplicates ORDER BY 1, 2")).fetchall()
        return {(r["listing_id"], r["other_id"]): r for r in rows}

    async def alert(self) -> int:
        f = {"marcas": ["Ford"], "modelos": ["Fiesta"], "sources": ["mercadolibre", "rosariogarage", "v6"]}
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Fiesta", filters=f)
        await rematch.run_pending()
        return aid

    async def flags(self, aid: int) -> dict[int, dict[str, dict]]:
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT listing_id, red_flags FROM matches WHERE search_profile_id = %s", (aid,))).fetchall()
        return {r["listing_id"]: {f["id"]: f for f in r["red_flags"]} for r in rows}


class DetectAllTests(DuplicatesCase):
    async def test_same_photos_in_two_sources_flag_both_and_link_each_other(self):
        a = await self.listing(hashes=[H1])
        b = await self.listing("rosariogarage", hashes=[H2, H1], mileage_km=91_000)
        await self.listing("v6", hashes=[H2], price_usd=8_000, price=8_000, model="Focus")   # another group
        aid = await self.alert()

        result = await detect_all("cli")

        pairs = await self.pairs()
        self.assertEqual(set(pairs), {(a, b), (b, a)})
        self.assertEqual({(p["kind"], p["shown"], p["photo_distance"]) for p in pairs.values()},
                         {("cross_source_photos", True, 0)})
        self.assertEqual(result["created"], {"cross_source_photos": 2})
        self.assertEqual(result["changed"], 2)
        self.assertGreaterEqual(result["rescored"], 2)
        flags = await self.flags(aid)
        self.assertEqual(flags[a]["cross_source_duplicate"]["link"],
                         {"listing_id": b, "url": f"https://example.test/rosariogarage/d{2}",
                          "source_name": "Rosario Garage", "kind": "cross_source_photos"})
        self.assertEqual(flags[b]["cross_source_duplicate"]["link"]["listing_id"], a)
        self.assertIn("(mismas fotos)", flags[a]["cross_source_duplicate"]["text"])

        async with db.connection() as cx:
            rows = await listings_repo.rows_for_scoring(cx, [a])
        self.assertEqual(rows[a]["risk_duplicates"][0]["other_id"], b)

        again = await detect_all("cli")
        self.assertEqual((again["created"], again["deleted"], again["changed"], again["rescored"]), ({}, {}, 0, 0))
        self.assertEqual(await self.pairs(), pairs, "idempotent")

    async def test_dry_run_writes_and_rescores_nothing(self):
        await self.listing(hashes=[H1])
        await self.listing("v6", hashes=[H1], price_usd=9_000, price=9_000)
        result = await detect_all("cli", dry_run=True, report=True)
        self.assertEqual(await self.pairs(), {})
        self.assertEqual((result["created"], result["rescored"]), ({"duplicate_photos": 2}, 0))
        self.assertEqual([p.kind for p in result["report"]["duplicate_photos"]], ["duplicate_photos"])

    async def test_a_gone_listing_drops_its_pairs_and_the_other_side_is_rescored(self):
        a = await self.listing(hashes=[H1])
        b = await self.listing("v6", hashes=[H1], price_usd=9_000, price=9_000)
        aid = await self.alert()
        await detect_all("cli")
        self.assertEqual((await self.flags(aid))[a]["duplicate_photos"]["severity"], "warning")

        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (b,))
        result = await detect_all("nightly")
        self.assertEqual(await self.pairs(), {})
        self.assertEqual(result["deleted"], {"duplicate_photos": 2})
        self.assertNotIn("duplicate_photos", (await self.flags(aid))[a])

    async def test_detect_for_rewrites_only_the_groups_of_those_listings(self):
        a = await self.listing(hashes=[H1])
        await self.listing("v6", hashes=[H1], price_usd=9_000, price=9_000)
        c = await self.listing(hashes=[H2], model="Focus")
        await self.listing("v6", hashes=[H2], model="Focus", price_usd=9_000, price=9_000)
        self.assertEqual(await detect_for([a]), 2)
        self.assertEqual({k for k in await self.pairs()} & {(c, c + 1)}, set())
        self.assertEqual(len(await self.pairs()), 2)

    async def test_the_data_level_starts_in_shadow_and_shows_when_turned_on(self):
        a = await self.listing(zone=ROSARIO)
        b = await self.listing("rosariogarage", zone=FUNES, mileage_km=91_500, price_usd=12_400, price=12_400)
        aid = await self.alert()
        await detect_all("cli")
        pairs = await self.pairs()
        self.assertEqual({(p["kind"], p["shown"]) for p in pairs.values()}, {("cross_source_data", False)})
        self.assertNotIn("cross_source_duplicate", (await self.flags(aid))[a])

        await self.signals(cross_source_data="on")
        result = await detect_all("cli")
        self.assertEqual(result["changed"], 2)
        self.assertEqual({p["shown"] for p in (await self.pairs()).values()}, {True})
        text = (await self.flags(aid))[b]["cross_source_duplicate"]["text"]
        self.assertIn("en MercadoLibre", text)
        self.assertIn("precio parecido", text)

        await self.signals(cross_source_data="off")
        await detect_all("cli")
        self.assertEqual(await self.pairs(), {})
        self.assertNotIn("cross_source_duplicate", (await self.flags(aid))[b])

    async def test_the_tool_prints_a_dry_run_report(self):
        await self.listing(hashes=[H1])
        await self.listing("v6", hashes=[H1], price_usd=9_000, price=9_000)
        result = await detect_all("cli", dry_run=True, report=True)
        ids = {i for pairs in result["report"].values() for p in pairs for i in (p.a, p.b)}
        async with db.connection() as cx:
            listings = await repo.describe(cx, ids)
        text = "\n".join(tool.summary_lines(result) + tool.report_lines(result, listings))
        self.assertIn("se crearían: duplicate_photos 2", text)
        self.assertIn("(simulación: no se escribió nada ni se re-puntuó)", text)
        self.assertIn("duplicate_photos (on): 1 pares de muestra", text)
        self.assertIn("https://example.test/v6/", text)
        self.assertEqual(await self.pairs(), {})


class PrivateManyListingsTests(DuplicatesCase):
    async def test_a_private_seller_with_six_cars_gets_the_flag_after_the_classification(self):
        ids = [await self.listing(seller_name="Juan Pérez", seller_key=None, mileage_km=50_000 + 1_000 * i)
               for i in range(6)]
        aid = await self.alert()
        await classify_sellers("cli")
        flags = await self.flags(aid)
        for lid in ids:
            self.assertEqual(flags[lid]["private_many_listings"]["text"],
                             "El vendedor tiene 6 publicaciones activas: conviene preguntar si es titular.")
        async with db.connection() as cx:
            row = await (await cx.execute("SELECT contact_questions FROM matches WHERE listing_id = %s",
                                          (ids[0],))).fetchone()
        self.assertTrue(any("titular" in q for q in row["contact_questions"]))


class PhotoBudgetTests(DuplicatesCase):
    async def test_the_daily_cap_counts_images_and_failed_runs(self):
        lid = await self.listing()
        first = await repo.reserve_photo_run(lid, 3, 5)
        self.assertIsNotNone(first)
        await repo.finish_photo_run(first, hashed=0, error="HTTP 404")
        self.assertIsNone(await repo.reserve_photo_run(lid, 3, 5), "3 + 3 > 5")
        self.assertIsNotNone(await repo.reserve_photo_run(lid, 2, 5))
        self.assertIsNone(await repo.reserve_photo_run(lid, 1, 0))

    async def test_saving_hashes_keeps_the_other_attributes_and_notifies_nothing(self):
        lid = await self.listing(attributes=Jsonb({"moneda": "USD"}))
        await repo.save_photo_hashes(lid, {"v": 1, "urls": ["u"], "hashes": [H1], "attempts": 1})
        async with db.connection() as cx:
            row = await (await cx.execute("SELECT attributes FROM listings WHERE id = %s", (lid,))).fetchone()
            snaps = await (await cx.execute("SELECT count(*) AS n FROM listing_snapshots")).fetchone()
        self.assertEqual(row["attributes"]["moneda"], "USD")
        self.assertEqual(row["attributes"]["_photo_hashes"]["hashes"], [H1])
        self.assertEqual(snaps["n"], 0)

    async def queue(self, **kw):
        args = dict(limit=50, skip_sources=["facebook"], km_tol_pct=3, price_tol_pct=5, version=1, max_attempts=2)
        return await repo.photo_hash_queue(**{**args, **kw})

    async def test_the_queue_brings_matched_listings_their_candidates_and_never_skipped_sources(self):
        a = await self.listing()
        b = await self.listing("rosariogarage", mileage_km=91_000)
        await self.listing("facebook", mileage_km=90_500)
        c = await self.listing("v6", mileage_km=150_000)             # out of tolerance: a photo candidate
        far = await self.listing("v6", year=2010)                    # another year: none
        await self.alert()
        async with db.connection() as cx:
            await cx.execute("DELETE FROM matches WHERE listing_id <> %s", (a,))
        rows = await self.queue()
        self.assertEqual([r["id"] for r in rows], [a, b, c], "matched, data candidate, photo candidate")
        self.assertNotIn(far, [r["id"] for r in rows])

    async def test_a_much_cheaper_copy_brings_the_original_into_the_queue(self):
        # Copied photos come with another price and year: the original is outside the data tolerances.
        original = await self.listing("rosariogarage", price=17_000, price_usd=17_000, year=2016)
        copy_ = await self.listing(price=12_000, price_usd=12_000)
        await self.alert()
        async with db.connection() as cx:
            await cx.execute("DELETE FROM matches WHERE listing_id <> %s", (copy_,))
        self.assertEqual([r["id"] for r in await self.queue()], [copy_, original])

    async def test_finished_listings_never_fill_the_queue(self):
        done = [await self.listing() for _ in range(3)]
        todo = await self.listing("rosariogarage")
        await self.alert()
        for lid in done:
            await repo.save_photo_hashes(lid, {"v": 1, "urls": [f"u{lid}"], "hashes": [H1], "attempts": 1})
        rows = await self.queue(limit=1)
        self.assertEqual([r["id"] for r in rows], [todo], "the hashed ones are skipped in SQL, not after the LIMIT")
        # Out of attempts: skipped too; with attempts left: back in.
        await repo.save_photo_hashes(todo, {"v": 1, "urls": ["u"], "hashes": [None], "attempts": 2})
        self.assertEqual(await self.queue(), [])
        self.assertEqual([r["id"] for r in await self.queue(max_attempts=3)], [todo])
        # Images changed: back in until the pass hashes it or marks it seen.
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET images = %s WHERE id = %s",
                             (Jsonb(["https://img.example.test/new.jpg"]), done[0]))
        [row] = await self.queue()
        self.assertEqual(row["id"], done[0])
        await repo.mark_photo_hashes_seen(done[0], row["photo_hashes"])
        self.assertEqual(await self.queue(), [])
        # Another version: back in.
        self.assertEqual(len(await self.queue(version=2)), 4)

    async def test_rows_for_scoring_carries_the_reason_of_a_duplicate(self):
        a = await self.listing(hashes=[H1])
        b = await self.listing(hashes=[H1], zone=("14", "Capital", "locality", -31.42, -64.18))
        async with db.connection() as cx:
            await cx.execute("INSERT INTO listing_zones (listing_id, province_id, department, precision, lat, lon) "
                             "VALUES (%s, %s, %s, %s, %s, %s)", (a, *ROSARIO))
        await detect_all("cli")
        pairs = await self.pairs()
        self.assertEqual({(p["kind"], p["evidence"]["reason"]) for p in pairs.values()},
                         {("duplicate_photos", "other_zone")})
        async with db.connection() as cx:
            rows = await listings_repo.rows_for_scoring(cx, [a])
        self.assertEqual((rows[a]["risk_duplicates"][0]["other_id"], rows[a]["risk_duplicates"][0]["reason"]),
                         (b, "other_zone"))
