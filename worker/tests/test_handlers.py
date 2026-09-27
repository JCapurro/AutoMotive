from __future__ import annotations

import unittest
from unittest.mock import patch

from bot.handlers import _coerce, _finish, cmd_list


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


if __name__ == "__main__":
    unittest.main()
