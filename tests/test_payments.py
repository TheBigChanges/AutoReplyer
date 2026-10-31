"""Payments v1.0 (Telegram Stars): hisob-kitob, baza (atomik faollashtirish/refund), bot handlerlari, i18n."""
import asyncio
import os
import random
import re
import sys
import threading
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
import i18n  # noqa: E402
import payments as pay  # noqa: E402
from i18n import t  # noqa: E402
from payments import PlanState  # noqa: E402
from telegram.error import TelegramError  # noqa: E402
from telegram.ext import ApplicationHandlerStop  # noqa: E402

run = asyncio.run
DAY = 86400.0
NOW = 1_800_000_000.0
add_months = lambda ts, n: ts + n * 30 * DAY  # noqa: E731  (toza testlar uchun oddiy 30 kunlik oy)


# --------------------------------------------------------------------------- toza hisob-kitob
class PriceTests(unittest.TestCase):
    def test_price_table_matches_approved(self):
        table = {"plus": (15, 41, 77, 144), "pro": (35, 95, 179, 336), "ultra": (70, 189, 357, 672)}
        for plan, prices in table.items():
            self.assertEqual(tuple(pay.stars_price(plan, m) for m in (1, 3, 6, 12)), prices, plan)

    def test_bad_input(self):
        with self.assertRaises(pay.PaymentError):
            pay.stars_price("free", 1)
        with self.assertRaises(pay.PaymentError):
            pay.stars_price("plus", 2)


class QuoteTests(unittest.TestCase):
    def q(self, state, target, months=1, now=NOW):
        return pay.quote(state, target, months, now, add_months)

    def test_new_from_free(self):
        q = self.q(PlanState(), "plus", 3)
        self.assertEqual((q.kind, q.pay, q.credit), ("new", 41, 0))
        self.assertEqual(q.new_state.expires_at, NOW + 90 * DAY)

    def test_expired_plan_is_new(self):
        q = self.q(PlanState("pro", NOW - 10, None), "plus")
        self.assertEqual(q.kind, "new")
        self.assertEqual(q.new_state.expires_at, NOW + 30 * DAY)

    def test_extend_keeps_remaining_time(self):
        st = PlanState("plus", NOW + 10 * DAY, None)
        q = self.q(st, "plus", 1)
        self.assertEqual(q.kind, "extend")
        self.assertEqual(q.pay, 15)
        self.assertEqual(q.new_state.expires_at, NOW + 40 * DAY)

    def test_upgrade_credits_unused_value(self):
        st = PlanState("plus", NOW + 15 * DAY, None)  # 15 kun * 0.5 = 7.5 -> 7
        q = self.q(st, "pro", 1)
        self.assertEqual((q.kind, q.credit, q.pay), ("upgrade", 7, 28))
        self.assertEqual(q.new_state.plan, "pro")
        self.assertEqual(q.new_state.expires_at, NOW + 30 * DAY)

    def test_upgrade_never_charges_more_than_price(self):
        for days in (0.01, 1, 15, 29):
            q = self.q(PlanState("plus", NOW + days * DAY, None), "ultra", 1)
            self.assertLessEqual(q.pay, q.price)
            self.assertGreaterEqual(q.pay, 0)

    def test_big_credit_switches_without_payment_and_adds_days(self):
        st = PlanState("pro", NOW + 330 * DAY, 336 / 360)  # qolgan qiymati ~308
        q = self.q(st, "plus", 1)  # pastga
        self.assertEqual((q.kind, q.pay), ("downgrade", 0))
        st2 = PlanState("plus", NOW + 360 * DAY, 144 / 360)  # qolgan qiymat 144 >= pro 1 oylik 35
        q2 = self.q(st2, "pro", 1)
        self.assertEqual((q2.kind, q2.pay), ("switch", 0))
        self.assertGreater(q2.new_state.expires_at, NOW + 30 * DAY)

    def test_downgrade_converts_value_to_days_no_money(self):
        st = PlanState("ultra", NOW + 30 * DAY, None)  # qiymat 70 -> plus kunlari: 70 / 0.5 = 140
        q = self.q(st, "plus", 1)
        self.assertEqual((q.kind, q.pay), ("downgrade", 0))
        self.assertAlmostEqual((q.new_state.expires_at - NOW) / DAY, 140, places=3)
        self.assertIsNone(q.new_state.rate)

    def test_unlimited_paid_plan_cannot_be_bought_over(self):
        with self.assertRaises(pay.PaymentError):
            self.q(PlanState("pro", None, None), "ultra")


class ApplyTests(unittest.TestCase):
    def test_extend_applies_on_top(self):
        st = PlanState("plus", NOW + 10 * DAY, None)
        new = pay.apply_order(st, "extend", "plus", 1, 15, 0, NOW, add_months)
        self.assertEqual(new.expires_at, NOW + 40 * DAY)

    def test_extend_but_plan_meanwhile_expired_starts_fresh_period(self):
        st = PlanState("plus", NOW - 5, None)
        new = pay.apply_order(st, "extend", "plus", 1, 15, 0, NOW, add_months)
        self.assertEqual(new.expires_at, NOW + 30 * DAY)

    def test_refund_takes_back_days(self):
        st = PlanState("plus", NOW + 60 * DAY, 0.5)
        new = pay.apply_refund(st, 15, NOW)  # 15 Stars / 0.5 = 30 kun
        self.assertAlmostEqual((new.expires_at - NOW) / DAY, 30, places=6)
        self.assertEqual(new.plan, "plus")

    def test_refund_beyond_period_goes_free(self):
        st = PlanState("plus", NOW + 10 * DAY, 0.5)
        self.assertEqual(pay.apply_refund(st, 15, NOW), PlanState("free", None, None))

    def test_refund_leaves_unlimited_and_free_alone(self):
        for st in (PlanState("pro", None, None), PlanState()):
            self.assertEqual(pay.apply_refund(st, 35, NOW), st)

    def test_buy_then_refund_roundtrip(self):
        st = PlanState()
        q = pay.quote(st, "pro", 3, NOW, add_months)
        after = pay.apply_order(st, q.kind, "pro", 3, q.pay, q.credit, NOW, add_months)
        back = pay.apply_refund(after, q.pay, NOW)
        self.assertEqual(back.plan, "free")


# --------------------------------------------------------------------------- baza
@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL kerak")
class DbBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.u = random.randint(10**12, 9 * 10**12)
        self.v = self.u + 1
        self.addCleanup(self._clean)

    def _clean(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM payment_audit WHERE user_id IN (%s, %s)", (self.u, self.v))
            cur.execute("DELETE FROM payments WHERE user_id IN (%s, %s)", (self.u, self.v))
            cur.execute("DELETE FROM users WHERE user_id IN (%s, %s)", (self.u, self.v))

    def order(self, user=None, plan="plus", months=1, now=None, state=None):
        user = user or self.u
        now = now or time.time()
        state = state or db.get_user_plan_state(user)
        q = pay.quote(state, plan, months, now, add_months)
        token = "T" + str(random.randint(10**9, 10**10))
        db.create_payment_order(user, token, q, state, 1800, now)
        return token, q

    def pay(self, token, q, charge=None, user=None, amount=None, now=None, currency="XTR"):
        charge = charge or "ch" + str(random.randint(10**9, 10**10))
        return db.activate_payment(token, charge, user or self.u, q.pay if amount is None else amount, add_months,
                                   now or time.time(), currency), charge

    def plan(self, user=None):
        return db.get_user_plan_state(user or self.u)


class ActivationTests(DbBase):
    def test_order_without_payment_gives_no_plan(self):
        self.order()
        self.assertEqual(self.plan().plan, "free")

    def test_successful_payment_grants_plan(self):
        now = time.time()
        token, q = self.order(now=now)
        res, _ = self.pay(token, q, now=now)
        self.assertEqual(res["status"], "activated")
        st = self.plan()
        self.assertEqual(st.plan, "plus")
        self.assertAlmostEqual(st.expires_at, now + 30 * DAY, delta=1)
        self.assertEqual(db.get_payment(token)["status"], "paid")

    def test_repeated_charge_id_grants_once(self):
        now = time.time()
        token, q = self.order(now=now)
        _, charge = self.pay(token, q, now=now)
        first = self.plan().expires_at
        res, _ = self.pay(token, q, charge=charge, now=now)
        self.assertEqual(res["status"], "duplicate")
        self.assertEqual(self.plan().expires_at, first)

    def test_parallel_same_charge_activates_once(self):
        now = time.time()
        token, q = self.order(now=now)
        results = []

        def go():
            results.append(db.activate_payment(token, "chPAR", self.u, q.pay, add_months, now)["status"])

        threads = [threading.Thread(target=go) for _ in range(6)]
        [x.start() for x in threads]
        [x.join() for x in threads]
        self.assertEqual(sorted(results), ["activated"] + ["duplicate"] * 5)
        self.assertAlmostEqual(self.plan().expires_at, now + 30 * DAY, delta=1)

    def test_second_charge_for_same_order_is_unmatched_not_double_grant(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, charge="c1", now=now)
        res, _ = self.pay(token, q, charge="c2", now=now)
        self.assertEqual(res["status"], "unmatched")
        self.assertTrue(res["reason"].startswith("order_closed"))
        self.assertAlmostEqual(self.plan().expires_at, now + 30 * DAY, delta=1)

    def test_wrong_amount_is_unmatched(self):
        token, q = self.order()
        res, _ = self.pay(token, q, amount=q.pay - 1)
        self.assertEqual((res["status"], res["reason"]), ("unmatched", "amount_mismatch"))
        self.assertEqual(self.plan().plan, "free")

    def test_wrong_currency_is_unmatched(self):
        token, q = self.order()
        res, _ = self.pay(token, q, currency="USD")
        self.assertEqual(res["status"], "unmatched")

    def test_someone_elses_order_is_unmatched(self):
        token, q = self.order()
        res, _ = self.pay(token, q, user=self.v)
        self.assertEqual((res["status"], res["reason"]), ("unmatched", "wrong_user"))
        self.assertEqual(self.plan(self.v).plan, "free")
        self.assertEqual(self.plan().plan, "free")

    def test_unknown_order_is_unmatched_and_stored_once(self):
        res = db.activate_payment("nope", "chU", self.u, 15, add_months)
        self.assertEqual(res["status"], "unmatched")
        self.assertEqual(db.activate_payment("nope", "chU", self.u, 15, add_months)["status"], "duplicate")

    def test_paid_after_order_expired_still_grants(self):
        now = time.time()
        token, q = self.order(now=now - 4000)
        db.expire_old_orders(now)
        self.assertEqual(db.get_payment(token)["status"], "expired")
        res, _ = self.pay(token, q, now=now)
        self.assertEqual(res["status"], "activated")  # pul olingan — tarif beriladi

    def test_new_order_cancels_previous_pending(self):
        t1, _ = self.order()
        t2, _ = self.order()
        self.assertEqual(db.get_payment(t1)["status"], "cancelled")
        self.assertEqual(db.get_payment(t2)["status"], "pending")

    def test_extend_keeps_remaining_time(self):
        now = time.time()
        db.set_user_plan(self.u, "plus", now + 10 * DAY)
        token, q = self.order(now=now)
        self.assertEqual(q.kind, "extend")
        self.pay(token, q, now=now)
        self.assertAlmostEqual(self.plan().expires_at, now + 40 * DAY, delta=1)

    def test_plan_changed_after_order_extend_does_not_lose_paid_time(self):
        now = time.time()
        db.set_user_plan(self.u, "plus", now + 10 * DAY)
        token, q = self.order(now=now)
        db.set_user_plan(self.u, "free")  # orada admin tarifni olib tashladi
        res, _ = self.pay(token, q, now=now)
        self.assertEqual(res["status"], "activated")
        self.assertAlmostEqual(self.plan().expires_at, now + 30 * DAY, delta=1)

    def test_upgrade_accounts_unused_value(self):
        now = time.time()
        db.set_user_plan(self.u, "plus", now + 15 * DAY)
        token, q = self.order(plan="pro", now=now)
        self.assertEqual((q.kind, q.credit, q.pay), ("upgrade", 7, 28))
        res, _ = self.pay(token, q, now=now)
        self.assertEqual(res["status"], "activated")
        st = self.plan()
        self.assertEqual(st.plan, "pro")
        self.assertAlmostEqual(st.expires_at, now + 30 * DAY, delta=1)

    def test_charge_id_unique_in_db(self):
        t1, q1 = self.order()
        self.pay(t1, q1, charge="same")
        with self.assertRaises(Exception):
            with db.get_conn() as conn, conn.cursor() as cur:
                cur.execute("INSERT INTO payments (token, user_id, kind, stars, status, charge_id, created_at) "
                            "VALUES ('x1', %s, 'new', 1, 'paid', 'same', 0)", (self.u,))

    def test_audit_trail_written(self):
        token, q = self.order()
        self.pay(token, q)
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT event FROM payment_audit WHERE user_id = %s ORDER BY id", (self.u,))
            events = [r[0] if not isinstance(r, dict) else r["event"] for r in cur.fetchall()]
        self.assertEqual(events, ["order_created", "paid"])


class SwitchTests(DbBase):
    def test_free_downgrade_switch(self):
        now = time.time()
        db.set_user_plan(self.u, "ultra", now + 30 * DAY)
        st = self.plan()
        q = pay.quote(st, "plus", 1, now, add_months)
        self.assertTrue(db.switch_plan(self.u, "ultra", int(st.expires_at), q, "S1", now))
        after = self.plan()
        self.assertEqual(after.plan, "plus")
        self.assertAlmostEqual((after.expires_at - now) / DAY, 140, delta=0.01)

    def test_switch_rejected_when_state_changed(self):
        now = time.time()
        db.set_user_plan(self.u, "ultra", now + 30 * DAY)
        st = self.plan()
        q = pay.quote(st, "plus", 1, now, add_months)
        db.set_user_plan(self.u, "pro", now + 30 * DAY)  # orada o'zgardi
        self.assertFalse(db.switch_plan(self.u, "ultra", int(st.expires_at), q, "S2", now))
        self.assertEqual(self.plan().plan, "pro")

    def test_switch_twice_with_same_snapshot_only_once(self):
        now = time.time()
        db.set_user_plan(self.u, "ultra", now + 30 * DAY)
        st = self.plan()
        q = pay.quote(st, "plus", 1, now, add_months)
        ok = [db.switch_plan(self.u, "ultra", int(st.expires_at), q, f"S{i}", now) for i in range(2)]
        self.assertEqual(ok, [True, False])

    def test_switch_refuses_paid_quote(self):
        q = pay.quote(PlanState(), "plus", 1, NOW, add_months)
        with self.assertRaises(ValueError):
            db.switch_plan(self.u, "free", None, q, "S3")


class RefundDbTests(DbBase):
    def paid(self, plan="plus", months=1, now=None):
        now = now or time.time()
        token, q = self.order(plan=plan, months=months, now=now)
        _, charge = self.pay(token, q, now=now, charge="ch" + token)
        return token, charge

    def test_refund_state_consistent(self):
        now = time.time()
        token, charge = self.paid(now=now)
        row, err = db.begin_refund(charge)
        self.assertIsNone(err)
        self.assertEqual(row["status"], "refunding")
        new = db.finish_refund(row["id"], now)
        self.assertEqual(new.plan, "free")
        self.assertEqual(db.get_payment(token)["status"], "refunded")
        self.assertEqual(self.plan().plan, "free")

    def test_double_refund_takes_days_once(self):
        now = time.time()
        db.set_user_plan(self.u, "plus", now + 60 * DAY)
        token, charge = self.paid(now=now)  # extend: +30 kun -> 90 kun
        row, _ = db.begin_refund(token)
        self.assertIsNotNone(row)
        second, reason = db.begin_refund(token)
        self.assertIsNone(second)
        self.assertEqual(reason, "not_paid:refunding")
        db.finish_refund(row["id"], now)
        self.assertIsNone(db.finish_refund(row["id"], now))
        self.assertAlmostEqual((self.plan().expires_at - now) / DAY, 60, delta=0.5)

    def test_refund_failure_restores_paid(self):
        token, charge = self.paid()
        row, _ = db.begin_refund(charge)
        db.fail_refund(row["id"])
        self.assertEqual(db.get_payment(token)["status"], "paid")
        self.assertEqual(self.plan().plan, "plus")  # tarifga tegilmagan

    def test_refund_unknown_and_unpaid(self):
        self.assertEqual(db.begin_refund("zzz"), (None, "not_found"))
        token, _ = self.order()
        self.assertEqual(db.begin_refund(token)[1], "not_paid:pending")

    def test_refund_leaves_unlimited_plan(self):
        now = time.time()
        token, charge = self.paid(now=now)
        db.set_user_plan(self.u, "ultra", None)  # admin muddatsiz berdi
        row, _ = db.begin_refund(charge)
        db.finish_refund(row["id"], now)
        self.assertEqual(self.plan(), PlanState("ultra", None, None))


# --------------------------------------------------------------------------- bot
def _bot_mock():
    b = MagicMock()
    b.send_message = AsyncMock()
    b.send_invoice = AsyncMock()
    b.refund_star_payment = AsyncMock(return_value=True)
    return b


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL kerak")
class BotBase(DbBase):
    def setUp(self):
        super().setUp()
        p = patch.object(bot, "ADMIN_ID", 999)
        p.start()
        self.addCleanup(p.stop)
        bot._pending_payments.clear()
        self.addCleanup(bot._pending_payments.clear)

    def pre(self, token, user=None, amount=15, currency="XTR"):
        q = MagicMock()
        q.from_user.id = user or self.u
        q.invoice_payload, q.total_amount, q.currency = token, amount, currency
        q.answer = AsyncMock()
        upd = MagicMock()
        upd.pre_checkout_query = q
        run(bot.on_pre_checkout(upd, MagicMock()))
        return q.answer.await_args.kwargs

    def sent_texts(self, b):
        return [c.kwargs.get("text") or c.args[1] for c in b.send_message.await_args_list]


class PreCheckoutTests(BotBase):
    def test_valid_order_ok(self):
        token, q = self.order()
        self.assertTrue(self.pre(token, amount=q.pay)["ok"])

    def test_wrong_amount_rejected(self):
        token, q = self.order()
        self.assertFalse(self.pre(token, amount=q.pay + 1)["ok"])
        self.assertFalse(self.pre(token, amount=1)["ok"])

    def test_wrong_currency_rejected(self):
        token, q = self.order()
        self.assertFalse(self.pre(token, amount=q.pay, currency="USD")["ok"])

    def test_someone_elses_order_rejected(self):
        token, q = self.order()
        self.assertFalse(self.pre(token, user=self.v, amount=q.pay)["ok"])

    def test_unknown_order_rejected(self):
        self.assertFalse(self.pre("PNOPE")["ok"])
        self.assertFalse(self.pre("")["ok"])

    def test_expired_and_cancelled_rejected(self):
        t1, q1 = self.order()
        t2, q2 = self.order()  # t1 bekor bo'ldi
        self.assertFalse(self.pre(t1, amount=q1.pay)["ok"])
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE payments SET expires_at = 1 WHERE token = %s", (t2,))
        self.assertFalse(self.pre(t2, amount=q2.pay)["ok"])

    def test_paid_order_rejected_again(self):
        token, q = self.order()
        self.pay(token, q)
        self.assertFalse(self.pre(token, amount=q.pay)["ok"])

    def test_plan_changed_since_order_rejected(self):
        token, q = self.order()
        db.set_user_plan(self.u, "pro", time.time() + 5 * DAY)
        self.assertFalse(self.pre(token, amount=q.pay)["ok"])

    def test_blocked_user_rejected(self):
        token, q = self.order()
        with patch.object(db, "get_block", return_value={"reason": "x"}):
            self.assertFalse(self.pre(token, amount=q.pay)["ok"])

    def test_db_error_rejects_safely(self):
        token, q = self.order()
        with patch.object(db, "get_payment", side_effect=RuntimeError("db down")):
            self.assertFalse(self.pre(token, amount=q.pay)["ok"])

    def test_stars_disabled_rejects(self):
        token, q = self.order()
        with patch.object(bot, "PAYMENTS_STARS_ENABLED", False):
            self.assertFalse(self.pre(token, amount=q.pay)["ok"])

    def test_pre_checkout_ok_without_payment_gives_no_plan(self):
        token, q = self.order()
        self.assertTrue(self.pre(token, amount=q.pay)["ok"])
        self.assertEqual(self.plan().plan, "free")


class ProcessPaymentTests(BotBase):
    def test_success_notifies_user_and_admin(self):
        token, q = self.order()
        b = _bot_mock()
        self.assertEqual(run(bot.process_payment(b, self.u, token, "chA", q.pay, "XTR")), "activated")
        chats = [c.kwargs.get("chat_id") for c in b.send_message.await_args_list]
        self.assertIn(self.u, chats)
        self.assertIn(999, chats)
        self.assertEqual(self.plan().plan, "plus")

    def test_duplicate_event_does_not_regrant_or_renotify(self):
        token, q = self.order()
        b = _bot_mock()
        run(bot.process_payment(b, self.u, token, "chB", q.pay, "XTR"))
        exp = self.plan().expires_at
        b.send_message.reset_mock()
        self.assertEqual(run(bot.process_payment(b, self.u, token, "chB", q.pay, "XTR")), "duplicate")
        b.send_message.assert_not_awaited()
        self.assertEqual(self.plan().expires_at, exp)

    def test_unmatched_alerts_admin_and_tells_user(self):
        b = _bot_mock()
        self.assertEqual(run(bot.process_payment(b, self.u, "PGHOST", "chC", 15, "XTR")), "unmatched")
        texts = " ".join(self.sent_texts(b))
        self.assertIn("/refund chC", texts)
        self.assertEqual(self.plan().plan, "free")

    def test_db_down_payment_kept_and_recovered(self):
        token, q = self.order()
        b = _bot_mock()
        with patch.object(db, "activate_payment", side_effect=RuntimeError("db down")):
            self.assertEqual(run(bot.process_payment(b, self.u, token, "chD", q.pay, "XTR")), "deferred")
            self.assertEqual(len(bot._pending_payments), 1)
            ctx = MagicMock()
            ctx.bot = b
            run(bot.payment_retry_job(ctx))  # baza hali ishlamaydi — navbatda qoladi
            self.assertEqual(len(bot._pending_payments), 1)
        self.assertEqual(self.plan().plan, "free")
        ctx = MagicMock()
        ctx.bot = b
        run(bot.payment_retry_job(ctx))  # baza tiklandi
        self.assertEqual(len(bot._pending_payments), 0)
        self.assertEqual(self.plan().plan, "plus")
        run(bot.payment_retry_job(ctx))
        self.assertEqual(self.plan().plan, "plus")

    def test_deferred_not_queued_twice(self):
        token, q = self.order()
        with patch.object(db, "activate_payment", side_effect=RuntimeError("x")):
            for _ in range(3):
                run(bot.process_payment(_bot_mock(), self.u, token, "chE", q.pay, "XTR"))
        self.assertEqual(len(bot._pending_payments), 1)


class GateBypassTests(BotBase):
    def _upd(self, paid):
        upd = MagicMock()
        upd.callback_query = None
        upd.effective_user.id = self.u
        upd.effective_user.is_bot = False
        upd.effective_chat.type = "private"
        upd.message.text = None
        upd.message.reply_text = AsyncMock()
        upd.message.successful_payment = MagicMock() if paid else None
        return upd

    def test_left_channel_user_payment_not_stopped_but_text_is(self):
        with patch.object(bot, "REQUIRED_CHANNEL_ID", -100), patch.object(bot, "_sub_exempt", return_value=False), \
                patch.object(bot, "is_subscribed_cached", AsyncMock(return_value=False)):
            run(bot.subscribe_gate(self._upd(True), MagicMock()))  # to'xtatilmaydi
            with self.assertRaises(ApplicationHandlerStop):
                run(bot.subscribe_gate(self._upd(False), MagicMock()))

    def test_blocked_user_payment_not_stopped(self):
        with patch.object(db, "get_block", return_value={"reason": "x"}):
            run(bot.block_gate(self._upd(True), MagicMock()))
            with patch.object(bot, "handle_blocked_update", AsyncMock()), self.assertRaises(ApplicationHandlerStop):
                run(bot.block_gate(self._upd(False), MagicMock()))

    def test_confirmed_payment_survives_leaving_channel(self):
        token, q = self.order()
        with patch.object(bot, "REQUIRED_CHANNEL_ID", -100), patch.object(bot, "is_subscribed_cached", AsyncMock(return_value=False)):
            run(bot.process_payment(_bot_mock(), self.u, token, "chF", q.pay, "XTR"))
        self.assertEqual(self.plan().plan, "plus")


class RefundCommandTests(BotBase):
    def _cmd(self, ref, b):
        upd = MagicMock()
        upd.effective_user.id = 999
        upd.message.reply_text = AsyncMock()
        ctx = MagicMock()
        ctx.args = [ref]
        ctx.bot = b
        run(bot.cmd_refund(upd, ctx))
        return upd.message.reply_text.await_args.args[0]

    def _paid(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, charge="chR" + token, now=now)
        return token, "chR" + token

    def test_refund_ok_returns_stars_and_takes_plan_back(self):
        token, charge = self._paid()
        b = _bot_mock()
        msg = self._cmd(charge, b)
        b.refund_star_payment.assert_awaited_once_with(user_id=self.u, telegram_payment_charge_id=charge)
        self.assertIn("✅", msg)
        self.assertEqual(db.get_payment(token)["status"], "refunded")
        self.assertEqual(self.plan().plan, "free")
        self.assertEqual(self.sent_texts(b)[0].count("↩️"), 1)

    def test_refund_api_error_keeps_everything(self):
        token, charge = self._paid()
        b = _bot_mock()
        b.refund_star_payment.side_effect = TelegramError("CHARGE_NOT_FOUND")
        msg = self._cmd(charge, b)
        self.assertIn("❌", msg)
        self.assertEqual(db.get_payment(token)["status"], "paid")
        self.assertEqual(self.plan().plan, "plus")

    def test_already_refunded_by_telegram_is_finished(self):
        token, charge = self._paid()
        b = _bot_mock()
        b.refund_star_payment.side_effect = TelegramError("Bad Request: CHARGE_ALREADY_REFUNDED")
        self._cmd(charge, b)
        self.assertEqual(db.get_payment(token)["status"], "refunded")

    def test_second_refund_rejected_without_api_call(self):
        token, charge = self._paid()
        b = _bot_mock()
        self._cmd(charge, b)
        b.refund_star_payment.reset_mock()
        msg = self._cmd(charge, b)
        b.refund_star_payment.assert_not_awaited()
        self.assertIn("refunded", msg)

    def test_non_admin_ignored(self):
        upd = MagicMock()
        upd.effective_user.id = 5
        upd.message.reply_text = AsyncMock()
        run(bot.cmd_refund(upd, MagicMock(args=["x"])))
        upd.message.reply_text.assert_not_awaited()


class ScreenTests(BotBase):
    def test_duration_and_quote_screens(self):
        text, markup = bot.build_pay_duration_view(self.u, "pro")
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertEqual(data[:4], [f"pay_q:pro:{m}" for m in (1, 3, 6, 12)])
        text, markup = bot.build_pay_quote_view(self.u, "pro", 3)
        self.assertIn("95", text)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "pay_buy:pro:3:95")

    def test_buy_creates_order_and_sends_xtr_invoice(self):
        q = MagicMock()
        q.answer = AsyncMock()
        b = _bot_mock()
        ctx = MagicMock()
        ctx.bot = b
        run(bot.handle_pay_callback(q, ctx, self.u, "pay_buy:plus:1:15"))
        kw = b.send_invoice.await_args.kwargs
        self.assertEqual(kw["currency"], "XTR")
        self.assertEqual(kw["provider_token"], "")
        self.assertEqual(kw["prices"][0].amount, 15)
        order = db.get_payment(kw["payload"])
        self.assertEqual((order["status"], order["stars"], order["user_id"]), ("pending", 15, self.u))
        self.assertEqual(self.plan().plan, "free")  # invoice yuborildi, lekin tarif berilmadi

    def test_buy_with_stale_price_does_not_invoice(self):
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        b = _bot_mock()
        ctx = MagicMock()
        ctx.bot = b
        run(bot.handle_pay_callback(q, ctx, self.u, "pay_buy:plus:1:14"))
        b.send_invoice.assert_not_awaited()
        q.edit_message_text.assert_awaited()

    def test_bad_callback_data_is_rejected(self):
        for data in ("pay_buy:free:1:1", "pay_buy:plus:2:15", "pay_q:plus:x", "pay_zzz:plus:1", "pay_q"):
            q = MagicMock()
            q.answer = AsyncMock()
            b = _bot_mock()
            ctx = MagicMock()
            ctx.bot = b
            run(bot.handle_pay_callback(q, ctx, self.u, data))
            b.send_invoice.assert_not_awaited()
            self.assertTrue(q.answer.await_args.kwargs.get("show_alert"), data)

    def test_free_switch_button_applies_and_stale_snapshot_blocked(self):
        now = time.time()
        db.set_user_plan(self.u, "ultra", now + 30 * DAY)
        st = self.plan()
        text, markup = bot.build_pay_quote_view(self.u, "plus", 1)
        data = markup.inline_keyboard[0][0].callback_data
        self.assertTrue(data.startswith("pay_swy:plus:1:ultra:"))
        stale = data.rsplit(":", 1)[0] + ":123"
        q = MagicMock()
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        ctx = MagicMock()
        ctx.bot = _bot_mock()
        run(bot.handle_pay_callback(q, ctx, self.u, stale))
        self.assertEqual(self.plan().plan, "ultra")
        run(bot.handle_pay_callback(q, ctx, self.u, data))
        self.assertEqual(self.plan().plan, "plus")

    def test_stars_disabled_blocks_purchase_buttons(self):
        q = MagicMock()
        q.answer = AsyncMock()
        b = _bot_mock()
        ctx = MagicMock()
        ctx.bot = b
        with patch.object(bot, "PAYMENTS_STARS_ENABLED", False):
            run(bot.handle_pay_callback(q, ctx, self.u, "pay_buy:plus:1:15"))
        b.send_invoice.assert_not_awaited()

    def test_plan_view_card_and_stars_switches(self):
        def rows(stars, card):
            with patch.object(bot, "PAYMENTS_STARS_ENABLED", stars), patch.object(bot, "PAYMENTS_CARD_ENABLED", card), \
                    patch.object(bot, "PAYMENT_CARD_NUMBER", "8600123412341234"):
                text, markup = bot.build_plan_view(self.u, "plus")
            return text, [b for r in markup.inline_keyboard for b in r]

        text, btns = rows(True, True)
        self.assertIn("8600 1234 1234 1234", text)
        self.assertTrue(any(b.callback_data == "pay_p:plus" for b in btns))
        text, btns = rows(True, False)
        self.assertNotIn("8600", text)
        self.assertTrue(any(b.callback_data == "pay_p:plus" for b in btns))
        text, btns = rows(False, True)
        self.assertIn("8600 1234 1234 1234", text)
        self.assertFalse(any((b.callback_data or "").startswith("pay_") for b in btns))

    def test_paysupport_lists_payments(self):
        token, q = self.order()
        self.pay(token, q)
        upd = MagicMock()
        upd.effective_user.id = self.u
        upd.message.reply_text = AsyncMock()
        run(bot.cmd_paysupport(upd, MagicMock()))
        text = upd.message.reply_text.await_args.args[0]
        self.assertIn(token, text)
        self.assertIn(bot.SUPPORT_ADMIN_USERNAME, text)

    def test_payments_admin_list(self):
        token, q = self.order()
        self.pay(token, q, charge="chLIST")
        upd = MagicMock()
        upd.effective_user.id = 999
        upd.message.reply_text = AsyncMock()
        run(bot.cmd_payments(upd, MagicMock()))
        self.assertIn("chLIST", upd.message.reply_text.await_args.args[0])


class HandlerRegistrationTests(unittest.TestCase):
    def test_payment_handlers_registered_before_other_message(self):
        app = bot.build_app()
        from telegram.ext import MessageHandler, PreCheckoutQueryHandler
        group0 = app.handlers[0]
        idx = {type(h).__name__ + getattr(getattr(h, "callback", None), "__name__", ""): i for i, h in enumerate(group0)}
        self.assertTrue(any(isinstance(h, PreCheckoutQueryHandler) for h in group0))
        sp = next(i for i, h in enumerate(group0) if isinstance(h, MessageHandler) and getattr(h.callback, "__name__", "") == "on_successful_payment")
        other = next(i for i, h in enumerate(group0) if getattr(h.callback, "__name__", "") == "on_other_message")
        self.assertLess(sp, other)
        for name in ("refund", "payments", "paysupport"):
            self.assertTrue(any(name in getattr(h, "commands", ()) for h in group0), name)


# --------------------------------------------------------------------------- i18n
class I18nTests(unittest.TestCase):
    KEYS = [k for k in i18n.T if k.startswith(("pay_", "btn_pay_"))]

    def test_keys_exist_and_have_three_languages(self):
        self.assertGreater(len(self.KEYS), 40)
        for k in self.KEYS:
            for lang in ("uz", "en", "ru"):
                self.assertTrue(t(lang, k), (k, lang))

    def test_placeholders_match_and_cyrillic(self):
        for k in self.KEYS:
            texts = {lang: t(lang, k) for lang in ("uz", "en", "ru")}
            ph = {lang: set(re.findall(r"\{(\w+)\}", s)) for lang, s in texts.items()}
            self.assertEqual(ph["uz"], ph["en"], k)
            self.assertEqual(ph["uz"], ph["ru"], k)
            self.assertTrue(re.search("[а-яА-Я]", texts["ru"]), k)


if __name__ == "__main__":
    unittest.main()
