"""Agencias (docs/superpowers/specs/2026-11-18-agencias-design.md §4.6): tell
a dealer it has new contact requests.

One email per dealer and tick to dealers.contact_email (or its owner's
email), through the existing email channel. It says how many people asked
and for which car, and links to /agencia/consultas: the buyer's name, phone
and message are only in the panel (RLS), never in this email nor in the logs,
which carry lead and dealer ids only (C2).
"""
from __future__ import annotations

import logging
from collections import defaultdict
from html import escape
from typing import Any, Mapping

from config import WEB_BASE_URL
from db.repos import dealers as repo
from notifications.links import Links
from notifications.templates import EmailMessage, vehicle

log = logging.getLogger("dealer_leads")

SUBJECT = ("Tenés {n} consulta nueva en Ese Auto", "Tenés {n} consultas nuevas en Ese Auto")
BODY = ("{n} persona pidió que la contactes por tu {car}. Mirá los datos en tu panel.",
        "{n} personas pidieron que las contactes por tu {car}. Mirá los datos en tu panel.")
BODY_MANY = ("{n} persona pidió que la contactes por tus autos. Mirá los datos en tu panel.",
             "{n} personas pidieron que las contactes por tus autos. Mirá los datos en tu panel.")
CTA = "Ver consultas"
FOOTER = "Recibís este email porque tu agencia publica autos en Ese Auto."


def inbox_url(links: Links | None) -> str:
    base = (links.base_url if links is not None and links.base_url else WEB_BASE_URL).rstrip("/")
    return f"{base}/agencia/consultas"


def message(leads: list[Mapping[str, Any]], links: Links | None) -> EmailMessage:
    """The email for one dealer's new leads. Only the count and the car(s)."""
    n = len(leads)
    many = n != 1
    cars = list(dict.fromkeys(vehicle(dict(lead)) for lead in leads if lead.get("make") or lead.get("title")))
    subject = SUBJECT[many].format(n=n)
    body = (BODY[many].format(n=n, car=cars[0]) if len(cars) == 1 else BODY_MANY[many].format(n=n))
    url = inbox_url(links)
    text = "\n".join([subject, "", body, "", f"{CTA}: {url}", "", "—", FOOTER])
    html = ('<div style="font-family:Arial,Helvetica,sans-serif;max-width:580px;margin:auto;color:#14213d;padding:28px">'
            '<p style="font-size:12px;color:#4e5a73">ESE AUTO · TU AGENCIA</p>'
            f'<h1 style="font-size:22px">{escape(subject)}</h1>'
            f'<p style="font-size:15px;line-height:1.6">{escape(body)}</p>'
            f'<p><a href="{escape(url, quote=True)}" style="display:inline-block;background:#14213d;color:#ffffff;'
            f'padding:12px 20px;border-radius:6px;text-decoration:none">{escape(CTA)}</a></p>'
            f'<p style="font-size:12px;color:#4e5a73">{escape(FOOTER)}</p></div>')
    return EmailMessage(subject, text, html)


async def notify_new_leads(channel, links: Links | None, *, limit: int = 50) -> int:
    """Email each dealer about its leads not told yet; mark them told. Returns
    how many emails went out. Without an email channel or address, the leads
    wait (the dealer still sees them in its panel)."""
    if channel is None:
        return 0
    by_dealer: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for lead in await repo.unnotified_leads(limit):
        by_dealer[lead["dealer_id"]].append(lead)
    sent = 0
    for dealer_id, leads in by_dealer.items():
        to = leads[0].get("email")
        ids = [lead["lead_id"] for lead in leads]
        if not to:
            log.info("dealer %s: %d new leads, no email to tell it", dealer_id, len(ids))
            continue
        key = f"dealer-leads-{dealer_id}-{min(ids)}-{max(ids)}"
        result = await channel.send_message(to, message(leads, links), idempotency_key=key, unsubscribe_token=None)
        if result.ok:
            await repo.mark_lead_notified(ids)
            sent += 1
            log.info("dealer %s: told about leads %s", dealer_id, ids)
        else:
            log.warning("dealer %s: lead email failed (%s), leads %s", dealer_id, result.error, ids)
    return sent
