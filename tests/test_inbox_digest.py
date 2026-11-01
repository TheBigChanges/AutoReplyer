"""Smart Inbox Digest (v1.3): idempotent kuzatuv, javob aniqlash, kunlik xulosa (bir marta), tarif limitlari, panel."""
import asyncio
import os
import random
import sys
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
import inbox  # noqa: E402
from telegram.error import BadRequest, Forbidden, TimedOut  # noqa: E402

run = asyncio.run
ADMIN = 999


# --------------------------------------------------------------------------- toza mantiq
class PureTests(unittest.TestCase):
    def test_effective_minutes(self):
        self.assertEqual(inbox.effective_minutes(600, True), 600)
        self.assertEqual(inbox.effective_minutes(600, False), 1200)  # Bepul/tarif pasaygan: 20:00
        self.assertEqual(inbox.effective_minutes(None, True), 1200)
        self.assertEqual(inbox.effective_minutes(5000, True), 1200)

    def test_digest_due(self):
        d = lambda h, m: datetime(2026, 11, 1, h, m)  # noqa: E731
        self.assertFalse(inbox.digest_due(d(19, 59), 1200, None))
        self.assertTrue(inbox.digest_due(d(20, 0), 1200, None))
        self.assertTrue(inbox.digest_due(d(23, 30), 1200, "2026-10-31"))  # bot kechikib ishga tushsa ham shu kun ichida yuboriladi
        self.assertFalse(inbox.digest_due(d(21, 0), 1200, "2026-11-01"))  # bugun yuborilgan

    def test_wait_parts(self):
        self.assertEqual(inbox.wait_parts(10), ("min", 1))
        self.assertEqual(inbox.wait_parts(7200), ("hr", 2))
        self.assertEqual(inbox.wait_parts(3 * 86400), ("day", 3))

    def test_plan_limits_and_feature_table(self):
        self.assertEqual(inbox.INBOX_PLAN_LIMITS, {"free": 3, "plus": 20, "pro": 20, "ultra": 20})
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["inbox_time"], ("plus", "pro", "ultra"))


# --------------------------------------------------------------------------- baza
@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class DbBase(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.o = random.randint(10**11, 10**12)
        self.addCleanup(self._clean)
        db.set_inbox_settings(self.o, enabled=True)

    def _clean(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM inbox_chats WHERE owner_user_id=%s", (self.o,))
            cur.execute("DELETE FROM inbox_settings WHERE owner_user_id=%s", (self.o,))


class TrackingTests(DbBase):
    def test_duplicate_customer_message_counts_once(self):
        self.assertTrue(db.record_customer_message(self.o, 5, 100, "Ali", 1000.0))
        self.assertFalse(db.record_customer_message(self.o, 5, 100, "Ali", 1001.0))  # takroriy update
        total, rows = db.get_pending_chats(self.o, 10, 1002.0)
        self.assertEqual((total, rows[0]["pending_count"]), (1, 1))

    def test_old_message_id_does_not_change_state(self):
        db.record_customer_message(self.o, 5, 100, "Ali", 1000.0)
        db.record_customer_message(self.o, 5, 101, "Ali", 1010.0)
        self.assertFalse(db.record_customer_message(self.o, 5, 99, "Ali", 1020.0))
        _, rows = db.get_pending_chats(self.o, 10, 1030.0)
        self.assertEqual(rows[0]["pending_count"], 2)
        self.assertEqual(rows[0]["waiting_since"], 1000.0)  # kutish boshi — birinchi javobsiz xabar

    def test_owner_reply_closes_chat(self):
        db.record_customer_message(self.o, 5, 100, "Ali", 1000.0)
        self.assertTrue(db.record_owner_reply(self.o, 5, 101, 1100.0))
        self.assertEqual(db.get_pending_chats(self.o, 10, 1200.0)[0], 0)

    def test_late_old_owner_reply_does_not_close_newer_customer_message(self):
        db.record_customer_message(self.o, 5, 100, "Ali", 1000.0)
        db.record_customer_message(self.o, 5, 105, "Ali", 1010.0)
        self.assertFalse(db.record_owner_reply(self.o, 5, 102, 1020.0))  # 102 < 105: yangi xabarga javob emas
        self.assertEqual(db.get_pending_chats(self.o, 10, 1030.0)[0], 1)

    def test_customer_message_reopens_after_reply(self):
        db.record_customer_message(self.o, 5, 100, "Ali", 1000.0)
        db.record_owner_reply(self.o, 5, 101, 1100.0)
        db.record_customer_message(self.o, 5, 102, "Ali", 1200.0)
        total, rows = db.get_pending_chats(self.o, 10, 1300.0)
        self.assertEqual((total, rows[0]["pending_count"], rows[0]["waiting_since"]), (1, 1, 1200.0))

    def test_owner_reply_arriving_before_customer_row_is_not_lost(self):
        # tartib buzilishi: egasi javobi (ID 101) mijoz xabari (ID 100) yozilishidan oldin kelsa ham, suhbat javobsiz bo'lmaydi
        db.record_customer_message(self.o, 5, 99, "Ali", 900.0)
        db.record_owner_reply(self.o, 5, 101, 1000.0)
        db.record_customer_message(self.o, 5, 100, "Ali", 1001.0)  # 100 < 101: bu xabarga allaqachon javob berilgan
        self.assertEqual(db.get_pending_chats(self.o, 10, 1002.0)[0], 0)

    def test_concurrent_duplicates_count_once(self):
        res = []
        threads = [threading.Thread(target=lambda: res.append(db.record_customer_message(self.o, 7, 500, "X", 1000.0))) for _ in range(8)]
        [x.start() for x in threads]
        [x.join() for x in threads]
        self.assertEqual(sum(res), 1)
        self.assertEqual(db.get_pending_chats(self.o, 10, 1001.0)[1][0]["pending_count"], 1)

    def test_oldest_first_and_limit(self):
        for i, chat in enumerate((11, 12, 13, 14, 15)):
            db.record_customer_message(self.o, chat, 10 + i, f"C{chat}", 1000.0 + i * 100)
        total, rows = db.get_pending_chats(self.o, 3, 2000.0)
        self.assertEqual((total, [r["chat_id"] for r in rows]), (5, [11, 12, 13]))

    def test_old_chats_ignored_and_purged(self):
        now = time.time()
        db.record_customer_message(self.o, 21, 1, "Eski", now - 20 * 86400)
        db.record_customer_message(self.o, 22, 1, "Yangi", now - 100)
        self.assertEqual(db.get_pending_chats(self.o, 10, now)[0], 1)
        db.purge_old_inbox()
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT chat_id FROM inbox_chats WHERE owner_user_id=%s", (self.o,))
            self.assertEqual([r[0] for r in cur.fetchall()], [22])

    def test_disabling_deletes_tracked_data(self):
        db.record_customer_message(self.o, 5, 100, "Ali", 1000.0)
        db.set_inbox_settings(self.o, enabled=False)
        self.assertFalse(db.inbox_enabled(self.o))
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM inbox_chats WHERE owner_user_id=%s", (self.o,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_message_text_is_never_stored(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='inbox_chats'")
            cols = {r[0] for r in cur.fetchall()}
        self.assertFalse({c for c in cols if "text" in c or "body" in c})

    def test_settings_whitelist_and_range(self):
        with self.assertRaises(ValueError):
            db.set_inbox_settings(self.o, last_digest_date="x")
        with self.assertRaises(ValueError):
            db.set_inbox_settings(self.o, digest_minutes=1440)

    def test_claim_digest_once_even_under_concurrency(self):
        res = []
        threads = [threading.Thread(target=lambda: res.append(db.claim_inbox_digest(self.o, "2026-11-01"))) for _ in range(8)]
        [x.start() for x in threads]
        [x.join() for x in threads]
        self.assertEqual(sum(res), 1)
        self.assertFalse(db.claim_inbox_digest(self.o, "2026-11-01"))  # qayta ishga tushgandan keyin ham
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-02"))
        db.release_inbox_digest(self.o, "2026-11-02")
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-02"))


# --------------------------------------------------------------------------- bot
def _bm(chat=5, mid=100, from_id=5, first="Ali", last=None, is_bot=False):
    bm = MagicMock()
    bm.chat.id = chat
    bm.message_id = mid
    bm.from_user.id = from_id
    bm.from_user.first_name = first
    bm.from_user.last_name = last
    bm.from_user.is_bot = is_bot
    return bm


class BotTrackingTests(unittest.TestCase):
    def test_tracking_only_when_enabled(self):
        with patch.object(db, "inbox_enabled", return_value=False), patch.object(db, "record_customer_message") as rec:
            bot.track_inbox_customer(1, _bm())
        rec.assert_not_called()
        with patch.object(db, "inbox_enabled", return_value=True), patch.object(db, "record_customer_message") as rec:
            bot.track_inbox_customer(1, _bm(first="Ali", last="Valiyev"))
        rec.assert_called_once_with(1, 5, 100, "Ali Valiyev")

    def test_db_error_never_breaks_main_flow(self):
        with patch.object(db, "inbox_enabled", side_effect=RuntimeError("db")):
            bot.track_inbox_customer(1, _bm())
            bot.track_inbox_owner_reply(1, _bm())

    def _raw(self, bm, owner=1):
        u = MagicMock()
        u.channel_post = None
        u.business_connection = None
        u.business_message = bm
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        conn = {"owner_user_id": owner, "is_enabled": True, "can_reply": True}
        settings = {"offline": False, "auto_reply_text": "x", "cooldown_hours": 1.0, "sleep_mode_enabled": False,
                    "sleep_start_minutes": 0, "sleep_end_minutes": 0, "sleep_reply_text": "", "ai_enabled": False}
        with patch.object(db, "get_connection_by_business_id", return_value=conn), \
                patch.object(db, "get_settings", return_value=settings), \
                patch.object(bot, "is_subscribed_cached", AsyncMock(return_value=True)), \
                patch.object(bot, "adopt_new_base_name"), patch.object(bot, "_bot_sent_ids", set()), \
                patch.object(db, "inbox_enabled", return_value=True), \
                patch.object(db, "record_customer_message") as rc, patch.object(db, "record_owner_reply") as ro:
            run(bot.on_raw_update(u, ctx))
        return rc, ro

    def test_customer_message_is_tracked_even_when_online(self):
        rc, ro = self._raw(_bm(from_id=5), owner=1)
        rc.assert_called_once()
        ro.assert_not_called()

    def test_owner_personal_reply_is_tracked(self):
        rc, ro = self._raw(_bm(from_id=1), owner=1)
        ro.assert_called_once_with(1, 5, 100)
        rc.assert_not_called()

    def test_bot_auto_reply_is_not_owner_reply(self):
        bm = _bm(from_id=1, mid=321)
        u = MagicMock()
        u.channel_post = None
        u.business_connection = None
        u.business_message = bm
        conn = {"owner_user_id": 1, "is_enabled": True, "can_reply": True}
        with patch.object(db, "get_connection_by_business_id", return_value=conn), \
                patch.object(bot, "is_subscribed_cached", AsyncMock(return_value=True)), \
                patch.object(bot, "_bot_sent_ids", {(5, 321)}), \
                patch.object(db, "inbox_enabled", return_value=True), \
                patch.object(db, "record_owner_reply") as ro:
            run(bot.on_raw_update(u, MagicMock()))
        ro.assert_not_called()  # botning o'zi yuborgan xabar egasining javobi hisoblanmaydi

    def test_bot_users_are_not_tracked(self):
        rc, _ = self._raw(_bm(from_id=77, is_bot=True), owner=1)
        rc.assert_not_called()


def _rows(n, now, base=3600.0):
    return [{"chat_id": 100 + i, "customer_name": f"Mijoz{i}", "pending_count": 1 + i, "waiting_since": now - base * (i + 1)} for i in range(n)]


class DigestTests(unittest.TestCase):
    NOW = datetime(2026, 11, 1, 20, 30, tzinfo=bot.TASHKENT_TZ).timestamp()

    def _owner(self, minutes=1200, last=None):
        return {"owner_user_id": 1, "digest_minutes": minutes, "last_digest_date": last}

    def _send(self, owner=None, total=2, plan="free", send_side=None, now=None, rows=None, claim=True):
        b = MagicMock()
        b.send_message = AsyncMock(side_effect=send_side)
        rows = rows if rows is not None else _rows(min(total, 3), now or self.NOW)
        with patch.object(db, "get_settings", return_value={}), patch.object(db, "get_block", return_value=None), \
                patch.object(db, "claim_inbox_digest", return_value=claim) as cl, \
                patch.object(db, "release_inbox_digest") as rel, \
                patch.object(db, "get_pending_chats", return_value=(total, rows)) as gp, \
                patch.object(bot, "plan_of", return_value=plan), patch.object(bot, "ADMIN_ID", ADMIN), \
                patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)):  # conftest barcha funksiyani ochadi: haqiqiy tarif jadvali
            res = run(bot.send_inbox_digest(b, owner or self._owner(), now or self.NOW))
        return res, b, cl, rel, gp

    def test_sent_once_with_summary_and_links(self):
        res, b, cl, _, _ = self._send()
        self.assertEqual(res, "sent")
        text = b.send_message.await_args.args[1]
        self.assertIn("tg://user?id=100", text)
        self.assertIn("Mijoz0", text)
        self.assertEqual(b.send_message.await_args.kwargs["parse_mode"], "HTML")
        cl.assert_called_once_with(1, "2026-11-01")

    def test_not_due_before_time(self):
        early = datetime(2026, 11, 1, 19, 0, tzinfo=bot.TASHKENT_TZ).timestamp()
        res, b, cl, _, _ = self._send(now=early)
        self.assertEqual(res, "not_due")
        b.send_message.assert_not_awaited()
        cl.assert_not_called()

    def test_already_sent_today_or_claimed_by_other_instance(self):
        res, b, _, _, _ = self._send(owner=self._owner(last="2026-11-01"))
        self.assertEqual(res, "not_due")
        res, b, _, _, _ = self._send(claim=False)
        self.assertEqual(res, "skipped")
        b.send_message.assert_not_awaited()

    def test_no_pending_means_no_message(self):
        res, b, _, _, _ = self._send(total=0, rows=[])
        self.assertEqual(res, "empty")
        b.send_message.assert_not_awaited()

    def test_limits_follow_plan(self):
        for plan, expected in (("free", 3), ("plus", 20), ("pro", 20), ("ultra", 20)):
            *_, gp = self._send(plan=plan)
            self.assertEqual(gp.call_args.args[1], expected, plan)

    def test_overflow_line_shown(self):
        res, b, *_ = self._send(total=7, rows=_rows(3, self.NOW))
        self.assertIn("4", b.send_message.await_args.args[1].splitlines()[-1])

    def test_free_plan_cannot_choose_time(self):
        res, *_ = self._send(owner=self._owner(minutes=600), plan="free")  # saqlangan 10:00, lekin Bepul: 20:00
        at_1030 = datetime(2026, 11, 1, 10, 30, tzinfo=bot.TASHKENT_TZ).timestamp()
        res, b, *_ = self._send(owner=self._owner(minutes=600), plan="free", now=at_1030)
        self.assertEqual(res, "not_due")
        res, b, *_ = self._send(owner=self._owner(minutes=600), plan="plus", now=at_1030)
        self.assertEqual(res, "sent")

    def test_timeout_keeps_day_claimed_and_no_resend(self):
        res, b, cl, rel, _ = self._send(send_side=TimedOut())
        self.assertEqual(res, "unknown")
        rel.assert_not_called()

    def test_definite_rejection_releases_day_for_retry(self):
        res, b, cl, rel, _ = self._send(send_side=BadRequest("x"))
        self.assertEqual(res, "failed")
        rel.assert_called_once_with(1, "2026-11-01")

    def test_blocked_owner_keeps_day_claimed(self):
        res, b, cl, rel, _ = self._send(send_side=Forbidden("blocked"))
        self.assertEqual(res, "failed")
        rel.assert_not_called()

    def test_admin_blocked_owner_skipped(self):
        b = MagicMock()
        b.send_message = AsyncMock()
        with patch.object(db, "get_settings", return_value={}), patch.object(db, "get_block", return_value={"reason": "x"}), \
                patch.object(bot, "ADMIN_ID", ADMIN):
            self.assertEqual(run(bot.send_inbox_digest(b, self._owner(), self.NOW)), "skipped")
        b.send_message.assert_not_awaited()

    def test_digest_html_escapes_customer_name(self):
        rows = [{"chat_id": 1, "customer_name": "<b>X&Y</b>", "pending_count": 1, "waiting_since": self.NOW - 60}]
        text = bot.build_inbox_digest(1, rows, self.NOW, "uz")
        self.assertIn("&lt;b&gt;X&amp;Y&lt;/b&gt;", text)
        self.assertNotIn("<b>", text)

    def test_digest_texts_exist_in_three_languages(self):
        rows = _rows(2, self.NOW)
        for lang in ("uz", "en", "ru"):
            self.assertIn("Mijoz0", bot.build_inbox_digest(2, rows, self.NOW, lang))

    def test_job_survives_one_owner_failing(self):
        ctx = MagicMock()
        calls = []

        async def fake(b, owner, now):
            calls.append(owner["owner_user_id"])
            if owner["owner_user_id"] == 1:
                raise RuntimeError("boom")
            return "sent"
        with patch.object(db, "list_inbox_owners", return_value=[{"owner_user_id": 1}, {"owner_user_id": 2}]), \
                patch.object(bot, "send_inbox_digest", fake):
            run(bot.inbox_digest_job(ctx))
        self.assertEqual(calls, [1, 2])

    def test_job_registered(self):
        app = bot.build_app()
        if app.job_queue is not None:
            self.assertTrue(any(j.callback.__name__ == "inbox_digest_job" for j in app.job_queue.jobs()))


class PanelTests(unittest.TestCase):
    def _query(self):
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        return q

    def test_panel_has_inbox_button(self):
        with patch.object(db, "get_settings", return_value={"offline": True, "cooldown_hours": 1.0, "auto_reply_text": "a"}), \
                patch.object(bot, "plan_of", return_value="free"):
            _, markup = bot.build_panel(1)
        self.assertIn("ib_menu", [b.callback_data for row in markup.inline_keyboard for b in row])

    def test_enable_disable_are_explicit_and_idempotent(self):
        q = self._query()
        cfg = {"enabled": True, "notify": True, "digest_minutes": 1200, "last_digest_date": None}
        with patch.object(db, "set_inbox_settings") as st, patch.object(db, "get_inbox_settings", return_value=cfg), \
                patch.object(db, "get_pending_chats", return_value=(0, [])), patch.object(bot, "plan_of", return_value="free"):
            run(bot.handle_inbox_callback(q, 1, "ib_on", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_on", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_off", "uz"))
        self.assertEqual([c.kwargs for c in st.call_args_list], [{"enabled": True}, {"enabled": True}, {"enabled": False}])

    def test_time_buttons_validated(self):
        q = self._query()
        cfg = {"enabled": True, "notify": True, "digest_minutes": 1200, "last_digest_date": None}
        with patch.object(db, "set_inbox_settings") as st, patch.object(db, "get_inbox_settings", return_value=cfg), \
                patch.object(db, "get_pending_chats", return_value=(0, [])), patch.object(bot, "plan_of", return_value="plus"):
            run(bot.handle_inbox_callback(q, 1, "ib_t:600", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_t:601", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_t:abc", "uz"))
        st.assert_called_once_with(1, digest_minutes=600)

    def test_time_choice_locked_for_free_plan(self):
        self.assertEqual(bot.locked_feature_for("ib_time"), "inbox_time")
        self.assertEqual(bot.locked_feature_for("ib_t:600"), "inbox_time")
        self.assertIsNone(bot.locked_feature_for("ib_on"))
        with patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)):
            with patch.object(bot, "plan_of", return_value="free"):
                self.assertFalse(bot.has_feature(1, "inbox_time"))
            with patch.object(bot, "plan_of", return_value="plus"):
                self.assertTrue(bot.has_feature(1, "inbox_time"))

    def test_view_lists_chats_and_empty_state(self):
        now = time.time()
        with patch.object(db, "get_pending_chats", return_value=(0, [])), patch.object(bot, "plan_of", return_value="free"):
            text, _ = bot.build_inbox_view(1)
        self.assertIn("\U0001F389", text)
        with patch.object(db, "get_pending_chats", return_value=(5, _rows(3, now))), patch.object(bot, "plan_of", return_value="free"):
            text, _ = bot.build_inbox_view(1)
        self.assertIn("Mijoz0", text)
        self.assertIn("2", text.splitlines()[-1])

    def test_plan_texts_mention_inbox(self):
        for lang in ("uz", "en", "ru"):
            self.assertIn("Smart Inbox", bot.plan_features_text(lang, "free"))
        self.assertIn("20", bot.plan_features_text("en", "plus"))
        self.assertIn("3", bot.plan_features_text("en", "free"))


if __name__ == "__main__":
    unittest.main()
