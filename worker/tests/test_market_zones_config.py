"""F-03 fase 0: the region map (app_config.market_zones, seeded from
normalization.zone.DEFAULT_ZONE_MAP) covers the country with places that exist."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from normalization.zone import DEFAULT_ZONE_MAP, load_localities, resolve_region
from test_intelligence_copy import forbidden_in

MIGRATION = (Path(__file__).resolve().parents[2] / "supabase" / "migrations"
             / "20261119110000_f03_market_stats.sql")


class ZoneMapTests(unittest.TestCase):
    def test_every_province_is_covered(self):
        provinces = {pid for pid, _ in load_localities().provinces}
        covered = {rule["province"] for rule in DEFAULT_ZONE_MAP["rules"]}
        self.assertEqual(covered, provinces)
        # A province split by departments ends with a rule for the rest of it.
        for pid in provinces:
            rules = [r for r in DEFAULT_ZONE_MAP["rules"] if r["province"] == pid]
            self.assertNotIn("departments", rules[-1], pid)

    def test_rules_point_at_known_regions(self):
        self.assertEqual(DEFAULT_ZONE_MAP["version"], 1)
        self.assertEqual(len(DEFAULT_ZONE_MAP["regions"]), 8)
        for rule in DEFAULT_ZONE_MAP["rules"]:
            self.assertIn(rule["region"], DEFAULT_ZONE_MAP["regions"])

    def test_every_department_exists_in_its_province(self):
        departments: dict[str, set[str]] = {}
        for city in load_localities().cities:
            departments.setdefault(city.province_id, set()).add(city.department)
        cited = [(r["province"], d) for r in DEFAULT_ZONE_MAP["rules"] for d in r.get("departments", [])]
        self.assertEqual(len(cited), 24)                              # the 24 partidos of the GBA
        for province, department in cited:
            self.assertIn(department, departments[province])

    def test_the_first_matching_rule_wins(self):
        self.assertEqual(resolve_region(DEFAULT_ZONE_MAP, "06", "San Isidro", "locality"), "amba")
        self.assertEqual(resolve_region(DEFAULT_ZONE_MAP, "06", "san isidro", "locality"), "amba")
        self.assertEqual(resolve_region(DEFAULT_ZONE_MAP, "06", "Pilar", "locality"), "buenos_aires_resto")
        self.assertEqual(resolve_region(DEFAULT_ZONE_MAP, "02", "Comuna 1", "locality"), "amba")
        self.assertIsNone(resolve_region(DEFAULT_ZONE_MAP, "99", "X", "locality"))
        swapped = {**DEFAULT_ZONE_MAP, "rules": [{"region": "buenos_aires_resto", "province": "06"},
                                                 *DEFAULT_ZONE_MAP["rules"]]}
        self.assertEqual(resolve_region(swapped, "06", "San Isidro", "locality"), "buenos_aires_resto")

    def test_labels_pass_the_copy_lint(self):
        for key, label in DEFAULT_ZONE_MAP["regions"].items():
            self.assertEqual(forbidden_in(label), [], key)

    def test_the_migration_seeds_the_same_map(self):
        sql = MIGRATION.read_text(encoding="utf-8")
        match = re.search(r"\('market_zones',\s*\$zones\$(.*?)\$zones\$", sql, re.DOTALL)
        self.assertIsNotNone(match, "the migration seeds app_config.market_zones")
        self.assertEqual(json.loads(match[1]), DEFAULT_ZONE_MAP)


if __name__ == "__main__":
    unittest.main()
