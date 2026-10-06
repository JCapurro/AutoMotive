"""Agency catalogs share an inventory target and retain per-profile matching."""
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import collectors
import config
import db
from pipeline.crawl import derive_targets, scraper_filters
from pipeline import enrich
from pipeline.ingest import IngestResult
from tools.scraper_cli import _source_of
from pgcase import requires_db
from test_ingest_postgres import IngestCase, FakeSource, card, fake

AGENCIES = ('autocity', 'carone', 'gruporandazzo')


def test_agencies_are_registered_and_derive_one_unfiltered_target_each():
    profiles = [
        {'id': 1, 'filters': {'make': 'Ford', 'model': 'Fiesta', 'year_min': 2018}},
        {'id': 2, 'filters': {'make': 'Fiat', 'model': 'Punto', 'sources': ['carone']}},
    ]
    assert set(AGENCIES).issubset(config.SOURCES)
    assert all(collectors.REGISTRY[src].INVENTORY_TARGET for src in AGENCIES)
    targets = derive_targets(profiles, list(AGENCIES))
    assert len(targets) == 3
    for target in targets:
        assert target.make is None and target.model is None
        assert target.query == {'inventory': True,
                                'profile_ids': [1, 2] if target.source == 'carone' else [1]}
        assert scraper_filters({'make': target.make, 'model': target.model,
                                'query': target.query}) == {}


@pytest.mark.parametrize('url,expected', [
    ('https://autocity.com.ar/catalogo/usados/m-ford/m-fiesta/example/', 'autocity'),
    ('https://carone.com.ar/comprar/usados/ford-fiesta', 'carone'),
    ('https://www.gruporandazzo.com/example/p', 'gruporandazzo'),
    ('https://carone.com.ar.other.example/comprar/usados/example', None),
])
def test_agency_cli_host_inference(url, expected):
    assert _source_of(url) == expected


class AgencyTransportDomainTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_redirect_is_rejected_before_sending_any_external_request(self):
        requests = []
        def transport(request):
            requests.append(str(request.url))
            return httpx.Response(302, headers={'location': 'https://external.example/probe'})
        scraper = collectors.REGISTRY['autocity'](transport=httpx.MockTransport(transport))
        with self.assertRaises(collectors.CollectorBlocked):
            await scraper.fetch_detail_page('https://autocity.com.ar/?p=95276')
        self.assertEqual(requests, ['https://autocity.com.ar/?p=95276'])

    async def test_official_shortlink_can_follow_same_domain_redirect(self):
        requests = []
        def transport(request):
            requests.append(str(request.url))
            if request.url.query:
                return httpx.Response(301, headers={'location': '/catalogo/usados/example/'})
            return httpx.Response(200, text='<main>Own vehicle</main>')
        scraper = collectors.REGISTRY['autocity'](transport=httpx.MockTransport(transport))
        page = await scraper.fetch_detail_page('https://autocity.com.ar/?p=95276')
        self.assertEqual(page.url, 'https://autocity.com.ar/catalogo/usados/example/')
        self.assertEqual(len(requests), 2)

    async def test_graphql_redirect_does_not_send_the_query_to_another_domain(self):
        requests = []
        def transport(request):
            requests.append(str(request.url))
            return httpx.Response(307, headers={'location': 'https://external.example/probe'})
        scraper = collectors.REGISTRY['carone'](transport=httpx.MockTransport(transport))
        with self.assertRaises((collectors.CollectorBlocked, RuntimeError)):
            await scraper._catalog_page(1)
        self.assertEqual(requests, ['https://carone.com.ar/api/graphql'])


class AgencyDetailIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_different_vehicle_cannot_overwrite_the_listing_during_raw_replay(self):
        for source in AGENCIES:
            with self.subTest(source=source):
                row = {'id': 7, 'source': source, 'external_id': 'expected', 'url': 'https://example.test/old'}
                item = collectors.Listing(source=source, listing_id='actual', titulo='Other vehicle', url='https://example.test/new')
                detail = collectors.ListingDetail(item.url, listing=item)
                llm = AsyncMock()
                with patch.object(enrich, 'ingest', new_callable=AsyncMock) as ingest, \
                     patch.object(enrich, 'log_error', new_callable=AsyncMock) as errors, \
                     patch.object(enrich.repo, 'mark_detail_checked', new_callable=AsyncMock) as checked:
                    result = await enrich.ingest_detail(row, detail, stage='reprocess', seen=False, llm=llm)
                ingest.assert_not_awaited()
                llm.refine.assert_not_awaited()
                errors.assert_awaited_once()
                checked.assert_awaited_once_with([7])
                self.assertEqual(result.found, 0)
                self.assertEqual(item.listing_id, 'actual')

    async def test_matching_identity_uses_stored_url_without_losing_detail_data(self):
        for source in AGENCIES:
            with self.subTest(source=source):
                row = {'id': 7, 'source': source, 'external_id': 'same', 'url': 'https://example.test/stable'}
                item = collectors.Listing(source=source, listing_id='same', titulo='Own vehicle',
                                          url='https://example.test/canonical', precio=20000000, moneda='ARS')
                detail = collectors.ListingDetail(item.url, listing=item)
                expected = IngestResult(found=1)
                with patch.object(enrich, 'ingest', new_callable=AsyncMock, return_value=expected) as ingest, \
                     patch.object(enrich, 'log_error', new_callable=AsyncMock) as errors:
                    result = await enrich.ingest_detail(row, detail, stage='reprocess', seen=False)
                self.assertIs(result, expected)
                errors.assert_not_awaited()
                ingest.assert_awaited_once()
                self.assertEqual((item.url, item.precio), (row['url'], 20000000))


@pytest.mark.db
@requires_db
class AgencyDatabaseTests(IngestCase):
    SOURCES = AGENCIES

    async def asyncSetUp(self):
        await super().asyncSetUp()
        registry = {src: fake(src) for src in AGENCIES}
        for collector in registry.values():
            collector.INVENTORY_TARGET = True
            collector.STRICT_DETAIL_ID = True
        patched = patch.dict(collectors.REGISTRY, registry, clear=True)
        patched.start()
        self.addCleanup(patched.stop)

    async def test_agency_inventory_matches_models_and_profile_source_selection(self):
        fiesta = await self.fiesta_alert(sources=['autocity', 'carone'])
        [punto] = await db.create_alert(user_id=10001, chat_id=10001, name='Punto',
            filters={'marcas': ['Fiat'], 'modelos': ['Punto'], 'sources': ['carone']})
        FakeSource.results['autocity'] = [card('auto-ford', source='autocity', marca='Ford', modelo='Fiesta')]
        FakeSource.results['carone'] = [
            card('carone-ford', source='carone', marca='Ford', modelo='Fiesta'),
            card('carone-fiat', source='carone', titulo='Fiat Punto Attractive', marca='Fiat', modelo='Punto'),
        ]
        await self.tick()
        targets = await self.rows('SELECT source, make, model, query FROM crawl_targets WHERE active ORDER BY source')
        assert [(r['source'], r['make'], r['model']) for r in targets] == [
            ('autocity', None, None), ('carone', None, None)]
        assert all(r['query']['inventory'] for r in targets)
        assert sorted(FakeSource.searches) == [('autocity', {}), ('carone', {})]
        matches = await self.rows('SELECT m.search_profile_id, l.external_id FROM matches m '
                                 'JOIN listings l ON l.id=m.listing_id')
        assert {(r['search_profile_id'], r['external_id']) for r in matches} == {
            (fiesta, 'auto-ford'), (fiesta, 'carone-ford'), (punto, 'carone-fiat')}

    async def test_refresh_cannot_persist_another_vehicle_on_the_stored_identity(self):
        original = card('expected', source='autocity', marca='Ford', modelo='Fiesta')
        await enrich.ingest([original], geocode=None)
        row = await self.listing('expected')
        FakeSource.details[row['url']] = collectors.ListingDetail(row['url'], listing=card(
            'actual', source='autocity', titulo='Fiat Punto Another vehicle',
            marca='Fiat', modelo='Punto', precio=5000))
        result = await enrich.refresh_listing(row, stage='watchlist')
        current = await self.listing('expected')
        assert (current['title'], current['price'], current['status']) == (
            row['title'], row['price'], 'active')
        assert result.updated == 0 and not result.events
        assert len(await self.rows('SELECT id FROM listings')) == 1
        assert len(await self.rows("SELECT id FROM pipeline_errors WHERE stage='watchlist'")) == 1

    async def test_agency_migration_is_idempotent_and_preserves_tuning(self):
        path = next((Path(__file__).resolve().parents[2] / 'supabase' / 'migrations').glob('*_agency_sources.sql'))
        sql = path.read_text(encoding='utf-8')
        async with db.connection() as cx:
            await cx.execute('SAVEPOINT agency_sources_test')
            try:
                await cx.execute('DELETE FROM sources WHERE id = ANY(%s)', (list(AGENCIES),))
                await cx.execute(sql)
                rows = await (await cx.execute('SELECT id, enabled FROM sources WHERE id = ANY(%s)',
                                              (list(AGENCIES),))).fetchall()
                assert len(rows) == 3 and all(r['enabled'] for r in rows)
                await cx.execute("UPDATE sources SET enabled=false, crawl_interval_seconds=9876 WHERE id='carone'")
                await cx.execute(sql)
                row = await (await cx.execute("SELECT enabled, crawl_interval_seconds FROM sources WHERE id='carone'")).fetchone()
                assert (row['enabled'], row['crawl_interval_seconds']) == (False, 9876)
            finally:
                await cx.execute('ROLLBACK TO SAVEPOINT agency_sources_test')
