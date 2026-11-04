"""Smart Inbox v1.2 — eslatmalar (follow-up reminders): rejalash, kunlik limit, yuborish, bekor qilish, tarif, parallel ishchilar."""
import asyncio
import os
import random
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

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
TZ = bot.TASHKENT_TZ
NOW = datetime(2026, 11, 1, 20, 30, tzinfo=TZ).timestamp()


class _Plan:
    def __init__(self, plan):
        self.ps = [patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)), patch.object(bot, "plan_of", return_value=plan),
                   patch.object(bot, "ADMIN_ID", ADMIN)]

    def __enter__(self):
        [p.start() for p in self.ps]

    def __exit__(self, *a):
        [p.stop() for p in self.ps]


class PureTests(unittest.TestCase):
    def test_delay_choices(self):
        self.assertEqual(inbox.reminder_due("1h", NOW, TZ)[0], NOW + 3600)
        self.assertEqual(inbox.reminder_due("3h", NOW, TZ)[0], NOW + 10800)
        self.assertEqual(inbox.reminder_due("6h", NOW, TZ)[0], NOW + 21600)
        self.assertIsNone(inbox.reminder_due("2h", NOW, TZ))
        self.assertIsNone(inbox.reminder_due("", NOW, TZ))

    def test_due_local_date_follows_due_time(self):
        due, date = inbox.reminder_due("6h", NOW, TZ)  # 20:30 + 6 soat -> ertasi kun
        self.assertEqual(date, "2026-11-02")

    def test_next9_in_owner_timezone(self):
        due, date = inbox.reminder_due("next9", NOW, TZ)
        self.assertEqual(datetime.fromtimestamp(due, TZ).strftime("%Y-%m-%d %H:%M"), "2026-11-02 09:00")
        self.assertEqual(date, "2026-11-02")
        ny = ZoneInfo("America/New_York")
        due, date = inbox.reminder_due("next9", NOW, ny)  # 2026-11-01 10:30 NY -> ertaga 09:00 NY (DST tugagan)
        self.assertEqual(datetime.fromtimestamp(due, ny).strftime("%Y-%m-%d %H:%M"), "2026-11-02 09:00")
        # yarim tundan keyin ham «ertaga» — keyingi kalendar kun
        late = datetime(2026, 11, 2, 0, 30, tzinfo=TZ).timestamp()
        due, date = inbox.reminder_due("next9", late, TZ)
        self.assertEqual(date, "2026-11-03")
        self.assertIsInstance(due, float)  # mutlaq UTC unix vaqti: keyin zona o'zgarsa ham siljimaydi

    def test_limits_and_choices(self):
        self.assertEqual(inbox.INBOX_REMINDER_DAILY_LIMITS, {"free": 0, "plus": 0, "pro": 3, "ultra": 10})
        self.assertEqual(inbox.INBOX_PRIORITY_LIMITS, {"free": 0, "plus": 0, "pro": 5, "ultra": 20})
        self.assertEqual(inbox.REMINDER_CHOICES, ("1h", "3h", "6h", "next9"))


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class DbBase(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.o = random.randint(10**11, 10**12)
        self.addCleanup(self._clean)
        db.set_inbox_settings(self.o, enabled=True)

    def _clean(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            for tbl in ("inbox_reminders", "inbox_chats", "inbox_settings"):
                cur.execute(f"DELETE FROM {tbl} WHERE owner_user_id=%s", (self.o,))

    def chat(self, chat_id=5, name="Ali", at=None):
        db.record_customer_message(self.o, chat_id, 1, name, at or NOW - 600)

    def state(self, chat_id=5):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT state FROM inbox_reminders WHERE owner_user_id=%s AND chat_id=%s ORDER BY id DESC LIMIT 1", (self.o, chat_id))
            r = cur.fetchone()
        return r[0] if r else None

    def states(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT state FROM inbox_reminders WHERE owner_user_id=%s ORDER BY id", (self.o,))
            return [r[0] for r in cur.fetchall()]

    def sched(self, chat_id=5, due=None, date="2026-11-01", limit=3):
        return db.schedule_inbox_reminder(self.o, chat_id, due if due is not None else NOW + 3600, date, limit, NOW)


class ScheduleDbTests(DbBase):
    def test_schedule_and_one_active_per_chat(self):
        self.chat()
        first = self.sched()
        self.assertIsInstance(first, int)
        second = self.sched(due=NOW + 7200)  # qayta belgilash: eskisi bekor qilinadi
        self.assertIsInstance(second, int)
        self.assertEqual(self.states(), ["cancelled", "scheduled"])

    def test_only_pending_chat_can_get_reminder(self):
        self.assertEqual(self.sched(), "no_chat")
        self.chat()
        db.record_owner_reply(self.o, 5, 2, NOW)
        self.assertEqual(self.sched(), "no_chat")

    def test_zero_limit_forbidden_and_disabled(self):
        self.chat()
        self.assertEqual(self.sched(limit=0), "forbidden")
        db.set_inbox_settings(self.o, enabled=False)
        self.assertEqual(self.sched(), "disabled")

    def test_daily_limit_counts_active_sent_unknown_but_not_cancelled_failed(self):
        for i in range(1, 6):
            self.chat(i)
        self.assertIsInstance(self.sched(1), int)
        self.assertIsInstance(self.sched(2), int)
        self.assertIsInstance(self.sched(3), int)
        self.assertEqual(self.sched(4), "limit")
        self.assertTrue(db.cancel_inbox_reminder(self.o, 1))  # bekor qilingan limitga kirmaydi
        self.assertIsInstance(self.sched(4), int)
        self.assertEqual(self.sched(5), "limit")
        # failed ham kirmaydi; sent / unknown kiradi
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE inbox_reminders SET state='failed' WHERE owner_user_id=%s AND chat_id=2", (self.o,))
        self.assertIsInstance(self.sched(5), int)
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE inbox_reminders SET state='sent' WHERE owner_user_id=%s AND chat_id=3", (self.o,))
            cur.execute("UPDATE inbox_reminders SET state='unknown' WHERE owner_user_id=%s AND chat_id=4", (self.o,))
        self.assertEqual(db.count_inbox_reminders_for_date(self.o, "2026-11-01"), 3)
        self.chat(6)
        self.assertEqual(self.sched(6), "limit")
        self.assertIsInstance(self.sched(6, date="2026-11-02"), int)  # boshqa kun — alohida limit

    def test_rescheduling_same_chat_does_not_use_extra_quota(self):
        for i in range(1, 4):
            self.chat(i)
        for i in (1, 2, 3):
            self.sched(i)
        self.assertIsInstance(self.sched(1, due=NOW + 9000), int)  # o'z eslatmasini almashtirish limitga to'smaydi

    def test_atomic_daily_limit_under_parallel_requests(self):
        for i in range(1, 11):
            self.chat(i)
        res = []
        ts = [threading.Thread(target=lambda i=i: res.append(self.sched(i, limit=3))) for i in range(1, 11)]
        [x.start() for x in ts]
        [x.join() for x in ts]
        self.assertEqual(sum(isinstance(r, int) for r in res), 3)
        self.assertEqual(db.count_inbox_reminders_for_date(self.o, "2026-11-01"), 3)

    def test_other_owner_chat_id_rejected(self):
        self.chat()
        other = self.o + 1
        db.set_inbox_settings(other, enabled=True)
        self.addCleanup(lambda: db.set_inbox_settings(other, enabled=False))
        self.assertEqual(db.schedule_inbox_reminder(other, 5, NOW + 3600, "2026-11-01", 3, NOW), "no_chat")
        self.assertFalse(db.cancel_inbox_reminder(other, 5))
        self.assertIsNone(db.get_inbox_chat(other, 5))

    def test_owner_reply_cancels_unsent_reminders_in_same_step(self):
        self.chat()
        self.sched()
        self.assertTrue(db.record_owner_reply(self.o, 5, 2, NOW))
        self.assertEqual(self.state(), "cancelled")
        self.assertEqual(db.claim_due_inbox_reminders(NOW + 99999), [])

    def test_disabling_inbox_deletes_chats_and_reminders(self):
        self.chat()
        self.sched()
        db.set_inbox_settings(self.o, enabled=False)
        self.assertEqual(self.states(), [])
        self.assertIsNone(db.get_inbox_chat(self.o, 5))

    def test_restart_keeps_reminders(self):
        self.chat()
        rid = self.sched()
        db.init_db()
        self.assertEqual(self.state(), "scheduled")
        due = [r for r in db.claim_due_inbox_reminders(NOW + 4000) if r["id"] == rid]
        self.assertEqual(len(due), 1)

    def test_absolute_due_time_unchanged_by_tz_change(self):
        self.chat()
        due, date = inbox.reminder_due("next9", NOW, TZ)
        self.sched(due=due, date=date)
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT due_at FROM inbox_reminders WHERE owner_user_id=%s", (self.o,))
            self.assertEqual(cur.fetchone()[0], due)

    def test_not_due_yet_is_not_claimed_and_two_workers_do_not_double_claim(self):
        self.chat()
        rid = self.sched()
        self.assertEqual([r for r in db.claim_due_inbox_reminders(NOW) if r["id"] == rid], [])
        res = []
        ts = [threading.Thread(target=lambda: res.extend(r["id"] for r in db.claim_due_inbox_reminders(NOW + 4000) if r["id"] == rid)) for _ in range(8)]
        [x.start() for x in ts]
        [x.join() for x in ts]
        self.assertEqual(res, [rid])

    def test_stale_preparing_reclaimed_but_sending_is_not(self):
        self.chat(1)
        self.chat(2)
        a, b = self.sched(1), self.sched(2)
        claimed = {r["id"]: r for r in db.claim_due_inbox_reminders(NOW + 4000)}
        self.assertIn(a, claimed)
        ra, rb = claimed[a], claimed[b]
        self.assertTrue(db.mark_inbox_reminder_sending(b, rb["attempt_token"], NOW + 4000))
        again = {r["id"] for r in db.claim_due_inbox_reminders(NOW + 4000 + 301)}
        self.assertIn(a, again)  # preparing: lease tugadi
        self.assertNotIn(b, again)  # sending: qayta olinmaydi
        self.assertFalse(db.mark_inbox_reminder_sending(a, ra["attempt_token"], NOW + 5000))  # eski token yaroqsiz
        self.assertEqual(db.mark_stale_sending_reminders(NOW + 4000 + 301), 1)
        self.assertEqual(self.state(2), "unknown")

    def test_stale_token_cannot_finish(self):
        self.chat()
        rid = self.sched()
        r1 = db.claim_due_inbox_reminders(NOW + 4000)[0]
        r2 = db.claim_due_inbox_reminders(NOW + 4000 + 400)[0]
        self.assertNotEqual(r1["attempt_token"], r2["attempt_token"])
        self.assertFalse(db.finish_inbox_reminder(rid, r1["attempt_token"], "sent"))
        self.assertTrue(db.finish_inbox_reminder(rid, r2["attempt_token"], "sent"))
        with self.assertRaises(ValueError):
            db.finish_inbox_reminder(rid, r2["attempt_token"], "bogus")

    def test_sending_reminder_blocks_new_one_for_same_chat(self):
        self.chat()
        rid = self.sched()
        r = db.claim_due_inbox_reminders(NOW + 4000)[0]
        db.mark_inbox_reminder_sending(rid, r["attempt_token"], NOW + 4000)
        self.assertEqual(self.sched(due=NOW + 9000), "busy")


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class SendTests(DbBase):
    def _bot(self, side=None):
        b = MagicMock()
        b.send_message = AsyncMock(side_effect=side)
        return b

    def _claim(self, now=NOW + 4000):
        return [r for r in db.claim_due_inbox_reminders(now) if r["owner_user_id"] == self.o]

    def _process(self, b, rem, plan="pro", now=NOW + 4000, block=None):
        with _Plan(plan), patch.object(db, "get_block", return_value=block):
            return run(bot.process_inbox_reminder(b, rem, now))

    def test_reminder_sent_to_owner_private_chat_without_message_text(self):
        self.chat(name="Ali <b>")
        self.sched()
        rem = self._claim()[0]
        seen = {}

        async def spy(chat_id, text, **kw):
            seen["state_during_send"] = self.state()  # yuborishdan OLDIN 'sending' belgilangan
            seen["chat_id"], seen["text"] = chat_id, text

        b = self._bot(side=spy)
        self.assertEqual(self._process(b, rem), "sent")
        self.assertEqual(seen["state_during_send"], "sending")
        self.assertEqual(seen["chat_id"], self.o)  # faqat botning shaxsiy chati (egasi), mijozga emas
        self.assertIn("tg://user?id=5", seen["text"])
        self.assertIn("&lt;b&gt;", seen["text"])
        self.assertEqual(self.state(), "sent")

    def test_timeout_is_unknown_and_never_resent(self):
        self.chat()
        self.sched()
        rem = self._claim()[0]
        b = self._bot(side=TimedOut())
        self.assertEqual(self._process(b, rem), "unknown")
        self.assertEqual(self.state(), "unknown")
        self.assertEqual(self._claim(NOW + 99999), [])
        db.mark_stale_sending_reminders(NOW + 99999)
        self.assertEqual(self._claim(NOW + 99999), [])
        self.assertEqual(b.send_message.await_count, 1)

    def test_definite_rejection_is_failed_not_retried(self):
        for exc in (BadRequest("x"), Forbidden("blocked")):
            self.chat()
            self.sched()
            rem = self._claim()[0]
            self.assertEqual(self._process(self._bot(side=exc), rem), "failed")
            self.assertEqual(self.state(), "failed")
            self._clean()
            db.set_inbox_settings(self.o, enabled=True)

    def test_answered_chat_cancels_before_send(self):
        self.chat()
        self.sched()
        rem = self._claim()[0]
        db.record_owner_reply(self.o, 5, 2, NOW + 100)  # claim va yuborish orasida egasi javob berdi
        b = self._bot()
        self.assertIn(self._process(b, rem), ("cancelled", "stale"))
        b.send_message.assert_not_awaited()

    def test_inbox_disabled_before_send(self):
        self.chat()
        self.sched()
        rem = self._claim()[0]
        db.set_inbox_settings(self.o, enabled=False)
        b = self._bot()
        self.assertIn(self._process(b, rem), ("cancelled", "stale"))
        b.send_message.assert_not_awaited()

    def test_downgraded_plan_does_not_send(self):
        self.chat()
        self.sched()
        rem = self._claim()[0]
        b = self._bot()
        self.assertEqual(self._process(b, rem, plan="plus"), "cancelled")
        self.assertEqual(self.state(), "cancelled")
        b.send_message.assert_not_awaited()

    def test_blocked_owner_does_not_get_reminder(self):
        self.chat()
        self.sched()
        rem = self._claim()[0]
        b = self._bot()
        self.assertEqual(self._process(b, rem, block={"reason": "x"}), "cancelled")
        b.send_message.assert_not_awaited()

    def test_two_workers_do_not_double_send(self):
        self.chat()
        self.sched()
        b = self._bot()
        batches = []
        ts = [threading.Thread(target=lambda: batches.append(self._claim())) for _ in range(6)]
        [x.start() for x in ts]
        [x.join() for x in ts]
        for batch in batches:
            for rem in batch:
                self._process(b, rem)
        self.assertEqual(b.send_message.await_count, 1)

    def test_job_claims_and_sends_due_reminders_only(self):
        self.chat(1)
        self.chat(2)
        self.sched(1, due=NOW - 10)
        self.sched(2, due=NOW + 99999)
        b = self._bot()
        ctx = MagicMock()
        ctx.bot = b
        with _Plan("pro"), patch.object(db, "get_block", return_value=None), patch("bot.time.time", return_value=NOW):
            run(bot.inbox_reminder_job(ctx))
        self.assertEqual(b.send_message.await_count, 1)
        self.assertEqual((self.state(1), self.state(2)), ("sent", "scheduled"))

    def test_job_survives_db_error_and_one_failing_reminder(self):
        ctx = MagicMock()
        with patch.object(db, "claim_due_inbox_reminders", side_effect=RuntimeError("down")):
            run(bot.inbox_reminder_job(ctx))  # istisno tashqariga chiqmaydi

        async def boom(b, rem, now):
            if rem["id"] == 1:
                raise RuntimeError("x")
            calls.append(rem["id"])
        calls = []
        with patch.object(db, "mark_stale_sending_reminders"), \
                patch.object(db, "claim_due_inbox_reminders", return_value=[{"id": 1}, {"id": 2}]), patch.object(bot, "process_inbox_reminder", boom):
            run(bot.inbox_reminder_job(ctx))
        self.assertEqual(calls, [2])

    def test_prepare_db_error_leaves_reminder_recoverable(self):
        self.chat()
        self.sched()
        rem = self._claim()[0]
        b = self._bot()
        with patch.object(db, "get_inbox_chat", side_effect=RuntimeError("down")):
            self.assertEqual(self._process(b, rem), "retry")
        b.send_message.assert_not_awaited()
        self.assertEqual(self.state(), "preparing")
        self.assertEqual(len(self._claim(NOW + 4000 + 301)), 1)  # lease tugagach qayta olinadi

    def test_job_registered_every_60s_first_95(self):
        app = bot.build_app()
        if app.job_queue is not None:
            jobs = [j for j in app.job_queue.jobs() if j.callback.__name__ == "inbox_reminder_job"]
            self.assertEqual(len(jobs), 1)
            self.assertEqual(jobs[0].trigger.interval.total_seconds(), 60)


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class UiTests(DbBase):
    def _q(self):
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        return q

    def _press(self, data, plan="pro", owner=None):
        q = self._q()
        with _Plan(plan):
            run(bot.handle_inbox_callback(q, owner or self.o, data, "uz"))
        return q.edit_message_text.await_args.args[0]

    def test_button_creates_reminder_and_shows_time(self):
        self.chat()
        text = self._press("ib_rt:5:3h")
        self.assertIn(bot.t("uz", "inbox_reminder_created", time="", date="", left=0)[:10], text)
        self.assertEqual(self.state(), "scheduled")

    def test_all_choices_work_and_callback_length_ok(self):
        for i, c in enumerate(inbox.REMINDER_CHOICES, 1):
            self.chat(10**12 + i)
            data = f"ib_rt:{10**12 + i}:{c}"
            self.assertLessEqual(len(data.encode()), 64)
            self._press(data, plan="ultra")
            self.assertEqual(self.state(10**12 + i), "scheduled")

    def test_free_plan_cannot_schedule_even_with_forged_button(self):
        self.chat()
        for plan in ("free", "plus"):
            text = self._press("ib_rt:5:1h", plan=plan)
            self.assertIn(bot.t("uz", "inbox_reminder_limit"), text)
            self.assertIsNone(self.state())

    def test_stale_button_for_answered_chat(self):
        self.chat()
        db.record_owner_reply(self.o, 5, 2, NOW)
        text = self._press("ib_rt:5:1h")
        self.assertIn(bot.t("uz", "inbox_reminder_already_answered"), text)
        self.assertIsNone(self.state())

    def test_other_users_chat_id_rejected_in_callbacks(self):
        self.chat()
        other = self.o + 1
        db.set_inbox_settings(other, enabled=True)
        self.addCleanup(lambda: db.set_inbox_settings(other, enabled=False))
        text = self._press("ib_rt:5:1h", owner=other)
        self.assertIn(bot.t("uz", "inbox_reminder_already_answered"), text)
        self.assertIsNone(self.state())
        text = self._press("ib_rem:5", owner=other)
        self.assertIn(bot.t("uz", "inbox_chat_gone"), text)
        self.sched()
        self._press("ib_rc:5", owner=other)
        self.assertEqual(self.state(), "scheduled")  # begona bekor qila olmaydi

    def test_cancel_button(self):
        self.chat()
        self.sched()
        text = self._press("ib_rc:5")
        self.assertIn(bot.t("uz", "inbox_reminder_cancelled"), text)
        self.assertEqual(self.state(), "cancelled")
        text = self._press("ib_rc:5")  # ikkinchi bosish — xato emas
        self.assertIn(bot.t("uz", "inbox_chat_gone"), text)

    def test_choice_view_buttons(self):
        self.chat()
        with _Plan("pro"):
            text, markup = bot.build_inbox_reminder_choice(self.o, 5)
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertEqual(data[:4], ["ib_rt:5:1h:0", "ib_rt:5:3h:0", "ib_rt:5:6h:0", "ib_rt:5:next9:0"])
        self.assertNotIn("ib_rc:5:0", data)
        self.sched()
        with _Plan("pro"):
            _, markup = bot.build_inbox_reminder_choice(self.o, 5)
        self.assertIn("ib_rc:5:0", [b.callback_data for row in markup.inline_keyboard for b in row])

    def test_reminders_view_lists_active_and_remaining_quota(self):
        self.chat()
        self.sched()
        with _Plan("pro"), patch("bot.time.time", return_value=NOW):
            text, _ = bot.build_inbox_reminders_view(self.o)
        self.assertIn("Ali", text)
        self.assertIn("2", text.split("\n")[0])  # Pro: 3 - 1 = 2 qoldi


class RaceAndRetentionTests(DbBase):
    def test_mark_sending_rechecks_pending_in_same_transaction(self):
        self.chat()
        rid = self.sched()
        rem = db.claim_due_inbox_reminders(NOW + 4000)[0]
        with db.get_conn() as conn, conn.cursor() as cur:  # egasi javobi (eslatma allaqachon 'preparing'da band qilingan)
            cur.execute("UPDATE inbox_chats SET pending = FALSE WHERE owner_user_id=%s AND chat_id=5", (self.o,))
        self.assertFalse(db.mark_inbox_reminder_sending(rid, rem["attempt_token"], NOW + 4000))
        self.assertEqual(self.state(), "cancelled")

    def test_mark_sending_requires_inbox_enabled(self):
        self.chat()
        rid = self.sched()
        rem = db.claim_due_inbox_reminders(NOW + 4000)[0]
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE inbox_settings SET enabled = FALSE WHERE owner_user_id=%s", (self.o,))
        self.assertFalse(db.mark_inbox_reminder_sending(rid, rem["attempt_token"], NOW + 4000))

    def test_reply_during_sending_cannot_be_cancelled_known_limitation(self):
        self.chat()
        rid = self.sched()
        rem = db.claim_due_inbox_reminders(NOW + 4000)[0]
        self.assertTrue(db.mark_inbox_reminder_sending(rid, rem["attempt_token"], NOW + 4000))
        db.record_owner_reply(self.o, 5, 2, NOW + 4001)
        self.assertEqual(self.state(), "sending")  # Telegram chaqiruvi boshlangan: qaytarib bo'lmaydi (README'da yozilgan)

    def test_reminder_for_chat_older_than_retention_rejected(self):
        self.chat(at=NOW - 15 * 86400)  # tozalash vazifasi hali o'chirmagan eski suhbat
        self.assertEqual(self.sched(), "no_chat")
        self.chat(6, at=NOW - 13 * 86400)
        self.assertIsInstance(self.sched(6), int)


class PurgeAndLimitUiTests(DbBase):
    def test_purge_cleans_reminders_for_expired_chats(self):
        now = __import__("time").time()
        self.chat(at=now - 13 * 86400)
        rid = db.schedule_inbox_reminder(self.o, 5, now + 3600, "2999-01-01", 3, now)
        self.assertIsInstance(rid, int)
        self.chat(6, at=now - 13 * 86400)
        sent = db.schedule_inbox_reminder(self.o, 6, now + 3600, "2999-01-01", 3, now)
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE inbox_reminders SET state='sent' WHERE id=%s", (sent,))
            cur.execute("UPDATE inbox_chats SET last_customer_at = %s WHERE owner_user_id=%s", (now - 15 * 86400, self.o))
        db.purge_old_inbox()
        self.assertEqual(db.list_inbox_reminders(self.o), [])
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT state FROM inbox_reminders WHERE owner_user_id=%s ORDER BY id", (self.o,))
            self.assertEqual([r[0] for r in cur.fetchall()], ["sent"])  # faol eslatma o'chdi; yuborilgani limit hisobi uchun qoladi
        self.assertEqual(db.count_inbox_reminders_for_date(self.o, "2999-01-01"), 1)

    def test_list_reminders_skips_orphans(self):
        self.chat()
        self.sched()
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM inbox_chats WHERE owner_user_id=%s", (self.o,))
        self.assertEqual(db.list_inbox_reminders(self.o), [])

    def test_created_message_shows_remaining_for_chosen_date(self):
        for i in (1, 2):
            self.chat(i)
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        with _Plan("pro"):
            run(bot.handle_inbox_callback(q, self.o, "ib_rt:1:next9", "uz"))
            run(bot.handle_inbox_callback(q, self.o, "ib_rt:2:next9", "uz"))
        text = q.edit_message_text.await_args.args[0]
        tomorrow = inbox.reminder_due("next9", __import__("time").time(), TZ)[1]
        self.assertIn(tomorrow, text)
        self.assertIn("1", text.split("\n")[0])  # Pro 3 - 2 = 1 ta qoldi

    def test_choice_view_shows_today_and_tomorrow_remaining(self):
        self.chat()
        with _Plan("pro"):
            text, _ = bot.build_inbox_reminder_choice(self.o, 5)
        self.assertIn("bugun: 3", text)
        self.assertIn("ertaga: 3", text)
        tomorrow = inbox.reminder_due("next9", __import__("time").time(), TZ)[1]
        for i in (11, 12, 13):
            self.chat(i)
            db.schedule_inbox_reminder(self.o, i, 1.0, tomorrow, 3, __import__("time").time())
        with _Plan("pro"):
            text, _ = bot.build_inbox_reminder_choice(self.o, 5)
        self.assertIn("bugun: 3", text)
        self.assertIn("ertaga: 0", text)


class LegacyAndDowngradeTests(DbBase):
    def test_legacy_answered_priority_rows_are_migrated(self):
        for i in range(1, 6):
            self.chat(i)
        with db.get_conn() as conn, conn.cursor() as cur:  # eski versiya: javob berilgan suhbatlarda ⭐ qolgan
            cur.execute("UPDATE inbox_chats SET is_priority = TRUE WHERE owner_user_id=%s", (self.o,))
            cur.execute("UPDATE inbox_chats SET pending = FALSE, pending_count = 0, waiting_since = NULL WHERE owner_user_id=%s AND chat_id IN (1,2,3)", (self.o,))
        self.assertEqual(db.count_priority_chats(self.o, NOW), 5)
        db.init_db()
        db.init_db()  # idempotent
        self.assertEqual(db.count_priority_chats(self.o, NOW), 2)  # faqat javobsiz 4, 5 qoldi
        self.assertEqual(db.set_inbox_priority(self.o, 1, True, 5, NOW), "no_chat")

    def _mark_many(self, n):
        for i in range(1, n + 1):
            self.chat(i, at=NOW - 1000 * (n - i + 1))  # chat 1 eng eski
            db.set_inbox_priority(self.o, i, True, 20, NOW)

    def test_ultra_to_pro_enforces_effective_priority_limit(self):
        self._mark_many(20)
        self.chat(99, at=NOW - 10)  # oddiy suhbat
        _, rows = db.get_pending_chats(self.o, 30, NOW, priority_first=True, priority_limit=5)
        active = [r["chat_id"] for r in rows if r["is_priority"]]
        self.assertEqual(active, [1, 2, 3, 4, 5])  # eng uzoq kutgan 5 tasi
        self.assertEqual([r["chat_id"] for r in rows[:5]], [1, 2, 3, 4, 5])
        self.assertEqual(sum(1 for r in rows if r["marked"]), 20)  # qolgan belgilar saqlanadi (Ultra'ga qaytsa ishlaydi)
        self.assertEqual(db.get_pending_stats(self.o, NOW, priority_limit=5)["priority"], 5)
        _, rows = db.get_pending_chats(self.o, 30, NOW, priority_first=True, priority_limit=20)
        self.assertEqual(sum(1 for r in rows if r["is_priority"]), 20)  # Ultra'ga qaytdi
        # yangi belgi qo'yib bo'lmaydi; ortiqcha belgilarni olib tashlash mumkin
        self.assertEqual(db.set_inbox_priority(self.o, 99, True, 5, NOW), "limit")
        self.assertEqual(db.set_inbox_priority(self.o, 20, True, 5, NOW), "limit")  # saqlangan, lekin faol emas
        for i in range(6, 21):
            self.assertEqual(db.set_inbox_priority(self.o, i, False, 5, NOW), "ok")
        self.assertEqual(db.count_priority_chats(self.o, NOW), 5)

    def test_bot_views_use_effective_limit_after_downgrade(self):
        self._mark_many(8)
        with _Plan("pro"), patch("bot.time.time", return_value=NOW):
            text, m = bot.build_inbox_view(self.o)
            self.assertEqual(text.count("⭐"), 5)
            _, m = bot.build_inbox_priority_view(self.o)
        labels = [b.text for row in m.inline_keyboard for b in row]
        self.assertEqual(sum(1 for x in labels if x.startswith("⭐")), 5)
        self.assertEqual(sum(1 for x in labels if x.startswith("☆")), 3)  # faol emas, lekin olib tashlash mumkin
        data = [b.callback_data for row in m.inline_keyboard for b in row]
        self.assertEqual(sum(1 for d in data if d.startswith("ib_unpr:")), 8)

    def test_free_plus_ignore_marks_entirely(self):
        self._mark_many(3)
        with _Plan("plus"), patch("bot.time.time", return_value=NOW):
            text, _ = bot.build_inbox_view(self.o)
        self.assertNotIn("⭐", text)


class PriorityOldButtonTests(DbBase):
    def test_old_button_cannot_mark_answered_chat(self):
        for i in range(1, 8):
            self.chat(i)
        db.record_owner_reply(self.o, 1, 9, NOW)  # A javob berildi
        self.assertEqual(db.set_inbox_priority(self.o, 1, True, 5, NOW), "no_chat")  # eski ib_pr:A
        res = [db.set_inbox_priority(self.o, i, True, 5, NOW) for i in range(2, 7)]
        self.assertEqual(res, ["ok"] * 5)
        db.record_customer_message(self.o, 1, 10, "Ali", NOW + 1)  # A ga yangi xabar
        self.assertEqual(db.count_priority_chats(self.o, NOW + 1), 5)  # 6 emas

    def test_unmark_still_allowed_for_answered_chat(self):
        self.chat()
        db.set_inbox_priority(self.o, 5, True, 5, NOW)
        db.record_owner_reply(self.o, 5, 9, NOW)
        self.assertEqual(db.set_inbox_priority(self.o, 5, False, 5, NOW), "ok")

    def test_old_chat_beyond_retention_cannot_be_marked(self):
        self.chat(at=NOW - 15 * 86400)
        self.assertEqual(db.set_inbox_priority(self.o, 5, True, 5, NOW), "no_chat")


class PaginationTests(DbBase):
    def _seed(self, n=25):
        for i in range(1, n + 1):
            self.chat(1000 + i, name=f"M{i:02d}", at=NOW - 60 * (n - i + 1))  # M01 eng eski

    def _data(self, markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    def test_all_chats_reachable_across_pages_in_stable_order(self):
        self._seed()
        seen = []
        with _Plan("ultra"), patch("bot.time.time", return_value=NOW):
            for page in range(3):
                _, m = bot.build_inbox_priority_view(self.o, "", page)
                seen += [d for d in self._data(m) if d.startswith("ib_pr:")]
        ids = [int(d.split(":")[1]) for d in seen]
        self.assertEqual(ids, [1000 + i for i in range(1, 26)])  # 25 ta, takrorsiz, barqaror tartibda
        with _Plan("ultra"), patch("bot.time.time", return_value=NOW):
            _, m = bot.build_inbox_priority_view(self.o, "", 0)
        self.assertIn("ib_priority:1", self._data(m))
        self.assertNotIn("ib_priority:-1", self._data(m))

    def test_reminders_view_reaches_11th_chat(self):
        self._seed(12)
        with _Plan("pro"), patch("bot.time.time", return_value=NOW):
            _, m0 = bot.build_inbox_reminders_view(self.o, "", 0)
            _, m1 = bot.build_inbox_reminders_view(self.o, "", 1)
        self.assertNotIn("ib_rem:1011:0", self._data(m0))
        self.assertIn("ib_rem:1011:1", self._data(m1))
        self.assertIn("ib_reminders:1", self._data(m0))
        self.assertIn("ib_reminders:0", self._data(m1))

    def test_out_of_range_page_clamps_and_garbage_page_is_zero(self):
        self._seed(12)
        with _Plan("pro"), patch("bot.time.time", return_value=NOW):
            t1, m = bot.build_inbox_reminders_view(self.o, "", 99)
            self.assertIn("ib_rem:1012:1", self._data(m))
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        for data in ("ib_priority:abc", "ib_priority:-3", "ib_reminders:zz", "ib_pr:1001:x", "ib_rem:1001:9999"):
            with _Plan("pro"), patch("bot.time.time", return_value=NOW):
                self.assertTrue(run(bot.handle_inbox_callback(q, self.o, data, "uz")), data)

    def test_buttons_keep_page_and_old_format_still_works(self):
        self._seed(12)
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        with _Plan("pro"), patch("bot.time.time", return_value=NOW):
            run(bot.handle_inbox_callback(q, self.o, "ib_pr:1011:1", "uz"))  # 2-sahifadagi chat
            _, m = q.edit_message_text.await_args.args[0], q.edit_message_text.await_args.kwargs["reply_markup"]
            self.assertIn("ib_pr:1012:1", self._data(m))  # foydalanuvchi 2-sahifada qoladi (belgilangan suhbat 1-sahifa tepasiga o'tadi)
            with patch("bot.time.time", return_value=NOW):
                _, m0 = bot.build_inbox_priority_view(self.o, "", 0)
            self.assertIn("ib_unpr:1011:0", self._data(m0))
            run(bot.handle_inbox_callback(q, self.o, "ib_pr:1002", "uz"))  # eski format (sahifasiz)
        self.assertEqual(db.count_priority_chats(self.o, NOW), 2)

    def test_callback_data_with_page_fits_limit(self):
        self.assertLessEqual(len(f"ib_rt:{-10**13}:next9:99".encode()), 64)
        self.assertLessEqual(len(f"ib_unpr:{-10**13}:99".encode()), 64)


class I18nTests(unittest.TestCase):
    KEYS = ["btn_inbox_priority", "btn_inbox_reminders", "inbox_priority_added", "inbox_priority_removed", "inbox_priority_limit",
            "inbox_reminder_title", "inbox_reminder_created", "inbox_reminder_cancelled", "inbox_reminder_sent", "inbox_reminder_limit",
            "inbox_reminder_already_answered", "btn_inbox_rt_1h", "btn_inbox_rt_next9", "feature_inbox_priority", "feature_inbox_reminder"]

    def test_keys_exist_in_three_languages(self):
        import i18n
        for k in self.KEYS:
            self.assertIn(k, i18n.T)
            for lang in ("uz", "en", "ru"):
                self.assertTrue(i18n.T[k].get(lang), (k, lang))
            self.assertNotEqual(i18n.T[k]["en"], i18n.T[k]["uz"], k)

    def test_callback_data_fits_telegram_limit(self):
        for d in ("ib_priority", "ib_reminders", f"ib_pr:{-10**13}", f"ib_unpr:{-10**13}", f"ib_rem:{-10**13}", f"ib_rt:{-10**13}:next9", f"ib_rc:{-10**13}"):
            self.assertLessEqual(len(d.encode()), 64)


if __name__ == "__main__":
    unittest.main()
