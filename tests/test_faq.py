"""Smart FAQ: moslik qoidalari, baza (egalar ajratilgan), boshqaruv paneli va mijozga javob berish tartibi."""
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

import ai  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402
import i18n  # noqa: E402
import logic  # noqa: E402

OWNER, OTHER, ADMIN, CHAT = 1, 2, 777, 99
run = asyncio.run
_REAL_FIND_FAQ_ANSWER = bot.find_faq_answer  # conftest uni o'chiradi; mijoz oqimi testlari qaytaradi


def E(q, kws, a="Javob", enabled=True, id_=1):
    return {"id": id_, "question": q, "keywords": kws, "answer": a, "is_enabled": enabled}


DELIVERY = E("Yetkazib berish bormi?", ["dostavka", "delivery", "yetkazish"], "Ha, O'zbekiston bo'ylab yetkazib beramiz.", id_=1)
PRICE = E("Narxi qancha?", ["narx", "narxi", "qancha"], "100$", id_=2)


class MatchTests(unittest.TestCase):
    def m(self, text, entries=(DELIVERY, PRICE)):
        r = logic.match_faq(text, list(entries))
        return r["id"] if r else None

    def test_spec_example(self):
        self.assertEqual(self.m("Toshkentga dostavka bormi?"), 1)

    def test_case_punctuation_apostrophes(self):
        self.assertEqual(self.m("DOSTAVKA!!!"), 1)
        self.assertEqual(self.m("  yetkazish, iltimos... "), 1)
        e = E("q", ["o'zbekiston", "узбекистан"], id_=5)
        self.assertEqual(self.m("O‘zbekiston bormi", [e]), 5)  # turli apostrof
        self.assertEqual(self.m("ozbekiston bormi", [e]), 5)  # apostrofsiz yozilgan
        self.assertEqual(self.m("в Узбекистан есть?", [e]), 5)

    def test_whole_words_only(self):
        self.assertIsNone(self.m("dostavkachi kerak"))
        self.assertIsNone(self.m("predelivery stuff"))

    def test_phrase_keywords(self):
        e = E("q", ["yetkazib berish"], id_=3)
        self.assertEqual(self.m("yetkazib berish narxi", [e]), 3)
        self.assertIsNone(self.m("berish yetkazib", [e]))  # tartib muhim
        self.assertIsNone(self.m("yetkazib", [e]))

    def test_negation_is_ambiguous(self):
        self.assertIsNone(self.m("Yetkazib berish yo'qmi?"))
        self.assertIsNone(self.m("Dostavka yoq"))
        self.assertIsNone(self.m("delivery not available?"))
        self.assertIsNone(self.m("Доставки нет?"))

    def test_tie_between_entries_falls_back(self):
        a, b = E("a", ["salom"], id_=7), E("b", ["salom"], id_=8)
        self.assertIsNone(self.m("salom", [a, b]))

    def test_stronger_match_wins(self):
        self.assertEqual(self.m("dostavka narxi qancha"), 2)  # narx tomoni ko'proq so'z

    def test_exact_question_wins(self):
        a = E("narx qancha", ["narx"], id_=1)
        b = E("narx qancha", ["narx", "qancha", "puli"], id_=2)
        self.assertIsNone(self.m("narx qancha", [a, b]))  # ikkalasi aniq — tenglik
        c = E("narx qancha bo'ladi", ["narx"], id_=3)
        self.assertEqual(self.m("narx qancha boladi", [c, b]), 3)

    def test_disabled_and_empty_ignored(self):
        self.assertIsNone(self.m("dostavka", [E("q", ["dostavka"], enabled=False)]))
        self.assertIsNone(self.m("", [DELIVERY]))
        self.assertIsNone(self.m(None, [DELIVERY]))
        self.assertIsNone(self.m("dostavka", []))

    def test_too_long_message_falls_back(self):
        self.assertIsNone(self.m("dostavka " + "so'z " * 70))

    def test_parse_keywords(self):
        self.assertEqual(logic.parse_faq_keywords("Dostavka, DELIVERY ,yetkazish\ndostavka"), ["dostavka", "delivery", "yetkazish"])
        self.assertEqual(logic.parse_faq_keywords("o'zbekiston; Yetkazib  berish"), ["ozbekiston", "yetkazib berish"])
        self.assertIsNone(logic.parse_faq_keywords(""))
        self.assertIsNone(logic.parse_faq_keywords(" , ,, !!! "))
        self.assertIsNone(logic.parse_faq_keywords(",".join(f"w{i}" for i in range(logic.FAQ_MAX_KEYWORDS + 1))))
        self.assertIsNone(logic.parse_faq_keywords("x" * (logic.FAQ_MAX_KEYWORD_LENGTH + 1)))


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class FaqDbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        db.init_db()  # idempotent

    def setUp(self):
        self.a = random.randint(10**14, 10**15)
        self.b = self.a + 1
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM faq_entries WHERE owner_user_id IN (%s, %s)", (self.a, self.b))
            cur.execute("DELETE FROM settings WHERE owner_user_id IN (%s, %s)", (self.a, self.b))

    def test_add_list_get_roundtrip(self):
        i = db.add_faq_entry(self.a, "Savol?", ["bir", "ikki uch"], "Javob", 20)
        rows = db.list_faq_entries(self.a)
        self.assertEqual([r["id"] for r in rows], [i])
        self.assertEqual(rows[0]["keywords"], ["bir", "ikki uch"])
        self.assertTrue(rows[0]["is_enabled"])
        self.assertEqual(db.get_faq_entry(self.a, i)["answer"], "Javob")
        self.assertEqual(db.count_faq_entries(self.a), 1)

    def test_limit_is_enforced(self):
        ids = [db.add_faq_entry(self.a, f"q{n}", ["k"], "a", 3) for n in range(5)]
        self.assertEqual([x is not None for x in ids], [True, True, True, False, False])
        self.assertEqual(db.count_faq_entries(self.a), 3)

    def test_owners_are_isolated(self):
        i = db.add_faq_entry(self.a, "Savol?", ["k"], "A", 20)
        self.assertEqual(db.list_faq_entries(self.b), [])
        self.assertEqual(db.get_enabled_faq_entries(self.b), [])
        self.assertIsNone(db.get_faq_entry(self.b, i))
        self.assertFalse(db.delete_faq_entry(self.b, i))
        self.assertIsNone(db.toggle_faq_entry(self.b, i))
        self.assertEqual(db.count_faq_entries(self.a), 1)  # egasi o'zgarmadi

    def test_toggle_and_delete(self):
        i = db.add_faq_entry(self.a, "Savol?", ["k"], "A", 20)
        self.assertFalse(db.toggle_faq_entry(self.a, i))
        self.assertEqual(db.get_enabled_faq_entries(self.a), [])
        self.assertTrue(db.toggle_faq_entry(self.a, i))
        self.assertEqual(len(db.get_enabled_faq_entries(self.a)), 1)
        self.assertTrue(db.delete_faq_entry(self.a, i))
        self.assertFalse(db.delete_faq_entry(self.a, i))

    def test_faq_enabled_setting_defaults_true(self):
        self.assertTrue(db.get_settings(self.a)["faq_enabled"])
        db.update_settings(self.a, faq_enabled=False)
        self.assertFalse(db.get_settings(self.a)["faq_enabled"])

    def test_special_characters_are_stored_safely(self):
        i = db.add_faq_entry(self.a, "'; DROP TABLE faq_entries; --", ["x"], "<b>\"q\"</b>", 20)
        self.assertEqual(db.get_faq_entry(self.a, i)["answer"], "<b>\"q\"</b>")


class FakeFaqDb:
    """Egalar bo'yicha ajratilgan xotiradagi soxta FAQ bazasi (boshqaruv oqimi testlari uchun)."""

    def __init__(self):
        self.rows = []
        self.next = 1

    def add(self, owner, q, kw, a, mx):
        if sum(r["owner_user_id"] == owner for r in self.rows) >= mx:
            return None
        self.rows.append({"id": self.next, "owner_user_id": owner, "question": q, "keywords": kw, "answer": a, "is_enabled": True})
        self.next += 1
        return self.next - 1

    def mine(self, owner):
        return [r for r in self.rows if r["owner_user_id"] == owner]

    def get(self, owner, i):
        return next((r for r in self.mine(owner) if r["id"] == i), None)

    def delete(self, owner, i):
        r = self.get(owner, i)
        if r:
            self.rows.remove(r)
        return bool(r)

    def toggle(self, owner, i):
        r = self.get(owner, i)
        if r:
            r["is_enabled"] = not r["is_enabled"]
        return r["is_enabled"] if r else None

    def install(self, test):
        for name, fn in (
            ("add_faq_entry", self.add), ("list_faq_entries", self.mine), ("get_faq_entry", self.get),
            ("delete_faq_entry", self.delete), ("toggle_faq_entry", self.toggle),
            ("count_faq_entries", lambda o: len(self.mine(o))),
            ("get_enabled_faq_entries", lambda o: [r for r in self.mine(o) if r["is_enabled"]]),
        ):
            p = patch.object(db, name, side_effect=fn)
            p.start()
            test.addCleanup(p.stop)


def _settings(**kw):
    base = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
            "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "", "faq_enabled": True,
            "ai_enabled": False, "ai_info": None, "ai_role": None}
    base.update(kw)
    return base


class PanelFlowTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeFaqDb()
        self.fake.install(self)
        for target, value in (("ADMIN_ID", ADMIN),):
            p = patch.object(bot, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(db, "get_settings", side_effect=lambda o: dict(_settings(), **self.settings_extra))
        self.settings_extra = {}
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(db, "update_settings", side_effect=lambda o, **kw: self.settings_extra.update(kw))
        p.start()
        self.addCleanup(p.stop)
        bot._faq_drafts.clear()
        bot.pending_settings_action.clear()
        self.addCleanup(bot.pending_settings_action.clear)
        p = patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS))  # haqiqiy tarif cheklovlari
        p.start()
        self.addCleanup(p.stop)
        self.plan_name = "ultra"
        p = patch.object(db, "get_user_plan", side_effect=lambda o: self.plan_name)
        p.start()
        self.addCleanup(p.stop)

    def press(self, data, user=OWNER):
        q = MagicMock()
        q.data = data
        q.from_user.id = user
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        u = MagicMock()
        u.callback_query = q
        with patch.object(bot, "track_user"):
            run(bot.on_button(u, MagicMock()))
        return q

    def say(self, text, user=OWNER):
        u = MagicMock()
        u.effective_user = MagicMock(id=user, is_bot=False)
        u.message.text = text
        u.message.reply_text = AsyncMock()
        with patch.object(bot, "track_user"):
            run(bot.on_text(u, MagicMock()))
        return u.message.reply_text

    def add_entry(self, q="Yetkazib berish bormi?", kw="dostavka, delivery", a="Ha.", user=OWNER):
        self.press("faq_add", user)
        self.say(q, user)
        self.say(kw, user)
        self.say(a, user)
        return self.press("faq_save", user)

    def test_panel_has_faq_button_and_menu_shows_counter(self):
        _, markup = bot.build_panel(OWNER)
        self.assertIn("faq_menu", [b.callback_data for r in markup.inline_keyboard for b in r])
        q = self.press("faq_menu")
        text = q.edit_message_text.call_args.args[0]
        self.assertIn("0/65", text)
        datas = [b.callback_data for r in q.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard for b in r]
        self.assertEqual(datas, ["faq_add", "faq_list", "faq_settings", "open_panel"])

    def test_three_steps_then_confirmation_then_save(self):
        self.press("faq_add")
        self.assertEqual(bot.get_pending_action(OWNER), "faq_q")
        r = self.say("Yetkazib berish bormi?")
        self.assertEqual(bot.get_pending_action(OWNER), "faq_kw")
        self.assertIn("Kalit", r.call_args.args[0])
        r = self.say("Dostavka, delivery, yetkazish")
        self.assertEqual(bot.get_pending_action(OWNER), "faq_ans")
        r = self.say("Ha, O'zbekiston bo'ylab.")
        self.assertEqual(bot.get_pending_action(OWNER), "faq_confirm")
        confirm = r.call_args.args[0]
        for part in ("Yetkazib berish bormi?", "dostavka, delivery, yetkazish", "Ha, O'zbekiston bo'ylab."):
            self.assertIn(part, confirm)
        datas = [b.callback_data for row in r.call_args.kwargs["reply_markup"].inline_keyboard for b in row]
        self.assertEqual(datas, ["faq_save", "faq_cancel"])
        self.assertEqual(self.fake.mine(OWNER), [])  # tasdiqlashdan oldin saqlanmaydi
        q = self.press("faq_save")
        self.assertEqual(len(self.fake.mine(OWNER)), 1)
        self.assertEqual(self.fake.mine(OWNER)[0]["keywords"], ["dostavka", "delivery", "yetkazish"])
        self.assertIn("saqlandi", q.edit_message_text.call_args.args[0])
        self.assertIn("1/65", q.edit_message_text.call_args.args[0])
        self.assertIsNone(bot.get_pending_action(OWNER))

    def test_cancel_discards_draft(self):
        self.press("faq_add")
        self.say("Savol?")
        self.say("kalit")
        self.say("Javob")
        self.press("faq_cancel")
        self.assertEqual(self.fake.mine(OWNER), [])
        q = self.press("faq_save")  # qoralama yo'q
        self.assertEqual(self.fake.mine(OWNER), [])
        self.assertIn("Qoralama", q.edit_message_text.call_args.args[0])

    def test_validation_keeps_step(self):
        self.press("faq_add")
        r = self.say("x" * (logic.FAQ_MAX_QUESTION + 1))
        self.assertEqual(bot.get_pending_action(OWNER), "faq_q")
        self.assertIn("uzun", r.call_args.args[0])
        self.say("Savol?")
        r = self.say(" , !!! ")
        self.assertEqual(bot.get_pending_action(OWNER), "faq_kw")
        self.assertIn("noto'g'ri", r.call_args.args[0])
        self.say("kalit")
        r = self.say("y" * (logic.FAQ_MAX_ANSWER + 1))
        self.assertEqual(bot.get_pending_action(OWNER), "faq_ans")
        self.assertIn("uzun", r.call_args.args[0])

    def test_typing_during_confirmation_does_not_change_draft(self):
        self.press("faq_add")
        self.say("Savol?")
        self.say("kalit")
        self.say("Javob")
        r = self.say("boshqa narsa")
        self.assertIn("tugma", r.call_args.args[0])
        self.assertEqual(bot.get_pending_action(OWNER), "faq_confirm")
        self.press("faq_save")
        self.assertEqual(self.fake.mine(OWNER)[0]["answer"], "Javob")

    def test_expired_draft(self):
        self.press("faq_add")
        self.say("Savol?")
        bot._faq_drafts[OWNER]["ts"] -= bot.PENDING_ACTION_TTL_SECONDS + 5
        r = self.say("kalit")
        self.assertIn("Qoralama", r.call_args.args[0])
        self.assertIsNone(bot.get_pending_action(OWNER))

    def test_limit_per_plan_blocks_adding(self):
        for plan, limit in (("plus", 15), ("pro", 30), ("ultra", 65)):
            self.plan_name = plan
            self.fake.rows.clear()
            for n in range(limit):
                self.fake.add(OWNER, f"q{n}", ["k"], "a", 999)
            q = self.press("faq_add")
            text = q.edit_message_text.call_args.args[0]
            self.assertIn("limiti", text, plan)
            self.assertIn(f"{limit}/{limit}", text, plan)
            self.assertIsNone(bot.get_pending_action(OWNER))
            self.fake.rows.pop()  # bitta joy bo'shadi
            q = self.press("faq_add")
            self.assertEqual(bot.get_pending_action(OWNER), "faq_q", plan)
            bot.clear_pending_action(OWNER)

    def test_limit_reached_during_save_is_safe(self):
        self.plan_name = "plus"
        self.press("faq_add")
        self.say("Savol?")
        self.say("kalit")
        self.say("Javob")
        for n in range(15):
            self.fake.add(OWNER, f"q{n}", ["k"], "a", 999)
        q = self.press("faq_save")
        self.assertEqual(len(self.fake.mine(OWNER)), 15)
        self.assertIn("limiti", q.edit_message_text.call_args.args[0])

    def test_free_plan_is_locked_everywhere(self):
        self.plan_name = "free"
        _, markup = bot.build_panel(OWNER)
        label = next(b.text for r in markup.inline_keyboard for b in r if b.callback_data == "faq_menu")
        self.assertTrue(label.startswith("\U0001F512"))
        for data in ("faq_menu", "faq_add", "faq_list", "faq_settings", "faq_toggle", "faq_save", "faq_view:1", "faq_del:1"):
            q = self.press(data)
            self.assertIn("Plus / Pro / Ultra", q.edit_message_text.call_args.args[0], data)
        self.assertEqual(self.fake.rows, [])
        self.assertNotIn("faq_enabled", self.settings_extra)
        self.assertIsNone(bot.get_pending_action(OWNER))

    def test_free_cannot_continue_a_started_draft(self):
        self.press("faq_add")
        self.say("Savol?")
        self.plan_name = "free"  # tarif muddati tugadi
        r = self.say("kalit")
        self.assertIn("Plus / Pro / Ultra", r.call_args.args[0])
        self.assertIsNone(bot.get_pending_action(OWNER))
        self.assertEqual(self.fake.rows, [])

    def test_free_cannot_save_even_with_old_confirm_button(self):
        self.press("faq_add")
        self.say("Savol?")
        self.say("kalit")
        self.say("Javob")
        self.plan_name = "free"
        self.press("faq_save")
        self.assertEqual(self.fake.rows, [])

    def test_admin_gets_top_limit(self):
        self.plan_name = "free"
        self.assertEqual(bot.faq_limit_for(ADMIN), 65)
        self.assertEqual([bot.faq_limit_for(OWNER, p) for p in ("free", "plus", "pro", "ultra")], [0, 15, 30, 65])

    def test_list_view_toggle_delete(self):
        self.add_entry()
        q = self.press("faq_list")
        labels = [b.text for r in q.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard for b in r]
        self.assertIn("Yetkazib berish bormi?", labels[0])
        entry_id = self.fake.mine(OWNER)[0]["id"]
        q = self.press(f"faq_view:{entry_id}")
        self.assertIn("dostavka, delivery", q.edit_message_text.call_args.args[0])
        self.press(f"faq_entry_toggle:{entry_id}")
        self.assertFalse(self.fake.mine(OWNER)[0]["is_enabled"])
        q = self.press("faq_list")
        self.assertTrue([b.text for r in q.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard for b in r][0].startswith("⏸"))
        q = self.press(f"faq_del:{entry_id}")
        self.assertEqual(self.fake.mine(OWNER), [])
        self.assertIn("o'chirildi", q.edit_message_text.call_args.args[0])

    def test_other_owner_cannot_see_or_change_entry(self):
        self.add_entry()
        entry_id = self.fake.mine(OWNER)[0]["id"]
        q = self.press(f"faq_view:{entry_id}", user=OTHER)
        self.assertNotIn("dostavka", q.edit_message_text.call_args.args[0])
        self.press(f"faq_entry_toggle:{entry_id}", user=OTHER)
        self.press(f"faq_del:{entry_id}", user=OTHER)
        self.assertEqual(len(self.fake.mine(OWNER)), 1)
        self.assertTrue(self.fake.mine(OWNER)[0]["is_enabled"])

    def test_bad_ids_do_not_crash(self):
        for data in ("faq_view:abc", "faq_del:", "faq_entry_toggle:-5", "faq_view:999999"):
            self.press(data)

    def test_settings_toggle(self):
        q = self.press("faq_settings")
        self.assertIn("Yoqilgan", q.edit_message_text.call_args.args[0])
        self.press("faq_toggle")
        self.assertEqual(self.settings_extra["faq_enabled"], False)

    def test_all_screens_in_three_languages(self):
        self.add_entry()
        for lang in i18n.LANGS:
            with patch.object(bot, "get_lang", return_value=lang):
                for text, markup in (bot.build_faq_menu(OWNER, "x"), bot.build_faq_settings(OWNER), bot.build_faq_list(OWNER),
                                     bot.build_faq_entry(OWNER, self.fake.mine(OWNER)[0]["id"])):
                    self.assertNotIn("{", text)
                    self.assertTrue(all(b.text for r in markup.inline_keyboard for b in r))


class ReplyOrderTests(unittest.TestCase):
    def setUp(self):
        self.entries = [DELIVERY, PRICE]
        for target, value in (("ADMIN_ID", ADMIN),):
            p = patch.object(bot, target, value)
            p.start()
            self.addCleanup(p.stop)
        bot._bot_sent_ids.clear()
        p = patch.object(bot, "find_faq_answer", _REAL_FIND_FAQ_ANSWER)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS))  # haqiqiy tarif cheklovlari
        p.start()
        self.addCleanup(p.stop)

    def flow(self, text="Toshkentga dostavka bormi?", settings=None, entries=None, faq_error=False, ai_ready=False,
             paused=False, owner=OWNER, ads=False, claim=123.0, plan="ultra"):
        settings = settings or _settings()
        u = MagicMock()
        u.channel_post = None
        u.business_connection = None
        bm = MagicMock()
        bm.business_connection_id = "bc"
        bm.from_user.id = 5
        bm.from_user.is_bot = False
        bm.chat.id = CHAT
        bm.message_id = 10
        bm.text = text
        bm.caption = None
        u.business_message = bm
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=555))
        conn = {"owner_user_id": owner, "is_enabled": True, "can_reply": True}
        faq = patch.object(db, "get_enabled_faq_entries", side_effect=RuntimeError("db down") if faq_error else None,
                           return_value=self.entries if entries is None else entries)
        patches = {
            "conn": patch.object(db, "get_connection_by_business_id", return_value=conn),
            "settings": patch.object(db, "get_settings", return_value=settings),
            "claim": patch.object(db, "try_claim_reply", return_value=claim),
            "release": patch.object(db, "release_reply_claim"),
            "paused": patch.object(db, "is_ai_paused", return_value=paused),
            "quota": patch.object(db, "try_consume_ai_quota", return_value=True),
            "refund": patch.object(db, "refund_ai_quota"),
            "hist": patch.object(db, "get_ai_history", return_value=[]),
            "add": patch.object(db, "add_ai_messages"),
            "user": patch.object(db, "get_user", return_value={"full_name": "Ali"}),
            "conf": patch.object(ai, "is_configured", return_value=ai_ready),
            "gen": patch.object(ai, "generate_reply", new=AsyncMock(return_value="AI javobi")),
            "ai_feature": patch.object(bot, "has_feature", return_value=True),
            "plan": patch.object(db, "get_user_plan", return_value=plan),
            "ads": patch.object(bot, "shows_ads", return_value=ads),
            "faq": faq,
        }
        m = {k: p.start() for k, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

        async def go():
            await bot.on_raw_update(u, ctx)
            await asyncio.gather(*list(bot._background_tasks))

        run(go())
        return [c.kwargs["text"] for c in ctx.bot.send_message.call_args_list], m

    def test_offline_match_sends_faq_answer_with_cooldown(self):
        texts, m = self.flow()
        self.assertEqual(texts, [DELIVERY["answer"]])
        m["claim"].assert_called_once()  # mavjud cooldown mexanizmi ishladi

    def test_cooldown_active_means_no_faq_answer(self):
        texts, _ = self.flow(claim=None)
        self.assertEqual(texts, [])

    def test_no_match_falls_back_to_static(self):
        texts, _ = self.flow(text="Salom, qalaysiz?")
        self.assertEqual(texts, ["Oflaynman"])

    def test_ambiguous_falls_back_to_static(self):
        a, b = E("a", ["salom"], id_=7), E("b", ["salom"], id_=8)
        texts, _ = self.flow(text="salom", entries=[a, b])
        self.assertEqual(texts, ["Oflaynman"])

    def test_negation_falls_back_to_static(self):
        texts, _ = self.flow(text="Yetkazib berish yo'qmi? dostavka")
        self.assertEqual(texts, ["Oflaynman"])

    def test_online_owner_gets_nothing(self):
        texts, m = self.flow(settings=_settings(offline=False))
        self.assertEqual(texts, [])
        m["faq"].assert_not_called()

    def test_sleep_mode_beats_faq(self):
        with patch.object(bot, "is_within_sleep_window", return_value=True):
            texts, m = self.flow(settings=_settings(sleep_mode_enabled=True, sleep_reply_text="Uxlayapman"))
        self.assertEqual(texts, ["Uxlayapman"])
        m["faq"].assert_not_called()

    def test_faq_switched_off_uses_static(self):
        texts, m = self.flow(settings=_settings(faq_enabled=False))
        self.assertEqual(texts, ["Oflaynman"])
        m["faq"].assert_not_called()

    def test_faq_missing_flag_defaults_to_on(self):
        s = _settings()
        del s["faq_enabled"]
        texts, _ = self.flow(settings=s)
        self.assertEqual(texts, [DELIVERY["answer"]])

    def test_database_error_falls_back_to_static(self):
        texts, _ = self.flow(faq_error=True)
        self.assertEqual(texts, ["Oflaynman"])

    def test_non_text_message_uses_static(self):
        texts, m = self.flow(text=None)
        self.assertEqual(texts, ["Oflaynman"])
        m["faq"].assert_not_called()

    def test_faq_answer_beats_ai_and_skips_cooldown_and_quota(self):
        texts, m = self.flow(settings=_settings(ai_enabled=True), ai_ready=True)
        self.assertEqual(texts, [DELIVERY["answer"]])
        m["gen"].assert_not_awaited()
        m["quota"].assert_not_called()  # FAQ uchun AI limiti sarflanmaydi
        m["claim"].assert_not_called()

    def test_ai_still_answers_when_no_faq_match(self):
        texts, m = self.flow(text="Menga maslahat bering", settings=_settings(ai_enabled=True), ai_ready=True)
        self.assertEqual(texts, ["AI javobi"])

    def test_paused_chat_gets_no_faq_when_ai_on(self):
        texts, _ = self.flow(settings=_settings(ai_enabled=True), ai_ready=True, paused=True)
        self.assertEqual(texts, [])

    def test_free_plan_gets_no_faq_answer(self):
        texts, m = self.flow(plan="free")
        self.assertEqual(texts, ["Oflaynman"])
        m["faq"].assert_not_called()

    def test_downgraded_plan_uses_only_first_entries_within_limit(self):
        many = [E(f"q{n}", [f"kalit{n}"], f"javob{n}", id_=n) for n in range(1, 41)]
        texts, _ = self.flow(text="kalit3", entries=many, plan="plus")  # 15 ichida
        self.assertEqual(texts, ["javob3"])
        texts, _ = self.flow(text="kalit20", entries=many, plan="plus")  # 15 dan keyin — ishlamaydi
        self.assertEqual(texts, ["Oflaynman"])
        texts, _ = self.flow(text="kalit20", entries=many, plan="pro")
        self.assertEqual(texts, ["javob20"])
        texts, _ = self.flow(text="kalit40", entries=many, plan="ultra")
        self.assertEqual(texts, ["javob40"])
        texts, _ = self.flow(text="kalit31", entries=many, plan="pro")
        self.assertEqual(texts, ["Oflaynman"])

    def test_free_plan_ad_is_appended_to_faq_answer(self):
        texts, _ = self.flow(ads=True)
        self.assertEqual(len(texts), 1)
        self.assertTrue(texts[0].startswith(DELIVERY["answer"] + "\n\n"))
        self.assertIn("@autoreplyer_dbot", texts[0])


if __name__ == "__main__":
    unittest.main()
