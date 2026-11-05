"""The admin's collector alert (sección 10) against a fake bot: when it fires,
what it says, and that it never breaks the crawl."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from telegram.constants import ParseMode

from db.repos.runs import SourceHealth
from notifications.ops import SourceAlerts, failing_text, last_error_line, recovered_text

NOW = datetime(2026, 10, 3, 15, 0, tzinfo=timezone.utc)
TRACEBACK = """Traceback (most recent call last):
  File "collectors/mercadolibre.py", line 80, in search
    raise RuntimeError("login wall")
RuntimeError: login wall
"""


def health(failures: int, previous: int, *, last_ok: datetime | None = None, error: str | None = TRACEBACK):
    return SourceHealth("mercadolibre", "MercadoLibre", failures, previous, last_ok, error)


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[dict] = []
        self.error = error

    async def send_message(self, **kwargs):
        if self.error:
            raise self.error
        self.sent.append(kwargs)


class TextTests(unittest.TestCase):
    def test_last_error_line_is_the_exception(self):
        self.assertEqual(last_error_line(TRACEBACK), "RuntimeError: login wall")
        self.assertIsNone(last_error_line(None))
        self.assertIsNone(last_error_line("  \n"))
        self.assertEqual(len(last_error_line("x" * 1000)), 300)

    def test_failing_text(self):
        text = failing_text(health(3, 2, last_ok=NOW - timedelta(hours=5)), NOW, "https://automotive.test")
        self.assertEqual(text.splitlines(), [
            "⚠️ <b>MercadoLibre</b> falló 3 veces seguidas.",
            "Última corrida OK: hace 5 horas.",
            "Último error: <code>RuntimeError: login wall</code>",
            '<a href="https://automotive.test/admin/sources">Ver en el admin</a>',
        ])

    def test_failing_text_never_ok_no_error_no_web(self):
        text = failing_text(health(3, 2, error=None), NOW)
        self.assertEqual(text.splitlines(), ["⚠️ <b>MercadoLibre</b> falló 3 veces seguidas.",
                                             "Última corrida OK: nunca."])

    def test_error_is_escaped(self):
        text = failing_text(health(3, 2, error="ValueError: <html> & co"), NOW)
        self.assertIn("<code>ValueError: &lt;html&gt; &amp; co</code>", text)

    def test_recovered_text(self):
        self.assertEqual(recovered_text(health(0, 5)),
                         "✅ <b>MercadoLibre</b> volvió a funcionar después de 5 fallas seguidas.")


@patch("notifications.ops.get_config", new=AsyncMock(return_value=3))
class OnHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_fires_once_when_the_streak_reaches_the_threshold(self):
        bot = FakeBot()
        alerts = SourceAlerts(bot, 42, clock=lambda: NOW)
        sent = [await alerts.on_health(health(n, n - 1)) for n in (1, 2, 3, 4, 5)]
        self.assertEqual(sent, [False, False, True, False, False])
        [msg] = bot.sent
        self.assertEqual((msg["chat_id"], msg["parse_mode"]), (42, ParseMode.HTML))
        self.assertIn("falló 3 veces seguidas", msg["text"])

    async def test_recovery_only_after_an_alerted_streak(self):
        bot = FakeBot()
        alerts = SourceAlerts(bot, 42)
        self.assertFalse(await alerts.on_health(health(0, 2)))      # never alerted: nothing to say
        self.assertFalse(await alerts.on_health(health(0, 0)))
        self.assertTrue(await alerts.on_health(health(0, 3)))
        self.assertIn("volvió a funcionar", bot.sent[0]["text"])

    async def test_disabled_without_chat_or_run(self):
        bot = FakeBot()
        self.assertFalse(SourceAlerts(bot, "").enabled)
        self.assertFalse(await SourceAlerts(bot, "").on_health(health(3, 2)))
        self.assertFalse(await SourceAlerts(bot, 42).on_health(None))
        self.assertEqual(bot.sent, [])

    async def test_a_telegram_error_is_swallowed(self):
        alerts = SourceAlerts(FakeBot(RuntimeError("telegram down")), 42)
        self.assertFalse(await alerts.on_health(health(3, 2)))

    async def test_threshold_comes_from_app_config(self):
        bot = FakeBot()
        with patch("notifications.ops.get_config", new=AsyncMock(return_value=5)):
            alerts = SourceAlerts(bot, 42)
            self.assertFalse(await alerts.on_health(health(3, 2)))
            self.assertTrue(await alerts.on_health(health(5, 4)))
            self.assertFalse(await alerts.on_health(health(0, 4)))   # recovered before alerting
            self.assertTrue(await alerts.on_health(health(0, 6)))


if __name__ == "__main__":
    unittest.main()


FB_EXPIRED = """Traceback (most recent call last):
  File "/opt/automotive/worker/collectors/_isolated.py", line 71, in call
    raise value
collectors.base.CollectorBlocked: facebook: session expired (logged out, no c_user cookie)
"""


def fb(failures: int, previous: int, error: str | None = FB_EXPIRED):
    return SourceHealth("facebook", "Facebook Marketplace", failures, previous, NOW - timedelta(minutes=20), error)


@patch("notifications.ops.get_config", new=AsyncMock(return_value=3))
class SessionExpiredTests(unittest.IsolatedAsyncioTestCase):
    """Juan, 2026-11-05: an expired session is told at once, with how to renew it."""

    async def test_told_on_the_first_failure_with_the_renewal(self):
        bot = FakeBot()
        alerts = SourceAlerts(bot, 42, clock=lambda: NOW)
        self.assertTrue(await alerts.on_health(fb(1, 0)))
        text = bot.sent[0]["text"]
        self.assertIn("Facebook Marketplace</b>: se cerró la sesión", text)
        self.assertIn("hace 20 minutos", text)
        self.assertIn("ops/fb-renovar.ps1", text)

    async def test_once_per_streak_without_the_generic_alert(self):
        bot = FakeBot()
        alerts = SourceAlerts(bot, 42, clock=lambda: NOW)
        for failures in range(1, 6):
            await alerts.on_health(fb(failures, failures - 1))
        self.assertEqual(len(bot.sent), 1)

    async def test_a_streak_that_started_with_another_error_is_still_told(self):
        bot = FakeBot()
        alerts = SourceAlerts(bot, 42, clock=lambda: NOW)
        await alerts.on_health(fb(1, 0, error="TimeoutError: feed"))
        await alerts.on_health(fb(2, 1))
        self.assertEqual(len(bot.sent), 1)
        self.assertIn("se cerró la sesión", bot.sent[0]["text"])

    async def test_the_renewal_is_told_even_before_the_threshold(self):
        bot = FakeBot()
        alerts = SourceAlerts(bot, 42, clock=lambda: NOW)
        await alerts.on_health(fb(1, 0))
        self.assertTrue(await alerts.on_health(fb(0, 1, error=None)))
        self.assertIn("volvió a funcionar después de 1 fallas", bot.sent[1]["text"])
        # A new death is a new streak: told again.
        await alerts.on_health(fb(1, 0))
        self.assertEqual(len(bot.sent), 3)

    async def test_a_failed_send_tries_again_on_the_next_run(self):
        bot = FakeBot(error=RuntimeError("telegram down"))
        alerts = SourceAlerts(bot, 42, clock=lambda: NOW)
        self.assertFalse(await alerts.on_health(fb(1, 0)))
        bot.error = None
        self.assertTrue(await alerts.on_health(fb(2, 1)))
        self.assertEqual(len(bot.sent), 1)
