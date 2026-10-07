"""
Avtojavob oqimi (bot.on_raw_update ichidagi business_message shoxi):
cooldown huquqi YUBORISHDAN OLDIN atomik band qilinishi, javob berilmasa
(Telegram xatosi) qaytarilishi va cooldown ichida xabar yuborilmasligi.
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
from telegram.error import BadRequest  # noqa: E402

OWNER_ID = 1
CHAT_ID = 99
CLAIMED_AT = 1_700_000_000.5


def _business_update():
    update = MagicMock()
    update.channel_post = None
    update.business_connection = None
    bm = MagicMock()
    bm.business_connection_id = "bc-1"
    bm.from_user.id = 5          # mijoz (owner emas)
    bm.from_user.is_bot = False
    bm.chat.id = CHAT_ID
    update.business_message = bm
    return update


def _settings(**overrides):
    base = {
        "offline": True,
        "auto_reply_text": "Salom, oflaynman",
        "cooldown_hours": 3.0,
        "sleep_mode_enabled": False,
        "sleep_start_minutes": 23 * 60,
        "sleep_end_minutes": 7 * 60,
        "sleep_reply_text": "",
    }
    base.update(overrides)
    return base


class TestAutoReplyClaimFlow(unittest.TestCase):
    def _run(self, claim_result, send_side_effect=None, cooldown_hours=3.0):
        update = _business_update()
        context = MagicMock()
        context.bot.send_message = AsyncMock(side_effect=send_side_effect)
        connection = {"owner_user_id": OWNER_ID, "is_enabled": True, "can_reply": True}

        with patch.object(db, "get_connection_by_business_id", return_value=connection), patch.object(
            db, "get_settings", return_value=_settings(cooldown_hours=cooldown_hours)
        ), patch.object(db, "try_claim_reply", return_value=claim_result) as claim, patch.object(
            db, "release_reply_claim"
        ) as release:
            error = None
            try:
                asyncio.run(bot.on_raw_update(update, context))
            except Exception as e:  # noqa: BLE001
                error = e
        return context.bot.send_message, claim, release, error

    def test_no_message_sent_while_cooldown_active(self):
        send, claim, release, error = self._run(claim_result=None)
        self.assertIsNone(error)
        send.assert_not_called()
        release.assert_not_called()

    def test_claim_uses_cooldown_from_settings(self):
        _, claim, _, _ = self._run(claim_result=None, cooldown_hours=0.5)
        claim.assert_called_once_with(OWNER_ID, CHAT_ID, 0.5)

    def test_message_sent_once_and_claim_kept_on_success(self):
        send, claim, release, error = self._run(claim_result=CLAIMED_AT)
        self.assertIsNone(error)
        send.assert_awaited_once()
        _, kwargs = send.call_args
        self.assertEqual(kwargs["chat_id"], CHAT_ID)
        self.assertEqual(kwargs["business_connection_id"], "bc-1")
        release.assert_not_called()  # muvaffaqiyatli yuborilgan javob cooldown'ni saqlab qoladi

    def test_claim_released_when_telegram_error(self):
        send, claim, release, error = self._run(
            claim_result=CLAIMED_AT, send_side_effect=BadRequest("chat not found")
        )
        self.assertIsNone(error, "Telegram xatosi handlerni yiqitmasligi kerak")
        release.assert_called_once_with(OWNER_ID, CHAT_ID, CLAIMED_AT)

    def test_claim_released_and_error_propagates_on_unexpected_exception(self):
        send, claim, release, error = self._run(
            claim_result=CLAIMED_AT, send_side_effect=RuntimeError("kutilmagan")
        )
        self.assertIsInstance(error, RuntimeError)
        release.assert_called_once_with(OWNER_ID, CHAT_ID, CLAIMED_AT)

    def test_online_user_without_sleep_mode_gets_no_claim_at_all(self):
        update = _business_update()
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        connection = {"owner_user_id": OWNER_ID, "is_enabled": True, "can_reply": True}
        with patch.object(db, "get_connection_by_business_id", return_value=connection), patch.object(
            db, "get_settings", return_value=_settings(offline=False)
        ), patch.object(db, "try_claim_reply") as claim:
            asyncio.run(bot.on_raw_update(update, context))
        claim.assert_not_called()
        context.bot.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
