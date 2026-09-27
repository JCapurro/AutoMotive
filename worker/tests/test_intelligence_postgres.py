"""F2 intelligence against the local Supabase Postgres (docs/TECHNICAL_PLAN.md, sección 6):
the comparables() cascade in SQL, scored matches, re-scoring and explain_match.
Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

import pytest

import db
from db.repos import matches as matches_repo
from intelligence import comparables
from intelligence.config import SCORING_VERSION
from pgcase import TEST_FX_RATE, PostgresTestCase, requires_db
from pipeline import rematch, rescore
from pipeline.scoring import Scorer
from tools import explain_match

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866


class IntelligenceCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._n = 0

    async def listing(self, **kw) -> int:
        """Insert a listing row directly: comparables are about stored columns."""
        self._n += 1
        row = dict(source="mercadolibre", external_id=f"x{self._n}", url=f"https://example.test/{self._n}",
                   title="Ford Fiesta", make="Ford", model="Fiesta", trim="Titanium", year=2017,
                   price=11_000, currency="USD", price_usd=11_000, mileage_km=100_000,
                   transmission="manual", location_text="CABA")
        row.update(kw)
        if row["currency"] == "ARS" and "price_usd" not in kw:
            row["price_usd"] = row["price"] / TEST_FX_RATE
        age = row.pop("last_seen_days_ago", 0)
        cols = list(row)
        async with db.connection() as cx:
            r = await (await cx.execute(
                f"INSERT INTO listings ({', '.join(cols)}, last_seen_at) "
                f"VALUES ({', '.join(['%s'] * len(cols))}, now() - make_interval(days => %s)) RETURNING id",
                [*row.values(), age])).fetchone()
        return r["id"]

    async def ref(self, listing_id: int, **cfg) -> comparables.PriceRef:
        async with db.connection() as cx:
            return await comparables.fetch(cx, listing_id, cfg)

    async def fiesta_alert(self, **filters) -> int:
        f = {"marcas": ["Ford"], "modelos": ["Fiesta"], "sources": ["mercadolibre"]}
        f.update(filters)
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Ford Fiesta", filters=f)
        return aid

    async def match_row(self, profile_id: int, listing_id: int) -> dict | None:
        async with db.connection() as cx:
            return await (await cx.execute(
                "SELECT * FROM matches WHERE search_profile_id = %s AND listing_id = %s",
                (profile_id, listing_id))).fetchone()


class ComparablesCascadeTests(IntelligenceCase):
    """Sección 6.2: trim+transmission → transmission → model, first with n ≥ min_n."""

    async def test_same_trim_and_transmission_when_there_are_enough(self):
        target = await self.listing(price_usd=10_300, price=10_300)
        for p in (11_000, 11_100, 11_200, 11_300, 11_400):
            await self.listing(price=p, price_usd=p)
        for p in (8_000, 8_100, 8_200):
            await self.listing(price=p, price_usd=p, trim="SE")

        ref = await self.ref(target)

        self.assertEqual((ref.level_used, ref.n, ref.median), ("trim_transmission", 5, 11_200.0))
        self.assertEqual((ref.p25, ref.p75), (11_100.0, 11_300.0))
        self.assertEqual(ref.median_km, 100_000)
        self.assertAlmostEqual(ref.diff_pct, 8.04, places=2)

    async def test_falls_back_to_transmission_then_model(self):
        target = await self.listing()
        for p in (11_000, 11_100):
            await self.listing(price=p, price_usd=p)
        for p in (9_000, 9_100, 9_200):
            await self.listing(price=p, price_usd=p, trim="SE")
        for p in (12_000, 12_100):
            await self.listing(price=p, price_usd=p, transmission="automatic")

        self.assertEqual((await self.ref(target)).level_used, "transmission")
        self.assertEqual((await self.ref(target)).n, 5)
        ref = await self.ref(target, min_n=6)
        self.assertEqual((ref.level_used, ref.n), ("model", 7))

    async def test_unknown_trim_or_transmission_skips_those_levels(self):
        target = await self.listing(trim=None, transmission=None)
        for p in (11_000, 11_100, 11_200, 11_300, 11_400):
            await self.listing(price=p, price_usd=p)
        self.assertEqual((await self.ref(target)).level_used, "model")

    async def test_never_enough_returns_the_model_level_with_its_n(self):
        target = await self.listing()
        await self.listing()
        ref = await self.ref(target)
        self.assertEqual((ref.level_used, ref.n), ("model", 1))
        self.assertFalse(ref.enough(5))

    async def test_what_is_not_comparable(self):
        target = await self.listing(price=10_000, price_usd=10_000)
        await self.listing(year=2020)                                   # year out of ±1
        await self.listing(mileage_km=200_000)                          # km out of ±25%
        await self.listing(last_seen_days_ago=45)                       # not seen in 30 days
        await self.listing(price_partial=True)
        original = await self.listing()
        await self.listing(probable_repost_of=original)
        await self.listing(model="Focus")
        await self.listing(currency="ARS", price=12_000_000)            # counted, in USD: 12.000
        await self.listing(make="ford", model="FIESTA", mileage_km=None)  # case-insensitive; unknown km ok

        ref = await self.ref(target, min_n=1)
        self.assertEqual((ref.level_used, ref.n), ("trim_transmission", 3))
        self.assertEqual(ref.median, 11_000.0)


class ScoredMatchesTests(IntelligenceCase):
    async def test_bootstrap_matches_an_ars_listing_against_a_usd_cap(self):
        cheap = await self.listing(currency="ARS", price=10_300_000)              # USD 10.300
        dear = await self.listing(currency="ARS", price=12_000_000)               # USD 12.000
        aid = await self.fiesta_alert(precio_max=11_500, moneda="USD")

        await rematch.run_pending()

        m = await self.match_row(aid, cheap)
        self.assertIsNotNone(m)
        self.assertEqual(m["match_reasons"]["price"]["detail"], "ARS 10.300.000 ≈ USD 10.300 ≤ USD 11.500")
        self.assertTrue(m["is_backfill"])
        self.assertEqual(m["scoring_version"], SCORING_VERSION)
        self.assertIsNone(await self.match_row(aid, dear))

    async def test_legacy_matches_are_rescored_and_enrichment_lifts_an_unknown(self):
        lid = await self.listing(transmission=None)
        for p in (11_000, 11_100, 11_200, 11_300, 11_400):
            await self.listing(price=p, price_usd=p, transmission=None)
        aid = await self.fiesta_alert(transmision="Manual")
        async with db.connection() as cx:
            await cx.execute("UPDATE search_profiles SET bootstrapped_at = now()")
        await db.mark_seen(aid, [{"source": "mercadolibre", "listing_id": "x1"}], backfill=True)
        self.assertEqual((await self.match_row(aid, lid))["scoring_version"], "legacy-v0")

        self.assertEqual(await rescore.rescore_outdated(), 1)
        before = await self.match_row(aid, lid)
        self.assertEqual(before["scoring_version"], SCORING_VERSION)
        self.assertEqual(before["match_reasons"]["transmission"]["result"], "unknown")
        self.assertTrue(before["is_backfill"])                          # kept on re-score

        async with db.connection() as cx:                               # enrichment found it
            await cx.execute("UPDATE listings SET transmission = 'manual' WHERE id = %s", (lid,))
        await rescore.rescore_listings([lid])
        after = await self.match_row(aid, lid)
        self.assertEqual(after["match_reasons"]["transmission"]["result"], "ok")
        self.assertGreater(after["score"], before["score"])

    async def test_nightly_rescore_follows_the_market(self):
        lid = await self.listing(price=10_000, price_usd=10_000)
        for p in (10_000, 10_100, 10_200, 10_300, 10_400):
            await self.listing(price=p, price_usd=p)
        aid = await self.fiesta_alert()
        await rematch.run_pending()
        before = await self.match_row(aid, lid)

        for p in (13_000, 13_100, 13_200, 13_300, 13_400, 13_500):     # the median moves up
            await self.listing(price=p, price_usd=p)
        queue = await matches_repo.rescore_queue(days=14, scoring_version=SCORING_VERSION)
        self.assertIn(lid, [q["listing_id"] for q in queue])
        await rescore.rescore_recent()

        after = await self.match_row(aid, lid)
        self.assertGreater(after["price_ref"]["median"], before["price_ref"]["median"])
        self.assertGreater(after["score"], before["score"])
        self.assertEqual(after["generated_at"], before["generated_at"])

    async def test_explain_match_renders_reasons_breakdown_flags_and_questions(self):
        lid = await self.listing(price=10_300, price_usd=10_300)
        for p in (11_000, 11_100, 11_200, 11_300, 11_400):
            await self.listing(price=p, price_usd=p)
        aid = await self.fiesta_alert(km_max=150_000)
        await rematch.run_pending()
        m = await self.match_row(aid, lid)

        stored, profile_id, listing_id = await explain_match.load(m["id"], None, None)
        [alert] = await db.repos.profiles.profiles_by_ids([profile_id])
        scorer = await Scorer.create()
        rows = await scorer.prepare([listing_id])
        data = explain_match.explain(rows[listing_id], alert["profile"], scorer)
        text = explain_match.render(data, stored)

        self.assertTrue(data["is_match"])
        self.assertEqual(data["score"], m["score"])
        self.assertIn("MATCH", text)
        self.assertIn("✅ km", text)
        self.assertIn("Comparables (trim_transmission, n=5)", text)
        self.assertIn(f"Opportunity Score {m['score']}", text)
        self.assertIn("Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular?", text)
        self.assertIn(f"Guardado (match #{m['id']})", text)
