"""
BIO startup "yetkazib olish": server 00:05 da o'chiq bo'lib qolsa, o'sha
kungi yangilanish o'tkazib yuborilardi (keyingisi ertasi kuni). Endi startup'da
bir marta, faqat bugun HALI yangilanmaganlar yangilanadi (har restartda hamma
uchun Telegram API'ni takrorlamaslik uchun).
"""

import asyncio
import os
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
from telegram.error import BadRequest  # noqa: E402

TODAY = date(2027, 1, 1)
TODAY_ISO = "2027-01-01"


def _row(owner, bcid, updated_on, target="new_year", month=None, day=None):
    return {
        "owner_user_id": owner,
        "business_connection_id": bcid,
        "bio_countdown_target": target,
        "birthday_month": month,
        "birthday_day": day,
        "bio_updated_on": updated_on,
    }


ROWS = [
    _row(1, "bc1", None),              # hech qachon yangilanmagan
    _row(2, "bc2", TODAY_ISO),         # bugun allaqachon yangilangan
    _row(3, "bc3", "2026-12-31"),      # kecha yangilangan (eskirgan)
]


def _refresh(only_stale, rows=ROWS, side_effect=None):
    fake_bot = MagicMock()
    fake_bot.set_business_account_bio = AsyncMock(side_effect=side_effect)
    with patch.object(bot, "today_tashkent", return_value=TODAY), patch.object(
        db, "get_all_bio_targets", return_value=rows
    ), patch.object(db, "update_settings") as update_settings:
        result = asyncio.run(bot.refresh_bios(fake_bot, only_stale=only_stale))
    return result, fake_bot.set_business_account_bio, update_settings


def _called_connection_ids(set_bio):
    return [c.kwargs["business_connection_id"] for c in set_bio.call_args_list]


class TestRefreshBios(unittest.TestCase):
    def test_startup_mode_updates_only_stale_rows(self):
        (updated, failed), set_bio, _ = _refresh(only_stale=True)
        self.assertEqual(_called_connection_ids(set_bio), ["bc1", "bc3"])
        self.assertEqual((updated, failed), (2, 0))

    def test_daily_mode_updates_everyone(self):
        (updated, failed), set_bio, _ = _refresh(only_stale=False)
        self.assertEqual(_called_connection_ids(set_bio), ["bc1", "bc2", "bc3"])
        self.assertEqual((updated, failed), (3, 0))

    def test_success_marks_today_per_owner(self):
        _, _, update_settings = _refresh(only_stale=True)
        marked = {c.args[0]: c.kwargs for c in update_settings.call_args_list}
        self.assertEqual(marked, {1: {"bio_updated_on": TODAY_ISO}, 3: {"bio_updated_on": TODAY_ISO}})

    def test_text_uses_tashkent_date(self):
        _, set_bio, _ = _refresh(only_stale=True)
        self.assertIn("Bugun yangi yil", set_bio.call_args_list[0].kwargs["bio"])

    def test_failed_update_is_not_marked_and_does_not_stop_others(self):
        # birinchi chaqiruv (bc1) xato beradi, ikkinchisi (bc3) muvaffaqiyatli
        (updated, failed), set_bio, update_settings = _refresh(
            only_stale=True, side_effect=[BadRequest("no rights"), None]
        )
        self.assertEqual((updated, failed), (1, 1))
        marked_owners = [c.args[0] for c in update_settings.call_args_list]
        self.assertEqual(marked_owners, [3], "xato bergan foydalanuvchi belgilanmasligi kerak")

    def test_row_without_text_is_skipped_and_not_marked(self):
        rows = [_row(9, "bc9", None, target="birthday", month=None, day=None)]  # sana kiritilmagan
        (updated, failed), set_bio, update_settings = _refresh(only_stale=True, rows=rows)
        set_bio.assert_not_called()
        update_settings.assert_not_called()
        self.assertEqual((updated, failed), (0, 0))


class TestJobWrappersAndRegistration(unittest.TestCase):
    def test_startup_job_uses_stale_only_mode(self):
        context = MagicMock()
        with patch.object(bot, "refresh_bios", AsyncMock(return_value=(0, 0))) as refresh:
            asyncio.run(bot.bio_startup_job(context))
        refresh.assert_awaited_once_with(context.bot, only_stale=True)

    def test_daily_job_updates_everyone(self):
        context = MagicMock()
        with patch.object(bot, "refresh_bios", AsyncMock(return_value=(0, 0))) as refresh:
            asyncio.run(bot.bio_daily_job(context))
        refresh.assert_awaited_once_with(context.bot, only_stale=False)

    def test_both_jobs_are_scheduled_by_build_app(self):
        app = bot.build_app()
        callbacks = {job.callback for job in app.job_queue.jobs()}
        self.assertIn(bot.bio_startup_job, callbacks)
        self.assertIn(bot.bio_daily_job, callbacks)


class TestApplyBioUpdateMarksDate(unittest.TestCase):
    def _run(self, side_effect=None):
        fake_bot = MagicMock()
        fake_bot.set_business_account_bio = AsyncMock(side_effect=side_effect)
        connection = {"is_enabled": True, "can_edit_bio": True, "business_connection_id": "bc1"}
        settings = {"bio_countdown_target": "new_year", "birthday_month": None, "birthday_day": None}
        with patch.object(bot, "today_tashkent", return_value=TODAY), patch.object(
            db, "get_connection", return_value=connection
        ), patch.object(db, "get_settings", return_value=settings), patch.object(
            db, "update_settings"
        ) as update_settings:
            result = asyncio.run(bot.apply_bio_update(fake_bot, 42))
        return result, update_settings

    def test_manual_update_marks_today_on_success(self):
        (ok, _), update_settings = self._run()
        self.assertTrue(ok)
        update_settings.assert_called_once_with(42, bio_updated_on=TODAY_ISO)

    def test_manual_update_does_not_mark_on_failure(self):
        (ok, _), update_settings = self._run(side_effect=BadRequest("nope"))
        self.assertFalse(ok)
        update_settings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
