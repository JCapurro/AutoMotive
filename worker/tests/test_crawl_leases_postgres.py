"""crawl_targets as a queue: a claimed target is crawled by one worker at a
time, and what a dead worker held comes back on its own (lease) or at the next
start of a worker on its host."""
from datetime import datetime, timedelta, timezone

import pytest

import db
from db.repos import runs, targets
from pgcase import requires_db
from test_ingest_postgres import IngestCase

pytestmark = [pytest.mark.db, requires_db]


class CrawlLeaseTests(IngestCase):
    SOURCES = ('mercadolibre',)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.fiesta_alert()
        await self.tick()                                   # creates the target and runs it once
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET next_run_at = NULL")
        [self.target] = await self.rows("SELECT id FROM crawl_targets WHERE active")

    async def test_a_claimed_target_goes_to_one_worker(self):
        first = await targets.claim_next('mercadolibre', 'vps:1', 60)
        self.assertEqual(first['id'], self.target['id'])
        self.assertGreater(first['crawl_interval_seconds'], 0)
        self.assertIsNone(await targets.claim_next('mercadolibre', 'vps:2', 60))
        self.assertEqual(await targets.due_targets(), [])

    async def test_finishing_frees_the_claim(self):
        await targets.claim_next('mercadolibre', 'vps:1', 60)
        await targets.finish_target(self.target['id'], ok=False, retry_seconds=0)
        [row] = await self.rows("SELECT claimed_by, claimed_until FROM crawl_targets WHERE id = %s",
                                self.target['id'])
        self.assertEqual((row['claimed_by'], row['claimed_until']), (None, None))
        self.assertIsNotNone(await targets.claim_next('mercadolibre', 'vps:2', 60))

    async def test_an_expired_lease_is_due_again(self):
        await targets.claim_next('mercadolibre', 'vps:1', 60)
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET claimed_until = now() - interval '1 second'")
        again = await targets.claim_next('mercadolibre', 'vps:2', 60)
        self.assertEqual(again['id'], self.target['id'])

    async def test_a_dead_workers_claims_are_released(self):
        await targets.claim_next('mercadolibre', 'vps:1', 3600)
        self.assertEqual(await targets.claim_holders('vps'), ['vps:1'])
        self.assertEqual(await targets.claim_holders('other'), [])
        self.assertEqual(await targets.release_claims(['vps:1']), 1)
        self.assertIsNotNone(await targets.claim_next('mercadolibre', 'vps:2', 60))

    async def test_runs_record_their_worker_and_only_dead_ones_are_failed(self):
        [run] = await self.rows("SELECT worker FROM collector_runs")
        self.assertEqual(run['worker'], runs.worker_id())
        host = runs.worker_id().rpartition(':')[0]
        async with db.connection() as cx:
            await cx.execute(
                "INSERT INTO collector_runs (source, target_id, worker) VALUES "
                "('mercadolibre', %(t)s, %(alive)s), ('mercadolibre', %(t)s, %(dead)s), "
                "('mercadolibre', %(t)s, 'elsewhere:1'), ('mercadolibre', %(t)s, NULL)",
                {'t': self.target['id'], 'alive': runs.worker_id(), 'dead': f'{host}:999999999'})
        self.assertEqual(await runs.fail_orphan_runs(datetime.now(timezone.utc) + timedelta(seconds=5)), 2)
        rows = await self.rows("SELECT worker, status FROM collector_runs WHERE status <> 'ok' ORDER BY id")
        self.assertEqual([(r['worker'], r['status']) for r in rows],
                         [(runs.worker_id(), 'running'), (f'{host}:999999999', 'failed'),
                          ('elsewhere:1', 'running'), (None, 'failed')])


class OneLanePerSourceTests(IngestCase):
    """Two workers never crawl the same source at once (one Facebook session)."""
    SOURCES = ('mercadolibre',)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.fiesta_alert()
        await self.fiesta_alert(user=10002, modelos=['Focus'])
        await self.tick()
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET next_run_at = NULL")
        self.targets = [r['id'] for r in await self.rows(
            "SELECT id FROM crawl_targets WHERE active AND source = 'mercadolibre' ORDER BY id")]

    async def test_another_worker_waits_for_the_source(self):
        self.assertEqual(len(self.targets), 2)
        first = await targets.claim_next('mercadolibre', 'vps:1', 60)
        self.assertIsNone(await targets.claim_next('mercadolibre', 'vps:2', 60))
        await targets.finish_target(first['id'], ok=True, retry_seconds=0)
        second = await targets.claim_next('mercadolibre', 'vps:2', 60)
        self.assertNotEqual(second['id'], first['id'])

    async def test_simultaneous_claims_give_the_source_to_one_worker(self):
        import asyncio

        got = await asyncio.gather(targets.claim_next('mercadolibre', 'vps:1', 60),
                                   targets.claim_next('mercadolibre', 'vps:2', 60))
        self.assertEqual(sum(1 for g in got if g is not None), 1)

    async def test_an_expired_claim_does_not_hold_the_source(self):
        await targets.claim_next('mercadolibre', 'vps:1', 60)
        async with db.connection() as cx:
            await cx.execute("UPDATE crawl_targets SET claimed_until = now() - interval '1 second'")
        self.assertIsNotNone(await targets.claim_next('mercadolibre', 'vps:2', 60))


class ClaimOrderTests(IngestCase):
    """A long bootstrap never makes the due targets that notify wait (Sentra
    waited ~140 minutes behind Facebook bootstraps, 2026-10-22)."""
    SOURCES = ('mercadolibre',)

    async def asyncSetUp(self):
        await super().asyncSetUp()
        for user, model in enumerate(('Fiesta', 'Focus', 'Ka', 'Mondeo'), start=20001):
            await self.fiesta_alert(user=user, modelos=[model])
        await self.tick()                                   # every target ran once
        self.ids = {r['model']: r['id'] for r in await self.rows(
            "SELECT id, model FROM crawl_targets WHERE active AND source = 'mercadolibre'")}

    async def due(self, model, minutes_ago, *, first_run_done=True, count_only=False):
        async with db.connection() as cx:
            await cx.execute(
                "UPDATE crawl_targets SET first_run_done = %s, "
                "  next_run_at = now() - make_interval(mins => %s), "
                "  query = CASE WHEN %s THEN query || '{\"count_only\": true}' ELSE query END WHERE id = %s",
                (first_run_done, minutes_ago, count_only, self.ids[model]))

    async def test_claim_order_puts_due_notifying_targets_before_bootstrap_retries(self):
        await self.due('Fiesta', 10, first_run_done=False)  # a bootstrap retry
        await self.due('Focus', 20, count_only=True)
        await self.due('Ka', 1)                              # in regime
        async with db.connection() as cx:                    # never ran (or reset)
            await cx.execute("UPDATE crawl_targets SET next_run_at = NULL WHERE id = %s", (self.ids['Mondeo'],))
        order = []
        while (target := await targets.claim_next('mercadolibre', 'vps:1', 60)) is not None:
            order.append(target['model'])
            await targets.finish_target(target['id'], ok=True, retry_seconds=0)
        self.assertEqual(order, ['Mondeo', 'Ka', 'Focus', 'Fiesta'])
