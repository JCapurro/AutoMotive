from __future__ import annotations

import importlib
import os
import sys
import unittest
from unittest.mock import patch

import dotenv


class ConfigTests(unittest.TestCase):
    def test_default_loop_intervals(self):
        original_config = sys.modules.pop("config", None)
        try:
            with patch.object(dotenv, "load_dotenv"), patch.dict(os.environ, {}, clear=True):
                config = importlib.import_module("config")
            self.assertEqual(config.TICK_INTERVAL_SECONDS, 300)
            self.assertEqual(config.ENRICH_TICK_SECONDS, 300)
            self.assertEqual(config.WATCHLIST_TICK_SECONDS, 3600)
            self.assertFalse(hasattr(config, "ALERT_RESCRAPE_INTERVAL_SECONDS"))
            self.assertEqual(config.LLM_PROVIDER, "openai")
            self.assertEqual(config.OPENAI_MODEL, "gpt-6-luna")
            self.assertEqual(config.OPENAI_API_KEY, "")
        finally:
            sys.modules.pop("config", None)
            if original_config is not None:
                sys.modules["config"] = original_config


if __name__ == "__main__":
    unittest.main()


class TestDatabaseGuardTests(unittest.TestCase):
    """F7, punto 4: the DB tests TRUNCATE, so they never touch the pilot's database."""

    def reason(self, test_url, app_url="postgresql://postgres:postgres@127.0.0.1:54322/postgres"):
        from pgcase import db_test_skip_reason
        return db_test_skip_reason(test_url, app_url)

    def test_the_test_database_runs(self):
        self.assertIsNone(self.reason("postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"))

    def test_the_app_database_is_refused(self):
        self.assertIn("_test", self.reason("postgresql://postgres:postgres@127.0.0.1:54322/postgres"))
        self.assertIn("DATABASE_URL", self.reason("postgresql://u:p@localhost:54322/automotive_test",
                                                  "postgresql://u:p@localhost:54322/automotive_test"))

    def test_remote_or_missing_is_refused(self):
        self.assertIn("local", self.reason("postgresql://u:p@db.example.com:5432/automotive_test"))
        self.assertIn("not set", self.reason(""))


class StartupWarningsTests(unittest.TestCase):
    """F7, punto 5: every channel or metric the .env leaves off is logged at startup."""

    FULL = {"WEB_BASE_URL": "https://automotive.example", "RESEND_API_KEY": "re_x",
            "EMAIL_FROM": "alertas@automotive.example", "TELEGRAM_ADMIN_CHAT_ID": "1",
            "LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "sk-x", "CLAUDE_CLI_PATH": "",
            "GEOCODING_ENABLED": True}

    def warnings(self, found=True, **changes):
        from config import startup_warnings
        return startup_warnings({**self.FULL, **changes}, which=lambda _: "/bin/claude" if found else None)

    def test_a_complete_configuration_is_quiet(self):
        self.assertEqual(self.warnings(), [])

    def test_each_missing_piece_is_named(self):
        self.assertIn("§53", self.warnings(WEB_BASE_URL="")[0])
        self.assertIn("https", self.warnings(WEB_BASE_URL="http://127.0.0.1:3000")[0])
        self.assertIn("RESEND_API_KEY", self.warnings(EMAIL_FROM="")[0])
        self.assertIn("TELEGRAM_ADMIN_CHAT_ID", self.warnings(TELEGRAM_ADMIN_CHAT_ID="")[0])
        self.assertIn("suscripción", self.warnings(LLM_PROVIDER="claude_cli")[0])
        self.assertIn("CLAUDE_CLI_PATH", self.warnings(found=False, LLM_PROVIDER="claude_cli")[1])
        self.assertIn("ANTHROPIC_API_KEY", self.warnings(ANTHROPIC_API_KEY="")[0])
        self.assertIn("OPENAI_API_KEY", self.warnings(LLM_PROVIDER="openai", OPENAI_API_KEY="")[0])
        self.assertEqual(self.warnings(LLM_PROVIDER="openai", OPENAI_API_KEY="sk-x"), [])
        self.assertIn("stub", self.warnings(LLM_PROVIDER="local")[0])
        self.assertIn("radio", self.warnings(GEOCODING_ENABLED=False)[0])
