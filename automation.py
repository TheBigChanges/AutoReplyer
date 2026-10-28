"""Automation Engine v1.1: "AGAR xabarda kalit so'z bo'lsa (VA hafta kuni/vaqt mos bo'lsa), UNDA maxsus javob yuborilsin".

Toza modul: bazaga ham, Telegramga ham bog'lanmaydi — shuning uchun alohida oson sinaladi.
Qoida (bazada JSONB):
    conditions = {"operator": "all", "items": [{"type": "keyword_contains", "value": "narx*"},
                                               {"type": "days_of_week", "value": [0, 1, 2, 3, 4]},          # ixtiyoriy
                                               {"type": "time_between", "value": {"start": 540, "end": 1080}}]}  # ixtiyoriy
    action     = {"type": "send_reply", "text": "..."}

Kalit so'z mosligi (Smart FAQ bilan bir xil normallashtirish — logic.faq_tokens):
  - sukut bo'yicha BUTUN so'z/ibora: "narx" -> "narx" mos, "narxi" yoki "unarxon" mos EMAS;
  - oxirida `*` bo'lsa — oxirgi so'z boshi bo'yicha: "narx*" -> "narx", "narxi", "narxlar" mos, "unarxon" mos emas;
  - inkor so'zi ("emas", "yo'q"...) bor xabarga javob berilmaydi (aksini so'rayotgan bo'lishi mumkin).
"""

from logic import _NEGATIONS, ALL_DAYS_MASK, SCHEDULE_ALL_DAY, days_mask, faq_tokens, schedule_active, valid_schedule_time

ALLOWED_OPERATORS = frozenset({"all"})
KEYWORD, DAYS, TIME = "keyword_contains", "days_of_week", "time_between"
ALLOWED_CONDITIONS = frozenset({KEYWORD, DAYS, TIME})
CANONICAL_ORDER = (KEYWORD, DAYS, TIME)  # saqlashda tartib: kalit so'z, kunlar, vaqt
MAX_CONDITIONS = 3
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


def _validate_conditions(conditions) -> list[dict]:
    """1-3 shart: bitta kalit so'z (majburiy) + ixtiyoriy hafta kunlari + ixtiyoriy vaqt oralig'i (har turdan ko'pi bilan bitta).
    Tozalangan, kanonik tartibdagi ro'yxatni qaytaradi (v1.0 qoidalari — bitta kalit so'z — o'zgarishsiz o'tadi)."""
    if not isinstance(conditions, dict) or set(conditions) != {"operator", "items"}:
        raise AutomationError("conditions")
    if conditions["operator"] not in ALLOWED_OPERATORS:
        raise AutomationError("operator")
    items = conditions["items"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_CONDITIONS:
        raise AutomationError("items")
    by_type: dict = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != {"type", "value"}:
            raise AutomationError("item")
        kind = item["type"]
        if kind not in ALLOWED_CONDITIONS:
            raise AutomationError("condition_type")
        if kind in by_type:
            raise AutomationError("duplicate_condition")
        by_type[kind] = _clean_condition_value(kind, item["value"])
    if KEYWORD not in by_type:
        raise AutomationError("keyword_required")
    return [{"type": kind, "value": by_type[kind]} for kind in CANONICAL_ORDER if kind in by_type]


def _clean_condition_value(kind: str, value):
    if kind == KEYWORD:
        parse_keyword(value)
        return value.strip()
    if kind == DAYS:
        if not isinstance(value, list) or not value or len(value) > 7:
            raise AutomationError("days")
        if any(isinstance(d, bool) or not isinstance(d, int) or not 0 <= d <= 6 for d in value) or len(set(value)) != len(value):
            raise AutomationError("days")
        return sorted(value)
    if not isinstance(value, dict) or set(value) != {"start", "end"}:
        raise AutomationError("time")
    start, end = value["start"], value["end"]
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (start, end)) or not valid_schedule_time(start, end):
        raise AutomationError("time")
    return {"start": start, "end": end}


def build_conditions(keyword: str, days=None, time_range=None) -> dict:
    """Panel/buyruq uchun yordamchi: kalit so'z + ixtiyoriy kunlar (0=Dushanba) + ixtiyoriy (boshlanish, tugash) daqiqalari."""
    items = [{"type": KEYWORD, "value": keyword}]
    if days:
        items.append({"type": DAYS, "value": sorted(days)})
    if time_range is not None:
        items.append({"type": TIME, "value": {"start": time_range[0], "end": time_range[1]}})
    return {"operator": "all", "items": items}


def split_conditions(rule: dict) -> tuple[str | None, list[int] | None, tuple[int, int] | None]:
    """Qoidadan (kalit so'z, kunlar yoki None, (boshlanish, tugash) yoki None). Buzuq ma'lumotda mos qismlar None."""
    keyword, days, time_range = None, None, None
    try:
        for item in rule["conditions"]["items"]:
            if item["type"] == KEYWORD and keyword is None:
                keyword = item["value"]
            elif item["type"] == DAYS and days is None:
                days = list(item["value"])
            elif item["type"] == TIME and time_range is None:
                time_range = (item["value"]["start"], item["value"]["end"])
    except (KeyError, TypeError, AttributeError):
        pass
    return keyword, days, time_range


def has_smart_conditions(rule: dict) -> bool:
    """Qoidada hafta kuni yoki vaqt sharti bormi (tarif cheklovi shu uchun)."""
    _, days, time_range = split_conditions(rule)
    return days is not None or time_range is not None


def validate_automation(name, conditions, action, priority=DEFAULT_PRIORITY) -> dict:
    """Qoidani tekshiradi va tozalangan holda qaytaradi: {"name", "conditions", "action", "priority"}.
    Noto'g'ri bo'lsa AutomationError (xato kodi bilan). Faqat ruxsat etilgan shart/amal turlari va maydonlar qabul qilinadi."""
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > MAX_NAME_LENGTH:
        raise AutomationError("name")
    if isinstance(priority, bool) or not isinstance(priority, int) or not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise AutomationError("priority")

    items = _validate_conditions(conditions)

    if not isinstance(action, dict) or set(action) != {"type", "text"}:
        raise AutomationError("action")
    if action["type"] not in ALLOWED_ACTIONS:
        raise AutomationError("action_type")
    text = action["text"]
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > MAX_REPLY_LENGTH:
        raise AutomationError("text")

    return {
        "name": name.strip(),
        "conditions": {"operator": "all", "items": items},
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


def _schedule_ok(days, time_range, when) -> bool:
    """Hafta kuni va vaqt BIRGALIKDA hisoblanadi (logic.schedule_active): yarim tundan o'tadigan oraliq (Du 22:00 -> Se 06:00)
    boshlangan kuniga tegishli. Faqat kunlar — butun kun; faqat vaqt — har kuni. `when` = (weekday, daqiqa), 0 = Dushanba."""
    if when is None:
        return False  # joriy vaqt noma'lum — vaqtga bog'liq qoida ishlamaydi (xavfsiz tomon)
    try:
        weekday, minutes = when
        mask = days_mask(days) if days is not None else ALL_DAYS_MASK
        start, end = time_range if time_range is not None else SCHEDULE_ALL_DAY
        return schedule_active(mask, start, end, weekday, minutes)
    except (TypeError, ValueError):
        return False


def rule_matches(message: str | None, rule: dict, when=None, allow_smart: bool = True) -> bool:
    """Qoidaning hamma sharti ("all") bajarilganmi. Bazadan kelgan buzuq/begona qoida — mos emas (xato bermaydi).
    `when` — (hafta kuni, kun boshidan daqiqa) egasining vaqt zonasida; `allow_smart=False` (tarifda yo'q) bo'lsa kun/vaqt
    shartli qoida ishlamaydi."""
    try:
        conditions = rule["conditions"]
        if conditions["operator"] != "all":
            return False
        items = conditions["items"]
        if not isinstance(items, list) or not items or len(items) > MAX_CONDITIONS:
            return False
        keyword, days, time_range = None, None, None
        seen = set()
        for item in items:
            kind = item["type"]
            if kind not in ALLOWED_CONDITIONS or kind in seen:
                return False
            seen.add(kind)
            if kind == KEYWORD:
                keyword = item["value"]
            elif kind == DAYS:
                days = item["value"]
            else:
                value = item["value"]
                time_range = (value["start"], value["end"])
        if keyword is None or not matches_keyword(message, keyword):
            return False
        if (days is not None or time_range is not None) and not (allow_smart and _schedule_ok(days, time_range, when)):
            return False
        action = rule["action"]
        text = action["text"]
        return action["type"] in ALLOWED_ACTIONS and isinstance(text, str) and bool(text.strip())
    except (KeyError, TypeError, AttributeError):
        return False


def _sort_key(rule: dict):
    priority = rule.get("priority")
    return (priority if isinstance(priority, int) and not isinstance(priority, bool) else DEFAULT_PRIORITY, rule.get("id") or 0)


def find_matching_automation(message: str | None, rules, when=None, allow_smart: bool = True) -> dict | None:
    """Faol qoidalar ichidan mos kelganini qaytaradi; bir nechta bo'lsa — eng kichik priority, so'ng eng kichik id.
    Bir xabarga faqat bitta qoida ishlaydi. O'chirilgan (is_enabled=False) qoida hisobga olinmaydi."""
    candidates = [r for r in (rules or []) if r.get("is_enabled", True) and rule_matches(message, r, when, allow_smart)]
    return min(candidates, key=_sort_key) if candidates else None
