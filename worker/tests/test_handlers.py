"""The bot after F4: /start <code> links the account, the old wizard commands
point to the web (bot/handlers.py)."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from bot.handlers import LEGACY_COMMANDS, register, retired, start
from notifications.links import Links


LINKS = Links("https://automotive.app")


class _FakeMessage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def reply_text(self, text: str, **kwargs) -> None:
        self.calls.append((text, kwargs))


class _FakeUser:
    id = 123


class _FakeChat:
    id = 456


class _FakeUpdate:
    def __init__(self) -> None:
        self.effective_user = _FakeUser()
        self.effective_chat = _FakeChat()
        self.message = _FakeMessage()
        self.callback_query = None


def _ctx(*args: str):
    ctx = type("FakeContext", (), {})()
    ctx.args = list(args)
    ctx.user_data = {}
    return ctx


class StartTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_with_a_code_links_the_account(self):
        update = _FakeUpdate()
        with patch("bot.handlers.db.link_telegram", AsyncMock(return_value="uuid-1")) as link:
            await start(LINKS)(update, _ctx("abc123"))
        link.assert_awaited_once_with("abc123", 123, 456)
        text, kwargs = update.message.calls[0]
        self.assertIn("vinculaste Telegram", text)
        self.assertIn("https://automotive.app/app", text)
        self.assertNotIn("parse_mode", kwargs)

    async def test_an_unknown_or_used_code_points_to_settings(self):
        update = _FakeUpdate()
        with patch("bot.handlers.db.link_telegram", AsyncMock(return_value=None)):
            await start(LINKS)(update, _ctx("expired"))
        text, _ = update.message.calls[0]
        self.assertIn("no es válido", text)
        self.assertIn("https://automotive.app/app/settings", text)

    async def test_start_without_a_code_explains_the_web(self):
        update = _FakeUpdate()
        with patch("bot.handlers.db.link_telegram", AsyncMock()) as link:
            await start(LINKS)(update, _ctx())
        link.assert_not_awaited()
        text, _ = update.message.calls[0]
        self.assertIn("https://automotive.app/app", text)
        self.assertIn("Ajustes", text)

    async def test_without_a_web_url_there_are_no_links(self):
        update = _FakeUpdate()
        await start(Links())(update, _ctx())
        text, _ = update.message.calls[0]
        self.assertNotIn("http", text)

    async def test_users_outside_the_allowlist_are_ignored(self):
        update = _FakeUpdate()
        with patch("bot.handlers.ALLOWED_USER_IDS", {999}), \
             patch("bot.handlers.db.link_telegram", AsyncMock()) as link:
            await start(LINKS)(update, _ctx("abc123"))
        link.assert_not_awaited()
        self.assertEqual(update.message.calls, [])


class RetiredWizardTests(unittest.IsolatedAsyncioTestCase):
    async def test_the_wizard_commands_point_to_the_web(self):
        update = _FakeUpdate()
        await retired(LINKS)(update, _ctx())
        text, _ = update.message.calls[0]
        self.assertIn("se crean y se editan en la web", text)
        self.assertIn("https://automotive.app/app/searches/new", text)

    def test_register_has_no_conversation(self):
        added = []
        app = type("App", (), {"add_handler": lambda self, h: added.append(h)})()
        register(app, LINKS)
        commands = set()
        for h in added:
            commands |= set(getattr(h, "commands", ()))
            self.assertNotEqual(type(h).__name__, "ConversationHandler")
        self.assertTrue({"start", "help", *LEGACY_COMMANDS} <= commands)


if __name__ == "__main__":
    unittest.main()
