"""Send persisted trial feedback to the owner using the existing email channel."""
from __future__ import annotations

import logging
import re
from datetime import timedelta, timezone
from html import escape

from db.repos import product_feedback as repo
from db.repos.config import get_config
from notifications.links import Links
from notifications.templates import EmailMessage

log = logging.getLogger(__name__)
AR = timezone(timedelta(hours=-3))
EMAIL = re.compile(r'^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$')


def feedback_message(row: dict, links: Links) -> EmailMessage:
    sent = row['created_at'].astimezone(AR).strftime('%d/%m/%Y %H:%M (hora argentina)')
    search = f"{row['search_name']} (#{row['search_profile_id']})" if row.get('search_profile_id') else 'Sin búsqueda asociada'
    admin = f"{links.base_url.rstrip('/')}/admin/searches#search-{row['search_profile_id']}" if links.base_url and row.get('search_profile_id') else ''
    text = f"Nuevo feedback de la prueba gratis\n\nCuenta: {row['email']}\nBúsqueda: {search}\nEnviado: {sent}\n\n{row['message']}\n\nLead: {row['id']}"
    if admin:
        text += f'\nVer búsquedas: {admin}'
    html = ('<div style="font-family:Arial,Helvetica,sans-serif;max-width:580px;margin:auto;color:#14213d;padding:28px">'
            '<p style="font-size:12px;color:#4e5a73">ESE AUTO · FEEDBACK</p>'
            '<h1 style="font-size:24px">Nuevo comentario de la prueba gratis</h1>'
            f'<p><strong>Cuenta:</strong> {escape(row["email"])}</p>'
            f'<p><strong>Búsqueda:</strong> {escape(search)}</p>'
            f'<p style="color:#4e5a73;font-size:13px">{escape(sent)}</p>'
            f'<div style="white-space:pre-wrap;background:#f1f3f7;border-radius:8px;padding:20px;line-height:1.6">{escape(row["message"])}</div>'
            + (f'<p><a href="{escape(admin, quote=True)}">Ver búsquedas en el panel</a></p>' if admin else '')
            + f'<p style="font-size:12px;color:#4e5a73">Lead: {escape(str(row["id"]))}</p></div>')
    reply_to = row['email'] if EMAIL.fullmatch(row['email']) else None
    return EmailMessage('Ese Auto: nuevo feedback de la prueba gratis', text, html, reply_to=reply_to, logo=False)


async def run_product_feedback(channel, links: Links) -> int:
    if channel is None:
        return 0
    cfg = await get_config('feedback_delivery', {})
    recipient = cfg.get('recipient_email', '') if isinstance(cfg,dict) else ''
    if not isinstance(cfg,dict) or cfg.get('enabled', True) is not True or not isinstance(recipient,str) or not EMAIL.fullmatch(recipient):
        return 0
    sent = 0
    for row in await repo.claim():
        try:
            result = await channel.send_message(recipient,feedback_message(row,links),
                idempotency_key=f"product-feedback-{row['id']}",unsubscribe_token=None)
            if result.ok:
                await repo.mark_sent(row['id'],row['claim_token'],result.provider_id)
                sent += 1
            else:
                await repo.mark_retry(row['id'],row['claim_token'],result.error or 'email_delivery_failed',retry=result.retry)
        except Exception as error:
            log.exception('feedback email failed: %s',row['id'])
            await repo.mark_retry(row['id'],row['claim_token'],type(error).__name__)
    return sent
