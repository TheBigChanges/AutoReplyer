"""Tarif cheklovlari: BIO (pro/ultra), matn (pro/ultra), AI (ultra), ism soati faqat standart shrift."""
import asyncio
import os
import random
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
import i18n  # noqa: E402
import logic  # noqa: E402

USER, ADMIN = 9, 1
TS = 1760000000.0


def run(c):
    return asyncio.run(c)


def buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


class Base(unittest.TestCase):
    def setUp(self):
        bot._lang_cache.clear()
        for p in (patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)),
                  patch.object(bot, "ADMIN_ID", ADMIN),
                  patch.object(db, "record_user")):
            p.start()
            self.addCleanup(p.stop)

    def plan(self, plan, user=USER):
        p = patch.object(db, "get_user_plan", return_value=plan)
        p.start()
        self.addCleanup(p.stop)


class TableTests(Base):
    def test_spec(self):
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["bio"], ("pro", "ultra"))
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["custom_text"], ("plus", "pro", "ultra"))
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["ai"], ("ultra",))
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["name_clock_fonts"], ("ultra",))
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["name_clock_zones"], ("pro", "ultra"))
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["faq"], ("plus", "pro", "ultra"))
        self.assertEqual(bot.FAQ_PLAN_LIMITS, {"plus": 15, "pro": 30, "ultra": 65})

    def test_matrix(self):
        expect = {
            "bio": {"free": False, "plus": False, "pro": True, "ultra": True},
            "custom_text": {"free": False, "plus": True, "pro": True, "ultra": True},
            "ai": {"free": False, "plus": False, "pro": False, "ultra": True},
            "name_clock_fonts": {"free": False, "plus": False, "pro": False, "ultra": True},
            "name_clock_zones": {"free": False, "plus": False, "pro": True, "ultra": True},
            "faq": {"free": False, "plus": True, "pro": True, "ultra": True},
        }
        for feature, row in expect.items():
            for plan, allowed in row.items():
                self.assertEqual(bot.plan_allows(USER, plan, feature), allowed, f"{feature}/{plan}")

    def test_admin_unrestricted_and_missing_plan_is_free(self):
        for feature in bot.DEFAULT_FEATURE_PLANS:
            self.assertTrue(bot.plan_allows(ADMIN, "free", feature))
        self.assertFalse(bot.plan_allows(USER, None, "bio"))

    def test_db_error_means_free(self):
        with patch.object(db, "get_user_plan", side_effect=RuntimeError("x")):
            self.assertFalse(bot.has_feature(USER, "bio"))

    def test_lock_texts_in_all_languages(self):
        for lang in i18n.LANGS:
            self.assertIn("Pro / Ultra", bot.locked_text(lang, "bio"))
            self.assertIn("Ultra", bot.locked_text(lang, "ai"))
            self.assertIn("Ultra", bot.locked_text(lang, "name_clock_fonts"))
            self.assertNotIn("{", bot.locked_text(lang, "name_clock_fonts"))
        self.assertIn("only on the Ultra plans", bot.locked_text("en", "name_clock_fonts"))
        
    def test_button_to_feature_mapping(self):
        f = bot.locked_feature_for
        for d in ("bio_menu", "bio_set_new_year", "bio_set_navroz", "bio_set_birthday"):
            self.assertEqual(f(d), "bio")
        self.assertIsNone(f("bio_disable"))  # o'chirish har doim mumkin
        for d in ("edit_text", "sleep_edit_text"):
            self.assertEqual(f(d), "custom_text")
        for d in ("ai_menu", "ai_on", "ai_off", "ai_toggle", "ai_roles", "ai_role:friend", "ai_edit_info"):
            self.assertEqual(f(d), "ai")
        for d in ("edit_cooldown", "sleep_menu", "nc_menu", "open_panel", "plans"):
            self.assertIsNone(f(d))


def _press(data, uid=USER):
    update = MagicMock()
    q = AsyncMock()
    q.data = data
    q.from_user.id = uid
    q.from_user.username = "x"
    q.from_user.full_name = "X"
    update.callback_query = q
    return update, q


def _settings(**kw):
    s = {"offline": True, "cooldown_hours": 1, "auto_reply_text": "hi", "sleep_mode_enabled": False,
         "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "zzz", "ai_enabled": False,
         "ai_info": None, "ai_role": None, "bio_countdown_target": None, "name_clock_enabled": False,
         "name_clock_first": "Ali", "name_clock_last": "", "name_clock_tz": "Asia/Tashkent", "name_clock_style": "bold"}
    s.update(kw)
    return s


class ButtonGateTests(Base):
    def _press_as(self, plan, data, uid=USER):
        self.plan(plan)
        u, q = _press(data, uid)
        with patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_connection", return_value=None):
            run(bot.on_button(u, MagicMock()))
        return q

    def test_free_user_blocked_from_locked_features(self):
        for data in ("bio_menu", "bio_set_navroz", "edit_text", "sleep_edit_text", "ai_menu", "ai_on", "ai_off", "ai_toggle", "ai_role:friend"):
            q = self._press_as("free", data)
            text = q.edit_message_text.call_args.args[0]
            self.assertIn("\U0001F512", text, data)
        with patch.object(db, "update_settings") as upd:
            self._press_as("free", "ai_on")
            self._press_as("free", "bio_set_navroz")
            upd.assert_not_called()

    def test_locked_view_has_plans_and_back_buttons(self):
        q = self._press_as("free", "ai_menu")
        data = [b.callback_data for b in buttons(q.edit_message_text.call_args.kwargs["reply_markup"])]
        self.assertEqual(data, ["plans", "open_panel"])

    def test_pending_prompt_not_started_for_locked(self):
        with patch.object(bot, "set_pending_action") as pend:
            self._press_as("free", "edit_text")
            self._press_as("plus", "birthday")
            pend.assert_not_called()

    def test_pro_gets_bio_and_text_but_not_ai(self):
        with patch.object(bot, "set_pending_action") as pend:
            self._press_as("pro", "edit_text")
            pend.assert_called_once_with(USER, "text")
        q = self._press_as("pro", "ai_menu")
        self.assertIn("\U0001F512", q.edit_message_text.call_args.args[0])

    def test_ultra_gets_everything(self):
        with patch.object(bot, "set_pending_action") as pend:
            self._press_as("ultra", "edit_text")
            pend.assert_called_once()
        q = self._press_as("ultra", "ai_menu")
        self.assertNotIn("\U0001F512 «", q.edit_message_text.call_args.args[0])

    def test_admin_unrestricted(self):
        with patch.object(bot, "set_pending_action") as pend:
            self._press_as("free", "edit_text", uid=ADMIN)
            pend.assert_called_once()

    def test_disable_bio_always_allowed(self):
        self.plan("free")
        u, q = _press("bio_disable")
        with patch.object(db, "update_settings") as upd, patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "get_connection", return_value={"can_edit_bio": True}):
            run(bot.on_button(u, MagicMock()))
        upd.assert_called_once_with(USER, bio_countdown_target=None)

    def test_pending_text_gated_in_on_text(self):
        self.plan("free")
        u = MagicMock()
        u.effective_user.id = USER
        u.message.text = "new text"
        u.message.reply_text = AsyncMock()
        with patch.object(bot, "get_pending_action", return_value="text"), patch.object(db, "update_settings") as upd:
            run(bot.on_text(u, MagicMock()))
        upd.assert_not_called()
        self.assertIn("\U0001F512", u.message.reply_text.call_args.args[0])


class PanelLockMarkTests(Base):
    def test_panel_marks_locked_buttons(self):
        for plan, locked in (("free", {"edit_text", "bio_menu", "ai_menu", "faq_menu", "kb_menu", "au_menu"}), ("plus", {"bio_menu", "ai_menu", "kb_menu"}), ("pro", {"ai_menu", "kb_menu"}), ("ultra", set())):
            self.plan(plan)
            with patch.object(db, "get_settings", return_value=_settings()):
                _, markup = bot.build_panel(USER)
            got = {b.callback_data for b in buttons(markup) if b.text.startswith("\U0001F512")}
            self.assertEqual(got, locked, plan)
            patch.stopall()
            self.setUp()


class NameClockFontTests(Base):
    def test_styles_menu_locks_everything_except_default_below_ultra(self):
        for plan in ("free", "plus", "pro"):
            self.plan(plan)
            with patch.object(db, "get_settings", return_value=_settings()):
                _, markup = bot.build_name_clock_styles_menu(USER)
            for b in buttons(markup)[:-1]:
                key = b.callback_data.split(":")[1]
                self.assertEqual(b.text.startswith("\U0001F512"), key != logic.DEFAULT_NAME_CLOCK_STYLE, f"{plan}/{key}")
            patch.stopall()
            self.setUp()

    def test_ultra_sees_all_fonts_unlocked_and_can_choose(self):
        self.plan("ultra")
        with patch.object(db, "get_settings", return_value=_settings()):
            _, markup = bot.build_name_clock_styles_menu(USER)
        self.assertFalse(any(b.text.startswith("\U0001F512") for b in buttons(markup)))
        with patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_connection", return_value=None), \
             patch.object(db, "update_settings") as upd, patch.object(bot, "_apply_now_if_enabled"):
            u, q = _press("nc_style:bold")
            run(bot.on_button(u, MagicMock()))
        upd.assert_called_once_with(USER, name_clock_style="bold", name_clock_applied=None)

    def test_choosing_locked_font_changes_nothing(self):
        self.plan("pro")
        ctx = MagicMock()
        with patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_connection", return_value=None), \
             patch.object(db, "update_settings") as upd:
            u, q = _press("nc_style:bold")
            run(bot.on_button(u, ctx))
        upd.assert_not_called()
        self.assertIn("\U0001F512", q.edit_message_text.call_args.args[0])

    def test_choosing_default_style_allowed(self):
        self.plan("free")
        with patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "update_settings") as upd, \
             patch.object(bot, "_apply_now_if_enabled"):
            u, q = _press("nc_style:default")
            run(bot.on_button(u, MagicMock()))
        upd.assert_called_once()

    def test_menu_shows_default_font_for_locked_user_with_old_style(self):
        self.plan("free")
        with patch.object(db, "get_settings", return_value=_settings(name_clock_style="bold", name_clock_enabled=True)):
            text, _ = bot.build_name_clock_menu(USER)
        self.assertNotIn(logic.style_time("20:45", "bold"), text)
        self.assertIn(logic.style_time("20:45", logic.DEFAULT_NAME_CLOCK_STYLE), text)

    def _tick_name(self, plan, owner=USER, style="bold"):
        tg = MagicMock()
        tg.set_business_account_name = AsyncMock()
        target = {"owner_user_id": owner, "business_connection_id": "bc", "name_clock_tz": "Asia/Tashkent",
                  "name_clock_first": "Ali", "name_clock_last": "", "name_clock_applied": None,
                  "name_clock_style": style, "plan": plan}
        with patch.object(db, "get_name_clock_targets", return_value=[target]), patch.object(db, "mark_name_clock_applied_bulk"):
            bot._name_clock_inflight.clear()
            bot._name_clock_backoff_until = 0.0
            run(bot.name_clock_tick(tg, TS))
        return tg.set_business_account_name.call_args.kwargs["first_name"]

    def test_clock_default_font_below_ultra_and_chosen_font_for_ultra(self):
        plain = self._tick_name("ultra", style="default")
        self.assertNotEqual(self._tick_name("ultra", style="bold"), plain)
        self.assertEqual(self._tick_name("pro", style="bold"), plain)
        self.assertEqual(self._tick_name("free", style="circle"), plain)
        self.assertEqual(self._tick_name("plus", style="bold"), plain)

    def test_admin_keeps_fonts(self):
        plain = self._tick_name("free", style="default")
        self.assertNotEqual(self._tick_name("free", owner=ADMIN, style="bold"), plain)

    def test_downgraded_ultra_returns_to_default_font(self):
        plain = self._tick_name("ultra", style="default")
        self.assertNotEqual(self._tick_name("ultra", style="strike"), plain)
        self.assertEqual(self._tick_name("free", style="strike"), plain)


class ZoneTests(Base):
    def _tick(self, plan, tz, owner=USER):
        tg = MagicMock()
        tg.set_business_account_name = AsyncMock()
        target = {"owner_user_id": owner, "business_connection_id": "bc", "name_clock_tz": tz, "name_clock_first": "Ali",
                  "name_clock_last": "", "name_clock_applied": None, "name_clock_style": "default", "plan": plan}
        with patch.object(db, "get_name_clock_targets", return_value=[target]), patch.object(db, "mark_name_clock_applied_bulk"):
            bot._name_clock_inflight.clear()
            bot._name_clock_backoff_until = 0.0
            run(bot.name_clock_tick(tg, TS))
        return tg.set_business_account_name.call_args.kwargs["first_name"]

    def test_zones_menu_only_tashkent_unlocked_below_pro(self):
        for plan in ("free", "plus"):
            self.plan(plan)
            with patch.object(db, "get_settings", return_value=_settings()):
                _, markup = bot.build_name_clock_zones_menu(USER)
            for b in buttons(markup)[:-1]:
                key = b.callback_data.split(":")[1]
                self.assertEqual(b.text.startswith("\U0001F512"), key != "tashkent", f"{plan}/{key}")
            patch.stopall()
            self.setUp()

    def test_pro_and_ultra_zones_all_unlocked(self):
        for plan in ("pro", "ultra"):
            self.plan(plan)
            with patch.object(db, "get_settings", return_value=_settings()):
                _, markup = bot.build_name_clock_zones_menu(USER)
            self.assertFalse(any(b.text.startswith("\U0001F512") for b in buttons(markup)), plan)
            patch.stopall()
            self.setUp()

    def test_free_cannot_choose_other_zone_but_can_choose_tashkent(self):
        self.plan("free")
        with patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_connection", return_value=None), \
             patch.object(db, "update_settings") as upd, patch.object(bot, "_apply_now_if_enabled"):
            u, q = _press("nc_tz:tokyo")
            run(bot.on_button(u, MagicMock()))
            upd.assert_not_called()
            self.assertIn("\U0001F512", q.edit_message_text.call_args.args[0])
            u, q = _press("nc_tz:tashkent")
            run(bot.on_button(u, MagicMock()))
            upd.assert_called_once()

    def test_pro_and_ultra_can_choose_other_zone(self):
        for plan in ("pro", "ultra"):
            self.plan(plan)
            with patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_connection", return_value=None), \
                 patch.object(db, "update_settings") as upd, patch.object(bot, "_apply_now_if_enabled"):
                u, q = _press("nc_tz:tokyo")
                run(bot.on_button(u, MagicMock()))
            upd.assert_called_once_with(USER, name_clock_tz="Asia/Tokyo", name_clock_applied=None)
            patch.stopall()
            self.setUp()

    def test_clock_uses_tashkent_below_pro_even_if_other_zone_saved(self):
        tashkent = self._tick("ultra", "Asia/Tashkent")
        self.assertNotEqual(self._tick("ultra", "Asia/Tokyo"), tashkent)
        self.assertNotEqual(self._tick("pro", "Asia/Tokyo"), tashkent)
        self.assertEqual(self._tick("free", "Asia/Tokyo"), tashkent)
        self.assertEqual(self._tick("plus", "Europe/London"), tashkent)

    def test_admin_keeps_zones(self):
        tashkent = self._tick("free", "Asia/Tashkent")
        self.assertNotEqual(self._tick("free", "Asia/Tokyo", owner=ADMIN), tashkent)

    def test_menu_shows_tashkent_for_locked_user_with_old_zone(self):
        self.plan("free")
        with patch.object(db, "get_settings", return_value=_settings(name_clock_tz="Asia/Tokyo")):
            text, _ = bot.build_name_clock_menu(USER)
        self.assertIn("Toshkent", text)
        self.assertNotIn("Tokio", text)


class PlanDescriptionTests(Base):
    def test_free_and_plus_list_locked_features_with_counts(self):
        text = bot.plan_features_text("uz", "free")
        self.assertIn("Nimalar kiradi", text)
        self.assertIn("yuqoriroq tariflarda ochiladi", text)
        self.assertIn("faqat O'zbekiston vaqti", text)
        self.assertIn(f"{len(bot.NAME_CLOCK_STYLES) - 1} xil", text)
        self.assertIn(f"{len(bot.NAME_CLOCK_ZONES) - 1} ta shahar", text)
        plus = bot.plan_features_text("uz", "plus")
        included, excluded = plus.split("Bu tarifda yo'q")
        self.assertIn("o'zingiz yozish", included)
        self.assertIn("BIO hisoblagich", excluded)
        self.assertNotIn("BIO hisoblagich", included)
        self.assertIn("Reklama yo'q", included)

    def test_pro_includes_bio_text_and_zones_but_not_ai_fonts(self):
        text = bot.plan_features_text("en", "pro")
        included, excluded = text.split("Not included")
        self.assertIn("BIO countdown", included)
        self.assertIn("Write your own auto-reply", included)
        self.assertIn("city time zones", included)
        self.assertIn("all city time zones", included)  # soat qatori ham shaharlarni aytadi
        for word in ("AI Assistant", "stylish fonts"):
            self.assertIn(word, excluded)
            self.assertNotIn(word, included)
        self.assertNotIn("time zones", excluded)

    def test_ultra_has_everything_and_no_excluded_section(self):
        for lang in i18n.LANGS:
            text = bot.plan_features_text(lang, "ultra")
            self.assertNotIn(i18n.T["plan_excludes"][lang], text)
            self.assertNotIn("only", text.lower() if lang == "en" else "")
        text = bot.plan_features_text("en", "ultra")
        for word in ("BIO countdown", "AI Assistant", "stylish fonts", "time zones", "updated every minute"):
            self.assertIn(word, text)
        self.assertNotIn("Uzbekistan time only", text)

    def test_description_follows_the_real_table(self):
        with patch.object(bot, "FEATURE_PLANS", {**bot.DEFAULT_FEATURE_PLANS, "bio": ("plus", "pro", "ultra")}):
            included, _ = bot.plan_features_text("en", "plus").split("Not included")
        self.assertIn("BIO countdown", included)

    def test_translated_and_screen_contains_features_and_card(self):
        for lang, word in (("uz", "Nimalar kiradi"), ("en", "What's included"), ("ru", "Что входит")):
            with patch.object(bot, "get_lang", return_value=lang), patch.object(db, "get_user_plan", return_value="free"), \
                 patch.object(bot, "PAYMENT_CARD_NUMBER", "8600123412341234"):
                for plan in ("free", "plus", "pro", "ultra"):
                    text, _ = bot.build_plan_view(USER, plan)
                    self.assertIn(word, text, f"{lang}/{plan}")
                    self.assertNotIn("{", text)
                    if plan != "free":
                        self.assertIn("<code>8600 1234 1234 1234</code>", text)

    def test_current_paid_plan_screen_has_features(self):
        with patch.object(db, "get_user_plan", return_value="pro"), patch.object(db, "get_user_plan_info", return_value=("pro", None)):
            text, _ = bot.build_plan_view(USER, "pro")
        self.assertIn("Nimalar kiradi", text)
        self.assertNotIn("Karta raqami", text)


class BehaviourGateTests(Base):
    def test_ai_not_used_after_downgrade(self):
        self.plan("pro")
        bm = MagicMock()
        bm.business_connection_id = "bc"
        bm.from_user.id = 500
        bm.from_user.is_bot = False
        bm.text = "hello"
        bm.chat.id = 5
        upd = MagicMock()
        upd.channel_post = None
        upd.business_connection = None
        upd.business_message = bm
        conn = {"owner_user_id": USER, "is_enabled": True, "can_reply": True, "is_blocked": False}
        ctx = MagicMock()
        with patch.object(db, "get_connection_by_business_id", return_value=conn), \
             patch.object(db, "get_settings", return_value=_settings(ai_enabled=True, cooldown_hours=1, auto_reply_text="Static")), \
             patch.object(bot.ai, "is_configured", return_value=True), \
             patch.object(bot, "run_ai_reply", AsyncMock()) as ai_run, patch.object(bot, "send_auto_reply", AsyncMock()) as static:
            run(bot.on_raw_update(upd, ctx))
        ai_run.assert_not_called()
        self.assertEqual(static.call_args.args[4], "Static")

    def test_ai_used_for_ultra(self):
        self.plan("ultra")
        bm = MagicMock()
        bm.business_connection_id = "bc"
        bm.from_user.id = 500
        bm.from_user.is_bot = False
        bm.text = "hello"
        bm.chat.id = 5
        upd = MagicMock()
        upd.channel_post = None
        upd.business_connection = None
        upd.business_message = bm
        conn = {"owner_user_id": USER, "is_enabled": True, "can_reply": True, "is_blocked": False}
        with patch.object(db, "get_connection_by_business_id", return_value=conn), \
             patch.object(db, "get_settings", return_value=_settings(ai_enabled=True)), \
             patch.object(db, "is_ai_paused", return_value=False), \
             patch.object(bot.ai, "is_configured", return_value=True), \
             patch.object(bot, "spawn_background") as spawn, patch.object(bot, "run_ai_reply", MagicMock()):
            run(bot.on_raw_update(upd, MagicMock()))
        spawn.assert_called_once()

    def test_bio_refresh_skips_non_entitled(self):
        rows = [
            {"owner_user_id": 10, "business_connection_id": "a", "bio_countdown_target": "new_year", "birthday_month": None,
             "birthday_day": None, "bio_updated_on": None, "lang": "uz", "plan": "free"},
            {"owner_user_id": 11, "business_connection_id": "b", "bio_countdown_target": "new_year", "birthday_month": None,
             "birthday_day": None, "bio_updated_on": None, "lang": "uz", "plan": "pro"},
            {"owner_user_id": ADMIN, "business_connection_id": "c", "bio_countdown_target": "new_year", "birthday_month": None,
             "birthday_day": None, "bio_updated_on": None, "lang": "uz", "plan": "free"},
        ]
        tg = MagicMock()
        tg.set_business_account_bio = AsyncMock()
        with patch.object(db, "get_all_bio_targets", return_value=rows), patch.object(db, "update_settings"):
            updated, failed = run(bot.refresh_bios(tg, only_stale=False))
        sent_to = sorted(c.kwargs["business_connection_id"] for c in tg.set_business_account_bio.call_args_list)
        self.assertEqual(sent_to, ["b", "c"])
        self.assertEqual((updated, failed), (2, 0))

    def test_existing_custom_text_still_sent_after_downgrade(self):
        s = _settings(auto_reply_text="Mening matnim")
        self.assertEqual(bot.auto_reply_text_for(s, "uz"), "Mening matnim")


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class PlanInQueriesDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.uid = random.randint(10**14, 10**15)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        with db.get_conn() as c, c.cursor() as cur:
            for table, col in (("connections", "owner_user_id"), ("settings", "owner_user_id"), ("users", "user_id")):
                cur.execute(f"DELETE FROM {table} WHERE {col} = %s", (self.uid,))

    def _setup_user(self):
        db.record_user(self.uid, username="u", full_name="U")
        db.upsert_connection(owner_user_id=self.uid, business_connection_id=f"bc{self.uid}", can_reply=True,
                             is_enabled=True, can_edit_bio=True, can_edit_name=True)
        db.update_settings(self.uid, name_clock_enabled=True, name_clock_first="Ali", name_clock_last="",
                           bio_countdown_target="new_year")

    def _row(self, rows):
        return next(r for r in rows if r["owner_user_id"] == self.uid)

    def test_targets_report_effective_plan(self):
        self._setup_user()
        self.assertEqual(self._row(db.get_name_clock_targets())["plan"], "free")
        self.assertEqual(self._row(db.get_all_bio_targets())["plan"], "free")
        import time
        db.set_user_plan(self.uid, "pro", time.time() + 3600)
        self.assertEqual(self._row(db.get_name_clock_targets())["plan"], "pro")
        self.assertEqual(self._row(db.get_all_bio_targets())["plan"], "pro")
        db.set_user_plan(self.uid, "pro", time.time() - 5)
        self.assertEqual(self._row(db.get_name_clock_targets())["plan"], "free")
        self.assertEqual(self._row(db.get_all_bio_targets())["plan"], "free")


class AiLimitTests(Base):
    def _run(self, plan, user=USER, times=1, quota_ok=True):
        self.plan(plan)
        bm = MagicMock(business_connection_id="bc")
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch.object(db, "try_consume_ai_quota", return_value=quota_ok) as quota, patch.object(db, "refund_ai_quota"), \
             patch.object(bot, "ai_reply_still_allowed", return_value=True), \
             patch.object(db, "get_ai_history", return_value=[]), patch.object(db, "get_user", return_value={"full_name": "Ali"}), \
             patch.object(db, "add_ai_messages"), patch.object(bot.ai, "generate_reply", AsyncMock(return_value="Hi")):
            for _ in range(times):
                run(bot.run_ai_reply(ctx.bot, bm, user, 5, "hello", {"cooldown_hours": 1, "ai_info": None, "ai_role": None}, "fallback", "x"))
        return quota, ctx

    def test_limit_is_50_per_day(self):
        self.assertEqual(bot.AI_DAILY_LIMIT, 50)
        quota, _ = self._run("ultra")
        self.assertEqual(quota.call_args.args[2], 50)

    def test_admin_has_no_limit(self):
        quota, ctx = self._run("free", user=ADMIN, times=3)
        quota.assert_not_called()
        self.assertEqual(ctx.bot.send_message.await_count, 3)

    def test_limit_reached_sends_static_text(self):
        with patch.object(db, "try_claim_reply", return_value=1.0):
            _, ctx = self._run("ultra", quota_ok=False)
        self.assertEqual(ctx.bot.send_message.call_args.kwargs["text"], "fallback")

    def test_menu_shows_counter_for_ultra_and_unlimited_for_admin(self):
        self.plan("ultra")
        with patch.object(db, "get_settings", return_value=_settings()), patch.object(db, "get_ai_usage", return_value=7):
            self.assertIn("7/50", bot.build_ai_menu(USER)[0])
            self.assertIn(i18n.T["ai_usage_unlimited"]["uz"], bot.build_ai_menu(ADMIN)[0])

    def test_plan_text_mentions_50_for_ultra(self):
        for lang in ("uz", "en", "ru"):
            self.assertIn("50", bot.plan_features_text(lang, "ultra"))
