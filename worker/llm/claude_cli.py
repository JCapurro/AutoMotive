"""`claude -p` as the pilot's LLM (sección 8.2).

    claude -p --output-format json --json-schema <schema> --system-prompt <prompt>
           --tools "" --no-session-persistence --model haiku  < user message

* The process is started with `asyncio.create_subprocess_exec`: no shell, the
  arguments go as a list. The user's text goes on stdin inside the user
  message, so it can never be read as a flag or reach a command line.
* No tools, no session saved, no MCP servers or settings files: the model can
  only answer with the schema's JSON.
* One budget per call (`LLM_TIMEOUT_SECONDS`) with one retry inside it: a
  fast failure (bad JSON, a transient error) is retried with the time left;
  a timeout is not.
* The answer is the envelope's `structured_output` (or its `result`, parsed),
  validated with the same Pydantic model whose schema was sent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from collectors._loop import run_collector
from llm import prompts
from llm.provider import LLMError, LLMTimeout
from llm.schemas import ListingFacts, PolishedQuestions, SearchDraft, SearchDrafts, json_schema
from normalization.vehicle import CatalogModel

log = logging.getLogger(__name__)

M = TypeVar("M", bound=BaseModel)

# (argv, stdin text, timeout seconds) -> stdout. Swapped in tests to replay
# recorded answers (tests/fixtures/llm/).
Runner = Callable[[list[str], str, float], Awaitable[str]]

# Below this, a retry has no real chance of finishing.
_MIN_ATTEMPT_SECONDS = 5.0
_STDERR_TAIL = 300

# Environment of the parent Claude Code session (when the worker is started
# from one) that would change how the child CLI behaves.
_DROP_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")


def _child_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _DROP_ENV}


async def run_cli(argv: list[str], stdin: str, timeout: float) -> str:
    """Run the CLI once and return its stdout. Raises LLMTimeout / LLMError."""

    executable = shutil.which(argv[0])
    if not executable:
        raise LLMError(f"no se encontró el CLI de Claude Code ({argv[0]}); revisá CLAUDE_CLI_PATH")

    async def go() -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                executable, *argv[1:],
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_child_env(),
                # Away from the repo, so no project CLAUDE.md or settings apply.
                cwd=tempfile.gettempdir(),
            )
        except OSError as e:
            raise LLMError(f"no se pudo ejecutar {argv[0]}: {e.strerror or e}") from e
        try:
            out, err = await asyncio.wait_for(proc.communicate(stdin.encode("utf-8")), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise LLMTimeout(f"claude -p no respondió en {timeout:.0f} s") from None
        text = out.decode("utf-8", "replace")
        if proc.returncode != 0 and not text.strip():
            tail = err.decode("utf-8", "replace").strip()[-_STDERR_TAIL:]
            raise LLMError(f"claude -p terminó con código {proc.returncode}: {tail}")
        return text

    # Subprocesses need the proactor loop on Windows; the worker runs on a
    # selector loop (psycopg), so this goes through the collectors' loop.
    return await run_collector(go())


def parse_envelope(stdout: str) -> Any:
    """The structured answer inside `--output-format json`'s envelope."""
    try:
        envelope = json.loads(stdout)
    except json.JSONDecodeError:
        raise LLMError("la salida de claude -p no es JSON") from None
    if not isinstance(envelope, dict):
        raise LLMError("la salida de claude -p no es un objeto JSON")
    if envelope.get("is_error") or envelope.get("subtype") not in (None, "success"):
        detail = str(envelope.get("result") or envelope.get("subtype") or "error")[:_STDERR_TAIL]
        raise LLMError(f"claude -p devolvió un error: {detail}")
    if envelope.get("structured_output") is not None:
        return envelope["structured_output"]
    result = envelope.get("result")
    if not isinstance(result, str):
        raise LLMError("la respuesta de claude -p no trae resultado")
    body = result.strip()
    if body.startswith("```"):
        body = body.strip("`").removeprefix("json").strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise LLMError("el resultado de claude -p no es JSON") from None


class ClaudeCliProvider:
    def __init__(self, *, cli_path: str = "", model: str = "haiku", timeout: float = 60.0,
                 runner: Runner | None = None) -> None:
        self.cli_path = cli_path
        self.model = model
        self.timeout = timeout
        self.runner = runner or run_cli
        self.name = f"claude_cli:{model}"

    def argv(self, system_prompt: str, schema: dict[str, Any]) -> list[str]:
        return [
            self.cli_path or "claude", "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(schema, ensure_ascii=False, separators=(",", ":")),
            "--system-prompt", system_prompt,
            "--tools", "",
            "--no-session-persistence",
            "--strict-mcp-config",
            "--setting-sources", "",
            "--model", self.model,
        ]

    async def _structured(self, system_prompt: str, user: str, out: type[M]) -> M:
        argv = self.argv(system_prompt, json_schema(out))
        deadline = time.monotonic() + self.timeout
        last: LLMError | None = None
        for attempt in (1, 2):
            remaining = deadline - time.monotonic()
            if attempt > 1 and remaining < _MIN_ATTEMPT_SECONDS:
                break
            try:
                data = parse_envelope(await self.runner(argv, user, remaining))
                return out.model_validate(data)
            except LLMTimeout:
                raise
            except ValidationError as e:
                last = LLMError(f"la respuesta no cumple el esquema ({e.error_count()} errores)")
            except LLMError as e:
                last = e
            log.warning("claude -p, intento %d: %s", attempt, last)
        assert last is not None
        raise last

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
