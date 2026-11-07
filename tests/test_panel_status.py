"""Boshqaruv paneli: barcha funksiyalar holati (yoqilgan / o'chirilgan / tarifda yo'q + qisqa tafsilot)."""

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
import i18n  # noqa: E402

OWNER = 424242
ON, OFF = "\U0001F7E2", "\U0001F534"

OV = {"faq_total": 5, "faq_active": 4, "kb_total": 3, "kb_active": 3, "au_total": 4, "au_active": 2,
      "sc_total": 3, "sc_active": 3, "inbox_enabled": True, "inbox_pending": 7}


def settings(**kw):
    base = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": True,
            "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "ai_enabled": True, "faq_enabled": True,
            "kb_enabled": True, "scheduler_enabled": True, "name_clock_enabled": True, "bio_countdown_target": "new_year"}
    base.update(kw)
    return base


def status(s=None, ov=OV, lang="uz", allows=lambda *a: True, clock=True, ov_error=None):
    with patch.object(db, "get_panel_overview", return_value=ov, side_effect=ov_error), \
            patch.object(bot, "plan_allows", side_effect=allows), patch.object(bot, "name_clock_allowed", return_value=clock):
        return bot.build_feature_status(OWNER, s or settings(), "pro", lang)


def line(text, key, lang="uz"):
    label = i18n.T[key][lang]
    return next(ln for ln in text.splitlines() if ln.startswith(label))


class FeatureStatusTests(unittest.TestCase):
    def test_every_feature_is_listed_with_details_when_on(self):
        text = status()
        self.assertIn(i18n.T["pnl_title"]["uz"], text)
        self.assertIn(f"— {ON} yoqilgan · 23:00–07:00", line(text, "pnl_sleep"))
        self.assertIn(f"— {ON} yoqilgan", line(text, "pnl_ai"))
        self.assertIn(f"{ON} yoqilgan · ", line(text, "pnl_bio"))
        self.assertIn(f"{ON} yoqilgan · 5 ta savol", line(text, "pnl_faq"))
        self.assertIn(f"{ON} yoqilgan · 3 ta yozuv", line(text, "pnl_kb"))
        self.assertIn(f"{ON} yoqilgan · 2/4 qoida faol", line(text, "pnl_automation"))
        self.assertIn(f"{ON} yoqilgan · 3/3 qoida faol", line(text, "pnl_sched"))
        self.assertIn(f"{ON} yoqilgan · 7 ta javobsiz", line(text, "pnl_inbox"))
        self.assertIn(f"— {ON} yoqilgan", line(text, "pnl_clock"))

    def test_off_states(self):
        s = settings(sleep_mode_enabled=False, ai_enabled=False, bio_countdown_target=None, faq_enabled=False,
                     scheduler_enabled=False, name_clock_enabled=False)
        ov = dict(OV, inbox_enabled=False, kb_active=0)
        text = status(s, ov)
        for key in ("pnl_sleep", "pnl_ai", "pnl_bio", "pnl_faq", "pnl_sched", "pnl_inbox", "pnl_clock", "pnl_kb"):
            self.assertTrue(line(text, key).endswith(f"{OFF} o'chirilgan"), key)
        self.assertNotIn("ta javobsiz", text)

    def test_empty_lists_show_not_added_yet(self):
        ov = dict(OV, faq_total=0, faq_active=0, kb_total=0, kb_active=0, au_total=0, au_active=0, sc_total=0, sc_active=0)
        text = status(ov=ov)
        for key in ("pnl_faq", "pnl_kb", "pnl_automation", "pnl_sched"):
            self.assertTrue(line(text, key).endswith(f"{OFF} hali qo'shilmagan"), key)

    def test_automation_with_no_active_rule_is_off(self):
        text = status(ov=dict(OV, au_active=0))
        self.assertTrue(line(text, "pnl_automation").endswith(f"{OFF} o'chirilgan"))

    def test_plan_locked_features_show_lock_not_state(self):
        text = status(allows=lambda uid, plan, feature: feature not in ("faq", "ai", "bio", "kb", "automation"))
        for key in ("pnl_faq", "pnl_ai", "pnl_bio", "pnl_kb", "pnl_automation"):
            self.assertTrue(line(text, key).endswith("\U0001F512 tarifda yo'q"), key)
        self.assertIn(f"{ON} yoqilgan", line(text, "pnl_sleep"))  # tarifga bog'liq bo'lmaganlar o'z holatida

    def test_name_clock_line_only_when_allowed(self):
        self.assertNotIn(i18n.T["pnl_clock"]["uz"], status(clock=False))

    def test_db_failure_never_breaks_panel_and_keeps_basic_states(self):
        text = status(ov=None, ov_error=RuntimeError("db"))
        self.assertIn(f"{ON} yoqilgan", line(text, "pnl_faq"))
        self.assertTrue(line(text, "pnl_inbox").endswith(f"{OFF} o'chirilgan"))
        self.assertNotIn(" ta savol", text)
        with patch.object(db, "get_settings", return_value=settings()), patch.object(db, "get_panel_overview", side_effect=RuntimeError("db")):
            panel_text, markup = bot.build_panel(OWNER)
        self.assertTrue(markup.inline_keyboard)  # tugmalar saqlanadi

    def test_all_languages_render(self):
        for lang in ("uz", "en", "ru"):
            text = status(lang=lang)
            self.assertEqual(len(text.splitlines()), 10, lang)  # sarlavha + 9 funksiya
            self.assertNotRegex(text, r"\{[a-z_]+\}", lang)
        self.assertIn("7 unanswered", status(lang="en"))
        self.assertIn("без ответа: 7", status(lang="ru"))

    def test_build_panel_contains_status_block_after_message(self):
        with patch.object(db, "get_settings", return_value=settings(ai_enabled=False)), \
                patch.object(db, "get_panel_overview", return_value=OV), patch.object(bot, "plan_of", return_value="pro"):
            text, _ = bot.build_panel(OWNER)
        self.assertRegex(text, r"Xabar: Oflaynman\n\n.*Funksiyalar holati\n")
        self.assertLess(text.index("Cooldown"), text.index(i18n.T["pnl_title"]["uz"]))


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class PanelOverviewDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.owner = 900_000_000 + int.from_bytes(os.urandom(3), "big")

    def test_counts_in_one_query(self):
        ov = db.get_panel_overview(self.owner)
        self.assertEqual(ov, dict.fromkeys(ov, 0) | {"inbox_enabled": False})
        db.add_faq_entry(self.owner, "Narx?", ["narx"], "100$", 10)
        db.add_faq_entry(self.owner, "Manzil?", ["manzil"], "Toshkent", 10)
        db.add_kb_entry(self.owner, "Biz", "Biz dizaynermiz", ["biz"], 10)
        cond = {"operator": "all", "items": [{"type": "keyword_contains", "value": "salom"}]}
        act = {"type": "send_reply", "text": "hi"}
        rid = db.add_automation_rule(self.owner, "r1", cond, act, 1, 10, enabled=True)
        db.add_automation_rule(self.owner, "r2", cond, act, 2, 10)
        db.set_inbox_settings(self.owner, enabled=True)
        ov = db.get_panel_overview(self.owner)
        self.assertEqual((ov["faq_total"], ov["faq_active"]), (2, 2))
        self.assertEqual((ov["kb_total"], ov["kb_active"]), (1, 1))
        self.assertEqual((ov["au_total"], ov["au_active"]), (2, 1))
        self.assertTrue(ov["inbox_enabled"])
        self.assertIsNotNone(rid)

    def test_other_owner_data_is_not_counted(self):
        db.add_faq_entry(self.owner + 1, "Q", ["q"], "A", 10)
        self.assertEqual(db.get_panel_overview(self.owner)["faq_total"], 0)


if __name__ == "__main__":
    unittest.main()
