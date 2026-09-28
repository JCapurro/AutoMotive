"""ClaudeCliProvider (sección 8.2): the command it runs, the subprocess
(no shell, timeout), the envelope and the retry inside one budget."""
from __future__ import annotations

import asyncio
import json
import sys

import pytest

from llm import prompts
from llm.claude_cli import ClaudeCliProvider, parse_envelope, run_cli
from llm.local import LocalProvider
from llm.provider import LLMError, LLMProvider, LLMTimeout, build_provider
from llm.schemas import SearchDrafts, json_schema
from seed_catalog import seed_catalog

FIESTA = {"make": "Ford", "model": "Fiesta", "trim": None, "trim_strict": False, "year_min": 2016,
          "year_max": 2018, "price_max": 11500, "price_target": None, "currency": "USD", "km_max": None,
          "km_target": None, "transmission": "manual", "fuel": None, "seller_type": None,
          "location": None, "radius_km": None}


def envelope(structured=None, **kw) -> str:
    env = {"type": "result", "subtype": "success", "is_error": False,
           "result": json.dumps(structured) if structured is not None else "", "structured_output": structured}
    env.update(kw)
    return json.dumps(env)


class FakeRunner:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[tuple[list[str], str, float]] = []

    async def __call__(self, argv, stdin, timeout):
        self.calls.append((argv, stdin, timeout))
        answer = self.answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, tuple):  # (seconds, answer): a slow call
            await asyncio.sleep(answer[0])
            answer = answer[1]
        return answer


def provider(runner, **kw) -> ClaudeCliProvider:
    return ClaudeCliProvider(cli_path="claude", model="haiku", timeout=kw.pop("timeout", 60), runner=runner, **kw)


# ---------------------------------------------------------------------------
# The command
# ---------------------------------------------------------------------------

def test_command_line_has_the_isolation_flags_and_no_user_text():
    runner = FakeRunner(envelope({"vehicles": [FIESTA]}))
    text = 'Busco Fiesta"; rm -rf ~ $(whoami) --tools default'
    asyncio.run(provider(runner).parse_search(text, seed_catalog()))

    [(argv, stdin, _)] = runner.calls
    assert argv[:2] == ["claude", "-p"]
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--tools") + 1] == ""
    assert "--no-session-persistence" in argv
    assert argv[argv.index("--model") + 1] == "haiku"
    assert json.loads(argv[argv.index("--json-schema") + 1]) == json_schema(SearchDrafts)
    system = argv[argv.index("--system-prompt") + 1]
    assert "Fiesta [S, SE, SEL, Titanium, ST]" in system
    # The user's text only travels on stdin, wrapped as data.
    assert all(text not in arg for arg in argv)
    assert stdin == prompts.parse_search_user(text)


def test_schema_is_self_contained_and_strict():
    schema = json_schema(SearchDrafts)
    dumped = json.dumps(schema)
    assert "$ref" not in dumped and "$defs" not in dumped
    item = schema["properties"]["vehicles"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])  # nullable, never missing


# ---------------------------------------------------------------------------
# The subprocess: a real one, with Python standing in for the CLI
# ---------------------------------------------------------------------------

def test_run_cli_passes_stdin_verbatim_without_a_shell():
    text = 'hola "; echo pwned & del * | $(id) `id` %PATH% ñandú'
    out = asyncio.run(run_cli([sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read())"],
                              text, timeout=30))
    assert out == text


def test_run_cli_kills_the_process_on_timeout():
    with pytest.raises(LLMTimeout):
        asyncio.run(run_cli([sys.executable, "-c", "import time; time.sleep(30)"], "", timeout=0.5))


def test_run_cli_reports_a_failed_process():
    with pytest.raises(LLMError, match="código 3: boom"):
        asyncio.run(run_cli([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
                            "", timeout=30))


def test_run_cli_without_the_executable():
    with pytest.raises(LLMError, match="CLAUDE_CLI_PATH"):
        asyncio.run(run_cli(["definitely-not-claude-cli"], "", timeout=5))


# ---------------------------------------------------------------------------
# The envelope
# ---------------------------------------------------------------------------

def test_envelope_prefers_structured_output():
    assert parse_envelope(envelope({"vehicles": []})) == {"vehicles": []}


def test_envelope_falls_back_to_result_even_in_a_code_fence():
    raw = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "result": '```json\n{"vehicles": []}\n```'})
    assert parse_envelope(raw) == {"vehicles": []}


@pytest.mark.parametrize("stdout, message", [
    ("not json", "no es JSON"),
    ("[1, 2]", "no es un objeto"),
    (json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True, "result": ""}), "error_max_turns"),
    (json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": "Credit balance is too low"}),
     "Credit balance"),
    (json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "Claro, acá va"}), "no es JSON"),
])
def test_envelope_errors(stdout, message):
    with pytest.raises(LLMError, match=message):
        parse_envelope(stdout)


# ---------------------------------------------------------------------------
# Validation and retry
# ---------------------------------------------------------------------------

def test_valid_answer():
    runner = FakeRunner(envelope({"vehicles": [FIESTA]}))
    [draft] = asyncio.run(provider(runner).parse_search("Fiesta"))
    assert (draft.make, draft.model, draft.transmission) == ("Ford", "Fiesta", "manual")


def test_invalid_answer_is_retried_once():
    bad = envelope({"vehicles": [{**FIESTA, "transmission": "cvt"}]})
    runner = FakeRunner(bad, envelope({"vehicles": [FIESTA]}))
    [draft] = asyncio.run(provider(runner).parse_search("Fiesta"))
    assert draft.model == "Fiesta"
    assert len(runner.calls) == 2
    # The retry gets what is left of the same budget.
    assert runner.calls[1][2] <= runner.calls[0][2]


def test_two_failures_fail_the_call():
    runner = FakeRunner(envelope({"cars": []}), "garbage")
    with pytest.raises(LLMError, match="no es JSON"):
        asyncio.run(provider(runner).parse_search("Fiesta"))
    assert len(runner.calls) == 2


def test_extra_fields_are_rejected():
    runner = FakeRunner(envelope({"vehicles": [{**FIESTA, "score": 99}]}), envelope({"vehicles": [{**FIESTA, "score": 1}]}))
    with pytest.raises(LLMError, match="esquema"):
        asyncio.run(provider(runner).parse_search("Fiesta"))


def test_too_many_vehicles_are_rejected():
    runner = FakeRunner(*[envelope({"vehicles": [FIESTA] * 6})] * 2)
    with pytest.raises(LLMError, match="esquema"):
        asyncio.run(provider(runner).parse_search("Fiesta"))


def test_a_timeout_is_not_retried():
    runner = FakeRunner(LLMTimeout("lento"), envelope({"vehicles": [FIESTA]}))
    with pytest.raises(LLMTimeout):
        asyncio.run(provider(runner).parse_search("Fiesta"))
    assert len(runner.calls) == 1


def test_no_retry_when_the_budget_is_spent():
    runner = FakeRunner((0.3, "garbage"), envelope({"vehicles": [FIESTA]}))
    with pytest.raises(LLMError):
        asyncio.run(provider(runner, timeout=5.2).parse_search("Fiesta"))
    assert len(runner.calls) == 1


# ---------------------------------------------------------------------------
# The optional tasks and the other providers
# ---------------------------------------------------------------------------

def test_optional_tasks_use_their_own_schema():
    facts = {"transmission": None, "fuel": "gnc", "single_owner": True, "service_history": None,
             "timing_belt_changed": True, "accepts_trade_in": None, "financing": False, "damage_mentioned": None}
    runner = FakeRunner(envelope(facts), envelope({"text": "¡Hola! ¿Lo seguís teniendo?"}))
    p = provider(runner)
    got = asyncio.run(p.extract_listing_facts("Gol Trend GNC", "Único dueño, distribución hecha."))
    assert got.single_owner and got.timing_belt_changed and got.fuel == "gnc"
    assert asyncio.run(p.polish_questions(["¿Lo seguís teniendo?"], {"title": "Gol Trend"})).startswith("¡Hola!")
    assert "<publicacion>" in runner.calls[0][1] and "<preguntas>" in runner.calls[1][1]


def test_providers_satisfy_the_interface():
    assert isinstance(provider(FakeRunner()), LLMProvider)
    assert isinstance(LocalProvider(base_url="http://x", model="m"), LLMProvider)


def test_local_provider_is_a_stub_that_fails_fast():
    with pytest.raises(LLMError, match="sección 8.3"):
        asyncio.run(LocalProvider(base_url="http://x", model="m").parse_search("Fiesta"))


def test_build_provider():
    assert build_provider("claude_cli").name.startswith("claude_cli:")
    assert isinstance(build_provider("local"), LocalProvider)
    with pytest.raises(ValueError):
        build_provider("gpt")
