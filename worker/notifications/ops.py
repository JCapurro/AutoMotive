"""Operational alerts for the admin (sección 10, §46).

A source that fails `app_config.collector_failure_alert_after` times in a row
(default 3) sends one Telegram message to TELEGRAM_ADMIN_CHAT_ID, and its first
good run after that sends another. One message per streak: the counter lives in
sources.consecutive_failures, so a restart doesn't repeat it. No extra
infrastructure: it's the bot the worker already runs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any, Callable

from telegram.constants import ParseMode

from db.repos.config import get_config
from db.repos.runs import SourceHealth
from notifications.templates import ago_long


log = logging.getLogger("ops")

DEFAULT_FAILURE_ALERT_AFTER = 3
_MAX_ERROR_CHARS = 300


def last_error_line(error: str | None) -> str | None:
    """The exception line of a traceback ("RuntimeError: login wall")."""
    lines = [l.strip() for l in (error or "").strip().splitlines() if l.strip()]
    if not lines:
        return None
    line = lines[-1]
    return line if len(line) <= _MAX_ERROR_CHARS else line[: _MAX_ERROR_CHARS - 1] + "…"


def failing_text(h: SourceHealth, now: datetime, web_base_url: str = "") -> str:
    lines = [f"⚠️ <b>{escape(h.name)}</b> falló {h.failures} veces seguidas."]
    lines.append("Última corrida OK: " + (f"hace {ago_long(h.last_ok_at, now)}." if h.last_ok_at else "nunca."))
    if err := last_error_line(h.error):
        lines.append(f"Último error: <code>{escape(err)}</code>")
    if web_base_url:
        lines.append(f'<a href="{escape(web_base_url)}/admin/sources">Ver en el admin</a>')
    return "\n".join(lines)


def recovered_text(h: SourceHealth) -> str:
    return f"✅ <b>{escape(h.name)}</b> volvió a funcionar después de {h.previous} fallas seguidas."


class SourceAlerts:
    """Tells the admin when a collector goes down and when it's back."""

    def __init__(self, bot: Any, chat_id: int | str | None, web_base_url: str = "",
                 clock: Callable[[], datetime] | None = None) -> None:
        self.bot = bot
        self.chat_id = chat_id
        self.web_base_url = web_base_url.rstrip("/")
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @property
    def enabled(self) -> bool:
        return self.bot is not None and bool(self.chat_id)

    async def on_health(self, h: SourceHealth | None) -> bool:
        """Called after every run. Returns whether a message went out; never raises."""
        if h is None or not self.enabled:
            return False
        try:
            after = int(await get_config("collector_failure_alert_after", DEFAULT_FAILURE_ALERT_AFTER)
                        or DEFAULT_FAILURE_ALERT_AFTER)
            if h.failures == after and h.previous < after:
                text = failing_text(h, self.clock(), self.web_base_url)
            elif h.failures == 0 and h.previous >= after:
                text = recovered_text(h)
            else:
                return False
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=ParseMode.HTML,
                                        disable_web_page_preview=True)
        except Exception:
            log.exception("could not alert the admin about source %s", h.source)
            return False
        log.info("admin alerted: source %s failures=%d previous=%d", h.source, h.failures, h.previous)
        return True
