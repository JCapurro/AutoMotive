"""Telegram (§21, canal existente): the §22 copy in HTML plus the inline
buttons ⭐ Me interesa · ✖ Descartar · 🔎 Ver en Ese Auto."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TelegramError

from notifications import templates
from notifications.channels.base import Notification, SendResult
from notifications.links import Links


def keyboard(rows: tuple[tuple[templates.Button, ...], ...]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(b.text, callback_data=b.callback_data, url=b.url)
                                  for b in row] for row in rows])


class TelegramChannel:
    name = "telegram"

    def __init__(self, bot: Any, links: Links, clock: Callable[[], datetime] | None = None) -> None:
        self.bot = bot
        self.links = links
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def send(self, notification: Notification) -> SendResult:
        if not notification.telegram_chat_id:
            return SendResult(False, "el usuario no tiene Telegram vinculado")
        msg = templates.telegram(notification, self.links, self.clock())
        try:
            sent = await self.bot.send_message(
                chat_id=notification.telegram_chat_id,
                text=msg.text,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard(msg.buttons),
                disable_web_page_preview=False,
            )
        except (Forbidden, BadRequest) as e:       # bot blocked, chat gone, bad markup
            return SendResult(False, f"{type(e).__name__}: {e}")
        except (RetryAfter, NetworkError) as e:     # flood control, timeouts
            return SendResult(False, f"{type(e).__name__}: {e}", retry=True)
        except TelegramError as e:
            return SendResult(False, f"{type(e).__name__}: {e}", retry=True)
        return SendResult(True, provider_id=str(getattr(sent, "message_id", "") or "") or None)
