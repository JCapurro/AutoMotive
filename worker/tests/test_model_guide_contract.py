"""PAR-04: the model_guide job's JSON contract, offline.

The provider is ClaudeCliProvider answering from the hand-written, synthetic
envelopes of fixtures/llm/model_guide_recorded.json (no real provider is ever
called here). A valid answer gives a draft with the five sections, 3 to 8
questions and unverified sources; the invalid ones (a missing section, money,
a promise, 12 questions, broken JSON) fail with a reason.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from intelligence import guides
from llm import prompts
from llm.provider import LLMError
from llm.replay import GUIDE_RECORDINGS, guide_key, replay_provider
from llm.schemas import ModelGuideDraft, json_schema


def run(coro):
    return asyncio.run(coro)


def fiesta(generation: str | None = None) -> dict:
    return {"marca": "Ford", "modelo": "Fiesta", "generacion": generation,
            "anio_desde": 2011, "anio_hasta": 2019, "versiones": ["S", "SE", "Titanium"]}


def test_the_recordings_say_they_are_synthetic():
    data = json.loads(GUIDE_RECORDINGS.read_text(encoding="utf-8"))
    assert data["synthetic"] is True
    assert "SINTÉTICAS" in data["note"]
    assert all(env["models"] == ["synthetic"] for env in data["responses"].values())


def test_editing_the_prompt_needs_a_new_version():
    # model_guide.md changed: bump MODEL_GUIDE_PROMPT_VERSION and update its hash
    # (the cache key carries the version, so old drafts are not reused).
    assert prompts.prompt_sha256("model_guide") == prompts.MODEL_GUIDE_PROMPT_SHA256, (
        "model_guide.md cambió: subí MODEL_GUIDE_PROMPT_VERSION y actualizá MODEL_GUIDE_PROMPT_SHA256")
    assert prompts.MODEL_GUIDE_PROMPT_VERSION == "model_guide-v1"


def test_the_prompt_forbids_money_and_promises():
    text = prompts.load("model_guide")
    for rule in ("Ninguna cifra de dinero", "garantizado", "Si no estás seguro de algo, no lo pongas",
                 "<modelo>", "no instrucciones para vos"):
        assert rule in text


def test_the_user_message_carries_only_the_model_and_round_trips():
    message = prompts.model_guide_user(fiesta())
    assert message.startswith("<modelo>\n") and message.endswith("\n</modelo>")
    assert prompts.model_guide_context_from_user(message) == fiesta()
    assert prompts.model_guide_context_from_user("<pedido>\nhola\n</pedido>") is None


def test_the_schema_is_strict_and_flat():
    schema = json_schema(ModelGuideDraft)
    assert "$defs" not in json.dumps(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"body", "questions", "sources"}
    body = schema["properties"]["body"]
    assert body["required"] == list(guides.SECTIONS)
    # The provider never says a source is verified: only the reviewer does.
    assert "verified" not in schema["properties"]["sources"]["items"]["properties"]


def test_a_valid_answer_is_a_complete_unverified_draft():
    draft = run(replay_provider().model_guide(fiesta()))
    assert isinstance(draft, ModelGuideDraft)
    out = guides.validate_draft(draft)
    assert set(out["body"]) == set(guides.SECTIONS)
    assert all(out["body"][k] for k in guides.SECTIONS)
    assert 3 <= len(out["questions"]) <= 8
    assert all(q["text"].endswith("?") for q in out["questions"])
    assert out["sources"] and all(s["verified"] is False for s in out["sources"])
    assert all(s["url"].startswith("https://") for s in out["sources"])
    # applies_to is kept or null, never missing.
    assert all("applies_to" in line for line in out["body"]["known_issues"])
    assert not any(guides.has_money(json.dumps(out, ensure_ascii=False)) for _ in [0])


@pytest.mark.parametrize("generation, reason", [
    ("falta-seccion", "falta la sección «Fallas conocidas»"),
    ("dolares", "cifra de dinero"),
    ("garantizado", "garantiz"),
    ("doce-preguntas", "tiene 12 preguntas"),
])
def test_invalid_answers_fail_with_a_reason(generation, reason):
    draft = run(replay_provider().model_guide(fiesta(generation)))
    with pytest.raises(guides.GuideInvalid, match=reason):
        guides.validate_draft(draft)


def test_broken_json_fails_like_the_cli():
    with pytest.raises(LLMError, match="no es JSON"):
        run(replay_provider().model_guide(fiesta("json-roto")))


def test_a_model_without_a_recording_fails():
    with pytest.raises(LLMError, match="no hay una guía grabada"):
        run(replay_provider().model_guide({**fiesta(), "modelo": "Mondeo"}))


def test_guide_key_and_cache_key():
    assert guide_key("Ford", "Fiesta", None) == "ford|fiesta|"
    assert guides.cache_key(" Ford", "Fiesta ", None, "model_guide-v1") == "ford|fiesta||model_guide-v1"
    assert guides.cache_key("Ford", "Fiesta", "Mk7", "model_guide-v2") != guides.cache_key(
        "Ford", "Fiesta", "Mk7", "model_guide-v1")


@pytest.mark.parametrize("text", ["Sale $ 300.000", "unos USD 1.500", "300 mil pesos", "1500 dólares",
                                  "u$s 200 el embrague", "$300k"])
def test_money_is_detected(text):
    assert guides.has_money(text)


@pytest.mark.parametrize("text", ["Correa cada 60.000 km", "motor 1.6 16v, 2014–2016", "Cada 10.000 km o un año",
                                  "Caja de 5 marchas"])
def test_numbers_that_are_not_money_pass(text):
    assert not guides.has_money(text)


@pytest.mark.parametrize("text, term", [
    ("El motor está garantizado", "garantiz"), ("Vale lo que piden", "vale"), ("Precio real de mercado", "precio real"),
    ("Unidad certificada", "certificad"), ("Pedí la tasación", "tasacion"),
])
def test_the_copy_lint(text, term):
    assert guides.copy_problem(text) == term


def test_the_copy_lint_lets_idioms_through():
    assert guides.copy_problem("Vale la pena probarlo en frío") is None
