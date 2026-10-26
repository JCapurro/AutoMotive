"""F2 intelligence against the local Supabase Postgres (docs/TECHNICAL_PLAN.md, sección 6):
the comparables() cascade in SQL, the listings a later complete read no longer
saw (comparable_pool), scored matches, re-scoring and explain_match.
Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres pytest
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from psycopg.types.json import Jsonb

import db
from db.repos import config as app_config
from db.repos import matches as matches_repo
from db.repos import targets as targets_repo
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


class ComparablesConfirmationTests(IntelligenceCase):
    """Comparables fase 1 (migration 20261105120000): a listing of a source in
    app_config.comparables.confirm_sources stops counting once a crawl target
    that covers it ran more than confirm_grace_hours after it was last seen."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        async with db.connection() as cx:
            row = await (await cx.execute("SELECT value FROM app_config WHERE key = 'comparables'")).fetchone()
            self._comparables = row["value"]
            await cx.execute(
                "UPDATE app_config SET value = value - 'gone_max_age_days' || %s WHERE key = 'comparables'",
                (Jsonb({"confirm_sources": ["autocity", "rosariogarage", "deruedas"], "confirm_grace_hours": 36}),))
        app_config.clear_config_cache()

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = %s WHERE key = 'comparables'", (Jsonb(self._comparables),))
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def config(self, sql: str, *params) -> None:
        async with db.connection() as cx:
            await cx.execute(f"UPDATE app_config SET value = {sql} WHERE key = 'comparables'", params)

    async def target(self, source: str, make: str | None = None, model: str | None = None, *,
                     query: dict | None = None, last_run_hours_ago: float = 0,
                     body_type: str | None = None, full_read_hours_ago: float | None = None) -> int:
        """A crawl target whose last complete run was that long ago; without
        make and model, an inventory target (pipeline/crawl.py). Its last read
        of its whole stock (last_full_read_at) is that run, as on a source
        without publication dates, unless `full_read_hours_ago` says when
        (None on Mercado Libre and Facebook: never)."""
        if query is None:
            query = {"inventory": True} if make is None else {}
        if full_read_hours_ago is None and source not in ("mercadolibre", "facebook"):
            full_read_hours_ago = last_run_hours_ago
        async with db.connection() as cx:
            row = await (await cx.execute(
                "INSERT INTO crawl_targets (source, make, model, body_type, query, last_run_at, last_full_read_at, "
                "                           first_run_done) "
                "VALUES (%s, %s, %s, %s, %s, now() - make_interval(secs => %s), "
                "        now() - make_interval(secs => %s), true) RETURNING id",
                (source, make, model, body_type, Jsonb(query), last_run_hours_ago * 3600,
                 None if full_read_hours_ago is None else full_read_hours_ago * 3600))).fetchone()
        return row["id"]

    async def pool(self, listing_id: int) -> set[int]:
        """public.comparable_pool(): what the web lists."""
        async with db.connection() as cx:
            rows = await (await cx.execute("SELECT id FROM comparable_pool(%s)", (listing_id,))).fetchall()
        return {r["id"] for r in rows}

    async def unconfirmed(self, listing_id: int) -> bool:
        async with db.connection() as cx:
            row = await (await cx.execute(
                "SELECT EXISTS (SELECT 1 FROM listings l, app_config c, listing_unconfirmed("
                "  l.source, l.make, l.model, l.year, l.mileage_km, greatest(l.last_seen_at, l.last_full_seen_at), "
                "  c.value->'confirm_sources', "
                "  make_interval(hours => (c.value->>'confirm_grace_hours')::int)) "
                " WHERE l.id = %s AND c.key = 'comparables') AS u", (listing_id,))).fetchone()
        return row["u"]

    async def test_an_inventory_read_that_no_longer_sees_a_listing_drops_it(self):
        target = await self.listing()
        gone_by = await self.listing(source="autocity", last_seen_days_ago=3)
        recent = await self.listing(source="autocity", last_seen_days_ago=1)      # 24 h < 36 h of grace
        await self.target("autocity")

        self.assertEqual(await self.pool(target), {recent})
        self.assertEqual((await self.ref(target, min_n=1)).n, 1)

    async def test_without_a_later_complete_read_nothing_is_dropped(self):
        target = await self.listing()
        old = await self.listing(source="autocity", last_seen_days_ago=10)
        self.assertEqual(await self.pool(target), {old})                         # no crawl target at all
        await self.target("autocity", last_run_hours_ago=9.5 * 24)              # the crawler stopped after it
        await self.target("rosariogarage")                                      # another source's read
        self.assertEqual(await self.pool(target), {old})
        self.assertFalse(await self.unconfirmed(old))

    async def test_a_model_target_only_vouches_for_what_its_query_covers(self):
        await self.target("rosariogarage", "Ford", "Fiesta", query={"year_min": 2014, "km_max": 150_000})
        covered = [await self.listing(source="rosariogarage", year=2016, last_seen_days_ago=3),
                   await self.listing(source="rosariogarage", make="FORD", model="fiesta", year=2015,
                                      last_seen_days_ago=3)]
        cases = {
            "older than year_min": await self.listing(source="rosariogarage", year=2012, last_seen_days_ago=3),
            "unknown year": await self.listing(source="rosariogarage", year=None, last_seen_days_ago=3),
            "km over km_max": await self.listing(source="rosariogarage", mileage_km=160_000, last_seen_days_ago=3),
            "unknown km": await self.listing(source="rosariogarage", mileage_km=None, last_seen_days_ago=3),
            "another model": await self.listing(source="rosariogarage", model="Focus", last_seen_days_ago=3),
        }
        for lid in covered:
            self.assertTrue(await self.unconfirmed(lid))
        for name, lid in cases.items():
            with self.subTest(name):
                self.assertFalse(await self.unconfirmed(lid))

        target = await self.listing(year=2016)
        # 2015 and 2016 leave; the 2017 with unknown km stays (2012, the unknown
        # year and 160.000 km were never comparable to a 2016 with 100.000 km).
        self.assertEqual(await self.pool(target), {cases["unknown km"]})

    async def test_the_year_band_widens_what_a_target_covers(self):
        await self.target("deruedas", "Ford", "Fiesta",
                          query={"year_min": 2014, "year_max": 2016, "year_band": 1})
        for year, unconfirmed in ((2012, False), (2013, True), (2016, True), (2017, True), (2018, False)):
            with self.subTest(year=year):
                lid = await self.listing(source="deruedas", year=year, last_seen_days_ago=3)
                self.assertEqual(await self.unconfirmed(lid), unconfirmed)

    async def test_body_type_targets_are_not_evidence(self):
        target = await self.listing()
        old = await self.listing(source="autocity", last_seen_days_ago=3)
        await self.target("autocity", body_type="hatchback")                    # make/model null, inventory-shaped
        self.assertEqual(await self.pool(target), {old})

    async def test_unlisted_sources_keep_the_whole_window(self):
        target = await self.listing()
        kept = {await self.listing(source=s, last_seen_days_ago=20) for s in ("mercadolibre", "facebook", "v6")}
        expired = await self.listing(source="v6", last_seen_days_ago=45)
        for source in ("mercadolibre", "facebook", "v6"):
            await self.target(source)
            await self.target(source, "Ford", "Fiesta")
        pool = await self.pool(target)
        self.assertEqual(pool, kept)
        self.assertNotIn(expired, pool)

    async def test_a_repost_counts_only_when_its_original_does_not(self):
        target = await self.listing()
        await self.target("autocity")
        original = await self.listing(source="autocity", last_seen_days_ago=3)
        repost = await self.listing(source="autocity", probable_repost_of=original)
        self.assertEqual(await self.pool(target), {repost})                     # the original is unconfirmed

        async with db.connection() as cx:                                       # the original shows up again
            await cx.execute("UPDATE listings SET last_seen_at = now() WHERE id = %s", (original,))
        self.assertEqual(await self.pool(target), {original})

        async with db.connection() as cx:                                       # a repost of the listing itself
            await cx.execute("UPDATE listings SET last_seen_at = now() - interval '3 days' WHERE id = %s",
                             (original,))
        self.assertNotIn(repost, await self.pool(original))

    async def test_without_confirm_sources_nothing_changes(self):
        target = await self.listing()
        old = await self.listing(source="autocity", last_seen_days_ago=10)
        await self.target("autocity")
        self.assertEqual(await self.pool(target), set())
        await self.config("value - 'confirm_sources'")
        self.assertEqual(await self.pool(target), {old})
        self.assertFalse(await self.unconfirmed(old))

    async def test_gone_listings_count_until_gone_max_age_days_says_otherwise(self):
        target = await self.listing()
        recent = await self.listing(status="gone", last_seen_days_ago=3)
        older = await self.listing(status="gone", last_seen_days_ago=10)
        original = await self.listing(status="gone", last_seen_days_ago=10)
        repost = await self.listing(probable_repost_of=original)
        self.assertEqual(await self.pool(target), {recent, older, original})    # Juan's decision (0f348a8)

        await self.config("value || '{\"gone_max_age_days\": 0}'")
        self.assertEqual(await self.pool(target), {repost})
        await self.config("value || '{\"gone_max_age_days\": 7}'")
        self.assertEqual(await self.pool(target), {recent, repost})             # the original stopped counting

    async def test_comparable_pool_is_the_pool_comparables_counts(self):
        target = await self.listing()
        await self.target("autocity")
        await self.target("rosariogarage", "Ford", "Fiesta", query={"year_min": 2014})
        for kw in (dict(source="autocity"), dict(source="autocity", last_seen_days_ago=3),
                   dict(source="rosariogarage", last_seen_days_ago=5), dict(source="rosariogarage", trim="SE"),
                   dict(source="deruedas", last_seen_days_ago=5), dict(last_seen_days_ago=20, status="gone"),
                   dict(transmission="automatic"), dict(year=2019)):
            await self.listing(**kw)
        original = await self.listing(source="autocity", last_seen_days_ago=4)
        await self.listing(source="carone", probable_repost_of=original)

        pool = await self.pool(target)
        ref = await self.ref(target, min_n=1000)
        self.assertEqual(ref.level_used, "model")
        self.assertEqual(ref.n, len(pool))
        self.assertEqual(len(pool), 6)



class ComparablesFullReadTests(ComparablesConfirmationTests):
    """Comparables fase 2 (migration 20261106120000): Mercado Libre's evidence
    is a read of the target's whole stock (crawl.full_read), not its runs."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        await self.config("jsonb_set(value, '{confirm_sources}', value->'confirm_sources' || %s)",
                          Jsonb(["mercadolibre"]))

    async def full_seen(self, listing_id: int, days_ago: float) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET last_full_seen_at = now() - make_interval(secs => %s) "
                             " WHERE id = %s", (days_ago * 86400, listing_id))

    async def crawl_rows(self) -> dict[int, dict]:
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT id, last_run_at, last_full_read_at, "
                "       extract(epoch FROM now() - last_full_read_at) / 3600 AS full_age_h "
                "  FROM crawl_targets")).fetchall()
        return {r["id"]: r for r in rows}

    async def test_a_full_read_that_no_longer_sees_a_car_drops_it(self):
        target = await self.listing(year=2016)
        sold = await self.listing(last_seen_days_ago=10)
        listed = await self.listing(last_seen_days_ago=10)
        new = await self.listing(last_seen_days_ago=1)                          # inside the grace
        await self.full_seen(listed, 0.01)
        await self.target("mercadolibre", "Ford", "Fiesta", query={"year_min": 2015}, full_read_hours_ago=0)
        self.assertEqual(await self.pool(target), {listed, new})
        self.assertTrue(await self.unconfirmed(sold))

    async def test_a_window_run_is_no_evidence(self):
        target = await self.listing(year=2016)
        old = await self.listing(last_seen_days_ago=10)
        await self.target("mercadolibre", "Ford", "Fiesta")                     # ran now, never read it all
        self.assertEqual(await self.pool(target), {old})
        self.assertFalse(await self.unconfirmed(old))

    async def test_a_car_seen_by_a_full_read_still_ages_out_with_its_last_seen(self):
        # last_full_seen_at vouches for the car, it doesn't keep it in the pool:
        # max_age_days still counts from the run that stored it.
        target = await self.listing(year=2016)
        old = await self.listing(last_seen_days_ago=31)
        await self.full_seen(old, 0.01)
        await self.target("mercadolibre", "Ford", "Fiesta", full_read_hours_ago=0)
        self.assertEqual(await self.pool(target), set())

    async def test_a_full_read_inside_the_grace_after_the_car_proves_nothing(self):
        target = await self.listing(year=2016)
        old = await self.listing(last_seen_days_ago=3)
        await self.full_seen(old, 2)                                            # seen by a full read 2 days ago
        await self.target("mercadolibre", "Ford", "Fiesta", full_read_hours_ago=24)
        self.assertEqual(await self.pool(target), {old})

    async def test_finish_target_moves_last_full_read_at_only_on_a_full_read(self):
        never = await self.target("autocity")
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET last_full_read_at = NULL WHERE id = %s", (never,))
        window = await self.target("mercadolibre", "Ford", "Fiesta", last_run_hours_ago=5, full_read_hours_ago=50)
        held = await self.target("deruedas", "Ford", "Fiesta", last_run_hours_ago=5)
        await targets_repo.finish_target(never, ok=True, retry_seconds=0, full_read=True)
        await targets_repo.finish_target(window, ok=True, retry_seconds=0)
        await targets_repo.finish_target(held, ok=True, retry_seconds=0, bootstrap=False, full_read=True)
        rows = await self.crawl_rows()
        self.assertEqual(rows[never]["last_full_read_at"], rows[never]["last_run_at"])
        self.assertGreater(rows[window]["last_run_at"], rows[window]["last_full_read_at"])
        self.assertAlmostEqual(float(rows[window]["full_age_h"]), 50, delta=0.1)  # only a full read moves it
        self.assertAlmostEqual(float(rows[held]["full_age_h"]), 5, delta=0.1)     # a held empty read moves neither

    async def test_record_full_read_vouches_for_what_it_saw_and_dates_a_complete_read(self):
        seen = await self.listing(external_id="seen", last_seen_days_ago=5)
        unseen = await self.listing(external_id="unseen", last_seen_days_ago=5)
        other = await self.listing(source="autocity", external_id="seen", last_seen_days_ago=5)
        tid = await self.target("mercadolibre", "Ford", "Fiesta")
        target = {"id": tid, "source": "mercadolibre"}
        started = datetime.now(timezone.utc) - timedelta(minutes=5)

        self.assertEqual(await targets_repo.record_full_read(target, started, ["seen", "gone-now"],
                                                             complete=False), 1)
        self.assertIsNone((await self.crawl_rows())[tid]["last_full_read_at"])  # an incomplete read proves nothing
        self.assertFalse(await self.unconfirmed(unseen))
        await targets_repo.record_full_read(target, started, ["seen"], complete=True)
        self.assertEqual((await self.crawl_rows())[tid]["last_full_read_at"], started)
        async with db.connection() as cx:
            got = {r["id"]: r["last_full_seen_at"] for r in await (await cx.execute(
                "SELECT id, last_full_seen_at FROM listings WHERE id = ANY(%s)",
                ([seen, unseen, other],))).fetchall()}
        self.assertIsNotNone(got[seen])
        self.assertEqual((got[unseen], got[other]), (None, None))
        self.assertFalse(await self.unconfirmed(seen))
        self.assertTrue(await self.unconfirmed(unseen))


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
        # §25: the questions the web copies are stored with the match.
        self.assertTrue(m["seller_questions"].startswith("Hola, ¿cómo estás? ¿Lo seguís teniendo?"))
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

    async def test_rescore_deletes_a_match_that_no_longer_fits(self):
        lid = await self.listing(price=10_000, price_usd=10_000)
        for p in (10_000, 10_100, 10_200, 10_300, 10_400):
            await self.listing(price=p, price_usd=p)
        aid = await self.fiesta_alert()
        await rematch.run_pending()
        self.assertIsNotNone(await self.match_row(aid, lid))

        async with db.connection() as cx:                               # enrichment: another model
            await cx.execute("UPDATE listings SET model = 'Focus' WHERE id = %s", (lid,))
        await rescore.rescore_listings([lid])
        self.assertIsNone(await self.match_row(aid, lid))

    async def test_edited_search_drops_the_matches_its_new_place_leaves_out(self):
        near = await self.listing(lat=-34.92, lon=-57.95)                  # La Plata
        far = await self.listing(lat=-31.42, lon=-64.19)                   # Córdoba
        aid = await self.fiesta_alert()                                    # no place: the whole country
        await rematch.run_pending()
        self.assertIsNotNone(await self.match_row(aid, far))

        async with db.connection() as cx:                                  # the web adds La Plata, 90 km
            await cx.execute(
                "UPDATE search_profiles SET origin_lat = -34.98902, origin_lon = -58.00259, radius_km = 90, "
                "  rematch_requested_at = now() WHERE id = %s", (aid,))
        await rematch.run_pending()

        self.assertIsNotNone(await self.match_row(aid, near))
        self.assertIsNone(await self.match_row(aid, far))

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
