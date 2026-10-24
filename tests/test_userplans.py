"""/userplans: admin uchun tariflar va obunachilar ro'yxati."""

import asyncio
import os
import random
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
ADMIN = 777


def run(coro):
    return asyncio.run(coro)


def update_from(uid):
    msg = MagicMock()
    msg.reply_text = AsyncMock()
    return SimpleNamespace(effective_user=SimpleNamespace(id=uid), message=msg), msg


class CommandTests(unittest.TestCase):
    PAID = [
        {"user_id": 1, "username": "ali", "full_name": "Ali", "plan": "plus", "plan_expires_at": 1_900_000_000.0},
        {"user_id": 2, "username": None, "full_name": None, "plan": "ultra", "plan_expires_at": None},
    ]

    def _call(self, uid, paid=None, free=5):
        upd, msg = update_from(uid)
        with patch.object(bot, "ADMIN_ID", ADMIN), \
             patch.object(bot.db, "list_plan_subscribers", return_value=(self.PAID if paid is None else paid, free)):
            run(bot.cmd_userplans(upd, MagicMock()))
        return "\n".join(c.args[0] for c in msg.reply_text.await_args_list) if msg.reply_text.await_args_list else None

    def test_non_admin_ignored(self):
        self.assertIsNone(self._call(1))

    def test_lists_every_plan_with_users(self):
        text = self._call(ADMIN)
        for key in ("Free — 5", "Plus", "Pro", "Ultra"):
            self.assertIn(key, text)
        self.assertIn("@ali / Ali (ID 1)", text)
        self.assertIn("gacha", text)
        self.assertIn("ID 2 — muddatsiz", text)
        self.assertIn("Pro (5000 so'm) — 0 ta", text)

    def test_long_list_is_split(self):
        many = [{"user_id": i, "username": f"u{i}", "full_name": "N" * 40, "plan": "pro", "plan_expires_at": None} for i in range(300)]
        upd, msg = update_from(ADMIN)
        with patch.object(bot, "ADMIN_ID", ADMIN), patch.object(bot.db, "list_plan_subscribers", return_value=(many, 0)):
            run(bot.cmd_userplans(upd, MagicMock()))
        self.assertGreater(msg.reply_text.await_count, 1)
        self.assertTrue(all(len(c.args[0]) <= 4096 for c in msg.reply_text.await_args_list))

    def test_registered_and_in_help(self):
        src = Path(bot.__file__).read_text()
        self.assertIn('CommandHandler("userplans", cmd_userplans', src)
        self.assertIn("/userplans — tariflar", src)  # admin yordam matnida


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class DbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.base = random.randint(10**12, 9 * 10**12)
        self.ids = [self.base + i for i in range(5)]
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE user_id = ANY(%s)", (self.ids,))

    def test_only_active_paid_listed(self):
        a, b, c, d, e = self.ids
        for uid in self.ids:
            db.record_user(uid, username=f"zz{uid}", full_name="T")
        db.set_user_plan(a, "plus", time.time() + 86400)
        db.set_user_plan(b, "ultra")                      # muddatsiz
        db.set_user_plan(c, "pro", time.time() - 10)      # muddati o'tgan -> bepul
        db.set_user_plan(d, "free")
        paid, free = db.list_plan_subscribers()
        mine = {r["user_id"]: r["plan"] for r in paid if r["user_id"] in self.ids}
        self.assertEqual(mine, {a: "plus", b: "ultra"})
        total_users = len(paid) + free
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            self.assertEqual(total_users, cur.fetchone()[0])


if __name__ == "__main__":
    unittest.main()
