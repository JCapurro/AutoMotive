"""Tracked links (sección 7.3): every link in an alert is /r/<notification_id>.

    <WEB_BASE_URL>/r/<id>?to=listing        → the listing at its source
    <WEB_BASE_URL>/r/<id>?to=detail         → the listing's page in Ese Auto
    <WEB_BASE_URL>/r/<id>?to=listing&l=<listing_id>   (one item of a digest)

the button of a plan email (docs/MAILS_DE_PLAN.md) is /m/<lifecycle_email_id>,
the feedback link of a remarketing email is /f/<lifecycle_email_id>,
the Sí / No of the welcome email's question (PAR-05, Prueba B) is
/vender-mi-auto?e=<lifecycle_email_id>&r=si|no,
every email carries a 1 px image that marks it opened,

    <WEB_BASE_URL>/o/<id>?k=n|m             → notifications | lifecycle_emails

and the user's unsubscribe link (F7, punto 7):

    <WEB_BASE_URL>/baja?t=<token>           → a page with a confirm button
    <WEB_BASE_URL>/api/baja?t=<token>       → one-click POST (RFC 8058)

The other plans' alerts show Pro locked with a way to the public plans page,
<WEB_BASE_URL>/planes: untracked and unsigned, it needs no session.

Navigation links (/r and /m) are unsigned and never grant account access.
With ALERT_LINK_SECRET, feedback and sell-intent links carry signatures for
only their limited action, without creating an account session.

Without WEB_BASE_URL links go straight to the listing, untracked, and there is
no "Ver en Ese Auto".
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import hmac
from urllib.parse import urlencode

# Shorter secrets are ignored (the web ignores them too): feedback goes unsigned.
MIN_SECRET_LENGTH = 32


def signature(secret: str, scope: str, item_id: int, user_id: str) -> str:
    """HMAC-SHA256 of v1:<scope>:<id>:<user_id>, truncated to 128 bits, base64url.
    Feedback keeps the existing "m" scope for compatibility with sent links.
    Same as web/lib/alert-session.ts; this is not a login credential."""
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

    def _r(self, notification_id: int, to: str, listing_id: int | None = None) -> str:
        query = {"to": to}
        if listing_id is not None:
            query["l"] = str(listing_id)
        return f"{self.base_url}/r/{notification_id}?{urlencode(query)}"

    def listing(self, notification_id: int, url: str, listing_id: int | None = None) -> str:
        return self._r(notification_id, "listing", listing_id) if self.tracked else url

    def detail(self, notification_id: int, listing_id: int | None = None, *, owner: str | None = None) -> str | None:
        """Unsigned navigation; `owner` is accepted for caller compatibility."""
        return self._r(notification_id, "detail", listing_id) if self.tracked else None

    def lifecycle(self, email_id: int, *, owner: str | None = None) -> str:
        """The button of a plan email (lifecycle_emails): /m/<id> records the
        click and redirects to the email's target without granting a session.
        `owner` is accepted for caller compatibility."""
        return f"{self.base_url}/m/{email_id}"

    def feedback(self, email_id: int, reason: str | None = None, *, owner: str | None = None) -> str:
        """The feedback link of a remarketing email: /f/<id> lists the reasons
        (`reason` comes marked) and asks to confirm. Keeps the legacy "m"
        signature for the email and owner, scoped only to feedback."""
        query = {"r": reason} if reason else {}
        if owner and self.signs:
            query["s"] = signature(self.secret, "m", email_id, owner)
        return f"{self.base_url}/f/{email_id}" + (f"?{urlencode(query)}" if query else "")

    def sell_intent(self, email_id: int, answer: str, *, owner: str | None = None) -> str:
        """PAR-05, Prueba B: one answer (`answer` "si" or "no") to «¿Tenés que
        vender tu auto actual para comprar?» in the welcome email. The page
        asks to confirm (mail scanners open every link). Signed like the
        email's button (scope "m"): same email, same owner."""
        query = self._signed({"e": str(email_id), "r": answer}, "m", email_id, owner)
        return f"{self.base_url}/vender-mi-auto?{urlencode(query)}"

    def open_pixel(self, kind: str, item_id: int) -> str | None:
        """The 1 px image that marks an email opened: kind "n" (notifications)
        or "m" (lifecycle_emails). Unsigned: it only ever sets opened_at."""
        return f"{self.base_url}/o/{item_id}?{urlencode({'k': kind})}" if self.tracked else None

    def plans(self) -> str | None:
        """The public plans page, where the other plans' Pro preview leads (Juan, 03/11)."""
        return f"{self.base_url}/planes" if self.tracked else None

    def unsubscribe(self, token: str | None) -> str | None:
        return f"{self.base_url}/baja?{urlencode({'t': token})}" if self.tracked and token else None

    def unsubscribe_one_click(self, token: str | None) -> str | None:
        return f"{self.base_url}/api/baja?{urlencode({'t': token})}" if self.tracked and token else None

    @property
    def buttons_allowed(self) -> bool:
        """Telegram only takes public https URLs in inline buttons."""
        return self.base_url.startswith("https://")
