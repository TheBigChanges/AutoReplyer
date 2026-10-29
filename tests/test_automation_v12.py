"""Automation Engine v1.2: YOKI (keyword_any), qoidani tahrirlash, qoida statistikasi, `automation` analitika turi."""
import asyncio
import os
import random
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import analytics  # noqa: E402
import automation as au  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402
from i18n import t  # noqa: E402
from telegram.error import TelegramError  # noqa: E402
from test_automation import OWNER, REPLY, R, FlowTests, _FixedNow, _settings, SR  # noqa: E402
from test_automation_panel import ADMIN, OTHER, USER, PanelBase  # noqa: E402

run = asyncio.run
UTC = timezone.utc


def OR(keywords=("narx*", "qancha", "price"), days=None, time=None, text="Javob", id_=1, enabled=True, priority=100):
    return {"id": id_, "name": "n", "priority": priority, "is_enabled": enabled,
            "conditions": au.build_conditions(list(keywords), days, time), "action": {"type": "send_reply", "text": text}}


# --------------------------------------------------------------------------- toza modul
class OrMatchTests(unittest.TestCase):
    def test_any_of_three_keywords_matches(self):
        rule = OR()
        for msg in ("Telefon narxi qancha?", "bu qancha turadi", "what is the price", "narxlar"):
            self.assertTrue(au.rule_matches(msg, rule), msg)

    def test_none_matches(self):
        self.assertFalse(au.rule_matches("salom, qalaysiz", OR()))
        self.assertFalse(au.rule_matches("", OR()))
        self.assertFalse(au.rule_matches(None, OR()))

    def test_prefix_and_whole_word_rules_hold_inside_or(self):
        rule = OR(("narx*", "price"))
        self.assertTrue(au.rule_matches("narxlar", rule))
        self.assertFalse(au.rule_matches("unarxon", rule))
        self.assertFalse(au.rule_matches("priceless", rule))  # butun so'z

    def test_negation_blocks_or(self):
        self.assertFalse(au.rule_matches("narxi emas", OR()))

    def test_or_with_days_and_time(self):
        rule = OR(days=[0, 1, 2, 3, 4], time=(540, 1080))
        self.assertTrue(au.rule_matches("qancha", rule, when=(0, 600)))
        self.assertFalse(au.rule_matches("qancha", rule, when=(0, 1200)))   # vaqt mos emas
        self.assertFalse(au.rule_matches("qancha", rule, when=(5, 600)))    # kun mos emas
        self.assertFalse(au.rule_matches("salom", rule, when=(0, 600)))     # kalit so'z mos emas
        self.assertFalse(au.rule_matches("qancha", rule, when=None))        # vaqt noma'lum -> xavfsiz

    def test_allow_smart_false_stops_or_rule(self):
        self.assertFalse(au.rule_matches("qancha", OR(), allow_smart=False))
        self.assertTrue(au.rule_matches("narx", R("narx"), allow_smart=False))  # v1.0/v1.1 bitta kalit so'z — doim

    def test_old_v10_and_v11_rules_unchanged(self):
        self.assertTrue(au.rule_matches("narxi qancha", R("narx*")))
        self.assertTrue(au.rule_matches("narxi", SR(days=[0], time=(0, 1000)), when=(0, 10)))

    def test_matches_any_keyword_edge_cases(self):
        self.assertFalse(au.matches_any_keyword("narx", []))
        self.assertFalse(au.matches_any_keyword("narx", "narx"))  # ro'yxat emas
        self.assertFalse(au.matches_any_keyword("narx", ["***"]))  # buzuq kalit so'z mos emas
        self.assertTrue(au.matches_any_keyword("narx", ["***", "narx"]))

    def test_find_matching_prefers_priority_then_id(self):
        rules = [OR(text="B", id_=2, priority=100), OR(text="A", id_=1, priority=200), R("narx", text="C", id_=3, priority=50)]
        self.assertEqual(au.find_matching_automation("narx", rules)["action"]["text"], "C")

    def test_rule_with_both_keyword_kinds_or_none_never_matches(self):
        both = {"id": 1, "name": "n", "priority": 1, "is_enabled": True, "action": {"type": "send_reply", "text": "x"},
                "conditions": {"operator": "all", "items": [{"type": "keyword_contains", "value": "narx"},
                                                            {"type": "keyword_any", "value": ["a1b", "c2d"]}]}}
        self.assertFalse(au.rule_matches("narx a1b", both))
        none = dict(both, conditions={"operator": "all", "items": [{"type": "days_of_week", "value": [0]}]})
        self.assertFalse(au.rule_matches("narx", none, when=(0, 1)))

    def test_split_keywords_and_smart_flag(self):
        self.assertEqual(au.split_keywords(OR(("a1b", "c2d"))), ["a1b", "c2d"])
        self.assertEqual(au.split_keywords(R("narx")), ["narx"])
        self.assertEqual(au.split_keywords({"conditions": 5}), [])
        self.assertTrue(au.has_smart_conditions(OR()))
        self.assertFalse(au.has_smart_conditions(R("narx")))
        self.assertTrue(au.has_smart_conditions(SR(days=[1])))


class OrValidateTests(unittest.TestCase):
    def v(self, cond, name="n"):
        return au.validate_automation(name, cond, {"type": "send_reply", "text": "x"})

    def cond(self, *items):
        return {"operator": "all", "items": list(items)}

    def test_valid_or_roundtrips_in_canonical_order(self):
        clean = self.v(self.cond({"type": "time_between", "value": {"start": 540, "end": 1080}},
                                 {"type": "keyword_any", "value": ["narx*", " qancha ", "price"]}))
        self.assertEqual([i["type"] for i in clean["conditions"]["items"]], ["keyword_any", "time_between"])
        self.assertEqual(clean["conditions"]["items"][0]["value"], ["narx*", "qancha", "price"])

    def test_count_limits(self):
        for bad in ([], ["narx"], ["a1b", "c2d", "e3f", "g4h", "i5j", "k6l"], "narx", None, {"a": 1}):
            with self.assertRaises(au.AutomationError, msg=str(bad)):
                self.v(self.cond({"type": "keyword_any", "value": bad}))
        self.v(self.cond({"type": "keyword_any", "value": ["a1b", "c2d", "e3f", "g4h", "i5j"]}))  # 5 ta — mumkin

    def test_duplicates_rejected_after_normalisation(self):
        for dup in (["narx", "narx"], ["Narx", "narx"], ["narx*", "NARX*"], ["narx qancha", "narx  qancha"]):
            with self.assertRaises(au.AutomationError, msg=str(dup)):
                self.v(self.cond({"type": "keyword_any", "value": dup}))
        self.v(self.cond({"type": "keyword_any", "value": ["narx", "narx*"]}))  # har xil moslik rejimi — takror emas

    def test_each_keyword_is_validated(self):
        for bad in (["narx", ""], ["narx", "a*"], ["narx", "x" * 60], ["narx", 5], ["narx", "a*b"], ["narx", "bir ikki uch to'rt besh olti"]):
            with self.assertRaises(au.AutomationError, msg=str(bad)):
                self.v(self.cond({"type": "keyword_any", "value": bad}))

    def test_cannot_mix_single_and_or_or_omit_keyword(self):
        with self.assertRaises(au.AutomationError):
            self.v(self.cond({"type": "keyword_contains", "value": "narx"}, {"type": "keyword_any", "value": ["a1b", "c2d"]}))
        with self.assertRaises(au.AutomationError):
            self.v(self.cond({"type": "days_of_week", "value": [1]}))
        with self.assertRaises(au.AutomationError):
            self.v(self.cond({"type": "keyword_any", "value": ["a1b", "c2d"]}, {"type": "keyword_any", "value": ["e3f", "g4h"]}))

    def test_or_plus_days_plus_time_is_three_items(self):
        clean = self.v(au.build_conditions(["narx*", "qancha", "price"], [0, 1, 2, 3, 4], (540, 1080)))
        self.assertEqual(len(clean["conditions"]["items"]), 3)

    def test_build_conditions_single_item_list_is_plain_keyword(self):
        self.assertEqual(au.build_conditions(["narx"])["items"], [{"type": "keyword_contains", "value": "narx"}])
        self.assertEqual(au.build_conditions("narx")["items"], [{"type": "keyword_contains", "value": "narx"}])
        self.assertEqual(au.build_conditions(["a1b", "c2d"])["items"][0]["type"], "keyword_any")


# --------------------------------------------------------------------------- baza
@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL o'rnatilmagan")
class DbV12Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.a = random.randint(10**12, 9 * 10**12)
        self.b = self.a + 1
        self.addCleanup(lambda: [self._drop(o) for o in (self.a, self.b)])

    @staticmethod
    def _drop(owner):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM automation_rules WHERE owner_user_id = %s", (owner,))

    def add(self, owner, kw="narx*", days=None, time=None, reply="Javob", name="Qoida", prio=100):
        return db.add_automation_rule(owner, name, au.build_conditions(kw, days, time),
                                      {"type": "send_reply", "text": reply}, prio, 20, enabled=True)

    def get(self, owner, rid):
        return next(r for r in db.list_automation_rules(owner) if r["id"] == rid)

    def test_migration_is_idempotent_and_defaults(self):
        db.init_db()
        rid = self.add(self.a)
        rule = self.get(self.a, rid)
        self.assertEqual(rule["sent_count"], 0)
        self.assertIsNone(rule["last_sent_at"])

    def test_or_rule_roundtrips_jsonb(self):
        rid = self.add(self.a, ["narx*", "qancha", "price"], [0, 1], (540, 1080))
        rule = self.get(self.a, rid)
        self.assertEqual(au.split_keywords(rule), ["narx*", "qancha", "price"])
        self.assertTrue(au.rule_matches("price?", rule, when=(0, 600)))

    def test_update_changes_only_given_fields(self):
        rid = self.add(self.a, "narx*", [0, 1], (540, 1080), reply="Eski", name="Eski nom", prio=100)
        self.assertTrue(db.update_automation_rule(self.a, rid, reply="Yangi"))
        r = self.get(self.a, rid)
        self.assertEqual((r["action"]["text"], r["name"], r["priority"], r["is_enabled"]), ("Yangi", "Eski nom", 100, True))
        self.assertEqual(au.split_conditions(r), ("narx*", [0, 1], (540, 1080)))
        self.assertTrue(db.update_automation_rule(self.a, rid, keywords=["qancha", "price"]))
        r = self.get(self.a, rid)
        self.assertEqual(au.split_keywords(r), ["qancha", "price"])
        self.assertEqual(au.split_conditions(r)[1:], ([0, 1], (540, 1080)))   # kun/vaqt saqlanadi
        self.assertTrue(db.update_automation_rule(self.a, rid, days=None))
        self.assertIsNone(au.split_conditions(self.get(self.a, rid))[1])
        self.assertTrue(db.update_automation_rule(self.a, rid, time_range=None, priority=7, name="Yangi nom"))
        r = self.get(self.a, rid)
        self.assertEqual((au.split_conditions(r)[2], r["priority"], r["name"]), (None, 7, "Yangi nom"))
        self.assertTrue(db.update_automation_rule(self.a, rid, keywords="bitta"))   # YOKI -> oddiy kalit so'z
        self.assertEqual(au.split_keywords(self.get(self.a, rid)), ["bitta"])

    def test_update_keeps_enabled_state_and_counter(self):
        rid = self.add(self.a)
        db.record_automation_sent(self.a, rid)
        db.set_automation_rule_enabled(self.a, rid, False)
        db.update_automation_rule(self.a, rid, name="Yangi")
        r = self.get(self.a, rid)
        self.assertFalse(r["is_enabled"])
        self.assertEqual(r["sent_count"], 1)

    def test_other_owner_cannot_edit(self):
        rid = self.add(self.a)
        self.assertFalse(db.update_automation_rule(self.b, rid, name="Hujum"))
        self.assertEqual(self.get(self.a, rid)["name"], "Qoida")
        self.assertFalse(db.update_automation_rule(self.a, rid + 99999, name="Yo'q"))

    def test_invalid_change_writes_nothing(self):
        rid = self.add(self.a, "narx*", reply="Asl")
        for bad in ({"keywords": ["a*"]}, {"keywords": ["narx", "narx"]}, {"keywords": []}, {"name": " "}, {"priority": -1},
                    {"priority": True}, {"reply": ""}, {"reply": "x" * 501}, {"time_range": (5, 5)}, {"days": [9]}):
            with self.assertRaises(au.AutomationError, msg=str(bad)):
                db.update_automation_rule(self.a, rid, **bad)
        r = self.get(self.a, rid)
        self.assertEqual((r["name"], r["action"]["text"], r["priority"]), ("Qoida", "Asl", 100))
        self.assertEqual(au.split_conditions(r), ("narx*", None, None))

    def test_unknown_or_empty_fields_rejected(self):
        rid = self.add(self.a)
        for bad in ({}, {"is_enabled": True}, {"sent_count": 5}, {"id": 5}):
            with self.assertRaises(ValueError):
                db.update_automation_rule(self.a, rid, **bad)

    def test_failed_edit_rolls_back_and_releases_lock(self):
        rid = self.add(self.a)
        with self.assertRaises(au.AutomationError):
            db.update_automation_rule(self.a, rid, name=" ")
        self.assertTrue(db.update_automation_rule(self.a, rid, name="Keyingi tahrir ishlaydi"))  # qator qulfda qolmadi

    def test_concurrent_edits_of_different_fields_both_survive(self):
        import threading
        rid = self.add(self.a, "narx*", reply="Asl", name="Asl nom")
        barrier = threading.Barrier(2)

        def w(**kw):
            barrier.wait()
            db.update_automation_rule(self.a, rid, **kw)

        ts = [threading.Thread(target=w, kwargs={"reply": "Yangi javob"}), threading.Thread(target=w, kwargs={"keywords": ["qancha", "price"]})]
        [x.start() for x in ts]
        [x.join() for x in ts]
        r = self.get(self.a, rid)
        self.assertEqual(r["action"]["text"], "Yangi javob")
        self.assertEqual(au.split_keywords(r), ["qancha", "price"])

    def test_record_sent_increments_atomically_and_is_owner_scoped(self):
        import threading
        rid = self.add(self.a)
        self.assertFalse(db.record_automation_sent(self.b, rid))
        self.assertEqual(self.get(self.a, rid)["sent_count"], 0)
        ts = [threading.Thread(target=db.record_automation_sent, args=(self.a, rid)) for _ in range(8)]
        [x.start() for x in ts]
        [x.join() for x in ts]
        r = self.get(self.a, rid)
        self.assertEqual(r["sent_count"], 8)
        self.assertIsNotNone(r["last_sent_at"])
        self.assertFalse(db.record_automation_sent(self.a, rid + 99999))

    def test_deleting_rule_keeps_its_sent_count_in_history(self):
        a, b = self.add(self.a, name="Narxlar"), self.add(self.a, name="Ish")
        for _ in range(3):
            db.record_automation_sent(self.a, a)
        db.record_automation_sent(self.a, b)
        self.addCleanup(lambda: self._del_totals(self.a, self.b))
        self.assertEqual(db.get_automation_deleted_sent(self.a), 0)
        self.assertTrue(db.delete_automation_rule(self.a, a))
        self.assertEqual(db.get_automation_deleted_sent(self.a), 3)
        self.assertFalse(db.delete_automation_rule(self.a, a))            # ikkinchi o'chirish ikki marta qo'shmaydi
        self.assertEqual(db.get_automation_deleted_sent(self.a), 3)
        self.assertTrue(db.delete_automation_rule(self.a, b))
        self.assertEqual(db.get_automation_deleted_sent(self.a), 4)
        self.assertEqual(db.get_automation_deleted_sent(self.b), 0)       # boshqa egasiga tegmaydi

    def test_other_owner_delete_changes_nothing(self):
        rid = self.add(self.a)
        db.record_automation_sent(self.a, rid)
        self.addCleanup(lambda: self._del_totals(self.a, self.b))
        self.assertFalse(db.delete_automation_rule(self.b, rid))
        self.assertEqual(db.get_automation_deleted_sent(self.b), 0)
        self.assertEqual(db.get_automation_deleted_sent(self.a), 0)
        self.assertEqual(db.count_automation_rules(self.a), 1)

    def test_zero_sent_rule_delete_and_counters_since(self):
        rid = self.add(self.a)
        self.addCleanup(lambda: self._del_totals(self.a, self.b))
        self.assertTrue(db.delete_automation_rule(self.a, rid))
        self.assertEqual(db.get_automation_deleted_sent(self.a), 0)
        since = db.get_automation_counters_since()
        self.assertIsNotNone(since)
        db.init_db()                                                       # qayta migratsiya sanani o'zgartirmaydi
        self.assertEqual(db.get_automation_counters_since(), since)

    @staticmethod
    def _del_totals(*owners):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM automation_deleted_totals WHERE owner_user_id = ANY(%s)", (list(owners),))

    def test_reply_sent_just_before_rule_deleted_is_not_lost(self):
        """Poyga: javob yuborildi, sanagich fonda yoziladi, shu orada qoida o'chirildi -> hisob tarixiy jamga tushadi."""
        rid = self.add(self.a)
        self.addCleanup(lambda: self._del_totals(self.a, self.b))
        self.assertTrue(db.delete_automation_rule(self.a, rid))          # o'chirish oldin o'tdi
        bot._record_automation_sent_safe(self.a, rid)                    # kechikkan fon vazifasi
        self.assertEqual(db.get_automation_deleted_sent(self.a), 1)

    def test_no_double_count_when_rule_still_exists(self):
        rid = self.add(self.a)
        self.addCleanup(lambda: self._del_totals(self.a, self.b))
        bot._record_automation_sent_safe(self.a, rid)                    # oddiy holat: qoida bor
        self.assertEqual(db.get_automation_deleted_sent(self.a), 0)
        db.delete_automation_rule(self.a, rid)                           # keyin o'chirildi: 1 marta, ko'chirilgan
        self.assertEqual(db.get_automation_deleted_sent(self.a), 1)

    def test_parallel_send_and_delete_counts_exactly_once(self):
        import threading
        for round_no in range(10):
            rid = self.add(self.a)
            self.addCleanup(lambda: self._del_totals(self.a, self.b))
            before = db.get_automation_deleted_sent(self.a)
            barrier = threading.Barrier(2)

            def send():
                barrier.wait()
                bot._record_automation_sent_safe(self.a, rid)

            def delete():
                barrier.wait()
                db.delete_automation_rule(self.a, rid)

            ts = [threading.Thread(target=send), threading.Thread(target=delete)]
            [x.start() for x in ts]
            [x.join() for x in ts]
            self.assertEqual(db.get_automation_deleted_sent(self.a) - before, 1, f"round {round_no}")

    def test_analytics_automation_kind_roundtrips(self):
        owner = self.a
        self.addCleanup(lambda: self._del_an(owner))
        db.record_analytics(owner, "automation")
        db.record_analytics(owner, "automation", n=2)
        rows = db.get_analytics_rows(owner, 0)
        self.assertEqual(sum(c for _, k, c in rows if k == "automation"), 3)

    @staticmethod
    def _del_an(owner):
        with db.get_conn() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM analytics_hourly WHERE owner_user_id = %s", (owner,))


# --------------------------------------------------------------------------- xabar oqimi / tarif / statistika
class OrFlowTests(FlowTests):
    def run_flow(self, rules, text="Telefon narxi qancha?", plan="pro", **kw):
        with patch.object(bot, "track_analytics") as an, patch.object(db, "record_automation_sent") as sent:
            texts, m = self.flow(text=text, rules=rules, plan=plan, **kw)
        return texts, m, an, sent

    def test_or_rule_replies_for_each_keyword_and_counts(self):
        for msg in ("qancha turadi", "narxi nima", "price?"):
            texts, _, an, sent = self.run_flow([OR(text="OR javobi")], text=msg)
            self.assertEqual(texts, ["OR javobi"], msg)
            sent.assert_called_once_with(OWNER, 1)

    def test_no_keyword_no_reply_no_counter(self):
        texts, _, an, sent = self.run_flow([OR()], text="dostavka bormi")
        self.assertEqual(texts, ["Oflaynman"])  # oddiy avtojavob
        sent.assert_not_called()
        self.assertEqual([c.args[1] for c in an.call_args_list if c.args[1] != "incoming"], ["static"])

    def test_analytics_kind_is_automation_and_not_double_counted(self):
        texts, _, an, sent = self.run_flow([OR(text="OR javobi")], text="narxi")
        kinds = [c.args[1] for c in an.call_args_list if c.args[1] != "incoming"]
        self.assertEqual(kinds, ["automation"])   # na "static", na ikkinchi marta
        sent.assert_called_once()

    def test_plus_cannot_run_or_rule_but_plain_still_works(self):
        texts, _, _, sent = self.run_flow([OR(), R("narx", text="Oddiy", id_=2)], plan="plus", text="qancha narx")
        self.assertEqual(texts, ["Oddiy"])
        texts, _, _, sent = self.run_flow([OR()], plan="plus", text="qancha")
        self.assertEqual(texts, ["Oflaynman"])   # Pro -> Plus: eski YOKI qoida to'xtaydi (o'chmaydi)
        sent.assert_not_called()

    def test_pro_downgrade_pauses_or_rule_and_upgrade_resumes(self):
        rule = OR(text="OR javobi")
        self.assertEqual(self.run_flow([rule], plan="pro", text="qancha")[0], ["OR javobi"])
        self.assertEqual(self.run_flow([rule], plan="plus", text="qancha")[0], ["Oflaynman"])
        self.assertEqual(self.run_flow([rule], plan="ultra", text="qancha")[0], ["OR javobi"])
        self.assertEqual(self.run_flow([rule], plan="free", text="qancha")[0], ["Oflaynman"])

    def test_or_plus_days_time_in_flow(self):
        rule = OR(days=[0, 1, 2, 3, 4], time=(540, 1080), text="Ish vaqti")
        _FixedNow.fixed_utc = datetime(2026, 10, 26, 5, 0, tzinfo=UTC)   # Dushanba, Toshkent 10:00
        with patch.object(bot, "datetime", _FixedNow):
            self.assertEqual(self.run_flow([rule], text="price")[0], ["Ish vaqti"])
        _FixedNow.fixed_utc = datetime(2026, 10, 26, 15, 0, tzinfo=UTC)  # Toshkent 20:00
        with patch.object(bot, "datetime", _FixedNow):
            self.assertEqual(self.run_flow([rule], text="price")[0], ["Oflaynman"])

    def test_cooldown_blocks_second_reply_and_counter(self):
        texts, _, an, sent = self.run_flow([OR()], text="qancha", claim=None)
        self.assertEqual(texts, [])
        sent.assert_not_called()
        self.assertEqual([c.args[1] for c in an.call_args_list if c.args[1] != "incoming"], ["skipped"])

    def test_sleep_and_schedule_beat_or_rule(self):
        with patch.object(bot, "is_within_sleep_window", return_value=True):
            texts, m, _, sent = self.run_flow([OR()], text="qancha", settings=_settings(sleep_mode_enabled=True, sleep_reply_text="Uxlayapman"))
        self.assertEqual(texts, ["Uxlayapman"])
        sent.assert_not_called()
        texts, m, _, sent = self.run_flow([OR()], text="qancha", schedule={"id": 1})
        self.assertEqual(texts, ["Jadval matni"])
        sent.assert_not_called()

    def test_faq_and_ai_keep_priority_order(self):
        texts, m, _, _ = self.run_flow([OR(text="OR javobi")], text="qancha", faq_answer="FAQ", settings=_settings(ai_enabled=True), ai_ready=True)
        self.assertEqual(texts, ["OR javobi"])                 # Automation > FAQ > AI
        m["gen"].assert_not_awaited()
        texts, _, _, _ = self.run_flow([OR(text="OR javobi")], text="boshqa savol", faq_answer="FAQ")
        self.assertEqual(texts, ["FAQ"])


class SentCounterFallbackTests(unittest.TestCase):
    def test_missing_rule_falls_back_to_history_once(self):
        with patch.object(db, "record_automation_sent", return_value=False), patch.object(db, "add_automation_deleted_sent") as add:
            bot._record_automation_sent_safe(OWNER, 5)
        add.assert_called_once_with(OWNER, 1)

    def test_existing_rule_does_not_touch_history(self):
        with patch.object(db, "record_automation_sent", return_value=True), patch.object(db, "add_automation_deleted_sent") as add:
            bot._record_automation_sent_safe(OWNER, 5)
        add.assert_not_called()

    def test_db_error_is_swallowed(self):
        with patch.object(db, "record_automation_sent", side_effect=RuntimeError("db")):
            bot._record_automation_sent_safe(OWNER, 5)  # javob oqimini buzmaydi


class SendFailureTests(unittest.TestCase):
    def _send(self, bot_obj):
        bm = MagicMock()
        bm.business_connection_id = "bc"
        with patch.object(db, "try_claim_reply", return_value=1.0), patch.object(db, "release_reply_claim") as rel, \
                patch.object(bot, "shows_ads", return_value=False), \
                patch.object(bot, "track_analytics") as an, patch.object(db, "record_automation_sent") as sent:
            async def go():
                await bot.send_auto_reply(bot_obj, bm, OWNER, 5, "x", 3.0, "l", kind="automation", automation_rule_id=7)
                await asyncio.gather(*list(bot._background_tasks))
            run(go())
        return rel, an, sent

    def test_telegram_failure_counts_nothing_and_releases_claim(self):
        b = MagicMock()
        b.send_message = AsyncMock(side_effect=TelegramError("boom"))
        rel, an, sent = self._send(b)
        rel.assert_called_once()
        an.assert_not_called()
        sent.assert_not_called()

    def test_success_counts_once_each(self):
        b = MagicMock()
        b.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        rel, an, sent = self._send(b)
        rel.assert_not_called()
        an.assert_called_once_with(OWNER, "automation")
        sent.assert_called_once_with(OWNER, 7)

    def test_counter_error_does_not_break_reply_flow(self):
        b = MagicMock()
        b.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        with patch.object(db, "record_automation_sent", side_effect=RuntimeError("db")):
            bm = MagicMock()
            with patch.object(db, "try_claim_reply", return_value=1.0), patch.object(bot, "shows_ads", return_value=False), \
                    patch.object(bot, "track_analytics"):
                async def go():
                    await bot.send_auto_reply(b, bm, OWNER, 5, "x", 3.0, "l", kind="automation", automation_rule_id=7)
                    await asyncio.gather(*list(bot._background_tasks))
                run(go())
        b.send_message.assert_awaited_once()


class AnalyticsKindTests(unittest.TestCase):
    def test_summarize_counts_automation_in_sent_once(self):
        tz = bot.TASHKENT_TZ
        now = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
        bucket = int(now.timestamp() // 3600) * 3600
        rows = [(bucket, "incoming", 5), (bucket, "automation", 2), (bucket, "static", 1), (bucket, "faq", 1)]
        s = analytics.summarize(rows, 1, tz, now)
        self.assertEqual(s["kinds"]["automation"], 2)
        self.assertEqual(s["sent"], 4)             # 2 + 1 + 1: automation static'ga qo'shilmaydi
        self.assertEqual(s["kinds"]["static"], 1)
        self.assertIn("automation", analytics.SENT_KINDS)
        self.assertIn("automation", db.ANALYTICS_KINDS)

    def test_pie_chart_includes_automation_slice(self):
        tz = bot.TASHKENT_TZ
        now = datetime(2026, 10, 26, 8, 0, tzinfo=UTC)
        bucket = int(now.timestamp() // 3600) * 3600
        s = analytics.summarize([(bucket, "incoming", 3), (bucket, "automation", 3)], 1, tz, now)
        for lang in ("uz", "en", "ru"):
            png = analytics.render_pie_chart(s, bot.analytics_chart_labels(lang, "pie"))
            self.assertTrue(png.startswith(b"\x89PNG"))

    def test_menu_text_shows_automation_line_in_three_languages(self):
        for lang in ("uz", "en", "ru"):
            text = t(lang, "an_menu", period="x", incoming=1, sent=1, faq=0, ai=0, static=0, sleep=0, automation=7, peak="-")
            self.assertIn("Automation: 7", text)


# --------------------------------------------------------------------------- panel
class V12PanelBase(PanelBase):
    plan = "pro"

    def make(self, kws=("narx*", "qancha"), days=None, time=None, reply="Javob matni", name=None, prio=100, owner=USER, enabled=True, sent=0):
        rid = self.fake.next_id
        self.fake.rows.append({"id": rid, "owner_user_id": owner, "name": name or au.split_keywords({"conditions": au.build_conditions(list(kws))})[0],
                               "conditions": au.build_conditions(list(kws), days, time), "action": {"type": "send_reply", "text": reply},
                               "priority": prio, "is_enabled": enabled, "sent_count": sent, "last_sent_at": None})
        self.fake.next_id += 1
        return rid

    def setUp(self):
        super().setUp()

        def update(owner, rid, **changes):
            for r in self.fake.rows:
                if r["owner_user_id"] == owner and r["id"] == rid:
                    kws = au.split_keywords(r)
                    _, days, tr = au.split_conditions(r)
                    if "keywords" in changes:
                        kws = changes["keywords"] if not isinstance(changes["keywords"], str) else [changes["keywords"]]
                    if "days" in changes:
                        days = changes["days"] or None
                    if "time_range" in changes:
                        tr = changes["time_range"]
                    clean = au.validate_automation(changes.get("name", r["name"]), au.build_conditions(list(kws), days, tr),
                                                   {"type": "send_reply", "text": changes.get("reply", r["action"]["text"])},
                                                   changes.get("priority", r["priority"]))
                    r.update(name=clean["name"], conditions=clean["conditions"], action=clean["action"], priority=clean["priority"])
                    self.fake.update_calls.append((owner, rid, changes))
                    return True
            return False

        self.fake.update_calls = []
        self.deleted_totals = {}
        orig_delete = db.delete_automation_rule

        def delete(owner, rid):
            for r in self.fake.rows:
                if r["owner_user_id"] == owner and r["id"] == rid:
                    self.deleted_totals[owner] = self.deleted_totals.get(owner, 0) + (r.get("sent_count") or 0)
            return orig_delete(owner, rid)

        for name, fn in (("delete_automation_rule", delete),
                         ("get_automation_deleted_sent", lambda owner: self.deleted_totals.get(owner, 0)),
                         ("get_automation_counters_since", lambda: datetime(2026, 10, 29, tzinfo=UTC))):
            q = patch.object(db, name, side_effect=fn)
            q.start()
            self.addCleanup(q.stop)
        p = patch.object(db, "update_automation_rule", side_effect=update)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(db, "get_analytics_rows", return_value=[])
        p.start()
        self.addCleanup(p.stop)
        bot._au_edits.clear()

    def rule(self, rid):
        return next(r for r in self.fake.rows if r["id"] == rid)

    def edit(self, field, rid, user=USER):
        q = self.press(f"au_ef:{field}:{rid}", user)
        e = bot._au_edit(user)
        return q, e


class CreateOrFlowTests(V12PanelBase):
    def test_pro_creates_or_rule_with_commas(self):
        self.press("au_add")
        reply = self.say("narx*, qancha, price")
        d = bot._au_draft(USER)
        self.assertEqual(d["kws"], ["narx*", "qancha", "price"])
        self.assertEqual(d["stage"], "days")
        self.press(f"au_dskip:{d['id']}")
        self.press(f"au_tskip:{d['id']}")
        confirm = self.say("Salom!")
        self.assertIn("narx* YOKI qancha YOKI price", confirm.await_args.args[0])
        self.press(self.datas(confirm.await_args.kwargs["reply_markup"])[0])
        row = self.fake.rows[0]
        self.assertEqual(row["conditions"]["items"], [{"type": "keyword_any", "value": ["narx*", "qancha", "price"]}])
        self.assertEqual(row["name"], "narx* +2")
        self.assertTrue(row["is_enabled"])

    def test_prompt_mentions_or_for_pro_not_for_plus(self):
        q = self.press("au_add")
        self.assertIn("YOKI", q.message.reply_text.await_args.args[0])
        self.plan = "plus"
        bot._au_drafts.clear()
        q = self.press("au_add")
        self.assertNotIn("YOKI", q.message.reply_text.await_args.args[0])

    def test_bad_lists_keep_waiting(self):
        self.press("au_add")
        for bad, key in (("narx, narx", "au_kw_dup"), ("a1b, c2d, e3f, g4h, i5j, k6l", "au_kw_count"), ("narx, a*", "au_kw_bad")):
            reply = self.say(bad)
            self.assertIn(t("uz", key).split("{")[0][:12], reply.await_args.args[0], bad)
            self.assertEqual(bot.get_pending_action(USER), "au_kw")
            self.assertNotIn("kws", bot._au_draft(USER))

    def test_single_keyword_still_plain_rule(self):
        self.press("au_add")
        self.say("narx*")
        d = bot._au_draft(USER)
        self.press(f"au_dskip:{d['id']}")
        self.press(f"au_tskip:{d['id']}")
        confirm = self.say("Javob")
        self.press(self.datas(confirm.await_args.kwargs["reply_markup"])[0])
        self.assertEqual(self.fake.rows[0]["conditions"]["items"], [{"type": "keyword_contains", "value": "narx*"}])
        self.assertEqual(self.fake.rows[0]["name"], "narx*")

    def test_plus_user_is_blocked_from_or(self):
        self.plan = "plus"
        self.press("au_add")
        reply = self.say("narx, qancha")
        self.assertEqual(reply.await_args.args[0], t("uz", "au_or_locked"))
        self.assertEqual(bot.get_pending_action(USER), "au_kw")
        self.assertNotIn("kws", bot._au_draft(USER))
        self.say("narx")  # bitta kalit so'z — davom etadi
        self.assertEqual(bot._au_draft(USER)["stage"], "ans")

    def test_plan_dropped_before_save_blocks_or_save(self):
        self.press("au_add")
        self.say("narx, qancha")
        d = bot._au_draft(USER)
        self.press(f"au_dskip:{d['id']}")
        self.press(f"au_tskip:{d['id']}")
        confirm = self.say("Javob")
        self.plan = "plus"                      # yozish paytida tarif tushdi
        q = self.press(self.datas(confirm.await_args.kwargs["reply_markup"])[0])
        self.assertEqual(self.fake.rows, [])
        self.assertIn(t("uz", "feature_automation_conditions"), self.shown(q))


class EditFlowTests(V12PanelBase):
    def test_rule_view_has_edit_button_and_new_lines(self):
        rid = self.make(("narx*", "qancha", "price"), [0, 1, 2, 3, 4], (540, 1080), name="Narxlar", prio=50, sent=25)
        q = self.press(f"au_view:{rid}")
        text = self.shown(q)
        for part in ("Narxlar", "narx* YOKI qancha YOKI price", "09:00", "50", "25"):
            self.assertIn(part, text)
        self.assertIn(f"au_edit:{rid}", self.keyboard(q))

    def test_edit_menu_lists_all_fields(self):
        rid = self.make()
        q = self.press(f"au_edit:{rid}")
        data = self.keyboard(q)
        for f in ("name", "kw", "days", "time", "reply", "prio"):
            self.assertIn(f"au_ef:{f}:{rid}", data)

    def test_edit_name(self):
        rid = self.make()
        _, e = self.edit("name", rid)
        self.assertEqual(bot.get_pending_action(USER), "au_e_text")
        reply = self.say("Narxlar haqida")
        self.assertEqual(self.rule(rid)["name"], "Narxlar haqida")
        self.assertIn(t("uz", "au_updated"), reply.await_args.args[0])
        self.assertIsNone(bot._au_edit(USER))
        self.assertIsNone(bot.get_pending_action(USER))

    def test_edit_name_too_long_keeps_waiting(self):
        rid = self.make(name="Eski")
        self.edit("name", rid)
        self.say("x" * 61)
        self.assertEqual(self.rule(rid)["name"], "Eski")
        self.assertEqual(bot.get_pending_action(USER), "au_e_text")

    def test_edit_keywords_to_three_or_and_back_to_one(self):
        rid = self.make()
        self.edit("kw", rid)
        self.say("narx*, qancha, price")
        self.assertEqual(au.split_keywords(self.rule(rid)), ["narx*", "qancha", "price"])
        self.edit("kw", rid)
        self.say("bitta")
        self.assertEqual(self.rule(rid)["conditions"]["items"], [{"type": "keyword_contains", "value": "bitta"}])

    def test_edit_keywords_validation(self):
        rid = self.make(("narx*", "qancha"))
        self.edit("kw", rid)
        for bad in ("narx, narx", "a1b, c2d, e3f, g4h, i5j, k6l", "ab*"):
            self.say(bad)
            self.assertEqual(au.split_keywords(self.rule(rid)), ["narx*", "qancha"], bad)
            self.assertEqual(bot.get_pending_action(USER), "au_e_text")

    def test_plus_cannot_set_or_but_can_edit_single_keyword_name_reply_priority(self):
        self.plan = "plus"
        rid = self.make(("narx",))
        self.edit("kw", rid)
        reply = self.say("narx, qancha")
        self.assertEqual(reply.await_args.args[0], t("uz", "au_or_locked"))
        self.assertEqual(au.split_keywords(self.rule(rid)), ["narx"])
        self.say("narxi")
        self.assertEqual(au.split_keywords(self.rule(rid)), ["narxi"])
        for field, value, check in (("name", "Yangi", lambda r: r["name"] == "Yangi"), ("reply", "Yangi javob", lambda r: r["action"]["text"] == "Yangi javob"),
                                    ("prio", "5", lambda r: r["priority"] == 5)):
            self.edit(field, rid)
            self.say(value)
            self.assertTrue(check(self.rule(rid)), field)

    def test_edit_reply(self):
        rid = self.make()
        self.edit("reply", rid)
        self.say("z" * 501)
        self.assertEqual(self.rule(rid)["action"]["text"], "Javob matni")
        self.say("Yangi javob")
        self.assertEqual(self.rule(rid)["action"]["text"], "Yangi javob")

    def test_edit_priority_validation(self):
        rid = self.make()
        self.edit("prio", rid)
        for bad in ("abc", "-1", "10001", "1.5", "", "٣"):
            self.say(bad)
            self.assertEqual(self.rule(rid)["priority"], 100, bad)
        self.say("0")
        self.assertEqual(self.rule(rid)["priority"], 0)
        self.edit("prio", rid)
        self.say("10000")
        self.assertEqual(self.rule(rid)["priority"], 10000)

    def test_edit_time_set_and_clear(self):
        rid = self.make(time=(540, 1080))
        q, e = self.edit("time", rid)
        self.assertIn(f"au_eclear:{e['id']}", self.datas(q.message.reply_text.await_args.kwargs["reply_markup"]))
        for bad in ("abc", "09:00-09:00", "25:00-26:00", "00:00-24:00"):
            self.say(bad)
            self.assertEqual(au.split_conditions(self.rule(rid))[2], (540, 1080), bad)
        self.say("22:00-06:00")
        self.assertEqual(au.split_conditions(self.rule(rid))[2], (1320, 360))
        _, e = self.edit("time", rid)
        self.press(f"au_eclear:{e['id']}")
        self.assertIsNone(au.split_conditions(self.rule(rid))[2])

    def test_edit_days_toggle_done_and_clear(self):
        rid = self.make(days=[0, 1])
        q, e = self.edit("days", rid)
        self.assertEqual(e["days"], {0, 1})
        tok = e["id"]
        self.press(f"au_ed:2:{tok}")
        self.press(f"au_ed:0:{tok}")
        self.assertEqual(bot._au_edit(USER)["days"], {1, 2})
        self.press(f"au_edp:we:{tok}")
        self.assertEqual(bot._au_edit(USER)["days"], {5, 6})
        self.press(f"au_edone:{tok}")
        self.assertEqual(au.split_conditions(self.rule(rid))[1], [5, 6])
        _, e = self.edit("days", rid)
        self.press(f"au_eclear:{e['id']}")
        self.assertIsNone(au.split_conditions(self.rule(rid))[1])

    def test_done_without_days_asks_and_changes_nothing(self):
        rid = self.make(days=[1])
        _, e = self.edit("days", rid)
        self.press(f"au_ed:1:{e['id']}")
        q = self.press(f"au_edone:{e['id']}")
        self.assertIn(t("uz", "au_e_days_empty"), self.shown(q))
        self.assertEqual(au.split_conditions(self.rule(rid))[1], [1])
        self.assertIsNotNone(bot._au_edit(USER))

    def test_typing_after_day_buttons_gets_hint(self):
        rid = self.make()
        _, e = self.edit("days", rid)
        self.press(f"au_ed:1:{e['id']}")
        self.assertEqual(bot.get_pending_action(USER), "au_e_days")
        self.assertEqual(self.say("dushanba").await_args.args[0], t("uz", "au_days_hint"))

    def test_plus_cannot_edit_days_or_time(self):
        self.plan = "plus"
        rid = self.make(("narx",))
        for f in ("days", "time"):
            q = self.press(f"au_ef:{f}:{rid}")
            self.assertIn(t("uz", "feature_automation_conditions"), self.shown(q))
            self.assertIsNone(bot._au_edit(USER))

    def test_plan_dropped_during_time_edit_blocks_write(self):
        rid = self.make(time=(540, 1080))
        self.edit("time", rid)
        self.plan = "plus"
        reply = self.say("22:00-06:00")
        self.assertEqual(au.split_conditions(self.rule(rid))[2], (540, 1080))
        self.assertIn(t("uz", "feature_automation_conditions"), reply.await_args.args[0])
        self.assertIsNone(bot._au_edit(USER))
        self.assertIsNone(bot.get_pending_action(USER))

    def test_plan_dropped_during_days_edit_blocks_done(self):
        rid = self.make(days=[1])
        _, e = self.edit("days", rid)
        self.press(f"au_ed:2:{e['id']}")
        self.plan = "plus"
        q = self.press(f"au_edone:{e['id']}")
        self.assertEqual(au.split_conditions(self.rule(rid))[1], [1])
        self.assertIn(t("uz", "feature_automation_conditions"), self.shown(q))

    def test_free_after_plan_drop_cannot_finish_any_text_edit(self):
        """Tahrirlash paytida tarif Bepulga tushsa: nom/javob/ustuvorlik/kalit so'z yozilmaydi, sessiya bekor."""
        for field, value in (("name", "Yangi nom"), ("reply", "Yangi javob"), ("prio", "5"), ("kw", "yangi")):
            self.plan = "plus"
            bot._au_edits.clear()
            rid = self.make(("narx",), name="Asl", reply="Asl javob", prio=100)
            self.edit(field, rid)
            self.plan = "free"
            reply = self.say(value)
            r = self.rule(rid)
            self.assertEqual((r["name"], r["action"]["text"], r["priority"], au.split_keywords(r)), ("Asl", "Asl javob", 100, ["narx"]), field)
            self.assertIn(t("uz", "feature_automation"), reply.await_args.args[0], field)
            self.assertIsNone(bot._au_edit(USER), field)
            self.assertIsNone(bot.get_pending_action(USER), field)
        self.assertEqual(self.fake.update_calls, [])

    def test_free_after_plan_drop_cannot_use_day_buttons_or_hint_path(self):
        self.plan = "plus"
        self.plan = "pro"
        rid = self.make(("narx",), days=[1])
        _, e = self.edit("days", rid)
        self.plan = "free"
        self.say("dushanba")                                   # matnli yo'l ham yopiq
        self.assertIsNone(bot._au_edit(USER))
        q = self.press(f"au_edone:{e['id']}")
        self.assertEqual(au.split_conditions(self.rule(rid))[1], [1])
        self.assertEqual(self.fake.update_calls, [])

    def test_cannot_edit_someone_elses_rule(self):
        rid = self.make(owner=OTHER, name="Boshqaniki")
        q = self.press(f"au_edit:{rid}")
        self.assertIn(t("uz", "au_rule_gone"), self.shown(q))
        q = self.press(f"au_ef:name:{rid}")
        self.assertIsNone(bot._au_edit(USER))
        self.say("Hujum")
        self.assertEqual(self.rule(rid)["name"], "Boshqaniki")
        self.assertEqual(self.fake.update_calls, [])

    def test_forged_session_cannot_reach_other_owners_rule(self):
        rid = self.make(owner=OTHER, name="Boshqaniki")
        bot._au_edits[USER] = {"id": "abc123", "rule_id": rid, "field": "name", "ts": __import__("time").time(), "stage": "text", "days": set()}
        bot.set_pending_action(USER, "au_e_text")
        reply = self.say("Hujum")
        self.assertEqual(self.rule(rid)["name"], "Boshqaniki")    # db owner bo'yicha cheklaydi
        self.assertIn(t("uz", "au_rule_gone"), reply.await_args.args[0])

    def test_stale_buttons_change_nothing(self):
        rid = self.make(days=[1])
        _, e = self.edit("days", rid)
        old = e["id"]
        self.press(f"au_ecancel:{old}")                       # sessiya tugadi
        _, e2 = self.edit("days", rid)
        self.press(f"au_ed:3:{old}")                          # eski token
        self.press(f"au_edone:{old}")
        self.press(f"au_eclear:{old}")
        self.assertEqual(bot._au_edit(USER)["days"], {1})
        self.assertEqual(au.split_conditions(self.rule(rid))[1], [1])
        self.assertEqual(self.fake.update_calls, [])
        self.press(f"au_ecancel:{old}")                       # eski «Bekor» ham yangi sessiyani buzmaydi
        self.assertIsNotNone(bot._au_edit(USER))
        self.assertEqual(bot._au_edit(USER)["id"], e2["id"])

    def test_old_save_button_changes_nothing(self):
        """Eski «Saqlash» (qoralama) tugmasi tahrirlash paytida hech narsani o'zgartirmaydi."""
        rid = self.make(name="Asl")
        self.press("au_add")
        self.say("narx")
        old = bot._au_draft(USER)["id"]
        self.edit("name", rid)
        self.press(f"au_save:{old}")
        self.assertEqual(len(self.fake.rows), 1)
        self.assertEqual(self.rule(rid)["name"], "Asl")

    def test_stale_button_keeps_pending_text_input(self):
        rid = self.make(name="Asl")
        self.edit("name", rid)
        self.press("au_edone:zzzzzz")
        self.assertEqual(bot.get_pending_action(USER), "au_e_text")
        self.say("Yangi")
        self.assertEqual(self.rule(rid)["name"], "Yangi")

    def test_cancel_restores_rule_view_and_leaves_data(self):
        rid = self.make(name="Asl")
        _, e = self.edit("name", rid)
        q = self.press(f"au_ecancel:{e['id']}")
        self.assertIsNone(bot._au_edit(USER))
        self.assertIn("Asl", self.shown(q))
        self.assertIsNone(bot.get_pending_action(USER))

    def test_session_expires_after_ttl(self):
        rid = self.make(name="Asl")
        _, e = self.edit("name", rid)
        e["ts"] -= bot.PENDING_ACTION_TTL_SECONDS + 1
        reply = self.say("Yangi")
        self.assertEqual(reply.await_args.args[0], t("uz", "au_edit_lost"))
        self.assertEqual(self.rule(rid)["name"], "Asl")

    def test_rule_deleted_during_edit(self):
        rid = self.make()
        self.edit("name", rid)
        self.fake.rows.clear()
        reply = self.say("Yangi")
        self.assertIn(t("uz", "au_rule_gone"), reply.await_args.args[0])

    def test_cancel_command_and_menu_clear_edit_session(self):
        rid = self.make()
        self.edit("name", rid)
        self.assertTrue(bot.clear_flow_state(USER))
        self.assertIsNone(bot._au_edit(USER))
        self.edit("name", rid)
        self.press("au_menu")
        self.assertIsNone(bot._au_edit(USER))

    def test_edit_keeps_enabled_state_and_smart_conditions(self):
        rid = self.make(("narx*", "qancha"), [0, 1], (540, 1080), enabled=False)
        self.edit("reply", rid)
        self.say("Yangi")
        r = self.rule(rid)
        self.assertFalse(r["is_enabled"])
        self.assertEqual(au.split_conditions(r)[1:], ([0, 1], (540, 1080)))
        self.assertEqual(au.split_keywords(r), ["narx*", "qancha"])

    def test_downgraded_plus_user_can_still_clear_old_days_but_view_shows_lock(self):
        self.plan = "plus"
        rid = self.make(("narx",), [0, 1])
        q = self.press(f"au_view:{rid}")
        self.assertIn(t("uz", "au_rule_locked"), self.shown(q))

    def test_list_shows_rule_names(self):
        self.make(name="Narxlar")
        self.make(name="Ish vaqti", enabled=False)
        q = self.press("au_list")
        labels = [b.text for row in q.edit_message_text.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
        self.assertIn("Narxlar", labels)
        self.assertIn("⏸ Ish vaqti", labels)


class StatsTests(V12PanelBase):
    def test_stats_screen(self):
        self.make(name="Narxlar", sent=45)
        self.make(name="Ish vaqti", sent=26)
        self.make(name="Yetkazib berish", sent=15, enabled=False)
        self.make(name="Jim", sent=0)
        with patch.object(db, "get_analytics_rows") as rows:
            rows.return_value = []
            with patch.object(bot, "analytics_summary", return_value={"kinds": {"automation": 86}}):
                q = self.press("au_stats")
        text = self.shown(q)
        self.assertIn("4", text)            # jami
        self.assertIn("3", text)            # faol
        self.assertIn("86", text)           # davr bo'yicha
        self.assertIn("86", text)           # jami 45+26+15
        self.assertIn("1. Narxlar — 45", text)
        self.assertIn("2. Ish vaqti — 26", text)
        self.assertIn("3. Yetkazib berish — 15", text)
        self.assertNotIn("Jim —", text)
        self.assertIn(self.keyboard(q)[-1], ("au_menu",))

    def test_deleted_rules_stay_in_historical_total(self):
        a = self.make(name="Narxlar", sent=100)
        self.make(name="Ish vaqti", sent=50)
        self.make(name="Yetkazib berish", sent=30)
        with patch.object(bot, "analytics_summary", return_value={"kinds": {"automation": 0}}):
            self.assertIn("180", self.shown(self.press("au_stats")))
            self.press(f"au_del:{a}")
            confirm = bot._au_del_confirms[USER]
            self.press(f"au_del_yes:{a}:{confirm['token']}")
            text = self.shown(self.press("au_stats"))
        self.assertIn("180", text)                      # 100 yo'qolmadi
        self.assertNotIn("Narxlar", text)               # o'chirilgan qoida «eng ko'p» ro'yxatda emas
        self.assertIn("29.10.2026", text)               # hisob qaysi sanadan boshlangani ko'rsatiladi

    def test_stats_survive_missing_history_reads(self):
        self.make(sent=2)
        with patch.object(db, "get_automation_deleted_sent", side_effect=RuntimeError("db")):
            self.assertIn("2", self.shown(self.press("au_stats")))

    def test_stats_empty(self):
        q = self.press("au_stats")
        self.assertIn(t("uz", "au_stats_top_none"), self.shown(q))

    def test_stats_only_own_rules(self):
        self.make(name="Meniki", sent=3)
        self.make(name="Boshqaniki", sent=99, owner=OTHER)
        text = self.shown(self.press("au_stats"))
        self.assertIn("Meniki — 3", text)
        self.assertNotIn("Boshqaniki", text)
        self.assertNotIn("99", text)

    def test_stats_use_today_when_plan_has_no_7_day_analytics(self):
        self.plan = "plus"
        self.make(sent=1)
        with patch.object(bot, "analytics_allowed_days", return_value=1), \
                patch.object(bot, "analytics_summary", return_value={"kinds": {"automation": 4}}) as s:
            self.press("au_stats")
        self.assertEqual(s.call_args.args[1], 1)

    def test_stats_survives_analytics_error(self):
        self.make(sent=2)
        with patch.object(bot, "analytics_summary", side_effect=RuntimeError("db")):
            q = self.press("au_stats")
        self.assertIn("2", self.shown(q))

    def test_menu_has_stats_button_and_free_is_locked(self):
        self.assertIn("au_stats", self.keyboard(self.press("au_menu")))
        self.plan = "free"
        self.assertIn(t("uz", "feature_automation"), self.shown(self.press("au_stats")))

    def test_stats_text_in_three_languages(self):
        for lang in ("uz", "en", "ru"):
            text = t(lang, "au_stats", total=1, active=1, period="p", period_sent=2, all_sent=3, since="01.10.2026", top="1. x — 3")
            self.assertIn("1. x — 3", text)
        self.assertIn("Статистика", t("ru", "au_stats", total=1, active=1, period="p", period_sent=2, all_sent=3, since="01.10.2026", top="-"))


class PlanTextTests(unittest.TestCase):
    def test_pro_plan_text_still_lists_or_via_smart_conditions(self):
        with patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)):
            self.assertIn("AND", bot.plan_features_text("uz", "pro"))
            self.assertIn("YOKI", t("uz", "au_or_join"))


class I18nTests(unittest.TestCase):
    KEYS = ("au_or_join", "au_kw_or_hint", "au_kw_count", "au_kw_dup", "au_or_locked", "btn_au_edit", "au_edit_menu", "btn_au_e_name",
            "btn_au_e_kw", "btn_au_e_days", "btn_au_e_time", "btn_au_e_reply", "btn_au_e_prio", "btn_au_e_clear", "btn_au_e_done",
            "au_e_name_prompt", "au_e_kw_prompt", "au_e_time_prompt", "au_e_reply_prompt", "au_e_prio_prompt", "au_e_days_title",
            "au_name_bad", "au_prio_bad", "au_updated", "au_edit_lost", "au_e_none", "au_e_days_empty", "btn_au_stats", "au_stats",
            "au_stats_top_none", "an_lbl_automation", "au_rule_view", "au_rule_locked")

    def test_three_languages_and_cyrillic(self):
        import re
        for k in self.KEYS:
            entry = bot.i18n.T[k] if hasattr(bot, "i18n") else __import__("i18n").T[k]
            for lang in ("uz", "en", "ru"):
                self.assertTrue(entry.get(lang), (k, lang))
            self.assertTrue(re.search("[а-яА-Я]", entry["ru"]), k)
            if k not in ("btn_au_stats",):
                self.assertNotEqual(entry["en"], entry["uz"], k)

    def test_placeholders_match_across_languages(self):
        import re
        import i18n
        for k in self.KEYS:
            sets = {lang: set(re.findall(r"\{(\w+)\}", i18n.T[k][lang])) for lang in ("uz", "en", "ru")}
            self.assertEqual(sets["uz"], sets["en"], k)
            self.assertEqual(sets["uz"], sets["ru"], k)


if __name__ == "__main__":
    unittest.main()
