"""
/users va profil to'ldirish SQL qismi — HAQIQIY Postgres'da (TEST_DATABASE_URL bo'lsa).
Aks holda o'tkazib yuboriladi. Testlar faqat o'zlarining tasodifiy ID'lari
bilan ishlaydi va oxirida o'zlarini tozalaydi.
"""

import os
import random
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")

if TEST_DB_URL:
    import psycopg2

    os.environ.setdefault("BOT_TOKEN", "123:dummy")
    _previous_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = TEST_DB_URL
    import db  # noqa: E402

    if _previous_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = _previous_url


class _FreshConnection:
    def __enter__(self):
        self._conn = psycopg2.connect(TEST_DB_URL)
        self._conn.autocommit = True
        return self._conn

    def __exit__(self, *exc):
        self._conn.close()
        return False


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan — haqiqiy Postgres testlari o'tkazib yuborildi")
class TestUsersOnRealPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patcher = patch.object(db, "get_conn", lambda: _FreshConnection())
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        db.init_db()
        db.init_db()

    def setUp(self):
        base = random.randint(10**14, 10**15)
        self.a, self.b, self.c = base, base + 1, base + 2
        self.tag = f"u{base}"

    def tearDown(self):
        with _FreshConnection() as conn, conn.cursor() as cur:
            for table in ("users", "blocked_users"):
                cur.execute(f"DELETE FROM {table} WHERE user_id = ANY(%s)", ([self.a, self.b, self.c],))

    def _legacy(self, uid, first_seen):
        """Eski foydalanuvchi: username/full_name yo'q (ustunlar keyin qo'shilgan)."""
        with _FreshConnection() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO users (user_id, first_seen) VALUES (%s, %s)", (uid, first_seen))

    def test_legacy_user_listed_in_users_page(self):
        far = time.time() + 10**7
        self._legacy(self.a, far)
        db.record_user(self.b, username=self.tag, full_name="Yangi")
        with _FreshConnection() as conn, conn.cursor() as cur:
            cur.execute("UPDATE users SET first_seen = %s WHERE user_id = %s", (far + 1, self.b))
        rows = db.get_users_page(0, 2)
        self.assertEqual([r["user_id"] for r in rows], [self.b, self.a])
        self.assertIsNone(rows[1]["username"])

    def test_blocked_flag_in_page(self):
        self._legacy(self.a, time.time() + 10**7)
        db.block_user(self.a, "spam", 1)
        row = db.get_users_page(0, 1)[0]
        self.assertEqual((row["user_id"], row["is_blocked"], row["block_reason"]), (self.a, True, "spam"))

    def test_pages_do_not_overlap(self):
        far = time.time() + 10**7
        for i, uid in enumerate((self.a, self.b, self.c)):
            self._legacy(uid, far + i)
        first = [r["user_id"] for r in db.get_users_page(0, 2)]
        second = [r["user_id"] for r in db.get_users_page(2, 1)]
        self.assertEqual(first, [self.c, self.b])
        self.assertEqual(second, [self.a])

    def test_backfill_makes_old_user_findable_by_username(self):
        self._legacy(self.a, time.time())
        self.assertIsNone(db.get_user_id_by_username(self.tag))
        self.assertIn(self.a, db.get_users_needing_info(10**6, time.time() - 100))
        db.set_user_info(self.a, self.tag, "Eski Odam")
        self.assertEqual(db.get_user_id_by_username(self.tag), self.a)
        self.assertNotIn(self.a, db.get_users_needing_info(10**6, time.time() - 100))

    def test_failed_lookup_is_retried_only_after_cutoff(self):
        self._legacy(self.a, time.time())
        db.set_user_info(self.a, None, None)  # Telegram hech narsa bermadi
        self.assertNotIn(self.a, db.get_users_needing_info(10**6, time.time() - 100))
        self.assertIn(self.a, db.get_users_needing_info(10**6, time.time() + 100))

    def test_empty_telegram_answer_keeps_existing_data(self):
        db.record_user(self.a, username=self.tag, full_name="Bor")
        db.set_user_info(self.a, None, None)
        info = db.get_user(self.a)
        self.assertEqual((info["username"], info["full_name"]), (self.tag, "Bor"))


if __name__ == "__main__":
    unittest.main()
