"""
Regressiya: "Xabar matnini o'zgartirish"ni bosib, "Orqaga"ga qaytgan (yoki
umuman unutib qo'ygan) odamning keyingi har qanday xabari avtojavob matniga
aylanib qolardi. Endi: boshqa tugma/ /start/ /cancel holatni tozalaydi va holat
10 daqiqadan keyin o'z-o'zidan eskiradi.
"""

import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402

USER = 9
SETTINGS = {
    "offline": False, "cooldown_hours": 3.0, "auto_reply_text": "eski",
    "sleep_mode_enabled": False, "sleep_start_minutes": 1380, "sleep_end_minutes": 420,
    "sleep_reply_text": "", "bio_countdown_target": None,
    "birthday_month": None, "birthday_day": None,
}


def _button(data, user_id=USER):
    update = MagicMock()
    query = AsyncMock()
    query.data = data
    query.from_user.id = user_id
    query.from_user.username = "x"
    query.from_user.full_name = "X"
    update.callback_query = query
    return update


def _text(text, user_id=USER):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "x"
    update.effective_user.full_name = "X"
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


class _Base(unittest.TestCase):
    def setUp(self):
        for patcher in (
            patch.object(db, "record_user"),
            patch.object(db, "get_connection", return_value=None),
            patch.object(db, "get_settings", return_value=dict(SETTINGS)),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        for d in (
            bot.pending_settings_action, bot._pending_settings_set_at,
            bot.pending_admin_action, bot._pending_admin_set_at,
        ):
            d.clear()
        self.addCleanup(lambda: [
            d.clear() for d in (
                bot.pending_settings_action, bot._pending_settings_set_at,
                bot.pending_admin_action, bot._pending_admin_set_at,
            )
        ])

    def press(self, data):
        asyncio.run(bot.on_button(_button(data), MagicMock()))


class TestPendingSettingsAction(_Base):
    def test_edit_text_then_back_clears_pending_and_text_is_not_saved(self):
        self.press("edit_text")
        self.assertEqual(bot.get_pending_action(USER), "text")
        self.press("back")
        self.assertIsNone(bot.get_pending_action(USER))
        with patch.object(db, "update_settings") as update_settings:
            asyncio.run(bot.on_text(_text("salom, kecha gaplashgan edik"), MagicMock()))
        update_settings.assert_not_called()

    def test_edit_text_then_input_is_saved(self):
        self.press("edit_text")
        with patch.object(db, "update_settings") as update_settings:
            asyncio.run(bot.on_text(_text("Yangi matn"), MagicMock()))
        update_settings.assert_called_once_with(USER, auto_reply_text="Yangi matn")
        self.assertIsNone(bot.get_pending_action(USER))

    def test_pending_expires_after_ttl(self):
        bot.set_pending_action(USER, "text")
        bot._pending_settings_set_at[USER] = time.time() - bot.PENDING_ACTION_TTL_SECONDS - 1
        self.assertIsNone(bot.get_pending_action(USER))
        self.assertNotIn(USER, bot.pending_settings_action)

    def test_fresh_pending_does_not_expire(self):
        bot.set_pending_action(USER, "text")
        self.assertEqual(bot.get_pending_action(USER), "text")

    def test_switching_between_actions_keeps_only_the_latest(self):
        self.press("edit_text")
        self.press("edit_cooldown")
        self.assertEqual(bot.get_pending_action(USER), "cooldown")

    def test_start_clears_pending(self):
        bot.set_pending_action(USER, "text")
        update = _text("/start")
        context = MagicMock()
        context.args = []
        with patch.object(bot, "is_subscribed", AsyncMock(return_value=True)):
            asyncio.run(bot.cmd_start(update, context))
        self.assertIsNone(bot.get_pending_action(USER))

    def test_cancel_clears_panel_pending(self):
        bot.set_pending_action(USER, "text")
        update = _text("/cancel")
        asyncio.run(bot.cmd_cancel(update, MagicMock()))
        self.assertIsNone(bot.get_pending_action(USER))
        self.assertIn("Bekor qilindi", update.message.reply_text.call_args[0][0])

    def test_cancel_with_nothing_pending_stays_silent(self):
        # Asl xatti-harakat saqlangan: bekor qiladigan narsa bo'lmasa, javob berilmaydi
        update = _text("/cancel")
        asyncio.run(bot.cmd_cancel(update, MagicMock()))
        update.message.reply_text.assert_not_called()


class TestPendingAdminActionExpiry(_Base):
    def test_admin_pending_expires(self):
        bot.set_pending_admin_action(777, "broadcast")
        self.assertEqual(bot.get_pending_admin_action(777), "broadcast")
        bot._pending_admin_set_at[777] = time.time() - bot.PENDING_ACTION_TTL_SECONDS - 1
        self.assertIsNone(bot.get_pending_admin_action(777))

    def test_expired_broadcast_prompt_ignores_message(self):
        update = MagicMock()
        update.effective_user.id = bot.ADMIN_ID
        update.effective_message.reply_text = AsyncMock()
        bot.set_pending_admin_action(bot.ADMIN_ID, "broadcast")
        bot._pending_admin_set_at[bot.ADMIN_ID] = time.time() - bot.PENDING_ACTION_TTL_SECONDS - 1
        with patch.object(db, "get_user_count") as count:
            asyncio.run(bot.on_admin_broadcast_content(update, MagicMock()))
        count.assert_not_called()
        update.effective_message.reply_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
