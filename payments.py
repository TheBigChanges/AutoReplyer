"""Payments v1.0 (Telegram Stars): narxlar, muddatlar, tarif almashtirish va refund hisobi.

Toza modul: bazaga ham, Telegramga ham bog'lanmaydi — shuning uchun alohida oson sinaladi.

Tarif holati — PlanState(plan, expires_at, rate):
  * plan        — 'free' | 'plus' | 'pro' | 'ultra';
  * expires_at  — tugash vaqti (unix soniya); None — muddatsiz (admin bergan, bu yerda sotib olinmaydi);
  * rate        — Stars'dagi bir kunlik qiymat (haqiqatan to'langan summa / kunlar). None — ro'yxat narxi (1 oylik narx / 30),
                  masalan /setplan yoki karta orqali berilgan tarif uchun.

Qoidalar:
  * yangi / muddati tugagan: to'liq narx, muddat hozirdan boshlanadi;
  * o'sha tarifni uzaytirish: muddat mavjud muddat ustiga qo'shiladi (qolgan vaqt saqlanadi);
  * yuqoriga o'tish: qolgan qiymat (butun Stars, pastga yaxlitlanadi) yangi narxdan ayriladi, farqi to'lanadi;
    qolgan qiymat narxga yetsa — to'lovsiz almashadi, ortig'i yangi tarif kunlariga aylanadi;
  * pastga o'tish: to'lovsiz, qolgan qiymat arzon tarif kunlariga aylanadi (pul qaytmaydi);
  * refund: qaytarilgan Stars qiymati joriy kunlik qiymat bo'yicha kunlarga aylantirilib, tarif muddatidan ayriladi.
"""
from dataclasses import dataclass
from typing import NamedTuple

PLAN_RANK = {"free": 0, "plus": 1, "pro": 2, "ultra": 3}
STARS_PRICE_1M = {"plus": 15, "pro": 35, "ultra": 70}  # 1 oylik narx, Stars
DURATION_DISCOUNT = {1: 0, 3: 10, 6: 15, 12: 20}  # oy -> chegirma foizi
DURATIONS = tuple(DURATION_DISCOUNT)
DAY = 86400.0
LIST_DAYS_PER_MONTH = 30


class PaymentError(ValueError):
    """Hisob-kitob mumkin emas (xato kodi bilan)."""


@dataclass(frozen=True)
class PlanState:
    plan: str = "free"
    expires_at: float | None = None
    rate: float | None = None


@dataclass(frozen=True)
class Quote:
    kind: str            # 'new' | 'extend' | 'upgrade' | 'switch' (to'lovsiz yuqoriga) | 'downgrade' (to'lovsiz pastga)
    target: str
    months: int
    price: int           # tanlangan muddatning to'liq narxi (Stars)
    credit: int          # qolgan qiymatdan hisobga olingan Stars (faqat yuqoriga o'tishda)
    pay: int             # to'lanadigan Stars (0 — to'lov kerak emas)
    new_state: PlanState


def stars_price(plan: str, months: int) -> int:
    """Muddat uchun to'liq narx: 1 oylik narx × oylar × (100 − chegirma)%, yarmi yuqoriga yaxlitlanadi."""
    if plan not in STARS_PRICE_1M:
        raise PaymentError("bad_plan")
    if months not in DURATION_DISCOUNT:
        raise PaymentError("bad_months")
    return (STARS_PRICE_1M[plan] * months * (100 - DURATION_DISCOUNT[months]) + 50) // 100


def list_rate(plan: str) -> float:
    """Ro'yxat narxidagi bir kunlik qiymat (Stars/kun)."""
    return STARS_PRICE_1M[plan] / LIST_DAYS_PER_MONTH


def is_active(state: PlanState, now: float) -> bool:
    return state.plan in STARS_PRICE_1M and (state.expires_at is None or state.expires_at > now)


def is_unlimited(state: PlanState, now: float) -> bool:
    return state.plan in STARS_PRICE_1M and state.expires_at is None


def rate_of(state: PlanState) -> float:
    return state.rate if state.rate else list_rate(state.plan)


def remaining_days(state: PlanState, now: float) -> float:
    if not is_active(state, now) or state.expires_at is None:
        return 0.0
    return max(0.0, (state.expires_at - now) / DAY)


def remaining_value(state: PlanState, now: float) -> float:
    return remaining_days(state, now) * rate_of(state) if state.plan in STARS_PRICE_1M else 0.0


def _days(start: float, end: float) -> float:
    return max((end - start) / DAY, 1e-9)


def quote(state: PlanState, target: str, months: int, now: float, add_months) -> Quote:
    """Tanlangan tarif va muddat uchun hisob-kitob. `add_months(ts, n)` — n oy keyingi vaqt (taqvim bo'yicha).
    Muddatsiz pullik tarifda sotib olish mumkin emas (PaymentError('unlimited'))."""
    price = stars_price(target, months)
    if is_unlimited(state, now):
        raise PaymentError("unlimited")

    if not is_active(state, now):
        end = add_months(now, months)
        return Quote("new", target, months, price, 0, price, PlanState(target, end, price / _days(now, end)))

    rem_value = remaining_value(state, now)
    if target == state.plan:
        end = add_months(state.expires_at, months)
        return Quote("extend", target, months, price, 0, price,
                     PlanState(target, end, (rem_value + price) / _days(now, end)))

    if PLAN_RANK[target] > PLAN_RANK[state.plan]:
        credit = int(rem_value)  # butun Stars, pastga yaxlitlanadi
        period_end = add_months(now, months)
        if credit >= price:  # qolgan qiymat narxni qoplaydi — to'lovsiz almashadi, ortig'i qo'shimcha kunlar
            extra_seconds = (credit - price) / (price / _days(now, period_end)) * DAY
            end = period_end + extra_seconds
            return Quote("switch", target, months, price, price, 0, PlanState(target, end, credit / _days(now, end)))
        return Quote("upgrade", target, months, price, credit, price - credit,
                     PlanState(target, period_end, price / _days(now, period_end)))

    # pastga: to'lovsiz, qolgan qiymat arzon tarif kunlariga aylanadi
    new_days = rem_value / list_rate(target)
    return Quote("downgrade", target, months, price, 0, 0, PlanState(target, now + new_days * DAY, None))


def apply_order(state: PlanState, kind: str, plan: str, months: int, stars: int, credit: int, now: float, add_months) -> PlanState:
    """To'langan buyurtmani joriy holatga qo'llaydi (to'lov vaqtida). To'langan summa — haqiqat: tarif doim beriladi.
    'extend' faqat o'sha tarif hali faol bo'lsagina uzaytiradi; aks holda (holat orada o'zgargan) yangi davr boshlanadi."""
    if kind == "extend" and state.plan == plan and is_active(state, now) and state.expires_at is not None:
        end = add_months(state.expires_at, months)
        return PlanState(plan, end, (remaining_value(state, now) + stars) / _days(now, end))
    end = add_months(now, months)
    value = stars + (credit if kind == "upgrade" else 0)
    return PlanState(plan, end, value / _days(now, end))


def apply_refund(state: PlanState, stars: int, now: float) -> PlanState:
    """Refund: qaytarilgan Stars qiymati kunlarga aylanib, tarif muddatidan ayriladi; muddat tugasa — Bepul.
    Muddatsiz yoki bepul tarifga tegmaydi."""
    if not is_active(state, now) or state.expires_at is None:
        return state
    end = state.expires_at - stars / rate_of(state) * DAY
    if end <= now:
        return PlanState("free", None, None)
    return PlanState(state.plan, end, state.rate)


class Grant(NamedTuple):
    new_state: PlanState
    start: float          # bu to'lov qo'shgan davrning boshi
    end: float            # ... va oxiri (refund shu oraliqning foydalanilmagan ulushini oladi)
    review: bool = False  # True: tarif o'zgarmadi (muddatsiz tarif) — admin qo'lda ko'rib chiqishi kerak


def normalize(state: PlanState, now: float) -> PlanState:
    """Muddati o'tgan tarif — Bepul."""
    return state if is_active(state, now) else PlanState()


def grant(state: PlanState, snapshot_ok: bool, kind: str, plan: str, months: int, stars: int, credit: int, now: float, add_months) -> Grant:
    """To'langan buyurtmani qo'llaydi. Buyurtma yaratilgandagi holat (snapshot) hali o'zgarmagan bo'lsa — kelishilgan hisob (apply_order).
    O'zgargan bo'lsa (eski invoice kechikib to'langan) — foydalanuvchining amaldagi huquqlari YO'QOTILMAYDI: haqiqatan to'langan Stars qiymati
    (credit hisobga olinmaydi, chunki u endi eski tarifga tayanmaydi) joriy holatga qo'shiladi:
      bo'sh/tugagan -> yangi davr; o'sha tarif -> uzaytirish; yuqoriroq joriy tarif -> uning kunlariga aylantiriladi;
      pastroq joriy tarif -> buyurtma tarifiga o'tadi, joriy qolgan qiymat kunlarga aylanib qo'shiladi; muddatsiz -> tegilmaydi (review)."""
    state = normalize(state, now)
    if snapshot_ok:
        new = apply_order(state, kind, plan, months, stars, credit, now, add_months)
        extended = kind == "extend" and state.plan == plan and state.expires_at is not None
        return Grant(new, state.expires_at if extended else now, new.expires_at)
    if is_unlimited(state, now):
        return Grant(state, now, now, True)
    price = stars_price(plan, months)
    period_days = _days(now, add_months(now, months))
    seconds = period_days * min(stars / price, 1.0) * DAY
    if state.plan == "free":
        end = now + seconds
        return Grant(PlanState(plan, end, stars / _days(now, end)), now, end)
    rem = remaining_value(state, now)
    if state.plan == plan:
        end = state.expires_at + seconds
        return Grant(PlanState(plan, end, (rem + stars) / _days(now, end)), state.expires_at, end)
    if PLAN_RANK[state.plan] > PLAN_RANK[plan]:
        end = state.expires_at + stars / list_rate(state.plan) * DAY
        return Grant(PlanState(state.plan, end, (rem + stars) / _days(now, end)), state.expires_at, end)
    end = now + seconds + rem / list_rate(plan) * DAY
    return Grant(PlanState(plan, end, (rem + stars) / _days(now, end)), now, end)


def carried_value(stars: int, grant_value, grant_start, grant_end, now: float) -> float:
    """Xarid qiymatidan hozir hali foydalanilmagan ulush (Stars). grant_value — qiymat grant_start paytida qancha edi (None — stars)."""
    if grant_start is None or grant_end is None:
        return float(stars)
    span = grant_end - grant_start
    unused = grant_end - max(now, grant_start)
    if span <= 0 or unused <= 0:
        return 0.0
    return (stars if grant_value is None else grant_value) * min(unused / span, 1.0)


def apply_refund_purchase(state: PlanState, stars: int, grant_start, grant_end, now: float, grant_value=None) -> PlanState:
    """Aynan shu xarid bo'yicha refund: xaridning HALI FOYDALANILMAGAN qiymati joriy tarifdan ayriladi.
    Xarid qiymati boshqa tarifga ko'chirilgan bo'lsa (pastga/yuqoriga o'tish), db uning oralig'ini yangi davrga ko'chirib qo'yadi
    (grant_start/grant_end/grant_value), shuning uchun bu yerda faqat chiziqli hisob qoladi. Davri o'tib ketgan xarid — hech narsa ayrilmaydi.
    grant_* yo'q (eski yozuv) bo'lsa — oddiy apply_refund."""
    if grant_start is None or grant_end is None:
        return apply_refund(state, stars, now)
    if not is_active(state, now) or state.expires_at is None:
        return state
    value = carried_value(stars, grant_value, grant_start, grant_end, now)
    if value <= 0:
        return state
    end = state.expires_at - value / rate_of(state) * DAY
    if end <= now:
        return PlanState("free", None, None)
    return PlanState(state.plan, end, state.rate)
