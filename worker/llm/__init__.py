"""The LLM layer (sección 8): providers behind one interface.

    provider.py    LLMProvider, LLMError, build_provider (LLM_PROVIDER)
    claude_cli.py  `claude -p` (pilot)
    local.py       OpenAI-compatible local server (launch; stub)
    schemas.py     Pydantic models = the JSON Schema sent and the validation
    prompts/       system prompts, shared by the providers

The queue that feeds it is pipeline/llm_jobs.py; the deterministic step after
it, normalization/drafts.py.
"""
from llm.provider import LLMError, LLMProvider, LLMTimeout, build_provider
from llm.schemas import ListingFacts, SearchDraft, SearchDrafts

__all__ = ["LLMError", "LLMProvider", "LLMTimeout", "build_provider",
           "ListingFacts", "SearchDraft", "SearchDrafts"]
