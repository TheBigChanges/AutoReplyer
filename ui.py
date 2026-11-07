"""Tugmalar ko'rinishi: yonma-yon joylashtirish va Telegram'ning rasmiy tugma ranglari (Bot API `style`).

bot.py'dagi barcha inline klaviaturalar `Markup` orqali yaratiladi: u qatorlarni ixcham qiladi (bitta tugmali qatorlar juft-juft
yonma-yon) va har bir tugmaga ma'nosiga qarab rang beradi:
  🔴 qizil (danger)  — Orqaga, Bekor qilish, O'chirish, o'chirib qo'yish
  🟢 yashil (success) — Yoqish, Saqlash, Tasdiqlash, To'lash, Qo'shish
  🔵 ko'k (primary)  — asosiy bo'limlarga kirish
Rang eski Telegram ilovalarida ko'rinmaydi (tugma oddiy chiqadi) — funksionallikka ta'sir qilmaydi.
"""

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

import i18n

DANGER, SUCCESS, PRIMARY = "danger", "success", "primary"

# i18n `btn_*` kalitlari bo'yicha rang (matn -> kalit teskari jadvali orqali, uch tilda)
_DANGER_KEYS = {
    "btn_back", "btn_disable", "btn_faq_cancel", "btn_faq_delete", "btn_faq_entry_off", "btn_pay_cancel", "btn_au_cancel",
    "btn_au_delete", "btn_au_del_yes", "btn_au_off", "btn_au_e_clear", "btn_ob_fail", "btn_sc_delete", "btn_sc_cancel",
    "btn_sc_del_yes", "btn_sc_pause", "btn_sc_toggle_on", "btn_inbox_notify_off", "btn_inbox_remind_cancel",
    "btn_inbox_prio_remove", "btn_kb_cancel", "btn_kb_delete", "btn_kb_entry_off", "btn_kb_del_yes",
}
_SUCCESS_KEYS = {
    "btn_enable", "btn_faq_save", "btn_faq_entry_on", "btn_faq_add", "btn_pay_stars", "btn_pay_extend", "btn_pay_go", "btn_pay_switch",
    "btn_au_add", "btn_au_save", "btn_au_on", "btn_au_e_done", "btn_ob_check", "btn_ob_enable", "btn_ob_ok", "btn_sc_add",
    "btn_sc_save", "btn_sc_resume", "btn_sc_toggle_off", "btn_inbox_notify_on", "btn_inbox_prio_add", "btn_kb_add", "btn_kb_save",
    "btn_kb_entry_on",
}
_DANGER_KEYS |= {"panel_go_offline"}
_SUCCESS_KEYS |= {"panel_go_online", "gate_btn_check", "ref_btn_share", "btn_pay_months", "btn_pay_months_off", "btn_pay_resend"}
# Holat almashtirgichlar (yoqish/o'chirish...) va "Orqaga": har doim to'liq kenglikdagi alohida qatorda
_WIDE_KEYS = {
    "btn_back", "btn_enable", "btn_disable", "btn_faq_entry_on", "btn_faq_entry_off", "btn_au_on", "btn_au_off", "btn_sc_pause",
    "btn_sc_resume", "btn_sc_toggle_on", "btn_sc_toggle_off", "btn_inbox_notify_on", "btn_inbox_notify_off", "btn_kb_entry_on",
    "btn_kb_entry_off", "btn_ob_enable", "btn_ob_check", "panel_go_online", "panel_go_offline", "btn_open_panel", "btn_ob_resume",
    "btn_ob_skip",
}
# Tasdiqlash/bekor qilish turidagi tugmalar faqat o'zaro juftlashadi (Saqlash | Bekor qilish)
_CONFIRM_KEYS = {
    "btn_faq_save", "btn_faq_cancel", "btn_faq_delete", "btn_pay_cancel", "btn_au_save", "btn_au_cancel", "btn_au_delete",
    "btn_au_del_yes", "btn_ob_ok", "btn_ob_fail", "btn_sc_save", "btn_sc_cancel", "btn_sc_delete", "btn_sc_del_yes", "btn_kb_save",
    "btn_kb_cancel", "btn_kb_delete", "btn_kb_del_yes", "btn_au_skip", "btn_pay_switch", "btn_pay_resend",
}
_PRIMARY_KEYS = {
    "btn_open_panel", "btn_autoreply", "btn_sleep", "btn_ai", "btn_name_clock", "btn_bio", "btn_faq", "btn_kb", "btn_automation",
    "btn_sched", "btn_inbox", "btn_analytics", "btn_plans", "btn_sc_continue", "btn_ob_resume",
}

# Matnsiz/dinamik tugmalar uchun callback_data bo'yicha (birinchi mos kelgan)
_CALLBACK_RULES: list[tuple[re.Pattern, str | None]] = [
    (re.compile(r"^(back$|rmbots:no|bc_cancel|rmbots:yes|ib_unpr:|ib_rc:|pay_cx:|.*_cancel(:|$)|.*_ecancel:|.*_del_yes:|.*_del:|ob_fail$)"), DANGER),
    (re.compile(r"^(bc_confirm:|unblock:|pay_buy:|pay_q:|ref_share|.*_save:|.*_edone:|ob_ok$|ob_check$|ob_enable$|ob_resume$)"), SUCCESS),
    (re.compile(r"^(ib_pr:)"), SUCCESS),
]
_SELECTED_PREFIXES = ("✅", "\u2705")  # tanlangan variant (kun, soat, rol, shrift...): yashil, tanlanmaganlari ko'k

_text_key: dict[str, str] | None = None


def _key_for_text(text: str) -> str | None:
    global _text_key
    if _text_key is None:
        _text_key = {}
        for key, variants in i18n.T.items():
            if key.startswith(("btn_", "panel_go_", "gate_btn_", "ref_btn_", "support_btn_")):
                for value in variants.values():
                    _text_key.setdefault(value, key)
    return _text_key.get(text)


def style_for(text: str, callback_data: str | None) -> str | None:
    """Tugma rangi: 'danger' (qizil) | 'success' (yashil) | 'primary' (ko'k). Har bir tugma rangli: boshqa qoidaga tushmagan
    tugma (tahrirlash, ro'yxat, sozlama, sahifalash, til...) ko'k bo'ladi; tanlangan variant (✅) yashil."""
    key = _key_for_text(text)
    if key in _DANGER_KEYS:
        return DANGER
    if key in _SUCCESS_KEYS:
        return SUCCESS
    if key in _PRIMARY_KEYS:
        return PRIMARY
    if isinstance(callback_data, str):
        for pattern, style in _CALLBACK_RULES:
            if pattern.match(callback_data):
                return style
    if text.startswith(_SELECTED_PREFIXES):
        return SUCCESS
    return PRIMARY


MAX_PAIR_TEXT = 24  # bu uzunlikdan uzun yozuvlar yarim kenglikda sig'maydi: alohida qatorda qoladi


def _kind(btn: InlineKeyboardButton) -> str | None:
    """Juftlash turi: 'plain' (oddiy bo'lim/amal), 'confirm' (Saqlash/Bekor...) yoki None (alohida qatorda qoladi)."""
    if (
        not isinstance(btn.callback_data, str) or len(btn.text) > MAX_PAIR_TEXT
        or btn.pay or btn.url or btn.web_app
    ):
        return None
    key = _key_for_text(btn.text)
    if key in _WIDE_KEYS:
        return None
    if key in _CONFIRM_KEYS:
        return "confirm"
    return "plain"


def arrange(rows: list[list[InlineKeyboardButton]]) -> list[list[InlineKeyboardButton]]:
    """Ketma-ket kelgan bitta tugmali qisqa qatorlarni juft-juft yonma-yon qiladi. Bir nechta tugmali qatorlar (sahifalash, vaqt
    tanlash), "Orqaga", yoqish/o'chirish almashtirgichlari va uzun yozuvli/URL/to'lov tugmalari o'z holicha qoladi.
    Saqlash/Bekor qilish turidagi tugmalar faqat o'zaro juftlashadi."""
    out: list[list[InlineKeyboardButton]] = []
    pending: InlineKeyboardButton | None = None
    pending_kind: str | None = None
    for row in rows:
        kind = _kind(row[0]) if len(row) == 1 else None
        if kind is not None:
            if pending is not None and pending_kind == kind:
                out.append([pending, row[0]])
                pending, pending_kind = None, None
                continue
            if pending is not None:
                out.append([pending])
            pending, pending_kind = row[0], kind
            continue
        if pending is not None:
            out.append([pending])
            pending, pending_kind = None, None
        out.append(list(row))
    if pending is not None:
        out.append([pending])
    return out


def _styled(btn: InlineKeyboardButton) -> InlineKeyboardButton:
    if btn.style is not None or btn.pay:
        return btn
    style = style_for(btn.text, btn.callback_data)
    return InlineKeyboardButton(
        btn.text, url=btn.url, callback_data=btn.callback_data, switch_inline_query=btn.switch_inline_query,
        switch_inline_query_current_chat=btn.switch_inline_query_current_chat, web_app=btn.web_app, copy_text=btn.copy_text,
        style=style,
    )


class Markup(InlineKeyboardMarkup):
    """InlineKeyboardMarkup: qatorlarni ixcham joylaydi va tugmalarga rang beradi."""

    def __init__(self, inline_keyboard, *args, **kwargs):
        rows = [list(r) for r in inline_keyboard]
        rows = [[_styled(b) for b in row] for row in arrange(rows)]
        super().__init__(rows, *args, **kwargs)
