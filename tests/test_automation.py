"""Automation Engine v1: moslik, tekshiruv, baza (egalar ajratilgan, limit, parallel), tarif cheklovi va mijoz oqimi."""
import asyncio
import os
import random
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import ai  # noqa: E402
import automation as au  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402

OWNER, ADMIN, CHAT = 1, 777, 99
run = asyncio.run
REPLY = "Salom! Telefon narxlari haqida ma'lumot beraman."


def R(keyword="narx*", text=REPLY, id_=1, priority=100, enabled=True, name="Narx haqida"):
    return {"id": id_, "name": name, "priority": priority, "is_enabled": enabled,
            "conditions": {"operator": "all", "items": [{"type": "keyword_contains", "value": keyword}]},
            "action": {"type": "send_reply", "text": text}}


class MatchTests(unittest.TestCase):
    def test_goal_example_matches_with_star(self):
        self.assertTrue(au.matches_keyword("Salom! Telefon narxi qancha?", "narx*"))

    def test_exact_word_matches(self):
        self.assertTrue(au.matches_keyword("Salom, narx qancha?", "narx"))

    def test_upper_case_matches(self):
        self.assertTrue(au.matches_keyword("NARX QANCHA", "narx"))
        self.assertTrue(au.matches_keyword("narx qancha", "NARX"))

    def test_no_keyword_no_match(self):
        self.assertFalse(au.matches_keyword("Salom, qalaysiz?", "narx*"))

    def test_keyword_inside_other_word_never_matches(self):
        self.assertFalse(au.matches_keyword("Unarxon degan joy bor", "narx"))
        self.assertFalse(au.matches_keyword("Unarxon degan joy bor", "narx*"))

    def test_without_star_suffix_form_does_not_match(self):
        self.assertFalse(au.matches_keyword("Telefon narxi qancha?", "narx"))

    def test_star_matches_suffixes(self):
        for word in ("narx", "narxi", "narxlar", "narxini"):
            self.assertTrue(au.matches_keyword(f"bu {word} qancha", "narx*"), word)

    def test_apostrophes_normalized(self):
        self.assertTrue(au.matches_keyword("O‘zbekistonga yetkazasizmi", "o'zbekistonga"))

    def test_phrase_needs_consecutive_words(self):
        self.assertTrue(au.matches_keyword("Menga narx qancha ekanini ayting", "narx qancha"))
        self.assertFalse(au.matches_keyword("narx haqida, qancha vaqt", "narx qancha"))

    def test_negation_is_ambiguous(self):
        self.assertFalse(au.matches_keyword("narx emas, dostavka kerak", "narx"))

    def test_empty_or_bad_inputs(self):
        self.assertFalse(au.matches_keyword(None, "narx"))
        self.assertFalse(au.matches_keyword("", "narx"))
        self.assertFalse(au.matches_keyword("narx", ""))
        self.assertFalse(au.matches_keyword("narx", None))


class FindTests(unittest.TestCase):
    def test_returns_match(self):
        self.assertEqual(au.find_matching_automation("narx qancha", [R("narx")])["id"], 1)

    def test_none_when_no_match(self):
        self.assertIsNone(au.find_matching_automation("salom", [R("narx")]))
        self.assertIsNone(au.find_matching_automation("narx", []))
        self.assertIsNone(au.find_matching_automation("narx", None))

    def test_disabled_rule_ignored(self):
        self.assertIsNone(au.find_matching_automation("narx", [R("narx", enabled=False)]))

    def test_first_by_priority_then_id(self):
        rules = [R("narx", id_=9, priority=10), R("narx", id_=3, priority=100), R("narx", id_=5, priority=100)]
        self.assertEqual(au.find_matching_automation("narx", rules)["id"], 9)  # eng kichik priority
        self.assertEqual(au.find_matching_automation("narx", list(reversed(rules)))["id"], 9)
        rules = [R("narx", id_=3), R("narx", id_=5)]
        self.assertEqual(au.find_matching_automation("narx", rules)["id"], 3)  # teng priority — kichik id
        self.assertEqual(au.find_matching_automation("narx", list(reversed(rules)))["id"], 3)

    def test_broken_rows_are_skipped_not_fatal(self):
        broken = [{"id": 1}, {"id": 2, "conditions": None, "action": {}}, R("narx", id_=3, text=""),
                  {"id": 4, "is_enabled": True, "conditions": {"operator": "any", "items": []}, "action": {"type": "send_reply", "text": "x"}},
                  R("narx", id_=5, text="OK")]
        self.assertEqual(au.find_matching_automation("narx", broken)["id"], 5)


class ValidateTests(unittest.TestCase):
    def ok(self, **kw):
        args = dict(name="Narx", conditions={"operator": "all", "items": [{"type": "keyword_contains", "value": "narx*"}]},
                    action={"type": "send_reply", "text": "Salom"}, priority=100)
        args.update(kw)
        return au.validate_automation(**args)

    def bad(self, **kw):
        with self.assertRaises(au.AutomationError):
            self.ok(**kw)

    def test_valid_rule(self):
        self.assertEqual(self.ok()["action"]["text"], "Salom")

    def test_empty_keyword_rejected(self):
        for v in ("", "   ", "*", "!!!", None, 5):
            self.bad(conditions={"operator": "all", "items": [{"type": "keyword_contains", "value": v}]})

    def test_reply_limit_500(self):
        self.ok(action={"type": "send_reply", "text": "a" * 500})
        self.bad(action={"type": "send_reply", "text": "a" * 501})
        self.bad(action={"type": "send_reply", "text": "  "})

    def test_only_allowed_types(self):
        self.bad(conditions={"operator": "all", "items": [{"type": "time_between", "value": "narx"}]})
        self.bad(action={"type": "send_ai", "text": "x"})
        self.bad(conditions={"operator": "any", "items": [{"type": "keyword_contains", "value": "narx"}]})

    def test_structure_strict(self):
        self.bad(conditions=None)
        self.bad(conditions={"operator": "all", "items": []})
        two = [{"type": "keyword_contains", "value": "a1"}, {"type": "keyword_contains", "value": "b1"}]
        self.bad(conditions={"operator": "all", "items": two})
        self.bad(conditions={"operator": "all", "items": [{"type": "keyword_contains", "value": "narx", "x": 1}]})
        self.bad(action={"type": "send_reply", "text": "x", "extra": 1})
        self.bad(action=None)

    def test_star_rules(self):
        self.bad(conditions={"operator": "all", "items": [{"type": "keyword_contains", "value": "na*rx"}]})
        self.bad(conditions={"operator": "all", "items": [{"type": "keyword_contains", "value": "a*"}]})  # juda qisqa prefiks

    def test_name_and_priority(self):
        self.bad(name="")
        self.bad(name="x" * 61)
        self.bad(priority=True)
        self.bad(priority=-1)
        self.bad(priority="5")


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan")
class DbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.a = random.randint(10**12, 9 * 10**12)
        self.b = self.a + 1
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM automation_rules WHERE owner_user_id = ANY(%s)", ([self.a, self.b],))

    def add(self, owner, kw="narx*", reply=REPLY, limit=20):
        return db.add_automation_rule(owner, "Narx", {"operator": "all", "items": [{"type": "keyword_contains", "value": kw}]},
                                      {"type": "send_reply", "text": reply}, 100, limit)

    def test_new_rule_is_disabled_and_roundtrips(self):
        rid = self.add(self.a, reply="Salom! O‘zbekiston — narxlar")
        rule = db.list_automation_rules(self.a)[0]
        self.assertEqual(rule["id"], rid)
        self.assertFalse(rule["is_enabled"])
        self.assertEqual(rule["action"]["text"], "Salom! O‘zbekiston — narxlar")
        self.assertEqual(db.get_enabled_automation_rules(self.a), [])

    def test_enable_is_idempotent_and_listed(self):
        rid = self.add(self.a)
        self.assertTrue(db.set_automation_rule_enabled(self.a, rid, True))
        self.assertTrue(db.set_automation_rule_enabled(self.a, rid, True))
        self.assertEqual([r["id"] for r in db.get_enabled_automation_rules(self.a)], [rid])
        self.assertTrue(db.set_automation_rule_enabled(self.a, rid, False))
        self.assertEqual(db.get_enabled_automation_rules(self.a), [])

    def test_other_owner_cannot_touch_or_read(self):
        rid = self.add(self.a)
        self.assertEqual(db.list_automation_rules(self.b), [])
        self.assertFalse(db.set_automation_rule_enabled(self.b, rid, True))
        self.assertFalse(db.delete_automation_rule(self.b, rid))
        self.assertEqual(len(db.list_automation_rules(self.a)), 1)
        self.assertFalse(db.list_automation_rules(self.a)[0]["is_enabled"])
        self.assertTrue(db.delete_automation_rule(self.a, rid))
        self.assertEqual(db.count_automation_rules(self.a), 0)

    def test_limit(self):
        self.assertIsNotNone(self.add(self.a, limit=1))
        self.assertIsNone(self.add(self.a, limit=1))
        self.assertIsNotNone(self.add(self.b, limit=1))  # boshqa egaga ta'sir qilmaydi

    def test_limit_holds_under_parallel_requests(self):
        for round_no in range(5):  # poyga kamdan-kam ushlanadi — bir necha marta takrorlaymiz
            owner = self.a + 100 + round_no
            self.addCleanup(lambda o=owner: self._drop(o))
            results, barrier = [], threading.Barrier(10)

            def worker():
                barrier.wait()
                results.append(self.add(owner, limit=3))

            threads = [threading.Thread(target=worker) for _ in range(10)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            self.assertEqual(db.count_automation_rules(owner), 3, f"round {round_no}")
            self.assertEqual(sum(r is not None for r in results), 3)

    def test_add_waits_for_the_owners_advisory_lock(self):
        """Deterministik: egasining lock'i band bo'lsa, qo'shish kutadi (lock olib tashlansa — poyga ochiladi)."""
        import time as _time
        done = []
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("BEGIN")
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('automation_rules'), (%s %% 2147483647)::int)", (self.a,))
            worker = threading.Thread(target=lambda: done.append(self.add(self.a, limit=3)))
            worker.start()
            _time.sleep(0.5)
            self.assertTrue(worker.is_alive(), "qo'shish lock'ni kutmadi")
            self.assertEqual(done, [])
            cur.execute("COMMIT")
        worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(done), 1)
        self.assertEqual(db.count_automation_rules(self.a), 1)

    @staticmethod
    def _drop(owner):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM automation_rules WHERE owner_user_id = %s", (owner,))

    def test_invalid_rule_never_reaches_database(self):
        with self.assertRaises(au.AutomationError):
            db.add_automation_rule(self.a, "x", {"operator": "all", "items": []}, {"type": "send_reply", "text": "x"}, 100, 20)
        self.assertEqual(db.count_automation_rules(self.a), 0)


def _settings(**kw):
    base = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
            "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "", "faq_enabled": True,
            "ai_enabled": False, "ai_info": None, "ai_role": None}
    base.update(kw)
    return base


class FlowTests(unittest.TestCase):
    """Mijoz xabari -> javob: tartib (Sleep -> Jadval -> Automation -> FAQ -> AI -> oddiy), tarif, cooldown."""

    def setUp(self):
        for p in (patch.object(bot, "ADMIN_ID", ADMIN),
                  patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS))):  # haqiqiy tarif cheklovlari
            p.start()
            self.addCleanup(p.stop)
        bot._bot_sent_ids.clear()

    def flow(self, text="Salom! Telefon narxi qancha?", settings=None, rules=None, plan="plus", paused=False,
             claim=123.0, schedule=None, faq_answer=None, ai_ready=False, rules_error=False, owner=OWNER):
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
        patches = {
            "conn": patch.object(db, "get_connection_by_business_id", return_value={"owner_user_id": owner, "is_enabled": True, "can_reply": True}),
            "settings": patch.object(db, "get_settings", return_value=settings or _settings()),
            "claim": patch.object(db, "try_claim_reply", return_value=claim),
            "release": patch.object(db, "release_reply_claim"),
            "paused": patch.object(db, "is_ai_paused", return_value=paused),
            "plan": patch.object(db, "get_user_plan", return_value=plan),
            "ads": patch.object(bot, "shows_ads", return_value=False),
            "rules": patch.object(db, "get_enabled_automation_rules", side_effect=RuntimeError("db") if rules_error else None,
                                  return_value=[R()] if rules is None else rules),
            "faq": patch.object(bot, "find_faq_answer", return_value=faq_answer),
            "conf": patch.object(ai, "is_configured", return_value=ai_ready),
            "gen": patch.object(ai, "generate_reply", new=AsyncMock(return_value="AI javobi")),
            "quota": patch.object(db, "try_consume_ai_quota", return_value=True),
            "user": patch.object(db, "get_user", return_value={"full_name": "Ali"}),
            "hist": patch.object(db, "get_ai_history", return_value=[]),
            "add": patch.object(db, "add_ai_messages"),
            "sub": patch.object(bot, "is_subscribed_cached", new=AsyncMock(return_value=True)),
        }
        if schedule is not None:
            patches["sched"] = patch.object(bot, "reply_state", return_value=(False, schedule))
            patches["sched_text"] = patch.object(bot, "schedule_text_for", return_value="Jadval matni")
        m = {k: p.start() for k, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

        async def go():
            await bot.on_raw_update(u, ctx)
            await asyncio.gather(*list(bot._background_tasks))

        run(go())
        return [c.kwargs["text"] for c in ctx.bot.send_message.call_args_list], m

    def test_goal_scenario(self):
        texts, m = self.flow()
        self.assertEqual(texts, [REPLY])
        m["claim"].assert_called_once()

    def test_no_match_falls_back_to_static(self):
        texts, _ = self.flow(text="Salom, qalaysiz?")
        self.assertEqual(texts, ["Oflaynman"])

    def test_disabled_rule_not_used(self):
        texts, _ = self.flow(rules=[R(enabled=False)])
        self.assertEqual(texts, ["Oflaynman"])

    def test_first_of_several_rules_only(self):
        texts, _ = self.flow(rules=[R(text="Ikkinchi", id_=2), R(text="Birinchi", id_=1)])
        self.assertEqual(texts, ["Birinchi"])

    def test_online_owner_gets_nothing(self):
        texts, m = self.flow(settings=_settings(offline=False))
        self.assertEqual(texts, [])
        m["rules"].assert_not_called()

    def test_sleep_mode_beats_automation(self):
        with patch.object(bot, "is_within_sleep_window", return_value=True):
            texts, m = self.flow(settings=_settings(sleep_mode_enabled=True, sleep_reply_text="Uxlayapman"))
        self.assertEqual(texts, ["Uxlayapman"])
        m["rules"].assert_not_called()

    def test_schedule_beats_automation(self):
        texts, m = self.flow(schedule={"id": 1})
        self.assertEqual(texts, ["Jadval matni"])
        m["rules"].assert_not_called()

    def test_cooldown_active_means_no_repeat(self):
        texts, _ = self.flow(claim=None)
        self.assertEqual(texts, [])

    def test_other_owners_rules_are_never_read(self):
        _, m = self.flow(owner=555)
        m["rules"].assert_called_once_with(555)

    def test_open_for_every_plan_including_free(self):
        for plan in ("free", "plus", "pro", "ultra"):
            texts, _ = self.flow(plan=plan)
            self.assertEqual(texts, [REPLY], plan)

    def test_automation_beats_faq_and_ai(self):
        texts, m = self.flow(faq_answer="FAQ javobi", settings=_settings(ai_enabled=True), ai_ready=True)
        self.assertEqual(texts, [REPLY])
        m["gen"].assert_not_awaited()

    def test_ai_pause_respected(self):
        texts, _ = self.flow(settings=_settings(ai_enabled=True), ai_ready=True, paused=True)
        self.assertEqual(texts, [])

    def test_non_text_message_skips_automation(self):
        texts, m = self.flow(text=None)
        self.assertEqual(texts, ["Oflaynman"])
        m["rules"].assert_not_called()

    def test_negation_falls_through(self):
        texts, _ = self.flow(text="narxi emas, dostavka kerak")
        self.assertEqual(texts, ["Oflaynman"])

    def test_database_error_falls_back_to_static(self):
        texts, _ = self.flow(rules_error=True)
        self.assertEqual(texts, ["Oflaynman"])

    def test_faq_still_works_without_rule_match(self):
        texts, _ = self.flow(text="dostavka bormi", faq_answer="FAQ javobi")
        self.assertEqual(texts, ["FAQ javobi"])


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan")
class ConcurrentMessagesTests(unittest.TestCase):
    """Bir vaqtda kelgan ikki xabar: haqiqiy cooldown (Postgres) tufayli faqat BITTA javob ketadi."""

    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_two_simultaneous_messages_send_one_reply(self):
        owner = random.randint(10**12, 9 * 10**12)
        chat = random.randint(10**9, 9 * 10**9)

        def update(mid):
            u = MagicMock()
            u.channel_post = None
            u.business_connection = None
            bm = MagicMock()
            bm.business_connection_id = "bc"
            bm.from_user.id = 5
            bm.from_user.is_bot = False
            bm.chat.id = chat
            bm.message_id = mid
            bm.text = "Telefon narxi qancha?"
            bm.caption = None
            u.business_message = bm
            return u

        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=555))
        patches = [
            patch.object(bot, "ADMIN_ID", ADMIN),
            patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)),
            patch.object(db, "get_connection_by_business_id", return_value={"owner_user_id": owner, "is_enabled": True, "can_reply": True}),
            patch.object(db, "get_settings", return_value=_settings()),
            patch.object(db, "get_user_plan", return_value="pro"),
            patch.object(bot, "shows_ads", return_value=False),
            patch.object(db, "get_enabled_automation_rules", return_value=[R()]),
            patch.object(bot, "is_subscribed_cached", new=AsyncMock(return_value=True)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._cleanup, owner, chat)

        async def go():
            await asyncio.gather(bot.on_raw_update(update(1), ctx), bot.on_raw_update(update(2), ctx))

        run(go())
        self.assertEqual(ctx.bot.send_message.await_count, 1)
        self.assertEqual(ctx.bot.send_message.await_args.kwargs["text"], REPLY)

    @staticmethod
    def _cleanup(owner, chat):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM replied_cache WHERE owner_user_id = %s", (owner,))


class CommandTests(unittest.TestCase):
    def call(self, text, uid=ADMIN, **dbmocks):
        msg = MagicMock()
        msg.text = text
        msg.reply_text = AsyncMock()
        upd = MagicMock()
        upd.effective_user.id = uid
        upd.message = msg
        with patch.object(bot, "ADMIN_ID", ADMIN):
            patches = [patch.object(db, k, **v) for k, v in dbmocks.items()]
            ms = {k: p.start() for k, p in zip(dbmocks, patches)}
            try:
                run(bot.cmd_automation(upd, MagicMock()))
            finally:
                for p in patches:
                    p.stop()
        return "\n".join(c.args[0] for c in msg.reply_text.await_args_list), ms

    def test_non_admin_ignored(self):
        text, ms = self.call("/automation add narx | x", uid=1, add_automation_rule={"return_value": 1})
        self.assertEqual(text, "")
        ms["add_automation_rule"].assert_not_called()

    def test_add_creates_disabled_rule_with_text_after_pipe(self):
        text, ms = self.call("/automation add narx* | Salom! | narxlar 100$", add_automation_rule={"return_value": 7})
        args = ms["add_automation_rule"].call_args.args
        self.assertEqual(args[0], ADMIN)
        self.assertEqual(args[2]["items"][0]["value"], "narx*")
        self.assertEqual(args[3]["text"], "Salom! | narxlar 100$")
        self.assertEqual(args[5], bot.AUTOMATION_RULE_LIMIT)
        self.assertIn("#7", text)

    def test_add_without_separator_shows_usage(self):
        text, ms = self.call("/automation add narx", add_automation_rule={"return_value": 1})
        self.assertIn("/automation add", text)
        ms["add_automation_rule"].assert_not_called()

    def test_add_invalid_and_limit_messages(self):
        text, _ = self.call("/automation add * | x", add_automation_rule={"side_effect": au.AutomationError("keyword_tokens")})
        self.assertIn("noto'g'ri", text)
        text, _ = self.call("/automation add narx | x", add_automation_rule={"return_value": None})
        self.assertIn("Limit", text)

    def test_on_off_del_use_own_owner_id(self):
        _, ms = self.call("/automation on 5", set_automation_rule_enabled={"return_value": True})
        ms["set_automation_rule_enabled"].assert_called_once_with(ADMIN, 5, True)
        _, ms = self.call("/automation off 5", set_automation_rule_enabled={"return_value": True})
        ms["set_automation_rule_enabled"].assert_called_once_with(ADMIN, 5, False)
        text, ms = self.call("/automation del 5", delete_automation_rule={"return_value": False})
        ms["delete_automation_rule"].assert_called_once_with(ADMIN, 5)
        self.assertIn("topilmadi", text)

    def test_bad_id_shows_usage(self):
        text, ms = self.call("/automation on abc", set_automation_rule_enabled={"return_value": True})
        ms["set_automation_rule_enabled"].assert_not_called()
        self.assertIn("/automation add", text)

    def test_list_survives_broken_rows(self):
        rows = [R(id_=1), {"id": 2, "is_enabled": False, "conditions": None, "action": None}]
        text, _ = self.call("/automation", list_automation_rules={"return_value": rows})
        self.assertIn("#1 [narx*]", text)
        self.assertIn("#2", text)

    def test_registered(self):
        self.assertIn('CommandHandler("automation", cmd_automation', Path(bot.__file__).read_text())


class FeatureGateTests(unittest.TestCase):
    def test_open_for_all_plans(self):
        self.assertEqual(bot.DEFAULT_FEATURE_PLANS["automation"], ("free", "plus", "pro", "ultra"))
        with patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)), patch.object(bot, "ADMIN_ID", ADMIN):
            for plan in ("free", "plus", "pro", "ultra"):
                self.assertTrue(bot.plan_allows(1, plan, "automation"), plan)
            self.assertFalse(bot.plan_allows(1, "free", "faq"))  # Smart FAQ Bepulda yopiq qoladi


if __name__ == "__main__":
    unittest.main()
