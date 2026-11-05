"""public.missed_car: the car the 2.5 email shows has to be the one asked for
(supabase/migrations/20261210120000_missed_car_fits_search.sql). The count
(found, below) and the email around it are in test_lifecycle_emails_postgres.py."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

import db
from pgcase import PostgresTestCase, requires_db

pytestmark = [pytest.mark.db, requires_db]

END = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
FILTERS = {"make": "Ford", "model": "Fiesta", "year_min": 2014, "year_max": 2017, "km_max": 120000,
           "price_max": 15000, "currency": "USD", "trims": ["Titanium"]}
FIESTA = {"make": "Ford", "model": "Fiesta", "trim": "Titanium", "year": 2016, "mileage_km": 90000,
          "price": 12000, "currency": "USD", "price_usd": 12000, "title": "Ford Fiesta 1.6 Titanium"}


class MissedCarTests(PostgresTestCase):
    async def rows(self, sql: str, *params) -> list[dict]:
        async with db.connection() as cx:
            cursor = await cx.execute(sql, params)
            return await cursor.fetchall() if cursor.description else []

    async def search(self, filters: dict, **place) -> int:
        [user] = await self.rows(
            "INSERT INTO auth.users (instance_id, id, aud, role, email, created_at, updated_at) "
            "VALUES ('00000000-0000-0000-0000-000000000000', gen_random_uuid(), 'authenticated', "
            "        'authenticated', %s, now(), now()) RETURNING id", f"{uuid4()}@automotive.test")
        async with db.connection() as cx:
            await cx.execute("SET LOCAL session_replication_role = replica")
            [row] = await (await cx.execute(
                "INSERT INTO search_profiles (user_id, name, filters, enabled, origin_lat, origin_lon, radius_km) "
                "VALUES (%s, 'Fiesta', %s, true, %s, %s, %s) RETURNING id",
                (user["id"], Jsonb(filters), place.get("lat"), place.get("lon"), place.get("radius")))).fetchall()
        return row["id"]

    async def counted(self, profile: int, *, level: str = "high", diff: float | None = 15, **fields) -> int:
        """A listing counted for the search after END, FIESTA unless `fields` say otherwise."""
        ref = uuid4().hex[:10]
        listing = {**FIESTA, **fields}
        cols = ", ".join(listing)
        [row] = await self.rows(
            f"INSERT INTO listings (source, external_id, url, {cols}) VALUES ('mercadolibre', %s, %s, "
            f"{', '.join(['%s'] * len(listing))}) RETURNING id",
            ref, f"https://example.test/{ref}", *listing.values())
        await self.rows("INSERT INTO expired_search_matches (search_profile_id, listing_id, access_ended_at, level, diff_pct) "
                        "VALUES (%s, %s, %s, %s, %s)", profile, row["id"], END, level, diff)
        return row["id"]

    async def shown(self, profile: int) -> int | None:
        [row] = await self.rows("SELECT missed_car(%s, %s) AS car", profile, END)
        return (row["car"] or {}).get("listing_id")

    async def test_a_car_that_fits_the_search_is_shown(self):
        profile = await self.search(FILTERS)
        listing = await self.counted(profile)
        self.assertEqual(await self.shown(profile), listing)

    async def test_bounds_the_search_set_need_a_known_value_inside_them(self):
        cases = {"year out": {"year": 2012}, "no year": {"year": None}, "km over": {"mileage_km": 130000},
                 "no km": {"mileage_km": None}, "over budget": {"price": 16000, "price_usd": 16000},
                 "other trim": {"trim": "SE"}, "other model": {"model": "Focus"}}
        for name, fields in cases.items():
            with self.subTest(name):
                profile = await self.search(FILTERS)
                await self.counted(profile, **fields)
                self.assertIsNone(await self.shown(profile))

    async def test_a_year_is_needed_even_without_a_year_range(self):
        profile = await self.search({"make": "Ford", "model": "Fiesta"})
        await self.counted(profile, year=None)
        self.assertIsNone(await self.shown(profile))

    async def test_the_trim_can_come_from_the_title(self):
        profile = await self.search(FILTERS)
        listing = await self.counted(profile, trim=None, title="2016 Ford fiesta titanium 1.6")
        self.assertEqual(await self.shown(profile), listing)
        other = await self.search(FILTERS)
        await self.counted(other, trim=None, title="2016 Ford fiesta 1.6")
        self.assertIsNone(await self.shown(other))

    async def test_only_a_believable_gap_under_comparables(self):
        for diff, level, shown in ((4, "high", False), (36, "high", False), (-10, "good", False),
                                   (None, "good", False), (None, "high", True), (35, "good", True)):
            with self.subTest(diff=diff, level=level):
                profile = await self.search(FILTERS)
                listing = await self.counted(profile, diff=diff, level=level)
                self.assertEqual(await self.shown(profile), listing if shown else None)

    async def test_the_best_of_the_cars_that_fit(self):
        profile = await self.search(FILTERS)
        await self.counted(profile, diff=10)
        best = await self.counted(profile, diff=20)
        await self.counted(profile, diff=30, mileage_km=150000)          # better gap, but out of the search
        self.assertEqual(await self.shown(profile), best)

    async def test_inside_one_of_the_search_s_zones(self):
        # Rosario, 30 km, plus Córdoba as an extra place.
        rosario = {"lat": -32.9468, "lon": -60.6393, "radius": 30}
        filters = {**FILTERS, "extra_locations": [{"lat": -31.4201, "lon": -64.1888, "radius_km": 20}]}
        cases = (("in Rosario", -32.95, -60.65, True), ("in Córdoba", -31.42, -64.19, True),
                 ("in Mendoza", -32.89, -68.83, False), ("no coordinates", None, None, False))
        for name, lat, lon, shown in cases:
            with self.subTest(name):
                profile = await self.search(filters, **rosario)
                listing = await self.counted(profile, lat=lat, lon=lon)
                self.assertEqual(await self.shown(profile), listing if shown else None)
