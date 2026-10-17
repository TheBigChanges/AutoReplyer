"""Umumiy sozlama: eski testlar til tanlash bosqichisiz (til allaqachon tanlangan) ishlaydi.
Til tanlashning o'zi tests/test_i18n_flow.py da alohida tekshiriladi."""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---- Test bazasi xavfsizligi -------------------------------------------------------------------
# Testlar HECH QACHON ishchi (production) bazaga tegmasligi kerak. Shu uchun test modullari import
# qilinishidan OLDIN DATABASE_URL majburan test bazasiga o'rnatiladi (yoki TEST_DATABASE_URL yo'q bo'lsa —
# soxta manzilga, shunda bazaga bog'liq testlar o'tkazib yuboriladi). Muhitdagi haqiqiy DATABASE_URL
# ishlatilmaydi. Test bazasi faqat lokal (localhost/127.0.0.1/::1/unix socket) bo'lishi shart; boshqa
# (masalan, bulutdagi) bazaga ruxsat berish uchun ALLOW_REMOTE_TEST_DB=1 qo'yilishi kerak.
_LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}
_test_db_url = os.environ.get("TEST_DATABASE_URL", "").strip()
if _test_db_url:
    _host = (urlparse(_test_db_url).hostname or "").lower()
    if _host not in _LOCAL_HOSTS and os.environ.get("ALLOW_REMOTE_TEST_DB") != "1":
        pytest.exit(
            f"TEST_DATABASE_URL lokal emas ({_host!r}). Testlar faqat lokal test bazasida ishlaydi; "
            "boshqa bazaga ataylab ruxsat berish uchun ALLOW_REMOTE_TEST_DB=1 qo'ying.",
            returncode=2,
        )
os.environ["DATABASE_URL"] = _test_db_url or "postgresql://fake/fake"


@pytest.fixture(autouse=True)
def _language_already_chosen(monkeypatch):
    try:
        import bot
    except Exception:  # BOT_TOKEN yo'q va h.k. — alohida testlar o'zi hal qiladi
        yield
        return
    bot._lang_cache.clear()
    monkeypatch.setattr(bot, "has_chosen_lang", lambda user_id: True)
    # Eski testlar tarif cheklovisiz ishlaydi; cheklovlarning o'zi tests/test_plan_features.py da tekshiriladi
    everyone = ("free", "plus", "pro", "ultra")
    monkeypatch.setattr(bot, "FEATURE_PLANS", {k: everyone for k in bot.DEFAULT_FEATURE_PLANS})
    monkeypatch.setattr(bot, "find_faq_answer", lambda owner_id, text: None)  # FAQ testlari o'zi yoqadi
    monkeypatch.setattr(bot, "onboarding_step_of", lambda owner_id: "legacy")  # onboarding testlari o'zi yoqadi
    monkeypatch.setattr(bot, "find_kb_context", lambda owner_id, messages: [])  # Knowledge Base testlari o'zi yoqadi
    monkeypatch.setattr(bot, "onboarding_start_view", lambda owner_id: None)  # onboarding testlari o'zi yoqadi
    monkeypatch.setattr(bot, "onboarding_view_on_connection", lambda owner_id: None)
    monkeypatch.setattr(bot, "shows_ads", lambda *a, **k: False)  # reklama testlari o'zi yoqadi
    monkeypatch.setattr(bot, "track_analytics", lambda owner_id, kind: None)  # analytics testlari o'zi yoqadi
    monkeypatch.setattr(bot, "NAME_CLOCK_RATE_PER_SEC", 100000.0)  # testlarda sekinlashtirmaslik
    yield
    bot._lang_cache.clear()
