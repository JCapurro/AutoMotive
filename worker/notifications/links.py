"""Tracked links (sección 7.3): every link in an alert is /r/<notification_id>.

    <WEB_BASE_URL>/r/<id>?to=listing        → the listing at its source
    <WEB_BASE_URL>/r/<id>?to=detail         → the listing's page in Automotive
    <WEB_BASE_URL>/r/<id>?to=listing&l=<listing_id>   (one item of a digest)

and every email carries the user's unsubscribe link (F7, punto 7):

    <WEB_BASE_URL>/baja?t=<token>           → a page with a confirm button
    <WEB_BASE_URL>/api/baja?t=<token>       → one-click POST (RFC 8058)

Without WEB_BASE_URL links go straight to the listing, untracked, and there is
no "Ver en Automotive".
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True)
class Links:
    base_url: str = ""

    @property
    def tracked(self) -> bool:
        return bool(self.base_url)

    def _r(self, notification_id: int, to: str, listing_id: int | None = None) -> str:
        query = {"to": to}
        if listing_id is not None:
            query["l"] = str(listing_id)
        return f"{self.base_url}/r/{notification_id}?{urlencode(query)}"

    def listing(self, notification_id: int, url: str, listing_id: int | None = None) -> str:
        return self._r(notification_id, "listing", listing_id) if self.tracked else url

    def detail(self, notification_id: int, listing_id: int | None = None) -> str | None:
        return self._r(notification_id, "detail", listing_id) if self.tracked else None

    def unsubscribe(self, token: str | None) -> str | None:
        return f"{self.base_url}/baja?{urlencode({'t': token})}" if self.tracked and token else None

    def unsubscribe_one_click(self, token: str | None) -> str | None:
        return f"{self.base_url}/api/baja?{urlencode({'t': token})}" if self.tracked and token else None

    @property
    def buttons_allowed(self) -> bool:
        """Telegram only takes public https URLs in inline buttons."""
        return self.base_url.startswith("https://")
