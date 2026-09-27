"""Helpers for tests that need Postgres (see conftest.py for the event loop)."""
from __future__ import annotations

import os
import unittest
from urllib.parse import urlparse

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Tables the DB tests write to; reference data (sources, app_config, catalog) stays.
_TRUNCATE = ("search_profiles, listings, listing_snapshots, matches, geocode_cache, "
             "events, notifications, user_listing_interactions, owned_vehicles")


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

        await db.open_pool(TEST_DATABASE_URL, max_size=2)
        async with db.connection() as cx:
            await cx.execute(f"TRUNCATE {_TRUNCATE} RESTART IDENTITY CASCADE")
            await cx.execute("DELETE FROM auth.users WHERE raw_app_meta_data->>'provider' = 'telegram' "
                             "   OR email LIKE '%@automotive.test'")
        app_config.clear_config_cache()
        catalog._fetched_at = 0.0

    async def asyncTearDown(self) -> None:
        import db

        await db.close_pool()
