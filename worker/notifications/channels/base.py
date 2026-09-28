"""The channel interface (sección 7.2): the engine never knows how an alert travels.

    Channel.send(notification) → SendResult

A new channel (push, §21 "futuro") is one more adapter; nothing else changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class Notification:
    """A notifications row, with the user's contact data, ready to send."""
    id: int
    user_id: str
    kind: str
    channel: str
    payload: Mapping[str, Any]
    listing_id: int | None = None
    created_at: datetime | None = None
    telegram_chat_id: int | None = None
    email: str | None = None
    unsubscribe_token: str | None = None   # profiles.email_unsubscribe_token


@dataclass(frozen=True)
class SendResult:
    ok: bool
    error: str | None = None
    retry: bool = False                 # transient: try again later
    provider_id: str | None = None      # Telegram message id, Resend email id
    extra: Mapping[str, Any] = field(default_factory=dict)


class Channel(Protocol):
    name: str

    async def send(self, notification: Notification) -> SendResult: ...
