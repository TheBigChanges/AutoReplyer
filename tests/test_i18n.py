"""Ko'p tillilik: lug'at yaxlitligi va sof yordamchilar."""
import os
import re
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123:dummy")
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")

import ai  # noqa: E402
import i18n  # noqa: E402
import logic  # noqa: E402

PH = re.compile(r"\{(\w+)\}")


class DictionaryTests(unittest.TestCase):
    def test_every_key_has_all_languages_with_same_placeholders(self):
        for key, entry in i18n.T.items():
            for lang in i18n.LANGS:
                self.assertTrue(entry.get(lang, "").strip(), f"{key}/{lang} bo'sh")
            base = set(PH.findall(entry["uz"]))
            for lang in ("en", "ru"):
                self.assertEqual(set(PH.findall(entry[lang])) - {"unit"}, base, f"{key}/{lang}: placeholderlar farq qiladi")

    def test_every_key_formats_without_error(self):
        for key, entry in i18n.T.items():
            kw = {n: "X" for n in PH.findall(entry["uz"])}
            for lang in i18n.LANGS:
                i18n.t(lang, key, **kw)

    def test_translations_are_really_translated(self):
        # Ingliz/rus matni o'zbekchaning nusxasi bo'lmasligi kerak (nomlar/emoji bundan mustasno)
        same = [k for k, e in i18n.T.items()
                if e["en"] == e["uz"] and re.search(r"[A-Za-z]{4,}", e["uz"].replace("{", "").replace("}", ""))
                and not k.startswith(("zone_", "lang_", "btn_language", "plan_name_"))]
        allowed = {"lang_pick", "btn_faq", "feature_faq"}  # "Smart FAQ" — brend nomi
        self.assertEqual([k for k in same if k not in allowed], [], "tarjima qilinmagan kalitlar")

    def test_russian_is_cyrillic(self):
        for k, e in i18n.T.items():
            if k in ("btn_faq", "feature_faq") or k.startswith(("lang_", "btn_language", "plan_name_plus", "plan_name_pro", "plan_name_ultra")):
                continue
            self.assertTrue(re.search(r"[А-Яа-я]", e["ru"]), f"{k}: ruscha matnda kirill yo'q")

    def test_fallbacks(self):
        self.assertEqual(i18n.t("xx", "saved"), i18n.T["saved"]["uz"])
        self.assertEqual(i18n.t("en", "no_such_key"), "no_such_key")
        self.assertEqual(i18n.normalize_lang(None), "uz")
        self.assertTrue(i18n.is_lang("ru"))
        self.assertFalse(i18n.is_lang("de"))

    def test_default_texts_detected_in_every_language(self):
        for key in ("default_auto_reply", "default_sleep"):
            self.assertEqual(len(i18n.all_defaults(key)), 3)

    def test_days_unit(self):
        self.assertEqual(i18n.days_unit("en", 1), "day")
        self.assertEqual(i18n.days_unit("en", 5), "days")
        self.assertEqual([i18n.days_unit("ru", n) for n in (1, 2, 5, 11, 21, 22, 25)],
                         ["день", "дня", "дней", "дней", "день", "дня", "дней"])


class LogicLangTests(unittest.TestCase):
    def test_cooldown_format(self):
        self.assertEqual(logic.format_cooldown(2.5, "en"), "2 h 30 min")
        self.assertEqual(logic.format_cooldown(2.5, "ru"), "2 ч 30 мин")
        self.assertEqual(logic.format_cooldown(2.5, "uz"), "2 soat 30 daqiqa")

    def test_cooldown_parsing_all_languages(self):
        for text in ("2 hours 30 minutes", "2 часа 30 минут", "2 soat 30 daqiqa", "2:30"):
            self.assertAlmostEqual(logic.parse_cooldown_input(text), 2.5, msg=text)

    def test_bio_texts(self):
        d = date(2026, 12, 25)
        self.assertIn("7 days", logic.compute_bio_text("new_year", None, None, today=d, lang="en"))
        self.assertIn("7 дней", logic.compute_bio_text("new_year", None, None, today=d, lang="ru"))
        self.assertIn("7 kun", logic.compute_bio_text("new_year", None, None, today=d, lang="uz"))
        self.assertIn("1 day ", logic.compute_bio_text("new_year", None, None, today=date(2026, 12, 31), lang="en") + " ")
        today_en = logic.compute_bio_text("new_year", None, None, today=date(2027, 1, 1), lang="en")
        self.assertIn("New Year", today_en)

    def test_bio_birthday_all_languages(self):
        for lang in i18n.LANGS:
            text = logic.compute_bio_text("birthday", 3, 15, today=date(2026, 3, 10), lang=lang)
            self.assertIn("5", text)

    def test_zone_labels_translated(self):
        self.assertIn("Tashkent", logic.zone_label("Asia/Tashkent", "en"))
        self.assertIn("Ташкент", logic.zone_label("Asia/Tashkent", "ru"))
        self.assertIn("Toshkent", logic.zone_label("Asia/Tashkent", "uz"))


class AiLangTests(unittest.TestCase):
    def test_role_labels(self):
        self.assertEqual(ai.role_label("developer", "en"), i18n.T["role_developer"]["en"])
        self.assertEqual(ai.role_label("developer", "ru"), i18n.T["role_developer"]["ru"])

    def test_system_prompt_language_fallback_and_honesty_rules(self):
        for lang in i18n.LANGS:
            prompt = ai.build_system_prompt("Ali", None, "friend", lang)
            self.assertIn("Reply in the language the other person writes in", prompt)
        self.assertIn("English", ai.build_system_prompt("Ali", None, "friend", "en"))
        self.assertIn("Russian", ai.build_system_prompt("Ali", None, "friend", "ru"))
