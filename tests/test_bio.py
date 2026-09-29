import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logic import compute_bio_text, days_until_next, parse_birthday_input


class TestDaysUntilNext(unittest.TestCase):
    def test_same_day_is_zero(self):
        today = date(2026, 1, 1)
        self.assertEqual(days_until_next(1, 1, today=today), 0)

    def test_one_day_before(self):
        today = date(2025, 12, 31)
        self.assertEqual(days_until_next(1, 1, today=today), 1)

    def test_date_already_passed_this_year_wraps_to_next_year(self):
        # Navro'z (21-mart) 27-sentabrda so'ralsa — keyingi yilga o'tishi kerak
        today = date(2026, 9, 27)
        result = days_until_next(3, 21, today=today)
        expected = (date(2027, 3, 21) - today).days
        self.assertEqual(result, expected)

    def test_date_later_this_year(self):
        today = date(2026, 1, 1)
        result = days_until_next(3, 21, today=today)
        expected = (date(2026, 3, 21) - today).days
        self.assertEqual(result, expected)

    def test_feb_29_on_non_leap_year_falls_back(self):
        # 2026 kabisa yil emas — 29-fevral bo'lmaydi, xato chiqmasligi kerak
        today = date(2026, 1, 1)
        result = days_until_next(2, 29, today=today)
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)


class TestComputeBioText(unittest.TestCase):
    def test_new_year_text(self):
        text = compute_bio_text("new_year", None, None)
        self.assertIn("Yangi yilga", text)
        self.assertIn("kun qoldi", text)

    def test_navroz_text(self):
        text = compute_bio_text("navroz", None, None)
        self.assertIn("Navro'zga", text)

    def test_birthday_without_date_returns_none(self):
        self.assertIsNone(compute_bio_text("birthday", None, None))

    def test_birthday_with_date(self):
        text = compute_bio_text("birthday", 3, 15)
        self.assertIn("Tug'ilgan kunimga", text)

    def test_unknown_target_returns_none(self):
        self.assertIsNone(compute_bio_text("nomalum", None, None))

    def test_each_event_has_its_own_emoji(self):
        birthday_text = compute_bio_text("birthday", 1, 1)
        new_year_text = compute_bio_text("new_year", None, None)
        navroz_text = compute_bio_text("navroz", None, None)
        self.assertTrue(birthday_text.startswith("\U0001F382"))  # 🎂
        self.assertTrue(new_year_text.startswith("\U0001F386"))  # 🎆
        self.assertTrue(navroz_text.startswith("\U0001F337"))    # 🌷


class TestParseBirthdayInput(unittest.TestCase):
    def test_dot_format(self):
        self.assertEqual(parse_birthday_input("15.03"), (3, 15))

    def test_dash_format(self):
        self.assertEqual(parse_birthday_input("15-03"), (3, 15))

    def test_slash_format(self):
        self.assertEqual(parse_birthday_input("15/03"), (3, 15))

    def test_invalid_month(self):
        self.assertIsNone(parse_birthday_input("15.13"))

    def test_invalid_day_for_month(self):
        self.assertIsNone(parse_birthday_input("31.02"))

    def test_garbage_input(self):
        self.assertIsNone(parse_birthday_input("salom"))


if __name__ == "__main__":
    unittest.main()