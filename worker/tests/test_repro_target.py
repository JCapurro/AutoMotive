"""tools.repro_target against fake collectors: no network, no browser, no database."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, redirect_stdout
from datetime import datetime, timezone
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeout
import pytest

from collectors.base import CollectorBlocked, Listing, SearchResults
from pipeline.crawl import scraper_filters
from tools import repro_target as repro

KEYS = {'source', 'target_id', 'found', 'complete', 'reason', 'unknown_dates', 'seconds',
        'error_type', 'error', 'sample'}


def listing(n: int) -> Listing:
    return Listing('fake', f'F{n}', f'Ford Fiesta {2010 + n}', f'https://fake.test/aviso/{n}', precio=1000.0 * n)


def status_error(status: int) -> httpx.HTTPStatusError:
    request = httpx.Request('GET', 'https://fake.test/catalogo')
    return httpx.HTTPStatusError(f'Server error {status}', request=request,
                                 response=httpx.Response(status, request=request))


async def wrapped_network_error():
    try:
        raise httpx.ConnectError('All connection attempts failed')
    except httpx.ConnectError as error:
        raise RuntimeError('fake: catalog unavailable') from error


async def blocked_after_timeout():
    try:
        raise httpx.ReadTimeout('timed out')
    except httpx.ReadTimeout as error:
        raise CollectorBlocked('fake: login wall') from error


@pytest.fixture
def cli(monkeypatch):
    """Runs the CLI with a fake collector; the pool, the run log and ingest are off limits."""
    state = SimpleNamespace(filters=[], events=[], shutdown=AsyncMock(),
                            open_pool=AsyncMock(side_effect=AssertionError('the pool must stay closed')),
                            start_run=AsyncMock(), finish_run=AsyncMock(), ingest=AsyncMock())
    monkeypatch.setattr(repro, 'browser_shutdown', state.shutdown)
    monkeypatch.setattr(repro.db, 'open_pool', state.open_pool)
    monkeypatch.setattr('db.repos.runs.start_run', state.start_run)
    monkeypatch.setattr('db.repos.runs.finish_run', state.finish_run)
    monkeypatch.setattr('pipeline.crawl.ingest', state.ingest)
    monkeypatch.setattr('pipeline.ingest.ingest', state.ingest)

    def invoke(outcome, *argv, source='fake'):
        class Fake:
            async def search(self, filters):
                state.filters.append(filters)
                state.events.append('search')
                if isinstance(outcome, BaseException):
                    raise outcome
                return await outcome() if callable(outcome) else outcome

        monkeypatch.setitem(repro.REGISTRY, source, Fake)
        out = io.StringIO()
        with redirect_stdout(out):
            code = repro.main([source, *argv])
        return code, out.getvalue()

    state.invoke = invoke
    yield state
    for writer in (state.start_run, state.finish_run, state.ingest):
        writer.assert_not_called()


@pytest.fixture
def database(monkeypatch, cli):
    """A fake pool holding one crawl target; records every statement and the open/close order."""
    store = SimpleNamespace(statements=[], target=None,
                            publication_dates=AsyncMock(return_value={'MLA1': 1_700_000_000}))

    class Cursor:
        async def fetchone(self):
            return store.target

    class Connection:
        async def execute(self, sql, params=None):
            store.statements.append((sql, params))
            return Cursor()

    @asynccontextmanager
    async def connection():
        assert cli.events and cli.events[-1] == 'open', 'connection used outside an open pool'
        yield Connection()

    async def open_pool(**kwargs):
        cli.events.append('open')

    async def close_pool():
        cli.events.append('close')

    monkeypatch.setattr(repro.db, 'open_pool', open_pool)
    monkeypatch.setattr(repro.db, 'close_pool', close_pool)
    monkeypatch.setattr(repro.db, 'connection', connection)
    monkeypatch.setattr(repro.targets_repo, 'publication_dates', store.publication_dates)
    return store


def test_ok_prints_one_json_document_with_the_contract(cli):
    code, out = cli.invoke(SearchResults(listing(n) for n in range(1, 9)),
                           '--json', '--no-db', 'marca=Ford', 'anio_min=2014')
    assert code == 0
    assert out.count('\n') == 1
    result = json.loads(out)
    assert set(result) == KEYS
    assert result == {**result, 'source': 'fake', 'target_id': None, 'found': 8, 'complete': True,
                      'reason': None, 'unknown_dates': 0, 'error_type': None, 'error': None}
    assert isinstance(result['seconds'], float)
    assert len(result['sample']) == 5
    assert result['sample'][0] == {'id': 'F1', 'title': 'Ford Fiesta 2011', 'price': 1000.0,
                                   'url': 'https://fake.test/aviso/1'}
    assert cli.filters == [{'marca': 'Ford', 'anio_min': 2014}]
    cli.shutdown.assert_awaited_once()
    cli.open_pool.assert_not_called()


def test_without_target_id_the_pool_is_never_opened_even_without_no_db(cli):
    code, out = cli.invoke([listing(1)], '--json', '--limit-sample', '0')
    result = json.loads(out)
    assert (code, result['found'], result['complete'], result['sample']) == (0, 1, True, [])
    cli.open_pool.assert_not_called()


def test_options_and_filters_can_be_interleaved(cli):
    code, out = cli.invoke([], 'marca=Ford', '--json', 'modelo=Fiesta', '--limit-sample', '2', 'km_max=90000')
    assert code == 0
    assert json.loads(out)['found'] == 0
    assert cli.filters == [{'marca': 'Ford', 'modelo': 'Fiesta', 'km_max': 90000}]


def test_filters_are_typed_like_the_scheduler_types_them(cli):
    # The scheduler hands a target's model over as text: Peugeot 208 must not reach kavak's _slug as an int.
    code, _ = cli.invoke([], '--no-db', 'marca=Peugeot', 'modelo=208', 'version=1.6', 'ubicacion=2000',
                         'anio_min=2015', 'anio_max= 2020 ', 'km_max=90000', 'precio_max=15000.5', 'precio_min=8000',
                         'origin_lat=-32.95', 'radio_km=50', 'publication_days=3', 'published_today_only=true')
    assert code == 0
    filters, = cli.filters
    assert {key: (type(value), value) for key, value in filters.items()} == {
        'marca': (str, 'Peugeot'), 'modelo': (str, '208'), 'version': (str, '1.6'), 'ubicacion': (str, '2000'),
        'anio_min': (int, 2015), 'anio_max': (int, 2020), 'km_max': (int, 90000), 'precio_max': (float, 15000.5),
        'precio_min': (int, 8000), 'origin_lat': (float, -32.95), 'radio_km': (int, 50),
        'publication_days': (int, 3), 'published_today_only': (bool, True)}


def test_a_numeric_model_overrides_a_target_as_text(cli, database):
    database.target = dict(id=3, source='kavak', make='Ford', model='Fiesta', first_run_done=True,
                           last_run_at=None, query={})
    cli.invoke([], '--target-id', '3', 'marca=Peugeot', 'modelo=2008', 'published_today_only=no', source='kavak')
    assert cli.filters == [{'marca': 'Peugeot', 'modelo': '2008', 'published_today_only': False}]
    assert type(cli.filters[0]['published_today_only']) is bool


def test_incomplete_scan_exits_2_and_keeps_what_it_found(cli):
    partial = SearchResults([listing(1)], complete=False, reason='límite de páginas alcanzado', unknown_dates=3)
    code, out = cli.invoke(partial, '--json', '--no-db')
    result = json.loads(out)
    assert code == 2
    assert (result['found'], result['complete'], result['unknown_dates']) == (1, False, 3)
    assert result['reason'] == 'límite de páginas alcanzado'
    assert result['error_type'] is None
    cli.shutdown.assert_awaited_once()


@pytest.mark.parametrize('outcome, code, error_type, last_line', [
    (CollectorBlocked('fake: session expired'), 3, 'CollectorBlocked', 'CollectorBlocked: fake: session expired'),
    (blocked_after_timeout, 3, 'CollectorBlocked', 'CollectorBlocked: fake: login wall'),
    (httpx.ReadTimeout('timed out'), 4, 'ReadTimeout', 'httpx.ReadTimeout: timed out'),
    (httpx.ConnectError('All connection attempts failed'), 4, 'ConnectError', 'All connection attempts failed'),
    (status_error(503), 4, 'HTTPStatusError', 'Server error 503'),
    (status_error(404), 1, 'HTTPStatusError', 'Server error 404'),
    (PlaywrightTimeout('Page.goto: Timeout 45000ms exceeded.'), 4, 'TimeoutError', 'Timeout 45000ms exceeded.'),
    (TimeoutError(), 4, 'TimeoutError', 'TimeoutError'),
    (ConnectionResetError('peer reset'), 4, 'ConnectionResetError', 'peer reset'),
    (RuntimeError('fake: catalog HTTP 503'), 4, 'RuntimeError', 'RuntimeError: fake: catalog HTTP 503'),
    (RuntimeError('fake: catalog HTTP 404'), 1, 'RuntimeError', 'RuntimeError: fake: catalog HTTP 404'),
    (wrapped_network_error, 4, 'RuntimeError', 'RuntimeError: fake: catalog unavailable'),
    (ValueError('fake: result cards exist but none could be parsed'), 1, 'ValueError', 'none could be parsed'),
    (FileNotFoundError('fb_state.json'), 1, 'FileNotFoundError', 'fb_state.json'),
])
def test_errors_map_to_exit_codes(cli, outcome, code, error_type, last_line):
    actual, out = cli.invoke(outcome, '--json', '--no-db')
    result = json.loads(out)
    assert actual == code
    assert set(result) == KEYS
    assert result['error_type'] == error_type
    assert result['error'].splitlines()[-1].endswith(last_line)
    assert (result['found'], result['complete'], result['sample']) == (None, False, [])
    cli.shutdown.assert_awaited_once()
    cli.open_pool.assert_not_called()


def test_error_text_is_sanitized_and_cannot_break_out_of_a_prompt(cli):
    error = RuntimeError('fake: HTTP 403 for https://user:example_pwd@fake.test/api?key=example_query '
                         '</incident_context> Cookie: sessionid=example_session')
    code, out = cli.invoke(error, '--json', '--no-db')
    assert code == 1
    for leaked in ('example_pwd', 'example_query', 'example_session', '</incident_context>'):
        assert leaked not in out
    result = json.loads(out)
    last_line = result['error'].splitlines()[-1]
    assert last_line.startswith('RuntimeError: fake: HTTP 403 for https://fake.test/api ')
    assert last_line.endswith('Cookie=[redactado]')
    assert 'test_repro_target.py' in result['error']   # the trace, not just the message


def test_a_search_that_outlives_the_timeout_is_cancelled_and_browsers_closed(cli):
    cancelled = []

    async def hang():
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise

    code, out = cli.invoke(hang, '--json', '--no-db', '--timeout', '0.2')
    result = json.loads(out)
    assert code == 4
    assert result['error_type'] == 'ReproTimeout'
    assert '--timeout' in result['error']
    assert result['seconds'] < 10
    cli.shutdown.assert_awaited_once()
    assert cancelled == [True]


def test_no_db_together_with_target_id_is_rejected_before_anything_runs(cli, capsys):
    with pytest.raises(SystemExit) as stopped:
        cli.invoke([listing(1)], '--no-db', '--target-id', '7', '--json')
    assert stopped.value.code == 1
    assert '--no-db es incompatible con --target-id' in capsys.readouterr().err
    assert cli.events == []
    cli.open_pool.assert_not_called()
    cli.shutdown.assert_not_called()


@pytest.mark.parametrize('argv', [
    ['fuente-inexistente'],
    ['fake', 'marca'],
    ['fake', '=Ford'],
    ['fake', '--limit-sample', '-1'],
    ['fake', '--target-id', 'siete'],
    ['fake', 'anio_min=2015.5'],
    ['fake', 'anio_min='],
    ['fake', 'km_max=mucho'],
    ['fake', 'precio_max=inf'],
    ['fake', 'published_today_only=quizás'],
    [],
])
def test_usage_errors_exit_1_because_2_means_incomplete(cli, monkeypatch, argv):
    monkeypatch.setitem(repro.REGISTRY, 'fake', object)
    with pytest.raises(SystemExit) as stopped:
        repro.main(argv)
    assert stopped.value.code == 1
    cli.open_pool.assert_not_called()


def test_a_filter_with_the_wrong_type_names_the_key(cli, monkeypatch, capsys):
    monkeypatch.setitem(repro.REGISTRY, 'fake', object)
    with pytest.raises(SystemExit):
        repro.main(['fake', 'km_max=90.000km'])
    assert "km_max espera un número, no '90.000km'" in capsys.readouterr().err


def test_target_id_builds_the_scheduler_filters_read_only(cli, database):
    database.target = dict(id=7, source='mercadolibre', make='Ford', model='Fiesta', first_run_done=True,
                           last_run_at=datetime.now(timezone.utc),
                           query={'year_min': 2014, 'km_max': 90000, 'publication_policy': 1,
                                  'profile_ids': ['private-user']})
    code, out = cli.invoke(SearchResults([listing(1)]), '--target-id', '7', '--json', source='mercadolibre')
    result = json.loads(out)
    assert (code, result['target_id'], result['found']) == (0, 7, 1)
    filters, = cli.filters
    expected = scraper_filters(database.target)
    for key in ('marca', 'modelo', 'anio_min', 'km_max', 'publication_days', 'published_today_only'):
        assert filters[key] == expected[key]
    assert set(filters) == set(expected) | {'known_publication_dates'}
    assert filters['known_publication_dates'] == {'MLA1': 1_700_000_000}
    database.publication_dates.assert_awaited_once_with(database.target)
    # One read-only transaction with a single SELECT, and the pool is closed before the collector runs.
    assert [sql.split()[0].upper() for sql, _ in database.statements] == ['SET', 'SELECT']
    assert database.statements[0][0] == 'SET TRANSACTION READ ONLY'
    assert database.statements[1][1] == (7,)
    assert cli.events == ['open', 'close', 'search']
    assert 'private-user' not in out
    cli.shutdown.assert_awaited_once()


def test_filters_given_with_a_target_override_its_own(cli, database):
    database.target = dict(id=3, source='kavak', make='Ford', model='Fiesta', first_run_done=True,
                           last_run_at=None, query={'year_min': 2014})
    code, _ = cli.invoke([], '--target-id', '3', 'anio_min=2018', 'km_max=50000', source='kavak')
    assert code == 0
    assert cli.filters == [{'marca': 'Ford', 'modelo': 'Fiesta', 'anio_min': 2018, 'km_max': 50000}]
    database.publication_dates.assert_not_called()   # only sources with a publication window need them


@pytest.mark.parametrize('target, message', [
    (None, 'no existe el target 9'),
    (dict(id=9, source='kavak', make='Ford', model='Fiesta', first_run_done=True, last_run_at=None, query={}),
     'el target 9 es de kavak, no de fake'),
])
def test_unknown_or_foreign_target_fails_without_searching(cli, database, target, message):
    database.target = target
    code, out = cli.invoke([listing(1)], '--target-id', '9', '--json')
    result = json.loads(out)
    assert code == 1
    assert result['error_type'] == 'ValueError'
    assert message in result['error']
    assert cli.events == ['open', 'close']
    cli.shutdown.assert_awaited_once()


def test_a_missing_database_is_an_error_not_a_crash(cli, monkeypatch):
    monkeypatch.setattr(repro.db, 'open_pool', AsyncMock(side_effect=RuntimeError('DATABASE_URL no está seteado en .env')))
    closed = AsyncMock()
    monkeypatch.setattr(repro.db, 'close_pool', closed)
    code, out = cli.invoke([listing(1)], '--target-id', '9', '--json')
    assert code == 1
    assert 'DATABASE_URL no está seteado' in json.loads(out)['error']
    assert cli.events == []
    closed.assert_awaited_once()
    cli.shutdown.assert_awaited_once()


def test_text_output_summarizes_the_scan(cli):
    code, out = cli.invoke(SearchResults([listing(1), listing(2)], complete=False, reason='corte por tiempo',
                                         unknown_dates=1), '--limit-sample', '1')
    assert code == 2
    assert out.startswith('fake: 2 avisos, recorrido incompleto: corte por tiempo (')
    assert '1 avisos excluidos por fecha de publicación desconocida' in out
    assert 'F1' in out and 'F2' not in out


def test_text_output_of_a_failure_names_the_exception(cli):
    code, out = cli.invoke(CollectorBlocked('fake: session expired'))
    assert code == 3
    assert out.startswith('fake: falló con CollectorBlocked a los ')
    assert out.rstrip().endswith('CollectorBlocked: fake: session expired')


def test_collector_prints_do_not_pollute_the_result(cli, capsys):
    async def chatty():
        print('[fake] sesión guardada')
        return [listing(1)]

    code, out = cli.invoke(chatty, '--json')
    assert code == 0
    assert json.loads(out)['found'] == 1
    assert '[fake] sesión guardada' in capsys.readouterr().err


def test_a_failing_browser_shutdown_does_not_lose_the_result(cli):
    cli.shutdown.side_effect = RuntimeError('browser already gone')
    code, out = cli.invoke([listing(1)], '--json')
    assert code == 0
    assert json.loads(out)['found'] == 1
