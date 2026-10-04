"""OpenAI Responses API, with Luna for the assisted search parser.

Uses the existing HTTP client dependency and the same prompts/Pydantic
contracts as the other providers. One timeout covers both attempts; only
transport errors, 429 and 5xx receive one retry. No tools or stored response.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Sequence
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from llm import prompts
from llm.provider import LLMError, LLMTimeout
from llm.schemas import ListingFacts, PolishedQuestions, SearchDraft, SearchDrafts, json_schema
from normalization.vehicle import CatalogModel

log = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)
_URL = "https://api.openai.com/v1/responses"
_MAX_OUTPUT_TOKENS = 4096


class OpenAIApiProvider:
    def __init__(self, *, api_key: str, model: str = "gpt-6-luna", timeout: float = 60.0,
                 client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout
        self.client = client
        self.name = f"openai:{model}"

    async def _post(self, client: httpx.AsyncClient, body: dict) -> httpx.Response:
        for attempt in range(2):
            try:
                response = await client.post(
                    _URL, json=body, timeout=self.timeout,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            except httpx.TimeoutException:
                raise
            except httpx.RequestError:
                if attempt:
                    raise
                await asyncio.sleep(0.5)
                continue
            if not attempt and (response.status_code == 429 or response.status_code >= 500):
                try:
                    delay = max(0.0, float(response.headers.get("retry-after", "0.5")))
                except ValueError:
                    delay = 0.5
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()
            return response
        raise AssertionError("unreachable")

    async def _structured(self, system_prompt: str, user: str, out: type[M]) -> M:
        # Check on use, so preparing a blank key does not stop crawl/alerts.
        if not self.api_key:
            raise LLMError("falta OPENAI_API_KEY para LLM_PROVIDER=openai")
        body = {
            "model": self.model,
            "instructions": system_prompt,
            "input": [{"role": "user", "content": user}],
            "reasoning": {"effort": "none"},
            "max_output_tokens": _MAX_OUTPUT_TOKENS,
            "store": False,
            "text": {"format": {"type": "json_schema", "name": out.__name__,
                                "strict": True, "schema": json_schema(out)}},
        }
        try:
            async with asyncio.timeout(self.timeout):
                if self.client is None:
                    async with httpx.AsyncClient() as client:
                        response = await self._post(client, body)
                else:
                    response = await self._post(self.client, body)
        except (TimeoutError, httpx.TimeoutException):
            raise LLMTimeout(f"la API de OpenAI no respondió en {self.timeout:.0f} s") from None
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 401:
                raise LLMError("la API de OpenAI rechazó la API key (OPENAI_API_KEY)") from None
            if status == 429:
                raise LLMError("la API de OpenAI está limitando pedidos o cuota (429)") from None
            raise LLMError(f"la API de OpenAI devolvió {status}") from None
        except httpx.RequestError:
            raise LLMError("no se pudo conectar con la API de OpenAI") from None

        try:
            answer = response.json()
        except ValueError:
            raise LLMError("la API de OpenAI no devolvió JSON") from None
        if not isinstance(answer, dict):
            raise LLMError("la API de OpenAI devolvió una respuesta inválida")
        if answer.get("status") == "incomplete":
            raise LLMError("la respuesta de la API de OpenAI quedó cortada (incomplete)")
        if answer.get("status") != "completed":
            raise LLMError("la API de OpenAI no completó la respuesta")
        output = answer.get("output")
        if not isinstance(output, list):
            raise LLMError("la API de OpenAI devolvió una respuesta inválida")
        texts = []
        for item in output:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            if item.get("status", "completed") != "completed":
                raise LLMError("la respuesta de la API de OpenAI quedó cortada (incomplete)")
            content = item.get("content")
            if not isinstance(content, list):
                raise LLMError("la API de OpenAI devolvió una respuesta inválida")
            for block in content:
                if not isinstance(block, dict):
                    raise LLMError("la API de OpenAI devolvió una respuesta inválida")
                if block.get("type") == "refusal":
                    raise LLMError("la API de OpenAI no quiso responder (refusal)")
                if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                    texts.append(block["text"])
        try:
            result = out.model_validate(json.loads("".join(texts)))
        except json.JSONDecodeError:
            raise LLMError("la API de OpenAI no devolvió JSON de salida") from None
        except ValidationError as e:
            raise LLMError(f"la respuesta no cumple el esquema ({e.error_count()} errores)") from None
        usage = answer.get("usage")
        if isinstance(usage, dict):
            log.info("openai %s: %s in / %s out tokens", self.model,
                     usage.get("input_tokens"), usage.get("output_tokens"))
        return result

    async def parse_search(self, text: str,
                           catalog: Sequence[CatalogModel] = ()) -> list[SearchDraft]:
        result = await self._structured(prompts.parse_search_system(catalog),
                                        prompts.parse_search_user(text), SearchDrafts)
        return result.vehicles

    async def extract_listing_facts(self, title: str, description: str) -> ListingFacts:
        return await self._structured(prompts.load("extract_listing_facts"),
                                      prompts.listing_facts_user(title, description), ListingFacts)

    async def polish_questions(self, questions: list[str], context: dict) -> str:
        result = await self._structured(prompts.load("polish_questions"),
                                        prompts.polish_questions_user(questions, context), PolishedQuestions)
        return result.text
