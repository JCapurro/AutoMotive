"""db/repos/match_decisions without a database: the row contract against the migration,
JSON-safe rows, and the statements it sends (the DB behavior: test_match_decisions_postgres.py)."""
from __future__ import annotations

import json
import re
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from config import ROOT
from db.repos import match_decisions as repo

MIGRATION = ROOT / "supabase" / "migrations" / "20261212120000_score_f3_shadow.sql"


def table_columns() -> list[str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    body = sql.split("create table if not exists public.match_decisions (", 1)[1].split("constraint match_decisions_once", 1)[0]
    cols = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("--"):
            continue
        cols.append(re.match(r"[a-z_0-9]+", line)[0])
    return cols


def minimal(**kw) -> dict:
    row = {"match_id": 1, "search_profile_id": 2, "listing_id": 3, "model": "f2", "phase": "card",
           "f3_decides": True, "f2_version": "f2-v5-seller-margin"}
    row.update(kw)
    return row


class _Cursor:
    def __init__(self, rows=(), rowcount=0):
        self._rows, self.rowcount = list(rows), rowcount

    async def fetchall(self):
        return self._rows

    async def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConnection:
    def __init__(self, rows=(), rowcount=0):
        self.calls: list[tuple[str, object]] = []
        self._rows, self._rowcount = rows, rowcount

    async def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return _Cursor(self._rows, self._rowcount)


class ContractTests(unittest.TestCase):
    def test_columns_are_the_tables_in_order(self):
        self.assertEqual(table_columns()[0], "id")
        self.assertEqual(list(repo.COLUMNS), table_columns()[1:])

    def test_required_columns_are_columns(self):
        self.assertLessEqual(set(repo.REQUIRED), set(repo.COLUMNS))

    def test_the_insert_names_every_column_once(self):
        self.assertIn("INSERT INTO public.match_decisions (" + ", ".join(repo.COLUMNS) + ")", repo._INSERT)
        self.assertIn("ON CONFLICT (match_id, model, phase) DO NOTHING", repo._INSERT)
        self.assertNotIn("DO UPDATE", repo._INSERT)     # would hit the insert-only trigger


class PrepareTests(unittest.TestCase):
    def test_unknown_or_missing_columns_are_a_bug(self):
        with self.assertRaisesRegex(ValueError, "unknown columns \\['shadow'\\]"):
            repo.prepare(minimal(shadow=1))
        with self.assertRaisesRegex(ValueError, "missing \\['f3_decides'\\]"):
            repo.prepare(minimal(f3_decides=None))
        bad = minimal()
        del bad["f2_version"]
        with self.assertRaisesRegex(ValueError, "missing"):
            repo.prepare(bad)

    def test_json_safe_values(self):
        at = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)
        row = repo.prepare(minimal(
            decided_at=at, user_id=UUID("f3f30000-0000-4000-8000-000000000001"),
            price=Decimal("10300"), price_usd=Decimal("10300.50"), f3_d=float("nan"), f3_d_eff=float("inf"),
            f2_score=88.0, f3_score=86, year=2017.0, f3_r=0.95,
            price_ref={"n": 23, "median": Decimal("11200.00"), "diff_pct": 8.04},
            red_flags=[{"id": "much_cheaper", "text": "…", "severity": "info"}, "repost"],
            f3_flags=("no_year",), f3_a_verificar=None, f3={"deal": {"value": float("nan")}}))
        self.assertEqual(row["decided_at"], "2026-11-12T15:00:00+00:00")
        self.assertEqual(row["user_id"], "f3f30000-0000-4000-8000-000000000001")
        self.assertEqual((row["price"], row["price_usd"]), (10300, 10300.5))
        self.assertIsNone(row["f3_d"])
        self.assertIsNone(row["f3_d_eff"])
        self.assertEqual((row["f2_score"], row["f3_score"], row["year"]), (88, 86, 2017))
        self.assertIsInstance(row["f2_score"], int)
        self.assertEqual(row["price_ref"], {"n": 23, "median": 11200, "diff_pct": 8.04})
        self.assertEqual(row["red_flags"], ["much_cheaper", "repost"])
        self.assertEqual(row["f3_flags"], ["no_year"])
        self.assertIsNone(row["f3_a_verificar"])         # null → the column's default ('{}') in SQL
        self.assertEqual(row["f3"], {"deal": {"value": None}})
        json.dumps(row, allow_nan=False)


class StatementTests(unittest.IsolatedAsyncioTestCase):
    async def test_insert_nothing_sends_nothing(self):
        cx = FakeConnection()
        self.assertEqual(await repo.insert(cx, []), 0)
        self.assertEqual(cx.calls, [])

    async def test_insert_one_statement_under_a_timeout(self):
        cx = FakeConnection(rowcount=2)
        self.assertEqual(await repo.insert(cx, [minimal(), minimal(phase="deferred")]), 2)
        (timeout, _), (sql, (payload,)) = cx.calls
        self.assertEqual(timeout, "SET LOCAL statement_timeout = '2s'")
        self.assertEqual(sql, repo._INSERT)
        self.assertEqual([r["phase"] for r in payload.obj], ["card", "deferred"])

    async def test_a_bad_row_sends_nothing(self):
        cx = FakeConnection()
        with self.assertRaises(ValueError):
            await repo.insert(cx, [minimal(), minimal(nope=1)])
        self.assertEqual(cx.calls, [])

    async def test_reads_without_ids_send_nothing(self):
        cx = FakeConnection()
        since = datetime(2026, 11, 12, tzinfo=timezone.utc)
        self.assertEqual(await repo.cards_for_listings(cx, [], since=since), [])
        self.assertEqual(await repo.current_state(cx, []), {})
        self.assertEqual(cx.calls, [])

    async def test_reads_are_under_the_timeout_too(self):
        cx = FakeConnection(rows=[{"match_id": 7}])
        since = datetime(2026, 11, 12, tzinfo=timezone.utc)
        await repo.cards_for_listings(cx, [3, 3, 1], since=since)
        self.assertEqual(cx.calls[0][0], "SET LOCAL statement_timeout = '2s'")
        self.assertEqual(cx.calls[1][1], ([1, 3], "f2", since))
        cx.calls.clear()
        await repo.due_sweeps(cx, before=since, since=since, limit=5)
        self.assertEqual(cx.calls[1][1], ("f2", since, since, 5))
        self.assertIn("c.phase = 'card' AND c.would_defer", cx.calls[1][0])   # the partial index's predicate
        cx.calls.clear()
        self.assertEqual(await repo.current_state(cx, [7]), {7: {"match_id": 7}})
