"""match_decisions against the local Supabase Postgres (migration 20261212120000_score_f3_shadow):
idempotent inserts, the deferred/sweeper rule inside the insert, the reads of the decision log,
the insert-only trigger through the worker's pool, and the shadow report reading read-only.
Skipped while the migration is not applied to the test database (`python -m tools.test_db`)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import match_decisions as repo
from pgcase import PostgresTestCase, requires_db
from tools import shadow_report

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987301


class MatchDecisionsCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            missing = not await repo.available(cx)
            if not missing:
                # Match ids restart with the TRUNCATE above: old rows would swallow new ones by ON CONFLICT.
                await cx.execute("TRUNCATE match_decisions")
        if missing:
            await db.close_pool()         # a skip in setUp does not run asyncTearDown
            self.skipTest("match_decisions missing: apply the migration and re-run `python -m tools.test_db`")
        [self.profile] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Sombra f3",
                                               filters={"marcas": ["Ford"], "modelos": ["Fiesta"]})
        async with db.connection() as cx:
            r = await (await cx.execute("SELECT user_id::text AS u FROM search_profiles WHERE id = %s",
                                        (self.profile,))).fetchone()
        self.user = r["u"]
        self.now = datetime.now(timezone.utc)
        self._n = 0

    async def listing(self, **kw) -> int:
        self._n += 1
        row = dict(source="mercadolibre", external_id=f"f3s{self._n}", url=f"https://example.test/f3s{self._n}",
                   title=f"Ford Fiesta {self._n}", make="Ford", model="Fiesta", year=2017,
                   price=10_300, currency="USD", price_usd=10_300)
        row.update(kw)
        async with db.connection() as cx:
            r = await (await cx.execute(
                f"INSERT INTO listings ({', '.join(row)}) VALUES ({', '.join(['%s'] * len(row))}) RETURNING id",
                list(row.values()))).fetchone()
        return r["id"]

    async def match(self, listing_id: int, *, level: str = "good", breakdown: dict | None = None) -> int:
        async with db.connection() as cx:
            r = await (await cx.execute(
                "INSERT INTO matches (search_profile_id, listing_id, score, level, score_breakdown, match_reasons, "
                "  price_ref, scoring_version) VALUES (%s, %s, 75, %s, %s, '{}', %s, 'f2-v5-seller-margin') RETURNING id",
                (self.profile, listing_id, level, Jsonb(breakdown or {}),
                 Jsonb({"n": 20, "level_used": "trim", "median": 11_200, "p25": 10_600, "p75": 12_000,
                        "diff_pct": 8.04})))).fetchone()
        return r["id"]

    def row(self, match_id: int, listing_id: int, phase: str = "card", **kw) -> dict:
        out = {"match_id": match_id, "search_profile_id": self.profile, "listing_id": listing_id,
               "user_id": self.user, "model": "f2", "phase": phase, "f3_decides": True,
               "f2_version": "f2-v5-seller-margin"}
        out.update(kw)
        return out

    async def insert(self, *rows: dict) -> int:
        async with db.connection() as cx:
            return await repo.insert(cx, rows)

    async def rows(self, sql: str, *params) -> list[dict]:
        async with db.connection() as cx:
            return await (await cx.execute(sql, params)).fetchall()


class InsertTests(MatchDecisionsCase):
    async def test_insert_is_idempotent_and_keeps_the_values(self):
        card = self.row(1, 11, f2_score=88.0, f2_level="high", f2_decision="queued", f2_kind="opportunity",
                        red_flags=[{"id": "much_cheaper", "text": "x", "severity": "info"}],
                        f3={"v": "f3-precio-encaje", "level": "high"}, f3_d=8.0357, price=10300,
                        price_ref={"n": 23, "diff_pct": 8.04}, audience={"min_level": "good"})
        self.assertEqual(await self.insert(card), 1)
        self.assertEqual(await self.insert(card, {**card}), 0)          # a retried batch
        [r] = await self.rows("SELECT * FROM match_decisions")
        self.assertEqual((r["f2_score"], r["f2_level"], r["red_flags"], r["f3_flags"], r["f3_a_verificar"]),
                         (88, "high", ["much_cheaper"], [], []))
        self.assertEqual(r["f3"], {"v": "f3-precio-encaje", "level": "high"})
        self.assertAlmostEqual(r["f3_d"], 8.0357, places=3)
        self.assertEqual(r["price_ref"], {"n": 23, "diff_pct": 8.04})
        self.assertLess(abs((r["decided_at"] - self.now).total_seconds()), 60)    # defaults to now()

    async def test_one_row_per_phase(self):
        self.assertEqual(await self.insert(self.row(1, 11), self.row(1, 11, "deferred", f3_decides=False)), 2)
        self.assertEqual(await self.insert(self.row(1, 11, "deferred")), 0)

    async def test_the_sweeper_does_nothing_after_the_deferred_row(self):
        await self.insert(self.row(1, 11, would_defer=True, f3_decides=False), self.row(1, 11, "deferred"))
        self.assertEqual(await self.insert(self.row(1, 11, "sweeper")), 0)
        self.assertEqual([r["phase"] for r in await self.rows("SELECT phase FROM match_decisions ORDER BY id")],
                         ["card", "deferred"])

    async def test_a_deferred_row_after_the_sweeper_does_not_decide(self):
        await self.insert(self.row(2, 12, would_defer=True, f3_decides=False), self.row(2, 12, "sweeper"))
        self.assertEqual(await self.insert(self.row(2, 12, "deferred", f3_decides=True)), 1)
        rows = await self.rows("SELECT phase, f3_decides FROM match_decisions ORDER BY id")
        self.assertEqual([(r["phase"], r["f3_decides"]) for r in rows],
                         [("card", False), ("sweeper", True), ("deferred", False)])

    async def test_a_bad_row_inserts_nothing(self):
        with self.assertRaises(psycopg.errors.CheckViolation):
            await self.insert(self.row(1, 11), self.row(2, 12, f3_level="top"))
        self.assertEqual(await self.rows("SELECT id FROM match_decisions"), [])

    async def test_the_trigger_refuses_updates_and_deletes(self):
        await self.insert(self.row(1, 11))
        for sql in ("UPDATE match_decisions SET f3_decides = false", "DELETE FROM match_decisions"):
            with self.assertRaisesRegex(psycopg.errors.RaiseException, "match_decisions is insert-only"):
                async with db.connection() as cx:
                    await cx.execute(sql)
        self.assertEqual(len(await self.rows("SELECT id FROM match_decisions")), 1)


class ReadTests(MatchDecisionsCase):
    async def test_cards_for_listings(self):
        since = self.now - timedelta(hours=24)
        await self.insert(
            self.row(1, 11),                                                        # listed
            self.row(2, 11, would_defer=True, f3_decides=False), self.row(2, 11, "sweeper"),   # listed, has_sweeper
            self.row(3, 12), self.row(3, 12, "deferred"),                           # already deferred
            self.row(4, 11, decided_at=(self.now - timedelta(hours=25)).isoformat()),   # too old
            self.row(5, 13),                                                        # another listing
            self.row(6, 11, model="f3"))                                            # another model
        async with db.connection() as cx:
            cards = await repo.cards_for_listings(cx, [11, 12], since=since)
        self.assertEqual([(c["match_id"], c["has_sweeper"]) for c in cards], [(1, False), (2, True)])
        self.assertEqual(cards[0]["user_id"], self.user)
        self.assertEqual(set(cards[0]) - {"id", "has_sweeper"}, set(repo.COLUMNS))
        async with db.connection() as cx:
            self.assertEqual([c["match_id"] for c in await repo.cards_for_listings(cx, [11], since=since, model="f3")],
                             [6])

    async def test_due_sweeps(self):
        at = lambda minutes: (self.now - timedelta(minutes=minutes)).isoformat()   # noqa: E731
        await self.insert(
            self.row(1, 11, would_defer=True, f3_decides=False, decided_at=at(25)),     # due
            self.row(2, 12, would_defer=True, f3_decides=False, decided_at=at(40)),     # due, older
            self.row(3, 13, would_defer=True, f3_decides=False, decided_at=at(5)),      # not yet
            self.row(4, 14, would_defer=False, decided_at=at(25)),                      # does not wait
            self.row(5, 15, would_defer=True, f3_decides=False, decided_at=at(25)),
            self.row(5, 15, "deferred"),                                                # the detail came
            self.row(6, 16, would_defer=True, f3_decides=False, decided_at=at(25)),
            self.row(6, 16, "sweeper"),                                                 # already swept
            self.row(7, 17, would_defer=True, f3_decides=False, decided_at=at(60 * 30)))   # outside the window
        async with db.connection() as cx:
            due = await repo.due_sweeps(cx, before=self.now - timedelta(minutes=20),
                                        since=self.now - timedelta(hours=24))
            self.assertEqual([r["match_id"] for r in due], [2, 1])
            one = await repo.due_sweeps(cx, before=self.now - timedelta(minutes=20),
                                        since=self.now - timedelta(hours=24), limit=1)
            self.assertEqual([r["match_id"] for r in one], [2])

    async def test_current_state(self):
        lid = await self.listing(seller_type="private", enriched_at=self.now, price=12_500_000, currency="ARS",
                                 price_usd=12_500)
        mid = await self.match(lid, level="high", breakdown={"price": {"score": 1}, "shadow_f3": {"level": "good"}})
        async with db.connection() as cx:
            [state] = (await repo.current_state(cx, [mid, 999_999])).values()
        self.assertEqual((state["match_id"], state["listing_id"], state["search_profile_id"], state["user_id"]),
                         (mid, lid, self.profile, self.user))
        self.assertEqual((state["level"], state["score"], state["scoring_version"]), ("high", 75, "f2-v5-seller-margin"))
        self.assertEqual(state["score_breakdown"]["shadow_f3"], {"level": "good"})
        self.assertEqual((state["price"], state["currency"], state["price_usd"]), (12_500_000.0, "ARS", 12_500.0))
        self.assertIsInstance(state["price"], float)
        self.assertEqual((state["status"], state["seller_type"], state["year"]), ("active", "private", 2017))
        self.assertIsNotNone(state["enriched_at"])
        async with db.connection() as cx:
            await cx.execute("DELETE FROM matches WHERE id = %s", (mid,))
            self.assertEqual(await repo.current_state(cx, [mid]), {})

    async def test_rows_outlive_the_match_and_the_listing(self):
        lid = await self.listing()
        mid = await self.match(lid)
        await self.insert(self.row(mid, lid))
        async with db.connection() as cx:
            await cx.execute("DELETE FROM listings WHERE id = %s", (lid,))      # cascades to the match
        self.assertEqual(len(await self.rows("SELECT id FROM match_decisions WHERE match_id = %s", mid)), 1)


class ReportTests(MatchDecisionsCase):
    async def test_the_report_cannot_write(self):
        with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
            async with db.connection() as cx:
                await shadow_report.read_only(cx)
                await repo.insert(cx, [self.row(1, 11)])
        self.assertEqual(await self.rows("SELECT id FROM match_decisions"), [])

    async def test_read_and_render(self):
        a = await self.listing(enriched_at=self.now)
        b = await self.listing(year=None)
        ma = await self.match(a, level="high", breakdown={"shadow_f3": {"level": "high"}})
        mb = await self.match(b, breakdown={"shadow_f3": {"level": "match"}})
        ref = {"n": 20, "level_used": "trim", "median": 11_200, "p25": 10_600, "p75": 12_000, "diff_pct": 12.0}
        common = dict(price=10_300, currency="USD", source="mercadolibre", listing_status="active", price_ref=ref,
                      f2_level="good", f2_score=78, f3_params="aaaaaaaaaaaa")
        await self.insert(
            self.row(ma, a, f2_decision="queued", f2_kind="opportunity", f3_level="high", f3_score=90,
                     f3_decision="queued", f3_kind="opportunity", year=2017, title="Fiesta A", **common),
            self.row(mb, b, f2_decision="queued", f2_kind="new_match", f3_level="match", f3_score=60,
                     f3_decision="none", f3_reason="below_min_level", year=None, title="Fiesta B", **common))
        async with db.connection() as cx:
            for mid, lid, kind in ((ma, a, "opportunity"), (mb, b, "new_match")):
                await cx.execute(
                    "INSERT INTO notifications (user_id, match_id, listing_id, search_profile_id, kind, channel, "
                    "  status, dedupe_key, created_at) VALUES (%s, %s, %s, %s, %s, 'telegram', 'sent', %s, now() - interval '1 second')",
                    (self.user, mid, lid, self.profile, kind, f"match:{lid}"))
            await cx.execute("INSERT INTO events (user_id, name, props) VALUES (%s, 'listing_outbound_clicked', %s)",
                             (self.user, Jsonb({"listing_id": a, "source": "mercadolibre"})))
            access = (await (await cx.execute("SELECT public.search_access_active(%s) AS ok",
                                              (self.profile,))).fetchone())["ok"]
        data = await shadow_report.read(since=self.now - timedelta(days=1), until=self.now + timedelta(minutes=1))
        self.assertEqual(sorted(r["match_id"] for r in data.rows), sorted([ma, mb]))
        self.assertEqual(len(data.notifications), 2)
        self.assertEqual(len(data.outbound), 1)
        self.assertEqual(set(data.listings), {a, b})
        self.assertEqual(data.searches[self.profile]["name"], "Sombra f3")
        if access:
            self.assertEqual(data.concentration, [{"search_id": self.profile, "cars": 2, "fire": 1}])
        cands = shadow_report.decisions(data)
        self.assertEqual([(c.f2_sent, c.f3_alert, c.outbound) for c in cands], [(True, True, True), (True, False, False)])
        text = shadow_report.render(data, now=self.now)
        self.assertIn("## Criterios para pasar a real", text)
        self.assertIn(f"| {self.profile} | Sombra f3 | 2 | 2 → 1 | 1 → 1 | 0 | 0 | 0 | 0 |", text)
        # Filters: another search, another parameter hash.
        other = await shadow_report.read(since=self.now - timedelta(days=1), until=self.now + timedelta(minutes=1),
                                         searches=[self.profile + 1])
        self.assertEqual(other.rows, [])
        other = await shadow_report.read(since=None, until=self.now + timedelta(minutes=1), params="bbbbbbbbbbbb")
        self.assertEqual(other.rows, [])
