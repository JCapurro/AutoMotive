"""Record the golden phrases' answers from the real `claude -p` (sección 8.2).

    python -m tools.record_llm                  # every phrase in parse_search_golden.json
    python -m tools.record_llm --only fiesta-titanium kangoo-palos
    python -m tools.record_llm --text "Busco un Ka SE 2018"   # try one text, record nothing

Needs Claude Code installed and logged in on this host. The catalog comes
from supabase/seed.sql, the same one the contract tests use. The recordings
feed the contract tests (tests/test_llm_contract.py) and
`tools.llm_jobs --replay`. Re-record after changing a prompt or a schema.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time

import config
from aio import run
from llm.claude_cli import ClaudeCliProvider, run_cli
from llm.replay import FIXTURES, RECORDINGS, trim_envelope
from normalization.drafts import normalize_drafts

# The contract tests' catalog (supabase/seed.sql), so recordings and tests agree.
sys.path.insert(0, str(FIXTURES.parents[1]))
from seed_catalog import seed_catalog  # noqa: E402

GOLDEN = FIXTURES / "parse_search_golden.json"


def _cli_version() -> str:
    try:
        return subprocess.run([config.CLAUDE_CLI_PATH or "claude", "--version"], capture_output=True,
                              text=True, timeout=30).stdout.strip()
    except OSError:
        return ""


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", nargs="+", metavar="ID")
    parser.add_argument("--text")
    args = parser.parse_args(argv)
    models = seed_catalog()

    captured: dict[str, str] = {}

    async def recording_runner(cli_argv: list[str], stdin: str, timeout: float) -> str:
        out = await run_cli(cli_argv, stdin, timeout)
        captured["stdout"] = out
        return out

    provider = ClaudeCliProvider(cli_path=config.CLAUDE_CLI_PATH, model=config.CLAUDE_CLI_MODEL,
                                 timeout=config.LLM_TIMEOUT_SECONDS, runner=recording_runner)

    if args.text:
        started = time.monotonic()
        drafts = await provider.parse_search(args.text, models)
        print(json.dumps(normalize_drafts(models, drafts), ensure_ascii=False, indent=2))
        print(f"{(time.monotonic() - started) * 1000:.0f} ms", file=sys.stderr)
        return 0

    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    existing = json.loads(RECORDINGS.read_text(encoding="utf-8")) if RECORDINGS.exists() else {}
    responses: dict = dict(existing.get("responses", {})) if args.only else {}
    failures = 0
    for case in golden:
        if args.only and case["id"] not in args.only:
            continue
        captured.clear()
        started = time.monotonic()
        try:
            await provider.parse_search(case["text"], models)
        except Exception as e:  # keep the envelope anyway: the contract test reports it
            failures += 1
            print(f"x {case['id']}: {e}", file=sys.stderr)
        if "stdout" in captured:
            responses[case["text"]] = trim_envelope(captured["stdout"])
        print(f"{case['id']}: {(time.monotonic() - started) * 1000:.0f} ms", file=sys.stderr)

    RECORDINGS.write_text(json.dumps({
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "cli_version": _cli_version(),
        "model": config.CLAUDE_CLI_MODEL,
        "responses": responses,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(responses)} respuestas en {RECORDINGS}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run(main(sys.argv[1:])))
