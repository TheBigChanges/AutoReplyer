"""
Regressiya: on_button() oldin boshida har doim bo'sh `query.answer()`
chaqirib, keyin ba'zi shoxlarda yana `query.answer(matn, show_alert=True)`
chaqirardi. Telegram faqat BIRINCHI javobni qabul qiladi, shuning uchun
"obuna bo'lmagansiz" va "Ruxsat yo'q" alertlari foydalanuvchiga ko'rinmasdi.
Endi har bir callback'ga aniq BIR marta javob beriladi.
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402


def _make_update(user_id: int, data: str):
    update = MagicMock()
    query = AsyncMock()
    query.from_user.id = user_id
    query.data = data
    update.callback_query = query
    return update, query


class TestCallbackAnsweredExactlyOnce(unittest.TestCase):
    def test_unsubscribed_user_gets_the_alert_as_the_only_answer(self):
        update, query = _make_update(12345, "check_subscription")
        context = MagicMock()
        with patch.object(db, "record_user"), patch.object(
            bot, "is_subscribed", AsyncMock(return_value=False)
        ):
            asyncio.run(bot.on_button(update, context))

        self.assertEqual(query.answer.await_count, 1)
        _, kwargs = query.answer.call_args
        self.assertTrue(kwargs.get("show_alert"), "alert ko'rsatilishi SHART")

    def test_subscribed_user_answered_once(self):
        update, query = _make_update(12345, "check_subscription")
        context = MagicMock()
        with patch.object(db, "record_user"), patch.object(
            bot, "is_subscribed", AsyncMock(return_value=True)
        ), patch.object(db, "get_connection", return_value=None):
            asyncio.run(bot.on_button(update, context))

        self.assertEqual(query.answer.await_count, 1)

    def test_non_admin_gets_permission_alert_as_the_only_answer(self):
        update, query = _make_update(12345, "admin_referrals")
        context = MagicMock()
        with patch.object(db, "record_user"), patch.object(bot, "ADMIN_ID", 777):
            asyncio.run(bot.on_button(update, context))

        self.assertEqual(query.answer.await_count, 1)
        _, kwargs = query.answer.call_args
        self.assertTrue(kwargs.get("show_alert"))
        query.edit_message_text.assert_not_called()

    def test_admin_referrals_view_answered_once(self):
        update, query = _make_update(777, "admin_referrals")
        context = MagicMock()
        with patch.object(db, "record_user"), patch.object(bot, "ADMIN_ID", 777), patch.object(
            db, "get_all_referral_counts", return_value=[]
        ):
            asyncio.run(bot.on_button(update, context))

        self.assertEqual(query.answer.await_count, 1)
        query.edit_message_text.assert_awaited()

    def test_regular_buttons_answered_once(self):
        for data in ("back", "referral"):
            with self.subTest(data=data):
                update, query = _make_update(12345, data)
                context = MagicMock()
                with patch.object(db, "record_user"), patch.object(
                    db, "get_connection", return_value=None
                ), patch.object(db, "get_referral_count", return_value=0):
                    asyncio.run(bot.on_button(update, context))

                self.assertEqual(query.answer.await_count, 1)


if __name__ == "__main__":
    unittest.main()
