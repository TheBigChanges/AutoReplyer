"""
Regressiya: BIO hisoblagich Toshkent sanasi bilan hisoblanishi kerak,
server (Render, UTC) sanasi bilan emas. Kunlik job Toshkent vaqti bilan
00:05 da ishlaydi — shu paytda UTC'da hali OLDINGI kun bo'ladi, shuning
uchun eski kod bio'da doim bir kunga ko'p ko'rsatardi.
"""

import os
import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
from logic import compute_bio_text  # noqa: E402


class _FrozenDatetime(datetime):
    """datetime.now(tz) har doim bitta aniq UTC lahzasini (tz'ga o'girib) qaytaradi."""

    frozen_utc = datetime(2026, 12, 31, 19, 5, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        return cls.frozen_utc.astimezone(tz) if tz else cls.frozen_utc


class TestTodayTashkent(unittest.TestCase):
    def test_utc_evening_is_already_next_day_in_tashkent(self):
        # 31-dekabr 19:05 UTC == 1-yanvar 00:05 Toshkent
        with patch.object(bot, "datetime", _FrozenDatetime):
            self.assertEqual(bot.today_tashkent(), date(2027, 1, 1))

    def test_bio_text_at_daily_job_time_says_today_is_new_year(self):
        # Kunlik job aynan shu lahzada ishlaydi: Toshkentda 1-yanvar -> "Bugun yangi yil"
        with patch.object(bot, "datetime", _FrozenDatetime):
            text = compute_bio_text("new_year", None, None, today=bot.today_tashkent())
        self.assertIn("Bugun yangi yil", text)
        # Eski xatti-harakat (UTC sanasi, 31-dekabr) "1 kun qoldi" deb noto'g'ri yozardi:
        old_text = compute_bio_text("new_year", None, None, today=date(2026, 12, 31))
        self.assertIn("1 kun qoldi", old_text)


if __name__ == "__main__":
    unittest.main()
