"""Email through Resend (§21, obligatorio): immediate alerts and the daily
digest, HTML + text. No tracking pixels (sección 7.3): "opened" is the first
click on a /r/ link.

The Idempotency-Key is the notification id, so a retry after a timeout
doesn't send the same email twice. With a WEB_BASE_URL every email carries
List-Unsubscribe with one-click POST (RFC 8058) besides the footer link.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

import httpx

from notifications import templates
from notifications.channels.base import Notification, SendResult
from notifications.links import Links
from notifications.email_assets import logo_attachment


RESEND_URL = "https://api.resend.com/emails"


class ResendEmailChannel:
    name = "email"

    def __init__(self, api_key: str, sender: str, links: Links, *,
                 client: httpx.AsyncClient | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self.api_key = api_key
        self.sender = sender
        self.links = links
        self.client = client or httpx.AsyncClient(timeout=20)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def send(self, notification: Notification) -> SendResult:
        if not notification.email:
            return SendResult(False, "el usuario no tiene email")
        msg = templates.email(notification, self.links, self.clock())
        body = {"from": self.sender, "to": [notification.email], "subject": msg.subject,
                "html": msg.html, "text": msg.text, "attachments": [logo_attachment()]}
        if one_click := self.links.unsubscribe_one_click(notification.unsubscribe_token):
            body["headers"] = {"List-Unsubscribe": f"<{one_click}>",
                               "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        try:
            r = await self.client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Idempotency-Key": f"notification-{notification.id}"},
                json=body,
            )
        except httpx.HTTPError as e:
            return SendResult(False, f"{type(e).__name__}: {e}", retry=True)
        if r.is_success:
            return SendResult(True, provider_id=(r.json() or {}).get("id"))
        error = f"resend {r.status_code}: {r.text[:300]}"
        return SendResult(False, error, retry=r.status_code == 429 or r.status_code >= 500)
