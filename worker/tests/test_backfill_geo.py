from __future__ import annotations

import unittest
from collections import Counter

from tools.backfill_geo import plan

CABA = (-34.6037, -58.3816)
ROSARIO = (-32.9442, -60.6505)


async def fake_geocode(place: str):
    return {"Ciudad de Buenos Aires, CF": CABA, "Rosario, Santa Fe": ROSARIO,
            "Necochea, Buenos Aires": (-38.5545, -58.7396)}.get(place)


def row(lid, source, text):
    return {"id": lid, "source": source, "location_text": text}


class BackfillGeoTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan(self):
        counts = Counter()
        rows = [
            row(1, "facebook", "Ciudad de Buenos Aires, CF"),
            row(2, "facebook", "Recién publicado"),
            row(3, "facebook", "2017 Ford mondeo 2.0 titanium ecoboot at 240cv"),
            row(4, "mercadolibre", "Necochea - Bs.As. Costa Atlántica"),
            row(5, "rosariogarage", None),
            row(6, "gruporandazzo", None),
            row(7, "mercadolibre", "Villa Inventada - Buenos Aires Interior"),
        ]
        updates = await plan(rows, fake_geocode, counts)
        self.assertEqual({lid: (coords, clear) for lid, coords, clear in updates}, {
            1: (CABA, False),
            2: (None, True),            # not a place: the text goes, nothing to place
            3: (None, True),
            4: ((-38.5545, -58.7396), False),
            5: (ROSARIO, False),        # the source's default town, coordinates only
        })                              # 6 and 7 stay as they are
        self.assertEqual(counts[("facebook", "texto descartado")], 2)
        self.assertEqual(counts[("gruporandazzo", "sin ubicar")], 1)
        self.assertEqual(counts[("mercadolibre", "ubicada")], 1)


class GeoCoverageCheckTests(unittest.TestCase):
    def test_alerts_only_on_sources_below_the_coverage_with_enough_listings(self):
        from tools.platform_health import geo_check
        rows = [
            {"source": "facebook", "total": 1000, "located": 700},
            {"source": "kavak", "total": 450, "located": 450},
            {"source": "gruporandazzo", "total": 274, "located": 0},      # known gap
            {"source": "v6", "total": 10, "located": 0},                  # too few to judge
        ]
        message = geo_check(rows)
        self.assertIn("facebook 70 % (700/1000)", message)
        self.assertNotIn("kavak", message)
        self.assertNotIn("gruporandazzo", message)
        self.assertNotIn("v6", message)
        self.assertIsNone(geo_check([rows[1]]))


if __name__ == "__main__":
    unittest.main()
