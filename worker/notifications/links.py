"""Tracked links (sección 7.3): every link in an alert is /r/<notification_id>.

    <WEB_BASE_URL>/r/<id>?to=listing        → the listing at its source
    <WEB_BASE_URL>/r/<id>?to=detail         → the listing's page in Ese Auto
    <WEB_BASE_URL>/r/<id>?to=listing&l=<listing_id>   (one item of a digest)

the button of a plan email (docs/MAILS_DE_PLAN.md) is /m/<lifecycle_email_id>,
every email carries a 1 px image that marks it opened,

    <WEB_BASE_URL>/o/<id>?k=n|m             → notifications | lifecycle_emails

and the user's unsubscribe link (F7, punto 7):

    <WEB_BASE_URL>/baja?t=<token>           → a page with a confirm button
    <WEB_BASE_URL>/api/baja?t=<token>       → one-click POST (RFC 8058)

With ALERT_LINK_SECRET, the email links that lead into the app (to=detail and
/m/<id>) also carry &s=<signature>: the web may sign an email-only account in
from them (docs/AUTENTICACION.md, «Links firmados»). Telegram links and links
to the source are never signed.

Without WEB_BASE_URL links go straight to the listing, untracked, and there is
no "Ver en Ese Auto".
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
from urllib.parse import urlencode

# Shorter secrets are ignored (the web ignores them too): links go unsigned.
MIN_SECRET_LENGTH = 32


def signature(secret: str, scope: str, item_id: int, user_id: str) -> str:
    """HMAC-SHA256 of v1:<scope>:<id>:<user_id>, truncated to 128 bits, base64url.
    `scope` is "r" (notifications) or "m" (lifecycle_emails). Same as
    web/lib/alert-session.ts."""
    message = f"v1:{scope}:{item_id}:{user_id}".encode()
    mac = hmac.new(secret.encode(), message, hashlib.sha256).digest()[:16]
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


@dataclass(frozen=True)
class Links:
    base_url: str = ""
    secret: str = field(default="", repr=False)

    @property
    def tracked(self) -> bool:
        return bool(self.base_url)

    @property
    def signs(self) -> bool:
        return self.tracked and len(self.secret) >= MIN_SECRET_LENGTH

    def _signed(self, query: dict[str, str], scope: str, item_id: int, owner: str | None) -> dict[str, str]:
        return {**query, "s": signature(self.secret, scope, item_id, owner)} if owner and self.signs else query

    def _r(self, notification_id: int, to: str, listing_id: int | None = None, owner: str | None = None) -> str:
        query = {"to": to}
        if listing_id is not None:
            query["l"] = str(listing_id)
        return f"{self.base_url}/r/{notification_id}?{urlencode(self._signed(query, 'r', notification_id, owner))}"

    def listing(self, notification_id: int, url: str, listing_id: int | None = None) -> str:
        return self._r(notification_id, "listing", listing_id) if self.tracked else url

    def detail(self, notification_id: int, listing_id: int | None = None, *, owner: str | None = None) -> str | None:
        """`owner` (the notification's user_id) signs the link: only for emails."""
        return self._r(notification_id, "detail", listing_id, owner) if self.tracked else None

    def lifecycle(self, email_id: int, *, owner: str | None = None) -> str:
        """The button of a plan email (lifecycle_emails): /m/<id> records the
        click and redirects to the email's target. `owner` signs it."""
        query = self._signed({}, "m", email_id, owner)
        return f"{self.base_url}/m/{email_id}" + (f"?{urlencode(query)}" if query else "")

    def open_pixel(self, kind: str, item_id: int) -> str | None:
        """The 1 px image that marks an email opened: kind "n" (notifications)
        or "m" (lifecycle_emails). Unsigned: it only ever sets opened_at."""
        return f"{self.base_url}/o/{item_id}?{urlencode({'k': kind})}" if self.tracked else None

    def unsubscribe(self, token: str | None) -> str | None:
        return f"{self.base_url}/baja?{urlencode({'t': token})}" if self.tracked and token else None

    def unsubscribe_one_click(self, token: str | None) -> str | None:
        return f"{self.base_url}/api/baja?{urlencode({'t': token})}" if self.tracked and token else None

    @property
    def buttons_allowed(self) -> bool:
        """Telegram only takes public https URLs in inline buttons."""
        return self.base_url.startswith("https://")
