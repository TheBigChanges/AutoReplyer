import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logic import format_cooldown, parse_cooldown_input


class TestParseCooldownInput(unittest.TestCase):
    def test_plain_number_is_hours(self):
        self.assertEqual(parse_cooldown_input("3"), 3.0)
        self.assertEqual(parse_cooldown_input("1.5"), 1.5)

    def test_hours_and_minutes_words(self):
        self.assertEqual(parse_cooldown_input("2 soat 30 daqiqa"), 2.5)
        self.assertEqual(parse_cooldown_input("45 daqiqa"), 0.75)
        self.assertEqual(parse_cooldown_input("3 soat"), 3.0)

    def test_short_abbreviations(self):
        self.assertEqual(parse_cooldown_input("2s 15d"), 2.25)

    def test_colon_format(self):
        self.assertEqual(parse_cooldown_input("1:30"), 1.5)
        self.assertEqual(parse_cooldown_input("0:45"), 0.75)
        self.assertAlmostEqual(parse_cooldown_input("0:59"), 59 / 60)

    def test_colon_format_invalid_minutes_rejected(self):
        # Daqiqa qismi 60 yoki undan katta bo'lsa — noto'g'ri format,
        # "1:90"ni 2.5 soat deb "tushunib" qabul qilib yubormasligi kerak.
        self.assertIsNone(parse_cooldown_input("1:90"))
        self.assertIsNone(parse_cooldown_input("0:60"))
        self.assertIsNone(parse_cooldown_input("2:100"))

    def test_colon_format_negative_rejected(self):
        self.assertIsNone(parse_cooldown_input("-1:30"))

    def test_comma_decimal(self):
        self.assertEqual(parse_cooldown_input("1,5"), 1.5)

    def test_invalid_input_returns_none(self):
        self.assertIsNone(parse_cooldown_input("yoq"))
        self.assertIsNone(parse_cooldown_input(""))
        self.assertIsNone(parse_cooldown_input("abc:def"))


class TestNonFiniteCooldownRejected(unittest.TestCase):
    """Regressiya: parse_cooldown_input("nan") / ("inf") oldin float('nan') /
    float('inf') qaytarardi. bot.py'dagi `hours <= 0` tekshiruvi nan'ni
    to'xtatmasdi, natijada:
      - nan: `(now - last) < nan * 3600` har doim False -> cooldown ishlamaydi;
      - inf: har doim True -> birinchi javobdan keyin bot abadiy jim;
      - format_cooldown() nan/inf'da ValueError/OverflowError bilan yiqilib,
        foydalanuvchi paneli ochilmay qolardi."""

    def test_nan_and_inf_words_rejected(self):
        for text in ("nan", "NaN", "inf", "-inf", "infinity", "+inf"):
            with self.subTest(text=text):
                self.assertIsNone(parse_cooldown_input(text))

    def test_overflowing_exponent_rejected(self):
        self.assertIsNone(parse_cooldown_input("1e999"))

    def test_nan_inside_colon_format_rejected(self):
        self.assertIsNone(parse_cooldown_input("nan:5"))
        self.assertIsNone(parse_cooldown_input("1:nan"))
        self.assertIsNone(parse_cooldown_input("inf:30"))

    def test_absurdly_long_digit_string_rejected(self):
        # 400 xonali raqam float()'da inf bo'lib ketadi
        self.assertIsNone(parse_cooldown_input("9" * 400))
        self.assertIsNone(parse_cooldown_input("9" * 400 + " soat"))

    def test_normal_values_still_work(self):
        self.assertEqual(parse_cooldown_input("3"), 3.0)
        self.assertEqual(parse_cooldown_input("1:30"), 1.5)
        self.assertEqual(parse_cooldown_input("2 soat 30 daqiqa"), 2.5)

    def test_every_accepted_result_is_finite_and_formattable(self):
        # Qabul qilingan har qanday natija format_cooldown()'ni yiqitmasligi kerak
        for text in ("nan", "inf", "1e999", "nan:5", "1:nan", "3", "45 daqiqa", "1:30"):
            with self.subTest(text=text):
                hours = parse_cooldown_input(text)
                if hours is not None:
                    self.assertTrue(math.isfinite(hours))
                    format_cooldown(hours)  # xato otmasligi kerak


class TestFormatCooldown(unittest.TestCase):
    def test_whole_hours(self):
        self.assertEqual(format_cooldown(3.0), "3 soat")

    def test_only_minutes(self):
        self.assertEqual(format_cooldown(0.5), "30 daqiqa")

    def test_hours_and_minutes(self):
        self.assertEqual(format_cooldown(2.5), "2 soat 30 daqiqa")

    def test_zero(self):
        self.assertEqual(format_cooldown(0), "Har doim javob beradi (cooldown yo'q)")

    def test_roundtrip_with_parser(self):
        for text, expected in [
            ("2 soat 30 daqiqa", "2 soat 30 daqiqa"),
            ("45 daqiqa", "45 daqiqa"),
            ("3", "3 soat"),
        ]:
            hours = parse_cooldown_input(text)
            self.assertEqual(format_cooldown(hours), expected)


if __name__ == "__main__":
    unittest.main()
