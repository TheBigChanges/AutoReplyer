"""Smart Handoff integration tests. No real Telegram messages or Gemini calls."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import bot
import db


class HandoffFlowTests(unittest.TestCase):
    def setUp(self):
        self.bm = SimpleNamespace(
            message_id=10, business_connection_id="test-business",
            from_user=SimpleNamespace(first_name="Ali", last_name=""), chat=SimpleNamespace(id=777),
        )
        self.bot = MagicMock()
        self.bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=999))

    def run_flow(self, *, active=False, claim=True, text="Men operator bilan gaplashmoqchiman"):
        with patch.object(db, "handoff_active", return_value=active) as exists, \
             patch.object(db, "claim_handoff", return_value=claim) as reserve, \
             patch.object(db, "release_handoff") as release:
            done = asyncio.run(bot.maybe_handoff(self.bot, self.bm, 42, 777, text))
        return done, exists, reserve, release

    def test_owner_notified_and_customer_acknowledged(self):
        # A claimed handoff is active when the acknowledgement is sent.
        checks = iter([False, True])
        with patch.object(db, "handoff_active", side_effect=lambda *a: next(checks)), \
             patch.object(db, "claim_handoff", return_value=True):
            done = asyncio.run(bot.maybe_handoff(self.bot, self.bm, 42, 777, "Men operator bilan gaplashmoqchiman"))
        self.assertTrue(done)
        self.assertEqual(self.bot.send_message.await_count, 2)
        self.assertEqual(self.bot.send_message.call_args_list[0].kwargs["chat_id"], 42)
        self.assertEqual(self.bot.send_message.call_args_list[1].kwargs["chat_id"], 777)

    def test_regular_message_does_not_handoff(self):
        done, _, reserve, _ = self.run_flow(text="Narx qancha?")
        self.assertFalse(done)
        reserve.assert_not_called()
        self.bot.send_message.assert_not_awaited()

    def test_existing_handoff_is_silent(self):
        done, _, reserve, _ = self.run_flow(active=True)
        self.assertTrue(done)
        reserve.assert_not_called()
        self.bot.send_message.assert_not_awaited()

    def test_definite_owner_notification_failure_releases_handoff(self):
        from telegram.error import Forbidden
        self.bot.send_message.side_effect = Forbidden("bot was blocked")
        with patch.object(db, "handoff_active", return_value=False), \
             patch.object(db, "claim_handoff", return_value=True), \
             patch.object(db, "release_handoff") as release:
            done = asyncio.run(bot.maybe_handoff(self.bot, self.bm, 42, 777, "I want to speak with a human"))
        self.assertFalse(done)
        release.assert_called_once_with(42, 777, 10)

    def test_ai_menu_contains_toggle(self):
        settings = {"ai_enabled": True, "ai_info": "", "ai_role": "assistant", "handoff_enabled": False}
        with patch.object(db, "get_settings", return_value=settings), patch.object(db, "get_ai_usage", return_value=0), \
             patch.object(bot, "get_lang", return_value="uz"):
            _, markup = bot.build_ai_menu(42)
        self.assertIn("ai_handoff_on", [btn.callback_data for row in markup.inline_keyboard for btn in row])
        settings["handoff_enabled"] = True
        with patch.object(db, "get_settings", return_value=settings), patch.object(db, "get_ai_usage", return_value=0), \
             patch.object(bot, "get_lang", return_value="uz"):
            _, markup = bot.build_ai_menu(42)
        self.assertIn("ai_handoff_off", [btn.callback_data for row in markup.inline_keyboard for btn in row])


if __name__ == "__main__":
    unittest.main()
