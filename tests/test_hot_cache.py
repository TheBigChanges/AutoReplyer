"""Tezlik: issiq kesh, so'rovlarni qisqartirish, track_user throttle, PERF log (HAQIQIY Postgres'da)."""

import asyncio
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import bot  # noqa: E402
import db  # noqa: E402


def queries(fn, *args, **kwargs):
    """fn ni bajaradi va (natija, bazaga so'rovlar soni) ni qaytaradi."""
    stats = db.perf_start()
    result = fn(*args, **kwargs)
    return result, stats["n"]


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class HotCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.o = 700_000_000 + int.from_bytes(os.urandom(3), "big")
        patcher = patch.object(db, "HOT_CACHE_TTL", 15.0)  # testlarda kesh odatda o'chiq (conftest): bu yerda yoqiladi
        patcher.start()
        self.addCleanup(patcher.stop)
        db.hot_cache_clear()
        self.addCleanup(db.hot_cache_clear)

    # --- so'rovlarni qisqartirish ------------------------------------------------------------------
    def test_get_settings_is_one_query_when_row_exists_and_creates_when_missing(self):
        with patch.object(db, "HOT_CACHE_TTL", 0.0):
            _, n_new = queries(db.get_settings, self.o)       # qator yo'q: yaratiladi
            self.assertGreaterEqual(n_new, 2)
            s, n = queries(db.get_settings, self.o)
            self.assertEqual(n, 1)                             # avval har safar 2 ta (INSERT + SELECT) edi
            self.assertEqual(s["owner_user_id"], self.o)

    def test_update_settings_is_one_query_when_row_exists_and_creates_when_missing(self):
        with patch.object(db, "HOT_CACHE_TTL", 0.0):
            db.update_settings(self.o, cooldown_hours=7.0)     # qator yo'q: ensure + UPDATE
            self.assertEqual(db.get_settings(self.o)["cooldown_hours"], 7.0)
            _, n = queries(db.update_settings, self.o, cooldown_hours=9.0)
            self.assertEqual(n, 1)
            self.assertEqual(db.get_settings(self.o)["cooldown_hours"], 9.0)

    # --- kesh ------------------------------------------------------------------------------------
    def test_second_read_hits_cache_and_returns_independent_copy(self):
        db.get_settings(self.o)
        s, n = queries(db.get_settings, self.o)
        self.assertEqual(n, 0)
        s["cooldown_hours"] = 12345.0                          # chaqiruvchi lug'atni o'zgartirsa ham kesh buzilmaydi
        self.assertNotEqual(db.get_settings(self.o)["cooldown_hours"], 12345.0)

    def test_first_caller_mutating_result_does_not_poison_cache(self):
        first = db.get_settings(self.o)                        # sovuq o'qish: kesh to'ldiriladi
        first["cooldown_hours"] = 4242.0
        self.assertNotEqual(db.get_settings(self.o)["cooldown_hours"], 4242.0)

    def test_write_invalidates_so_changes_are_visible_immediately(self):
        db.get_settings(self.o)
        db.update_settings(self.o, cooldown_hours=5.5)
        self.assertEqual(db.get_settings(self.o)["cooldown_hours"], 5.5)

    def test_plan_change_is_visible_immediately_and_expiry_is_respected(self):
        self.assertEqual(db.get_user_plan(self.o), "free")
        db.set_user_plan(self.o, "pro", time.time() + 3600)
        self.assertEqual(db.get_user_plan(self.o), "pro")
        _, n = queries(db.get_user_plan, self.o)
        self.assertEqual(n, 0)                                 # keshdan
        with patch("db.time.time", return_value=time.time() + 7200):   # muddat o'tdi — keshdagi 'pro' ishlatilmaydi
            self.assertEqual(db.get_user_plan(self.o), "free")

    def test_connection_change_is_visible_immediately(self):
        self.assertIsNone(db.get_connection(self.o))
        db.upsert_connection(self.o, "bc-x", True, True, False, False)
        self.assertEqual(db.get_connection(self.o)["business_connection_id"], "bc-x")
        db.upsert_connection(self.o, "bc-y", True, True, False, False)
        self.assertEqual(db.get_connection(self.o)["business_connection_id"], "bc-y")

    def test_failed_writer_still_clears_cache(self):
        db.get_settings(self.o)
        with self.assertRaises(ValueError):
            db.update_settings(self.o, no_such_column=1)
        _, n = queries(db.get_settings, self.o)
        self.assertEqual(n, 1)

    def test_ttl_expiry_refreshes(self):
        db.get_settings(self.o)
        with patch("db.time.monotonic", return_value=time.monotonic() + 16):
            _, n = queries(db.get_settings, self.o)
        self.assertEqual(n, 1)

    def test_harmless_hot_path_writers_keep_cache(self):
        db.get_settings(self.o)
        db.record_user(self.o)
        db.record_analytics(self.o, "ai")
        _, n = queries(db.get_settings, self.o)
        self.assertEqual(n, 0)

    def test_disabled_when_ttl_zero(self):
        with patch.object(db, "HOT_CACHE_TTL", 0.0):
            db.get_settings(self.o)
            _, n = queries(db.get_settings, self.o)
        self.assertEqual(n, 1)

    def test_every_non_read_db_function_clears_the_cache(self):
        """Yangi yozuvchi funksiya qo'shilsa ham kesh avtomatik tozalanadi (ro'yxatni qo'lda yuritish shart emas)."""
        import inspect
        missing = []
        for name, fn in inspect.getmembers(db, inspect.isfunction):
            if fn.__module__ != db.__name__ or name.startswith("_") or name.startswith(db._READ_PREFIXES):
                continue
            if name in db._HOT_HARMLESS_WRITERS or name == "hot_cache_clear":
                continue
            if not getattr(fn, "_clears_cache", False):
                missing.append(name)
        self.assertEqual(missing, [])

    def test_writer_in_between_makes_next_read_hit_db(self):
        db.get_user_plan(self.o)
        db.set_user_lang(self.o, "uz")
        _, n = queries(db.get_user_plan, self.o)
        self.assertEqual(n, 1)


class PoolSettingsTests(unittest.TestCase):
    def test_pool_is_warm_and_uses_tcp_keepalive(self):
        created = {}

        def fake_pool(minconn, maxconn, **kw):
            created.update(minconn=minconn, maxconn=maxconn, **kw)
            return MagicMock()

        with patch.object(db, "_pool", None), patch("db.psycopg2.pool.ThreadedConnectionPool", side_effect=fake_pool):
            db._get_pool()
        self.assertGreaterEqual(created["minconn"], 2)             # tayyor ulanishlar: birinchi bosish yangi TLS ochmaydi
        self.assertEqual(created["keepalives"], 1)                 # bo'sh ulanish jimgina uzilmasin
        self.assertLessEqual(created["keepalives_idle"], 60)


class TrackUserThrottleTests(unittest.TestCase):
    def setUp(self):
        bot._user_tracked.clear()
        self.user = MagicMock(id=5, is_bot=False, username="ali", full_name="Ali V", first_name="Ali", last_name="V")

    def run_track(self, user=None):
        with patch.object(db, "record_user") as rec, patch.object(bot, "name_clock_allowed", return_value=False):
            bot.track_user(user or self.user)
        return rec

    def test_repeated_clicks_write_once(self):
        self.assertEqual(self.run_track().call_count, 1)
        for _ in range(5):
            self.assertEqual(self.run_track().call_count, 0)

    def test_changed_username_or_name_is_written_immediately(self):
        self.run_track()
        self.user.username = "ali2"
        self.assertEqual(self.run_track().call_count, 1)
        self.user.full_name = "Ali Valiyev"
        self.assertEqual(self.run_track().call_count, 1)

    def test_written_again_after_ttl(self):
        self.run_track()
        with patch.object(bot.time, "monotonic", return_value=time.monotonic() + bot.USER_TRACK_TTL + 1):
            self.assertEqual(self.run_track().call_count, 1)

    def test_failed_write_is_retried_next_click(self):
        with patch.object(db, "record_user", side_effect=RuntimeError("db")), patch.object(bot, "name_clock_allowed", return_value=False):
            with self.assertRaises(RuntimeError):
                bot.track_user(self.user)
        self.assertEqual(self.run_track().call_count, 1)

    def test_bots_are_never_tracked(self):
        bot_user = MagicMock(id=6, is_bot=True)
        self.assertEqual(self.run_track(bot_user).call_count, 0)


class PerfLogTests(unittest.TestCase):
    def test_slow_click_is_logged_with_query_counts(self):
        stats = {"n": 7, "ms": 1234.0}
        with self.assertLogs(bot.logger, level="INFO") as cm:
            with patch.object(bot, "PERF_LOG_SLOW_MS", 0.0):
                bot._log_perf("button", "open_panel", time.perf_counter() - 1.0, stats)
        line = cm.output[0]
        self.assertIn("PERF button open_panel", line)
        self.assertIn("7 ta so'rov", line)

    def test_fast_click_is_not_logged(self):
        with patch.object(bot, "PERF_LOG_SLOW_MS", 10_000.0):
            with self.assertNoLogs(bot.logger, level="INFO"):
                bot._log_perf("button", "x", time.perf_counter(), {"n": 1, "ms": 1.0})

    def test_on_button_wrapper_logs_and_still_raises(self):
        update = MagicMock()
        update.callback_query.data = "open_panel"
        with patch.object(bot, "_on_button", new=AsyncMock(side_effect=RuntimeError("boom"))), \
                patch.object(bot, "_log_perf") as log:
            with self.assertRaises(RuntimeError):
                asyncio.run(bot.on_button(update, MagicMock()))
        log.assert_called_once()
        self.assertEqual(log.call_args.args[:2], ("button", "open_panel"))


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL yo'q")
class ClickQueryBudgetTests(unittest.TestCase):
    """Regressiya: iliq (keshlangan) tugma bosilishi bazaga 1 tadan ko'p so'rov qilmasligi kerak (avval 5–13 ta edi)."""

    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.o = 710_000_000 + int.from_bytes(os.urandom(3), "big")
        p = patch.object(db, "HOT_CACHE_TTL", 15.0)
        p.start()
        self.addCleanup(p.stop)
        db.hot_cache_clear()
        self.addCleanup(db.hot_cache_clear)
        bot._user_tracked.clear()
        bot._lang_cache.clear()
        db.record_user(self.o, username="u", full_name="U")
        db.set_user_lang(self.o, "uz")
        db.upsert_connection(self.o, f"bc{self.o}", True, True, True, True)
        db.ensure_settings(self.o)

    def click(self, data):
        q = MagicMock()
        q.data = data
        q.from_user = MagicMock(id=self.o, is_bot=False, username="u", full_name="U", first_name="U", last_name=None)
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        update = MagicMock()
        update.callback_query = q
        stats = db.perf_start()
        asyncio.run(bot._on_button(update, MagicMock()))
        self.assertEqual(q.edit_message_text.await_count, 1, data)
        return stats["n"]

    def test_warm_menu_clicks_use_at_most_one_query(self):
        self.click("open_panel")  # sovuq: keshni to'ldiradi
        for data in ("open_panel", "back", "ar_menu", "bio_menu", "ai_menu", "faq_menu", "kb_menu", "au_menu", "sc_menu", "ib_menu", "an_menu", "nc_menu"):
            with self.subTest(data=data):
                self.assertLessEqual(self.click(data), 1)


if __name__ == "__main__":
    unittest.main()
