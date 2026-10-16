"""Smart Onboarding: baza (holatlar, himoya), bosqichlar, tugmalar, ulanish hodisasi, statistika, 3 til."""
import asyncio
import os
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
import i18n  # noqa: E402

run = asyncio.run
ADMIN = 777
_REAL_START_VIEW = bot.onboarding_start_view  # conftest uni o'chiradi; shu yerda qaytariladi
_REAL_ON_CONNECTION = bot.onboarding_view_on_connection


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL kerak")
class OnboardingBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.u = random.randint(10**14, 10**15)
        self.addCleanup(self._cleanup)
        for name, real in (("onboarding_start_view", _REAL_START_VIEW), ("onboarding_view_on_connection", _REAL_ON_CONNECTION)):
            p = patch.object(bot, name, real)
            p.start()
            self.addCleanup(p.stop)
        bot._lang_cache.pop(self.u, None)
        db.record_user(self.u)  # yangi foydalanuvchi -> 'welcome'

    def _cleanup(self):
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id = %s", (self.u,))
            cur.execute("DELETE FROM settings WHERE owner_user_id = %s", (self.u,))
            cur.execute("DELETE FROM connections WHERE owner_user_id = %s", (self.u,))
        bot._lang_cache.pop(self.u, None)

    def connect(self, enabled=True, can_reply=True):
        db.upsert_connection(self.u, f"bc{self.u}", can_reply, enabled, False, False)

    def press(self, data):
        q = MagicMock()
        q.data = data
        q.from_user.id = self.u
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        u = MagicMock()
        u.callback_query = q
        with patch.object(bot, "track_user"):
            run(bot.on_button(u, MagicMock()))
        return q

    def step(self):
        return db.get_onboarding_step(self.u)


class DbTests(OnboardingBase):
    def test_new_user_starts_at_welcome_and_missing_user_is_legacy(self):
        self.assertEqual(self.step(), "welcome")
        self.assertEqual(db.get_onboarding_step(self.u + 12345), "legacy")

    def test_existing_rows_stay_legacy_after_repeated_init(self):
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("UPDATE users SET onboarding_step = 'legacy' WHERE user_id = %s", (self.u,))
        db.init_db()
        self.assertEqual(self.step(), "legacy")

    def test_set_step_and_timestamps(self):
        self.assertTrue(db.set_onboarding_step(self.u, "connect"))
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("SELECT onboarding_started_at, onboarding_completed_at FROM users WHERE user_id=%s", (self.u,))
            started, completed = cur.fetchone()
        self.assertIsNotNone(started)
        self.assertIsNone(completed)
        db.set_onboarding_step(self.u, "completed")
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("SELECT onboarding_started_at, onboarding_completed_at FROM users WHERE user_id=%s", (self.u,))
            started2, completed2 = cur.fetchone()
        self.assertEqual(started, started2)
        self.assertIsNotNone(completed2)

    def test_welcome_does_not_set_started_at(self):
        db.set_onboarding_step(self.u, "welcome")
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("SELECT onboarding_started_at FROM users WHERE user_id=%s", (self.u,))
            self.assertIsNone(cur.fetchone()[0])

    def test_only_from_guard_protects_legacy(self):
        db.set_onboarding_step(self.u, "legacy")
        self.assertFalse(db.set_onboarding_step(self.u, "connect", only_from=("welcome",)))
        self.assertEqual(self.step(), "legacy")

    def test_invalid_step_rejected(self):
        with self.assertRaises(ValueError):
            db.set_onboarding_step(self.u, "hack'; DROP TABLE users;--")

    def test_stats_counts_this_user(self):
        before = db.onboarding_stats()
        self.connect()
        db.update_settings(self.u, offline=True)
        db.set_onboarding_step(self.u, "verify")
        mid = db.onboarding_stats()
        self.assertEqual(mid["started"], before["started"] + 1)
        self.assertEqual(mid["connected"], before["connected"] + 1)
        self.assertEqual(mid["auto_reply_on"], before["auto_reply_on"] + 1)
        self.assertEqual(mid["in_progress"], before["in_progress"] + 1)
        db.set_onboarding_step(self.u, "completed")
        after = db.onboarding_stats()
        self.assertEqual(after["completed"], before["completed"] + 1)
        self.assertEqual(after["in_progress"], before["in_progress"])
        db.set_onboarding_step(self.u, "skipped")
        self.assertEqual(db.onboarding_stats()["skipped"], before["skipped"] + 1)


class StartViewTests(OnboardingBase):
    def test_welcome_user_gets_connect_screen_with_bot_username(self):
        text, markup = bot.onboarding_start_view(self.u)
        self.assertIn("1/3", text)
        self.assertIn(bot.BOT_USERNAME, text)
        self.assertIn(i18n.t("uz", "ob_welcome").strip(), text)
        datas = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertEqual(datas, ["ob_check", "ob_skip"])
        self.assertEqual(self.step(), "connect")

    def test_resume_has_no_welcome_prefix(self):
        bot.onboarding_start_view(self.u)
        text, _ = bot.onboarding_start_view(self.u)
        self.assertNotIn(i18n.t("uz", "ob_welcome").strip(), text)
        self.assertIn("1/3", text)

    def test_legacy_completed_skipped_see_no_onboarding(self):
        for step in ("legacy", "completed", "skipped"):
            db.set_onboarding_step(self.u, step)
            self.assertIsNone(bot.onboarding_start_view(self.u), step)

    def test_connected_user_goes_straight_to_configure_or_verify(self):
        self.connect()
        text, _ = bot.onboarding_start_view(self.u)
        self.assertIn("2/3", text)
        self.assertEqual(self.step(), "configure")
        db.update_settings(self.u, offline=True)
        text, _ = bot.onboarding_start_view(self.u)
        self.assertIn("3/3", text)
        self.assertEqual(self.step(), "verify")

    def test_disconnect_returns_to_connect(self):
        self.connect()
        bot.onboarding_start_view(self.u)
        self.connect(enabled=False)
        text, _ = bot.onboarding_start_view(self.u)
        self.assertIn("1/3", text)
        self.assertEqual(self.step(), "connect")

    def test_run_start_flow_shows_onboarding_then_normal_menu_after_skip(self):
        sent = []

        async def send(text, markup):
            sent.append(text)

        with patch.object(bot, "is_subscribed", AsyncMock(return_value=True)), \
                patch.object(bot, "process_referral", AsyncMock()):
            run(bot.run_start_flow(MagicMock(), self.u, None, send))
            self.assertIn("1/3", sent[-1])
            db.set_onboarding_step(self.u, "skipped")
            run(bot.run_start_flow(MagicMock(), self.u, None, send))
            self.assertEqual(sent[-1], i18n.t("uz", "greeting_new"))

    def test_subscription_gate_comes_before_onboarding(self):
        sent = []

        async def send(text, markup):
            sent.append(text)

        with patch.object(bot, "is_subscribed", AsyncMock(return_value=False)):
            run(bot.run_start_flow(MagicMock(), self.u, None, send))
        self.assertEqual(sent, [i18n.t("uz", "gate_text")])
        self.assertEqual(self.step(), "welcome")  # hali boshlanmagan

    def test_configure_plan_note_free_vs_paid(self):
        self.connect()
        with patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)):
            with patch.object(db, "get_user_plan", return_value="free"):
                text, _ = bot.build_onboarding_view(self.u, "configure")
                self.assertIn(i18n.t("uz", "ob_plan_free"), text)
            with patch.object(db, "get_user_plan", return_value="plus"):
                text, _ = bot.build_onboarding_view(self.u, "configure")
                self.assertIn(i18n.t("uz", "ob_plan_paid"), text)

    def test_all_screens_render_in_all_languages(self):
        self.connect()
        for lang in i18n.LANGS:
            bot.set_lang(self.u, lang)
            for step in ("connect", "configure", "verify"):
                text, markup = bot.build_onboarding_view(self.u, step, welcome=True)
                self.assertTrue(text)
                self.assertNotIn("{", text)
                self.assertTrue(markup.inline_keyboard)


class ButtonTests(OnboardingBase):
    def alerted(self, q):
        return q.answer.call_args.kwargs.get("show_alert") is True

    def test_check_without_connection_alerts_and_keeps_step(self):
        bot.onboarding_start_view(self.u)
        q = self.press("ob_check")
        self.assertTrue(self.alerted(q))
        self.assertEqual(q.answer.call_args.args[0], i18n.t("uz", "ob_not_connected"))
        q.edit_message_text.assert_not_called()
        self.assertEqual(self.step(), "connect")

    def test_check_without_reply_permission_alerts(self):
        bot.onboarding_start_view(self.u)
        self.connect(can_reply=False)
        q = self.press("ob_check")
        self.assertEqual(q.answer.call_args.args[0], i18n.t("uz", "ob_no_reply_perm"))
        self.assertEqual(self.step(), "connect")

    def test_full_happy_path(self):
        bot.onboarding_start_view(self.u)
        self.connect()
        q = self.press("ob_check")
        self.assertIn("2/3", q.edit_message_text.call_args.args[0])
        self.assertEqual(self.step(), "configure")
        self.assertFalse(db.get_settings(self.u)["offline"])
        q = self.press("ob_enable")
        self.assertTrue(db.get_settings(self.u)["offline"])
        self.assertEqual(self.step(), "verify")
        self.assertIn("3/3", q.edit_message_text.call_args.args[0])
        self.assertEqual(q.answer.call_count, 1)
        q = self.press("ob_ok")
        self.assertEqual(self.step(), "completed")
        self.assertEqual(q.edit_message_text.call_args.args[0], i18n.t("uz", "ob_done"))
        datas = [b.callback_data for r in q.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard for b in r]
        self.assertIn("open_panel", datas)

    def test_fail_shows_diagnosis_and_keeps_verify(self):
        self.connect()
        db.update_settings(self.u, offline=True, sleep_mode_enabled=True, cooldown_hours=2.0)
        bot.onboarding_start_view(self.u)  # verify
        q = self.press("ob_fail")
        text = q.edit_message_text.call_args.args[0]
        self.assertIn("❌", i18n.t("uz", "ob_fail", checks="❌ x", hours="2", sleep=""))
        self.assertIn("2 soatda", text)
        self.assertIn("Sleep Mode", text)
        self.assertEqual(self.step(), "verify")
        datas = [b.callback_data for r in q.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard for b in r]
        self.assertEqual(datas, ["ob_ok", "ob_fail", "ob_skip"])

    def test_fail_marks_missing_pieces(self):
        self.connect()
        db.update_settings(self.u, offline=True)
        bot.onboarding_start_view(self.u)  # verify
        self.connect(can_reply=False)  # ruxsat olib tashlandi
        q = self.press("ob_fail")
        text = q.edit_message_text.call_args.args[0]
        self.assertIn("✅ " + i18n.t("uz", "ob_chk_connected"), text)
        self.assertIn("❌ " + i18n.t("uz", "ob_chk_reply"), text)

    def test_repeated_fail_press_ignores_not_modified(self):
        from telegram.error import BadRequest
        self.connect()
        db.update_settings(self.u, offline=True)
        bot.onboarding_start_view(self.u)  # verify
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock(side_effect=BadRequest("Message is not modified"))
        run(bot.handle_onboarding_callback(q, self.u, "ob_fail"))  # yiqilmasligi kerak

    def test_ok_requires_verify_step(self):
        self.connect()
        bot.onboarding_start_view(self.u)  # configure
        q = self.press("ob_ok")
        self.assertTrue(self.alerted(q))
        self.assertEqual(self.step(), "configure")

    def test_enable_not_allowed_at_connect_step(self):
        bot.onboarding_start_view(self.u)
        q = self.press("ob_enable")
        self.assertTrue(self.alerted(q))
        self.assertFalse(db.get_settings(self.u)["offline"])

    def test_skip_then_resume(self):
        bot.onboarding_start_view(self.u)
        q = self.press("ob_skip")
        self.assertEqual(self.step(), "skipped")
        self.assertEqual(q.edit_message_text.call_args.args[0], i18n.t("uz", "ob_skipped"))
        datas = [b.callback_data for r in q.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard for b in r]
        self.assertIn("ob_resume", datas)
        q = self.press("ob_resume")
        self.assertEqual(self.step(), "connect")
        self.assertIn("1/3", q.edit_message_text.call_args.args[0])

    def test_resume_button_only_for_skipped(self):
        for step in ("welcome", "legacy", "completed", "connect"):
            db.set_onboarding_step(self.u, step)
            datas = [b.callback_data for r in bot.main_menu_markup(self.u).inline_keyboard for b in r]
            self.assertNotIn("ob_resume", datas, step)
        db.set_onboarding_step(self.u, "skipped")
        datas = [b.callback_data for r in bot.main_menu_markup(self.u).inline_keyboard for b in r]
        self.assertIn("ob_resume", datas)

    def test_stale_and_invalid_callbacks_are_rejected(self):
        for step in ("legacy", "completed"):
            db.set_onboarding_step(self.u, step)
            for data in ("ob_check", "ob_enable", "ob_ok", "ob_fail", "ob_skip", "ob_resume"):
                q = self.press(data)
                self.assertTrue(self.alerted(q), (step, data))
                q.edit_message_text.assert_not_called()
            self.assertEqual(self.step(), step)
        db.set_onboarding_step(self.u, "connect")
        for data in ("ob_", "ob_xyz", "ob_check:1"):
            q = self.press(data)
            self.assertTrue(self.alerted(q), data)
        self.assertEqual(self.step(), "connect")

    def test_buttons_work_in_other_languages(self):
        for lang in ("en", "ru"):
            bot.set_lang(self.u, lang)
            db.set_onboarding_step(self.u, "connect")
            q = self.press("ob_check")
            self.assertEqual(q.answer.call_args.args[0], i18n.t(lang, "ob_not_connected"))


class ConnectionEventTests(OnboardingBase):
    def test_connection_moves_new_user_to_configure(self):
        self.connect()
        text, markup = bot.onboarding_view_on_connection(self.u)
        self.assertIn("2/3", text)
        self.assertEqual(self.step(), "configure")
        self.assertIsNone(bot.onboarding_view_on_connection(self.u))  # o'zgarish yo'q -> oddiy xabar

    def test_legacy_and_finished_users_unaffected(self):
        self.connect()
        for step in ("legacy", "completed", "skipped"):
            db.set_onboarding_step(self.u, step)
            self.assertIsNone(bot.onboarding_view_on_connection(self.u), step)
            self.assertEqual(self.step(), step)

    def test_connection_without_reply_permission_keeps_plain_message(self):
        db.set_onboarding_step(self.u, "connect")
        self.connect(can_reply=False)
        self.assertIsNone(bot.onboarding_view_on_connection(self.u))

    def test_business_connection_update_sends_onboarding_screen(self):
        bc = MagicMock()
        bc.id = f"bc{self.u}"
        bc.user.id = self.u
        bc.user_chat_id = self.u
        bc.is_enabled = True
        bc.can_reply = True
        bc.rights = MagicMock(can_edit_bio=False, can_edit_name=False)
        upd = MagicMock()
        upd.business_connection = bc
        upd.business_message = None
        upd.edited_business_message = None
        upd.deleted_business_messages = None
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock()
        run(bot.on_raw_update(upd, ctx))
        kwargs = ctx.bot.send_message.call_args.kwargs
        self.assertIn("2/3", kwargs["text"])
        self.assertIsNotNone(kwargs["reply_markup"])
        self.assertEqual(self.step(), "configure")

    def test_disconnect_event_sends_back_to_connect(self):
        self.connect()
        bot.onboarding_start_view(self.u)
        bc = MagicMock()
        bc.id = f"bc{self.u}"
        bc.user.id = self.u
        bc.user_chat_id = self.u
        bc.is_enabled = False
        bc.can_reply = False
        bc.rights = None
        upd = MagicMock()
        upd.business_connection = bc
        upd.business_message = None
        upd.edited_business_message = None
        upd.deleted_business_messages = None
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock()
        run(bot.on_raw_update(upd, ctx))
        self.assertEqual(self.step(), "connect")
        self.assertEqual(ctx.bot.send_message.call_args.kwargs["text"], i18n.t("uz", "disconnected"))


class AdminCommandTests(OnboardingBase):
    def cmd(self, user):
        u = MagicMock()
        u.effective_user = MagicMock(id=user)
        u.message.reply_text = AsyncMock()
        with patch.object(bot, "ADMIN_ID", ADMIN):
            run(bot.cmd_onboarding(u, MagicMock()))
        return u.message.reply_text

    def test_non_admin_gets_nothing(self):
        self.cmd(self.u).assert_not_called()

    def test_admin_gets_statistics(self):
        reply = self.cmd(ADMIN)
        text = reply.call_args.args[0]
        for part in ("Onboarding Statistics", "Boshlaganlar", "Telegram ulaganlar", "Auto-Reply yoqqanlar", "Tugatganlar"):
            self.assertIn(part, text)

    def test_listed_in_admin_help(self):
        self.assertIn("/onboarding", bot.ADMIN_HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
