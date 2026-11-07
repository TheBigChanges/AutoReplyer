"""AI-Yordamchi oqimi: on_raw_update ichida AI javobi, limit, zaxira matn, pauza, panel."""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import ai  # noqa: E402
from telegram import Voice  # noqa: E402
from telegram.error import NetworkError  # noqa: E402
import bot  # noqa: E402
import db  # noqa: E402

OWNER = 1
ADMIN = 777
CHAT = 99


def _settings(**kw):
    base = {"offline": True, "auto_reply_text": "Oflaynman", "cooldown_hours": 3.0, "sleep_mode_enabled": False,
            "sleep_start_minutes": 1380, "sleep_end_minutes": 420, "sleep_reply_text": "",
            "ai_enabled": True, "ai_info": "Men dizaynerman", "ai_role": "seller"}
    base.update(kw)
    return base


def _update(text="Salom, narx qancha?", from_id=5, message_id=10):
    u = MagicMock()
    u.channel_post = None
    u.business_connection = None
    bm = MagicMock()
    bm.business_connection_id = "bc"
    bm.from_user.id = from_id
    bm.from_user.is_bot = False
    bm.chat.id = CHAT
    bm.message_id = message_id
    bm.text = text
    bm.caption = None
    u.business_message = bm
    return u


class Base(unittest.TestCase):
    def setUp(self):
        for target, value in (("ADMIN_ID", ADMIN),):
            p = patch.object(bot, target, value)
            p.start()
            self.addCleanup(p.stop)
        bot._bot_sent_ids.clear()

    def flow(self, update=None, owner=OWNER, settings=None, answer="Salom! Narx 100$.", quota=True,
             paused=False, configured=True, history=None, send_side_effect=None, paused_after_generate=False,
             history_error=None, add_error=None, gen_error=None, during_generate=None,
             attempt=True, seen=False, refund_effect=None, track=True, mark=True):
        update = update or _update()
        state = dict(settings or _settings())  # joriy sozlamalar (so'rov davomida o'zgartirilishi mumkin)
        sent = MagicMock(message_id=555)
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock(side_effect=send_side_effect, return_value=sent)
        conn = {"owner_user_id": owner, "is_enabled": True, "can_reply": True}
        async def generate(*a, **k):
            if during_generate:
                during_generate(state)  # Gemini ishlayotgan paytda egasi sozlamani o'zgartiradi
            if gen_error:
                raise gen_error
            return answer

        patches = {
            "conn": patch.object(db, "get_connection_by_business_id", return_value=conn),
            "settings": patch.object(db, "get_settings", side_effect=lambda o: dict(state)),
            "claim": patch.object(db, "try_claim_reply", return_value=123.0),
            "release": patch.object(db, "release_reply_claim"),
            "quota": patch.object(db, "try_consume_ai_quota", return_value=quota),
            "refund": patch.object(db, "refund_ai_quota", side_effect=refund_effect),
            "seen": patch.object(db, "ai_request_seen", return_value=seen),
            "attempt": patch.object(db, "try_consume_voice_attempt", **({"side_effect": attempt} if callable(attempt) else {"return_value": attempt})),
            "track": patch.object(db, "track_ai_request", return_value=track),
            "mark": patch.object(db, "mark_ai_request", **({"side_effect": mark} if callable(mark) else {"return_value": mark})),
            "usage": patch.object(db, "get_ai_usage", return_value=0),
            # paused_after_generate: pauza dastlabki ikki tekshiruvda (qabul + navbat) yo'q, Gemini javobi tayyor bo'lgach (egasi yozgan) yoqilgan
            "paused": patch.object(db, "is_ai_paused", side_effect=(lambda o, c, _n=[0]: (_n.__setitem__(0, _n[0] + 1) or _n[0] >= 3))
                                   if paused_after_generate else None, return_value=paused),
            "pause": patch.object(db, "pause_ai_chat"),
            "hist": patch.object(db, "get_ai_history", side_effect=history_error, return_value=history or []),
            "add": patch.object(db, "add_ai_messages", side_effect=add_error),
            "user": patch.object(db, "get_user", return_value={"full_name": "Dilshod"}),
            "conf": patch.object(ai, "is_configured", return_value=configured),
            "gen": patch.object(ai, "generate_reply", new=AsyncMock(side_effect=generate)),
        }
        started = {k: p.start() for k, p in patches.items()}
        for p in patches.values():
            self.addCleanup(p.stop)

        async def go():
            await bot.on_raw_update(update, ctx)
            await asyncio.gather(*list(bot._background_tasks))

        asyncio.run(go())
        return ctx.bot.send_message, started

    def texts(self, send):
        return [c.kwargs["text"] for c in send.call_args_list]


def _voice_update(duration=5, file_size=20000, mime="audio/ogg", message_id=10, caption=None):
    u = _update(text="", message_id=message_id)
    u.business_message.caption = caption
    u.business_message.voice = Voice("fid", "uid", duration, mime_type=mime, file_size=file_size)
    return u


class VoiceAiTests(Base):
    """Voice AI: ovozli xabar mavjud AI oqimidan o'tadi (limit, tarix, pauza, takroriy himoya, zaxira)."""

    def voice_flow(self, transcript="Assalomu alaykum, yetkazib berish bormi?", update=None, **kw):
        tr = AsyncMock(return_value=transcript)
        p = patch.object(bot, "transcribe_business_voice", new=tr)
        p.start()
        self.addCleanup(p.stop)
        send, m = self.flow(update=update or _voice_update(), **kw)
        return send, m, tr

    def test_voice_gets_text_ai_reply_and_history_has_transcript(self):
        send, m, tr = self.voice_flow()
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])
        tr.assert_awaited_once()
        hist = m["gen"].call_args.args[0]
        self.assertEqual(hist[-1], {"role": "user", "text": "Assalomu alaykum, yetkazib berish bormi?"})
        self.assertEqual(m["add"].call_args.args[2], [("user", "Assalomu alaykum, yetkazib berish bormi?"), ("model", "Salom! Narx 100$.")])
        m["quota"].assert_called_once()
        m["refund"].assert_not_called()

    def test_ai_disabled_uses_plain_autoreply_and_no_transcription(self):
        send, m, tr = self.voice_flow(settings=_settings(ai_enabled=False))
        self.assertEqual(self.texts(send), ["Oflaynman"])
        tr.assert_not_awaited()
        m["gen"].assert_not_awaited()

    def test_sleep_mode_beats_voice_ai(self):
        with patch.object(bot, "reply_state", return_value=(True, None)):
            send, m, tr = self.voice_flow(settings=_settings(sleep_mode_enabled=True))
        tr.assert_not_awaited()
        m["gen"].assert_not_awaited()

    def test_owner_chatting_blocks_voice_ai(self):
        send, m, tr = self.voice_flow(paused=True)
        self.assertEqual(self.texts(send), [])
        tr.assert_not_awaited()
        m["quota"].assert_not_called()

    def test_owner_wrote_during_transcription_cancels_and_refunds(self):
        send, m, tr = self.voice_flow(paused_after_generate=True)
        self.assertEqual(self.texts(send), [])
        tr.assert_awaited_once()
        m["gen"].assert_not_awaited()
        m["refund"].assert_called_once()
        m["claim"].assert_not_called()

    def test_too_long_voice_is_not_transcribed_and_uses_fallback_without_quota(self):
        send, m, tr = self.voice_flow(update=_voice_update(duration=ai.MAX_VOICE_SECONDS + 1))
        self.assertEqual(self.texts(send), ["Oflaynman"])
        tr.assert_not_awaited()
        m["quota"].assert_not_called()
        m["gen"].assert_not_awaited()

    def test_too_big_or_wrong_mime_voice_uses_fallback(self):
        for upd in (_voice_update(file_size=ai.MAX_VOICE_BYTES + 1, message_id=21), _voice_update(mime="audio/mpeg", message_id=22)):
            send, m, tr = self.voice_flow(update=upd)
            self.assertEqual(self.texts(send), ["Oflaynman"])
            tr.assert_not_awaited()

    def test_daily_limit_exhausted_makes_no_gemini_call(self):
        send, m, tr = self.voice_flow(quota=False)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        tr.assert_not_awaited()
        m["gen"].assert_not_awaited()

    def test_transcription_failure_falls_back_and_refunds(self):
        send, m, tr = self.voice_flow(transcript=None)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["refund"].assert_called_once()
        m["gen"].assert_not_awaited()
        m["add"].assert_not_called()

    def test_duplicate_voice_update_answers_once(self):
        send1, m1, tr1 = self.voice_flow()
        self.assertEqual(len(self.texts(send1)), 1)
        send2, m2 = self.flow(update=_voice_update())  # xuddi shu message_id qayta keldi
        self.assertEqual(self.texts(send2), [])
        m2["gen"].assert_not_awaited()
        m2["quota"].assert_not_called()

    def test_duplicate_after_failed_transcription_does_not_retranscribe(self):
        send1, m1, tr1 = self.voice_flow(transcript=None)
        send2, m2 = self.flow(update=_voice_update())
        tr1.assert_awaited_once()
        self.assertEqual(self.texts(send2), [])

    def test_failed_voice_transcriptions_respect_attempt_limit(self):
        """Muvaffaqiyatsiz transkripsiyalar AI limitini qaytarsa ham, Gemini'ga yuboriladigan urinishlar kunlik chegaradan oshmaydi."""
        used = []

        def attempt(owner, day, limit):
            if len(used) >= limit:
                return False
            used.append(1)
            return True

        tg_file = MagicMock(file_size=100)
        tg_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"abc"))
        fake_bot = MagicMock()
        fake_bot.get_file = AsyncMock(return_value=tg_file)
        real = bot.transcribe_business_voice

        async def via_fake_bot(_b, voice, attempt=None):
            return await real(fake_bot, voice, attempt=attempt)

        gemini = AsyncMock(return_value=None)  # Gemini har safar muvaffaqiyatsiz
        sent = []
        with patch.object(bot, "VOICE_ATTEMPTS_DAILY_LIMIT", 3), patch.object(bot, "transcribe_business_voice", new=via_fake_bot), \
                patch.object(ai, "transcribe_voice", new=gemini):
            for i in range(6):
                send, m = self.flow(update=_voice_update(message_id=100 + i), attempt=attempt)
                sent.append(self.texts(send))
        self.assertEqual(gemini.await_count, 3)                  # 4-6-urinishlar Gemini'ga yetmadi
        self.assertTrue(all(t == ["Oflaynman"] for t in sent))   # lekin mijozga zaxira matn ketdi
        self.assertEqual(m["refund"].call_count, 1)              # AI javob limiti qaytarildi (foydalanuvchi aybdor emas)

    def test_exhausted_voice_attempts_make_no_gemini_call_and_keep_ai_quota(self):
        tr = AsyncMock(side_effect=bot.VoiceAttemptsExhausted())
        with patch.object(bot, "transcribe_business_voice", new=tr):
            send, m = self.flow(update=_voice_update(message_id=32))
        m["gen"].assert_not_awaited()
        m["refund"].assert_called_once()
        self.assertEqual(self.texts(send), ["Oflaynman"])

    def test_admin_voice_is_not_attempt_limited(self):
        send, m, tr = self.voice_flow(owner=ADMIN, update=_voice_update(message_id=33))
        self.assertIsNone(tr.call_args.kwargs["attempt"])  # admin uchun urinish hisoblagichi yo'q
        tr.assert_awaited_once()

    def test_distinct_voice_messages_both_answered(self):
        self.voice_flow(update=_voice_update(message_id=1))
        send, m = self.flow(update=_voice_update(message_id=2))
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])

    def test_non_voice_media_keeps_plain_autoreply(self):
        # rasm/sticker: `bm.voice` Voice emas (None yoki boshqa) — AI ishlamaydi, odatiy matn ketadi
        for i, v in enumerate((None, MagicMock())):
            upd = _update(text="", message_id=30 + i)
            upd.business_message.voice = v
            send, m, tr = self.voice_flow(update=upd)
            self.assertEqual(self.texts(send), ["Oflaynman"])
            tr.assert_not_awaited()
            m["gen"].assert_not_awaited()

    def test_text_message_never_takes_voice_path(self):
        send, m, tr = self.voice_flow(update=_update(text="Salom"))
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])
        tr.assert_not_awaited()

    def test_voice_with_caption_transcribes_audio(self):
        send, m, tr = self.voice_flow(transcript="Ertaga soat uchga vaqt bormi?", update=_voice_update(caption="Salom"))
        tr.assert_awaited_once()  # audio eshitiladi, faqat caption emas
        sent_to_ai = m["gen"].call_args.args[0][-1]["text"]
        self.assertIn("Ertaga soat uchga vaqt bormi?", sent_to_ai)
        self.assertIn("Salom", sent_to_ai)  # caption qo'shimcha kontekst
        self.assertEqual(len(self.texts(send)), 1)

    def test_voice_caption_does_not_trigger_faq_or_automation(self):
        rule = {"id": 1, "action": {"text": "AUTOMATION"}}
        with patch.object(bot, "find_automation_rule", return_value=rule) as far, \
                patch.object(bot, "find_faq_answer", return_value="FAQ JAVOB") as ffa:
            send, m, tr = self.voice_flow(update=_voice_update(caption="narx"))
        far.assert_not_called()
        ffa.assert_not_called()
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])  # AI javobi, FAQ/Automation emas
        tr.assert_awaited_once()

    def test_voice_caption_with_ai_off_uses_plain_autoreply_not_faq(self):
        with patch.object(bot, "find_faq_answer", return_value="FAQ JAVOB") as ffa:
            send, m, tr = self.voice_flow(update=_voice_update(caption="narx", message_id=41), settings=_settings(ai_enabled=False))
        ffa.assert_not_called()
        self.assertEqual(self.texts(send), ["Oflaynman"])

    def test_photo_caption_still_uses_caption_as_text(self):
        upd = _update(text="", message_id=42)
        upd.business_message.caption = "Narxi qancha?"
        upd.business_message.voice = None
        send, m, tr = self.voice_flow(update=upd)
        tr.assert_not_awaited()
        self.assertEqual(m["gen"].call_args.args[0][-1]["text"], "Narxi qancha?")

    def test_admin_voice_unlimited_no_quota(self):
        send, m, tr = self.voice_flow(owner=ADMIN)
        self.assertEqual(len(self.texts(send)), 1)
        m["quota"].assert_not_called()


class TranscribeBusinessVoiceTests(unittest.TestCase):
    def _bot(self, data=b"abc", size=100, get_err=None, dl_err=None):
        tg_file = MagicMock(file_size=size)
        tg_file.download_as_bytearray = AsyncMock(side_effect=dl_err, return_value=bytearray(data))
        b = MagicMock()
        b.get_file = AsyncMock(side_effect=get_err, return_value=tg_file)
        return b

    def _run(self, b, voice, result="matn"):
        with patch.object(ai, "transcribe_voice", new=AsyncMock(return_value=result)) as tv:
            return asyncio.run(bot.transcribe_business_voice(b, voice)), tv

    def test_success_passes_bytes_and_mime(self):
        out, tv = self._run(self._bot(), Voice("f", "u", 5, mime_type="audio/ogg"))
        self.assertEqual(out, "matn")
        self.assertEqual(tv.call_args.args, (b"abc", "audio/ogg"))

    def test_missing_mime_defaults_to_ogg(self):
        out, tv = self._run(self._bot(), Voice("f", "u", 5))
        self.assertEqual(tv.call_args.args[1], "audio/ogg")

    def test_limits_checked_before_download(self):
        for v in (Voice("f", "u", 61), Voice("f", "u", 5, file_size=ai.MAX_VOICE_BYTES + 1), Voice("f", "u", 5, mime_type="video/mp4"), None):
            b = self._bot()
            out, tv = self._run(b, v)
            self.assertIsNone(out)
            b.get_file.assert_not_awaited()

    def test_telegram_download_failure_does_not_consume_voice_attempt(self):
        calls = []
        for kw in ({"get_err": NetworkError("x")}, {"dl_err": NetworkError("x")}, {"dl_err": OSError("x")}, {"data": b""},
                   {"size": ai.MAX_VOICE_BYTES + 1}):
            with patch.object(ai, "transcribe_voice", new=AsyncMock(return_value="m")) as tv:
                out = asyncio.run(bot.transcribe_business_voice(self._bot(**kw), Voice("f", "u", 5), attempt=lambda: calls.append(1) or True))
            self.assertIsNone(out)
            tv.assert_not_awaited()
        self.assertEqual(calls, [])  # urinish faqat Gemini'ga yuborishdan oldin sanaladi

    def test_attempt_is_consumed_right_before_gemini_and_exhaustion_blocks_it(self):
        order = []
        with patch.object(ai, "transcribe_voice", new=AsyncMock(side_effect=lambda *a: order.append("gemini") or "matn")) as tv:
            out = asyncio.run(bot.transcribe_business_voice(self._bot(), Voice("f", "u", 5), attempt=lambda: order.append("attempt") or True))
            self.assertEqual((out, order), ("matn", ["attempt", "gemini"]))
            tv.reset_mock()
            with self.assertRaises(bot.VoiceAttemptsExhausted):
                asyncio.run(bot.transcribe_business_voice(self._bot(), Voice("f", "u", 5), attempt=lambda: False))
            tv.assert_not_awaited()

    def test_timedelta_duration_supported(self):
        from datetime import timedelta
        v = MagicMock(spec=Voice)
        v.duration, v.file_size, v.mime_type, v.file_id = timedelta(seconds=30), 1000, "audio/ogg", "f"
        self.assertTrue(bot.voice_acceptable(v))
        v.duration = timedelta(seconds=90)
        self.assertFalse(bot.voice_acceptable(v))

    def test_download_errors_return_none(self):
        for kw in ({"get_err": NetworkError("x")}, {"dl_err": NetworkError("x")}, {"dl_err": OSError("x")}):
            out, tv = self._run(self._bot(**kw), Voice("f", "u", 5))
            self.assertIsNone(out)
            tv.assert_not_awaited()

    def test_empty_or_oversized_download_returns_none(self):
        for b in (self._bot(data=b""), self._bot(data=b"x" * (ai.MAX_VOICE_BYTES + 1)), self._bot(size=ai.MAX_VOICE_BYTES + 1)):
            out, tv = self._run(b, Voice("f", "u", 5))
            self.assertIsNone(out)
            tv.assert_not_awaited()


class AiPauseRecheckTests(Base):
    """Egasi chatga Gemini javob tayyorlayotgan paytda yozsa — hech narsa yuborilmaydi."""

    def test_owner_wrote_while_generating_blocks_ai_answer(self):
        send, m = self.flow(paused_after_generate=True)
        self.assertEqual(self.texts(send), [])
        m["gen"].assert_awaited_once()
        m["add"].assert_not_called()  # suhbat tarixiga ham yozilmaydi
        m["refund"].assert_called_once()  # sarflangan limit qaytariladi

    def test_owner_wrote_while_generating_blocks_fallback_text_too(self):
        send, m = self.flow(paused_after_generate=True, answer=None)
        self.assertEqual(self.texts(send), [])  # AI xato qilganda zaxira matn ham ketmaydi
        m["claim"].assert_not_called()

    def test_admin_without_quota_also_blocked(self):
        send, m = self.flow(owner=ADMIN, paused_after_generate=True)
        self.assertEqual(self.texts(send), [])
        m["refund"].assert_not_called()  # limit sarflanmagan edi

    def test_no_pause_still_sends(self):
        send, _ = self.flow()
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])


class AiSettingsRecheckTests(Base):
    """Gemini ishlayotgan paytda sozlama o'zgarsa — eski so'rov javobi yuborilmaydi (limit qaytariladi)."""

    def assert_dropped(self, mutate, **kw):
        send, m = self.flow(during_generate=mutate, **kw)
        self.assertEqual(self.texts(send), [])
        m["gen"].assert_awaited_once()
        m["add"].assert_not_called()
        m["refund"].assert_called_once()
        m["claim"].assert_not_called()  # zaxira matn ham ketmaydi

    def test_ai_turned_off_during_generation(self):
        self.assert_dropped(lambda st: st.update(ai_enabled=False))

    def test_owner_went_online_during_generation(self):
        self.assert_dropped(lambda st: st.update(offline=False))

    def test_sleep_mode_started_during_generation(self):
        with patch.object(bot, "is_within_sleep_window", return_value=True):
            def start_sleep(st):
                st.update(sleep_mode_enabled=True)
            self.assert_dropped(start_sleep)

    def test_plan_lost_ai_during_generation(self):
        state = {"ai": True}

        def revoke(st):
            state["ai"] = False

        with patch.object(bot, "has_feature", lambda uid, f: state["ai"] if f == "ai" else True):
            self.assert_dropped(revoke)

    def test_fallback_text_also_dropped_when_ai_failed_and_setting_changed(self):
        send, m = self.flow(answer=None, during_generate=lambda st: st.update(offline=False))
        self.assertEqual(self.texts(send), [])
        m["claim"].assert_not_called()

    def test_unchanged_settings_still_send(self):
        send, m = self.flow(during_generate=lambda st: st.update(auto_reply_text="boshqa matn"))
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])
        m["refund"].assert_not_called()

    def test_settings_changed_while_waiting_for_chat_lock_never_consumes_quota(self):
        with patch.object(bot, "ai_reply_still_allowed", return_value=False):
            send, m = self.flow()
        self.assertEqual(self.texts(send), [])
        m["quota"].assert_not_called()
        m["gen"].assert_not_awaited()

    def test_schedule_window_keeps_ai_allowed_when_owner_online(self):
        with patch.object(bot, "current_schedule_rule", lambda owner, st, now=None: {"id": 1}):
            send, _ = self.flow(settings=_settings(offline=False), during_generate=lambda st: None)
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])

    def test_schedule_window_closing_during_generation_drops_reply(self):
        window = {"open": True}
        with patch.object(bot, "current_schedule_rule", lambda owner, st, now=None: {"id": 1} if window["open"] else None):
            send, m = self.flow(settings=_settings(offline=False), during_generate=lambda st: window.update(open=False))
        self.assertEqual(self.texts(send), [])
        m["refund"].assert_called_once()


class AiQuotaSafetyNetTests(Base):
    """Kutilmagan xato bo'lsa band qilingan kunlik limit qaytariladi; yuborilgan javob uchun esa qaytarilmaydi."""

    def test_postgres_error_after_consuming_refunds_quota(self):
        send, m = self.flow(history_error=RuntimeError("connection lost"))
        self.assertEqual(self.texts(send), [])
        m["quota"].assert_called_once()
        m["refund"].assert_called_once()

    def test_unexpected_error_in_generation_refunds_quota(self):
        send, m = self.flow(gen_error=ValueError("boom"))
        self.assertEqual(self.texts(send), [])
        m["refund"].assert_called_once()

    def test_non_telegram_error_while_sending_refunds_quota(self):
        send, m = self.flow(send_side_effect=OSError("socket"))
        m["refund"].assert_called_once()

    def test_error_after_successful_send_does_not_refund(self):
        """Javob mijozga ketdi, keyin tarixni yozishda xato — limit sarflanganicha qoladi."""
        send, m = self.flow(add_error=RuntimeError("db down"))
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])
        m["refund"].assert_not_called()

    def test_successful_reply_does_not_refund(self):
        _, m = self.flow()
        m["refund"].assert_not_called()

    def test_refund_happens_only_once_on_handled_failures(self):
        _, m = self.flow(answer=None)  # AI javob bermadi: mavjud yo'l qaytaradi
        self.assertEqual(m["refund"].call_count, 1)
        _, m = self.flow(send_side_effect=__import__("telegram.error", fromlist=["TelegramError"]).TelegramError("x"))
        self.assertEqual(m["refund"].call_count, 1)
        _, m = self.flow(paused_after_generate=True)
        self.assertEqual(m["refund"].call_count, 1)

    def test_admin_never_consumes_or_refunds_on_error(self):
        _, m = self.flow(owner=ADMIN, history_error=RuntimeError("x"))
        m["quota"].assert_not_called()
        m["refund"].assert_not_called()

    def test_failing_refund_does_not_crash_the_flow(self):
        with patch.object(db, "refund_ai_quota", side_effect=RuntimeError("db")):
            send, _ = self.flow(history_error=RuntimeError("x"))
        self.assertEqual(self.texts(send), [])


class RefundReliabilityTests(Base):
    def test_refund_db_error_is_retried_with_same_request_key(self):
        """Refund DB xatosi bo'lsa — xuddi shu xabar kaliti bilan qayta uriniladi (idempotent), limit yo'qolib qolmaydi."""
        calls = []

        def refund(owner, day, request=None):
            calls.append(request)
            if len(calls) == 1:
                raise RuntimeError("db")

        self.flow(paused_after_generate=True, refund_effect=refund)
        self.assertEqual(calls, [(CHAT, 10), (CHAT, 10)])

    def test_refund_is_attempted_via_finally_when_every_try_fails_once(self):
        send, m = self.flow(history_error=RuntimeError("x"), refund_effect=RuntimeError("db"))
        self.assertEqual(self.texts(send), [])
        self.assertGreaterEqual(m["refund"].call_count, 3)

    def test_quota_and_refund_get_request_key(self):
        _, m = self.flow(paused_after_generate=True)
        self.assertEqual(m["quota"].call_args.kwargs["request"], (CHAT, 10))
        self.assertEqual(m["refund"].call_args.kwargs["request"], (CHAT, 10))

    def test_message_already_in_ledger_is_skipped_after_restart(self):
        """RAM bo'sh (qayta ishga tushish), lekin DB daftarida bu xabar bor: na AI, na limit, na zaxira matn."""
        bot._ai_answered.clear()
        send, m = self.flow(seen=True)
        self.assertEqual(self.texts(send), [])
        m["quota"].assert_not_called()
        m["gen"].assert_not_awaited()


class LedgerStateFlowTests(Base):
    def states(self, m):
        return [c.args[2] for c in m["mark"].call_args_list]

    def test_sending_is_marked_before_telegram_and_sent_after(self):
        order = []
        send, m = self.flow(mark=lambda o, r, st: order.append(("mark", st)) or True,
                            send_side_effect=lambda **k: order.append(("send",)) or MagicMock(message_id=1))
        self.assertEqual(order, [("mark", "sending"), ("send",), ("mark", "sent")])

    def test_unknown_send_outcome_is_marked_unknown_and_not_refunded(self):
        send, m = self.flow(send_side_effect=NetworkError("timeout"))
        self.assertEqual(self.states(m), ["sending", "unknown"])
        m["refund"].assert_not_called()

    def test_definite_telegram_error_refunds_instead_of_unknown(self):
        from telegram.error import BadRequest
        send, m = self.flow(send_side_effect=BadRequest("chat not found"))
        self.assertEqual(self.states(m), ["sending"])
        m["refund"].assert_called_once()

    def test_row_no_longer_ours_means_no_send(self):
        send, m = self.flow(mark=False)
        self.assertEqual(self.texts(send), [])
        m["refund"].assert_not_called()

    def test_admin_request_is_tracked_in_ledger_without_quota(self):
        send, m = self.flow(owner=ADMIN)
        m["track"].assert_called_once()
        m["quota"].assert_not_called()
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])

    def test_admin_duplicate_after_restart_is_not_reprocessed(self):
        bot._ai_answered.clear()  # restart: RAM bo'sh
        send, m = self.flow(owner=ADMIN, seen=True)
        self.assertEqual(self.texts(send), [])
        m["gen"].assert_not_awaited()
        send, m = self.flow(owner=ADMIN, track=False)  # daftar "takroriy" deydi
        self.assertEqual(self.texts(send), [])
        m["gen"].assert_not_awaited()

    def test_admin_failure_releases_ledger_without_touching_quota(self):
        send, m = self.flow(owner=ADMIN, history_error=RuntimeError("x"))
        self.assertIn("refunded", self.states(m))
        m["refund"].assert_not_called()


class RecoveryJobTests(unittest.TestCase):
    def test_job_calls_recovery_and_swallows_errors(self):
        with patch.object(db, "recover_orphaned_ai_requests", return_value=2) as r:
            asyncio.run(bot.ai_recovery_job(MagicMock()))
        r.assert_called_once()
        with patch.object(db, "recover_orphaned_ai_requests", side_effect=RuntimeError("db")):
            asyncio.run(bot.ai_recovery_job(MagicMock()))  # xato job'ni yiqitmaydi

    def test_job_is_scheduled_repeatedly_at_startup(self):
        src = (Path(__file__).resolve().parent.parent / "bot.py").read_text(encoding="utf-8")
        self.assertIn("run_repeating(ai_recovery_job, interval=60", src)


class AiReplyTests(Base):
    def test_ai_replies_instead_of_static_text(self):
        send, m = self.flow()
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])
        m["claim"].assert_not_called()  # AI yoqilganda cooldown ishlatilmaydi
        m["quota"].assert_called_once()
        m["add"].assert_called_once()
        msgs = m["add"].call_args.args[2]
        self.assertEqual(msgs, [("user", "Salom, narx qancha?"), ("model", "Salom! Narx 100$.")])
        self.assertIn((CHAT, 555), bot._bot_sent_ids)

    def test_generate_gets_history_plus_new_message_and_owner_info(self):
        _, m = self.flow(history=[{"role": "user", "text": "eski"}, {"role": "model", "text": "javob"}])
        hist, name, info, role = m["gen"].call_args.args
        self.assertEqual([h["text"] for h in hist], ["eski", "javob", "Salom, narx qancha?"])
        self.assertEqual((name, info, role), ("Dilshod", "Men dizaynerman", "seller"))

    def test_admin_has_no_limit(self):
        send, m = self.flow(owner=ADMIN)
        m["quota"].assert_not_called()
        self.assertEqual(len(self.texts(send)), 1)

    def test_limit_reached_falls_back_to_static_text(self):
        send, m = self.flow(quota=False)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()
        m["claim"].assert_called_once()

    def test_ai_failure_refunds_and_falls_back(self):
        send, m = self.flow(answer=None)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["refund"].assert_called_once()
        m["add"].assert_not_called()

    def test_telegram_send_failure_refunds_quota_and_saves_nothing(self):
        from telegram.error import BadRequest
        _, m = self.flow(send_side_effect=BadRequest("x"))
        m["refund"].assert_called_once()
        m["add"].assert_not_called()

    def test_non_text_message_uses_static_text(self):
        update = _update(text=None)
        send, m = self.flow(update=update)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()

    def test_caption_is_used_for_media(self):
        update = _update(text=None)
        update.business_message.caption = "Mana rasm"
        _, m = self.flow(update=update)
        self.assertEqual(m["gen"].call_args.args[0][-1]["text"], "Mana rasm")

    def test_paused_chat_gets_no_reply_at_all(self):
        send, m = self.flow(paused=True)
        send.assert_not_called()
        m["claim"].assert_not_called()

    def test_ai_off_keeps_old_behaviour(self):
        send, m = self.flow(settings=_settings(ai_enabled=False))
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()

    def test_not_configured_falls_back_to_static(self):
        send, m = self.flow(configured=False)
        self.assertEqual(self.texts(send), ["Oflaynman"])
        m["gen"].assert_not_awaited()

    def test_online_owner_gets_no_ai_reply(self):
        send, m = self.flow(settings=_settings(offline=False))
        send.assert_not_called()
        m["gen"].assert_not_awaited()


class TakeoverTests(Base):
    def test_owner_message_pauses_chat(self):
        send, m = self.flow(update=_update(from_id=OWNER))
        m["pause"].assert_called_once_with(OWNER, CHAT, bot.AI_TAKEOVER_PAUSE_SECONDS)
        send.assert_not_called()

    def test_bots_own_echo_does_not_pause(self):
        bot._bot_sent_ids.append((CHAT, 10))
        _, m = self.flow(update=_update(from_id=OWNER, message_id=10))
        m["pause"].assert_not_called()

    def test_no_pause_when_ai_off(self):
        _, m = self.flow(update=_update(from_id=OWNER), settings=_settings(ai_enabled=False))
        m["pause"].assert_not_called()


class PanelTests(Base):
    def _query(self, data, user_id=OWNER):
        q = MagicMock()
        q.data = data
        q.from_user.id = user_id
        q.answer = AsyncMock()
        q.edit_message_text = AsyncMock()
        q.message.reply_text = AsyncMock()
        u = MagicMock()
        u.callback_query = q
        return u, q

    def test_panel_has_ai_button_and_support_stays_out(self):
        with patch.object(db, "get_settings", return_value=_settings(ai_enabled=False)):
            text, markup = bot.build_panel(OWNER)
        datas = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn("ai_menu", datas)
        self.assertNotIn("support", datas)
        self.assertIn("AI-Yordamchi: o'chirilgan", text)

    def test_panel_hides_static_text_when_ai_on(self):
        with patch.object(db, "get_settings", return_value=_settings()):
            text, _ = bot.build_panel(OWNER)
        self.assertNotIn("Xabar: Oflaynman", text)
        self.assertIn("AI-Yordamchi yoqilgan", text)

    def test_menu_shows_usage_and_unlimited_for_admin(self):
        with patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "get_ai_usage", return_value=3):
            self.assertIn("3/50", bot.build_ai_menu(OWNER)[0])
            self.assertIn("cheklovsiz", bot.build_ai_menu(ADMIN)[0])

    def test_toggle_on_requires_configuration(self):
        u, q = self._query("ai_on")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings(ai_enabled=False)), \
             patch.object(db, "update_settings") as upd, \
             patch.object(ai, "is_configured", return_value=False):
            asyncio.run(bot.on_button(u, MagicMock()))
        upd.assert_not_called()
        self.assertIn("GEMINI_API_KEY", q.edit_message_text.call_args.args[0])
        q.answer.assert_awaited_once()

    def test_toggle_on_and_off(self):
        for data, current, expected in (("ai_on", False, True), ("ai_off", True, False)):
            u, q = self._query(data)
            with patch.object(bot, "track_user"), \
                 patch.object(db, "get_settings", return_value=_settings(ai_enabled=current)), \
                 patch.object(db, "update_settings") as upd, \
                 patch.object(ai, "is_configured", return_value=True):
                asyncio.run(bot.on_button(u, MagicMock()))
            upd.assert_called_once_with(OWNER, ai_enabled=expected)

    def test_edit_info_flow(self):
        u, q = self._query("ai_edit_info")
        with patch.object(bot, "track_user"):
            asyncio.run(bot.on_button(u, MagicMock()))
        self.assertEqual(bot.get_pending_action(OWNER), "ai_info")

        def text_update(t):
            tu = MagicMock()
            tu.effective_user = MagicMock(id=OWNER, is_bot=False)
            tu.message.text = t
            tu.message.reply_text = AsyncMock()
            return tu

        too_long = text_update("x" * (bot.AI_INFO_MAX_LENGTH + 1))
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_text(too_long, MagicMock()))
        upd.assert_not_called()
        self.assertEqual(bot.get_pending_action(OWNER), "ai_info")

        ok = text_update("Men dizaynerman")
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd, \
             patch.object(db, "get_settings", return_value=_settings()):
            asyncio.run(bot.on_text(ok, MagicMock()))
        upd.assert_called_once_with(OWNER, ai_info="Men dizaynerman")
        self.assertIsNone(bot.get_pending_action(OWNER))

        clear = text_update("-")
        bot.set_pending_action(OWNER, "ai_info")
        with patch.object(bot, "track_user"), patch.object(db, "update_settings") as upd, \
             patch.object(db, "get_settings", return_value=_settings()):
            asyncio.run(bot.on_text(clear, MagicMock()))
        upd.assert_called_once_with(OWNER, ai_info=None)

    def test_roles_menu_marks_current_and_lists_all(self):
        with patch.object(db, "get_settings", return_value=_settings(ai_role="support")):
            text, markup = bot.build_ai_roles_menu(OWNER)
        labels = {b.callback_data: b.text for row in markup.inline_keyboard for b in row}
        for key in ai.ROLES:
            self.assertIn(f"ai_role:{key}", labels)
        self.assertTrue(labels["ai_role:support"].startswith("\u2705"))
        self.assertFalse(labels["ai_role:seller"].startswith("\u2705"))

    def test_main_ai_menu_shows_role_and_button(self):
        with patch.object(db, "get_settings", return_value=_settings(ai_role=None)):
            text, markup = bot.build_ai_menu(OWNER)
        self.assertIn(ai.role_label(None), text)
        self.assertIn("ai_roles", [b.callback_data for row in markup.inline_keyboard for b in row])

    def test_choosing_role_saves_it(self):
        u, q = self._query("ai_role:support")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_button(u, MagicMock()))
        upd.assert_called_once_with(OWNER, ai_role="support")
        q.answer.assert_awaited_once()

    def test_unknown_role_is_ignored(self):
        u, q = self._query("ai_role:hacker")
        with patch.object(bot, "track_user"), patch.object(db, "get_settings", return_value=_settings()), \
             patch.object(db, "update_settings") as upd:
            asyncio.run(bot.on_button(u, MagicMock()))
        upd.assert_not_called()

    def test_role_whitelisted_in_db(self):
        self.assertIn("ai_role", db.ALLOWED_SETTINGS_FIELDS)

    def test_settings_whitelist_accepts_ai_fields(self):
        self.assertTrue({"ai_enabled", "ai_info"} <= db.ALLOWED_SETTINGS_FIELDS)


class DisconnectTests(Base):
    def test_disconnect_deletes_ai_data(self):
        u = MagicMock()
        u.channel_post = None
        u.business_message = None
        conn = u.business_connection
        conn.user.id = OWNER
        conn.is_enabled = False
        conn.can_reply = True
        ctx = MagicMock()
        ctx.bot.send_message = AsyncMock()
        with patch.object(db, "upsert_connection"), patch.object(db, "delete_ai_data") as d:
            asyncio.run(bot.on_raw_update(u, ctx))
        d.assert_called_once_with(OWNER)


if __name__ == "__main__":
    unittest.main()


class AiPlusStaticDuplicateTests(Base):
    """Takroriy javob himoyasi aniq kiruvchi xabar (message_id) bo'yicha ishlaydi, butun suhbat bo'yicha emas."""

    def setUp(self):
        super().setUp()
        bot._ai_answered.clear()

    def test_second_distinct_message_gets_fallback_when_ai_fails(self):
        bot._ai_answered[(OWNER, CHAT, 10)] = __import__("time").time()  # oldingi xabarga AI javob bergan
        send, m = self.flow(update=_update(message_id=11), answer=None)
        self.assertEqual(self.texts(send), ["Oflaynman"])

    def test_new_media_message_not_suppressed_by_previous_ai_reply(self):
        bot._ai_answered[(OWNER, CHAT, 10)] = __import__("time").time()
        send, _ = self.flow(update=_update(text=None, message_id=11))
        self.assertEqual(self.texts(send), ["Oflaynman"])

    def test_same_message_already_answered_gets_no_fallback(self):
        bot._ai_answered[(OWNER, CHAT, 10)] = __import__("time").time()
        send, m = self.flow(update=_update(message_id=10), answer=None)
        send.assert_not_called()

    def test_successful_ai_reply_marks_message(self):
        send, _ = self.flow()
        self.assertEqual(self.texts(send), ["Salom! Narx 100$."])
        self.assertTrue(bot._ai_answered_message(OWNER, CHAT, 10))
        self.assertFalse(bot._ai_answered_message(OWNER, CHAT, 11))

    def test_same_incoming_message_does_not_generate_or_send_twice(self):
        send1, m1 = self.flow()
        self.assertEqual(send1.await_count, 1)
        send2, m2 = self.flow()  # xuddi shu message_id qayta qayta ishlanadi
        send2.assert_not_called()
        m2["gen"].assert_not_awaited()
        m2["quota"].assert_not_called()

    def test_duplicate_message_when_ai_quota_exhausted_sends_no_fallback(self):
        bot._ai_answered[(OWNER, CHAT, 10)] = __import__("time").time()
        send, m = self.flow(quota=False)
        send.assert_not_called()
        m["gen"].assert_not_awaited()

    def test_ai_send_timeout_preserves_uncertain_delivery_state(self):
        from telegram.error import TimedOut
        send, m = self.flow(send_side_effect=TimedOut())
        m["refund"].assert_not_called()   # limit qaytarilmaydi
        m["add"].assert_called_once()
        self.assertEqual(m["add"].call_args.args[2], [("user", "Salom, narx qancha?")])  # AI javobi tarixga yozilmaydi
        self.assertTrue(bot._ai_answered_message(OWNER, CHAT, 10))
        self.assertEqual(send.await_count, 1)  # zaxira matn ham yuborilmaydi

    def test_ai_definite_rejection_still_refunds(self):
        from telegram.error import BadRequest
        _, m = self.flow(send_side_effect=BadRequest("x"))
        m["refund"].assert_called_once()
        m["add"].assert_not_called()
        self.assertFalse(bot._ai_answered_message(OWNER, CHAT, 10))


class AutoReplyUnknownOutcomeTests(unittest.TestCase):
    def _run(self, exc):
        bm = MagicMock()
        bm.business_connection_id = "bc"
        b = MagicMock()
        b.send_message = AsyncMock(side_effect=exc)
        with patch.object(db, "try_claim_reply", return_value=5.0), patch.object(db, "release_reply_claim") as rel:
            asyncio.run(bot.send_auto_reply(b, bm, OWNER, CHAT, "x", 3.0, "lbl"))
        return rel

    def test_autoreply_network_timeout_does_not_release_claim_unsafely(self):
        from telegram.error import NetworkError, TimedOut
        self._run(NetworkError("conn")).assert_not_called()
        self._run(TimedOut()).assert_not_called()

    def test_definite_rejection_releases_claim(self):
        from telegram.error import BadRequest, Forbidden
        self._run(BadRequest("chat not found")).assert_called_once()
        self._run(Forbidden("blocked")).assert_called_once()


class TimeDictPruneTests(unittest.TestCase):
    def test_prune_removes_only_old_entries_when_large(self):
        import time
        d = {i: time.time() - 7200 for i in range(600)}
        d[9999] = time.time()
        bot._prune_times(d, 3600.0)
        self.assertEqual(list(d), [9999])

    def test_small_dict_untouched(self):
        import time
        d = {1: time.time() - 7200}
        bot._prune_times(d, 3600.0)
        self.assertEqual(len(d), 1)


class FaqAiModeDuplicateTests(unittest.TestCase):
    def setUp(self):
        bot._ai_answered.clear()
        self.addCleanup(bot._ai_answered.clear)

    def _bm(self, mid):
        bm = MagicMock()
        bm.business_connection_id = "bc"
        bm.message_id = mid
        return bm

    def _send(self, b, mid, side=None):
        if side is not None:
            b.send_message.side_effect = side
        asyncio.run(bot.send_faq_reply(b, self._bm(mid), OWNER, CHAT, "Javob", 3.0, "lbl", True))

    def _bot(self):
        b = MagicMock()
        b.send_message = AsyncMock(return_value=MagicMock(message_id=1))
        return b

    def test_duplicate_faq_update_in_ai_mode_sends_only_one_reply(self):
        b = self._bot()
        self._send(b, 100)
        self._send(b, 100)
        self.assertEqual(b.send_message.await_count, 1)

    def test_new_message_id_faq_still_answered_in_ai_mode(self):
        b = self._bot()
        self._send(b, 100)
        self._send(b, 101)
        self.assertEqual(b.send_message.await_count, 2)

    def test_concurrent_duplicate_faq_sends_once(self):
        b = self._bot()

        async def go():
            await asyncio.gather(*[bot.send_faq_reply(b, self._bm(200), OWNER, CHAT, "J", 3.0, "l", True) for _ in range(5)])
        asyncio.run(go())
        self.assertEqual(b.send_message.await_count, 1)

    def test_faq_timeout_marks_answered_but_definite_failure_does_not(self):
        from telegram.error import BadRequest, TimedOut
        b = self._bot()
        self._send(b, 300, side=TimedOut())
        self._send(b, 300, side=None)
        self.assertEqual(b.send_message.await_count, 1)  # noma'lum natija: qayta yuborilmaydi
        b2 = self._bot()
        self._send(b2, 301, side=BadRequest("x"))
        b2.send_message.side_effect = None
        self._send(b2, 301)
        self.assertEqual(b2.send_message.await_count, 2)  # aniq rad etish: qayta urinish mumkin


class IncomingDedupTests(Base):
    def test_duplicate_business_message_counts_incoming_once(self):
        calls = []
        with patch.object(bot, "track_analytics", lambda o, k: calls.append(k)):
            self.flow(settings=_settings(offline=False, ai_enabled=False))
            self.flow(settings=_settings(offline=False, ai_enabled=False))  # xuddi shu message_id
            self.flow(update=_update(message_id=11), settings=_settings(offline=False, ai_enabled=False))
        self.assertEqual(calls.count("incoming"), 2)

    def test_first_time_seen_unknown_id_always_counts(self):
        self.assertTrue(bot._first_time_seen(1, 2, None))
        self.assertTrue(bot._first_time_seen(1, 2, None))
