from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from repairbot import state as st

WORKER = Path(st.__file__).resolve().parents[1]
INCIDENT = 'a183b3b6-ae12-4bf1-add2-c2569ad64fa2'

# Holds the lock until a line arrives, releases it, then waits for another line before exiting.
HOLDER = """
import sys
from repairbot.state import Lock
lock = Lock(sys.argv[1])
print('held' if lock.acquire() else 'busy', flush=True)
sys.stdin.readline()
lock.release()
print('released', flush=True)
sys.stdin.readline()
"""


def sample(**changes) -> st.IncidentState:
    values = dict(incident_id=INCIDENT, source='kavak', phase='deployed',
                  attempts=[st.Attempt(n=1, run_id='run-1', started_at='2026-10-13T12:00:00+00:00',
                                       outcome='fixed', root_cause='cambió el selector', commit='a' * 40)],
                  retry_after='2026-10-13T13:00:00+00:00',
                  deploy={'commit': 'a' * 40, 'prev_head': 'b' * 40, 'targets': [7, 9]})
    return st.IncidentState(**{**values, **changes})


def holder(path: Path) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, '-c', HOLDER, str(path)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True, env={**os.environ, 'PYTHONPATH': str(WORKER)})


def test_state_round_trip_keeps_attempts_and_deploy(tmp_path):
    store = st.Store(tmp_path / 'state')   # the directory is created on first write
    store.save(sample())
    loaded = store.load(INCIDENT)
    assert loaded == sample()
    assert isinstance(loaded.attempts[0], st.Attempt)
    assert [path.name for path in (tmp_path / 'state').iterdir()] == [f'{INCIDENT}.json']
    assert store.load('00000000-0000-0000-0000-000000000000') is None


def test_defaults_and_unknown_keys_from_another_version(tmp_path):
    store = st.Store(tmp_path)
    (tmp_path / f'{INCIDENT}.json').write_text(json.dumps(
        {'incident_id': INCIDENT, 'source': 'kavak', 'future_field': 1,
         'attempts': [{'n': 1, 'run_id': 'r', 'started_at': 'x', 'extra': True}]}), encoding='utf-8')
    loaded = store.load(INCIDENT)
    assert (loaded.phase, loaded.retry_after, loaded.deploy) == ('new', None, None)
    assert loaded.attempts == [st.Attempt(n=1, run_id='r', started_at='x')]


def test_failed_write_keeps_the_previous_state(tmp_path, monkeypatch):
    store = st.Store(tmp_path)
    store.save(sample())

    def broken(source, target):
        raise OSError('disco lleno')
    monkeypatch.setattr(st.os, 'replace', broken)
    with pytest.raises(OSError):
        store.save(sample(phase='done'))
    monkeypatch.undo()
    assert store.load(INCIDENT).phase == 'deployed'
    assert [path.name for path in tmp_path.iterdir()] == [f'{INCIDENT}.json']


def test_save_waits_for_a_reader_that_blocks_the_swap(tmp_path, monkeypatch):
    store = st.Store(tmp_path)
    store.save(sample())
    real, failures = os.replace, [PermissionError(13, 'en uso'), PermissionError(13, 'en uso')]

    def flaky(source, target):
        if failures:
            raise failures.pop()
        real(source, target)
    monkeypatch.setattr(st.os, 'replace', flaky)
    monkeypatch.setattr(st.time, 'sleep', lambda seconds: None)
    store.save(sample(phase='waiting'))
    assert store.load(INCIDENT).phase == 'waiting'
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('content', [
    b'{"incident_id": "a183b3b6-ae12-4bf1-add2-c2569ad6',                        # cut short
    b'\xff\xfe not utf-8',
    b'[]',
    json.dumps({'incident_id': INCIDENT}).encode(),                                # no source
    json.dumps({'incident_id': INCIDENT, 'source': 'kavak', 'phase': 'exploded'}).encode(),
    json.dumps({'incident_id': INCIDENT, 'source': 'kavak', 'attempts': 'x'}).encode(),
    json.dumps({'incident_id': INCIDENT, 'source': 'kavak', 'attempts': [{'n': 1}]}).encode(),
    json.dumps({'incident_id': 'otro-incidente', 'source': 'kavak'}).encode(),
])
def test_corrupt_file_is_set_aside(tmp_path, content):
    store = st.Store(tmp_path)
    path = tmp_path / f'{INCIDENT}.json'
    path.write_bytes(content)
    assert store.load(INCIDENT) is None
    assert not path.exists()
    assert (tmp_path / f'{INCIDENT}.json.bad').read_bytes() == content
    assert store.all_open() == []
    store.save(sample())   # the incident can be adopted again
    assert store.load(INCIDENT) == sample()


def test_incident_id_cannot_escape_the_state_directory(tmp_path):
    store = st.Store(tmp_path / 'state')
    for bad in ('../config', 'a/b', 'C:\\x', '', 'x' * 65, 'a.b'):
        with pytest.raises(ValueError):
            store.load(bad)
        with pytest.raises(ValueError):
            store.save(sample(incident_id=bad))


def test_all_open_skips_done_and_foreign_files(tmp_path):
    store = st.Store(tmp_path)
    assert st.Store(tmp_path / 'missing').all_open() == []
    for incident, phase in (('inc-1', 'waiting'), ('inc-2', 'done'), ('inc-3', 'needs_input'), ('inc-0', 'new')):
        store.save(sample(incident_id=incident, phase=phase))
    store.event('tick')
    (tmp_path / 'bot.lock').write_bytes(b'0')
    (tmp_path / 'not an incident.json').write_text('{}', encoding='utf-8')
    assert [(item.incident_id, item.phase) for item in store.all_open()] == [
        ('inc-0', 'new'), ('inc-1', 'waiting'), ('inc-3', 'needs_input')]
    assert (tmp_path / 'not an incident.json').exists()


def test_events_are_appended_as_utc_json_lines(tmp_path):
    clock = [datetime(2026, 10, 13, 15, 4, 5, tzinfo=timezone(timedelta(hours=-3)))]
    store = st.Store(tmp_path, clock=lambda: clock[0])
    store.event('claude_run', incident=INCIDENT, run_id='run-1', path=Path('x'))
    store.event('deploy', ts='spoofed', note='año')   # the store's clock wins
    lines = (tmp_path / 'events.jsonl').read_bytes().split(b'\n')
    assert lines[-1] == b'' and b'\r' not in b''.join(lines)
    first, second = (json.loads(line) for line in lines[:2])
    assert first == {'incident': INCIDENT, 'run_id': 'run-1', 'path': 'x',
                     'ts': '2026-10-13T18:04:05+00:00', 'kind': 'claude_run'}
    assert (second['kind'], second['ts'], second['note']) == ('deploy', '2026-10-13T18:04:05+00:00', 'año')


def test_sessions_today_counts_claude_runs_of_the_local_day(tmp_path):
    noon = datetime(2026, 10, 13, 12, 0).astimezone()   # local noon, whatever the machine's zone is
    clock = [noon]
    store = st.Store(tmp_path, clock=lambda: clock[0])
    assert store.sessions_today() == 0
    for moment, kind in ((noon.replace(hour=0, minute=1), 'claude_run'),
                         (noon - timedelta(days=1, hours=-11, minutes=1), 'claude_run'),   # 22:59 yesterday
                         (noon, 'claude_run'), (noon, 'deploy'),
                         (noon.replace(hour=23, minute=59), 'claude_run')):
        clock[0] = moment
        store.event(kind)
    with (tmp_path / 'events.jsonl').open('a', encoding='utf-8') as handle:
        handle.write('{"kind": "claude_run", "ts": "no es una fecha"}\n{"kind": "claude_run"}\n[1]\n{"kind": "cla')
    clock[0] = noon
    assert store.sessions_today() == 3
    clock[0] = noon + timedelta(days=1)
    assert store.sessions_today() == 0
    clock[0] = noon - timedelta(days=1)
    assert store.sessions_today() == 1


def test_timestamps_are_iso_utc():
    argentina = timezone(timedelta(hours=-3))
    assert st.now_iso(datetime(2026, 1, 2, 3, 4, 5, 999, tzinfo=argentina)) == '2026-01-02T06:04:05+00:00'
    assert st.now_iso().endswith('+00:00')
    assert st.parse_ts('2026-01-02T06:04:05') == datetime(2026, 1, 2, 6, 4, 5, tzinfo=timezone.utc)
    assert st.parse_ts(st.now_iso()).tzinfo is not None


def test_lock_is_exclusive_and_reusable(tmp_path):
    path = tmp_path / 'state' / 'bot.lock'   # parent directory does not exist yet
    first, second = st.Lock(path), st.Lock(path)
    assert first.acquire() and first.acquired
    assert first.acquire()                    # idempotent for the holder
    assert not second.acquire() and not second.acquired
    first.release()
    first.release()
    assert second.acquire()
    second.release()


def test_lock_as_context_manager_reports_instead_of_raising(tmp_path):
    path = tmp_path / 'bot.lock'
    with st.Lock(path) as held:
        assert held.acquired and held
        with st.Lock(path) as other:
            assert not other.acquired and not other   # `with Lock(p) as ok: if not ok:` reads right
        assert held.acquired               # the loser's exit must not free the winner's lock
        assert not st.Lock(path).acquire()
    assert not held.acquired and not held
    with st.Lock(path) as again:
        assert again.acquired


def test_second_lock_fails_while_another_process_holds_it(tmp_path):
    path = tmp_path / 'bot.lock'
    process = holder(path)
    try:
        assert process.stdout.readline().strip() == 'held'
        assert not st.Lock(path).acquire()
        process.stdin.write('\n')
        process.stdin.flush()
        assert process.stdout.readline().strip() == 'released'
        lock = st.Lock(path)
        assert lock.acquire()              # the other process is still alive: it released, not died
        other = holder(path)
        try:
            assert other.stdout.readline().strip() == 'busy'
        finally:
            other.kill()
            other.wait(timeout=10)
        lock.release()
    finally:
        process.kill()
        process.wait(timeout=10)


def test_lock_of_a_killed_process_is_released_by_the_os(tmp_path):
    path = tmp_path / 'bot.lock'
    process = holder(path)
    try:
        assert process.stdout.readline().strip() == 'held'
        assert not st.Lock(path).acquire()
    finally:
        process.kill()
        process.wait(timeout=10)
    # Windows frees a dead process's locks "after a time that depends on system resources"
    # (LockFileEx): soon, not necessarily by the time wait() returns.
    lock, until = st.Lock(path), time.monotonic() + 10
    while not lock.acquire() and time.monotonic() < until:
        time.sleep(0.05)
    assert lock.acquired
    lock.release()
