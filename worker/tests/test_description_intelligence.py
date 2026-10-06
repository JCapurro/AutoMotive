from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from collectors.base import Listing
from llm.schemas import ListingFacts
from normalization.description_facts import DescriptionFacts, from_llm, parse
from pipeline.enrich import DescriptionLLM
from normalization.listing import normalize_listing
from pipeline.ingest import merge
from test_normalization_v2 import CATALOG
from datetime import datetime, timezone
from intelligence.red_flags import red_flags
from intelligence.config import IntelligenceConfig
from intelligence.seller_questions import seller_questions


def answer(**values):
    data = {k: None for k in ListingFacts.model_fields}
    data.update(equipment=[], evidence=[])
    data.update(values)
    return ListingFacts.model_validate(data)


def read(text, **values):
    return from_llm(answer(**values), parse(text), llm_at="2026-10-05T00:00:00+00:00",
                    title="Ford Fiesta", description=text)


def test_preserves_seller_claims_and_literal_evidence_round_trip():
    text = "Único dueño. Distribución hecha. Motor 1.6. Tiene techo solar. Acepto permuta."
    facts = read(text, single_owner=True, timing_belt_changed=True, engine="1.6",
                 equipment=["techo solar"], accepts_trade_in=True, evidence=[
                     {"field": "single_owner", "quote": "Único dueño"},
                     {"field": "timing_belt_changed", "quote": "Distribución hecha"},
                     {"field": "engine", "quote": "Motor 1.6"},
                     {"field": "equipment", "quote": "Tiene techo solar"},
                     {"field": "accepts_trade_in", "quote": "Acepto permuta"},
                 ])
    stored = DescriptionFacts.from_json(facts.to_json())
    assert stored.claims == {"single_owner": True, "timing_belt_changed": True,
                             "engine": "1.6", "equipment": ["techo solar"], "accepts_trade_in": True}
    assert len(stored.evidence) == 5
    assert stored.input_hash and stored.to_json()["v"] == 2


def test_rejects_missing_or_invented_evidence_and_unknown_values():
    facts = read("Muy buen estado.", single_owner=True, service_history=True,
                 engine="1.6", evidence=[{"field": "single_owner", "quote": "Único dueño"},
                                         {"field": "engine", "quote": "Muy buen estado"}])
    assert facts.claims == {}
    assert facts.evidence == []


def test_negations_do_not_become_positive_claims():
    facts = read("No soy único dueño. Sin choques. No acepto permuta. VTV vencida.",
                 single_owner=True, damage_mentioned=True, accepts_trade_in=True,
                 vtv_current=True, evidence=[
                     {"field": "single_owner", "quote": "No soy único dueño"},
                     {"field": "damage_mentioned", "quote": "Sin choques"},
                     {"field": "accepts_trade_in", "quote": "No acepto permuta"},
                     {"field": "vtv_current", "quote": "VTV vencida"},
                 ])
    assert facts.claims == {}
    negative = read("Sin choques. No acepto permuta.", damage_mentioned=False,
                    accepts_trade_in=False, evidence=[
                        {"field": "damage_mentioned", "quote": "Sin choques"},
                        {"field": "accepts_trade_in", "quote": "No acepto permuta"},
                    ])
    assert negative.claims == {"damage_mentioned": False, "accepts_trade_in": False}


def test_price_and_mileage_need_matching_numbers_in_evidence():
    facts = read("Contado USD 12.000. Distribución a los 90.000 km.", cash_price=9_000,
                 price_currency="USD", mileage_km=90_000, evidence=[
                     {"field": "cash_price", "quote": "Contado USD 12.000"},
                     {"field": "price_currency", "quote": "Contado USD 12.000"},
                     {"field": "mileage_km", "quote": "Distribución a los 90.000 km"},
                 ])
    assert facts.of_kind("cash")[0].amount == 12_000
    assert facts.mileage_km is None
    rounded = read("Contado USD 12.000.", cash_price=11_999, price_currency="USD", evidence=[
        {"field": "cash_price", "quote": "Contado USD 12.000"},
        {"field": "price_currency", "quote": "Contado USD 12.000"}])
    assert rounded.of_kind("cash")[0].amount == 12_000
    assert not any(e["field"] == "cash_price" for e in rounded.evidence)


def test_an_anticipo_cannot_become_the_cash_price():
    facts = read("Anticipo USD 9.000 y cuotas.", cash_price=9_000, price_currency="USD", evidence=[
        {"field": "cash_price", "quote": "Anticipo USD 9.000 y cuotas"},
        {"field": "price_currency", "quote": "Anticipo USD 9.000 y cuotas"}])
    assert facts.of_kind("cash") == []
    assert facts.of_kind("down_payment")[0].amount == 9_000


def test_cropped_quotes_cannot_hide_negations_or_maintenance_mileage():
    facts = read("No soy único dueño. Distribución realizada a los 90.000 km.",
                 single_owner=True, mileage_km=90_000, evidence=[
                     {"field": "single_owner", "quote": "único dueño"},
                     {"field": "mileage_km", "quote": "90.000 km"}])
    assert facts.claims == {} and facts.mileage_km is None
    equipment = read("Sin techo solar. No son nuevas las cubiertas.", equipment=["techo solar"],
                     tires_condition="nuevas", evidence=[{"field": "equipment", "quote": "techo solar"},
                                                        {"field": "tires_condition", "quote": "nuevas"}])
    assert equipment.claims == {}
    price = read("Anticipo USD 9.000 y cuotas.", cash_price=9_000, price_currency="USD", evidence=[
        {"field": "cash_price", "quote": "USD 9.000"}, {"field": "price_currency", "quote": "USD 9.000"}])
    assert price.of_kind("cash") == []


def test_description_only_fills_missing_fields_and_keeps_conflicts_visible():
    original = normalize_listing(Listing(source="v6", listing_id="1", titulo="Ford Fiesta",
        url="https://example.test/1", anio=2018, km=100_000), catalog=CATALOG)
    new = normalize_listing(Listing(source="v6", listing_id="1", titulo="Ford Fiesta",
        url="https://example.test/1", descripcion="Año 2017. Km: 130.000. Caja manual."), catalog=CATALOG)
    merged, _ = merge(original, new, detail=True)
    assert merged["year"] == 2018 and merged["mileage_km"] == 100_000
    assert merged["description_facts"]["year"] == 2017
    assert merged["transmission"] == "manual"
    assert merged["attributes"]["_description_filled"] == ["transmission"]


def test_changed_description_invalidates_old_claims_even_when_new_text_has_no_facts():
    original = normalize_listing(Listing(source="v6", listing_id="1", titulo="Ford Fiesta",
        url="https://example.test/1", descripcion="Único dueño.", extra={"description_facts":
            from_llm(answer(single_owner=True, evidence=[{"field": "single_owner", "quote": "Único dueño"}]),
                parse("Único dueño."), llm_at="2026-10-05T00:00:00Z", title="Ford Fiesta",
                description="Único dueño.").to_json()}), catalog=CATALOG)
    new = normalize_listing(Listing(source="v6", listing_id="1", titulo="Ford Fiesta",
        url="https://example.test/1", descripcion="Impecable."), catalog=CATALOG)
    result, changes = merge(original, new, detail=True)
    assert result["description_facts"] is None
    assert "description" in changes


def test_questions_use_negative_answers_instead_of_asking_again():
    description = "Sin historial de mantenimiento. Distribución pendiente. Sin choques."
    facts = read(description, service_history=False, timing_belt_changed=False, damage_mentioned=False,
                 evidence=[{"field": "service_history", "quote": "Sin historial de mantenimiento"},
                           {"field": "timing_belt_changed", "quote": "Distribución pendiente"},
                           {"field": "damage_mentioned", "quote": "Sin choques"}])
    listing = {"description": description, "description_facts": facts.to_json(), "year": 2017}
    now = datetime.now(timezone.utc)
    flags = red_flags(listing, diff_pct=None, guard=None, timing_belt=True, cfg=IntelligenceConfig(), now=now)
    questions = seller_questions(listing, flags, timing_belt=True, now=now)
    assert "distribución pendiente" in questions and "Si no tenés historial" in questions
    assert "¿Tenés historial de services?" not in questions
    assert "¿Tuvo choques" not in questions


def test_non_ambiguous_description_is_analyzed_and_failure_keeps_rules():
    async def run():
        provider = AsyncMock()
        provider.extract_listing_facts.return_value = answer(
            single_owner=True, evidence=[{"field": "single_owner", "quote": "Único dueño"}])
        item = Listing(source="v6", listing_id="1", url="https://example.test/1",
                       titulo="Ford Fiesta", descripcion="Único dueño.")
        helper = DescriptionLLM(provider, daily_cap=2)
        with patch("pipeline.enrich.repo.stored_description", AsyncMock(return_value=None)), \
             patch("pipeline.enrich.repo.reserve_description_run", AsyncMock(return_value=1)), \
             patch("pipeline.enrich.repo.finish_description_run", AsyncMock()) as finish:
            await helper.refine(1, item)
            assert item.extra["description_facts"]["claims"]["single_owner"] is True
            finish.assert_awaited_once_with(1, error=None)
            provider.extract_listing_facts.side_effect = RuntimeError("secret")
            other = Listing(source="v6", listing_id="2", url="https://example.test/2",
                            titulo="Ford Fiesta", descripcion="Contado USD 12.000.")
            await helper.refine(2, other)
            assert "description_facts" not in other.extra
            assert finish.await_args.kwargs["error"] == "RuntimeError"
    asyncio.run(run())


def test_cache_uses_title_description_and_analysis_version():
    async def run():
        provider = AsyncMock()
        provider.extract_listing_facts.return_value = answer()
        original = read("Único dueño.").to_json()
        item = Listing(source="v6", listing_id="1", url="https://example.test/1",
                       titulo="Ford Fiesta", descripcion="Único dueño.")
        helper = DescriptionLLM(provider, daily_cap=2)
        with patch("pipeline.enrich.repo.stored_description", AsyncMock(return_value={
            "description": item.descripcion, "description_facts": original})), \
             patch("pipeline.enrich.repo.reserve_description_run", AsyncMock(return_value=1)), \
             patch("pipeline.enrich.repo.finish_description_run", AsyncMock()):
            await helper.refine(1, item)
            provider.extract_listing_facts.assert_not_awaited()
            item.titulo = "Ford Fiesta Titanium"
            await helper.refine(1, item)
            provider.extract_listing_facts.assert_awaited_once()
    asyncio.run(run())
