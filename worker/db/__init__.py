"""Postgres (Supabase) data access for the worker.

Replaces the old SQLite module. The functions the bot already used keep their
names (now async); each lives in the repo that owns its table:

    alerts           → search_profiles   (repos/profiles.py)
    seen_listings    → matches           (repos/matches.py)
    listings_cache   → listings          (repos/listings.py; written by pipeline/ingest.py)
    geocode_cache    → geocode_cache     (repos/geocode.py)
    app_config       → repos/config.py
    crawl_targets    → repos/targets.py
    collector_runs, pipeline_errors → repos/runs.py
    fx_rates         → repos/fx.py

Open the pool once per process with `await db.open_pool()`.
"""
from db.pool import close_pool, connection, open_pool
from db.repos.config import get_config
from db.repos.geocode import (
    get_geocode_cache,
    has_fresh_geocode_failure,
    set_geocode_cache,
    set_geocode_cache_failure,
)
from db.repos.listings import comparables
from db.repos.matches import filter_unseen, mark_seen, matched_by_other_profiles
from db.repos.profiles import (
    alerts_for_target,
    create_alert,
    delete_alert,
    enabled_profiles,
    get_alert,
    list_alerts,
    mark_bootstrapped,
    pending_rematch,
    set_alert_active,
    update_alert,
)

__all__ = [
    "alerts_for_target", "close_pool", "comparables", "connection", "create_alert",
    "delete_alert", "enabled_profiles", "filter_unseen", "get_alert", "get_config",
    "get_geocode_cache", "has_fresh_geocode_failure", "list_alerts", "mark_bootstrapped",
    "mark_seen", "matched_by_other_profiles", "open_pool", "pending_rematch",
    "set_alert_active", "set_geocode_cache", "set_geocode_cache_failure", "update_alert",
]
