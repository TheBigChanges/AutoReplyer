"""
/reklama tasdiqlash oqimi: xabar darhol yuborilmaydi; admin "Yuborish"
tugmasini bosgandagina job yaratiladi. Tasdiq muddati tugasa, boshqa odam
bossa yoki ikki marta bosilsa — xavfsiz.
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402

ADMIN = 777


def _query(data, user_id=ADMIN, age_seconds=5):
    update = MagicMock()
    query = AsyncMock()
    query.data = data
    query.from_user.id = user_id
    query.from_user.username = "a"
    query.from_user.full_name = "A"
    query.message.text = "Yuqoridagi xabar 10 ta foydalanuvchiga yuboriladi."
    query.message.chat_id = 555
    query.message.date = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    update.callback_query = query
    return update, query


class _Base(unittest.TestCase):
    def setUp(self):
        for patcher in (patch.object(bot, "ADMIN_ID", ADMIN), patch.object(db, "record_user")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def press(self, data, running=None, **kw):
        update, query = _query(data, **kw)
        context = MagicMock()
        with patch.object(db, "get_running_broadcast_jobs", return_value=running or []), patch.object(
            db, "get_user_count", return_value=10
        ), patch.object(db, "create_broadcast_job", return_value=42) as create, patch(
            "bot.run_broadcast_job", new=AsyncMock()
        ) as run:
            async def scenario():
                await bot.on_button(update, context)
                await asyncio.sleep(0)
            asyncio.run(scenario())
        return query, create, run


class TestConfirmButtons(_Base):
    def test_confirm_creates_job_and_starts_background_run(self):
        query, create, run = self.press("bc_confirm:999")
        create.assert_called_once_with(555, 999, 10)
        run.assert_called_once()
        self.assertEqual(run.call_args.args[1:4], (42, 555, 999))
        query.answer.assert_awaited_once()
        edited = query.edit_message_text.call_args[0][0]
        self.assertIn("fonda yuborilmoqda", edited)

    def test_cancel_creates_nothing(self):
        query, create, run = self.press("bc_cancel")
        create.assert_not_called()
        run.assert_not_called()
        query.answer.assert_awaited_once()
        self.assertIn("Bekor qilindi", query.edit_message_text.call_args[0][0])

    def test_non_admin_cannot_confirm(self):
        query, create, run = self.press("bc_confirm:999", user_id=12345)
        create.assert_not_called()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.call_args.kwargs.get("show_alert"))
        query.edit_message_text.assert_not_called()

    def test_non_admin_cannot_cancel(self):
        query, create, _ = self.press("bc_cancel", user_id=12345)
        query.edit_message_text.assert_not_called()
        self.assertTrue(query.answer.call_args.kwargs.get("show_alert"))

    def test_expired_confirmation_is_refused(self):
        query, create, run = self.press("bc_confirm:999", age_seconds=bot.BROADCAST_CONFIRM_TTL_SECONDS + 5)
        create.assert_not_called()
        run.assert_not_called()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.call_args.kwargs.get("show_alert"))
        self.assertIn("Muddati o'tdi", query.edit_message_text.call_args[0][0])

    def test_bad_payload_is_harmless(self):
        query, create, _ = self.press("bc_confirm:abc")
        create.assert_not_called()
        query.answer.assert_awaited_once()

    def test_confirm_refused_when_another_job_already_running(self):
        query, create, run = self.press(
            "bc_confirm:999", running=[{"id": 10, "sent_count": 3, "total_count": 100}]
        )
        create.assert_not_called()
        run.assert_not_called()
        self.assertIn("10", query.edit_message_text.call_args[0][0])

    def test_confirmation_message_loses_buttons_on_finish(self):
        query, _, _ = self.press("bc_confirm:999")
        _, kwargs = query.edit_message_text.call_args
        self.assertNotIn("reply_markup", kwargs)  # tugmalar yo'qoladi: ikki marta bosib bo'lmaydi


class TestBroadcastTaskIsKept(unittest.TestCase):
    def test_spawn_background_keeps_a_strong_reference_until_done(self):
        async def scenario():
            gate = asyncio.Event()

            async def work():
                await gate.wait()

            task = bot.spawn_background(work())
            self.assertIn(task, bot._background_tasks)
            gate.set()
            await task
            await asyncio.sleep(0)
            self.assertNotIn(task, bot._background_tasks)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
