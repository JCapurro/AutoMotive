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
ALL_ON = {"trial_no_matches": True, "trial_ended": True, "pass_expiring": True, "pass_expires_today": True,
          "count_after_expiry": True, "search_activated": True}


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
                                                         {"model": "Ford Focus", "found": 12, "below": 3}),
                          "lifecycle_pass_expiring": email("pass_expiring", {"found": 18, "below": 4, "ended": False}),
                          "lifecycle_pass_expires_today": email("pass_expires_today",
                                                                {"found": 18, "below": 4, "ended": False}),
                          "lifecycle_count_after_expiry": email("count_after_expiry",
                                                                {"model": "Ford Focus", "found": 9, "below": 2,
                                                                 "stage": 7}),
                          "lifecycle_search_activated": email("search_activated",
                                                              {"model": "Ford Focus", "found": 14, "below": 2})}.items():
            with self.subTest(name=name):
                text = render(msg)
                path = SNAPSHOTS / f"{name}.txt"
                if os.getenv("UPDATE_SNAPSHOTS") or not path.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8", newline="\n")
                self.assertEqual(text, path.read_text(encoding="utf-8"))


class SearchActivatedEmailTests(unittest.TestCase):
    """The welcome: 45 minutes after the account's first search."""

    def lines(self, msg: templates.EmailMessage) -> list[str]:
        return msg.text.split("\n—\n")[0].splitlines()

    def test_what_it_found_and_how_to_keep_the_alerts_out_of_spam(self):
        msg = email("search_activated", {"model": "Ford Focus", "found": 14, "below": 2})
        self.assertEqual(msg.subject, "Tu búsqueda de Ford Focus ya está activa")
        self.assertEqual(self.lines(msg), [
            "Tu búsqueda de Ford Focus ya está activa",
            "Ya encontramos 14 autos que coinciden con tu búsqueda de Ford Focus, y 2 están por debajo de "
            "publicaciones comparables. Te avisamos de los nuevos apenas aparezcan.",
            "Para que nuestras alertas no terminen en Spam o Promociones, agregá este remitente a tus contactos "
            "o mové este email a Principal.",
            "Ver mis resultados: https://automotive.app/m/41",
        ])

    def test_nothing_found_yet_and_no_model(self):
        msg = email("search_activated", {"found": 0, "below": 0})
        self.assertEqual(msg.subject, "Tu búsqueda ya está activa")
        self.assertEqual(self.lines(msg)[1], "Ya estamos revisando las publicaciones para tu búsqueda. "
                                             "Todavía no apareció ninguno que coincida: te avisamos apenas aparezca.")
        self.assertEqual(email("search_activated", {"model": "Ford Ka", "found": 1})
                         .text.splitlines()[1], "Ya encontramos 1 auto que coincide con tu búsqueda de Ford Ka. "
                         "Te avisamos de los nuevos apenas aparezcan.")


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


class PassExpiryEmailTests(unittest.TestCase):
    """2.3: before Particular ends."""

    def lines(self, msg: templates.EmailMessage) -> list[str]:
        return msg.text.split("\n—\n")[0].splitlines()

    def test_five_days_before(self):
        msg = email("pass_expiring", {"found": 18, "below": 4, "ended": False})
        self.assertEqual(msg.subject, "Te quedan 5 días de Ese Auto")
        self.assertEqual(self.lines(msg), [
            "Te quedan 5 días de Ese Auto",
            "Desde que activaste Particular encontramos 18 autos, 4 por debajo de comparables.",
            "Si todavía no lo encontraste, extendé 30 días más: se suman a tu vencimiento.",
            "Extender 30 días: https://automotive.app/m/41",
        ])

    def test_the_last_day_adds_what_happens_tomorrow(self):
        msg = email("pass_expires_today", {"found": 18, "below": 0, "ended": False})
        self.assertEqual(msg.subject, "Hoy vence tu acceso a Ese Auto")
        self.assertEqual(self.lines(msg)[1:4], [
            "Desde que activaste Particular encontramos 18 autos.",
            "Si todavía no lo encontraste, extendé 30 días más: se suman a tu vencimiento.",
            "Desde mañana dejamos de buscar y de avisarte. Tu historial y tus favoritos quedan guardados.",
        ])

    def test_nothing_found_and_a_pass_that_already_ended_that_morning(self):
        msg = email("pass_expires_today", {"found": 0, "below": 0, "ended": True})
        self.assertEqual(self.lines(msg)[1:3], ["Si todavía no lo encontraste, extendé 30 días más.",
                                                 "Tu historial y tus favoritos quedan guardados."])
        self.assertNotIn("encontramos", msg.text)
        self.assertNotIn("Desde mañana", msg.text)


class CountAfterExpiryEmailTests(unittest.TestCase):
    """2.5: what appeared since access ended, never the cars."""

    def lines(self, msg: templates.EmailMessage) -> list[str]:
        return msg.text.split("\n—\n")[0].splitlines()

    def test_the_plans_document_copy(self):
        msg = email("count_after_expiry", {"model": "Ford Focus", "found": 9, "below": 2, "stage": 14})
        self.assertEqual(msg.subject, "Aparecieron 9 autos nuevos para tu búsqueda de Ford Focus")
        self.assertEqual(self.lines(msg), [
            "Aparecieron 9 autos nuevos para tu búsqueda de Ford Focus",
            "Desde que venció tu acceso aparecieron 9 autos nuevos que coinciden con tu búsqueda, "
            "y 2 están por debajo de comparables.",
            "Reactivá para verlos.",
            "Reactivar por $15.000: https://automotive.app/m/41",
        ])

    def test_one_car_none_below_and_no_model(self):
        msg = email("count_after_expiry", {"found": 1, "below": 0})
        self.assertEqual(msg.subject, "Apareció 1 auto nuevo para tu búsqueda")
        self.assertEqual(self.lines(msg)[1:3], [
            "Desde que venció tu acceso apareció 1 auto nuevo que coincide con tu búsqueda.",
            "Reactivá para verlo.",
        ])
        self.assertNotIn("comparables", msg.text)

    def test_without_a_usable_price_the_button_names_none(self):
        msg = email("count_after_expiry", {"model": "Ford Focus", "found": 3, "below": 3},
                    offer={"pass_30": {"amount": "gratis", "currency": "ARS", "days": 30}})
        self.assertIn("Reactivar: https://automotive.app/m/41", msg.text)
        self.assertNotIn("$", msg.text)
        self.assertIn("y 3 están por debajo de comparables", msg.text)

    def test_never_an_email_about_zero_cars(self):
        for payload in ({"model": "Ford Focus", "found": 0, "below": 0}, {}):
            with self.assertRaises(ValueError):
                email("count_after_expiry", payload)


class PlanEmailCopyTests(unittest.TestCase):
    def test_no_banned_or_forbidden_words(self):
        for msg in (email("trial_no_matches", {"model": "Ford Focus"}),
                    email("trial_ended", {"model": "Ford Focus", "found": 12, "below": 3}),
                    email("pass_expiring", {"found": 18, "below": 4}),
                    email("pass_expires_today", {"found": 18, "below": 4}),
                    email("count_after_expiry", {"model": "Ford Focus", "found": 9, "below": 2}),
                    email("search_activated", {"model": "Ford Focus", "found": 14, "below": 2})):
            text = normalize_text(f"{msg.subject} {msg.text} {msg.html}")
            for term in BANNED + FORBIDDEN_TERMS:
                self.assertNotRegex(text, rf"\b{normalize_text(term)}\b", term)

    def test_unknown_kinds_are_refused(self):
        with self.assertRaises(ValueError):
            email("pass_renewed", {})


class SettingsTests(unittest.TestCase):
    def test_defaults(self):
        cfg = settings({})
        self.assertEqual((cfg["enabled"], cfg["send_from"], cfg["send_until"], cfg["window_hours"], cfg["max_per_day"]),
                         (True, time(9), time(21), 48.0, 30))
        self.assertEqual(cfg["kinds"], ALL_ON)
        self.assertEqual(settings(None), cfg)
        self.assertEqual(DEFAULTS["kinds"], ALL_ON)

    def test_bad_values_fall_back(self):
        cfg = settings({"enabled": "quizás", "send_from": "22:00", "send_until": "08:00", "window_hours": "x",
                        "max_per_day": -1, "kinds": "todos"})
        self.assertEqual((cfg["enabled"], cfg["send_from"], cfg["send_until"], cfg["window_hours"], cfg["max_per_day"]),
                         (True, time(9), time(21), 48.0, 30))
        self.assertEqual(cfg["kinds"], ALL_ON)

    def test_each_kind_can_be_turned_off(self):
        cfg = settings({"kinds": {"trial_no_matches": False, "pass_expiring": "false", "count_after_expiry": " FALSE",
                                  "pass_renewed": True}})
        self.assertEqual(cfg["kinds"], {**ALL_ON, "trial_no_matches": False, "pass_expiring": False,
                                        "count_after_expiry": False})

    def test_the_window_outlasts_the_night(self):
        self.assertEqual(settings({"window_hours": 6})["window_hours"], 48.0)
        self.assertEqual(settings({"window_hours": 13})["window_hours"], 13.0)


if __name__ == "__main__":
    unittest.main()
