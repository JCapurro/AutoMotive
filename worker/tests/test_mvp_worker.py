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

    async def test_admin_alerts_go_out_with_the_user_bot_off(self):
        """2026-11-07: TELEGRAM_ENABLED=false left the Facebook session alert mute."""
        stop = asyncio.Event()
        stop.set()
        bot = AsyncMock()
        with (
            patch.object(main, 'TELEGRAM_ENABLED', False),
            patch.object(main, 'TELEGRAM_TOKEN', '123:abc'),
            patch.object(main, 'TELEGRAM_ADMIN_CHAT_ID', '42'),
            patch.object(main.Application, 'builder', side_effect=AssertionError('no polling bot')),
            patch.object(main, 'Bot', return_value=bot) as made,
            patch.object(main, 'SourceAlerts') as alerts,
            patch.object(main.asyncio, 'Event', return_value=stop),
            patch.object(main.db, 'open_pool', new_callable=AsyncMock),
            patch.object(main.db, 'close_pool', new_callable=AsyncMock),
            patch.object(main, 'build_provider'),
            patch.object(main, 'run_collector', new=lambda job: job),
            patch.object(main, 'browser_shutdown', new_callable=AsyncMock),
            patch.object(main, 'startup_warnings', return_value=[]),
        ):
            await main.amain()
        made.assert_called_once_with('123:abc')
        bot.initialize.assert_awaited_once()
        bot.shutdown.assert_awaited_once()
        alerts.assert_called_once_with(bot, '42', main.WEB_BASE_URL)

    async def test_mvp_notifier_has_no_telegram_adapter(self):
        from notifications.links import Links
        notifier = main.build_notifier(None, Links('https://www.eseauto.com.ar'))
        self.assertNotIn('web', notifier.channels)
        self.assertNotIn('telegram', notifier.channels)
