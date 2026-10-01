"""
run_broadcast_job() kutilmagan xato (masalan baza bilan bog'liq) chiqsa
job holati abadiy 'running' bo'lib qolmasligini, balki 'failed'ga
o'tishini tekshiradi. Bu muhim: aks holda har server restart'da
(resume_pending_broadcasts) xato job cheksiz qayta urinib, hech qachon
tugamaydi.

Bu modul `bot` va `db`ni import qilgani uchun, import paytida kerak
bo'ladigan environment variable'larni oldindan (dummy qiymatlar bilan)
o'rnatadi — haqiqiy Telegram/Postgres'ga ulanmaydi, barcha tashqi
chaqiruvlar mock qilinadi.
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402


class TestBroadcastJobFailureHandling(unittest.TestCase):
    def test_unexpected_exception_marks_job_failed_not_completed(self):
        status_calls = []

        def fake_set_status(job_id, status):
            status_calls.append((job_id, status))

        def fake_get_user_ids_after(last_id, limit=200):
            raise RuntimeError("simulated unexpected db error")

        fake_bot = AsyncMock()

        with patch.object(db, "set_broadcast_status", side_effect=fake_set_status), patch.object(
            db, "get_user_ids_after", side_effect=fake_get_user_ids_after
        ):
            asyncio.run(
                bot.run_broadcast_job(
                    fake_bot, job_id=42, source_chat_id=1, source_message_id=2, reply_to_chat_id=999
                )
            )

        # 'completed' emas, aniq 'failed' deb belgilanishi SHART — shunda
        # get_running_broadcast_jobs() uni qayta topmaydi va cheksiz
        # qayta urinish bo'lmaydi.
        self.assertEqual(status_calls, [(42, "failed")])

    def test_admin_is_notified_on_unexpected_failure(self):
        fake_bot = AsyncMock()

        with patch.object(db, "set_broadcast_status"), patch.object(
            db, "get_user_ids_after", side_effect=RuntimeError("boom")
        ):
            asyncio.run(
                bot.run_broadcast_job(
                    fake_bot, job_id=7, source_chat_id=1, source_message_id=2, reply_to_chat_id=555
                )
            )

        self.assertTrue(fake_bot.send_message.called)
        _, kwargs = fake_bot.send_message.call_args
        self.assertEqual(kwargs["chat_id"], 555)

    def test_successful_run_marks_completed(self):
        status_calls = []

        def fake_set_status(job_id, status):
            status_calls.append((job_id, status))

        # Birinchi chaqiruvda bitta foydalanuvchi, ikkinchisida bo'sh ro'yxat (tugadi)
        batches = iter([[111], []])

        def fake_get_user_ids_after(last_id, limit=200):
            return next(batches, [])

        fake_bot = AsyncMock()

        with patch.object(db, "set_broadcast_status", side_effect=fake_set_status), patch.object(
            db, "get_user_ids_after", side_effect=fake_get_user_ids_after
        ), patch.object(db, "update_broadcast_progress"), patch.object(db, "record_broadcast_failure"):
            asyncio.run(
                bot.run_broadcast_job(
                    fake_bot, job_id=1, source_chat_id=1, source_message_id=2, reply_to_chat_id=None
                )
            )

        self.assertEqual(status_calls, [(1, "completed")])


if __name__ == "__main__":
    unittest.main()
