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
# (ARS 20.000.000, CABA, private, 2017 sedan, dollar 1.300) and case 18 (no zone:
# no amount at all since Juan's 02/11 request).
TOTAL_COST_CABA = {"ars_min": 21188000, "ars_max": 21518000, "usd_min": 16290, "usd_max": 16560, "missing": [],
                   "jurisdiction": ["caba"], "as_of": "2026-10-30"}
TOTAL_COST_NO_ZONE = {"ars_min": None, "ars_max": None, "usd_min": None, "usd_max": None,
                      "missing": ["zone"], "jurisdiction": None, "as_of": "2026-10-30"}
_ARS_LISTING = {**FIESTA, "price": 20000000.0, "currency": "ARS"}
OPPORTUNITY_TOTAL_COST = notification("opportunity", {**OPPORTUNITY.payload, "listing": _ARS_LISTING,
                                                      "total_cost": TOTAL_COST_CABA})
OPPORTUNITY_TOTAL_COST_MISSING = notification("opportunity", {**OPPORTUNITY.payload, "listing": _ARS_LISTING,
                                                              "total_cost": TOTAL_COST_NO_ZONE})
# The flag on and no app_config.cost_estimator: on_matches stores no key, the
# email is OPPORTUNITY's byte for byte (test_notifications_total_cost.py builds it).
OPPORTUNITY_TOTAL_COST_NO_CONFIG = notification("opportunity", dict(OPPORTUNITY.payload))

# PRO-02: payload["margin"] (margin.email_payload) of tests/test_margin.py's
# pool (6 dealers at a median of USD 18.000, golden case 1's listing), with
# and without the search's place, and with only 2 dealers (Juan, 02/11: say so).
MARGIN_CABA = {"status": "ok", "usd_min": 1210, "usd_max": 1230, "pct_min": 7, "pct_max": 8, "dealer_median": 18000,
               "dealer_n": 6, "reconditioning_pct": 5.0, "transfer_status": "ok", "jurisdiction": ["caba"],
               "as_of": "2026-10-30"}
MARGIN_NO_ZONE = {"status": "ok", "usd_min": 1850, "usd_max": 1850, "pct_min": 11, "pct_max": 11,
                  "dealer_median": 18000, "dealer_n": 6, "reconditioning_pct": 5.0, "transfer_status": "no_zone",
                  "jurisdiction": None, "as_of": "2026-11-02"}
MARGIN_FEW_DEALERS = {"status": "few_dealers", "dealer_n": 2, "min_n": 5}
OPPORTUNITY_MARGIN = notification("opportunity", {**OPPORTUNITY.payload, "listing": _ARS_LISTING, "margin": MARGIN_CABA})
OPPORTUNITY_MARGIN_NO_ZONE = notification("opportunity", {**OPPORTUNITY.payload, "listing": _ARS_LISTING,
                                                          "margin": MARGIN_NO_ZONE})
OPPORTUNITY_MARGIN_FEW_DEALERS = notification("opportunity", {**OPPORTUNITY.payload, "listing": _ARS_LISTING,
                                                              "margin": MARGIN_FEW_DEALERS})
PRICE_DROP_MARGIN = notification("price_drop", {**PRICE_DROP.payload, "margin": MARGIN_CABA})
# PRO-01: payload["contact_message"] (contact_message.render, Pro with contact_email).
CONTACT_MESSAGE = "Hola, vi tu Fiesta 2017 publicado.\n¿Lo seguís teniendo?\n¿Cuántos dueños tuvo?\n¿Cuándo se puede ver?"
OPPORTUNITY_CONTACT_MESSAGE = notification("opportunity", {**OPPORTUNITY.payload, "contact_message": CONTACT_MESSAGE})
# PRO-01, option C (Juan, 02/11): payload["seller_unknown"], the strict seller
# filter let a listing without a known seller through.
OPPORTUNITY_SELLER_UNKNOWN = notification("opportunity", {**OPPORTUNITY.payload, "seller_unknown": True})

# PAR-02 resto: the email's two flags cut by app_config.red_flags.order, from
# the stored flags as intelligence/red_flags.py builds them.
def _cut(*flags: tuple[str, str, str]) -> list[str]:
    from intelligence.config import DEFAULT_FLAG_ORDER
    from notifications.service import flag_texts
    return flag_texts([{"id": i, "text": t, "severity": s} for i, t, s in flags], DEFAULT_FLAG_ORDER)


_MUCH_CHEAPER = ("much_cheaper", RED_FLAG["much_cheaper"].format(pct="28"), "warning")
OPPORTUNITY_PRIVATE_MANY = notification("opportunity", {**OPPORTUNITY.payload, "red_flags": _cut(
    ("no_owners", RED_FLAG["no_owners"], "info"),
    _MUCH_CHEAPER,
    ("private_many_listings", RED_FLAG["private_many_listings"].format(n="7"), "info"))})
OPPORTUNITY_DUPLICATE_PHOTOS = notification("opportunity", {**OPPORTUNITY.payload, "red_flags": _cut(
    ("short_description", RED_FLAG["short_description"], "info"),
    _MUCH_CHEAPER,
    ("duplicate_photos", RED_FLAG["duplicate_photos"].format(source="Rosario Garage"), "warning"))})

CASES = {"opportunity": OPPORTUNITY, "new_match": NEW_MATCH, "price_drop": PRICE_DROP, "digest": DIGEST,
         "opportunity_1_drop": OPPORTUNITY_1_DROP, "opportunity_3_drops": OPPORTUNITY_3_DROPS,
         "opportunity_ars": OPPORTUNITY_ARS, "opportunity_much_cheaper_verify": OPPORTUNITY_MUCH_CHEAPER,
         "opportunity_total_cost": OPPORTUNITY_TOTAL_COST, "opportunity_total_cost_missing": OPPORTUNITY_TOTAL_COST_MISSING,
         "opportunity_total_cost_no_config": OPPORTUNITY_TOTAL_COST_NO_CONFIG,
         "opportunity_contact_message": OPPORTUNITY_CONTACT_MESSAGE,
         "opportunity_seller_unknown": OPPORTUNITY_SELLER_UNKNOWN,
         "opportunity_margin": OPPORTUNITY_MARGIN, "opportunity_margin_no_zone": OPPORTUNITY_MARGIN_NO_ZONE,
         "opportunity_margin_few_dealers": OPPORTUNITY_MARGIN_FEW_DEALERS,
         "price_drop_margin": PRICE_DROP_MARGIN,
         "opportunity_private_many_listings": OPPORTUNITY_PRIVATE_MANY,
         "opportunity_duplicate_photos": OPPORTUNITY_DUPLICATE_PHOTOS}
