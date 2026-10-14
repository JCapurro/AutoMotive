"""Local memory of the bot: one JSON per incident, an event log and the instance lock.

The queue in Postgres has no attempt counter or outcome, so retries, deploys awaiting
verification and the daily session cap live here (<home>/state). Timestamps are ISO-8601 UTC.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time

PHASES = ('new', 'deployed', 'waiting', 'needs_input', 'done')
UNCOUNTED = ('rate_limited',)   # attempt outcomes that do not use up the budget
EVENTS_FILE = 'events.jsonl'
_ID = re.compile(r'[A-Za-z0-9_-]{1,64}')   # incident ids become file names


def now_iso(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec='seconds')


def parse_ts(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _known(cls, raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f'{cls.__name__}: se esperaba un objeto')
    return {item.name: raw[item.name] for item in fields(cls) if item.name in raw}


@dataclass
class Attempt:
    n: int
    run_id: str
    started_at: str
    finished_at: str | None = None
    outcome: str | None = None
    root_cause: str = ''
    summary: str = ''
    commit: str | None = None
    detail: str = ''              # the launcher's reason: failed gate, rollback, deploy refusal


@dataclass
class IncidentState:
    incident_id: str
    source: str
    phase: str = 'new'            # new | deployed | waiting | needs_input | done
    attempts: list[Attempt] = field(default_factory=list)
    retry_after: str | None = None
    deploy: dict | None = None    # {commit, prev_head, deployed_at, targets: [int]}
    budget_from: int = 0          # attempts before this index predate the owner handing it back

    def counted(self) -> int:
        """Attempts that used up the budget: since the last hand-back, rate limits excluded."""
        return sum(1 for item in self.attempts[self.budget_from:] if item.outcome not in UNCOUNTED)

    @classmethod
    def from_dict(cls, raw: dict) -> IncidentState:
        values = _known(cls, raw)
        attempts = values.get('attempts', [])
        if not isinstance(attempts, list):
            raise ValueError('attempts: se esperaba una lista')
        values['attempts'] = [Attempt(**_known(Attempt, item)) for item in attempts]
        state = cls(**values)
        if not (isinstance(state.incident_id, str) and isinstance(state.source, str)
                and state.phase in PHASES and isinstance(state.deploy, (dict, type(None)))
                and type(state.budget_from) is int and state.budget_from >= 0):
            raise ValueError('estado de incidente inválido')
        return state


def _write_atomic(path: Path, text: str) -> None:
    temporary = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    with temporary.open('w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    # On Windows a reader that has the file open (--status, antivirus) blocks the swap briefly.
    for pause in (0.05, 0.2, 0.5, None):
        try:
            os.replace(temporary, path)
            return
        except OSError as error:
            if pause is None or not isinstance(error, PermissionError):
                temporary.unlink(missing_ok=True)
                raise
            time.sleep(pause)


class Store:
    def __init__(self, state_dir: Path, *, clock=None):
        self.dir = Path(state_dir)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def _path(self, incident_id) -> Path:
        name = str(incident_id)
        if not _ID.fullmatch(name):
            raise ValueError(f'id de incidente inválido: {name[:80]!r}')
        return self.dir / f'{name}.json'

    def load(self, incident_id) -> IncidentState | None:
        path = self._path(incident_id)
        try:
            state = IncidentState.from_dict(json.loads(path.read_text(encoding='utf-8')))
            if state.incident_id != str(incident_id):
                raise ValueError('el archivo pertenece a otro incidente')
            return state
        except FileNotFoundError:
            return None
        except (ValueError, TypeError):   # bad JSON, bad encoding or an unexpected shape
            # Lost state is survivable (the bot re-adopts the incident); a file that
            # breaks every tick is not. Keep it aside for inspection.
            try:
                os.replace(path, path.with_name(path.name + '.bad'))
            except OSError:
                pass
            return None

    def save(self, state: IncidentState) -> None:
        path = self._path(state.incident_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        _write_atomic(path, json.dumps(asdict(state), ensure_ascii=False, indent=2, default=str))

    def all_open(self) -> list[IncidentState]:
        """Every incident the bot still owes work to (phase other than 'done')."""
        if not self.dir.is_dir():
            return []
        states = []
        for path in sorted(self.dir.glob('*.json')):
            try:
                state = self.load(path.stem)
            except ValueError:   # a stray file whose name is not an incident id
                continue
            if state and state.phase != 'done':
                states.append(state)
        return states

    def event(self, kind: str, **data) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps({**data, 'ts': now_iso(self._clock()), 'kind': kind}, ensure_ascii=False, default=str)
        with (self.dir / EVENTS_FILE).open('a', encoding='utf-8', newline='\n') as handle:
            handle.write(line + '\n')

    def events(self) -> list[dict]:
        try:
            lines = (self.dir / EVENTS_FILE).read_text(encoding='utf-8', errors='replace').splitlines()
        except FileNotFoundError:
            return []
        events = []
        for line in lines:
            try:
                event = json.loads(line)
            except ValueError:   # a line cut short by a crash
                continue
            if isinstance(event, dict):
                events.append(event)
        return events

    def sessions_today(self) -> int:
        """Claude sessions started during the current local day (the daily cap)."""
        today = self._clock().astimezone().date()
        count = 0
        for event in self.events():
            if event.get('kind') != 'claude_run':
                continue
            try:
                count += parse_ts(event['ts']).astimezone().date() == today
            except (KeyError, TypeError, ValueError):
                continue
        return count


if sys.platform == 'win32':
    import msvcrt

    def _lock(handle) -> None:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(handle) -> None:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle, fcntl.LOCK_UN)


class Lock:
    """Non-blocking OS lock on a file; released on exit even if the process is killed.

        with Lock(path) as lock:
            if not lock.acquired: ...   # another instance is running
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def __bool__(self) -> bool:
        return self.acquired

    def acquire(self) -> bool:
        if self._handle:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        try:
            if os.fstat(handle.fileno()).st_size == 0:   # the locked byte has to exist
                handle.write(b'0')
                handle.flush()
            handle.seek(0)
            _lock(handle)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle:
            try:
                _unlock(handle)
            finally:
                handle.close()

    def __enter__(self) -> Lock:
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()
