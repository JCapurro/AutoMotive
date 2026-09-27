"""F3 notification engine against the local Supabase Postgres (docs/TECHNICAL_PLAN.md, sección 7).

Channels are fakes (a Telegram bot that records, Resend behind httpx's
MockTransport); the decision, the notifications log, the daily cap, dedupe,
the digest, click tracking and the Telegram buttons run for real. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from db.repos import matches as matches_repo
from db.repos import notifications as repo
from db.repos.listings import rows_for_scoring
from notifications.channels.email import ResendEmailChannel
from notifications.channels.telegram import TelegramChannel
from notifications.channels.web import WebChannel
from notifications.digest import run_digest
from notifications.links import Links
from notifications.service import MatchCandidate, Notifier
from pgcase import PostgresTestCase, requires_db
from pipeline.ingest import ListingEvent
from tools import redirect_server

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866
EMAIL = "ana@automotive.test"
LINKS = Links("https://automotive.app")


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return type("Message", (), {"message_id": len(self.sent)})()


class NotificationsCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._n = 0
        self.bot = FakeBot()
        self.emails: list[dict] = []

        def resend(request: httpx.Request) -> httpx.Response:
            self.emails.append(json.loads(request.content))
            return httpx.Response(200, json={"id": f"email_{len(self.emails)}"})

        client = httpx.AsyncClient(transport=httpx.MockTransport(resend))
        self.addAsyncCleanup(client.aclose)
        self.notifier = Notifier({
            "telegram": TelegramChannel(self.bot, LINKS),
            "email": ResendEmailChannel("re_test", "Automotive <alertas@automotive.test>", LINKS, client=client),
            "web": WebChannel(LINKS),
        })
        self.profile = await self.alert()
        self.user = await self.user_of(self.profile)

    # -- helpers -----------------------------------------------------------

    async def alert(self, *, user: int = TG_USER, channels=("telegram", "email", "web"),
                    frequency: str = "immediate", min_level: str = "good", email: str | None = EMAIL) -> int:
        [pid] = await db.create_alert(user_id=user, chat_id=user, name="Fiesta Titanium AMBA",
                                      filters={"marcas": ["Ford"], "modelos": ["Fiesta"],
                                               "sources": ["mercadolibre"]})
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET channels = %s, notification_frequency = %s, "
                             "  notify_min_level = %s, bootstrapped_at = now() WHERE id = %s",
                             (list(channels), frequency, min_level, pid))
            await cx.execute("UPDATE profiles SET email = %s WHERE telegram_user_id = %s", (email, user))
        return pid

    async def user_of(self, profile_id: int) -> str:
        [r] = await self.rows("SELECT user_id::text AS id FROM search_profiles WHERE id = %s", profile_id)
        return r["id"]

    async def listing(self, **kw) -> int:
        self._n += 1
        row = dict(source="mercadolibre", external_id=f"n{self._n}", url=f"https://example.test/n{self._n}",
                   title="Ford Fiesta Titanium", make="Ford", model="Fiesta", trim="Titanium", year=2017,
                   price=10_300, currency="USD", price_usd=10_300, mileage_km=112_000)
        row.update(kw)
        cols = list(row)
        async with db.connection() as cx:
            r = await (await cx.execute(
                f"INSERT INTO listings ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) RETURNING id",
                list(row.values()))).fetchone()
        return r["id"]

    async def match(self, profile_id: int, listing_id: int, level: str, score: int, *,
                    backfill: bool = False, diff_pct: float | None = 8.0) -> MatchCandidate:
        ev = {"score": score, "level": level, "score_breakdown": {}, "match_reasons": {},
              "price_ref": {"n": 7, "median": 11_200, "diff_pct": diff_pct, "level_used": "model"},
              "red_flags": [], "scoring_version": "test"}
        async with db.connection() as cx:
            ids = await matches_repo.upsert_scored(cx, profile_id, [(listing_id, ev)], backfill=backfill)
        return MatchCandidate(profile_id, listing_id, ids.get(listing_id), ev)

    async def matched(self, *candidates: MatchCandidate) -> list[int]:
        async with db.connection() as cx:
            rows = await rows_for_scoring(cx, [c.listing_id for c in candidates])
        return await self.notifier.on_matches(list(candidates), rows)

    def drop(self, listing_id: int, snapshot_id: int = 1, **kw) -> ListingEvent:
        base = dict(snapshot_id=snapshot_id, old_price=11_500, new_price=10_800, currency="USD",
                    old_currency="USD", drop_pct=6.09)
        base.update(kw)
        return ListingEvent("price_drop", listing_id, "mercadolibre", f"n{listing_id}", **base)

    async def rows(self, sql: str, *params) -> list[dict]:
        async with db.connection() as cx:
            return await (await cx.execute(sql, params)).fetchall()

    async def notifications(self, channel: str | None = None) -> list[dict]:
        where = "WHERE channel = %s" if channel else ""
        return await self.rows(
            "SELECT id, kind::text AS kind, channel::text AS channel, status::text AS status, dedupe_key, "
            f"       listing_id, payload, digested_in FROM notifications {where} ORDER BY id",
            *([channel] if channel else []))

    async def set_config(self, key: str, value) -> None:
        [old] = await self.rows("SELECT value FROM app_config WHERE key = %s", key)

        async def restore() -> None:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = %s WHERE key = %s", (Jsonb(old["value"]), key))
            app_config.clear_config_cache()

        self._restore = restore
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = %s WHERE key = %s", (Jsonb(value), key))
        app_config.clear_config_cache()

    async def asyncTearDown(self) -> None:
        if getattr(self, "_restore", None):
            await self._restore()
        await super().asyncTearDown()


class AlertTypesTests(NotificationsCase):
    """Acceptance: the three types of §22 reach Telegram and email with the right copy."""

    async def test_opportunity_new_match_and_price_drop_on_telegram_and_email(self):
        deal = await self.listing(published_at=datetime.now(timezone.utc) - timedelta(minutes=4))
        normal = await self.listing(price=11_000, price_usd=11_000, mileage_km=128_000)
        followed = await self.listing(price=10_800, price_usd=10_800)
        await self.matched(await self.match(self.profile, deal, "high", 88),
                           await self.match(self.profile, normal, "good", 74))
        await self.match(self.profile, followed, "good", 81, backfill=True)
        await self.notifier.on_listing_events([self.drop(followed)])

        self.assertEqual(await self.notifier.deliver(), 9)          # 3 alerts × 3 channels

        tg = [m["text"] for m in self.bot.sent]
        self.assertTrue(tg[0].startswith(
            "<b>🔥 Nueva oportunidad</b>\n<b>Ford Fiesta Titanium 2017</b>\n112.000 km\nUSD 10.300\n"
            "Opportunity Score 88/100\n8% debajo de publicaciones comparables.\nPublicado hace 4 minutos.\n"))
        self.assertTrue(tg[1].startswith(
            "<b>🚗 Nuevo vehículo encontrado</b>\n<b>Ford Fiesta Titanium 2017</b>\n128.000 km\nUSD 11.000\n"))
        self.assertTrue(tg[2].startswith(
            "<b>📉 Bajó de precio</b>\n<b>Ford Fiesta Titanium 2017</b>\nAntes: USD 11.500\n"
            "Ahora: USD 10.800\n-6,1%\n"))
        self.assertEqual({m["chat_id"] for m in self.bot.sent}, {TG_USER})

        mails = {m["subject"].split(":")[0]: m for m in self.emails}
        self.assertEqual(set(mails), {"🔥 Nueva oportunidad", "🚗 Nuevo vehículo encontrado", "📉 Bajó de precio"})
        self.assertTrue(mails["🔥 Nueva oportunidad"]["text"].startswith(
            "🔥 Nueva oportunidad\nFord Fiesta Titanium 2017\n112.000 km\nUSD 10.300\nOpportunity Score 88/100\n"
            "8% debajo de publicaciones comparables.\nPublicado hace 4 minutos.\n"))
        self.assertTrue(mails["📉 Bajó de precio"]["text"].startswith(
            "📉 Bajó de precio\nFord Fiesta Titanium 2017\nAntes: USD 11.500\nAhora: USD 10.800\n-6,1%\n"))
        self.assertEqual({tuple(m["to"]) for m in self.emails}, {(EMAIL,)})

        rows = await self.notifications()
        self.assertEqual({r["status"] for r in rows}, {"sent"})
        self.assertEqual(sorted({r["kind"] for r in rows}), ["new_match", "opportunity", "price_drop"])
        web = [r for r in rows if r["channel"] == "web"]
        self.assertEqual(web[0]["payload"]["web"]["title"], "🔥 Nueva oportunidad")
        [n] = await self.rows("SELECT count(*) AS n FROM events WHERE name = 'alert_sent'")
        self.assertEqual(n["n"], 9)

    async def test_below_min_level_is_silent(self):
        await self.matched(await self.match(self.profile, await self.listing(), "match", 60))
        self.assertEqual(await self.notifications(), [])

    async def test_without_email_or_telegram_only_the_web_inbox(self):
        pid = await self.alert(user=1, email=None)
        async with db.connection() as cx:
            await cx.execute("UPDATE profiles SET telegram_chat_id = NULL WHERE telegram_user_id = 1")
        await self.matched(await self.match(pid, await self.listing(), "high", 90))
        self.assertEqual([r["channel"] for r in await self.notifications()], ["web"])


class DedupeTests(NotificationsCase):
    """Acceptance: the same listing never generates two alerts of the same type."""

    async def test_the_same_match_twice_and_through_another_profile(self):
        lid = await self.listing()
        other = await self.alert()                                  # same user, second profile
        await self.matched(await self.match(self.profile, lid, "good", 75))
        await self.matched(await self.match(self.profile, lid, "good", 75))
        await self.matched(await self.match(other, lid, "high", 92))  # now 🔥 elsewhere: still one
        await self.notifier.deliver()
        rows = await self.notifications("telegram")
        self.assertEqual([(r["kind"], r["dedupe_key"]) for r in rows], [("new_match", f"match:{lid}")])
        self.assertEqual(len(self.bot.sent), 1)

    async def test_one_alert_per_user_with_the_highest_level(self):
        lid = await self.listing()
        other = await self.alert()
        await self.matched(await self.match(self.profile, lid, "good", 75),
                           await self.match(other, lid, "high", 92))
        rows = await self.notifications("telegram")
        self.assertEqual([(r["kind"], r["payload"]["match"]["level"]) for r in rows], [("opportunity", "high")])

    async def test_a_price_drop_once_per_snapshot(self):
        lid = await self.listing()
        await self.match(self.profile, lid, "good", 75, backfill=True)
        await self.notifier.on_listing_events([self.drop(lid, 10)])
        await self.notifier.on_listing_events([self.drop(lid, 10)])
        await self.notifier.on_listing_events([self.drop(lid, 11, old_price=10_800, new_price=10_000,
                                                         drop_pct=7.4)])
        keys = [r["dedupe_key"] for r in await self.notifications("telegram")]
        self.assertEqual(keys, [f"price_drop:{lid}:10", f"price_drop:{lid}:11"])

    async def test_two_users_are_independent(self):
        lid = await self.listing()
        other = await self.alert(user=2, email="beto@automotive.test")
        await self.matched(await self.match(self.profile, lid, "high", 90),
                           await self.match(other, lid, "high", 90))
        self.assertEqual(len(await self.notifications("telegram")), 2)


class DailyCapAndDigestTests(NotificationsCase):
    async def test_with_the_cap_at_2_the_third_alert_goes_to_the_digest(self):
        await self.set_config("alerts_max_per_user_day", 2)
        ids = [await self.listing() for _ in range(3)]
        for lid in ids:                                              # one per crawl batch
            await self.matched(await self.match(self.profile, lid, "high", 90))
        await self.notifier.deliver()

        rows = await self.notifications("telegram")
        self.assertEqual([r["status"] for r in rows], ["sent", "sent", "digest"])
        self.assertEqual(rows[2]["payload"]["degraded"], "daily_cap")
        self.assertEqual(len(self.bot.sent), 2)

        self.assertEqual(await run_digest(self.notifier), 3)         # telegram, email, web
        [digest] = [r for r in await self.notifications("telegram") if r["kind"] == "digest"]
        self.assertEqual(digest["status"], "sent")
        self.assertEqual(digest["payload"]["degraded"], 1)
        self.assertEqual([i["listing_id"] for i in digest["payload"]["items"]], [ids[2]])
        [carried] = [r for r in await self.notifications("telegram") if r["listing_id"] == ids[2]]
        self.assertEqual(carried["digested_in"], digest["id"])
        self.assertTrue(self.bot.sent[-1]["text"].startswith("<b>🗓 Tu resumen del día</b>\n"
                                                             "1 alerta superó el tope diario"))
        # Running again the same day (a restart) creates nothing.
        self.assertEqual(await run_digest(self.notifier), 0)

    async def test_daily_profiles_top_matches_and_gone_listings(self):
        pid = await self.alert(user=3, email=None, channels=("telegram",), frequency="daily")
        user = await self.user_of(pid)
        good = await self.listing(price=10_900, price_usd=10_900)
        low = await self.listing(price=12_900, price_usd=12_900)
        saved = await self.listing()
        async with db.connection() as cx:
            await cx.execute("INSERT INTO user_listing_interactions (user_id, listing_id, saved) "
                             "VALUES (%s, %s, true)", (user, saved))
        await self.matched(await self.match(pid, good, "good", 76),
                           await self.match(pid, low, "low", 35))
        await self.notifier.on_listing_events([ListingEvent("listing_gone", saved, "mercadolibre", "x")])
        self.assertEqual(await self.notifier.deliver(), 0)           # all waits for the digest

        await run_digest(self.notifier)
        [digest] = [r for r in await self.notifications("telegram") if r["kind"] == "digest"]
        items = [(i["section"], i["listing_id"]) for i in digest["payload"]["items"]]
        self.assertEqual(items, [("matches", good), ("matches", low), ("gone", saved)])
        text = self.bot.sent[-1]["text"]
        self.assertIn("<b>Publicaciones nuevas</b>", text)
        self.assertIn("🟢 76 · ", text)
        self.assertIn("⚪ 35 · ", text)                                # below min level: digest only
        self.assertIn("<b>Ya no están disponibles</b>", text)

    async def test_a_saved_listing_price_drop_is_immediate_even_on_a_daily_profile(self):
        pid = await self.alert(user=4, email=None, channels=("telegram",), frequency="daily")
        user = await self.user_of(pid)
        lid = await self.listing()
        async with db.connection() as cx:
            await cx.execute("INSERT INTO user_listing_interactions (user_id, listing_id, saved) "
                             "VALUES (%s, %s, true)", (user, lid))
        await self.notifier.on_listing_events([self.drop(lid)])
        self.assertEqual(await self.notifier.deliver(), 1)
        self.assertIn("Bajó de precio", self.bot.sent[0]["text"])


class TrackingTests(NotificationsCase):
    """/r/<id> (sección 7.3): click = opened; previews don't count."""

    async def sent(self) -> dict:
        lid = await self.listing()
        await self.matched(await self.match(self.profile, lid, "high", 90))
        [n] = await self.notifications("telegram")
        return n

    async def test_a_click_records_and_redirects(self):
        n = await self.sent()
        r = await redirect_server.resolve("GET", f"/r/{n['id']}?to=listing", "Mozilla/5.0")
        self.assertEqual((r.status, r.location), (302, "https://example.test/n1"))
        [row] = await self.rows("SELECT clicked_at, opened_at FROM notifications WHERE id = %s", n["id"])
        self.assertIsNotNone(row["clicked_at"])
        self.assertEqual(row["clicked_at"], row["opened_at"])
        [ev] = await self.rows("SELECT props FROM events WHERE name = 'alert_clicked'")
        self.assertEqual((ev["props"]["notification_id"], ev["props"]["to"]), (n["id"], "listing"))

        # The first click stays the "opened" time; later clicks are events.
        await redirect_server.resolve("GET", f"/r/{n['id']}?to=detail", "Mozilla/5.0")
        [again] = await self.rows("SELECT clicked_at FROM notifications WHERE id = %s", n["id"])
        self.assertEqual(again["clicked_at"], row["clicked_at"])
        self.assertEqual(len(await self.rows("SELECT 1 FROM events WHERE name = 'alert_clicked'")), 2)

    async def test_detail_goes_to_the_web_when_it_exists(self):
        n = await self.sent()
        r = await redirect_server.resolve("GET", f"/r/{n['id']}?to=detail", "Mozilla/5.0",
                                          detail_url="https://automotive.app/app/listings/{listing_id}")
        self.assertEqual(r.location, f"https://automotive.app/app/listings/{n['listing_id']}")

    async def test_previews_and_head_do_not_count(self):
        n = await self.sent()
        for method, ua in (("GET", "TelegramBot (like TwitterBot)"), ("HEAD", "Mozilla/5.0")):
            r = await redirect_server.resolve(method, f"/r/{n['id']}", ua)
            self.assertEqual(r.status, 302)
        [row] = await self.rows("SELECT clicked_at FROM notifications WHERE id = %s", n["id"])
        self.assertIsNone(row["clicked_at"])

    async def test_unknown_ids_and_foreign_listings_are_404(self):
        n = await self.sent()
        other = await self.listing()
        self.assertEqual((await redirect_server.resolve("GET", "/r/999999", None)).status, 404)
        self.assertEqual((await redirect_server.resolve("GET", f"/r/{n['id']}?l={other}", None)).status, 404)
        self.assertEqual((await redirect_server.resolve("GET", "/nope", None)).status, 404)
        self.assertEqual((await redirect_server.resolve("POST", f"/r/{n['id']}", None)).status, 405)

    async def test_a_digest_item_marks_the_row_it_carries(self):
        await self.set_config("alerts_max_per_user_day", 0)
        lid = await self.listing()
        await self.matched(await self.match(self.profile, lid, "high", 90))
        await run_digest(self.notifier)
        [digest] = [r for r in await self.notifications("telegram") if r["kind"] == "digest"]
        r = await redirect_server.resolve("GET", f"/r/{digest['id']}?to=listing&l={lid}", "Mozilla/5.0")
        self.assertEqual(r.status, 302)
        clicked = await self.rows("SELECT kind::text AS kind FROM notifications "
                                  "WHERE channel = 'telegram' AND clicked_at IS NOT NULL ORDER BY id")
        self.assertEqual([c["kind"] for c in clicked], ["opportunity", "digest"])

    async def test_over_http(self):
        n = await self.sent()
        server = await asyncio.start_server(redirect_server.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        async with server, httpx.AsyncClient() as client:
            r = await client.get(f"http://127.0.0.1:{port}/r/{n['id']}?to=listing")
        self.assertEqual((r.status_code, r.headers["location"]), (302, "https://example.test/n1"))


class TelegramActionTests(NotificationsCase):
    async def sent(self) -> dict:
        lid = await self.listing()
        await self.matched(await self.match(self.profile, lid, "high", 90))
        [n] = await self.notifications("telegram")
        return n

    async def interaction(self, listing_id: int) -> dict:
        [row] = await self.rows("SELECT status::text AS status FROM user_listing_interactions "
                                "WHERE listing_id = %s", listing_id)
        return row

    async def test_me_interesa_and_descartar(self):
        n = await self.sent()
        self.assertIsNotNone(await repo.apply_telegram_action(n["id"], TG_USER, "interested"))
        self.assertEqual((await self.interaction(n["listing_id"]))["status"], "interested")
        await repo.apply_telegram_action(n["id"], TG_USER, "discarded")
        self.assertEqual((await self.interaction(n["listing_id"]))["status"], "discarded")
        names = [r["name"] for r in await self.rows("SELECT name FROM events WHERE name LIKE 'listing_%%' ORDER BY id")]
        self.assertEqual(names, ["listing_status_changed", "listing_status_changed", "listing_discarded"])
        [row] = await self.rows("SELECT opened_at FROM notifications WHERE id = %s", n["id"])
        self.assertIsNotNone(row["opened_at"])

    async def test_only_the_owner(self):
        n = await self.sent()
        self.assertIsNone(await repo.apply_telegram_action(n["id"], 1, "interested"))
        self.assertEqual(await self.rows("SELECT 1 FROM user_listing_interactions"), [])

    async def test_never_downgrades_a_later_status(self):
        n = await self.sent()
        async with db.connection() as cx:
            await cx.execute("INSERT INTO user_listing_interactions (user_id, listing_id, status) "
                             "VALUES (%s, %s, 'contacted')", (self.user, n["listing_id"]))
        await repo.apply_telegram_action(n["id"], TG_USER, "interested")
        self.assertEqual((await self.interaction(n["listing_id"]))["status"], "contacted")

    async def test_a_discarded_listing_is_not_notified_again(self):
        n = await self.sent()
        await repo.apply_telegram_action(n["id"], TG_USER, "discarded")
        await self.notifier.on_listing_events([self.drop(n["listing_id"])])
        self.assertEqual([r["kind"] for r in await self.notifications("telegram")], ["opportunity"])
