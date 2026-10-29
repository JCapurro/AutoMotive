"""F-03 fase 0 against the local Supabase Postgres
(docs/superpowers/specs/2026-10-29-f03-market-stats-fase0-design.md): listing
zones, the weekly market_stats job and its retention.
Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest
"""
from __future__ import annotations

import pytest

import db
from pgcase import PostgresTestCase, requires_db
from pipeline.market_zones import sync_zones

pytestmark = [pytest.mark.db, requires_db]

SAN_ISIDRO = (-34.4708, -58.5286)
ROSARIO = (-32.9442, -60.6505)


class MarketCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._n = 0

    async def listing(self, **kw) -> int:
        """A listing row inserted directly; `*_days_ago` set its dates."""
        self._n += 1
        row = dict(source="mercadolibre", external_id=f"m{self._n}", url=f"https://example.test/m{self._n}",
                   title="Ford Fiesta", make="Ford", model="Fiesta", year=2018, price=11_000, currency="USD",
                   price_usd=11_000, mileage_km=100_000, location_text="San Isidro, Buenos Aires",
                   lat=SAN_ISIDRO[0], lon=SAN_ISIDRO[1])
        row.update(kw)
        seen = row.pop("last_seen_days_ago", 0)
        first = row.pop("first_seen_days_ago", max(seen, 0) + 10)
        cols = list(row)
        async with db.connection() as cx:
            r = await (await cx.execute(
                f"INSERT INTO listings ({', '.join(cols)}, first_seen_at, last_seen_at) "
                f"VALUES ({', '.join(['%s'] * len(cols))}, now() - make_interval(secs => %s), "
                f"        now() - make_interval(secs => %s)) RETURNING id",
                [*row.values(), first * 86400, seen * 86400])).fetchone()
        return r["id"]

    async def zone(self, listing_id: int) -> dict | None:
        async with db.connection() as cx:
            return await (await cx.execute("SELECT * FROM listing_zones WHERE listing_id = %s",
                                            (listing_id,))).fetchone()


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
