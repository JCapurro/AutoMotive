"""Agencias against Postgres: the Mercado Libre profile an agency gave us, read whole
by the dealers tick (pipeline/dealers.py read_profiles, migration 20270105120000).

Needs a database with the dealer migrations through 20270105120000 applied; skipped otherwise.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

import db
from collectors import mercadolibre as ml
from collectors.base import CollectorBlocked, Listing
from db.repos import dealers as dealers_repo
from pgcase import requires_db
from pipeline import dealers as pipeline
from test_dealers_postgres import PANEL_ONLY, DealersCase

pytestmark = [pytest.mark.db, requires_db]

PROFILE = "https://vehiculos.mercadolibre.com.ar/_CustId_145347970"
NAME = "BUSTELO AUTOMOTORES"
KEY = "bustelo automotores"


def car(ext: str, title: str = "Ford Fiesta 2017 1.6 Titanium", **kw) -> Listing:
    values = dict(precio=15_000_000.0, moneda="ARS", anio=2017, km=112_000, vendedor_nombre=NAME)
    values.update(kw)
    return Listing("mercadolibre", ext, title, f"https://auto.mercadolibre.com.ar/{ext}", **values)


class ProfileCase(DealersCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        dealers_repo._profiles_ready = None
        if not await dealers_repo.profiles_ready():
            self.skipTest("migration 20270105120000_dealer_source_profile.sql not applied")
        await self.program(PANEL_ONLY)
        self.reads: list[str] = []

    async def source(self, dealer_id: int, *, status: str = "approved", seller_key: str | None = KEY,
                     url: str | None = PROFILE) -> int:
        [r] = await self.rows(
            "INSERT INTO dealer_sources (dealer_id, source, profile_url, seller_key, status, approved_at) "
            "VALUES (%s, 'mercadolibre', %s, %s, %s, CASE WHEN %s = 'approved' THEN now() END) RETURNING id",
            dealer_id, url, seller_key, status, status)
        return r["id"]

    async def source_row(self, source_id: int) -> dict:
        [r] = await self.rows("SELECT * FROM dealer_sources WHERE id = %s", source_id)
        return r

    async def tick_with(self, profile: ml.SellerProfile | BaseException):
        async def seller_profile(_self, cust_id):
            self.reads.append(cust_id)
            if isinstance(profile, BaseException):
                raise profile
            return profile

        with patch.object(ml.MercadoLibreScraper, "seller_profile", seller_profile):
            return await self.tick()

    async def ml_listings(self) -> list[dict]:
        return await self.rows("SELECT external_id, status, seller_key, dealer_id FROM listings "
                               " WHERE source = 'mercadolibre' ORDER BY external_id")


class ProfileReadTests(ProfileCase):
    async def test_an_approved_profile_becomes_the_agencys_stock_in_one_tick(self):
        d = await self.dealer()
        s = await self.source(d)
        tick = await self.tick_with(ml.SellerProfile(NAME, [car("MLA1"), car("MLA2", km=90_000), car("MLA3", anio=2018)]))
        self.assertEqual(self.reads, ["145347970"])
        self.assertEqual([(r["external_id"], r["status"], r["seller_key"], r["dealer_id"]) for r in await self.ml_listings()],
                         [("MLA1", "active", KEY, d), ("MLA2", "active", KEY, d), ("MLA3", "active", KEY, d)])
        items = await self.rows("SELECT origin, sync_state FROM dealer_stock_items WHERE dealer_id = %s", d)
        self.assertEqual([(i["origin"], i["sync_state"]) for i in items], [("sync", "linked")] * 3)
        self.assertEqual((tick.profile_cars, tick.linked), (3, 3))
        row = await self.source_row(s)
        self.assertEqual((row["profile_count"], row["profile_error"], row["seller_key"]), (3, None, KEY))
        self.assertIsNotNone(row["profile_read_at"])

    async def test_it_is_not_read_again_until_it_is_due(self):
        d = await self.dealer()
        s = await self.source(d)
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual(len(self.reads), 1)
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_sources SET profile_read_at = now() - interval '7 hours' WHERE id = %s", (s,))
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual(len(self.reads), 2)

    async def test_a_car_a_complete_read_no_longer_finds_is_over(self):
        d = await self.dealer()
        s = await self.source(d)
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1"), car("MLA2", km=90_000)]))
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_sources SET profile_read_at = now() - interval '7 hours' WHERE id = %s", (s,))
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '7 hours' WHERE source = 'mercadolibre'")
        # An incomplete read ends nothing...
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")], complete=False, reason="mercadolibre: pagination repeated a page"))
        self.assertEqual([r["status"] for r in await self.ml_listings()], ["active", "active"])
        self.assertEqual((await self.source_row(s))["profile_error"], "mercadolibre: pagination repeated a page")
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_sources SET profile_read_at = now() - interval '7 hours' WHERE id = %s", (s,))
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '7 hours' WHERE external_id = 'MLA2'")
        # ...a complete one ends the car that is gone from the profile, and its item is archived.
        tick = await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual([(r["external_id"], r["status"]) for r in await self.ml_listings()], [("MLA1", "active"), ("MLA2", "gone")])
        self.assertGreaterEqual(tick.gone, 1)
        self.assertIsNone((await self.source_row(s))["profile_error"])

    async def test_an_empty_read_ends_nothing(self):
        d = await self.dealer()
        s = await self.source(d)
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_sources SET profile_read_at = now() - interval '7 hours' WHERE id = %s", (s,))
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '7 hours' WHERE source = 'mercadolibre'")
        await self.tick_with(ml.SellerProfile(NAME, []))
        self.assertEqual([r["status"] for r in await self.ml_listings()], ["active"])
        self.assertEqual((await self.source_row(s))["profile_count"], 0)

    async def test_a_pending_profile_is_read_once_and_suggests_the_seller_without_linking(self):
        d = await self.dealer()
        s = await self.source(d, status="pending", seller_key=None)
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        row = await self.source_row(s)
        self.assertEqual((row["status"], row["seller_key"], row["seller_name_hint"], row["profile_count"]),
                         ("pending", KEY, NAME, 1))
        self.assertEqual([(r["seller_key"], r["dealer_id"]) for r in await self.ml_listings()], [(KEY, None)])
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_sources SET profile_read_at = now() - interval '30 days' WHERE id = %s", (s,))
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual(len(self.reads), 1)        # pending: only the first read
        # Juan approves the suggestion: the next tick links what was read.
        async with db.connection() as cx:
            await cx.execute("UPDATE dealer_sources SET status = 'approved', approved_at = now() WHERE id = %s", (s,))
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual([r["dealer_id"] for r in await self.ml_listings()], [d])

    async def test_a_profile_of_another_seller_than_the_approved_one_is_never_linked(self):
        d = await self.dealer()
        s = await self.source(d, seller_key="otra agencia")
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual([(r["seller_key"], r["dealer_id"]) for r in await self.ml_listings()], [(KEY, None)])
        row = await self.source_row(s)
        self.assertEqual((row["profile_error"], row["seller_key"]), ("seller_mismatch", "otra agencia"))

    async def test_a_blocked_read_is_recorded_and_waits_for_its_turn(self):
        d = await self.dealer()
        s = await self.source(d)
        await self.tick_with(CollectorBlocked("mercadolibre seller profile: login wall"))
        row = await self.source_row(s)
        self.assertEqual((row["profile_error"], row["profile_count"]), ("read_failed:CollectorBlocked", None))
        self.assertIsNotNone(row["profile_read_at"])
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual(len(self.reads), 1)

    async def test_links_that_are_not_a_profile_a_rejected_source_and_a_paused_agency_are_not_read(self):
        d = await self.dealer()
        await self.source(d, url="https://www.mercadolibre.com.ar/perfil/BUSTELO", seller_key="x1")
        await self.source(d, status="rejected", seller_key=None)
        paused = await self.dealer(name="Pausada", status="paused")
        await self.source(paused, seller_key="x2")
        await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual(self.reads, [])

    async def test_with_the_reads_off_nothing_is_read(self):
        d = await self.dealer()
        await self.source(d)
        with patch.object(pipeline, "DEALER_PROFILE_HOURS", 0):
            await self.tick_with(ml.SellerProfile(NAME, [car("MLA1")]))
        self.assertEqual(self.reads, [])
