"""F7, punto 8: the watchdog's decisions (tools/watchdog.py), without network or DB."""
from __future__ import annotations

import unittest
from datetime import timedelta

import httpx

from tools.watchdog import check_web, transitions, worker_problem

STALE = timedelta(minutes=10)


class WorkerHeartbeatTests(unittest.TestCase):
    def test_fresh_stale_and_missing(self):
        self.assertIsNone(worker_problem({"age": timedelta(minutes=1), "host": "pc"}, STALE))
        self.assertIn("12 min", worker_problem({"age": timedelta(minutes=12), "host": "pc"}, STALE))
        self.assertIn("nunca", worker_problem(None, STALE))


class WebCheckTests(unittest.TestCase):
    def test_statuses(self):
        ok = lambda url: httpx.Response(200)  # noqa: E731
        self.assertIsNone(check_web("https://automotive.example", ok))
        self.assertIn("502", check_web("https://automotive.example", lambda url: httpx.Response(502)))

        def down(url):
            raise httpx.ConnectError("boom")
        self.assertIn("no responde", check_web("https://automotive.example", down))
        self.assertIsNone(check_web("", down))  # no WEB_BASE_URL: nothing to check


class TransitionTests(unittest.TestCase):
    def test_alerts_once_and_on_recovery(self):
        down = {"worker": "no late", "base": None, "web": None}
        up = {"worker": None, "base": None, "web": None}
        self.assertEqual(transitions(up, down), ["🔴 AutoMotive · worker: no late"])
        self.assertEqual(transitions(down, down), [])          # still down: no spam
        self.assertEqual(transitions(down, up), ["🟢 AutoMotive · worker: volvió a funcionar"])
        self.assertEqual(transitions({}, up), [])              # first run, all fine


class EnvFileTests(unittest.TestCase):
    """tools/supabase_keys.py rewrites .env files in place."""

    def test_set_vars(self):
        from tools.supabase_keys import new_keys, set_vars

        text = "A=1\nJWT_SECRET=old\n"
        self.assertEqual(set_vars(text, {"JWT_SECRET": "new", "B": "2"}), "A=1\nJWT_SECRET=new\nB=2\n")
        self.assertEqual(set_vars(text, {"JWT_SECRET": "new"}, overwrite=False), text)
        keys = new_keys()
        self.assertTrue(keys["SUPABASE_SECRET_KEY"].startswith("sb_secret_"))
        self.assertGreaterEqual(len(keys["JWT_SECRET"]), 40)
