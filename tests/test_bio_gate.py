"""Bepul tarifda ism soati: "Edit bio" ruxsati shart (yoqishda + har 5 daqiqada tekshiruv)."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import bot  # noqa: E402
from i18n import t  # noqa: E402
from telegram.error import NetworkError  # noqa: E402

OWNER = 555


def run(coro):
    return asyncio.run(coro)


def live(can_name=True, can_bio=True, enabled=True):
    return SimpleNamespace(is_enabled=enabled, rights=SimpleNamespace(can_edit_name=can_name, can_edit_bio=can_bio))


class EnableTests(unittest.TestCase):
    def _enable(self, *, free, rights, conn_bio=True):
        b = MagicMock()
        b.get_business_connection = AsyncMock(return_value=rights)
        conn = {"is_enabled": True, "business_connection_id": "c", "can_reply": True, "can_edit_bio": conn_bio, "can_edit_name": True}
        with patch.object(bot, "shows_ads", lambda *a, **k: free), \
             patch.object(bot.db, "get_connection", return_value=conn), \
             patch.object(bot.db, "upsert_connection") as up, \
             patch.object(bot, "capture_base_name", AsyncMock(return_value=("Ali", ""))), \
             patch.object(bot.db, "get_settings", return_value={}), \
             patch.object(bot.db, "update_settings") as upd, \
             patch.object(bot, "spawn_background", lambda c: c.close()), \
             patch.object(bot, "get_lang", return_value="uz"):
            msg = run(bot._enable_name_clock(b, OWNER))
        return msg, up, upd

    def test_free_without_bio_refused(self):
        msg, up, upd = self._enable(free=True, rights=live(can_bio=False))
        self.assertEqual(msg, t("uz", "nc_need_bio"))
        upd.assert_not_called()
        self.assertFalse(up.call_args.kwargs["can_edit_bio"])  # jonli qiymat saqlanadi

    def test_free_with_bio_enabled(self):
        msg, _, upd = self._enable(free=True, rights=live(can_bio=True), conn_bio=False)
        self.assertEqual(msg, t("uz", "nc_enabled"))
        self.assertIs(upd.call_args.kwargs["clock_bio_notified"], False)

    def test_paid_or_admin_not_required(self):
        msg, _, _ = self._enable(free=False, rights=live(can_bio=False))
        self.assertEqual(msg, t("uz", "nc_enabled"))

    def test_both_missing_one_message(self):
        msg, _, _ = self._enable(free=True, rights=live(can_name=False, can_bio=False))
        self.assertIn(t("uz", "nc_need_right"), msg)
        self.assertIn(t("uz", "nc_need_bio"), msg)


class GateTests(unittest.TestCase):
    def test_bio_gate_ok(self):
        tgt = {"owner_user_id": OWNER, "plan": "free", "can_edit_bio": False}
        with patch.object(bot, "shows_ads", lambda *a, **k: True):
            self.assertFalse(bot.bio_gate_ok(tgt))
            self.assertTrue(bot.bio_gate_ok({**tgt, "can_edit_bio": True}))
        with patch.object(bot, "shows_ads", lambda *a, **k: False):
            self.assertTrue(bot.bio_gate_ok(tgt))

    def test_apply_gate_notifies_once_and_restores(self):
        b = MagicMock()
        flags = iter([True, False])  # birinchi chaqiruv o'zgartiradi, ikkinchisi — yo'q
        with patch.object(bot.db, "set_bio_gate_flag", side_effect=lambda *a: next(flags)), \
             patch.object(bot, "restore_base_name", AsyncMock()) as rest, \
             patch.object(bot, "_notify_owner", AsyncMock()) as notify, \
             patch.object(bot, "get_lang", return_value="uz"):
            run(bot.apply_bio_gate(b, OWNER, False))
            run(bot.apply_bio_gate(b, OWNER, False))
        rest.assert_awaited_once()
        notify.assert_awaited_once_with(b, OWNER, t("uz", "nc_bio_stopped"))

    def test_apply_gate_resumes_once(self):
        b = MagicMock()
        flags = iter([True, False])
        with patch.object(bot.db, "set_bio_gate_flag", side_effect=lambda *a: next(flags)), \
             patch.object(bot.db, "update_settings") as upd, \
             patch.object(bot, "_notify_owner", AsyncMock()) as notify, \
             patch.object(bot, "get_lang", return_value="uz"):
            run(bot.apply_bio_gate(b, OWNER, True))
            run(bot.apply_bio_gate(b, OWNER, True))
        notify.assert_awaited_once_with(b, OWNER, t("uz", "nc_bio_restored"))
        upd.assert_called_once_with(OWNER, name_clock_applied=None)


class ReconcileTests(unittest.TestCase):
    def _run(self, row, get_conn, free=True):
        b = MagicMock()
        b.get_business_connection = get_conn
        with patch.object(bot, "shows_ads", lambda *a, **k: free), \
             patch.object(bot.db, "get_name_clock_targets", return_value=[row]), \
             patch.object(bot.db, "set_can_edit_bio") as sync, \
             patch.object(bot.db, "set_bio_gate_flag", return_value=False), \
             patch.object(bot.db, "update_settings"), \
             patch.object(bot, "apply_bio_gate", AsyncMock()) as gate, \
             patch.object(bot.asyncio, "sleep", AsyncMock()):
            run(bot.reconcile_bio_gate(b))
        return gate, sync

    ROW = {"owner_user_id": OWNER, "plan": "free", "business_connection_id": "c", "can_edit_bio": True, "clock_bio_notified": False}

    def test_missing_bio_triggers_gate_and_syncs(self):
        gate, sync = self._run(self.ROW, AsyncMock(return_value=live(can_bio=False)))
        gate.assert_awaited_once()
        self.assertIs(gate.await_args.args[2], False)
        sync.assert_called_once_with(OWNER, False)

    def test_unknown_rights_do_not_pause(self):
        gate, _ = self._run(self.ROW, AsyncMock(return_value=SimpleNamespace(is_enabled=True, rights=None)))
        gate.assert_not_awaited()

    def test_telegram_error_does_not_pause(self):
        gate, _ = self._run(self.ROW, AsyncMock(side_effect=NetworkError("x")))
        gate.assert_not_awaited()

    def test_paid_plan_skipped(self):
        get = AsyncMock()
        gate, _ = self._run(self.ROW, get, free=False)
        gate.assert_not_awaited()
        get.assert_not_awaited()


class TickAndJobTests(unittest.TestCase):
    def test_tick_skips_paused_free_target(self):
        target = {"owner_user_id": OWNER, "plan": "free", "can_edit_bio": False}
        with patch.object(bot, "shows_ads", lambda *a, **k: True), \
             patch.object(bot.db, "get_name_clock_targets", return_value=[target]), \
             patch.object(bot, "sub_ok_sync", return_value=True), \
             patch.object(bot, "_apply_clock", AsyncMock()) as apply:
            run(bot.name_clock_tick(MagicMock(), 1_700_000_000.0))
        apply.assert_not_awaited()

    def test_job_registered_every_5_minutes(self):
        src = Path(bot.__file__).read_text()
        self.assertIn("run_repeating(bio_gate_check_job, interval=300", src)


if __name__ == "__main__":
    unittest.main()
