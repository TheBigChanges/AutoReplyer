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

    def test_retry_lists_skip_blocked_and_deleted_accounts(self):
        db.record_broadcast_failure(self.job_id, self.ids[0], db.NON_RETRYABLE_FAILURE)
        db.record_broadcast_failure(self.job_id, self.ids[1], "Timed out")
        db.record_broadcast_failure(self.job_id, self.ids[2], "Bad Request: chat not found")
        self.assertEqual(sorted(db.get_broadcast_failed_user_ids(self.job_id)), [self.ids[1], self.ids[2]])
        self.assertEqual(db.get_failed_user_ids_after(self.job_id, 0, limit=50), [self.ids[1], self.ids[2]])


if __name__ == "__main__":
    unittest.main()
