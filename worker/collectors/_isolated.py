"""Run one collector call in a child process that can be killed.

A collector with ISOLATED = True (the logged-in browser ones: Facebook,
Instagram) has hung inside Playwright before (2026-10-21), where cancelling
the coroutine doesn't always free it. Its search() and fetch_detail_page()
run here instead: `python -m collectors._isolated` gets (class, method, args)
pickled on stdin, runs the call with its own browser, and leaves the pickled
result, or the exception it raised, in a file the parent names. Past its
timeout the child's whole process group gets SIGTERM, so Playwright's driver
closes the browser it launched, then SIGKILL.

The child logs to the inherited stderr (journald on the VPS).
"""
from __future__ import annotations

import asyncio
import logging
import os
import pickle
import signal
import sys
import tempfile
from pathlib import Path
from typing import Any

from ._loop import CollectorTimeout

log = logging.getLogger("collectors.isolated")

WORKER_DIR = Path(__file__).resolve().parent.parent
# After SIGTERM, how long the child gets to close its browser before SIGKILL.
TERMINATE_GRACE_SECONDS = 10


class IsolatedCrash(RuntimeError):
    """The child died without leaving a result (killed, out of memory...)."""


def isolated(scraper: Any) -> bool:
    """Whether this collector's calls go through a child process."""
    return getattr(type(scraper), "ISOLATED", False) is True


async def call(scraper: Any, method: str, *args: Any, timeout: float) -> Any:
    """`scraper.<method>(*args)` in a child process, killed after `timeout`
    seconds (CollectorTimeout). The child's exception is raised here as is."""
    cls = type(scraper)
    fd, out = tempfile.mkstemp(prefix="collector-", suffix=".pickle")
    os.close(fd)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "collectors._isolated", out,
            stdin=asyncio.subprocess.PIPE, cwd=WORKER_DIR,
            start_new_session=sys.platform != "win32")
        try:
            await asyncio.wait_for(proc.communicate(pickle.dumps((cls.__module__, cls.__qualname__, method, args))),
                                   timeout)
        except TimeoutError:
            await _kill(proc)
            raise CollectorTimeout(f"{cls.__name__}.{method} timed out after {timeout:g}s, process killed")
        except BaseException:
            await _kill(proc)       # cancelled (worker shutting down): never leave the browser behind
            raise
        data = Path(out).read_bytes()
        if not data:
            raise IsolatedCrash(f"{cls.__name__}.{method}: child exited {proc.returncode} without a result")
        ok, value = pickle.loads(data)
    finally:
        Path(out).unlink(missing_ok=True)
    if not ok:
        raise value
    return value


async def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None:
        return
    _signal(proc, signal.SIGTERM)
    try:
        await asyncio.wait_for(proc.wait(), TERMINATE_GRACE_SECONDS)
    except TimeoutError:
        pass
    _signal(proc, getattr(signal, "SIGKILL", signal.SIGTERM))
    try:
        await asyncio.wait_for(proc.wait(), TERMINATE_GRACE_SECONDS)
    except TimeoutError:
        log.error("collector child %s did not exit after SIGKILL", proc.pid)


def _signal(proc: asyncio.subprocess.Process, sig: int) -> None:
    """The child's whole group on POSIX (its Playwright driver too), the child on Windows."""
    try:
        if sys.platform != "win32":
            os.killpg(proc.pid, sig)
        elif sig == signal.SIGTERM:
            proc.terminate()
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError):
        pass


def _picklable(exc: BaseException) -> BaseException:
    try:
        pickle.loads(pickle.dumps(exc))
        return exc
    except Exception:
        return RuntimeError(f"{type(exc).__name__}: {exc}")


async def _child(module: str, qualname: str, method: str, args: tuple) -> Any:
    import importlib

    from ._browser import shutdown

    cls: Any = importlib.import_module(module)
    for part in qualname.split("."):
        cls = getattr(cls, part)
    try:
        return await getattr(cls(), method)(*args)
    finally:
        await shutdown()


def main(out: str) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        stream=sys.stderr)
    module, qualname, method, args = pickle.loads(sys.stdin.buffer.read())
    if sys.platform == "win32":
        # Playwright starts its driver as a subprocess: the proactor loop.
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        result: tuple[bool, Any] = (True, asyncio.run(_child(module, qualname, method, args)))
    except Exception as exc:
        result = (False, _picklable(exc))
    Path(out).write_bytes(pickle.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
