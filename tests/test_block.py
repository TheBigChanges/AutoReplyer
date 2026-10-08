"""
Admin bloklash tizimi: /block, /unblock, /blocked, bloklangan foydalanuvchiga
xabar, apellyatsiya ("Izoh qoldirish") oqimi va handler yo'naltirish.
"""

import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
from telegram import Update, User  # noqa: E402
from telegram.error import Forbidden  # noqa: E402
from telegram.ext import ApplicationHandlerStop, CommandHandler  # noqa: E402

ADMIN = 777
TARGET = 55


def run(coro):
    return asyncio.run(coro)


class _BaseCase(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(bot, "ADMIN_ID", ADMIN)
        patcher.start()
        self.addCleanup(patcher.stop)
        bot.pending_appeal.clear()
        bot._last_block_notice.clear()
        bot.pending_settings_action.clear()

    def tearDown(self):
        bot.pending_appeal.clear()
        bot._last_block_notice.clear()
        bot.pending_settings_action.clear()


def _admin_update():
    update = MagicMock()
    update.effective_user.id = ADMIN
    update.message.reply_text = AsyncMock()
    return update


def _context(args=None):
    context = MagicMock()
    context.args = args or []
    context.bot.send_message = AsyncMock()
    context.bot.get_chat = AsyncMock()
    return context


def _last_reply(update):
    return update.message.reply_text.call_args[0][0]


# ---------------------------------------------------------------------------
class TestResolveTargetUser(_BaseCase):
    def test_numeric_id(self):
        self.assertEqual(run(bot.resolve_target_user(MagicMock(), "123456789")), (123456789, None))

    def test_zero_id_rejected(self):
        uid, err = run(bot.resolve_target_user(MagicMock(), "0"))
        self.assertIsNone(uid)
        self.assertTrue(err)

    def test_username_found_in_db_with_and_without_at(self):
        with patch.object(db, "get_user_id_by_username", return_value=TARGET) as lookup:
            self.assertEqual(run(bot.resolve_target_user(MagicMock(), "@example")), (TARGET, None))
            self.assertEqual(run(bot.resolve_target_user(MagicMock(), "example")), (TARGET, None))
        lookup.assert_called_with("example")

    def test_username_not_in_db_falls_back_to_telegram(self):
        tg_bot = MagicMock()
        tg_bot.get_chat = AsyncMock(return_value=MagicMock(id=999, type="private"))
        with patch.object(db, "get_user_id_by_username", return_value=None):
            self.assertEqual(run(bot.resolve_target_user(tg_bot, "@example")), (999, None))
        tg_bot.get_chat.assert_awaited_once_with("@example")

    def test_non_private_chat_from_telegram_is_rejected(self):
        tg_bot = MagicMock()
        tg_bot.get_chat = AsyncMock(return_value=MagicMock(id=-100, type="channel"))
        with patch.object(db, "get_user_id_by_username", return_value=None):
            uid, err = run(bot.resolve_target_user(tg_bot, "@somechannel"))
        self.assertIsNone(uid)
        self.assertIn("topilmadi", err)

    def test_unknown_username_gives_helpful_error(self):
        tg_bot = MagicMock()
        tg_bot.get_chat = AsyncMock(side_effect=Forbidden("chat not found"))
        with patch.object(db, "get_user_id_by_username", return_value=None):
            uid, err = run(bot.resolve_target_user(tg_bot, "@example"))
        self.assertIsNone(uid)
        self.assertIn("/block 123456789", err)

    def test_garbage_rejected(self):
        for raw in ("???", "a b", "@", "ab", "@-bad"):
            with self.subTest(raw=raw):
                uid, err = run(bot.resolve_target_user(MagicMock(), raw))
                self.assertIsNone(uid)
                self.assertTrue(err)


# ---------------------------------------------------------------------------
class TestCmdBlock(_BaseCase):
    def _block(self, args, block_result=True, send_side_effect=None, known_user=True):
        update, context = _admin_update(), _context(args)
        context.bot.send_message = AsyncMock(side_effect=send_side_effect)
        info = {"username": "example", "full_name": "Ex Ample"} if known_user else None
        with patch.object(db, "get_user_id_by_username", return_value=TARGET), patch.object(
            db, "get_user", return_value=info
        ), patch.object(db, "block_user", return_value=block_result) as block_user:
            run(bot.cmd_block(update, context))
        return update, context, block_user

    def test_non_admin_is_ignored(self):
        update, context = _admin_update(), _context(["@example"])
        update.effective_user.id = 5
        with patch.object(db, "block_user") as block_user:
            run(bot.cmd_block(update, context))
        block_user.assert_not_called()
        update.message.reply_text.assert_not_called()

    def test_no_args_shows_usage(self):
        update, context, block_user = self._block([])
        block_user.assert_not_called()
        self.assertIn("/block @username", _last_reply(update))

    def test_blocks_notifies_user_with_reason_and_appeal_button(self):
        update, context, block_user = self._block(["@example", "spam", "yubordi"])
        block_user.assert_called_once_with(TARGET, "spam yubordi", ADMIN)

        context.bot.send_message.assert_awaited_once()
        kwargs = context.bot.send_message.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], TARGET)
        self.assertIn("bloklandingiz", kwargs["text"])
        self.assertIn("spam yubordi", kwargs["text"])
        button = kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(button.callback_data, "appeal_start")

        report = _last_reply(update)
        self.assertIn("@example", report)
        self.assertIn("bloklandi", report)
        self.assertIn("xabar yuborildi", report)

    def test_works_without_reason(self):
        update, context, block_user = self._block(["@example"])
        block_user.assert_called_once_with(TARGET, "", ADMIN)
        self.assertNotIn("Sabab:", context.bot.send_message.call_args.kwargs["text"])

    def test_block_by_numeric_id(self):
        update, context = _admin_update(), _context(["123456789", "abuse"])
        with patch.object(db, "get_user", return_value=None), patch.object(
            db, "block_user", return_value=True
        ) as block_user:
            run(bot.cmd_block(update, context))
        block_user.assert_called_once_with(123456789, "abuse", ADMIN)

    def test_reason_is_truncated(self):
        update, context, block_user = self._block(["@example", "x" * 1000])
        self.assertEqual(len(block_user.call_args.args[1]), bot.BLOCK_REASON_MAX_LENGTH)

    def test_still_blocked_when_user_cannot_be_notified(self):
        update, context, block_user = self._block(
            ["@example"], send_side_effect=Forbidden("bot can't initiate conversation")
        )
        block_user.assert_called_once()
        self.assertIn("xabar yuborib bo'lmadi", _last_reply(update))

    def test_already_blocked_is_not_renotified(self):
        update, context, _ = self._block(["@example"], block_result=False)
        context.bot.send_message.assert_not_called()
        self.assertIn("allaqachon bloklangan", _last_reply(update))

    def test_admin_cannot_block_self(self):
        update, context = _admin_update(), _context([str(ADMIN)])
        with patch.object(db, "block_user") as block_user:
            run(bot.cmd_block(update, context))
        block_user.assert_not_called()
        self.assertIn("O'zingizni", _last_reply(update))

    def test_unresolvable_username_blocks_nobody(self):
        update, context = _admin_update(), _context(["@nobody"])
        context.bot.get_chat = AsyncMock(side_effect=Forbidden("nope"))
        with patch.object(db, "get_user_id_by_username", return_value=None), patch.object(
            db, "block_user"
        ) as block_user:
            run(bot.cmd_block(update, context))
        block_user.assert_not_called()
        self.assertIn("topilmadi", _last_reply(update))

    def test_clears_stale_pending_states_of_blocked_user(self):
        bot.pending_settings_action[TARGET] = "text"
        bot.pending_appeal[TARGET] = time.time()
        self._block(["@example"])
        self.assertNotIn(TARGET, bot.pending_settings_action)
        self.assertNotIn(TARGET, bot.pending_appeal)


class TestUnblockAndList(_BaseCase):
    def test_unblock_notifies_user(self):
        update, context = _admin_update(), _context(["@example"])
        with patch.object(db, "get_user_id_by_username", return_value=TARGET), patch.object(
            db, "get_user", return_value={"username": "example", "full_name": None}
        ), patch.object(db, "unblock_user", return_value=True):
            run(bot.cmd_unblock(update, context))
        self.assertEqual(context.bot.send_message.call_args.kwargs["chat_id"], TARGET)
        self.assertIn("blokdan chiqarildingiz", context.bot.send_message.call_args.kwargs["text"])
        self.assertIn("blokdan chiqarildi", _last_reply(update))

    def test_unblock_not_blocked_user(self):
        update, context = _admin_update(), _context(["@example"])
        with patch.object(db, "get_user_id_by_username", return_value=TARGET), patch.object(
            db, "get_user", return_value=None
        ), patch.object(db, "unblock_user", return_value=False):
            run(bot.cmd_unblock(update, context))
        context.bot.send_message.assert_not_called()
        self.assertIn("bloklanmagan", _last_reply(update))

    def test_unblock_non_admin_ignored(self):
        update, context = _admin_update(), _context(["@example"])
        update.effective_user.id = 5
        with patch.object(db, "unblock_user") as unblock:
            run(bot.cmd_unblock(update, context))
        unblock.assert_not_called()

    def test_blocked_list(self):
        update, context = _admin_update(), _context()
        rows = [
            {"user_id": 1, "reason": "spam", "blocked_at": 1_800_000_000.0, "username": "a", "full_name": "A"},
            {"user_id": 2, "reason": "", "blocked_at": 1_800_000_000.0, "username": None, "full_name": None},
        ]
        with patch.object(db, "list_blocked", return_value=rows), patch.object(
            db, "count_blocked", return_value=2
        ):
            run(bot.cmd_blocked(update, context))
        text = _last_reply(update)
        self.assertIn("@a", text)
        self.assertIn("spam", text)
        self.assertIn("ID 2", text)
        self.assertIn("sababsiz", text)

    def test_blocked_list_empty(self):
        update, context = _admin_update(), _context()
        with patch.object(db, "list_blocked", return_value=[]):
            run(bot.cmd_blocked(update, context))
        self.assertIn("yo'q", _last_reply(update))


# ---------------------------------------------------------------------------
def _msg_update(user_id=TARGET, text="salom"):
    update = MagicMock()
    update.callback_query = None
    update.effective_user.id = user_id
    update.effective_user.username = "example"
    update.effective_user.full_name = "Ex Ample"
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def _cb_update(data, user_id=TARGET):
    update = MagicMock()
    update.message = None
    update.effective_user.id = user_id
    update.effective_user.username = "example"
    update.effective_user.full_name = "Ex Ample"
    query = AsyncMock()
    query.data = data
    # haqiqiy Telegramda query.from_user == effective_user; on_button aynan shuni o'qiydi
    query.from_user.id = user_id
    query.from_user.username = "example"
    query.from_user.full_name = "Ex Ample"
    update.callback_query = query
    return update, query


BLOCK = {"user_id": TARGET, "reason": "spam", "blocked_by": ADMIN, "blocked_at": 1.0}


def gate(update, context=None, block=BLOCK):
    context = context or _context()
    with patch.object(db, "get_block", return_value=block) as get_block:
        try:
            run(bot.block_gate(update, context))
            stopped = False
        except ApplicationHandlerStop:
            stopped = True
    return stopped, context, get_block


class TestBlockGate(_BaseCase):
    def test_unblocked_user_passes_through(self):
        stopped, _, _ = gate(_msg_update(), block=None)
        self.assertFalse(stopped)

    def test_admin_is_never_gated_and_costs_no_query(self):
        stopped, _, get_block = gate(_msg_update(user_id=ADMIN))
        self.assertFalse(stopped)
        get_block.assert_not_called()

    def test_business_updates_are_ignored_by_gate(self):
        update = MagicMock()
        update.message = None
        update.callback_query = None
        stopped, _, get_block = gate(update)
        self.assertFalse(stopped)
        get_block.assert_not_called()

    def test_blocked_message_gets_notice_with_reason_and_stops_other_handlers(self):
        update = _msg_update()
        stopped, _, _ = gate(update)
        self.assertTrue(stopped)
        update.message.reply_text.assert_awaited_once()
        notice = update.message.reply_text.call_args[0][0]
        self.assertIn("bloklandingiz", notice)
        self.assertIn("spam", notice)
        markup = update.message.reply_text.call_args.kwargs["reply_markup"]
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "appeal_start")

    def test_notice_is_throttled_but_handlers_still_stopped(self):
        first, second = _msg_update(), _msg_update(text="yana")
        self.assertTrue(gate(first)[0])
        self.assertTrue(gate(second)[0])
        first.message.reply_text.assert_awaited_once()
        second.message.reply_text.assert_not_called()

    def test_notice_repeats_after_cooldown(self):
        bot._last_block_notice[TARGET] = time.time() - bot.BLOCK_NOTICE_COOLDOWN_SECONDS - 1
        update = _msg_update()
        gate(update)
        update.message.reply_text.assert_awaited_once()

    def test_blocked_button_gets_single_alert_answer(self):
        update, query = _cb_update("toggle_status")
        stopped, _, _ = gate(update)
        self.assertTrue(stopped)
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.call_args.kwargs.get("show_alert"))


class TestAppealFlow(_BaseCase):
    def _start_appeal(self, used=0):
        update, query = _cb_update("appeal_start")
        context = _context()
        with patch.object(db, "count_recent_appeals", return_value=used):
            stopped, _, _ = gate(update, context)
        return stopped, query, context

    def test_pressing_appeal_button_asks_for_comment(self):
        stopped, query, context = self._start_appeal()
        self.assertTrue(stopped)
        query.answer.assert_awaited_once()
        self.assertIn(TARGET, bot.pending_appeal)
        self.assertEqual(context.bot.send_message.call_args.kwargs["chat_id"], TARGET)
        self.assertIn("Izohingizni", context.bot.send_message.call_args.kwargs["text"])

    def test_appeal_rate_limit(self):
        _, query, context = self._start_appeal(used=bot.APPEAL_MAX_PER_DAY)
        self.assertNotIn(TARGET, bot.pending_appeal)
        self.assertIn(str(bot.APPEAL_MAX_PER_DAY), context.bot.send_message.call_args.kwargs["text"])

    def test_comment_is_forwarded_to_admin_with_unblock_button(self):
        bot.pending_appeal[TARGET] = time.time()
        update, context = _msg_update(text="Bu xato edi, men spam qilmaganman"), _context()
        with patch.object(db, "add_appeal") as add_appeal:
            stopped, _, _ = gate(update, context)
        self.assertTrue(stopped)

        calls = context.bot.send_message.call_args_list
        admin_call, user_call = calls[0].kwargs, calls[1].kwargs
        self.assertEqual(admin_call["chat_id"], ADMIN)
        self.assertIn("Bu xato edi, men spam qilmaganman", admin_call["text"])
        self.assertIn("@example", admin_call["text"])
        self.assertIn("spam", admin_call["text"])  # bloklash sababi
        self.assertEqual(admin_call["reply_markup"].inline_keyboard[0][0].callback_data, f"unblock:{TARGET}")
        self.assertEqual(user_call["chat_id"], TARGET)
        self.assertIn("adminga yuborildi", user_call["text"])
        add_appeal.assert_called_once_with(TARGET, "Bu xato edi, men spam qilmaganman")
        self.assertNotIn(TARGET, bot.pending_appeal)

    def test_if_admin_cannot_be_reached_user_is_told_and_state_kept(self):
        bot.pending_appeal[TARGET] = time.time()
        update, context = _msg_update(text="izoh"), _context()
        context.bot.send_message = AsyncMock(side_effect=[Forbidden("blocked"), None])
        with patch.object(db, "add_appeal") as add_appeal:
            gate(update, context)
        add_appeal.assert_not_called()
        self.assertIn(TARGET, bot.pending_appeal)
        self.assertIn("yetkazib bo'lmadi", context.bot.send_message.call_args_list[1].kwargs["text"])

    def test_too_long_comment_is_rejected_but_user_can_retry(self):
        bot.pending_appeal[TARGET] = time.time()
        update, context = _msg_update(text="x" * (bot.APPEAL_MAX_LENGTH + 1)), _context()
        with patch.object(db, "add_appeal") as add_appeal:
            gate(update, context)
        add_appeal.assert_not_called()
        context.bot.send_message.assert_not_called()
        self.assertIn("juda uzun", update.message.reply_text.call_args[0][0])
        self.assertIn(TARGET, bot.pending_appeal)

    def test_cancel_clears_pending_appeal(self):
        bot.pending_appeal[TARGET] = time.time()
        update = _msg_update(text="/cancel")
        gate(update)
        self.assertNotIn(TARGET, bot.pending_appeal)
        self.assertIn("Bekor qilindi", update.message.reply_text.call_args[0][0])

    def test_text_without_pending_state_is_not_forwarded(self):
        update, context = _msg_update(text="salom admin"), _context()
        with patch.object(db, "add_appeal") as add_appeal:
            gate(update, context)
        add_appeal.assert_not_called()
        context.bot.send_message.assert_not_called()

    def test_expired_pending_state_is_ignored(self):
        bot.pending_appeal[TARGET] = time.time() - bot.APPEAL_PENDING_TTL_SECONDS - 5
        update, context = _msg_update(text="kech qoldim"), _context()
        with patch.object(db, "add_appeal") as add_appeal:
            gate(update, context)
        add_appeal.assert_not_called()
        self.assertNotIn(TARGET, bot.pending_appeal)
        self.assertIn("bloklandingiz", update.message.reply_text.call_args[0][0])


# ---------------------------------------------------------------------------
class TestUnblockButtonAndStaleButtons(_BaseCase):
    def test_admin_unblocks_from_appeal_message(self):
        update, query = _cb_update(f"unblock:{TARGET}", user_id=ADMIN)
        query.message.text = "Izoh: ..."
        context = _context()
        with patch.object(db, "record_user"), patch.object(db, "unblock_user", return_value=True):
            run(bot.on_button(update, context))
        query.answer.assert_awaited_once()
        self.assertEqual(context.bot.send_message.call_args.kwargs["chat_id"], TARGET)
        edited = query.edit_message_text.call_args[0][0]
        self.assertIn("Izoh: ...", edited)
        self.assertIn("Blokdan chiqarildi", edited)

    def test_unblock_button_from_non_admin_is_rejected(self):
        update, query = _cb_update(f"unblock:{TARGET}", user_id=12345)
        with patch.object(db, "record_user"), patch.object(db, "unblock_user") as unblock:
            run(bot.on_button(update, _context()))
        unblock.assert_not_called()
        query.answer.assert_awaited_once()
        self.assertTrue(query.answer.call_args.kwargs.get("show_alert"))

    def test_bad_unblock_payload(self):
        update, query = _cb_update("unblock:abc", user_id=ADMIN)
        with patch.object(db, "record_user"), patch.object(db, "unblock_user") as unblock:
            run(bot.on_button(update, _context()))
        unblock.assert_not_called()
        query.answer.assert_awaited_once()

    def test_double_click_on_unblock_is_harmless(self):
        update, query = _cb_update(f"unblock:{TARGET}", user_id=ADMIN)
        query.message.text = "Izoh"
        context = _context()
        with patch.object(db, "record_user"), patch.object(db, "unblock_user", return_value=False):
            run(bot.on_button(update, context))
        context.bot.send_message.assert_not_called()
        self.assertIn("allaqachon", query.answer.call_args[0][0])

    def test_stale_appeal_button_for_unblocked_user(self):
        update, query = _cb_update("appeal_start", user_id=12345)
        with patch.object(db, "record_user"):
            run(bot.on_button(update, _context()))
        query.answer.assert_awaited_once()
        self.assertIn("bloklanmagansiz", query.answer.call_args[0][0])


# ---------------------------------------------------------------------------
class TestBlockedOwnerGetsNoAutoReply(_BaseCase):
    def test_business_message_for_blocked_owner_is_ignored(self):
        update = MagicMock()
        update.channel_post = None
        update.business_connection = None
        bm = update.business_message
        bm.business_connection_id = "bc-1"
        bm.from_user.id = 5
        bm.from_user.is_bot = False
        bm.chat.id = 99
        context = _context()
        connection = {"owner_user_id": 1, "is_enabled": True, "can_reply": True, "is_blocked": True}
        with patch.object(db, "get_connection_by_business_id", return_value=connection), patch.object(
            db, "get_settings"
        ) as get_settings, patch.object(db, "try_claim_reply") as claim:
            run(bot.on_raw_update(update, context))
        get_settings.assert_not_called()
        claim.assert_not_called()
        context.bot.send_message.assert_not_called()


# ---------------------------------------------------------------------------
class TestHandlerRouting(_BaseCase):
    """Regressiya: MessageHandler(filters.TEXT ...) mijozning business_message'ini
    ham ushlab, har bir mijozni bot "foydalanuvchisi" qilib yozib, reklama
    ro'yxatini ifloslantirardi (va admin /reklama'dan keyin o'z biznes-chatiga
    yozgan xabari reklama sifatida hammaga ketib qolishi mumkin edi)."""

    @classmethod
    def setUpClass(cls):
        cls.app = bot.build_app()
        cls.app.bot._bot_user = User(id=1, first_name="Bot", is_bot=True, username="testbot")

    def _update(self, kind, text, command=False):
        msg = {
            "message_id": 1, "date": 1_700_000_000,
            "chat": {"id": 5, "type": "private", "first_name": "X"},
            "from": {"id": 5, "is_bot": False, "first_name": "X"},
            "text": text,
        }
        if command:
            msg["entities"] = [{"type": "bot_command", "offset": 0, "length": text.split()[0].__len__()}]
        if kind == "business_message":
            msg["business_connection_id"] = "bc1"
        return Update.de_json({"update_id": 1, kind: msg}, self.app.bot)

    def _matching(self, update):
        names = set()
        for handlers in self.app.handlers.values():
            for h in handlers:
                if h.check_update(update) not in (False, None):
                    names.add(h.callback.__name__)
        return names

    def test_regular_text_reaches_text_handlers(self):
        names = self._matching(self._update("message", "salom"))
        self.assertTrue({"on_text", "on_admin_broadcast_content", "block_gate"} <= names)

    def test_business_text_only_reaches_raw_update_and_gate(self):
        names = self._matching(self._update("business_message", "salom"))
        self.assertEqual(names, {"block_gate", "on_raw_update"})

    def test_edited_text_does_not_reach_text_handlers(self):
        names = self._matching(self._update("edited_message", "salom"))
        self.assertNotIn("on_text", names)
        self.assertNotIn("on_admin_broadcast_content", names)

    def test_block_command_matches_only_normal_messages(self):
        self.assertIn("cmd_block", self._matching(self._update("message", "/block @x", command=True)))
        self.assertNotIn("cmd_block", self._matching(self._update("business_message", "/block @x", command=True)))
        self.assertNotIn("cmd_block", self._matching(self._update("edited_message", "/block @x", command=True)))

    def test_new_commands_are_registered(self):
        commands = {
            c for hs in self.app.handlers.values() for h in hs if isinstance(h, CommandHandler) for c in h.commands
        }
        self.assertTrue({"block", "unblock", "blocked"} <= commands)

    def test_gate_runs_before_every_other_group(self):
        groups = sorted(self.app.handlers)
        self.assertEqual(groups[0], -2)
        self.assertEqual([h.callback.__name__ for h in self.app.handlers[-2]], ["block_gate"])


class TestEndToEndThroughRealDispatcher(_BaseCase):
    """Handlerlarni alohida emas, PTB'ning haqiqiy dispatcher'i (guruhlar tartibi
    va ApplicationHandlerStop) orqali o'tkazib tekshiradi. Faqat tarmoq (send_message)
    va baza mock qilingan."""

    @classmethod
    def setUpClass(cls):
        from telegram.ext import ExtBot

        cls.ExtBot = ExtBot
        cls.app = bot.build_app()
        cls.app.bot._bot_user = User(id=1, first_name="Bot", is_bot=True, username="testbot")
        with patch.object(ExtBot, "initialize", AsyncMock()):
            asyncio.run(cls.app.initialize())

    def _update(self, user_id, text):
        entities = (
            [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}] if text.startswith("/") else []
        )
        return Update.de_json(
            {"update_id": 1, "message": {
                "message_id": 1, "date": 1_700_000_000, "text": text, "entities": entities,
                "chat": {"id": user_id, "type": "private", "first_name": "X"},
                "from": {"id": user_id, "is_bot": False, "first_name": "X", "username": "example"},
            }},
            self.app.bot,
        )

    def _process(self, user_id, text, blocked):
        block = {"user_id": user_id, "reason": "spam", "blocked_by": ADMIN, "blocked_at": 1.0} if blocked else None

        async def go():
            await self.app.process_update(self._update(user_id, text))

        with patch.object(self.ExtBot, "send_message", AsyncMock()) as send, patch.object(
            db, "get_block", return_value=block
        ), patch.object(db, "record_user") as record_user, patch.object(
            db, "get_connection", return_value=None
        ), patch.object(db, "get_user", return_value=None), patch.object(
            db, "get_user_id_by_username", return_value=TARGET
        ), patch.object(db, "block_user", return_value=True) as block_user:
            asyncio.run(go())
        sent = [(c.kwargs["chat_id"], c.kwargs["text"]) for c in send.call_args_list]
        return sent, record_user, block_user

    def test_normal_user_start_runs_normally(self):
        sent, record_user, _ = self._process(5, "/start", blocked=False)
        record_user.assert_called()
        self.assertEqual(len(sent), 1)
        self.assertNotIn("bloklandingiz", sent[0][1])

    def test_blocked_user_start_never_reaches_cmd_start(self):
        sent, record_user, _ = self._process(5, "/start", blocked=True)
        record_user.assert_not_called()  # cmd_start ishlamadi
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], 5)
        self.assertIn("bloklandingiz", sent[0][1])

    def test_blocked_user_plain_text_is_stopped_too(self):
        sent, record_user, _ = self._process(5, "salom", blocked=True)
        record_user.assert_not_called()  # on_text ishlamadi
        self.assertIn("bloklandingiz", sent[0][1])

    def test_admin_block_command_notifies_target_and_reports_to_admin(self):
        sent, _, block_user = self._process(ADMIN, "/block @example spam", blocked=False)
        block_user.assert_called_once_with(TARGET, "spam", ADMIN)
        self.assertEqual([chat for chat, _ in sent], [TARGET, ADMIN])
        self.assertIn("bloklandingiz", sent[0][1])
        self.assertIn("bloklandi", sent[1][1])


if __name__ == "__main__":
    unittest.main()
