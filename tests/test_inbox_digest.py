"""Smart Inbox Digest (v1.3): idempotent kuzatuv, javob aniqlash, kunlik xulosa (bir marta), tarif limitlari, panel."""
import asyncio
import os
import random
import secrets
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
            cur.execute("DELETE FROM inbox_reminders WHERE owner_user_id=%s", (self.o,))
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

    def test_owner_reply_before_first_customer_row_does_not_create_false_pending(self):
        # hodisalar teskari tartibda: egasi javobi (101) mijoz xabaridan (100) oldin keladi, suhbat qatori hali yo'q
        self.assertTrue(db.record_owner_reply(self.o, 31, 101, 1000.0))
        db.record_customer_message(self.o, 31, 100, "Ali", 990.0)
        self.assertEqual(db.get_pending_chats(self.o, 10, 1100.0)[0], 0)
        db.record_customer_message(self.o, 31, 102, "Ali", 1200.0)  # keyingi yangi xabar esa javobsiz bo'ladi
        self.assertEqual(db.get_pending_chats(self.o, 10, 1300.0)[0], 1)

    def test_disable_during_record_never_recreates_rows(self):
        import psycopg2
        holder = psycopg2.connect(TEST_DB_URL)
        holder.autocommit = False
        out = {}
        try:
            cur = holder.cursor()
            # "o'chirish" tranzaksiyasi ochiq: sozlama qatori qulflangan, ma'lumot hali o'chirilmagan
            cur.execute("UPDATE inbox_settings SET enabled = FALSE WHERE owner_user_id = %s", (self.o,))
            t1 = threading.Thread(target=lambda: out.update(c=db.record_customer_message(self.o, 41, 1, "Ali", 1000.0)))
            t2 = threading.Thread(target=lambda: out.update(r=db.record_owner_reply(self.o, 42, 1, 1000.0)))
            t1.start(); t2.start()
            time.sleep(0.4)
            self.assertTrue(t1.is_alive() and t2.is_alive(), "yozuv o'chirish tranzaksiyasini kutishi kerak")
            cur.execute("DELETE FROM inbox_chats WHERE owner_user_id = %s", (self.o,))
            holder.commit()
            t1.join(5); t2.join(5)
        finally:
            holder.close()
        self.assertFalse(out["c"])
        with db.get_conn() as conn, conn.cursor() as c2:
            c2.execute("SELECT COUNT(*) FROM inbox_chats WHERE owner_user_id=%s", (self.o,))
            self.assertEqual(c2.fetchone()[0], 0)

    def test_records_ignored_when_feature_disabled_or_never_enabled(self):
        other = self.o + 1
        self.addCleanup(lambda: db.set_inbox_settings(other, enabled=False))
        self.assertFalse(db.record_customer_message(other, 1, 1, "X", 1.0))  # sozlama qatori yo'q
        db.set_inbox_settings(self.o, enabled=False)
        self.assertFalse(db.record_customer_message(self.o, 1, 1, "X", 1.0))
        self.assertFalse(db.record_owner_reply(self.o, 1, 2, 1.0))
        with db.get_conn() as conn, conn.cursor() as c2:
            c2.execute("SELECT COUNT(*) FROM inbox_chats WHERE owner_user_id IN (%s, %s)", (self.o, other))
            self.assertEqual(c2.fetchone()[0], 0)

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
        threads = [threading.Thread(target=lambda: res.append(db.claim_inbox_digest(self.o, "2026-11-01", secrets.token_hex(4)))) for _ in range(8)]
        [x.start() for x in threads]
        [x.join() for x in threads]
        self.assertEqual(sum(res), 1)
        self.assertFalse(db.claim_inbox_digest(self.o, "2026-11-01", "x"))  # qayta ishga tushgandan keyin ham
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-02", "a"))
        db.release_inbox_digest(self.o, "2026-11-02", "a")
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-02", "b"))


# --------------------------------------------------------------------------- bot
def _bm(chat=5, mid=100, from_id=5, first="Ali", last=None, is_bot=False, via_bot=None):
    bm = MagicMock()
    bm.sender_business_bot = via_bot
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

    def test_bot_echo_after_restart_does_not_close_pending(self):
        from telegram import User
        # xotiradagi ro'yxat bo'sh (qayta ishga tushgan), lekin Telegram xabarni biznes-bot yuborgan deb belgilagan
        echo = _bm(from_id=1, mid=555, via_bot=User(id=777, first_name="AutoReplyer", is_bot=True))
        rc, ro = self._raw(echo, owner=1)
        ro.assert_not_called()
        rc.assert_not_called()
        rc, ro = self._raw(_bm(from_id=1, mid=556), owner=1)  # oddiy shaxsiy javob — hisoblanadi
        ro.assert_called_once()

    def test_bot_echo_does_not_pause_ai_or_adopt_name(self):
        from telegram import User
        echo = _bm(from_id=1, mid=557, via_bot=User(id=777, first_name="B", is_bot=True))
        with patch.object(bot, "adopt_new_base_name") as adopt:
            self._raw(echo, owner=1)
        adopt.assert_not_called()

    def _raw_conn(self, bm, conn, subscribed=True):
        u = MagicMock()
        u.channel_post = None
        u.business_connection = None
        u.business_message = bm
        with patch.object(db, "get_connection_by_business_id", return_value=conn), \
                patch.object(bot, "is_subscribed_cached", AsyncMock(return_value=subscribed)), \
                patch.object(bot, "_bot_sent_ids", set()), \
                patch.object(db, "inbox_enabled", return_value=True), \
                patch.object(db, "record_customer_message") as rc, patch.object(db, "record_owner_reply") as ro, \
                patch.object(db, "get_settings") as gs:
            ctx = MagicMock()
            ctx.bot.send_message = AsyncMock()
            run(bot.on_raw_update(u, ctx))
        return rc, ro, gs, ctx

    def test_inbox_keeps_tracking_when_can_reply_is_false_but_never_replies(self):
        conn = {"owner_user_id": 1, "is_enabled": True, "can_reply": False}
        rc, ro, gs, ctx = self._raw_conn(_bm(from_id=5), conn)
        rc.assert_called_once()
        gs.assert_not_called()  # avtojavob oqimiga o'tilmaydi
        ctx.bot.send_message.assert_not_awaited()
        rc, ro, *_ = self._raw_conn(_bm(from_id=1, mid=700), conn)
        ro.assert_called_once()

    def test_observe_only_respects_block_subscription_and_disabled_connection(self):
        base = {"owner_user_id": 1, "is_enabled": True, "can_reply": False}
        rc, *_ = self._raw_conn(_bm(), {**base, "is_blocked": True})
        rc.assert_not_called()
        rc, *_ = self._raw_conn(_bm(), base, subscribed=False)
        rc.assert_not_called()
        rc, *_ = self._raw_conn(_bm(), {**base, "is_enabled": False})
        rc.assert_not_called()

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
        stats = {"total": total, "oldest_waiting_since": (now or self.NOW) - 3600.0 * max(total, 1), "priority": 0}
        with patch.object(db, "get_settings", return_value={}), patch.object(db, "get_block", return_value=None), \
                patch.object(db, "claim_inbox_digest", return_value=claim) as cl, \
                patch.object(db, "release_inbox_digest") as rel, \
                patch.object(db, "get_pending_stats", return_value=stats), \
                patch.object(db, "start_inbox_digest_sending", return_value=True) as self.start, \
                patch.object(db, "finish_inbox_digest") as self.fin, \
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
        self.assertEqual(cl.call_args.args[:2], (1, "2026-11-01"))
        self.assertEqual(self.fin.call_args.args[1:], ("2026-11-01", cl.call_args.args[2], "sent"))

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
        self.assertEqual(self.fin.call_args.args[-1], "unknown")

    def test_definite_rejection_releases_day_for_retry(self):
        res, b, cl, rel, _ = self._send(send_side=BadRequest("x"))
        self.assertEqual(res, "failed")
        self.assertEqual(rel.call_args.args[:2], (1, "2026-11-01"))
        rel.assert_called_once()

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

    def test_digest_db_failure_after_claim_allows_retry(self):
        b = MagicMock()
        b.send_message = AsyncMock()
        with patch.object(db, "get_settings", return_value={}), patch.object(db, "get_block", return_value=None), \
                patch.object(db, "claim_inbox_digest", return_value=True), patch.object(db, "release_inbox_digest") as rel, \
                patch.object(db, "get_pending_stats", side_effect=RuntimeError("db down")), \
                patch.object(bot, "plan_of", return_value="plus"), patch.object(bot, "ADMIN_ID", ADMIN):
            res = run(bot.send_inbox_digest(b, self._owner(), self.NOW))
        self.assertEqual(res, "failed")
        self.assertEqual(rel.call_args.args[:2], (1, "2026-11-01"))
        rel.assert_called_once()
        b.send_message.assert_not_awaited()

    def test_release_failure_does_not_crash_job_and_is_retried_on_disconnect(self):
        import psycopg2
        b = MagicMock()
        b.send_message = AsyncMock()
        with patch.object(db, "get_settings", return_value={}), patch.object(db, "get_block", return_value=None), \
                patch.object(db, "claim_inbox_digest", return_value=True), \
                patch.object(db, "release_inbox_digest", side_effect=psycopg2.OperationalError("down")), \
                patch.object(db, "get_pending_stats", side_effect=RuntimeError("db down")), \
                patch.object(bot, "plan_of", return_value="plus"), patch.object(bot, "ADMIN_ID", ADMIN):
            self.assertEqual(run(bot.send_inbox_digest(b, self._owner(), self.NOW)), "failed")  # istisno tashqariga chiqmaydi
        calls = []

        def flaky(*a, **k):
            calls.append(1)
            if len(calls) == 1:
                raise psycopg2.OperationalError("lost")
        wrapped = db.retry_on_disconnect(flaky)
        wrapped(1, "2026-11-01", "tok")
        self.assertEqual(len(calls), 2)
        self.assertIn("release_inbox_digest", [n for n in ("release_inbox_digest",) if getattr(db.release_inbox_digest, "__wrapped__", None)])

    def test_digest_text_build_failure_allows_retry(self):
        res, b, cl, rel, _ = self._send()  # normal holat: bandlik qaytarilmaydi
        rel.assert_not_called()
        b2 = MagicMock()
        b2.send_message = AsyncMock()
        with patch.object(db, "get_settings", return_value={}), patch.object(db, "get_block", return_value=None), \
                patch.object(db, "claim_inbox_digest", return_value=True), patch.object(db, "release_inbox_digest") as rel2, \
                patch.object(db, "get_pending_stats", return_value={"total": 1, "oldest_waiting_since": self.NOW - 60, "priority": 0}), \
                patch.object(db, "get_pending_chats", return_value=(1, _rows(1, self.NOW))), \
                patch.object(bot, "build_inbox_digest", side_effect=RuntimeError("fmt")), \
                patch.object(bot, "plan_of", return_value="plus"), patch.object(bot, "ADMIN_ID", ADMIN):
            self.assertEqual(run(bot.send_inbox_digest(b2, self._owner(), self.NOW)), "failed")
        rel2.assert_called_once()

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


PLANS = lambda plan: (  # noqa: E731
    patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)), patch.object(bot, "plan_of", return_value=plan),
    patch.object(bot, "ADMIN_ID", ADMIN))


class _Plan:
    """with _Plan('pro'): haqiqiy tarif jadvali (conftest hamma funksiyani ochadi) va tarif almashtiriladi."""
    def __init__(self, plan):
        self.ps = PLANS(plan)

    def __enter__(self):
        [p.start() for p in self.ps]

    def __exit__(self, *a):
        [p.stop() for p in self.ps]


NOW_TS = datetime(2026, 11, 1, 20, 30, tzinfo=bot.TASHKENT_TZ).timestamp()


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class DigestRecoveryTests(DbBase):
    """Digest recovery: preparing -> sending -> sent/unknown (token + 5 daqiqalik lease)."""

    def _owner(self):
        return next(o for o in db.list_inbox_owners() if o["owner_user_id"] == self.o)

    def _bot(self, side=None):
        b = MagicMock()
        b.send_message = AsyncMock(side_effect=side)
        return b

    def _run_send(self, b, now):
        with patch.object(bot, "plan_of", return_value="plus"), patch.object(bot, "ADMIN_ID", ADMIN), \
                patch.object(db, "get_block", return_value=None):
            return run(bot.send_inbox_digest(b, self._owner(), now))

    def _phase(self):
        return db.get_inbox_settings(self.o)["digest_phase"]

    def test_preparing_claim_recovers_after_db_outage(self):
        import psycopg2
        db.record_customer_message(self.o, 5, 100, "Ali", NOW_TS - 3600)
        b = self._bot()
        with patch.object(db, "get_pending_stats", side_effect=psycopg2.OperationalError("down")), \
                patch.object(db, "release_inbox_digest", side_effect=psycopg2.OperationalError("down")):
            self.assertEqual(self._run_send(b, NOW_TS), "failed")  # tayyorlash ham, qaytarish ham yiqildi
        self.assertEqual(self._phase(), "preparing")  # bandlik 'preparing'da qolib ketdi
        self.assertEqual(self._run_send(b, NOW_TS + 60), "not_due")  # lease (5 daq) hali tugamagan
        self.assertEqual(self._run_send(b, NOW_TS + 301), "sent")  # lease tugadi: qayta olinadi
        self.assertEqual(b.send_message.await_count, 1)
        self.assertEqual(self._phase(), "sent")

    def test_sending_claim_is_not_retried(self):
        db.record_customer_message(self.o, 5, 100, "Ali", NOW_TS - 3600)
        b = self._bot(side=TimedOut())
        self.assertEqual(self._run_send(b, NOW_TS), "unknown")
        self.assertEqual(self._phase(), "unknown")
        for later in (NOW_TS + 400, NOW_TS + 4000):
            self.assertEqual(self._run_send(b, later), "not_due")
        self.assertEqual(b.send_message.await_count, 1)
        # ishchi 'sending' da o'lgan: qayta olinmaydi
        db.set_inbox_settings(self.o, notify=True)
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-02", "t1", NOW_TS))
        self.assertTrue(db.start_inbox_digest_sending(self.o, "2026-11-02", "t1", NOW_TS))
        self.assertFalse(db.claim_inbox_digest(self.o, "2026-11-02", "t2", NOW_TS + 10000))
        self.assertFalse(inbox.digest_due(datetime(2026, 11, 2, 21, 0), 1200, "2026-11-02", "sending", NOW_TS, NOW_TS + 10000))

    def test_stale_worker_cannot_release_new_claim(self):
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-01", "A", 1000.0))
        self.assertFalse(db.claim_inbox_digest(self.o, "2026-11-01", "B", 1100.0))  # lease hali tugamagan
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-01", "B", 1400.0))  # tugagan: B oldi
        self.assertFalse(db.release_inbox_digest(self.o, "2026-11-01", "A"))  # eskirgan ishchi B ning bandini bekor qila olmaydi
        self.assertFalse(db.start_inbox_digest_sending(self.o, "2026-11-01", "A", 1401.0))
        self.assertFalse(db.finish_inbox_digest(self.o, "2026-11-01", "A", "sent"))
        self.assertEqual(self._phase(), "preparing")
        self.assertTrue(db.start_inbox_digest_sending(self.o, "2026-11-01", "B", 1402.0))
        self.assertFalse(db.release_inbox_digest(self.o, "2026-11-01", "A"))
        self.assertTrue(db.finish_inbox_digest(self.o, "2026-11-01", "B", "sent"))

    def test_stale_worker_does_not_send_after_losing_claim(self):
        db.record_customer_message(self.o, 5, 100, "Ali", NOW_TS - 3600)
        b = self._bot()
        real_start = db.start_inbox_digest_sending

        def lose_claim(owner_id, date_str, token, now=None):
            db.claim_inbox_digest(owner_id, date_str, "other", NOW_TS + 400)  # boshqa ishchi lease tugagach oldi
            return real_start(owner_id, date_str, token, now)
        with patch.object(db, "start_inbox_digest_sending", side_effect=lose_claim):
            self.assertEqual(self._run_send(b, NOW_TS), "skipped")
        b.send_message.assert_not_awaited()

    def test_digest_does_not_duplicate_after_restart(self):
        db.record_customer_message(self.o, 5, 100, "Ali", NOW_TS - 3600)
        b = self._bot()
        self.assertEqual(self._run_send(b, NOW_TS), "sent")
        db.init_db()  # qayta ishga tushish (migratsiyalar qayta ishlaydi)
        self.assertEqual(self._run_send(b, NOW_TS + 60), "not_due")
        self.assertEqual(self._run_send(b, NOW_TS + 900), "not_due")
        self.assertEqual(b.send_message.await_count, 1)

    def test_legacy_digest_date_is_preserved(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE inbox_settings SET last_digest_date='2026-11-01', digest_phase=DEFAULT, digest_claimed_at=NULL, "
                        "digest_claim_token=NULL WHERE owner_user_id=%s", (self.o,))
        db.init_db()
        cfg = db.get_inbox_settings(self.o)
        self.assertEqual((cfg["last_digest_date"], cfg["digest_phase"]), ("2026-11-01", "sent"))  # eski yozuv 'sent' hisoblanadi
        db.record_customer_message(self.o, 5, 100, "Ali", NOW_TS - 3600)
        b = self._bot()
        self.assertEqual(self._run_send(b, NOW_TS), "not_due")  # qayta yuborilmaydi
        b.send_message.assert_not_awaited()

    def test_digest_due_pure_lease(self):
        d = datetime(2026, 11, 1, 21, 0)
        self.assertFalse(inbox.digest_due(d, 1200, "2026-11-01", "preparing", 1000.0, 1200.0))
        self.assertTrue(inbox.digest_due(d, 1200, "2026-11-01", "preparing", 1000.0, 1301.0))
        for ph in ("sending", "sent", "unknown", "empty", "failed"):
            self.assertFalse(inbox.digest_due(d, 1200, "2026-11-01", ph, 1000.0, 99999.0), ph)

    def test_unknown_phase_blocks_retry_and_empty_is_final(self):
        self.assertTrue(db.claim_inbox_digest(self.o, "2026-11-01", "A", 1000.0))
        self.assertTrue(db.finish_inbox_digest(self.o, "2026-11-01", "A", "empty"))
        self.assertFalse(db.claim_inbox_digest(self.o, "2026-11-01", "B", 99999.0))
        with self.assertRaises(ValueError):
            db.finish_inbox_digest(self.o, "2026-11-01", "A", "bogus")


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class PriorityDbTests(DbBase):
    NOW = 100000.0

    def _chat(self, chat_id, since=None):
        db.record_customer_message(self.o, chat_id, 1, f"M{chat_id}", since or self.NOW - 100)

    def test_set_unset_and_double_press_idempotent(self):
        self._chat(1)
        self.assertEqual(db.set_inbox_priority(self.o, 1, True, 5, self.NOW), "ok")
        self.assertEqual(db.set_inbox_priority(self.o, 1, True, 5, self.NOW), "ok")  # qayta bosish
        self.assertEqual(db.count_priority_chats(self.o, self.NOW), 1)
        self.assertEqual(db.set_inbox_priority(self.o, 1, False, 5, self.NOW), "ok")
        self.assertEqual(db.set_inbox_priority(self.o, 1, False, 5, self.NOW), "ok")
        self.assertEqual(db.count_priority_chats(self.o, self.NOW), 0)

    def test_limit_enforced_and_unmark_frees_slot(self):
        for i in range(1, 7):
            self._chat(i)
        res = [db.set_inbox_priority(self.o, i, True, 5, self.NOW) for i in range(1, 7)]
        self.assertEqual(res, ["ok"] * 5 + ["limit"])
        self.assertEqual(db.set_inbox_priority(self.o, 1, False, 5, self.NOW), "ok")
        self.assertEqual(db.set_inbox_priority(self.o, 6, True, 5, self.NOW), "ok")

    def test_zero_limit_forbidden_and_missing_or_disabled(self):
        self._chat(1)
        self.assertEqual(db.set_inbox_priority(self.o, 1, True, 0, self.NOW), "forbidden")  # Free/Plus
        self.assertEqual(db.set_inbox_priority(self.o, 999, True, 5, self.NOW), "no_chat")
        db.set_inbox_settings(self.o, enabled=False)
        self.assertEqual(db.set_inbox_priority(self.o, 1, True, 5, self.NOW), "disabled")

    def test_other_owner_chat_rejected(self):
        self._chat(1)
        other = self.o + 1
        db.set_inbox_settings(other, enabled=True)
        self.addCleanup(lambda: db.set_inbox_settings(other, enabled=False))
        self.assertEqual(db.set_inbox_priority(other, 1, True, 5, self.NOW), "no_chat")
        self.assertEqual(db.count_priority_chats(self.o, self.NOW), 0)

    def test_parallel_presses_do_not_exceed_limit(self):
        for i in range(1, 11):
            self._chat(i)
        res = []
        ts = [threading.Thread(target=lambda i=i: res.append(db.set_inbox_priority(self.o, i, True, 3, self.NOW))) for i in range(1, 11)]
        [x.start() for x in ts]
        [x.join() for x in ts]
        self.assertEqual(res.count("ok"), 3)
        self.assertEqual(db.count_priority_chats(self.o, self.NOW), 3)

    def test_ordering_priority_first_only_when_requested(self):
        self._chat(1, self.NOW - 900)  # eng uzoq kutayotgan
        self._chat(2, self.NOW - 500)
        self._chat(3, self.NOW - 100)
        db.set_inbox_priority(self.o, 3, True, 5, self.NOW)
        db.set_inbox_priority(self.o, 2, True, 5, self.NOW)
        _, rows = db.get_pending_chats(self.o, 10, self.NOW, priority_first=True)
        self.assertEqual([r["chat_id"] for r in rows], [2, 3, 1])  # muhimlar (eskisi avval), keyin oddiy
        _, rows = db.get_pending_chats(self.o, 10, self.NOW)  # Free/Plus/tarifi pasaygan: belgi e'tiborga olinmaydi
        self.assertEqual([r["chat_id"] for r in rows], [1, 2, 3])

    def test_priority_persists_on_new_customer_message_and_answered_leaves_pending(self):
        self._chat(1)
        db.set_inbox_priority(self.o, 1, True, 5, self.NOW)
        db.record_customer_message(self.o, 1, 2, "M1", self.NOW - 50)
        self.assertEqual(db.count_priority_chats(self.o, self.NOW), 1)
        self.assertTrue(db.record_owner_reply(self.o, 1, 3, self.NOW - 10))
        self.assertEqual(db.get_pending_chats(self.o, 10, self.NOW)[0], 0)  # javob berilgan — pendingdan chiqdi
        self.assertEqual(db.get_pending_stats(self.o, self.NOW)["priority"], 0)
        self.assertEqual(db.set_inbox_priority(self.o, 1, True, 5, self.NOW), "ok")  # chat bor, lekin ro'yxatda ko'rinmaydi

    def test_disable_deletes_priority_data(self):
        self._chat(1)
        db.set_inbox_priority(self.o, 1, True, 5, self.NOW)
        db.set_inbox_settings(self.o, enabled=False)
        db.set_inbox_settings(self.o, enabled=True)
        self.assertEqual(db.count_priority_chats(self.o, self.NOW), 0)
        self.assertIsNone(db.get_inbox_chat(self.o, 1))

    def test_retention_14_days(self):
        self._chat(1, self.NOW - 100)
        db.set_inbox_priority(self.o, 1, True, 5, self.NOW)
        self.assertEqual(db.count_priority_chats(self.o, self.NOW + 15 * 86400), 0)

    def test_stats_oldest_wait_covers_all_pending_not_top_n(self):
        for i in range(1, 6):
            self._chat(i, self.NOW - 1000 * i)  # chat 5 eng eski
        db.set_inbox_priority(self.o, 1, True, 5, self.NOW)
        total, rows = db.get_pending_chats(self.o, 1, self.NOW, priority_first=True)
        self.assertEqual([r["chat_id"] for r in rows], [1])  # eng eski (5) qaytgan ro'yxatda yo'q
        st = db.get_pending_stats(self.o, self.NOW)
        self.assertEqual((st["total"], st["oldest_waiting_since"], st["priority"]), (5, self.NOW - 5000, 1))


class PriorityBotTests(unittest.TestCase):
    def _query(self):
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        return q

    def test_limits_by_plan_server_side(self):
        for plan, lim in (("free", 0), ("plus", 0), ("pro", 5), ("ultra", 20)):
            with _Plan(plan):
                self.assertEqual(bot.inbox_priority_limit_for(1, plan), lim, plan)
        with _Plan("free"):
            self.assertEqual(bot.inbox_priority_limit_for(ADMIN, "free"), 20)  # admin — eng yuqori
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["inbox_priority"], ("pro", "ultra"))
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["inbox_reminder"], ("pro", "ultra"))

    def test_free_plus_and_downgraded_ignore_priority_ordering(self):
        for plan, expected in (("free", False), ("plus", False), ("pro", True), ("ultra", True)):
            with _Plan(plan), patch.object(db, "get_pending_chats", return_value=(0, [])) as gp:
                bot.build_inbox_view(1)
            self.assertEqual(gp.call_args.kwargs.get("priority_first"), expected, plan)

    def test_callbacks_locked_for_free_but_unmark_allowed(self):
        self.assertEqual(bot.locked_feature_for("ib_priority"), "inbox_priority")
        self.assertEqual(bot.locked_feature_for("ib_pr:5"), "inbox_priority")
        self.assertIsNone(bot.locked_feature_for("ib_unpr:5"))  # belgini olib tashlash tarifdan qat'i nazar
        self.assertEqual(bot.locked_feature_for("ib_reminders"), "inbox_reminder")
        self.assertEqual(bot.locked_feature_for("ib_rem:5"), "inbox_reminder")
        self.assertEqual(bot.locked_feature_for("ib_rt:5:1h"), "inbox_reminder")
        self.assertIsNone(bot.locked_feature_for("ib_rc:5"))
        for plan, locked in (("free", True), ("plus", True), ("pro", False)):
            with _Plan(plan):
                self.assertEqual(not bot.has_feature(1, "inbox_priority"), locked, plan)

    def test_priority_buttons_are_explicit_and_stale_safe(self):
        q = self._query()
        with _Plan("pro"), patch.object(db, "set_inbox_priority", return_value="ok") as sp, \
                patch.object(db, "get_pending_chats", return_value=(0, [])), patch.object(db, "count_priority_chats", return_value=0):
            run(bot.handle_inbox_callback(q, 1, "ib_pr:5", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_pr:5", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_unpr:5", "uz"))
        self.assertEqual([c.args[2] for c in sp.call_args_list], [True, True, False])  # toggle emas
        self.assertEqual(sp.call_args.args[3], 5)

    def test_invalid_and_stale_callbacks_do_not_crash(self):
        q = self._query()
        for data in ("ib_pr:abc", "ib_pr:", "ib_unpr:x", "ib_rem:zz", "ib_rt:5", "ib_rt:5:99h", "ib_rt:x:1h", "ib_rc:q"):
            q.edit_message_text.reset_mock()
            with _Plan("pro"), patch.object(db, "get_pending_chats", return_value=(0, [])), patch.object(db, "count_priority_chats", return_value=0), \
                    patch.object(db, "list_inbox_reminders", return_value=[]), patch.object(db, "get_settings", return_value={}), \
                    patch.object(db, "count_inbox_reminders_for_date", return_value=0), \
                    patch.object(db, "get_inbox_chat", return_value=None):
                self.assertTrue(run(bot.handle_inbox_callback(q, 1, data, "uz")), data)
            q.edit_message_text.assert_awaited_once()

    def test_stale_priority_results_show_warning(self):
        for result, key in (("limit", "inbox_priority_limit"), ("no_chat", "inbox_chat_gone"), ("disabled", "inbox_disabled_warn")):
            q = self._query()
            with _Plan("pro"), patch.object(db, "set_inbox_priority", return_value=result), \
                    patch.object(db, "get_pending_chats", return_value=(0, [])), patch.object(db, "count_priority_chats", return_value=0):
                run(bot.handle_inbox_callback(q, 1, "ib_pr:5", "uz"))
            self.assertIn(bot.t("uz", key), q.edit_message_text.await_args.args[0])

    def test_view_and_digest_mark_priority_only_for_pro_ultra(self):
        now = time.time()
        rows = [{"chat_id": 7, "customer_name": "Vip", "pending_count": 1, "waiting_since": now - 60, "is_priority": True}]
        for plan, star in (("free", False), ("plus", False), ("pro", True), ("ultra", True)):
            with _Plan(plan), patch.object(db, "get_pending_chats", return_value=(1, rows)):
                text, _ = bot.build_inbox_view(1)
            self.assertEqual("⭐" in text, star, plan)
        self.assertIn("⭐", bot.build_inbox_digest(1, rows, now, "uz", None, True))
        self.assertNotIn("⭐", bot.build_inbox_digest(1, rows, now, "uz", None, False))

    def test_digest_oldest_wait_from_all_pending_chats(self):
        now = 10 ** 6
        rows = [{"chat_id": 1, "customer_name": "A", "pending_count": 1, "waiting_since": now - 600, "is_priority": True}]
        text = bot.build_inbox_digest(9, rows, now, "en", oldest_since=now - 3 * 86400 - 5)
        self.assertIn("3 d", text.splitlines()[1])  # qatorlardagi 10 daqiqa emas, jami eng uzoq — 3 kun

    def test_menu_shows_priority_line_and_buttons(self):
        cfg = {"enabled": True, "notify": True, "digest_minutes": 1200, "last_digest_date": None}
        with _Plan("pro"), patch.object(db, "get_inbox_settings", return_value=cfg), \
                patch.object(db, "get_pending_stats", return_value={"total": 2, "oldest_waiting_since": 1.0, "priority": 2}):
            text, markup = bot.build_inbox_menu(1)
        self.assertIn("2/5", text)
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn("ib_priority", data)
        self.assertIn("ib_reminders", data)
        for d in data:
            self.assertLessEqual(len(d.encode()), 64)

    def test_plan_texts_mention_priority_and_reminders(self):
        with _Plan("pro"):
            txt = bot.plan_features_text("en", "pro")
        self.assertIn("5 important", txt)
        self.assertIn("3 reminders", txt)
        with _Plan("free"):
            txt = bot.plan_features_text("en", "free")
        self.assertIn("Pro — 5", txt)
        with _Plan("ultra"):
            txt = bot.plan_features_text("en", "ultra")
        self.assertIn("20 important", txt)
        self.assertIn("10 reminders", txt)


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
                patch.object(db, "get_pending_stats", return_value={"total": 0, "oldest_waiting_since": None, "priority": 0}), \
                patch.object(bot, "plan_of", return_value="free"):
            run(bot.handle_inbox_callback(q, 1, "ib_on", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_on", "uz"))
            run(bot.handle_inbox_callback(q, 1, "ib_off", "uz"))
        self.assertEqual([c.kwargs for c in st.call_args_list], [{"enabled": True}, {"enabled": True}, {"enabled": False}])

    def test_time_buttons_validated(self):
        q = self._query()
        cfg = {"enabled": True, "notify": True, "digest_minutes": 1200, "last_digest_date": None}
        with patch.object(db, "set_inbox_settings") as st, patch.object(db, "get_inbox_settings", return_value=cfg), \
                patch.object(db, "get_pending_stats", return_value={"total": 0, "oldest_waiting_since": None, "priority": 0}), \
                patch.object(bot, "plan_of", return_value="plus"):
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
