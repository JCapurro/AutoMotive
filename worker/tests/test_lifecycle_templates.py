"""The plan emails (docs/MAILS_DE_PLAN.md): snapshots, the plans document's
copy and the settings the worker reads from app_config.lifecycle_emails.

The snapshots live in tests/snapshots/notifications/lifecycle_*.txt. After an
intended copy change, regenerate them with UPDATE_SNAPSHOTS=1 pytest and
review the diff.
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, time, timezone
from pathlib import Path

from intelligence.copy import FORBIDDEN_TERMS
from normalization.normalize import normalize_text
from notifications import templates
from notifications.lifecycle import DEFAULTS, settings
from notifications.links import Links


SNAPSHOTS = Path(__file__).parent / "snapshots" / "notifications"
LINKS = Links("https://automotive.app")
NOW = datetime(2026, 10, 20, 13, 0, tzinfo=timezone.utc)          # 10:00 in Argentina
OFFER = {"version": "ars-launch-2026-10",
         "pass_30": {"amount": 15000, "currency": "ARS", "days": 30},
         "pro_monthly": {"amount": 75000, "currency": "ARS", "days": 30}}
LIMITS = {"enforced": True, "free": {"max_profiles": 1}, "pass": {"max_profiles": 3}, "pro": {"max_profiles": 20}}
TOKEN = "3f0c1a52-6c55-4a43-9f39-0d8f3c7c2b11"
# The plans document forbids these in every plan email.
BANNED = ("en tiempo real", "todos los portales", "el mas barato")


def render(msg: templates.EmailMessage) -> str:
    return "\n".join(["=== email subject ===", msg.subject, "=== email text ===", msg.text,
                      "=== email html ===", msg.html, ""])


def email(kind: str, payload: dict, **kw) -> templates.EmailMessage:
    row = {"id": 41, "kind": kind, "payload": payload, "unsubscribe_token": TOKEN}
    return templates.lifecycle_email(row, LINKS, NOW, offer=kw.get("offer", OFFER), limits=kw.get("limits", LIMITS))


class PlanEmailSnapshotTests(unittest.TestCase):
    maxDiff = None

    def test_snapshots(self):
        for name, msg in {"lifecycle_trial_no_matches": email("trial_no_matches", {"model": "Ford Focus"}),
                          "lifecycle_trial_ended": email("trial_ended",
                                                         {"model": "Ford Focus", "found": 12, "below": 3})}.items():
            with self.subTest(name=name):
                text = render(msg)
                path = SNAPSHOTS / f"{name}.txt"
                if os.getenv("UPDATE_SNAPSHOTS") or not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8", newline="\n")
                self.assertEqual(text, path.read_text(encoding="utf-8"))


class TrialNoMatchesEmailTests(unittest.TestCase):
    """2.1: 24 h into the trial without a new match."""

    def test_the_plans_document_copy(self):
        msg = email("trial_no_matches", {"model": "Ford Focus"})
        self.assertEqual(msg.subject, "Tu búsqueda de Ford Focus todavía no tuvo coincidencias nuevas")
        self.assertEqual(msg.text.splitlines()[:3], [
            "Tu búsqueda de Ford Focus todavía no tuvo coincidencias nuevas",
            "En las primeras 24 horas no apareció ningún auto nuevo con tus filtros. Si ampliás años, "
            "kilómetros o zona, vas a ver más opciones en lo que queda de la prueba.",
            "Ajustar filtros: https://automotive.app/m/41",
        ])
        self.assertIn(f"Dejar de recibir estos emails: https://automotive.app/baja?t={TOKEN}", msg.text)
        self.assertIn('href="https://automotive.app/m/41"', msg.html)

    def test_without_a_model_it_still_reads_well(self):
        self.assertEqual(email("trial_no_matches", {}).subject, "Tu búsqueda todavía no tuvo coincidencias nuevas")


class TrialEndedEmailTests(unittest.TestCase):
    """2.2: the 72 h trial ended without a purchase."""

    def lines(self, msg: templates.EmailMessage) -> list[str]:
        return msg.text.split("\n—\n")[0].splitlines()

    def test_the_plans_document_copy(self):
        msg = email("trial_ended", {"model": "Ford Focus", "found": 12, "below": 3})
        self.assertEqual(msg.subject, "Terminó tu prueba: encontramos 12 autos para tu búsqueda")
        self.assertEqual(self.lines(msg), [
            "Terminó tu prueba",
            "En 3 días encontramos 12 autos para tu búsqueda de Ford Focus, y 3 estaban por debajo "
            "de publicaciones comparables.",
            "Para seguir recibiendo avisos, Particular sale $15.000 por 30 días, con 3 búsquedas y pago único.",
            "Tu historial y tus favoritos quedan guardados.",
            "Seguir con Particular: https://automotive.app/m/41",
        ])

    def test_a_number_that_is_zero_takes_its_sentence_with_it(self):
        none_below = email("trial_ended", {"model": "Ford Focus", "found": 4, "below": 0})
        self.assertIn("En 3 días encontramos 4 autos para tu búsqueda de Ford Focus.", none_below.text)
        self.assertNotIn("por debajo", none_below.text)
        nothing = email("trial_ended", {"model": "Ford Focus", "found": 0, "below": 0})
        self.assertEqual(nothing.subject, "Terminó tu prueba")
        self.assertNotIn("encontramos", nothing.text)
        self.assertEqual(self.lines(nothing)[1], "Para seguir recibiendo avisos, Particular sale $15.000 por 30 días, "
                                                 "con 3 búsquedas y pago único.")

    def test_one_car_in_the_singular(self):
        msg = email("trial_ended", {"model": "Ford Focus", "found": 1, "below": 1})
        self.assertEqual(msg.subject, "Terminó tu prueba: encontramos 1 auto para tu búsqueda")
        self.assertIn("encontramos 1 auto para tu búsqueda de Ford Focus, y 1 estaba por debajo", msg.text)

    def test_price_and_searches_follow_the_configuration_never_a_wrong_price(self):
        offer = {**OFFER, "pass_30": {"amount": 18000, "currency": "ARS", "days": 30}}
        limits = {"pass": {"max_profiles": 4}}
        self.assertIn("Particular sale $18.000 por 30 días, con 4 búsquedas y pago único.",
                      email("trial_ended", {"found": 2}, offer=offer, limits=limits).text)
        for broken in (None, {}, {"pass_30": {"price_usd": 12}}, {"pass_30": {"amount": 15000, "currency": "USD", "days": 30}}):
            with self.subTest(offer=broken):
                text = email("trial_ended", {"found": 2}, offer=broken).text
                self.assertIn("Para seguir recibiendo avisos, elegí Particular.", text)
                self.assertNotIn("$", text)

    def test_without_a_model(self):
        self.assertIn("En 3 días encontramos 2 autos para tu búsqueda.", email("trial_ended", {"found": 2}).text)


class PlanEmailCopyTests(unittest.TestCase):
    def test_no_banned_or_forbidden_words(self):
        for msg in (email("trial_no_matches", {"model": "Ford Focus"}),
                    email("trial_ended", {"model": "Ford Focus", "found": 12, "below": 3})):
            text = normalize_text(f"{msg.subject} {msg.text} {msg.html}")
            for term in BANNED + FORBIDDEN_TERMS:
                self.assertNotRegex(text, rf"\b{normalize_text(term)}\b", term)

    def test_unknown_kinds_are_refused(self):
        with self.assertRaises(ValueError):
            email("count_after_expiry", {})


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        cfg = settings({})
        self.assertEqual((cfg["enabled"], cfg["send_from"], cfg["send_until"], cfg["window_hours"], cfg["max_per_day"]),
                         (True, time(9), time(21), 48.0, 30))
        self.assertEqual(cfg["kinds"], {"trial_ended": True, "trial_no_matches": True})
        self.assertEqual(settings(None), cfg)
        self.assertEqual(DEFAULTS["kinds"], {"trial_no_matches": True, "trial_ended": True})

    def test_bad_values_fall_back(self):
        cfg = settings({"enabled": "quizás", "send_from": "22:00", "send_until": "08:00", "window_hours": "x",
                        "max_per_day": -1, "kinds": "todos"})
        self.assertEqual((cfg["enabled"], cfg["send_from"], cfg["send_until"], cfg["window_hours"], cfg["max_per_day"]),
                         (True, time(9), time(21), 48.0, 30))
        self.assertEqual(cfg["kinds"], {"trial_ended": True, "trial_no_matches": True})

    def test_each_kind_can_be_turned_off(self):
        cfg = settings({"kinds": {"trial_no_matches": False, "pass_expiring": True}})
        self.assertEqual(cfg["kinds"], {"trial_ended": True, "trial_no_matches": False})

    def test_the_window_outlasts_the_night(self):
        self.assertEqual(settings({"window_hours": 6})["window_hours"], 48.0)
        self.assertEqual(settings({"window_hours": 13})["window_hours"], 13.0)


if __name__ == "__main__":
    unittest.main()
