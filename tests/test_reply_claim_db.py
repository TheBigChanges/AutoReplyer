"""
db.try_claim_reply() / release_reply_claim() — HAQIQIY Postgres'da.

Bu testlar atomiklikni (bir vaqtda kelgan so'rovlardan faqat bittasi
"javob berish huquqi"ni olishi) mock bilan emas, bazaning o'zida tekshiradi.
Faqat TEST_DATABASE_URL o'rnatilgan bo'lsa ishlaydi (bo'lmasa o'tkazib
yuboriladi). DIQQAT: bu BOSHQA (sinov) baza bo'lishi kerak — testlar
replied_cache'ga yozadi (faqat o'zlarining tasodifiy owner_id'lari bilan
va oxirida o'zlarini tozalaydi), lekin init_db() ham ishga tushadi.

    TEST_DATABASE_URL=postgresql://user:pass@localhost/testdb pytest tests/test_reply_claim_db.py
"""

import os
import random
import sys
import threading
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
    """Har chaqiruvda alohida (thread-xavfsiz) ulanish ochadigan get_conn() o'rnini bosuvchi."""

    def __enter__(self):
        self._conn = psycopg2.connect(TEST_DB_URL)
        self._conn.autocommit = True
        return self._conn

    def __exit__(self, *exc):
        self._conn.close()
        return False


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan — haqiqiy Postgres testlari o'tkazib yuborildi")
class TestReplyClaimOnRealPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._patch = patch.object(db, "get_conn", lambda: _FreshConnection())
        cls._patch.start()
        db.init_db()  # sxema haqiqiy Postgres'da xatosiz yaratilishini ham tekshiradi

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()

    def setUp(self):
        self.owner = random.randint(10**12, 10**13)
        self.chat = random.randint(10**12, 10**13)

    def tearDown(self):
        with _FreshConnection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM replied_cache WHERE owner_user_id = %s", (self.owner,))

    def test_first_claim_granted_second_denied_within_cooldown(self):
        first = db.try_claim_reply(self.owner, self.chat, 3.0)
        second = db.try_claim_reply(self.owner, self.chat, 3.0)
        self.assertIsNotNone(first)
        self.assertIsNone(second)

    def test_different_chats_are_independent(self):
        self.assertIsNotNone(db.try_claim_reply(self.owner, self.chat, 3.0))
        self.assertIsNotNone(db.try_claim_reply(self.owner, self.chat + 1, 3.0))

    def test_claim_allowed_again_after_cooldown_elapsed(self):
        self.assertIsNotNone(db.try_claim_reply(self.owner, self.chat, 3.0))
        # cooldown 0 soat => "oldingi javob endi eskirgan" (threshold = hozir)
        self.assertIsNotNone(db.try_claim_reply(self.owner, self.chat, 0.0))

    def test_release_allows_immediate_reclaim(self):
        claimed = db.try_claim_reply(self.owner, self.chat, 3.0)
        db.release_reply_claim(self.owner, self.chat, claimed)
        self.assertIsNotNone(db.try_claim_reply(self.owner, self.chat, 3.0))

    def test_release_with_stale_timestamp_does_not_cancel_newer_claim(self):
        old_claim = db.try_claim_reply(self.owner, self.chat, 3.0)
        newer_claim = db.try_claim_reply(self.owner, self.chat, 0.0)  # cooldown tugagan deb qayta band
        self.assertIsNotNone(newer_claim)
        db.release_reply_claim(self.owner, self.chat, old_claim)  # eski claim — hech narsani o'chirmasligi kerak
        self.assertIsNone(db.try_claim_reply(self.owner, self.chat, 3.0))

    def test_concurrent_claims_only_one_wins(self):
        """Asosiy test: 8 ta oqim bir vaqtda (barrier bilan) bir xil chat uchun
        huquq so'raydi. Eski tekshir-keyin-yoz usulida bir nechtasi o'tib
        ketardi; atomik SQL bilan FAQAT BITTASI o'tishi kerak."""
        n = 8
        barrier = threading.Barrier(n)
        results = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            r = db.try_claim_reply(self.owner, self.chat, 3.0)
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        winners = [r for r in results if r is not None]
        self.assertEqual(len(results), n)
        self.assertEqual(len(winners), 1, f"Aynan 1 ta g'olib bo'lishi kerak edi, {len(winners)} ta chiqdi")


if __name__ == "__main__":
    unittest.main()
