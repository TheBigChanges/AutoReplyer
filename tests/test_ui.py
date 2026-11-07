"""ui.py: tugmalarni yonma-yon joylash va rang berish."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import i18n  # noqa: E402
import ui  # noqa: E402
from telegram import InlineKeyboardButton as B  # noqa: E402


def b(key_or_text, cb="x", lang="uz"):
    text = i18n.T[key_or_text][lang] if key_or_text in i18n.T else key_or_text
    return B(text, callback_data=cb)


def flat(markup):
    return [x.callback_data for row in markup.inline_keyboard for x in row]


class StyleTests(unittest.TestCase):
    def test_back_cancel_delete_disable_are_red_in_all_languages(self):
        for key in ("btn_back", "btn_disable", "btn_faq_cancel", "btn_au_delete", "btn_sc_cancel", "btn_kb_del_yes",
                    "btn_inbox_remind_cancel", "panel_go_offline"):
            for lang in ("uz", "en", "ru"):
                self.assertEqual(ui.style_for(i18n.T[key][lang], "x"), ui.DANGER, (key, lang))

    def test_enable_save_pay_are_green(self):
        for key in ("btn_enable", "btn_faq_save", "btn_au_on", "btn_pay_stars", "btn_sc_save", "panel_go_online", "btn_faq_add"):
            for lang in ("uz", "en", "ru"):
                self.assertEqual(ui.style_for(i18n.T[key][lang], "x"), ui.SUCCESS, (key, lang))

    def test_sections_are_blue_and_unknown_is_plain(self):
        for key in ("btn_ai", "btn_autoreply", "btn_plans", "btn_inbox"):
            self.assertEqual(ui.style_for(i18n.T[key]["en"], "x"), ui.PRIMARY, key)
        self.assertIsNone(ui.style_for("Ali", "ib_rem:5:0"))
        self.assertIsNone(ui.style_for(i18n.T["btn_ai_roles"]["uz"], "ai_roles"))

    def test_callback_rules_for_dynamic_buttons(self):
        self.assertEqual(ui.style_for("⭐ Ali ✖", "ib_unpr:5:0"), ui.DANGER)
        self.assertEqual(ui.style_for("x", "pay_cx:tok"), ui.DANGER)
        self.assertEqual(ui.style_for("x", "au_cancel:1"), ui.DANGER)
        self.assertEqual(ui.style_for("x", "bc_confirm:9"), ui.SUCCESS)
        self.assertEqual(ui.style_for("x", "pay_buy:pro:1:5"), ui.SUCCESS)
        self.assertIsNone(ui.style_for("x", "lang:uz"))
        self.assertIsNone(ui.style_for("x", None))

    def test_all_configured_keys_exist_in_i18n(self):
        for group in (ui._DANGER_KEYS, ui._SUCCESS_KEYS, ui._PRIMARY_KEYS, ui._WIDE_KEYS, ui._CONFIRM_KEYS):
            for key in group:
                self.assertIn(key, i18n.T, key)

    def test_no_key_is_both_red_and_green(self):
        self.assertFalse(ui._DANGER_KEYS & ui._SUCCESS_KEYS)


class ArrangeTests(unittest.TestCase):
    def test_single_rows_are_paired_and_odd_one_stays_alone(self):
        rows = ui.arrange([[b("A", "1")], [b("B", "2")], [b("C", "3")]])
        self.assertEqual([[x.callback_data for x in r] for r in rows], [["1", "2"], ["3"]])

    def test_back_and_toggles_stay_full_width(self):
        m = ui.Markup([[b("btn_disable", "off")], [b("A", "1")], [b("B", "2")], [b("btn_back", "back")]])
        self.assertEqual([[x.callback_data for x in r] for r in m.inline_keyboard], [["off"], ["1", "2"], ["back"]])

    def test_long_and_multi_button_rows_untouched(self):
        long = "x" * (ui.MAX_PAIR_TEXT + 1)
        rows = ui.arrange([[b(long, "1")], [b("B", "2")], [b("P", "p1"), b("N", "p2"), b("Z", "p3")]])
        self.assertEqual([[x.callback_data for x in r] for r in rows], [["1"], ["2"], ["p1", "p2", "p3"]])

    def test_confirm_buttons_pair_only_with_each_other(self):
        m = ui.Markup([[b("A", "1")], [b("btn_faq_save", "s")], [b("btn_faq_cancel", "c")], [b("B", "2")]])
        self.assertEqual([[x.callback_data for x in r] for r in m.inline_keyboard], [["1"], ["s", "c"], ["2"]])

    def test_pay_url_and_order_preserved(self):
        pay = B("Pay", pay=True)
        url = B("Open", url="https://t.me/x")
        m = ui.Markup([[pay], [url], [b("A", "1")], [b("B", "2")]])
        self.assertTrue(m.inline_keyboard[0][0].pay)  # to'lov tugmasi birinchi qatorda, birinchi o'rinda
        self.assertEqual(len(m.inline_keyboard[0]), 1)
        self.assertEqual(m.inline_keyboard[1][0].url, "https://t.me/x")
        self.assertEqual(flat(m)[2:], ["1", "2"])

    def test_callback_order_and_data_preserved_overall(self):
        src = [[b(f"T{i}", f"cb{i}")] for i in range(7)] + [[b("btn_back", "back")]]
        self.assertEqual(flat(ui.Markup(src)), [f"cb{i}" for i in range(7)] + ["back"])

    def test_empty_and_idempotent(self):
        self.assertEqual(ui.arrange([]), [])
        m1 = ui.Markup([[b("A", "1")], [b("B", "2")], [b("btn_back", "back")]])
        m2 = ui.Markup(m1.inline_keyboard)
        self.assertEqual([[x.callback_data for x in r] for r in m1.inline_keyboard], [[x.callback_data for x in r] for r in m2.inline_keyboard])


class MarkupTests(unittest.TestCase):
    def test_style_is_serialized_for_telegram(self):
        d = ui.Markup([[b("btn_back", "back")]]).to_dict()
        self.assertEqual(d["inline_keyboard"][0][0]["style"], "danger")
        self.assertEqual(d["inline_keyboard"][0][0]["callback_data"], "back")

    def test_plain_button_has_no_style_key(self):
        d = ui.Markup([[b("Ali", "ib_rem:5")]]).to_dict()
        self.assertNotIn("style", d["inline_keyboard"][0][0])

    def test_existing_style_not_overridden(self):
        btn = B(i18n.T["btn_back"]["uz"], callback_data="back", style="primary")
        self.assertEqual(ui.Markup([[btn]]).inline_keyboard[0][0].style, "primary")

    def test_is_an_inline_keyboard_markup(self):
        from telegram import InlineKeyboardMarkup
        self.assertIsInstance(ui.Markup([[b("A", "1")]]), InlineKeyboardMarkup)


class RealMenusTests(unittest.TestCase):
    """Haqiqiy menyular: hamma "Orqaga" tugmasi qizil, qatorda 3 tadan ko'p tugma yo'q (sahifalash/vaqt tanlashdan tashqari)."""

    def test_every_back_button_in_app_is_red(self):
        import bot
        from unittest.mock import patch
        import db
        with patch.object(db, "get_settings", return_value={"offline": True, "auto_reply_text": "x", "cooldown_hours": 3.0,
                                                          "sleep_mode_enabled": False, "sleep_start_minutes": 1380, "sleep_end_minutes": 420,
                                                          "sleep_reply_text": "", "ai_enabled": True, "ai_info": "i", "ai_role": "seller"}), \
                patch.object(bot, "get_lang", return_value="uz"), patch.object(bot, "plan_of", return_value="ultra"):
            for name in ("build_autoreply_menu", "build_ai_menu"):
                r = getattr(bot, name)(1)
                markup = r[1] if isinstance(r, tuple) else r
                backs = [x for row in markup.inline_keyboard for x in row if x.text == i18n.T["btn_back"]["uz"]]
                self.assertTrue(backs, name)
                self.assertTrue(all(x.style == "danger" for x in backs), name)
                self.assertEqual(list(markup.inline_keyboard[-1]), backs[-1:])  # "Orqaga" pastda, alohida qatorda


if __name__ == "__main__":
    unittest.main()
