"""
Bloklash tizimining SQL qismi — HAQIQIY Postgres'da (TEST_DATABASE_URL bo'lsa).
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


ADMIN = 777


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan — haqiqiy Postgres testlari o'tkazib yuborildi")
class TestBlockingOnRealPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patcher = patch.object(db, "get_conn", lambda: _FreshConnection())
        patcher.start()
        cls.addClassCleanup(patcher.stop)
        db.init_db()
        db.init_db()  # ikkinchi marta ham xatosiz (IF NOT EXISTS)

    def setUp(self):
        base = random.randint(10**14, 10**15)
        self.a, self.b, self.c = base, base + 1, base + 2
        self.job_id = random.randint(10**8, 2 * 10**9)
        self.tag = f"t{base}"

    def tearDown(self):
        ids = (self.a, self.b, self.c)
        with _FreshConnection() as conn, conn.cursor() as cur:
            for table, col in (
                ("users", "user_id"), ("blocked_users", "user_id"), ("block_appeals", "user_id"),
                ("connections", "owner_user_id"), ("settings", "owner_user_id"),
            ):
                cur.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (list(ids),))
            cur.execute("DELETE FROM broadcast_failures WHERE job_id = %s", (self.job_id,))

    # ---- bloklash ----
    def test_block_unblock_roundtrip(self):
        self.assertTrue(db.block_user(self.a, "spam", ADMIN))
        block = db.get_block(self.a)
        self.assertEqual((block["reason"], block["blocked_by"]), ("spam", ADMIN))
        self.assertTrue(db.unblock_user(self.a))
        self.assertIsNone(db.get_block(self.a))

    def test_double_block_is_noop_and_keeps_original_reason(self):
        self.assertTrue(db.block_user(self.a, "birinchi sabab", ADMIN))
        self.assertFalse(db.block_user(self.a, "ikkinchi sabab", ADMIN))
        self.assertEqual(db.get_block(self.a)["reason"], "birinchi sabab")

    def test_unblock_of_unblocked_user_returns_false(self):
        self.assertFalse(db.unblock_user(self.a))

    def test_empty_reason_is_stored_as_empty_string(self):
        db.block_user(self.a, "", ADMIN)
        self.assertEqual(db.get_block(self.a)["reason"], "")

    def test_list_and_count_blocked(self):
        before = db.count_blocked()
        db.record_user(self.a, username=f"{self.tag}a", full_name="A Name")
        db.block_user(self.a, "spam", ADMIN)
        time.sleep(0.01)
        db.block_user(self.b, "abuse", ADMIN)
        self.assertEqual(db.count_blocked(), before + 2)
        rows = [r for r in db.list_blocked(500) if r["user_id"] in (self.a, self.b)]
        self.assertEqual([r["user_id"] for r in rows], [self.b, self.a])  # eng oxirgisi oldinda
        self.assertEqual(rows[1]["username"], f"{self.tag}a")
        self.assertIsNone(rows[0]["username"])  # users'da yo'q odam ham ro'yxatda chiqadi

    # ---- username ----
    def test_username_lookup_is_case_insensitive_and_accepts_at(self):
        db.record_user(self.a, username=f"Mixed_{self.tag}", full_name="A")
        self.assertEqual(db.get_user_id_by_username(f"mixed_{self.tag}"), self.a)
        self.assertEqual(db.get_user_id_by_username(f"@MIXED_{self.tag.upper()}"), self.a)
        self.assertIsNone(db.get_user_id_by_username(f"yoq_{self.tag}"))

    def test_username_moves_to_new_owner(self):
        name = f"reuse_{self.tag}"
        db.record_user(self.a, username=name, full_name="Eski")
        db.record_user(self.b, username=name, full_name="Yangi")
        self.assertEqual(db.get_user_id_by_username(name), self.b)
        self.assertIsNone(db.get_user(self.a)["username"])

    def test_record_user_without_username_keeps_existing_one(self):
        db.record_user(self.a, username=f"keep_{self.tag}", full_name="Nom")
        db.record_user(self.a)  # eski imzo: hech narsani o'chirmasligi kerak
        info = db.get_user(self.a)
        self.assertEqual((info["username"], info["full_name"]), (f"keep_{self.tag}", "Nom"))

    def test_explicit_none_clears_username(self):
        db.record_user(self.a, username=f"gone_{self.tag}", full_name="Nom")
        db.record_user(self.a, username=None, full_name="Nom")
        self.assertIsNone(db.get_user(self.a)["username"])
        self.assertIsNone(db.get_user_id_by_username(f"gone_{self.tag}"))

    # ---- reklama / BIO / avtojavob ro'yxatlaridan chiqarish ----
    def test_blocked_users_are_excluded_from_broadcast_audience(self):
        for uid in (self.a, self.b, self.c):
            db.record_user(uid)
        db.block_user(self.b, "spam", ADMIN)
        ids = db.get_user_ids_after(self.a - 1, limit=200)
        self.assertIn(self.a, ids)
        self.assertIn(self.c, ids)
        self.assertNotIn(self.b, ids)

    def test_user_count_can_exclude_blocked(self):
        db.record_user(self.a)
        total_before, active_before = db.get_user_count(), db.get_user_count(exclude_blocked=True)
        db.block_user(self.a, "", ADMIN)
        self.assertEqual(db.get_user_count(), total_before)
        self.assertEqual(db.get_user_count(exclude_blocked=True), active_before - 1)

    def test_blocked_users_are_excluded_from_retry_list(self):
        db.record_broadcast_failure(self.job_id, self.a, "x")
        db.record_broadcast_failure(self.job_id, self.b, "x")
        db.block_user(self.b, "", ADMIN)
        self.assertEqual(db.get_failed_user_ids_after(self.job_id, 0), [self.a])

    def test_connection_lookup_reports_is_blocked(self):
        bcid = f"bc-{self.tag}"
        db.upsert_connection(self.a, bcid, can_reply=True, is_enabled=True)
        self.assertFalse(db.get_connection_by_business_id(bcid)["is_blocked"])
        db.block_user(self.a, "", ADMIN)
        self.assertTrue(db.get_connection_by_business_id(bcid)["is_blocked"])

    def test_blocked_owner_is_excluded_from_bio_refresh(self):
        db.upsert_connection(self.a, f"bc-{self.tag}", can_reply=True, is_enabled=True, can_edit_bio=True)
        db.update_settings(self.a, bio_countdown_target="new_year")
        mine = lambda: [r for r in db.get_all_bio_targets() if r["owner_user_id"] == self.a]  # noqa: E731
        self.assertEqual(len(mine()), 1)
        db.block_user(self.a, "", ADMIN)
        self.assertEqual(mine(), [])
        db.unblock_user(self.a)
        self.assertEqual(len(mine()), 1)

    # ---- apellyatsiya ----
    def test_appeal_counting_window(self):
        db.add_appeal(self.a, "birinchi")
        db.add_appeal(self.a, "ikkinchi")
        self.assertEqual(db.count_recent_appeals(self.a, time.time() - 60), 2)
        self.assertEqual(db.count_recent_appeals(self.a, time.time() + 60), 0)
        self.assertEqual(db.count_recent_appeals(self.b, time.time() - 60), 0)


if __name__ == "__main__":
    unittest.main()
