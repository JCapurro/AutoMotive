"""The Claude API with an API key (F7, punto 6): the provider for serving the
pilot's users, in place of `claude -p` on a personal subscription.

* Official SDK (`anthropic`), async client, structured outputs: the response
  is constrained (`output_config.format`, the schema run through the SDK's
  `transform_schema`) to the same Pydantic models the other providers
  validate against (llm/schemas.py). The answer is validated here, after
  checking `stop_reason`, so a refusal or a cut answer says so.
* Same prompts (llm/prompts/) and the same contract tests as claude_cli.
* One budget per call (`LLM_TIMEOUT_SECONDS`), with the SDK's one retry inside
  it for 429 / 5xx / connection errors. Errors never carry the user's text
  (they go to llm_jobs.error).

Needs ANTHROPIC_API_KEY. The model is ANTHROPIC_MODEL (Claude Haiku 4.5 by
default: the plan's choice for turning a short request into filters).
"""
from __future__ import annotations

import base64
import json
import logging
from collections.abc import Sequence
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from llm import prompts
from llm.provider import LLMError, LLMTimeout, color_result
from llm.schemas import (LISTING_COLOR_MAX_IMAGES, ListingColorAnswer, ListingFacts, LowResultsExplanation,
                         ModelGuideDraft, PolishedQuestions, SearchDraft, SearchDrafts)
from normalization.vehicle import CatalogModel

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)

# A few vehicles' drafts, a facts object or a short message: plenty of room.
_MAX_TOKENS = 4096
# PAR-04: a guide is several sections long.
_GUIDE_MAX_TOKENS = 8192
# The color answer: a handful of codes.
_COLOR_MAX_TOKENS = 200


class AnthropicApiProvider:
    def __init__(self, *, api_key: str, model: str = "claude-haiku-4-5", timeout: float = 60.0,
                 client: anthropic.AsyncAnthropic | None = None) -> None:
        if not api_key and client is None:
            raise LLMError("falta ANTHROPIC_API_KEY para LLM_PROVIDER=anthropic")
        self.model = model
        self.timeout = timeout
        self.client = client or anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=1)
        self.name = f"anthropic:{model}"

    async def _structured(self, system_prompt: str, user: str, out: type[M], *,
                          timeout: float | None = None, max_tokens: int = _MAX_TOKENS) -> M:
        result, _ = await self._structured_usage(system_prompt, user, out, timeout=timeout, max_tokens=max_tokens)
        return result

    async def _structured_usage(self, system_prompt: str, user: str | list[dict[str, Any]], out: type[M], *,
                                timeout: float | None = None, max_tokens: int = _MAX_TOKENS
                                ) -> tuple[M, tuple[int | None, int | None]]:
        """The validated answer and (input, output) tokens. `user` is a text
        or a list of content blocks (text, image)."""
        budget = timeout or self.timeout
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                timeout=budget,
                system=system_prompt,
                messages=[{"role": "user", "content": user}],
                output_config={"format": {"type": "json_schema", "schema": anthropic.transform_schema(out)}},
            )
        except anthropic.APITimeoutError:
            raise LLMTimeout(f"la API de Claude no respondió en {budget:.0f} s") from None
        except anthropic.AuthenticationError:
            raise LLMError("la API de Claude rechazó la API key (ANTHROPIC_API_KEY)") from None
        except anthropic.RateLimitError:
            raise LLMError("la API de Claude está limitando pedidos (429)") from None
        except anthropic.APIStatusError as e:
            raise LLMError(f"la API de Claude devolvió {e.status_code}") from None
        except anthropic.APIConnectionError as e:
            raise LLMError(f"no se pudo conectar con la API de Claude: {type(e).__name__}") from None

        if response.stop_reason == "refusal":
            raise LLMError("la API de Claude no quiso responder (refusal)")
        if response.stop_reason == "max_tokens":
            raise LLMError("la respuesta de la API de Claude quedó cortada (max_tokens)")
        log.info("anthropic %s: %d in / %d out tokens", self.model,
                 response.usage.input_tokens, response.usage.output_tokens)
        text = next((b.text for b in response.content if b.type == "text"), "")
        tokens = (response.usage.input_tokens, response.usage.output_tokens)
        try:
            return out.model_validate(json.loads(text)), tokens
        except json.JSONDecodeError:
            raise LLMError("la API de Claude no devolvió JSON") from None
        except ValidationError as e:
            raise LLMError(f"la respuesta no cumple el esquema ({e.error_count()} errores)") from None

    async def parse_search(self, text: str,
                           catalog: Sequence[CatalogModel] = ()) -> list[SearchDraft]:
        drafts = await self._structured(prompts.parse_search_system(catalog),
                                        prompts.parse_search_user(text), SearchDrafts)
        return drafts.vehicles

    async def extract_listing_facts(self, title: str, description: str) -> ListingFacts:
        return await self._structured(prompts.load("extract_listing_facts"),
                                      prompts.listing_facts_user(title, description), ListingFacts)

    async def polish_questions(self, questions: list[str], context: dict) -> str:
        polished = await self._structured(prompts.load("polish_questions"),
                                          prompts.polish_questions_user(questions, context),
                                          PolishedQuestions)
        return polished.text

    async def explain_low_results(self, context: dict) -> LowResultsExplanation:
        return await self._structured(prompts.load("explain_low_results"),
                                      prompts.low_results_user(context), LowResultsExplanation)

    async def model_guide(self, context: dict, *, timeout: float | None = None) -> ModelGuideDraft:
        return await self._structured(prompts.load("model_guide"), prompts.model_guide_user(context),
                                      ModelGuideDraft, timeout=timeout, max_tokens=_GUIDE_MAX_TOKENS)

    async def listing_color(self, images: list[bytes]) -> dict[str, Any]:
        """The same contract as OpenAIApiProvider.listing_color: the measured
        prompt, each photo a base64 image block before the text, and the same
        schema (as a Pydantic model, through the SDK's transform_schema)."""
        images = [i for i in images if i][:LISTING_COLOR_MAX_IMAGES]
        if not images:
            raise LLMError("no hay fotos para leer el color")
        content: list[dict[str, Any]] = [
            *({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                           "data": base64.b64encode(data).decode("ascii")}} for data in images),
            {"type": "text", "text": prompts.LISTING_COLOR_USER_TEXT},
        ]
        answer, (tokens_in, tokens_out) = await self._structured_usage(
            prompts.listing_color_system(), content, ListingColorAnswer, max_tokens=_COLOR_MAX_TOKENS)
        return color_result(answer, tokens_in, tokens_out, self.model)
