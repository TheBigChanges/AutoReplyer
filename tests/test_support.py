"""Qo'llab-quvvatlash xizmati: tugma, 3 ta ichki tugma va fikr/taklif oqimi."""

import asyncio
import os
import random
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402

ADMIN = 777
USER = 55


def run(coro):
    return asyncio.run(coro)


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


class Base(unittest.TestCase):
    def setUp(self):
        p = patch.object(bot, "ADMIN_ID", ADMIN)
        p.start()
        self.addCleanup(p.stop)
        bot.pending_settings_action.clear()
        self.addCleanup(bot.pending_settings_action.clear)


class MenuTests(Base):
    def test_main_menu_has_support_button(self):
        with patch.object(db, "get_connection", return_value=None):
            markup = bot.main_menu_markup(USER)
        self.assertIn("support", [b.callback_data for b in _buttons(markup)])

    def test_support_view_has_three_actions(self):
        text, markup = bot.build_support_view()
        btns = _buttons(markup)
        urls = [b.url for b in btns if b.url]
        self.assertEqual(urls, ["https://t.me/+P_Uv4zsFGE03NmI6", "https://t.me/MyAndro1d"])
        self.assertIn("support_feedback", [b.callback_data for b in btns])
        self.assertIn("Savolingiz", text)

    def test_panel_has_no_support_buttons(self):
        import inspect

        src = inspect.getsource(bot.build_panel)
        self.assertNotIn("support", src)


def _query(data, user_id=USER):
    q = MagicMock()
    q.data = data
    q.from_user.id = user_id
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


class ButtonFlowTests(Base):
    def test_support_button_opens_menu(self):
        u, q = _query("support")
        with patch.object(bot, "track_user"):
            run(bot.on_button(u, MagicMock()))
        q.answer.assert_awaited_once()
        self.assertIn("Qo'llab-quvvatlash", q.edit_message_text.call_args.args[0])

    def test_feedback_button_sets_pending_and_asks(self):
        u, q = _query("support_feedback")
        with patch.object(bot, "track_user"):
            run(bot.on_button(u, MagicMock()))
        q.answer.assert_awaited_once()
        self.assertEqual(bot.get_pending_action(USER), "feedback")
        q.message.reply_text.assert_awaited_once()


def _text_update(text, user_id=USER):
    u = MagicMock()
    u.effective_user = MagicMock(id=user_id, username="ali", full_name="Ali", is_bot=False)
    u.message.text = text
    u.message.reply_text = AsyncMock()
    return u


class FeedbackTests(Base):
    def test_feedback_forwarded_to_admin_and_saved(self):
        tg = MagicMock()
        tg.send_message = AsyncMock()
        bot.set_pending_action(USER, "feedback")
        u = _text_update("Bot juda yaxshi!")
        with patch.object(bot, "track_user"), patch.object(db, "count_recent_feedback", return_value=0), \
             patch.object(db, "add_feedback") as add:
            run(bot.on_text(u, MagicMock(bot=tg)))
        sent = tg.send_message.call_args.kwargs
        self.assertEqual(sent["chat_id"], ADMIN)
        self.assertIn("Bot juda yaxshi!", sent["text"])
        self.assertIn("@ali", sent["text"])
        self.assertIn(str(USER), sent["text"])
        add.assert_called_once_with(USER, "Bot juda yaxshi!")
        self.assertIsNone(bot.get_pending_action(USER))
        self.assertIn("Rahmat", u.message.reply_text.call_args.args[0])

    def test_rate_limited(self):
        tg = MagicMock()
        tg.send_message = AsyncMock()
        bot.set_pending_action(USER, "feedback")
        u = _text_update("spam")
        with patch.object(bot, "track_user"), \
             patch.object(db, "count_recent_feedback", return_value=bot.FEEDBACK_MAX_PER_HOUR), \
             patch.object(db, "add_feedback") as add:
            run(bot.on_text(u, MagicMock(bot=tg)))
        tg.send_message.assert_not_called()
        add.assert_not_called()
        self.assertIn("Juda ko'p", u.message.reply_text.call_args.args[0])

    def test_too_long_keeps_pending(self):
        bot.set_pending_action(USER, "feedback")
        u = _text_update("x" * (bot.FEEDBACK_MAX_LENGTH + 1))
        with patch.object(bot, "track_user"), patch.object(db, "add_feedback") as add:
            run(bot.on_text(u, MagicMock()))
        add.assert_not_called()
        self.assertEqual(bot.get_pending_action(USER), "feedback")

    def test_admin_unreachable_not_saved(self):
        tg = MagicMock()
        from telegram.error import Forbidden
        tg.send_message = AsyncMock(side_effect=Forbidden("x"))
        bot.set_pending_action(USER, "feedback")
        u = _text_update("salom")
        with patch.object(bot, "track_user"), patch.object(db, "count_recent_feedback", return_value=0), \
             patch.object(db, "add_feedback") as add:
            run(bot.on_text(u, MagicMock(bot=tg)))
        add.assert_not_called()
        self.assertIn("yetkazib bo'lmadi", u.message.reply_text.call_args.args[0])

    def test_plain_text_without_pending_is_ignored(self):
        u = _text_update("salom")
        tg = MagicMock()
        tg.send_message = AsyncMock()
        with patch.object(bot, "track_user"):
            run(bot.on_text(u, MagicMock(bot=tg)))
        tg.send_message.assert_not_called()


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class FeedbackDbTests(unittest.TestCase):
    def test_counts_only_recent(self):
        import psycopg2

        def conn():
            c = psycopg2.connect(TEST_DB_URL)
            c.autocommit = True

            class Ctx:
                def __enter__(s):
                    return c

                def __exit__(s, *a):
                    c.close()
                    return False

            return Ctx()

        uid = random.randint(10**14, 10**15)
        with patch.object(db, "get_conn", conn):
            db.init_db()
            try:
                db.add_feedback(uid, "a")
                db.add_feedback(uid, "b")
                with conn() as c, c.cursor() as cur:
                    cur.execute("UPDATE feedback_messages SET created_at = %s WHERE user_id=%s AND message='a'",
                                (time.time() - 7200, uid))
                self.assertEqual(db.count_recent_feedback(uid, time.time() - 3600), 1)
                self.assertEqual(db.count_recent_feedback(uid, 0), 2)
            finally:
                with conn() as c, c.cursor() as cur:
                    cur.execute("DELETE FROM feedback_messages WHERE user_id=%s", (uid,))


if __name__ == "__main__":
    unittest.main()
