"""
Ikkita reklama bir vaqtda (tasodifan deyarli bir xil paytda) boshlanib
ketmasligini tekshiradi. Haqiqiy Postgres mavjud bo'lmagan sinov muhitida
UniqueViolation'ni qo'lda simulyatsiya qilib, db.py uni to'g'ri
BroadcastAlreadyRunningError'ga aylantirishini, va bot.py buni tutib
foydalanuvchiga tushunarli xabar berishini (crash qilmasligini) tekshiradi.
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

import psycopg2.errors  # noqa: E402

import bot  # noqa: E402
import db  # noqa: E402


class _FakeCursor:
    """execute() chaqirilganda psycopg2.errors.UniqueViolation otadigan soxta kursor."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *args, **kwargs):
        raise psycopg2.errors.UniqueViolation("duplicate key value violates unique constraint")

    def fetchone(self):
        return None


class _FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self, *args, **kwargs):
        return _FakeCursor()


class TestDbLevelBroadcastLock(unittest.TestCase):
    """db.py: UniqueViolation to'g'ri BroadcastAlreadyRunningError'ga
    aylanishini (va bu funksiyalar o'zlari boshqa xatoni chiqarmasligini)
    tekshiradi."""

    def test_create_broadcast_job_translates_unique_violation(self):
        with patch.object(db, "get_conn", return_value=_FakeConn()):
            with self.assertRaises(db.BroadcastAlreadyRunningError):
                db.create_broadcast_job(source_chat_id=1, source_message_id=2, total_count=10)

    def test_set_broadcast_status_translates_unique_violation(self):
        with patch.object(db, "get_conn", return_value=_FakeConn()):
            with self.assertRaises(db.BroadcastAlreadyRunningError):
                db.set_broadcast_status(job_id=5, status="running")

    def test_set_broadcast_status_to_completed_never_conflicts(self):
        """'completed'/'failed'ga o'tishda unique index hech qachon
        to'qnashmaydi — bu test shunchaki haqiqiy (xato otmaydigan)
        kursor bilan oddiy ishlashni tasdiqlaydi."""

        class _OkCursor:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, *args, **kwargs):
                pass

        class _OkConn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def cursor(self, *args, **kwargs):
                return _OkCursor()

        with patch.object(db, "get_conn", return_value=_OkConn()):
            db.set_broadcast_status(job_id=5, status="completed")  # xato otmasligi kerak


class TestBotHandlesLockGracefully(unittest.TestCase):
    """bot.py: db.BroadcastAlreadyRunningError chiqsa, foydalanuvchiga
    tushunarli xabar ketishi va dastur yiqilib tushmasligi kerak."""

    def _fake_update(self):
        update = AsyncMock()
        update.effective_user.id = bot.ADMIN_ID
        update.effective_chat.id = 555
        update.message = AsyncMock()
        update.effective_message = update.message
        update.effective_message.message_id = 999
        return update

    def test_start_broadcast_handles_race_at_db_level(self):
        """Pre-check "running yo'q" deb o'tgan bo'lsa ham, create_broadcast_job()
        bazada UniqueViolation'ga uchrasa — bot crash qilmasligi, adminga
        tushunarli xabar berishi SHART. (Job endi tasdiq tugmasi bosilganda,
        start_broadcast() ichida yaratiladi.)"""

        def fake_create_job(*args, **kwargs):
            raise db.BroadcastAlreadyRunningError("boshqa job allaqachon running")

        with patch.object(db, "get_running_broadcast_jobs", return_value=[]), patch.object(
            db, "get_user_count", return_value=100
        ), patch.object(db, "create_broadcast_job", side_effect=fake_create_job):
            result = asyncio.run(bot.start_broadcast(AsyncMock(), 555, 999))

        self.assertIn("ishga tushib ulgurdi", result)

    def test_cmd_reklama_retry_completed_branch_handles_race_at_db_level(self):
        old_job = {
            "id": 100, "status": "completed", "source_chat_id": 1,
            "source_message_id": 2, "last_user_id": 0,
        }
        update = self._fake_update()
        context = AsyncMock()

        def fake_create_job(*args, **kwargs):
            raise db.BroadcastAlreadyRunningError("boshqa job allaqachon running")

        with patch.object(db, "get_latest_broadcast_job", return_value=old_job), patch.object(
            db, "get_broadcast_failed_user_ids", return_value=[111, 222]
        ), patch.object(db, "get_running_broadcast_jobs", return_value=[]), patch.object(
            db, "create_broadcast_job", side_effect=fake_create_job
        ):
            asyncio.run(bot.cmd_reklama_retry(update, context))

        update.message.reply_text.assert_called()

    def test_cmd_reklama_retry_failed_branch_handles_race_at_db_level(self):
        failed_job = {
            "id": 100, "status": "failed", "source_chat_id": 1,
            "source_message_id": 2, "last_user_id": 30, "retry_of_job_id": None,
        }
        update = self._fake_update()
        context = AsyncMock()

        def fake_set_status(job_id, status):
            raise db.BroadcastAlreadyRunningError("boshqa job allaqachon running")

        with patch.object(db, "get_latest_broadcast_job", return_value=failed_job), patch.object(
            db, "get_running_broadcast_jobs", return_value=[]
        ), patch.object(db, "set_broadcast_status", side_effect=fake_set_status):
            asyncio.run(bot.cmd_reklama_retry(update, context))

        update.message.reply_text.assert_called()
        last_text = update.message.reply_text.call_args[0][0]
        self.assertIn("ishga tushib ulgurdi", last_text)


if __name__ == "__main__":
    unittest.main()
