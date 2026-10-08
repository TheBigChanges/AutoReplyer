"""
README `/help` buyrug'ini va'da qilgan edi, lekin handler yo'q edi —
foydalanuvchi /help yozsa bot jim qolardi. Endi /help ro'yxatdan o'tgan,
oddiy foydalanuvchiga yo'riqnoma, adminga qo'shimcha admin buyruqlari ham
ko'rsatiladi.
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
from telegram.ext import CommandHandler  # noqa: E402


def _update(user_id: int):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    return update


class TestHelpCommand(unittest.TestCase):
    def test_help_handler_is_registered(self):
        app = bot.build_app()
        commands = {
            cmd
            for handlers in app.handlers.values()
            for h in handlers
            if isinstance(h, CommandHandler)
            for cmd in h.commands
        }
        self.assertIn("help", commands)

    def test_regular_user_gets_help_without_admin_commands(self):
        update = _update(12345)
        with patch.object(bot, "ADMIN_ID", 777), patch.object(db, "record_user"):
            asyncio.run(bot.cmd_help(update, MagicMock()))

        update.message.reply_text.assert_awaited_once()
        text = update.message.reply_text.call_args[0][0]
        self.assertIn("/start", text)
        self.assertIn("/help", text)
        for admin_cmd in ("/stats", "/reklama", "/reklama_retry", "/block", "/unblock", "/blocked"):
            self.assertNotIn(admin_cmd, text)

    def test_admin_also_sees_admin_commands(self):
        update = _update(777)
        with patch.object(bot, "ADMIN_ID", 777), patch.object(db, "record_user"):
            asyncio.run(bot.cmd_help(update, MagicMock()))

        text = update.message.reply_text.call_args[0][0]
        for cmd in (
            "/start", "/help", "/stats", "/reklama", "/reklama_status", "/reklama_retry", "/cancel",
            "/block", "/unblock", "/blocked",
        ):
            self.assertIn(cmd, text)

    def test_unconfigured_admin_id_zero_never_matches_a_user(self):
        # ADMIN_ID=0 (sozlanmagan) bo'lsa hech kim admin hisoblanmasligi kerak
        update = _update(0)
        with patch.object(bot, "ADMIN_ID", 0), patch.object(db, "record_user"):
            asyncio.run(bot.cmd_help(update, MagicMock()))
        self.assertNotIn("/stats", update.message.reply_text.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
