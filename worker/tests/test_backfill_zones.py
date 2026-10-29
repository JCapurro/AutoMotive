"""F-03 fase 0: which listings get a zone row (pipeline/market_zones.plan_zones)
and what tools.backfill_zones reports, without a database."""
from __future__ import annotations

import unittest
from collections import Counter
from unittest.mock import AsyncMock, patch

from pipeline import market_zones
from pipeline.market_zones import plan_zones
from tools import backfill_zones

SAN_ISIDRO = (-34.4708, -58.5286)
ROSARIO = (-32.9442, -60.6505)
CABA = (-34.6037, -58.3816)


def row(lid, source, text, coords=None, zone=None, status="active", **stored):
    lat, lon = coords or (None, None)
    zlat, zlon = zone or (None, None)
    return {"id": lid, "source": source, "location_text": text, "lat": lat, "lon": lon, "status": status,
            "zone_lat": zlat, "zone_lon": zlon, **stored}


class PlanZonesTests(unittest.TestCase):
    def rows(self):
        return [
            row(1, "mercadolibre", "San Isidro, Buenos Aires", SAN_ISIDRO),                 # no zone yet
            row(2, "mercadolibre", "Rosario, Santa Fe", ROSARIO, zone=SAN_ISIDRO),          # moved
            row(3, "mercadolibre", "San Isidro, Buenos Aires", SAN_ISIDRO, zone=SAN_ISIDRO,  # unchanged
                zone_province_id="06", zone_department="San Isidro", zone_precision="locality"),
            row(4, "gruporandazzo", None),                                                  # no coordinates
            row(5, "rosariogarage", None, ROSARIO),                                          # source default
            row(6, "facebook", "Buenos Aires", CABA),                                        # province alone
            row(7, "facebook", "Ciudad de Buenos Aires", CABA, status="gone"),               # gone: written, not counted
        ]

    def test_only_new_and_moved_listings_are_written(self):
        updates = plan_zones(self.rows())
        self.assertEqual([lid for lid, _ in updates], [1, 2, 5, 6, 7])
        facts = dict(updates)
        self.assertEqual((facts[1].province_id, facts[1].department), ("06", "San Isidro"))
        self.assertEqual((facts[2].province_id, facts[2].lat, facts[2].lon), ("82", *ROSARIO))
        self.assertEqual(facts[5].precision, "source_default")
        self.assertEqual(facts[6].precision, "province")

    def test_report_per_source(self):
        counts = Counter()
        plan_zones(self.rows(), counts=counts)
        self.assertEqual(counts[("mercadolibre", "con región")], 3)
        self.assertEqual(counts[("gruporandazzo", "sin coordenadas")], 1)
        self.assertEqual(counts[("rosariogarage", "con región")], 1)
        self.assertEqual(counts[("rosariogarage", "source_default")], 1)
        self.assertEqual(counts[("facebook", "provincia sin región")], 1)
        self.assertEqual(counts[("facebook", "con región")], 0)                 # the gone one is not counted
        self.assertEqual(counts[("mercadolibre", "a escribir")], 2)


class SyncZonesTests(unittest.IsolatedAsyncioTestCase):
    async def test_dry_run_writes_nothing(self):
        rows = [row(1, "mercadolibre", "San Isidro, Buenos Aires", SAN_ISIDRO)]
        with patch.object(market_zones, "_fetch", AsyncMock(return_value=rows)), \
             patch.object(market_zones, "_zone_map", AsyncMock(return_value=market_zones.DEFAULT_ZONE_MAP)), \
             patch.object(market_zones, "_write", AsyncMock()) as write:
            counts = await market_zones.sync_zones(dry_run=True)
            write.assert_not_called()
            self.assertEqual(counts[("mercadolibre", "a escribir")], 1)
            await market_zones.sync_zones()
            write.assert_awaited_once()

    def test_report_says_when_nothing_was_written(self):
        lines = backfill_zones.report(Counter({("facebook", "con región"): 3}), dry_run=True)
        self.assertEqual(lines[-1], "(simulación: no se escribió nada)")
        self.assertIn("facebook", lines[0])


if __name__ == "__main__":
    unittest.main()
