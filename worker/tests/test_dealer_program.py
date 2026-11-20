"""Agencias (docs/superpowers/specs/2026-11-18-agencias-design.md §1, §2, §4.1-4.2):
the switch, the send gate, the label and the private-only filter. Pure."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from intelligence.config import DEFAULT_DEALER_PROGRAM, dealer_program
from intelligence.dealer import (DEALER_SOURCE, HIDDEN_REASONS, hidden_reason, is_dealer_listing, label,
                                 private_only)

NOW = datetime(2026, 11, 18, 15, 0, tzinfo=timezone.utc)
ON = dealer_program({"enabled": True, "channel_enabled": True, "manual_confirm_days": 7})
OFF = dealer_program(None)


def car(**kw) -> dict:
    row = {"id": 1, "source": DEALER_SOURCE, "dealer_id": 3, "dealer_status": "available",
           "dealer_confirmed_at": NOW - timedelta(days=1), "dealer_approved": True, "dealer_active": True,
           "dealer_name": "TT Autos"}
    row.update(kw)
    return row


class DealerProgramTests(unittest.TestCase):
    def test_defaults_are_off(self):
        self.assertEqual(DEFAULT_DEALER_PROGRAM, {"enabled": False, "channel_enabled": False,
                                                  "manual_confirm_days": 7, "demand_min_count": 3,
                                                  "alerts_enabled": False, "alerts_every_hours": 24,
                                                  "photo_import_enabled": False, "photo_import_daily_limit": 5})
        for raw in (None, {}, [], "x", 3):
            with self.subTest(raw=raw):
                self.assertEqual(dealer_program(raw), {**DEFAULT_DEALER_PROGRAM, "channel": False})

    def test_channel_needs_both_switches(self):
        self.assertFalse(dealer_program({"enabled": True})["channel"])
        self.assertFalse(dealer_program({"channel_enabled": True})["channel"])
        self.assertTrue(dealer_program({"enabled": True, "channel_enabled": True})["channel"])

    def test_bad_types_fall_back_key_by_key(self):
        p = dealer_program({"enabled": "true", "channel_enabled": 1, "manual_confirm_days": "10",
                            "demand_min_count": True})
        self.assertEqual(p, {**DEFAULT_DEALER_PROGRAM, "channel": False})

    def test_demand_min_count_is_never_under_three(self):
        for value, expected in ((1, 3), (2, 3), (3, 3), (4, 4), (50, 50), (51, 3), (3.5, 3), (5.0, 5), (-1, 3)):
            with self.subTest(value=value):
                self.assertEqual(dealer_program({"demand_min_count": value})["demand_min_count"], expected)

    def test_manual_confirm_days_bounds(self):
        for value, expected in ((0, 7), (1, 1), (60, 60), (61, 7), (14, 14), (7.5, 7), (float("nan"), 7)):
            with self.subTest(value=value):
                self.assertEqual(dealer_program({"manual_confirm_days": value})["manual_confirm_days"], expected)


class HiddenReasonTests(unittest.TestCase):
    """The nine cases of §2, in order (the twin of public.dealer_listing_hidden)."""

    def test_matrix(self):
        old = NOW - timedelta(days=8)
        cases = [
            ("1 ordinary listing", {"source": "mercadolibre", "dealer_id": None}, ON, None),
            ("1 ordinary listing, program off", {"source": "mercadolibre", "dealer_id": None}, OFF, None),
            ("2 directo without dealer", car(dealer_id=None), ON, "no_dealer"),
            ("3 channel off", car(), OFF, "channel_off"),
            ("3 enabled, channel off", car(), dealer_program({"enabled": True}), "channel_off"),
            ("4 not approved", car(dealer_approved=False), ON, "not_approved"),
            ("4 paused", car(dealer_active=False), ON, "not_approved"),
            ("5 reserved", car(dealer_status="reserved"), ON, "not_available"),
            ("5 sold", car(dealer_status="sold"), ON, "not_available"),
            ("5 no status", car(dealer_status=None), ON, "not_available"),
            ("6 never confirmed", car(dealer_confirmed_at=None), ON, "unconfirmed"),
            ("6 eight days with 7", car(dealer_confirmed_at=old), ON, "unconfirmed"),
            ("7 directo sent", car(), ON, None),
            ("7 six days with 7", car(dealer_confirmed_at=NOW - timedelta(days=6)), ON, None),
            ("8 synced reserved", car(source="mercadolibre", dealer_status="reserved"), ON, "not_available"),
            ("8 synced sold, program off", car(source="kavak", dealer_status="sold"), OFF, "not_available"),
            ("9 synced", car(source="mercadolibre", dealer_confirmed_at=None, dealer_approved=False), OFF, None),
        ]
        for name, row, program, expected in cases:
            with self.subTest(name):
                self.assertEqual(hidden_reason(row, program, now=NOW), expected)
                self.assertTrue(expected is None or expected in HIDDEN_REASONS)

    def test_confirm_days_come_from_the_program(self):
        row = car(dealer_confirmed_at=NOW - timedelta(days=10))
        self.assertEqual(hidden_reason(row, ON, now=NOW), "unconfirmed")
        longer = dealer_program({"enabled": True, "channel_enabled": True, "manual_confirm_days": 14})
        self.assertIsNone(hidden_reason(row, longer, now=NOW))

    def test_confirmed_at_as_text_or_naive(self):
        self.assertIsNone(hidden_reason(car(dealer_confirmed_at=(NOW - timedelta(days=1)).isoformat()), ON, now=NOW))
        naive = (NOW - timedelta(days=1)).replace(tzinfo=None)
        self.assertIsNone(hidden_reason(car(dealer_confirmed_at=naive), ON, now=NOW))
        self.assertEqual(hidden_reason(car(dealer_confirmed_at="mañana"), ON, now=NOW), "unconfirmed")

    def test_is_dealer_listing(self):
        self.assertTrue(is_dealer_listing({"source": DEALER_SOURCE}))
        self.assertTrue(is_dealer_listing({"source": "mercadolibre", "dealer_id": 4}))
        self.assertFalse(is_dealer_listing({"source": "mercadolibre", "dealer_id": None}))


class LabelTests(unittest.TestCase):
    def test_visible_dealer_car_has_the_label(self):
        self.assertEqual(label(car(), ON, now=NOW), {"label": "Promocionado", "name": "TT Autos"})
        self.assertEqual(label(car(source="mercadolibre"), ON, now=NOW), {"label": "Promocionado", "name": "TT Autos"})

    def test_no_label(self):
        cases = {
            "ordinary": ({"source": "mercadolibre", "dealer_id": None, "dealer_name": "X"}, ON),
            "channel off": (car(), OFF),
            "only enabled": (car(), dealer_program({"enabled": True})),
            "not approved synced": (car(source="mercadolibre", dealer_approved=False), ON),
            "paused": (car(dealer_active=False), ON),
            "no name": (car(dealer_name="  "), ON),
            "hidden": (car(dealer_status="reserved"), ON),
            "unconfirmed": (car(dealer_confirmed_at=None), ON),
        }
        for name, (row, program) in cases.items():
            with self.subTest(name):
                self.assertIsNone(label(row, program, now=NOW))


class PrivateOnlyTests(unittest.TestCase):
    def test_private_only(self):
        self.assertTrue(private_only({"seller_types": ["private"]}))
        self.assertTrue(private_only({"seller_types": ["private", "nonsense"]}))
        for f in ({}, {"seller_types": []}, {"seller_types": ["dealer"]}, {"seller_types": ["private", "dealer"]},
                  {"seller_types": "private"}, {"seller_types": ["nonsense"]}, {"seller_types": None}):
            with self.subTest(f=f):
                self.assertFalse(private_only(f))


if __name__ == "__main__":
    unittest.main()


class RunDealersTests(unittest.IsolatedAsyncioTestCase):
    """pipeline/dealers.run_dealers with its repo faked: which steps run under each switch (C5)."""

    async def run_with(self, *, ready=True, raw=None):
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock, patch

        from pipeline import dealers as job

        @asynccontextmanager
        async def fake_connection():
            yield object()

        calls = {}

        def fake(name, value=None):
            calls[name] = AsyncMock(return_value=value)
            return calls[name]

        notifier = type("N", (), {"channels": {"email": object()}})()
        with patch.object(job.db, "connection", fake_connection), \
                patch.object(job.db, "get_config", AsyncMock(return_value=raw)), \
                patch.object(job.repo, "schema_ready", AsyncMock(return_value=ready)), \
                patch.object(job.repo, "sweep", fake("sweep", {"matches_deleted": 2, "notifications_skipped": 1,
                                                                "expired_deleted": 0})), \
                patch.object(job, "sync_linked", fake("sync_linked")), \
                patch.object(job, "sync_manual", fake("sync_manual")), \
                patch.object(job.repo, "touch_directo", fake("touch", 0)), \
                patch.object(job, "match_visible", fake("match")), \
                patch.object(job, "notify_new_leads", fake("leads", 1)):
            tick = await job.run_dealers(notifier, None)
        return tick, {k for k, v in calls.items() if v.await_count}

    async def test_without_the_schema_nothing_runs(self):
        tick, ran = await self.run_with(ready=False)
        self.assertEqual(ran, set())
        self.assertFalse(any(vars(tick).values()))

    async def test_disabled_only_sweeps(self):
        tick, ran = await self.run_with(raw=None)
        self.assertEqual(ran, {"sweep"})
        self.assertEqual((tick.swept_matches, tick.skipped_notifications), (2, 1))

    async def test_panel_only_syncs_but_never_matches(self):
        _, ran = await self.run_with(raw={"enabled": True})
        self.assertEqual(ran, {"sweep", "sync_linked", "sync_manual", "touch"})

    async def test_channel_on_runs_everything(self):
        tick, ran = await self.run_with(raw={"enabled": True, "channel_enabled": True})
        self.assertEqual(ran, {"sweep", "sync_linked", "sync_manual", "touch", "match", "leads"})
        self.assertEqual(tick.lead_notices, 1)


class ListingForTests(unittest.TestCase):
    def test_item_as_a_collector_listing(self):
        from pipeline.dealers import listing_for

        created = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        item = {"id": 42, "make": "Ford", "model": "Focus", "trim": "SE", "year": 2017, "mileage_km": 68000,
                "price": 15_900, "currency": "USD", "transmission": "manual", "fuel": "nafta", "color": "rojo",
                "body_type": None, "title": None, "description": "Impecable", "images": ["https://a/1.jpg", 3],
                "created_at": created, "dealer_name": "TT Autos", "locality_label": "Quilmes"}
        li = listing_for(item, base_url="https://eseauto.test")
        self.assertEqual((li.source, li.listing_id, li.url), ("directo", "42", "https://eseauto.test/app/listings/directo/42"))
        self.assertEqual(li.titulo, "Ford Focus SE 2017")
        self.assertEqual((li.precio, li.moneda, li.km, li.anio), (15_900.0, "USD", 68000, 2017))
        self.assertEqual((li.vendedor, li.vendedor_nombre, li.ubicacion), ("dealer", "TT Autos", "Quilmes"))
        self.assertEqual(li.imagenes, ["https://a/1.jpg"])
        self.assertEqual(li.published_at, int(created.timestamp()))
        self.assertEqual(li.atributos, {"Color": "rojo"})
