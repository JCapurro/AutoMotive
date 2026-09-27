from __future__ import annotations

import unittest
from unittest.mock import patch

from bot.handlers import _coerce, _finish, cmd_list, cmd_edit_alert


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


class HandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_alertas_uses_plain_text_for_user_supplied_filters(self):
        update = _FakeUpdate()
        rows = [
            {
                "id": 7,
                "active": 1,
                "name": "Ford_Fiesta",
                "filters": {
                    "marcas": ["Ford"],
                    "modelos": ["Fiesta_Kinetic"],
                    "sources": ["mercadolibre"],
                },
            }
        ]

        with patch("bot.handlers.db.list_alerts", return_value=rows):
            await cmd_list(update, None)

        self.assertEqual(len(update.message.calls), 1)
        text, kwargs = update.message.calls[0]
        self.assertIn("Ford_Fiesta", text)
        self.assertNotIn("parse_mode", kwargs)

    def test_price_inputs_accept_argentine_thousands_separators(self):
        self.assertEqual(_coerce("precio_max", "15.000"), 15000.0)
        self.assertEqual(_coerce("precio_max", "$ 15.000"), 15000.0)
        self.assertEqual(_coerce("precio_max", "USD 15,000"), 15000.0)

    def test_discount_percentage_accepts_decimal_comma(self):
        self.assertEqual(_coerce("descuento_pct", "12,5"), 12.5)

    async def test_finish_alert_uses_plain_text_for_user_supplied_filters(self):
        update = _FakeUpdate()
        ctx = type("FakeContext", (), {})()
        ctx.user_data = {
            "wizard": {
                "filters": {
                    "marcas": ["Ford"],
                    "modelos": ["Fiesta_Kinetic"],
                    "sources": ["mercadolibre"],
                    "origin_lat": -34.6037,
                    "origin_lon": -58.3816,
                    "radio_km": 75,
                }
            }
        }

        with patch("bot.handlers.db.create_alert", return_value=[9]):
            await _finish(update, ctx)

        self.assertEqual(len(update.message.calls), 1)
        text, kwargs = update.message.calls[0]
        self.assertIn("#9", text)
        self.assertIn("Fiesta_Kinetic", text)
        self.assertNotIn("parse_mode", kwargs)


    async def test_edit_loads_current_filters_into_wizard(self):
        update = _FakeUpdate()
        ctx = type("FakeContext", (), {})()
        ctx.user_data = {}
        ctx.args = ["7"]
        alert = {
            "id": 7,
            "user_id": 123,
            "name": "Ford Fiesta",
            "filters": {
                "marcas": ["Ford"],
                "modelos": ["Fiesta"],
                "sources": ["mercadolibre"],
                "descuento_pct": 12,
            },
        }

        with patch("bot.handlers._allowed", return_value=True), \
             patch("bot.handlers.db.get_alert", return_value=alert):
            await cmd_edit_alert(update, ctx)

        w = ctx.user_data["wizard"]
        self.assertEqual(w["edit_id"], 7)
        self.assertEqual(w["step"], 0)
        self.assertEqual(w["filters"]["marcas"], ["Ford"])
        self.assertEqual(w["filters"]["descuento_pct"], 12)

    async def test_edit_rejects_other_users_alert(self):
        update = _FakeUpdate()
        ctx = type("FakeContext", (), {})()
        ctx.user_data = {}
        ctx.args = ["7"]
        alert = {"id": 7, "user_id": 999, "name": "x", "filters": {}}

        with patch("bot.handlers._allowed", return_value=True), \
             patch("bot.handlers.db.get_alert", return_value=alert):
            await cmd_edit_alert(update, ctx)

        self.assertNotIn("wizard", ctx.user_data)
        text, _ = update.message.calls[0]
        self.assertIn("no encontrada", text.lower())

    async def test_finish_in_edit_mode_updates_instead_of_creating(self):
        update = _FakeUpdate()
        ctx = type("FakeContext", (), {})()
        ctx.user_data = {
            "wizard": {
                "edit_id": 9,
                "filters": {
                    "marcas": ["Ford"],
                    "modelos": ["Fiesta_Kinetic"],
                    "sources": ["mercadolibre"],
                    "origin_lat": -34.6037,
                    "origin_lon": -58.3816,
                    "radio_km": 75,
                    "descuento_pct": 15,
                },
            }
        }

        with patch("bot.handlers.db.update_alert") as upd, \
             patch("bot.handlers.db.create_alert") as create:
            await _finish(update, ctx)

        create.assert_not_called()
        upd.assert_called_once()
        self.assertEqual(upd.call_args.args[0], 9)
        text, kwargs = update.message.calls[0]
        self.assertIn("#9", text)
        self.assertIn("actualizada", text)
        self.assertNotIn("parse_mode", kwargs)


if __name__ == "__main__":
    unittest.main()
