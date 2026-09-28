"""Process the queued llm_jobs once and exit (the worker's loop does it continuously).

    python -m tools.llm_jobs              # with LLM_PROVIDER (claude_cli by default)
    python -m tools.llm_jobs --replay     # recorded answers (tests/fixtures/llm/), no CLI

The web e2e uses --replay to answer the assisted-mode jobs it creates.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import db
from aio import run
from llm import build_provider
from llm.replay import replay_provider
from pipeline.llm_jobs import drain


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--replay", nargs="?", const="", metavar="FILE",
                        help="answer from recorded envelopes (default: tests/fixtures/llm/parse_search_recorded.json)")
    args = parser.parse_args(argv)
    if args.replay is not None:
        provider = replay_provider(Path(args.replay) if args.replay else None)
    else:
        provider = build_provider()
    await db.open_pool()
    try:
        n = await drain(provider)
    finally:
        await db.close_pool()
    print(f"{n} job(s) procesados con {provider.name}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(run(main(sys.argv[1:])))
