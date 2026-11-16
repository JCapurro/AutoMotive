"""One `claude -p` call with a JSON schema, on Juan's subscription.

No shell: arguments go as a list and the prospects' data go on stdin. No
settings, MCP servers or slash commands; tools only where a call asks for them
(the phone lookup uses WebSearch and WebFetch, the writer and the reviewer none).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

_DROP_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT")
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class ClaudeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Call:
    system: str
    user: str
    schema: dict[str, Any]
    model: str
    effort: str = "high"
    tools: tuple[str, ...] = ()
    timeout_s: int = 900
    max_turns: int | None = None


def claude_path() -> str:
    found = os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")
    if not found:
        raise ClaudeError("no encuentro claude en el PATH (o en CLAUDE_CLI_PATH)")
    return found


def argv(call: Call, exe: str) -> list[str]:
    args = [exe, "-p", "--output-format", "json", "--model", call.model, "--effort", call.effort,
            "--json-schema", json.dumps(call.schema, ensure_ascii=False, separators=(",", ":")),
            "--system-prompt", call.system, "--no-session-persistence", "--setting-sources", "",
            "--strict-mcp-config", "--disable-slash-commands", "--tools", ",".join(call.tools)]
    if call.tools:
        args += ["--permission-mode", "dontAsk", "--allowedTools", *call.tools]
    if call.max_turns:
        args += ["--max-turns", str(call.max_turns)]
    return args


def parse(stdout: str) -> dict[str, Any]:
    try:
        envelope = json.loads(stdout)
    except ValueError as error:
        raise ClaudeError(f"claude no devolvió JSON: {stdout[-300:]!r}") from error
    if isinstance(envelope, list):          # stream form: the last result event
        envelope = next((e for e in reversed(envelope) if isinstance(e, dict) and e.get("type") == "result"), {})
    if envelope.get("is_error"):
        raise ClaudeError(f"claude falló: {str(envelope.get('result'))[:300]}")
    out = envelope.get("structured_output")
    if out is None and isinstance(envelope.get("result"), str):
        try:
            out = json.loads(envelope["result"])
        except ValueError:
            out = None
    if not isinstance(out, dict):
        raise ClaudeError("claude no devolvió la salida estructurada")
    return out


def run(call: Call, *, runner=subprocess.run, retries: int = 1) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if k not in _DROP_ENV}
    exe = claude_path()
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            done = runner(argv(call, exe), input=call.user, capture_output=True, encoding="utf-8",
                          errors="replace", timeout=call.timeout_s, env=env, creationflags=_NO_WINDOW)
            if done.returncode != 0 and not done.stdout:
                raise ClaudeError(f"claude salió con {done.returncode}: {(done.stderr or '')[-300:]}")
            return parse(done.stdout)
        except subprocess.TimeoutExpired as error:
            raise ClaudeError(f"claude tardó más de {call.timeout_s} s") from error
        except ClaudeError as error:
            last = error
            time.sleep(5 * (attempt + 1))
    raise last or ClaudeError("claude falló")
