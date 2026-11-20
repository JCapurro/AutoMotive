"""Agencias, fase 1: the agency's alerts (intelligence/dealer_alerts.py) and
their summary email (notifications/dealer_alerts.py). Pure."""
from __future__ import annotations

from datetime import datetime, timezone

from intelligence.config import dealer_program
from intelligence.dealer_alerts import (CHEAPER_PCT, MARKET_MOVE_PCT, SLOW_DAYS_FALLBACK, decide, is_slow)
from notifications import dealer_alerts as mail
from notifications.links import Links

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


def row(**kw) -> dict:
    r = {"item_id": 7, "make": "Toyota", "model": "Corolla", "year": 2019, "price_usd": 20000,
         "market": {"n": 12, "median": 20000, "enough": True}, "model_days": {"median": 40, "n": 9},
         "days_in_stock": 10, "demand": None, "cheaper": None, "state": None}
    r.update(kw)
    return r


def kinds(alerts) -> list[str]:
    return [a.kind for a in alerts]


# --- the switch --------------------------------------------------------------

def test_switches_are_off_and_sanitized():
    p = dealer_program(None)
    assert (p["alerts_enabled"], p["alerts_every_hours"], p["photo_import_enabled"], p["photo_import_daily_limit"]) \
        == (False, 24, False, 5)
    p = dealer_program({"alerts_enabled": True, "alerts_every_hours": 6, "photo_import_enabled": True,
                        "photo_import_daily_limit": 50})
    assert (p["alerts_enabled"], p["alerts_every_hours"], p["photo_import_enabled"], p["photo_import_daily_limit"]) \
        == (True, 6, True, 50)
    for bad in ({"alerts_every_hours": 5}, {"alerts_every_hours": 169}, {"alerts_every_hours": 12.5},
                {"alerts_enabled": "true"}, {"photo_import_daily_limit": 0}, {"photo_import_daily_limit": 51},
                {"photo_import_enabled": 1}):
        p = dealer_program(bad)
        assert (p["alerts_enabled"], p["alerts_every_hours"], p["photo_import_enabled"],
                p["photo_import_daily_limit"]) == (False, 24, False, 5), bad


# --- market ------------------------------------------------------------------

def test_first_scan_only_records_the_reference():
    alerts, state = decide(row(), min_count=3, now=NOW)
    assert alerts == []
    assert (state["market_median_usd"], state["market_n"], state["market_at"]) == (20000, 12, NOW)
    assert state["cheaper_since"] == NOW


def test_market_moved_down_once_and_the_reference_moves():
    st = {"market_median_usd": 20000, "market_n": 10, "market_at": "x"}
    alerts, state = decide(row(market={"n": 14, "median": 17800, "enough": True}, state=st), min_count=3, now=NOW)
    assert kinds(alerts) == ["market_moved"]
    a = alerts[0]
    assert a.payload == {"car": "Toyota Corolla 2019", "direction": "down", "pct": 11, "before_usd": 20000,
                         "now_usd": 17800, "n": 14}
    assert state["market_median_usd"] == 17800
    # Next scan, same market: nothing new.
    again, _ = decide(row(market={"n": 14, "median": 17800, "enough": True}, state=state), min_count=3, now=NOW)
    assert again == []


def test_small_moves_add_up_against_the_kept_reference():
    st = {"market_median_usd": 20000, "market_n": 10}
    alerts, state = decide(row(market={"n": 10, "median": 19000, "enough": True}, state=st), min_count=3, now=NOW)
    assert alerts == [] and state["market_median_usd"] == 20000          # 5 %: keep the reference
    alerts, _ = decide(row(market={"n": 10, "median": 18000, "enough": True}, state=state), min_count=3, now=NOW)
    assert kinds(alerts) == ["market_moved"]                              # 10 % from where we told


def test_market_up_and_not_enough_comparables():
    st = {"market_median_usd": 20000}
    alerts, _ = decide(row(market={"n": 9, "median": 22000, "enough": True}, state=st), min_count=3, now=NOW)
    assert alerts[0].payload["direction"] == "up" and alerts[0].payload["pct"] == MARKET_MOVE_PCT
    alerts, state = decide(row(market={"n": 3, "median": 10000, "enough": False}, state=st), min_count=3, now=NOW)
    assert alerts == [] and state["market_median_usd"] == 20000


# --- cheaper nearby ----------------------------------------------------------

def test_cheaper_nearby():
    cheaper = {"listing_id": 99, "price_usd": 18000, "distance_km": 12, "source_name": "Mercado Libre", "year": 2019}
    alerts, _ = decide(row(cheaper=cheaper, state={"market_median_usd": 20000}), min_count=3, now=NOW)
    assert kinds(alerts) == ["cheaper_nearby"]
    assert alerts[0].dedup_key == "cheaper:7:99"
    assert alerts[0].payload["pct"] == 10 and alerts[0].payload["distance_km"] == 12


def test_barely_cheaper_or_without_own_price_is_not_told():
    near = {"listing_id": 99, "price_usd": 20000 * (1 - (CHEAPER_PCT - 1) / 100)}
    assert decide(row(cheaper=near), min_count=3, now=NOW)[0] == []
    assert decide(row(cheaper={"listing_id": 99, "price_usd": 1000}, price_usd=None), min_count=3, now=NOW)[0] == []


# --- slow ----------------------------------------------------------------------

def test_slow_against_the_model_or_the_fallback():
    assert is_slow(61, 40) and not is_slow(60, 40)
    assert is_slow(SLOW_DAYS_FALLBACK, None) and not is_slow(SLOW_DAYS_FALLBACK - 1, None)
    assert not is_slow(None, 40)
    alerts, _ = decide(row(days_in_stock=61), min_count=3, now=NOW)
    assert kinds(alerts) == ["slow"] and alerts[0].dedup_key == "slow:7"
    assert alerts[0].payload == {"car": "Toyota Corolla 2019", "days": 61, "model_days": 40}
    # Fewer than 5 sold cars: we don't know the model, the fallback decides.
    alerts, _ = decide(row(days_in_stock=59, model_days={"median": 10, "n": 4}), min_count=3, now=NOW)
    assert alerts == []


# --- demand (C2: never fewer than 3 people) ------------------------------------

def test_new_demand_needs_min_count_new_people():
    first, st = decide(row(demand={"searches": 4, "people": 2}), min_count=3, now=NOW)
    assert first == [] and (st["demand_searches"], st["demand_people"]) == (4, 2)
    two_more, st2 = decide(row(demand={"searches": 6, "people": 4}, state=st), min_count=3, now=NOW)
    assert two_more == [] and st2["demand_people"] == 2                  # 2 new people: not told, mark stays
    three, st3 = decide(row(demand={"searches": 8, "people": 5}, state=st2), min_count=3, now=NOW)
    assert kinds(three) == ["new_demand"] and three[0].payload["searches"] == 4
    assert (st3["demand_searches"], st3["demand_people"]) == (8, 5)


def test_demand_min_count_is_never_below_three_and_searches_count_too():
    st = {"demand_searches": 0, "demand_people": 0}
    assert decide(row(demand={"searches": 2, "people": 2}, state=st), min_count=1, now=NOW)[0] == []
    many_by_few, _ = decide(row(demand={"searches": 9, "people": 2}, state=st), min_count=3, now=NOW)
    assert many_by_few == []
    higher, _ = decide(row(demand={"searches": 4, "people": 4}, state=st), min_count=5, now=NOW)
    assert higher == []


def test_searches_that_leave_never_bring_the_alert_back():
    st = {"demand_searches": 8, "demand_people": 5}
    _, st = decide(row(demand={"searches": 2, "people": 1}, state=st), min_count=3, now=NOW)
    assert (st["demand_searches"], st["demand_people"]) == (8, 5)
    back, _ = decide(row(demand={"searches": 8, "people": 5}, state=st), min_count=3, now=NOW)
    assert back == []


def test_no_demand_for_a_dealer_not_approved():
    alerts, st = decide(row(demand=None, state={"demand_searches": 0, "demand_people": 0}), min_count=3, now=NOW)
    assert alerts == [] and st["demand_people"] == 0


# --- the email -----------------------------------------------------------------

LINKS = Links(base_url="https://eseauto.test", secret="s")


def test_summary_email():
    alerts = [
        {"id": 3, "kind": "slow", "payload": {"car": "Ford Focus 2017", "days": 70, "model_days": 41}},
        {"id": 1, "kind": "market_moved", "payload": {"car": "Toyota Corolla 2019", "direction": "down", "pct": 11,
                                                      "before_usd": 20000, "now_usd": 17800, "n": 14}},
        {"id": 2, "kind": "cheaper_nearby", "payload": {"car": "Toyota Corolla 2019", "pct": 9, "price_usd": 18200,
                                                        "distance_km": 12, "source_name": "Mercado Libre"}},
        {"id": 4, "kind": "new_demand", "payload": {"car": "VW Amarok 2018", "searches": 3}},
    ]
    m = mail.message(alerts, LINKS)
    assert m.subject == "4 novedades de tu stock en Ese Auto"
    lines = [x for x in m.text.splitlines() if x.startswith("• ")]
    assert lines == [
        "• Apareció uno como tu Toyota Corolla 2019 9 % más barato a 12 km: USD 18.200, en Mercado Libre.",
        "• Bajó el mercado del Toyota Corolla 2019: la mediana pasó de USD 20.000 a USD 17.800 (11 %).",
        "• Entraron 3 búsquedas nuevas que aceptan tu VW Amarok 2018 en tu zona.",
        "• Tu Ford Focus 2017 lleva 70 días en stock. El modelo se vende en unos 41.",
    ]
    assert "https://eseauto.test/agencia/stock" in m.text and "https://eseauto.test/agencia/datos" in m.text
    assert "no valuaciones" in m.text
    assert not any(t in m.text.lower() for t in ("tasaci", "tasado", "valor real", "precio real"))   # §19
    assert "https://eseauto.test/agencia/datos" in m.html and "<li" in m.html


def test_one_alert_and_the_cap_on_lines():
    one = mail.message([{"id": 1, "kind": "slow", "payload": {"car": "Ford Ka 2015", "days": 65, "model_days": None}}],
                       LINKS)
    assert one.subject == "Una novedad de tu stock en Ese Auto"
    assert "• Tu Ford Ka 2015 lleva 65 días en stock." in one.text
    many = [{"id": i, "kind": "slow", "payload": {"car": f"Auto {i}", "days": 70}} for i in range(25)]
    m = mail.message(many, LINKS)
    assert sum(1 for x in m.text.splitlines() if x.startswith("• ")) == mail.MAX_LINES
    assert "Y 5 más en tu panel." in m.text


def test_html_escapes_what_comes_from_listings():
    m = mail.message([{"id": 1, "kind": "slow", "payload": {"car": "<b>X</b>", "days": 70}}], LINKS)
    assert "<b>X</b>" not in m.html and "&lt;b&gt;X&lt;/b&gt;" in m.html
