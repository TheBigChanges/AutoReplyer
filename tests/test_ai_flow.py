"""AI-Yordamchi oqimi: on_raw_update ichida AI javobi, limit, zaxira matn, pauza, panel."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import ai  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402

OWNER = 1
ADMIN = 777
CHAT = 99


def _settings(**kw):
    base = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
            "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "",
            "ai_enabled": True, "ai_info": "Men dizaynerman", "ai_role": "seller"}
    base.update(kw)
    return base


def _update(text="Salom, narx qancha?", from_id=5, message_id=10):
    u = MagicMock()
    u.channel_post = None
    u.business_connection = None
    bm = MagicMock()
    bm.business_connection_id = "bc"
    bm.from_user.id = from_id
    bm.from_user.is_bot = False
    bm.chat.id = CHAT
    bm.message_id = message_id
    bm.text = text
    bm.caption = None
    u.business_message = bm
    return u


class Base(unittest.TestCase):
    def setUp(self):
        for target, value in (("ADMIN_ID", ADMIN),):
            p = patch.object(bot, target, value)
            p.start()
            self.addCleanup(p.stop)
        bot._bot_sent_ids.clear()

    def flow(self, update=None, owner=OWNER, settings=None, answer="Salom! Narx 100$.", quota=True,
             paused=False, configured=True, history=None, send_side_effect=None):
        update = update or _update()
        settings = settings or _settings()
        sent = MagicMock(message_id=555)
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(side_effect=send_side_effect, return_value=sent)
        conn = {"owner_user_id": owner, "is_enabled": True, "can_reply": True}
        patches = {
            "conn": patch.object(db, "get_connection_by_business_id", return_value=conn),
            "settings": patch.object(db, "get_settings", return_value=settings),
            "claim": patch.object(db, "try_claim_reply", return_value=123.0),
            "release": patch.object(db, "release_reply_claim"),
            "quota": patch.object(db, "try_consume_ai_quota", return_value=quota),
            "refund": patch.object(db, "refund_ai_quota"),
            "paused": patch.object(db, "is_ai_paused", return_value=paused),
            "pause": patch.object(db, "pause_ai_chat"),
            "hist": patch.object(db, "get_ai_history", return_value=history or []),
            "add": patch.object(db, "add_ai_messages"),
            "user": patch.object(db, "get_user", return_value={"full_name": "Dilshod"}),
            "conf": patch.object(ai, "is_configured", return_value=configured),
            "gen": patch.object(ai, "generate_reply", new=AsyncMock(return_value=answer)),
        }
        started = {k: p.start() for k, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

        async def go():
            await bot.on_raw_update(update, ctx)
            await asyncio.gather(*list(bot._background_tasks))

        asyncio.run(go())
        return ctx.bot.send_message, started

    def texts(self, send):
        return [c.kwargs["text"] for c in send.call_args_list]


class AiReplyTests(Base):
    def test_ai_replies_instead_of_static_text(self):
        send, m = self.flow()
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])
        m["claim"].assert_not_called()  # AI yoqilganda cooldown ishlatilmaydi
        m["quota"].assert_called_once()
        m["add"].assert_called_once()
        msgs = m["add"].call_args.args[2]
        self.assertEqual(msgs, [("user", "Salom, narx qancha?"), ("model", "Salom! Narx 100$.")])
        self.assertIn((CHAT, 555), bot._bot_sent_ids)

    def test_generate_gets_history_plus_new_message_and_owner_info(self):
        _, m = self.flow(history=[{"role": "user", "text": "eski"}, {"role": "model", "text": "javob"}])
        hist, name, info, role = m["gen"].call_args.args
        self.assertEqual([h["text"] for h in hist], ["eski", "javob", "Salom, narx qancha?"])
        self.assertEqual((name, info, role), ("Dilshod", "Men dizaynerman", "seller"))

    def test_admin_has_no_limit(self):
        send, m = self.flow(owner=ADMIN)
        m["quota"].assert_not_called()
        self.assertEqual(len(self.texts(send)), 1)

    def test_limit_reached_falls_back_to_static_text(self):
        send, m = self.flow(quota=False)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()
        m["claim"].assert_called_once()

    def test_ai_failure_refunds_and_falls_back(self):
        send, m = self.flow(answer=None)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["refund"].assert_called_once()
        m["add"].assert_not_called()

    def test_telegram_send_failure_refunds_quota_and_saves_nothing(self):
        from telegram.error import BadRequest
        _, m = self.flow(send_side_effect=BadRequest("x"))
        m["refund"].assert_called_once()
        m["add"].assert_not_called()

    def test_non_text_message_uses_static_text(self):
        update = _update(text=None)
        send, m = self.flow(update=update)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()

    def test_caption_is_used_for_media(self):
        update = _update(text=None)
        update.business_message.caption = "Mana rasm"
        _, m = self.flow(update=update)
        self.assertEqual(m["gen"].call_args.args[0][-1]["text"], "Mana rasm")

    def test_paused_chat_gets_no_reply_at_all(self):
        send, m = self.flow(paused=True)
        send.assert_not_called()
        m["claim"].assert_not_called()

    def test_ai_off_keeps_old_behaviour(self):
        send, m = self.flow(settings=_settings(ai_enabled=False))
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()

    def test_not_configured_falls_back_to_static(self):
        send, m = self.flow(configured=False)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()

    def test_online_owner_gets_no_ai_reply(self):
        send, m = self.flow(settings=_settings(offline=False))
        send.assert_not_called()
        m["gen"].assert_not_awaited()


class TakeoverTests(Base):
    def test_owner_message_pauses_chat(self):
        send, m = self.flow(update=_update(from_id=OWNER))
        m["pause"].assert_called_once_with(OWNER, CHAT, bot.AI_TAKEOVER_PAUSE_SECONDS)
        send.assert_not_called()

    def test_bots_own_echo_does_not_pause(self):
        bot._bot_sent_ids.append((CHAT, 10))
        _, m = self.flow(update=_update(from_id=OWNER, message_id=10))
        m["pause"].assert_not_called()

    def test_no_pause_when_ai_off(self):
        _, m = self.flow(update=_update(from_id=OWNER), settings=_settings(ai_enabled=False))
        m["pause"].assert_not_called()


class PanelTests(Base):
    def _query(self, data, user_id=OWNER):
        q = MagicMock()
        q.data = data
        q.from_user.id = user_id
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        u = MagicMock()
        u.callback_query = q
        return u, q

    def test_panel_has_ai_button_and_support_stays_out(self):
        with patch.object(db, "get_settings", return_value=_settings(ai_enabled=False)):
            text, markup = bot.build_panel(OWNER)
        datas = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn("ai_menu", datas)
        self.assertNotIn("support", datas)
        self.assertIn("AI-Yordamchi: o'chirilgan", text)

    def test_panel_hides_static_text_when_ai_on(self):
        with patch.object(db, "get_settings", return_value=_settings()):
            text, _ = bot.build_panel(OWNER)
        self.assertNotIn("Xabar: Oflaynman", text)
        self.assertIn("AI-Yordamchi yoqilgan", text)

    def test_menu_shows_usage_and_unlimited_for_admin(self):
        with patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "get_ai_usage", return_value=3):
            self.assertIn("3/10", bot.build_ai_menu(OWNER)[0])
            self.assertIn("cheklovsiz", bot.build_ai_menu(ADMIN)[0])

    def test_toggle_on_requires_configuration(self):
        u, q = self._query("ai_toggle")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings(ai_enabled=False)), \
             patch.object(db, "update_settings") as upd, patch.object(db, "get_ai_usage", return_value=0), \
             patch.object(ai, "is_configured", return_value=False):
            asyncio.run(bot.on_button(u, MagicMock()))
        upd.assert_not_called()
        self.assertIn("GEMINI_API_KEY", q.edit_message_text.call_args.args[0])
        q.answer.assert_awaited_once()

    def test_toggle_on_and_off(self):
        for current, expected in ((False, True), (True, False)):
            u, q = self._query("ai_toggle")
            with patch.object(bot, "track_user"), \
                 patch.object(db, "get_settings", return_value=_settings(ai_enabled=current)), \
                 patch.object(db, "update_settings") as upd, patch.object(db, "get_ai_usage", return_value=0), \
                 patch.object(ai, "is_configured", return_value=True):
                asyncio.run(bot.on_button(u, MagicMock()))
            upd.assert_called_once_with(OWNER, ai_enabled=expected)

    def test_edit_info_flow(self):
        u, q = self._query("ai_edit_info")
        with patch.object(bot, "track_user"):
            asyncio.run(bot.on_button(u, MagicMock()))
        self.assertEqual(bot.get_pending_action(OWNER), "ai_info")

        def text_update(t):
            tu = MagicMock()
            tu.effective_user = MagicMock(id=OWNER, is_bot=False)
            tu.message.text = t
            tu.message.reply_text = AsyncMock()
            return tu

        too_long = text_update("x" * (bot.AI_INFO_MAX_LENGTH + 1))
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_text(too_long, MagicMock()))
        upd.assert_not_called()
        self.assertEqual(bot.get_pending_action(OWNER), "ai_info")

        ok = text_update("Men dizaynerman")
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd, \
             patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_ai_usage", return_value=0):
            asyncio.run(bot.on_text(ok, MagicMock()))
        upd.assert_called_once_with(OWNER, ai_info="Men dizaynerman")
        self.assertIsNone(bot.get_pending_action(OWNER))

        clear = text_update("-")
        bot.set_pending_action(OWNER, "ai_info")
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd, \
             patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_ai_usage", return_value=0):
            asyncio.run(bot.on_text(clear, MagicMock()))
        upd.assert_called_once_with(OWNER, ai_info=None)

    def test_roles_menu_marks_current_and_lists_all(self):
        with patch.object(db, "get_settings", return_value=_settings(ai_role="support")):
            text, markup = bot.build_ai_roles_menu(OWNER)
        labels = {b.callback_data: b.text for row in markup.inline_keyboard for b in row}
        for key in ai.ROLES:
            self.assertIn(f"ai_role:{key}", labels)
        self.assertTrue(labels["ai_role:support"].startswith("\u2705"))
        self.assertFalse(labels["ai_role:seller"].startswith("\u2705"))

    def test_main_ai_menu_shows_role_and_button(self):
        with patch.object(db, "get_settings", return_value=_settings(ai_role=None)), \
             patch.object(db, "get_ai_usage", return_value=0):
            text, markup = bot.build_ai_menu(OWNER)
        self.assertIn(ai.role_label(None), text)
        self.assertIn("ai_roles", [b.callback_data for row in markup.inline_keyboard for b in row])

    def test_choosing_role_saves_it(self):
        u, q = self._query("ai_role:support")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_button(u, MagicMock()))
        upd.assert_called_once_with(OWNER, ai_role="support")
        q.answer.assert_awaited_once()

    def test_unknown_role_is_ignored(self):
        u, q = self._query("ai_role:hacker")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_button(u, MagicMock()))
        upd.assert_not_called()

    def test_role_whitelisted_in_db(self):
        self.assertIn("ai_role", db.ALLOWED_SETTINGS_FIELDS)

    def test_settings_whitelist_accepts_ai_fields(self):
        self.assertTrue({"ai_enabled", "ai_info"} <= db.ALLOWED_SETTINGS_FIELDS)


class DisconnectTests(Base):
    def test_disconnect_deletes_ai_data(self):
        u = MagicMock()
        u.channel_post = None
        u.business_message = None
        conn = u.business_connection
        conn.user.id = OWNER
        conn.is_enabled = False
        conn.can_reply = True
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock()
        with patch.object(db, "upsert_connection"), patch.object(db, "delete_ai_data") as d:
            asyncio.run(bot.on_raw_update(u, ctx))
        d.assert_called_once_with(OWNER)


if __name__ == "__main__":
    unittest.main()
