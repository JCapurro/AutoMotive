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
             "crawl_targets, collector_runs, pipeline_errors, fx_rates, description_llm_runs")

# Every DB test gets this quote instead of calling dolarapi.com.
TEST_FX_RATE = 1_000.0


def _database(url: str) -> tuple[str | None, int, str]:
    parsed = urlparse(url)
    return parsed.hostname, parsed.port or 5432, parsed.path.lstrip("/") or "postgres"


def db_test_skip_reason(test_url: str | None = None, app_url: str | None = None) -> str | None:
    """Why the DB tests can't run here, or None. They TRUNCATE tables, so they
    only run on a local database whose name ends in _test that isn't the one
    the worker uses (DATABASE_URL): `python -m tools.test_db` creates it."""
    test_url = TEST_DATABASE_URL if test_url is None else test_url
    if app_url is None:
        import config  # loads .env

        app_url = config.DATABASE_URL
    if not test_url:
        return "TEST_DATABASE_URL not set (`python -m tools.test_db` creates automotive_test)"
    host, port, name = _database(test_url)
    if host not in _LOCAL_HOSTS:
        return "DB tests truncate tables; TEST_DATABASE_URL must point to a local database"
    if not name.endswith("_test"):
        return (f"DB tests truncate tables; TEST_DATABASE_URL points to {name!r}, "
                "use a database whose name ends in _test (`python -m tools.test_db`)")
    if app_url and _database(app_url) == (host, port, name):
        return "DB tests truncate tables; TEST_DATABASE_URL is the worker's DATABASE_URL"
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
