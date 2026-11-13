"""The LLM layer's interface (sección 8.1).

The LLM only proposes; everything it returns is validated against the
schemas in llm/schemas.py and normalized deterministically before the user
sees it (§44). Providers:

    claude_cli  `claude -p` on the worker's host, for development (llm/claude_cli.py)
    anthropic   the Claude API with an API key, for the pilot's users (llm/anthropic_api.py)
    openai      OpenAI Responses API, Luna by default (llm/openai_api.py)
    local       an OpenAI-compatible local server, for the launch (llm/local.py)

`LLM_PROVIDER` picks one (config.py).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

import config
from llm.schemas import ListingColorAnswer, ListingFacts, LowResultsExplanation, ModelGuideDraft, SearchDraft
from normalization.vehicle import CatalogModel


class LLMError(Exception):
    """The provider could not produce a valid answer: the job fails and the
    web falls back to the structured form. The message is stored in
    llm_jobs.error, so it never carries the user's text."""


class LLMTimeout(LLMError):
    pass


@runtime_checkable
class LLMProvider(Protocol):
    # Stored in llm_jobs.provider, e.g. "claude_cli:haiku".
    name: str

    async def parse_search(self, text: str,
                           catalog: Sequence[CatalogModel] = ()) -> list[SearchDraft]:
        """Modo asistido (§12): one draft per vehicle the text asks for.
        `catalog` lets the provider show the model the names it should use."""
        ...

    async def extract_listing_facts(self, title: str, description: str) -> ListingFacts:
        """Optional: facts stated in a listing's free text (red flags, sección 6.5)."""
        ...

    async def polish_questions(self, questions: list[str], context: dict) -> str:
        """Optional: the seller questions (sección 6.6) as one friendly message."""
        ...

    async def explain_low_results(self, context: dict) -> LowResultsExplanation:
        """Optional: why a search brings few results, from its filter funnel
        (intelligence/low_results.py). The worker falls back to a fixed text."""
        ...

    async def model_guide(self, context: dict, *, timeout: float | None = None) -> ModelGuideDraft:
        """PAR-04: the draft of a model guide (llm/prompts/model_guide.md), with
        its own time budget (llm_limits.model_guide.timeout_seconds). Only a
        draft: intelligence/guides.py validates it and Juan reviews it."""
        ...

    async def listing_color(self, images: list[bytes]) -> dict[str, Any]:
        """Optional: the body color from up to 10 photos of a listing, each a
        JPEG already fitted to 512x384 (pipeline/color_vision.py,
        docs/COLOR.md). Returns {"visible": bool, "colors": [{"color", "prob"}],
        "tokens_in", "tokens_out", "model"}, the most probable color first.
        Providers that can't send images raise LLMError."""
        ...


def color_result(answer: ListingColorAnswer, tokens_in: Any, tokens_out: Any, model: str) -> dict[str, Any]:
    """The provider-neutral shape of a color answer."""
    colors = sorted(({"color": c.color, "prob": c.prob} for c in answer.colors), key=lambda c: -c["prob"])
    return {"visible": answer.visible, "colors": colors,
            "tokens_in": tokens_in if isinstance(tokens_in, int) else None,
            "tokens_out": tokens_out if isinstance(tokens_out, int) else None,
            "model": model}


def build_provider(name: str | None = None) -> LLMProvider:
    """The provider `LLM_PROVIDER` names."""
    name = (name or config.LLM_PROVIDER).strip().lower()
    if name == "claude_cli":
        from llm.claude_cli import ClaudeCliProvider
        return ClaudeCliProvider(cli_path=config.CLAUDE_CLI_PATH, model=config.CLAUDE_CLI_MODEL,
                                 timeout=config.LLM_TIMEOUT_SECONDS)
    if name == "local":
        from llm.local import LocalProvider
        return LocalProvider(base_url=config.LOCAL_LLM_BASE_URL, model=config.LOCAL_LLM_MODEL,
                             timeout=config.LLM_TIMEOUT_SECONDS)
    if name == "anthropic":
        from llm.anthropic_api import AnthropicApiProvider
        return AnthropicApiProvider(api_key=config.ANTHROPIC_API_KEY, model=config.ANTHROPIC_MODEL,
                                    timeout=config.LLM_TIMEOUT_SECONDS)
    if name == "openai":
        from llm.openai_api import OpenAIApiProvider
        return OpenAIApiProvider(api_key=config.OPENAI_API_KEY, model=config.OPENAI_MODEL,
                                timeout=config.LLM_TIMEOUT_SECONDS)
    raise ValueError(f"LLM_PROVIDER desconocido: {name!r} (openai | claude_cli | anthropic | local)")
