"""
Audit tuzatishlari uchun regressiya testlari:
  - uzun avtojavob/uxlash matni menyuni ochib bo'lmas qilmasligi (4096 belgi);
  - Jadval vaqti tahrirlashda to'qnashuvdan keyin kiritish qotib qolmasligi;
  - /bots faqat admin KO'RGAN yozuvlarni o'chirishi;
  - /blocked va referral statistikasi 4096 belgidan oshmasligi;
  - reklama: manba xabari yo'q bo'lsa job 'failed' bo'lishi; botni bloklaganlar retry'ga kirmasligi;
  - ID/referral argumentlarini tekshirish; ushlanmagan xatolar handleri; apellyatsiya spami.
"""

import asyncio
import os
import random
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
import i18n  # noqa: E402
from telegram.error import BadRequest, Forbidden  # noqa: E402

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
ADMIN = 777
USER = 9

SETTINGS = {
    "offline": True, "cooldown_hours": 3.0, "auto_reply_text": "eski",
    "sleep_mode_enabled": False, "sleep_start_minutes": 1380, "sleep_end_minutes": 420,
    "sleep_reply_text": "", "bio_countdown_target": None,
    "birthday_month": None, "birthday_day": None, "ai_enabled": False,
    "name_clock_tz": None,
}


def _text_update(text, user_id=USER):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "x"
    update.effective_user.full_name = "X"
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _clear_state():
    for d in (bot.pending_settings_action, bot._pending_settings_set_at,
              bot.pending_admin_action, bot._pending_admin_set_at, bot._sc_drafts,
              bot._bots_listed, bot.pending_appeal):
        d.clear()


class _Base(unittest.TestCase):
    def setUp(self):
        _clear_state()
        self.addCleanup(_clear_state)
        for patcher in (
            patch.object(bot, "ADMIN_ID", ADMIN),
            patch.object(db, "record_user"),
            patch.object(db, "get_name_clock_base", return_value=None),
            patch.object(db, "get_connection", return_value=None),
            patch.object(db, "get_user_plan", return_value="ultra"),
            patch.object(db, "get_onboarding_step", return_value="legacy"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)


# ---------------------------------------------------------------------------
# Matn uzunligi
# ---------------------------------------------------------------------------
class TestLongTextCannotBreakMenus(_Base):
    def test_too_long_auto_reply_text_is_rejected_and_pending_kept(self):
        bot.set_pending_action(USER, "text")
        update = _text_update("a" * (bot.AUTO_REPLY_MAX_TEXT + 1))
        with patch.object(db, "get_settings", return_value=dict(SETTINGS)), \
                patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_text(update, MagicMock()))
        upd.assert_not_called()
        update.message.reply_text.assert_awaited_once()
        self.assertEqual(bot.get_pending_action(USER), "text")  # foydalanuvchi qisqartirib qayta yuboradi

    def test_too_long_sleep_text_is_rejected(self):
        bot.set_pending_action(USER, "sleep_text")
        update = _text_update("b" * 3800)
        with patch.object(db, "get_settings", return_value=dict(SETTINGS)), \
                patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_text(update, MagicMock()))
        upd.assert_not_called()
        self.assertEqual(bot.get_pending_action(USER), "sleep_text")

    def test_text_at_the_limit_is_saved(self):
        bot.set_pending_action(USER, "text")
        update = _text_update("c" * bot.AUTO_REPLY_MAX_TEXT)
        with patch.object(db, "get_settings", return_value=dict(SETTINGS)), \
                patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_text(update, MagicMock()))
        upd.assert_called_once_with(USER, auto_reply_text="c" * bot.AUTO_REPLY_MAX_TEXT)

    def test_panel_and_sleep_menu_stay_under_telegram_limit_with_old_huge_text(self):
        huge = dict(SETTINGS, auto_reply_text="x" * 4000, sleep_reply_text="y" * 4000)
        with patch.object(db, "get_settings", return_value=huge):
            panel_text, _ = bot.build_panel(USER)
            sleep_text, _ = bot.build_sleep_menu(USER)
        self.assertLessEqual(len(panel_text), 4096)
        self.assertLessEqual(len(sleep_text), 4096)


# ---------------------------------------------------------------------------
# Jadval: to'qnashuvdan keyin kiritish qotib qolmasligi
# ---------------------------------------------------------------------------
class TestSchedulerConflictKeepsTimeInput(_Base):
    def test_conflict_on_time_edit_rearms_pending_time_input(self):
        bot._sc_new_draft(USER, edit_id=5, stage="time")
        bot.clear_pending_action(USER)  # tugma bosilganda on_button shuni qiladi
        message = MagicMock()
        message.reply_text = AsyncMock()
        with patch.object(db, "update_schedule_rule", return_value=("conflict", 2)):
            asyncio.run(bot._sc_after_time(message, USER, "uz", 600, 720))
        self.assertEqual(bot.get_pending_action(USER), "sc_time")
        message.reply_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Kirish argumentlarini tekshirish
# ---------------------------------------------------------------------------
class TestInputValidation(_Base):
    def test_referral_arg(self):
        self.assertEqual(bot.parse_referral_arg(["ref_12345"]), 12345)
        self.assertIsNone(bot.parse_referral_arg(["ref_" + "9" * 60]))   # tugma 64 baytdan oshib ketardi
        self.assertIsNone(bot.parse_referral_arg(["ref_" + "9" * 16]))
        self.assertIsNone(bot.parse_referral_arg(["ref_²"]))        # Unicode raqam
        self.assertIsNone(bot.parse_referral_arg(["ref_0"]))
        self.assertIsNone(bot.parse_referral_arg(["ref_-5"]))
        self.assertIsNone(bot.parse_referral_arg(["ref_1 2"]))

    def test_resolve_target_user_rejects_weird_and_oversized_ids(self):
        for raw in ("²", "٣٢", "9" * 20):
            user_id, error = asyncio.run(bot.resolve_target_user(MagicMock(), raw))
            self.assertIsNone(user_id, raw)
            self.assertTrue(error)
        user_id, error = asyncio.run(bot.resolve_target_user(MagicMock(), "123456"))
        self.assertEqual((user_id, error), (123456, None))


class TestSplitForTelegram(unittest.TestCase):
    def test_chunks_fit_and_lose_nothing(self):
        text = "\n".join(f"{i}. " + "q" * 120 for i in range(200))
        chunks = bot.split_for_telegram(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 4000 for c in chunks))
        self.assertEqual("\n".join(chunks), text)

    def test_single_giant_line_is_hard_cut(self):
        chunks = bot.split_for_telegram("z" * 9000)
        self.assertTrue(all(len(c) <= 4000 for c in chunks))
        self.assertEqual("".join(chunks), "z" * 9000)

    def test_short_text_is_one_chunk(self):
        self.assertEqual(bot.split_for_telegram("salom"), ["salom"])


# ---------------------------------------------------------------------------
# Admin ro'yxatlari
# ---------------------------------------------------------------------------
class TestAdminListsStayUnderLimit(_Base):
    def test_blocked_list_with_long_reasons_is_split(self):
        rows = [
            {"user_id": 1000 + i, "username": f"user{i}", "full_name": "N" * 40,
             "reason": "r" * 300, "blocked_at": time.time()}
            for i in range(30)
        ]
        update = _text_update("/blocked", user_id=ADMIN)
        with patch.object(db, "list_blocked", return_value=rows), patch.object(db, "count_blocked", return_value=30):
            asyncio.run(bot.cmd_blocked(update, MagicMock()))
        sent = [call.args[0] for call in update.message.reply_text.await_args_list]
        self.assertTrue(sent)
        self.assertTrue(all(len(s) <= 4096 for s in sent))
        self.assertIn("1000", "".join(sent))
        self.assertIn("1029", "".join(sent))  # hech kim yo'qolmagan

    def test_admin_referral_view_is_limited(self):
        rows = [(5000 + i, 100 - i) for i in range(100)]
        with patch.object(db, "get_all_referral_counts", return_value=rows), \
                patch.object(bot, "_display_name_for", new=AsyncMock(return_value="@someone_with_a_long_name")):
            text, _ = asyncio.run(bot.build_admin_referrals_view(MagicMock()))
        self.assertLessEqual(len(text), 4096)
        self.assertIn(f"yana {100 - bot.ADMIN_REFERRALS_LIMIT} ta", text)


class TestBotsCleanupOnlyDeletesWhatAdminSaw(_Base):
    def _rows(self, n):
        return [{"user_id": 100 + i, "username": f"spam{i}bot", "full_name": "A & B <x>"} for i in range(n)]

    def test_confirm_deletes_only_listed_ids(self):
        update = _text_update("/bots", user_id=ADMIN)
        with patch.object(db, "list_bot_like_users", return_value=self._rows(3)):
            asyncio.run(bot.cmd_bots(update, MagicMock()))
        text = update.message.reply_text.await_args.args[0]
        self.assertNotIn("&amp;", text)  # parse_mode yo'q — qo'shimcha escape ko'rinib qolmasin
        self.assertLessEqual(len(text), 4096)

        query = AsyncMock()
        query.from_user.id = ADMIN
        with patch.object(db, "delete_bot_like_users", return_value=3) as delete:
            asyncio.run(bot.handle_rmbots(query, MagicMock(), "rmbots:yes"))
        delete.assert_called_once_with([100, 101, 102])

    def test_confirm_without_a_fresh_listing_deletes_nothing(self):
        query = AsyncMock()
        query.from_user.id = ADMIN
        with patch.object(db, "delete_bot_like_users") as delete:
            asyncio.run(bot.handle_rmbots(query, MagicMock(), "rmbots:yes"))
        delete.assert_not_called()

    def test_expired_listing_deletes_nothing(self):
        bot._bots_listed[ADMIN] = ([1, 2], time.time() - bot.BOTS_CONFIRM_TTL_SECONDS - 1)
        query = AsyncMock()
        query.from_user.id = ADMIN
        with patch.object(db, "delete_bot_like_users") as delete:
            asyncio.run(bot.handle_rmbots(query, MagicMock(), "rmbots:yes"))
        delete.assert_not_called()

    def test_non_admin_cannot_confirm(self):
        bot._bots_listed[ADMIN] = ([1, 2], time.time())
        query = AsyncMock()
        query.from_user.id = 31337
        with patch.object(db, "delete_bot_like_users") as delete:
            asyncio.run(bot.handle_rmbots(query, MagicMock(), "rmbots:yes"))
        delete.assert_not_called()


# ---------------------------------------------------------------------------
# Reklama
# ---------------------------------------------------------------------------
def _run_job(copy_side_effect, user_ids):
    fake_bot = AsyncMock()
    fake_bot.copy_message = AsyncMock(side_effect=copy_side_effect)
    batches = [list(user_ids), []]
    with patch.object(db, "get_user_ids_after", side_effect=lambda last, limit=200: batches.pop(0) if batches else []), \
            patch.object(db, "record_broadcast_failure") as record, \
            patch.object(db, "update_broadcast_progress"), \
            patch.object(db, "set_broadcast_status") as status, \
            patch.object(db, "get_broadcast_failed_user_ids", return_value=[]), \
            patch.object(bot.asyncio, "sleep", new=AsyncMock()):
        asyncio.run(bot.run_broadcast_job(fake_bot, 1, 10, 20, reply_to_chat_id=ADMIN))
    return fake_bot, record, status


class TestBroadcastSourceMissing(unittest.TestCase):
    def test_deleted_source_message_fails_the_job_instead_of_completing(self):
        fake_bot, _, status = _run_job(BadRequest("Message to copy not found"), range(1, 21))
        status.assert_called_once_with(1, "failed")
        self.assertLessEqual(fake_bot.copy_message.await_count, bot.BROADCAST_MAX_SOURCE_ERRORS)
        text = fake_bot.send_message.await_args.kwargs["text"]
        self.assertIn("topilmadi", text)

    def test_ordinary_per_user_bad_request_does_not_abort(self):
        fake_bot, _, status = _run_job(BadRequest("Chat not found"), range(1, 21))
        status.assert_called_once_with(1, "completed")
        self.assertEqual(fake_bot.copy_message.await_count, 20)

    def test_blocked_users_are_recorded_as_non_retryable(self):
        fake_bot, record, status = _run_job(Forbidden("bot was blocked by the user"), [1, 2, 3])
        status.assert_called_once_with(1, "completed")
        self.assertEqual({c.args[2] for c in record.call_args_list}, {db.NON_RETRYABLE_FAILURE})
        self.assertNotIn("/reklama_retry", fake_bot.send_message.await_args.kwargs["text"])

    def test_success_resets_the_source_error_streak(self):
        side_effect = [BadRequest("Message to copy not found")] * 4 + [None] + [BadRequest("Message to copy not found")] * 4
        fake_bot, _, status = _run_job(side_effect, range(1, 10))
        status.assert_called_once_with(1, "completed")


class TestCmdReklamaClearsPanelAction(_Base):
    def test_pending_panel_action_is_cleared(self):
        bot.set_pending_action(ADMIN, "feedback")
        update = _text_update("/reklama", user_id=ADMIN)
        with patch.object(bot, "_reject_if_broadcast_already_running", new=AsyncMock(return_value=False)):
            asyncio.run(bot.cmd_reklama(update, MagicMock()))
        self.assertIsNone(bot.get_pending_action(ADMIN))
        self.assertEqual(bot.get_pending_admin_action(ADMIN), "broadcast")


# ---------------------------------------------------------------------------
# Apellyatsiya spami va xato handleri
# ---------------------------------------------------------------------------
class TestAppealPromptNotSpammable(_Base):
    def test_second_press_while_pending_sends_nothing(self):
        sent = AsyncMock(return_value=True)
        with patch.object(bot, "_try_send", new=sent), patch.object(db, "count_recent_appeals", return_value=0):
            asyncio.run(bot._begin_appeal(MagicMock(), 55))
            asyncio.run(bot._begin_appeal(MagicMock(), 55))
            asyncio.run(bot._begin_appeal(MagicMock(), 55))
        self.assertEqual(sent.await_count, 1)

    def test_prompt_is_sent_again_after_ttl(self):
        sent = AsyncMock(return_value=True)
        with patch.object(bot, "_try_send", new=sent), patch.object(db, "count_recent_appeals", return_value=0):
            asyncio.run(bot._begin_appeal(MagicMock(), 56))
            bot.pending_appeal[56] = time.time() - bot.APPEAL_PENDING_TTL_SECONDS - 1
            asyncio.run(bot._begin_appeal(MagicMock(), 56))
        self.assertEqual(sent.await_count, 2)


class TestErrorHandler(unittest.TestCase):
    def test_not_modified_is_silent_other_errors_are_logged(self):
        ctx = MagicMock()
        ctx.error = BadRequest("Message is not modified: specified new message content is exactly the same")
        with patch.object(bot.logger, "error") as log:
            asyncio.run(bot.on_error(None, ctx))
            log.assert_not_called()
            ctx.error = RuntimeError("boom")
            asyncio.run(bot.on_error(None, ctx))
            log.assert_called_once()

    def test_error_handler_is_registered(self):
        with patch.object(bot, "BOT_TOKEN", "123:dummy"):
            app = bot.build_app()
        self.assertIn(bot.on_error, app.error_handlers)


# ---------------------------------------------------------------------------
# Eskirgan tugmalar: Bilimlar bazasi o'chirish, FAQ/KB qoralamalari, jadval o'chirish tasdig'i
# ---------------------------------------------------------------------------
class _PanelBase(_Base):
    def setUp(self):
        super().setUp()
        bot._kb_del_confirms.clear()
        bot._sc_del_confirms.clear()
        bot._faq_drafts.clear()
        bot._kb_drafts.clear()
        self.addCleanup(bot._kb_del_confirms.clear)
        self.addCleanup(bot._sc_del_confirms.clear)
        self.addCleanup(bot._faq_drafts.clear)
        self.addCleanup(bot._kb_drafts.clear)
        self.settings = dict(SETTINGS, faq_enabled=True, kb_enabled=True)
        self.mocks = {}
        for name, kwargs in (
            ("get_settings", {"side_effect": lambda owner: dict(self.settings)}),
            ("update_settings", {}),
            ("count_faq_entries", {"return_value": 0}),
            ("count_kb_entries", {"return_value": 0}),
            ("list_faq_entries", {"return_value": []}),
            ("list_kb_entries", {"return_value": []}),
            ("add_faq_entry", {"return_value": 1}),
            ("add_kb_entry", {"return_value": 1}),
            ("delete_kb_entry", {"return_value": True}),
            ("get_kb_entry", {"side_effect": lambda owner, i: {
                "id": i, "owner_user_id": owner, "title": f"T{i}", "content": "C", "keywords": [], "is_enabled": True}}),
            ("get_faq_entry", {"side_effect": lambda owner, i: {
                "id": i, "owner_user_id": owner, "question": "Q", "keywords": ["k"], "answer": "A", "is_enabled": True}}),
            ("set_faq_entry_enabled", {"return_value": True}),
            ("set_kb_entry_enabled", {"return_value": True}),
            ("toggle_faq_entry", {"return_value": True}),
            ("toggle_kb_entry", {"return_value": True}),
        ):
            patcher = patch.object(db, name, **kwargs)
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (patch.object(bot, "track_user"), patch.object(bot.ai, "is_configured", return_value=True)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def press(self, data, user=USER):
        q = MagicMock()
        q.data = data
        q.from_user.id = user
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        update = MagicMock()
        update.callback_query = q
        asyncio.run(bot.on_button(update, MagicMock()))
        return q

    def say(self, text, user=USER):
        update = _text_update(text, user)
        asyncio.run(bot.on_text(update, MagicMock()))
        return update.message.reply_text

    @staticmethod
    def shown(q):
        return q.edit_message_text.await_args.args[0]

    @staticmethod
    def datas(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]


class TestKnowledgeDeleteConfirmationIsOneTime(_PanelBase):
    STALE = "eskirgan"

    def _open_confirm(self, entry_id=5):
        q = self.press(f"kb_del:{entry_id}")
        return self.datas(q.edit_message_text.await_args.kwargs["reply_markup"])[0]

    def test_fresh_confirmation_deletes_once_and_cannot_be_replayed(self):
        yes = self._open_confirm()
        self.assertRegex(yes, r"^kb_del_yes:5:[0-9a-f]{6}$")
        self.press(yes)
        self.mocks["delete_kb_entry"].assert_called_once_with(USER, 5)
        q = self.press(yes)  # ikkinchi bosish
        self.mocks["delete_kb_entry"].assert_called_once()
        self.assertIn(self.STALE, self.shown(q))

    def test_legacy_button_without_token_does_nothing(self):
        self._open_confirm()
        q = self.press("kb_del_yes:5")
        self.mocks["delete_kb_entry"].assert_not_called()
        self.assertIn(self.STALE, self.shown(q))

    def test_old_confirmation_is_dead_after_user_goes_to_edit(self):
        yes = self._open_confirm()
        self.press("kb_edit:t:5")  # fikridan qaytib tahrirlashga o'tdi
        self.press("kb_view:5")
        q = self.press(yes)  # eski «Ha, o'chirish»
        self.mocks["delete_kb_entry"].assert_not_called()
        self.assertIn(self.STALE, self.shown(q))

    def test_token_of_one_entry_cannot_delete_another(self):
        yes = self._open_confirm(5)
        self.press(yes.replace("kb_del_yes:5:", "kb_del_yes:6:"))
        self.mocks["delete_kb_entry"].assert_not_called()

    def test_expired_confirmation_does_nothing(self):
        yes = self._open_confirm()
        bot._kb_del_confirms[USER]["ts"] -= bot.PENDING_ACTION_TTL_SECONDS + 1
        self.press(yes)
        self.mocks["delete_kb_entry"].assert_not_called()

    def test_stale_press_keeps_the_live_confirmation(self):
        old_yes = self._open_confirm(5)
        new_yes = self._open_confirm(5)  # yangi tasdiq eskisini almashtiradi
        self.assertNotEqual(old_yes, new_yes)
        self.press(old_yes)
        self.mocks["delete_kb_entry"].assert_not_called()
        self.press(new_yes)  # joriy tasdiq hamon ishlaydi
        self.mocks["delete_kb_entry"].assert_called_once_with(USER, 5)

    def test_start_and_cancel_clear_a_pending_confirmation(self):
        yes = self._open_confirm()
        self.assertTrue(bot.clear_scheduler_state(USER))
        self.press(yes)
        self.mocks["delete_kb_entry"].assert_not_called()


class TestSchedulerDeleteConfirmationStaleButton(_PanelBase):
    def setUp(self):
        super().setUp()
        for patcher in (
            patch.object(bot, "_sc_entry_text", side_effect=lambda owner, rid: ("1", "Jadval", {"id": rid})),
            patch.object(bot, "build_sched_menu", side_effect=lambda owner, notice=None, page=0: (notice or "menu", None)),
            patch.object(db, "delete_schedule_rule", return_value=True),
        ):
            self.addCleanup(patcher.stop)
            patcher.start()

    def _open(self, rule_id):
        q = self.press(f"sc_del:{rule_id}")
        return self.datas(q.edit_message_text.await_args.kwargs["reply_markup"])[0]

    def test_stale_yes_does_not_cancel_the_new_confirmation(self):
        old_yes = self._open(1)
        new_yes = self._open(2)  # yangi tasdiq eskisining o'rniga ochildi
        q = self.press(old_yes)
        self.assertIn("eskirgan", self.shown(q))
        self.assertEqual(bot._sc_del_confirms[USER]["rule_id"], 2)  # yangisi tirik
        self.press(new_yes)
        db.delete_schedule_rule.assert_called_once_with(USER, 2)

    def test_stale_yes_does_not_interrupt_typing_a_schedule_time_or_text(self):
        old_yes = self._open(1)
        self._open(2)
        bot.set_pending_action(USER, "sc_text")
        self.press(old_yes)
        self.assertEqual(bot.get_pending_action(USER), "sc_text")

    def test_forged_yes_buttons_delete_nothing(self):
        self._open(1)
        for forged in ("sc_del_yes:1", "sc_del_yes:1:zzzzzz", "sc_del_yes:abc:zzzzzz", "sc_del_yes:", "sc_del_yes:1:2:3"):
            self.press(forged)
        db.delete_schedule_rule.assert_not_called()
        self.assertIn(USER, bot._sc_del_confirms)  # haqiqiy tasdiq buzilmadi


class TestDraftSaveCancelAreBoundToTheirDraft(_PanelBase):
    def _faq_confirm_buttons(self, q="Savol?", kw="kalit", ans="Javob"):
        self.press("faq_add")
        self.say(q)
        self.say(kw)
        reply = self.say(ans)
        return self.datas(reply.await_args.kwargs["reply_markup"])  # [save, cancel]

    def _kb_confirm_buttons(self, title="Sarlavha", content="Matn", kw="-"):
        self.press("kb_add")
        self.say(title)
        self.say(content)
        reply = self.say(kw)
        return self.datas(reply.await_args.kwargs["reply_markup"])

    def test_faq_old_save_cannot_save_or_destroy_the_new_draft(self):
        old_save, old_cancel = self._faq_confirm_buttons("Eski savol?", "eski", "Eski javob")
        new_save, new_cancel = self._faq_confirm_buttons("Yangi savol?", "yangi", "Yangi javob")
        self.assertNotEqual(old_save, new_save)
        q = self.press(old_save)
        self.mocks["add_faq_entry"].assert_not_called()
        self.assertIn("eskirgan", self.shown(q))
        self.assertEqual(bot._faq_drafts[USER]["q"], "Yangi savol?")      # yangi qoralama joyida
        self.assertEqual(bot.get_pending_action(USER), "faq_confirm")     # kutilayotgan holat buzilmadi
        self.press(old_cancel)
        self.assertIn(USER, bot._faq_drafts)                               # eski «Bekor qilish» yangisini o'chirmaydi
        self.press(new_save)
        self.mocks["add_faq_entry"].assert_called_once()
        self.assertEqual(self.mocks["add_faq_entry"].call_args.args[1], "Yangi savol?")

    def test_faq_own_cancel_discards_and_then_save_is_dead(self):
        save, cancel = self._faq_confirm_buttons()
        self.press(cancel)
        self.assertNotIn(USER, bot._faq_drafts)
        self.press(save)
        self.mocks["add_faq_entry"].assert_not_called()

    def test_kb_old_save_cannot_save_or_destroy_the_new_draft(self):
        old_save, old_cancel = self._kb_confirm_buttons("Eski", "Eski matn")
        new_save, new_cancel = self._kb_confirm_buttons("Yangi", "Yangi matn")
        self.assertNotEqual(old_save, new_save)
        q = self.press(old_save)
        self.mocks["add_kb_entry"].assert_not_called()
        self.assertIn("eskirgan", self.shown(q))
        self.assertEqual(bot._kb_drafts[USER]["title"], "Yangi")
        self.assertEqual(bot.get_pending_action(USER), "kb_confirm")
        self.press(old_cancel)
        self.assertIn(USER, bot._kb_drafts)
        self.press(new_save)
        self.mocks["add_kb_entry"].assert_called_once()
        self.assertEqual(self.mocks["add_kb_entry"].call_args.args[1], "Yangi")

    def test_legacy_tokenless_buttons_are_stale(self):
        self._faq_confirm_buttons()
        self._kb_confirm_buttons()
        for data in ("faq_save", "kb_save", "faq_cancel", "kb_cancel"):
            self.press(data)
        self.mocks["add_faq_entry"].assert_not_called()
        self.mocks["add_kb_entry"].assert_not_called()
        self.assertIn(USER, bot._faq_drafts)
        self.assertIn(USER, bot._kb_drafts)

    def test_cancel_without_any_draft_is_harmless(self):
        q = self.press("faq_cancel")  # menyuga qaytadi, yiqilmaydi
        self.assertIn(i18n.t("uz", "faq_cancelled"), self.shown(q))


class TestExplicitOnOffButtons(_PanelBase):
    def test_settings_buttons_are_explicit_and_idempotent(self):
        for off, on, field in (("faq_off", "faq_on", "faq_enabled"), ("kb_off", "kb_on", "kb_enabled")):
            self.mocks["update_settings"].reset_mock()
            self.press(off)
            self.press(off)  # eski xabardagi tugma qayta bosildi
            self.assertEqual(self.mocks["update_settings"].call_args_list, [((USER,), {field: False})] * 2)
            self.mocks["update_settings"].reset_mock()
            self.press(on)
            self.press(on)
            self.assertEqual(self.mocks["update_settings"].call_args_list, [((USER,), {field: True})] * 2)

    def test_ai_buttons_are_explicit_and_idempotent(self):
        self.press("ai_off")
        self.press("ai_off")
        self.press("ai_on")
        self.press("ai_on")
        self.assertEqual(
            [c.kwargs for c in self.mocks["update_settings"].call_args_list],
            [{"ai_enabled": False}, {"ai_enabled": False}, {"ai_enabled": True}, {"ai_enabled": True}],
        )

    def test_ai_on_still_requires_configuration(self):
        with patch.object(bot.ai, "is_configured", return_value=False):
            q = self.press("ai_on")
        self.mocks["update_settings"].assert_not_called()
        self.assertIn("GEMINI_API_KEY", self.shown(q))

    def test_entry_buttons_are_explicit_and_idempotent(self):
        for off, on, mock in (
            ("faq_entry_off", "faq_entry_on", self.mocks["set_faq_entry_enabled"]),
            ("kb_entry_off", "kb_entry_on", self.mocks["set_kb_entry_enabled"]),
        ):
            self.press(f"{off}:7")
            self.press(f"{off}:7")
            self.press(f"{on}:7")
            self.assertEqual(mock.call_args_list, [((USER, 7, False),), ((USER, 7, False),), ((USER, 7, True),)])

    def test_legacy_toggle_buttons_change_nothing(self):
        for data in ("faq_toggle", "kb_toggle", "ai_toggle", "faq_entry_toggle:7", "kb_entry_toggle:7"):
            q = self.press(data)
            self.assertTrue(q.edit_message_text.await_count, data)  # joriy holatni ko'rsatadi, yiqilmaydi
        self.mocks["update_settings"].assert_not_called()
        for name in ("set_faq_entry_enabled", "set_kb_entry_enabled", "toggle_faq_entry", "toggle_kb_entry"):
            self.mocks[name].assert_not_called()

    def test_menus_carry_the_explicit_action_for_the_current_state(self):
        for enabled, faq_expected, kb_expected in ((True, "faq_off", "kb_off"), (False, "faq_on", "kb_on")):
            self.settings.update(faq_enabled=enabled, kb_enabled=enabled)
            self.assertIn(faq_expected, self.datas(bot.build_faq_settings(USER)[1]))
            self.assertIn(kb_expected, self.datas(bot.build_kb_settings(USER)[1]))
        self.settings.update(ai_enabled=True)
        self.assertIn("ai_off", self.datas(bot.build_ai_menu(USER)[1]))
        self.settings.update(ai_enabled=False)
        self.assertIn("ai_on", self.datas(bot.build_ai_menu(USER)[1]))
        entry = {"id": 3, "owner_user_id": USER, "question": "Q", "keywords": ["k"], "answer": "A"}
        self.mocks["get_faq_entry"].side_effect = lambda o, i: dict(entry, is_enabled=True)
        self.assertIn("faq_entry_off:3", self.datas(bot.build_faq_entry(USER, 3)[1]))
        self.mocks["get_faq_entry"].side_effect = lambda o, i: dict(entry, is_enabled=False)
        self.assertIn("faq_entry_on:3", self.datas(bot.build_faq_entry(USER, 3)[1]))
        kb = {"id": 4, "owner_user_id": USER, "title": "T", "content": "C", "keywords": []}
        self.mocks["get_kb_entry"].side_effect = lambda o, i: dict(kb, is_enabled=True)
        self.assertIn("kb_entry_off:4", self.datas(bot.build_kb_entry(USER, 4)[1]))
        self.mocks["get_kb_entry"].side_effect = lambda o, i: dict(kb, is_enabled=False)
        self.assertIn("kb_entry_on:4", self.datas(bot.build_kb_entry(USER, 4)[1]))

    def test_new_buttons_are_plan_gated_like_the_old_ones(self):
        for data in ("faq_on", "faq_off", "faq_entry_on:1", "faq_entry_off:1", "kb_on", "kb_off", "kb_entry_on:1",
                     "kb_entry_off:1", "ai_on", "ai_off"):
            self.assertIn(bot.locked_feature_for(data), ("faq", "kb", "ai"), data)


# ---------------------------------------------------------------------------
# HAQIQIY Postgres
# ---------------------------------------------------------------------------
@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan — haqiqiy Postgres testlari o'tkazib yuborildi")
class TestDbOnRealPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.base = random.randint(10**12, 9 * 10**12)
        self.ids = [self.base + i for i in range(4)]
        self.job_id = random.randint(10**8, 2 * 10**9)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id = ANY(%s)", (self.ids,))
            cur.execute("DELETE FROM broadcast_failures WHERE job_id = %s", (self.job_id,))

    def test_delete_bot_like_users_with_ids_touches_only_those(self):
        for i, uid in enumerate(self.ids):
            db.record_user(uid, username=f"zz{self.base}_{i}bot", full_name="T")
        deleted = db.delete_bot_like_users(self.ids[:2])
        self.assertEqual(deleted, 2)
        self.assertIsNone(db.get_user(self.ids[0]))
        self.assertIsNone(db.get_user(self.ids[1]))
        self.assertIsNotNone(db.get_user(self.ids[2]))
        self.assertIsNotNone(db.get_user(self.ids[3]))

    def test_delete_with_ids_still_requires_bot_like_username(self):
        db.record_user(self.ids[0], username=f"zz{self.base}human", full_name="T")
        self.assertEqual(db.delete_bot_like_users([self.ids[0]]), 0)
        self.assertIsNotNone(db.get_user(self.ids[0]))

    def test_entry_setters_are_idempotent_and_owner_scoped(self):
        owner, other = self.ids[0], self.ids[1]
        faq_id = db.add_faq_entry(owner, "Q", ["k"], "A", 20)
        kb_id = db.add_kb_entry(owner, "T", "C", [], 55)
        self.addCleanup(lambda: [db.delete_faq_entry(owner, faq_id), db.delete_kb_entry(owner, kb_id)])
        for _ in range(2):
            self.assertTrue(db.set_faq_entry_enabled(owner, faq_id, False))
            self.assertFalse(db.get_faq_entry(owner, faq_id)["is_enabled"])
            self.assertTrue(db.set_kb_entry_enabled(owner, kb_id, False))
            self.assertFalse(db.get_kb_entry(owner, kb_id)["is_enabled"])
        self.assertTrue(db.set_faq_entry_enabled(owner, faq_id, True))
        self.assertTrue(db.set_kb_entry_enabled(owner, kb_id, True))
        self.assertTrue(db.get_faq_entry(owner, faq_id)["is_enabled"])
        self.assertTrue(db.get_kb_entry(owner, kb_id)["is_enabled"])
        # boshqa egasining yozuviga tegib bo'lmaydi
        self.assertFalse(db.set_faq_entry_enabled(other, faq_id, False))
        self.assertFalse(db.set_kb_entry_enabled(other, kb_id, False))
        self.assertTrue(db.get_faq_entry(owner, faq_id)["is_enabled"])
        self.assertTrue(db.get_kb_entry(owner, kb_id)["is_enabled"])

    def test_retry_lists_skip_blocked_and_deleted_accounts(self):
        db.record_broadcast_failure(self.job_id, self.ids[0], db.NON_RETRYABLE_FAILURE)
        db.record_broadcast_failure(self.job_id, self.ids[1], "Timed out")
        db.record_broadcast_failure(self.job_id, self.ids[2], "Bad Request: chat not found")
        self.assertEqual(sorted(db.get_broadcast_failed_user_ids(self.job_id)), [self.ids[1], self.ids[2]])
        self.assertEqual(db.get_failed_user_ids_after(self.job_id, 0, limit=50), [self.ids[1], self.ids[2]])


if __name__ == "__main__":
    unittest.main()
