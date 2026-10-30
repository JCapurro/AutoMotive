"""The notice of the bot de pocos resultados (pipeline/low_results.py).

Once per set of filters, on the search's own channels (Telegram linked,
email): why the search brings few results and that we keep watching. The web
shows the same diagnosis on the search's page (search_diagnoses).
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from typing import Any, Mapping

from telegram.constants import ParseMode

from notifications.email_html import render as render_email_html
from notifications.links import Links
from notifications.templates import UNSUBSCRIBE, Content, EmailMessage, Link

log = logging.getLogger(__name__)

TITLE = "¿Por qué hay pocos resultados?"
SUBJECT = "Por qué tu búsqueda de {vehicle} trae pocos resultados"
SUBJECT_ANY = "Por qué tu búsqueda trae pocos resultados"
SUGGESTIONS = "Si querés ver más:"
CTA = "Ver mi búsqueda"
EYEBROW = "TU BÚSQUEDA"
FOOTER = "Recibís este email porque tenés una búsqueda activa en Ese Auto con avisos por email."


def vehicle(row: Mapping[str, Any]) -> str | None:
    f = row.get("filters") or {}
    name = " ".join(x for x in (f.get("make"), f.get("model")) if isinstance(x, str) and x.strip())
    return name or None


def search_url(links: Links, profile_id: int) -> str:
    return f"{links.base_url.rstrip('/')}/app/searches/{profile_id}" if links.base_url else ""


def telegram_text(row: Mapping[str, Any], diagnosis: Mapping[str, Any], url: str) -> str:
    name = vehicle(row)
    lines = [f"<b>🔎 {escape(TITLE)}</b>" + (f"\n{escape(name)}" if name else ""), "",
             escape(diagnosis["explanation"])]
    if diagnosis.get("suggestions"):
        lines += ["", escape(SUGGESTIONS), *(f"• {escape(s)}" for s in diagnosis["suggestions"])]
    if url:
        lines += ["", f'<a href="{escape(url, quote=True)}">{escape(CTA)}</a>']
    return "\n".join(lines)


def email_message(row: Mapping[str, Any], diagnosis: Mapping[str, Any], links: Links, now: datetime) -> EmailMessage:
    name = vehicle(row)
    subject = SUBJECT.format(vehicle=name) if name else SUBJECT_ANY
    url = search_url(links, row["id"])
    lines = [diagnosis["explanation"]]
    if diagnosis.get("suggestions"):
        lines += [SUGGESTIONS, *(f"• {s}" for s in diagnosis["suggestions"])]
    # No vehicle on the Content: the template would show a photo box for it.
    c = Content(TITLE, subject, lines=[f"Tu búsqueda de {name}." if name else "Tu búsqueda.", *lines],
                link=Link(CTA, url) if url else None)
    unsubscribe = links.unsubscribe(row.get("unsubscribe_token"))
    text = [TITLE, *([name] if name else []), *lines, *([f"{CTA}: {url}"] if url else []), "", "—", FOOTER]
    if unsubscribe:
        text.append(f"{UNSUBSCRIBE}: {unsubscribe}")
    html = render_email_html(c, kind="low_results", now=now, day=None, detail_url=None, app_url=None,
                             unsubscribe_url=unsubscribe, footer=FOOTER, unsubscribe_label=UNSUBSCRIBE,
                             eyebrow=EYEBROW, title=TITLE, preheader=diagnosis["explanation"][:140])
    return EmailMessage(subject, "\n".join(text), html)


async def notify(row: Mapping[str, Any], diagnosis: Mapping[str, Any], channels: Mapping[str, Any],
                 links: Links, now: datetime) -> list[str]:
    """Send the notice on the search's channels; returns the ones that took it."""
    wanted = set(row.get("channels") or ())
    sent: list[str] = []
    telegram = channels.get("telegram")
    if "telegram" in wanted and telegram is not None and row.get("telegram_chat_id"):
        try:
            await telegram.bot.send_message(chat_id=row["telegram_chat_id"],
                                            text=telegram_text(row, diagnosis, search_url(links, row["id"])),
                                            parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            sent.append("telegram")
        except Exception:
            log.exception("low_results: telegram profile=%s", row["id"])
    email = channels.get("email")
    if "email" in wanted and email is not None and row.get("email"):
        try:
            result = await email.send_message(row["email"], email_message(row, diagnosis, links, now),
                                              idempotency_key=f"low-results-{row['id']}-{diagnosis['fingerprint']}",
                                              unsubscribe_token=row.get("unsubscribe_token"))
            if result.ok:
                sent.append("email")
            else:
                log.warning("low_results: email profile=%s: %s", row["id"], result.error)
        except Exception:
            log.exception("low_results: email profile=%s", row["id"])
    return sent
