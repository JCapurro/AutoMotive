"""Alert fixtures shared by the notification tests: the §22 examples."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from notifications.channels.base import Notification
from notifications.links import Links


NOW = datetime(2026, 9, 27, 18, 30, tzinfo=timezone.utc)
LINKS = Links("https://automotive.app")

FIESTA = {"id": 501, "title": "Ford Fiesta Titanium 1.6 2017 impecable", "make": "Ford", "model": "Fiesta",
          "trim": "Titanium", "year": 2017, "mileage_km": 112000, "price": 10300.0, "currency": "USD",
          "url": "https://auto.mercadolibre.com.ar/MLA-123456789-ford-fiesta-titanium-_JM",
          "source": "mercadolibre", "location_text": "Palermo, Capital Federal",
          "published_at": (NOW - timedelta(minutes=4)).isoformat(),
          "first_seen_at": (NOW - timedelta(minutes=2)).isoformat()}


def notification(kind: str, payload: dict, *, id=42, listing_id=501) -> Notification:
    return Notification(id=id, user_id="u1", kind=kind, channel="telegram", payload=payload,
                        listing_id=listing_id, telegram_chat_id=1234, email="ana@automotive.test")


OPPORTUNITY = notification("opportunity", {
    "listing": FIESTA, "profile_name": "Fiesta Titanium AMBA",
    "match": {"score": 88, "level": "high", "diff_pct": 8.2},
    "red_flags": ["No especifica cantidad de dueños: conviene verificar."],
})
NEW_MATCH = notification("new_match", {
    "listing": {**FIESTA, "mileage_km": 128000, "price": 11000.0, "published_at": None},
    "profile_name": "Fiesta Titanium AMBA",
    "match": {"score": 74, "level": "good", "diff_pct": 1.5},
})
PRICE_DROP = notification("price_drop", {
    "listing": {**FIESTA, "price": 10800.0}, "profile_name": "Fiesta Titanium AMBA",
    "match": {"score": 81, "level": "good", "diff_pct": 4.0},
    "price_drop": {"old_price": 11500.0, "new_price": 10800.0, "currency": "USD", "drop_pct": 6.09},
})
DIGEST = notification("digest", {"date": "2026-09-27", "degraded": 1, "items": [
    {"section": "price_drops", "listing_id": 501, "kind": "price_drop", "listing": {**FIESTA, "price": 10800.0},
     "price_drop": {"old_price": 11500.0, "new_price": 10800.0, "currency": "USD", "drop_pct": 6.09}},
    {"section": "matches", "listing_id": 502, "kind": "opportunity", "degraded": "daily_cap",
     "listing": {**FIESTA, "id": 502, "mileage_km": 98000, "price": 10900.0},
     "match": {"score": 86, "level": "high"}},
    {"section": "matches", "listing_id": 503, "kind": "match",
     "listing": {**FIESTA, "id": 503, "trim": None, "year": 2016, "mileage_km": 140000,
                 "price": 12500000.0, "currency": "ARS"},
     "match": {"score": 58, "level": "match"}},
    {"section": "gone", "listing_id": 504, "kind": "listing_gone",
     "listing": {**FIESTA, "id": 504, "make": None, "title": "Fiesta Kinetic Design 2015"}},
]}, id=43, listing_id=None)

CASES = {"opportunity": OPPORTUNITY, "new_match": NEW_MATCH, "price_drop": PRICE_DROP, "digest": DIGEST}
