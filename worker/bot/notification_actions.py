"""Inline buttons of a Telegram alert (sección 7.2): ⭐ Me interesa · ✖ Descartar.

Callback data is nt:<action>:<notification_id>. Only the user the alert was
sent to can act on it. The listing's status goes to user_listing_interactions
(§26; the discard reason is asked by the web, §27) and the alert counts as
opened.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler, ContextTypes

from db.repos import notifications as repo
from notifications.channels.base import Notification
from notifications.channels.telegram import keyboard
from notifications.links import Links
from notifications.templates import telegram_buttons


log = logging.getLogger("bot.actions")

PATTERN = r"^nt:(interested|discarded):\d+$"
ANSWER = {"interested": "⭐ Guardado como «Me interesa»", "discarded": "✖ Descartada"}


def parse(data: str) -> tuple[str, int] | None:
    parts = (data or "").split(":")
    if len(parts) != 3 or parts[0] != "nt" or parts[1] not in ANSWER or not parts[2].isdigit():
        return None
    return parts[1], int(parts[2])


def handler(links: Links) -> CallbackQueryHandler:
    async def on_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        parsed = parse(q.data)
        if parsed is None or update.effective_user is None:
            await q.answer()
            return
        action, notification_id = parsed
        n = await repo.apply_telegram_action(notification_id, update.effective_user.id, action)
        if n is None:
            await q.answer("No se encontró la alerta.", show_alert=False)
            return
        await q.answer(ANSWER[action])
        shown = Notification(id=notification_id, user_id=str(n["user_id"]), kind=n["kind"],
                             channel=n["channel"], payload={}, listing_id=n["listing_id"])
        try:
            await q.edit_message_reply_markup(keyboard(telegram_buttons(shown, links, chosen=action)))
        except BadRequest as e:        # "message is not modified" on a second tap
            log.debug("edit_message_reply_markup: %s", e)

    return CallbackQueryHandler(on_action, pattern=PATTERN)
