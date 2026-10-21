"""AutoReply Analytics: hisoblash, baza (egalar ajratilgan), hodisalarni sanash, tarif cheklovlari, menyu, grafiklar."""
import asyncio
import os
import sys
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", TEST_DB_URL or "postgresql://fake/fake")

import analytics  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402
import i18n  # noqa: E402

OWNER = 4101
OTHER = 4102
ADMIN = 777
CHAT = 99
TZ = timezone(timedelta(hours=5))
_REAL_TRACK = bot.track_analytics  # conftest uni o'chiradi


def hour_ts(days_ago=0, hour=10):
    """Toshkent (UTC+5) bo'yicha `days_ago` kun oldingi `hour:00` — soat boshiga tekislangan UTC epoch."""
    now = datetime.now(TZ).replace(hour=hour, minute=0, second=0, microsecond=0)
    return (now - timedelta(days=days_ago)).timestamp()


class SummarizeTests(unittest.TestCase):
    def rows(self):
        return [
            (hour_ts(0, 9), "incoming", 3), (hour_ts(0, 9), "static", 2), (hour_ts(0, 9), "faq", 1),
            (hour_ts(0, 10), "incoming", 5), (hour_ts(0, 10), "ai", 4), (hour_ts(0, 10), "sleep", 1),
            (hour_ts(0, 10), "skipped", 2),
            (hour_ts(3, 21), "incoming", 4), (hour_ts(3, 21), "static", 4),
            (hour_ts(20, 12), "incoming", 7), (hour_ts(20, 12), "ai", 7),
        ]

    def test_today_counts_incoming_and_sent_separately(self):
        s = analytics.summarize(self.rows(), 1, TZ)
        self.assertEqual((s["incoming"], s["sent"]), (8, 8))
        self.assertEqual(s["kinds"]["faq"], 1)
        self.assertEqual(s["kinds"]["ai"], 4)
        self.assertEqual(s["kinds"]["static"], 2)
        self.assertEqual(s["kinds"]["sleep"], 1)
        self.assertEqual(s["skipped"], 2)
        self.assertEqual(s["peak"], (9, 11))  # 9:00 (3) + 10:00 (5)

    def test_period_windows(self):
        self.assertEqual(analytics.summarize(self.rows(), 7, TZ)["incoming"], 12)
        self.assertEqual(analytics.summarize(self.rows(), 30, TZ)["incoming"], 19)

    def test_daily_list_covers_every_day_and_rates(self):
        s = analytics.summarize(self.rows(), 7, TZ)
        self.assertEqual(len(s["daily"]), 7)
        self.assertEqual(s["daily"][-1][1:], (8, 8))
        self.assertEqual(s["daily_avg"], round(12 / 7, 1))
        self.assertEqual(s["reply_rate"], round(100 * 12 / 12))
        self.assertEqual(s["busiest_day"][1], 8)

    def test_empty_and_busiest_window(self):
        s = analytics.summarize([], 7, TZ)
        self.assertTrue(analytics.is_empty(s))
        self.assertIsNone(s["peak"])
        self.assertIsNone(s["busiest_day"])
        self.assertEqual(s["reply_rate"], 0)
        self.assertIsNone(analytics.busiest_window([0] * 24))
        h = [0] * 24
        h[23] = 5
        self.assertEqual(analytics.busiest_window(h), (23, 1))  # faol soatdan boshlanadigan oyna

    def test_busiest_window_compares_all_two_hour_sums(self):
        h = [0] * 24
        h[0], h[1], h[12] = 10, 10, 11
        self.assertEqual(analytics.busiest_window(h), (0, 2))  # 20 ta > 12:00-14:00 dagi 11 ta
        h = [0] * 24
        h[5], h[6] = 3, 3
        self.assertEqual(analytics.busiest_window(h), (5, 7))

    def test_busiest_window_wraps_around_midnight(self):
        """Xabarlar asosan 23:00 va 00:00 da kelsa — eng faol oyna 23:00-01:00."""
        h = [0] * 24
        h[23], h[0] = 9, 8
        h[12], h[13] = 10, 5  # kunduzgi oyna: 15 ta < 17 ta
        self.assertEqual(analytics.busiest_window(h), (23, 1))
        self.assertEqual(analytics.busiest_window([0] * 22 + [4, 4]), (22, 0))  # 22:00-24:00 ham yarim tun chegarasi

    def test_wrap_window_does_not_beat_larger_regular_window(self):
        h = [0] * 24
        h[23], h[0] = 3, 3
        h[10], h[11] = 5, 5
        self.assertEqual(analytics.busiest_window(h), (10, 12))

    def test_wrap_window_in_summary_and_text(self):
        rows = [(hour_ts(1, 23), "incoming", 6), (hour_ts(0, 0), "incoming", 5), (hour_ts(0, 12), "incoming", 4)]
        s = analytics.summarize(rows, 7, TZ)
        self.assertEqual(s["peak"], (23, 1))
        self.assertEqual(bot._an_peak_text("uz", s["peak"]), "23:00\u201301:00")

    def test_peak_contains_handles_wrap(self):
        self.assertTrue(all(analytics.peak_contains((23, 1), h) for h in (23, 0)))
        self.assertFalse(any(analytics.peak_contains((23, 1), h) for h in (1, 2, 12, 22)))
        self.assertTrue(analytics.peak_contains((9, 11), 10))
        self.assertFalse(analytics.peak_contains((9, 11), 11))
        self.assertFalse(analytics.peak_contains(None, 3))

    def test_bar_chart_highlights_wrapping_peak_hours(self):
        s = analytics.summarize([(hour_ts(1, 23), "incoming", 6), (hour_ts(0, 0), "incoming", 5)], 7, TZ)
        with patch.object(analytics, "_fig_to_png", lambda fig: [p.get_facecolor() for p in fig.axes[0].patches]):
            colors = analytics.render_bar_chart(s, bot.analytics_chart_labels("uz", "bar"))
        import matplotlib.colors as mc
        hi = mc.to_rgba(analytics._COLORS["faq"])
        self.assertEqual([i for i, c in enumerate(colors) if tuple(c) == hi], [0, 23])

    def test_today_has_hourly_sent_series(self):
        s = analytics.summarize(self.rows(), 1, TZ)
        self.assertEqual(s["hourly_sent"][9], 3)
        self.assertEqual(s["hourly_sent"][10], 5)

    def test_unknown_kind_ignored(self):
        s = analytics.summarize([(hour_ts(0, 9), "weird", 9)], 1, TZ)
        self.assertTrue(analytics.is_empty(s))


@unittest.skipUnless(TEST_DB_URL, "TEST_DATABASE_URL kerak")
class DbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM analytics_hourly WHERE owner_user_id IN (%s, %s)", (OWNER, OTHER))

    def test_upsert_increments_same_hour_bucket(self):
        ts = hour_ts(0, 9)
        db.record_analytics(OWNER, "incoming", ts)
        db.record_analytics(OWNER, "incoming", ts + 600)  # shu soatning ichida
        db.record_analytics(OWNER, "static", ts)
        rows = dict(((b, k), c) for b, k, c in db.get_analytics_rows(OWNER, ts - 3600))
        self.assertEqual(rows[(int(ts // 3600 * 3600), "incoming")], 2)
        self.assertEqual(rows[(int(ts // 3600 * 3600), "static")], 1)

    def test_owners_are_isolated(self):
        db.record_analytics(OWNER, "incoming")
        db.record_analytics(OTHER, "incoming", n=5)
        mine = db.get_analytics_rows(OWNER, time.time() - 7200)
        self.assertEqual(sum(c for _, _, c in mine), 1)

    def test_since_filter_and_purge(self):
        old = time.time() - 100 * 86400
        db.record_analytics(OWNER, "incoming", old)
        db.record_analytics(OWNER, "incoming")
        self.assertEqual(len(db.get_analytics_rows(OWNER, time.time() - 86400)), 1)
        self.assertGreaterEqual(db.purge_old_analytics(), 1)
        self.assertEqual(len(db.get_analytics_rows(OWNER, 0)), 1)

    def test_unknown_kind_rejected_and_no_text_columns(self):
        with self.assertRaises(ValueError):
            db.record_analytics(OWNER, "message_text")
        with db.get_conn() as c, c.cursor() as cur:
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'analytics_hourly'")
            cols = {r[0] for r in cur.fetchall()}
        self.assertEqual(cols, {"owner_user_id", "bucket", "kind", "count"})  # matn/chat ID ustuni yo'q

    def test_pool_is_threaded_and_parallel_writes_are_exact(self):
        import threading
        import psycopg2.pool
        db._get_pool()
        self.assertIsInstance(db._pool, psycopg2.pool.ThreadedConnectionPool)
        ts = hour_ts(0, 9)
        errors = []

        def work():
            try:
                for _ in range(10):
                    db.record_analytics(OWNER, "incoming", ts)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=work) for _ in range(30)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(sum(c for _, k, c in db.get_analytics_rows(OWNER, ts - 3600) if k == "incoming"), 300)

    def test_track_analytics_end_to_end_and_errors_swallowed(self):
        async def go():
            _REAL_TRACK(OWNER, "faq")
            await asyncio.gather(*list(bot._background_tasks))
        asyncio.run(go())
        self.assertEqual(sum(c for _, k, c in db.get_analytics_rows(OWNER, time.time() - 7200) if k == "faq"), 1)
        with patch.object(db, "record_analytics", side_effect=RuntimeError("db down")):
            bot._record_analytics_safe(OWNER, "faq")  # xato tashqariga chiqmaydi


def _update(text="Salom", from_id=5, is_bot=False):
    u = MagicMock()
    u.channel_post = None
    u.business_connection = None
    bm = MagicMock()
    bm.business_connection_id = "bc"
    bm.from_user.id = from_id
    bm.from_user.is_bot = is_bot
    bm.chat.id = CHAT
    bm.message_id = 10
    bm.text = text
    bm.caption = None
    u.business_message = bm
    return u


def _settings(**kw):
    base = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
            "sleep_start_minutes": 0, "sleep_end_minutes": 0, "sleep_reply_text": "", "ai_enabled": False,
            "ai_info": None, "ai_role": None, "faq_enabled": True}
    base.update(kw)
    return base


class CountingFlowTests(unittest.TestCase):
    """on_raw_update orqali: qaysi hodisa qaysi turda sanaladi."""

    def setUp(self):
        for target, value in (("ADMIN_ID", ADMIN),):
            p = patch.object(bot, target, value)
            p.start()
            self.addCleanup(p.stop)
        bot._bot_sent_ids.clear()

    def flow(self, update=None, settings=None, claim=123.0, send_error=None, faq=None, ai_answer=None, ai_quota=True):
        events = []
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(side_effect=send_error, return_value=MagicMock(message_id=555))
        conn = {"owner_user_id": OWNER, "is_enabled": True, "can_reply": True}
        ps = [
            patch.object(bot, "track_analytics", lambda o, k: events.append((o, k))),
            patch.object(db, "get_connection_by_business_id", return_value=conn),
            patch.object(db, "get_settings", return_value=settings or _settings()),
            patch.object(db, "try_claim_reply", return_value=claim),
            patch.object(db, "release_reply_claim"),
            patch.object(db, "is_ai_paused", return_value=False),
            patch.object(db, "pause_ai_chat"),
            patch.object(db, "try_consume_ai_quota", return_value=ai_quota),
            patch.object(db, "refund_ai_quota"),
            patch.object(db, "get_ai_history", return_value=[]),
            patch.object(db, "add_ai_messages"),
            patch.object(db, "get_user", return_value={"full_name": "D"}),
            patch.object(bot, "find_faq_answer", lambda owner, text: faq),
            patch.object(bot.ai, "is_configured", return_value=ai_answer is not None),
            patch.object(bot.ai, "generate_reply", new=AsyncMock(return_value=ai_answer)),
        ]
        for p in ps:
            p.start()
            self.addCleanup(p.stop)

        async def go():
            await bot.on_raw_update(update or _update(), ctx)
            await asyncio.gather(*list(bot._background_tasks))

        asyncio.run(go())
        return events

    def test_static_reply_counts_incoming_and_static(self):
        self.assertEqual(self.flow(), [(OWNER, "incoming"), (OWNER, "static")])

    def test_owner_online_counts_incoming_only(self):
        self.assertEqual(self.flow(settings=_settings(offline=False)), [(OWNER, "incoming")])

    def test_sleep_reply_counts_as_sleep(self):
        s = _settings(sleep_mode_enabled=True, sleep_start_minutes=0, sleep_end_minutes=1439)
        with patch.object(bot, "is_within_sleep_window", return_value=True):
            self.assertEqual(self.flow(settings=s), [(OWNER, "incoming"), (OWNER, "sleep")])

    def test_cooldown_skip_counts_incoming_and_skipped_not_sent(self):
        self.assertEqual(self.flow(claim=None), [(OWNER, "incoming"), (OWNER, "skipped")])

    def test_failed_send_is_not_counted_as_reply(self):
        from telegram.error import TelegramError
        self.assertEqual(self.flow(send_error=TelegramError("x")), [(OWNER, "incoming")])

    def test_faq_reply_counts_as_faq(self):
        self.assertEqual(self.flow(faq="Ish vaqti 9-18"), [(OWNER, "incoming"), (OWNER, "faq")])

    def test_ai_reply_counts_as_ai(self):
        self.assertEqual(self.flow(ai_answer="Salom!", settings=_settings(ai_enabled=True)), [(OWNER, "incoming"), (OWNER, "ai")])

    def test_ai_fallbacks_count_as_static(self):
        s = _settings(ai_enabled=True)
        self.assertEqual(self.flow(ai_answer="x", settings=s, ai_quota=False), [(OWNER, "incoming"), (OWNER, "static")])

    def test_owner_own_and_bot_messages_not_counted(self):
        self.assertEqual(self.flow(update=_update(from_id=OWNER)), [])
        self.assertEqual(self.flow(update=_update(is_bot=True)), [])


class PlanGatingTests(unittest.TestCase):
    def setUp(self):
        self.plan = "free"
        for p in (
            patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)),
            patch.object(bot, "ADMIN_ID", ADMIN),
            patch.object(bot, "plan_of", lambda uid: self.plan),
            patch.object(bot, "get_lang", lambda uid: "uz"),
            patch.object(db, "get_settings", return_value=_settings(name_clock_tz=None)),
            patch.object(db, "get_analytics_rows", return_value=[]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def datas(self, markup):
        return {b.callback_data: b.text for row in markup.inline_keyboard for b in row}

    def test_ranges_by_plan(self):
        for plan, days in (("free", 1), ("plus", 7), ("pro", 30), ("ultra", 30)):
            self.plan = plan
            self.assertEqual(bot.analytics_allowed_days(OWNER), days)

    def test_locked_buttons_for_free(self):
        _, m = bot.build_analytics_menu(OWNER)
        d = self.datas(m)
        self.assertNotIn("\U0001F512", d["an:1"])
        self.assertIn("\U0001F512", d["an:7"])
        self.assertIn("\U0001F512", d["an:30"])
        self.assertIn("\U0001F512", d["an_ch:1"])
        self.assertIn("\U0001F512", d["an_detail:1"])

    def test_ultra_has_no_locks_and_all_charts(self):
        self.plan = "ultra"
        _, m = bot.build_analytics_menu(OWNER, 30)
        self.assertFalse(any("\U0001F512" in v for v in self.datas(m).values()))
        self.assertEqual(bot.analytics_chart_kinds(OWNER), ["line", "pie", "bar"])

    def test_charts_by_plan(self):
        expected = {"free": [], "plus": ["line"], "pro": ["line", "pie"], "ultra": ["line", "pie", "bar"]}
        for plan, kinds in expected.items():
            self.plan = plan
            self.assertEqual(bot.analytics_chart_kinds(OWNER), kinds, plan)

    def test_locked_feature_mapping_and_locked_view(self):
        self.assertIsNone(bot.locked_feature_for("an:1"))
        self.assertIsNone(bot.locked_feature_for("an_menu"))
        self.assertEqual(bot.locked_feature_for("an:7"), "analytics_7")
        self.assertEqual(bot.locked_feature_for("an:30"), "analytics_30")
        self.assertEqual(bot.locked_feature_for("an_ch:7"), "analytics_charts")
        self.assertEqual(bot.locked_feature_for("an_detail:7"), "analytics_full")
        text, _ = bot.build_locked_view(OWNER, "analytics_7")
        self.assertIn("7", text)

    def test_menu_clamps_days_to_plan(self):
        text, _ = bot.build_analytics_menu(OWNER, 30)  # free
        self.assertIn(i18n.t("uz", "an_period_1"), text)

    def test_plan_features_text_mentions_analytics_per_plan(self):
        for plan in ("free", "plus", "pro", "ultra"):
            self.assertIn(i18n.t("uz", "pf_an_" + plan), bot.plan_features_text("uz", plan))

    def test_panel_has_analytics_button_for_everyone(self):
        for plan in ("free", "ultra"):
            self.plan = plan
            _, m = bot.build_panel(OWNER)
            self.assertIn("an_menu", self.datas(m))


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.rows = [(hour_ts(0, 9), "incoming", 6), (hour_ts(0, 9), "faq", 1), (hour_ts(0, 9), "ai", 2),
                     (hour_ts(0, 9), "static", 1), (hour_ts(0, 9), "sleep", 1), (hour_ts(2, 20), "incoming", 4),
                     (hour_ts(2, 20), "static", 3), (hour_ts(2, 20), "skipped", 1)]
        for p in (
            patch.object(bot, "ADMIN_ID", ADMIN),
            patch.object(bot, "get_lang", lambda uid: "uz"),
            patch.object(db, "get_settings", return_value={"name_clock_tz": "Asia/Tashkent"}),
            patch.object(db, "get_analytics_rows", side_effect=lambda owner, since: [r for r in self.rows if r[0] >= since]),
        ):
            p.start()
            self.addCleanup(p.stop)

    def test_menu_shows_all_numbers(self):
        text, _ = bot.build_analytics_menu(ADMIN, 1)
        for needle in ("AUTOREPLY ANALYTICS", "Kelgan xabarlar: 6", "Yuborilgan javoblar: 5", "Smart FAQ: 1",
                       "Gemini AI: 2", "Oddiy javoblar: 1", "Sleep Mode: 1", "09:00–11:00"):
            self.assertIn(needle, text)
        self.assertIn(i18n.t("uz", "an_privacy"), text)

    def test_empty_state_message(self):
        self.rows = []
        text, _ = bot.build_analytics_menu(ADMIN, 7)
        self.assertIn(i18n.t("uz", "an_empty"), text)

    def test_detail_report(self):
        text, markup = bot.build_analytics_detail(ADMIN, 7)
        self.assertIn("Kelgan: 10", text)
        self.assertIn("Yuborilgan: 8", text)
        self.assertIn("80%", text)
        self.assertIn("cooldown", text.lower())
        self.assertIn("1", text)
        self.assertEqual(markup.inline_keyboard[0][0].callback_data, "an:7")
        self.assertLess(len(text), 4096)
        text30, _ = bot.build_analytics_detail(ADMIN, 30)
        self.assertLess(len(text30), 4096)

    def test_timezone_follows_clock_zone_else_tashkent(self):
        with patch.object(db, "get_settings", return_value={"name_clock_tz": "Asia/Tokyo"}):
            self.assertEqual(str(bot.analytics_tz(1)), "Asia/Tokyo")
        with patch.object(db, "get_settings", return_value={"name_clock_tz": None}):
            self.assertIs(bot.analytics_tz(1), bot.TASHKENT_TZ)
        with patch.object(db, "get_settings", return_value={"name_clock_tz": "Mars/Base"}):
            self.assertIs(bot.analytics_tz(1), bot.TASHKENT_TZ)


class ButtonAndChartTests(unittest.TestCase):
    def setUp(self):
        self.plan = "pro"
        rows = [(hour_ts(d, 9 + d), k, c) for d in range(5) for k, c in (("incoming", 5), ("faq", 2), ("ai", 1), ("static", 1))]
        for p in (
            patch.object(bot, "FEATURE_PLANS", dict(bot.DEFAULT_FEATURE_PLANS)),
            patch.object(bot, "ADMIN_ID", ADMIN),
            patch.object(bot, "plan_of", lambda uid: self.plan),
            patch.object(bot, "get_lang", lambda uid: "uz"),
            patch.object(bot, "track_user"),
            patch.object(db, "get_settings", return_value={"name_clock_tz": None}),
            patch.object(db, "get_analytics_rows", side_effect=lambda owner, since: [r for r in rows if r[0] >= since]),
        ):
            p.start()
            self.addCleanup(p.stop)
        analytics._cache.clear()

    def press(self, data):
        q = MagicMock()
        q.data = data
        q.from_user.id = OWNER
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.chat_id = CHAT
        u = MagicMock()
        u.callback_query = q
        ctx = MagicMock()
        ctx.bot.send_photo = AsyncMock()
        ctx.bot.send_message = AsyncMock()
        asyncio.run(bot.on_button(u, ctx))
        return q, ctx

    def test_charts_sent_as_images_per_plan(self):
        for plan, n in (("plus", 1), ("pro", 2), ("ultra", 3)):
            self.plan = plan
            _, ctx = self.press("an_ch:7")
            self.assertEqual(ctx.bot.send_photo.await_count, n, plan)
            photo = ctx.bot.send_photo.await_args.kwargs["photo"]
            self.assertTrue(photo.startswith(b"\x89PNG"))

    def test_downgraded_user_cannot_get_30_day_charts(self):
        self.plan = "plus"  # eski Pro tugmasi (an_ch:30) hali ekranda
        q, ctx = self.press("an_ch:30")
        ctx.bot.send_photo.assert_not_awaited()
        self.assertIn(i18n.t("uz", "feature_an30"), q.edit_message_text.await_args.args[0])

    def test_charts_keep_selected_period(self):
        self.plan = "ultra"
        for days, key in ((1, "an_period_1"), (7, "an_period_7"), (30, "an_period_30")):
            _, ctx = self.press(f"an_ch:{days}")
            self.assertIn(i18n.t("uz", key), ctx.bot.send_photo.await_args.kwargs["caption"])

    def test_detail_keeps_selected_period(self):
        self.plan = "ultra"
        for days, key in ((1, "an_period_1"), (7, "an_period_7"), (30, "an_period_30")):
            q, _ = self.press(f"an_detail:{days}")
            self.assertIn(i18n.t("uz", key), q.edit_message_text.await_args.args[0])

    def test_free_user_gets_locked_view_instead_of_charts(self):
        self.plan = "free"
        q, ctx = self.press("an_ch:1")
        ctx.bot.send_photo.assert_not_awaited()
        q.edit_message_text.assert_awaited_once()

    def test_locked_range_shows_locked_view(self):
        self.plan = "plus"
        q, _ = self.press("an:30")
        text = q.edit_message_text.await_args.args[0]
        self.assertIn(i18n.t("uz", "feature_an30"), text)

    def test_range_and_detail_buttons_edit_message(self):
        self.plan = "ultra"
        q, _ = self.press("an:7")
        self.assertIn("AUTOREPLY ANALYTICS", q.edit_message_text.await_args.args[0])
        q, _ = self.press("an_detail:7")
        self.assertIn("BATAFSIL", q.edit_message_text.await_args.args[0])

    def test_empty_data_sends_message_not_charts(self):
        self.plan = "ultra"
        with patch.object(db, "get_analytics_rows", return_value=[]):
            _, ctx = self.press("an_ch:7")
        ctx.bot.send_photo.assert_not_awaited()
        ctx.bot.send_message.assert_awaited_once()

    def test_render_failure_reports_error(self):
        self.plan = "ultra"
        with patch.object(analytics, "render_chart", new=AsyncMock(side_effect=RuntimeError("boom"))):
            _, ctx = self.press("an_ch:7")
        self.assertIn(i18n.t("uz", "an_charts_failed"), ctx.bot.send_message.await_args.kwargs["text"])


class ChartTests(unittest.TestCase):
    def setUp(self):
        rows = [(hour_ts(d, 8 + d), k, c) for d in range(6) for k, c in (("incoming", 4), ("faq", 1), ("ai", 1), ("static", 1), ("sleep", 1))]
        self.summary = analytics.summarize(rows, 7, TZ)
        self.labels = bot.analytics_chart_labels("ru", "line")
        analytics._cache.clear()

    def test_all_charts_render_png_in_every_language(self):
        for lang in ("uz", "en", "ru"):
            for kind in ("line", "pie", "bar"):
                labels = bot.analytics_chart_labels(lang, kind)
                png = asyncio.run(analytics.render_chart(kind, OWNER, self.summary, labels))
                self.assertTrue(png.startswith(b"\x89PNG"), (lang, kind))

    def test_today_line_chart_renders_hourly(self):
        s = analytics.summarize([(hour_ts(0, 9), "incoming", 3), (hour_ts(0, 9), "static", 2)], 1, TZ)
        png = asyncio.run(analytics.render_chart("line", OWNER, s, bot.analytics_chart_labels("uz", "line")))
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_pie_without_sent_replies_still_renders(self):
        s = analytics.summarize([(hour_ts(0, 9), "incoming", 3)], 7, TZ)
        png = asyncio.run(analytics.render_chart("pie", OWNER, s, bot.analytics_chart_labels("uz", "pie")))
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_cache_key_covers_whole_daily_distribution(self):
        """Jami va oxirgi kun bir xil, lekin kunlar taqsimoti boshqa — keshdan eski grafik qaytmasligi kerak."""
        a = analytics.summarize([(hour_ts(1, 9), "incoming", 5), (hour_ts(0, 9), "incoming", 1)], 7, TZ)
        b = analytics.summarize([(hour_ts(1, 9), "incoming", 1), (hour_ts(0, 9), "incoming", 5)], 7, TZ)
        a["hourly"], b["hourly"] = list(a["hourly"]), list(a["hourly"])  # soatlar ham bir xil
        a["incoming"] = b["incoming"] = 6
        labels = bot.analytics_chart_labels("uz", "line")
        self.assertNotEqual(analytics._cache_key("line", OWNER, a, labels), analytics._cache_key("line", OWNER, b, labels))
        hash(analytics._cache_key("line", OWNER, a, labels))  # kalit hashlanadigan bo'lishi shart

    def test_identical_chart_is_cached(self):
        async def go():
            a = await analytics.render_chart("bar", OWNER, self.summary, self.labels)
            with patch.dict(analytics.RENDERERS, {"bar": MagicMock(side_effect=AssertionError("qayta chizilmasligi kerak"))}):
                b = await analytics.render_chart("bar", OWNER, self.summary, self.labels)
            return a, b
        a, b = asyncio.run(go())
        self.assertIs(a, b)

    def test_chart_labels_have_no_emoji(self):
        for lang in ("uz", "en", "ru"):
            for kind in ("line", "pie", "bar"):
                for v in bot.analytics_chart_labels(lang, kind).values():
                    self.assertTrue(all(ord(ch) < 0x2190 for ch in v), (lang, kind, v))


class I18nTests(unittest.TestCase):
    def test_privacy_text_mentions_separate_ai_history(self):
        for lang in ("uz", "en", "ru"):
            self.assertIn("Gemini", i18n.t(lang, "an_privacy"))

    def test_every_analytics_key_in_three_languages(self):
        keys = [k for k in i18n.T if k.startswith(("an_", "btn_an", "feature_an", "pf_an_", "btn_analytics"))]
        self.assertTrue(keys)
        for k in keys:
            for lang in ("uz", "en", "ru"):
                self.assertTrue(i18n.t(lang, k, **{n: 1 for n in ("period", "incoming", "sent", "faq", "ai", "static", "sleep", "peak",
                                                                   "rate", "skipped", "avg", "best_day", "hours", "days", "name")}))


if __name__ == "__main__":
    unittest.main()
