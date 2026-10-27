"""Panel: 🚀 Auto-Reply bo'limi — Cooldown, Xabar matni, Uxlayapman rejimi va avtojavobni yoqish/o'chirish bitta joyda."""
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
from i18n import t  # noqa: E402

ADMIN, USER = 777, 9
LOCK = "\U0001F512"


class Base(unittest.TestCase):
    plan = "plus"

    def setUp(self):
        for d in (bot.pending_settings_action, bot._pending_settings_set_at):
            d.clear()
        self.settings = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
                         "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "", "faq_enabled": True,
                         "kb_enabled": True, "ai_enabled": False, "ai_info": None, "ai_role": None, "lang": "uz"}
        self.updates = []

        def update(owner, **kw):
            self.updates.append(kw)
            self.settings.update(kw)

        for p in (
            patch.object(bot, "ADMIN_ID", ADMIN),
            patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)),
            patch.object(db, "get_user_plan", side_effect=lambda uid: self.plan),
            patch.object(db, "get_settings", side_effect=lambda owner: dict(self.settings)),
            patch.object(db, "update_settings", side_effect=update),
            patch.object(db, "record_user"),
            patch.object(db, "get_name_clock_base", return_value=None),
            patch.object(db, "get_connection", return_value={"is_enabled": True, "can_reply": True}),
            patch.object(db, "get_onboarding_step", return_value="legacy"),
            patch.object(db, "count_faq_entries", return_value=0),
            patch.object(db, "count_kb_entries", return_value=0),
            patch.object(db, "count_automation_rules", return_value=0),
            patch.object(bot, "track_user"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def press(self, data):
        q = MagicMock()
        q.data = data
        q.from_user.id = USER
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        update = MagicMock()
        update.callback_query = q
        asyncio.run(bot.on_button(update, MagicMock()))
        return q

    def say(self, text):
        update = MagicMock()
        update.effective_user.id = USER
        update.effective_user.username = "x"
        update.effective_user.full_name = "X"
        update.message.text = text
        update.message.reply_text = AsyncMock()
        asyncio.run(bot.on_text(update, MagicMock()))
        return update.message.reply_text

    @staticmethod
    def datas(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    def shown_markup(self, q):
        return q.edit_message_text.await_args.kwargs["reply_markup"]


class MainPanelTests(Base):
    def test_one_autoreply_button_replaces_the_three(self):
        text, markup = bot.build_panel(USER)
        datas = self.datas(markup)
        self.assertIn("ar_menu", datas)
        for moved in ("edit_cooldown", "edit_text", "sleep_menu"):
            self.assertNotIn(moved, datas)
        button = next(b for row in markup.inline_keyboard for b in row if b.callback_data == "ar_menu")
        self.assertEqual(button.text, "\U0001F680 Auto-Reply")
        self.assertEqual(datas.count("ar_menu"), 1)

    def test_other_buttons_kept(self):
        _, markup = bot.build_panel(USER)
        datas = self.datas(markup)
        for kept in ("bio_menu", "ai_menu", "faq_menu", "kb_menu", "au_menu", "sc_menu", "an_menu", "back"):
            self.assertIn(kept, datas, kept)
        self.assertTrue({"status_online", "status_offline"} & set(datas))


class MenuTests(Base):
    def test_opens_with_all_controls(self):
        q = self.press("ar_menu")
        self.assertEqual(self.datas(self.shown_markup(q)), ["ar_off", "edit_cooldown", "edit_text", "sleep_menu", "open_panel"])
        text = q.edit_message_text.await_args.args[0]
        self.assertIn("3 soat", text)
        self.assertIn("Oflaynman", text)

    def test_toggle_button_reflects_state(self):
        self.settings["offline"] = False
        q = self.press("ar_menu")
        self.assertEqual(self.datas(self.shown_markup(q))[0], "ar_on")

    def test_back_goes_to_panel(self):
        q = self.press("open_panel")
        self.assertIn("ar_menu", self.datas(self.shown_markup(q)))

    def test_works_for_every_plan(self):
        for plan in ("free", "plus", "pro", "ultra"):
            self.plan = plan
            q = self.press("ar_menu")
            self.assertIn("edit_cooldown", self.datas(self.shown_markup(q)), plan)

    def test_message_text_locked_for_free_only(self):
        self.plan = "free"
        q = self.press("ar_menu")
        markup = self.shown_markup(q)
        locked = {b.callback_data for row in markup.inline_keyboard for b in row if b.text.startswith(LOCK)}
        self.assertEqual(locked, {"edit_text"})


class OnOffTests(Base):
    def test_off_then_on_explicit_and_idempotent(self):
        q = self.press("ar_off")
        self.assertFalse(self.settings["offline"])
        self.assertEqual(self.datas(self.shown_markup(q))[0], "ar_on")
        self.press("ar_off")  # eski tugma qayta bosildi — holat teskarilanmaydi
        self.assertFalse(self.settings["offline"])
        q = self.press("ar_on")
        self.assertTrue(self.settings["offline"])
        self.assertEqual(self.datas(self.shown_markup(q))[0], "ar_off")
        self.press("ar_on")
        self.assertTrue(self.settings["offline"])

    def test_only_offline_flag_changes(self):
        self.press("ar_off")
        self.assertEqual(self.updates, [{"offline": False}])

    def test_main_panel_toggle_still_works(self):
        self.press("status_online")
        self.assertFalse(self.settings["offline"])
        self.press("status_offline")
        self.assertTrue(self.settings["offline"])


class CooldownAndTextTests(Base):
    def test_cooldown_flow_returns_to_autoreply_menu(self):
        self.press("edit_cooldown")
        self.assertEqual(bot.get_pending_action(USER), "cooldown")
        reply = self.say("2")
        self.assertEqual(self.settings["cooldown_hours"], 2.0)
        self.assertIsNone(bot.get_pending_action(USER))
        markup = reply.await_args.kwargs["reply_markup"]
        self.assertEqual(self.datas(markup)[0], "ar_off")

    def test_bad_cooldown_keeps_waiting(self):
        self.press("edit_cooldown")
        reply = self.say("abc")
        self.assertEqual(reply.await_args.args[0], t("uz", "cooldown_bad"))
        self.assertEqual(bot.get_pending_action(USER), "cooldown")
        self.assertEqual(self.settings["cooldown_hours"], 3.0)

    def test_text_flow_returns_to_autoreply_menu(self):
        self.press("edit_text")
        self.assertEqual(bot.get_pending_action(USER), "text")
        reply = self.say("Hozir band, keyin yozaman")
        self.assertEqual(self.settings["auto_reply_text"], "Hozir band, keyin yozaman")
        self.assertEqual(self.datas(reply.await_args.kwargs["reply_markup"])[0], "ar_off")
        self.assertIn("Hozir band", reply.await_args.args[0])

    def test_free_cannot_change_text(self):
        self.plan = "free"
        q = self.press("edit_text")
        self.assertIsNone(bot.get_pending_action(USER))
        self.assertIn(t("uz", "feature_text"), q.edit_message_text.await_args.args[0])
        self.assertEqual(self.settings["auto_reply_text"], "Oflaynman")

    def test_free_can_change_cooldown(self):
        self.plan = "free"
        self.press("edit_cooldown")
        self.say("1")
        self.assertEqual(self.settings["cooldown_hours"], 1.0)


class SleepInsideTests(Base):
    def test_sleep_reachable_and_back_returns_to_autoreply(self):
        q = self.press("sleep_menu")
        self.assertEqual(self.datas(self.shown_markup(q))[-1], "ar_menu")

    def test_sleep_enable_still_works_and_shows_in_menu(self):
        self.press("sleep_enable")
        self.assertTrue(self.settings["sleep_mode_enabled"])
        q = self.press("ar_menu")
        self.assertIn(t("uz", "panel_sleep_on"), q.edit_message_text.await_args.args[0])

    def test_sleep_time_save_returns_to_sleep_menu(self):
        self.press("sleep_edit_time")
        reply = self.say("22:00-06:00")
        self.assertEqual(self.datas(reply.await_args.kwargs["reply_markup"])[-1], "ar_menu")


class LanguageTests(Base):
    def test_every_language_renders(self):
        for lang in ("uz", "en", "ru"):
            self.settings["lang"] = lang
            with patch.object(db, "get_user_lang", return_value=lang):
                bot._lang_cache.clear()
                text, markup = bot.build_autoreply_menu(USER)
            self.assertIn("Auto-Reply", text)
            self.assertNotIn("{", text, lang)
        bot._lang_cache.clear()


if __name__ == "__main__":
    unittest.main()
