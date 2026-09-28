"""Recorded `claude -p` answers, replayed without the CLI.

tools/record_llm.py runs the golden phrases (tests/fixtures/llm/) through the
real CLI and stores each envelope by the user's text. `ReplayRunner` answers
ClaudeCliProvider's calls from that file, so the contract tests and the web
e2e run the real prompt building, envelope parsing, validation and
normalization without Claude Code installed. A text without a recording
fails like the CLI would (LLMError), which exercises the fallback.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from llm import prompts
from llm.claude_cli import ClaudeCliProvider
from llm.provider import LLMError

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "llm"
RECORDINGS = FIXTURES / "parse_search_recorded.json"

# What a recording keeps of the CLI's envelope.
ENVELOPE_KEYS = ("type", "subtype", "is_error", "result", "structured_output", "duration_ms")


def trim_envelope(stdout: str) -> dict[str, Any]:
    envelope = json.loads(stdout)
    kept = {k: envelope[k] for k in ENVELOPE_KEYS if k in envelope}
    kept["models"] = sorted(envelope.get("modelUsage") or {})
    return kept


def load_recordings(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """{user text: trimmed envelope}."""
    data = json.loads((path or RECORDINGS).read_text(encoding="utf-8"))
    return data["responses"]


class ReplayRunner:
    def __init__(self, recordings: dict[str, dict[str, Any]]) -> None:
        self._by_message = {prompts.parse_search_user(text): json.dumps(envelope, ensure_ascii=False)
                            for text, envelope in recordings.items()}

    async def __call__(self, argv: list[str], stdin: str, timeout: float) -> str:
        try:
            return self._by_message[stdin]
        except KeyError:
            raise LLMError("no hay una respuesta grabada para este texto") from None


def replay_provider(path: Path | None = None) -> ClaudeCliProvider:
    provider = ClaudeCliProvider(model="replay", runner=ReplayRunner(load_recordings(path)))
    provider.name = "replay"
    return provider
