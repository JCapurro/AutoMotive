"""Inventory targets must ingest different models and match every eligible profile."""
from unittest.mock import patch
from pathlib import Path

import pytest

import collectors
import db
from db.repos import profiles, targets
from pgcase import requires_db
from test_ingest_postgres import IngestCase, FakeSource, card, fake

pytestmark = [pytest.mark.db, requires_db]


class InventoryIntegrationTests(IngestCase):
    SOURCES = ('mardelusados',)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        inventory = fake('mardelusados')
        inventory.INVENTORY_TARGET = True
        p = patch.dict(collectors.REGISTRY, {'mardelusados': inventory}, clear=True)
        p.start()
        self.addCleanup(p.stop)

    async def test_single_target_ingests_and_matches_two_different_vehicle_profiles(self):
        fiesta = await self.fiesta_alert(sources=['mardelusados'])
        [punto] = await db.create_alert(user_id=10001, chat_id=10001, name='Fiat Punto',
            filters={'marcas': ['Fiat'], 'modelos': ['Punto'], 'sources': ['mardelusados']})
        FakeSource.results['mardelusados'] = [
            card('ford', source='mardelusados', marca='Ford', modelo='Fiesta'),
            card('fiat', source='mardelusados', titulo='Fiat Punto Attractive', marca='Fiat',
                 modelo='Punto', anio=2012, precio=8000),
        ]
        await self.tick()
        [target] = await self.rows('select * from crawl_targets where active')
        self.assertEqual((target['source'], target['make'], target['model']), ('mardelusados', None, None))
        self.assertTrue(target['query']['inventory'])
        self.assertEqual(FakeSource.searches, [('mardelusados', {})])
        listings = await self.rows('select external_id, make, model from listings order by external_id')
        self.assertEqual([(r['external_id'], r['make'], r['model']) for r in listings],
                         [('fiat', 'Fiat', 'Punto'), ('ford', 'Ford', 'Fiesta')])
        matches = await self.rows('select m.search_profile_id, l.external_id from matches m '
                                 'join listings l on l.id=m.listing_id order by m.search_profile_id')
        self.assertEqual({(r['search_profile_id'], r['external_id']) for r in matches},
                         {(fiesta, 'ford'), (punto, 'fiat')})

    async def test_inventory_queries_respect_source_selection_and_active_access(self):
        yes = await self.fiesta_alert(sources=['mardelusados'])
        await self.fiesta_alert(user=10002, sources=['mercadolibre'])
        await self.tick()
        alerts = await profiles.alerts_for_target('mardelusados', None, None,
                                                   inventory=True, telegram_only=False)
        self.assertEqual([a['id'] for a in alerts], [yes])
        await db.set_alert_active(yes, False)
        self.assertEqual(await targets.due_targets(), [])
        self.assertEqual(await profiles.alerts_for_target('mardelusados', None, None,
                                                   inventory=True, telegram_only=False), [])

    async def test_migration_registers_five_sources_and_preserves_operator_tuning(self):
        sql = next((Path(__file__).resolve().parents[2] / 'supabase' / 'migrations').glob('*_regional_sources.sql')).read_text(encoding='utf-8')
        ids = ['mardelusados', 'rosariogarage', 'usadossantafe', 'onlycarsusados', 'sc_clasificados']
        async with db.connection() as cx:
            await cx.execute('SAVEPOINT regional_migration_test')
            try:
                await cx.execute('DELETE FROM sources WHERE id = ANY(%s)', (ids,))
                await cx.execute(sql)
                rows = await (await cx.execute('SELECT id, enabled FROM sources WHERE id = ANY(%s)', (ids,))).fetchall()
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(r['enabled'] for r in rows))
                await cx.execute("UPDATE sources SET enabled=false, crawl_interval_seconds=1234 WHERE id='mardelusados'")
                await cx.execute(sql)
                row = await (await cx.execute("SELECT enabled, crawl_interval_seconds FROM sources WHERE id='mardelusados'")).fetchone()
                self.assertEqual((row['enabled'], row['crawl_interval_seconds']), (False, 1234))
            finally:
                await cx.execute('ROLLBACK TO SAVEPOINT regional_migration_test')
