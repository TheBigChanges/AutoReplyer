"""AI-Yordamchi SQL qismi — HAQIQIY Postgres'da (TEST_DATABASE_URL bo'lsa)."""

import os
import random
import sys
import threading
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
            for t in ("ai_usage", "ai_chat_history", "ai_chat_pause", "settings"):
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
        db.update_settings(self.owner, ai_enabled=True, ai_info="info")
        s = db.get_settings(self.owner)
        self.assertEqual((s["ai_enabled"], s["ai_info"]), (True, "info"))


if __name__ == "__main__":
    unittest.main()
