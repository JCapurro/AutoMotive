"""Helpers for tests that need Postgres (see conftest.py for the event loop)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Tables the DB tests write to; reference data (sources, app_config, catalog) stays.
_TRUNCATE = ("search_profiles, listings, listing_snapshots, matches, geocode_cache, "
             "events, notifications, user_listing_interactions, owned_vehicles, "
             "crawl_targets, collector_runs, pipeline_errors, fx_rates")

# Every DB test gets this quote instead of calling dolarapi.com.
TEST_FX_RATE = 1_000.0


def db_test_skip_reason() -> str | None:
    if not TEST_DATABASE_URL:
        return "TEST_DATABASE_URL not set (e.g. the local `supabase start` database)"
    if urlparse(TEST_DATABASE_URL).hostname not in _LOCAL_HOSTS:
        return "DB tests truncate tables; TEST_DATABASE_URL must point to a local database"
    return None


requires_db = pytest.mark.skipif(db_test_skip_reason() is not None,
                                 reason=db_test_skip_reason() or "")


class PostgresTestCase(unittest.IsolatedAsyncioTestCase):
    """Opens the worker pool on TEST_DATABASE_URL over a clean slate."""

    async def asyncSetUp(self) -> None:
        import db
        from db.repos import catalog, config as app_config
        from normalization.fx import FxQuote

        fx = patch("db.repos.fx.usd_ars_quote", return_value=FxQuote(TEST_FX_RATE, "blue", "test"))
        fx.start()
        self.addCleanup(fx.stop)

        await db.open_pool(TEST_DATABASE_URL, max_size=2)
        async with db.connection() as cx:
            await cx.execute(f"TRUNCATE {_TRUNCATE} RESTART IDENTITY CASCADE")
            await cx.execute("DELETE FROM auth.users WHERE raw_app_meta_data->>'provider' = 'telegram' "
                             "   OR email LIKE '%automotive.test'")
            await cx.execute("UPDATE sources SET last_ok_at = NULL, consecutive_failures = 0")
        app_config.clear_config_cache()
        catalog.clear_catalog_cache()

    async def asyncTearDown(self) -> None:
        import db

        await db.close_pool()
