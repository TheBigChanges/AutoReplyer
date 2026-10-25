"""Automation Engine v1: "AGAR xabarda kalit so'z bo'lsa, UNDA maxsus javob yuborilsin".

Toza modul: bazaga ham, Telegramga ham bog'lanmaydi — shuning uchun alohida oson sinaladi.
Qoida (bazada JSONB):
    conditions = {"operator": "all", "items": [{"type": "keyword_contains", "value": "narx*"}]}
    action     = {"type": "send_reply", "text": "..."}

Kalit so'z mosligi (Smart FAQ bilan bir xil normallashtirish — logic.faq_tokens):
  - sukut bo'yicha BUTUN so'z/ibora: "narx" -> "narx" mos, "narxi" yoki "unarxon" mos EMAS;
  - oxirida `*` bo'lsa — oxirgi so'z boshi bo'yicha: "narx*" -> "narx", "narxi", "narxlar" mos, "unarxon" mos emas;
  - inkor so'zi ("emas", "yo'q"...) bor xabarga javob berilmaydi (aksini so'rayotgan bo'lishi mumkin).
"""

from logic import _NEGATIONS, faq_tokens

ALLOWED_OPERATORS = frozenset({"all"})
ALLOWED_CONDITIONS = frozenset({"keyword_contains"})
ALLOWED_ACTIONS = frozenset({"send_reply"})

MAX_NAME_LENGTH = 60
MAX_KEYWORD_LENGTH = 50
MAX_KEYWORD_TOKENS = 5
MIN_PREFIX_LENGTH = 3  # "a*" kabi hamma narsaga mos keladigan qisqa prefikslar rad etiladi
MAX_REPLY_LENGTH = 500
PRIORITY_MIN, PRIORITY_MAX = 0, 10000
DEFAULT_PRIORITY = 100


class AutomationError(ValueError):
    """Qoida ma'lumotlari noto'g'ri."""


def parse_keyword(raw) -> tuple[list[str], bool]:
    """Kalit so'z matnini (so'zlar ro'yxati, prefiks_rejimi) ga aylantiradi. Noto'g'ri bo'lsa AutomationError."""
    if not isinstance(raw, str):
        raise AutomationError("keyword_type")
    value = raw.strip()
    if not value or len(value) > MAX_KEYWORD_LENGTH:
        raise AutomationError("keyword_length")
    prefix = value.endswith("*")
    if prefix:
        value = value[:-1]
    if "*" in value:
        raise AutomationError("keyword_star")
    tokens = faq_tokens(value)
    if not tokens or len(tokens) > MAX_KEYWORD_TOKENS:
        raise AutomationError("keyword_tokens")
    if prefix and len(tokens[-1]) < MIN_PREFIX_LENGTH:
        raise AutomationError("keyword_prefix_short")
    return tokens, prefix


def validate_automation(name, conditions, action, priority=DEFAULT_PRIORITY) -> dict:
    """Qoidani tekshiradi va tozalangan holda qaytaradi: {"name", "conditions", "action", "priority"}.
    Noto'g'ri bo'lsa AutomationError (xato kodi bilan). Faqat ruxsat etilgan shart/amal turlari va maydonlar qabul qilinadi."""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_NAME_LENGTH:
        raise AutomationError("name")
    if isinstance(priority, bool) or not isinstance(priority, int) or not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise AutomationError("priority")

    if not isinstance(conditions, dict) or set(conditions) != {"operator", "items"}:
        raise AutomationError("conditions")
    if conditions["operator"] not in ALLOWED_OPERATORS:
        raise AutomationError("operator")
    items = conditions["items"]
    if not isinstance(items, list) or len(items) != 1:  # v1: bitta shart
        raise AutomationError("items")
    item = items[0]
    if not isinstance(item, dict) or set(item) != {"type", "value"}:
        raise AutomationError("item")
    if item["type"] not in ALLOWED_CONDITIONS:
        raise AutomationError("condition_type")
    parse_keyword(item["value"])

    if not isinstance(action, dict) or set(action) != {"type", "text"}:
        raise AutomationError("action")
    if action["type"] not in ALLOWED_ACTIONS:
        raise AutomationError("action_type")
    text = action["text"]
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > MAX_REPLY_LENGTH:
        raise AutomationError("text")

    return {
        "name": name.strip(),
        "conditions": {"operator": "all", "items": [{"type": item["type"], "value": item["value"].strip()}]},
        "action": {"type": action["type"], "text": text.strip()},
        "priority": priority,
    }


def make_keyword_rule(keyword: str, reply: str, name: str | None = None, priority: int = DEFAULT_PRIORITY) -> dict:
    """Eng oddiy qoida (bitta kalit so'z -> bitta javob) uchun yordamchi; validatsiyadan o'tkazib qaytaradi."""
    keyword = (keyword or "").strip()
    return validate_automation(
        name if name else keyword,
        {"operator": "all", "items": [{"type": "keyword_contains", "value": keyword}]},
        {"type": "send_reply", "text": reply},
        priority,
    )


def matches_keyword(message: str | None, keyword) -> bool:
    """Xabarda kalit so'z (butun so'z/ibora, yoki `*` bilan so'z boshi) bormi. Inkor so'zi bor xabar — mos emas."""
    try:
        words, prefix = parse_keyword(keyword)
    except AutomationError:
        return False
    tokens = faq_tokens(message)
    if not tokens or any(tok in _NEGATIONS for tok in tokens):
        return False
    n = len(words)
    for start in range(len(tokens) - n + 1):
        window = tokens[start:start + n]
        if window[:-1] != words[:-1]:
            continue
        last = window[-1]
        if last == words[-1] or (prefix and last.startswith(words[-1])):
            return True
    return False


def rule_matches(message: str | None, rule: dict) -> bool:
    """Qoidaning hamma sharti ("all") bajarilganmi. Bazadan kelgan buzuq/begona qoida — mos emas (xato bermaydi)."""
    try:
        conditions = rule["conditions"]
        if conditions["operator"] != "all":
            return False
        items = conditions["items"]
        if not isinstance(items, list) or not items:
            return False
        for item in items:
            if item["type"] not in ALLOWED_CONDITIONS or not matches_keyword(message, item["value"]):
                return False
        action = rule["action"]
        text = action["text"]
        return action["type"] in ALLOWED_ACTIONS and isinstance(text, str) and bool(text.strip())
    except (KeyError, TypeError, AttributeError):
        return False


def _sort_key(rule: dict):
    priority = rule.get("priority")
    return (priority if isinstance(priority, int) and not isinstance(priority, bool) else DEFAULT_PRIORITY, rule.get("id") or 0)


def find_matching_automation(message: str | None, rules) -> dict | None:
    """Faol qoidalar ichidan mos kelganini qaytaradi; bir nechta bo'lsa — eng kichik priority, so'ng eng kichik id.
    Bir xabarga faqat bitta qoida ishlaydi. O'chirilgan (is_enabled=False) qoida hisobga olinmaydi."""
    candidates = [r for r in (rules or []) if r.get("is_enabled", True) and rule_matches(message, r)]
    return min(candidates, key=_sort_key) if candidates else None
