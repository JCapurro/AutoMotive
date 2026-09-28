"""
(Re)create the database the Postgres tests run on (F7, punto 4).

The DB tests TRUNCATE listings, matches, notifications… so they must never run
on the database the worker and the web use. This clones the local Supabase
database into `automotive_test` in the same Postgres: the whole schema
(public, auth, extensions) plus the reference data (sources, app_config,
vehicle_catalog), and no user data. Run it once, and again after a new
migration.

Usage (from worker/, with `npx supabase start` running):
    python -m tools.test_db
    $env:TEST_DATABASE_URL = "postgresql://postgres:postgres@127.0.0.1:54322/automotive_test"
    pytest
"""
from __future__ import annotations

import re
import subprocess
import sys

from config import ROOT

TEST_DB = "automotive_test"
TEST_DATABASE_URL = f"postgresql://postgres:postgres@127.0.0.1:54322/{TEST_DB}"

# Only these tables keep their rows; everything else is copied empty.
REFERENCE_TABLES = {"sources", "app_config", "vehicle_catalog"}
SKIP_DATA_SCHEMAS = ("auth", "storage", "realtime", "_realtime", "supabase_functions")


def container() -> str:
    """The local stack's Postgres container: supabase_db_<project_id>."""
    config = (ROOT / "supabase" / "config.toml").read_text(encoding="utf-8")
    match = re.search(r'^project_id\s*=\s*"([^"]+)"', config, re.MULTILINE)
    if not match:
        raise SystemExit("no encontré project_id en supabase/config.toml")
    return f"supabase_db_{match[1]}"


def script(public_tables: list[str]) -> str:
    excluded = [f"--exclude-table-data=public.{t}" for t in public_tables if t not in REFERENCE_TABLES]
    excluded += [f"--exclude-table-data='{s}.*'" for s in SKIP_DATA_SCHEMAS]
    return "\n".join([
        "set -euo pipefail",
        f'psql -U supabase_admin -d postgres -qc "drop database if exists {TEST_DB} with (force)"',
        f'psql -U supabase_admin -d postgres -qc "create database {TEST_DB}"',
        "pg_dump -U supabase_admin -d postgres --no-publications --no-subscriptions "
        + " ".join(excluded) + f" | psql -U supabase_admin -d {TEST_DB} -q -v ON_ERROR_STOP=1 >/dev/null",
    ])


def main() -> int:
    name = container()

    def psql(sql: str) -> str:
        return subprocess.run(["docker", "exec", name, "psql", "-U", "postgres", "-d", "postgres", "-tAc", sql],
                              check=True, capture_output=True, text=True).stdout

    tables = psql("select tablename from pg_tables where schemaname = 'public' order by 1").split()
    # Bytes, not text: on Windows text mode would send CRLF line endings to bash.
    subprocess.run(["docker", "exec", "-i", name, "bash", "-s"], input=script(tables).encode(),
                   check=True)
    print(f"{TEST_DB} listo (esquema + {', '.join(sorted(REFERENCE_TABLES))}).")
    print(f"TEST_DATABASE_URL={TEST_DATABASE_URL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
