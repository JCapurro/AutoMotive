"""The f3 shadow's decision log against the local Supabase Postgres (spec
docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §4.4, §11.3; migration
20261212120000_score_f3_shadow): a crawl batch through scheduler.process_batch with score_model_f3 off and
then shadow gives the same f2 outputs (matches but for score_breakdown.shadow_f3, notifications byte for
byte) and, in shadow, one 'card' row per candidate with f2's real decision; a retried batch adds nothing;
the enrichment re-score (enrich.rescore_changed) writes one 'deferred' row and the sweeper one 'sweeper'
row, once each. Skipped while the migration is not applied to the test database (`python -m tools.test_db`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from db.repos import match_decisions as repo
from db.repos.listings import rows_for_scoring
from intelligence.config import DEFAULT_SCORE_MODEL_F3
from notifications import decision_log
from notifications.service import MatchCandidate
from pgcase import _TRUNCATE, requires_db
from pipeline import enrich, scheduler
from pipeline.ingest import IngestResult, ListingEvent
from test_notifications_postgres import NotificationsCase

pytestmark = [pytest.mark.db, requires_db]

TARGET = {"id": None, "source": "mercadolibre", "make": "Ford", "model": "Fiesta", "body_type": None, "query": {}}
MATCH_COLUMNS = ("id", "search_profile_id", "listing_id", "score", "level", "score_breakdown", "match_reasons",
                 "red_flags", "price_ref", "scoring_version", "is_backfill", "margin_ref", "seller_questions",
                 "contact_questions", "question_origins")


class DecisionLogCase(NotificationsCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            missing = not await repo.available(cx)
        if missing:
            await db.close_pool()          # a skip in setUp does not run asyncTearDown
            self.skipTest("match_decisions missing: apply the migration and re-run `python -m tools.test_db`")
        decision_log.reset()
        self.addCleanup(decision_log.reset)
        # Decisions only: nothing is delivered, so the notifications keep the payload they were decided with.
        self.notifier.deliver = AsyncMock(return_value=0)
        self.published = datetime.now(timezone.utc) - timedelta(minutes=5)
        [row] = await self.rows("SELECT value FROM app_config WHERE key = 'score_model_f3'")
        self._f3_original = row["value"]

    async def asyncTearDown(self) -> None:
        if getattr(self, "_f3_original", None) is not None:
            async with db.connection() as cx:
                await cx.execute("UPDATE app_config SET value = %s WHERE key = 'score_model_f3'",
                                 (Jsonb(self._f3_original),))
            app_config.clear_config_cache()
        await super().asyncTearDown()

    async def mode(self, mode: str) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = %s WHERE key = 'score_model_f3'",
                             (Jsonb({**DEFAULT_SCORE_MODEL_F3, **self._f3_original, "mode": mode}),))
        app_config.clear_config_cache()
        decision_log.reset()

    async def market(self) -> None:
        """Twelve comparables around USD 11.550, seen today, not news."""
        for i, price in enumerate(range(11_000, 12_200, 100)):
            await self.listing(transmission="manual", price=price, price_usd=price, mileage_km=100_000 + 1_000 * i,
                               published_at=self.published - timedelta(days=20),
                               first_seen_at=self.published - timedelta(days=20))

    async def fresh(self, **kw) -> int:
        return await self.listing(transmission="manual", published_at=self.published, first_seen_at=self.published,
                                  **kw)

    async def crawl(self, *ids: int) -> None:
        await scheduler.process_batch(self.notifier, TARGET, list(ids), first_run=False)

    async def decisions(self, phase: str | None = None) -> list[dict]:
        where = "WHERE phase = %s" if phase else ""
        return await self.rows(f"SELECT * FROM match_decisions {where} ORDER BY id", *([phase] if phase else []))

    async def prefer_private(self) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET preferences = preferences || '{\"seller_type\": \"private\"}' "
                             " WHERE id = %s", (self.profile,))


class F2InvarianceTests(DecisionLogCase):
    async def reset(self) -> None:
        """A clean slate with the same ids (RESTART IDENTITY): the profile, then the same listings."""
        async with db.connection() as cx:
            await cx.execute(f"TRUNCATE {_TRUNCATE}, match_decisions RESTART IDENTITY CASCADE")
            await cx.execute("DELETE FROM auth.users WHERE raw_app_meta_data->>'provider' = 'telegram' "
                             "   OR email LIKE '%automotive.test'")
        app_config.clear_config_cache()
        self._n = 0
        self.profile = await self.alert()
        self.user = await self.user_of(self.profile)

    async def batch(self, mode: str) -> dict:
        await self.reset()
        await self.mode(mode)
        await self.market()
        ids = [await self.fresh(price=9_300, price_usd=9_300),                       # ~20 % below
               await self.fresh(price=11_600, price_usd=11_600, mileage_km=90_000),   # at the median
               await self.fresh(price=11_111, price_usd=11_111),                     # a placeholder-looking price
               await self.fresh(price=5_400, price_usd=5_400),                       # 50 %+ below: suspicious
               await self.fresh(price=10_500, price_usd=10_500, year=None)]          # no year
        await self.crawl(*ids)
        matches = await self.rows(f"SELECT {', '.join(MATCH_COLUMNS)} FROM matches ORDER BY id")
        notifications = await self.rows(
            "SELECT id, kind::text AS kind, channel::text AS channel, status::text AS status, dedupe_key, "
            "       listing_id, match_id, search_profile_id, payload FROM notifications ORDER BY id")
        return {"ids": ids, "matches": matches, "notifications": notifications, "decisions": await self.decisions()}

    async def test_the_same_f2_outputs_with_mode_off_and_shadow(self):
        off = await self.batch("off")
        shadow = await self.batch("shadow")
        self.assertEqual(off["ids"], shadow["ids"])
        self.assertGreaterEqual(len(off["matches"]), 5)
        self.assertGreaterEqual(len(off["notifications"]), 2)
        for m in off["matches"]:
            self.assertNotIn("shadow_f3", m["score_breakdown"])
        stripped = []
        for m in shadow["matches"]:
            breakdown = dict(m["score_breakdown"])
            self.assertIn("shadow_f3", breakdown, m["listing_id"])
            breakdown.pop("shadow_f3")
            stripped.append({**m, "score_breakdown": breakdown})
        self.assertEqual(stripped, off["matches"])
        self.assertEqual(shadow["notifications"], off["notifications"])
        self.assertEqual(off["decisions"], [])
        for n in shadow["notifications"]:
            self.assertEqual(set(n["payload"]["match"]), {"score", "level", "diff_pct", "scoring_version", "price_ref"})

    async def test_one_card_row_per_candidate_with_the_decision_f2_took(self):
        got = await self.batch("shadow")
        fresh = [m for m in got["matches"] if not m["is_backfill"]]
        cards = got["decisions"]
        self.assertEqual(sorted(r["match_id"] for r in cards), sorted(m["id"] for m in fresh))
        self.assertEqual({r["phase"] for r in cards}, {"card"})
        sent = {n["listing_id"]: n["kind"] for n in got["notifications"]}
        by_id = {m["id"]: m for m in fresh}
        for r in cards:
            m = by_id[r["match_id"]]
            with self.subTest(listing=r["listing_id"]):
                self.assertEqual((r["f2_score"], r["f2_level"], r["f2_version"]),
                                 (m["score"], m["level"], m["scoring_version"]))
                self.assertEqual(r["f2_breakdown"], {k: v for k, v in m["score_breakdown"].items() if k != "shadow_f3"})
                self.assertEqual(r["f3"], m["score_breakdown"]["shadow_f3"])
                self.assertEqual(r["f3_level"], m["score_breakdown"]["shadow_f3"]["level"])
                if r["f2_decision"] in ("queued", "digest"):
                    self.assertEqual(sent.get(r["listing_id"]), r["f2_kind"])
                else:
                    self.assertNotIn(r["listing_id"], sent)
                self.assertEqual(r["price_ref"], {k: m["price_ref"][k] for k in decision_log.PRICE_REF_KEYS})
                self.assertEqual((str(r["user_id"]), r["listing_status"], r["enriched"]), (self.user, "active", False))
                self.assertEqual(r["red_flags"], [f["id"] for f in m["red_flags"]])
                self.assertTrue(r["f3_decides"])                         # no seller preference: nothing to wait for
                self.assertIsNotNone(r["audience"])
        placeholder = next(r for r in cards if r["price"] == 11_111)
        self.assertTrue(placeholder["placeholder"])
        self.assertIn("placeholder_price", placeholder["f3_flags"])

    async def test_a_retried_batch_adds_nothing(self):
        got = await self.batch("shadow")
        before = await self.decisions()
        await self.crawl(*got["ids"])                                   # the same batch again: nothing fresh
        matches = await self.rows("SELECT * FROM matches WHERE NOT is_backfill ORDER BY id")
        async with db.connection() as cx:
            rows = await rows_for_scoring(cx, [m["listing_id"] for m in matches])
        again = [MatchCandidate(m["search_profile_id"], m["listing_id"], m["id"], m) for m in matches]
        await self.notifier.on_matches(again, rows)                     # the Notifier's call retried
        self.assertEqual(await self.decisions(), before)


class DetailPhaseTests(DecisionLogCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await self.mode("shadow")
        await self.market()
        await self.prefer_private()
        # A card without a seller: the search prefers a private seller, so f3 would wait for the detail.
        self.lid = await self.fresh(price=9_300, price_usd=9_300, seller_type=None)
        await self.crawl(self.lid)
        [self.card] = await self.decisions("card")
        self.assertTrue(self.card["would_defer"])
        self.assertFalse(self.card["f3_decides"])

    async def detail(self) -> int:
        """The detail page says «particular», and its text an agency's; then the enrichment re-score."""
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET seller_type = 'private', enriched_at = now(), "
                             "  description = 'Impecable. Recibimos tu usado y financiamos.' WHERE id = %s",
                             (self.lid,))
        result = IngestResult(events=[ListingEvent("listing_updated", self.lid, "mercadolibre", "n13")])
        return await enrich.rescore_changed(result)

    async def test_the_enrichment_re_score_writes_one_deferred_row(self):
        self.assertEqual(await self.detail(), 1)
        [d] = await self.decisions("deferred")
        [m] = await self.rows("SELECT * FROM matches WHERE id = %s", self.card["match_id"])
        self.assertEqual((d["f2_decision"], d["f2_reason"], d["f3_decides"]), (None, "f2_card_only", True))
        self.assertEqual(d["f3"], m["score_breakdown"]["shadow_f3"])
        self.assertEqual(d["agency_voice"], "recibimos tu usado")
        # The search only states the seller: a confirmed agency is a failed preference (fit 0.4), «match»
        # already without the cap; the voice is what moved it (decision 2's alternative logged).
        self.assertTrue(d["f3"]["seller"]["mismatch"])
        self.assertEqual((d["f3_level"], d["f3_decision"], d["f3_reason"]), ("match", "none", "below_min_level"))
        self.assertEqual(d["f3"]["alternatives"]["agency_voice_off"]["level"], "high")
        self.assertEqual(d["f2_level"], m["level"])                     # f2 keeps its own reading
        self.assertEqual((d["seller_type"], d["enriched"], d["would_defer"]), ("private", True, False))
        self.assertEqual(d["audience"], self.card["audience"])
        await self.detail()                                             # read again: still one
        self.assertEqual(len(await self.decisions("deferred")), 1)
        self.assertEqual(await decision_log.sweep(now=datetime.now(timezone.utc) + timedelta(minutes=25)), 0)
        self.assertEqual(await self.decisions("sweeper"), [])

    async def test_the_sweeper_decides_what_still_waits(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(await decision_log.sweep(now=now + timedelta(minutes=10)), 0)      # not 20 min yet
        self.assertEqual(await decision_log.sweep(now=now + timedelta(minutes=25)), 1)
        self.assertEqual(await decision_log.sweep(now=now + timedelta(minutes=26)), 0)
        [s] = await self.decisions("sweeper")
        self.assertEqual((s["match_id"], s["f3_decides"], s["f2_reason"]),
                         (self.card["match_id"], True, "f2_card_only"))
        self.assertIn("seller_unknown", s["f3_flags"])
        await self.detail()                                             # the detail after the sweeper
        [d] = await self.decisions("deferred")
        self.assertFalse(d["f3_decides"])

    async def test_nothing_with_mode_off(self):
        await self.mode("off")
        await self.detail()
        self.assertEqual(await decision_log.sweep(now=datetime.now(timezone.utc) + timedelta(minutes=25)), 0)
        self.assertEqual([r["phase"] for r in await self.decisions()], ["card"])
        [m] = await self.rows("SELECT score_breakdown FROM matches WHERE id = %s", self.card["match_id"])
        self.assertNotIn("shadow_f3", m["score_breakdown"])            # the re-score with mode off: f2 only
