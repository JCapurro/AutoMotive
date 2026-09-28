"""A local LLM for the launch (sección 8.3) — stub.

The plan: an OpenAI-compatible endpoint (Ollama or llama.cpp server) at
`LOCAL_LLM_BASE_URL`, with JSON mode or a grammar built from the same schemas
(llm/schemas.py: `json_schema(SearchDrafts)`), the same prompts
(llm/prompts/) and the same contract tests (tests/test_llm_contract.py).

Until then every call fails fast with LLMError, so a job that reaches it is
marked failed right away and the web falls back to the structured form.
"""
from __future__ import annotations

from collections.abc import Sequence

from llm.provider import LLMError
from llm.schemas import ListingFacts, SearchDraft
from normalization.vehicle import CatalogModel


class LocalProvider:
    def __init__(self, *, base_url: str, model: str, timeout: float = 60.0) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.name = f"local:{model or 'sin-modelo'}"

    def _unavailable(self) -> LLMError:
        return LLMError("LocalProvider todavía no está implementado (sección 8.3)")

    async def parse_search(self, text: str,
                           catalog: Sequence[CatalogModel] = ()) -> list[SearchDraft]:
        raise self._unavailable()

    async def extract_listing_facts(self, title: str, description: str) -> ListingFacts:
        raise self._unavailable()

    async def polish_questions(self, questions: list[str], context: dict) -> str:
        raise self._unavailable()
