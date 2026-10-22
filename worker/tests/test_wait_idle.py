"""tools/wait_idle.py: a deploy waits for the Facebook and Mercado Libre
targets being crawled before restarting the worker."""
from __future__ import annotations

from datetime import datetime, timezone
import unittest

from tools import wait_idle

UNTIL = datetime(2026, 10, 22, 18, 30, tzinfo=timezone.utc)


class FakeConnection:
    """Answers HELD_SQL with the next of `answers` (the last one repeats)."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql, params):
        self.asked.append((sql, params))
        rows = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return FakeCursor(rows)


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows

    async def fetchall(self):
        return self.rows


def held(*ids):
    return [{"source": "facebook", "id": i, "claimed_until": UNTIL} for i in ids]


class WaitIdleTests(unittest.TestCase):
    def run_tool(self, answers, *args):
        cx = FakeConnection(answers)

        async def connect():
            return cx
        code = wait_idle.main(["facebook", "mercadolibre", "--poll", "0", *args], connect=connect)
        return code, cx

    def test_free_sources_exit_0_at_once(self):
        code, cx = self.run_tool([[]])
        self.assertEqual(code, 0)
        [(sql, params)] = cx.asked
        self.assertIn("claimed_until > now()", sql)
        self.assertEqual(params, (["facebook", "mercadolibre"],))

    def test_it_waits_until_the_claims_end(self):
        code, cx = self.run_tool([held(7), held(7), []], "--max-wait", "60")
        self.assertEqual((code, len(cx.asked)), (0, 3))

    def test_claims_past_max_wait_exit_2(self):
        code, cx = self.run_tool([held(7)], "--max-wait", "0")
        self.assertEqual(code, 2)

    def test_an_unreadable_database_exits_1(self):
        async def connect():
            raise OSError("connection refused")
        self.assertEqual(wait_idle.main(["facebook"], connect=connect), 1)


if __name__ == "__main__":
    unittest.main()
