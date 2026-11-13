"""OpenAI Responses API, with Luna for the assisted search parser.

Uses the existing HTTP client dependency and the same prompts/Pydantic
contracts as the other providers. One timeout covers both attempts; only
transport errors, 429 and 5xx receive one retry. No tools or stored response.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from llm import prompts
from llm.provider import LLMError, LLMTimeout, color_result
from llm.schemas import (LISTING_COLOR_MAX_IMAGES, LISTING_COLOR_SCHEMA, ListingColorAnswer, ListingFacts,
                         LowResultsExplanation, ModelGuideDraft, PolishedQuestions, SearchDraft, SearchDrafts,
                         json_schema)
from normalization.vehicle import CatalogModel

log = logging.getLogger(__name__)
M = TypeVar("M", bound=BaseModel)
_URL = "https://api.openai.com/v1/responses"
_MAX_OUTPUT_TOKENS = 4096
# A guide is several sections long.
_GUIDE_MAX_OUTPUT_TOKENS = 8192
# The color answer is a handful of codes (docs/COLOR.md measured it with 200).
_COLOR_MAX_OUTPUT_TOKENS = 200


class OpenAIApiProvider:
    def __init__(self, *, api_key: str, model: str = "gpt-6-luna", timeout: float = 60.0,
                 client: httpx.AsyncClient | None = None) -> None:
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout
        self.client = client
        self.name = f"openai:{model}"

    async def _post(self, client: httpx.AsyncClient, body: dict, timeout: float | None = None) -> httpx.Response:
        for attempt in range(2):
            try:
                response = await client.post(
                    _URL, json=body, timeout=timeout or self.timeout,
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

    async def _structured(self, system_prompt: str, user: str, out: type[M], *,
                          timeout: float | None = None, max_output_tokens: int = _MAX_OUTPUT_TOKENS) -> M:
        result, _ = await self._structured_usage(system_prompt, user, out, timeout=timeout,
                                                 max_output_tokens=max_output_tokens)
        return result

    async def _structured_usage(self, system_prompt: str, user: str | list[dict[str, Any]], out: type[M], *,
                                timeout: float | None = None, max_output_tokens: int = _MAX_OUTPUT_TOKENS,
                                schema: dict[str, Any] | None = None, schema_name: str | None = None
                                ) -> tuple[M, dict[str, Any]]:
        """The validated answer and the usage the API reported ({} without it).
        `user` is a text or a list of content parts (input_text, input_image);
        `schema` replaces the model's own (the color pass sends the measured one)."""
        # Check on use, so preparing a blank key does not stop crawl/alerts.
        if not self.api_key:
            raise LLMError("falta OPENAI_API_KEY para LLM_PROVIDER=openai")
        body = {
            "model": self.model,
            "instructions": system_prompt,
            "input": [{"role": "user", "content": user}],
            "reasoning": {"effort": "none"},
            "max_output_tokens": max_output_tokens,
            "store": False,
            "text": {"format": {"type": "json_schema", "name": schema_name or out.__name__,
                                "strict": True, "schema": schema or json_schema(out)}},
        }
        budget = timeout or self.timeout
        try:
            async with asyncio.timeout(budget):
                if self.client is None:
                    async with httpx.AsyncClient() as client:
                        response = await self._post(client, body, budget)
                else:
                    response = await self._post(self.client, body, budget)
        except (TimeoutError, httpx.TimeoutException):
            raise LLMTimeout(f"la API de OpenAI no respondió en {budget:.0f} s") from None
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
        return result, (usage if isinstance(usage, dict) else {})

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

    async def explain_low_results(self, context: dict) -> LowResultsExplanation:
        return await self._structured(prompts.load("explain_low_results"),
                                      prompts.low_results_user(context), LowResultsExplanation)

    async def model_guide(self, context: dict, *, timeout: float | None = None) -> ModelGuideDraft:
        return await self._structured(prompts.load("model_guide"), prompts.model_guide_user(context),
                                      ModelGuideDraft, timeout=timeout, max_output_tokens=_GUIDE_MAX_OUTPUT_TOKENS)

    async def listing_color(self, images: list[bytes]) -> dict[str, Any]:
        """The body color from a listing's photos (docs/COLOR.md, variant
        «todas»): each JPEG a separate input_image at detail low, the
        measured prompt and schema. {visible, colors: [{color, prob}],
        tokens_in, tokens_out, model}, colors most probable first."""
        images = [i for i in images if i][:LISTING_COLOR_MAX_IMAGES]
        if not images:
            raise LLMError("no hay fotos para leer el color")
        content: list[dict[str, Any]] = [
            {"type": "input_text", "text": prompts.LISTING_COLOR_USER_TEXT},
            *({"type": "input_image", "detail": "low",
               "image_url": "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")} for data in images),
        ]
        answer, usage = await self._structured_usage(
            prompts.listing_color_system(), content, ListingColorAnswer,
            max_output_tokens=_COLOR_MAX_OUTPUT_TOKENS, schema=LISTING_COLOR_SCHEMA, schema_name="ListingColor")
        return color_result(answer, usage.get("input_tokens"), usage.get("output_tokens"), self.model)

