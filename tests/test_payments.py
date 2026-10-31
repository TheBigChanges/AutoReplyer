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


class GrantTests(unittest.TestCase):
    def g(self, state, snap_ok, kind, plan, months, stars, credit=0, now=NOW):
        return pay.grant(state, snap_ok, kind, plan, months, stars, credit, now, add_months)

    def test_snapshot_ok_matches_old_behaviour(self):
        st = PlanState("plus", NOW + 10 * DAY, None)
        g = self.g(st, True, "extend", "plus", 1, 15)
        self.assertEqual((g.start, g.end), (NOW + 10 * DAY, NOW + 40 * DAY))

    def test_stale_pro_invoice_does_not_overwrite_ultra(self):
        ultra = PlanState("ultra", NOW + 30 * DAY, None)
        g = self.g(ultra, False, "new", "pro", 1, 35)
        self.assertEqual(g.new_state.plan, "ultra")
        self.assertGreater(g.new_state.expires_at, ultra.expires_at)  # to'langan qiymat Ultra kunlariga qo'shildi
        self.assertAlmostEqual((g.new_state.expires_at - ultra.expires_at) / DAY, 35 / (70 / 30), places=3)

    def test_stale_invoice_on_lower_plan_upgrades_and_keeps_value(self):
        plus = PlanState("plus", NOW + 30 * DAY, None)  # qolgan qiymat 15
        g = self.g(plus, False, "new", "pro", 1, 35)
        self.assertEqual(g.new_state.plan, "pro")
        self.assertAlmostEqual((g.new_state.expires_at - NOW) / DAY, 30 + 15 / (35 / 30), places=3)

    def test_stale_same_plan_extends(self):
        st = PlanState("pro", NOW + 5 * DAY, None)
        g = self.g(st, False, "new", "pro", 1, 35)
        self.assertEqual(g.new_state.expires_at, NOW + 35 * DAY)

    def test_stale_upgrade_credit_is_not_trusted(self):
        # credit bilan to'langan upgrade (pay=28 < price=35), lekin eski tarif endi yo'q: faqat to'langan 28 ning ulushi
        g = self.g(PlanState(), False, "upgrade", "pro", 1, 28, credit=7)
        self.assertAlmostEqual((g.new_state.expires_at - NOW) / DAY, 30 * 28 / 35, places=3)

    def test_unlimited_is_never_touched(self):
        st = PlanState("ultra", None, None)
        g = self.g(st, False, "new", "pro", 1, 35)
        self.assertEqual(g.new_state, st)
        self.assertTrue(g.review)


class PurchaseRefundTests(unittest.TestCase):
    def test_expired_old_purchase_preserves_unrelated_subscription(self):
        pro = PlanState("pro", NOW + 30 * DAY, 35 / 30)
        new = pay.apply_refund_purchase(pro, 15, NOW - 60 * DAY, NOW - 30 * DAY, NOW)  # eski Plus davri o'tib ketgan
        self.assertEqual(new, pro)

    def test_partially_used_purchase_takes_only_unused_share(self):
        st = PlanState("plus", NOW + 10 * DAY, 0.5)
        new = pay.apply_refund_purchase(st, 15, NOW - 20 * DAY, NOW + 10 * DAY, NOW)  # 1/3 qolgan = 5 Stars = 10 kun
        self.assertEqual(new.plan, "free")

    def test_future_stacked_purchase_refunds_in_full(self):
        st = PlanState("plus", NOW + 60 * DAY, 0.5)
        new = pay.apply_refund_purchase(st, 15, NOW + 30 * DAY, NOW + 60 * DAY, NOW)
        self.assertAlmostEqual((new.expires_at - NOW) / DAY, 30, places=3)

    def test_legacy_row_without_grant_uses_old_rule(self):
        st = PlanState("plus", NOW + 60 * DAY, 0.5)
        self.assertAlmostEqual((pay.apply_refund_purchase(st, 15, None, None, NOW).expires_at - NOW) / DAY, 30, places=3)


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
            cur.execute("DELETE FROM payment_inbox WHERE user_id IN (%s, %s)", (self.u, self.v))
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


class StaleAndLedgerTests(DbBase):
    def test_stale_invoice_does_not_overwrite_newer_subscription(self):
        now = time.time()
        token, q = self.order(plan="pro", now=now)  # Pro buyurtmasi (free holatda)
        db.set_user_plan(self.u, "ultra", now + 30 * DAY)  # orada Ultra berildi
        res, _ = self.pay(token, q, now=now)
        self.assertEqual(res["status"], "activated")
        self.assertTrue(res["state_changed"])
        st = self.plan()
        self.assertEqual(st.plan, "ultra")
        self.assertGreater(st.expires_at, now + 30 * DAY)

    def test_stale_invoice_on_unlimited_flags_review_and_changes_nothing(self):
        now = time.time()
        token, q = self.order(plan="pro", now=now)
        db.set_user_plan(self.u, "ultra", None)
        res, _ = self.pay(token, q, now=now)
        self.assertTrue(res["review"])
        self.assertEqual(self.plan(), PlanState("ultra", None, None))
        self.assertEqual(db.get_payment(token)["status"], "paid")  # to'lov qayd etilgan, refund mumkin

    def test_expired_but_not_yet_swept_plan_counts_as_free(self):
        now = time.time()
        db.set_user_plan(self.u, "plus", now - 5)  # o'tib ketgan, job hali tozalamagan
        token, q = self.order(now=now)  # snapshot: free
        res, _ = self.pay(token, q, now=now)
        self.assertFalse(res["state_changed"])

    def test_refund_expired_old_purchase_preserves_unrelated_subscription(self):
        now = time.time()
        t1, q1 = self.order(plan="plus", now=now - 90 * DAY)
        self.pay(t1, q1, charge="chOLD", now=now - 90 * DAY)  # Plus: -90..-60 kun, o'tib ketgan
        db.set_user_plan(self.u, "pro", now + 30 * DAY)
        row, _ = db.begin_refund("chOLD")
        db.finish_refund(row["id"], now)
        st = self.plan()
        self.assertEqual(st.plan, "pro")
        self.assertAlmostEqual(st.expires_at, now + 30 * DAY, delta=1)
        self.assertEqual(db.get_payment(t1)["status"], "refunded")

    def test_grant_interval_stored(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, now=now)
        row = db.get_payment(token)
        self.assertAlmostEqual(row["grant_start"], now, delta=1)
        self.assertAlmostEqual(row["grant_end"], now + 30 * DAY, delta=1)


class InboxTests(DbBase):
    def test_inbox_roundtrip(self):
        db.record_payment_event(self.u, "TK", "chI1", 15, "XTR")
        db.record_payment_event(self.u, "TK", "chI1", 15, "XTR")  # takror — bitta yozuv
        evs = [e for e in db.list_unprocessed_payment_events() if e["user_id"] == self.u]
        self.assertEqual(len(evs), 1)
        db.mark_payment_event_done("chI1")
        self.assertEqual([e for e in db.list_unprocessed_payment_events() if e["user_id"] == self.u], [])

    def test_recon_mark(self):
        db.set_payment_recon_mark(123.0, key="t_" + str(self.u))
        self.assertEqual(db.get_payment_recon_mark("t_" + str(self.u)), 123.0)
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM payment_recon WHERE key = %s", ("t_" + str(self.u),))


# --------------------------------------------------------------------------- bot
def _bot_mock():
    b = MagicMock()
    b.send_message = AsyncMock()
    b.send_invoice = AsyncMock(return_value=MagicMock(message_id=777))
    b.delete_message = AsyncMock()
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


class RecoveryTests(BotBase):
    def _ctx(self, b):
        ctx = MagicMock()
        ctx.bot = b
        return ctx

    def test_payment_recovered_after_process_restart(self):
        token, q = self.order()
        b = _bot_mock()
        with patch.object(db, "activate_payment", side_effect=RuntimeError("db down")):
            run(bot.process_payment(b, self.u, token, "chRST", q.pay, "XTR"))
        self.assertEqual(self.plan().plan, "free")
        bot._pending_payments.clear()  # server qayta ishga tushdi: xotira yo'qoldi
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE payment_inbox SET received_at = received_at - 100 WHERE charge_id = 'chRST'")
        run(bot.payment_retry_job(self._ctx(b)))
        self.assertEqual(self.plan().plan, "plus")
        self.assertEqual([e for e in db.list_unprocessed_payment_events() if e["charge_id"] == "chRST"], [])

    def test_repeated_db_failure_does_not_spam_admin(self):
        token, q = self.order()
        b = _bot_mock()
        with patch.object(db, "activate_payment", side_effect=RuntimeError("down")):
            run(bot.process_payment(b, self.u, token, "chSP", q.pay, "XTR"))
            n = b.send_message.await_count
            run(bot.process_payment(b, self.u, token, "chSP", q.pay, "XTR"))
        self.assertEqual(b.send_message.await_count, n)

    def _tx(self, charge, user, payload, amount, age_days=0.0, refund=False):
        from telegram import TransactionPartnerUser
        tx = MagicMock()
        tx.id = charge
        tx.amount = amount
        tx.date = __import__("datetime").datetime.fromtimestamp(time.time() - age_days * DAY, __import__("datetime").timezone.utc)
        if refund:
            tx.receiver, tx.source = MagicMock(), None
        else:
            tx.receiver = None
            tx.source = MagicMock(spec=TransactionPartnerUser)
            tx.source.user.id = user
            tx.source.invoice_payload = payload
        return tx

    def _batch(self, txs):
        r = MagicMock()
        r.transactions = txs
        return r

    def test_reconcile_finds_old_payment_beyond_500_after_long_downtime(self):
        token, q = self.order()
        db.set_payment_recon_mark(time.time() - 20 * DAY)
        self.addCleanup(lambda: db.set_payment_recon_mark(time.time()))
        filler = [self._tx(f"f{i}_{self.u}", self.v, "Pfiller", 1, age_days=1) for i in range(100)]  # boshqalar (bazada yo'q -> unmatched)
        target = self._tx("chOLDER", self.u, token, q.pay, age_days=10)
        pages = [self._batch(filler)] * 6 + [self._batch([target])]
        b = _bot_mock()
        b.get_star_transactions = AsyncMock(side_effect=pages)
        run(bot.payment_reconcile_job(self._ctx(b)))
        self.assertEqual(self.plan().plan, "plus")  # 600 ta tranzaksiyadan keyin topildi
        self.assertGreater(db.get_payment_recon_mark(), time.time() - 5)  # belgi yangilandi
        with db.get_conn() as conn, conn.cursor() as cur:  # filler uchun hosil bo'lgan unmatched yozuvlar tozalanadi
            cur.execute("DELETE FROM payments WHERE charge_id LIKE %s", (f"f%_{self.u}",))

    def test_reconcile_mark_not_advanced_when_processing_deferred(self):
        token, q = self.order()
        db.set_payment_recon_mark(1000.0)
        self.addCleanup(lambda: db.set_payment_recon_mark(time.time()))
        b = _bot_mock()
        b.get_star_transactions = AsyncMock(return_value=self._batch([self._tx("chDEF", self.u, token, q.pay)]))
        with patch.object(db, "activate_payment", side_effect=RuntimeError("down")):
            run(bot.payment_reconcile_job(self._ctx(b)))
        self.assertEqual(db.get_payment_recon_mark(), 1000.0)

    def test_external_refund_reconciles_subscription(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, charge="chEXT", now=now)
        self.assertEqual(self.plan().plan, "plus")
        self.addCleanup(lambda: db.set_payment_recon_mark(time.time()))
        b = _bot_mock()
        b.get_star_transactions = AsyncMock(return_value=self._batch([
            self._tx("chEXT", self.u, token, q.pay), self._tx("chEXT", self.u, token, q.pay, refund=True)]))
        run(bot.payment_reconcile_job(self._ctx(b)))
        self.assertEqual(db.get_payment(token)["status"], "refunded")
        self.assertEqual(self.plan().plan, "free")
        n = b.send_message.await_count
        run(bot.payment_reconcile_job(self._ctx(b)))  # ikkinchi marta hech narsa ayrilmaydi
        self.assertEqual(b.send_message.await_count, n)

    def test_external_refund_of_old_purchase_keeps_other_subscription(self):
        now = time.time()
        t1, q1 = self.order(now=now - 90 * DAY)
        self.pay(t1, q1, charge="chEX2", now=now - 90 * DAY)
        db.set_user_plan(self.u, "pro", now + 30 * DAY)
        self.addCleanup(lambda: db.set_payment_recon_mark(time.time()))
        b = _bot_mock()
        b.get_star_transactions = AsyncMock(return_value=self._batch([self._tx("chEX2", self.u, t1, q1.pay, refund=True)]))
        run(bot.payment_reconcile_job(self._ctx(b)))
        self.assertEqual(self.plan().plan, "pro")
        self.assertEqual(db.get_payment(t1)["status"], "refunded")


class InvoiceLifecycleTests(BotBase):
    def _ctx(self, b):
        ctx = MagicMock()
        ctx.bot = b
        return ctx

    def _buy(self, b, price=15, plan="plus", months=1):
        q = MagicMock()
        q.answer = AsyncMock()
        run(bot.handle_pay_callback(q, self._ctx(b), self.u, f"pay_buy:{plan}:{months}:{price}"))
        return b.send_invoice.await_args.kwargs["payload"]

    def test_ttl_is_15_minutes(self):
        self.assertEqual(bot.PAYMENT_ORDER_TTL_SECONDS, 900)
        token = self._buy(_bot_mock())
        o = db.get_payment(token)
        self.assertAlmostEqual(o["expires_at"] - o["created_at"], 900, delta=1)

    def test_invoice_has_pay_button_first_then_cancel_and_message_id_saved(self):
        b = _bot_mock()
        token = self._buy(b)
        rows = b.send_invoice.await_args.kwargs["reply_markup"].inline_keyboard
        self.assertTrue(rows[0][0].pay)
        self.assertEqual(rows[1][0].callback_data, f"pay_cx:{token}")
        self.assertEqual(db.get_payment(token)["invoice_msg_id"], 777)

    def _cancel(self, token, user=None):
        q = MagicMock()
        q.answer = AsyncMock()
        q.message.message_id = 777
        q.message.delete = AsyncMock()
        b = _bot_mock()
        run(bot.handle_pay_callback(q, self._ctx(b), user or self.u, f"pay_cx:{token}"))
        return q, b

    def test_cancel_button_cancels_order_and_removes_invoice(self):
        token = self._buy(_bot_mock())
        q, b = self._cancel(token)
        self.assertEqual(db.get_payment(token)["status"], "cancelled")
        b.delete_message.assert_awaited_once_with(chat_id=self.u, message_id=777)
        order = db.get_payment(token)
        self.assertFalse(self.pre(token, amount=order["stars"])["ok"])  # bekor qilingan buyurtma to'lanmaydi

    def test_cancel_foreign_or_paid_order_is_refused(self):
        token = self._buy(_bot_mock())
        q, b = self._cancel(token, user=self.v)
        self.assertEqual(db.get_payment(token)["status"], "pending")
        b.delete_message.assert_not_awaited()
        self.assertTrue(q.answer.await_args.kwargs.get("show_alert"))
        order = db.get_payment(token)
        db.activate_payment(token, "chCX", self.u, order["stars"], add_months)
        self._cancel(token)
        self.assertEqual(db.get_payment(token)["status"], "paid")
        self.assertEqual(self.plan().plan, "plus")

    def test_expiry_job_closes_order_deletes_invoice_and_notifies(self):
        b = _bot_mock()
        token = self._buy(b)
        fresh = db.get_payment(token)
        run(bot.payment_orders_job(self._ctx(b)))  # hali muddati o'tmagan
        self.assertEqual(db.get_payment(token)["status"], "pending")
        b.delete_message.assert_not_awaited()
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE payments SET expires_at = %s WHERE token = %s", (time.time() - 1, token))
        run(bot.payment_orders_job(self._ctx(b)))
        self.assertEqual(db.get_payment(token)["status"], "expired")
        b.delete_message.assert_awaited_once_with(chat_id=self.u, message_id=777)
        self.assertIn(self.u, [c.kwargs.get("chat_id") for c in b.send_message.await_args_list])
        self.assertEqual(self.plan().plan, "free")

    def test_new_invoice_removes_previous_invoice_message(self):
        b = _bot_mock()
        first = self._buy(b)
        b.send_invoice.return_value = MagicMock(message_id=888)
        b.delete_message.reset_mock()
        second = self._buy(b, price=41, months=3)
        b.delete_message.assert_awaited_once_with(chat_id=self.u, message_id=777)
        self.assertEqual(db.get_payment(first)["status"], "cancelled")
        self.assertEqual(db.get_payment(second)["invoice_msg_id"], 888)


class AuditRound2Tests(BotBase):
    def _ctx(self, b):
        ctx = MagicMock()
        ctx.bot = b
        return ctx

    def _refund(self, ref, b=None):
        b = b or _bot_mock()
        upd = MagicMock()
        upd.effective_user.id = 999
        upd.message.reply_text = AsyncMock()
        ctx = MagicMock()
        ctx.args = [ref]
        ctx.bot = b
        run(bot.cmd_refund(upd, ctx))
        return upd.message.reply_text.await_args.args[0], b

    def test_unmatched_payment_can_be_refunded_without_changing_subscription(self):
        now = time.time()
        db.set_user_plan(self.u, "pro", now + 20 * DAY)
        before = self.plan()
        b = _bot_mock()
        self.assertEqual(run(bot.process_payment(b, self.u, "PGHOST", "chUNM", 15, "XTR")), "unmatched")
        msg, b2 = self._refund("chUNM")
        b2.refund_star_payment.assert_awaited_once_with(user_id=self.u, telegram_payment_charge_id="chUNM")
        self.assertIn("✅", msg)
        self.assertEqual(db.get_payment_by_charge("chUNM")["status"], "refunded")
        self.assertEqual(self.plan(), before)

    def test_unmatched_refund_api_failure_restores_unmatched(self):
        run(bot.process_payment(_bot_mock(), self.u, "PGHOST", "chUN2", 15, "XTR"))
        b = _bot_mock()
        b.refund_star_payment.side_effect = TelegramError("CHARGE_NOT_FOUND")
        self._refund("chUN2", b)
        self.assertEqual(db.get_payment_by_charge("chUN2")["status"], "unmatched")

    def test_refund_after_downgrade_removes_remaining_transferred_credit(self):
        now = time.time()
        token, q = self.order(plan="ultra", now=now)
        self.pay(token, q, charge="chULT", now=now)  # Ultra, 70 Stars, hozir
        t0 = now + 60  # bir daqiqadan keyin Plus ga o'tadi
        state = db.get_user_plan_state(self.u)
        qs = pay.quote(state, "plus", 1, t0, add_months)
        self.assertEqual(qs.kind, "downgrade")
        self.assertTrue(db.switch_plan(self.u, "ultra", int(state.expires_at), qs, "SDW", t0))
        plus = self.plan()
        self.assertEqual(plus.plan, "plus")
        self.assertGreater(plus.expires_at, now + 130 * DAY)  # ~140 kun
        later = now + 35 * DAY  # 35 kundan keyin asl Ultra xarid refund qilinadi
        row, _ = db.begin_refund("chULT")
        new = db.finish_refund(row["id"], later)
        # asl xaridning grant_end (30 kun) o'tib ketgan, lekin qiymati Plus'da ishlatilmoqda: ~105 kun ayrilishi kerak
        self.assertTrue(new.plan == "free" or new.expires_at - later < 2 * DAY, new)

    def test_refund_after_upgrade_credit_transfer(self):
        now = time.time()
        t1, q1 = self.order(plan="plus", now=now)
        self.pay(t1, q1, charge="chUP1", now=now)  # Plus 15
        t2, q2 = self.order(plan="pro", now=now)  # upgrade: credit ~14, pay ~21
        self.assertEqual(q2.kind, "upgrade")
        self.pay(t2, q2, charge="chUP2", now=now)
        row, _ = db.begin_refund("chUP1")
        db.finish_refund(row["id"], now)
        st = self.plan()
        self.assertEqual(st.plan, "pro")
        self.assertLess(st.expires_at - now, 18 * DAY)  # Pro ~30 kundan Plus qiymatiga mos ~12-14 kun ayrildi

    def test_upgrade_moves_old_purchase_value_into_new_period(self):
        now = time.time()
        t1, q1 = self.order(plan="plus", now=now)
        self.pay(t1, q1, charge="chMV1", now=now)  # Plus 15, hozir
        at = now + 15 * DAY  # 15 kundan keyin Pro ga yuqoriga o'tish
        st = db.get_user_plan_state(self.u)
        q2 = pay.quote(st, "pro", 1, at, add_months)
        self.assertEqual(q2.kind, "upgrade")
        db.create_payment_order(self.u, "UP2", q2, st, 900, at)
        self.assertEqual(db.activate_payment("UP2", "chMV2", self.u, q2.pay, add_months, at)["status"], "activated")
        old = db.get_payment("UP2")  # yangi xarid davri
        row = db.get_payment(t1)
        self.assertAlmostEqual(row["grant_start"], at, delta=1)  # eski xarid qiymati yangi davrga ko'chdi
        self.assertAlmostEqual(row["grant_end"], old["grant_end"], delta=1)
        self.assertAlmostEqual(row["grant_value"], 7.5, delta=0.2)
        before = self.plan().expires_at
        refund_at = at + 15 * DAY
        rrow, _ = db.begin_refund("chMV1")
        db.finish_refund(rrow["id"], refund_at)
        self.assertGreater(before - self.plan().expires_at, 2 * DAY)  # asl davr o'tib ketgan bo'lsa ham ko'chirilgan qiymat ayrildi

    def test_external_refund_recovers_after_database_failure(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, charge="chRCV", now=now)
        self.addCleanup(lambda: db.set_payment_recon_mark(time.time()))
        b = _bot_mock()
        tx = MagicMock()
        tx.id, tx.receiver, tx.source = "chRCV", MagicMock(), None
        tx.date = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        batch = MagicMock()
        batch.transactions = [tx]
        b.get_star_transactions = AsyncMock(return_value=batch)
        with patch.object(db, "finish_refund", side_effect=RuntimeError("db down")):
            run(bot.payment_reconcile_job(self._ctx(b)))
        self.assertEqual(db.get_payment(token)["status"], "refunding")  # yarim qoldi
        run(bot.payment_reconcile_job(self._ctx(b)))  # baza tiklandi
        self.assertEqual(db.get_payment(token)["status"], "refunded")
        self.assertEqual(self.plan().plan, "free")

    def test_stuck_refunding_without_visible_telegram_refund_alerts_admin_once(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, charge="chSTK", now=now)
        db.begin_refund("chSTK")
        self.addCleanup(lambda: db.set_payment_recon_mark(time.time()))
        bot._recon_alerted.discard("chSTK")
        b = _bot_mock()
        b.get_star_transactions = AsyncMock(return_value=MagicMock(transactions=[]))
        run(bot.payment_reconcile_job(self._ctx(b)))
        n = b.send_message.await_count
        self.assertGreaterEqual(n, 1)
        run(bot.payment_reconcile_job(self._ctx(b)))
        self.assertEqual(b.send_message.await_count, n)

    def test_reconcile_not_marked_ok_when_page_limit_hit(self):
        db.set_payment_recon_mark(1000.0)
        self.addCleanup(lambda: db.set_payment_recon_mark(time.time()))
        bot._recon_alerted.clear()
        dt = __import__("datetime")
        txs = []
        for i in range(100):
            tx = MagicMock()
            tx.id, tx.receiver, tx.source = f"zz{i}", MagicMock(), None
            tx.date = dt.datetime.now(dt.timezone.utc)  # hammasi yangi: eski belgigacha yetib bo'lmaydi
            txs.append(tx)
        b = _bot_mock()
        b.get_star_transactions = AsyncMock(return_value=MagicMock(transactions=txs))
        run(bot.payment_reconcile_job(self._ctx(b)))
        self.assertEqual(b.get_star_transactions.await_count, bot.RECON_MAX_PAGES)
        self.assertEqual(db.get_payment_recon_mark(), 1000.0)
        self.assertIn(999, [c.kwargs.get("chat_id") for c in b.send_message.await_args_list])
        bot._recon_alerted.clear()


class AuditRound3Tests(BotBase):
    def _ctx(self, b):
        ctx = MagicMock()
        ctx.bot = b
        return ctx

    def _buy(self, b, price=15, plan="plus", months=1):
        q = MagicMock()
        q.answer = AsyncMock()
        run(bot.handle_pay_callback(q, self._ctx(b), self.u, f"pay_buy:{plan}:{months}:{price}"))
        return q

    def test_plan_switch_during_pending_refund_preserves_correct_value(self):
        now = time.time()
        token, q = self.order(plan="ultra", now=now)
        self.pay(token, q, charge="chPR", now=now)
        row, _ = db.begin_refund("chPR")  # refund boshlandi (refunding), hali yakunlanmagan
        self.assertEqual(row["status"], "refunding")
        t0 = now + 60
        state = db.get_user_plan_state(self.u)
        qs = pay.quote(state, "plus", 1, t0, add_months)
        self.assertTrue(db.switch_plan(self.u, "ultra", int(state.expires_at), qs, "SPR", t0))
        self.assertAlmostEqual(db.get_payment(token)["grant_start"], t0, delta=1)  # refunding xarid ham ko'chirildi
        later = now + 35 * DAY
        new = db.finish_refund(row["id"], later)
        self.assertTrue(new.plan == "free" or new.expires_at - later < 2 * DAY, new)

    def test_manual_admin_plan_not_reduced_by_old_stars_refund(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, charge="chADM", now=now)  # Stars orqali Plus, hozir
        db.set_user_plan(self.u, "ultra", now + 30 * DAY)  # admin Ultra berdi
        before = self.plan()
        row, _ = db.begin_refund("chADM")
        new = db.finish_refund(row["id"], now + 1)
        self.assertEqual(db.get_payment(token)["status"], "refunded")
        self.assertEqual(new.plan, "ultra")
        self.assertAlmostEqual(self.plan().expires_at, before.expires_at, delta=1)

    def test_admin_plan_after_purchase_with_refunding_also_detached(self):
        now = time.time()
        token, q = self.order(now=now)
        self.pay(token, q, charge="chAD2", now=now)
        row, _ = db.begin_refund("chAD2")
        db.set_user_plan(self.u, "pro", now + 30 * DAY)
        db.finish_refund(row["id"], now + 1)
        self.assertEqual(self.plan().plan, "pro")
        self.assertAlmostEqual(self.plan().expires_at, now + 30 * DAY, delta=1)

    def _gate_update(self, text):
        upd = MagicMock()
        upd.callback_query = None
        upd.effective_user.id = self.u
        upd.effective_user.is_bot = False
        upd.effective_chat.type = "private"
        upd.message.text = text
        upd.message.successful_payment = None
        upd.message.reply_text = AsyncMock()
        return upd

    def test_paysupport_available_to_unsubscribed_and_blocked_users(self):
        with patch.object(bot, "REQUIRED_CHANNEL_ID", -100), patch.object(bot, "_sub_exempt", return_value=False), \
                patch.object(bot, "is_subscribed_cached", AsyncMock(return_value=False)):
            for text in ("/paysupport", "/paysupport@SomeBot", "/paysupport 123"):
                run(bot.subscribe_gate(self._gate_update(text), MagicMock()))  # to'xtatilmaydi
            with self.assertRaises(ApplicationHandlerStop):
                run(bot.subscribe_gate(self._gate_update("/stats"), MagicMock()))
            with self.assertRaises(ApplicationHandlerStop):
                run(bot.subscribe_gate(self._gate_update("/paysupportx"), MagicMock()))
        with patch.object(db, "get_block", return_value={"reason": "x"}):
            run(bot.block_gate(self._gate_update("/paysupport"), MagicMock()))
            with patch.object(bot, "handle_blocked_update", AsyncMock()), self.assertRaises(ApplicationHandlerStop):
                run(bot.block_gate(self._gate_update("/start"), MagicMock()))

    def test_same_active_order_is_reused_not_duplicated(self):
        b = _bot_mock()
        self._buy(b)
        first = b.send_invoice.await_args.kwargs["payload"]
        q = self._buy(b)  # xuddi shu tugma qayta bosildi
        self.assertEqual(b.send_invoice.await_count, 1)
        self.assertTrue(q.answer.await_args.kwargs.get("show_alert"))
        self.assertEqual(db.get_payment(first)["status"], "pending")
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM payments WHERE user_id = %s", (self.u,))
            self.assertEqual(cur.fetchone()[0], 1)

    def test_not_reused_after_cancel_or_when_plan_changed(self):
        b = _bot_mock()
        self._buy(b)
        first = b.send_invoice.await_args.kwargs["payload"]
        db.cancel_order(first, self.u)
        self._buy(b)
        self.assertEqual(b.send_invoice.await_count, 2)
        db.set_user_plan(self.u, "pro", time.time() + 10 * DAY)  # holat o'zgardi: eski buyurtma yaroqsiz
        cur = self.plan()
        self.assertIsNone(db.get_reusable_order(self.u, "plus", 1, 15, cur.plan, int(cur.expires_at)))

    def test_new_orders_rate_limited_per_user(self):
        bot._pay_rate.pop(self.u, None)
        self.addCleanup(lambda: bot._pay_rate.pop(self.u, None))
        b = _bot_mock()
        # har safar boshqa (tarif, muddat) — qayta ishlatilmaydi, lekin tezlik cheklovi ishlaydi
        combos = [("plus", 1, 15), ("plus", 3, 41), ("plus", 6, 77), ("plus", 12, 144), ("pro", 1, 35), ("pro", 3, 95)]
        for plan, months, price in combos:
            self._buy(b, price=price, plan=plan, months=months)
        self.assertEqual(b.send_invoice.await_count, bot.PAY_RATE_MAX)
        self.assertFalse(bot._pay_rate_ok(self.u, time.time()))
        self.assertTrue(bot._pay_rate_ok(self.u, time.time() + bot.PAY_RATE_WINDOW + 1))


class CardDefaultTests(unittest.TestCase):
    def test_card_route_off_by_default_stars_on(self):
        import importlib
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PAYMENTS_CARD_ENABLED", None)
            os.environ.pop("PAYMENTS_STARS_ENABLED", None)
            self.assertFalse(bot._env_flag("PAYMENTS_CARD_ENABLED", False))
            self.assertTrue(bot._env_flag("PAYMENTS_STARS_ENABLED", True))
        self.assertFalse(bot.PAYMENTS_CARD_ENABLED)  # test muhitida o'zgaruvchi berilmagan


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
