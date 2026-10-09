"""
Regressiya: majburiy obuna yoqilganda, obuna bo'lmagan odam referal havola
(/start ref_5) bilan kirsa, referal yo'qolardi. Endi taklif qilgan odamning
ID'si "Tekshirish" tugmasi ichida (callback_data) olib o'tiladi va referal
obuna tasdiqlangandan KEYIN hisoblanadi.
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
from telegram.error import Forbidden  # noqa: E402

USER, INVITER = 9, 5


def _start_update():
    update = MagicMock()
    update.effective_user.id = USER
    update.effective_user.username = "x"
    update.effective_user.full_name = "X"
    update.message.reply_text = AsyncMock()
    return update


def _context(args):
    context = MagicMock()
    context.args = args
    context.bot.send_message = AsyncMock()
    return context


def _button_update(data):
    update = MagicMock()
    query = AsyncMock()
    query.data = data
    query.from_user.id = USER
    query.from_user.username = "x"
    query.from_user.full_name = "X"
    update.callback_query = query
    return update, query


def _gate_buttons(update):
    markup = update.message.reply_text.call_args.kwargs["reply_markup"]
    return [b for row in markup.inline_keyboard for b in row]


class _Base(unittest.TestCase):
    def setUp(self):
        for patcher in (
            patch.object(bot, "REQUIRED_CHANNEL_LINK", "https://t.me/example"),
            patch.object(db, "record_user"),
            patch.object(db, "get_connection", return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)


class TestParseReferralArg(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(bot.parse_referral_arg(["ref_5"]), 5)

    def test_invalid_variants(self):
        for args in ([], None, ["abc"], ["ref_x"], ["ref_0"], ["ref_-3"], ["ref_"]):
            with self.subTest(args=args):
                self.assertIsNone(bot.parse_referral_arg(args))


class TestGatedStart(_Base):
    def _gated_start(self, args):
        update, context = _start_update(), _context(args)
        with patch.object(bot, "is_subscribed", AsyncMock(return_value=False)), patch.object(
            db, "record_referral", return_value=True
        ) as record_referral:
            asyncio.run(bot.cmd_start(update, context))
        return update, context, record_referral

    def test_referral_not_counted_before_subscription_but_carried_in_button(self):
        update, context, record_referral = self._gated_start([f"ref_{INVITER}"])
        record_referral.assert_not_called()
        context.bot.send_message.assert_not_called()
        self.assertEqual(_gate_buttons(update)[1].callback_data, f"check_subscription:{INVITER}")

    def test_no_referral_keeps_plain_callback(self):
        update, _, _ = self._gated_start([])
        self.assertEqual(_gate_buttons(update)[1].callback_data, "check_subscription")

    def test_malformed_referral_keeps_plain_callback(self):
        update, _, _ = self._gated_start(["ref_abc"])
        self.assertEqual(_gate_buttons(update)[1].callback_data, "check_subscription")

    def test_callback_data_stays_within_telegram_limit(self):
        markup = bot.build_subscribe_gate_markup(10**13)
        self.assertLessEqual(len(markup.inline_keyboard[1][0].callback_data.encode()), 64)


class TestCheckSubscriptionButton(_Base):
    def _press(self, data, subscribed=True, record_result=True):
        update, query = _button_update(data)
        context = _context([])
        with patch.object(bot, "is_subscribed", AsyncMock(return_value=subscribed)), patch.object(
            db, "record_referral", return_value=record_result
        ) as record_referral:
            asyncio.run(bot.on_button(update, context))
        return query, context, record_referral

    def test_referral_counted_after_subscribing_and_inviter_notified(self):
        query, context, record_referral = self._press(f"check_subscription:{INVITER}")
        record_referral.assert_called_once_with(referred_user_id=USER, inviter_user_id=INVITER)
        self.assertEqual(context.bot.send_message.call_args.kwargs["chat_id"], INVITER)
        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited()

    def test_not_subscribed_yet_counts_nothing_and_shows_alert(self):
        query, _, record_referral = self._press(f"check_subscription:{INVITER}", subscribed=False)
        record_referral.assert_not_called()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.call_args.kwargs.get("show_alert"))

    def test_old_plain_button_still_works_without_referral(self):
        query, _, record_referral = self._press("check_subscription")
        record_referral.assert_not_called()
        query.answer.assert_awaited_once()
        query.edit_message_text.assert_awaited()

    def test_garbage_payload_is_harmless(self):
        query, _, record_referral = self._press("check_subscription:abc")
        record_referral.assert_not_called()
        query.edit_message_text.assert_awaited()

    def test_duplicate_or_self_referral_sends_no_notification(self):
        _, context, _ = self._press(f"check_subscription:{INVITER}", record_result=False)
        context.bot.send_message.assert_not_called()

    def test_full_journey_counts_referral_exactly_once(self):
        update, context = _start_update(), _context([f"ref_{INVITER}"])
        with patch.object(bot, "is_subscribed", AsyncMock(side_effect=[False, True])), patch.object(
            db, "record_referral", return_value=True
        ) as record_referral:
            asyncio.run(bot.cmd_start(update, context))
            press_update, _ = _button_update(_gate_buttons(update)[1].callback_data)
            asyncio.run(bot.on_button(press_update, _context([])))
        record_referral.assert_called_once_with(referred_user_id=USER, inviter_user_id=INVITER)


class TestUngatedStartStillWorks(_Base):
    def test_referral_counted_immediately_when_already_subscribed(self):
        update, context = _start_update(), _context([f"ref_{INVITER}"])
        with patch.object(bot, "is_subscribed", AsyncMock(return_value=True)), patch.object(
            db, "record_referral", return_value=True
        ) as record_referral:
            asyncio.run(bot.cmd_start(update, context))
        record_referral.assert_called_once_with(referred_user_id=USER, inviter_user_id=INVITER)
        self.assertEqual(context.bot.send_message.call_args.kwargs["chat_id"], INVITER)

    def test_inviter_who_blocked_the_bot_does_not_break_start(self):
        update, context = _start_update(), _context([f"ref_{INVITER}"])
        context.bot.send_message = AsyncMock(side_effect=Forbidden("bot was blocked by the user"))
        with patch.object(bot, "is_subscribed", AsyncMock(return_value=True)), patch.object(
            db, "record_referral", return_value=True
        ):
            asyncio.run(bot.cmd_start(update, context))
        update.message.reply_text.assert_awaited()


if __name__ == "__main__":
    unittest.main()
