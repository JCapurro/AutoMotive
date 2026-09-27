from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import psycopg
import pytest

import db
from pgcase import TEST_DATABASE_URL, PostgresTestCase, requires_db
from tools.migrate_sqlite import Migration, load_emails

pytestmark = [pytest.mark.db, requires_db]

# The SQLite schema as the old db.py created it.
SQLITE_SCHEMA = """
CREATE TABLE alerts (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
    name TEXT NOT NULL, filters_json TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL, bootstrapped INTEGER NOT NULL DEFAULT 0, last_scraped_at INTEGER);
CREATE TABLE seen_listings (alert_id INTEGER NOT NULL, source TEXT NOT NULL,
    listing_id TEXT NOT NULL, first_seen INTEGER NOT NULL, PRIMARY KEY (alert_id, source, listing_id));
CREATE TABLE listings_cache (source TEXT NOT NULL, listing_id TEXT NOT NULL, marca TEXT, modelo TEXT,
    anio INTEGER, km INTEGER, precio REAL, moneda TEXT, titulo TEXT, url TEXT, ubicacion TEXT,
    combustible TEXT, transmision TEXT, vendedor TEXT, price_partial INTEGER NOT NULL DEFAULT 0,
    price_partial_reason TEXT, scraped_at INTEGER NOT NULL, PRIMARY KEY (source, listing_id));
CREATE TABLE geocode_cache (query TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL,
    source TEXT NOT NULL, updated_at INTEGER NOT NULL, not_found INTEGER NOT NULL DEFAULT 0);
"""

T0 = 1_788_000_000


def _make_sqlite(path: Path) -> None:
    cx = sqlite3.connect(path)
    cx.executescript(SQLITE_SCHEMA)
    cx.executemany("INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?)", [
        (1, 111, 111, "Fiesta y Mondeo", json.dumps(
            {"marcas": ["Ford"], "modelos": ["Fiesta", "Mondeo"], "descuento_pct": 15}), 1, T0, 1, T0 + 60),
        (2, 222, 222, "Gol", json.dumps({"marcas": ["VW"], "modelos": ["Gol Trend"]}), 0, T0, 0, None),
    ])
    cx.executemany("INSERT INTO listings_cache (source, listing_id, marca, modelo, anio, km, precio, "
                   "moneda, titulo, url, transmision, vendedor, scraped_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("mercadolibre", "MLA1", "ford", "fiesta", 2018, 90000, 11000, "USD", "Ford Fiesta", "u1",
         "Manual", "particular", T0),
        ("kavak", "K1", "ford", "fiesta", 2019, 80000, 13000000, "ARS", "Ford Fiesta SE", "u2",
         None, "concesionaria", T0),
        ("demotores", "D1", "ford", "ka", 2015, 1, 1, "USD", "Ford Ka", "u3", None, None, T0),
    ])
    cx.executemany("INSERT INTO seen_listings VALUES (?,?,?,?)", [
        (1, "mercadolibre", "MLA1", T0), (1, "kavak", "K1", T0), (1, "v6", "gone", T0),
        (99, "mercadolibre", "MLA1", T0),
    ])
    cx.execute("INSERT INTO geocode_cache VALUES ('munro', -34.52, -58.52, 'nominatim', ?, 0)", (T0,))
    cx.commit()
    cx.close()


class MigrateSqliteTests(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.sqlite = Path(self.tmp.name) / "automotive.db"
        _make_sqlite(self.sqlite)
        # 222 already has a web account with this email.
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
                "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
                "'authenticated', 'gol@automotive.test', now(), now())")

    async def asyncTearDown(self) -> None:
        self.tmp.cleanup()
        await super().asyncTearDown()

    async def _migrate(self, *, dry_run: bool = False) -> Migration:
        async with await psycopg.AsyncConnection.connect(TEST_DATABASE_URL,
                                                         row_factory=psycopg.rows.dict_row) as cx:
            m = Migration(str(self.sqlite), cx, emails={222: "gol@automotive.test"},
                          dry_run=dry_run, include_unknown=False, supabase_url=None, service_key=None)
            try:
                await m.run()
            finally:
                m.close()
            await (cx.rollback() if dry_run else cx.commit())
        return m

    async def _count(self, table: str) -> int:
        async with db.connection() as cx:
            return (await (await cx.execute(f"SELECT count(*) AS n FROM {table}")).fetchone())["n"]

    async def test_dry_run_reports_without_writing(self):
        m = await self._migrate(dry_run=True)

        self.assertEqual(m.stats["listings_inserted"], 2)
        self.assertEqual(await self._count("listings"), 0)
        self.assertEqual(await self._count("search_profiles"), 0)

    async def test_migrates_everything_once(self):
        m = await self._migrate()
        again = await self._migrate()

        self.assertEqual(m.stats["listings_inserted"], 2)
        self.assertEqual(m.stats["listings_skipped_unknown_source"], 1)
        self.assertEqual(m.stats["profiles_created"], 2)          # Fiesta + Gol Trend
        self.assertEqual(m.stats["profiles_skipped_not_in_catalog"], 1)   # Mondeo
        self.assertEqual(m.stats["matches_inserted"], 2)
        self.assertEqual(m.stats["seen_without_listing"], 1)
        self.assertEqual(m.stats["seen_of_deleted_alerts"], 1)
        self.assertEqual(m.stats["geocode_inserted"], 1)
        self.assertTrue(any("Mondeo" in n for n in m.notes))

        self.assertEqual(again.stats["listings_inserted"], 0)
        self.assertEqual(again.stats["profiles_created"], 0)
        self.assertEqual(again.stats["matches_inserted"], 0)
        self.assertEqual(again.stats["geocode_inserted"], 0)
        self.assertEqual(await self._count("listings"), 2)
        self.assertEqual(await self._count("listing_snapshots"), 2)
        self.assertEqual(await self._count("search_profiles"), 2)
        self.assertEqual(await self._count("matches"), 2)

        by_user = {a["user_id"]: a for a in await db.list_alerts()}
        fiesta, gol = by_user[111], by_user[222]
        self.assertEqual(fiesta["filters"]["modelos"], ["Fiesta"])
        self.assertEqual(fiesta["filters"]["descuento_pct"], 15)
        self.assertEqual((fiesta["active"], fiesta["bootstrapped"], fiesta["last_scraped_at"]),
                         (1, 1, T0 + 60))
        self.assertEqual(gol["filters"]["marcas"], ["Volkswagen"])
        self.assertEqual((gol["active"], gol["bootstrapped"]), (0, 0))
        # Already-seen listings are backfill: the bot won't alert them again.
        self.assertEqual(len(await db.filter_unseen(fiesta["id"], [
            {"source": "mercadolibre", "listing_id": "MLA1"}, {"source": "kavak", "listing_id": "K1"}])), 0)

        async with db.connection() as cx:
            gol_user = await (await cx.execute(
                "SELECT u.email, u.is_anonymous FROM profiles p JOIN auth.users u ON u.id = p.id "
                "WHERE p.telegram_user_id = 222")).fetchone()
            listing = await (await cx.execute(
                "SELECT first_seen_at, currency, seller_type FROM listings WHERE external_id = 'K1'")).fetchone()
        self.assertEqual(gol_user["email"], "gol@automotive.test")
        self.assertFalse(gol_user["is_anonymous"])
        self.assertEqual(int(listing["first_seen_at"].timestamp()), T0)
        self.assertEqual((listing["currency"], listing["seller_type"]), ("ARS", "dealer"))


class LoadEmailsTests(unittest.TestCase):
    def test_flags_and_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "emails.csv"
            csv_path.write_text("telegram_user_id,email\n111,a@x.com\n", encoding="utf-8")
            json_path = Path(tmp) / "emails.json"
            json_path.write_text('{"222": "b@x.com"}', encoding="utf-8")

            self.assertEqual(load_emails(["333=c@x.com"], str(csv_path)), {111: "a@x.com", 333: "c@x.com"})
            self.assertEqual(load_emails([], str(json_path)), {222: "b@x.com"})
        with self.assertRaises(SystemExit):
            load_emails(["nope"], None)


if __name__ == "__main__":
    unittest.main()
