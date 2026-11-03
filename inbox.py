"""Smart Inbox Digest (v1.3) — sof mantiq (bazaga va Telegram'ga bog'liq emas): xulosa vaqti, limitlar, kutish vaqti."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

DEFAULT_DIGEST_MINUTES = 20 * 60
DIGEST_HOUR_CHOICES = (8, 10, 12, 14, 16, 18, 20, 22)  # tanlash tugmalari (Plus va undan yuqori)
INBOX_PLAN_LIMITS = {"free": 3, "plus": 20, "pro": 20, "ultra": 20}  # xulosada ko'rsatiladigan suhbatlar soni
INBOX_PRIORITY_LIMITS = {"free": 0, "plus": 0, "pro": 5, "ultra": 20}  # v1.2: muhim suhbatlar soni
INBOX_REMINDER_DAILY_LIMITS = {"free": 0, "plus": 0, "pro": 3, "ultra": 10}  # v1.2: kuniga eslatmalar soni
REMINDER_DELAY_CHOICES = {"1h": 3600, "3h": 10800, "6h": 21600}
REMINDER_CHOICES = ("1h", "3h", "6h", "next9")
DIGEST_LEASE_SECONDS = 300.0  # 'preparing' da qolgan band qilish shundan keyin qayta olinadi


def effective_minutes(stored: int | None, can_choose: bool) -> int:
    """Xulosa vaqti (kun boshidan daqiqalarda). Tanlash tarifda yo'q bo'lsa (masalan, Bepul yoki tarif pasaygan) — 20:00."""
    if not can_choose or stored is None or not (0 <= stored < 1440):
        return DEFAULT_DIGEST_MINUTES
    return int(stored)


def digest_due(now_local: datetime, minutes: int, last_date: str | None, phase: str | None = "sent",
               claimed_at: float | None = None, now_ts: float | None = None, lease: float = DIGEST_LEASE_SECONDS) -> bool:
    """Bugungi xulosa vaqti kelganmi va u hali yuborilmaganmi (kun egasi vaqt zonasi bo'yicha). Bot o'sha paytda o'chiq bo'lsa,
    kun tugaguncha keyingi tekshiruvda yuboriladi. Bugun 'preparing' da qolib ketgan (lease o'tgan) band qilish ham qayta olinadi;
    'sending' / 'unknown' / 'sent' avtomatik qayta yuborilmaydi."""
    if now_local.hour * 60 + now_local.minute < minutes:
        return False
    if last_date != now_local.date().isoformat():
        return True
    return phase == "preparing" and claimed_at is not None and now_ts is not None and now_ts - float(claimed_at) > lease


def next_nine_due(now_ts: float, tz) -> tuple[float, str]:
    """Ertaga 09:00 (egasining vaqt zonasi) — mutlaq UTC unix vaqti va o'sha kunning mahalliy sanasi. Keyin zona o'zgarsa ham siljimaydi."""
    local = datetime.fromtimestamp(now_ts, tz)
    target = datetime.combine(local.date() + timedelta(days=1), datetime.min.time().replace(hour=9), tzinfo=tz)
    return target.astimezone(timezone.utc).timestamp(), target.date().isoformat()


def reminder_due(choice: str, now_ts: float, tz) -> tuple[float, str] | None:
    """Tanlov ('1h'|'3h'|'6h'|'next9') -> (due_at, due_local_date). Noma'lum tanlov — None."""
    if choice == "next9":
        return next_nine_due(now_ts, tz)
    secs = REMINDER_DELAY_CHOICES.get(choice)
    if secs is None:
        return None
    due = now_ts + secs
    return due, datetime.fromtimestamp(due, tz).date().isoformat()


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
