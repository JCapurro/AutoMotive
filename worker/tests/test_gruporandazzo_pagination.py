"""Recover inconsistent VTEX pages without publishing partial inventory."""
import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from collectors.gruporandazzo import GrupoRandazzoScraper as Randazzo
from test_agency_sources import randazzo_api_record, randazzo_api_transport


@pytest.mark.parametrize('failure', ['total', 'overlap', 'short', 'range'])
def test_inconsistent_inventory_restarts_from_zero_with_fresh_cache_key(failure):
    calls = []
    attempt = 0

    def handler(request, offset, end):
        nonlocal attempt
        if offset == 0:
            attempt += 1
        calls.append((offset, parse_qs(request.url.query.decode())))
        if attempt == 1:
            ids, total = (['1', '2'], 3) if offset == 0 else (['3'], 3)
            if offset:
                if failure == 'total':
                    ids, total = ['3', '4'], 4
                elif failure == 'overlap':
                    ids = ['1']
                elif failure == 'short':
                    ids = []
            interval = f'{offset}-{end}/{total}'
            if offset and failure == 'range':
                interval = '0-1/3'
        else:
            ids, total = (['10', '11'], 3) if offset == 0 else (['12'], 3)
            interval = f'{offset}-{end}/{total}'
        return httpx.Response(206, json=[randazzo_api_record(i) for i in ids],
                              headers={'resources': interval})

    collector = Randazzo(transport=randazzo_api_transport(handler))
    collector.PAGE_SIZE = 2
    collector.PAGE_DELAY = collector.SCAN_RETRY_DELAY = 0
    items = asyncio.run(collector.search({}))
    assert [item.listing_id for item in items] == ['FAKE10_UNIT', 'FAKE11_UNIT', 'FAKE12_UNIT']
    assert [offset for offset, _ in calls] == [0, 2, 0, 2]
    keys = [query['_eseauto_scan'][0] for _, query in calls]
    assert keys[0] == keys[1]
    assert keys[2] == keys[3]
    assert keys[0] != keys[2]


def test_persistent_inventory_changes_exhaust_bounded_retries_without_partial_stock():
    offsets = []

    def handler(request, offset, end):
        offsets.append(offset)
        ids, total = (['1', '2'], 3) if offset == 0 else (['3', '4'], 4)
        return httpx.Response(206, json=[randazzo_api_record(i) for i in ids],
                              headers={'resources': f'{offset}-{end}/{total}'})

    collector = Randazzo(transport=randazzo_api_transport(handler))
    collector.PAGE_SIZE = 2
    collector.PAGE_DELAY = collector.SCAN_RETRY_DELAY = 0
    with pytest.raises(RuntimeError, match='inventory changed during pagination'):
        asyncio.run(collector.search({}))
    assert offsets == [0, 2] * 3


@pytest.mark.parametrize('failure', ['metadata', 'state', 'identity', 'http'])
def test_structural_and_http_errors_are_not_retried(failure):
    calls = []

    def handler(request, offset, end):
        calls.append(offset)
        changes = {'Estado': []} if failure == 'state' else {}
        if failure == 'identity':
            changes['productReference'] = ''
        return httpx.Response(503 if failure == 'http' else 200,
            json=[randazzo_api_record('1', **changes)],
            headers={} if failure == 'metadata' else {'resources': f'{offset}-{end}/1'})

    collector = Randazzo(transport=randazzo_api_transport(handler))
    collector.PAGE_DELAY = collector.SCAN_RETRY_DELAY = 0
    with pytest.raises(RuntimeError):
        asyncio.run(collector.search({}))
    assert calls == [0]
