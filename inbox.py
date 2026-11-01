"""Smart Inbox Digest (v1.3) — sof mantiq (bazaga va Telegram'ga bog'liq emas): xulosa vaqti, limitlar, kutish vaqti."""

from __future__ import annotations

from datetime import datetime

DEFAULT_DIGEST_MINUTES = 20 * 60
DIGEST_HOUR_CHOICES = (8, 10, 12, 14, 16, 18, 20, 22)  # tanlash tugmalari (Plus va undan yuqori)
INBOX_PLAN_LIMITS = {"free": 3, "plus": 20, "pro": 20, "ultra": 20}  # xulosada ko'rsatiladigan suhbatlar soni


def effective_minutes(stored: int | None, can_choose: bool) -> int:
    """Xulosa vaqti (kun boshidan daqiqalarda). Tanlash tarifda yo'q bo'lsa (masalan, Bepul yoki tarif pasaygan) — 20:00."""
    if not can_choose or stored is None or not (0 <= stored < 1440):
        return DEFAULT_DIGEST_MINUTES
    return int(stored)


def digest_due(now_local: datetime, minutes: int, last_date: str | None) -> bool:
    """Bugungi xulosa vaqti kelganmi va u hali yuborilmaganmi (kun egasi vaqt zonasi bo'yicha). Bot o'sha paytda o'chiq bo'lsa,
    kun tugaguncha keyingi tekshiruvda yuboriladi."""
    return last_date != now_local.date().isoformat() and now_local.hour * 60 + now_local.minute >= minutes


def wait_parts(seconds: float) -> tuple[str, int]:
    """Kutish vaqti: ('min' | 'hr' | 'day', son)."""
    seconds = max(0.0, seconds)
    if seconds < 3600:
        return "min", max(1, int(seconds // 60))
    if seconds < 48 * 3600:
        return "hr", int(seconds // 3600)
    return "day", int(seconds // 86400)


def format_minutes(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
