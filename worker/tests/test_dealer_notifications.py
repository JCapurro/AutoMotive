"""Agencias (spec §4.3, §4.6; C1 label, C2 privacy, C3 gate): the «Agencia»
line in alerts, the gate in the Notifier and the lead email to the dealer."""
from __future__ import annotations

import logging
import unittest
from contextlib import asynccontextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from intelligence.config import dealer_program
from notification_fixtures import DIGEST, FIESTA, LINKS, NEW_MATCH, NOW, OPPORTUNITY, PRICE_DROP, notification
from notifications import dealer_leads, service, templates
from notifications.channels.base import SendResult
from pipeline.ingest import ListingEvent

from test_lifecycle_templates import MISSED, WELCOME_CARS, email as lifecycle_email

ON = dealer_program({"enabled": True, "channel_enabled": True})
TAG = {"label": "Agencia", "name": "TT Autos"}


def row(**kw) -> dict:
    r = {**FIESTA, "source": "directo", "dealer_id": 4, "dealer_status": "available",
         "dealer_confirmed_at": NOW - timedelta(days=1), "dealer_approved": True, "dealer_active": True,
         "dealer_name": "TT Autos"}
    r.update(kw)
    return r


def with_dealer(n, **listing):
    return notification(n.kind, {**n.payload, "listing": {**n.payload["listing"], "dealer": TAG, **listing}},
                        id=n.id, listing_id=n.listing_id)


class ListingPayloadTests(unittest.TestCase):
    def test_visible_dealer_car_carries_the_label(self):
        self.assertEqual(service.listing_payload(row(), ON, now=NOW)["dealer"], TAG)

    def test_no_label(self):
        for name, (r, program) in {
            "no program": (row(), None),
            "channel off": (row(), dealer_program(None)),
            "hidden": (row(dealer_status="reserved"), ON),
            "ordinary listing": (dict(FIESTA), ON),
        }.items():
            with self.subTest(name):
                self.assertNotIn("dealer", service.listing_payload(r, program, now=NOW))

    def test_ordinary_payload_is_unchanged(self):
        self.assertEqual(service.listing_payload(dict(FIESTA)), service.listing_payload(dict(FIESTA), ON, now=NOW))

    def test_program_is_read_only_for_dealer_batches(self):
        async def run():
            with patch.object(service.db, "get_config", AsyncMock(return_value={"enabled": True})) as cfg:
                self.assertIsNone(await service.dealer_program([dict(FIESTA), None]))
                cfg.assert_not_awaited()
                self.assertTrue((await service.dealer_program([row()]))["enabled"])
        import asyncio
        asyncio.run(run())


class TemplateTests(unittest.TestCase):
    def test_line_after_km_and_price_in_every_channel(self):
        for n in (NEW_MATCH, OPPORTUNITY):
            with self.subTest(n.kind):
                tagged = with_dealer(n)
                tg = templates.telegram(tagged, LINKS, NOW).text
                mail = templates.email(tagged, LINKS, NOW)
                for text in (tg, mail.text, mail.html):
                    self.assertIn("Agencia · TT Autos", text)
                c = templates.content(tagged, LINKS, NOW)
                self.assertEqual(c.lines[2], "Agencia · TT Autos")
                self.assertEqual(templates.web(tagged, LINKS, NOW)["lines"][2], "Agencia · TT Autos")

    def test_price_drop_and_gone_have_it_last(self):
        c = templates.content(with_dealer(PRICE_DROP), LINKS, NOW)
        self.assertEqual(c.lines[-1], "Agencia · TT Autos")
        gone = notification("listing_gone", {"listing": {**FIESTA, "dealer": TAG}})
        self.assertEqual(templates.content(gone, LINKS, NOW).lines[-1], "Agencia · TT Autos")

    def test_directo_has_no_source_tag(self):
        c = templates.content(with_dealer(NEW_MATCH, source="directo"), LINKS, NOW)
        self.assertFalse(any("🏷" in x for x in c.notes))

    def test_without_dealer_the_output_is_the_same(self):
        for n in (NEW_MATCH, OPPORTUNITY, PRICE_DROP, DIGEST):
            with self.subTest(n.kind):
                self.assertNotIn("Agencia ·", templates.telegram(n, LINKS, NOW).text)
                self.assertNotIn("Agencia ·", templates.email(n, LINKS, NOW).text)
        bad = with_dealer(NEW_MATCH)
        bad.payload["listing"]["dealer"] = {"label": "Agencia", "name": " "}
        self.assertEqual(templates.content(bad, LINKS, NOW).lines, templates.content(NEW_MATCH, LINKS, NOW).lines)

    def test_digest_item(self):
        items = [dict(it) for it in DIGEST.payload["items"]]
        items[1] = {**items[1], "listing": {**items[1]["listing"], "dealer": TAG}}
        n = notification("digest", {**DIGEST.payload, "items": items}, id=43, listing_id=None)
        tg = templates.telegram(n, LINKS, NOW).text
        mail = templates.email(n, LINKS, NOW)
        self.assertEqual(tg.count("Agencia · TT Autos"), 1)
        self.assertIn("Agencia · TT Autos", mail.text)
        self.assertIn("Agencia · TT Autos", mail.html)

    def test_welcome_cars_and_missed_car(self):
        cars = [dict(c) for c in WELCOME_CARS]
        cars[0]["dealer_name"] = "TT Autos"
        msg = lifecycle_email("search_activated", {"model": "Ford Focus", "found": 14, "below": 2, "cars": cars})
        self.assertEqual(msg.html.count("Agencia · TT Autos"), 1)
        plain = lifecycle_email("search_activated", {"model": "Ford Focus", "found": 14, "below": 2,
                                                     "cars": WELCOME_CARS})
        self.assertNotIn("Agencia", plain.html)
        missed = {**MISSED, "car": {**MISSED["car"], "dealer_name": "TT Autos"}}
        self.assertIn("Agencia · TT Autos", lifecycle_email("count_after_expiry", missed).text)
        self.assertNotIn("Agencia ·", lifecycle_email("count_after_expiry", MISSED).text)


@asynccontextmanager
async def fake_connection():
    yield SimpleNamespace()


class NotifierGateTests(unittest.IsolatedAsyncioTestCase):
    async def events_for(self, rows: dict, program_raw):
        notifier = service.Notifier({"email": object()})
        audiences = [{"listing_id": lid, "user_id": "u1", "channels": ["email"], "email": "a@b.test",
                      "profile_id": 7, "profile_name": "Focus", "level": "good", "score": 75}
                     for lid in rows]
        captured: list = []

        async def commit(events, **kw):
            captured.extend(events)
            return []

        with patch.object(service.db, "connection", fake_connection), \
                patch.object(service.listings_repo, "rows_for_scoring", AsyncMock(return_value=rows)), \
                patch.object(service.repo, "listing_audiences", AsyncMock(return_value=audiences)), \
                patch.object(service, "_min_n", AsyncMock(return_value=5)), \
                patch.object(service, "flag_order", AsyncMock(return_value=())), \
                patch.object(service.db, "get_config", AsyncMock(return_value=program_raw)), \
                patch.object(notifier, "_commit", commit):
            await notifier.on_listing_events(
                [ListingEvent("price_drop", lid, "directo", str(lid), old_price=11000.0, new_price=10000.0,
                              currency="USD", drop_pct=9.1) for lid in rows], now=NOW)
        return captured

    async def test_hidden_listings_are_skipped(self):
        rows = {1: row(id=1), 2: row(id=2, dealer_status="reserved"), 3: {**FIESTA, "id": 3}}
        events = await self.events_for(rows, {"enabled": True, "channel_enabled": True})
        self.assertEqual(sorted(e.listing_id for e in events), [1, 3])
        tagged = {e.listing_id: e.payload["listing"].get("dealer") for e in events}
        self.assertEqual(tagged, {1: TAG, 3: None})

    async def test_channel_off_skips_every_directo(self):
        rows = {1: row(id=1), 3: {**FIESTA, "id": 3}}
        events = await self.events_for(rows, None)
        self.assertEqual([e.listing_id for e in events], [3])


BUYER = {"buyer_name": "Ana Pérez", "buyer_phone": "1155556666", "message": "Hola, ¿sigue disponible?",
         "buyer_user_id": "00000000-0000-0000-0000-000000000009"}


class FakeChannel:
    def __init__(self, ok=True):
        self.sent: list = []
        self.ok = ok

    async def send_message(self, to, msg, *, idempotency_key, unsubscribe_token):
        self.sent.append((to, msg, idempotency_key))
        return SendResult(self.ok, None if self.ok else "resend 500: boom", provider_id="p1" if self.ok else None)


class LeadEmailTests(unittest.IsolatedAsyncioTestCase):
    LEADS = [
        {"lead_id": 10, "dealer_id": 1, "listing_id": 5, "email": "tt@agencia.test", "make": "Ford",
         "model": "Focus", "trim": "SE", "year": 2017, "title": "Ford Focus SE 2017", **BUYER},
        {"lead_id": 11, "dealer_id": 1, "listing_id": 5, "email": "tt@agencia.test", "make": "Ford",
         "model": "Focus", "trim": "SE", "year": 2017, "title": "Ford Focus SE 2017", **BUYER},
        {"lead_id": 12, "dealer_id": 2, "listing_id": 6, "email": None, "make": "Fiat", "model": "Cronos",
         "trim": None, "year": 2020, "title": None, **BUYER},
    ]

    async def test_one_email_per_dealer_without_buyer_data(self):
        channel = FakeChannel()
        with patch.object(dealer_leads.repo, "unnotified_leads", AsyncMock(return_value=self.LEADS)), \
                patch.object(dealer_leads.repo, "mark_lead_notified", AsyncMock()) as marked, \
                self.assertLogs("dealer_leads", logging.INFO) as logs:
            sent = await dealer_leads.notify_new_leads(channel, LINKS)
        self.assertEqual(sent, 1)
        marked.assert_awaited_once_with([10, 11])                 # dealer 2 has no address: its lead waits
        to, msg, key = channel.sent[0]
        self.assertEqual(to, "tt@agencia.test")
        self.assertEqual(msg.subject, "Tenés 2 consultas nuevas en Ese Auto")
        self.assertIn("2 personas pidieron que las contactes por tu Ford Focus SE 2017.", msg.text)
        self.assertIn("https://automotive.app/agencia/consultas", msg.text)
        self.assertEqual(key, "dealer-leads-1-10-11")
        everything = "\n".join([msg.subject, msg.text, msg.html, *(r.getMessage() for r in logs.records)])
        for value in BUYER.values():
            self.assertNotIn(value, everything)
        self.assertNotIn("tt@agencia.test", "\n".join(r.getMessage() for r in logs.records))

    async def test_singular_and_failure(self):
        channel = FakeChannel(ok=False)
        with patch.object(dealer_leads.repo, "unnotified_leads", AsyncMock(return_value=self.LEADS[:1])), \
                patch.object(dealer_leads.repo, "mark_lead_notified", AsyncMock()) as marked, \
                self.assertLogs("dealer_leads", logging.WARNING) as logs:
            self.assertEqual(await dealer_leads.notify_new_leads(channel, LINKS), 0)
        marked.assert_not_awaited()
        msg = channel.sent[0][1]
        self.assertEqual(msg.subject, "Tenés 1 consulta nueva en Ese Auto")
        self.assertIn("1 persona pidió que la contactes por tu Ford Focus SE 2017.", msg.text)
        for value in BUYER.values():
            self.assertNotIn(value, "\n".join(r.getMessage() for r in logs.records))

    async def test_no_channel(self):
        self.assertEqual(await dealer_leads.notify_new_leads(None, LINKS), 0)


if __name__ == "__main__":
    unittest.main()
