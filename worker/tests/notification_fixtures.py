"""Alert fixtures shared by the notification tests: the §22 examples."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from intelligence.copy import RED_FLAG
from notifications.channels.base import Notification
from notifications.links import Links


NOW = datetime(2026, 9, 27, 18, 30, tzinfo=timezone.utc)
LINKS = Links("https://automotive.app")

FIESTA = {"id": 501, "title": "Ford Fiesta Titanium 1.6 2017 impecable", "make": "Ford", "model": "Fiesta",
          "trim": "Titanium", "year": 2017, "mileage_km": 112000, "price": 10300.0, "currency": "USD",
          "url": "https://auto.mercadolibre.com.ar/MLA-123456789-ford-fiesta-titanium-_JM",
          "source": "mercadolibre", "location_text": "Palermo, Capital Federal",
          "images": ["https://images.example.test/fiesta-front.jpg", {"url": "https://images.example.test/fiesta-side.jpg"},
                     "https://images.example.test/fiesta-interior.jpg"],
          "published_at": (NOW - timedelta(minutes=4)).isoformat(),
          "first_seen_at": (NOW - timedelta(minutes=2)).isoformat()}


def notification(kind: str, payload: dict, *, id=42, listing_id=501) -> Notification:
    return Notification(id=id, user_id="u1", kind=kind, channel="telegram", payload=payload,
                        listing_id=listing_id, telegram_chat_id=1234, email="ana@automotive.test")


OPPORTUNITY = notification("opportunity", {
    "listing": FIESTA, "profile_name": "Fiesta Titanium AMBA",
    "match": {"score": 88, "level": "high", "diff_pct": 8.2},
    "red_flags": ["No especifica cantidad de dueños: conviene verificar."],
    "questions": ["¿Cuántos dueños tuvo?", "¿Tiene VTV vigente?"],
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
# PAR-03: payload["price_track"] (notifications/service.price_track_payload).
TRACK_1 = {"drops": 1, "cum_pct": 6.0, "cum_usd": 700.0, "currency": "USD", "first_at": "2026-09-20T12:00:00+00:00"}
TRACK_3 = {"drops": 3, "cum_pct": 12.4, "cum_usd": 1450.0, "currency": "USD", "first_at": "2026-09-12T12:00:00+00:00"}
TRACK_ARS = {"drops": 3, "cum_pct": 9.4, "cum_usd": 1000.0, "cum_ars": 1300000.0, "currency": "ARS",
             "first_at": "2026-09-12T12:00:00+00:00"}
OPPORTUNITY_1_DROP = notification("opportunity", {**OPPORTUNITY.payload, "price_track": TRACK_1})
OPPORTUNITY_3_DROPS = notification("opportunity", {**OPPORTUNITY.payload, "price_track": TRACK_3})
OPPORTUNITY_ARS = notification("opportunity", {
    **OPPORTUNITY.payload, "price_track": TRACK_ARS,
    "listing": {**FIESTA, "price": 12500000.0, "currency": "ARS", "published_at": None,
                "first_seen_at": (NOW - timedelta(days=17)).isoformat()},
})
# PAR-02: much_cheaper in the [35, 50) band, first (warning), then an informative flag.
OPPORTUNITY_MUCH_CHEAPER = notification("opportunity", {
    **OPPORTUNITY.payload,
    "red_flags": [RED_FLAG["much_cheaper_verify"].format(pct="40"), RED_FLAG["no_owners"]],
})
DIGEST = notification("digest", {"date": "2026-09-27", "degraded": 1, "items": [
    {"section": "price_drops", "listing_id": 501, "kind": "price_drop", "listing": {**FIESTA, "price": 10800.0},
     "price_drop": {"old_price": 11500.0, "new_price": 10800.0, "currency": "USD", "drop_pct": 6.09}},
    {"section": "matches", "listing_id": 502, "kind": "opportunity", "degraded": "daily_cap",
     "listing": {**FIESTA, "id": 502, "mileage_km": 98000, "price": 10900.0},
     "match": {"score": 86, "level": "high"}, "price_track": TRACK_1},
    {"section": "matches", "listing_id": 503, "kind": "match",
     "listing": {**FIESTA, "id": 503, "trim": None, "year": 2016, "mileage_km": 140000,
                 "price": 12500000.0, "currency": "ARS", "published_at": None,
                 "first_seen_at": (NOW - timedelta(days=2, hours=3)).isoformat()},
     "match": {"score": 58, "level": "match"}, "price_track": TRACK_ARS},
    {"section": "matches", "listing_id": 505, "kind": "match",
     "listing": {**FIESTA, "id": 505, "trim": "S", "year": 2015, "mileage_km": 151000, "price": 8900.0},
     "match": {"score": 52, "level": "match"}},
    {"section": "gone", "listing_id": 504, "kind": "listing_gone",
     "listing": {**FIESTA, "id": 504, "make": None, "title": "Fiesta Kinetic Design 2015"}},
]}, id=43, listing_id=None)

# PAR-01: payload["total_cost"] (cost_estimator.email_payload) of golden case 1
# (ARS 20.000.000, CABA, private, 2017 sedan, dollar 1.300) and case 18 (no zone).
TOTAL_COST_CABA = {"ars_min": 21188000, "ars_max": 21518000, "usd_min": 16290, "usd_max": 16560, "missing": [],
                   "jurisdiction": ["caba"], "as_of": "2026-10-30"}
TOTAL_COST_NO_ZONE = {"ars_min": 20208000, "ars_max": 20219000, "usd_min": 15540, "usd_max": 15560,
                      "missing": ["sellos", "patente"], "jurisdiction": None, "as_of": "2026-10-30"}
_ARS_LISTING = {**FIESTA, "price": 20000000.0, "currency": "ARS"}
OPPORTUNITY_TOTAL_COST = notification("opportunity", {**OPPORTUNITY.payload, "listing": _ARS_LISTING,
                                                      "total_cost": TOTAL_COST_CABA})
OPPORTUNITY_TOTAL_COST_MISSING = notification("opportunity", {**OPPORTUNITY.payload, "listing": _ARS_LISTING,
                                                              "total_cost": TOTAL_COST_NO_ZONE})
# The flag on and no app_config.cost_estimator: on_matches stores no key, the
# email is OPPORTUNITY's byte for byte (test_notifications_total_cost.py builds it).
OPPORTUNITY_TOTAL_COST_NO_CONFIG = notification("opportunity", dict(OPPORTUNITY.payload))

# PRO-01: payload["contact_message"] (contact_message.render, Pro with contact_email).
CONTACT_MESSAGE = "Hola, vi tu Fiesta 2017 publicado.\n¿Lo seguís teniendo?\n¿Cuántos dueños tuvo?\n¿Cuándo se puede ver?"
OPPORTUNITY_CONTACT_MESSAGE = notification("opportunity", {**OPPORTUNITY.payload, "contact_message": CONTACT_MESSAGE})

CASES = {"opportunity": OPPORTUNITY, "new_match": NEW_MATCH, "price_drop": PRICE_DROP, "digest": DIGEST,
         "opportunity_1_drop": OPPORTUNITY_1_DROP, "opportunity_3_drops": OPPORTUNITY_3_DROPS,
         "opportunity_ars": OPPORTUNITY_ARS, "opportunity_much_cheaper_verify": OPPORTUNITY_MUCH_CHEAPER,
         "opportunity_total_cost": OPPORTUNITY_TOTAL_COST, "opportunity_total_cost_missing": OPPORTUNITY_TOTAL_COST_MISSING,
         "opportunity_total_cost_no_config": OPPORTUNITY_TOTAL_COST_NO_CONFIG,
         "opportunity_contact_message": OPPORTUNITY_CONTACT_MESSAGE}
