"""
Sof (side-effect'siz) yordamchi funksiyalar: cooldown parsing va BIO
hisob-kitoblari. Bu modul atayin hech qanday environment variable yoki
bazaga bog'liq emas — shu tufayli uni muhitsiz ham (masalan tests/ ichida)
xavfsiz import qilish mumkin.
"""

from __future__ import annotations

import math
import re
from datetime import date

from i18n import days_unit, t

# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------
# Spamning oldini olish uchun eng kichik ruxsat etilgan cooldown (1 daqiqa).
# Bu qoida shu yerda (logic qatlamida) turadi, shuning uchun UI'dagi matn
# ("eng kami 1 daqiqa") va haqiqiy tekshiruv doim mos bo'ladi.
MIN_COOLDOWN_HOURS = 1 / 60


def format_cooldown(hours: float, lang: str = "uz") -> str:
    """0.5 -> '30 daqiqa', 1.0 -> '1 soat', 2.5 -> '2 soat 30 daqiqa', 0 -> 'Har doim javob beradi'.
    `lang` bo'yicha: en -> '2 h 30 min', ru -> '2 ч 30 мин'."""
    if hours <= 0:
        return t(lang, "cd_always")
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    parts = []
    if h:
        parts.append(t(lang, "unit_hour", n=h))
    if m or not parts:
        parts.append(t(lang, "unit_minute", n=m))
    return " ".join(parts)


def parse_cooldown_input(text: str) -> float | None:
    """Turli formatlarni qabul qiladi va soat (float) qilib qaytaradi, yoki None.

    Natija FAQAT chekli (finite) va kamida MIN_COOLDOWN_HOURS (1 daqiqa) bo'lgan
    son bo'ladi, aks holda None. Chekli bo'lish talabi: "nan", "inf",
    "1e999", "nan:5", "1:nan" yoki juda uzun raqamlar (float'da inf bo'lib
    ketadigan) None qaytaradi. Aks holda bunday qiymat bazaga yozilib, cooldown
    tekshiruvini buzardi (nan -> cooldown ishlamaydi, inf -> bot abadiy jim)
    va format_cooldown() yiqilib, foydalanuvchi panelini ochib bo'lmay qolardi."""
    value = _parse_cooldown_raw(text)
    if value is None or not math.isfinite(value):
        return None
    # 1 daqiqadan kam (jumladan 0 va manfiy) qabul qilinmaydi. Kichik tolerantlik
    # float yaxlitlash xatosi ("0:01" kabi aniq 1 daqiqa) rad etilmasligi uchun.
    if value * 60 < 1 - 1e-9:
        return None
    return value


def _parse_cooldown_raw(text: str) -> float | None:
    """parse_cooldown_input() uchun ichki yordamchi: chekli ekanligini TEKSHIRMAYDI."""
    text = text.strip().lower()

    # Hech bir to'g'ri format minus belgisini ishlatmaydi. Regex esa "-0.5 soat"dagi
    # minusni ko'rmay, uni jimgina 0.5 soat deb o'qib yuborardi (foydalanuvchi
    # niyatini buzib talqin qilish) — shuning uchun oldindan rad etamiz.
    if "-" in text:
        return None

    # "2 soat 30 daqiqa", "1s 30d", "45 daqiqa", "3 soat" kabi formatlar
    # Uzbek (soat/daqiqa), English (hour/minute) va Rus (час/минута) birliklari qabul qilinadi.
    hours_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:soat|hours?|hrs?|h|s|часов|часа|час|ч)(?![^\W\d_])", text
    )
    minutes_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(?:daqiqa|minutes?|minut|min|mins|m|d|минуты|минуту|минут|мин|м)(?![^\W\d_])", text
    )
    if hours_match or minutes_match:
        h = float(hours_match.group(1).replace(",", ".")) if hours_match else 0.0
        m = float(minutes_match.group(1).replace(",", ".")) if minutes_match else 0.0
        return h + m / 60

    # "1:30" -> 1 soat 30 daqiqa
    if ":" in text:
        try:
            h_str, m_str = text.split(":", 1)
            h = float(h_str)
            m = float(m_str)
        except ValueError:
            return None
        # Daqiqa qismi 0–59 oralig'ida bo'lishi kerak — "1:90" kabi
        # noto'g'ri formatni jim qabul qilib, 2.5 soat deb hisoblab
        # yubormasligi uchun (bu foydalanuvchi niyatini buzib talqin qilish).
        if h < 0 or m < 0 or m >= 60:
            return None
        return h + m / 60

    # Oddiy raqam -> soat sifatida
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# BIO hisoblagich
# ---------------------------------------------------------------------------
BIO_EVENT_LABELS = {
    "new_year": "Yangi yil",
    "navroz": "Navro'z",
    "birthday": "Tug'ilgan kunim",
}
BIO_EVENT_EMOJIS = {
    "new_year": "\U0001F386",  # 🎆
    "navroz": "\U0001F337",    # 🌷
    "birthday": "\U0001F382",  # 🎂
}
# (oy, kun) — har yili takrorlanadigan bayramlar uchun
FIXED_EVENT_DATES = {
    "new_year": (1, 1),
    "navroz": (3, 21),
}


def days_until_next(month: int, day: int, today: date | None = None) -> int:
    if today is None:
        today = date.today()
    year = today.year
    try:
        target = date(year, month, day)
    except ValueError:
        target = date(year, 3, 1)  # 29-fevral kabi holatlar uchun zaxira
    if target < today:
        try:
            target = date(year + 1, month, day)
        except ValueError:
            target = date(year + 1, 3, 1)
    return (target - today).days


def bio_event_label(target: str, lang: str = "uz") -> str:
    key = f"bio_event_{target}"
    return t(lang, key) if target in BIO_EVENT_LABELS else target


def compute_bio_text(
    target: str, birthday_month, birthday_day, today: date | None = None, lang: str = "uz"
) -> str | None:
    """`today` berilmasa serverning mahalliy sanasi olinadi (Render'da UTC).
    Foydalanuvchi uchun to'g'ri kun hisobi kerak bo'lsa, chaqiruvchi o'z
    vaqt zonasidagi sanani uzatishi kerak."""
    if target in FIXED_EVENT_DATES:
        month, day = FIXED_EVENT_DATES[target]
    elif target == "birthday":
        if not birthday_month or not birthday_day:
            return None
        month, day = birthday_month, birthday_day
    else:
        return None

    days = days_until_next(month, day, today=today)
    emoji = BIO_EVENT_EMOJIS.get(target, "")
    if days == 0:
        return f"{emoji} {t(lang, 'bio_today_' + target)}".strip()
    return f"{emoji} {t(lang, 'bio_text_' + target, days=days, unit=days_unit(lang, days))}".strip()


def parse_birthday_input(text: str) -> tuple[int, int] | None:
    """'15.03', '15-03', '15/03' kabi formatlarni (oy, kun) qilib qaytaradi."""
    match = re.match(r"^\s*(\d{1,2})[.\-/](\d{1,2})\s*$", text)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    if not (1 <= month <= 12) or not (1 <= day <= 31):
        return None
    try:
        date(2024, month, day)  # to'g'ri sana ekanini tekshirish (2024 — kabisa yil)
    except ValueError:
        return None
    return month, day


# ---------------------------------------------------------------------------
# Uxlash rejimi
# ---------------------------------------------------------------------------
DEFAULT_SLEEP_START_MINUTES = 23 * 60  # 23:00
DEFAULT_SLEEP_END_MINUTES = 7 * 60     # 07:00
DEFAULT_SLEEP_MESSAGE = "\U0001F634 Men hozir uxlayapman, ertalab uyg'onishim bilan albatta javob beraman!"


def parse_time_range_input(text: str) -> tuple[int, int] | None:
    """'23:00-07:00', '23-07', '23:00 - 7:00' kabi formatlarni
    (boshlanish_daqiqa, tugash_daqiqa) — kun boshidan hisoblab — qilib qaytaradi."""
    match = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*-\s*(\d{1,2})(?::(\d{2}))?\s*$", text.strip())
    if not match:
        return None
    sh, sm, eh, em = match.groups()
    start_h, end_h = int(sh), int(eh)
    start_m = int(sm) if sm else 0
    end_m = int(em) if em else 0
    if not (0 <= start_h <= 23 and 0 <= end_h <= 23 and 0 <= start_m <= 59 and 0 <= end_m <= 59):
        return None
    return start_h * 60 + start_m, end_h * 60 + end_m


def format_time_range(start_minutes: int, end_minutes: int) -> str:
    sh, sm = divmod(start_minutes, 60)
    eh, em = divmod(end_minutes, 60)
    return f"{sh:02d}:{sm:02d}\u2013{eh:02d}:{em:02d}"


def is_within_sleep_window(now_minutes: int, start_minutes: int, end_minutes: int) -> bool:
    """Joriy vaqt (kun boshidan daqiqada) uyqu oralig'ida ekanini tekshiradi.
    Yarim tunni kesib o'tadigan oraliqlarni (masalan 23:00 -> 07:00) ham
    to'g'ri hisoblaydi."""
    if start_minutes == end_minutes:
        return False  # nol uzunlikdagi oraliq — hech qachon faol emas
    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes
    return now_minutes >= start_minutes or now_minutes < end_minutes


# --------------------------------------------------------------------------
# Ism soati: "Ism | 12:30"
# --------------------------------------------------------------------------
NAME_MAX_LENGTH = 64  # Telegram: ism va familiya har biri 1-64 / 0-64 belgi

# (kalit, tugmadagi nom, IANA vaqt zonasi)
NAME_CLOCK_ZONES = [
    ("tashkent", "\U0001F1FA\U0001F1FF Toshkent (UTC+5)", "Asia/Tashkent"),
    ("moscow", "\U0001F1F7\U0001F1FA Moskva (UTC+3)", "Europe/Moscow"),
    ("istanbul", "\U0001F1F9\U0001F1F7 Istanbul (UTC+3)", "Europe/Istanbul"),
    ("dubai", "\U0001F1E6\U0001F1EA Dubay (UTC+4)", "Asia/Dubai"),
    ("bishkek", "\U0001F1F0\U0001F1EC Bishkek (UTC+6)", "Asia/Bishkek"),
    ("beijing", "\U0001F1E8\U0001F1F3 Pekin (UTC+8)", "Asia/Shanghai"),
    ("tokyo", "\U0001F1EF\U0001F1F5 Tokio (UTC+9)", "Asia/Tokyo"),
    ("london", "\U0001F1EC\U0001F1E7 London", "Europe/London"),
    ("berlin", "\U0001F1E9\U0001F1EA Berlin", "Europe/Berlin"),
    ("newyork", "\U0001F1FA\U0001F1F8 Nyu-York", "America/New_York"),
]
DEFAULT_NAME_CLOCK_ZONE = "Asia/Tashkent"

# Raqamlar ko'rinishi (Telegram ismidagi soat uchun).
# Kalit -> (nom, 0-9 raqamlar, ikki nuqta belgisi, har RAQAM orqasiga qo'shiladigan belgi, ikki nuqta orqasiga qo'shiladigan belgi)
_ASCII_DIGITS = "0123456789"
_STROKE = "\u0336"  # birlashtiruvchi uzun chiziq (Strike)
_UNDERLINE = "\u0332"  # birlashtiruvchi past chiziq (Underline)
_RING = "\u20dd"  # birlashtiruvchi aylana (Ring)
_KEYCAP = "\ufe0f\u20e3"  # emoji "keycap" (2\ufe0f\u20e3)


def _seq(first_cp: int) -> str:
    return "".join(chr(first_cp + i) for i in range(10))


NAME_CLOCK_STYLES = {
    "default": ("Default", _ASCII_DIGITS, ":", "", ""),
    "mono": ("Monospace", _seq(0x1D7F6), ":", "", ""),
    "strike": ("Strike", _ASCII_DIGITS, ":", _STROKE, _STROKE),
    "super": ("SuperScript", "\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079", "\u02f8", "", ""),
    "sub": ("SubScript", _seq(0x2080), ":", "", ""),
    "bold": ("Bold", _seq(0x1D7EC), ":", "", ""),
    "boldserif": ("Bold Serif", _seq(0x1D7CE), ":", "", ""),
    "double": ("Double Struck", _seq(0x1D7D8), ":", "", ""),
    "circle": ("Circle", "\u24ea" + "".join(chr(0x2460 + i) for i in range(9)), ":", "", ""),
    "darkcircle": ("Dark Circle", "\u24ff" + "".join(chr(0x2776 + i) for i in range(9)), ":", "", ""),
    "wide": ("Wide", _seq(0xFF10), "\uff1a", "", ""),
    "sans": ("Sans", _seq(0x1D7E2), ":", "", ""),
    "underline": ("Underline", _ASCII_DIGITS, ":", _UNDERLINE, _UNDERLINE),
    "keycap": ("Keycap", _ASCII_DIGITS, ":", _KEYCAP, ""),
    "ring": ("Ring", _ASCII_DIGITS, ":", _RING, ""),
}
DEFAULT_NAME_CLOCK_STYLE = "default"


def is_known_style(key: str | None) -> bool:
    return key in NAME_CLOCK_STYLES


def style_time(text: str, style: str | None) -> str:
    """'20:45' ni tanlangan ko'rinishga o'tkazadi."""
    _, digits, colon, digit_extra, colon_extra = NAME_CLOCK_STYLES[
        style if is_known_style(style) else DEFAULT_NAME_CLOCK_STYLE
    ]
    out = []
    for ch in text:
        if ch.isascii() and ch.isdigit():
            out.append(digits[int(ch)] + digit_extra)
        elif ch == ":":
            out.append(colon + colon_extra)
        else:
            out.append(ch)
    return "".join(out)


def _build_suffix_re():
    digit_chars = set(_ASCII_DIGITS)
    colon_chars = {":"}
    extras = set()
    for _, digits, colon, digit_extra, colon_extra in NAME_CLOCK_STYLES.values():
        digit_chars.update(digits)
        colon_chars.add(colon)
        extras.update(e for e in (digit_extra, colon_extra) if e)
    # Ixtiyoriy qo'shimcha belgilar (chiziq, aylana, keycap...) — uzunroqlari avval
    extra_re = "(?:" + "|".join(re.escape(e) for e in sorted(extras, key=len, reverse=True)) + ")?"
    d = "(?:[" + re.escape("".join(sorted(digit_chars))) + "]" + extra_re + ")"
    c = "(?:[" + re.escape("".join(sorted(colon_chars))) + "]" + extra_re + ")"
    return re.compile(r"\s*\|\s*" + d + "{1,2}" + c + d + "{2}" + r"\s*$")


_CLOCK_SUFFIX_RE = _build_suffix_re()


def u16len(text: str) -> int:
    """Telegram uzunlikni UTF-16 birligida sanashi mumkin (astral belgilar = 2)."""
    return len(text.encode("utf-16-le")) // 2


def _cut(text: str, max_units: int) -> str:
    """Matnni UTF-16 uzunligi `max_units` dan oshmaydigan qilib (belgini bo'lmasdan) qisqartiradi."""
    out, used = [], 0
    for ch in text:
        w = 2 if ord(ch) > 0xFFFF else 1
        if used + w > max_units:
            break
        out.append(ch)
        used += w
    return "".join(out)


def zone_button_label(key: str, label: str, lang: str = "uz") -> str:
    """Zona tugmasi nomi: shahar nomi tilga o'giriladi (bayroq va UTC qismi o'zgarmaydi)."""
    return label.replace(t("uz", "zone_" + key), t(lang, "zone_" + key), 1)


def zone_label(tz_name: str | None, lang: str = "uz") -> str:
    for key, label, tz in NAME_CLOCK_ZONES:
        if tz == tz_name:
            return zone_button_label(key, label, lang)
    key, label, _tz = next(z for z in NAME_CLOCK_ZONES if z[2] == DEFAULT_NAME_CLOCK_ZONE)
    return zone_button_label(key, label, lang)


def is_known_zone(tz_name: str | None) -> bool:
    return any(tz == tz_name for _, _, tz in NAME_CLOCK_ZONES)


def strip_clock_suffix(text: str | None) -> str:
    """Oldingi " | 12:30" qo'shimchasini olib tashlaydi (bot yarim yo'lda to'xtagan bo'lsa,
    asl ism sifatida soatli ism saqlanib qolmasligi uchun)."""
    return _CLOCK_SUFFIX_RE.sub("", text or "").strip()


def split_full_name(full_name: str) -> tuple[str, str]:
    """'Dilshodbek Abdu' -> ('Dilshodbek', 'Abdu'). Familiya bo'lmasa ikkinchisi ''."""
    parts = strip_clock_suffix(full_name).split(None, 1)
    if not parts:
        return "", ""
    return parts[0][:NAME_MAX_LENGTH], (parts[1].strip() if len(parts) > 1 else "")[:NAME_MAX_LENGTH]


def build_clock_name(
    base_first: str, base_last: str | None, hour: int, minute: int, style: str | None = None
) -> tuple[str, str | None]:
    """(first_name, last_name) ni qaytaradi.
    Familiya yo'q:  ('Dilshodbek | 12:30', None)       -> "Dilshodbek | 12:30"
    Familiya bor:   ('Dilshodbek', 'Abdu | 12:30')     -> "Dilshodbek Abdu | 12:30"
    Har bir qism 64 birlikdan oshmaydi: kerak bo'lsa asl ism qisqartiriladi, soat doim to'liq qoladi."""
    suffix = " | " + style_time(f"{hour:02d}:{minute:02d}", style)
    base_first = (base_first or "").strip()
    base_last = (base_last or "").strip()
    room = NAME_MAX_LENGTH - u16len(suffix)
    if base_last:
        return _cut(base_first, NAME_MAX_LENGTH), _cut(base_last, room) + suffix
    return _cut(base_first, room) + suffix, None


def is_external_rename(base_first: str, base_last: str | None, cur_first: str | None, cur_last: str | None) -> bool:
    """Foydalanuvchi ismni Telegramda o'zi o'zgartirdimi? Joriy ism (soatsiz) saqlangan asl ismdan
    farq qilsa — True. Uzun ism soat uchun qisqartirilgan bo'lsa (asl ismning boshi) — o'zgarish emas."""
    def same(base: str, cur: str) -> bool:
        base, cur = strip_clock_suffix(base), strip_clock_suffix(cur)
        if base == cur:
            return True
        return len(base) >= NAME_MAX_LENGTH - 8 and base.startswith(cur)

    cf = strip_clock_suffix(cur_first)
    if not cf:
        return False  # Telegram ismni qaytarmadi — o'zgargan deb hisoblamaymiz
    return not (same(base_first or "", cf) and same(base_last or "", cur_last or ""))


# ---------------------------------------------------------------------------
# Tarif muddati (/setplan @user plus 1oy)
# ---------------------------------------------------------------------------
_DURATION_RE = re.compile(
    r"^(\d{1,4})\s*(oy|oylik|kun|kunlik|hafta|haftalik|yil|yillik|month|months|day|days|week|weeks|year|years)$"
)
_DURATION_KIND = {
    "oy": "month", "oylik": "month", "month": "month", "months": "month",
    "kun": "day", "kunlik": "day", "day": "day", "days": "day",
    "hafta": "week", "haftalik": "week", "week": "week", "weeks": "week",
    "yil": "year", "yillik": "year", "year": "year", "years": "year",
}
MAX_PLAN_DAYS = 3650


def parse_plan_duration(text: str):
    """'1oy', '30 kun', '2hafta', '1yil' -> (son, 'month'|'day'|'week'|'year'); noto'g'ri bo'lsa None.
    0 va 10 yildan uzun muddat rad etiladi."""
    m = _DURATION_RE.match((text or "").strip().lower())
    if not m:
        return None
    n, kind = int(m.group(1)), _DURATION_KIND[m.group(2)]
    if n <= 0:
        return None
    days = {"day": 1, "week": 7, "month": 31, "year": 366}[kind] * n
    return (n, kind) if days <= MAX_PLAN_DAYS + 31 else None


def add_plan_duration(start_ts: float, n: int, kind: str, tz) -> float:
    """`start_ts` dan boshlab n oy/kun/hafta/yil keyingi vaqt (taqvim bo'yicha: 31-yanvar + 1 oy = 28/29-fevral)."""
    import calendar
    from datetime import datetime, timedelta

    start = datetime.fromtimestamp(start_ts, tz)
    if kind in ("month", "year"):
        months = n * (12 if kind == "year" else 1)
        index = start.year * 12 + (start.month - 1) + months
        year, month = divmod(index, 12)
        month += 1
        day = min(start.day, calendar.monthrange(year, month)[1])
        return start.replace(year=year, month=month, day=day).timestamp()
    return (start + timedelta(days=n * (7 if kind == "week" else 1))).timestamp()


# ---------------------------------------------------------------------------
# Smart FAQ: mijoz xabariga mos tayyor javobni topish (Gemini'siz, qoidalar asosida)
# ---------------------------------------------------------------------------
# Tarif bo'yicha Smart FAQ savollari soni (Bepul tarifda Smart FAQ yo'q)
FAQ_PLAN_LIMITS = {"plus": 15, "pro": 30, "ultra": 65}
FAQ_MAX_QUESTION = 200
FAQ_MAX_KEYWORDS = 10
FAQ_MAX_KEYWORD_LENGTH = 40
FAQ_MAX_ANSWER = 1000
FAQ_MAX_MESSAGE_TOKENS = 60  # juda uzun (ko'p mavzuli) xabarga FAQ javobi berilmaydi

_APOSTROPHES = "‘’ʻʼʹ`´'"
# "yo'qmi", "emas", "нет" kabi inkor so'zlari: savol aksini so'rayotgan bo'lishi mumkin -> aniq emas
_NEGATIONS = frozenset({
    "yoq", "yoqmi", "yoqku", "yoqmidi", "emas", "emasmi", "bolmaydi", "mumkinmas",
    "no", "not", "dont", "cant", "нет", "не", "нету", "без", "нельзя",
})


# ---------------- AI Knowledge Base (biznes/shaxsiy ma'lumotlar bazasi) ----------------
KB_LIMIT = 55  # Ultra: nechta yozuv saqlash mumkin
KB_MAX_TITLE = 100
KB_MAX_CONTENT = 1000
KB_MAX_SELECTED = 5  # katta bazadan AI'ga eng ko'pi bilan shuncha yozuv beriladi
KB_MAX_CONTEXT_CHARS = 4000


def faq_tokens(text: str | None) -> list[str]:
    """Kichik harf, apostrof/tinish belgilarsiz so'zlar ro'yxati ("O'zbekiston?" -> ["ozbekiston"])."""
    if not text:
        return []
    s = text.lower().replace("ё", "е")
    for ch in _APOSTROPHES:
        s = s.replace(ch, "")
    return re.findall(r"[^\W_]+", s, flags=re.UNICODE)


def parse_faq_keywords(raw: str) -> list[str] | None:
    """Vergul/yangi qator bilan ajratilgan kalit so'z/iboralar -> normallashtirilgan, takrorsiz ro'yxat.
    Noto'g'ri bo'lsa (bo'sh, juda ko'p yoki juda uzun) — None."""
    out: list[str] = []
    for part in re.split(r"[,;\n]", raw or ""):
        toks = faq_tokens(part)
        if not toks:
            continue
        phrase = " ".join(toks)
        if len(phrase) > FAQ_MAX_KEYWORD_LENGTH:
            return None
        if phrase not in out:
            out.append(phrase)
    if not out or len(out) > FAQ_MAX_KEYWORDS:
        return None
    return out


def _contains_phrase(tokens: list[str], phrase: list[str]) -> bool:
    n = len(phrase)
    if n == 0 or n > len(tokens):
        return False
    return any(tokens[i:i + n] == phrase for i in range(len(tokens) - n + 1))


def match_faq(message: str | None, entries) -> dict | None:
    """Xabarga eng mos FAQ yozuvini qaytaradi; ishonchli bo'lmasa — None (oddiy javobga qaytiladi).

    Qoidalar: faqat BUTUN so'z/ibora mosligi; inkor so'zi bor xabar — noaniq; juda uzun xabar — noaniq;
    bir nechta yozuv bir xil darajada mos kelsa — noaniq. Daraja = mos kelgan kalit so'zlardagi so'zlar soni;
    savolning o'zi bilan aynan bir xil xabar eng yuqori darajaga ega."""
    tokens = faq_tokens(message)
    if not tokens or len(tokens) > FAQ_MAX_MESSAGE_TOKENS:
        return None
    if any(tok in _NEGATIONS for tok in tokens):
        return None
    scored: list[tuple[int, dict]] = []
    for entry in entries:
        if entry.get("is_enabled") is False:
            continue
        score = 0
        if tokens == faq_tokens(entry.get("question")):
            score = 1000
        else:
            seen = set()
            for kw in entry.get("keywords") or []:
                kt = faq_tokens(kw)
                key = tuple(kt)
                if key in seen:
                    continue
                seen.add(key)
                if _contains_phrase(tokens, kt):
                    score += len(kt)
        if score > 0:
            scored.append((score, entry))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    return scored[0][1]


_KB_STOPWORDS = frozenset({
    # uz
    "qancha", "qachon", "qanday", "qaysi", "qayer", "qayerda", "bormi", "nima", "nimaga", "kerak", "yana", "bilan",
    "uchun", "menga", "sizga", "sizda", "mening", "sizning", "haqida", "keyin", "hozir", "iltimos", "rahmat",
    # en
    "what", "when", "where", "which", "does", "have", "your", "this", "that", "with", "there", "about", "please",
    "thanks", "would", "could", "will",
    # ru
    "что", "как", "где", "когда", "какой", "какая", "есть", "можно", "ваш", "ваша", "этот", "пожалуйста", "спасибо",
})


def _kb_stem(token: str) -> str:
    """Qo'shimchalarga chidamli oddiy "o'zak": uzun so'zning birinchi 5 harfi ("vaqtim"/"vaqtingiz" -> "vaqti")."""
    return token[:5] if len(token) >= 6 else token


def _kb_stems(text: str | None) -> set[str]:
    return {_kb_stem(tok) for tok in faq_tokens(text) if len(tok) >= 4 and tok not in _KB_STOPWORDS}


def select_knowledge(messages, entries) -> list[dict]:
    """AI'ga beriladigan Knowledge Base yozuvlarini tanlaydi — FAQAT mijoz xabariga mos kelganlarini
    (maxfiylik: ortiqcha yozuvlar Gemini'ga yuborilmaydi; hech narsa mos kelmasa — bo'sh ro'yxat).

    `messages` — mijozning oxirgi xabar(lar)i (matn yoki matnlar ro'yxati; oldingi xabarlar "qancha turadi?"
    kabi davomli savollarni tushunish uchun). Faqat yoqilgan yozuvlar. Ball: kalit ibora mosligi (eng kuchli),
    sarlavhadagi so'z o'zaklari mosligi, yozuv matnidagi so'z o'zaklari mosligi. Ko'p yozuvlarda uchraydigan
    umumiy so'zlar (bazaning yarmidan ko'pida) va savol so'zlari (qancha, qachon, what...) hisobga olinmaydi.
    Eng yuqori ballli KB_MAX_SELECTED tasi olinadi (jami KB_MAX_CONTEXT_CHARS dan oshmaydi)."""
    enabled = [e for e in entries if e.get("is_enabled") is not False]
    if not enabled:
        return []
    if isinstance(messages, str):
        messages = [messages]
    tokens = faq_tokens(" ".join(m for m in (messages or []) if m))
    msg_stems = {_kb_stem(tok) for tok in tokens if len(tok) >= 4 and tok not in _KB_STOPWORDS}
    if not tokens:
        return []

    def size(e):
        return len(e.get("title") or "") + len(e.get("content") or "")

    title_stems = [_kb_stems(e.get("title")) for e in enabled]
    content_stems = [_kb_stems(e.get("content")) for e in enabled]
    # Umumiy so'zlarni (ko'p yozuvda uchraydigan) tashlab yuboramiz — faqat yozuvlar soni yetarli bo'lganda
    common: set[str] = set()
    if len(enabled) >= 4:
        df: dict[str, int] = {}
        for ts, cs in zip(title_stems, content_stems):
            for st in ts | cs:
                df[st] = df.get(st, 0) + 1
        common = {st for st, n in df.items() if n > len(enabled) / 2}
    live_stems = msg_stems - common

    scored: list[tuple[int, int, dict]] = []
    for idx, e in enumerate(enabled):
        score = 0
        for kw in e.get("keywords") or []:
            kt = faq_tokens(kw)
            if kt and _contains_phrase(tokens, kt):
                score += 3 * len(kt)
        score += 2 * len(title_stems[idx] & live_stems)
        score += len(content_stems[idx] & live_stems)
        if score > 0:
            scored.append((score, idx, e))
    scored.sort(key=lambda x: (-x[0], x[1]))
    picked, total = [], 0
    for _, _, e in scored:
        if len(picked) >= KB_MAX_SELECTED or (picked and total + size(e) > KB_MAX_CONTEXT_CHARS):
            break
        picked.append(e)
        total += size(e)
    return picked


def parse_kb_keywords(raw: str) -> list[str] | None:
    """Knowledge Base kalit so'zlari — ixtiyoriy: "-" yoki bo'sh -> []. Noto'g'ri (juda ko'p/uzun) bo'lsa — None."""
    raw = (raw or "").strip()
    if raw in ("", "-"):
        return []
    return parse_faq_keywords(raw)


# ---------------------------------------------------------------------------
# Smart Auto-Reply Scheduler: haftalik jadval mantig'i (sof funksiyalar)
# ---------------------------------------------------------------------------
SCHEDULE_PLAN_LIMITS = {"free": 1, "plus": 3, "pro": 10, "ultra": 30}
SCHEDULE_MAX_TEXT = 500
SCHEDULE_WEEK_MINUTES = 7 * 1440
SCHEDULE_ALL_DAY = (0, 1440)  # "butun kun": boshlanish 00:00, tugash 24:00
ALL_DAYS_MASK = 0b1111111
WEEKDAYS_MASK = 0b0011111  # Dushanba..Juma (bit 0 = Dushanba)
WEEKEND_MASK = 0b1100000   # Shanba, Yakshanba


def days_mask(days) -> int:
    """[0..6] (0 = Dushanba) -> bitmask."""
    mask = 0
    for d in days:
        if 0 <= d <= 6:
            mask |= 1 << d
    return mask


def mask_days(mask: int) -> list[int]:
    return [d for d in range(7) if mask & (1 << d)]


def is_all_day(start: int, end: int) -> bool:
    return (start, end) == SCHEDULE_ALL_DAY


def valid_schedule_time(start: int, end: int) -> bool:
    """Oddiy oraliq: 0 <= start < 1440, 0 <= end < 1440, start != end (end < start — yarim tundan o'tadi);
    yoki aynan 'butun kun' (0, 1440)."""
    if is_all_day(start, end):
        return True
    return 0 <= start < 1440 and 0 <= end < 1440 and start != end


def schedule_segments(mask: int, start: int, end: int) -> list[tuple[int, int]]:
    """Jadvalning haftalik daqiqalar o'qidagi [a, b) bo'laklari. Hafta Dushanba 00:00 dan boshlanadi.
    Yarim tundan o'tadigan oraliq ertasi kunga o'tadi, Yakshanbadan keyin Dushanbaga aylanadi."""
    segments = []
    for d in mask_days(mask):
        a = d * 1440 + start
        b = d * 1440 + (end if end > start else end + 1440)
        if b > SCHEDULE_WEEK_MINUTES:
            segments.append((a, SCHEDULE_WEEK_MINUTES))
            segments.append((0, b - SCHEDULE_WEEK_MINUTES))
        else:
            segments.append((a, b))
    return segments


def schedules_overlap(m1: int, s1: int, e1: int, m2: int, s2: int, e2: int) -> bool:
    for a1, b1 in schedule_segments(m1, s1, e1):
        for a2, b2 in schedule_segments(m2, s2, e2):
            if a1 < b2 and a2 < b1:
                return True
    return False


def schedule_active(mask: int, start: int, end: int, weekday: int, minutes_of_day: int) -> bool:
    """weekday: 0 = Dushanba (datetime.weekday())."""
    wm = weekday * 1440 + minutes_of_day
    return any(a <= wm < b for a, b in schedule_segments(mask, start, end))


def find_active_schedule(rules, weekday: int, minutes_of_day: int):
    """Faol (yoqilgan) jadvallar ichidan hozirgi vaqtga mosini qaytaradi (kesishmaydi, shuning uchun bitta)."""
    for r in rules:
        if r.get("is_enabled", True) and schedule_active(r["days"], r["start_min"], r["end_min"], weekday, minutes_of_day):
            return r
    return None


def format_day_set(mask: int, names: list[str], everyday: str, sep: str = " – ") -> str:
    """Kunlar to'plamini o'qiladigan matnga aylantiradi: ketma-ket 3+ kun 'Dushanba – Juma', qolganlari vergul bilan."""
    days = mask_days(mask)
    if len(days) == 7:
        return everyday
    parts, i = [], 0
    while i < len(days):
        j = i
        while j + 1 < len(days) and days[j + 1] == days[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{names[days[i]]}{sep}{names[days[j]]}")
        else:
            parts.extend(names[d] for d in days[i:j + 1])
        i = j + 1
    return ", ".join(parts)
