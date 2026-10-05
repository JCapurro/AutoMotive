"""normalization/drafts.py: the deterministic step after the LLM (sección 8.4, paso 4)."""
from __future__ import annotations

import datetime as dt

from llm.schemas import SearchDraft
from intelligence.matching import match
from normalization.drafts import MAX_VEHICLES, normalize_draft, normalize_drafts
from seed_catalog import seed_catalog

TODAY = dt.date(2026, 9, 28)
EMPTY = dict(make=None, model=None, trim=None, trim_strict=False, year_min=None, year_max=None, price_max=None,
             price_target=None, currency=None, km_max=None, km_target=None, transmission=None, fuel=None,
             seller_type=None, location=None, radius_km=None)


def draft(**kw) -> SearchDraft:
    return SearchDraft(**{**EMPTY, **kw})


def norm(**kw) -> dict:
    return normalize_draft(seed_catalog(), draft(**kw), today=TODAY)


def test_catalog_names_win_over_the_llm_spelling():
    out = norm(make="vw", model="goltrend", trim="highline")
    assert out["resolved"]
    assert (out["values"]["make"], out["values"]["model"], out["values"]["trim"]) == ("Volkswagen", "Gol Trend", "Highline")
    assert out["notes"] == []


def test_typos_resolve_fuzzily():
    out = norm(make="Toyota", model="Corola")
    assert out["values"]["model"] == "Corolla"


def test_model_without_make():
    out = norm(model="Hilux SW4")
    assert (out["values"]["make"], out["values"]["model"]) == ("Toyota", "SW4")


def test_trim_inside_the_model_field():
    out = norm(make="Volkswagen", model="Gol Trend Highline")
    assert (out["values"]["model"], out["values"]["trim"]) == ("Gol Trend", "Highline")


def test_unknown_model_leaves_the_vehicle_for_the_user():
    out = norm(make="Tesla", model="Model 3", year_min=2021)
    assert not out["resolved"]
    assert (out["values"]["make"], out["values"]["model"]) == ("", "")
    assert out["values"]["year_min"] == 2021
    assert "Tesla Model 3" in out["notes"][0]


def test_known_make_unknown_model_keeps_the_make():
    out = norm(make="Ford", model="Mustang")
    assert (out["values"]["make"], out["values"]["model"]) == ("Ford", "")
    assert not out["resolved"]


def test_make_only():
    out = norm(make="Chevrolet")
    assert out["values"]["make"] == "Chevrolet"
    assert "Falta el modelo" in out["notes"][0]


def test_trim_of_another_model_is_dropped():
    out = norm(make="Ford", model="Fiesta", trim="Highline", trim_strict=True)
    assert out["values"]["trim"] == "" and out["values"]["trim_strict"] is False
    assert "Highline" in out["notes"][0]


def test_trim_is_free_text_when_the_catalog_has_none():
    assert norm(make="Suzuki", model="Swift", trim="GLX")["values"]["trim"] == "GLX"


def test_years_are_ordered_and_bounded():
    out = norm(make="Ford", model="Focus", year_min=2018, year_max=2014)
    assert (out["values"]["year_min"], out["values"]["year_max"]) == (2014, 2018)
    out = norm(make="Ford", model="Focus", year_min=1800, year_max=2090)
    assert (out["values"]["year_min"], out["values"]["year_max"]) == (None, None)
    assert len(out["notes"]) == 2


def test_years_outside_production_are_flagged_not_changed():
    out = norm(make="Ford", model="Fiesta", year_min=2021)
    assert out["values"]["year_min"] == 2021
    assert "se fabricó" in out["notes"][0]


def test_money():
    out = norm(make="Ford", model="Ka", price_max=8500.4, currency=None)
    assert (out["values"]["price_max"], out["values"]["currency"]) == (8500, "USD")
    assert "moneda" in out["notes"][0]
    assert norm(make="Ford", model="Ka", price_max=9_000_000)["values"]["currency"] == "ARS"
    assert norm(make="Ford", model="Ka", price_max=-5, currency="USD")["values"]["price_max"] is None
    out = norm(make="Ford", model="Ka", price_max=8000, price_target=9000, currency="USD")
    assert out["values"]["price_target"] is None


def test_km_and_radius():
    out = norm(make="Ford", model="Ka", km_max=-1, km_target=90_000, radius_km=99_999, location=" Zona Norte ")
    assert (out["values"]["km_max"], out["values"]["km_target"]) == (None, 90_000)
    assert out["values"]["radius_km"] is None
    assert out["values"]["location"] == "Zona Norte"


def test_enums_become_the_form_empty_value():
    values = norm(make="Ford", model="Ka")["values"]
    assert (values["transmission"], values["fuel"], values["seller_type"]) == ("", "", "")


def test_duplicates_collapse_and_the_list_is_capped():
    fiesta = draft(make="Ford", model="Fiesta", trim="Titanium")
    out = normalize_drafts(seed_catalog(), [fiesta, draft(make="ford", model="fiesta", trim="titanium"),
                                            draft(make="Ford", model="Fiesta", trim="SE")], today=TODAY)
    assert len(out["drafts"]) == 1
    assert out["drafts"][0]["values"]["trims"] == ["Titanium", "SE"]

    many = [draft(make="Ford", model=m) for m in ("Fiesta", "Focus", "Ka", "Ranger", "EcoSport", "Territory")]
    assert len(normalize_drafts(seed_catalog(), many, today=TODAY)["drafts"]) == MAX_VEHICLES


def test_no_vehicles():
    assert normalize_drafts(seed_catalog(), [], today=TODAY) == {"drafts": []}


def test_multiple_versions_in_one_proposal_and_distinct_models():
    out = normalize_drafts(seed_catalog(), [
        draft(model="Fiesta", trims=["Titanium", "SE"], trim_strict=True, price_max=12000),
        draft(model="Polo", trim="Highline", price_max=12000),
    ], today=TODAY)
    assert len(out["drafts"]) == 2
    fiesta, polo = (d["values"] for d in out["drafts"])
    assert fiesta["trims"] == ["Titanium", "SE"]
    assert fiesta["trim_strict"] is True
    assert polo["trims"] == ["Highline"]
    assert fiesta["price_max"] == polo["price_max"] == 12000


def test_both_versions_match_the_same_search():
    values = norm(model="Fiesta", trims=["Titanium", "SE"], trim_strict=True)["values"]
    profile = {"filters": {"make": values["make"], "model": values["model"],
                            "trims": values["trims"], "trim_strict": True}}
    for trim in ("Titanium", "SE"):
        assert match({"make": "Ford", "model": "Fiesta", "trim": trim}, profile) is not None
    assert match({"make": "Ford", "model": "Fiesta", "trim": "S"}, profile) is None


def test_invalid_versions_do_not_remove_valid_ones():
    out = norm(model="Fiesta", trims=["titanium", "SE", "Highline", "Titanium"])
    assert out["values"]["trims"] == ["Titanium", "SE"]
    assert any("Highline" in n for n in out["notes"])


def test_grouping_does_not_narrow_the_requested_ranges():
    out = normalize_drafts(seed_catalog(), [
        draft(model="Fiesta", trim="Titanium", year_min=2016, year_max=2018, km_max=100000),
        draft(model="Fiesta", trim="SE", year_min=2014, year_max=2016, km_max=150000),
    ], today=TODAY)
    values = out["drafts"][0]["values"]
    assert (values["year_min"], values["year_max"], values["km_max"]) == (2014, 2018, 150000)
    assert out["drafts"][0]["notes"]
