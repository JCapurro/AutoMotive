"""The LLM layer's interface (sección 8.1).

The LLM only proposes; everything it returns is validated against the
schemas in llm/schemas.py and normalized deterministically before the user
sees it (§44). Providers:

    claude_cli  `claude -p` on the worker's host, for development (llm/claude_cli.py)
    anthropic   the Claude API with an API key, for the pilot's users (llm/anthropic_api.py)
    local       an OpenAI-compatible local server, for the launch (llm/local.py)

`LLM_PROVIDER` picks one (config.py).
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

import config
from llm.schemas import ListingFacts, SearchDraft
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
    raise ValueError(f"LLM_PROVIDER desconocido: {name!r} (claude_cli | anthropic | local)")
