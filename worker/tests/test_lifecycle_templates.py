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
# Every kind on, except remarketing and the extra trial: they start off.
ALL_ON = {"trial_no_matches": True, "trial_ended": True, "pass_expiring": True, "pass_expires_today": True,
          "count_after_expiry": True, "search_activated": True,
          "search_abandoned": False, "search_not_started": False, "search_feedback": False,
          "bonus_trial_offer": False, "bonus_trial_ending": False, "bonus_trial_ended": False}


def render(msg: templates.EmailMessage) -> str:
    return "\n".join(["=== email subject ===", msg.subject, "=== email text ===", msg.text,
                      "=== email html ===", msg.html, ""])


REMARKETING = {"reply_to": "juan@automotive.test"}


def email(kind: str, payload: dict, **kw) -> templates.EmailMessage:
    row = {"id": 41, "kind": kind, "payload": payload, "unsubscribe_token": TOKEN}
    return templates.lifecycle_email(row, LINKS, NOW, offer=kw.get("offer", OFFER), limits=kw.get("limits", LIMITS),
                                     remarketing=kw.get("remarketing", REMARKETING))


ABANDONED = {"text": "Toyota hilux 2.5 de 2013 a 2016", "model": "Toyota Hilux",
             "asked_at": "2026-10-24T02:30:00+00:00", "job_id": 7}


MISSED = {"model": "Ford Focus", "found": 9, "below": 2, "stage": 7, "ended_at": "2026-10-10T12:00:00+00:00",
          "car": {"listing_id": 2, "title": "Ford Focus SE 2017", "make": "Ford", "model": "Focus", "trim": "SE",
                  "year": 2017, "price": 15900, "currency": "USD", "km": 68000, "location": "San Isidro",
                  "images": ["https://img.example/focus-1.jpg", "https://img.example/focus-2.jpg"],
                  "below": True, "diff_pct": 18.4, "gone": True, "days_listed": 3}}


BONUS = {"model": "Ford Ka", "found": 652, "new": 41, "below": 5,
         "cars": [{"title": "Ford Ka 1.5 S", "year": 2018, "price": 9800, "currency": "USD", "km": 72000, "below": True},
                  {"title": "Ford Ka SE 2019", "year": 2019, "price": 14500000, "currency": "ARS", "km": 51000}]}


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
                          "lifecycle_count_after_expiry_missed": email("count_after_expiry", MISSED),
                          "lifecycle_search_activated": email("search_activated",
                                                              {"model": "Ford Focus", "found": 14, "below": 2}),
                          "lifecycle_search_abandoned": email("search_abandoned", ABANDONED),
                          "lifecycle_search_not_started": email("search_not_started", {}),
                          "lifecycle_search_feedback": email("search_feedback",
                                                             {"model": "Toyota Hilux", "after": "search_abandoned"}),
                          "lifecycle_bonus_trial_offer": email("bonus_trial_offer", BONUS),
                          "lifecycle_bonus_trial_ending": email("bonus_trial_ending",
                                                                {"model": "Ford Ka", "found": 12, "below": 2,
                                                                 "ends_at": "2026-11-02T22:00:00+00:00"}),
                          "lifecycle_bonus_trial_ended": email("bonus_trial_ended",
                                                               {"model": "Ford Ka", "found": 12, "below": 1}),
                          }.items():
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
    """2.5 without a car to show: the count of what appeared since access ended."""

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


class MissedCarEmailTests(unittest.TestCase):
    """2.5 with payload.car: the opportunity the paused search missed."""

    def lines(self, msg: templates.EmailMessage) -> list[str]:
        return msg.text.split("\n—\n")[0].splitlines()

    def missed(self, **car) -> templates.EmailMessage:
        return email("count_after_expiry", {**MISSED, "car": {**MISSED["car"], **car}})

    def test_a_gone_car_with_photo_price_and_how_long_it_lasted(self):
        msg = email("count_after_expiry", MISSED)
        self.assertEqual(msg.subject, "Te perdiste este Ford Focus SE 2017, 18% debajo de comparables")
        self.assertEqual(self.lines(msg), [
            "La oportunidad que te perdiste",
            "Ford Focus SE 2017",
            "USD 15.900",
            "18% debajo de publicaciones comparables.",
            "68.000 km · San Isidro",
            "Estuvo publicado 3 días y ya no está.",
            "Con tu búsqueda activa, te hubiéramos avisado apenas apareció.",
            "Y no fue el único: desde que venció tu acceso aparecieron 9 autos nuevos para tu búsqueda, "
            "2 por debajo de comparables.",
            "Reactivar por $15.000: https://automotive.app/m/41",
        ])
        self.assertIn('src="https://img.example/focus-1.jpg"', msg.html)
        self.assertIn("background:#ffe14d;font-weight:bold", msg.html)     # the % line, highlighted

    def test_a_car_still_published_is_not_called_lost(self):
        msg = self.missed(gone=False, days_listed=None)
        self.assertEqual(msg.subject, "Apareció este Ford Focus SE 2017 y tu búsqueda estaba pausada, "
                                      "18% debajo de comparables")
        self.assertIn("Esto apareció mientras tu búsqueda estaba pausada", msg.text)
        self.assertIn("Todavía está publicado: reactivá tu búsqueda para verlo.", msg.text)
        self.assertNotIn("perdiste", msg.text)
        self.assertNotIn("ya no está", msg.text)

    def test_zero_or_missing_numbers_leave_their_sentence_out(self):
        msg = email("count_after_expiry", {"found": 1, "below": 0, "car": {
            "title": "Ford Focus SE 2017", "price": 15900, "currency": "USD", "gone": True, "diff_pct": 0.3}})
        self.assertEqual(msg.subject, "Te perdiste este Ford Focus SE 2017")
        self.assertEqual(self.lines(msg)[3:], [
            "Ya no está publicado.",
            "Con tu búsqueda activa, te hubiéramos avisado apenas apareció.",
            "Reactivar por $15.000: https://automotive.app/m/41",
        ])
        self.assertNotIn("comparables", msg.text)
        self.assertIn("Foto no disponible", msg.html)

    def test_below_without_a_percentage(self):
        msg = self.missed(diff_pct=None)
        self.assertIn("Por debajo de publicaciones comparables.", msg.text)
        self.assertEqual(msg.subject, "Te perdiste este Ford Focus SE 2017")

    def test_without_a_showable_car_it_is_the_count(self):
        for car in (None, "x", {"title": "Ford Focus", "price": None}, {"price": 100}):
            with self.subTest(car=car):
                msg = email("count_after_expiry", {"model": "Ford Focus", "found": 9, "below": 2, "car": car})
                self.assertEqual(msg.subject, "Aparecieron 9 autos nuevos para tu búsqueda de Ford Focus")


class PlanEmailCopyTests(unittest.TestCase):
    def test_no_banned_or_forbidden_words(self):
        for msg in (email("trial_no_matches", {"model": "Ford Focus"}),
                    email("trial_ended", {"model": "Ford Focus", "found": 12, "below": 3}),
                    email("pass_expiring", {"found": 18, "below": 4}),
                    email("pass_expires_today", {"found": 18, "below": 4}),
                    email("count_after_expiry", {"model": "Ford Focus", "found": 9, "below": 2}),
                    email("count_after_expiry", MISSED),
                    email("count_after_expiry", {**MISSED, "car": {**MISSED["car"], "gone": False}}),
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


class RemarketingEmailTests(unittest.TestCase):
    """Accounts without a search (docs/MAILS_DE_PLAN.md, «Remarketing»)."""

    def test_the_brand_template_with_one_line_and_one_button(self):
        msg = email("search_abandoned", ABANDONED)
        self.assertEqual(msg.subject, "Tu búsqueda de Toyota Hilux está lista")
        self.assertEqual(msg.text.split("\n—\n")[0].splitlines(),
                         ["Tu búsqueda de Toyota Hilux está lista", templates.ABANDONED_BODY,
                          "Activar mi búsqueda: https://automotive.app/m/41"])
        self.assertIn("cid:", msg.html)
        self.assertIn("Menos buscar. Más encontrar.", msg.html)
        self.assertIn('/o/41?k=m"', msg.html)
        self.assertNotIn("/f/41", msg.text)

    def test_brand_sender_and_reply_to_from_the_config(self):
        msg = email("search_not_started", {})
        self.assertEqual((msg.from_name, msg.reply_to, msg.logo), (None, "juan@automotive.test", True))
        self.assertIsNone(email("search_not_started", {}, remarketing={"reply_to": "no es un email"}).reply_to)

    def test_the_follow_up_links_to_the_feedback_page(self):
        msg = email("search_feedback", {"model": "Toyota Hilux", "after": "search_abandoned"})
        self.assertEqual(msg.subject, "Tu Toyota Hilux te está esperando")
        self.assertIn("Activar mi búsqueda: https://automotive.app/m/41", msg.text)
        self.assertIn("¿Algo te frenó? Contanos: https://automotive.app/f/41", msg.text)
        self.assertIn('href="https://automotive.app/f/41"', msg.html)
        msg = email("search_feedback", {"after": "search_not_started"})
        self.assertEqual(msg.subject, "Tu próximo auto te está esperando")
        self.assertIn("Empezar mi búsqueda:", msg.text)

    def test_signed_links_sign_the_feedback_link_too(self):
        links = Links("https://automotive.app", "s" * 32)
        row = {"id": 41, "kind": "search_feedback", "payload": {}, "unsubscribe_token": TOKEN, "user_id": "u-1"}
        msg = templates.lifecycle_email(row, links, NOW)
        button = links.lifecycle(41, owner="u-1")
        signature = button.split("s=")[1]
        self.assertIn(button, msg.text)
        self.assertIn(f"/f/41?s={signature}", msg.text)

    def test_no_banned_or_forbidden_words(self):
        for kind, payload in (("search_abandoned", ABANDONED), ("search_not_started", {}),
                              ("search_feedback", {"model": "Toyota Hilux", "after": "search_abandoned"})):
            msg = email(kind, payload)
            text = normalize_text(f"{msg.subject} {msg.text} {msg.html}")
            for term in BANNED + FORBIDDEN_TERMS:
                self.assertNotRegex(text, rf"\b{normalize_text(term)}\b", term)


class BonusTrialEmailTests(unittest.TestCase):
    """The extra 7-day trial (docs/MAILS_DE_PLAN.md, «Prueba extra de 7 días»)."""

    def lines(self, msg: templates.EmailMessage) -> list[str]:
        return msg.text.split("\n—\n")[0].splitlines()

    def test_the_offer_says_what_appeared_in_one_line(self):
        msg = email("bonus_trial_offer", BONUS)
        self.assertEqual(msg.subject, "Te damos 7 días más para tu búsqueda de Ford Ka")
        self.assertEqual(self.lines(msg), ["Te damos 7 días más para tu búsqueda de Ford Ka",
                                           "Desde que pausamos tu búsqueda aparecieron 41 autos nuevos. "
                                           "Reactivala gratis 7 días, sin tarjeta.",
                                           "Activar mis 7 días: https://automotive.app/m/41"])
        self.assertNotIn("Ford Ka 1.5 S", msg.html)

    def test_nothing_new_falls_back_to_what_the_trial_found(self):
        lines = self.lines(email("bonus_trial_offer", {"found": 1, "new": 0}))
        self.assertEqual(lines[1], "En tu prueba encontramos 1 auto. Reactivala gratis 7 días, sin tarjeta.")

    def test_ending_names_the_day(self):
        lines = self.lines(email("bonus_trial_ending", {"found": 3, "ends_at": "2026-11-02T02:00:00+00:00"}))
        self.assertEqual(lines[:3], ["Te quedan 2 días gratis", "Ya encontramos 3 autos. El 1/11 tu búsqueda se pausa.",
                                     "Ver mis resultados: https://automotive.app/m/41"])
        self.assertTrue(email("bonus_trial_ending", {"found": 0}).html)

    def test_ended_without_results(self):
        msg = email("bonus_trial_ended", {"found": 0}, offer=None)
        self.assertEqual(msg.subject, "Terminaron tus 7 días")
        self.assertIn(templates.BONUS_ENDED_NONE, msg.text)

    def test_no_banned_or_forbidden_words(self):
        for kind, payload in (("bonus_trial_offer", BONUS), ("bonus_trial_ending", {"found": 3, "below": 1}),
                              ("bonus_trial_ended", {"found": 3, "below": 1})):
            msg = email(kind, payload)
            text = normalize_text(f"{msg.subject} {msg.text} {msg.html}")
            for term in BANNED + FORBIDDEN_TERMS:
                self.assertNotRegex(text, rf"\b{normalize_text(term)}\b", term)
