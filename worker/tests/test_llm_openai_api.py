"""Responses wire contract and failure handling, with no live API calls.

Replays existing answers to exercise the adapter and normalization, not to
claim Luna's quality on the golden phrases.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

import config
from llm.openai_api import OpenAIApiProvider
from llm.provider import LLMError, LLMProvider, LLMTimeout, build_provider
from llm.replay import load_recordings
from llm.schemas import ListingFacts, json_schema
from seed_catalog import seed_catalog
from test_llm_contract import GOLDEN, check_contract

RECORDED = {text: env["structured_output"] for text, env in load_recordings().items()}


def answer(text: str, status: str = "completed", block_type: str = "output_text") -> dict:
    return {"id": "resp_test", "status": status,
            "output": [{"type": "message", "status": "completed", "role": "assistant",
                        "content": [{"type": block_type, "text": text}]}],
            "usage": {"input_tokens": 900, "output_tokens": 120}}


def provider(handler, *, timeout=2, api_key="sk-test-private"):
    seen = []

    async def record(request):
        seen.append(json.loads(request.content))
        response = handler(request)
        return await response if hasattr(response, "__await__") else response

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return OpenAIApiProvider(api_key=api_key, client=client, timeout=timeout), seen


def replay(request):
    assert str(request.url) == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer sk-test-private"
    user = json.loads(request.content)["input"][0]["content"]
    text = max((t for t in RECORDED if t in user), key=len)
    return httpx.Response(200, json=answer(json.dumps(RECORDED[text], ensure_ascii=False)))


@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_golden_wire_contract(case):
    p, seen = provider(replay)
    drafts = asyncio.run(p.parse_search(case["text"], seed_catalog()))
    check_contract(case, drafts)
    body = seen[0]
    assert body["model"] == "gpt-6-luna"
    assert body["reasoning"] == {"effort": "none"}
    assert body["store"] is False and "tools" not in body
    assert body["max_output_tokens"] == 4096
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["type"] == "json_schema"
    assert case["text"] in body["input"][0]["content"]
    assert case["text"] not in body["instructions"]
    schema = body["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    vehicle = schema["properties"]["vehicles"]["items"]
    assert vehicle["additionalProperties"] is False
    assert set(vehicle["required"]) == set(vehicle["properties"])


@pytest.mark.parametrize("status,words,attempts", [
    (401, "API key", 1), (403, "403", 1), (400, "400", 1),
    (429, "429", 2), (500, "500", 2),
])
def test_http_errors_are_safe_and_retry_only_transient(status, words, attempts):
    p, seen = provider(lambda r: httpx.Response(status, headers={"retry-after": "0"},
                                              json={"error": "sk-test-private secreto-usuario"}))
    with pytest.raises(LLMError, match=words) as err:
        asyncio.run(p.parse_search("secreto-usuario"))
    assert "secreto-usuario" not in str(err.value)
    assert "sk-test-private" not in str(err.value)
    assert len(seen) == attempts


def test_transient_error_then_success():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, headers={"retry-after": "0"})
        return httpx.Response(200, json=answer('{"vehicles": []}'))

    p, seen = provider(handler)
    assert asyncio.run(p.parse_search("sin vehículo")) == []
    assert len(seen) == 2


def test_connection_error_is_retried_once_and_sanitized():
    def broken(request):
        raise httpx.ConnectError("sk-test-private secreto-usuario", request=request)

    p, seen = provider(broken)
    with pytest.raises(LLMError, match="conectar") as err:
        asyncio.run(p.parse_search("secreto-usuario"))
    assert len(seen) == 2
    assert "secreto-usuario" not in str(err.value)
    assert "sk-test-private" not in str(err.value)


def test_http_timeout_is_not_retried():
    def slow(request):
        raise httpx.ReadTimeout("secreto-usuario", request=request)

    p, seen = provider(slow)
    with pytest.raises(LLMTimeout):
        asyncio.run(p.parse_search("Fiesta"))
    assert len(seen) == 1


def test_total_timeout_cancels_a_pending_request():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200, json=answer('{"vehicles": []}'))

    p, seen = provider(slow, timeout=0.01)
    with pytest.raises(LLMTimeout):
        asyncio.run(p.parse_search("Fiesta"))
    assert len(seen) == 1


def test_retry_after_shares_the_total_timeout():
    p, seen = provider(lambda r: httpx.Response(429, headers={"retry-after": "120"}), timeout=0.01)
    with pytest.raises(LLMTimeout):
        asyncio.run(p.parse_search("Fiesta"))
    assert len(seen) == 1


@pytest.mark.parametrize("status,text,block_type,words", [
    ("incomplete", '{"vehicles": [', "output_text", "cortada"),
    ("failed", "", "output_text", "completó"),
    ("completed", "secreto-usuario", "refusal", "refusal"),
    ("completed", "garbage", "output_text", "JSON"),
    ("completed", '{"nope": 1}', "output_text", "esquema"),
    ("completed", '{"vehicles": [], "extra": "secreto-usuario"}', "output_text", "esquema"),
])
def test_unusable_answers(status, text, block_type, words):
    p, seen = provider(lambda r: httpx.Response(200, json=answer(text, status, block_type)))
    with pytest.raises(LLMError, match=words) as err:
        asyncio.run(p.parse_search("secreto-usuario"))
    assert "secreto-usuario" not in str(err.value)
    assert len(seen) == 1


@pytest.mark.parametrize("envelope", [[], {"status": "completed", "output": {}},
                                       {"status": "completed", "output": [{"type": "message", "content": 1}]}])
def test_malformed_envelopes_fail_safely(envelope):
    p, _ = provider(lambda r: httpx.Response(200, json=envelope))
    with pytest.raises(LLMError):
        asyncio.run(p.parse_search("Fiesta"))


def test_invalid_http_json():
    p, _ = provider(lambda r: httpx.Response(200, text="garbage"))
    with pytest.raises(LLMError, match="JSON"):
        asyncio.run(p.parse_search("Fiesta"))


def test_too_many_vehicles_are_rejected():
    vehicle = next(v for recorded in RECORDED.values() for v in recorded["vehicles"])
    p, _ = provider(lambda r: httpx.Response(200, json=answer(json.dumps({"vehicles": [vehicle] * 6}))))
    with pytest.raises(LLMError, match="esquema"):
        asyncio.run(p.parse_search("seis vehículos"))


def test_missing_key_fails_on_use_without_network():
    p, seen = provider(lambda r: pytest.fail("must not call HTTP"), api_key=" ")
    assert isinstance(p, LLMProvider)
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        asyncio.run(p.parse_search("Fiesta"))
    assert seen == []


def test_factory_uses_the_configured_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_MODEL", "gpt-6-luna")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert build_provider().name == "openai:gpt-6-luna"


def test_optional_tasks_use_their_own_schema():
    facts = dict.fromkeys(json_schema(ListingFacts)["properties"])
    facts.update(fuel="gnc", single_owner=True, mileage_km=90000, equipment=[], evidence=[])
    responses = iter([facts, {"text": "¡Hola! ¿Lo seguís teniendo?"}])
    p, seen = provider(lambda r: httpx.Response(200, json=answer(json.dumps(next(responses)))))
    result = asyncio.run(p.extract_listing_facts("Gol GNC", "Único dueño, 90 mil km"))
    assert result.fuel == "gnc" and result.single_owner and result.mileage_km == 90000
    assert asyncio.run(p.polish_questions(["¿Lo seguís teniendo?"], {})).startswith("¡Hola!")
    assert seen[0]["text"]["format"]["name"] == "ListingFacts"
    assert seen[1]["text"]["format"]["name"] == "PolishedQuestions"


def test_preflight_checks_config_without_calling_api(monkeypatch, capsys):
    from tools.check_llm import main

    monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    assert main() == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().out
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test-private")
    assert main() == 0
    output = capsys.readouterr().out
    assert "openai:gpt-6-luna" in output
    assert "sk-test-private" not in output
    assert "No se llamó" in output
