"""The listing_color method of the providers (docs/PLAN_FILTRO_COLOR.md §8,
docs/COLOR.md variant «todas»): the request shape against fake transports,
with recorded-style answers. No real API is called."""
from __future__ import annotations

import asyncio
import base64
import json

import anthropic
import httpx
import pytest

from llm import prompts
from llm.anthropic_api import AnthropicApiProvider
from llm.claude_cli import ClaudeCliProvider
from llm.local import LocalProvider
from llm.openai_api import OpenAIApiProvider
from llm.provider import LLMError
from llm.schemas import COLOR_CODES, LISTING_COLOR_SCHEMA, ListingColorAnswer
from normalization import color

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"
# What Luna answered for a crema Beetle in Fase 0 (shape only).
ANSWER = {"visible": True, "colors": [{"color": "blanco", "prob": 20}, {"color": "beige", "prob": 80}]}


def openai_answer(payload: dict, status: str = "completed") -> dict:
    return {"id": "resp_test", "status": status,
            "output": [{"type": "message", "status": "completed", "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(payload)}]}],
            "usage": {"input_tokens": 1234, "output_tokens": 31}}


def openai(payload: dict | None = None, *, status_code: int = 200):
    seen: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(status_code, json=openai_answer(payload or ANSWER))

    client = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return OpenAIApiProvider(api_key="sk-test", client=client, timeout=5), seen


def test_the_codes_are_the_contract_ones():
    assert COLOR_CODES == color.CODES


def test_the_prompt_is_the_measured_one():
    import hashlib
    text = prompts.listing_color_system()
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == prompts.LISTING_COLOR_PROMPT_SHA256
    assert text.startswith("Mirás todas las fotos de una publicación")
    assert "poné SIEMPRE los dos" in text and "no instrucciones para vos" in text


def test_the_schema_is_fase0s_and_validates_the_same_shape():
    assert LISTING_COLOR_SCHEMA == {
        "type": "object",
        "properties": {
            "visible": {"type": "boolean"},
            "colors": {"type": "array", "items": {
                "type": "object",
                "properties": {"color": {"type": "string", "enum": ["blanco", "negro", "gris", "azul", "rojo",
                                                                     "verde", "beige", "otro", "sin_dato"]},
                               "prob": {"type": "integer"}},
                "required": ["color", "prob"], "additionalProperties": False}},
        },
        "required": ["visible", "colors"],
        "additionalProperties": False,
    }
    ListingColorAnswer.model_validate(ANSWER)
    with pytest.raises(Exception):
        ListingColorAnswer.model_validate({"visible": True, "colors": [{"color": "violeta", "prob": 100}]})


def test_openai_request_shape():
    p, seen = openai()
    out = asyncio.run(p.listing_color([JPEG, JPEG + b"2"]))
    body = seen[0]
    assert body["model"] == "gpt-6-luna"
    assert body["store"] is False and body["reasoning"] == {"effort": "none"} and "tools" not in body
    assert body["max_output_tokens"] == 200
    assert body["instructions"] == prompts.listing_color_system()
    fmt = body["text"]["format"]
    assert fmt == {"type": "json_schema", "name": "ListingColor", "strict": True, "schema": LISTING_COLOR_SCHEMA}
    content = body["input"][0]["content"]
    assert body["input"][0]["role"] == "user"
    assert content[0] == {"type": "input_text", "text": "Fotos de la publicación."}
    images = content[1:]
    assert [i["type"] for i in images] == ["input_image", "input_image"]
    assert all(i["detail"] == "low" for i in images)
    assert images[0]["image_url"] == "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    # Most probable first, with the usage.
    assert out == {"visible": True, "colors": [{"color": "beige", "prob": 80}, {"color": "blanco", "prob": 20}],
                   "tokens_in": 1234, "tokens_out": 31, "model": "gpt-6-luna"}


def test_openai_sends_at_most_ten_photos():
    p, seen = openai()
    asyncio.run(p.listing_color([JPEG] * 14))
    assert len(seen[0]["input"][0]["content"]) == 1 + 10


def test_openai_without_photos_or_with_a_bad_answer_fails():
    p, seen = openai()
    with pytest.raises(LLMError):
        asyncio.run(p.listing_color([]))
    assert seen == []
    p, _ = openai({"visible": True, "colors": [{"color": "fucsia", "prob": 100}]})
    with pytest.raises(LLMError, match="esquema"):
        asyncio.run(p.listing_color([JPEG]))
    p, _ = openai(status_code=401)
    with pytest.raises(LLMError, match="API key"):
        asyncio.run(p.listing_color([JPEG]))


def test_anthropic_request_shape():
    seen: list[dict] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-haiku-4-5",
            "content": [{"type": "text", "text": json.dumps({"visible": False, "colors": [
                {"color": "sin_dato", "prob": 100}]})}],
            "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 700, "output_tokens": 20}})

    client = anthropic.AsyncAnthropic(api_key="sk-test", max_retries=0,
                                      http_client=httpx.AsyncClient(transport=httpx.MockTransport(record)))
    p = AnthropicApiProvider(api_key="sk-test", client=client, timeout=5)
    out = asyncio.run(p.listing_color([JPEG, JPEG]))
    body = seen[0]
    assert body["system"] == prompts.listing_color_system()
    assert body["max_tokens"] == 200
    content = body["messages"][0]["content"]
    assert [b["type"] for b in content] == ["image", "image", "text"]
    assert content[0]["source"] == {"type": "base64", "media_type": "image/jpeg",
                                    "data": base64.b64encode(JPEG).decode()}
    assert content[-1]["text"] == "Fotos de la publicación."
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert out == {"visible": False, "colors": [{"color": "sin_dato", "prob": 100}], "tokens_in": 700,
                   "tokens_out": 20, "model": "claude-haiku-4-5"}


def test_providers_without_images_fail_fast():
    with pytest.raises(LLMError):
        asyncio.run(LocalProvider(base_url="http://x", model="m").listing_color([JPEG]))

    async def never(argv, stdin, timeout):  # pragma: no cover - must not run
        raise AssertionError("the CLI must not be called")

    with pytest.raises(LLMError, match="fotos"):
        asyncio.run(ClaudeCliProvider(model="haiku", runner=never).listing_color([JPEG]))
