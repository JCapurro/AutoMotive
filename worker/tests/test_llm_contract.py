"""Contract of every LLMProvider (sección 8.3): the 20 golden phrases
(fixtures/llm/parse_search_golden.json) produce valid drafts that, normalized
against the seed catalog, carry the filters the phrase asks for.

By default the provider is ClaudeCliProvider answering from recorded
`claude -p` envelopes (fixtures/llm/parse_search_recorded.json, made with
`python -m tools.record_llm`). With LLM_SMOKE=1 the same contract runs
against the real provider of LLM_PROVIDER (claude_cli: Claude Code installed
and logged in; anthropic: ANTHROPIC_API_KEY), which is the smoke test:

    LLM_SMOKE=1 pytest worker/tests/test_llm_contract.py -k smoke
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import time

import pytest

from llm import build_provider
from llm.provider import LLMProvider
from llm.replay import FIXTURES, load_recordings, replay_provider
from llm.schemas import SearchDraft
from normalization.drafts import normalize_drafts
from seed_catalog import seed_catalog

GOLDEN = json.loads((FIXTURES / "parse_search_golden.json").read_text(encoding="utf-8"))
SMOKE = os.getenv("LLM_SMOKE", "").strip().lower() in {"1", "true", "yes"}
# The recordings were made in 2026; relative years ("de hasta 5 años") use this.
TODAY = dt.date(2026, 9, 28)


def check_contract(case: dict, drafts: list[SearchDraft]) -> None:
    assert all(isinstance(d, SearchDraft) for d in drafts)
    output = normalize_drafts(seed_catalog(), drafts, today=TODAY)
    got = output["drafts"]
    expected = case["drafts"]
    assert len(got) == len(expected), f"{case['id']}: {len(got)} drafts, expected {len(expected)}: {got}"

    pending = list(got)
    for want in expected:
        want = dict(want)
        resolved = want.pop("resolved", True)
        if resolved:
            match = next((d for d in pending if d["resolved"]
                          and (d["values"]["make"], d["values"]["model"]) == (want["make"], want["model"])), None)
        else:
            match = next((d for d in pending if not d["resolved"]), None)
        assert match, f"{case['id']}: no draft for {want} in {got}"
        pending.remove(match)
        values = match["values"]
        contains = want.pop("location_contains", None)
        if contains:
            assert contains in values["location"].lower(), f"{case['id']}: location {values['location']!r}"
        for key, value in want.items():
            assert values[key] == value, f"{case['id']}: {key} = {values[key]!r}, expected {value!r} ({values})"
        # Editable in the form: the make/model the catalog knows, or blank for the user to pick.
        assert values["model"] == "" or resolved


def test_there_are_21_golden_phrases():
    assert len(GOLDEN) == 21
    assert len({c["id"] for c in GOLDEN}) == 21


def test_every_golden_phrase_has_a_recording():
    recorded = load_recordings()
    assert [c["id"] for c in GOLDEN if c["text"] not in recorded] == []


@pytest.fixture(scope="module")
def recorded() -> LLMProvider:
    return replay_provider()


@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_recorded(case: dict, recorded: LLMProvider):
    drafts = asyncio.run(recorded.parse_search(case["text"], seed_catalog()))
    check_contract(case, drafts)


@pytest.mark.skipif(not SMOKE, reason="LLM_SMOKE=1 runs the real provider of LLM_PROVIDER")
@pytest.mark.parametrize("case", GOLDEN, ids=[c["id"] for c in GOLDEN])
def test_smoke(case: dict):
    """The real provider, end to end. Slow (~10 s per phrase) and uses the
    Claude Code subscription of this host. Prints the latency of each phrase."""
    from aio import run

    provider = build_provider()
    started = time.monotonic()
    drafts = run(provider.parse_search(case["text"], seed_catalog()))
    print(f"{case['id']}: {(time.monotonic() - started) * 1000:.0f} ms")
    check_contract(case, drafts)


# Texts whose normalized drafts are stored in fixtures/llm/parse_search_output.json:
# the web parses that file with its own schema (web/lib/assisted.test.ts), so
# the two sides of llm_jobs.output can't drift apart silently.
WEB_EXAMPLE_TEXTS = [
    "Fiesta Titanium o Polo Highline, 2017 en adelante, hasta 12 mil dólares",
    "Tesla Model 3 2021",
    "Solo Highline: Vento 2.0 TSI 2015 a 2017, en Córdoba a 50 km",
]


def test_web_example_output_is_current(recorded: LLMProvider):
    drafts = []
    for text in WEB_EXAMPLE_TEXTS:
        drafts += normalize_drafts(seed_catalog(), asyncio.run(recorded.parse_search(text, seed_catalog())),
                                   today=TODAY)["drafts"]
    stored = json.loads((FIXTURES / "parse_search_output.json").read_text(encoding="utf-8"))
    assert stored == {"drafts": drafts}, "regenerate fixtures/llm/parse_search_output.json"
