"""Aviso de auto cerca de la zona: the settings, the pick and the email
(intelligence/near_zone.py, notifications/near_zone.py, pipeline/near_zone.py)."""
from __future__ import annotations

import unittest
from datetime import datetime, time, timedelta, timezone
from unittest import mock

from intelligence import near_zone as nz
from notifications import near_zone as notice
from notifications.channels.base import SendResult
from notifications.links import Links
from pipeline import near_zone as job

NOW = datetime(2026, 11, 14, 15, tzinfo=timezone.utc)          # 12:00 in Argentina
CREATED = NOW - timedelta(days=2)
CFG = nz.settings({"enabled": True})
# Buenos Aires (Obelisco); one degree of latitude is about 111 km.
LAT, LON = -34.6037, -58.3816
LINKS = Links("https://automotive.app")


def listing(id: int, km_north: float, **over) -> dict:
    return {"id": id, "make": "Ford", "model": "Focus", "year": 2016, "price": 12_000, "currency": "USD",
            "price_usd": 12_000, "price_partial": False, "mileage_km": 80_000, "source": "mercadolibre",
            "lat": LAT + km_north / 111.19, "lon": LON, "location_text": "Pilar",
            "url": f"https://autos.example/{id}", "images": ["https://img.example/1.jpg"],
            "first_seen_at": NOW - timedelta(hours=6), "published_at": NOW - timedelta(hours=8), **over}


def profile(radius: float = 30, **filters) -> dict:
    return {"id": 7, "filters": {"make": "Ford", "model": "Focus", "location_label": "Laferrere", **filters},
            "preferences": {}, "origin_lat": LAT, "origin_lon": LON, "radius_km": radius}


def pick(listings, prof=None, **kw):
    return nz.pick(listings, prof or profile(), created_at=CREATED, now=NOW, cfg=CFG, **kw)


class SettingsTest(unittest.TestCase):
    def test_ships_off_and_only_true_turns_it_on(self):
        self.assertFalse(nz.settings(None)["enabled"])
        self.assertFalse(nz.settings({"enabled": "true"})["enabled"])
        self.assertTrue(nz.settings({"enabled": True})["enabled"])

    def test_bad_values_fall_back(self):
        cfg = nz.settings({"enabled": True, "max_extra_km": "lejos", "cooldown_days": -1, "max_results": True,
                           "send_from": "22:00", "send_until": "09:00"})
        self.assertEqual((cfg["max_extra_km"], cfg["cooldown_days"], cfg["max_results"]), (100, 3, 3))
        self.assertEqual((cfg["send_from"], cfg["send_until"]), (time(9), time(21)))


class PickTest(unittest.TestCase):
    def test_the_closest_car_only_the_zone_leaves_out(self):
        found = pick([listing(1, 90), listing(2, 45), listing(3, 20)])
        self.assertEqual(found[0]["id"], 2)
        self.assertAlmostEqual(found[1], 45, delta=0.5)

    def test_inside_the_zone_or_too_far_is_not_told(self):
        self.assertIsNone(pick([listing(1, 20), listing(2, 131)]))

    def test_another_filter_failing_is_not_told(self):
        self.assertIsNone(pick([listing(1, 45, year=2010)], profile(year_min=2015)))
        self.assertIsNone(pick([listing(1, 45, price=30_000, price_usd=30_000)], profile(price_max=15_000)))

    def test_a_listing_without_a_year_is_never_told(self):
        # 14/11/2026, first pass: a search for a 2003 Gol was told about a Facebook listing without a year.
        self.assertIsNone(pick([listing(1, 45, year=None)], profile(year_min=2003, year_max=2003)))
        self.assertIsNone(pick([listing(1, 45, year=None)]))

    def test_what_the_search_asked_for_must_be_known(self):
        self.assertIsNone(pick([listing(1, 45, mileage_km=None)], profile(km_max=100_000)))
        self.assertIsNone(pick([listing(1, 45, transmission=None)], profile(transmission="automatic")))
        self.assertEqual(pick([listing(1, 45, mileage_km=None)])[0]["id"], 1)      # nothing asked about km

    def test_a_part_a_scale_model_or_a_wanted_post_is_never_told(self):
        for title in ("Paragolpes delantero Ford Focus", "Ford Focus escala 1:24 Welly", "Busco Ford Focus 2016"):
            with self.subTest(title=title):
                self.assertIsNone(pick([listing(1, 45, title=title)]))

    def test_the_first_pass_of_14_11(self):
        """The six listings told that day, as stored: only the three with a year are told now."""
        gol = {"make": "Volkswagen", "model": "Gol"}
        cases = [
            (False, {**gol, "title": "Volkswagen Gol 1.6 3 ptas con aire y dirección", "year": None, "mileage_km": None,
                     "price": 3500}, {**gol, "year_min": 2003, "year_max": 2003}),
            (True, {**gol, "title": "Volkswagen Gol", "year": 1997, "mileage_km": None, "price": 3_500_000,
                    "currency": "ARS", "price_usd": 2500}, {**gol, "price_max": 7_000_000, "currency": "ARS"}),
            (True, {"make": "Volkswagen", "model": "Amarok", "title": "2022 Volkswagen Amarok", "year": 2022,
                    "mileage_km": None, "price": 25_300_000, "currency": "ARS", "price_usd": 18_000},
             {"make": "Volkswagen", "model": "Amarok", "year_min": 2020, "year_max": 2026, "price_max": 30_000_000,
              "currency": "ARS"}),
            (True, {"title": "FLORENCIO SÁNCHEZ AUTOMOTORES", "year": 2008, "mileage_km": 230_000, "price": 6000},
             {"year_max": 2015, "price_max": 9500, "currency": "USD"}),
            (False, {"make": "Volkswagen", "model": "Gol Trend", "title": "Motor Volkswagen CFZ gol Trend/ Suran/ Fox",
                     "year": None, "mileage_km": None, "price": 1400},
             {"make": "Volkswagen", "model": "Gol Trend", "year_min": 2004, "year_max": 2008, "price_max": 3400,
              "currency": "USD"}),
            (False, {"make": "Toyota", "model": "Etios", "title": "Toyota Etios con cola [hidden information]km",
                     "year": None, "mileage_km": None, "price": 13_500},
             {"make": "Toyota", "model": "Etios", "year_min": 2017, "year_max": 2017}),
        ]
        for told, car, filters in cases:
            with self.subTest(title=car["title"]):
                car = {"price_usd": car["price"], **car}
                found = pick([listing(1, 45, **car)], profile(**filters), fx_rate=1400.0)
                self.assertEqual(found is not None, told)

    def test_only_what_is_new_for_the_search_and_recent(self):
        old_for_search = listing(1, 45, first_seen_at=CREATED - timedelta(hours=1))
        old_stock = listing(2, 45, published_at=NOW - timedelta(days=10))
        self.assertIsNone(pick([old_for_search, old_stock]))

    def test_needs_a_full_price_and_coordinates(self):
        self.assertIsNone(pick([listing(1, 45, price=None), listing(2, 45, price_partial=True),
                                listing(3, 45, lat=None)]))

    def test_what_was_already_told_is_skipped(self):
        self.assertEqual(pick([listing(1, 45), listing(2, 60)], seen={1})[0]["id"], 2)

    def test_a_search_without_one_zone_of_its_own_is_not_eligible(self):
        nationwide = {**profile(), "radius_km": None}
        two_places = profile(extra_locations=[{"lat": -31.4, "lon": -64.2, "radius_km": 50}])
        no_model = {**profile(), "filters": {"make": "Ford"}}
        for prof in (nationwide, two_places, no_model):
            self.assertFalse(nz.eligible(prof))
        self.assertIsNone(pick([listing(1, 45)], nationwide))
        self.assertIsNone(pick([listing(1, 45)], two_places))
        self.assertTrue(nz.eligible(profile()))


class EmailTest(unittest.TestCase):
    ROW = {**profile(), "unsubscribe_token": "3f0c1a52-6c55-4a43-9f39-0d8f3c7c2b11"}

    def test_says_the_distance_the_radius_and_both_ways_out(self):
        msg = notice.email_message(self.ROW, listing(2, 45), 45.2, LINKS, NOW)
        self.assertEqual(msg.subject, "Apareció un Ford Focus 2016 a 45 km de Laferrere")
        self.assertIn("Está a 45 km de Laferrere. Tu búsqueda llega hasta 30 km", msg.text)
        self.assertIn("USD 12.000", msg.text)
        self.assertIn("Ver la publicación: https://autos.example/2", msg.text)
        self.assertIn("Ampliar la zona de mi búsqueda: https://automotive.app/app/searches/7", msg.text)
        self.assertIn("https://automotive.app/baja?t=", msg.text)
        for text in ("https://autos.example/2", "https://automotive.app/app/searches/7",
                     "https://img.example/1.jpg", "Un auto cerca de tu zona"):
            self.assertIn(text, msg.html)

    def test_the_place_is_said_without_the_webs_notes(self):
        for label, said in (("La Plata (zona aproximada)", "La Plata"), ("Morón (GBA)", "Morón"),
                            ("Mi ubicación actual", "tu zona"), ("  ", "tu zona"), ("Villa María, Córdoba",
                                                                                   "Villa María, Córdoba")):
            with self.subTest(label=label):
                row = {**self.ROW, "filters": {"make": "Ford", "model": "Focus", "location_label": label}}
                msg = notice.email_message(row, listing(2, 45), 45, LINKS, NOW)
                self.assertEqual(msg.subject, f"Apareció un Ford Focus 2016 a 45 km de {said}")
                self.assertIn(f"Está a 45 km de {said}. ", msg.text)

    def test_without_a_place_label_it_says_tu_zona(self):
        row = {**self.ROW, "filters": {"make": "Ford", "model": "Focus"}}
        self.assertEqual(notice.email_message(row, listing(2, 45), 45, LINKS, NOW).subject,
                         "Apareció un Ford Focus 2016 a 45 km de tu zona")


class _Channel:
    def __init__(self, ok: bool = True):
        self.ok, self.sent = ok, []

    async def send_message(self, to, msg, **kw):
        self.sent.append((to, msg.subject, kw["idempotency_key"]))
        return SendResult(self.ok, None if self.ok else "boom")


class _Fx:
    rate = 1400.0


class _Cx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class RunTest(unittest.IsolatedAsyncioTestCase):
    ROW = {**profile(), "user_id": "u1", "created_at": CREATED, "email": "ana@example.com",
           "unsubscribe_token": "t", "seller_filter": False, "result_count": 0}

    async def run_job(self, *, cfg=None, rows=None, kept=False, channel=None, now=NOW, claim=11):
        channel = channel or _Channel()
        marks: list = []

        async def mark(notice_id, *, sent, error=None):
            marks.append((notice_id, sent))

        async def const(value):
            return value

        with mock.patch.object(job, "get_config", lambda *a: const(cfg if cfg is not None else {"enabled": True})), \
             mock.patch.object(job.repo, "candidates", lambda **kw: const([self.ROW] if rows is None else rows)), \
             mock.patch.object(job.repo, "told", lambda pid: const(set())), \
             mock.patch.object(job.repo, "claim", lambda *a: const(claim)), \
             mock.patch.object(job.repo, "mark", mark), \
             mock.patch.object(job, "zone_kept", lambda row: const(kept)), \
             mock.patch.object(job, "recent_active", lambda *a, **kw: const([listing(2, 45)])), \
             mock.patch.object(job, "quote_for_today", lambda cx: const(_Fx())), \
             mock.patch.object(job.db, "connection", lambda: _Cx()):
            sent = await job.run_near_zone(channel, LINKS, now=now)
        return sent, channel, marks

    async def test_sends_one_email_and_marks_it(self):
        sent, channel, marks = await self.run_job()
        self.assertEqual(sent, 1)
        self.assertEqual(channel.sent, [("ana@example.com", "Apareció un Ford Focus 2016 a 45 km de Laferrere",
                                         "near-zone-11")])
        self.assertEqual(marks, [(11, True)])

    async def test_off_by_default_and_outside_the_hours(self):
        self.assertEqual((await self.run_job(cfg={}))[0], 0)
        self.assertEqual((await self.run_job(now=NOW.replace(hour=3)))[0], 0)       # 00:00 in Argentina

    async def test_a_kept_zone_or_a_listing_already_claimed_gets_nothing(self):
        self.assertEqual((await self.run_job(kept=True))[1].sent, [])
        self.assertEqual((await self.run_job(claim=None))[1].sent, [])

    async def test_a_failed_send_is_marked_failed(self):
        sent, _, marks = await self.run_job(channel=_Channel(ok=False))
        self.assertEqual((sent, marks), (0, [(11, False)]))


if __name__ == "__main__":
    unittest.main()
