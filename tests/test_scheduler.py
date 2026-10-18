"""Smart Auto-Reply Scheduler: jadval mantig'i, baza (kesishish, limit, egalar ajratilgan), javob ustuvorligi, menyu oqimi."""
import asyncio
import os
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402
import i18n  # noqa: E402
import logic  # noqa: E402

_REAL_CURRENT = bot.current_schedule_rule  # conftest uni o'chiradi
run = asyncio.run
OWNER, OTHER, ADMIN, CHAT = 5101, 5102, 777, 99
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)


def m(h, mi=0):
    return h * 60 + mi


class LogicTests(unittest.TestCase):
    def test_mask_roundtrip(self):
        self.assertEqual(logic.mask_days(logic.days_mask([0, 2, 6])), [0, 2, 6])
        self.assertEqual(logic.WEEKDAYS_MASK, logic.days_mask([0, 1, 2, 3, 4]))
        self.assertEqual(logic.WEEKEND_MASK, logic.days_mask([5, 6]))

    def test_window_boundaries_start_inclusive_end_exclusive(self):
        mask = logic.WEEKDAYS_MASK
        self.assertTrue(logic.schedule_active(mask, m(9), m(18), MON, m(9)))
        self.assertTrue(logic.schedule_active(mask, m(9), m(18), MON, m(17, 59)))
        self.assertFalse(logic.schedule_active(mask, m(9), m(18), MON, m(18)))
        self.assertFalse(logic.schedule_active(mask, m(9), m(18), MON, m(8, 59)))
        self.assertFalse(logic.schedule_active(mask, m(9), m(18), SAT, m(12)))

    def test_overnight_crosses_into_next_day(self):
        mask = logic.days_mask([FRI])
        self.assertTrue(logic.schedule_active(mask, m(22), m(6), FRI, m(23)))
        self.assertTrue(logic.schedule_active(mask, m(22), m(6), SAT, m(3)))
        self.assertFalse(logic.schedule_active(mask, m(22), m(6), SAT, m(6)))
        self.assertFalse(logic.schedule_active(mask, m(22), m(6), FRI, m(3)))  # o'sha kunning ertalabi emas

    def test_overnight_on_sunday_wraps_to_monday(self):
        mask = logic.days_mask([SUN])
        self.assertTrue(logic.schedule_active(mask, m(22), m(6), MON, m(2)))
        self.assertFalse(logic.schedule_active(mask, m(22), m(6), MON, m(7)))

    def test_all_day(self):
        mask = logic.days_mask([SUN])
        self.assertTrue(logic.is_all_day(*logic.SCHEDULE_ALL_DAY))
        self.assertTrue(logic.schedule_active(mask, 0, 1440, SUN, 0))
        self.assertTrue(logic.schedule_active(mask, 0, 1440, SUN, m(23, 59)))
        self.assertFalse(logic.schedule_active(mask, 0, 1440, MON, 0))

    def test_valid_time(self):
        self.assertTrue(logic.valid_schedule_time(m(9), m(18)))
        self.assertTrue(logic.valid_schedule_time(m(22), m(6)))
        self.assertTrue(logic.valid_schedule_time(0, 1440))
        self.assertFalse(logic.valid_schedule_time(m(9), m(9)))
        self.assertFalse(logic.valid_schedule_time(0, 0))
        self.assertFalse(logic.valid_schedule_time(-1, 100))

    def test_overlap_detection(self):
        wd = logic.WEEKDAYS_MASK
        self.assertTrue(logic.schedules_overlap(wd, m(9), m(18), logic.days_mask([MON]), m(17), m(20)))
        self.assertFalse(logic.schedules_overlap(wd, m(9), m(18), wd, m(18), m(20)))  # chegarada tegib turadi, kesishmaydi
        self.assertFalse(logic.schedules_overlap(wd, m(9), m(18), logic.WEEKEND_MASK, m(9), m(18)))
        # yarim tundan o'tuvchi: Juma 22-06 va Shanba 05-08 kesishadi
        self.assertTrue(logic.schedules_overlap(logic.days_mask([FRI]), m(22), m(6), logic.days_mask([SAT]), m(5), m(8)))
        self.assertFalse(logic.schedules_overlap(logic.days_mask([FRI]), m(22), m(6), logic.days_mask([SAT]), m(6), m(8)))
        # Yakshanba 22-06 va Dushanba 01-03 kesishadi (hafta aylanishi)
        self.assertTrue(logic.schedules_overlap(logic.days_mask([SUN]), m(22), m(6), logic.days_mask([MON]), m(1), m(3)))
        # butun kun + shu kunning ichidagi oraliq
        self.assertTrue(logic.schedules_overlap(logic.days_mask([SUN]), 0, 1440, logic.days_mask([SUN]), m(10), m(11)))

    def test_find_active_skips_disabled(self):
        rules = [
            {"days": logic.WEEKDAYS_MASK, "start_min": m(9), "end_min": m(18), "is_enabled": False, "id": 1},
            {"days": logic.WEEKEND_MASK, "start_min": 0, "end_min": 1440, "is_enabled": True, "id": 2},
        ]
        self.assertIsNone(logic.find_active_schedule(rules, MON, m(10)))
        self.assertEqual(logic.find_active_schedule(rules, SUN, m(10))["id"], 2)

    def test_format_day_set(self):
        names = i18n.t("uz", "sched_days_full").split("|")
        f = lambda mask: logic.format_day_set(mask, names, "Har kuni")  # noqa: E731
        self.assertEqual(f(logic.WEEKDAYS_MASK), "Dushanba – Juma")
        self.assertEqual(f(logic.days_mask([SAT])), "Shanba")
        self.assertEqual(f(logic.WEEKEND_MASK), "Shanba, Yakshanba")  # 2 ta kun — vergul bilan
        self.assertEqual(f(logic.ALL_DAYS_MASK), "Har kuni")
        self.assertEqual(f(logic.days_mask([MON, WED, FRI])), "Dushanba, Chorshanba, Juma")

    def test_plan_limits(self):
        self.assertEqual(logic.SCHEDULE_PLAN_LIMITS, {"free": 1, "plus": 3, "pro": 10, "ultra": 30})


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL kerak")
class DbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM schedule_rules WHERE owner_user_id IN (%s, %s)", (OWNER, OTHER))

    def add(self, mask=logic.WEEKDAYS_MASK, s=m(9), e=m(18), text="Band", owner=OWNER, limit=30):
        return db.add_schedule_rule(owner, mask, s, e, text, limit)

    def test_add_list_and_numbering(self):
        self.assertEqual(self.add()[0], "ok")
        self.assertEqual(self.add(logic.WEEKEND_MASK, 0, 1440, None)[0], "ok")
        rules = db.list_schedule_rules(OWNER)
        self.assertEqual([r["days"] for r in rules], [logic.WEEKDAYS_MASK, logic.WEEKEND_MASK])
        self.assertIsNone(rules[1]["text"])
        self.assertTrue(all(r["is_enabled"] for r in rules))

    def test_limit(self):
        self.assertEqual(self.add(limit=1)[0], "ok")
        self.assertEqual(self.add(logic.WEEKEND_MASK, limit=1), ("limit", None))

    def test_conflict_reports_number(self):
        self.add()
        self.add(logic.WEEKEND_MASK, m(10), m(14))
        self.assertEqual(self.add(logic.days_mask([MON]), m(17), m(20)), ("conflict", 1))
        self.assertEqual(self.add(logic.days_mask([SAT]), m(13), m(15)), ("conflict", 2))
        self.assertEqual(db.count_schedule_rules(OWNER), 2)

    def test_update_conflict_ok_and_gone(self):
        _, a = self.add()
        _, b = self.add(logic.WEEKEND_MASK, m(10), m(14))
        self.assertEqual(db.update_schedule_rule(OWNER, b, days=logic.ALL_DAYS_MASK), ("conflict", 1))
        self.assertEqual(db.update_schedule_rule(OWNER, a, end_min=m(19))[0], "ok")  # o'zi bilan kesishish xato emas
        self.assertEqual(db.get_schedule_rule(OWNER, a)["end_min"], m(19))
        self.assertEqual(db.update_schedule_rule(OWNER, a, is_enabled=False)[0], "ok")
        self.assertEqual(db.update_schedule_rule(OWNER, 10**9, text="x"), ("gone", None))
        with self.assertRaises(ValueError):
            db.update_schedule_rule(OWNER, a, id=5)

    def test_owners_are_isolated(self):
        _, rid = self.add()
        self.assertEqual(self.add(owner=OTHER, limit=1)[0], "ok")  # boshqa egasining jadvali kesishmaydi
        self.assertIsNone(db.get_schedule_rule(OTHER, rid))
        self.assertEqual(db.update_schedule_rule(OTHER, rid, text="hack"), ("gone", None))
        self.assertFalse(db.delete_schedule_rule(OTHER, rid))
        self.assertEqual(db.get_schedule_rule(OWNER, rid)["text"], "Band")
        self.assertTrue(db.delete_schedule_rule(OWNER, rid))

    def test_parallel_adds_respect_limit(self):
        results = []

        def work(i):
            results.append(db.add_schedule_rule(OWNER, logic.days_mask([i % 7]), m(9), m(10), None, 3)[0])

        threads = [threading.Thread(target=work, args=(i,)) for i in range(7)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results.count("ok"), 3)
        self.assertEqual(db.count_schedule_rules(OWNER), 3)

    def test_scheduler_enabled_setting_whitelisted(self):
        self.assertIn("scheduler_enabled", db.ALLOWED_SETTINGS_FIELDS)


def _settings(**kw):
    base = {"offline": False, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
            "sleep_start_minutes": 0, "sleep_end_minutes": 0, "sleep_reply_text": "", "ai_enabled": False,
            "ai_info": None, "ai_role": None, "faq_enabled": True, "scheduler_enabled": True, "name_clock_tz": None}
    base.update(kw)
    return base


def _rule(text="Hozir bandman", mask=logic.WEEKDAYS_MASK, s=m(9), e=m(18), enabled=True, id_=1):
    return {"id": id_, "days": mask, "start_min": s, "end_min": e, "text": text, "is_enabled": enabled}


def _update(text="Salom", from_id=5):
    u = MagicMock()
    u.channel_post = None
    u.business_connection = None
    bm = MagicMock()
    bm.business_connection_id = "bc"
    bm.from_user.id = from_id
    bm.from_user.is_bot = False
    bm.chat.id = CHAT
    bm.message_id = 10
    bm.text = text
    bm.caption = None
    u.business_message = bm
    return u


TASH = ZoneInfo("Asia/Tashkent")
MON_10 = datetime(2026, 10, 19, 10, 0, tzinfo=TASH)   # Dushanba 10:00
MON_20 = datetime(2026, 10, 19, 20, 0, tzinfo=TASH)   # Dushanba 20:00


class CurrentRuleTests(unittest.TestCase):
    def setUp(self):
        for p in (patch.object(bot, "ADMIN_ID", ADMIN), patch.object(bot, "plan_of", lambda uid: "ultra")):
            p.start()
            self.addCleanup(p.stop)

    def cur(self, rules, settings=None, now=MON_10):
        with patch.object(db, "get_schedule_rules_cached", return_value=rules):
            return _REAL_CURRENT(OWNER, settings or _settings(), now)

    def test_inside_and_outside_window(self):
        self.assertEqual(self.cur([_rule()])["id"], 1)
        self.assertIsNone(self.cur([_rule()], now=MON_20))

    def test_globally_disabled_or_paused(self):
        self.assertIsNone(self.cur([_rule()], settings=_settings(scheduler_enabled=False)))
        self.assertIsNone(self.cur([_rule(enabled=False)]))

    def test_db_error_means_no_schedule(self):
        with patch.object(db, "get_schedule_rules_cached", side_effect=RuntimeError("db")):
            self.assertIsNone(_REAL_CURRENT(OWNER, _settings(), MON_10))

    def test_downgraded_user_only_first_rules_within_limit_work(self):
        rules = [_rule(mask=logic.days_mask([TUE]), id_=1), _rule(id_=2)]  # 2-chisi Dushanba oynasi
        with patch.object(bot, "plan_of", lambda uid: "free"):  # Free limiti = 1
            self.assertIsNone(self.cur(rules))
        self.assertEqual(self.cur(rules)["id"], 2)  # Ultra'da ikkalasi ham ishlaydi

    def test_uses_owner_time_zone(self):
        tokyo = _settings(name_clock_tz="Asia/Tokyo")  # Tokio Toshkentdan 4 soat oldinda
        now = datetime(2026, 10, 19, 6, 0, tzinfo=TASH)  # Toshkent 06:00 -> Tokio 10:00
        self.assertEqual(self.cur([_rule()], settings=tokyo, now=now.astimezone(ZoneInfo("Asia/Tokyo")))["id"], 1)


class ReplyFlowTests(unittest.TestCase):
    """on_raw_update: jadval ustuvorligi va mavjud funksiyalar bilan ishlashi."""

    def setUp(self):
        for p in (patch.object(bot, "ADMIN_ID", ADMIN),):
            p.start()
            self.addCleanup(p.stop)
        bot._bot_sent_ids.clear()

    def flow(self, settings=None, rule=None, sleeping=False, faq=None, ai_answer=None, claim=123.0, custom_text=True, update=None,
             sleep_fn=None):
        settings = settings or _settings()
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(return_value=MagicMock(message_id=555))
        conn = {"owner_user_id": OWNER, "is_enabled": True, "can_reply": True}
        patches = {
            "conn": patch.object(db, "get_connection_by_business_id", return_value=conn),
            "settings": patch.object(db, "get_settings", return_value=settings),
            "claim": patch.object(db, "try_claim_reply", return_value=claim),
            "release": patch.object(db, "release_reply_claim"),
            "rule": patch.object(bot, "current_schedule_rule", lambda owner, st, now=None: rule),
            "sleepwin": patch.object(bot, "is_within_sleep_window", sleep_fn or MagicMock(return_value=sleeping)),
            "faq": patch.object(bot, "find_faq_answer", lambda owner, text: faq),
            "paused": patch.object(db, "is_ai_paused", return_value=False),
            "quota": patch.object(db, "try_consume_ai_quota", return_value=True),
            "hist": patch.object(db, "get_ai_history", return_value=[]),
            "add": patch.object(db, "add_ai_messages"),
            "user": patch.object(db, "get_user", return_value={"full_name": "D"}),
            "conf": patch.object(bot.ai, "is_configured", return_value=ai_answer is not None),
            "gen": patch.object(bot.ai, "generate_reply", new=AsyncMock(return_value=ai_answer)),
            "feat": patch.object(bot, "has_feature", lambda uid, f: custom_text if f == "custom_text" else True),
        }
        started = {k: p.start() for k, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

        async def go():
            await bot.on_raw_update(update or _update(), ctx)
            await asyncio.gather(*list(bot._background_tasks))

        run(go())
        return [c.kwargs["text"] for c in ctx.bot.send_message.call_args_list], started

    def test_window_replies_even_when_owner_online_with_schedule_text(self):
        texts, _ = self.flow(settings=_settings(offline=False), rule=_rule("Hozir ish bilan bandman"))
        self.assertEqual(texts, ["Hozir ish bilan bandman"])

    def test_outside_window_falls_back_to_normal_settings(self):
        self.assertEqual(self.flow(settings=_settings(offline=True), rule=None)[0], ["Oflaynman"])
        self.assertEqual(self.flow(settings=_settings(offline=False), rule=None)[0], [])  # onlayn — javob yo'q

    def test_sleep_mode_beats_schedule(self):
        texts, _ = self.flow(settings=_settings(sleep_mode_enabled=True, sleep_reply_text="Uxlayapman"),
                             rule=_rule("Bandman"), sleeping=True)
        self.assertEqual(texts, ["Uxlayapman"])

    def test_schedule_does_not_change_user_settings(self):
        with patch.object(db, "update_settings") as upd:
            self.flow(settings=_settings(offline=False), rule=_rule())
        upd.assert_not_called()

    def test_faq_works_inside_window_and_beats_schedule_text(self):
        texts, _ = self.flow(rule=_rule("Bandman"), faq="Ish vaqti 9-18")
        self.assertEqual(texts, ["Ish vaqti 9-18"])

    def test_ai_works_inside_window_schedule_text_is_fallback(self):
        s = _settings(ai_enabled=True)
        texts, _ = self.flow(settings=s, rule=_rule("Bandman"), ai_answer="AI javobi")
        self.assertEqual(texts, ["AI javobi"])
        texts, _ = self.flow(settings=s, rule=_rule("Bandman"), ai_answer=None)  # AI sozlanmagan -> jadval matni
        self.assertEqual(texts, ["Bandman"])

    def test_cooldown_still_applies(self):
        texts, m_ = self.flow(rule=_rule(), claim=None)
        self.assertEqual(texts, [])
        m_["claim"].assert_called_once()

    def test_free_without_custom_text_uses_standard_text(self):
        texts, _ = self.flow(settings=_settings(auto_reply_text="Standart"), rule=_rule("Maxsus"), custom_text=False)
        self.assertEqual(texts, ["Standart"])

    def test_rule_without_text_uses_standard_text(self):
        texts, _ = self.flow(settings=_settings(auto_reply_text="Standart"), rule=_rule(None))
        self.assertEqual(texts, ["Standart"])

    def test_sleep_and_scheduler_share_owner_time_zone(self):
        seen = {}

        def spy(now_minutes, a, b):
            seen["minutes"] = now_minutes
            return False

        class FixedDT(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 10, 19, 6, 30, tzinfo=ZoneInfo("Asia/Tashkent")).astimezone(tz)  # Toshkent 06:30

        with patch.object(bot, "datetime", FixedDT):
            self.flow(settings=_settings(sleep_mode_enabled=True, name_clock_tz="Asia/Tokyo"), sleep_fn=spy)
            self.assertEqual(seen["minutes"], 10 * 60 + 30)  # Tokio 10:30 (Toshkent 06:30 emas)
            self.flow(settings=_settings(sleep_mode_enabled=True), sleep_fn=spy)
            self.assertEqual(seen["minutes"], 6 * 60 + 30)  # zona tanlanmagan — Toshkent

    def test_scheduler_receives_the_same_now_as_sleep(self):
        captured = {}

        def fake(owner, st, now=None):
            captured["now"] = now
            return None

        with patch.object(bot, "current_schedule_rule", fake), \
             patch.object(db, "get_connection_by_business_id", return_value={"owner_user_id": OWNER, "is_enabled": True, "can_reply": True}), \
             patch.object(db, "get_settings", return_value=_settings(name_clock_tz="Asia/Tokyo")):
            ctx = MagicMock()
            ctx.bot.send_message = AsyncMock()
            run(bot.on_raw_update(_update(), ctx))
        self.assertEqual(str(captured["now"].tzinfo), "Asia/Tokyo")

    def test_sleep_menu_shows_the_time_zone(self):
        with patch.object(db, "get_settings", return_value=_settings(name_clock_tz="Asia/Tokyo")), \
             patch.object(bot, "get_lang", lambda uid: "uz"):
            text, _ = bot.build_sleep_menu(OWNER)
        self.assertIn("Asia/Tokyo", text)

    def test_own_messages_still_ignored(self):
        texts, _ = self.flow(rule=_rule(), update=_update(from_id=OWNER))
        self.assertEqual(texts, [])


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL kerak")
class CacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM schedule_rules WHERE owner_user_id IN (%s, %s)", (OWNER, OTHER))
        db.invalidate_schedule_cache(OWNER)
        db.invalidate_schedule_cache(OTHER)

    def reads(self):
        """list_schedule_rules ga haqiqiy murojaatlar soni."""
        return patch.object(db, "list_schedule_rules", wraps=db.list_schedule_rules)

    def test_repeated_reads_hit_db_once_even_when_empty(self):
        with self.reads() as spy:
            for _ in range(5):
                self.assertEqual(db.get_schedule_rules_cached(OWNER), [])
        self.assertEqual(spy.call_count, 1)

    def test_add_update_delete_invalidate_immediately(self):
        self.assertEqual(db.get_schedule_rules_cached(OWNER), [])
        _, rid = db.add_schedule_rule(OWNER, logic.WEEKDAYS_MASK, m(9), m(18), "A", 5)
        self.assertEqual(len(db.get_schedule_rules_cached(OWNER)), 1)  # yangi jadval darhol ko'rinadi
        db.update_schedule_rule(OWNER, rid, text="B")
        self.assertEqual(db.get_schedule_rules_cached(OWNER)[0]["text"], "B")
        db.update_schedule_rule(OWNER, rid, is_enabled=False)
        self.assertFalse(db.get_schedule_rules_cached(OWNER)[0]["is_enabled"])
        db.delete_schedule_rule(OWNER, rid)
        self.assertEqual(db.get_schedule_rules_cached(OWNER), [])

    def test_ttl_expiry_rereads(self):
        db.get_schedule_rules_cached(OWNER)
        with self.reads() as spy, patch.object(db.time, "monotonic", return_value=db.time.monotonic() + db.SCHEDULE_CACHE_TTL_SECONDS + 1):
            db.get_schedule_rules_cached(OWNER)
        self.assertEqual(spy.call_count, 1)

    def test_cache_is_per_owner(self):
        db.add_schedule_rule(OWNER, logic.WEEKDAYS_MASK, m(9), m(18), "A", 5)
        self.assertEqual(len(db.get_schedule_rules_cached(OWNER)), 1)
        self.assertEqual(db.get_schedule_rules_cached(OTHER), [])

    def test_concurrent_write_during_read_does_not_leave_stale_cache(self):
        """O'quvchi eski ma'lumotni o'qiyotganda boshqa oqim jadvalni yangilab keshni tozalasa — eski natija keshga qaytib yozilmasligi kerak."""
        _, rid = db.add_schedule_rule(OWNER, logic.WEEKDAYS_MASK, m(9), m(18), "ESKI", 5)
        db.invalidate_schedule_cache(OWNER)
        real = db.list_schedule_rules
        fired = []

        def racing_read(owner):
            old = real(owner)  # 1) eski ma'lumot o'qildi
            if not fired:
                fired.append(1)
                db.update_schedule_rule(owner, rid, text="YANGI")  # 2) boshqa oqim yozdi va keshni tozaladi
            return old  # 3) o'quvchi eski ma'lumot bilan qaytadi

        with patch.object(db, "list_schedule_rules", racing_read):
            # o'qish davomida jadval o'zgardi — eskirgan natija qaytarilmaydi, bazadan qayta o'qiladi
            self.assertEqual(db.get_schedule_rules_cached(OWNER)[0]["text"], "YANGI")
        self.assertEqual(db.get_schedule_rules_cached(OWNER)[0]["text"], "YANGI")  # keshda ham yangi (60 soniya kutmaydi)

    def test_threaded_readers_and_writers_end_with_fresh_cache(self):
        _, rid = db.add_schedule_rule(OWNER, logic.WEEKDAYS_MASK, m(9), m(18), "0", 5)
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                db.get_schedule_rules_cached(OWNER)

        readers = [threading.Thread(target=reader) for _ in range(4)]
        [t.start() for t in readers]
        for i in range(1, 40):
            db.update_schedule_rule(OWNER, rid, text=str(i))
        stop.set()
        [t.join() for t in readers]
        self.assertEqual(db.get_schedule_rules_cached(OWNER)[0]["text"], "39")

    def test_failed_write_does_not_leave_stale_cache(self):
        db.add_schedule_rule(OWNER, logic.WEEKDAYS_MASK, m(9), m(18), "A", 5)
        db.get_schedule_rules_cached(OWNER)
        self.assertEqual(db.add_schedule_rule(OWNER, logic.WEEKDAYS_MASK, m(10), m(11), "x", 5)[0], "conflict")
        self.assertEqual(len(db.get_schedule_rules_cached(OWNER)), 1)

    def test_current_schedule_rule_uses_cache_not_direct_reads(self):
        with patch.object(bot, "plan_of", lambda uid: "ultra"), patch.object(bot, "ADMIN_ID", ADMIN), \
             patch.object(db, "list_schedule_rules", return_value=[]) as direct:
            for _ in range(3):
                _REAL_CURRENT(OWNER, _settings(), MON_10)
        self.assertEqual(direct.call_count, 1)


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL kerak")
class MenuFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM schedule_rules WHERE owner_user_id IN (%s, %s)", (OWNER, OTHER))
        bot._sc_drafts.clear()
        bot.clear_pending_action(OWNER)
        self.plan = "ultra"
        for p in (patch.object(bot, "ADMIN_ID", ADMIN), patch.object(bot, "plan_of", lambda uid: self.plan),
                  patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)),  # haqiqiy tarif qoidalari
                  patch.object(bot, "get_lang", lambda uid: "uz")):
            p.start()
            self.addCleanup(p.stop)

    STAGED = ("sc_d", "sc_dp", "sc_dnext", "sc_allday", "sc_deftext", "sc_save", "sc_cancel")

    def press(self, data, user=OWNER, fresh=True):
        """fresh=True: tugma hozirgi qoralamaning ID sini oladi (yangi ekrandagi tugma kabi);
        fresh=False: `data` aynan berilganidek yuboriladi (eski xabardagi tugma)."""
        draft = bot._sc_drafts.get(user)
        if fresh and draft and data.split(":")[0] in self.STAGED:
            data = f"{data}:{draft['id']}"
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

    def shown(self, q):
        return q.edit_message_text.await_args.args[0]

    def create(self, days=(0, 1, 2, 3, 4), time="09:00-18:00", text="Hozir bandman"):
        self.press("sc_add")
        for d in days:
            self.press(f"sc_d:{d}")
        self.press("sc_dnext")
        self.say(time)
        if text is not None:
            self.say(text)
        else:
            self.press("sc_deftext")
        return self.press("sc_save")

    def test_panel_has_scheduler_button_and_menu_opens_empty(self):
        _, markup = bot.build_panel(OWNER)
        self.assertIn("sc_menu", [b.callback_data for row in markup.inline_keyboard for b in row])
        q = self.press("sc_menu")
        self.assertIn("SMART AUTO-REPLY SCHEDULER", self.shown(q))
        self.assertIn(i18n.t("uz", "sched_none"), self.shown(q))

    def test_full_create_flow_shows_formatted_menu(self):
        q = self.create()
        text = self.shown(q)
        self.assertIn(i18n.t("uz", "sc_saved"), text)
        self.assertIn("1. Dushanba – Juma", text)
        self.assertIn("09:00–18:00", text)
        self.assertIn("Hozir bandman", text)
        rule = db.list_schedule_rules(OWNER)[0]
        self.assertEqual((rule["days"], rule["start_min"], rule["end_min"], rule["text"]),
                         (logic.WEEKDAYS_MASK, m(9), m(18), "Hozir bandman"))

    def test_all_day_and_default_text(self):
        self.press("sc_add")
        self.press("sc_d:6")
        self.press("sc_dnext")
        self.press("sc_allday")
        self.press("sc_deftext")
        q = self.press("sc_save")
        rule = db.list_schedule_rules(OWNER)[0]
        self.assertEqual((rule["start_min"], rule["end_min"], rule["text"]), (0, 1440, None))
        self.assertIn(i18n.t("uz", "sched_all_day"), self.shown(q))

    def test_continue_without_days_warns_and_stays(self):
        self.press("sc_add")
        q = self.press("sc_dnext")
        self.assertIn(i18n.t("uz", "sc_days_none"), self.shown(q))
        q.answer.assert_awaited_once()  # callback'ga faqat bir marta javob

    def test_bad_time_keeps_waiting(self):
        self.press("sc_add")
        self.press("sc_d:0")
        self.press("sc_dnext")
        reply = self.say("09:00-09:00")
        self.assertIn(i18n.t("uz", "sc_time_bad"), reply.await_args.args[0])
        self.assertEqual(bot.get_pending_action(OWNER), "sc_time")
        self.say("noto'g'ri")
        self.assertEqual(bot.get_pending_action(OWNER), "sc_time")

    def test_overnight_schedule_can_be_created(self):
        self.create(days=(4,), time="22:00-06:00", text=None)
        rule = db.list_schedule_rules(OWNER)[0]
        self.assertEqual((rule["start_min"], rule["end_min"]), (m(22), m(6)))

    def test_conflict_is_rejected_with_number(self):
        self.create()
        q = self.create(days=(0,), time="17:00-20:00", text=None)
        self.assertIn("1", self.shown(q).split("\n")[0])
        self.assertIn("kesishadi", self.shown(q).split("\n")[0])
        self.assertEqual(db.count_schedule_rules(OWNER), 1)

    def test_limit_by_plan_blocks_adding(self):
        self.plan = "free"
        self.create(days=(0,), text=None)
        q = self.press("sc_add")
        self.assertIn(i18n.t("uz", "sc_limit", max=1), self.shown(q))
        self.assertIsNone(bot._sc_draft(OWNER))

    def test_free_skips_text_step_with_note(self):
        self.plan = "free"
        self.press("sc_add")
        self.press("sc_d:0")
        self.press("sc_dnext")
        reply = self.say("09:00-18:00")
        self.assertIn(i18n.t("uz", "sc_text_locked_note"), reply.await_args.args[0])
        q = self.press("sc_save")
        self.assertIsNone(db.list_schedule_rules(OWNER)[0]["text"])
        self.assertIn(i18n.t("uz", "sc_saved"), self.shown(q))

    def test_free_cannot_edit_rule_text(self):
        self.plan = "free"
        self.create(days=(0,), text=None)
        rid = db.list_schedule_rules(OWNER)[0]["id"]
        q = self.press(f"sc_ed:text:{rid}")
        self.assertIn(i18n.t("uz", "feature_text"), self.shown(q))

    def test_old_save_button_cannot_save_a_newer_draft(self):
        """Birinchi jadval tasdiqlash ekraniga yetdi -> bekor qilindi -> ikkinchisi ham tasdiqlashga yetdi:
        birinchisining eski «Saqlash» tugmasi ikkinchisini saqlamasligi kerak."""
        self.press("sc_add")
        self.press("sc_d:0")
        self.press("sc_dnext")
        self.say("09:00-18:00")
        self.say("Birinchi")
        old_save = f"sc_save:{bot._sc_drafts[OWNER]['id']}"
        self.press("sc_cancel")
        self.press("sc_add")
        self.press("sc_d:1")
        self.press("sc_dnext")
        self.say("10:00-12:00")
        self.say("Ikkinchi")
        self.assertEqual(bot._sc_drafts[OWNER]["stage"], "confirm")
        q = self.press(old_save, fresh=False)
        self.assertIn(i18n.t("uz", "sc_stale_button"), self.shown(q))
        self.assertEqual(db.count_schedule_rules(OWNER), 0)
        # Yangi qoralama buzilmaydi: uning o'z «Saqlash» tugmasi ishlaydi
        self.assertEqual(bot._sc_drafts[OWNER]["text"], "Ikkinchi")
        self.press("sc_save")
        rules = db.list_schedule_rules(OWNER)
        self.assertEqual([(r["days"], r["text"]) for r in rules], [(logic.days_mask([1]), "Ikkinchi")])

    def test_old_id_buttons_are_ignored_on_every_step(self):
        self.press("sc_add")
        old = bot._sc_drafts[OWNER]["id"]
        self.press("sc_cancel")
        self.press("sc_add")
        new = bot._sc_drafts[OWNER]
        for data in (f"sc_d:3:{old}", f"sc_dp:all:{old}", f"sc_dnext:{old}", f"sc_allday:{old}", f"sc_deftext:{old}"):
            q = self.press(data, fresh=False)
            self.assertIn(i18n.t("uz", "sc_stale_button"), self.shown(q), data)
            self.press("sc_add")
            new = bot._sc_drafts[OWNER]
        self.assertEqual(new["days"], set())

    def test_buttons_without_draft_id_from_old_messages_are_ignored(self):
        self.press("sc_add")
        self.press("sc_d:0")
        q = self.press("sc_dnext", fresh=False)  # deploydan oldingi xabar: ID yo'q
        self.assertIn(i18n.t("uz", "sc_stale_button"), self.shown(q))
        self.assertEqual(db.count_schedule_rules(OWNER), 0)

    def test_every_staged_button_in_screens_carries_the_draft_id(self):
        self.press("sc_add")
        d = bot._sc_drafts[OWNER]
        _, markup = bot.build_sched_days(OWNER)
        datas = [b.callback_data for row in markup.inline_keyboard for b in row]
        staged = [x for x in datas if x.split(":")[0] in self.STAGED]
        self.assertTrue(staged)
        self.assertTrue(all(x.endswith(f":{d['id']}") for x in staged))
        self.assertTrue(all(len(x.encode()) <= 64 for x in datas))
        self.assertTrue(all(b.callback_data.endswith(d["id"]) for b in bot._sc_time_markup("uz", d).inline_keyboard[0]))

    def test_stale_save_button_never_writes_incomplete_draft(self):
        """Eski «Saqlash» tugmasi: yangi qoralama hali to'liq emas (kun/vaqt yo'q) — bazaga hech narsa yozilmaydi."""
        self.press("sc_add")
        for stage_action in (lambda: None, lambda: self.press("sc_d:0"), lambda: (self.press("sc_dnext"))):
            stage_action()
            q = self.press("sc_save")
            self.assertIn(i18n.t("uz", "sc_stale_button"), self.shown(q))
            self.assertEqual(db.count_schedule_rules(OWNER), 0)
            self.press("sc_add")  # qoralama bekor bo'ldi — qaytadan boshlaymiz

    def test_stale_buttons_from_other_stages_are_ignored(self):
        self.press("sc_add")
        self.press("sc_d:2")
        self.press("sc_dnext")  # endi bosqich: vaqt
        for stale in ("sc_deftext", "sc_save", "sc_dnext", "sc_d:3", "sc_dp:all"):
            q = self.press(stale)
            self.assertIn(i18n.t("uz", "sc_stale_button"), self.shown(q), stale)
            self.assertEqual(db.count_schedule_rules(OWNER), 0)
            self.press("sc_add")
            self.press("sc_d:2")
            self.press("sc_dnext")

    def test_save_validates_fields_even_if_stage_is_forged(self):
        self.press("sc_add")
        d = bot._sc_drafts[OWNER]
        d["stage"] = "confirm"  # kun va vaqt yo'q
        self.press("sc_save")
        self.assertEqual(db.count_schedule_rules(OWNER), 0)
        d = {"id": "forged", "days": {0}, "start": None, "end": None, "text": None, "edit_id": None, "edit": None,
             "stage": "confirm", "ts": 10**12}
        bot._sc_drafts[OWNER] = d
        self.press("sc_save")
        self.assertEqual(db.count_schedule_rules(OWNER), 0)
        d.update(start=m(9), end=m(9))  # noto'g'ri vaqt
        bot._sc_drafts[OWNER] = d
        self.press("sc_save")
        self.assertEqual(db.count_schedule_rules(OWNER), 0)

    def test_stale_button_does_not_cancel_current_input(self):
        """Foydalanuvchi vaqt kiritayotgan paytda eski xabardagi tugma bosilsa — kiritish bekor bo'lmaydi."""
        self.press("sc_add")
        old_id = bot._sc_drafts[OWNER]["id"]
        self.press("sc_cancel")
        self.press("sc_add")
        self.press("sc_d:2")
        self.press("sc_dnext")  # endi vaqt kutilmoqda
        draft_id = bot._sc_drafts[OWNER]["id"]
        self.assertEqual(bot.get_pending_action(OWNER), "sc_time")
        for stale in (f"sc_dnext:{old_id}", f"sc_save:{old_id}", f"sc_allday:{old_id}", f"sc_d:1:{old_id}"):
            q = self.press(stale, fresh=False)
            self.assertIn(i18n.t("uz", "sc_stale_button"), self.shown(q))
            self.assertEqual(bot.get_pending_action(OWNER), "sc_time", stale)  # kiritish davom etadi
            self.assertEqual(bot._sc_drafts[OWNER]["id"], draft_id)
            self.assertEqual(bot._sc_drafts[OWNER]["days"], {2})
        self.say("09:00-18:00")  # joriy kiritish hamon ishlaydi
        self.assertEqual(bot._sc_drafts[OWNER]["stage"], "text")
        self.assertEqual(bot._sc_drafts[OWNER]["start"], m(9))

    def test_old_cancel_button_cannot_cancel_new_draft(self):
        """Eski oynadagi «Bekor qilish» yangi qoralamani ham, kutilayotgan kiritishni ham bekor qilmasligi kerak."""
        self.press("sc_add")
        old_cancel = f"sc_cancel:{bot._sc_drafts[OWNER]['id']}"
        self.press("sc_cancel")
        self.press("sc_add")
        self.press("sc_d:2")
        self.press("sc_dnext")
        draft_id = bot._sc_drafts[OWNER]["id"]
        self.assertEqual(bot.get_pending_action(OWNER), "sc_time")
        for stale in (old_cancel, "sc_cancel", "sc_cancel:zzzzzz"):  # eski ID, ID'siz (eski format), noma'lum ID
            q = self.press(stale, fresh=False)
            self.assertIn(i18n.t("uz", "sc_stale_button"), self.shown(q))
            self.assertEqual(bot.get_pending_action(OWNER), "sc_time", stale)
            self.assertEqual(bot._sc_drafts[OWNER]["id"], draft_id)
            self.assertEqual(bot._sc_drafts[OWNER]["days"], {2})

    def test_current_cancel_button_cancels_own_draft(self):
        self.press("sc_add")
        self.press("sc_d:2")
        self.press("sc_dnext")
        did = bot._sc_drafts[OWNER]["id"]
        q = self.press(f"sc_cancel:{did}", fresh=False)
        self.assertNotIn(OWNER, bot._sc_drafts)
        self.assertIsNone(bot.get_pending_action(OWNER))
        self.assertIn(i18n.t("uz", "sc_cancelled"), self.shown(q))

    def test_cancel_without_draft_is_harmless(self):
        q = self.press("sc_cancel:abc123", fresh=False)
        self.assertIn(i18n.t("uz", "sc_cancelled"), self.shown(q))

    def test_every_cancel_button_carries_draft_id(self):
        d = bot._sc_new_draft(OWNER, days={0}, start=m(9), end=m(18), text="x", stage="confirm")
        views = [bot._sc_time_markup("uz", d), bot._sc_confirm_view(OWNER, d)[1], bot.build_sched_days(OWNER)[1]]
        step = bot._sc_text_step(OWNER, d)
        if step:
            views.append(step[1])
        found = 0
        for markup in views:
            for row in markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data.startswith("sc_cancel"):
                        found += 1
                        self.assertEqual(btn.callback_data, f"sc_cancel:{d['id']}")
        self.assertGreaterEqual(found, 3)

    def test_valid_buttons_still_clear_pending_input(self):
        self.press("sc_add")
        self.press("sc_d:2")
        self.press("sc_dnext")
        self.assertEqual(bot.get_pending_action(OWNER), "sc_time")
        self.press("sc_menu")  # haqiqiy tugma — oldingi kiritishni bekor qiladi (avvalgi xatti-harakat)
        self.assertIsNone(bot.get_pending_action(OWNER))

    def test_stale_button_when_no_draft_shows_draft_lost(self):
        q = self.press("sc_save:abc123", fresh=False)
        self.assertIn(i18n.t("uz", "sc_draft_lost"), self.shown(q))

    def test_expired_draft_is_handled(self):
        self.press("sc_add")
        self.press("sc_d:0")
        bot._sc_drafts.pop(OWNER)
        q = self.press("sc_save")
        self.assertIn(i18n.t("uz", "sc_draft_lost"), self.shown(q))

    def test_text_too_long(self):
        self.press("sc_add")
        self.press("sc_d:0")
        self.press("sc_dnext")
        self.say("09:00-18:00")
        reply = self.say("x" * (logic.SCHEDULE_MAX_TEXT + 1))
        self.assertIn(str(logic.SCHEDULE_MAX_TEXT), reply.await_args.args[0])
        self.assertEqual(bot.get_pending_action(OWNER), "sc_text")

    def test_edit_time_days_text_and_pause(self):
        self.create()
        rid = db.list_schedule_rules(OWNER)[0]["id"]
        self.press(f"sc_ed:time:{rid}")
        self.say("10:00-14:00")
        self.assertEqual(db.get_schedule_rule(OWNER, rid)["start_min"], m(10))
        self.press(f"sc_ed:text:{rid}")
        self.say("Yangi matn")
        self.assertEqual(db.get_schedule_rule(OWNER, rid)["text"], "Yangi matn")
        self.press(f"sc_ed:days:{rid}")
        self.press("sc_dp:we")
        self.press("sc_dnext")
        self.assertEqual(db.get_schedule_rule(OWNER, rid)["days"], logic.WEEKEND_MASK)
        self.press(f"sc_tg:{rid}")
        self.assertFalse(db.get_schedule_rule(OWNER, rid)["is_enabled"])
        q = self.press("sc_menu")
        self.assertIn(i18n.t("uz", "sched_paused"), self.shown(q))

    def test_edit_causing_conflict_is_blocked(self):
        self.create()
        self.create(days=(5,), time="10:00-14:00", text=None)
        rid = db.list_schedule_rules(OWNER)[1]["id"]
        self.press(f"sc_ed:days:{rid}")
        self.press("sc_dp:all")
        q = self.press("sc_dnext")
        self.assertIn("kesishadi", self.shown(q))
        self.assertEqual(db.get_schedule_rule(OWNER, rid)["days"], logic.days_mask([SAT]))

    def test_delete_needs_confirmation(self):
        self.create()
        rid = db.list_schedule_rules(OWNER)[0]["id"]
        q = self.press(f"sc_del:{rid}")
        self.assertIn(i18n.t("uz", "sc_del_confirm", entry="")[:12], self.shown(q))
        self.assertEqual(db.count_schedule_rules(OWNER), 1)  # tasdiqsiz o'chmaydi
        self.press(f"sc_del_yes:{rid}")
        self.assertEqual(db.count_schedule_rules(OWNER), 0)

    def test_cannot_touch_other_owners_rules(self):
        _, rid = db.add_schedule_rule(OTHER, logic.WEEKDAYS_MASK, m(9), m(18), "Boshqa", 30)
        for data in (f"sc_e:{rid}", f"sc_tg:{rid}", f"sc_del:{rid}", f"sc_del_yes:{rid}", f"sc_ed:time:{rid}"):
            self.press(data)
        rule = db.get_schedule_rule(OTHER, rid)
        self.assertIsNotNone(rule)
        self.assertTrue(rule["is_enabled"])
        self.assertEqual(rule["text"], "Boshqa")

    def test_global_toggle(self):
        self.press("sc_toggle")
        self.assertFalse(db.get_settings(OWNER)["scheduler_enabled"])
        q = self.press("sc_settings")
        self.assertIn(i18n.t("uz", "btn_sc_toggle_off"), str(q.edit_message_text.await_args.kwargs["reply_markup"]))
        self.press("sc_toggle")
        self.assertTrue(db.get_settings(OWNER)["scheduler_enabled"])

    def test_full_menu_with_30_rules_fits_telegram_limit(self):
        for d in range(7):
            for k in range(5):
                db.add_schedule_rule(OWNER, logic.days_mask([d]), m(k * 4), m(k * 4 + 3), "x" * 400, 35)
        self.assertEqual(db.count_schedule_rules(OWNER), 35)
        text, _ = bot.build_sched_menu(OWNER)
        self.assertLess(len(text), 4096)


class PlanAndI18nTests(unittest.TestCase):
    def test_plan_features_text_lists_scheduler_limit_per_plan(self):
        with patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)):
            for plan, n in logic.SCHEDULE_PLAN_LIMITS.items():
                self.assertIn(i18n.t("uz", "pf_sched", n=n), bot.plan_features_text("uz", plan))

    def test_limit_for_admin_and_plans(self):
        with patch.object(bot, "ADMIN_ID", ADMIN):
            self.assertEqual(bot.schedule_limit_for(ADMIN), 30)
            for plan, n in logic.SCHEDULE_PLAN_LIMITS.items():
                self.assertEqual(bot.schedule_limit_for(1, plan), n)

    def test_day_names_have_seven_entries_in_every_language(self):
        for lang in ("uz", "en", "ru"):
            self.assertEqual(len(i18n.t(lang, "sched_days_full").split("|")), 7)
            self.assertEqual(len(i18n.t(lang, "sched_days_short").split("|")), 7)

    def test_locked_mapping(self):
        self.assertEqual(bot.locked_feature_for("sc_ed:text:5"), "custom_text")
        self.assertIsNone(bot.locked_feature_for("sc_menu"))
        self.assertIsNone(bot.locked_feature_for("sc_ed:time:5"))


if __name__ == "__main__":
    unittest.main()
