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

# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------
# Spamning oldini olish uchun eng kichik ruxsat etilgan cooldown (1 daqiqa).
# Bu qoida shu yerda (logic qatlamida) turadi, shuning uchun UI'dagi matn
# ("eng kami 1 daqiqa") va haqiqiy tekshiruv doim mos bo'ladi.
MIN_COOLDOWN_HOURS = 1 / 60


def format_cooldown(hours: float) -> str:
    """0.5 -> '30 daqiqa', 1.0 -> '1 soat', 2.5 -> '2 soat 30 daqiqa', 0 -> 'Har doim javob beradi'."""
    if hours <= 0:
        return "Har doim javob beradi (cooldown yo'q)"
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    parts = []
    if h:
        parts.append(f"{h} soat")
    if m or not parts:
        parts.append(f"{m} daqiqa")
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
    hours_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:soat|s|h|hour)\b", text)
    minutes_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:daqiqa|minut|min|m|d)\b", text)
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


def compute_bio_text(
    target: str, birthday_month, birthday_day, today: date | None = None
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
    label = BIO_EVENT_LABELS[target]
    emoji = BIO_EVENT_EMOJIS.get(target, "")
    if days == 0:
        return f"{emoji} Bugun {label.lower()}!".strip()
    return f"{emoji} {label}ga {days} kun qoldi!".strip()


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

_CLOCK_SUFFIX_RE = re.compile(r"\s*\|\s*\d{1,2}:\d{2}\s*$")


def zone_label(tz_name: str | None) -> str:
    for _, label, tz in NAME_CLOCK_ZONES:
        if tz == tz_name:
            return label
    return dict((tz, label) for _, label, tz in NAME_CLOCK_ZONES)[DEFAULT_NAME_CLOCK_ZONE]


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


def build_clock_name(base_first: str, base_last: str | None, hour: int, minute: int) -> tuple[str, str | None]:
    """(first_name, last_name) ni qaytaradi.
    Familiya yo'q:  ('Dilshodbek | 12:30', None)       -> "Dilshodbek | 12:30"
    Familiya bor:   ('Dilshodbek', 'Abdu | 12:30')     -> "Dilshodbek Abdu | 12:30"
    Har bir qism 64 belgidan oshmaydi: kerak bo'lsa asl ism qisqartiriladi, soat doim to'liq qoladi."""
    suffix = f" | {hour:02d}:{minute:02d}"
    base_first = (base_first or "").strip()
    base_last = (base_last or "").strip()
    if base_last:
        return base_first[:NAME_MAX_LENGTH], base_last[: NAME_MAX_LENGTH - len(suffix)] + suffix
    return base_first[: NAME_MAX_LENGTH - len(suffix)] + suffix, None


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
