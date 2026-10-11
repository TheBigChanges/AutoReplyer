"""Ism soati SQL qismi — HAQIQIY Postgres'da (TEST_DATABASE_URL bo'lsa)."""

import os
import random
import sys
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
class NameClockDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = patch.object(db, "get_conn", _conn)
        p.start()
        cls.addClassCleanup(p.stop)
        db.init_db()
        db.init_db()

    def setUp(self):
        self.owner = random.randint(10**14, 10**15)

    def tearDown(self):
        with _conn() as c, c.cursor() as cur:
            for t, col in (("settings", "owner_user_id"), ("connections", "owner_user_id"),
                           ("blocked_users", "user_id")):
                cur.execute(f"DELETE FROM {t} WHERE {col} = %s", (self.owner,))

    def _setup(self, enabled=True, connected=True, can_edit_name=True, first="Ali"):
        db.upsert_connection(self.owner, f"bc{self.owner}", True, connected, False, can_edit_name)
        db.update_settings(self.owner, name_clock_enabled=enabled, name_clock_first=first,
                           name_clock_last="", name_clock_tz="Asia/Tokyo")

    def ids(self):
        return [t["owner_user_id"] for t in db.get_name_clock_targets()]

    def test_active_owner_is_target_with_all_fields(self):
        self._setup()
        t = [t for t in db.get_name_clock_targets() if t["owner_user_id"] == self.owner][0]
        self.assertEqual((t["name_clock_first"], t["name_clock_tz"], t["business_connection_id"]),
                         ("Ali", "Asia/Tokyo", f"bc{self.owner}"))

    def test_excluded_when_disabled_disconnected_no_permission_or_blocked(self):
        self._setup(enabled=False)
        self.assertNotIn(self.owner, self.ids())
        self._setup(connected=False)
        self.assertNotIn(self.owner, self.ids())
        self._setup(can_edit_name=False)
        self.assertNotIn(self.owner, self.ids())
        self._setup()
        self.assertIn(self.owner, self.ids())
        db.block_user(self.owner, "x", 1)
        self.assertNotIn(self.owner, self.ids())

    def test_excluded_without_base_name(self):
        self._setup()
        with _conn() as c, c.cursor() as cur:
            cur.execute("UPDATE settings SET name_clock_first = NULL WHERE owner_user_id = %s", (self.owner,))
        self.assertNotIn(self.owner, self.ids())

    def test_mark_applied_roundtrip(self):
        self._setup()
        db.mark_name_clock_applied(self.owner, "2026-10-11 12:30")
        t = [t for t in db.get_name_clock_targets() if t["owner_user_id"] == self.owner][0]
        self.assertEqual(t["name_clock_applied"], "2026-10-11 12:30")

    def test_can_edit_name_default_false_and_saved(self):
        db.upsert_connection(self.owner, "x", True, True)
        self.assertFalse(db.get_connection(self.owner)["can_edit_name"])
        db.upsert_connection(self.owner, "x", True, True, can_edit_name=True)
        self.assertTrue(db.get_connection(self.owner)["can_edit_name"])


if __name__ == "__main__":
    unittest.main()
