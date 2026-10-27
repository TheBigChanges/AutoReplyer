"""Ko'p tillilik: /start'da til tanlash, tugmalar, menyular, standart avtojavob tili (db'siz)."""
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
import i18n  # noqa: E402

USER, INVITER = 9, 5


def run(coro):
    return asyncio.run(coro)


def _start_update():
    update = MagicMock()
    update.effective_user.id = USER
    update.effective_user.username = "x"
    update.effective_user.full_name = "X"
    update.message.reply_text = AsyncMock()
    return update


def _context(args=None):
    context = MagicMock()
    context.args = args or []
    context.bot.send_message = AsyncMock()
    return context


def _press(data):
    update = MagicMock()
    query = AsyncMock()
    query.data = data
    query.from_user.id = USER
    query.from_user.username = "x"
    query.from_user.full_name = "X"
    update.callback_query = query
    return update, query


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


class Base(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(db, "record_user"), patch.object(db, "get_connection", return_value=None)):
            p.start()
            self.addCleanup(p.stop)
        bot._lang_cache.clear()


class PickerTests(Base):
    def test_new_user_gets_three_languages_first(self):
        update = _start_update()
        with patch.object(bot, "has_chosen_lang", return_value=False):
            run(bot.cmd_start(update, _context()))
        kwargs = update.message.reply_text.call_args.kwargs
        self.assertEqual([b.callback_data for b in _buttons(kwargs["reply_markup"])], ["lang:uz", "lang:en", "lang:ru"])
        self.assertEqual([b.text for b in _buttons(kwargs["reply_markup"])], [i18n.LANG_NAMES[c] for c in i18n.LANGS])

    def test_referral_survives_language_step(self):
        update = _start_update()
        with patch.object(bot, "has_chosen_lang", return_value=False), patch.object(db, "record_referral") as rec:
            run(bot.cmd_start(update, _context([f"ref_{INVITER}"])))
        rec.assert_not_called()
        data = [b.callback_data for b in _buttons(update.message.reply_text.call_args.kwargs["reply_markup"])]
        self.assertEqual(data, [f"lang:uz:{INVITER}", f"lang:en:{INVITER}", f"lang:ru:{INVITER}"])

    def test_chosen_language_skips_picker(self):
        update = _start_update()
        with patch.object(bot, "is_subscribed", AsyncMock(return_value=True)):
            run(bot.cmd_start(update, _context()))
        self.assertEqual(update.message.reply_text.call_args.args[0], i18n.T["greeting_new"]["uz"])

    def test_choosing_language_saves_counts_referral_and_greets_in_it(self):
        update, query = _press(f"lang:ru:{INVITER}")
        with patch.object(db, "set_user_lang") as save, patch.object(bot, "is_subscribed", AsyncMock(return_value=True)), \
             patch.object(db, "record_referral", return_value=True) as rec:
            ctx = _context()
            run(bot.on_button(update, ctx))
        save.assert_called_once_with(USER, "ru")
        rec.assert_called_once_with(referred_user_id=USER, inviter_user_id=INVITER)
        query.answer.assert_awaited_once_with(i18n.T["lang_changed"]["ru"])
        self.assertEqual(query.edit_message_text.call_args.args[0], i18n.T["greeting_new"]["ru"])
        self.assertEqual(bot.get_lang(USER), "ru")

    def test_inviter_is_notified_in_their_own_language(self):
        with patch.object(db, "record_referral", return_value=True), patch.object(db, "get_user_lang", return_value="en"):
            ctx = _context()
            run(bot.process_referral(ctx.bot, USER, INVITER))
        self.assertEqual(ctx.bot.send_message.call_args.kwargs["text"], i18n.T["referral_joined"]["en"])

    def test_not_subscribed_after_choice_shows_gate_in_chosen_language(self):
        update, query = _press("lang:en")
        with patch.object(db, "set_user_lang"), patch.object(bot, "is_subscribed", AsyncMock(return_value=False)), \
             patch.object(bot, "REQUIRED_CHANNEL_LINK", "https://t.me/x"):
            run(bot.on_button(update, _context()))
        self.assertEqual(query.edit_message_text.call_args.args[0], i18n.T["gate_text"]["en"])
        checks = [b for b in _buttons(query.edit_message_text.call_args.kwargs["reply_markup"])]
        self.assertEqual(checks[1].text, i18n.T["gate_btn_check"]["en"])

    def test_invalid_language_code_rejected(self):
        update, query = _press("lang:xx")
        with patch.object(db, "set_user_lang") as save:
            run(bot.on_button(update, _context()))
        save.assert_not_called()
        self.assertTrue(query.answer.call_args.kwargs.get("show_alert"))

    def test_language_button_in_main_menu_opens_picker(self):
        markup = bot.main_menu_markup(USER)
        self.assertIn("lang_menu", [b.callback_data for b in _buttons(markup)])
        update, query = _press("lang_menu")
        run(bot.on_button(update, _context()))
        self.assertEqual(query.edit_message_text.call_args.args[0], i18n.T["lang_pick"]["uz"])
        self.assertEqual(len(_buttons(query.edit_message_text.call_args.kwargs["reply_markup"])), 3)

    def test_database_error_falls_back_to_uzbek_without_crash(self):
        with patch.object(db, "get_user_lang", side_effect=RuntimeError("db down")):
            self.assertEqual(bot.get_lang(USER), "uz")


class MenuLanguageTests(Base):
    def _settings(self, **kw):
        s = {"offline": True, "cooldown_hours": 2.5, "auto_reply_text": db.DEFAULT_AUTO_REPLY_TEXT,
             "sleep_mode_enabled": False, "sleep_start_minutes": 1380, "sleep_end_minutes": 420,
             "sleep_reply_text": bot.t("uz", "default_sleep"), "ai_enabled": False, "ai_info": None, "ai_role": None,
             "bio_countdown_target": None, "name_clock_enabled": False}
        s.update(kw)
        return s

    def test_panel_in_each_language(self):
        for lang, expect_cd, expect_btn in (("en", "2 h 30 min", "Change cooldown"), ("ru", "2 ч 30 мин", "Изменить"), ("uz", "2 soat 30 daqiqa", "Cooldown")):
            with patch.object(db, "get_user_lang", return_value=lang), patch.object(db, "get_settings", return_value=self._settings()):
                bot._lang_cache.clear()
                text, markup = bot.build_panel(USER)
                ar_text, ar_markup = bot.build_autoreply_menu(USER)
            self.assertIn(expect_cd, text, lang)
            self.assertIn(expect_cd, ar_text, lang)
            self.assertTrue(any("Auto-Reply" in b.text for b in _buttons(markup)), lang)
            self.assertTrue(any(expect_btn in b.text for b in _buttons(ar_markup)), lang)  # Cooldown tugmasi endi Auto-Reply bo'limida

    def test_default_auto_reply_follows_owner_language(self):
        s = self._settings()
        self.assertEqual(bot.auto_reply_text_for(s, "en"), i18n.T["default_auto_reply"]["en"])
        self.assertEqual(bot.auto_reply_text_for(s, "ru"), i18n.T["default_auto_reply"]["ru"])
        self.assertEqual(bot.auto_reply_text_for(self._settings(auto_reply_text=i18n.T["default_auto_reply"]["ru"]), "en"),
                         i18n.T["default_auto_reply"]["en"])
        self.assertEqual(bot.auto_reply_text_for(self._settings(auto_reply_text=""), "en"), i18n.T["default_auto_reply"]["en"])

    def test_custom_text_is_never_translated(self):
        s = self._settings(auto_reply_text="Men band, keyin yozaman", sleep_reply_text="Zzz")
        self.assertEqual(bot.auto_reply_text_for(s, "en"), "Men band, keyin yozaman")
        self.assertEqual(bot.sleep_text_for(s, "ru"), "Zzz")

    def test_default_sleep_follows_language(self):
        self.assertEqual(bot.sleep_text_for(self._settings(), "en"), i18n.T["default_sleep"]["en"])

    def test_zones_and_roles_menus_localized(self):
        with patch.object(db, "get_user_lang", return_value="ru"), patch.object(db, "get_settings", return_value=self._settings()):
            _, zm = bot.build_name_clock_zones_menu(USER)
            _, rm = bot.build_ai_roles_menu(USER)
        self.assertTrue(any("Ташкент" in b.text for b in _buttons(zm)))
        self.assertTrue(any(i18n.T["role_developer"]["ru"] in b.text for b in _buttons(rm)))

    def test_bio_menu_localized(self):
        conn = {"can_edit_bio": True, "is_enabled": True}
        s = self._settings(bio_countdown_target="new_year")
        with patch.object(db, "get_user_lang", return_value="en"), patch.object(db, "get_settings", return_value=s), \
             patch.object(db, "get_connection", return_value=conn):
            text, markup = bot.build_bio_menu(USER)
        self.assertIn("New Year", text)
        self.assertIn(i18n.T["btn_bio_navroz"]["en"], [b.text for b in _buttons(markup)])

    def test_help_and_block_notice_localized(self):
        notice, markup = bot.build_block_notice("spam", "ru")
        self.assertIn("spam", notice)
        self.assertEqual(_buttons(markup)[0].text, i18n.T["btn_appeal"]["ru"])
        notice_en, _ = bot.build_block_notice("", "en")
        self.assertNotIn("Sabab", notice_en)

    def test_support_view_localized(self):
        text, markup = bot.build_support_view("en")
        self.assertEqual(text, i18n.T["support_text"]["en"])
        self.assertEqual(_buttons(markup)[3].text, i18n.T["btn_back"]["en"])

    def test_feedback_replies_use_user_language(self):
        bot_ = MagicMock()
        user = MagicMock(id=USER, username="x", full_name="X")
        with patch.object(db, "get_user_lang", return_value="ru"), patch.object(db, "count_recent_feedback", return_value=99):
            reply = run(bot.submit_feedback(bot_, user, "hi"))
        self.assertEqual(reply, i18n.T["feedback_rate"]["ru"])

    def test_admin_reply_delivered_in_recipient_language(self):
        update = MagicMock()
        update.message.text = "Rahmat"
        update.message.reply_text = AsyncMock()
        ctx = _context()
        with patch.object(db, "get_user_lang", return_value="en"), patch.object(bot, "_try_send", AsyncMock(return_value=True)) as send:
            run(bot.send_feedback_reply(update, ctx, 77))
        self.assertEqual(send.call_args.args[2], i18n.T["admin_reply_to_user"]["en"].format(text="Rahmat"))


class AiLanguageTests(Base):
    def test_ai_gets_owner_language(self):
        bm = MagicMock(business_connection_id="bc")
        settings = {"cooldown_hours": 1, "ai_info": None, "ai_role": None}
        ctx = _context()
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch.object(db, "get_user_lang", return_value="ru"), patch.object(bot, "ai_reply_still_allowed", return_value=True), \
             patch.object(db, "get_ai_history", return_value=[]), patch.object(db, "get_user", return_value={"full_name": "Ali"}), \
             patch.object(db, "add_ai_messages"), patch.object(bot.ai, "generate_reply", AsyncMock(return_value="Привет")) as gen:
            run(bot.run_ai_reply(ctx.bot, bm, USER, 5, "hi", settings, "fallback", "x"))
        self.assertEqual(gen.call_args.kwargs["lang"], "ru")


if __name__ == "__main__":
    unittest.main()
