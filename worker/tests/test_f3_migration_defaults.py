"""The app_config.score_model_f3 row the f3 shadow migration inserts
(supabase/migrations/20261212120000_score_f3_shadow.sql) is the code's DEFAULT_SCORE_MODEL_F3 with mode
'shadow', and the worker's parser keeps every value of it: the shadow runs with the spec's parameters
(§14, «Parámetros»), and the code default stays 'off' (tests and an un-migrated database behave as before)."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from intelligence.config import DEFAULT_SCORE_MODEL_F3, F3_GROUPS, IntelligenceConfig, score_model_f3

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20261212120000_score_f3_shadow.sql"


def migration_value() -> dict:
    sql = MIGRATION.read_text(encoding="utf-8")
    found = re.search(r"values \('score_model_f3', '(\{.*?\})'::jsonb\)", sql, re.S)
    if found is None:
        raise AssertionError(f"no score_model_f3 literal in {MIGRATION.name}")
    return json.loads(found[1])


class MigrationDefaultsTests(unittest.TestCase):
    def test_the_row_is_the_code_defaults_with_mode_shadow(self):
        self.assertEqual(migration_value(), {**DEFAULT_SCORE_MODEL_F3, "mode": "shadow"})

    def test_the_parser_keeps_every_value(self):
        value = migration_value()
        parsed = score_model_f3(value, suspicious_pct=50, min_n=5)
        self.assertEqual(parsed["mode"], "shadow")
        for group in (*F3_GROUPS, "rules"):
            self.assertEqual(parsed[group], value[group], group)
            self.assertEqual(set(parsed[group]), set(DEFAULT_SCORE_MODEL_F3[group]), group)
        # The measurement's hash does not depend on the mode: the defaults' and the row's are the same.
        self.assertEqual(parsed["params"], score_model_f3(None)["params"])

    def test_only_mode_is_a_string_and_rules_are_booleans(self):
        value = migration_value()
        self.assertIsInstance(value["mode"], str)
        for group in F3_GROUPS:
            for key, v in value[group].items():
                self.assertTrue(isinstance(v, (int, float)) and not isinstance(v, bool), f"{group}.{key}")
        self.assertTrue(all(isinstance(v, bool) for v in value["rules"].values()))

    def test_the_code_default_is_off(self):
        self.assertEqual(DEFAULT_SCORE_MODEL_F3["mode"], "off")
        self.assertEqual(score_model_f3(None)["mode"], "off")
        self.assertEqual(IntelligenceConfig().f3["mode"], "off")
        self.assertEqual(IntelligenceConfig.from_app_config({}).f3["mode"], "off")

    def test_inserted_without_overwriting_a_tuned_row(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        tail = sql[sql.index("values ('score_model_f3'"):]
        self.assertRegex(tail, r"on conflict \(key\) do nothing")


if __name__ == "__main__":
    unittest.main()
