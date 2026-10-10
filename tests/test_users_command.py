"""/users buyrug'i, eski foydalanuvchilar profilini to'ldirish va /block @username qidiruvi."""

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
from telegram.error import BadRequest, Forbidden, NetworkError  # noqa: E402
from telegram.ext import CommandHandler, MessageHandler  # noqa: E402

ADMIN = 777


def run(coro):
    return asyncio.run(coro)


def row(uid, username=None, full_name=None, blocked=False, first_seen=1_700_000_000.0):
    return {"user_id": uid, "username": username, "full_name": full_name,
            "first_seen": first_seen, "is_blocked": blocked, "block_reason": None}


class Base(unittest.TestCase):
    def setUp(self):
        p = patch.object(bot, "ADMIN_ID", ADMIN)
        p.start()
        self.addCleanup(p.stop)
        bot._profile_backfill_running = False


class ViewTests(Base):
    def test_lists_everyone_with_marks_and_escapes_html(self):
        rows = [row(1, "ali", "Ali <b>"), row(2, None, None, blocked=True), row(3, None, "Vali")]
        text, markup = bot.build_users_view(0, 3, 1, rows)
        self.assertIn("3 ta", text)
        self.assertIn("@ali", text)
        self.assertIn("Ali &lt;b&gt;", text)
        self.assertNotIn("<b>Ali", text)
        self.assertIn("\U0001F6AB", text)
        self.assertIn("<code>2</code>", text)
        self.assertIn("ism noma'lum", text)
        self.assertIsNone(markup)

    def test_pagination_buttons(self):
        n = bot.USERS_PAGE_SIZE * 2 + 1
        _, m0 = bot.build_users_view(0, n, 0, [])
        _, m1 = bot.build_users_view(1, n, 0, [])
        _, m2 = bot.build_users_view(2, n, 0, [])
        data = lambda m: [b.callback_data for b in m.inline_keyboard[0]]
        self.assertEqual(data(m0), ["users:1"])
        self.assertEqual(data(m1), ["users:0", "users:2"])
        self.assertEqual(data(m2), ["users:1"])

    def test_page_out_of_range_is_clamped(self):
        text, _ = bot.build_users_view(99, 3, 0, [row(1)])
        self.assertIn("Sahifa 1/1", text)

    def test_cmd_users_admin_only(self):
        u = MagicMock()
        u.effective_user.id = 5
        u.message.reply_text = AsyncMock()
        run(bot.cmd_users(u, MagicMock()))
        u.message.reply_text.assert_not_called()

    def test_cmd_users_sends_html(self):
        u = MagicMock()
        u.effective_user.id = ADMIN
        u.message.reply_text = AsyncMock()
        with patch.object(db, "get_user_count", return_value=1), \
             patch.object(db, "count_blocked", return_value=0), \
             patch.object(db, "get_users_page", return_value=[row(1, "ali", "Ali")]), \
             patch.object(db, "get_users_needing_info", return_value=[]):
            run(bot.cmd_users(u, MagicMock(bot=MagicMock())))
        self.assertEqual(u.message.reply_text.call_args.kwargs["parse_mode"], "HTML")
        self.assertIn("@ali", u.message.reply_text.call_args.args[0])

    def test_page_button_answered_once_and_non_admin_rejected(self):
        q = MagicMock()
        q.from_user.id = 5
        q.answer = AsyncMock()
        run(bot.handle_users_page(q, MagicMock(), "users:1"))
        q.answer.assert_awaited_once()
        self.assertTrue(q.answer.call_args.kwargs.get("show_alert"))

        q = MagicMock()
        q.from_user.id = ADMIN
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        with patch.object(bot, "render_users_page", return_value=("t", None)):
            run(bot.handle_users_page(q, MagicMock(), "users:1"))
        q.answer.assert_awaited_once()
        q.edit_message_text.assert_awaited_once()


class BackfillTests(Base):
    def test_refresh_saves_username_and_name(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(return_value=MagicMock(username="ali", full_name="Ali V"))
        with patch.object(db, "set_user_info") as s:
            self.assertTrue(run(bot._refresh_profile(tg, 5)))
        s.assert_called_once_with(5, "ali", "Ali V")

    def test_forbidden_marks_checked(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(side_effect=Forbidden("blocked"))
        with patch.object(db, "mark_user_info_checked") as m:
            self.assertFalse(run(bot._refresh_profile(tg, 5)))
        m.assert_called_once_with(5)

    def test_network_error_not_marked_in_refresh(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(side_effect=NetworkError("x"))
        with patch.object(db, "mark_user_info_checked") as m:
            self.assertFalse(run(bot._refresh_profile(tg, 5)))
        m.assert_not_called()

    def test_backfill_processes_batches_until_empty_and_marks_failures(self):
        batches = [[1, 2], [3], []]
        tg = MagicMock()
        tg.get_chat = AsyncMock(side_effect=[MagicMock(username="a", full_name="A"),
                                             BadRequest("gone"), NetworkError("x")])
        with patch.object(db, "get_users_needing_info", side_effect=batches), \
             patch.object(db, "set_user_info"), \
             patch.object(db, "mark_user_info_checked") as m, \
             patch.object(bot.asyncio, "sleep", new=AsyncMock()):
            tried, ok = run(bot.backfill_profiles(tg))
        self.assertEqual((tried, ok), (3, 1))
        self.assertEqual({c.args[0] for c in m.call_args_list}, {2, 3})
        self.assertFalse(bot._profile_backfill_running)

    def test_backfill_respects_max_users(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(return_value=MagicMock(username=None, full_name="A"))
        with patch.object(db, "get_users_needing_info", return_value=[1, 2, 3]) as g, \
             patch.object(db, "set_user_info"), \
             patch.object(bot.asyncio, "sleep", new=AsyncMock()):
            tried, _ = run(bot.backfill_profiles(tg, max_users=3))
        self.assertEqual(tried, 3)
        self.assertEqual(g.call_args.args[0], 3)

    def test_second_run_is_noop_while_running(self):
        bot._profile_backfill_running = True
        self.assertEqual(run(bot.backfill_profiles(MagicMock())), (0, 0))
        self.assertTrue(bot._profile_backfill_running)


class ResolveOldUserTests(Base):
    def test_old_user_found_after_backfill(self):
        tg = MagicMock()
        with patch.object(db, "get_user_id_by_username", side_effect=[None, 42]), \
             patch.object(db, "get_users_needing_info", return_value=[42]), \
             patch.object(bot, "backfill_profiles", new=AsyncMock(return_value=(1, 1))) as bf:
            self.assertEqual(run(bot.resolve_target_user(tg, "@old_user")), (42, None))
        bf.assert_awaited_once()

    def test_no_backfill_when_nothing_pending(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(side_effect=BadRequest("x"))
        with patch.object(db, "get_user_id_by_username", return_value=None), \
             patch.object(db, "get_users_needing_info", return_value=[]), \
             patch.object(bot, "backfill_profiles", new=AsyncMock()) as bf:
            uid, err = run(bot.resolve_target_user(tg, "@nobody1"))
        bf.assert_not_awaited()
        self.assertIsNone(uid)
        self.assertIn("topilmadi", err)

    def test_backfill_error_does_not_break_block(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(side_effect=BadRequest("x"))
        with patch.object(db, "get_user_id_by_username", return_value=None), \
             patch.object(db, "get_users_needing_info", side_effect=RuntimeError("db")):
            uid, err = run(bot.resolve_target_user(tg, "@nobody1"))
        self.assertIsNone(uid)
        self.assertIn("topilmadi", err)


class WiringTests(Base):
    def test_handlers_and_jobs_registered(self):
        app = bot.build_app()
        handlers = [h for hs in app.handlers.values() for h in hs]
        self.assertTrue(any(isinstance(h, CommandHandler) and "users" in h.commands for h in handlers))
        self.assertTrue(any(isinstance(h, MessageHandler) and h.callback is bot.on_other_message for h in handlers))
        if app.job_queue is not None:
            names = [j.callback.__name__ for j in app.job_queue.jobs()]
            self.assertIn("profile_backfill_job", names)

    def test_admin_help_lists_users(self):
        self.assertIn("/users", bot.ADMIN_HELP_TEXT)

    def test_other_message_tracks_user(self):
        u = MagicMock()
        with patch.object(bot, "track_user") as t:
            run(bot.on_other_message(u, MagicMock()))
        t.assert_called_once_with(u.effective_user)


if __name__ == "__main__":
    unittest.main()
