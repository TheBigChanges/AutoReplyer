"""Panel: 🧩 Avtomatlashtirish (qoida qo'shish, ro'yxat, yoqish/o'chirish, o'chirish) — Plus/Pro/Ultra; Bepul tarifda to'liq yopiq."""
import asyncio
import os
import random
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import automation as au  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402
from i18n import t  # noqa: E402

ADMIN, USER, OTHER = 777, 9, 10
SETTINGS = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
            "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "", "faq_enabled": True,
            "kb_enabled": True, "ai_enabled": False, "ai_info": None, "ai_role": None, "lang": "uz"}


class FakeRules:
    """Xotiradagi qoidalar ombori (egasi bo'yicha ajratilgan) — db funksiyalari o'rniga."""

    def __init__(self):
        self.rows = []
        self.next_id = 1
        self.add_calls = []

    def install(self, case):
        def add(owner, name, cond, act, prio, max_rules, enabled=False):
            self.add_calls.append({"owner": owner, "cond": cond, "act": act, "enabled": enabled})
            if sum(r["owner_user_id"] == owner for r in self.rows) >= max_rules:
                return None
            rule = {"id": self.next_id, "owner_user_id": owner, "name": name, "conditions": cond, "action": act,
                    "priority": prio, "is_enabled": enabled}
            self.next_id += 1
            self.rows.append(rule)
            return rule["id"]

        def set_enabled(owner, rid, enabled):
            for r in self.rows:
                if r["owner_user_id"] == owner and r["id"] == rid:
                    r["is_enabled"] = enabled
                    return True
            return False

        def delete(owner, rid):
            before = len(self.rows)
            self.rows = [r for r in self.rows if not (r["owner_user_id"] == owner and r["id"] == rid)]
            return len(self.rows) < before

        for name, fn in (
            ("add_automation_rule", add),
            ("list_automation_rules", lambda owner: [dict(r) for r in self.rows if r["owner_user_id"] == owner]),
            ("count_automation_rules", lambda owner: sum(r["owner_user_id"] == owner for r in self.rows)),
            ("set_automation_rule_enabled", set_enabled),
            ("delete_automation_rule", delete),
        ):
            p = patch.object(db, name, side_effect=fn)
            p.start()
            case.addCleanup(p.stop)


def _text_update(text, user_id=USER):
    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_user.username = "x"
    update.effective_user.full_name = "X"
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


class PanelBase(unittest.TestCase):
    plan = "plus"

    def setUp(self):
        for d in (bot.pending_settings_action, bot._pending_settings_set_at, bot._au_drafts, bot._au_del_confirms, bot._faq_drafts, bot._kb_drafts, bot._sc_drafts):
            d.clear()
        self.fake = FakeRules()
        self.fake.install(self)
        for p in (
            patch.object(bot, "ADMIN_ID", ADMIN),
            patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)),  # haqiqiy tarif cheklovlari
            patch.object(db, "get_user_plan", side_effect=lambda uid: self.plan),
            patch.object(db, "get_settings", side_effect=lambda owner: dict(SETTINGS)),
            patch.object(db, "update_settings"),
            patch.object(db, "record_user"),
            patch.object(db, "get_name_clock_base", return_value=None),
            patch.object(db, "get_connection", return_value=None),
            patch.object(db, "get_onboarding_step", return_value="legacy"),
            patch.object(db, "count_faq_entries", return_value=0),
            patch.object(db, "count_kb_entries", return_value=0),
            patch.object(bot, "track_user"),
        ):
            p.start()
            self.addCleanup(p.stop)

    def press(self, data, user=USER):
        q = MagicMock()
        q.data = data
        q.from_user.id = user
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        update = MagicMock()
        update.callback_query = q
        asyncio.run(bot.on_button(update, MagicMock()))
        return q

    def say(self, text, user=USER):
        update = _text_update(text, user)
        asyncio.run(bot.on_text(update, MagicMock()))
        return update.message.reply_text

    @staticmethod
    def shown(q):
        return q.edit_message_text.await_args.args[0]

    @staticmethod
    def datas(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    def keyboard(self, q):
        return self.datas(q.edit_message_text.await_args.kwargs["reply_markup"])

    def create(self, kw="narx*", reply="Salom! Narxlar haqida ma'lumot beraman.", user=USER):
        self.press("au_add", user)
        self.say(kw, user)
        confirm = self.say(reply, user)
        markup = confirm.await_args.kwargs["reply_markup"]
        save = [b.callback_data for row in markup.inline_keyboard for b in row][0]
        return self.press(save, user), confirm


class MainMenuTests(PanelBase):
    def _button(self):
        text, markup = bot.build_panel(USER)
        buttons = [b for row in markup.inline_keyboard for b in row if b.callback_data == "au_menu"]
        self.assertEqual(len(buttons), 1)
        return buttons[0]

    def test_button_unlocked_for_paid(self):
        self.assertNotIn("\U0001F512", self._button().text)

    def test_button_locked_for_free(self):
        self.plan = "free"
        self.assertIn("\U0001F512", self._button().text)

    def test_menu_opens_for_paid_plan(self):
        q = self.press("au_menu")
        self.assertIn("0/", self.shown(q))
        self.assertEqual(self.keyboard(q)[:2], ["au_add", "au_list"])


class AddFlowTests(PanelBase):
    def test_full_flow_saves_enabled_rule(self):
        q, confirm = self.create()
        self.assertIn("narx*", confirm.await_args.args[0])
        call = self.fake.add_calls[-1]
        self.assertEqual((call["owner"], call["enabled"]), (USER, True))
        self.assertEqual(call["cond"]["items"][0]["value"], "narx*")
        self.assertEqual(call["act"]["text"], "Salom! Narxlar haqida ma'lumot beraman.")
        self.assertIn(t("uz", "au_saved"), self.shown(q))
        self.assertTrue(self.fake.rows[0]["is_enabled"])
        self.assertIsNone(bot._au_draft(USER))  # qoralama tozalandi

    def test_saved_rule_actually_matches_a_customer_message(self):
        self.create()
        rule = au.find_matching_automation("Telefon narxi qancha?", self.fake.rows)
        self.assertEqual(rule["action"]["text"], "Salom! Narxlar haqida ma'lumot beraman.")

    def test_steps_set_pending_actions(self):
        self.press("au_add")
        self.assertEqual(bot.get_pending_action(USER), "au_kw")
        self.say("narx*")
        self.assertEqual(bot.get_pending_action(USER), "au_ans")
        self.say("Javob")
        self.assertEqual(bot.get_pending_action(USER), "au_confirm")

    def test_bad_keywords_rejected_and_step_kept(self):
        self.press("au_add")
        for bad in ("*", "a*", "na*rx", "x" * 51, "!!!", "bir ikki uch tort besh olti"):
            reply = self.say(bad)
            self.assertIn("❌", reply.await_args.args[0], bad)
            self.assertEqual(bot.get_pending_action(USER), "au_kw", bad)
            self.assertNotIn("kw", bot._au_draft(USER))

    def test_too_long_reply_rejected(self):
        self.press("au_add")
        self.say("narx")
        reply = self.say("a" * (au.MAX_REPLY_LENGTH + 1))
        self.assertIn("501", reply.await_args.args[0])
        self.assertEqual(bot.get_pending_action(USER), "au_ans")
        self.say("a" * au.MAX_REPLY_LENGTH)
        self.assertEqual(bot.get_pending_action(USER), "au_confirm")

    def test_typing_while_confirming_only_reminds(self):
        self.press("au_add")
        self.say("narx")
        self.say("Javob")
        reply = self.say("yana matn")
        self.assertEqual(reply.await_args.args[0], t("uz", "au_confirm_hint"))
        self.assertEqual(bot.get_pending_action(USER), "au_confirm")
        self.assertEqual(self.fake.rows, [])

    def test_limit_blocks_add(self):
        for i in range(bot.AUTOMATION_RULE_LIMIT):
            self.fake.rows.append({"id": 1000 + i, "owner_user_id": USER, "name": "n", "conditions": {}, "action": {}, "priority": 1, "is_enabled": True})
        q = self.press("au_add")
        self.assertIn("❌", self.shown(q))
        self.assertIsNone(bot.get_pending_action(USER))
        self.assertIsNone(bot._au_draft(USER))

    def test_expired_draft_is_lost(self):
        self.press("au_add")
        self.say("narx")
        self.say("Javob")
        bot._au_drafts[USER]["ts"] -= bot.PENDING_ACTION_TTL_SECONDS + 5
        self.assertIsNone(bot._au_draft(USER))
        reply = self.say("narx")
        self.assertEqual(reply.await_args.args[0], t("uz", "au_draft_lost"))


class StaleButtonTests(PanelBase):
    def _draft_ready(self):
        self.press("au_add")
        self.say("narx")
        self.say("Javob")
        return bot._au_draft(USER)["id"]

    def test_stale_save_does_not_save_and_keeps_draft(self):
        token = self._draft_ready()
        q = self.press("au_save:deadbe")
        self.assertEqual(self.fake.rows, [])
        self.assertEqual(self.shown(q), t("uz", "sc_stale_button"))
        self.assertEqual(bot._au_draft(USER)["id"], token)
        self.assertEqual(bot.get_pending_action(USER), "au_confirm")

    def test_save_twice_creates_one_rule(self):
        token = self._draft_ready()
        self.press(f"au_save:{token}")
        self.press(f"au_save:{token}")
        self.assertEqual(len(self.fake.rows), 1)

    def test_cancel_removes_draft(self):
        token = self._draft_ready()
        q = self.press(f"au_cancel:{token}")
        self.assertIn(t("uz", "au_cancelled"), self.shown(q))
        self.assertIsNone(bot._au_draft(USER))
        self.assertEqual(self.fake.rows, [])

    def test_foreign_cancel_without_draft_keeps_other_pending_input(self):
        bot.set_pending_action(USER, "text")  # boshqa jarayon: avtojavob matni kutilmoqda
        self.press("au_cancel:abc123")
        self.assertEqual(bot.get_pending_action(USER), "text")

    def test_start_and_cancel_drop_the_draft(self):
        self._draft_ready()
        self.assertTrue(bot.clear_flow_state(USER))
        self.assertIsNone(bot._au_draft(USER))
        self.assertEqual(self.fake.rows, [])


class RuleManagementTests(PanelBase):
    def setUp(self):
        super().setUp()
        self.create("narx*", "Narxlar 100$")
        self.rid = self.fake.rows[0]["id"]

    def test_list_shows_rule_and_view_opens(self):
        q = self.press("au_list")
        self.assertIn(f"au_view:{self.rid}", self.keyboard(q))
        q = self.press(f"au_view:{self.rid}")
        self.assertIn("narx*", self.shown(q))
        self.assertIn("Narxlar 100$", self.shown(q))

    def test_off_then_on_is_explicit_and_idempotent(self):
        q = self.press(f"au_off:{self.rid}")
        self.assertFalse(self.fake.rows[0]["is_enabled"])
        self.assertIn(f"au_on:{self.rid}", self.keyboard(q))
        self.press(f"au_off:{self.rid}")  # eski tugma qayta bosildi — holat teskarilanmaydi
        self.assertFalse(self.fake.rows[0]["is_enabled"])
        self.press(f"au_on:{self.rid}")
        self.press(f"au_on:{self.rid}")
        self.assertTrue(self.fake.rows[0]["is_enabled"])

    def test_disabled_rule_marked_in_list(self):
        self.press(f"au_off:{self.rid}")
        q = self.press("au_list")
        markup = q.edit_message_text.await_args.kwargs["reply_markup"]
        self.assertTrue(markup.inline_keyboard[0][0].text.startswith("⏸"))

    def _open_confirm(self, rule_id=None):
        q = self.press(f"au_del:{self.rid if rule_id is None else rule_id}")
        return self.keyboard(q)[0]

    def test_delete_needs_confirmation_and_is_one_time(self):
        yes = self._open_confirm()
        self.assertRegex(yes, rf"^au_del_yes:{self.rid}:[0-9a-f]{{6}}$")
        self.assertEqual(len(self.fake.rows), 1)  # tasdiqsiz o'chmaydi
        q = self.press(yes)
        self.assertEqual(self.fake.rows, [])
        self.assertIn(t("uz", "au_deleted"), self.shown(q))
        self.assertNotIn(USER, bot._au_del_confirms)
        # tasdiqni takrorlash — hech narsani o'chirmaydi (yangi qoida bir xil ID olmasa ham, tasdiq eskirgan)
        self.fake.rows.append({"id": self.rid, "owner_user_id": USER, "name": "n", "conditions": {}, "action": {}, "priority": 1, "is_enabled": True})
        q = self.press(yes)
        self.assertEqual(len(self.fake.rows), 1)
        self.assertEqual(self.shown(q), t("uz", "sc_stale_button"))

    def test_old_yes_button_after_going_back_deletes_nothing(self):
        """Hisobotdagi holat: o'chirish oynasi ochildi -> orqaga qaytildi -> eski «Ha» bosildi."""
        yes = self._open_confirm()
        self.press(f"au_view:{self.rid}")  # orqaga qaytdi: tasdiq bekor
        self.assertNotIn(USER, bot._au_del_confirms)
        q = self.press(yes)
        self.assertEqual(len(self.fake.rows), 1)
        self.assertEqual(self.shown(q), t("uz", "sc_stale_button"))

    def test_yes_with_wrong_token_or_other_rule_deletes_nothing(self):
        self.create("narx2", "Boshqa")
        other_id = self.fake.rows[1]["id"]
        yes = self._open_confirm()
        for bad in (f"au_del_yes:{self.rid}:abcdef", f"au_del_yes:{other_id}:{yes.rsplit(':', 1)[1]}",
                    f"au_del_yes:{self.rid}", "au_del_yes:abc:def", "au_del_yes"):
            self.press(bad)
            self.assertEqual(len(self.fake.rows), 2, bad)
        self.press(yes)  # haqiqiysi hamon ishlaydi
        self.assertEqual([r["id"] for r in self.fake.rows], [other_id])

    def test_new_confirmation_invalidates_the_previous_one(self):
        self.create("narx2", "Boshqa")
        other_id = self.fake.rows[1]["id"]
        first = self._open_confirm()
        self._open_confirm(other_id)
        self.press(first)
        self.assertEqual(len(self.fake.rows), 2)

    def test_confirmation_expires(self):
        yes = self._open_confirm()
        bot._au_del_confirms[USER]["ts"] -= bot.PENDING_ACTION_TTL_SECONDS + 5
        self.press(yes)
        self.assertEqual(len(self.fake.rows), 1)

    def test_other_button_or_cancel_clears_confirmation(self):
        yes = self._open_confirm()
        self.press("au_list")
        self.press(yes)
        self.assertEqual(len(self.fake.rows), 1)
        yes = self._open_confirm()
        bot.clear_flow_state(USER)  # /start, /cancel
        self.press(yes)
        self.assertEqual(len(self.fake.rows), 1)

    def test_stale_yes_keeps_pending_input_of_other_flow(self):
        yes = self._open_confirm()
        self.press(f"au_view:{self.rid}")
        bot.set_pending_action(USER, "text")
        self.press(yes)
        self.assertEqual(bot.get_pending_action(USER), "text")

    def test_other_users_rules_are_invisible_and_untouchable(self):
        for data in (f"au_view:{self.rid}", f"au_on:{self.rid}", f"au_off:{self.rid}", f"au_del:{self.rid}"):
            q = self.press(data, user=OTHER)
            self.assertIn(t("uz", "au_rule_gone"), self.shown(q), data)
        self.assertEqual(len(self.fake.rows), 1)
        self.assertTrue(self.fake.rows[0]["is_enabled"])

    def test_other_user_cannot_use_my_confirmation(self):
        yes = self._open_confirm()
        self.press(yes, user=OTHER)
        self.assertEqual(len(self.fake.rows), 1)

    def test_garbage_ids_do_not_crash(self):
        for data in ("au_view:abc", "au_view:", "au_on:99999999999999999999", "au_del:-5", "au_unknown"):
            self.press(data)  # xato bermasligi kerak


class PlansTests(PanelBase):
    def test_paid_plans_can_use_the_panel(self):
        for plan in ("plus", "pro", "ultra"):
            self.plan = plan
            q = self.press("au_menu")
            self.assertEqual(self.keyboard(q)[:2], ["au_add", "au_list"], plan)

    def test_free_plan_is_fully_closed(self):
        """Bepul tarif: hech bir au_* tugma ishlamaydi, qulflangan ko'rinish chiqadi, hech narsa yozilmaydi."""
        self.plan = "free"
        locked = t("uz", "locked_feature", feature=t("uz", "feature_automation"),
                   plans=" / ".join(t("uz", "plan_name_" + p) for p in ("plus", "pro", "ultra")))
        for data in ("au_menu", "au_add", "au_list", "au_view:1", "au_on:1", "au_off:1", "au_del:1",
                     "au_del_yes:1:abc123", "au_save:abc123", "au_cancel:abc123"):
            q = self.press(data)
            self.assertEqual(self.shown(q), locked, data)
        self.assertIsNone(bot.get_pending_action(USER))
        self.assertIsNone(bot._au_draft(USER))
        self.assertEqual(self.fake.add_calls, [])
        self.assertEqual(self.fake.rows, [])

    def test_downgraded_user_typing_is_stopped(self):
        """Tarifi pasayib ketgan foydalanuvchining yozayotgan matni qoida yaratmaydi."""
        self.press("au_add")
        self.plan = "free"
        reply = self.say("narx*")
        self.assertIsNone(bot.get_pending_action(USER))
        self.assertEqual(self.fake.rows, [])
        self.assertNotEqual(reply.await_args.args[0], t("uz", "au_ans_prompt", max=au.MAX_REPLY_LENGTH))

    def test_downgrade_keeps_rules_but_they_stop_working(self):
        self.create()
        self.plan = "free"
        with patch.object(db, "get_enabled_automation_rules", return_value=self.fake.rows):
            self.assertIsNone(bot.find_automation_rule(USER, "narxi qancha"))
        self.assertEqual(len(self.fake.rows), 1)  # qoidalar o'chmaydi — Plus'ga qaytsa yana ishlaydi
        self.plan = "plus"
        with patch.object(db, "get_enabled_automation_rules", return_value=self.fake.rows):
            self.assertIsNotNone(bot.find_automation_rule(USER, "narxi qancha"))

    def test_restricted_deployment_locks_even_paid(self):
        with patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS, automation=("ultra",))):
            q = self.press("au_menu")
            self.assertNotEqual(self.keyboard(q)[:2], ["au_add", "au_list"])


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan")
class DbEnabledFlagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_enabled_flag_is_respected(self):
        owner = random.randint(10**12, 9 * 10**12)
        self.addCleanup(self._drop, owner)
        cond = {"operator": "all", "items": [{"type": "keyword_contains", "value": "narx*"}]}
        act = {"type": "send_reply", "text": "x"}
        off = db.add_automation_rule(owner, "a", cond, act, 100, 20)
        on = db.add_automation_rule(owner, "b", cond, act, 100, 20, enabled=True)
        self.assertEqual([r["id"] for r in db.get_enabled_automation_rules(owner)], [on])
        self.assertNotEqual(off, on)

    @staticmethod
    def _drop(owner):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM automation_rules WHERE owner_user_id = %s", (owner,))


if __name__ == "__main__":
    unittest.main()
