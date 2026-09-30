import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from logic import format_time_range, is_within_sleep_window, parse_time_range_input


class TestParseTimeRangeInput(unittest.TestCase):
    def test_hh_mm_dash_hh_mm(self):
        self.assertEqual(parse_time_range_input("23:00-07:00"), (23 * 60, 7 * 60))

    def test_hh_dash_hh(self):
        self.assertEqual(parse_time_range_input("23-07"), (23 * 60, 7 * 60))

    def test_spaces_around_dash(self):
        self.assertEqual(parse_time_range_input("23:00 - 7:00"), (23 * 60, 7 * 60))

    def test_invalid_hour(self):
        self.assertIsNone(parse_time_range_input("25:00-07:00"))

    def test_garbage(self):
        self.assertIsNone(parse_time_range_input("uxlayapman"))


class TestFormatTimeRange(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(format_time_range(23 * 60, 7 * 60), "23:00\u201307:00")


class TestIsWithinSleepWindow(unittest.TestCase):
    def test_wraps_midnight_inside(self):
        # 23:00 -> 07:00 oralig'i, 03:00 shu oraliqda
        self.assertTrue(is_within_sleep_window(3 * 60, 23 * 60, 7 * 60))

    def test_wraps_midnight_outside(self):
        self.assertFalse(is_within_sleep_window(12 * 60, 23 * 60, 7 * 60))

    def test_wraps_midnight_start_inclusive(self):
        self.assertTrue(is_within_sleep_window(23 * 60, 23 * 60, 7 * 60))

    def test_wraps_midnight_end_exclusive(self):
        self.assertFalse(is_within_sleep_window(7 * 60, 23 * 60, 7 * 60))

    def test_non_wrapping_range(self):
        self.assertTrue(is_within_sleep_window(10 * 60, 9 * 60, 17 * 60))
        self.assertFalse(is_within_sleep_window(8 * 60, 9 * 60, 17 * 60))

    def test_zero_length_window_never_active(self):
        self.assertFalse(is_within_sleep_window(10 * 60, 5 * 60, 5 * 60))


if __name__ == "__main__":
    unittest.main()
