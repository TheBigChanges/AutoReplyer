"""Aniq (idempotent) holat tugmalari: Onlayn/Oflayn va Uxlash rejimi. Eski xabardagi tugma qayta bosilsa holat
teskarilanmaydi (Scheduler'dagi Pauza/Davom ettirish va yoqish/o'chirish kabi)."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402

USER = 9


def _settings(**kw):
    base = {"offline": False, "cooldown_hours": 3.0, "auto_reply_text": "x", "sleep_mode_enabled": False,
            "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "", "bio_countdown_target": None,
            "birthday_month": None, "birthday_day": None, "ai_enabled": False, "name_clock_tz": None}
    base.update(kw)
    return base


class StateButtonTests(unittest.TestCase):
    def setUp(self):
        self.state = _settings()

        def update_settings(owner, **fields):
            self.state.update(fields)

        for p in (
            patch.object(db, "record_user"),
            patch.object(db, "get_connection", return_value=None),
            patch.object(db, "get_settings", side_effect=lambda owner: dict(self.state)),
            patch.object(db, "update_settings", side_effect=update_settings),
        ):
            p.start()
            self.addCleanup(p.stop)
        bot.pending_settings_action.clear()

    def press(self, data):
        q = AsyncMock()
        q.data = data
        q.from_user.id = USER
        q.from_user.username = "x"
        q.from_user.full_name = "X"
        u = MagicMock()
        u.callback_query = q
        asyncio.run(bot.on_button(u, MagicMock()))
        return q

    @staticmethod
    def callbacks(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    # ---- Onlayn / Oflayn
    def test_offline_online_are_idempotent(self):
        self.press("status_offline")
        self.press("status_offline")
        self.assertTrue(self.state["offline"])
        self.press("status_online")
        self.press("status_online")
        self.assertFalse(self.state["offline"])

    def test_legacy_toggle_status_changes_nothing(self):
        self.press("toggle_status")
        self.assertFalse(self.state["offline"])
        self.state["offline"] = True
        self.press("toggle_status")
        self.assertTrue(self.state["offline"])

    def test_panel_button_matches_state(self):
        self.assertIn("status_offline", self.callbacks(bot.build_panel(USER)[1]))
        self.state["offline"] = True
        cbs = self.callbacks(bot.build_panel(USER)[1])
        self.assertIn("status_online", cbs)
        self.assertNotIn("status_offline", cbs)

    # ---- Uxlash rejimi
    def test_sleep_enable_disable_are_idempotent(self):
        self.press("sleep_enable")
        self.press("sleep_enable")
        self.assertTrue(self.state["sleep_mode_enabled"])
        self.press("sleep_disable")
        self.press("sleep_disable")  # eski «O'chirish» tugmasi qayta bosildi — yana yoqilib qolmaydi
        self.assertFalse(self.state["sleep_mode_enabled"])

    def test_legacy_sleep_toggle_changes_nothing(self):
        self.press("sleep_toggle")
        self.assertFalse(self.state["sleep_mode_enabled"])
        self.state["sleep_mode_enabled"] = True
        self.press("sleep_toggle")
        self.assertTrue(self.state["sleep_mode_enabled"])

    def test_sleep_menu_button_matches_state(self):
        def cb():
            return [c for c in self.callbacks(bot.build_sleep_menu(USER)[1]) if c.startswith("sleep_") and "toggle" not in c and c in ("sleep_enable", "sleep_disable")]
        self.assertEqual(cb(), ["sleep_enable"])
        self.state["sleep_mode_enabled"] = True
        self.assertEqual(cb(), ["sleep_disable"])

    def test_buttons_refresh_the_view(self):
        q = self.press("sleep_enable")
        q.edit_message_text.assert_awaited()
        q = self.press("status_offline")
        q.edit_message_text.assert_awaited()


if __name__ == "__main__":
    unittest.main()
