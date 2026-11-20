"""The app_config.fair_value row the migration inserts (20270107120000_fair_value_shadow.sql) is the code's
DEFAULT_FAIR_VALUE with mode 'shadow', and the parser keeps every value of it; the code default stays 'off'."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from intelligence.config import DEFAULT_FAIR_VALUE, fair_value_config

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase" / "migrations" / "20270107120000_fair_value_shadow.sql"


def migration_value() -> dict:
    sql = MIGRATION.read_text(encoding="utf-8")
    found = re.search(r"values \('fair_value', '(\{.*?\})'::jsonb\)", sql, re.S)
    if found is None:
        raise AssertionError(f"no fair_value literal in {MIGRATION.name}")
    return json.loads(found[1])


class MigrationDefaultsTests(unittest.TestCase):
    def test_the_row_is_the_code_defaults_with_mode_shadow(self):
        self.assertEqual(migration_value(), {**DEFAULT_FAIR_VALUE, "mode": "shadow"})

    def test_the_parser_keeps_every_value(self):
        value = migration_value()
        parsed = fair_value_config(value)
        self.assertEqual({k: v for k, v in parsed.items() if k != "params"}, value)
        self.assertEqual(parsed["params"], fair_value_config(None)["params"])

    def test_the_code_default_is_off(self):
        self.assertEqual(DEFAULT_FAIR_VALUE["mode"], "off")

    def test_inserted_without_overwriting_a_tuned_row_and_not_in_the_seed(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertRegex(sql[sql.index("values ('fair_value'"):], r"on conflict \(key\) do nothing")
        self.assertNotIn("'fair_value'", (ROOT / "supabase" / "seed.sql").read_text(encoding="utf-8"))

    def test_the_version_is_after_the_last_one(self):
        versions = sorted(p.name[:14] for p in MIGRATION.parent.glob("*.sql"))
        self.assertEqual(versions[-1], MIGRATION.name[:14])
        self.assertGreater(MIGRATION.name[:14], "20270106120000")


if __name__ == "__main__":
    unittest.main()
