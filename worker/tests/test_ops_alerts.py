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
