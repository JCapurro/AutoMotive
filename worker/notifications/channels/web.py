"""Web inbox (§21): the notifications row is the delivery. Supabase Realtime
pushes it to the open app (badge + feed, F4); nothing leaves the worker."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from notifications import templates
from notifications.channels.base import Notification, SendResult
from notifications.links import Links


class WebChannel:
    name = "web"

    def __init__(self, links: Links, clock: Callable[[], datetime] | None = None) -> None:
        self.links = links
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def send(self, notification: Notification) -> SendResult:
        return SendResult(True, extra={"web": templates.web(notification, self.links, self.clock())})
