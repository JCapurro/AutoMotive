from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from notifications.channels.base import SendResult
from notifications.links import Links
from notifications.product_feedback import feedback_message, run_product_feedback

ROW = {
    'id': 'feedback-1', 'claim_token': 'claim-1', 'email': 'buyer@example.test',
    'user_id': 'account-1', 'search_profile_id': 12, 'search_name': 'Ford Fiesta',
    'message': 'Quiero comparar <versiones> & precios.\nGracias.',
    'created_at': datetime(2026, 10, 28, 18, 0, tzinfo=timezone.utc),
}


class ProductFeedbackTests(IsolatedAsyncioTestCase):
    def test_message_is_safe_and_replyable(self):
        msg = feedback_message(ROW, Links('https://www.eseauto.com.ar'))
        self.assertEqual(msg.reply_to, ROW['email'])
        self.assertIn('&lt;versiones&gt; &amp;', msg.html)
        self.assertNotIn('<versiones>', msg.html)
        self.assertIn('Ford Fiesta', msg.text)
        self.assertIn('15:00', msg.text)
        self.assertIn('/admin/searches#search-12', msg.text)

    async def test_a_provider_failure_is_retried_without_losing_the_lead(self):
        channel = AsyncMock()
        channel.send_message.return_value = SendResult(False, 'resend 503', retry=True)
        with patch('notifications.product_feedback.repo') as repo, patch('notifications.product_feedback.get_config', AsyncMock(return_value={'recipient_email': 'owner@example.test'})):
            repo.claim = AsyncMock(return_value=[ROW])
            repo.mark_sent = AsyncMock()
            repo.mark_retry = AsyncMock()
            self.assertEqual(await run_product_feedback(channel, Links()), 0)
            repo.mark_sent.assert_not_called()
            repo.mark_retry.assert_awaited_once()

    async def test_sends_to_the_configured_owner_and_marks_only_provider_success(self):
        channel = AsyncMock()
        channel.send_message.return_value = SendResult(True, provider_id='provider-123')
        with patch('notifications.product_feedback.repo') as repo, patch('notifications.product_feedback.get_config', AsyncMock(return_value={'recipient_email': 'owner@example.test'})):
            repo.claim = AsyncMock(return_value=[ROW])
            repo.mark_sent = AsyncMock()
            repo.mark_retry = AsyncMock()
            self.assertEqual(await run_product_feedback(channel, Links()), 1)
            args, kwargs = channel.send_message.call_args
            self.assertEqual(args[0], 'owner@example.test')
            self.assertEqual(kwargs['idempotency_key'], 'product-feedback-feedback-1')
            self.assertIsNone(kwargs['unsubscribe_token'])
            repo.mark_sent.assert_awaited_once_with('feedback-1', 'claim-1', 'provider-123')

    async def test_no_channel_leaves_feedback_pending(self):
        with patch('notifications.product_feedback.repo') as repo:
            self.assertEqual(await run_product_feedback(None, Links()), 0)
            repo.claim.assert_not_called()

    async def test_disabled_or_invalid_delivery_config_leaves_feedback_pending(self):
        for cfg in ({'enabled': False, 'recipient_email': 'owner@example.test'}, {'recipient_email': None}, {'recipient_email': 'bad\naddress@example.test'}):
            with self.subTest(config=cfg), patch('notifications.product_feedback.repo') as repo, patch('notifications.product_feedback.get_config', AsyncMock(return_value=cfg)):
                self.assertEqual(await run_product_feedback(AsyncMock(),Links()),0)
                repo.claim.assert_not_called()
