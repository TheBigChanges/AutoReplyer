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
from telegram.error import BadRequest, Forbidden  # noqa: E402


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

    def test_progress_deltas_match_actual_outcome_not_hardcoded(self):
        """Regressiya testi: oldin har bir urinishdan keyin har doim
        sent_delta=1, failed_delta=0 yuborilar edi — hatto muvaffaqiyatsiz
        (Forbidden/TelegramError) holatlarda ham. Endi delta aniq natijaga
        mos bo'lishi SHART."""
        progress_calls = []

        def fake_update_progress(job_id, last_user_id, sent_delta, failed_delta):
            progress_calls.append((last_user_id, sent_delta, failed_delta))

        # 4 ta foydalanuvchi: muvaffaqiyatli, Forbidden, boshqa TelegramError, yana muvaffaqiyatli
        batches = iter([[101, 102, 103, 104], []])

        def fake_get_user_ids_after(last_id, limit=200):
            return next(batches, [])

        async def fake_copy_message(chat_id, from_chat_id, message_id):
            if chat_id == 102:
                raise Forbidden("blocked")
            if chat_id == 103:
                raise BadRequest("chat not found")
            return None

        fake_bot = AsyncMock()
        fake_bot.copy_message.side_effect = fake_copy_message

        with patch.object(db, "set_broadcast_status"), patch.object(
            db, "get_user_ids_after", side_effect=fake_get_user_ids_after
        ), patch.object(
            db, "update_broadcast_progress", side_effect=fake_update_progress
        ), patch.object(db, "record_broadcast_failure"):
            asyncio.run(
                bot.run_broadcast_job(
                    fake_bot, job_id=9, source_chat_id=1, source_message_id=2, reply_to_chat_id=None
                )
            )

        self.assertEqual(
            progress_calls,
            [
                (101, 1, 0),  # muvaffaqiyatli
                (102, 0, 1),  # Forbidden — failed bo'lishi kerak, sent emas
                (103, 0, 1),  # boshqa TelegramError — failed
                (104, 1, 0),  # muvaffaqiyatli
            ],
        )


class TestRetryScoping(unittest.TestCase):
    """`retry_of_job_id` bazada to'g'ri saqlanib, keyin to'g'ri o'qilishini
    tekshiradi — bu aynan sodir bo'lgan bug: retry job restart'dan keyin
    cheklangan ro'yxat o'rniga BUTUN foydalanuvchilar bazasiga ketib
    qolishi mumkin edi, chunki bog'lanish RAM'dagi parametrda emas,
    bazada saqlanishi kerak edi."""

    def test_broadcast_loop_uses_failed_user_ids_when_retry_of_job_id_set(self):
        """_broadcast_loop'ga retry_of_job_id berilsa, u get_user_ids_after
        (butun jadval) emas, aynan get_failed_user_ids_after (cheklangan
        ro'yxat) orqali o'qishi SHART."""
        calls = {"all_users": 0, "failed_only": 0}

        def fake_get_user_ids_after(last_id, limit=200):
            calls["all_users"] += 1
            return []

        def fake_get_failed_user_ids_after(source_job_id, last_id, limit=200):
            calls["failed_only"] += 1
            self.assertEqual(source_job_id, 100)  # aynan ASL job'ning ID'si
            return []

        fake_bot = AsyncMock()

        with patch.object(db, "get_user_ids_after", side_effect=fake_get_user_ids_after), patch.object(
            db, "get_failed_user_ids_after", side_effect=fake_get_failed_user_ids_after
        ):
            asyncio.run(
                bot._broadcast_loop(
                    fake_bot,
                    job_id=101,
                    source_chat_id=1,
                    source_message_id=2,
                    retry_of_job_id=100,
                    start_after_user_id=0,
                )
            )

        self.assertEqual(calls["failed_only"], 1)
        self.assertEqual(calls["all_users"], 0)

    def test_cmd_reklama_retry_passes_retry_of_job_id_on_completed_job(self):
        """/reklama_retry (completed job uchun) yangi job yaratganda
        retry_of_job_id'ni HAM create_broadcast_job'ga, HAM
        run_broadcast_job'ga uzatishi SHART — aks holda yangi job bazada
        oddiy (cheklanmagan) broadcast sifatida qolib ketadi."""
        old_job = {
            "id": 100,
            "status": "completed",
            "source_chat_id": 1,
            "source_message_id": 2,
            "last_user_id": 0,
        }
        create_calls = []
        run_calls = []

        def fake_create_job(*args, **kwargs):
            create_calls.append(kwargs)
            return 101

        async def fake_run_broadcast_job(*args, **kwargs):
            run_calls.append(kwargs)

        update = AsyncMock()
        update.effective_user.id = bot.ADMIN_ID
        update.effective_chat.id = 555
        update.message = AsyncMock()
        context = AsyncMock()

        async def scenario():
            await bot.cmd_reklama_retry(update, context)
            # asyncio.create_task() bilan rejalashtirilgan fon vazifasiga
            # ishga tushish (va tugash, chunki fake'da ichki await yo'q)
            # imkoniyati berish uchun bitta "tick" kutamiz.
            await asyncio.sleep(0)

        with patch.object(db, "get_latest_broadcast_job", return_value=old_job), patch.object(
            db, "get_broadcast_failed_user_ids", return_value=[111, 222]
        ), patch.object(db, "create_broadcast_job", side_effect=fake_create_job), patch(
            "bot.run_broadcast_job", side_effect=fake_run_broadcast_job
        ):
            asyncio.run(scenario())

        self.assertEqual(create_calls[0].get("retry_of_job_id"), 100)
        self.assertEqual(len(run_calls), 1, "run_broadcast_job fon vazifasi bajarilmadi")
        self.assertEqual(run_calls[0].get("retry_of_job_id"), 100)

    def test_resume_pending_broadcasts_preserves_retry_of_job_id(self):
        """Server restart'dan keyin resume_pending_broadcasts() bazadagi
        'running' job'ni topganda, uning retry_of_job_id'sini ham
        run_broadcast_job'ga uzatishi SHART — aks holda retry job
        restart'dan keyin to'satdan BARCHA foydalanuvchiga ketib qolishi
        mumkin edi (aynan xabar qilingan bug)."""
        running_retry_job = {
            "id": 101,
            "source_chat_id": 1,
            "source_message_id": 2,
            "last_user_id": 50,
            "retry_of_job_id": 100,  # bu job aslida job#100'ning retry'si
        }

        run_calls = []

        async def fake_run_broadcast_job(*args, **kwargs):
            run_calls.append(kwargs)

        fake_app = AsyncMock()

        async def scenario():
            await bot.resume_pending_broadcasts(fake_app)
            await asyncio.sleep(0)  # rejalashtirilgan fon vazifasi tugashi uchun

        with patch.object(db, "get_running_broadcast_jobs", return_value=[running_retry_job]), patch(
            "bot.run_broadcast_job", side_effect=fake_run_broadcast_job
        ):
            asyncio.run(scenario())

        self.assertEqual(len(run_calls), 1, "run_broadcast_job fon vazifasi bajarilmadi")
        self.assertEqual(
            run_calls[0].get("retry_of_job_id"), 100,
            "resume_pending_broadcasts retry_of_job_id'ni yo'qotib qo'ydi — "
            "bu holda resumed job BUTUN foydalanuvchilar bazasiga ketib qoladi!",
        )


if __name__ == "__main__":
    unittest.main()
