"""
Sof (side-effect'siz) yordamchi funksiyalar: cooldown parsing va BIO
hisob-kitoblari. Bu modul atayin hech qanday environment variable yoki
bazaga bog'liq emas — shu tufayli uni muhitsiz ham (masalan tests/ ichida)
xavfsiz import qilish mumkin.
"""

from __future__ import annotations

import re
from datetime import date

# ---------------------------------------------------------------------------
# Cooldown
# ---------------------------------------------------------------------------
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
    """Turli formatlarni qabul qiladi va soat (float) qilib qaytaradi, yoki None."""
    text = text.strip().lower()

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
