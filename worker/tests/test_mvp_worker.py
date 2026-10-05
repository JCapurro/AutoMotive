"""The web/email worker must start without a Telegram token or API connection."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

import main


class MvpWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_lifecycle_without_telegram(self):
        stop = asyncio.Event()
        stop.set()
        with (
            patch.object(main, 'TELEGRAM_ENABLED', False),
            patch.object(main, 'TELEGRAM_TOKEN', ''),
            patch.object(main.Application, 'builder', side_effect=AssertionError('Telegram must not start')),
            patch.object(main.asyncio, 'Event', return_value=stop),
            patch.object(main.db, 'open_pool', new_callable=AsyncMock) as opened,
            patch.object(main.db, 'close_pool', new_callable=AsyncMock) as closed,
            patch.object(main, 'build_provider'),
            patch.object(main, 'run_collector', new=lambda job: job),
            patch.object(main, 'browser_shutdown', new_callable=AsyncMock),
            patch.object(main, 'startup_warnings', return_value=[]),
        ):
            await main.amain()
        opened.assert_awaited_once()
        closed.assert_awaited_once()

    async def test_mvp_notifier_has_no_telegram_adapter(self):
        from notifications.links import Links
        notifier = main.build_notifier(None, Links('https://www.eseauto.com.ar'))
        self.assertIn('web', notifier.channels)
        self.assertNotIn('telegram', notifier.channels)
