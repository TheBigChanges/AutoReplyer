"""AI-Yordamchi SQL qismi — HAQIQIY Postgres'da (TEST_DATABASE_URL bo'lsa)."""

import os
import random
import threading
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import db  # noqa: E402

if TEST_DB_URL:
    import psycopg2


def _conn():
    c = psycopg2.connect(TEST_DB_URL)
    c.autocommit = True

    class Ctx:
        def __enter__(s):
            return c

        def __exit__(s, *a):
            c.close()
            return False

    return Ctx()


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class AiDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = patch.object(db, "get_conn", _conn)
        p.start()
        cls.addClassCleanup(p.stop)
        db.init_db()
        db.init_db()

    def setUp(self):
        self.owner = random.randint(10**14, 10**15)
        self.chat = self.owner + 1

    def tearDown(self):
        with _conn() as c, c.cursor() as cur:
            for t in ("ai_usage", "ai_requests", "voice_attempts", "ai_chat_history", "ai_chat_pause", "settings"):
                cur.execute(f"DELETE FROM {t} WHERE owner_user_id = %s", (self.owner,))

    def test_quota_stops_at_limit_and_refund_gives_back(self):
        results = [db.try_consume_ai_quota(self.owner, "2026-10-11", 3) for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 3)
        db.refund_ai_quota(self.owner, "2026-10-11")
        self.assertTrue(db.try_consume_ai_quota(self.owner, "2026-10-11", 3))
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 3))

    def test_quota_is_per_day(self):
        for _ in range(2):
            db.try_consume_ai_quota(self.owner, "2026-10-11", 2)
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 2))
        self.assertTrue(db.try_consume_ai_quota(self.owner, "2026-10-12", 2))

    def test_quota_never_exceeded_under_concurrency(self):
        wins = []

        def worker():
            wins.append(db.try_consume_ai_quota(self.owner, "2026-10-11", 10))

        threads = [threading.Thread(target=worker) for _ in range(30)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sum(wins), 10)

    def test_refund_never_goes_negative(self):
        db.refund_ai_quota(self.owner, "2026-10-11")
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 0)

    def test_reserve_is_idempotent_per_message(self):
        req = (self.chat, 1)
        self.assertTrue(db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req))
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req))  # takror: limit ikki marta sarflanmaydi
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 1)
        self.assertTrue(db.ai_request_seen(self.owner, self.chat, 1))
        self.assertFalse(db.ai_request_seen(self.owner, self.chat, 2))

    def test_refund_is_idempotent_per_message(self):
        a, b = (self.chat, 1), (self.chat, 2)
        db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=a)
        db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=b)
        db.refund_ai_quota(self.owner, "2026-10-11", request=a)
        db.refund_ai_quota(self.owner, "2026-10-11", request=a)  # javob yo'qolgan qayta urinish
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 1)  # b ning limiti buzilmadi
        db.refund_ai_quota(self.owner, "2026-10-11", request=(self.chat, 3))  # band qilinmagan xabar: hech narsa qaytmaydi
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 1)

    def test_limit_hit_leaves_no_ledger_row(self):
        self.assertTrue(db.try_consume_ai_quota(self.owner, "2026-10-11", 1, request=(self.chat, 1)))
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 1, request=(self.chat, 2)))
        self.assertFalse(db.ai_request_seen(self.owner, self.chat, 2))

    def test_ledger_survives_like_a_restart_and_is_purged_when_old(self):
        db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=(self.chat, 1))
        self.assertTrue(db.ai_request_seen(self.owner, self.chat, 1))  # RAM'ga bog'liq emas
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE ai_requests SET created_at = %s WHERE owner_user_id = %s", (time.time() - 10 * 86400, self.owner))
        db.purge_old_ai_data()
        self.assertFalse(db.ai_request_seen(self.owner, self.chat, 1))

    def _state(self, msg):
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT state FROM ai_requests WHERE owner_user_id = %s AND message_id = %s", (self.owner, msg))
            return cur.fetchone()[0]

    def _age(self, seconds=db.AI_REQUEST_STALE_SECONDS + 60):
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE ai_requests SET updated_at = updated_at - %s WHERE owner_user_id = %s", (seconds, self.owner))

    def test_stale_preparing_ai_request_can_recover(self):
        req = (self.chat, 1)
        self.assertTrue(db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req))
        self.assertTrue(db.ai_request_seen(self.owner, self.chat, 1))      # yangi `reserved`: boshqa jarayon ishlayapti, tegilmaydi
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req))
        self._age()                                                         # jarayon to'xtagan
        self.assertFalse(db.ai_request_seen(self.owner, self.chat, 1))     # tiklash mumkin
        self.assertTrue(db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req))
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 1)     # limit ikki marta sarflanmadi
        self.assertTrue(db.ai_request_seen(self.owner, self.chat, 1))      # tiklangan so'rov endi yangi (parallel qayta tiklash yo'q)
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req))

    def test_stale_sending_ai_request_is_not_resent(self):
        req = (self.chat, 1)
        db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req)
        self.assertTrue(db.mark_ai_request(self.owner, req, "sending"))
        self._age(10 * 86400)
        self.assertTrue(db.ai_request_seen(self.owner, self.chat, 1))      # Telegram qabul qilgan bo'lishi mumkin: qayta yuborilmaydi
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req))
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 1)     # limit ham qaytarilmaydi
        self.assertEqual(self._state(1), "sending")
        self.assertFalse(db.mark_ai_request(self.owner, req, "sending"))   # ikkinchi marta "sending" bo'lmaydi

    def test_unknown_and_sent_are_final(self):
        for msg, state in ((1, "sent"), (2, "unknown")):
            req = (self.chat, msg)
            db.try_consume_ai_quota(self.owner, "2026-10-11", 9, request=req)
            db.mark_ai_request(self.owner, req, "sending")
            db.mark_ai_request(self.owner, req, state)
        self._age(10 * 86400)
        self.assertTrue(db.ai_request_seen(self.owner, self.chat, 1))
        self.assertTrue(db.ai_request_seen(self.owner, self.chat, 2))

    def test_crash_before_ai_send_does_not_permanently_consume_quota(self):
        """Gemini tayyor bo'lmasdan jarayon to'xtadi: limit band, lekin yozuv eskirgach xabar qayta ishlanadi va limit yo'qolmaydi."""
        req = (self.chat, 1)
        db.try_consume_ai_quota(self.owner, "2026-10-11", 1, request=req)   # limit = 1 va u band
        self.assertFalse(db.try_consume_ai_quota(self.owner, "2026-10-11", 1, request=(self.chat, 2)))  # boshqa xabar sig'maydi
        self._age()
        self.assertTrue(db.try_consume_ai_quota(self.owner, "2026-10-11", 1, request=req))  # tiklandi, limitga qaramay
        db.refund_ai_quota(self.owner, "2026-10-11", request=req)           # tiklangan so'rov ham muvaffaqiyatsiz bo'lsa — qaytadi
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 0)

    def test_refund_goes_to_the_reserved_day_not_today(self):
        req = (self.chat, 1)
        db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req)
        db.refund_ai_quota(self.owner, "2026-10-12", request=req)           # yarim tundan keyin qaytarilsa ham
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 0)

    def test_sending_request_cannot_be_refunded_after_sent(self):
        req = (self.chat, 1)
        db.try_consume_ai_quota(self.owner, "2026-10-11", 5, request=req)
        db.mark_ai_request(self.owner, req, "sending")
        db.mark_ai_request(self.owner, req, "sent")
        db.refund_ai_quota(self.owner, "2026-10-11", request=req)
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 1)

    def test_admin_tracking_dedupes_without_touching_quota(self):
        req = (self.chat, 1)
        self.assertTrue(db.track_ai_request(self.owner, req, "2026-10-11"))
        self.assertFalse(db.track_ai_request(self.owner, req, "2026-10-11"))   # restartdan keyin ham takroriy
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 0)
        self._age()
        self.assertTrue(db.track_ai_request(self.owner, req, "2026-10-11"))     # eskirgan `reserved` — tiklanadi
        db.refund_ai_quota(self.owner, "2026-10-11", request=req)               # admin yozuvi limitga tegmaydi
        self.assertEqual(db.get_ai_usage(self.owner, "2026-10-11"), 0)
        self._age()
        self.assertFalse(db.track_ai_request(self.owner, req, "2026-10-11"))    # yopilgan (`refunded`) qayta ochilmaydi

    def test_voice_attempts_stop_at_limit_and_are_never_refunded(self):
        res = [db.try_consume_voice_attempt(self.owner, "2026-10-11", 3) for _ in range(5)]
        self.assertEqual(res, [True, True, True, False, False])
        self.assertTrue(db.try_consume_voice_attempt(self.owner, "2026-10-12", 3))  # keyingi kun yangi

    def test_voice_attempts_never_exceeded_under_concurrency(self):
        wins = []
        threads = [threading.Thread(target=lambda: wins.append(db.try_consume_voice_attempt(self.owner, "2026-10-11", 7))) for _ in range(25)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(sum(wins), 7)

    def test_history_keeps_only_last_10_in_order(self):
        for i in range(8):
            db.add_ai_messages(self.owner, self.chat, [("user", f"q{i}"), ("model", f"a{i}")], keep=10)
        hist = db.get_ai_history(self.owner, self.chat, 10)
        self.assertEqual(len(hist), 10)
        self.assertEqual(hist[0], {"role": "user", "text": "q3"})
        self.assertEqual(hist[-1], {"role": "model", "text": "a7"})

    def test_history_is_per_chat_and_owner(self):
        db.add_ai_messages(self.owner, self.chat, [("user", "x")])
        db.add_ai_messages(self.owner, self.chat + 1, [("user", "y")])
        self.assertEqual(db.get_ai_history(self.owner, self.chat), [{"role": "user", "text": "x"}])

    def test_old_history_ignored_and_purged(self):
        db.add_ai_messages(self.owner, self.chat, [("user", "eski")])
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE ai_chat_history SET created_at = %s WHERE owner_user_id = %s",
                        (time.time() - 10 * 86400, self.owner))
        self.assertEqual(db.get_ai_history(self.owner, self.chat), [])
        db.purge_old_ai_data()
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ai_chat_history WHERE owner_user_id = %s", (self.owner,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_history_forgotten_after_two_days(self):
        self.assertEqual(db.AI_HISTORY_MAX_AGE_SECONDS, 2 * 86400)
        db.add_ai_messages(self.owner, self.chat, [("user", "kecha")])
        with _conn() as c, c.cursor() as cur:  # 1.5 kun oldin — hali eslanadi
            cur.execute("UPDATE ai_chat_history SET created_at = %s WHERE owner_user_id = %s",
                        (time.time() - 1.5 * 86400, self.owner))
        self.assertEqual(len(db.get_ai_history(self.owner, self.chat)), 1)
        db.purge_old_ai_data()
        self.assertEqual(len(db.get_ai_history(self.owner, self.chat)), 1)
        with _conn() as c, c.cursor() as cur:  # 2.5 kun oldin — unutiladi va o'chiriladi
            cur.execute("UPDATE ai_chat_history SET created_at = %s WHERE owner_user_id = %s",
                        (time.time() - 2.5 * 86400, self.owner))
        self.assertEqual(db.get_ai_history(self.owner, self.chat), [])
        db.purge_old_ai_data()
        with _conn() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM ai_chat_history WHERE owner_user_id = %s", (self.owner,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_pause_and_expiry(self):
        self.assertFalse(db.is_ai_paused(self.owner, self.chat))
        db.pause_ai_chat(self.owner, self.chat, 3600)
        self.assertTrue(db.is_ai_paused(self.owner, self.chat))
        db.pause_ai_chat(self.owner, self.chat, -5)
        self.assertFalse(db.is_ai_paused(self.owner, self.chat))

    def test_delete_ai_data(self):
        db.add_ai_messages(self.owner, self.chat, [("user", "x")])
        db.pause_ai_chat(self.owner, self.chat, 3600)
        db.delete_ai_data(self.owner)
        self.assertEqual(db.get_ai_history(self.owner, self.chat), [])
        self.assertFalse(db.is_ai_paused(self.owner, self.chat))

    def test_settings_columns(self):
        s = db.get_settings(self.owner)
        self.assertFalse(s["ai_enabled"])
        self.assertIsNone(s["ai_role"])
        db.update_settings(self.owner, ai_enabled=True, ai_info="info", ai_role="seller")
        s = db.get_settings(self.owner)
        self.assertEqual((s["ai_enabled"], s["ai_info"], s["ai_role"]), (True, "info", "seller"))


if __name__ == "__main__":
    unittest.main()
