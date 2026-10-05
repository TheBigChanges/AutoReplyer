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
