"""The free-trial reminder email (docs/RECORDATORIO_PRUEBA.md): snapshot, copy
and the settings the worker reads from app_config.trial_reminder.

The snapshot lives in tests/snapshots/notifications/trial_reminder.txt. After
an intended copy change, regenerate it with UPDATE_SNAPSHOTS=1 pytest and
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
from notifications.links import Links
from notifications.trial_reminder import DEFAULTS, settings


SNAPSHOTS = Path(__file__).parent / "snapshots" / "notifications"
LINKS = Links("https://automotive.app")
NOW = datetime(2026, 10, 9, 13, 0, tzinfo=timezone.utc)          # 10:00 in Argentina
ENDED = datetime(2026, 10, 9, 0, 30, tzinfo=timezone.utc)        # 8 de octubre, 21:30 in Argentina
OFFER = {"version": "ars-launch-2026-10",
         "pass_30": {"amount": 15000, "currency": "ARS", "days": 30},
         "pro_monthly": {"amount": 75000, "currency": "ARS", "days": 30}}
TOKEN = "3f0c1a52-6c55-4a43-9f39-0d8f3c7c2b11"
PLANS_URL = "https://automotive.app/app/pro?utm_source=email&utm_medium=email&utm_campaign=trial_reminder"


def render(msg: templates.EmailMessage) -> str:
    return "\n".join(["=== email subject ===", msg.subject, "=== email text ===", msg.text,
                      "=== email html ===", msg.html, ""])


class TrialReminderEmailTests(unittest.TestCase):
    maxDiff = None

    def email(self, **kw) -> templates.EmailMessage:
        args = {"trial_expires_at": ENDED, "links": LINKS, "unsubscribe_token": TOKEN, "now": NOW,
                "offer": OFFER, **kw}
        return templates.trial_reminder_email(**args)

    def test_snapshot(self):
        text = render(self.email())
        path = SNAPSHOTS / "trial_reminder.txt"
        if os.getenv("UPDATE_SNAPSHOTS") or not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        self.assertEqual(text, path.read_text(encoding="utf-8"))

    def test_copy_in_order(self):
        msg = self.email()
        self.assertEqual(msg.subject, "Terminó tu prueba gratis en Ese Auto")
        self.assertEqual(msg.text.splitlines()[:6], [
            "Terminó tu prueba de 3 días",
            "Tu prueba gratis venció el 8 de octubre a las 21:30 (hora de Argentina).",
            "Pausamos tu búsqueda y dejamos de mandarte alertas. Conservamos tus resultados y favoritos.",
            "Para volver a monitorear, elegí Particular (ARS 15.000 por 30 días, pago único) "
            "o Agencia (ARS 75.000 por mes).",
            "Después de pagar, reactivás tu búsqueda desde Ese Auto.",
            f"Ver planes: {PLANS_URL}",
        ])
        self.assertIn("No hay cobros automáticos: solo pagás si elegís un plan.", msg.text)
        self.assertIn(">TU PRUEBA GRATIS</p>", msg.html)
        self.assertIn(">Terminó tu prueba de 3 días</h1>", msg.html)
        self.assertIn("Tus resultados y favoritos siguen guardados. Elegí un plan para volver a recibir alertas.",
                      msg.html)
        self.assertNotIn("TUS ALERTAS", msg.html)
        self.assertNotIn("!", msg.text)

    def test_dates_in_argentina(self):
        msg = self.email(trial_expires_at=datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc))
        self.assertIn("venció el 31 de octubre a las 20:59", msg.text)
        naive = self.email(trial_expires_at=datetime(2026, 11, 1, 2, 5))   # read as UTC
        self.assertIn("venció el 31 de octubre a las 23:05", naive.text)
        self.assertIn("9 de octubre de 2026", self.email().html)      # the email's date, Argentina

    def test_plan_line_falls_back_without_a_valid_offer(self):
        fallback = "Para volver a monitorear, elegí Particular o Agencia."
        bad = [None, {}, "x", {"pass_30": OFFER["pass_30"]},
               {**OFFER, "pass_30": {"amount": 0, "currency": "ARS", "days": 30}},
               {**OFFER, "pro_monthly": {"amount": "mucho", "currency": "ARS"}},
               {**OFFER, "pass_30": {"amount": 15000, "currency": "", "days": 30}},
               {**OFFER, "pass_30": {"amount": 15000, "currency": "ARS", "days": None}},
               {**OFFER, "pass_30": {"amount": True, "currency": "ARS", "days": 30}}]
        for offer in bad:
            with self.subTest(offer=offer):
                text = self.email(offer=offer).text
                self.assertIn(fallback, text)
                self.assertNotIn("ARS", text)
        self.assertIn("Particular (ARS 12.500 por 30 días, pago único) o Agencia (ARS 80.000 por mes).",
                      self.email(offer={**OFFER, "pass_30": {"amount": "12500", "currency": "ARS", "days": 30},
                                        "pro_monthly": {"amount": 80000.0, "currency": "ARS"}}).text)

    def test_cta_is_a_plain_link_to_the_plans(self):
        msg = self.email()
        self.assertIn(f'href="{PLANS_URL.replace("&", "&amp;")}"', msg.html)
        self.assertNotIn("/r/", msg.text + msg.html)

    def test_unsubscribe_link_and_its_own_footer(self):
        msg = self.email()
        unsubscribe = f"https://automotive.app/baja?t={TOKEN}"
        self.assertIn(f"Dejar de recibir estos emails: {unsubscribe}", msg.text)
        self.assertIn(f'href="{unsubscribe}"', msg.html)
        footer = ("Recibís este email porque activaste una búsqueda gratis en Ese Auto. "
                  "Es el único aviso que te mandamos sobre el fin de la prueba.")
        self.assertIn(footer, msg.text)
        self.assertIn(footer, msg.html)
        self.assertNotIn(templates.EMAIL_FOOTER, msg.text + msg.html)   # "tenés búsquedas activas"
        without = self.email(unsubscribe_token=None)
        self.assertNotIn("/baja", without.text + without.html)

    def test_no_forbidden_terms(self):
        rendered = normalize_text(render(self.email()) + render(self.email(offer=None)))
        constants = normalize_text(" ".join(str(v) for k, v in vars(templates).items()
                                            if k.startswith("TRIAL_REMINDER") and isinstance(v, str)))
        for term in FORBIDDEN_TERMS:
            t = normalize_text(term)
            with self.subTest(term):
                self.assertNotRegex(rendered, rf"\b{t}\b")
                self.assertNotRegex(constants, rf"\b{t}\b")


class TrialReminderSettingsTests(unittest.TestCase):
    def test_defaults(self):
        cfg = settings(None)
        self.assertEqual(cfg, {"enabled": True, "delay_hours": 0.0, "window_hours": 48.0,
                               "send_from": time(9), "send_until": time(21), "max_per_day": 30})
        self.assertEqual(settings({}), cfg)
        self.assertEqual(settings(DEFAULTS), cfg)

    def test_values_from_app_config(self):
        cfg = settings({"enabled": False, "delay_hours": 2, "window_hours": 36, "send_from": "10:30",
                        "send_until": "20:00", "max_per_day": 5})
        self.assertEqual(cfg, {"enabled": False, "delay_hours": 2.0, "window_hours": 36.0,
                               "send_from": time(10, 30), "send_until": time(20), "max_per_day": 5})
        self.assertFalse(settings({"enabled": "false"})["enabled"])
        self.assertEqual(settings({"max_per_day": 0})["max_per_day"], 0)

    def test_bad_values_fall_back_to_defaults(self):
        cfg = settings({"enabled": "quizás", "delay_hours": -1, "window_hours": "x", "send_from": "9",
                        "send_until": "25:00", "max_per_day": -3})
        self.assertEqual(cfg, settings(None))
        self.assertEqual(settings({"delay_hours": True, "max_per_day": 2.5}), settings(None))

    def test_send_hours_must_be_a_daytime_range(self):
        cfg = settings({"send_from": "21:00", "send_until": "09:00"})
        self.assertEqual((cfg["send_from"], cfg["send_until"]), (time(9), time(21)))

    def test_window_must_outlast_the_night(self):
        """With 09:00–21:00 the night is 12 h: a 12 h window would lose the
        trials that end after 21:00."""
        self.assertEqual(settings({"window_hours": 12})["window_hours"], 48.0)
        self.assertEqual(settings({"window_hours": 13})["window_hours"], 13.0)
        short_day = {"send_from": "12:00", "send_until": "13:00"}           # a 23 h night
        self.assertEqual(settings({**short_day, "window_hours": 20})["window_hours"], 48.0)
        self.assertEqual(settings({**short_day, "window_hours": 30})["window_hours"], 30.0)


if __name__ == "__main__":
    unittest.main()
