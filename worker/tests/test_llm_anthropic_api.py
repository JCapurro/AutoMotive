"""F7, punto 6: the Claude API provider (llm/anthropic_api.py) against a
mocked Messages API. Same contract as claude_cli: the 20 golden phrases, fed
the recorded answers, give the same drafts; errors become LLMError without
the user's text."""
from __future__ import annotations

import asyncio
import json

import anthropic
import httpx
import pytest

from llm.anthropic_api import AnthropicApiProvider
from llm.provider import LLMError, LLMTimeout
from llm.replay import load_recordings
from seed_catalog import seed_catalog
from test_llm_contract import GOLDEN, check_contract

RECORDED = {text: env["structured_output"] for text, env in load_recordings().items()}


def message(text: str, stop_reason: str = "end_turn") -> dict:
    return {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-4-5",
            "content": [{"type": "text", "text": text}], "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 900, "output_tokens": 120}}


def provider(handler) -> tuple[AnthropicApiProvider, list[dict]]:
    seen: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return handler(request)

    client = anthropic.AsyncAnthropic(api_key="sk-test", max_retries=0,
                                      http_client=httpx.AsyncClient(transport=httpx.MockTransport(record)))
    return AnthropicApiProvider(api_key="sk-test", client=client, timeout=5), seen


def replay(request: httpx.Request) -> httpx.Response:
    user = json.loads(request.content)["messages"][0]["content"]
    text = max((t for t in RECORDED if t in user), key=len)
    return httpx.Response(200, json=message(json.dumps(RECORDED[text], ensure_ascii=False)))


@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_golden_phrases(case: dict):
    p, seen = provider(replay)
    drafts = asyncio.run(p.parse_search(case["text"], seed_catalog()))
    check_contract(case, drafts)
    body = seen[0]
    assert body["model"] == "claude-haiku-4-5"
    assert body["output_config"]["format"]["type"] == "json_schema"   # structured outputs
    assert case["text"] in body["messages"][0]["content"]              # the text goes in the user turn
    assert case["text"] not in body["system"]                          # never in the system prompt


@pytest.mark.parametrize("status, kind, words", [
    (401, LLMError, "API key"), (429, LLMError, "429"), (500, LLMError, "500"),
])
def test_http_errors(status, kind, words):
    p, _ = provider(lambda r: httpx.Response(status, json={"type": "error", "error": {"type": "x", "message": "m"}}))
    with pytest.raises(kind, match=words) as err:
        asyncio.run(p.parse_search("Busco Fiesta secreto-del-usuario", ()))
    assert "secreto-del-usuario" not in str(err.value)


def test_timeout_is_llm_timeout():
    def slow(request):
        raise httpx.ReadTimeout("slow", request=request)
    p, _ = provider(slow)
    with pytest.raises(LLMTimeout):
        asyncio.run(p.parse_search("Busco Fiesta", ()))


@pytest.mark.parametrize("stop_reason, text, words", [
    ("refusal", "", "refusal"), ("max_tokens", '{"vehicles": [', "cortada"), ("end_turn", '{"nope": 1}', "esquema"),
])
def test_unusable_answers(stop_reason, text, words):
    p, _ = provider(lambda r: httpx.Response(200, json=message(text, stop_reason)))
    with pytest.raises(LLMError, match=words):
        asyncio.run(p.parse_search("Busco Fiesta", ()))


def test_needs_an_api_key():
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        AnthropicApiProvider(api_key="")
