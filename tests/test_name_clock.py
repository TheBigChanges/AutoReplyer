"""Ism soati ("Ism | 12:30"): mantiq, yangilash sikli, xatolar va panel."""

import asyncio
import os
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
import logic  # noqa: E402
from telegram.error import BadRequest, NetworkError, RetryAfter  # noqa: E402

ADMIN = 777
OWNER = 777


def run(coro):
    return asyncio.run(coro)


class LogicTests(unittest.TestCase):
    def test_no_last_name_goes_into_first(self):
        self.assertEqual(logic.build_clock_name("Dilshodbek", "", 12, 30), ("Dilshodbek | 12:30", None))
        self.assertEqual(logic.build_clock_name("Dilshodbek", None, 9, 5), ("Dilshodbek | 09:05", None))

    def test_with_last_name_goes_into_last(self):
        self.assertEqual(logic.build_clock_name("Dilshodbek", "Abdu", 0, 0), ("Dilshodbek", "Abdu | 00:00"))

    def test_64_char_limit_keeps_full_clock(self):
        first, last = logic.build_clock_name("A" * 100, "", 12, 30)
        self.assertEqual(len(first), 64)
        self.assertTrue(first.endswith(" | 12:30"))
        first, last = logic.build_clock_name("B" * 100, "C" * 100, 23, 59)
        self.assertEqual((len(first), len(last)), (64, 64))
        self.assertTrue(last.endswith(" | 23:59"))

    def test_strip_clock_suffix_prevents_stacking(self):
        self.assertEqual(logic.strip_clock_suffix("Dilshodbek | 12:30"), "Dilshodbek")
        self.assertEqual(logic.strip_clock_suffix("Dilshodbek | 12:30 | 12:31"), "Dilshodbek | 12:30")
        self.assertEqual(logic.strip_clock_suffix("Ali"), "Ali")
        self.assertEqual(logic.strip_clock_suffix(None), "")

    def test_split_full_name(self):
        self.assertEqual(logic.split_full_name("Dilshodbek Abdu"), ("Dilshodbek", "Abdu"))
        self.assertEqual(logic.split_full_name("Dilshodbek"), ("Dilshodbek", ""))
        self.assertEqual(logic.split_full_name("Ali Vali Aliyev | 10:00"), ("Ali", "Vali Aliyev"))
        self.assertEqual(logic.split_full_name("   "), ("", ""))

    def test_ten_valid_zones(self):
        self.assertEqual(len(logic.NAME_CLOCK_ZONES), 10)
        for key, label, tz in logic.NAME_CLOCK_ZONES:
            ZoneInfo(tz)
            self.assertTrue(label)
        self.assertEqual(logic.NAME_CLOCK_ZONES[0][2], "Asia/Tashkent")

    def test_zone_helpers(self):
        self.assertTrue(logic.is_known_zone("Asia/Tokyo"))
        self.assertFalse(logic.is_known_zone("Mars/Base"))
        self.assertEqual(logic.zone_label("nonsense"), logic.zone_label("Asia/Tashkent"))


class ClockNamesTests(unittest.TestCase):
    def test_uses_zone_time_and_key(self):
        ts = datetime(2026, 10, 11, 7, 30, 0, tzinfo=timezone.utc).timestamp()  # 12:30 Toshkent
        first, last, key = bot.clock_names_for("Dilshodbek", "", "Asia/Tashkent", ts)
        self.assertEqual((first, last, key), ("Dilshodbek | 12:30", None, "2026-10-11 12:30"))
        first, _, key = bot.clock_names_for("Dilshodbek", "", "Asia/Tokyo", ts)
        self.assertEqual((first, key), ("Dilshodbek | 16:30", "2026-10-11 16:30"))

    def test_unknown_zone_falls_back_to_tashkent(self):
        ts = datetime(2026, 10, 11, 7, 30, tzinfo=timezone.utc).timestamp()
        self.assertEqual(bot.clock_names_for("A", "", "Bad/Zone", ts)[0], "A | 12:30")

    def test_boundary_scheduling(self):
        fire_at, boundary = bot.next_clock_boundary(1000.0 * 60 + 10)  # daqiqa o'rtasida
        self.assertEqual(boundary, 1001 * 60)
        self.assertAlmostEqual(fire_at, boundary - bot.NAME_CLOCK_LEAD_SECONDS)
        # LEAD oynasiga kech tushsa — keyingi daqiqa
        late = 1001 * 60 - bot.NAME_CLOCK_LEAD_SECONDS + 0.1
        fire_at, boundary = bot.next_clock_boundary(late)
        self.assertEqual(boundary, 1002 * 60)
        self.assertGreater(fire_at, late)

    def test_boundary_never_drifts(self):
        t = 123456.3
        for _ in range(500):
            fire_at, boundary = bot.next_clock_boundary(t)
            self.assertEqual(boundary % 60, 0)
            t = fire_at + 0.2  # har safar biroz kechikib uyg'onsa ham chegara 60 ga karrali
        self.assertEqual(boundary % 60, 0)


def _target(**kw):
    base = {"owner_user_id": 1, "business_connection_id": "bc", "name_clock_tz": "Asia/Tashkent",
            "name_clock_first": "Dilshodbek", "name_clock_last": "", "name_clock_applied": None}
    base.update(kw)
    return base


TS = datetime(2026, 10, 11, 7, 30, tzinfo=timezone.utc).timestamp()


class Base(unittest.TestCase):
    def setUp(self):
        for name, value in (("ADMIN_ID", ADMIN), ("NAME_CLOCK_PUBLIC", False)):
            p = patch.object(bot, name, value)
            p.start()
            self.addCleanup(p.stop)
        bot._name_clock_backoff_until = 0.0
        bot._name_clock_failures.clear()
        bot._name_clock_inflight.clear()
        bot._last_flood_notice = 0.0

    def tick(self, targets, set_side_effect=None, at_ts=TS):
        tg = MagicMock()
        tg.set_business_account_name = AsyncMock(side_effect=set_side_effect)
        tg.send_message = AsyncMock()
        with patch.object(db, "get_name_clock_targets", return_value=targets), \
             patch.object(db, "mark_name_clock_applied") as mark, \
             patch.object(db, "update_settings") as upd:
            run(bot.name_clock_tick(tg, at_ts))
        return tg, mark, upd


class TickTests(Base):
    def test_sets_name_and_marks_minute(self):
        tg, mark, _ = self.tick([_target()])
        tg.set_business_account_name.assert_awaited_once_with(
            business_connection_id="bc", first_name="Dilshodbek | 12:30", last_name=None
        )
        mark.assert_called_once_with(1, "2026-10-11 12:30")

    def test_with_last_name(self):
        tg, _, _ = self.tick([_target(name_clock_last="Abdu")])
        kw = tg.set_business_account_name.call_args.kwargs
        self.assertEqual((kw["first_name"], kw["last_name"]), ("Dilshodbek", "Abdu | 12:30"))

    def test_same_minute_not_resent(self):
        tg, mark, _ = self.tick([_target(name_clock_applied="2026-10-11 12:30")])
        tg.set_business_account_name.assert_not_called()
        mark.assert_not_called()

    def test_next_minute_is_sent(self):
        tg, _, _ = self.tick([_target(name_clock_applied="2026-10-11 12:29")])
        tg.set_business_account_name.assert_awaited_once()

    def test_many_users_all_updated_concurrently(self):
        targets = [_target(owner_user_id=i, business_connection_id=f"bc{i}") for i in range(60)]
        tg, mark, _ = self.tick(targets)
        self.assertEqual(tg.set_business_account_name.await_count, 60)
        self.assertEqual(mark.call_count, 60)

    def test_one_failure_does_not_block_others(self):
        calls = []

        async def side(business_connection_id, first_name, last_name=None):
            calls.append(business_connection_id)
            if business_connection_id == "bc1":
                raise NetworkError("x")

        tg = MagicMock()
        tg.set_business_account_name = AsyncMock(side_effect=side)
        targets = [_target(owner_user_id=i, business_connection_id=f"bc{i}") for i in range(3)]
        with patch.object(db, "get_name_clock_targets", return_value=targets), \
             patch.object(db, "mark_name_clock_applied") as mark:
            run(bot.name_clock_tick(tg, TS))
        self.assertEqual(sorted(calls), ["bc0", "bc1", "bc2"])
        self.assertEqual(mark.call_count, 2)  # xato bergani belgilanmaydi — keyingi daqiqada qayta uriniladi

    def test_flood_sets_backoff_notifies_admin_once(self):
        tg, mark, _ = self.tick([_target(), _target(owner_user_id=2, business_connection_id="b2")],
                                set_side_effect=RetryAfter(30))
        mark.assert_not_called()
        self.assertGreater(bot._name_clock_backoff_until, time.time() + 20)
        self.assertEqual(tg.send_message.await_count, 1)
        self.assertEqual(tg.send_message.call_args.kwargs["chat_id"], ADMIN)
        # Backoff davomida keyingi tick umuman so'rov yubormaydi
        tg2, _, _ = self.tick([_target()])
        tg2.set_business_account_name.assert_not_called()

    def test_not_modified_counts_as_success(self):
        tg, mark, upd = self.tick([_target()], set_side_effect=BadRequest("Bad Request: name is not modified"))
        mark.assert_called_once_with(1, "2026-10-11 12:30")
        upd.assert_not_called()

    def test_repeated_permission_errors_disable_feature_and_notify(self):
        for i in range(bot.NAME_CLOCK_MAX_FAILURES):
            tg, _, upd = self.tick([_target()], set_side_effect=BadRequest("rights"))
        upd.assert_called_with(1, name_clock_enabled=False)
        self.assertEqual(tg.send_message.call_args.kwargs["chat_id"], 1)
        self.assertIn("o'chirildi", tg.send_message.call_args.kwargs["text"])

    def test_success_resets_failure_counter(self):
        self.tick([_target()], set_side_effect=BadRequest("rights"))
        self.tick([_target(name_clock_applied=None)])
        self.assertNotIn(1, bot._name_clock_failures)

    def test_no_targets_no_calls(self):
        tg, _, _ = self.tick([])
        tg.set_business_account_name.assert_not_called()


def _query(data, user_id=OWNER):
    q = MagicMock()
    q.data = data
    q.from_user.id = user_id
    q.answer = AsyncMock()
    q.edit_message_text = AsyncMock()
    q.message.reply_text = AsyncMock()
    u = MagicMock()
    u.callback_query = q
    return u, q


def _settings(**kw):
    base = {"name_clock_enabled": False, "name_clock_tz": None, "name_clock_first": None,
            "name_clock_last": None, "ai_enabled": False, "offline": False, "cooldown_hours": 3.0,
            "auto_reply_text": "x"}
    base.update(kw)
    return base


class MenuTests(Base):
    def test_panel_button_only_for_admin_unless_public(self):
        def datas(uid):
            with patch.object(db, "get_settings", return_value=_settings()):
                _, m = bot.build_panel(uid)
            return [b.callback_data for row in m.inline_keyboard for b in row]

        self.assertIn("nc_menu", datas(ADMIN))
        self.assertNotIn("nc_menu", datas(5))
        with patch.object(bot, "NAME_CLOCK_PUBLIC", True):
            self.assertIn("nc_menu", datas(5))

    def test_non_admin_cannot_use_buttons(self):
        u, q = _query("nc_toggle", user_id=5)
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd:
            run(bot.on_button(u, MagicMock()))
        upd.assert_not_called()
        q.edit_message_text.assert_not_called()

    def test_menu_preview_and_zone(self):
        with patch.object(db, "get_settings", return_value=_settings(name_clock_first="Dilshod", name_clock_tz="Asia/Tokyo")):
            text, _ = bot.build_name_clock_menu(OWNER)
        self.assertIn("Dilshod | ", text)
        self.assertIn("Tokio", text)

    def test_zone_menu_has_ten_and_marks_current(self):
        with patch.object(db, "get_settings", return_value=_settings(name_clock_tz="Europe/Berlin")):
            _, m = bot.build_name_clock_zones_menu(OWNER)
        buttons = [b for row in m.inline_keyboard for b in row if b.callback_data.startswith("nc_tz:")]
        self.assertEqual(len(buttons), 10)
        self.assertTrue([b for b in buttons if b.callback_data == "nc_tz:berlin"][0].text.startswith("✅"))

    def test_choose_zone_saves_and_resets_applied(self):
        u, q = _query("nc_tz:tokyo")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "update_settings") as upd:
            run(bot.on_button(u, MagicMock()))
        upd.assert_called_once_with(OWNER, name_clock_tz="Asia/Tokyo", name_clock_applied=None)

    def test_unknown_zone_key_ignored(self):
        u, q = _query("nc_tz:hacker")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "update_settings") as upd:
            run(bot.on_button(u, MagicMock()))
        upd.assert_not_called()


class ToggleTests(Base):
    def _enable(self, can_edit_name=True, chat=None, connected=True):
        u, q = _query("nc_toggle")
        tg = MagicMock()
        tg.get_business_connection = AsyncMock(return_value=MagicMock(
            is_enabled=True, rights=MagicMock(can_edit_name=can_edit_name)))
        tg.get_chat = AsyncMock(return_value=chat or MagicMock(first_name="Dilshodbek", last_name=None))
        tg.set_business_account_name = AsyncMock()
        conn = {"owner_user_id": OWNER, "business_connection_id": "bc", "is_enabled": True,
                "can_reply": True, "can_edit_bio": False, "can_edit_name": False} if connected else None
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "get_connection", return_value=conn), \
             patch.object(db, "upsert_connection") as ups, patch.object(db, "update_settings") as upd, \
             patch.object(db, "get_name_clock_targets", return_value=[]):
            async def go():
                await bot.on_button(u, MagicMock(bot=tg))
                await asyncio.gather(*list(bot._background_tasks))
            run(go())
        return q, upd, ups

    def test_enable_captures_base_name_and_turns_on(self):
        q, upd, ups = self._enable()
        kwargs = [c.kwargs for c in upd.call_args_list if "name_clock_enabled" in c.kwargs][0]
        self.assertTrue(kwargs["name_clock_enabled"])
        self.assertEqual((kwargs["name_clock_first"], kwargs["name_clock_last"]), ("Dilshodbek", ""))
        self.assertTrue(ups.call_args.kwargs["can_edit_name"])  # joriy ruxsat Telegramdan yangilandi
        q.answer.assert_awaited_once()

    def test_enable_strips_old_clock_from_captured_name(self):
        q, upd, _ = self._enable(chat=MagicMock(first_name="Dilshodbek | 12:30", last_name=None))
        kwargs = [c.kwargs for c in upd.call_args_list if "name_clock_enabled" in c.kwargs][0]
        self.assertEqual(kwargs["name_clock_first"], "Dilshodbek")

    def test_enable_refused_without_permission(self):
        q, upd, _ = self._enable(can_edit_name=False)
        self.assertFalse([c for c in upd.call_args_list if "name_clock_enabled" in c.kwargs])
        self.assertIn("ruxsati yo'q", q.edit_message_text.call_args.args[0])

    def test_enable_refused_when_not_connected(self):
        q, upd, _ = self._enable(connected=False)
        self.assertFalse(upd.call_args_list)
        self.assertIn("ulang", q.edit_message_text.call_args.args[0])

    def test_disable_restores_original_name(self):
        u, q = _query("nc_toggle")
        tg = MagicMock()
        tg.set_business_account_name = AsyncMock()
        s = _settings(name_clock_enabled=True, name_clock_first="Dilshodbek", name_clock_last="Abdu")
        conn = {"owner_user_id": OWNER, "business_connection_id": "bc", "is_enabled": True}
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=s), \
             patch.object(db, "get_connection", return_value=conn), patch.object(db, "update_settings") as upd:
            run(bot.on_button(u, MagicMock(bot=tg)))
        tg.set_business_account_name.assert_awaited_once_with(
            business_connection_id="bc", first_name="Dilshodbek", last_name="Abdu")
        self.assertIn(((OWNER,), {"name_clock_enabled": False}), [(c.args, c.kwargs) for c in upd.call_args_list])

    def test_edit_base_name_flow(self):
        u, q = _query("nc_edit_name")
        with patch.object(bot, "track_user"):
            run(bot.on_button(u, MagicMock()))
        self.assertEqual(bot.get_pending_action(OWNER), "nc_name")
        tu = MagicMock()
        tu.effective_user = MagicMock(id=OWNER, is_bot=False)
        tu.message.text = "Ali Aliyev | 10:00"
        tu.message.reply_text = AsyncMock()
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd, \
             patch.object(db, "get_settings", return_value=_settings()):
            run(bot.on_text(tu, MagicMock()))
        upd.assert_called_once_with(OWNER, name_clock_first="Ali", name_clock_last="Aliyev", name_clock_applied=None)
        self.assertIsNone(bot.get_pending_action(OWNER))


class ConnectionUpdateTests(Base):
    def _update(self, enabled, can_edit_name):
        u = MagicMock()
        u.channel_post = None
        u.business_message = None
        c = u.business_connection
        c.user.id = OWNER
        c.user_chat_id = OWNER
        c.id = "bc"
        c.is_enabled = enabled
        c.can_reply = True
        c.rights = MagicMock(can_reply=True, can_edit_bio=False, can_edit_name=can_edit_name)
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock()
        with patch.object(db, "upsert_connection") as ups, patch.object(db, "delete_ai_data"), \
             patch.object(db, "get_settings", return_value=_settings(name_clock_enabled=True)), \
             patch.object(db, "update_settings") as upd:
            run(bot.on_raw_update(u, ctx))
        return ups, upd, ctx

    def test_rights_saved(self):
        ups, _, _ = self._update(True, True)
        self.assertTrue(ups.call_args.kwargs["can_edit_name"])

    def test_losing_permission_disables_clock(self):
        _, upd, ctx = self._update(True, False)
        upd.assert_called_with(OWNER, name_clock_enabled=False)

    def test_disconnect_disables_clock(self):
        _, upd, _ = self._update(False, True)
        upd.assert_called_with(OWNER, name_clock_enabled=False)


class WiringTests(Base):
    def test_post_init_registered(self):
        app = bot.build_app()
        self.assertIsNotNone(app.post_init)


class ExternalRenameTests(Base):
    """Regressiya: egasi ismni Telegramda o'zi o'zgartirsa, bot eski ismni qaytarib qo'yardi."""

    def test_logic_detects_real_rename_only(self):
        f = logic.is_external_rename
        self.assertFalse(f("Ali", "", "Ali", None))
        self.assertFalse(f("Ali", "", "Ali | 12:30", ""))          # bot qo'ygan soat — o'zgarish emas
        self.assertFalse(f("Ali", "Vali", "Ali", "Vali | 12:30"))
        self.assertTrue(f("Ali", "", "Dilshodbek", ""))
        self.assertTrue(f("Ali", "", "Dilshodbek | 12:30", ""))   # yangi ism + o'zi yozgan soat
        self.assertTrue(f("Ali", "Vali", "Ali", ""))              # familiyani olib tashladi
        self.assertFalse(f("Ali", "", "", None))                  # Telegram ism bermadi

    def test_truncated_long_name_is_not_a_rename(self):
        long_name = "A" * 64
        self.assertFalse(logic.is_external_rename(long_name, "", "A" * 56, ""))
        self.assertTrue(logic.is_external_rename("Ali", "", "A", ""))  # qisqa ismda prefiks o'zgarish hisoblanadi

    def _adopt(self, settings, cur_first, cur_last=None):
        with patch.object(db, "get_settings", return_value=settings), \
             patch.object(db, "update_settings") as upd:
            result = bot.adopt_new_base_name(OWNER, cur_first, cur_last)
        return result, upd

    def test_new_name_becomes_base(self):
        s = _settings(name_clock_enabled=True, name_clock_first="Eski", name_clock_last="")
        result, upd = self._adopt(s, "Dilshodbek | 13:00")
        self.assertTrue(result)
        upd.assert_called_once_with(OWNER, name_clock_first="Dilshodbek", name_clock_last="", name_clock_applied=None)

    def test_own_clock_name_is_not_adopted(self):
        s = _settings(name_clock_enabled=True, name_clock_first="Ali", name_clock_last="")
        result, upd = self._adopt(s, "Ali | 12:30")
        self.assertFalse(result)
        upd.assert_not_called()

    def test_ignored_when_clock_disabled(self):
        result, upd = self._adopt(_settings(name_clock_enabled=False, name_clock_first="Eski"), "Yangi")
        self.assertFalse(result)
        upd.assert_not_called()

    def test_track_user_adopts_for_allowed_user(self):
        user = MagicMock(id=OWNER, username="u", full_name="x", first_name="Yangi", last_name=None, is_bot=False)
        with patch.object(db, "record_user"), patch.object(bot, "adopt_new_base_name") as adopt:
            bot.track_user(user)
        adopt.assert_called_once_with(OWNER, "Yangi", None)

    def test_track_user_skips_unallowed_user(self):
        user = MagicMock(id=5, username="u", full_name="x", first_name="Yangi", last_name=None, is_bot=False)
        with patch.object(db, "record_user"), patch.object(bot, "adopt_new_base_name") as adopt:
            bot.track_user(user)
        adopt.assert_not_called()

    def test_sync_reads_real_name_and_adopts(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(return_value=MagicMock(first_name="Yangi ism", last_name=None))
        with patch.object(db, "get_name_clock_targets", return_value=[_target()]), \
             patch.object(bot, "adopt_new_base_name") as adopt:
            run(bot.name_clock_sync(tg))
        adopt.assert_called_once_with(1, "Yangi ism", None)

    def test_sync_survives_telegram_errors(self):
        tg = MagicMock()
        tg.get_chat = AsyncMock(side_effect=NetworkError("x"))
        with patch.object(db, "get_name_clock_targets", return_value=[_target()]), \
             patch.object(bot, "adopt_new_base_name") as adopt:
            run(bot.name_clock_sync(tg))
        adopt.assert_not_called()

    def test_owner_business_message_adopts_new_name(self):
        u = MagicMock()
        u.channel_post = None
        u.business_connection = None
        bm = u.business_message
        bm.business_connection_id = "bc"
        bm.from_user = MagicMock(id=OWNER, first_name="Yangi", last_name="Familiya")
        bm.chat.id = 9
        bm.message_id = 1
        conn = {"owner_user_id": OWNER, "is_enabled": True, "can_reply": True, "is_blocked": False}
        with patch.object(db, "get_connection_by_business_id", return_value=conn), \
             patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(bot, "adopt_new_base_name") as adopt, patch.object(db, "pause_ai_chat"):
            run(bot.on_raw_update(u, MagicMock()))
        adopt.assert_called_once_with(OWNER, "Yangi", "Familiya")

    def test_sync_loop_registered(self):
        import inspect
        self.assertIn("name_clock_sync_loop", inspect.getsource(bot._post_init))


if __name__ == "__main__":
    unittest.main()
