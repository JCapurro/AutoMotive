"""Channel adapters against fakes: a fake Telegram bot and a mocked Resend API."""
from __future__ import annotations

import json
from base64 import b64decode
import unittest

import httpx
from telegram import InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import Forbidden, NetworkError

from bot.notification_actions import parse
from notifications.channels.email import RESEND_URL, ResendEmailChannel
from notifications.channels.telegram import TelegramChannel
from notifications.channels.web import WebChannel
from notifications.links import Links
from notification_fixtures import LINKS, NOW, OPPORTUNITY, PRICE_DROP


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[dict] = []
        self.error = error

    async def send_message(self, **kwargs):
        if self.error:
            raise self.error
        self.sent.append(kwargs)
        return type("Message", (), {"message_id": 900 + len(self.sent)})()


class TelegramChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_sends_html_with_the_inline_buttons(self):
        bot = FakeBot()
        result = await TelegramChannel(bot, LINKS, clock=lambda: NOW).send(OPPORTUNITY)
        self.assertTrue(result.ok)
        self.assertEqual(result.provider_id, "901")
        msg = bot.sent[0]
        self.assertEqual(msg["chat_id"], 1234)
        self.assertEqual(msg["parse_mode"], ParseMode.HTML)
        self.assertTrue(msg["text"].startswith("<b>🔥 Nueva oportunidad</b>"))
        markup: InlineKeyboardMarkup = msg["reply_markup"]
        rows = [[(b.text, b.callback_data, b.url) for b in row] for row in markup.inline_keyboard]
        self.assertEqual(rows, [
            [("⭐ Me interesa", "nt:interested:42", None), ("✖ Descartar", "nt:discarded:42", None)],
            [("🔎 Ver en Ese Auto", None, "https://automotive.app/r/42?to=detail")],
        ])

    async def test_no_url_button_without_a_public_https_base(self):
        bot = FakeBot()
        await TelegramChannel(bot, Links("http://127.0.0.1:8787"), clock=lambda: NOW).send(OPPORTUNITY)
        buttons = [b.text for row in bot.sent[0]["reply_markup"].inline_keyboard for b in row]
        self.assertNotIn("🔎 Ver en Ese Auto", buttons)

    async def test_blocked_bot_is_permanent_network_error_is_retried(self):
        blocked = await TelegramChannel(FakeBot(Forbidden("bot was blocked by the user")), LINKS).send(OPPORTUNITY)
        self.assertEqual((blocked.ok, blocked.retry), (False, False))
        flaky = await TelegramChannel(FakeBot(NetworkError("timed out")), LINKS).send(OPPORTUNITY)
        self.assertEqual((flaky.ok, flaky.retry), (False, True))

    async def test_without_chat_id(self):
        from dataclasses import replace
        result = await TelegramChannel(FakeBot(), LINKS).send(replace(OPPORTUNITY, telegram_chat_id=None))
        self.assertFalse(result.ok)
        self.assertFalse(result.retry)


class ResendEmailChannelTests(unittest.IsolatedAsyncioTestCase):
    def channel(self, handler) -> tuple[ResendEmailChannel, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def record(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(record))
        self.addAsyncCleanup(client.aclose)
        return ResendEmailChannel("re_test_key", "Automotive <alertas@automotive.test>", LINKS,
                                  client=client, clock=lambda: NOW), seen

    async def test_posts_subject_html_and_text(self):
        ch, seen = self.channel(lambda r: httpx.Response(200, json={"id": "email_123"}))
        result = await ch.send(PRICE_DROP)
        self.assertTrue(result.ok)
        self.assertEqual(result.provider_id, "email_123")
        req = seen[0]
        self.assertEqual(str(req.url), RESEND_URL)
        self.assertEqual(req.headers["Authorization"], "Bearer re_test_key")
        self.assertEqual(req.headers["Idempotency-Key"], "notification-42")
        body = json.loads(req.content)
        self.assertEqual(body["to"], ["ana@automotive.test"])
        self.assertEqual(body["from"], "Automotive <alertas@automotive.test>")
        self.assertEqual(body["subject"], "📉 Bajó de precio: Ford Fiesta Titanium 2017 (-6,1%) · Ese Auto")
        self.assertTrue(body["text"].startswith("📉 Bajó de precio\nFord Fiesta Titanium 2017\n"
                                                "Antes: USD 11.500\nAhora: USD 10.800\n-6,1%"))
        self.assertIn(">Bajó de precio</h1>", body["html"])
        [logo] = body["attachments"]
        self.assertEqual(logo["content_id"], "ese-auto-logo")
        self.assertEqual(logo["content_type"], "image/png")
        self.assertTrue(b64decode(logo["content"]).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIn('src="cid:ese-auto-logo"', body["html"])

    async def test_every_email_can_unsubscribe(self):
        """F7, punto 7: a footer link and List-Unsubscribe one-click (RFC 8058)."""
        from dataclasses import replace

        ch, seen = self.channel(lambda r: httpx.Response(200, json={"id": "email_1"}))
        await ch.send(replace(PRICE_DROP, unsubscribe_token="tok-123"))
        body = json.loads(seen[0].content)
        self.assertEqual(body["headers"], {"List-Unsubscribe": "<https://automotive.app/api/baja?t=tok-123>",
                                           "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})
        # No double opt-in: the footer speaks to whoever owns the address.
        self.assertIn("Recibís este email porque se creó una búsqueda en Ese Auto con esta dirección. "
                      "¿No fuiste vos?\nDejá de recibirlos: https://automotive.app/baja?t=tok-123", body["text"])
        self.assertIn('href="https://automotive.app/baja?t=tok-123"', body["html"])
        self.assertIn("¿No fuiste vos?</p>", body["html"])

        ch, seen = self.channel(lambda r: httpx.Response(200, json={"id": "email_2"}))
        await ch.send(PRICE_DROP)  # no token (e.g. an old row): no link, no header
        old = json.loads(seen[0].content)
        self.assertNotIn("headers", old)
        self.assertNotIn("¿No fuiste vos?", old["text"] + old["html"])   # no question without the link

    async def test_rate_limit_and_server_errors_are_retried(self):
        for status, retry in ((429, True), (503, True), (422, False)):
            ch, _ = self.channel(lambda r, s=status: httpx.Response(s, json={"message": "nope"}))
            result = await ch.send(OPPORTUNITY)
            with self.subTest(status=status):
                self.assertFalse(result.ok)
                self.assertEqual(result.retry, retry)

    async def test_connection_errors_are_retried(self):
        def boom(request):
            raise httpx.ConnectError("down")
        ch, _ = self.channel(boom)
        result = await ch.send(OPPORTUNITY)
        self.assertEqual((result.ok, result.retry), (False, True))

    async def test_send_message_posts_a_rendered_email_with_its_own_key(self):
        """A plan email reuses the POST: its key never collides with a notification's."""
        from notifications import templates

        ch, seen = self.channel(lambda r: httpx.Response(200, json={"id": "email_9"}))
        msg = templates.lifecycle_email({"id": 9, "kind": "trial_ended", "payload": {"found": 2},
                                         "unsubscribe_token": "tok-9"}, LINKS, NOW)
        result = await ch.send_message("ana@automotive.test", msg, idempotency_key="lifecycle-9",
                                       unsubscribe_token="tok-9")
        self.assertEqual((result.ok, result.provider_id), (True, "email_9"))
        req = seen[0]
        self.assertEqual(req.headers["Idempotency-Key"], "lifecycle-9")
        self.assertEqual(req.headers["Authorization"], "Bearer re_test_key")
        body = json.loads(req.content)
        self.assertEqual(body["to"], ["ana@automotive.test"])
        self.assertEqual(body["subject"], "Terminó tu prueba: encontramos 2 autos para tu búsqueda")
        self.assertEqual((body["text"], body["html"]), (msg.text, msg.html))
        [logo] = body["attachments"]
        self.assertEqual(logo["content_id"], "ese-auto-logo")
        self.assertIn('src="cid:ese-auto-logo"', body["html"])
        self.assertEqual(body["headers"], {"List-Unsubscribe": "<https://automotive.app/api/baja?t=tok-9>",
                                           "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})

        ch, seen = self.channel(lambda r: httpx.Response(422, json={"message": "nope"}))
        result = await ch.send_message("ana@automotive.test", msg, idempotency_key="k",
                                       unsubscribe_token=None)
        self.assertEqual((result.ok, result.retry), (False, False))
        self.assertNotIn("headers", json.loads(seen[0].content))


class WebChannelTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_row_is_the_delivery(self):
        result = await WebChannel(LINKS, clock=lambda: NOW).send(OPPORTUNITY)
        self.assertTrue(result.ok)
        self.assertEqual(result.extra["web"]["title"], "🔥 Nueva oportunidad")
        self.assertEqual(result.extra["web"]["vehicle"], "Ford Fiesta Titanium 2017")


class CallbackDataTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse("nt:interested:42"), ("interested", 42))
        self.assertEqual(parse("nt:discarded:7"), ("discarded", 7))
        for bad in ("nt:purchased:1", "nt:interested:x", "v:Toyota", "", "nt:interested"):
            self.assertIsNone(parse(bad))


if __name__ == "__main__":
    unittest.main()
