"""Smart Handoff persistence tests against an isolated PostgreSQL test database."""

import os
import random
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

    class Context:
        def __enter__(self):
            return c

        def __exit__(self, *_):
            c.close()
    return Context()


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL not configured")
class HandoffDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = patch.object(db, "get_conn", _conn)
        p.start()
        cls.addClassCleanup(p.stop)
        db.init_db()

    def setUp(self):
        self.owner = random.randint(10**14, 10**15)
        self.chat = self.owner + 1

    def tearDown(self):
        with _conn() as conn, conn.cursor() as cur:
            for table in ("handoff_chats", "settings"):
                cur.execute(f"DELETE FROM {table} WHERE owner_user_id = %s", (self.owner,))

    def test_claim_once_and_close_on_owner_reply(self):
        self.assertTrue(db.claim_handoff(self.owner, self.chat, 10))
        self.assertTrue(db.handoff_active(self.owner, self.chat))
        self.assertFalse(db.claim_handoff(self.owner, self.chat, 10))
        self.assertFalse(db.claim_handoff(self.owner, self.chat, 11))
        self.assertTrue(db.close_handoff(self.owner, self.chat))
        self.assertFalse(db.handoff_active(self.owner, self.chat))
        self.assertFalse(db.claim_handoff(self.owner, self.chat, 10))
        self.assertTrue(db.claim_handoff(self.owner, self.chat, 11))

    def test_definite_notification_failure_releases_handoff(self):
        self.assertTrue(db.claim_handoff(self.owner, self.chat, 10))
        db.release_handoff(self.owner, self.chat, 10)
        self.assertFalse(db.handoff_active(self.owner, self.chat))
        self.assertFalse(db.claim_handoff(self.owner, self.chat, 10))
        self.assertTrue(db.claim_handoff(self.owner, self.chat, 11))

    def test_different_owners_independent(self):
        other = self.owner + 500
        try:
            self.assertTrue(db.claim_handoff(self.owner, self.chat, 10))
            self.assertTrue(db.claim_handoff(other, self.chat, 10))
            self.assertTrue(db.handoff_active(other, self.chat))
            db.close_handoff(self.owner, self.chat)
            self.assertTrue(db.handoff_active(other, self.chat))
        finally:
            with _conn() as conn, conn.cursor() as cur:
                cur.execute("DELETE FROM handoff_chats WHERE owner_user_id = %s", (other,))

    def test_expired_handoff_rows_purged(self):
        db.claim_handoff(self.owner, self.chat, 10)
        with _conn() as conn, conn.cursor() as cur:
            cur.execute("UPDATE handoff_chats SET updated_at = %s WHERE owner_user_id = %s", (time.time()-15*86400,self.owner))
        self.assertGreaterEqual(db.purge_old_handoffs(), 1)
        self.assertFalse(db.handoff_active(self.owner, self.chat))

    def test_ai_disconnect_purges_handoff_state(self):
        db.claim_handoff(self.owner, self.chat, 10)
        db.delete_ai_data(self.owner)
        self.assertFalse(db.handoff_active(self.owner, self.chat))

    def test_feature_is_off_by_default(self):
        self.assertFalse(db.get_settings(self.owner)["handoff_enabled"])
        db.update_settings(self.owner, handoff_enabled=True)
        self.assertTrue(db.get_settings(self.owner)["handoff_enabled"])


if __name__ == "__main__":
    unittest.main()
