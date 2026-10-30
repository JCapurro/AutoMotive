"""F-02 against the local Supabase Postgres
(docs/superpowers/specs/2026-10-30-f02-vendedor-design.md). Paso 1: the ingest
repo writes seller_key, and the seller classification job writes
seller_listing_count without touching anything else. Paso 2: the same job and
the ingest write dealer_inferred («posible agencia»), the matches of a listing
that flips are re-scored right away, and enabled = false turns it all off. Run with
    TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest -m db
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from psycopg.types.json import Jsonb

import db
from collectors.base import Listing
from db.repos import config as app_config
from db.repos import sellers
from pgcase import PostgresTestCase, requires_db
from intelligence.config import SCORING_VERSION
from notifications.channels.telegram import TelegramChannel
from notifications.channels.web import WebChannel
from notifications.links import Links
from notifications.service import Notifier
from pipeline import rematch, rescore, scheduler
from pipeline.ingest import ingest
from pipeline.seller_classification import backfill_keys, classify_groups, classify_sellers
from test_ingest_postgres import _FakeBot

pytestmark = [pytest.mark.db, requires_db]

TG_USER = 864987866
SPELLINGS = ("Juan Pérez", "juan perez", "JUAN PEREZ", "Juan  Pérez.", "juan-pérez", "  Juan Perez!! ")


def card(listing_id: str, **kw) -> Listing:
    base = dict(source="mercadolibre", listing_id=listing_id, titulo=f"Ford Fiesta Titanium {listing_id}",
                url=f"https://example.test/mercadolibre/{listing_id}", precio=10_000.0, moneda="USD",
                anio=2017, km=100_000)
    base.update(kw)
    return Listing(**base)


class SellerCase(PostgresTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self._n = 0
        async with db.connection() as cx:
            row = await (await cx.execute(
                "SELECT value FROM app_config WHERE key = 'seller_classification'")).fetchone()
        self._saved = row["value"] if row else None

    async def asyncTearDown(self) -> None:
        async with db.connection() as cx:
            if self._saved is None:
                await cx.execute("DELETE FROM app_config WHERE key = 'seller_classification'")
            else:
                await cx.execute(
                    "INSERT INTO app_config (key, value) VALUES ('seller_classification', %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (Jsonb(self._saved),))
        app_config.clear_config_cache()
        await super().asyncTearDown()

    async def set_config(self, value) -> None:
        async with db.connection() as cx:
            await cx.execute("UPDATE app_config SET value = %s WHERE key = 'seller_classification'",
                             (Jsonb(value),))
        app_config.clear_config_cache()

    async def listing(self, seller_name: str | None = "Juan Pérez", *, days_ago: float = 1, **kw) -> int:
        """A listing inserted directly, first seen `days_ago`, without a seller
        key: the run fills the keys of the active ones."""
        self._n += 1
        row = dict(source="mercadolibre", external_id=f"s{self._n}", url=f"https://example.test/s{self._n}",
                   title="Ford Fiesta", make="Ford", model="Fiesta", trim="Titanium", year=2017,
                   price=11_000 + self._n, currency="USD", price_usd=11_000 + self._n, mileage_km=100_000,
                   transmission="manual", location_text="CABA", seller_name=seller_name,
                   fingerprint=f"fp{self._n}")
        row.update(kw)
        cols = list(row)
        async with db.connection() as cx:
            r = await (await cx.execute(
                f"INSERT INTO listings ({', '.join(cols)}, first_seen_at) "
                f"VALUES ({', '.join(['%s'] * len(cols))}, now() - make_interval(secs => %s)) RETURNING id",
                [*row.values(), days_ago * 86_400])).fetchone()
        return r["id"]

    async def rows(self, *ids: int) -> dict[int, dict]:
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT * FROM listings WHERE id = ANY(%s) ORDER BY id", (list(ids),))).fetchall()
        return {r["id"]: r for r in rows}

    async def counts(self, *ids: int) -> list[int | None]:
        rows = await self.rows(*ids)
        return [rows[i]["seller_listing_count"] for i in ids]

    async def runs(self) -> list[dict]:
        async with db.connection() as cx:
            return await (await cx.execute("SELECT * FROM seller_classification_runs ORDER BY id")).fetchall()

    async def snapshot_count(self) -> int:
        async with db.connection() as cx:
            return (await (await cx.execute("SELECT count(*) AS n FROM listing_snapshots")).fetchone())["n"]

    async def inferred(self, *ids: int) -> list[bool]:
        rows = await self.rows(*ids)
        return [rows[i]["dealer_inferred"] for i in ids]

    async def private_alert(self) -> int:
        """A Fiesta search that prefers a private seller (soft preference)."""
        f = {"marcas": ["Ford"], "modelos": ["Fiesta"], "sources": ["mercadolibre"], "vendedor": "particular"}
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Fiesta", filters=f)
        return aid

    async def seller_reasons(self, aid: int) -> dict[int, dict]:
        """listing_id -> the seller_type reason of its match in this search."""
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT listing_id, match_reasons, scoring_version FROM matches "
                " WHERE search_profile_id = %s ORDER BY listing_id", (aid,))).fetchall()
        return {r["listing_id"]: {**r["match_reasons"]["seller_type"], "version": r["scoring_version"]}
                for r in rows}


class SellerKeyIngestTests(SellerCase):
    async def test_ingest_writes_the_key_from_the_merged_name(self):
        await ingest([card("k1", vendedor_nombre="Juan Pérez")], geocode=None)
        [row] = (await self.rows(1)).values()
        self.assertEqual((row["seller_name"], row["seller_key"]), ("Juan Pérez", "juan perez"))
        # Paso 2: the ingest counts the group it touched.
        self.assertEqual((row["seller_listing_count"], row["dealer_inferred"]), (1, False))
        snapshots = await self.snapshot_count()

        # Seen again without a name: merge keeps the stored one, and so the key.
        await ingest([card("k1", vendedor_nombre=None)], geocode=None)
        row = (await self.rows(1))[1]
        self.assertEqual((row["seller_name"], row["seller_key"]), ("Juan Pérez", "juan perez"))
        self.assertEqual(await self.snapshot_count(), snapshots, "the key creates no snapshot")

        await ingest([card("k1", vendedor_nombre="Autos S.A.")], geocode=None)
        row = (await self.rows(1))[1]
        self.assertEqual((row["seller_key"], row["seller_listing_count"]), ("autos sa", 1))

        await ingest([card("k2", vendedor_nombre="Dueño directo")], geocode=None)
        row = (await self.rows(2))[2]
        self.assertEqual((row["seller_name"], row["seller_key"], row["seller_listing_count"]),
                         ("Dueño directo", None, None))

    async def test_an_update_without_the_name_leaves_the_key(self):
        await ingest([card("k1", vendedor_nombre="Juan Pérez")], geocode=None)
        from db.repos import listings as repo
        async with db.connection() as cx:
            await repo.update_listing(cx, 1, {"title": "Ford Fiesta Titanium"}, seen=False)
        self.assertEqual((await self.rows(1))[1]["seller_key"], "juan perez")


class ClassifySellersTests(SellerCase):
    async def test_six_spellings_of_one_seller_count_six_on_every_row(self):
        ids = [await self.listing(name) for name in SPELLINGS]
        other = await self.listing("Autos S.A.")
        await self.listing("Autos SA", status="gone")                 # gone: not counted

        result = await classify_sellers("cli")

        rows = await self.rows(*ids, other)
        self.assertEqual({rows[i]["seller_key"] for i in ids}, {"juan perez"})
        self.assertEqual(await self.counts(*ids), [6] * 6)
        self.assertEqual(rows[other]["seller_key"], "autos sa")
        self.assertEqual(rows[other]["seller_listing_count"], 1)
        self.assertEqual((result["rows_read"], result["rows_written"], result["keys_filled"]), (7, 7, 7))

    async def test_one_car_published_twice_counts_once(self):
        a = await self.listing(fingerprint="same")
        b = await self.listing(fingerprint="same")
        c = await self.listing()
        nofp = await self.listing(fingerprint=None)
        await classify_sellers("cli")
        self.assertEqual(await self.counts(a, b, c, nofp), [3, 3, 3, 3])

    async def test_a_repost_does_not_add_while_its_original_counts(self):
        original = await self.listing()
        repost = await self.listing(probable_repost_of=original)          # its own fingerprint
        third = await self.listing()
        await classify_sellers("cli")
        self.assertEqual(await self.counts(original, repost, third), [2, 2, 2])

    async def test_a_repost_is_never_the_copy_that_goes_missing(self):
        """Review NEW-A: the repost counts when its original is gone, out of
        the window or another seller's: it is the only live copy here."""
        gone = await self.listing(status="gone")
        old = await self.listing(days_ago=40)
        other = await self.listing("Autos SA")
        r1 = await self.listing(probable_repost_of=gone)
        r2 = await self.listing(probable_repost_of=old)
        r3 = await self.listing(probable_repost_of=other)
        await classify_sellers("cli")
        self.assertEqual(await self.counts(old, r1, r2, r3), [3, 3, 3, 3])
        self.assertEqual(await self.counts(other), [1])

    async def test_the_window_is_publication_or_first_seen(self):
        recent = [await self.listing() for _ in range(2)]
        published_old = await self.listing(published_at=datetime.now(timezone.utc) - timedelta(days=40))
        seen_old = await self.listing(days_ago=40)                            # no published_at
        # Published recently, first seen long ago: the publication date wins.
        republished = await self.listing(days_ago=40, published_at=datetime.now(timezone.utc) - timedelta(days=2))
        lonely_old = await self.listing("Autos SA", days_ago=45)

        await classify_sellers("cli")
        self.assertEqual(await self.counts(*recent, published_old, seen_old, republished), [3] * 5)
        self.assertEqual(await self.counts(lonely_old), [None], "nothing in the window: no count")

        await self.set_config({"enabled": True, "min_listings": 6, "window_days": 50})
        await classify_sellers("cli")
        self.assertEqual(await self.counts(*recent, published_old, seen_old, republished), [5] * 5)
        self.assertEqual(await self.counts(lonely_old), [1])

    async def test_a_bad_window_falls_back_to_30_days(self):
        a = await self.listing()
        await self.listing(days_ago=40)
        await self.set_config({"enabled": True, "min_listings": 6, "window_days": "50"})
        result = await classify_sellers("cli")
        self.assertEqual(result["params"], {"enabled": True, "min_listings": 6, "window_days": 30})
        self.assertEqual(await self.counts(a), [1])

    async def test_generic_names_get_no_key_and_no_count(self):
        ids = [await self.listing(name) for name in ("Particular", "Dueño directo", "WhatsApp", None, "ab")]
        await classify_sellers("cli")
        rows = await self.rows(*ids)
        self.assertEqual([(rows[i]["seller_key"], rows[i]["seller_listing_count"]) for i in ids],
                         [(None, None)] * 5)

    async def test_only_the_count_changes(self):
        ids = [await self.listing(name, seller_type=t, attributes=Jsonb({"x": 1}))
               for name, t in (("Juan Pérez", "private"), ("JUAN PEREZ", None), ("Juan Perez", "dealer"))]
        gone = await self.listing(status="gone", seller_listing_count=9)
        async with db.connection() as cx:
            await cx.execute("INSERT INTO listing_snapshots (listing_id, price, currency, change_kind, attrs_hash) "
                             "SELECT id, price, currency, 'new', 'h' FROM listings")
        before = await self.rows(*ids, gone)
        snapshots = await self.snapshot_count()

        await classify_sellers("cli")

        after = await self.rows(*ids, gone)
        for i in ids:
            self.assertEqual(after[i]["seller_listing_count"], 3)
            for col in ("seller_type", "seller_name", "attributes", "fingerprint", "last_seen_at", "status"):
                self.assertEqual(after[i][col], before[i][col], col)
        self.assertEqual(after[gone], before[gone], "a gone listing is left alone")
        self.assertEqual(after[gone]["seller_listing_count"], 9)
        self.assertEqual(await self.snapshot_count(), snapshots)

    async def test_a_second_run_writes_nothing_and_both_are_recorded(self):
        for name in SPELLINGS[:3]:
            await self.listing(name)
        await classify_sellers("cli")
        await classify_sellers("nightly")

        first, second = await self.runs()
        self.assertEqual((first["trigger"], first["mode"], first["status"]), ("cli", "write", "ok"))
        self.assertEqual((first["rows_read"], first["rows_written"]), (3, 3))
        self.assertEqual(first["params"], {"enabled": True, "min_listings": 6, "window_days": 30})
        self.assertIsNotNone(first["finished_at"])
        self.assertEqual((second["trigger"], second["rows_read"], second["rows_written"]), ("nightly", 3, 0))
        self.assertEqual((first["inferred_changed"], second["inferred_changed"]), (0, 0))

    async def test_a_group_that_shrinks_or_loses_its_key_is_rewritten(self):
        a, b, c = [await self.listing() for _ in range(3)]
        await classify_sellers("cli")
        self.assertEqual(await self.counts(a, b, c), [3, 3, 3])

        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (c,))
            await cx.execute("UPDATE listings SET seller_name = NULL, seller_key = NULL WHERE id = %s", (b,))
        await classify_sellers("cli")
        self.assertEqual(await self.counts(a, b, c), [1, None, 3])

    async def test_dry_run_writes_no_listing_and_reports(self):
        ids = [await self.listing(name) for name in SPELLINGS]
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET seller_key = 'juan perez'")
        await self.listing("Autos SA", seller_key="autos sa")

        result = await classify_sellers("cli", dry_run=True, report=True)

        self.assertEqual(await self.counts(*ids), [None] * 6)
        self.assertEqual(result["would_write"], 7)
        [src] = result["sources"]
        self.assertEqual((src["source"], src["active"], src["groups"], src["over_threshold"]),
                         ("mercadolibre", 7, 2, 6))
        self.assertEqual(src["top"][0]["key"], "juan perez")
        self.assertEqual(src["top"][0]["n"], 6)
        self.assertEqual(len(src["top"][0]["names"]), 5, "up to 5 raw names")
        [run] = await self.runs()
        self.assertEqual((run["mode"], run["status"], run["rows_read"], run["rows_written"]),
                         ("dry_run", "ok", 7, None))

    async def test_a_failed_run_is_recorded_and_raised(self):
        await self.listing()
        with patch.object(sellers, "write_groups", AsyncMock(side_effect=RuntimeError("boom"))):
            with self.assertRaises(RuntimeError):
                await classify_sellers("startup")
        [run] = await self.runs()
        self.assertEqual((run["trigger"], run["status"]), ("startup", "failed"))
        self.assertIn("boom", run["error"])

    async def test_batches_of_groups_cover_every_group(self):
        names = [f"Vendedor {i:02d}" for i in range(5)]
        ids = [await self.listing(n) for n in names for _ in range(2)]
        with patch.object(sellers, "GROUP_BATCH", 2):
            await classify_sellers("cli")
        self.assertEqual(await self.counts(*ids), [2] * 10)

    async def test_backfill_keys_in_batches_covers_active_and_gone(self):
        active = [await self.listing(n) for n in ("Juan Pérez", "Autos S.A.", "0341 15 555-1234")]
        gone = await self.listing("+54 9 341 555-1234", status="gone")
        stale = await self.listing(None, seller_key="old key")
        result = await backfill_keys(batch=2)
        rows = await self.rows(*active, gone, stale)
        self.assertEqual([rows[i]["seller_key"] for i in (*active, gone, stale)],
                         ["juan perez", "autos sa", "tel:3415551234", "tel:3415551234", None])
        self.assertEqual(result, {"batches": 3, "rows_written": 5})
        self.assertEqual((await backfill_keys(batch=2))["rows_written"], 0)
        self.assertEqual(await self.runs(), [], "the backfill is no classification run")


class DisabledNoScoreChangeTests(SellerCase):
    async def test_with_enabled_false_the_anchor_slot_leaves_matches_as_rescore_recent_alone(self):
        """Paso 1's guarantee, now the off switch's: counts but no inference,
        and no score moves."""
        await self.set_config({"enabled": False, "min_listings": 6, "window_days": 30})
        for p in (10_000, 10_100, 10_200, 10_300, 10_400, 10_500):
            await self.listing(None, price=p, price_usd=p, seller_type="private")
        for name in SPELLINGS:
            await self.listing(name, price=9_500, price_usd=9_500, seller_type="private")
        f = {"marcas": ["Ford"], "modelos": ["Fiesta"], "sources": ["mercadolibre"], "vendedor": "particular"}
        [aid] = await db.create_alert(user_id=TG_USER, chat_id=TG_USER, name="Fiesta", filters=f)
        await rematch.run_pending()

        await rescore.rescore_recent()
        alone = await self._matches(aid)
        self.assertEqual(len(alone), 12)
        self.assertEqual(alone[-1][3]["seller_type"]["result"], "ok")     # the preference is scored

        await classify_sellers("nightly")
        await rescore.rescore_recent()
        after = await self._matches(aid)
        self.assertEqual(after, alone)
        self.assertEqual((await self.counts(self._n))[0], 6, "the run did count")
        self.assertEqual(await self.inferred(self._n), [False])

    async def _matches(self, aid: int) -> list[tuple]:
        async with db.connection() as cx:
            rows = await (await cx.execute(
                "SELECT listing_id, score, level, match_reasons, score_breakdown, red_flags, price_ref, "
                "       scoring_version FROM matches WHERE search_profile_id = %s ORDER BY listing_id",
                (aid,))).fetchall()
        return [tuple(r.values()) for r in rows]


# ---------------------------------------------------------------------------
# Paso 2: dealer_inferred («posible agencia»)
# ---------------------------------------------------------------------------

POSIBLE_AGENCIA_6 = "vendedor posible agencia (publica 6 autos), se prefiere particular"
POSIBLE_AGENCIA_7 = "vendedor posible agencia (publica 7 autos), se prefiere particular"


class DealerInferredTests(SellerCase):
    async def test_a_group_of_six_is_inferred_and_one_of_five_is_not(self):
        six = [await self.listing(name, seller_type=t)
               for name, t in zip(SPELLINGS, ("private", None, None, "private", None, None))]
        five = [await self.listing("Autos SA") for _ in range(5)]
        dealers = [await self.listing("Autos del Norte", seller_type="dealer") for _ in range(6)]

        result = await classify_sellers("cli")

        self.assertEqual(await self.inferred(*six), [True] * 6, "also the rows that say private")
        self.assertEqual(await self.inferred(*five), [False] * 5)
        self.assertEqual(await self.inferred(*dealers), [False] * 6, "a dealer is never inferred")
        self.assertEqual(await self.counts(*dealers), [6] * 6)
        rows = await self.rows(*six)
        self.assertEqual([rows[i]["seller_type"] for i in six], ["private", None, None, "private", None, None],
                         "seller_type is never rewritten")
        self.assertEqual(result["inferred_changed"], 6)
        [run] = await self.runs()
        self.assertEqual(run["inferred_changed"], 6)

    async def test_min_listings_5_marks_the_group_of_5(self):
        five = [await self.listing("Autos SA") for _ in range(5)]
        await self.set_config({"enabled": True, "min_listings": 5, "window_days": 30})
        await classify_sellers("cli")
        self.assertEqual(await self.inferred(*five), [True] * 5)

    async def test_a_group_that_drops_under_the_threshold_or_a_row_that_loses_its_key_resets(self):
        ids = [await self.listing() for _ in range(7)]
        await classify_sellers("cli")
        self.assertEqual(await self.inferred(*ids), [True] * 7)

        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET status = 'gone' WHERE id = %s", (ids[6],))
            await cx.execute("UPDATE listings SET seller_name = 'Particular', seller_key = NULL WHERE id = %s",
                             (ids[5],))
        snapshots = await self.snapshot_count()
        result = await classify_sellers("cli")

        self.assertEqual(await self.inferred(*ids[:5]), [False] * 5, "5 left: under the threshold")
        self.assertEqual(await self.counts(*ids[:5]), [5] * 5)
        self.assertEqual((await self.inferred(ids[5]), await self.counts(ids[5])), ([False], [None]),
                         "no key: no count, no inference")
        self.assertEqual((await self.inferred(ids[6]), await self.counts(ids[6])), ([True], [7]),
                         "a gone listing keeps its last values")
        self.assertEqual(result["inferred_changed"], 6)
        self.assertEqual(await self.snapshot_count(), snapshots)

    async def test_a_flip_rescores_its_matches_now(self):
        ids = [await self.listing(name, seller_type="private") for name in SPELLINGS[:5]]
        aid = await self.private_alert()
        await rematch.run_pending()
        await classify_sellers("cli")
        reasons = await self.seller_reasons(aid)
        self.assertEqual({r["detail"] for r in reasons.values()}, {"vendedor particular"})

        ids.append(await self.listing(SPELLINGS[5], seller_type="private"))
        await rematch.run_pending()   # nothing pending: the new one has no match yet
        result = await classify_sellers("nightly")

        reasons = await self.seller_reasons(aid)
        self.assertEqual(result["inferred_changed"], 6)
        for lid in ids[:5]:
            self.assertEqual((reasons[lid]["result"], reasons[lid]["detail"]), ("fail", POSIBLE_AGENCIA_6), lid)

    async def test_enabled_false_takes_it_off_everywhere_and_rescores(self):
        ids = [await self.listing(name, seller_type="private") for name in SPELLINGS]
        gone = await self.listing("Juan Perez", status="gone", seller_type="private", seller_key="juan perez",
                                  seller_listing_count=6, dealer_inferred=True)
        aid = await self.private_alert()
        await rematch.run_pending()
        await classify_sellers("cli")
        self.assertEqual({r["detail"] for r in (await self.seller_reasons(aid)).values()}, {POSIBLE_AGENCIA_6})
        snapshots = await self.snapshot_count()

        await self.set_config({"enabled": False, "min_listings": 6, "window_days": 30})
        result = await classify_sellers("nightly")

        self.assertEqual(await self.inferred(*ids, gone), [False] * 7, "also the gone one")
        self.assertEqual(await self.counts(*ids), [6] * 6, "the count stays")
        self.assertEqual(result["inferred_changed"], 7)
        reasons = await self.seller_reasons(aid)
        self.assertEqual({(r["result"], r["detail"]) for r in reasons.values()}, {("ok", "vendedor particular")})
        self.assertFalse(any("posible agencia" in r["detail"] for r in reasons.values()))
        self.assertEqual(await self.snapshot_count(), snapshots)

    async def test_a_dry_run_marks_nothing(self):
        ids = [await self.listing() for _ in range(6)]
        async with db.connection() as cx:
            await cx.execute("UPDATE listings SET seller_key = 'juan perez'")
        result = await classify_sellers("cli", dry_run=True)
        self.assertEqual(await self.inferred(*ids), [False] * 6)
        self.assertEqual((result["would_write"], result["inferred_changed"], result["rescored"]), (6, 6, 0))


    async def test_a_dry_run_with_enabled_false_counts_each_row_once(self):
        active = [await self.listing(name, seller_type="private") for name in SPELLINGS]
        gone = [await self.listing("Juan Perez", status="gone", seller_key="juan perez",
                                   seller_listing_count=6, dealer_inferred=True) for _ in range(2)]
        await classify_sellers("cli")
        self.assertEqual(await self.inferred(*active), [True] * 6)
        await self.set_config({"enabled": False, "min_listings": 6, "window_days": 30})

        dry = await classify_sellers("cli", dry_run=True)
        real = await classify_sellers("cli")

        self.assertEqual((dry["would_write"], dry["inferred_changed"]), (8, 8))
        self.assertEqual((real["rows_written"], real["inferred_changed"]), (8, 8))
        self.assertEqual(await self.inferred(*active, *gone), [False] * 8)

    async def test_a_new_count_of_an_inferred_group_rescores_its_reason(self):
        ids = [await self.listing(name, seller_type="private") for name in SPELLINGS]
        aid = await self.private_alert()
        await rematch.run_pending()
        await classify_sellers("cli")
        self.assertEqual({r["detail"] for r in (await self.seller_reasons(aid)).values()}, {POSIBLE_AGENCIA_6})

        await self.listing("Juan Perez", seller_type="private")
        result = await classify_sellers("nightly")

        self.assertEqual(result["inferred_changed"], 1, "only the new one flips")
        self.assertEqual(await self.counts(*ids), [7] * 6)
        reasons = await self.seller_reasons(aid)
        for lid in ids:
            self.assertEqual(reasons[lid]["detail"], POSIBLE_AGENCIA_7, "the reason carries the new count")

    async def test_a_run_that_fails_midway_rescores_what_it_already_flipped(self):
        ids = [await self.listing(name, seller_type="private") for name in SPELLINGS]
        aid = await self.private_alert()
        await rematch.run_pending()
        with patch.object(sellers, "clear_stale", AsyncMock(side_effect=RuntimeError("boom"))):
            with self.assertRaises(RuntimeError):
                await classify_sellers("startup")
        self.assertEqual(await self.inferred(*ids), [True] * 6, "the group batch committed")
        reasons = await self.seller_reasons(aid)
        self.assertEqual({(r["result"], r["detail"]) for r in reasons.values()}, {("fail", POSIBLE_AGENCIA_6)})
        [run] = await self.runs()
        self.assertEqual(run["status"], "failed")


class IngestInferenceTests(SellerCase):
    TARGET = {"id": None, "source": "mercadolibre", "make": "Ford", "model": "Fiesta", "body_type": None,
              "query": {}}

    def notifier(self) -> Notifier:
        return Notifier({"telegram": TelegramChannel(_FakeBot(), Links()), "web": WebChannel(Links())})

    async def ingest_one(self, external_id: str, km: int) -> int:
        result = await ingest([card(external_id, vendedor="particular", vendedor_nombre="Juan Pérez", km=km)],
                              geocode=None)
        [lid] = result.ids.values()
        return lid

    async def score_like_crawl(self, lid: int) -> None:
        await scheduler.process_batch(self.notifier(), self.TARGET, [lid], first_run=False)

    async def test_the_sixth_listing_of_a_group_is_a_posible_agencia_from_its_first_alert(self):
        aid = await self.private_alert()
        await rematch.run_pending()
        five = []
        for i in range(5):
            five.append(await self.ingest_one(f"i{i}", 100_000 + 5_000 * i))
            await self.score_like_crawl(five[-1])
        self.assertEqual(await self.inferred(*five), [False] * 5)
        self.assertEqual(await self.counts(*five), [5] * 5, "the ingest counts the groups it touches")
        self.assertEqual({r["detail"] for r in (await self.seller_reasons(aid)).values()}, {"vendedor particular"})

        sixth = await self.ingest_one("i5", 130_000)
        # No full run in between: the ingest itself classified the group.
        self.assertEqual(await self.inferred(*five, sixth), [True] * 6)
        self.assertEqual(await self.counts(*five, sixth), [6] * 6)
        await self.score_like_crawl(sixth)

        reasons = await self.seller_reasons(aid)
        self.assertEqual((reasons[sixth]["result"], reasons[sixth]["detail"]), ("fail", POSIBLE_AGENCIA_6))
        for lid in five:
            self.assertEqual(reasons[lid]["detail"], POSIBLE_AGENCIA_6, "the old ones were re-scored now")
        async with db.connection() as cx:
            payloads = await (await cx.execute(
                "SELECT kind::text AS kind, payload::text AS payload FROM notifications WHERE listing_id = %s",
                (sixth,))).fetchall()
        self.assertFalse([p for p in payloads if p["kind"] == "new_match" and "vendedor particular" in p["payload"]])
        row = (await self.rows(sixth))[sixth]
        self.assertEqual((row["seller_type"], row["seller_name"]), ("private", "Juan Pérez"))

    async def test_a_failed_classification_at_ingest_is_logged_and_the_ingest_goes_on(self):
        with patch.object(sellers, "write_groups", AsyncMock(side_effect=RuntimeError("boom"))):
            lid = await self.ingest_one("f1", 100_000)
        row = (await self.rows(lid))[lid]
        self.assertEqual((row["seller_key"], row["dealer_inferred"]), ("juan perez", False))
        async with db.connection() as cx:
            errors = await (await cx.execute(
                "SELECT stage, ref, error FROM pipeline_errors WHERE stage = 'seller_classification'")).fetchall()
        self.assertEqual([(e["stage"], e["ref"]) for e in errors], [("seller_classification", "ingest")])
        self.assertIn("boom", errors[0]["error"])


    async def test_a_seller_type_that_crosses_dealer_is_classified_at_ingest(self):
        """Rosario Garage (design): the card says concesionaria, the detail
        says dueño directo, same name. And the reverse."""
        ids = [await self.ingest_one(f"d{i}", 100_000 + 5_000 * i) for i in range(6)]
        self.assertEqual(await self.inferred(*ids), [True] * 6)

        result = await ingest([card("d0", vendedor="concesionaria", vendedor_nombre="Juan Pérez", km=100_000)],
                              geocode=None)
        self.assertIn(("mercadolibre", "juan perez"), result.seller_groups)
        row = (await self.rows(ids[0]))[ids[0]]
        self.assertEqual((row["seller_type"], row["dealer_inferred"]), ("dealer", False),
                         "an explicit dealer is never inferred, also before the nightly run")

        await ingest([card("d0", vendedor="particular", vendedor_nombre="Juan Pérez", km=100_000)], geocode=None)
        row = (await self.rows(ids[0]))[ids[0]]
        self.assertEqual((row["seller_type"], row["dealer_inferred"]), ("private", True))

    async def test_a_failure_after_a_committed_flip_still_rescores_it(self):
        ids = [await self.listing(name, seller_type="private", seller_key="juan perez") for name in SPELLINGS]
        keyless = await self.listing("Particular", seller_listing_count=3)
        aid = await self.private_alert()
        await rematch.run_pending()

        with patch.object(sellers, "clear_listings", AsyncMock(side_effect=RuntimeError("boom"))):
            flipped = await classify_groups([("mercadolibre", "juan perez")], [keyless])

        self.assertEqual(sorted(flipped), ids)
        reasons = await self.seller_reasons(aid)
        for lid in ids:
            self.assertEqual((reasons[lid]["result"], reasons[lid]["detail"]), ("fail", POSIBLE_AGENCIA_6), lid)
        async with db.connection() as cx:
            errors = await (await cx.execute(
                "SELECT ref FROM pipeline_errors WHERE stage = 'seller_classification'")).fetchall()
        self.assertEqual([e["ref"] for e in errors], ["ingest"])


class StartupTests(SellerCase):
    async def test_the_startup_sequence_rescores_with_the_new_version_and_the_inference(self):
        """Deploy of paso 2: counts from paso 1, nothing inferred yet, matches
        of the old SCORING_VERSION. After the startup sequence of nightly_loop
        (classify, then rescore_outdated) every match has the new version and
        the FAIL reason."""
        ids = [await self.listing(name, seller_type="private", seller_key="juan perez", seller_listing_count=6)
               for name in SPELLINGS]
        other = await self.listing("Autos SA", seller_type="private", price=9_000, price_usd=9_000)
        aid = await self.private_alert()
        await rematch.run_pending()
        async with db.connection() as cx:
            await cx.execute("UPDATE matches SET scoring_version = 'f2-v4-publication-or-first-seen'")
        self.assertEqual(await self.inferred(*ids), [False] * 6)

        stop = asyncio.Event()
        stop.set()                  # the startup passes only
        await rescore.nightly_loop(stop)

        reasons = await self.seller_reasons(aid)
        self.assertEqual({r["version"] for r in reasons.values()}, {SCORING_VERSION})
        for lid in ids:
            self.assertEqual((reasons[lid]["result"], reasons[lid]["detail"]), ("fail", POSIBLE_AGENCIA_6))
        self.assertEqual((reasons[other]["result"], reasons[other]["detail"]), ("ok", "vendedor particular"))
        [run] = await self.runs()
        self.assertEqual((run["trigger"], run["inferred_changed"]), ("startup", 6))
