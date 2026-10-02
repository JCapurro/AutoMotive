"""The Telegram bot after F4: it links the account and answers alert buttons.

Searches are created and edited in the web (sección 9); the wizard is gone.

    /start <code>   links this Telegram user to the web account whose
                    profiles.telegram_link_code is <code> (the deep link
                    t.me/<bot>?start=<code> of /app/settings). The code rotates.
    /start, /help   what the bot does now, with links to the web
    /nuevaalerta, /editar, /alertas, /pausar, /activar, /borrar, /cancelar
                    the old wizard commands: they point to the web

The ⭐ Me interesa / ✖ Descartar buttons of an alert are
bot/notification_actions.py.
"""
from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

import db
from bot.notification_actions import handler as notification_actions
from config import ALLOWED_USER_IDS
from notifications.links import Links


log = logging.getLogger("bot")

LEGACY_COMMANDS = ("nuevaalerta", "editar", "alertas", "pausar", "activar", "borrar", "cancelar")


def _allowed(update: Update) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return user is not None and user.id in ALLOWED_USER_IDS


def _web(links: Links, path: str) -> str | None:
    return f"{links.base_url}{path}" if links.base_url else None


def welcome_text(links: Links) -> str:
    lines = ["🚗 Ese Auto", "",
             "Te aviso por acá cuando aparece un auto que coincide con tus búsquedas."]
    if app := _web(links, "/app"):
        lines += ["", f"Creá y editá tus búsquedas en la web: {app}"]
    if settings := _web(links, "/app/settings"):
        lines.append(f"Para recibir las alertas acá, vinculá Telegram desde Ajustes: {settings}")
    return "\n".join(lines)


def linked_text(links: Links) -> str:
    text = "✅ Listo, vinculaste Telegram con tu cuenta de Ese Auto. Las alertas van a llegar a este chat."
    if app := _web(links, "/app"):
        text += f"\n\nTus búsquedas: {app}"
    return text


def invalid_code_text(links: Links) -> str:
    text = "Ese link de vinculación no es válido o ya se usó."
    if settings := _web(links, "/app/settings"):
        text += f" Generá uno nuevo en Ajustes: {settings}"
    return text


def retired_text(links: Links) -> str:
    text = "Las búsquedas ahora se crean y se editan en la web."
    if new := _web(links, "/app/searches/new"):
        text += f"\n\nCreá una búsqueda: {new}\nTus búsquedas: {_web(links, '/app')}"
    return text


def start(links: Links):
    async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not _allowed(update) or update.message is None:
            return
        code = (ctx.args or [None])[0]
        if not code:
            await update.message.reply_text(welcome_text(links))
            return
        user, chat = update.effective_user, update.effective_chat
        linked = await db.link_telegram(code, user.id, chat.id)
        if linked is None:
            await update.message.reply_text(invalid_code_text(links))
            return
        log.info("telegram user %s linked to profile %s", user.id, linked)
        await update.message.reply_text(linked_text(links))
    return cmd_start


def help_(links: Links):
    async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if _allowed(update) and update.message is not None:
            await update.message.reply_text(welcome_text(links))
    return cmd_help


def retired(links: Links):
    async def cmd_retired(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if _allowed(update) and update.message is not None:
            await update.message.reply_text(retired_text(links))
    return cmd_retired


def register(app, links: Links | None = None) -> None:
    links = links or Links()
    app.add_handler(notification_actions(links))
    app.add_handler(CommandHandler("start", start(links)))
    app.add_handler(CommandHandler("help", help_(links)))
    app.add_handler(CommandHandler(list(LEGACY_COMMANDS), retired(links)))
