"""Umumiy sozlama: eski testlar til tanlash bosqichisiz (til allaqachon tanlangan) ishlaydi.
Til tanlashning o'zi tests/test_i18n_flow.py da alohida tekshiriladi."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
    monkeypatch.setattr(bot, "find_kb_context", lambda owner_id, messages: [])  # Knowledge Base testlari o'zi yoqadi
    monkeypatch.setattr(bot, "onboarding_start_view", lambda owner_id: None)  # onboarding testlari o'zi yoqadi
    monkeypatch.setattr(bot, "onboarding_view_on_connection", lambda owner_id: None)
    monkeypatch.setattr(bot, "shows_ads", lambda *a, **k: False)  # reklama testlari o'zi yoqadi
    monkeypatch.setattr(bot, "NAME_CLOCK_RATE_PER_SEC", 100000.0)  # testlarda sekinlashtirmaslik
    yield
    bot._lang_cache.clear()
