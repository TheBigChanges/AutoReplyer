"""
Foydalanuvchi o'z akkountini Telegramning o'z "Chat Automation" (Settings ->
My Profile -> Chat Automations) funksiyasi orqali shu botga ulaydi. Hech qanday
telefon raqam, kod yoki parol so'rash shart emas — bularning barchasi
Telegramning o'zi tomonidan, o'zining rasmiy oqimida amalga oshiriladi.

Ulangach:
  - update.business_connection — ulanish/uzilish/huquq o'zgarishi haqida keladi
  - update.business_message — mijozdan kelgan xabar haqida keladi, shunga
    javob berish uchun business_connection_id kerak bo'ladi

Foydalanuvchi shu botga /start yozib, o'zining panelini ochadi:
online/offline, cooldown, avtojavob matni.
"""

import asyncio
import html
import logging
import os
import re
import threading
import weakref
from collections import deque
import time
from datetime import datetime
from datetime import time as dtime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest, Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

import secrets

import ai
import analytics
import db
from i18n import DEFAULT_LANG, LANG_NAMES, LANGS, all_defaults, is_lang, t
from logic import (
    ALL_DAYS_MASK,
    SCHEDULE_ALL_DAY,
    SCHEDULE_MAX_TEXT,
    SCHEDULE_PLAN_LIMITS,
    WEEKDAYS_MASK,
    WEEKEND_MASK,
    days_mask,
    find_active_schedule,
    format_day_set,
    is_all_day,
    mask_days,
    valid_schedule_time,
    bio_event_label,
    DEFAULT_NAME_CLOCK_STYLE,
    DEFAULT_NAME_CLOCK_ZONE,
    NAME_CLOCK_STYLES,
    NAME_CLOCK_ZONES,
    NAME_MAX_LENGTH,
    build_clock_name,
    compute_bio_text,
    format_cooldown,
    format_time_range,
    is_external_rename,
    is_known_style,
    is_known_zone,
    is_within_sleep_window,
    parse_birthday_input,
    add_plan_duration,
    parse_cooldown_input,
    parse_plan_duration,
    parse_time_range_input,
    split_full_name,
    style_time,
    strip_clock_suffix,
    zone_button_label,
    zone_label,
    FAQ_MAX_ANSWER,
    FAQ_PLAN_LIMITS,
    FAQ_MAX_KEYWORD_LENGTH,
    FAQ_MAX_KEYWORDS,
    FAQ_MAX_QUESTION,
    match_faq,
    KB_LIMIT,
    KB_MAX_CONTENT,
    KB_MAX_TITLE,
    parse_kb_keywords,
    select_knowledge,
    parse_faq_keywords,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
# httpx har bir so'rovni INFO'da URL bilan yozadi — Telegram URL'ida bot TOKENI bor,
# shuning uchun loglarda token chiqib ketmasligi uchun ogohlantirish darajasiga tushiramiz.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("autoreplyer")

TASHKENT_TZ = ZoneInfo("Asia/Tashkent")


def today_tashkent():
    """Toshkent vaqti bo'yicha bugungi sana. Server (Render) UTC'da ishlasa ham,
    BIO hisoblagich foydalanuvchining haqiqiy kuni bilan hisoblanishi uchun."""
    return datetime.now(TASHKENT_TZ).date()

BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ.get("BOT_USERNAME", "bot_username_bu_yerga")
# Sizning shaxsiy Telegram user ID'ingiz — faqat shu odam referral statistikasini
# (barcha foydalanuvchilar bo'yicha) ko'ra oladi. @userinfobot'dan olish mumkin.
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
# Majburiy obuna (force-subscribe): kanal ID'si (masalan -1001234567890) va
# unga olib boruvchi havola. Ikkalasi ham bo'lmasa, tekshiruv butunlay
# o'chirilgan hisoblanadi. Bot bu kanalda ADMIN bo'lishi SHART — aks holda
# a'zolikni tekshira olmaydi.
_required_channel_id_raw = os.environ.get("REQUIRED_CHANNEL_ID", "").strip()
if _required_channel_id_raw:
    try:
        REQUIRED_CHANNEL_ID: int | str | None = int(_required_channel_id_raw)
    except ValueError:
        REQUIRED_CHANNEL_ID = _required_channel_id_raw  # "@channel_username" shaklida ham bo'lishi mumkin
else:
    REQUIRED_CHANNEL_ID = None
REQUIRED_CHANNEL_LINK = os.environ.get("REQUIRED_CHANNEL_LINK", "").strip() or None

if bool(REQUIRED_CHANNEL_ID) != bool(REQUIRED_CHANNEL_LINK):
    logger.warning(
        "REQUIRED_CHANNEL_ID va REQUIRED_CHANNEL_LINK ikkalasi ham birga sozlanishi kerak — "
        "hozircha faqat bittasi bor, shuning uchun majburiy obuna tekshiruvi O'CHIRILGAN."
    )
    REQUIRED_CHANNEL_ID = None
    REQUIRED_CHANNEL_LINK = None

# owner_user_id -> "cooldown" | "text"  (panel orqali nimani tahrirlayotgani)
pending_settings_action: dict[int, str] = {}
# owner_user_id -> "broadcast"  (admin /reklama oqimida)
pending_admin_action: dict[int, str] = {}

# Tugallanmagan amal (masalan "yangi matn yuboring") shuncha vaqtdan keyin o'z-o'zidan
# bekor bo'ladi — aks holda foydalanuvchining keyingi har qanday xabari tasodifan
# avtojavob matniga aylanib qolardi.
PENDING_ACTION_TTL_SECONDS = 10 * 60
_pending_settings_set_at: dict[int, float] = {}
_pending_admin_set_at: dict[int, float] = {}


def set_pending_action(user_id: int, action: str):
    pending_settings_action[user_id] = action
    _pending_settings_set_at[user_id] = time.time()


def clear_pending_action(user_id: int) -> bool:
    """Tugallanmagan panel amalini bekor qiladi. True — haqiqatan nimadir bekor qilindi."""
    _pending_settings_set_at.pop(user_id, None)
    return pending_settings_action.pop(user_id, None) is not None


def get_pending_action(user_id: int) -> str | None:
    action = pending_settings_action.get(user_id)
    if action is None:
        return None
    started = _pending_settings_set_at.get(user_id)
    if started is not None and time.time() - started > PENDING_ACTION_TTL_SECONDS:
        clear_pending_action(user_id)
        return None
    return action


def set_pending_admin_action(user_id: int, action: str):
    pending_admin_action[user_id] = action
    _pending_admin_set_at[user_id] = time.time()


def clear_pending_admin_action(user_id: int) -> bool:
    _pending_admin_set_at.pop(user_id, None)
    return pending_admin_action.pop(user_id, None) is not None


def get_pending_admin_action(user_id: int) -> str | None:
    action = pending_admin_action.get(user_id)
    if action is None:
        return None
    started = _pending_admin_set_at.get(user_id)
    if started is not None and time.time() - started > PENDING_ACTION_TTL_SECONDS:
        clear_pending_admin_action(user_id)
        return None
    return action


# Fonda ishlaydigan vazifalarga (reklama) kuchli havola: aks holda event loop ularga
# faqat zaif havola saqlaydi va Python vazifani ish o'rtasida yig'ishtirib yuborishi mumkin.
_background_tasks: set = set()


def spawn_background(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


# user_id -> til kodi (faqat bazadan o'qilgan to'g'ri qiymatlar keshlanadi)
_lang_cache: dict[int, str] = {}


def get_lang(user_id) -> str:
    """Foydalanuvchining tanlagan tili; tanlamagan yoki baza xato bersa — o'zbekcha."""
    cached = _lang_cache.get(user_id)
    if cached:
        return cached
    try:
        lang = db.get_user_lang(user_id)
    except Exception:
        return DEFAULT_LANG
    if is_lang(lang):
        _lang_cache[user_id] = lang
        return lang
    return DEFAULT_LANG


def has_chosen_lang(user_id) -> bool:
    if user_id in _lang_cache:
        return True
    try:
        return is_lang(db.get_user_lang(user_id))
    except Exception:
        return True  # baza xatosida til tanlashni qayta-qayta so'ramaymiz


def set_lang(user_id: int, lang: str) -> None:
    db.set_user_lang(user_id, lang)
    _lang_cache[user_id] = lang


def build_lang_markup(inviter_id: int | None = None):
    """Til tanlash tugmalari. Taklif qilgan odam ID'si tugma ichida olib yuriladi (referal yo'qolmasin)."""
    suffix = f":{inviter_id}" if inviter_id else ""
    rows = [[InlineKeyboardButton(LANG_NAMES[code], callback_data=f"lang:{code}{suffix}")] for code in LANGS]
    return InlineKeyboardMarkup(rows)


def auto_reply_text_for(settings: dict, lang: str) -> str:
    """Egasi o'zi matn yozmagan bo'lsa (standart) — uning tilidagi standart matn."""
    text = settings.get("auto_reply_text") or ""
    return t(lang, "default_auto_reply") if (not text or text in all_defaults("default_auto_reply")) else text


def sleep_text_for(settings: dict, lang: str) -> str:
    text = settings.get("sleep_reply_text") or ""
    return t(lang, "default_sleep") if (not text or text in all_defaults("default_sleep")) else text


def track_user(user):
    """Foydalanuvchini (va uning username/ismini) bazaga yozadi. Username
    saqlanishi sababli admin /block @username bilan odamni topa oladi."""
    if user is None or getattr(user, "is_bot", False):
        return  # botlar "foydalanuvchi" emas: ro'yxat, /stats va reklamaga kirmasin
    db.record_user(user.id, username=user.username, full_name=user.full_name)
    # Ism soati yoqilgan egasi botga biror narsa yozsa/bossa, uning joriy ismi shu yerda keladi —
    # o'zi o'zgartirgan bo'lsa, darhol yangi ismni asl ism qilib olamiz.
    if name_clock_allowed(user.id):
        try:
            adopt_new_base_name(user.id, getattr(user, "first_name", None), getattr(user, "last_name", None))
        except Exception:
            logger.exception("Ism soati: yangi ismni olishda xato (owner=%s)", user.id)

def how_connect_text(lang: str = DEFAULT_LANG) -> str:
    return t(lang, "how_connect", bot=BOT_USERNAME)


HOW_CONNECT_TEXT = how_connect_text("uz")  # eski nom (o'zbekcha)


async def apply_bio_update(bot, owner_id: int) -> tuple[bool, str]:
    """Bitta foydalanuvchining BIO'sini hozirgi sozlamalariga qarab yangilaydi."""
    lang = get_lang(owner_id)
    connection = db.get_connection(owner_id)
    settings = db.get_settings(owner_id)
    target = settings.get("bio_countdown_target")

    if not connection or not connection["is_enabled"]:
        return False, t(lang, "bio_err_not_connected")
    if not connection.get("can_edit_bio"):
        return False, t(lang, "bio_err_no_perm")
    if not target:
        return False, t(lang, "bio_err_off")

    text = compute_bio_text(
        target, settings.get("birthday_month"), settings.get("birthday_day"), today=today_tashkent(), lang=lang
    )
    if text is None:
        return False, t(lang, "bio_err_no_birthday")

    try:
        await bot.set_business_account_bio(
            business_connection_id=connection["business_connection_id"], bio=text
        )
        db.update_settings(owner_id, bio_updated_on=today_tashkent().isoformat())
        return True, text
    except TelegramError as e:
        logger.warning("BIO yangilash xatosi (owner=%s): %s", owner_id, e)
        return False, str(e)


async def refresh_bios(bot, only_stale: bool) -> tuple[int, int]:
    """Faol BIO hisoblagichlarni yangilaydi. Muvaffaqiyatli yangilangan har bir
    ulanish uchun bugungi (Toshkent) sana `bio_updated_on` ga yoziladi.

    only_stale=True — faqat bugun HALI yangilanmaganlarni (startup "yetkazib
    olish" rejimi); False — hammasini (kunlik 00:05 job). Startup'da faqat
    eskirganlarni yangilash har restartda hamma foydalanuvchi uchun Telegram
    API'ni bekorga qayta-qayta chaqirmaslik uchun."""
    today = today_tashkent()
    today_iso = today.isoformat()
    rows = db.get_all_bio_targets()
    if only_stale:
        rows = [r for r in rows if r.get("bio_updated_on") != today_iso]
    updated, failed = 0, 0
    for row in rows:
        if not plan_allows(row["owner_user_id"], row.get("plan"), "bio"):
            continue  # tarif pasaygan: BIO hisoblagich yangilanmaydi
        if not sub_ok_sync(row["owner_user_id"]):
            continue  # kanalga obuna emas: BIO hisoblagich yangilanmaydi
        text = compute_bio_text(
            row["bio_countdown_target"], row["birthday_month"], row["birthday_day"], today=today,
            lang=row.get("lang") if is_lang(row.get("lang")) else DEFAULT_LANG,
        )
        if text is None:
            continue
        try:
            await bot.set_business_account_bio(
                business_connection_id=row["business_connection_id"], bio=text
            )
            db.update_settings(row["owner_user_id"], bio_updated_on=today_iso)
            updated += 1
        except TelegramError as e:
            failed += 1
            logger.warning("BIO yangilash xatosi (owner=%s): %s", row["owner_user_id"], e)
    return updated, failed


async def bio_daily_job(context: ContextTypes.DEFAULT_TYPE):
    """Har kuni (Toshkent vaqti bilan 00:05) barcha faol BIO hisoblagichlarni yangilaydi."""
    logger.info("BIO kunlik yangilash boshlandi")
    updated, failed = await refresh_bios(context.bot, only_stale=False)
    logger.info("BIO kunlik yangilash tugadi: %d muvaffaqiyatli, %d xato", updated, failed)


async def bio_startup_job(context: ContextTypes.DEFAULT_TYPE):
    """Server ishga tushganda BIR marta: agar 00:05 da server o'chiq bo'lgani
    uchun bugungi yangilash o'tkazib yuborilgan bo'lsa, shuni darhol yetkazadi
    (faqat bugun hali yangilanmaganlarni). So'ng odatdagi 00:05 jadvali davom etadi."""
    logger.info("BIO startup tekshiruvi boshlandi")
    updated, failed = await refresh_bios(context.bot, only_stale=True)
    logger.info("BIO startup tekshiruvi tugadi: %d yangilandi, %d xato", updated, failed)


# ---------------------------------------------------------------------------
# Menyu va panel
# ---------------------------------------------------------------------------
SUB_CACHE_OK_SECONDS = 600.0   # a'zo bo'lgan odam natijasi shuncha vaqt eslab qolinadi
SUB_CACHE_NO_SECONDS = 60.0    # a'zo bo'lmagan odam tezroq qayta tekshiriladi (obuna bo'lgach tez tiklansin)
_sub_cache: dict[int, tuple[float, bool]] = {}
_sub_notice_at: dict[int, float] = {}
SUB_NOTICE_COOLDOWN_SECONDS = 24 * 3600.0
_gate_reply_at: dict[int, float] = {}
GATE_REPLY_COOLDOWN_SECONDS = 3.0


def _sub_exempt(user_id: int) -> bool:
    """Tekshiruvdan ozod: majburiy kanal sozlanmagan yoki admin."""
    return REQUIRED_CHANNEL_ID is None or (bool(ADMIN_ID) and user_id == ADMIN_ID)


async def check_membership(bot, user_id: int) -> bool | None:
    """Telegramdan HAQIQIY a'zolikni so'raydi va keshga yozadi. True/False; xato bo'lsa None
    (keshga yozilmaydi)."""
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
    except TelegramError as e:
        logger.warning(
            "Obuna tekshiruvida xato (user=%s, channel=%s): %s — bot kanalda admin ekanini tekshiring",
            user_id, REQUIRED_CHANNEL_ID, e,
        )
        return None
    ok = member.status not in ("left", "kicked")
    _sub_cache[user_id] = (time.time(), ok)
    return ok


async def is_subscribed(bot, user_id: int) -> bool:
    """Majburiy kanalga a'zoligini (har doim yangidan) tekshiradi. Sozlanmagan bo'lsa — True.
    Xato chiqsa (masalan bot kanalda admin emas) — butun botni to'sib qo'ymaslik uchun
    ruxsat berilgan deb olinadi, lekin loglanadi."""
    if REQUIRED_CHANNEL_ID is None:
        return True
    ok = await check_membership(bot, user_id)
    return True if ok is None else ok


async def is_subscribed_cached(bot, user_id: int) -> bool:
    """Har bir xabar/tugma uchun: kesh yangi bo'lsa — API'siz javob beradi."""
    if _sub_exempt(user_id):
        return True
    hit = _sub_cache.get(user_id)
    if hit is not None:
        ttl = SUB_CACHE_OK_SECONDS if hit[1] else SUB_CACHE_NO_SECONDS
        if time.time() - hit[0] < ttl:
            return hit[1]
    return await is_subscribed(bot, user_id)


def sub_ok_sync(user_id: int) -> bool:
    """Faqat keshga qaraydi (tarmoqsiz): ism soati/BIO kabi ommaviy sikllar uchun. Noma'lum — ruxsat."""
    if _sub_exempt(user_id):
        return True
    hit = _sub_cache.get(user_id)
    return True if hit is None else hit[1]


async def notify_subscription_lost(bot, user_id: int):
    """Funksiyalar to'xtaganini bildiradi (kuniga ko'pi bilan 1 marta)."""
    now = time.time()
    if now - _sub_notice_at.get(user_id, 0.0) < SUB_NOTICE_COOLDOWN_SECONDS:
        return
    _sub_notice_at[user_id] = now
    lang = get_lang(user_id)
    await _try_send(bot, user_id, t(lang, "gate_lost"), build_subscribe_gate_markup(None, lang))


async def subscription_refresh_job(context: ContextTypes.DEFAULT_TYPE):
    """Har daqiqada: ism soati/BIO yoqilgan odamlarning obunasini (keshi eskirganlarni) yangilaydi.
    Obunani yo'qotgan odamning ismi asl holiga qaytariladi va unga xabar yuboriladi."""
    if REQUIRED_CHANNEL_ID is None:
        return
    try:
        ids = {r["owner_user_id"] for r in db.get_name_clock_targets()}
        ids |= {r["owner_user_id"] for r in db.get_all_bio_targets()}
    except Exception:
        logger.exception("Obuna yangilash: ro'yxat o'qilmadi")
        return
    now = time.time()
    for uid in ids:
        if _sub_exempt(uid):
            continue
        hit = _sub_cache.get(uid)
        if hit is not None and now - hit[0] < (SUB_CACHE_OK_SECONDS if hit[1] else SUB_CACHE_NO_SECONDS):
            continue
        was_ok = hit[1] if hit is not None else True
        ok = await check_membership(context.bot, uid)
        if ok is False and was_ok:
            try:
                await restore_base_name(context.bot, uid)
            except Exception:
                logger.exception("Obuna yo'qolganda ismni qaytarishda xato (owner=%s)", uid)
            await notify_subscription_lost(context.bot, uid)
        await asyncio.sleep(0.05)


def build_subscribe_gate_markup(inviter_id: int | None = None, lang: str = DEFAULT_LANG):
    # Taklif qilgan odamning ID'si tugma ichida (callback_data) olib yuriladi: shunda
    # foydalanuvchi obuna bo'lib "Tekshirish"ni bosganda referal yo'qolmaydi
    # (holat RAM'da emas — server restart bo'lsa ham saqlanadi). Limit 64 bayt.
    check_data = f"check_subscription:{inviter_id}" if inviter_id else "check_subscription"
    keyboard = [
        [InlineKeyboardButton(t(lang, "gate_btn_channel"), url=REQUIRED_CHANNEL_LINK)],
        [InlineKeyboardButton(t(lang, "gate_btn_check"), callback_data=check_data)],
    ]
    return InlineKeyboardMarkup(keyboard)


def parse_referral_arg(args) -> int | None:
    """/start ref_123 -> 123 (noto'g'ri bo'lsa None)."""
    if not args:
        return None
    arg = args[0]
    if not arg.startswith("ref_"):
        return None
    digits = arg[4:]
    # Faqat oddiy ASCII raqamlar, real Telegram ID uzunligida: aks holda juda uzun ID tugma
    # ma'lumotini (64 bayt) oshirib yoki BIGINT'dan toshib, /start'ni yiqitardi.
    if not re.fullmatch(r"[0-9]{1,15}", digits):
        return None
    inviter_id = int(digits)
    return inviter_id if inviter_id > 0 else None


async def process_referral(bot, owner_id: int, inviter_id: int | None):
    """Referalni yozadi va taklif qilgan odamga xabar beradi (faqat yangi bo'lsa)."""
    if not inviter_id:
        return
    if not db.record_referral(referred_user_id=owner_id, inviter_user_id=inviter_id):
        return
    try:
        await bot.send_message(
            chat_id=inviter_id,
            text=t(get_lang(inviter_id), "referral_joined"),
        )
    except TelegramError as e:
        logger.info("Referral bildirishnomasi yuborilmadi (inviter=%s): %s", inviter_id, e)


SUBSCRIBE_GATE_TEXT = t("uz", "gate_text")  # eski nom (o'zbekcha)


# ---------------------------------------------------------------------------
# Smart Onboarding: yangi foydalanuvchini ulash -> Auto-Reply -> sinov bosqichlariga yo'naltirish.
# Majburiy emas: har bosqichda "O'tkazib yuborish" bor; eski foydalanuvchilar ('legacy') ko'rmaydi.
# ---------------------------------------------------------------------------
ONBOARDING_ACTIVE = db.ONBOARDING_ACTIVE_STEPS  # connect, configure, verify


def _ob_state(owner_id: int) -> dict:
    conn = db.get_connection(owner_id)
    enabled = bool(conn and conn["is_enabled"])
    can_reply = bool(enabled and conn["can_reply"])
    settings = db.get_settings(owner_id)
    return {
        "enabled": enabled,
        "can_reply": can_reply,
        "offline": bool(settings.get("offline")),
        "settings": settings,
    }


def _ob_target_step(owner_id: int) -> str:
    """Haqiqiy holatga qarab qaysi bosqich ko'rsatilishi kerak (bazadagi holat emas — haqiqat)."""
    st = _ob_state(owner_id)
    if not st["can_reply"]:
        return "connect"
    if not st["offline"]:
        return "configure"
    return "verify"


def _ob_checks_text(lang: str, st: dict) -> str:
    rows = (
        (st["enabled"], "ob_chk_connected"),
        (st["can_reply"], "ob_chk_reply"),
        (st["offline"], "ob_chk_enabled"),
    )
    return "\n".join(("✅ " if ok else "❌ ") + t(lang, key) for ok, key in rows)


def _ob_skip_row(lang: str):
    return [InlineKeyboardButton(t(lang, "btn_ob_skip"), callback_data="ob_skip")]


def build_onboarding_view(owner_id: int, step: str, welcome: bool = False):
    """Berilgan bosqich uchun (matn, tugmalar)."""
    lang = get_lang(owner_id)
    if step == "connect":
        text = (t(lang, "ob_welcome") if welcome else "") + t(lang, "ob_connect", bot=BOT_USERNAME)
        rows = [[InlineKeyboardButton(t(lang, "btn_ob_check"), callback_data="ob_check")], _ob_skip_row(lang)]
    elif step == "configure":
        st = _ob_state(owner_id)
        plan_note = t(lang, "ob_plan_paid" if has_feature(owner_id, "custom_text") else "ob_plan_free")
        text = t(lang, "ob_configure", text=auto_reply_text_for(st["settings"], lang)[:MENU_TEXT_PREVIEW_CHARS], plan_note=plan_note)
        rows = [[InlineKeyboardButton(t(lang, "btn_ob_enable"), callback_data="ob_enable")], _ob_skip_row(lang)]
    else:  # verify
        text = t(lang, "ob_verify", checks=_ob_checks_text(lang, _ob_state(owner_id)))
        rows = [
            [
                InlineKeyboardButton(t(lang, "btn_ob_ok"), callback_data="ob_ok"),
                InlineKeyboardButton(t(lang, "btn_ob_fail"), callback_data="ob_fail"),
            ],
            _ob_skip_row(lang),
        ]
    return text, InlineKeyboardMarkup(rows)


def onboarding_start_view(owner_id: int):
    """/start paytida: onboarding kerak bo'lsa (matn, tugmalar), kerak bo'lmasa None.
    'welcome' -> birinchi marta; connect/configure/verify -> qolgan joyidan davom ettirish."""
    step = db.get_onboarding_step(owner_id)
    if step == "welcome":
        target = _ob_target_step(owner_id)
        db.set_onboarding_step(owner_id, target, only_from=("welcome",))
        return build_onboarding_view(owner_id, target, welcome=True)
    if step in ONBOARDING_ACTIVE:
        target = _ob_target_step(owner_id)
        if target != step:
            db.set_onboarding_step(owner_id, target, only_from=ONBOARDING_ACTIVE)
        return build_onboarding_view(owner_id, target)
    return None


def onboarding_view_on_connection(owner_id: int):
    """Business ulanish hodisasi kelganda: onboarding'dagi foydalanuvchini keyingi bosqichga
    o'tkazadi va yangi ekranni qaytaradi. Onboarding'da bo'lmasa yoki bosqich o'zgarmasa — None."""
    step = db.get_onboarding_step(owner_id)
    if step != "welcome" and step not in ONBOARDING_ACTIVE:
        return None
    target = _ob_target_step(owner_id)
    if step != "welcome" and target == step:
        return None
    db.set_onboarding_step(owner_id, target, only_from=("welcome",) + tuple(ONBOARDING_ACTIVE))
    return build_onboarding_view(owner_id, target)


async def _ob_edit(query, text: str, markup):
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            raise


async def handle_onboarding_callback(query, owner_id: int, data: str):
    """ob_* tugmalari. Har bir shox query.answer() ni aynan BIR marta chaqiradi."""
    lang = get_lang(owner_id)
    action = data[3:]
    step = db.get_onboarding_step(owner_id)

    async def bad():
        await query.answer(t(lang, "bad_button"), show_alert=True)

    async def need_connection() -> bool:
        """Ulanish yo'q/ruxsat yo'q bo'lsa alert ko'rsatadi va True qaytaradi."""
        st = _ob_state(owner_id)
        if not st["enabled"]:
            await query.answer(t(lang, "ob_not_connected"), show_alert=True)
            return True
        if not st["can_reply"]:
            await query.answer(t(lang, "ob_no_reply_perm"), show_alert=True)
            return True
        return False

    if action == "resume":
        if step != "skipped" and step not in ONBOARDING_ACTIVE:
            await bad()
            return
        target = _ob_target_step(owner_id)
        db.set_onboarding_step(owner_id, target, only_from=("skipped",) + tuple(ONBOARDING_ACTIVE))
        await query.answer()
        text, markup = build_onboarding_view(owner_id, target)
        await _ob_edit(query, text, markup)
        return

    if step not in ONBOARDING_ACTIVE or action not in ("check", "enable", "ok", "fail", "skip"):
        await bad()
        return

    if action == "skip":
        db.set_onboarding_step(owner_id, "skipped", only_from=ONBOARDING_ACTIVE)
        await query.answer()
        await _ob_edit(query, t(lang, "ob_skipped"), main_menu_markup(owner_id))
        return

    if action == "check":
        if await need_connection():
            return
        target = _ob_target_step(owner_id)
        db.set_onboarding_step(owner_id, target, only_from=ONBOARDING_ACTIVE)
        await query.answer()
        text, markup = build_onboarding_view(owner_id, target)
        await _ob_edit(query, text, markup)
        return

    if action == "enable":
        if step == "connect":
            await bad()
            return
        if await need_connection():
            return
        db.update_settings(owner_id, offline=True)
        db.set_onboarding_step(owner_id, "verify", only_from=ONBOARDING_ACTIVE)
        await query.answer()
        text, markup = build_onboarding_view(owner_id, "verify")
        await _ob_edit(query, text, markup)
        return

    # ok / fail faqat 'verify' bosqichida
    if step != "verify":
        await bad()
        return
    if action == "ok":
        if await need_connection():
            return
        if not _ob_state(owner_id)["offline"]:
            # Auto-Reply o'chirilgan bo'lsa tugatib bo'lmaydi — 2/3 bosqichga qaytaramiz
            await query.answer(t(lang, "ob_not_enabled"), show_alert=True)
            db.set_onboarding_step(owner_id, "configure", only_from=("verify",))
            text, markup = build_onboarding_view(owner_id, "configure")
            await _ob_edit(query, text, markup)
            return
        db.set_onboarding_step(owner_id, "completed", only_from=("verify",))
        await query.answer()
        await _ob_edit(query, t(lang, "ob_done"), main_menu_markup(owner_id))
        return
    # fail: sabablarni tekshirib ko'rsatamiz
    st = _ob_state(owner_id)
    sleep = t(lang, "ob_fail_sleep") if st["settings"].get("sleep_mode_enabled") else ""
    hours = st["settings"].get("cooldown_hours")
    hours = f"{hours:g}" if isinstance(hours, (int, float)) else str(hours)
    text = t(lang, "ob_fail", checks=_ob_checks_text(lang, st), hours=hours, sleep=sleep)
    _, markup = build_onboarding_view(owner_id, "verify")
    await query.answer()
    await _ob_edit(query, text, markup)


def build_start_view(owner_id: int):
    """Bosh menyu matni va tugmalarini qaytaradi (obunadan o'tgan foydalanuvchi uchun)."""
    lang = get_lang(owner_id)
    conn = db.get_connection(owner_id)
    greeting = t(lang, "greeting_connected" if (conn and conn["is_enabled"]) else "greeting_new")
    return greeting, main_menu_markup(owner_id)


def onboarding_step_of(owner_id: int) -> str:
    """Onboarding holati; baza xatosi menyuni buzmasin — shunda 'legacy' (hech narsa ko'rsatilmaydi)."""
    try:
        return db.get_onboarding_step(owner_id)
    except Exception:
        logger.exception("Onboarding holatini o'qishda xato (owner=%s)", owner_id)
        return "legacy"


def main_menu_markup(owner_id: int):
    lang = get_lang(owner_id)
    conn = db.get_connection(owner_id)
    rows = []
    if onboarding_step_of(owner_id) == "skipped":
        rows.append([InlineKeyboardButton(t(lang, "btn_ob_resume"), callback_data="ob_resume")])
    if conn and conn["is_enabled"]:
        rows.append([InlineKeyboardButton(t(lang, "btn_open_panel"), callback_data="open_panel")])
    else:
        rows.append([InlineKeyboardButton(t(lang, "btn_how_connect"), callback_data="how_connect")])
    rows.append([InlineKeyboardButton(t(lang, "btn_referral"), callback_data="referral")])
    rows.append([InlineKeyboardButton(t(lang, "btn_plans"), callback_data="plans")])
    rows.append([InlineKeyboardButton(t(lang, "btn_support"), callback_data="support")])
    rows.append([InlineKeyboardButton(t(lang, "btn_language"), callback_data="lang_menu")])
    if owner_id == ADMIN_ID:
        rows.append([InlineKeyboardButton("\U0001F4CA Referral statistikasi (admin)", callback_data="admin_referrals")])
    return InlineKeyboardMarkup(rows)


# Tariflar: (kalit, emoji, narx so'mda). "free" — hamma shundan boshlaydi.
PLANS = (
    ("free", "\U0001F530", 0),
    ("plus", "\u23F0", 2000),
    ("pro", "\u2728", 5000),
    ("ultra", "\u2B50", 10000),
)
PLAN_KEYS = tuple(k for k, _, _ in PLANS)
# To'lov kartasi Render muhit o'zgaruvchilarida saqlanadi (kodga yozilmaydi)
PAYMENT_CARD_NUMBER = os.environ.get("PAYMENT_CARD_NUMBER", "").strip()
PAYMENT_CARD_HOLDER = os.environ.get("PAYMENT_CARD_HOLDER", "Malika Abdukarimova").strip()


def format_card_number(raw: str) -> str:
    digits = re.sub(r"\s+", "", raw)
    return " ".join(digits[i:i + 4] for i in range(0, len(digits), 4)) if digits.isdigit() else raw


# Qaysi funksiya qaysi tariflarda ochiq. Admin (ADMIN_ID) hamma narsadan cheklovsiz foydalanadi.
# Bo'sh ro'yxat — hech bir tarifda ochiq emas (faqat admin).
DEFAULT_FEATURE_PLANS = {
    "bio": ("pro", "ultra"),            # BIO hisoblagich
    "custom_text": ("plus", "pro", "ultra"),  # avtojavob / uxlash matnini o'zgartirish
    "ai": ("ultra",),                   # AI-Yordamchi
    "name_clock_fonts": ("ultra",),    # ism soatining standart bo'lmagan shriftlari
    "name_clock_zones": ("pro", "ultra"),  # ism soatining Toshkentdan boshqa vaqt zonalari
    "faq": ("plus", "pro", "ultra"),    # Smart FAQ (savollar soni tarifga qarab: FAQ_PLAN_LIMITS)
    "kb": ("ultra",),                   # AI Bilimlar bazasi (AI bilan birga ishlaydi; KB_LIMIT ta yozuv)
    "scheduler": ("free", "plus", "pro", "ultra"),  # Smart Jadval (jadvallar soni: SCHEDULE_PLAN_LIMITS)
    "analytics_7": ("plus", "pro", "ultra"),   # Statistika: 7 kunlik davr
    "analytics_30": ("pro", "ultra"),          # Statistika: 30 kunlik davr
    "analytics_charts": ("plus", "pro", "ultra"),  # Statistika grafiklari (turlari tarifga qarab)
    "analytics_full": ("ultra",),              # Batafsil statistika + barcha grafiklar
}
FEATURE_PLANS = dict(DEFAULT_FEATURE_PLANS)
FEATURE_NAME_KEYS = {
    "bio": "feature_bio", "custom_text": "feature_text", "ai": "feature_ai", "name_clock_fonts": "feature_fonts",
    "name_clock_zones": "feature_zones", "faq": "feature_faq", "kb": "feature_kb",
    "analytics_7": "feature_an7", "analytics_30": "feature_an30", "analytics_charts": "feature_anch",
    "analytics_full": "feature_anfull", "scheduler": "feature_sched",
}


def plan_allows(user_id: int, plan: str | None, feature: str) -> bool:
    if ADMIN_ID and user_id == ADMIN_ID:
        return True
    return (plan or "free") in FEATURE_PLANS.get(feature, ())


def plan_of(user_id: int) -> str:
    try:
        return db.get_user_plan(user_id)
    except Exception:
        return "free"


AD_FREE_PLANS = ("plus", "pro", "ultra")  # pullik tariflarda reklama yo'q


def shows_ads(user_id: int, plan: str | None = None) -> bool:
    """Bepul tarifdagi (admin emas) egaga reklama qo'shiladi."""
    if ADMIN_ID and user_id == ADMIN_ID:
        return False
    return (plan if plan is not None else plan_of(user_id)) not in AD_FREE_PLANS


def with_ad(text: str, owner_id: int) -> str:
    """Avtojavob matni tagiga (ikki bo'sh qator qoldirib) reklama qo'shadi (faqat bepul tarifda)."""
    if not shows_ads(owner_id):
        return text
    ad = t(get_lang(owner_id), "ad_reply")
    suffix = "\n\n" + ad
    room = 4096 - len(suffix)
    return (text[:room] if len(text) > room else text) + suffix


async def reconcile_clock_bio_ads(bot):
    """Bepul tarifda ism soati yoqilgan bo'lsa — BIO'ga reklama yoziladi; yoqilmagan/pullik bo'lsa — olib tashlanadi
    (BIO hisoblagich bo'lsa u qaytariladi, bo'lmasa BIO bo'shatiladi)."""
    try:
        rows = db.get_bio_ad_candidates()
    except Exception:
        logger.exception("BIO reklamasi: ro'yxat o'qilmadi")
        return
    for row in rows:
        uid = row["owner_user_id"]
        want = bool(row["name_clock_enabled"]) and shows_ads(uid, row.get("plan"))
        have = bool(row["clock_bio_ad"])
        if want == have or (want and not sub_ok_sync(uid)):
            continue
        lang = row.get("lang") if is_lang(row.get("lang")) else DEFAULT_LANG
        if want:
            bio = t(lang, "ad_bio")
        else:
            bio = ""
            if row.get("bio_countdown_target") and plan_allows(uid, row.get("plan"), "bio"):
                bio = compute_bio_text(
                    row["bio_countdown_target"], row.get("birthday_month"), row.get("birthday_day"),
                    today=today_tashkent(), lang=lang,
                ) or ""
        try:
            await bot.set_business_account_bio(business_connection_id=row["business_connection_id"], bio=bio)
            db.update_settings(uid, clock_bio_ad=want)
        except TelegramError as e:
            logger.info("BIO reklamasi o'zgartirilmadi (owner=%s): %s", uid, e)
        except Exception:
            logger.exception("BIO reklamasi xatosi (owner=%s)", uid)
        await asyncio.sleep(0.05)


async def clock_bio_ad_job(context: ContextTypes.DEFAULT_TYPE):
    await reconcile_clock_bio_ads(context.bot)


def has_feature(user_id: int, feature: str) -> bool:
    return plan_allows(user_id, plan_of(user_id), feature)


def schedule_limit_for(user_id: int, plan: str | None = None) -> int:
    """Nechta jadval yaratish mumkin (tarifga qarab). Admin — eng yuqori limit."""
    if ADMIN_ID and user_id == ADMIN_ID:
        return max(SCHEDULE_PLAN_LIMITS.values())
    plan = plan if plan is not None else plan_of(user_id)
    return SCHEDULE_PLAN_LIMITS.get(plan, SCHEDULE_PLAN_LIMITS["free"])


def kb_limit_for(user_id: int, plan: str | None = None) -> int:
    """Bilimlar bazasida nechta yozuv saqlash mumkin (0 — tarifda yo'q). Admin ham KB_LIMIT bilan cheklanadi."""
    plan = plan if plan is not None else plan_of(user_id)
    return KB_LIMIT if plan_allows(user_id, plan, "kb") else 0


def faq_limit_for(user_id: int, plan: str | None = None) -> int:
    """Smart FAQ'da nechta savol saqlash mumkin (0 — Smart FAQ ochiq emas). Admin — eng yuqori limit."""
    plan = plan if plan is not None else plan_of(user_id)
    if not plan_allows(user_id, plan, "faq"):
        return 0
    if ADMIN_ID and user_id == ADMIN_ID:
        return max(FAQ_PLAN_LIMITS.values())
    return FAQ_PLAN_LIMITS.get(plan, min(FAQ_PLAN_LIMITS.values()))


def locked_text(lang: str, feature: str) -> str:
    plans = FEATURE_PLANS.get(feature, ())
    name = t(lang, FEATURE_NAME_KEYS[feature])
    if not plans:
        return t(lang, "locked_unavailable", feature=name)
    return t(lang, "locked_feature", feature=name, plans=" / ".join(t(lang, "plan_name_" + p) for p in plans))


def build_locked_view(owner_id: int, feature: str, back_data: str = "open_panel"):
    lang = get_lang(owner_id)
    rows = []
    if FEATURE_PLANS.get(feature):
        rows.append([InlineKeyboardButton(t(lang, "btn_plans"), callback_data="plans")])
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data=back_data)])
    return locked_text(lang, feature), InlineKeyboardMarkup(rows)


def locked_feature_for(data: str) -> str | None:
    """Tugma ma'lumotidan qaysi tarif-cheklangan funksiyaga tegishli ekanini aniqlaydi."""
    if data in ("bio_menu", "bio_set_new_year", "bio_set_navroz", "bio_set_birthday"):
        return "bio"
    if data in ("edit_text", "sleep_edit_text"):
        return "custom_text"
    if data == "ai_menu" or data.startswith("ai_"):
        return "ai"
    if data.startswith("faq_"):
        return "faq"
    if data.startswith("kb_"):
        return "kb"
    if data.startswith("sc_ed:text"):
        return "custom_text"  # jadval uchun alohida matn — Plus'dan
    if data == "an:7":
        return "analytics_7"
    if data == "an:30":
        return "analytics_30"
    if data.startswith("an_ch:"):
        return "analytics_charts"
    if data.startswith("an_detail"):
        return "analytics_full"
    return None


def lock_label(label: str, allowed: bool) -> str:
    return label if allowed else "\U0001F512 " + label


def format_plan_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, TASHKENT_TZ).strftime("%d.%m.%Y")


def plan_price_label(lang: str, price: int) -> str:
    return t(lang, "plan_price", price=f"{price:,}")


def build_plans_menu(owner_id: int):
    lang = get_lang(owner_id)
    try:
        current = db.get_user_plan(owner_id)
    except Exception:
        current = "free"
    rows = []
    for key, emoji, price in PLANS:
        name = t(lang, "plan_name_" + key)
        label = f"{emoji} {name} - " + (plan_price_label(lang, price) if price else "")
        if key == current:
            label = f"{emoji} {name} - {t(lang, 'plan_active')} \u2705"
        elif not price:
            label = f"{emoji} {name}"
        rows.append([InlineKeyboardButton(label, callback_data=f"plan:{key}")])
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="back")])
    return t(lang, "plans_menu"), InlineKeyboardMarkup(rows)


def plan_features_text(lang: str, plan: str) -> str:
    """Tarifga nimalar kirishi va kirmasligi — oddiy foydalanuvchi tushunadigan ro'yxat.
    Manba — haqiqiy cheklovlar jadvali (FEATURE_PLANS), shuning uchun matn doim amaldagi holatga mos."""
    fonts_ok = plan in FEATURE_PLANS.get("name_clock_fonts", ())
    zones_ok = plan in FEATURE_PLANS.get("name_clock_zones", ())
    clock_key = "pf_clock_full" if fonts_ok and zones_ok else "pf_clock_zones" if zones_ok else "pf_clock_fonts" if fonts_ok else "pf_clock"
    items = (
        (None, "pf_autoreply", {}),
        (None, "pf_sleep", {}),
        (None, clock_key, {}),
        ("custom_text", "pf_text", {}),
        ("bio", "pf_bio", {}),
        ("ai", "pf_ai", {}),
        ("name_clock_fonts", "pf_fonts", {"n": len(NAME_CLOCK_STYLES) - 1}),
        ("name_clock_zones", "pf_zones", {"n": len(NAME_CLOCK_ZONES) - 1}),
    )
    included, excluded = [], []
    for feature, key, kw in items:
        (included if feature is None or plan in FEATURE_PLANS.get(feature, ()) else excluded).append(t(lang, key, **kw))
    if plan in FEATURE_PLANS.get("faq", ()):
        included.append(t(lang, "pf_faq", n=FAQ_PLAN_LIMITS.get(plan, min(FAQ_PLAN_LIMITS.values()))))
    else:
        excluded.append(t(lang, "pf_faq_locked", limits=" / ".join(f"{p.capitalize()} — {n}" for p, n in FAQ_PLAN_LIMITS.items() if p in FEATURE_PLANS.get("faq", ()))))
    (included if plan in FEATURE_PLANS.get("kb", ()) else excluded).append(t(lang, "pf_kb", n=KB_LIMIT))
    included.append(t(lang, "pf_sched", n=SCHEDULE_PLAN_LIMITS.get(plan, SCHEDULE_PLAN_LIMITS["free"])))
    included.append(t(lang, "pf_an_" + (plan if plan in ("plus", "pro", "ultra") else "free")))
    included.append(t(lang, "pf_ads_off" if plan in AD_FREE_PLANS else "pf_ads_on"))
    parts = [t(lang, "plan_includes")] + [f"• {line}" for line in included]
    if excluded:
        parts += ["", t(lang, "plan_excludes")] + [f"• {line}" for line in excluded]
    return "\n".join(parts)


def build_plan_view(owner_id: int, key: str):
    """Tanlangan tarif ekrani: nimalar kirishi + (pullik bo'lsa) to'lov ma'lumoti.
    HTML parse_mode bilan yuboriladi (karta raqami bosib nusxalanadi)."""
    lang = get_lang(owner_id)
    emoji, price = next(((e, p) for k, e, p in PLANS if k == key), ("", 0))
    try:
        current = db.get_user_plan(owner_id)
    except Exception:
        current = "free"
    esc = lambda x: html.escape(x, quote=False)  # noqa: E731
    back = [InlineKeyboardButton(t(lang, "btn_back"), callback_data="plans")]
    name = t(lang, "plan_name_" + key)
    features = esc(plan_features_text(lang, key))

    if key == "free":
        text = esc(t(lang, "plan_free_info")) + "\n\n" + features
        if current == "free":
            text += "\n\n" + esc(t(lang, "plan_current"))
        return text, InlineKeyboardMarkup([back])

    title = esc(t(lang, "plan_title", emoji=emoji, name=name, price=plan_price_label(lang, price)))
    if key == current:
        text = title + "\n\n" + features + "\n\n" + esc(t(lang, "plan_current"))
        try:
            expires_at = db.get_user_plan_info(owner_id)[1]
        except Exception:
            expires_at = None
        if expires_at:
            text += "\n" + esc(t(lang, "plan_until", date=format_plan_date(expires_at)))
        return text, InlineKeyboardMarkup([back])
    if not PAYMENT_CARD_NUMBER:
        pay = esc(t(lang, "plan_no_card"))
    else:
        pay = t(
            lang, "plan_pay",
            card="<code>" + esc(format_card_number(PAYMENT_CARD_NUMBER)) + "</code>",
            holder=esc(PAYMENT_CARD_HOLDER),
        )
    rows = [[InlineKeyboardButton(t(lang, "support_btn_admin"), url=f"https://t.me/{SUPPORT_ADMIN_USERNAME}")], back]
    return title + "\n\n" + features + "\n\n" + pay, InlineKeyboardMarkup(rows)


SUPPORT_CHANNEL_LINK = "https://t.me/+P_Uv4zsFGE03NmI6"
SUPPORT_ADMIN_USERNAME = "MyAndro1d"
FEEDBACK_MAX_LENGTH = 1500
FEEDBACK_MAX_PER_HOUR = 5

SUPPORT_TEXT = t("uz", "support_text")  # eski nom (o'zbekcha)


def build_support_view(lang: str = DEFAULT_LANG):
    markup = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(t(lang, "support_btn_channel"), url=SUPPORT_CHANNEL_LINK)],
            [InlineKeyboardButton(t(lang, "support_btn_admin"), url=f"https://t.me/{SUPPORT_ADMIN_USERNAME}")],
            [InlineKeyboardButton(t(lang, "support_btn_feedback"), callback_data="support_feedback")],
            [InlineKeyboardButton(t(lang, "btn_back"), callback_data="back")],
        ]
    )
    return t(lang, "support_text"), markup


async def send_feedback_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, target_id: int):
    """Admin yozgan javobni fikr yuborgan foydalanuvchiga yetkazadi."""
    text = update.message.text.strip()
    if len(text) > FEEDBACK_MAX_LENGTH:
        await update.message.reply_text(
            f"Javob juda uzun ({len(text)} belgi). {FEEDBACK_MAX_LENGTH} belgidan qisqaroq yozing."
        )
        return  # amal saqlanadi
    clear_pending_admin_action(ADMIN_ID)
    delivered = await _try_send(context.bot, target_id, t(get_lang(target_id), "admin_reply_to_user", text=text))
    await update.message.reply_text(
        "\u2705 Javob yuborildi." if delivered
        else "\u274C Yuborib bo'lmadi \u2014 foydalanuvchi botni bloklagan bo'lishi mumkin."
    )


async def submit_feedback(bot, user, text: str) -> str:
    """Foydalanuvchi fikrini adminga yuboradi. Foydalanuvchiga ko'rsatiladigan javob matnini qaytaradi."""
    lang = get_lang(user.id)
    if db.count_recent_feedback(user.id, time.time() - 3600) >= FEEDBACK_MAX_PER_HOUR:
        return t(lang, "feedback_rate")
    label = format_user_label(user.id, user.username, user.full_name)
    admin_text = f"\U0001F4AC Yangi fikr/taklif\n\nKimdan: {label}\n\n{text}"
    reply_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u21A9\uFE0F Javob berish", callback_data=f"fbreply:{user.id}")]]
    )
    if not (ADMIN_ID and await _try_send(bot, ADMIN_ID, admin_text, reply_markup)):
        return t(lang, "feedback_fail")
    db.add_feedback(user.id, text)
    return t(lang, "feedback_thanks")


def build_referral_view(owner_id: int):
    lang = get_lang(owner_id)
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{owner_id}"
    count = db.get_referral_count(owner_id)
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(t(lang, 'ref_share_text'))}"

    text = t(lang, "ref_view", count=count, link=link)
    keyboard = [
        [InlineKeyboardButton(t(lang, "ref_btn_share"), url=share_url)],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="back")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


ADMIN_REFERRALS_LIMIT = 30


async def build_admin_referrals_view(bot):
    all_rows = db.get_all_referral_counts()
    rows = all_rows[:ADMIN_REFERRALS_LIMIT]  # xabar 4096 belgidan oshmasin va har biri uchun get_chat chaqirilmasin
    if not rows:
        body = "Hozircha hech kim hech kimni taklif qilmagan."
    else:
        lines = []
        for i, (inviter_id, cnt) in enumerate(rows):
            label = await _display_name_for(bot, inviter_id)
            lines.append(f"{i + 1}. {label} — {cnt} ta do'st")
        if len(all_rows) > len(rows):
            lines.append(f"\n... va yana {len(all_rows) - len(rows)} ta (eng ko'p taklif qilgan {len(rows)} tasi ko'rsatildi)")
        body = "\n".join(lines)

    text = f"\U0001F4CA Referral statistikasi\n\n{body}"
    keyboard = [[InlineKeyboardButton("\u2B05\uFE0F Orqaga", callback_data="back")]]
    return text, InlineKeyboardMarkup(keyboard)


async def _display_name_for(bot, user_id: int) -> str:
    """Username bo'lsa @username, bo'lmasa Telegram ismi, u ham topilmasa ID."""
    try:
        chat = await bot.get_chat(user_id)
        if chat.username:
            return f"@{chat.username}"
        if chat.full_name:
            return chat.full_name
    except Exception as e:
        logger.debug("Chat ma'lumoti olinmadi (user=%s): %s", user_id, e)
    return f"ID {user_id}"


AI_DAILY_LIMIT = 50  # Ultra tarifida kuniga AI javoblar soni (admin uchun limit yo'q)
AI_HISTORY_MESSAGES = 10
AI_INFO_MAX_LENGTH = 1000
AUTO_REPLY_MAX_TEXT = 1000  # avtojavob va uxlash xabari matni uzunligi (menyu 4096 belgidan oshmasligi uchun)
MENU_TEXT_PREVIEW_CHARS = 1000  # eski (cheklovdan oldin saqlangan) uzun matnlar menyuni buzmasin
AI_TAKEOVER_PAUSE_SECONDS = 2 * 3600  # egasi chatga o'zi yozsa, AI shu chatda shuncha vaqt jim turadi

# Botning o'zi yuborgan xabarlar (chat_id, message_id): agar Telegram ularni "egasi yozdi"
# deb qaytarsa ham, AI'ni noto'g'ri pauza qilib qo'ymaslik uchun.
_bot_sent_ids: deque = deque(maxlen=500)
_ai_chat_locks: "weakref.WeakValueDictionary" = weakref.WeakValueDictionary()


def _remember_sent(chat_id: int, message) -> None:
    message_id = getattr(message, "message_id", None)
    if isinstance(message_id, int):
        _bot_sent_ids.append((chat_id, message_id))


def _chat_lock(owner_id: int, chat_id: int) -> asyncio.Lock:
    key = (owner_id, chat_id)
    lock = _ai_chat_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _ai_chat_locks[key] = lock
    return lock


# --------------------------------------------------------------------------
# Ism soati: "Ism | 12:30" — har daqiqada akkaunt ismiga joriy vaqt yoziladi
# --------------------------------------------------------------------------
# Hamma ulangan foydalanuvchiga ochiq. Kerak bo'lsa, Render'da NAME_CLOCK_PUBLIC=0 qo'yib, faqat adminga cheklash mumkin.
NAME_CLOCK_PUBLIC = os.environ.get("NAME_CLOCK_PUBLIC", "").strip() != "0"
# Telegram so'rovi borib-kelishi ~0.3-1 s: yangilashni daqiqa chegarasidan shuncha oldin boshlaymiz,
# shunda yangi vaqt aynan daqiqa almashganda ko'rinadi (ism keyingi daqiqa vaqti bilan yoziladi).
NAME_CLOCK_LEAD_SECONDS = 0.8
NAME_CLOCK_CONCURRENCY = 25
NAME_CLOCK_SYNC_LEAD_SECONDS = 4.0  # ism o'zgarganini tekshirish: yangilashdan shuncha oldin
NAME_CLOCK_MAX_FAILURES = 3  # ketma-ket shuncha xatodan keyin funksiya o'zi o'chadi
FLOOD_NOTICE_COOLDOWN_SECONDS = 600
# Telegram'ga soniyasiga eng ko'pi bilan shuncha ism-soat chaqiruvi (umumiy bot limiti ~30/s) — flood'dan saqlanish.
NAME_CLOCK_RATE_PER_SEC = 20.0
NAME_CLOCK_MAX_LEAD_SECONDS = 25.0       # ko'p foydalanuvchida yangilashni shuncha soniyagacha oldinroq boshlaymiz
NAME_CLOCK_MAX_SYNC_LEAD_SECONDS = 55.0
_name_clock_target_count = 0             # oxirgi ko'ringan faol soatlar soni (yangilash oldinligini hisoblash uchun)


class _Pacer:
    """Chaqiruvlarni teng oraliqda (rate/s) tarqatadi: hammasi bir lahzada Telegram'ga urilmasin."""

    def __init__(self):
        self._next = 0.0

    async def wait(self, rate: float):
        now = time.monotonic()
        slot = max(self._next, now)
        self._next = slot + 1.0 / max(rate, 0.001)
        if slot > now:
            await asyncio.sleep(slot - now)


_clock_pacer = _Pacer()
_sync_pacer = _Pacer()


def clock_lead_seconds(n: int | None = None) -> float:
    """Yangilashni daqiqa chegarasidan qancha oldin boshlash: foydalanuvchi ko'p bo'lsa, oxirgisi ham
    deyarli o'z vaqtida yangilanishi uchun (n / tezlik soniya + kichik zaxira)."""
    n = _name_clock_target_count if n is None else n
    return min(NAME_CLOCK_MAX_LEAD_SECONDS, NAME_CLOCK_LEAD_SECONDS + n / NAME_CLOCK_RATE_PER_SEC)

_name_clock_backoff_until = 0.0
_name_clock_failures: dict[int, int] = {}
_name_clock_inflight: set[int] = set()
_last_flood_notice = 0.0


def name_clock_allowed(user_id: int) -> bool:
    return NAME_CLOCK_PUBLIC or (bool(ADMIN_ID) and user_id == ADMIN_ID)


def clock_names_for(base_first: str, base_last: str | None, tz_name: str | None, at_ts: float, style: str | None = None):
    """(first, last, key): `at_ts` payti shu zonadagi soat bilan ism va "shu daqiqa" kaliti."""
    tz = ZoneInfo(tz_name if is_known_zone(tz_name) else DEFAULT_NAME_CLOCK_ZONE)
    dt = datetime.fromtimestamp(at_ts, tz)
    first, last = build_clock_name(base_first, base_last, dt.hour, dt.minute, style)
    return first, last, dt.strftime("%Y-%m-%d %H:%M")


async def _set_account_name(bot, connection_id: str, first: str, last: str | None):
    # last_name HAR DOIM yuboriladi ("" — familiya yo'q): aks holda oldingi familiya (masalan
    # "Abdu | 12:30") akkauntda qolib, ism "Ali | 12:31 Abdu | 12:30" bo'lib ketardi.
    await bot.set_business_account_name(
        business_connection_id=connection_id, first_name=first, last_name=last or ""
    )


async def _notify_owner(bot, owner_id: int, text: str):
    await _try_send(bot, owner_id, text)


async def _disable_name_clock(bot, owner_id: int, reason: str):
    db.update_settings(owner_id, name_clock_enabled=False)
    _name_clock_failures.pop(owner_id, None)
    await _notify_owner(bot, owner_id, t(get_lang(owner_id), "nc_auto_disabled", reason=reason))


async def _apply_clock(bot, target: dict, at_ts: float, sem: asyncio.Semaphore):
    owner_id = target["owner_user_id"]
    style = target.get("name_clock_style")
    if not plan_allows(owner_id, target.get("plan"), "name_clock_fonts"):
        style = None  # standart bo'lmagan shriftlar tarifda yo'q — standart shriftga qaytadi
    tz_name = target.get("name_clock_tz")
    if not plan_allows(owner_id, target.get("plan"), "name_clock_zones"):
        tz_name = None  # boshqa vaqt zonalari tarifda yo'q — Toshkent vaqtiga qaytadi
    first, last, key = clock_names_for(
        target["name_clock_first"], target.get("name_clock_last"), tz_name, at_ts, style,
    )
    if target.get("name_clock_applied") == key or owner_id in _name_clock_inflight:
        return None
    _name_clock_inflight.add(owner_id)
    try:
        async with sem:
            try:
                await _clock_pacer.wait(NAME_CLOCK_RATE_PER_SEC)
                await _set_account_name(bot, target["business_connection_id"], first, last)
            except RetryAfter as e:
                global _name_clock_backoff_until, _last_flood_notice
                _name_clock_backoff_until = max(_name_clock_backoff_until, time.time() + float(e.retry_after) + 1)
                logger.warning("Ism soati: Telegram flood, %s s kutiladi", e.retry_after)
                now = time.time()
                if ADMIN_ID and now - _last_flood_notice > FLOOD_NOTICE_COOLDOWN_SECONDS:
                    _last_flood_notice = now
                    await _try_send(
                        bot, ADMIN_ID,
                        f"⚠️ Ism soati: Telegram {int(e.retry_after)} soniya kutishni so'radi (flood). "
                        "Shu vaqt davomida soat yangilanmaydi.",
                    )
                return None
            except (BadRequest, Forbidden) as e:
                if "not modified" in str(e).lower():
                    return owner_id, key  # ism allaqachon shunday — muammo yo'q
                _name_clock_failures[owner_id] = _name_clock_failures.get(owner_id, 0) + 1
                logger.warning("Ism soati yangilanmadi (owner=%s): %s", owner_id, e)
                if _name_clock_failures[owner_id] >= NAME_CLOCK_MAX_FAILURES:
                    await _disable_name_clock(bot, owner_id, t(get_lang(owner_id), "nc_denied_reason"))
                return None
            except TelegramError as e:
                logger.info("Ism soati: vaqtinchalik xato (owner=%s): %s", owner_id, e)
                return None
            _name_clock_failures.pop(owner_id, None)
            return owner_id, key
    finally:
        _name_clock_inflight.discard(owner_id)


async def name_clock_tick(bot, at_ts: float):
    """Barcha yoqilgan akkauntlarning ismini `at_ts` (daqiqa chegarasi) vaqti bilan yangilaydi."""
    if time.time() < _name_clock_backoff_until:
        return
    try:
        targets = db.get_name_clock_targets()
    except Exception:
        logger.exception("Ism soati: ro'yxatni o'qib bo'lmadi")
        return
    targets = [x for x in targets if sub_ok_sync(x["owner_user_id"])]
    global _name_clock_target_count
    _name_clock_target_count = len(targets)
    if not targets:
        return
    sem = asyncio.Semaphore(NAME_CLOCK_CONCURRENCY)
    results = await asyncio.gather(*(_apply_clock(bot, t, at_ts, sem) for t in targets), return_exceptions=True)
    applied = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("Ism soati: kutilmagan xato", exc_info=r)
        elif r is not None:
            applied.append(r)
    try:
        if applied:
            db.mark_name_clock_applied_bulk(applied)  # bitta so'rov, Telegram chaqiruvlaridan KEYIN
    except Exception:
        logger.exception("Ism soati: belgilashda xato")


def next_clock_boundary(now: float, lead: float | None = None) -> tuple[float, float]:
    """(uyg'onish vaqti, yangi daqiqa chegarasi): chegaradan `lead` soniya oldin uyg'onadi."""
    lead = NAME_CLOCK_LEAD_SECONDS if lead is None else lead
    boundary = (now // 60 + 1) * 60
    fire_at = boundary - lead
    if fire_at <= now:  # oldinlik oynasiga kech tushdik — keyingi daqiqaga
        boundary += 60
        fire_at += 60
    return fire_at, boundary


async def name_clock_loop(bot):
    """Doimiy sikl: har safar devor soatiga qarab keyingi daqiqa chegarasini hisoblaydi
    (interval qo'shib bormaydi), shuning uchun vaqt siljimaydi. Sekin tick keyingisini kechiktirmaydi."""
    while True:
        try:
            fire_at, boundary = next_clock_boundary(time.time(), clock_lead_seconds())
            await asyncio.sleep(max(0.0, fire_at - time.time()))
            spawn_background(name_clock_tick(bot, boundary))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ism soati sikli xatosi")
            await asyncio.sleep(1)


async def _post_init(app: Application):
    spawn_background(name_clock_loop(app.bot))
    spawn_background(name_clock_sync_loop(app.bot))


def adopt_new_base_name(owner_id: int, cur_first, cur_last, state: dict | None = None) -> bool:
    """Egasi ismni Telegramda o'zi o'zgartirgan bo'lsa, yangi ismni asl ism qilib oladi
    (aks holda bot keyingi daqiqada eski ismni qaytarib qo'yardi). True — yangilandi.
    `state` berilmasa, bazadan yengil so'rov bilan olinadi (yoqilmagan bo'lsa — hech narsa qilinmaydi)."""
    if state is None:
        state = db.get_name_clock_base(owner_id)
    if not state or not state.get("name_clock_first"):
        return False
    if not is_external_rename(state["name_clock_first"], state.get("name_clock_last"), cur_first, cur_last):
        return False
    db.update_settings(
        owner_id,
        name_clock_first=strip_clock_suffix(cur_first)[:NAME_MAX_LENGTH],
        name_clock_last=strip_clock_suffix(cur_last)[:NAME_MAX_LENGTH],
        name_clock_applied=None,
    )
    logger.info("Ism soati: egasi ismni o'zgartirgan, yangi asl ism olindi (owner=%s)", owner_id)
    return True


async def name_clock_sync(bot):
    """Daqiqa chegarasidan biroz oldin: yoqilgan akkauntlarning haqiqiy ismini Telegramdan o'qib,
    egasi o'zi o'zgartirgan bo'lsa yangi asl ismni qabul qiladi."""
    try:
        targets = db.get_name_clock_targets()
    except Exception:
        logger.exception("Ism soati: sinxronlash ro'yxati o'qilmadi")
        return
    targets = [x for x in targets if sub_ok_sync(x["owner_user_id"])]
    global _name_clock_target_count
    _name_clock_target_count = len(targets)
    sem = asyncio.Semaphore(NAME_CLOCK_CONCURRENCY)

    async def one(target):
        async with sem:
            await _sync_pacer.wait(NAME_CLOCK_RATE_PER_SEC)
            try:
                chat = await bot.get_chat(target["owner_user_id"])
            except TelegramError:
                return
            adopt_new_base_name(
                target["owner_user_id"], getattr(chat, "first_name", None), getattr(chat, "last_name", None), state=target
            )

    await asyncio.gather(*(one(t) for t in targets), return_exceptions=True)


def clock_sync_lead_seconds(n: int | None = None) -> float:
    """Ism tekshiruvi yangilashdan oldin tugashi kerak: yangilash oldinligi + tekshiruv davomiyligi + zaxira."""
    n = _name_clock_target_count if n is None else n
    return min(NAME_CLOCK_MAX_SYNC_LEAD_SECONDS, clock_lead_seconds(n) + n / NAME_CLOCK_RATE_PER_SEC + 3.0)


async def name_clock_sync_loop(bot):
    """Har daqiqada, yangilashdan oldin ism o'zgarganini tekshiradi (egasi ismni o'zi o'zgartirgan bo'lsa,
    bot uni eski ismga qaytarib yubormasligi uchun). Har daqiqada — chunki kamroq tekshirsak, bot
    o'zgartirilgan ismni ustidan yozib yuborib, yangi ismni yo'qotib qo'yishi mumkin."""
    while True:
        try:
            fire_at, _ = next_clock_boundary(time.time(), clock_sync_lead_seconds())
            await asyncio.sleep(max(0.0, fire_at - time.time()))
            spawn_background(name_clock_sync(bot))
            await asyncio.sleep(1.0)  # bir daqiqaga ikki marta ishga tushmasin
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Ism soati sinxronlash sikli xatosi")
            await asyncio.sleep(1)


async def capture_base_name(bot, owner_id: int) -> tuple[str, str] | None:
    """Hozirgi (soatsiz) ismni Telegramdan oladi."""
    try:
        chat = await bot.get_chat(owner_id)
    except TelegramError as e:
        logger.info("Asl ism olinmadi (owner=%s): %s", owner_id, e)
        return None
    first = strip_clock_suffix(getattr(chat, "first_name", None))
    last = strip_clock_suffix(getattr(chat, "last_name", None))
    if not first:
        return None
    return first[:NAME_MAX_LENGTH], last[:NAME_MAX_LENGTH]


async def restore_base_name(bot, owner_id: int) -> bool:
    s = db.get_settings(owner_id)
    conn = db.get_connection(owner_id)
    if not conn or not conn.get("is_enabled") or not s.get("name_clock_first"):
        return False
    try:
        await _set_account_name(bot, conn["business_connection_id"], s["name_clock_first"], s.get("name_clock_last") or None)
    except TelegramError as e:
        logger.warning("Asl ism qaytarilmadi (owner=%s): %s", owner_id, e)
        return False
    db.update_settings(owner_id, name_clock_applied=None)
    return True


def build_name_clock_menu(owner_id: int, notice: str | None = None):
    lang = get_lang(owner_id)
    s = db.get_settings(owner_id)
    enabled = bool(s.get("name_clock_enabled"))
    first, last = s.get("name_clock_first"), s.get("name_clock_last")
    tz = s.get("name_clock_tz") or DEFAULT_NAME_CLOCK_ZONE
    if not has_feature(owner_id, "name_clock_zones"):
        tz = DEFAULT_NAME_CLOCK_ZONE
    fonts_ok = has_feature(owner_id, "name_clock_fonts")
    chosen_style = s.get("name_clock_style") if fonts_ok else None
    if first:
        preview_first, preview_last, _ = clock_names_for(first, last, tz, time.time(), chosen_style)
        preview = f"{preview_first} {preview_last or ''}".strip()
        base = f"{first} {last or ''}".strip()
    else:
        preview, base = "—", t(lang, "nc_base_pending")
    style_key = chosen_style if is_known_style(chosen_style) else DEFAULT_NAME_CLOCK_STYLE
    text = t(
        lang, "nc_menu",
        status=t(lang, "status_on" if enabled else "status_off"),
        zone=zone_label(tz, lang),
        digits=f"{NAME_CLOCK_STYLES[style_key][0]} {style_time('20:45', style_key)}",
        base=base,
        preview=preview,
    )
    if notice:
        text += f"\n\n{notice}"
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_disable" if enabled else "btn_enable"), callback_data="nc_toggle")],
        [InlineKeyboardButton(t(lang, "btn_nc_tz"), callback_data="nc_tz_menu")],
        [InlineKeyboardButton(t(lang, "btn_nc_style"), callback_data="nc_style_menu")],
        [InlineKeyboardButton(t(lang, "btn_nc_edit"), callback_data="nc_edit_name")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_name_clock_zones_menu(owner_id: int):
    lang = get_lang(owner_id)
    zones_ok = has_feature(owner_id, "name_clock_zones")
    current = (db.get_settings(owner_id).get("name_clock_tz") or DEFAULT_NAME_CLOCK_ZONE) if zones_ok else DEFAULT_NAME_CLOCK_ZONE
    rows = [
        [InlineKeyboardButton(
            lock_label(("✅ " if tz == current else "") + zone_button_label(key, label, lang),
                       zones_ok or tz == DEFAULT_NAME_CLOCK_ZONE),
            callback_data=f"nc_tz:{key}",
        )]
        for key, label, tz in NAME_CLOCK_ZONES
    ]
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nc_menu")])
    return t(lang, "nc_tz_title"), InlineKeyboardMarkup(rows)


def build_name_clock_styles_menu(owner_id: int):
    lang = get_lang(owner_id)
    fonts_ok = has_feature(owner_id, "name_clock_fonts")
    current = db.get_settings(owner_id).get("name_clock_style") if fonts_ok else None
    current = current if is_known_style(current) else DEFAULT_NAME_CLOCK_STYLE
    rows, pair = [], []
    for key, (label, *_rest) in NAME_CLOCK_STYLES.items():
        mark = " \u2705" if key == current else ""
        locked = not fonts_ok and key != DEFAULT_NAME_CLOCK_STYLE
        pair.append(InlineKeyboardButton(
            lock_label(f"{label} {style_time('20:45', key)}{mark}", not locked), callback_data=f"nc_style:{key}"
        ))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="nc_menu")])
    return t(lang, "nc_style_title"), InlineKeyboardMarkup(rows)


def _apply_now_if_enabled(bot, owner_id: int):
    """Sozlama o'zgarganda keyingi daqiqani kutmasdan yangi ko'rinishni darrov qo'llaydi."""
    if db.get_settings(owner_id).get("name_clock_enabled"):
        spawn_background(name_clock_tick(bot, time.time()))


async def handle_name_clock_button(query, context, data: str, owner_id: int):
    """nc_* tugmalari. True qaytarsa, tugma shu yerda qayta ishlangan."""
    bot = context.bot
    if data == "nc_menu":
        text, markup = build_name_clock_menu(owner_id)
    elif data == "nc_tz_menu":
        text, markup = build_name_clock_zones_menu(owner_id)
    elif data.startswith("nc_tz:"):
        key = data.split(":", 1)[1]
        zone = next((tz for k, _, tz in NAME_CLOCK_ZONES if k == key), None)
        notice = None
        if zone:
            if zone != DEFAULT_NAME_CLOCK_ZONE and not has_feature(owner_id, "name_clock_zones"):
                notice = locked_text(get_lang(owner_id), "name_clock_zones")
            else:
                db.update_settings(owner_id, name_clock_tz=zone, name_clock_applied=None)
                _apply_now_if_enabled(bot, owner_id)
        text, markup = build_name_clock_menu(owner_id, notice)
    elif data == "nc_style_menu":
        text, markup = build_name_clock_styles_menu(owner_id)
    elif data.startswith("nc_style:"):
        key = data.split(":", 1)[1]
        notice = None
        if is_known_style(key):
            if key != DEFAULT_NAME_CLOCK_STYLE and not has_feature(owner_id, "name_clock_fonts"):
                notice = locked_text(get_lang(owner_id), "name_clock_fonts")
            else:
                db.update_settings(owner_id, name_clock_style=key, name_clock_applied=None)
                _apply_now_if_enabled(bot, owner_id)
        text, markup = build_name_clock_menu(owner_id, notice)
    elif data == "nc_toggle":
        s = db.get_settings(owner_id)
        notice = None
        if s.get("name_clock_enabled"):
            db.update_settings(owner_id, name_clock_enabled=False)
            restored = await restore_base_name(bot, owner_id)
            notice = t(get_lang(owner_id), "nc_off_restored" if restored else "nc_off_not_restored")
        else:
            notice = await _enable_name_clock(bot, owner_id)
        text, markup = build_name_clock_menu(owner_id, notice)
    elif data == "nc_edit_name":
        set_pending_action(owner_id, "nc_name")
        await query.message.reply_text(t(get_lang(owner_id), "nc_name_prompt"))
        return
    else:
        return
    await query.edit_message_text(text, reply_markup=markup)


async def _enable_name_clock(bot, owner_id: int) -> str | None:
    """Yoqishdan oldin tekshiradi. Muammo bo'lsa, foydalanuvchiga ko'rsatiladigan izohni qaytaradi."""
    lang = get_lang(owner_id)
    conn = db.get_connection(owner_id)
    if not conn or not conn.get("is_enabled"):
        return t(lang, "nc_need_connect")
    # Ruxsat o'zgargan bo'lishi mumkin — Telegramdan joriy holatni so'raymiz
    try:
        live = await bot.get_business_connection(conn["business_connection_id"])
        rights = getattr(live, "rights", None)
        can_edit_name = bool(getattr(rights, "can_edit_name", False)) if rights is not None else False
        db.upsert_connection(
            owner_user_id=owner_id,
            business_connection_id=conn["business_connection_id"],
            can_reply=conn["can_reply"],
            is_enabled=live.is_enabled,
            can_edit_bio=conn["can_edit_bio"],
            can_edit_name=can_edit_name,
        )
    except TelegramError as e:
        logger.info("Ulanish huquqlarini o'qib bo'lmadi (owner=%s): %s", owner_id, e)
        can_edit_name = bool(conn.get("can_edit_name"))
    if not can_edit_name:
        return t(lang, "nc_need_right")
    names = await capture_base_name(bot, owner_id)
    if names is None:
        return t(lang, "nc_name_unknown")
    db.update_settings(
        owner_id,
        name_clock_enabled=True,
        name_clock_first=names[0],
        name_clock_last=names[1],
        name_clock_applied=None,
        name_clock_tz=db.get_settings(owner_id).get("name_clock_tz") or DEFAULT_NAME_CLOCK_ZONE,
    )
    _name_clock_failures.pop(owner_id, None)
    # Keyingi daqiqani kutmasdan, hoziroq birinchi marta qo'yamiz
    spawn_background(name_clock_tick(bot, time.time()))
    return t(lang, "nc_enabled")


def build_ai_menu(owner_id: int, notice: str | None = None):
    lang = get_lang(owner_id)
    s = db.get_settings(owner_id)
    enabled = bool(s.get("ai_enabled"))
    info = (s.get("ai_info") or "").strip()
    if ADMIN_ID and owner_id == ADMIN_ID:
        usage_line = t(lang, "ai_usage_unlimited")
    else:
        usage_line = t(lang, "ai_usage", used=db.get_ai_usage(owner_id, str(today_tashkent())), limit=AI_DAILY_LIMIT)
    text = t(
        lang, "ai_menu",
        status=t(lang, "status_on" if enabled else "status_off"),
        usage=usage_line,
        role=ai.role_label(s.get("ai_role"), lang),
        info=info if info else t(lang, "ai_info_empty"),
    )
    if notice:
        text += f"\n\n{notice}"
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_disable" if enabled else "btn_enable"), callback_data="ai_off" if enabled else "ai_on")],
        [InlineKeyboardButton(t(lang, "btn_ai_roles"), callback_data="ai_roles")],
        [InlineKeyboardButton(t(lang, "btn_ai_info"), callback_data="ai_edit_info")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_ai_roles_menu(owner_id: int):
    lang = get_lang(owner_id)
    current = ai.normalize_role(db.get_settings(owner_id).get("ai_role"))
    rows = [
        [InlineKeyboardButton(("\u2705 " if key == current else "") + ai.role_label(key, lang), callback_data=f"ai_role:{key}")]
        for key in ai.ROLES
    ]
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="ai_menu")])
    return t(lang, "ai_roles_menu"), InlineKeyboardMarkup(rows)


async def send_auto_reply(bot, bm, owner_id: int, chat_id: int, reply_text: str, cooldown_hours: float, label: str, kind: str | None = None):
    """Oddiy (matnli) avtojavob: cooldown huquqini atomik band qilib, yuboradi."""
    # Cooldown huquqini YUBORISHDAN OLDIN atomik band qilamiz (bitta SQL).
    # Oldingi "tekshir -> yubor -> belgila" ketma-ketligida ikkita xabar
    # (yoki ikkita instance) bir vaqtda kelsa, ikkalasi ham "cooldown yo'q"
    # deb ko'rib, ikki marta javob yuborishi mumkin edi.
    claimed_at = db.try_claim_reply(owner_id, chat_id, cooldown_hours)
    if claimed_at is None:
        track_analytics(owner_id, "skipped")
        return  # cooldown hali tugamagan

    try:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=with_ad(reply_text, owner_id),
            business_connection_id=bm.business_connection_id,
        )
    except Exception as e:
        # Yuborib bo'lmadi — band qilingan huquqni qaytaramiz, aks holda
        # javob berilmagan bo'lsa ham keyingi xabarlar cooldown'da qolib ketardi.
        db.release_reply_claim(owner_id, chat_id, claimed_at)
        if isinstance(e, TelegramError):
            logger.warning("Avtojavob yuborilmadi (owner=%s, chat=%s): %s", owner_id, chat_id, e)
            return
        raise
    _remember_sent(chat_id, sent)
    # Statistika: javob FAQAT muvaffaqiyatli yuborilgandan keyin sanaladi
    track_analytics(owner_id, kind or ("sleep" if "sleeping=True" in label else "static"))
    logger.info("auto reply sent (owner=%s, chat=%s, %s)", owner_id, chat_id, label)


async def send_faq_reply(bot, bm, owner_id: int, chat_id: int, answer: str, cooldown_hours: float, label: str, ai_mode: bool):
    """FAQ javobini yuboradi. Oddiy rejimda — cooldown bilan (avtojavob kabi); AI yoqilgan egada cooldown
    ishlatilmaydi (AI javoblari kabi), shunda mijozning keyingi savoliga ham javob ketadi."""
    if not ai_mode:
        await send_auto_reply(bot, bm, owner_id, chat_id, answer, cooldown_hours, label, kind="faq")
        return
    try:
        sent = await bot.send_message(
            chat_id=chat_id, text=with_ad(answer, owner_id), business_connection_id=bm.business_connection_id
        )
    except TelegramError as e:
        logger.warning("FAQ javobi yuborilmadi (owner=%s, chat=%s): %s", owner_id, chat_id, e)
        return
    _remember_sent(chat_id, sent)
    track_analytics(owner_id, "faq")
    logger.info("faq reply sent (owner=%s, chat=%s, %s)", owner_id, chat_id, label)


async def run_ai_reply(bot, bm, owner_id: int, chat_id: int, text: str, settings: dict, fallback_text: str, label: str):
    """AI javobini yaratib yuboradi. Limit tugasa yoki xato bo'lsa — odatiy matnli avtojavob (zaxira)."""
    business_connection_id = bm.business_connection_id
    day = str(today_tashkent())
    unlimited = bool(ADMIN_ID) and owner_id == ADMIN_ID
    consumed = False   # kunlik limitdan bitta foydalanish band qilinganmi (hali qaytarilmagan)
    delivered = False  # AI javobi mijozga muvaffaqiyatli yuborildimi
    try:
        async with _chat_lock(owner_id, chat_id):
            if db.is_ai_paused(owner_id, chat_id) or not ai_reply_still_allowed(owner_id):
                return  # navbat kutayotganda egasi chatga yozgan yoki sozlamalar o'zgargan: AI ham, zaxira matn ham ketmaydi
            if not unlimited:
                if not db.try_consume_ai_quota(owner_id, day, AI_DAILY_LIMIT):
                    await send_auto_reply(bot, bm, owner_id, chat_id, fallback_text, settings["cooldown_hours"], label + ",ai-limit")
                    return
                consumed = True

            history = db.get_ai_history(owner_id, chat_id, AI_HISTORY_MESSAGES)
            history.append({"role": "user", "text": text})
            info = db.get_user(owner_id) or {}
            # Bilimlar bazasi: mijozning oxirgi xabarlari bo'yicha mos yozuvlar (davomli savollar uchun 3 tagacha)
            recent_user_texts = [h["text"] for h in history if h.get("role") == "user"][-3:]
            kb_entries = find_kb_context(owner_id, recent_user_texts)
            answer = await ai.generate_reply(
                history, info.get("full_name"), settings.get("ai_info"), settings.get("ai_role"),
                lang=get_lang(owner_id), **({"knowledge": kb_entries} if kb_entries else {}),
            )
            # Javob tayyorlanayotganda egasi chatga o'zi yozgan bo'lishi mumkin (AI pauzasi yoqilgan): na AI javobi, na zaxira
            # matn yuboriladi — egasi suhbatni o'zi olib bormoqda. Sarflangan kunlik limit qaytariladi.
            # Shuningdek, so'rov davomida AI o'chirilgan, holat Onlayn qilingan, jadval oynasi tugagan yoki uxlash vaqti
            # boshlangan bo'lishi mumkin: joriy sozlamalar bo'yicha qayta tekshiramiz (eski so'rov yangi sozlamani buzmaydi).
            if db.is_ai_paused(owner_id, chat_id) or not ai_reply_still_allowed(owner_id):
                if consumed:
                    consumed = False
                    db.refund_ai_quota(owner_id, day)
                logger.info("AI javobi bekor qilindi: egasi yozgan yoki sozlamalar o'zgargan (owner=%s, chat=%s)", owner_id, chat_id)
                return
            if not answer:
                if consumed:
                    consumed = False
                    db.refund_ai_quota(owner_id, day)
                await send_auto_reply(bot, bm, owner_id, chat_id, fallback_text, settings["cooldown_hours"], label + ",ai-failed")
                return
            try:
                sent = await bot.send_message(
                    chat_id=chat_id, text=answer, business_connection_id=business_connection_id
                )
            except TelegramError as e:
                if consumed:
                    consumed = False
                    db.refund_ai_quota(owner_id, day)
                logger.warning("AI javobi yuborilmadi (owner=%s, chat=%s): %s", owner_id, chat_id, e)
                return
            delivered = True  # javob ketdi: bundan keyingi xatolar limitni qaytarmaydi
            _remember_sent(chat_id, sent)
            track_analytics(owner_id, "ai")
            db.add_ai_messages(owner_id, chat_id, [("user", text), ("model", answer)], keep=AI_HISTORY_MESSAGES)
            logger.info("ai reply sent (owner=%s, chat=%s, %s)", owner_id, chat_id, label)
    except Exception:
        logger.exception("AI javob oqimida kutilmagan xato (owner=%s, chat=%s)", owner_id, chat_id)
    finally:
        # Kutilmagan xato (Python/PostgreSQL), bekor qilish yoki boshqa chiqish yo'li: javob yuborilmagan bo'lsa,
        # band qilingan kunlik limit qaytariladi. Allaqachon qaytarilgan bo'lsa (`consumed` False) — ikki marta emas.
        if consumed and not delivered:
            try:
                db.refund_ai_quota(owner_id, day)
            except Exception:
                logger.exception("AI limitini qaytarib bo'lmadi (owner=%s)", owner_id)


async def ai_cleanup_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        db.purge_old_ai_data()
    except Exception:
        logger.exception("AI ma'lumotlarini tozalashda xato")
    try:
        db.purge_old_analytics()  # statistika: eng ko'pi bilan 90 kunlik soatlik hisoblagichlar
    except Exception:
        logger.exception("Statistikani tozalashda xato")


def build_panel(owner_id: int):
    lang = get_lang(owner_id)
    s = db.get_settings(owner_id)
    status_line = t(lang, "panel_offline" if s["offline"] else "panel_online")
    toggle_label = t(lang, "panel_go_online" if s["offline"] else "panel_go_offline")
    toggle_data = "status_online" if s["offline"] else "status_offline"  # aniq amal: eski tugma qayta bosilsa holat teskarilanmaydi
    sleep_line = t(lang, "panel_sleep_on" if s.get("sleep_mode_enabled") else "panel_sleep_off")

    ai_on = bool(s.get("ai_enabled"))
    ai_line = t(lang, "panel_ai_on" if ai_on else "panel_ai_off")
    message_line = t(lang, "panel_ai_message") if ai_on else auto_reply_text_for(s, lang)[:MENU_TEXT_PREVIEW_CHARS]
    text = t(
        lang, "panel",
        status=status_line,
        cooldown=format_cooldown(s["cooldown_hours"], lang),
        message=message_line,
        sleep=sleep_line,
        ai=ai_line,
    )
    plan = plan_of(owner_id)
    keyboard = [
        [InlineKeyboardButton(toggle_label, callback_data=toggle_data)],
        [InlineKeyboardButton(t(lang, "btn_edit_cooldown"), callback_data="edit_cooldown")],
        [InlineKeyboardButton(lock_label(t(lang, "btn_edit_text"), plan_allows(owner_id, plan, "custom_text")), callback_data="edit_text")],
        [InlineKeyboardButton(lock_label(t(lang, "btn_bio"), plan_allows(owner_id, plan, "bio")), callback_data="bio_menu")],
        [InlineKeyboardButton(t(lang, "btn_sleep"), callback_data="sleep_menu")],
        [InlineKeyboardButton(lock_label(t(lang, "btn_ai"), plan_allows(owner_id, plan, "ai")), callback_data="ai_menu")],
        [InlineKeyboardButton(lock_label(t(lang, "btn_faq"), plan_allows(owner_id, plan, "faq")), callback_data="faq_menu")],
        [InlineKeyboardButton(lock_label(t(lang, "btn_kb"), plan_allows(owner_id, plan, "kb")), callback_data="kb_menu")],
    ]
    keyboard.append([InlineKeyboardButton(t(lang, "btn_sched"), callback_data="sc_menu")])
    keyboard.append([InlineKeyboardButton(t(lang, "btn_analytics"), callback_data="an_menu")])
    if name_clock_allowed(owner_id):
        keyboard.append([InlineKeyboardButton(t(lang, "btn_name_clock"), callback_data="nc_menu")])
    keyboard.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="back")])
    return text, InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# AutoReply Analytics
# Faqat soatlik hisoblagichlar saqlanadi (vaqt + tur + son): xabar matni va chat ID yozilmaydi.
# ---------------------------------------------------------------------------
def _record_analytics_safe(owner_id: int, kind: str):
    """Hisoblagichni yozadi; xato bo'lsa faqat log — javob yuborish oqimi hech qachon buzilmaydi."""
    try:
        db.record_analytics(owner_id, kind)
    except Exception:
        logger.warning("Analytics yozilmadi (owner=%s, kind=%s)", owner_id, kind, exc_info=True)


def track_analytics(owner_id: int, kind: str):
    """Orqa fonda (event loop'ni bloklamasdan) hisoblagichni oshiradi."""
    try:
        spawn_background(asyncio.to_thread(_record_analytics_safe, owner_id, kind))
    except RuntimeError:  # ishlayotgan event loop yo'q
        _record_analytics_safe(owner_id, kind)


def tz_from_settings(settings: dict, owner_id: int):
    """YAGONA vaqt zonasi qoidasi (Sleep Mode, Jadval, Analytics va Ism soati uchun bir xil): tanlangan zona
    faqat tarif «name_clock_zones» ni bersa va zona ma'lum bo'lsagina amal qiladi; aks holda — Toshkent.
    Tarif pasaysa ham (Pro -> Free) hamma funksiyalar birdaniga Toshkent vaqtiga qaytadi."""
    name = (settings or {}).get("name_clock_tz")
    if name and is_known_zone(name) and has_feature(owner_id, "name_clock_zones"):
        return ZoneInfo(name)
    return TASHKENT_TZ


def analytics_tz(owner_id: int):
    """"Eng faol soat" uchun vaqt zonasi: ism soati zonasi (agar tanlangan bo'lsa), aks holda Toshkent."""
    try:
        return tz_from_settings(db.get_settings(owner_id), owner_id)
    except Exception:
        logger.warning("Analytics: vaqt zonasini o'qib bo'lmadi (owner=%s)", owner_id, exc_info=True)
    return TASHKENT_TZ


def analytics_allowed_days(owner_id: int) -> int:
    if has_feature(owner_id, "analytics_30"):
        return 30
    if has_feature(owner_id, "analytics_7"):
        return 7
    return 1


def analytics_summary(owner_id: int, days: int) -> dict:
    tz = analytics_tz(owner_id)
    start = analytics.period_start(days, tz)
    rows = db.get_analytics_rows(owner_id, start.timestamp())
    return analytics.summarize(rows, days, tz)


def _an_period_name(lang: str, days: int) -> str:
    return t(lang, "an_period_" + str(days if days in (7, 30) else 1))


def _an_peak_text(lang: str, peak) -> str:
    return f"{peak[0]:02d}:00\u2013{peak[1]:02d}:00" if peak else t(lang, "an_peak_none")


def build_analytics_menu(owner_id: int, days: int = 1):
    lang = get_lang(owner_id)
    days = days if days in (1, 7, 30) and days <= analytics_allowed_days(owner_id) else 1
    summary = analytics_summary(owner_id, days)
    if analytics.is_empty(summary):
        text = t(lang, "an_menu", period=_an_period_name(lang, days), incoming=0, sent=0, faq=0, ai=0, static=0, sleep=0,
                 peak=t(lang, "an_peak_none")) + "\n\n" + t(lang, "an_empty")
    else:
        k = summary["kinds"]
        text = t(lang, "an_menu", period=_an_period_name(lang, days), incoming=summary["incoming"], sent=summary["sent"],
                 faq=k["faq"], ai=k["ai"], static=k["static"], sleep=k["sleep"], peak=_an_peak_text(lang, summary["peak"]))
        text += "\n\n" + t(lang, "an_note")
    text += "\n\n" + t(lang, "an_privacy")
    ok = lambda f: has_feature(owner_id, f)  # noqa: E731
    keyboard = [
        [InlineKeyboardButton(lock_label(t(lang, "btn_an_charts"), ok("analytics_charts")), callback_data=f"an_ch:{days}")],
        [
            InlineKeyboardButton(t(lang, "btn_an_today"), callback_data="an:1"),
            InlineKeyboardButton(lock_label(t(lang, "btn_an_7"), ok("analytics_7")), callback_data="an:7"),
            InlineKeyboardButton(lock_label(t(lang, "btn_an_30"), ok("analytics_30")), callback_data="an:30"),
        ],
        [InlineKeyboardButton(lock_label(t(lang, "btn_an_detail"), ok("analytics_full")), callback_data=f"an_detail:{days}")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_analytics_detail(owner_id: int, days: int = 1):
    lang = get_lang(owner_id)
    days = days if days in (1, 7, 30) and days <= analytics_allowed_days(owner_id) else 1
    summary = analytics_summary(owner_id, days)
    back = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data=f"an:{days}")]])
    if analytics.is_empty(summary):
        return t(lang, "an_empty"), back
    blocks = [sum(summary["hourly"][h:h + 4]) for h in range(0, 24, 4)]
    top = max(blocks) or 1
    hour_lines = [
        f"{h:02d}-{h + 4:02d}  {chr(0x2588) * round(10 * blk / top)} {blk}" for h, blk in zip(range(0, 24, 4), blocks)
    ]
    day_lines = [f"{d.strftime('%d.%m')}: {i} / {s}" for d, i, s in summary["daily"]]
    bd = summary["busiest_day"]
    text = t(
        lang, "an_detail",
        period=_an_period_name(lang, days), incoming=summary["incoming"], sent=summary["sent"],
        rate=summary["reply_rate"], skipped=summary["skipped"], avg=summary["daily_avg"],
        best_day=f"{bd[0].strftime('%d.%m')} ({bd[1]})" if bd else t(lang, "an_peak_none"),
        peak=_an_peak_text(lang, summary["peak"]), hours="\n".join(hour_lines), days="\n".join(day_lines),
    )
    return text, back


def analytics_chart_kinds(owner_id: int) -> list[str]:
    """Tarifga mos grafiklar: Plus — chiziqli; Pro — chiziqli + doira; Ultra — hammasi (+ ustunli)."""
    kinds = []
    if has_feature(owner_id, "analytics_charts"):
        kinds.append("line")
    if has_feature(owner_id, "analytics_30"):
        kinds.append("pie")
    if has_feature(owner_id, "analytics_full"):
        kinds.append("bar")
    return kinds


def analytics_chart_labels(lang: str, kind: str) -> dict:
    return {
        "title": t(lang, "an_chart_" + kind), "incoming": t(lang, "an_lbl_incoming"), "sent": t(lang, "an_lbl_sent"),
        "faq": t(lang, "an_lbl_faq"), "ai": t(lang, "an_lbl_ai"), "static": t(lang, "an_lbl_static"),
        "sleep": t(lang, "an_lbl_sleep"), "none": t(lang, "an_lbl_none"), "hour": t(lang, "an_lbl_hour"),
    }


async def send_analytics_charts(bot, owner_id: int, chat_id: int, days: int) -> bool:
    """Tarifga mos grafiklarni TANLANGAN davr uchun rasm sifatida yuboradi.
    Davr joriy tarif bilan qayta tekshiriladi (tarif tushirilgandan keyin eski tugma 30 kunlik grafik bermaydi).
    Ruxsat yo'q bo'lsa False qaytaradi."""
    lang = get_lang(owner_id)
    if days not in (1, 7, 30) or days > analytics_allowed_days(owner_id):
        return False
    summary = analytics_summary(owner_id, days)
    if analytics.is_empty(summary):
        await bot.send_message(chat_id=chat_id, text=t(lang, "an_empty"))
        return True
    for kind in analytics_chart_kinds(owner_id):
        labels = analytics_chart_labels(lang, kind)
        png = await analytics.render_chart(kind, owner_id, summary, labels)
        caption = t(lang, "an_charts_caption", name=labels["title"], period=_an_period_name(lang, days))
        await bot.send_photo(chat_id=chat_id, photo=png, caption=caption)
    return True


# ---------------------------------------------------------------------------
# Smart Auto-Reply Scheduler
# Ustuvorlik (on_raw_update): Sleep Mode -> Jadval -> Smart FAQ -> Gemini AI -> oddiy avtojavob.
# Jadval foydalanuvchi sozlamalarini HECH QACHON o'zgartirmaydi: faqat javob berish paytida
# "hozir jadval oynasidami?" deb hisoblanadi.
# ---------------------------------------------------------------------------
# O'chirish tasdig'i: {owner_id: {"rule_id", "token", "ts"}} — «Ha, o'chirish» faqat HOZIRGI tasdiq oynasidan ishlaydi
_sc_del_confirms: dict[int, dict] = {}
_sc_drafts: dict[int, dict] = {}


def clear_scheduler_state(owner_id: int) -> bool:
    """Scheduler'ning vaqtinchalik holatlarini (qoralama va o'chirish tasdig'i) tozalaydi; Bilimlar bazasining
    ochiq o'chirish tasdig'i ham shu yerda tozalanadi (/start, /cancel). Biror narsa bekor bo'lsa True."""
    had_draft = _sc_drafts.pop(owner_id, None) is not None
    had_confirm = _sc_del_confirms.pop(owner_id, None) is not None
    had_kb_confirm = _kb_del_confirms.pop(owner_id, None) is not None
    return had_draft or had_confirm or had_kb_confirm  # {owner_id: {"id", "days": set, "start", "end", "text", "edit_id", "edit", "stage", "ts"}}
# Qaysi tugma qoralamaning qaysi bosqichida ma'noga ega (eski xabardagi tugma boshqa bosqichda ishlamasligi uchun)
_SC_STAGE_FOR = {"sc_dnext": "days", "sc_allday": "time", "sc_deftext": "text", "sc_save": "confirm"}
SC_PREVIEW_CHARS = 60


def _sc_new_draft(owner_id: int, **fields) -> dict:
    """Yangi qoralama. Har qoralamaga o'ziga xos ID beriladi; qoralamaga bog'liq tugmalar shu ID ni olib yuradi —
    shuning uchun eski (bekor qilingan) qoralamaning tugmasi yangisiga ta'sir qila olmaydi."""
    d = {"id": secrets.token_hex(3), "days": set(), "start": None, "end": None, "text": None,
         "edit_id": None, "edit": None, "stage": "days", "ts": time.time()}
    d.update(fields)
    _sc_drafts[owner_id] = d
    return d


def sc_button_is_stale(owner_id: int, data: str) -> bool:
    """Qoralamaga bog'liq tugma eskirganmi: qoralama yo'q, ID boshqa yoki bosqich mos emas."""
    base, *rest = data.split(":")
    d = _sc_draft(owner_id)
    token = rest[-1] if rest else None
    if base == "sc_cancel":
        # Bekor qilish bosqichga bog'liq emas, lekin faqat O'ZINING qoralamasini bekor qiladi.
        # Qoralama yo'q bo'lsa — zararsiz (menyuga qaytaradi), stale emas.
        return d is not None and d.get("id") != token
    if base not in _SC_STAGE_FOR and base not in ("sc_d", "sc_dp"):
        return False
    return d is None or d.get("id") != token or d.get("stage") != _SC_STAGE_FOR.get(base, "days")


def stale_confirm_button(owner_id: int, data: str) -> bool:
    """Qoralama/tasdiqqa bog'liq tugma eskirganmi (joriy qoralama yoki tasdiqning ID'si bilan mos kelmaydi).
    Eskirgan tugma HECH NARSANI o'zgartirmaydi: joriy qoralama, tasdiq va kutilayotgan kiritish saqlanadi.
      - sc_del_yes:ID:TOKEN  — joriy jadval o'chirish tasdig'iga mos bo'lishi shart;
      - kb_del_yes:ID:TOKEN  — joriy bilim o'chirish tasdig'iga mos bo'lishi shart;
      - faq_save:TOKEN / kb_save:TOKEN — joriy qoralamaning ID'si;
      - faq_cancel:TOKEN / kb_cancel:TOKEN — qoralama bor bo'lsa, o'zinikiga mos (qoralama yo'q bo'lsa — zararsiz)."""
    base, *rest = data.split(":")
    if base in ("sc_del_yes", "kb_del_yes"):
        confirms = _sc_del_confirms if base == "sc_del_yes" else _kb_del_confirms
        id_key = "rule_id" if base == "sc_del_yes" else "entry_id"
        confirm = confirms.get(owner_id)
        try:
            item_id, token = int(rest[0]), (rest[1] if len(rest) > 1 else None)
        except (ValueError, IndexError):
            return True
        return (
            confirm is None or confirm[id_key] != item_id or confirm["token"] != token
            or time.time() - confirm["ts"] > PENDING_ACTION_TTL_SECONDS
        )
    if base in ("faq_save", "faq_cancel", "kb_save", "kb_cancel"):
        d = (_faq_draft if base.startswith("faq") else _kb_draft)(owner_id)
        token = rest[0] if rest else None
        if base.endswith("cancel"):
            return d is not None and d.get("id") != token
        return d is None or d.get("id") != token
    return False


def _sc_cb(prefix: str, d: dict) -> str:
    return f"{prefix}:{d['id']}"


def _sc_time_markup(lang: str, d: dict) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_sc_allday"), callback_data=_sc_cb("sc_allday", d))],
        [InlineKeyboardButton(t(lang, "btn_sc_cancel"), callback_data=_sc_cb("sc_cancel", d))],
    ])


def _sc_draft(owner_id: int) -> dict | None:
    d = _sc_drafts.get(owner_id)
    if d is None or time.time() - d["ts"] > PENDING_ACTION_TTL_SECONDS:
        _sc_drafts.pop(owner_id, None)
        return None
    return d


def _sc_day_names(lang: str, short: bool = False) -> list[str]:
    return t(lang, "sched_days_short" if short else "sched_days_full").split("|")


def _sc_time_text(lang: str, start: int, end: int) -> tuple[str, str]:
    """(belgi, matn): 'Butun kun' yoki 09:00–18:00."""
    if is_all_day(start, end):
        return "\U0001F334", t(lang, "sched_all_day")
    return "\U0001F558", format_time_range(start, end)


def _sc_text_preview(lang: str, rule_text: str | None, limit: int = SC_PREVIEW_CHARS) -> str:
    if not rule_text:
        return t(lang, "sched_default_text")
    one = " ".join(rule_text.split())
    return f"«{one if len(one) <= limit else one[: limit - 1] + chr(0x2026)}»"


def _sc_rule_lines(lang: str, n: int, r: dict) -> str:
    icon, time_text = _sc_time_text(lang, r["start_min"], r["end_min"])
    days = format_day_set(r["days"], _sc_day_names(lang), t(lang, "sched_everyday"))
    head = f"{n}. {days}" + ("" if r["is_enabled"] else f" ({t(lang, 'sched_paused')})")
    return f"{head}\n{icon} {time_text}\n\U0001F4AC {_sc_text_preview(lang, r['text'])}"


def reply_state(owner_id: int, settings: dict):
    """Avtojavob holati: (uxlayaptimi, faol jadval qoidasi yoki None). Sleep Mode va Jadval BIR XIL vaqt zonasi va
    BIR XIL «hozir» bilan hisoblanadi; Sleep Mode jadvaldan ustun. on_raw_update va AI javobini yuborishdan oldingi
    qayta tekshiruv shu funksiyadan foydalanadi."""
    now = datetime.now(tz_from_settings(settings, owner_id))
    now_minutes = now.hour * 60 + now.minute
    sleeping = bool(settings.get("sleep_mode_enabled")) and is_within_sleep_window(
        now_minutes, settings.get("sleep_start_minutes", 0), settings.get("sleep_end_minutes", 0)
    )
    return sleeping, (None if sleeping else current_schedule_rule(owner_id, settings, now))


def ai_reply_still_allowed(owner_id: int) -> bool:
    """AI so'rovi ishlayotgan paytda sozlamalar o'zgargan bo'lishi mumkin (AI o'chirilgan, Onlayn qilingan, tarif tugagan,
    uxlash vaqti boshlangan). Joriy sozlamalar bo'yicha AI hozir javob yuborishi mumkinmi."""
    s = db.get_settings(owner_id)
    if not s.get("ai_enabled") or not has_feature(owner_id, "ai"):
        return False
    sleeping, rule = reply_state(owner_id, s)
    return not sleeping and (bool(s.get("offline")) or rule is not None)


def schedule_text_for(owner_id: int, rule: dict, settings: dict, lang: str) -> str:
    """Jadval javob matni: o'z matni (faqat custom_text tarifida) yoki egasining standart avtojavob matni."""
    own = (rule.get("text") or "").strip()
    if own and has_feature(owner_id, "custom_text"):
        return own
    return auto_reply_text_for(settings, lang)


def current_schedule_rule(owner_id: int, settings: dict, now: datetime | None = None):
    """Hozir faol jadval yoki None (o'chirilgan / oyna tashqarisida / xato bo'lsa). Tarif pasaygan bo'lsa,
    faqat limitga sig'adigan birinchi jadvallar ishlaydi."""
    try:
        if not settings.get("scheduler_enabled", True):
            return None
        rules = db.get_schedule_rules_cached(owner_id)[: schedule_limit_for(owner_id)]
        if not rules:
            return None
        now = now or datetime.now(tz_from_settings(settings, owner_id))
        return find_active_schedule(rules, now.weekday(), now.hour * 60 + now.minute)
    except Exception:
        logger.warning("Jadvalni tekshirib bo'lmadi (owner=%s)", owner_id, exc_info=True)
        return None


SC_PAGE_SIZE = 5  # menyuda bir sahifada ko'rsatiladigan jadvallar (Ultra: 30 ta jadval Telegram'ning 4096 belgi limitiga sig'maydi)


def build_sched_menu(owner_id: int, notice: str | None = None, page: int = 0):
    lang = get_lang(owner_id)
    s = db.get_settings(owner_id)
    on = s.get("scheduler_enabled", True)
    rules = db.list_schedule_rules(owner_id)
    limit = schedule_limit_for(owner_id)
    pages = max(1, -(-len(rules) // SC_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    first = page * SC_PAGE_SIZE
    body = (
        "\n\n".join(_sc_rule_lines(lang, n, r) for n, r in enumerate(rules[first:first + SC_PAGE_SIZE], first + 1))
        if rules else t(lang, "sched_none")
    )
    if pages > 1:
        body += "\n\n" + t(lang, "sc_page", p=page + 1, n=pages)
    text = t(
        lang, "sched_menu",
        status_icon="\U0001F7E2" if on else "\U0001F534",
        status=t(lang, "status_on" if on else "status_off").replace("\U0001F7E2 ", ""),
        tz=str(tz_from_settings(s, owner_id)), count=len(rules), max=limit, rules=body,
    ) + "\n\n" + t(lang, "sched_how")
    if notice:
        text = f"{notice}\n\n{text}"
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️", callback_data=f"sc_pg:{page - 1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("▶️", callback_data=f"sc_pg:{page + 1}"))
    keyboard = ([nav] if nav else []) + [
        [InlineKeyboardButton(t(lang, "btn_sc_add"), callback_data="sc_add")],
        [InlineKeyboardButton(t(lang, "btn_sc_edit"), callback_data="sc_list:edit")],
        [InlineKeyboardButton(t(lang, "btn_sc_delete"), callback_data="sc_list:del")],
        [InlineKeyboardButton(t(lang, "btn_sc_settings"), callback_data="sc_settings")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_sched_settings(owner_id: int):
    lang = get_lang(owner_id)
    s = db.get_settings(owner_id)
    on = s.get("scheduler_enabled", True)
    text = t(
        lang, "sc_settings", status_icon="\U0001F7E2" if on else "\U0001F534",
        status=t(lang, "status_on" if on else "status_off").replace("\U0001F7E2 ", ""), tz=str(tz_from_settings(s, owner_id)),
    )
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_sc_toggle_on" if on else "btn_sc_toggle_off"), callback_data="sc_disable" if on else "sc_enable")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sc_menu")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_sched_list(owner_id: int, mode: str):
    """mode: 'edit' | 'del' — jadvalni tanlash ro'yxati."""
    lang = get_lang(owner_id)
    rules = db.list_schedule_rules(owner_id)
    if not rules:
        return t(lang, "sc_no_rules"), InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="sc_menu")]])
    rows = []
    for n, r in enumerate(rules, 1):
        icon, time_text = _sc_time_text(lang, r["start_min"], r["end_min"])
        days = format_day_set(r["days"], _sc_day_names(lang, short=True), t(lang, "sched_everyday"), sep="–")
        label = f"{n}. {days} {time_text}" + ("" if r["is_enabled"] else " ⏸")
        rows.append([InlineKeyboardButton(label, callback_data=(f"sc_e:{r['id']}" if mode == "edit" else f"sc_del:{r['id']}"))])
    rows.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="sc_menu")])
    return t(lang, "sc_pick_edit" if mode == "edit" else "sc_pick_delete"), InlineKeyboardMarkup(rows)


def _sc_entry_text(owner_id: int, rule_id: int):
    """(tartib raqami, matn) yoki None."""
    lang = get_lang(owner_id)
    rules = db.list_schedule_rules(owner_id)
    for n, r in enumerate(rules, 1):
        if r["id"] == rule_id:
            icon, time_text = _sc_time_text(lang, r["start_min"], r["end_min"])
            return n, t(
                lang, "sc_entry", n=n, days=format_day_set(r["days"], _sc_day_names(lang), t(lang, "sched_everyday")),
                time_icon=icon, time=time_text, text=_sc_text_preview(lang, r["text"], 200),
                status_icon="\U0001F7E2" if r["is_enabled"] else "⏸",
                status=t(lang, "status_on" if r["is_enabled"] else "status_off").replace("\U0001F7E2 ", ""),
            ), r
    return None


def build_sched_entry(owner_id: int, rule_id: int, notice: str | None = None):
    lang = get_lang(owner_id)
    found = _sc_entry_text(owner_id, rule_id)
    if found is None:
        return None
    _, text, r = found
    if notice:
        text += f"\n\n{notice}"
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_sc_ed_days"), callback_data=f"sc_ed:days:{rule_id}")],
        [InlineKeyboardButton(t(lang, "btn_sc_ed_time"), callback_data=f"sc_ed:time:{rule_id}")],
        [InlineKeyboardButton(lock_label(t(lang, "btn_sc_ed_text"), has_feature(owner_id, "custom_text")), callback_data=f"sc_ed:text:{rule_id}")],
        [InlineKeyboardButton(t(lang, "btn_sc_pause" if r["is_enabled"] else "btn_sc_resume"), callback_data=f"{'sc_pause' if r['is_enabled'] else 'sc_resume'}:{rule_id}")],
        [InlineKeyboardButton(t(lang, "btn_sc_delete"), callback_data=f"sc_del:{rule_id}")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="sc_list:edit")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_sched_days(owner_id: int):
    """Kunlarni belgilash ekrani (qoralamadagi tanlovga qarab)."""
    lang = get_lang(owner_id)
    d = _sc_draft(owner_id) or {"id": "-", "days": set()}
    chosen = d["days"]
    short = _sc_day_names(lang, short=True)
    day_buttons = [
        InlineKeyboardButton(("✅ " if i in chosen else "") + short[i], callback_data=f"sc_d:{i}:{d['id']}") for i in range(7)
    ]
    keyboard = [
        day_buttons[:4], day_buttons[4:],
        [
            InlineKeyboardButton(t(lang, "btn_sc_wd"), callback_data=f"sc_dp:wd:{d['id']}"),
            InlineKeyboardButton(t(lang, "btn_sc_we"), callback_data=f"sc_dp:we:{d['id']}"),
            InlineKeyboardButton(t(lang, "btn_sc_all"), callback_data=f"sc_dp:all:{d['id']}"),
        ],
        [InlineKeyboardButton(t(lang, "btn_sc_continue"), callback_data=_sc_cb("sc_dnext", d))],
        [InlineKeyboardButton(t(lang, "btn_sc_cancel"), callback_data=_sc_cb("sc_cancel", d))],
    ]
    return t(lang, "sc_days_prompt"), InlineKeyboardMarkup(keyboard)


def _sc_conflict_notice(lang: str, n: int) -> str:
    return t(lang, "sc_conflict", n=n)


def _sc_confirm_view(owner_id: int, d: dict):
    lang = get_lang(owner_id)
    icon, time_text = _sc_time_text(lang, d["start"], d["end"])
    text = t(
        lang, "sc_confirm", days=format_day_set(days_mask(d["days"]), _sc_day_names(lang), t(lang, "sched_everyday")),
        time_icon=icon, time=time_text, text=_sc_text_preview(lang, d.get("text"), 300),
    )
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton(t(lang, "btn_sc_save"), callback_data=_sc_cb("sc_save", d)),
        InlineKeyboardButton(t(lang, "btn_sc_cancel"), callback_data=_sc_cb("sc_cancel", d)),
    ]])
    return text, markup


def _sc_text_step(owner_id: int, d: dict):
    """Matn qadami: (matn, tugmalar) — Free'da matn qadami o'tkazib yuboriladi (None)."""
    lang = get_lang(owner_id)
    if not has_feature(owner_id, "custom_text"):
        return None
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t(lang, "btn_sc_deftext"), callback_data=_sc_cb("sc_deftext", d))],
        [InlineKeyboardButton(t(lang, "btn_sc_cancel"), callback_data=_sc_cb("sc_cancel", d))],
    ])
    return t(lang, "sc_text_prompt", max=SCHEDULE_MAX_TEXT), markup


async def handle_schedule_callback(query, owner_id: int, data: str, lang: str) -> bool:
    """sc_* tugmalari. True — qayta ishlandi."""
    if data == "sc_menu":
        _sc_drafts.pop(owner_id, None)
        text, markup = build_sched_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data.startswith("sc_pg:"):
        try:
            page = int(data.split(":")[1])
        except (ValueError, IndexError):
            page = 0
        text, markup = build_sched_menu(owner_id, page=page)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data == "sc_settings":
        text, markup = build_sched_settings(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data in ("sc_enable", "sc_disable", "sc_toggle"):
        # Aniq amallar (idempotent): eski xabardagi tugma qayta bosilsa ham holat teskarilanmaydi.
        # Eski «sc_toggle» tugmalari (yangilashdan oldingi xabarlar) hech narsani o'zgartirmaydi.
        if data != "sc_toggle":
            db.update_settings(owner_id, scheduler_enabled=(data == "sc_enable"))
        text, markup = build_sched_settings(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data.startswith("sc_list:"):
        text, markup = build_sched_list(owner_id, "del" if data.endswith(":del") else "edit")
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data == "sc_add":
        if db.count_schedule_rules(owner_id) >= schedule_limit_for(owner_id):
            text, markup = build_sched_menu(owner_id, t(lang, "sc_limit", max=schedule_limit_for(owner_id)))
        else:
            _sc_new_draft(owner_id)
            text, markup = build_sched_days(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data.startswith("sc_e:"):
        try:
            view = build_sched_entry(owner_id, int(data.split(":")[1]))
        except ValueError:
            view = None
        if view is None:
            view = build_sched_list(owner_id, "edit")
            view = (f"{t(lang, 'sc_gone')}\n\n{view[0]}", view[1])
        await query.edit_message_text(view[0], reply_markup=view[1])
        return True

    if data.split(":")[0] in ("sc_pause", "sc_resume", "sc_tg"):
        # Pauza va Davom ettirish ALOHIDA amallar (idempotent): eski xabardagi tugma ikki marta bosilsa ham holat teskarilanmaydi.
        # Eski formatdagi «sc_tg:ID» tugmalari (yangilashdan oldingi xabarlar) hech narsani o'zgartirmaydi.
        action = data.split(":")[0]
        try:
            rule_id = int(data.split(":")[1])
        except (ValueError, IndexError):
            return True
        rule = db.get_schedule_rule(owner_id, rule_id)
        if rule is None:
            text, markup = build_sched_list(owner_id, "edit")
            await query.edit_message_text(f"{t(lang, 'sc_gone')}\n\n{text}", reply_markup=markup)
            return True
        if action != "sc_tg":
            want = action == "sc_resume"
            if bool(rule["is_enabled"]) != want:
                db.update_schedule_rule(owner_id, rule_id, is_enabled=want)
        text, markup = build_sched_entry(owner_id, rule_id, t(lang, "sc_updated"))
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data.startswith("sc_del:"):
        try:
            found = _sc_entry_text(owner_id, int(data.split(":")[1]))
        except ValueError:
            found = None
        if found is None:
            text, markup = build_sched_list(owner_id, "del")
            await query.edit_message_text(f"{t(lang, 'sc_gone')}\n\n{text}", reply_markup=markup)
            return True
        rule_id = found[2]["id"]
        token = secrets.token_hex(3)
        _sc_del_confirms[owner_id] = {"rule_id": rule_id, "token": token, "ts": time.time()}
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(t(lang, "btn_sc_del_yes"), callback_data=f"sc_del_yes:{rule_id}:{token}")],
            [InlineKeyboardButton(t(lang, "btn_sc_cancel"), callback_data="sc_menu")],
        ])
        await query.edit_message_text(t(lang, "sc_del_confirm", entry=found[1]), reply_markup=markup)
        return True

    if data.startswith("sc_del_yes:"):
        parts = data.split(":")
        if stale_confirm_button(owner_id, data):
            # Eski/soxta tugma: joriy (yangi ochilgan) tasdiqni ham, kiritilayotgan vaqt/matnni ham BEKOR QILMAYDI
            text, markup = build_sched_menu(owner_id, t(lang, "sc_stale_button"))
            await query.edit_message_text(text, reply_markup=markup)
            return True
        _sc_del_confirms.pop(owner_id, None)  # bir martalik: ikkinchi bosish ham o'chirmaydi
        rule_id = int(parts[1])
        gone = not db.delete_schedule_rule(owner_id, rule_id)
        text, markup = build_sched_menu(owner_id, t(lang, "sc_gone" if gone else "sc_deleted"))
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data.split(":")[0] == "sc_cancel":
        if sc_button_is_stale(owner_id, data):  # eski xabardagi «Bekor qilish» — joriy qoralamaga tegmaydi
            await query.edit_message_text(
                t(lang, "sc_stale_button"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="sc_menu")]]),
            )
            return True
        _sc_drafts.pop(owner_id, None)
        clear_pending_action(owner_id)
        text, markup = build_sched_menu(owner_id, t(lang, "sc_cancelled"))
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data.startswith("sc_ed:"):
        parts = data.split(":")
        try:
            field, rule_id = parts[1], int(parts[2])
        except (IndexError, ValueError):
            return True
        rule = db.get_schedule_rule(owner_id, rule_id)
        if rule is None or field not in ("days", "time", "text"):
            text, markup = build_sched_list(owner_id, "edit")
            await query.edit_message_text(f"{t(lang, 'sc_gone')}\n\n{text}", reply_markup=markup)
            return True
        d = _sc_new_draft(
            owner_id, days=set(mask_days(rule["days"])), start=rule["start_min"], end=rule["end_min"], text=rule["text"],
            edit_id=rule_id, edit=field, stage={"days": "days", "time": "time", "text": "text"}[field],
        )
        if field == "days":
            text, markup = build_sched_days(owner_id)
        elif field == "time":
            set_pending_action(owner_id, "sc_time")
            text = t(lang, "sc_time_prompt")
            markup = _sc_time_markup(lang, d)
        else:
            set_pending_action(owner_id, "sc_text")
            text, markup = _sc_text_step(owner_id, d)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    # --- qoralama bilan ishlaydigan qadamlar ---
    d = _sc_draft(owner_id)
    base, *rest = data.split(":")
    arg = None
    if base in _SC_STAGE_FOR or base in ("sc_d", "sc_dp"):
        # Tugma qoralama ID sini olib yuradi (oxirgi qism): ID mos kelmasa yoki bosqich mos bo'lmasa — eski xabar, hech narsa o'zgarmaydi
        token = rest[-1] if rest else None
        arg = rest[0] if base in ("sc_d", "sc_dp") and len(rest) >= 2 else None
        if sc_button_is_stale(owner_id, data):
            if d is None:  # qoralama umuman yo'q (tugagan/bekor qilingan)
                text, markup = build_sched_menu(owner_id, t(lang, "sc_draft_lost"))
            else:  # boshqa (joriy) qoralama bor — unga tegmaymiz, faqat eski xabarni ogohlantirishga almashtiramiz
                text = t(lang, "sc_stale_button")
                markup = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data="sc_menu")]])
            await query.edit_message_text(text, reply_markup=markup)
            return True
        data = base  # pastdagi qadamlar tugma turi bo'yicha ishlaydi

    if data == "sc_d":
        try:
            i = int(arg)
        except (TypeError, ValueError):
            return True
        if 0 <= i <= 6:
            d["days"] ^= {i}
        d["ts"] = time.time()
        text, markup = build_sched_days(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data == "sc_dp":
        d["days"] = set(mask_days({"wd": WEEKDAYS_MASK, "we": WEEKEND_MASK, "all": ALL_DAYS_MASK}.get(arg, 0)))
        d["ts"] = time.time()
        text, markup = build_sched_days(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    if data == "sc_dnext":
        if not d["days"]:  # callback'ga bir martadan ortiq javob berib bo'lmaydi — ogohlantirish xabar ichida
            text, markup = build_sched_days(owner_id)
            await query.edit_message_text(f"\u26A0\uFE0F {t(lang, 'sc_days_none')}\n\n{text}", reply_markup=markup)
            return True
        d["ts"] = time.time()
        if d["edit_id"] is not None:  # mavjud jadval kunlarini o'zgartirish
            status, n = db.update_schedule_rule(owner_id, d["edit_id"], days=days_mask(d["days"]))
            if status == "conflict":
                text, markup = build_sched_days(owner_id)
                await query.edit_message_text(f"{_sc_conflict_notice(lang, n)}\n\n{text}", reply_markup=markup)
                return True
            _sc_drafts.pop(owner_id, None)
            view = build_sched_entry(owner_id, d["edit_id"], t(lang, "sc_updated"))
            if view is None:
                view = build_sched_menu(owner_id, t(lang, "sc_gone"))
            await query.edit_message_text(view[0], reply_markup=view[1])
            return True
        d["stage"] = "time"
        set_pending_action(owner_id, "sc_time")
        await query.edit_message_text(t(lang, "sc_time_prompt"), reply_markup=_sc_time_markup(lang, d))
        return True

    if data == "sc_allday":
        await _sc_after_time(query.message, owner_id, lang, *SCHEDULE_ALL_DAY, edit_message=query)
        return True

    if data == "sc_deftext":
        clear_pending_action(owner_id)
        d["text"] = None
        await _sc_finish_text(query.message, owner_id, lang, edit_message=query)
        return True

    if data == "sc_save":
        clear_pending_action(owner_id)
        valid = (
            d["edit_id"] is None and d["days"] and d["start"] is not None and d["end"] is not None
            and valid_schedule_time(d["start"], d["end"])
        )
        if not valid:  # to'liq bo'lmagan qoralama bazaga yozilmaydi
            _sc_drafts.pop(owner_id, None)
            text, markup = build_sched_menu(owner_id, t(lang, "sc_draft_lost"))
            await query.edit_message_text(text, reply_markup=markup)
            return True
        _sc_drafts.pop(owner_id, None)
        status, n = db.add_schedule_rule(
            owner_id, days_mask(d["days"]), d["start"], d["end"], d.get("text"), schedule_limit_for(owner_id)
        )
        if status == "ok":
            notice = t(lang, "sc_saved")
        elif status == "limit":
            notice = t(lang, "sc_limit", max=schedule_limit_for(owner_id))
        else:
            notice = _sc_conflict_notice(lang, n)
        text, markup = build_sched_menu(owner_id, notice)
        await query.edit_message_text(text, reply_markup=markup)
        return True

    return False


async def _sc_reply(message, edit_message, text, markup):
    if edit_message is not None:
        await edit_message.edit_message_text(text, reply_markup=markup)
    else:
        await message.reply_text(text, reply_markup=markup)


async def _sc_after_time(message, owner_id: int, lang: str, start: int, end: int, edit_message=None):
    """Vaqt kiritilgach: tahrirlash bo'lsa — saqlaydi; yangi jadval bo'lsa — matn qadamiga (yoki tasdiqqa) o'tadi."""
    d = _sc_draft(owner_id)
    if d is None:
        clear_pending_action(owner_id)
        await _sc_reply(message, edit_message, t(lang, "sc_draft_lost"), None)
        return
    d["start"], d["end"], d["ts"] = start, end, time.time()
    if d["edit_id"] is not None:
        status, n = db.update_schedule_rule(owner_id, d["edit_id"], start_min=start, end_min=end)
        if status == "conflict":
            # Tugma bosilganda (masalan "Kun bo'yi") kutilayotgan amal tozalangan bo'lishi mumkin — yangi vaqt
            # yozilsa qabul qilinishi uchun qayta yoqamiz, aks holda kiritilgan vaqt jimgina e'tiborsiz qolardi.
            set_pending_action(owner_id, "sc_time")
            await _sc_reply(message, edit_message, f"{_sc_conflict_notice(lang, n)}\n\n{t(lang, 'sc_time_prompt')}", _sc_time_markup(lang, d))
            return
        clear_pending_action(owner_id)
        _sc_drafts.pop(owner_id, None)
        view = build_sched_entry(owner_id, d["edit_id"], t(lang, "sc_updated")) or build_sched_menu(owner_id, t(lang, "sc_gone"))
        await _sc_reply(message, edit_message, view[0], view[1])
        return
    step = _sc_text_step(owner_id, d)
    if step is None:  # Free: alohida matn yo'q — standart matn ishlatiladi
        clear_pending_action(owner_id)
        d["text"] = None
        d["stage"] = "confirm"
        text, markup = _sc_confirm_view(owner_id, d)
        await _sc_reply(message, edit_message, f"{t(lang, 'sc_text_locked_note')}\n\n{text}", markup)
        return
    d["stage"] = "text"
    set_pending_action(owner_id, "sc_text")
    await _sc_reply(message, edit_message, step[0], step[1])


async def _sc_finish_text(message, owner_id: int, lang: str, edit_message=None):
    """Matn tanlangach: tahrirlash bo'lsa saqlaydi, aks holda tasdiq ekrani."""
    d = _sc_draft(owner_id)
    if d is None:
        await _sc_reply(message, edit_message, t(lang, "sc_draft_lost"), None)
        return
    d["ts"] = time.time()
    if d["edit_id"] is not None:
        status, _ = db.update_schedule_rule(owner_id, d["edit_id"], text=d["text"])
        _sc_drafts.pop(owner_id, None)
        view = (build_sched_entry(owner_id, d["edit_id"], t(lang, "sc_updated")) if status == "ok" else None) \
            or build_sched_menu(owner_id, t(lang, "sc_gone"))
        await _sc_reply(message, edit_message, view[0], view[1])
        return
    d["stage"] = "confirm"
    text, markup = _sc_confirm_view(owner_id, d)
    await _sc_reply(message, edit_message, text, markup)


async def handle_schedule_text(update, owner_id: int, action: str, value: str, lang: str) -> bool:
    """Foydalanuvchi matn yuborganda: sc_time / sc_text qadamlari. True — qayta ishlandi."""
    if action == "sc_time":
        parsed = parse_time_range_input(value)
        if parsed is None or not valid_schedule_time(*parsed):
            await update.message.reply_text(t(lang, "sc_time_bad"))
            return True  # amal saqlanadi — qayta yuboradi
        await _sc_after_time(update.message, owner_id, lang, parsed[0], parsed[1])
        return True
    if action == "sc_text":
        d = _sc_draft(owner_id)
        if d is None:
            clear_pending_action(owner_id)
            await update.message.reply_text(t(lang, "sc_draft_lost"))
            return True
        if not value:
            await update.message.reply_text(t(lang, "sc_text_too_long", n=0, max=SCHEDULE_MAX_TEXT))
            return True
        if len(value) > SCHEDULE_MAX_TEXT:
            await update.message.reply_text(t(lang, "sc_text_too_long", n=len(value), max=SCHEDULE_MAX_TEXT))
            return True
        clear_pending_action(owner_id)
        d["text"] = value
        await _sc_finish_text(update.message, owner_id, lang)
        return True
    return False


# ---------------------------------------------------------------------------
# Smart FAQ
# ---------------------------------------------------------------------------
_faq_edit_target: dict[int, dict] = {}  # {owner_id: {"id", "ts"}} — qaysi savol tahrirlanmoqda
_faq_drafts: dict[int, dict] = {}  # {owner_id: {"q","kw","ans","ts"}} — saqlashdan oldingi qoralama (RAM, 10 daqiqa)


def _faq_draft(owner_id: int) -> dict | None:
    d = _faq_drafts.get(owner_id)
    if d is None or time.time() - d["ts"] > PENDING_ACTION_TTL_SECONDS:
        _faq_drafts.pop(owner_id, None)
        return None
    return d


def _faq_short(text: str, n: int = 40) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[: n - 1] + "\u2026"


def build_faq_menu(owner_id: int, notice: str | None = None):
    lang = get_lang(owner_id)
    s = db.get_settings(owner_id)
    enabled = s.get("faq_enabled", True)
    text = t(
        lang, "faq_menu",
        count=db.count_faq_entries(owner_id), max=faq_limit_for(owner_id),
        status=t(lang, "status_on" if enabled else "status_off"),
        notice=f"\n\n{notice}" if notice else "",
    )
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_faq_add"), callback_data="faq_add")],
        [InlineKeyboardButton(t(lang, "btn_faq_list"), callback_data="faq_list")],
        [InlineKeyboardButton(t(lang, "btn_faq_settings"), callback_data="faq_settings")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_faq_settings(owner_id: int):
    lang = get_lang(owner_id)
    enabled = db.get_settings(owner_id).get("faq_enabled", True)
    text = t(lang, "faq_settings", status=t(lang, "status_on" if enabled else "status_off"))
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_disable" if enabled else "btn_enable"), callback_data="faq_off" if enabled else "faq_on")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="faq_menu")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_faq_list(owner_id: int):
    lang = get_lang(owner_id)
    entries = db.list_faq_entries(owner_id)
    if not entries:
        text = t(lang, "faq_list_empty")
    else:
        text = t(lang, "faq_list_title", count=len(entries), max=faq_limit_for(owner_id))
    keyboard = [
        [InlineKeyboardButton(("" if e["is_enabled"] else "\u23F8 ") + _faq_short(e["question"]), callback_data=f"faq_view:{e['id']}")]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="faq_menu")])
    return text, InlineKeyboardMarkup(keyboard)


def build_faq_entry(owner_id: int, entry_id: int, notice: str | None = None):
    """(matn, tugmalar) yoki None — yozuv topilmasa (boshqa egasiniki ham 'topilmadi')."""
    lang = get_lang(owner_id)
    e = db.get_faq_entry(owner_id, entry_id)
    if e is None:
        return None
    text = t(
        lang, "faq_entry_view",
        q=e["question"], kw=", ".join(e["keywords"]), a=e["answer"],
        status=t(lang, "status_on" if e["is_enabled"] else "status_off"),
    )
    if notice:
        text += f"\n\n{notice}"
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_faq_edit_q"), callback_data=f"faq_edit:q:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_faq_edit_kw"), callback_data=f"faq_edit:kw:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_faq_edit_ans"), callback_data=f"faq_edit:ans:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_faq_entry_off" if e["is_enabled"] else "btn_faq_entry_on"), callback_data=f"faq_entry_{'off' if e['is_enabled'] else 'on'}:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_faq_delete"), callback_data=f"faq_del:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="faq_list")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def find_faq_answer(owner_id: int, text: str) -> str | None:
    """Mijoz xabariga mos FAQ javobi (ishonchli bo'lsagina), aks holda None. Xatolik oqimni buzmaydi."""
    try:
        limit = faq_limit_for(owner_id)
        if limit <= 0:
            return None  # tarifda Smart FAQ yo'q (masalan Bepulga tushgan)
        # Tarif pasaygan bo'lsa, faqat limitga sig'adigan birinchi savollar ishlaydi
        entries = db.get_enabled_faq_entries(owner_id)[:limit]
        entry = match_faq(text, entries)
    except Exception:
        logger.exception("Smart FAQ qidiruvida xato (owner=%s)", owner_id)
        return None
    return entry["answer"] if entry else None


# ---------------------------------------------------------------------------
# AI Bilimlar bazasi (Knowledge Base)
# ---------------------------------------------------------------------------
_kb_edit_target: dict[int, dict] = {}  # {owner_id: {"id", "ts"}} — qaysi yozuv tahrirlanmoqda
_kb_del_confirms: dict[int, dict] = {}  # {owner_id: {"entry_id","token","ts"}} — bir martalik o'chirish tasdig'i (RAM)
_kb_drafts: dict[int, dict] = {}  # {owner_id: {"title","content","kw","ts"}} — saqlashdan oldingi qoralama (RAM)


def _kb_draft(owner_id: int) -> dict | None:
    d = _kb_drafts.get(owner_id)
    if d is None or time.time() - d["ts"] > PENDING_ACTION_TTL_SECONDS:
        _kb_drafts.pop(owner_id, None)
        return None
    return d


def _kb_kw_text(lang: str, keywords) -> str:
    return ", ".join(keywords) if keywords else t(lang, "kb_no_keywords")


def build_kb_menu(owner_id: int, notice: str | None = None):
    lang = get_lang(owner_id)
    enabled = db.get_settings(owner_id).get("kb_enabled", True)
    text = t(
        lang, "kb_menu",
        count=db.count_kb_entries(owner_id), max=kb_limit_for(owner_id),
        status=t(lang, "status_on" if enabled else "status_off"),
        notice=f"\n\n{notice}" if notice else "",
    ) + "\n\n" + t(lang, "kb_privacy")
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_kb_add"), callback_data="kb_add")],
        [InlineKeyboardButton(t(lang, "btn_kb_list"), callback_data="kb_list")],
        [InlineKeyboardButton(t(lang, "btn_kb_settings"), callback_data="kb_settings")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_kb_settings(owner_id: int):
    lang = get_lang(owner_id)
    enabled = db.get_settings(owner_id).get("kb_enabled", True)
    text = t(lang, "kb_settings", status=t(lang, "status_on" if enabled else "status_off"))
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_disable" if enabled else "btn_enable"), callback_data="kb_off" if enabled else "kb_on")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="kb_menu")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_kb_list(owner_id: int):
    lang = get_lang(owner_id)
    entries = db.list_kb_entries(owner_id)
    if not entries:
        text = t(lang, "kb_list_empty")
    else:
        text = t(lang, "kb_list_title", count=len(entries), max=kb_limit_for(owner_id))
    keyboard = [
        [InlineKeyboardButton(("" if e["is_enabled"] else "\u23F8 ") + _faq_short(e["title"]), callback_data=f"kb_view:{e['id']}")]
        for e in entries
    ]
    keyboard.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="kb_menu")])
    return text, InlineKeyboardMarkup(keyboard)


def build_kb_entry(owner_id: int, entry_id: int, notice: str | None = None):
    """(matn, tugmalar) yoki None — yozuv topilmasa (boshqa egasiniki ham 'topilmadi')."""
    lang = get_lang(owner_id)
    e = db.get_kb_entry(owner_id, entry_id)
    if e is None:
        return None
    text = t(
        lang, "kb_entry_view",
        title=e["title"], content=e["content"], kw=_kb_kw_text(lang, e["keywords"]),
        status=t(lang, "status_on" if e["is_enabled"] else "status_off"),
    )
    if notice:
        text += f"\n\n{notice}"
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_kb_edit_t"), callback_data=f"kb_edit:t:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_kb_edit_c"), callback_data=f"kb_edit:c:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_kb_edit_kw"), callback_data=f"kb_edit:kw:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_kb_entry_off" if e["is_enabled"] else "btn_kb_entry_on"), callback_data=f"kb_entry_{'off' if e['is_enabled'] else 'on'}:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_kb_delete"), callback_data=f"kb_del:{e['id']}")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="kb_list")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def find_kb_context(owner_id: int, messages) -> list[dict]:
    """AI'ga beriladigan Bilimlar bazasi yozuvlari. Tarifda yo'q / o'chirilgan / xato bo'lsa — [] (AI odatdagidek ishlaydi)."""
    try:
        limit = kb_limit_for(owner_id)
        if limit <= 0 or not db.get_settings(owner_id).get("kb_enabled", True):
            return []
        # Tarif pasaygan bo'lsa, faqat limitga sig'adigan birinchi yozuvlar ishlaydi
        entries = db.get_enabled_kb_entries(owner_id)[:limit]
        return select_knowledge(messages, entries)
    except Exception:
        logger.exception("Bilimlar bazasi qidiruvida xato (owner=%s)", owner_id)
        return []


def build_sleep_menu(owner_id: int):
    lang = get_lang(owner_id)
    s = db.get_settings(owner_id)
    enabled = s.get("sleep_mode_enabled", False)
    start_minutes = s.get("sleep_start_minutes", 23 * 60)
    end_minutes = s.get("sleep_end_minutes", 7 * 60)

    text = t(
        lang, "sleep_menu",
        status=t(lang, "sleep_status_on" if enabled else "status_off"),
        range=format_time_range(start_minutes, end_minutes),
        text=sleep_text_for(s, lang)[:MENU_TEXT_PREVIEW_CHARS],
    ) + "\n\n" + t(lang, "sleep_tz_note", tz=str(tz_from_settings(s, owner_id)))
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_disable" if enabled else "btn_enable"), callback_data="sleep_disable" if enabled else "sleep_enable")],
        [InlineKeyboardButton(t(lang, "btn_sleep_time"), callback_data="sleep_edit_time")],
        [InlineKeyboardButton(lock_label(t(lang, "btn_edit_text"), has_feature(owner_id, "custom_text")), callback_data="sleep_edit_text")],
        [InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_bio_menu(owner_id: int):
    lang = get_lang(owner_id)
    connection = db.get_connection(owner_id)
    s = db.get_settings(owner_id)
    target = s.get("bio_countdown_target")

    if not connection or not connection.get("can_edit_bio"):
        keyboard = [[InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")]]
        return t(lang, "bio_no_perm"), InlineKeyboardMarkup(keyboard)

    if target:
        preview = compute_bio_text(
            target, s.get("birthday_month"), s.get("birthday_day"), today=today_tashkent(), lang=lang
        )
        status = t(lang, "bio_status_on", label=bio_event_label(target, lang), preview=preview or t(lang, "bio_no_date"))
    else:
        status = t(lang, "bio_status_off")

    text = t(lang, "bio_menu", status=status)
    keyboard = [
        [InlineKeyboardButton(t(lang, "btn_bio_new_year"), callback_data="bio_set_new_year")],
        [InlineKeyboardButton(t(lang, "btn_bio_navroz"), callback_data="bio_set_navroz")],
        [InlineKeyboardButton(t(lang, "btn_bio_birthday"), callback_data="bio_set_birthday")],
    ]
    if target:
        keyboard.append([InlineKeyboardButton(t(lang, "btn_disable"), callback_data="bio_disable")])
    keyboard.append([InlineKeyboardButton(t(lang, "btn_back"), callback_data="open_panel")])
    return text, InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Buyruq va tugmalar
# ---------------------------------------------------------------------------
async def run_start_flow(bot, owner_id: int, inviter_id: int | None, send):
    """Til tanlangandan keyingi umumiy oqim: obuna tekshiruvi -> referal -> bosh menyu.
    `send(text, markup)` — xabarni yuboruvchi (yangi xabar yoki tugma xabarini tahrirlash)."""
    lang = get_lang(owner_id)
    if not await is_subscribed(bot, owner_id):
        # Referal obuna bo'lgandan KEYIN hisoblanadi (tugma orqali olib o'tiladi)
        await send(t(lang, "gate_text"), build_subscribe_gate_markup(inviter_id, lang))
        return
    await finish_start_flow(bot, owner_id, inviter_id, send)


async def finish_start_flow(bot, owner_id: int, inviter_id: int | None, send):
    """Obunadan o'tgandan keyingi qism: referal -> Smart Onboarding (kerak bo'lsa) -> bosh menyu.
    Obuna "✅ Tekshirish" tugmasi bilan tasdiqlanganda ham SHU funksiya ishlaydi (onboarding o'tib ketmasin)."""
    await process_referral(bot, owner_id, inviter_id)
    ob_view = onboarding_start_view(owner_id)
    if ob_view is not None:
        await send(*ob_view)
        return
    greeting, markup = build_start_view(owner_id)
    await send(greeting, markup)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    track_user(update.effective_user)
    clear_pending_action(owner_id)  # /start har doim tugallanmagan amalni tozalaydi
    clear_scheduler_state(owner_id)  # ... shu jumladan jadval qoralamasi va o'chirish tasdig'ini

    inviter_id = parse_referral_arg(context.args)

    if not has_chosen_lang(owner_id):
        # Birinchi marta: avval til tanlanadi (referal ID tugma ichida saqlanadi)
        await update.message.reply_text(t(DEFAULT_LANG, "lang_pick"), reply_markup=build_lang_markup(inviter_id))
        return

    async def send(text, markup):
        await update.message.reply_text(text, reply_markup=markup)

    await run_start_flow(context.bot, owner_id, inviter_id, send)


HELP_TEXT = t("uz", "help")  # eski nom (o'zbekcha)

ADMIN_HELP_TEXT = (
    "\n\n\U0001F510 Admin buyruqlari:\n"
    "/stats — foydalanuvchilar soni\n"
    "/onboarding — yangi foydalanuvchilar onboarding statistikasi\n"
    "/users — botga start bosgan barcha foydalanuvchilar ro'yxati\n"
    "/bots — bazaga tushib qolgan botlarni topish va tozalash\n"
    "/block @username [sabab] — foydalanuvchini bloklash (yoki /block 123456789)\n"
    "/unblock @username — blokdan chiqarish\n"
    "/setplan @username plus 1oy — tarifni belgilash (muddat: 1oy, 2hafta, 30kun, 1yil; tugagach avtomatik Bepul; muddatsiz ham mumkin)\n"
    "/blocked — bloklanganlar ro'yxati\n"
    "/reklama — barcha foydalanuvchilarga xabar yuborish (yuborishdan oldin tasdiqlanadi)\n"
    "/reklama_status — oxirgi reklama holati\n"
    "/reklama_retry — oxirgi reklamani qayta urinish\n"
    "/cancel — joriy admin amalini bekor qilish"
)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    track_user(update.effective_user)
    text = t(get_lang(user_id), "help")
    # Admin buyruqlari faqat adminning o'ziga ko'rsatiladi
    if ADMIN_ID and user_id == ADMIN_ID:
        text += ADMIN_HELP_TEXT
    await update.message.reply_text(text)


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    owner_id = query.from_user.id
    track_user(query.from_user)
    data = query.data

    # MUHIM: Telegram har bir callback_query'ga FAQAT BIR MARTA javob (answer)
    # qabul qiladi — ikkinchi chaqiruv e'tiborsiz qoldiriladi. Shuning uchun
    # matnli/alert bilan javob beradigan shoxlar umumiy `query.answer()`
    # dan OLDIN, har biri o'zi bir marta javob berib, tugaydi. Qolgan hamma
    # tugmalar uchun pastdagi umumiy answer() chaqiriladi.
    if data.startswith("ob_"):
        await handle_onboarding_callback(query, owner_id, data)
        return

    if data.startswith("lang:"):
        parts = data.split(":")
        code = parts[1] if len(parts) > 1 else ""
        if not is_lang(code):
            await query.answer(t(get_lang(owner_id), "bad_button"), show_alert=True)
            return
        set_lang(owner_id, code)
        inviter_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        await query.answer(t(code, "lang_changed"))
        clear_pending_action(owner_id)

        async def send(text, markup):
            await query.edit_message_text(text, reply_markup=markup)

        await run_start_flow(context.bot, owner_id, inviter_id, send)
        return

    if data == "check_subscription" or data.startswith("check_subscription:"):
        lang = get_lang(owner_id)
        if await is_subscribed(context.bot, owner_id):
            await query.answer(t(lang, "gate_ok"))
            inviter_id = None
            if ":" in data:
                try:
                    inviter_id = int(data.split(":", 1)[1])
                except ValueError:
                    inviter_id = None

            async def send(text, markup):
                await query.edit_message_text(text, reply_markup=markup)

            await finish_start_flow(context.bot, owner_id, inviter_id, send)
        else:
            await query.answer(t(lang, "gate_fail"), show_alert=True)
        return

    if data.startswith("fbreply:"):
        if owner_id != ADMIN_ID:
            await query.answer(t(get_lang(owner_id), "no_permission"), show_alert=True)
            return
        try:
            target_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer(t(get_lang(owner_id), "bad_button"), show_alert=True)
            return
        await query.answer()
        set_pending_admin_action(owner_id, f"feedback_reply:{target_id}")
        await query.message.reply_text(
            f"\u21A9\uFE0F {_label_for(target_id)} ga javobingizni bitta xabar qilib yozing.\n"
            "Bekor qilish: /cancel"
        )
        return

    if data.startswith("rmbots:"):
        await handle_rmbots(query, context, data)
        return

    if data.startswith("users:"):
        await handle_users_page(query, context, data)
        return

    if data == "admin_referrals" and owner_id != ADMIN_ID:
        await query.answer(t(get_lang(owner_id), "no_permission"), show_alert=True)
        return

    if data == "bc_cancel" or data.startswith("bc_confirm:"):
        await handle_broadcast_confirmation(query, context, data)
        return

    if data == "appeal_start":
        # Bloklangan foydalanuvchining bosishi block_gate'da ushlanadi. Bu yerga
        # faqat bloklanmagan (masalan blokdan chiqarilgan) odam eski tugmani
        # bossa keladi.
        await query.answer(t(get_lang(owner_id), "not_blocked"), show_alert=True)
        return

    if data.startswith("unblock:"):
        if owner_id != ADMIN_ID:
            await query.answer(t(get_lang(owner_id), "no_permission"), show_alert=True)
            return
        try:
            target_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer(t(get_lang(owner_id), "bad_button"), show_alert=True)
            return
        changed = await do_unblock(context.bot, target_id)
        await query.answer(
            "\u2705 Blokdan chiqarildi." if changed else "Bu foydalanuvchi allaqachon blokdan chiqarilgan."
        )
        original = getattr(query.message, "text", None) or ""
        suffix = (
            "\u2705 Blokdan chiqarildi." if changed else "\u2139\uFE0F Allaqachon blokdan chiqarilgan edi."
        )
        try:
            await query.edit_message_text(f"{original}\n\n{suffix}")  # tugma ham yo'qoladi
        except TelegramError as e:
            logger.info("Apellyatsiya xabarini yangilab bo'lmadi: %s", e)
        return

    await query.answer()

    # Har qanday boshqa tugma bosilsa, oldingi tugallanmagan amal (masalan "yangi matn
    # yuboring") bekor bo'ladi; yangi amal boshlaydigan tugmalar pastda uni qayta o'rnatadi.
    # Istisno: jadval qoralamasiga bog'liq ESKIRGAN tugma hech narsani bekor qilmaydi — foydalanuvchining
    # hozirgi kiritishi (vaqt/matn) davom etaveradi.
    # Xuddi shu qoida FAQ/Bilimlar bazasi qoralamalari va o'chirish tasdiqlari uchun ham: eskirgan tugma
    # (boshqa/eski qoralama yoki tasdiqniki) hech narsani bekor qilmaydi.
    stale_button = (data.startswith("sc_") and sc_button_is_stale(owner_id, data)) or stale_confirm_button(owner_id, data)
    if not stale_button:
        clear_pending_action(owner_id)
    # Har qanday boshqa tugma (o'chirishni tasdiqlashdan tashqari) ochiq o'chirish tasdig'ini bekor qiladi
    if not stale_button and not data.startswith(("sc_del_yes:", "kb_del_yes:")):
        _sc_del_confirms.pop(owner_id, None)
        _kb_del_confirms.pop(owner_id, None)

    lang = get_lang(owner_id)

    feature = locked_feature_for(data)
    if feature and not has_feature(owner_id, feature):
        text, markup = build_locked_view(owner_id, feature)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith(("faq_", "kb_")) and stale_confirm_button(owner_id, data):
        back = "faq_menu" if data.startswith("faq_") else "kb_menu"
        await query.edit_message_text(
            t(lang, "sc_stale_button"),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_back"), callback_data=back)]]),
        )
        return

    if data == "lang_menu":
        await query.edit_message_text(t(lang, "lang_pick"), reply_markup=build_lang_markup())
        return

    if data == "how_connect":
        await query.edit_message_text(how_connect_text(lang), reply_markup=main_menu_markup(owner_id))
        return

    if data == "open_panel":
        conn = db.get_connection(owner_id)
        if not conn or not conn["is_enabled"]:
            await query.edit_message_text(how_connect_text(lang), reply_markup=main_menu_markup(owner_id))
            return
        text, markup = build_panel(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "back":
        await query.edit_message_text(t(lang, "main_menu"), reply_markup=main_menu_markup(owner_id))
        return

    if data == "plans":
        text, markup = build_plans_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith("plan:"):
        key = data.split(":", 1)[1]
        if key not in PLAN_KEYS:
            return
        text, markup = build_plan_view(owner_id, key)
        await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        return

    if data == "support":
        text, markup = build_support_view(lang)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "support_feedback":
        set_pending_action(owner_id, "feedback")
        await query.message.reply_text(t(lang, "feedback_prompt"))
        return

    if data == "referral":
        text, markup = build_referral_view(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "admin_referrals":
        text, markup = await build_admin_referrals_view(context.bot)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data in ("status_online", "status_offline", "toggle_status"):
        # Aniq (idempotent) amallar. Eski «toggle_status» tugmalari (yangilashdan oldingi xabarlar) holatni o'zgartirmaydi,
        # faqat panelni yangilaydi.
        if data != "toggle_status":
            db.update_settings(owner_id, offline=(data == "status_offline"))

    elif data == "edit_cooldown":
        set_pending_action(owner_id, "cooldown")
        await query.message.reply_text(t(lang, "cooldown_prompt"))
        return

    elif data == "edit_text":
        set_pending_action(owner_id, "text")
        await query.message.reply_text(t(lang, "text_prompt"))
        return

    if data == "bio_menu":
        text, markup = build_bio_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data in ("bio_set_new_year", "bio_set_navroz"):
        target = "new_year" if data == "bio_set_new_year" else "navroz"
        db.update_settings(owner_id, bio_countdown_target=target)
        ok, info = await apply_bio_update(context.bot, owner_id)
        text, markup = build_bio_menu(owner_id)
        if not ok:
            text += "\n\n" + t(lang, "bio_failed", info=info)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "bio_set_birthday":
        s = db.get_settings(owner_id)
        if s.get("birthday_month") and s.get("birthday_day"):
            db.update_settings(owner_id, bio_countdown_target="birthday")
            ok, info = await apply_bio_update(context.bot, owner_id)
            text, markup = build_bio_menu(owner_id)
            if not ok:
                text += "\n\n" + t(lang, "bio_failed", info=info)
            await query.edit_message_text(text, reply_markup=markup)
        else:
            set_pending_action(owner_id, "birthday_date")
            await query.message.reply_text(t(lang, "bio_birthday_prompt"))
        return

    if data == "bio_disable":
        db.update_settings(owner_id, bio_countdown_target=None)
        text, markup = build_bio_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith("nc_"):
        if not name_clock_allowed(owner_id):
            return  # ruxsatsiz; umumiy answer() yuqorida allaqachon chaqirilgan
        await handle_name_clock_button(query, context, data, owner_id)
        return

    if data == "faq_menu":
        _faq_drafts.pop(owner_id, None)
        text, markup = build_faq_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "faq_settings":
        text, markup = build_faq_settings(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data in ("faq_on", "faq_off", "faq_toggle"):
        # Aniq (idempotent) amallar; eski «faq_toggle» tugmasi holatni o'zgartirmaydi, faqat joriy holatni ko'rsatadi.
        if data != "faq_toggle":
            db.update_settings(owner_id, faq_enabled=(data == "faq_on"))
        text, markup = build_faq_settings(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "faq_list":
        text, markup = build_faq_list(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith(("faq_view:", "faq_del:", "faq_entry_toggle:", "faq_entry_on:", "faq_entry_off:")):
        action, _, raw_id = data.partition(":")
        entry_id = int(raw_id) if raw_id.isdigit() else -1
        notice = None
        if action == "faq_del":
            notice = t(lang, "faq_deleted") if db.delete_faq_entry(owner_id, entry_id) else t(lang, "faq_entry_gone")
            text, markup = build_faq_list(owner_id)
            await query.edit_message_text(f"{notice}\n\n{text}", reply_markup=markup)
            return
        if action in ("faq_entry_on", "faq_entry_off"):  # eski «faq_entry_toggle» holatni o'zgartirmaydi
            db.set_faq_entry_enabled(owner_id, entry_id, action == "faq_entry_on")
        view = build_faq_entry(owner_id, entry_id)
        if view is None:
            text, markup = build_faq_list(owner_id)
            await query.edit_message_text(f"{t(lang, 'faq_entry_gone')}\n\n{text}", reply_markup=markup)
            return
        await query.edit_message_text(view[0], reply_markup=view[1])
        return

    if data.startswith("faq_edit:"):
        _, _, rest = data.partition(":")
        field, _, raw_id = rest.partition(":")
        entry_id = int(raw_id) if raw_id.isdigit() else -1
        entry = db.get_faq_entry(owner_id, entry_id) if field in ("q", "kw", "ans") else None
        if entry is None:
            text, markup = build_faq_list(owner_id)
            await query.edit_message_text(f"{t(lang, 'faq_entry_gone')}\n\n{text}", reply_markup=markup)
            return
        current = {"q": entry["question"], "kw": ", ".join(entry["keywords"]), "ans": entry["answer"]}[field]
        _faq_edit_target[owner_id] = {"id": entry_id, "ts": time.time()}
        set_pending_action(owner_id, f"faq_edit_{field}")
        await query.message.reply_text(
            t(lang, f"faq_edit_{field}_prompt", cur=current, max=FAQ_MAX_ANSWER if field == "ans" else FAQ_MAX_QUESTION)
        )
        return

    if data == "faq_add":
        limit = faq_limit_for(owner_id)
        if db.count_faq_entries(owner_id) >= limit:
            text, markup = build_faq_menu(owner_id, t(lang, "faq_limit", max=limit))
            await query.edit_message_text(text, reply_markup=markup)
            return
        _faq_drafts[owner_id] = {"ts": time.time(), "id": secrets.token_hex(3)}
        set_pending_action(owner_id, "faq_q")
        await query.message.reply_text(t(lang, "faq_q_prompt"))
        return

    if data.split(":")[0] == "faq_cancel":
        _faq_drafts.pop(owner_id, None)
        text, markup = build_faq_menu(owner_id, t(lang, "faq_cancelled"))
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.split(":")[0] == "faq_save":
        d = _faq_draft(owner_id)
        _faq_drafts.pop(owner_id, None)
        if d is None or not all(k in d for k in ("q", "kw", "ans")):
            text, markup = build_faq_menu(owner_id, t(lang, "faq_draft_lost"))
        elif db.add_faq_entry(owner_id, d["q"], d["kw"], d["ans"], faq_limit_for(owner_id)) is None:
            text, markup = build_faq_menu(owner_id, t(lang, "faq_limit", max=faq_limit_for(owner_id)))
        else:
            text, markup = build_faq_menu(owner_id, t(lang, "faq_saved"))
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith("sc_") and await handle_schedule_callback(query, owner_id, data, lang):
        return

    if data in ("an_menu", "an:1", "an:7", "an:30"):
        text, markup = build_analytics_menu(owner_id, int(data.split(":")[1]) if ":" in data else 1)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith("an_ch:"):
        try:
            days = int(data.split(":")[1])
        except ValueError:
            days = 1
        try:
            if not await send_analytics_charts(context.bot, owner_id, query.message.chat_id, days):
                text, markup = build_locked_view(owner_id, "analytics_30" if days == 30 else "analytics_7")
                await query.edit_message_text(text, reply_markup=markup)
        except Exception:
            logger.exception("Analytics grafigini yuborishda xato (owner=%s)", owner_id)
            await context.bot.send_message(chat_id=query.message.chat_id, text=t(lang, "an_charts_failed"))
        return

    if data.startswith("an_detail:"):
        try:
            days = int(data.split(":")[1])
        except ValueError:
            days = 1
        text, markup = build_analytics_detail(owner_id, days)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "kb_menu":
        _kb_drafts.pop(owner_id, None)
        text, markup = build_kb_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "kb_settings":
        text, markup = build_kb_settings(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data in ("kb_on", "kb_off", "kb_toggle"):
        if data != "kb_toggle":
            db.update_settings(owner_id, kb_enabled=(data == "kb_on"))
        text, markup = build_kb_settings(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "kb_list":
        text, markup = build_kb_list(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith(("kb_view:", "kb_del:", "kb_del_yes:", "kb_entry_toggle:", "kb_entry_on:", "kb_entry_off:")):
        action, _, raw_id = data.partition(":")
        if action == "kb_del_yes":
            raw_id = raw_id.split(":")[0]  # kb_del_yes:ID:TOKEN — ID birinchi qism
        entry_id = int(raw_id) if raw_id.isdigit() else -1
        if action == "kb_del":
            # Tasodifan bosib yuborishdan himoya: avval tasdiqlash so'raladi
            entry = db.get_kb_entry(owner_id, entry_id)
            if entry is None:
                text, markup = build_kb_list(owner_id)
                await query.edit_message_text(f"{t(lang, 'kb_entry_gone')}\n\n{text}", reply_markup=markup)
                return
            token = secrets.token_hex(3)
            _kb_del_confirms[owner_id] = {"entry_id": entry_id, "token": token, "ts": time.time()}
            markup = InlineKeyboardMarkup([[
                InlineKeyboardButton(t(lang, "btn_kb_del_yes"), callback_data=f"kb_del_yes:{entry_id}:{token}"),
                InlineKeyboardButton(t(lang, "btn_kb_cancel"), callback_data=f"kb_view:{entry_id}"),
            ]])
            await query.edit_message_text(t(lang, "kb_del_confirm", title=_faq_short(entry["title"], 80)), reply_markup=markup)
            return
        if action == "kb_del_yes":
            # Eskirgan/soxta tugma yuqorida (stale_draft_button) to'xtatilgan; bu yerga faqat joriy tasdiq yetib keladi.
            _kb_del_confirms.pop(owner_id, None)  # bir martalik
            notice = t(lang, "kb_deleted") if db.delete_kb_entry(owner_id, entry_id) else t(lang, "kb_entry_gone")
            text, markup = build_kb_list(owner_id)
            await query.edit_message_text(f"{notice}\n\n{text}", reply_markup=markup)
            return
        if action in ("kb_entry_on", "kb_entry_off"):  # eski «kb_entry_toggle» holatni o'zgartirmaydi
            db.set_kb_entry_enabled(owner_id, entry_id, action == "kb_entry_on")
        view = build_kb_entry(owner_id, entry_id)
        if view is None:
            text, markup = build_kb_list(owner_id)
            await query.edit_message_text(f"{t(lang, 'kb_entry_gone')}\n\n{text}", reply_markup=markup)
            return
        await query.edit_message_text(view[0], reply_markup=view[1])
        return

    if data.startswith("kb_edit:"):
        _, _, rest = data.partition(":")
        field, _, raw_id = rest.partition(":")
        entry_id = int(raw_id) if raw_id.isdigit() else -1
        entry = db.get_kb_entry(owner_id, entry_id) if field in ("t", "c", "kw") else None
        if entry is None:
            text, markup = build_kb_list(owner_id)
            await query.edit_message_text(f"{t(lang, 'kb_entry_gone')}\n\n{text}", reply_markup=markup)
            return
        current = {"t": entry["title"], "c": entry["content"], "kw": _kb_kw_text(lang, entry["keywords"])}[field]
        _kb_edit_target[owner_id] = {"id": entry_id, "ts": time.time()}
        set_pending_action(owner_id, f"kb_edit_{field}")
        await query.message.reply_text(
            t(lang, f"kb_edit_{field}_prompt", cur=current, max=KB_MAX_CONTENT if field == "c" else KB_MAX_TITLE)
        )
        return

    if data == "kb_add":
        limit = kb_limit_for(owner_id)
        if db.count_kb_entries(owner_id) >= limit:
            text, markup = build_kb_menu(owner_id, t(lang, "kb_limit", max=limit))
            await query.edit_message_text(text, reply_markup=markup)
            return
        _kb_drafts[owner_id] = {"ts": time.time(), "id": secrets.token_hex(3)}
        set_pending_action(owner_id, "kb_title")
        await query.message.reply_text(t(lang, "kb_title_prompt", max=KB_MAX_TITLE))
        return

    if data.split(":")[0] == "kb_cancel":
        _kb_drafts.pop(owner_id, None)
        clear_pending_action(owner_id)
        text, markup = build_kb_menu(owner_id, t(lang, "kb_cancelled"))
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.split(":")[0] == "kb_save":
        d = _kb_draft(owner_id)
        _kb_drafts.pop(owner_id, None)
        clear_pending_action(owner_id)
        if d is None or not all(k in d for k in ("title", "content", "kw")):
            text, markup = build_kb_menu(owner_id, t(lang, "kb_draft_lost"))
        elif db.add_kb_entry(owner_id, d["title"], d["content"], d["kw"], kb_limit_for(owner_id)) is None:
            text, markup = build_kb_menu(owner_id, t(lang, "kb_limit", max=kb_limit_for(owner_id)))
        else:
            text, markup = build_kb_menu(owner_id, t(lang, "kb_saved"))
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "ai_menu":
        text, markup = build_ai_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data in ("ai_on", "ai_off", "ai_toggle"):
        notice = None
        if data == "ai_off":
            db.update_settings(owner_id, ai_enabled=False)
        elif data == "ai_on":
            if not ai.is_configured():
                notice = t(lang, "ai_not_configured")
            else:
                db.update_settings(owner_id, ai_enabled=True)
        # eski «ai_toggle» tugmasi holatni o'zgartirmaydi
        text, markup = build_ai_menu(owner_id, notice)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "ai_roles":
        text, markup = build_ai_roles_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data.startswith("ai_role:"):
        role = data.split(":", 1)[1]
        if role in ai.ROLES:
            db.update_settings(owner_id, ai_role=role)
        text, markup = build_ai_roles_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "ai_edit_info":
        set_pending_action(owner_id, "ai_info")
        await query.message.reply_text(t(lang, "ai_info_prompt", max=AI_INFO_MAX_LENGTH))
        return

    if data == "sleep_menu":
        text, markup = build_sleep_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data in ("sleep_enable", "sleep_disable", "sleep_toggle"):
        # Aniq (idempotent) amallar; eski «sleep_toggle» tugmasi holatni o'zgartirmaydi.
        if data != "sleep_toggle":
            db.update_settings(owner_id, sleep_mode_enabled=(data == "sleep_enable"))
        text, markup = build_sleep_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "sleep_edit_time":
        set_pending_action(owner_id, "sleep_time")
        await query.message.reply_text(t(lang, "sleep_time_prompt"))
        return

    if data == "sleep_edit_text":
        set_pending_action(owner_id, "sleep_text")
        await query.message.reply_text(t(lang, "sleep_text_prompt"))
        return

    text, markup = build_panel(owner_id)
    await query.edit_message_text(text, reply_markup=markup)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    track_user(update.effective_user)

    if owner_id == ADMIN_ID:
        admin_action = get_pending_admin_action(owner_id) or ""
        if admin_action.startswith("feedback_reply:"):
            await send_feedback_reply(update, context, int(admin_action.split(":", 1)[1]))
            return

    action = get_pending_action(owner_id)
    if action is None:
        return  # panelga aloqasi yo'q oddiy xabar

    value = update.message.text.strip()
    lang = get_lang(owner_id)

    gated = {"text": "custom_text", "sleep_text": "custom_text", "birthday_date": "bio", "ai_info": "ai",
             "faq_q": "faq", "faq_kw": "faq", "faq_ans": "faq", "faq_confirm": "faq",
             "faq_edit_q": "faq", "faq_edit_kw": "faq", "faq_edit_ans": "faq",
             "kb_title": "kb", "kb_content": "kb", "kb_kw": "kb", "kb_confirm": "kb",
             "kb_edit_t": "kb", "kb_edit_c": "kb", "kb_edit_kw": "kb", "sc_text": "custom_text"}.get(action)
    if gated and not has_feature(owner_id, gated):
        clear_pending_action(owner_id)
        text, markup = build_locked_view(owner_id, gated)
        await update.message.reply_text(text, reply_markup=markup)
        return

    if action in ("sc_time", "sc_text"):
        await handle_schedule_text(update, owner_id, action, value, lang)
        return

    if action == "feedback":
        if len(value) > FEEDBACK_MAX_LENGTH:
            await update.message.reply_text(t(lang, "feedback_too_long", n=len(value), max=FEEDBACK_MAX_LENGTH))
            return  # amal saqlanadi — foydalanuvchi qisqartirib qayta yuboradi
        clear_pending_action(owner_id)
        reply = await submit_feedback(context.bot, update.effective_user, value)
        await update.message.reply_text(reply)
        return

    if action == "nc_name":
        if not name_clock_allowed(owner_id):
            clear_pending_action(owner_id)
            return
        first, last = split_full_name(value)
        if not first:
            await update.message.reply_text(t(lang, "nc_name_empty"))
            return
        db.update_settings(owner_id, name_clock_first=first, name_clock_last=last, name_clock_applied=None)
        clear_pending_action(owner_id)
        text, markup = build_name_clock_menu(owner_id, t(lang, "saved"))
        await update.message.reply_text(text, reply_markup=markup)
        return

    if action == "ai_info":
        if len(value) > AI_INFO_MAX_LENGTH:
            await update.message.reply_text(t(lang, "ai_info_too_long", n=len(value), max=AI_INFO_MAX_LENGTH))
            return  # amal saqlanadi
        db.update_settings(owner_id, ai_info=None if value == "-" else value)
        clear_pending_action(owner_id)
        text, markup = build_ai_menu(owner_id, t(lang, "saved"))
        await update.message.reply_text(text, reply_markup=markup)
        return

    if action in ("faq_edit_q", "faq_edit_kw", "faq_edit_ans"):
        target = _faq_edit_target.get(owner_id)
        if target is None or time.time() - target["ts"] > PENDING_ACTION_TTL_SECONDS:
            _faq_edit_target.pop(owner_id, None)
            clear_pending_action(owner_id)
            await update.message.reply_text(t(lang, "faq_draft_lost"))
            return
        if not value:
            await update.message.reply_text(t(lang, "faq_empty_text"))
            return
        if action == "faq_edit_kw":
            keywords = parse_faq_keywords(value)
            if keywords is None:
                await update.message.reply_text(t(lang, "faq_kw_bad", max=FAQ_MAX_KEYWORDS, len=FAQ_MAX_KEYWORD_LENGTH))
                return
            changes = {"keywords": keywords}
        else:
            limit_chars = FAQ_MAX_QUESTION if action == "faq_edit_q" else FAQ_MAX_ANSWER
            if len(value) > limit_chars:
                await update.message.reply_text(t(lang, "faq_too_long", n=len(value), max=limit_chars))
                return
            changes = {"question" if action == "faq_edit_q" else "answer": value}
        _faq_edit_target.pop(owner_id, None)
        clear_pending_action(owner_id)
        if not db.update_faq_entry(owner_id, target["id"], **changes):
            text, markup = build_faq_list(owner_id)
            await update.message.reply_text(f"{t(lang, 'faq_entry_gone')}\n\n{text}", reply_markup=markup)
            return
        view = build_faq_entry(owner_id, target["id"], t(lang, "faq_updated"))
        await update.message.reply_text(view[0], reply_markup=view[1])
        return

    if action in ("faq_q", "faq_kw", "faq_ans", "faq_confirm"):
        d = _faq_draft(owner_id)
        if d is None:
            clear_pending_action(owner_id)
            await update.message.reply_text(t(lang, "faq_draft_lost"))
            return
        if action == "faq_confirm":
            await update.message.reply_text(t(lang, "faq_confirm_hint"))
            return  # amal saqlanadi
        if not value:
            await update.message.reply_text(t(lang, "faq_empty_text"))
            return
        if action == "faq_q":
            if len(value) > FAQ_MAX_QUESTION:
                await update.message.reply_text(t(lang, "faq_too_long", n=len(value), max=FAQ_MAX_QUESTION))
                return
            d["q"] = value
            set_pending_action(owner_id, "faq_kw")
            await update.message.reply_text(t(lang, "faq_kw_prompt"))
            return
        if action == "faq_kw":
            keywords = parse_faq_keywords(value)
            if keywords is None:
                await update.message.reply_text(t(lang, "faq_kw_bad", max=FAQ_MAX_KEYWORDS, len=FAQ_MAX_KEYWORD_LENGTH))
                return
            d["kw"] = keywords
            set_pending_action(owner_id, "faq_ans")
            await update.message.reply_text(t(lang, "faq_ans_prompt", max=FAQ_MAX_ANSWER))
            return
        if len(value) > FAQ_MAX_ANSWER:
            await update.message.reply_text(t(lang, "faq_too_long", n=len(value), max=FAQ_MAX_ANSWER))
            return
        d["ans"] = value
        d["ts"] = time.time()
        set_pending_action(owner_id, "faq_confirm")
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "btn_faq_save"), callback_data=f"faq_save:{d['id']}"),
            InlineKeyboardButton(t(lang, "btn_faq_cancel"), callback_data=f"faq_cancel:{d['id']}"),
        ]])
        await update.message.reply_text(
            t(lang, "faq_confirm", q=d["q"], kw=", ".join(d["kw"]), a=value), reply_markup=markup
        )
        return

    if action in ("kb_edit_t", "kb_edit_c", "kb_edit_kw"):
        target = _kb_edit_target.get(owner_id)
        if target is None or time.time() - target["ts"] > PENDING_ACTION_TTL_SECONDS:
            _kb_edit_target.pop(owner_id, None)
            clear_pending_action(owner_id)
            await update.message.reply_text(t(lang, "kb_draft_lost"))
            return
        if not value:
            await update.message.reply_text(t(lang, "kb_empty_text"))
            return
        if action == "kb_edit_kw":
            keywords = parse_kb_keywords(value)
            if keywords is None:
                await update.message.reply_text(t(lang, "kb_kw_bad", max=FAQ_MAX_KEYWORDS, len=FAQ_MAX_KEYWORD_LENGTH))
                return
            changes = {"keywords": keywords}
        else:
            limit_chars = KB_MAX_TITLE if action == "kb_edit_t" else KB_MAX_CONTENT
            if len(value) > limit_chars:
                await update.message.reply_text(t(lang, "kb_too_long", n=len(value), max=limit_chars))
                return
            changes = {"title" if action == "kb_edit_t" else "content": value}
        _kb_edit_target.pop(owner_id, None)
        clear_pending_action(owner_id)
        if not db.update_kb_entry(owner_id, target["id"], **changes):
            text, markup = build_kb_list(owner_id)
            await update.message.reply_text(f"{t(lang, 'kb_entry_gone')}\n\n{text}", reply_markup=markup)
            return
        view = build_kb_entry(owner_id, target["id"], t(lang, "kb_updated"))
        await update.message.reply_text(view[0], reply_markup=view[1])
        return

    if action in ("kb_title", "kb_content", "kb_kw", "kb_confirm"):
        d = _kb_draft(owner_id)
        if d is None:
            clear_pending_action(owner_id)
            await update.message.reply_text(t(lang, "kb_draft_lost"))
            return
        if action == "kb_confirm":
            await update.message.reply_text(t(lang, "kb_confirm_hint"))
            return  # amal saqlanadi
        if not value:
            await update.message.reply_text(t(lang, "kb_empty_text"))
            return
        if action == "kb_title":
            if len(value) > KB_MAX_TITLE:
                await update.message.reply_text(t(lang, "kb_too_long", n=len(value), max=KB_MAX_TITLE))
                return
            d["title"] = value
            set_pending_action(owner_id, "kb_content")
            await update.message.reply_text(t(lang, "kb_content_prompt", max=KB_MAX_CONTENT) + "\n\n" + t(lang, "kb_privacy"))
            return
        if action == "kb_content":
            if len(value) > KB_MAX_CONTENT:
                await update.message.reply_text(t(lang, "kb_too_long", n=len(value), max=KB_MAX_CONTENT))
                return
            d["content"] = value
            set_pending_action(owner_id, "kb_kw")
            await update.message.reply_text(t(lang, "kb_kw_prompt"))
            return
        keywords = parse_kb_keywords(value)
        if keywords is None:
            await update.message.reply_text(t(lang, "kb_kw_bad", max=FAQ_MAX_KEYWORDS, len=FAQ_MAX_KEYWORD_LENGTH))
            return
        d["kw"] = keywords
        d["ts"] = time.time()
        set_pending_action(owner_id, "kb_confirm")
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(t(lang, "btn_kb_save"), callback_data=f"kb_save:{d['id']}"),
            InlineKeyboardButton(t(lang, "btn_kb_cancel"), callback_data=f"kb_cancel:{d['id']}"),
        ]])
        await update.message.reply_text(
            t(lang, "kb_confirm", title=d["title"], content=d["content"], kw=_kb_kw_text(lang, keywords)),
            reply_markup=markup,
        )
        return

    if action in ("text", "sleep_text") and len(value) > AUTO_REPLY_MAX_TEXT:
        # Cheksiz uzun matn panel/uxlash menyusini 4096 belgidan oshirib, menyuni ochib bo'lmas qilardi
        await update.message.reply_text(t(lang, "ai_info_too_long", n=len(value), max=AUTO_REPLY_MAX_TEXT))
        return  # amal saqlanadi — foydalanuvchi qisqartirib qayta yuboradi

    if action == "cooldown":
        hours = parse_cooldown_input(value)
        if hours is None or hours <= 0:
            await update.message.reply_text(t(lang, "cooldown_bad"))
            return
        db.update_settings(owner_id, cooldown_hours=hours)

    elif action == "text":
        db.update_settings(owner_id, auto_reply_text=value)

    elif action == "birthday_date":
        parsed = parse_birthday_input(value)
        if parsed is None:
            await update.message.reply_text(t(lang, "bio_birthday_bad"))
            return
        month, day = parsed
        db.update_settings(owner_id, birthday_month=month, birthday_day=day, bio_countdown_target="birthday")
        ok, info = await apply_bio_update(context.bot, owner_id)
        clear_pending_action(owner_id)
        text, markup = build_bio_menu(owner_id)
        if not ok:
            text += "\n\n" + t(lang, "bio_failed", info=info)
        await update.message.reply_text(t(lang, "saved_plain"))
        await update.message.reply_text(text, reply_markup=markup)
        return

    elif action == "sleep_time":
        parsed = parse_time_range_input(value)
        if parsed is None:
            await update.message.reply_text(t(lang, "sleep_time_bad"))
            return
        start_minutes, end_minutes = parsed
        db.update_settings(owner_id, sleep_start_minutes=start_minutes, sleep_end_minutes=end_minutes)
        clear_pending_action(owner_id)
        text, markup = build_sleep_menu(owner_id)
        await update.message.reply_text(t(lang, "saved_plain"))
        await update.message.reply_text(text, reply_markup=markup)
        return

    elif action == "sleep_text":
        db.update_settings(owner_id, sleep_reply_text=value)
        clear_pending_action(owner_id)
        text, markup = build_sleep_menu(owner_id)
        await update.message.reply_text(t(lang, "saved_plain"))
        await update.message.reply_text(text, reply_markup=markup)
        return

    clear_pending_action(owner_id)
    text, markup = build_panel(owner_id)
    await update.message.reply_text(t(lang, "updated"))
    await update.message.reply_text(text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Admin buyruqlari: /stats va /reklama
# ---------------------------------------------------------------------------
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    count = db.get_user_count()
    blocked = db.count_blocked()
    text = f"\U0001F465 Botdan jami foydalanuvchilar soni: {count}"
    if blocked:
        text += f"\n\U0001F6AB Shundan bloklangan: {blocked}"
    await update.message.reply_text(text)


async def cmd_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    st = db.onboarding_stats()
    await update.message.reply_text(
        "\U0001F4CA Onboarding Statistics\n\n"
        f"\U0001F465 Boshlaganlar: {st['started']}\n"
        f"\U0001F517 Telegram ulaganlar: {st['connected']}\n"
        f"\U0001F4AC Auto-Reply yoqqanlar: {st['auto_reply_on']}\n"
        f"✅ Tugatganlar: {st['completed']}\n"
        f"⏭ O'tkazib yuborganlar: {st['skipped']}\n"
        f"⏳ Jarayonda: {st['in_progress']}"
    )


def _get_running_broadcast_job():
    """Agar hozir allaqachon 'running' holatdagi biror reklama job bo'lsa,
    o'shani qaytaradi (bo'lmasa None). Bir vaqtning o'zida ikkita reklama
    ketib, bir xil xabar ikki marta yuborilib ketmasligi uchun — yangi job
    yaratishdan OLDIN shu tekshiriladi."""
    jobs = db.get_running_broadcast_jobs()
    return jobs[0] if jobs else None


def _running_warning_text(running: dict) -> str:
    return (
        f"\u26A0\uFE0F Hozir allaqachon reklama job#{running['id']} ishlamoqda "
        f"({running['sent_count']}/{running['total_count']} yuborildi).\n"
        "Bir vaqtda ikkita reklama yuborilib, xabar takrorlanib ketmasligi uchun "
        "avval shu tugashini kuting (/reklama_status bilan tekshiring)."
    )


async def _reject_if_broadcast_already_running(reply_target) -> bool:
    """True qaytarsa — demak allaqachon reklama ishlamoqda va chaqiruvchi
    yangi job boshlamasligi kerak (xabar reply_target orqali yuboriladi)."""
    running = _get_running_broadcast_job()
    if running is None:
        return False
    await reply_target.reply_text(_running_warning_text(running))
    return True


async def cmd_reklama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if await _reject_if_broadcast_already_running(update.message):
        return
    # Admin panelda boshqa amal (masalan "fikr yozish") kutayotgan bo'lsa, keyingi xabar ikkalasiga ham ketmasin
    clear_pending_action(update.effective_user.id)
    set_pending_admin_action(update.effective_user.id, "broadcast")
    await update.message.reply_text(
        "Reklama sifatida barcha foydalanuvchilarga yuboriladigan xabarni yuboring "
        "(matn, rasm, video — istalgan turda mumkin). 10 daqiqa ichida yuboring.\n"
        "Yuborishdan oldin sizdan tasdiq so'raladi.\n"
        "Bekor qilish uchun /cancel yozing."
    )


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    cleared_admin = clear_pending_admin_action(owner_id)
    cleared_panel = clear_pending_action(owner_id)
    cleared_scheduler = clear_scheduler_state(owner_id)
    if cleared_admin or cleared_panel or cleared_scheduler:
        await update.message.reply_text(t(get_lang(owner_id), "cancelled"))


async def cmd_reklama_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    job = db.get_latest_broadcast_job()
    if not job:
        await update.message.reply_text("Hali birorta ham reklama yuborilmagan.")
        return
    await update.message.reply_text(
        f"Holat: {job['status']}\n"
        f"Jami: {job['total_count']}\n"
        f"Yuborildi: {job['sent_count']}\n"
        f"Xato: {job['failed_count']}"
    )


async def cmd_reklama_retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oxirgi reklamani qayta urinadi:
    - `failed` (kutilmagan xato bilan to'xtagan) bo'lsa — xuddi shu job'ni
      qolgan joydan (`last_user_id`dan) davom ettiradi.
    - `completed` bo'lsa — faqat individual yuborib bo'linmagan
      foydalanuvchilarga qayta uradi."""
    if update.effective_user.id != ADMIN_ID:
        return
    job = db.get_latest_broadcast_job()
    if not job:
        await update.message.reply_text("Hali birorta ham reklama yuborilmagan.")
        return

    if job["status"] == "failed":
        if await _reject_if_broadcast_already_running(update.message):
            return
        try:
            db.set_broadcast_status(job["id"], "running")
        except db.BroadcastAlreadyRunningError:
            # Baza darajasidagi haqiqiy kafolat: tez-tez tasodifan ikkita
            # so'rov bir-biriga yugurib qolsa ham, bu yerda rad etiladi.
            await update.message.reply_text(
                "\u26A0\uFE0F Boshqa reklama shu orada ishga tushib ulgurdi. /reklama_status bilan tekshiring."
            )
            return
        await update.message.reply_text(
            f"Job#{job['id']} qolgan joydan (user_id > {job['last_user_id']}) davom ettirilmoqda..."
        )
        spawn_background(
            run_broadcast_job(
                context.bot, job["id"], job["source_chat_id"], job["source_message_id"],
                reply_to_chat_id=update.effective_chat.id,
                retry_of_job_id=job.get("retry_of_job_id"),
                start_after_user_id=job["last_user_id"],
            )
        )
        return

    if job["status"] != "completed":
        await update.message.reply_text(
            f"Joriy reklama hali tugamagan (holat: {job['status']}). /reklama_status bilan tekshiring."
        )
        return

    failed_ids = db.get_broadcast_failed_user_ids(job["id"])
    if not failed_ids:
        await update.message.reply_text("Xato bilan yuborilgan foydalanuvchi yo'q.")
        return

    if await _reject_if_broadcast_already_running(update.message):
        return

    try:
        new_job_id = db.create_broadcast_job(
            job["source_chat_id"], job["source_message_id"], len(failed_ids), retry_of_job_id=job["id"]
        )
    except db.BroadcastAlreadyRunningError:
        await update.message.reply_text(
            "\u26A0\uFE0F Boshqa reklama shu orada ishga tushib ulgurdi. /reklama_status bilan tekshiring."
        )
        return

    await update.message.reply_text(f"{len(failed_ids)} ta foydalanuvchiga qayta urinilmoqda...")
    spawn_background(
        run_broadcast_job(
            context.bot, new_job_id, job["source_chat_id"], job["source_message_id"],
            reply_to_chat_id=update.effective_chat.id, retry_of_job_id=job["id"],
        )
    )


async def on_admin_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin /reklama bosgandan keyin yuborgan XOHLAGAN turdagi xabarni ushlaydi,
    lekin darhol YUBORMAYDI: avval "Yuborilsinmi?" deb tasdiq so'raydi. Sabab:
    admin /reklama bosib, keyin fikridan qaytib oddiy xabar yozib yuborsa, u
    tasodifan hammaga ketib qolmasligi kerak. Yuborish tasdiqlash tugmasi
    bosilganda (handle_broadcast_confirmation) boshlanadi."""
    if update.effective_user is None or update.effective_message is None:
        return
    owner_id = update.effective_user.id
    if owner_id != ADMIN_ID or get_pending_admin_action(owner_id) != "broadcast":
        return

    clear_pending_admin_action(owner_id)

    # Tezkor (UX) tekshiruv: allaqachon reklama ketayotgan bo'lsa, tasdiq so'ramaymiz
    if await _reject_if_broadcast_already_running(update.effective_message):
        return

    message = update.effective_message
    total = db.get_user_count(exclude_blocked=True)
    markup = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("\u2705 Yuborish", callback_data=f"bc_confirm:{message.message_id}"),
            InlineKeyboardButton("\u274C Bekor qilish", callback_data="bc_cancel"),
        ]]
    )
    await message.reply_text(
        f"\U0001F4E3 Yuqoridagi xabar {total} ta foydalanuvchiga yuboriladi.\n\n"
        f"Tasdiqlaysizmi? Tugmalar {BROADCAST_CONFIRM_TTL_SECONDS // 60} daqiqa amal qiladi.",
        reply_markup=markup,
    )


BROADCAST_CONFIRM_TTL_SECONDS = 10 * 60


async def start_broadcast(bot, source_chat_id: int, source_message_id: int) -> str:
    """Reklama job'ini yaratib, yuborishni FONDA boshlaydi. Admin uchun natija matnini
    qaytaradi (muvaffaqiyat yoki nima uchun boshlanmagani)."""
    running = _get_running_broadcast_job()
    if running is not None:
        return _running_warning_text(running)

    total = db.get_user_count(exclude_blocked=True)

    # Haqiqiy, atomik kafolat shu yerda: create_broadcast_job() bazadagi partial
    # unique index'ga tiraladi. Ikkita so'rov deyarli bir vaqtda kelib, yuqoridagi
    # tekshiruvning ikkalasi ham "running yo'q" deb ko'rsatib ulgursa ham (klassik
    # TOCTOU poyga holati), faqat BITTASI haqiqatan INSERT qila oladi.
    try:
        job_id = db.create_broadcast_job(source_chat_id, source_message_id, total)
    except db.BroadcastAlreadyRunningError:
        return "\u26A0\uFE0F Boshqa reklama shu orada ishga tushib ulgurdi. /reklama_status bilan tekshiring."

    spawn_background(
        run_broadcast_job(bot, job_id, source_chat_id, source_message_id, reply_to_chat_id=source_chat_id)
    )
    return (
        f"\U0001F4E4 Reklama fonda yuborilmoqda ({total} ta foydalanuvchiga).\n"
        "Progressni /reklama_status bilan tekshirishingiz mumkin."
    )


async def handle_broadcast_confirmation(query, context: ContextTypes.DEFAULT_TYPE, data: str):
    """'bc_confirm:<message_id>' va 'bc_cancel' tugmalari. Har bir shoxda query.answer()
    aniq BIR marta chaqiriladi. Muddat tasdiq xabarining o'z vaqtidan olinadi
    (RAM'da emas), shuning uchun server restart bo'lsa ham to'g'ri ishlaydi."""
    if query.from_user.id != ADMIN_ID:
        await query.answer(t(get_lang(query.from_user.id), "no_permission"), show_alert=True)
        return

    original = getattr(query.message, "text", None) or ""

    async def finish(suffix: str):
        # Xabarni yangilaydi (tugmalar ham yo'qoladi — ikki marta bosib bo'lmaydi)
        try:
            await query.edit_message_text(f"{original}\n\n{suffix}")
        except TelegramError as e:
            logger.info("Tasdiq xabarini yangilab bo'lmadi: %s", e)

    if data == "bc_cancel":
        await query.answer("Bekor qilindi.")
        await finish("\u274C Bekor qilindi. Reklama yuborilmadi.")
        return

    try:
        source_message_id = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        await query.answer("Noto'g'ri tugma.", show_alert=True)
        return

    sent_at = getattr(query.message, "date", None)
    if sent_at is None or time.time() - sent_at.timestamp() > BROADCAST_CONFIRM_TTL_SECONDS:
        await query.answer(
            "Tasdiqlash muddati o'tdi. /reklama bilan qaytadan boshlang.", show_alert=True
        )
        await finish("\u231B Muddati o'tdi. Reklama yuborilmadi.")
        return

    await query.answer()
    result = await start_broadcast(context.bot, query.message.chat_id, source_message_id)
    await finish(result)


async def run_broadcast_job(
    bot,
    job_id: int,
    source_chat_id: int,
    source_message_id: int,
    reply_to_chat_id: int | None = None,
    retry_of_job_id: int | None = None,
    start_after_user_id: int = 0,
):
    """Reklamani bo'lib-bo'lib (keyset pagination), xabarlar orasida kichik
    pauza bilan yuboradi. Har bir urinishdan keyin progress bazaga yoziladi —
    shuning uchun process qayta ishga tushib qolsa ham (Render restart va h.k.),
    keyingi safar shu joydan davom ettirish mumkin (resume_pending_broadcasts).

    `retry_of_job_id` berilsa (masalan /reklama_retry), faqat o'sha job'da
    muvaffaqiyatsiz bo'lgan foydalanuvchilarga yuboriladi — bu cheklov
    `broadcast_jobs.retry_of_job_id` ustunida BAZADA saqlanadi (RAM'da
    emas), shuning uchun server restart bo'lib resume_pending_broadcasts()
    qayta ishga tushirsa ham, retry job hamon faqat o'sha cheklangan
    ro'yxatdan davom etadi, tasodifan BARCHA foydalanuvchiga ketib
    qolmaydi.

    Butun funksiya tashqi try/except bilan o'ralgan: kutilmagan xato
    (masalan baza uzilib qolishi, dastur xatosi) chiqsa ham, job holati
    doim 'running'dan chiqib ketadi ('completed' yoki 'failed') — aks
    holda u abadiy 'running' bo'lib qolib, har restart'da qayta-qayta
    (muvaffaqiyatsiz) urinib, cheksiz tsiklga aylanishi mumkin edi."""
    try:
        sent, failed = await _broadcast_loop(
            bot, job_id, source_chat_id, source_message_id, retry_of_job_id, start_after_user_id
        )
    except Exception as exc:
        logger.exception("Reklama job#%d kutilmagan xato bilan to'xtadi", job_id)
        db.set_broadcast_status(job_id, "failed")
        if reply_to_chat_id is not None:
            if isinstance(exc, BroadcastSourceError):
                message = (
                    f"\u26A0\uFE0F Reklama job#{job_id} to'xtatildi: reklama xabari topilmadi yoki ko'chirib bo'lmaydi "
                    "(o'chirib yuborilgan bo'lishi mumkin).\nYangi xabar bilan qaytadan boshlash uchun /reklama yozing."
                )
            else:
                message = (
                    f"\u26A0\uFE0F Reklama job#{job_id} kutilmagan xato bilan to'xtadi.\n"
                    "Qaytadan boshlash uchun /reklama yozing."
                )
            try:
                await bot.send_message(chat_id=reply_to_chat_id, text=message)
            except TelegramError:
                pass
        return

    db.set_broadcast_status(job_id, "completed")
    logger.info("Reklama job#%d tugadi: %d muvaffaqiyatli, %d xato", job_id, sent, failed)

    if reply_to_chat_id is not None:
        retryable = 0
        if failed:
            try:  # botni bloklaganlar qayta urinishga kirmaydi — maslahat faqat foydasi bo'lsa chiqadi
                retryable = len(db.get_broadcast_failed_user_ids(job_id))
            except Exception:
                logger.exception("Reklama job#%d: qayta uriniladiganlar sonini o'qib bo'lmadi", job_id)
                retryable = failed
        try:
            await bot.send_message(
                chat_id=reply_to_chat_id,
                text=(
                    f"\u2705 Reklama tugadi (job#{job_id}).\n"
                    f"Muvaffaqiyatli: {sent}\nYuborib bo'lmadi: {failed}"
                    + (f"\n(shundan {failed - retryable} tasi botni bloklagan/akkaunti o'chgan)" if failed and retryable < failed else "")
                    + ("\nQayta urinish uchun: /reklama_retry" if retryable else "")
                ),
            )
        except TelegramError:
            pass


class BroadcastSourceError(Exception):
    """Reklama qilinayotgan xabarning o'zi Telegramda topilmadi (masalan admin o'chirib yuborgan)."""


BROADCAST_MAX_SOURCE_ERRORS = 5
_SOURCE_ERROR_MARKERS = ("message to copy not found", "message_id_invalid", "message can't be copied", "message not found")


def _is_broadcast_source_error(e: Exception) -> bool:
    """copy_message xatosi foydalanuvchiga emas, reklama xabarining o'ziga tegishlimi."""
    text = str(e).lower()
    return any(marker in text for marker in _SOURCE_ERROR_MARKERS)


async def _broadcast_loop(
    bot,
    job_id: int,
    source_chat_id: int,
    source_message_id: int,
    retry_of_job_id: int | None,
    start_after_user_id: int,
) -> tuple[int, int]:
    """Haqiqiy yuborish tsikli. Kutilmagan xatoni ushlamaydi — ularni
    chaqiruvchi (`run_broadcast_job`) ushlab, job holatini belgilaydi.

    YETKAZISH KAFOLATI: "kamida bir marta" (at-least-once), "aynan bir marta"
    (exactly-once) EMAS — Telegram copy_message uchun idempotency kaliti
    bermaydi, shuning uchun bu texnik jihatdan to'liq mumkin emas. Progress
    har bir foydalanuvchidan KEYIN yoziladi, demak yuborish va DB yozuvi
    orasida process o'lib qolsa, restartdan keyin AYNAN SHU BITTA foydalanuvchi
    xabarni ikkinchi marta olishi mumkin (har bir crash uchun ko'pi bilan 1 ta).
    Shunga o'xshash noaniqlik: TimedOut/NetworkError xatosida xabar aslida
    yetib borgan bo'lishi mumkin, lekin "xato" deb yoziladi va /reklama_retry
    uni qayta yuboradi. Tanlov ataylab shunday: foydalanuvchi reklamani
    umuman olmay qolishidan ko'ra, kamdan-kam holatda ikki marta olgani yaxshiroq."""
    logger.info("Reklama job#%d boshlandi (last_user_id=%d)", job_id, start_after_user_id)
    sent, failed = 0, 0
    source_errors = 0  # ketma-ket "xabar topilmadi" xatolari
    last_user_id = start_after_user_id

    while True:
        if retry_of_job_id is not None:
            batch = db.get_failed_user_ids_after(retry_of_job_id, last_user_id, limit=200)
        else:
            batch = db.get_user_ids_after(last_user_id, limit=200)
        if not batch:
            break

        for user_id in batch:
            last_user_id = max(last_user_id, user_id)

            if user_id == ADMIN_ID:
                continue

            sent_delta, failed_delta = 0, 0

            try:
                await bot.copy_message(
                    chat_id=user_id, from_chat_id=source_chat_id, message_id=source_message_id
                )
                sent += 1
                sent_delta = 1
            except RetryAfter as e:
                # Telegram "shuncha soniya kut" desa — kutib, shu foydalanuvchiga qayta urinamiz
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await bot.copy_message(
                        chat_id=user_id, from_chat_id=source_chat_id, message_id=source_message_id
                    )
                    sent += 1
                    sent_delta = 1
                except TelegramError as e2:
                    failed += 1
                    failed_delta = 1
                    db.record_broadcast_failure(job_id, user_id, str(e2))
            except Forbidden:
                # Foydalanuvchi botni bloklagan/o'chirgan — kutilgan holat
                failed += 1
                failed_delta = 1
                db.record_broadcast_failure(job_id, user_id, db.NON_RETRYABLE_FAILURE)
            except TelegramError as e:
                failed += 1
                failed_delta = 1
                db.record_broadcast_failure(job_id, user_id, str(e))
                if isinstance(e, BadRequest) and _is_broadcast_source_error(e):
                    source_errors += 1
                else:
                    source_errors = 0
            else:
                source_errors = 0

            db.update_broadcast_progress(job_id, last_user_id, sent_delta=sent_delta, failed_delta=failed_delta)
            await asyncio.sleep(0.05)  # ~20 xabar/soniya — Telegram limitidan pastroq

            if source_errors >= BROADCAST_MAX_SOURCE_ERRORS:
                # Reklama xabarining o'zi yo'q (admin o'chirib yuborgan): hammaga "xato" yozib, ishni
                # "tugadi" deb ko'rsatish o'rniga to'xtatamiz — admin aniq sababni bilsin.
                raise BroadcastSourceError("reklama xabari topilmadi yoki ko'chirib bo'lmaydi")

    return sent, failed


async def resume_pending_broadcasts(app: Application):
    """Server qayta ishga tushganda, oldin 'running' holatda qolib ketgan
    reklama job'larini (masalan restart tufayli yarim qolgan) davom ettiradi."""
    jobs = db.get_running_broadcast_jobs()
    for job in jobs:
        logger.info("Tugallanmagan reklama job#%d topildi — davom ettirilmoqda", job["id"])
        spawn_background(
            run_broadcast_job(
                app.bot,
                job["id"],
                job["source_chat_id"],
                job["source_message_id"],
                reply_to_chat_id=job["source_chat_id"],
                retry_of_job_id=job.get("retry_of_job_id"),
                start_after_user_id=job["last_user_id"],
            )
        )


async def _resume_broadcasts_job_callback(context: ContextTypes.DEFAULT_TYPE):
    """job_queue.run_once uchun to'g'ri (async) shakldagi wrapper."""
    await resume_pending_broadcasts(context.application)




# ---------------------------------------------------------------------------
# Admin: foydalanuvchini bloklash (/block, /unblock, /blocked) va apellyatsiya
# ---------------------------------------------------------------------------
BLOCK_REASON_MAX_LENGTH = 300
APPEAL_MAX_LENGTH = 1000
APPEAL_MAX_PER_DAY = 3
APPEAL_PENDING_TTL_SECONDS = 15 * 60
BLOCK_NOTICE_COOLDOWN_SECONDS = 60

# user_id -> izoh yozish boshlangan vaqt (bloklangan odam "Izoh qoldirish"ni bosgan)
pending_appeal: dict[int, float] = {}
# user_id -> oxirgi marta "Siz bloklangansiz" deb javob berilgan vaqt (bot spamga aylanmasligi uchun)
_last_block_notice: dict[int, float] = {}

_USERNAME_RE = re.compile(r"^@?([A-Za-z][A-Za-z0-9_]{3,31})$")


def format_user_label(user_id: int, username: str | None = None, full_name: str | None = None) -> str:
    names = " / ".join(x for x in (f"@{username}" if username else None, full_name) if x)
    return f"{names} (ID {user_id})" if names else f"ID {user_id}"


def _label_for(user_id: int) -> str:
    info = db.get_user(user_id) or {}
    return format_user_label(user_id, info.get("username"), info.get("full_name"))


async def _try_send(bot, chat_id: int, text: str, reply_markup=None) -> bool:
    try:
        await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        return True
    except TelegramError as e:
        logger.info("Xabar yuborilmadi (chat=%s): %s", chat_id, e)
        return False


async def resolve_target_user(bot, raw: str) -> tuple[int | None, str | None]:
    """'@username' yoki raqamli ID'dan user_id topadi. (user_id, None) yoki (None, xato_matni)."""
    raw = raw.strip()
    if re.fullmatch(r"[0-9]{1,15}", raw):  # ASCII raqamlar, real ID uzunligi (isdigit() "²" kabilarni ham o'tkazardi)
        user_id = int(raw)
        if user_id <= 0:
            return None, "Noto'g'ri ID."
        return user_id, None

    match = _USERNAME_RE.match(raw)
    if not match:
        return None, "Noto'g'ri format. @username yoki raqamli ID yuboring."
    username = match.group(1)

    user_id = db.get_user_id_by_username(username)
    if user_id is not None:
        return user_id, None

    # Eski foydalanuvchilarning username'i hali bazada bo'lmasligi mumkin (username
    # saqlash keyinroq qo'shilgan) — ularni Telegramdan to'ldirib, qayta qidiramiz.
    try:
        if db.get_users_needing_info(1, time.time() - PROFILE_RETRY_AFTER_SECONDS):
            await backfill_profiles(bot, max_users=RESOLVE_BACKFILL_LIMIT)
            user_id = db.get_user_id_by_username(username)
            if user_id is not None:
                return user_id, None
    except Exception:
        logger.exception("Username qidiruvida profillarni to'ldirish xatosi")

    # Bazada yo'q — Telegramning o'zidan so'rab ko'ramiz (har doim ham ishlamaydi)
    try:
        chat = await bot.get_chat(f"@{username}")
    except TelegramError:
        chat = None
    if chat is not None and getattr(chat, "type", None) == "private":
        return chat.id, None
    return None, (
        f"@{username} topilmadi. Bu odam botga hali yozmagan bo'lishi mumkin — "
        "raqamli ID'si bilan bloklang: /block 123456789 [sabab]"
    )


def build_block_notice(reason: str, lang: str = DEFAULT_LANG):
    reason_line = t(lang, "block_reason_line", reason=reason) if reason else ""
    text = t(lang, "block_notice", reason_line=reason_line)
    markup = InlineKeyboardMarkup([[InlineKeyboardButton(t(lang, "btn_appeal"), callback_data="appeal_start")]])
    return text, markup


async def cmd_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text(
            "Foydalanish:\n/block @username [sabab]\n/block 123456789 [sabab]"
        )
        return

    target_id, error = await resolve_target_user(context.bot, context.args[0])
    if target_id is None:
        await update.message.reply_text(error)
        return
    if target_id == ADMIN_ID:
        await update.message.reply_text("O'zingizni bloklab bo'lmaydi.")
        return

    reason = " ".join(context.args[1:]).strip()[:BLOCK_REASON_MAX_LENGTH]
    label = _label_for(target_id)

    if not db.block_user(target_id, reason, update.effective_user.id):
        await update.message.reply_text(
            f"{label} allaqachon bloklangan. Blokdan chiqarish: /unblock {context.args[0]}"
        )
        return

    # Eski, tugallanmagan panel amallari qolib ketmasligi uchun
    clear_pending_action(target_id)
    pending_appeal.pop(target_id, None)
    _last_block_notice.pop(target_id, None)

    text, markup = build_block_notice(reason, get_lang(target_id))
    notified = await _try_send(context.bot, target_id, text, markup)
    await update.message.reply_text(
        f"\U0001F6AB {label} bloklandi.\n"
        f"Sabab: {reason or '—'}\n"
        + (
            "Foydalanuvchiga xabar yuborildi."
            if notified
            else "Foydalanuvchiga xabar yuborib bo'lmadi (u botga yozmagan yoki botni to'xtatgan). "
            "Baribir bloklangan: u botga yozganda bloklanganini ko'radi."
        )
    )


async def do_unblock(bot, target_id: int) -> bool:
    """Blokdan chiqaradi va foydalanuvchiga xabar beradi. True — haqiqatan chiqarildi."""
    changed = db.unblock_user(target_id)
    pending_appeal.pop(target_id, None)
    _last_block_notice.pop(target_id, None)
    if changed:
        await _try_send(bot, target_id, t(get_lang(target_id), "unblocked_user"))
    return changed


async def cmd_setplan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: to'lovni tasdiqlagach tarifni belgilaydi. Muddat berilsa (1oy, 30kun, 2hafta, 1yil),
    tugagach foydalanuvchi avtomatik Bepul tarifga qaytadi; berilmasa — muddatsiz."""
    if update.effective_user.id != ADMIN_ID:
        return
    args = context.args or []
    usage = (
        "Foydalanish:\n/setplan @username plus 1oy\n/setplan 123456789 pro 30kun\n/setplan @username ultra\n"
        "Tariflar: " + ", ".join(PLAN_KEYS) + "\nMuddat: 1oy, 3oy, 2hafta, 30kun, 1yil (yozilmasa — muddatsiz)"
    )
    if len(args) not in (2, 3) or args[1].lower() not in PLAN_KEYS:
        await update.message.reply_text(usage)
        return
    plan = args[1].lower()
    expires_at = None
    if len(args) == 3:
        duration = parse_plan_duration(args[2])
        if duration is None:
            await update.message.reply_text("Muddat noto'g'ri.\n\n" + usage)
            return
        if plan == "free":
            await update.message.reply_text("Bepul tarifga muddat berilmaydi.")
            return
        expires_at = add_plan_duration(time.time(), duration[0], duration[1], TASHKENT_TZ)
    target_id, error = await resolve_target_user(context.bot, args[0])
    if target_id is None:
        await update.message.reply_text(error)
        return
    db.set_user_plan(target_id, plan, expires_at)
    label = _label_for(target_id)
    lang = get_lang(target_id)
    name = t(lang, "plan_name_" + plan)
    if expires_at:
        message = t(lang, "plan_activated_until", name=name, date=format_plan_date(expires_at))
    else:
        message = t(lang, "plan_activated", name=name)
    notified = await _try_send(context.bot, target_id, message)
    until = f" ({format_plan_date(expires_at)} gacha)" if expires_at else " (muddatsiz)" if plan != "free" else ""
    await update.message.reply_text(
        f"\u2705 {label} tarifi: {plan}{until}." + ("" if notified else "\nFoydalanuvchiga xabar yuborib bo'lmadi.")
    )


async def plan_expiry_job(context: ContextTypes.DEFAULT_TYPE):
    """Muddati tugagan tariflarni Bepulga qaytaradi va foydalanuvchilarga xabar beradi."""
    try:
        expired = db.expire_plans()
    except Exception:
        logger.exception("Tarif muddatini tekshirishda xato")
        return
    for user_id, old_plan in expired:
        lang = get_lang(user_id)
        await _try_send(context.bot, user_id, t(lang, "plan_expired", name=t(lang, "plan_name_" + old_plan)))
    if expired:
        logger.info("Tarif muddati tugadi: %d foydalanuvchi bepulga qaytdi", len(expired))


async def cmd_unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Foydalanish:\n/unblock @username\n/unblock 123456789")
        return
    target_id, error = await resolve_target_user(context.bot, context.args[0])
    if target_id is None:
        await update.message.reply_text(error)
        return
    label = _label_for(target_id)
    if await do_unblock(context.bot, target_id):
        await update.message.reply_text(f"\u2705 {label} blokdan chiqarildi va unga xabar yuborildi.")
    else:
        await update.message.reply_text(f"{label} bloklanmagan.")


# --------------------------------------------------------------------------
# /users — botga start bosgan barcha foydalanuvchilar + eski foydalanuvchilarning
# username/ismini Telegramdan to'ldirish
# --------------------------------------------------------------------------
USERS_PAGE_SIZE = 15
USER_NAME_MAX_LENGTH = 30
PROFILE_BACKFILL_BATCH = 100
PROFILE_RETRY_AFTER_SECONDS = 7 * 24 * 3600
RESOLVE_BACKFILL_LIMIT = 300
_profile_backfill_running = False


async def _refresh_profile(bot, user_id: int) -> bool:
    """Bitta foydalanuvchining ism/username'ini Telegramdan olib saqlaydi.
    True — Telegram javob berdi. Foydalanuvchi botni bloklagan/akkaunti o'chgan
    bo'lsa ham "tekshirildi" deb belgilanadi (har restartda qayta urinmaslik uchun)."""
    for attempt in range(2):
        try:
            chat = await bot.get_chat(user_id)
        except RetryAfter as e:
            if attempt == 0:
                await asyncio.sleep(min(float(e.retry_after) + 1, 30))
                continue
            return False
        except (Forbidden, BadRequest):
            db.mark_user_info_checked(user_id)
            return False
        except TelegramError as e:
            logger.info("Profil olinmadi (user=%s): %s", user_id, e)
            return False
        db.set_user_info(user_id, getattr(chat, "username", None), getattr(chat, "full_name", None))
        return True
    return False


async def backfill_profiles(bot, max_users: int | None = None) -> tuple[int, int]:
    """Ismi noma'lum eski foydalanuvchilarni Telegramdan to'ldiradi.
    (urinilgan, muvaffaqiyatli) qaytaradi. Bir vaqtda faqat bitta ishlaydi."""
    global _profile_backfill_running
    if _profile_backfill_running:
        return 0, 0
    _profile_backfill_running = True
    tried = ok = 0
    try:
        while max_users is None or tried < max_users:
            limit = PROFILE_BACKFILL_BATCH if max_users is None else min(PROFILE_BACKFILL_BATCH, max_users - tried)
            ids = db.get_users_needing_info(limit, time.time() - PROFILE_RETRY_AFTER_SECONDS)
            if not ids:
                break
            for uid in ids:
                tried += 1
                try:
                    refreshed = await _refresh_profile(bot, uid)
                except Exception:
                    # Bitta foydalanuvchidagi kutilmagan xato butun to'ldirishni to'xtatmasin
                    logger.exception("Profilni yangilashda xato (user=%s)", uid)
                    refreshed = False
                if refreshed:
                    ok += 1
                else:
                    # Vaqtinchalik xato bo'lsa ham shu ishga tushirishda qayta aylanib
                    # qolmasligi uchun belgilab qo'yamiz (keyingi urinish — 7 kundan keyin)
                    db.mark_user_info_checked(uid)
                await asyncio.sleep(0.05)
    finally:
        _profile_backfill_running = False
    if tried:
        logger.info("Profillar to'ldirildi: %s urinish, %s muvaffaqiyatli", tried, ok)
    return tried, ok


async def profile_backfill_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await backfill_profiles(context.bot)
    except Exception:
        logger.exception("Profillarni to'ldirish xatosi")


def split_for_telegram(text: str, limit: int = 4000) -> list[str]:
    """Uzun matnni qator chegarasida `limit` belgidan oshmaydigan bo'laklarga ajratadi (Telegram limiti 4096)."""
    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:  # bitta qatorning o'zi limitdan uzun bo'lsa — qattiq kesamiz
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else current + "\n" + line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current or not chunks:
        chunks.append(current)
    return chunks


def _short(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= USER_NAME_MAX_LENGTH else text[: USER_NAME_MAX_LENGTH - 1] + "…"


def build_users_view(page: int, total: int, blocked_total: int, rows: list, pending: int = 0):
    pages = max(1, -(-total // USERS_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    start = page * USERS_PAGE_SIZE
    lines = [
        f"\U0001F465 <b>Foydalanuvchilar</b>: {total} ta"
        + (f" (\U0001F6AB bloklangan: {blocked_total})" if blocked_total else ""),
        f"Sahifa {page + 1}/{pages} — eng yangilari birinchi",
        "",
    ]
    if not rows:
        lines.append("Hozircha hech kim yo'q.")
    for i, row in enumerate(rows, start + 1):
        names = " / ".join(
            x
            for x in (
                f"@{html.escape(row['username'])}" if row.get("username") else None,
                html.escape(_short(row.get("full_name"))) if row.get("full_name") else None,
            )
            if x
        ) or "<i>ism noma'lum</i>"
        when = (
            datetime.fromtimestamp(row["first_seen"], TASHKENT_TZ).strftime("%d.%m.%Y")
            if row.get("first_seen")
            else "?"
        )
        mark = "\U0001F6AB " if row.get("is_blocked") else ""
        lines.append(f"{i}. {mark}{names} — <code>{row['user_id']}</code> — {when}")
    if pending:
        lines.append(f"\n⏳ {pending} ta eski foydalanuvchining ismi/username'i yangilanmoqda — birozdan keyin sahifani qayta oching.")
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Oldingi", callback_data=f"users:{page - 1}"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("Keyingi ➡️", callback_data=f"users:{page + 1}"))
    markup = InlineKeyboardMarkup([nav]) if nav else None
    return "\n".join(lines), markup


def render_users_page(bot, page: int):
    total = db.get_user_count()
    pages = max(1, -(-total // USERS_PAGE_SIZE))
    page = min(max(page, 0), pages - 1)
    rows = db.get_users_page(page * USERS_PAGE_SIZE, USERS_PAGE_SIZE)
    pending = len(db.get_users_needing_info(1000, time.time() - PROFILE_RETRY_AFTER_SECONDS))
    if pending and not _profile_backfill_running:
        spawn_background(backfill_profiles(bot))
    return build_users_view(page, total, db.count_blocked(), rows, pending)


async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text, markup = render_users_page(context.bot, 0)
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)


async def handle_users_page(query, context: ContextTypes.DEFAULT_TYPE, data: str):
    if query.from_user.id != ADMIN_ID:
        await query.answer(t(get_lang(query.from_user.id), "no_permission"), show_alert=True)
        return
    await query.answer()
    try:
        page = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        page = 0
    text, markup = render_users_page(context.bot, page)
    try:
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=markup)
    except TelegramError as e:
        logger.info("/users sahifasi yangilanmadi: %s", e)


BOTS_LIST_LIMIT = 30  # xabar 4096 belgidan oshmasligi uchun
BOTS_CONFIRM_TTL_SECONDS = 15 * 60
_bots_listed: dict[int, tuple[list[int], float]] = {}  # admin_id -> (ko'rsatilgan user_id'lar, vaqt)


async def cmd_bots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    rows = db.list_bot_like_users(BOTS_LIST_LIMIT)
    if not rows:
        await update.message.reply_text("Bazada bot-ga o'xshash yozuv topilmadi.")
        return
    lines = [
        f"{i}. {format_user_label(r['user_id'], r.get('username'), _short(r.get('full_name')))}"
        for i, r in enumerate(rows, 1)
    ]
    # Faqat admin KO'RGAN ro'yxat o'chiriladi: bazada ko'proq mos yozuv bo'lsa ham, ko'rilmaganlarga tegilmaydi
    _bots_listed[update.effective_user.id] = ([r["user_id"] for r in rows], time.time())
    text = (
        f"\U0001F916 Username'i \"bot\" bilan tugaydigan yozuvlar ({len(rows)} ta):\n\n"
        + "\n".join(lines)
        + "\n\nBular bazadan o'chirilsinmi? (Odam ham username'ini shunday qo'ygan bo'lishi mumkin — ro'yxatni tekshiring.)"
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\U0001F5D1 Hammasini o'chirish", callback_data="rmbots:yes"),
          InlineKeyboardButton("Bekor qilish", callback_data="rmbots:no")]]
    )
    await update.message.reply_text(text[:4096], reply_markup=markup)


async def handle_rmbots(query, context: ContextTypes.DEFAULT_TYPE, data: str):
    if query.from_user.id != ADMIN_ID:
        await query.answer(t(get_lang(query.from_user.id), "no_permission"), show_alert=True)
        return
    if data == "rmbots:yes":
        listed = _bots_listed.pop(query.from_user.id, None)
        if listed is None or time.time() - listed[1] > BOTS_CONFIRM_TTL_SECONDS:
            # Ro'yxat eskirgan yoki bot qayta ishga tushgan: nima o'chirilishini admin ko'rmagan — o'chirmaymiz
            await query.answer("Ro'yxat eskirgan. /bots ni qaytadan yuboring.", show_alert=True)
            result = "Ro'yxat eskirgan. Qaytadan /bots yuboring."
        else:
            count = db.delete_bot_like_users(listed[0])
            await query.answer(f"{count} ta yozuv o'chirildi.", show_alert=True)
            result = f"✅ {count} ta bot yozuvi bazadan o'chirildi."
    else:
        await query.answer()
        result = "Bekor qilindi."
    try:
        await query.edit_message_text(result)
    except TelegramError as e:
        logger.info("/bots xabari yangilanmadi: %s", e)


async def on_other_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matnsiz xabar (rasm, sticker, ...) yozib ketgan odam ham ro'yxatga tushsin."""
    track_user(update.effective_user)


async def cmd_blocked(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    limit = 30
    rows = db.list_blocked(limit)
    if not rows:
        await update.message.reply_text("Bloklangan foydalanuvchi yo'q.")
        return
    total = db.count_blocked()
    lines = []
    for i, row in enumerate(rows, 1):
        when = datetime.fromtimestamp(row["blocked_at"], TASHKENT_TZ).strftime("%d.%m.%Y") if row.get("blocked_at") else "?"
        label = format_user_label(row["user_id"], row.get("username"), row.get("full_name"))
        reason = " ".join((row.get("reason") or "").split()) or "sababsiz"
        if len(reason) > 100:
            reason = reason[:99] + "…"
        lines.append(f"{i}. {label} — {reason} ({when})")
    text = f"\U0001F6AB Bloklanganlar ({total} ta):\n\n" + "\n".join(lines)
    if total > len(rows):
        text += f"\n\n... va yana {total - len(rows)} ta (eng oxirgi {limit} tasi ko'rsatildi)"
    # Sabablar uzun bo'lsa matn 4096 belgidan oshib, buyruq javobsiz qolardi — bo'lib yuboramiz
    for chunk in split_for_telegram(text):
        await update.message.reply_text(chunk)


async def _begin_appeal(bot, user_id: int):
    """Bloklangan foydalanuvchi "Izoh qoldirish"ni bosdi."""
    lang = get_lang(user_id)
    used = db.count_recent_appeals(user_id, time.time() - 24 * 3600)
    if used >= APPEAL_MAX_PER_DAY:
        await _try_send(bot, user_id, t(lang, "appeal_limit", used=used))
        return
    started = pending_appeal.get(user_id)
    if started is not None and time.time() - started < APPEAL_PENDING_TTL_SECONDS:
        return  # so'rov allaqachon yuborilgan va kutilmoqda — tugmani qayta bosib spam qilib bo'lmaydi
    pending_appeal[user_id] = time.time()
    await _try_send(bot, user_id, t(lang, "appeal_prompt", max=APPEAL_MAX_LENGTH))


async def _submit_appeal(bot, user, block: dict, text: str):
    """Izohni adminga yuboradi (blokdan chiqarish tugmasi bilan) va foydalanuvchiga tasdiq beradi."""
    label = format_user_label(user.id, user.username, user.full_name)
    admin_text = (
        "\U0001F4E9 Bloklangan foydalanuvchidan izoh\n\n"
        f"Kimdan: {label}\n"
        f"Bloklash sababi: {block.get('reason') or '—'}\n\n"
        f"Izoh:\n{text}"
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u2705 Blokdan chiqarish", callback_data=f"unblock:{user.id}")]]
    )
    delivered = bool(ADMIN_ID) and await _try_send(bot, ADMIN_ID, admin_text, markup)
    lang = get_lang(user.id)
    if not delivered:
        await _try_send(bot, user.id, t(lang, "appeal_fail"))
        return
    db.add_appeal(user.id, text)
    pending_appeal.pop(user.id, None)
    await _try_send(bot, user.id, t(lang, "appeal_sent"))


async def handle_blocked_update(update: Update, context: ContextTypes.DEFAULT_TYPE, block: dict):
    user = update.effective_user
    now = time.time()
    query = update.callback_query
    lang = get_lang(user.id)

    if query is not None:
        if query.data == "appeal_start":
            await query.answer()
            await _begin_appeal(context.bot, user.id)
        else:
            await query.answer(t(lang, "blocked_alert"), show_alert=True)
        return

    message = update.message
    text = (message.text or "").strip()

    started = pending_appeal.get(user.id)
    if started is not None and now - started > APPEAL_PENDING_TTL_SECONDS:
        pending_appeal.pop(user.id, None)
        started = None

    if started is not None:
        if text.startswith("/cancel"):
            pending_appeal.pop(user.id, None)
            await message.reply_text(t(lang, "cancelled"))
            return
        if text and not text.startswith("/"):
            if len(text) > APPEAL_MAX_LENGTH:
                await message.reply_text(t(lang, "appeal_too_long", n=len(text), max=APPEAL_MAX_LENGTH))
                return
            await _submit_appeal(context.bot, user, block, text)
            return

    # Oddiy xabar/buyruq: bloklangani haqida eslatma (bot spamga aylanmasligi uchun
    # bir foydalanuvchiga daqiqada ko'pi bilan bitta)
    if now - _last_block_notice.get(user.id, 0.0) < BLOCK_NOTICE_COOLDOWN_SECONDS:
        return
    _last_block_notice[user.id] = now
    notice, markup = build_block_notice(block.get("reason") or "", lang)
    await message.reply_text(notice, reply_markup=markup)


async def subscribe_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botning HAR BIR xabari/tugmasi uchun majburiy obuna. Obuna bo'lmaganda faqat
    /start, til tanlash va "Tekshirish" tugmasi ishlaydi; qolganlari to'xtatiladi."""
    if REQUIRED_CHANNEL_ID is None:
        return
    query = update.callback_query
    message = update.message
    if query is None and message is None:
        return
    user = update.effective_user
    chat = update.effective_chat
    if user is None or user.is_bot or _sub_exempt(user.id) or (chat is not None and chat.type != "private"):
        return
    if query is not None:
        data = query.data or ""
        if data.startswith("check_subscription") or data.startswith("lang:"):
            return
    else:
        text = (message.text or "").strip()
        if text.split("@", 1)[0].split(" ", 1)[0] == "/start":
            return
    if await is_subscribed_cached(context.bot, user.id):
        return
    lang = get_lang(user.id)
    markup = build_subscribe_gate_markup(None, lang)
    if query is not None:
        try:
            await query.answer(t(lang, "gate_fail"), show_alert=True)
            await query.edit_message_text(t(lang, "gate_text"), reply_markup=markup)
        except TelegramError as e:
            logger.info("Obuna oynasini ko'rsatib bo'lmadi (user=%s): %s", user.id, e)
    else:
        now = time.time()
        if now - _gate_reply_at.get(user.id, 0.0) >= GATE_REPLY_COOLDOWN_SECONDS:
            _gate_reply_at[user.id] = now
            await message.reply_text(t(lang, "gate_text"), reply_markup=markup)
    raise ApplicationHandlerStop


async def block_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Eng birinchi (group -2) handler: bot bilan to'g'ridan-to'g'ri muloqot
    (xabar yoki tugma) qilayotgan bloklangan foydalanuvchini ushlab qoladi va
    boshqa hech bir handlerga o'tkazmaydi. business_message (mijozlarning
    xabarlari) bu yerda e'tiborga olinmaydi — ular bot foydalanuvchisi emas."""
    if update.message is None and update.callback_query is None:
        return
    user = update.effective_user
    if user is None or user.id == ADMIN_ID:
        return
    block = db.get_block(user.id)
    if block is None:
        return
    await handle_blocked_update(update, context, block)
    raise ApplicationHandlerStop


# ---------------------------------------------------------------------------
# Business connection va business message (asosiy avtojavob logikasi)
# ---------------------------------------------------------------------------
async def on_raw_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Diagnostika: kanaldan post kelsa, aniq chat_id'ni to'g'ridan-to'g'ri
    # adminga DM qilib yuboradi — REQUIRED_CHANNEL_ID'ni to'g'ri topish uchun
    # eng ishonchli usul (userinfobot ba'zan noto'g'ri/eski ID berishi mumkin).
    if update.channel_post and ADMIN_ID:
        chat = update.channel_post.chat
        logger.info("channel_post: chat_id=%s title=%r", chat.id, chat.title)
        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"\U0001F4E1 Kanal post aniqlandi:\nNomi: {chat.title}\nID: `{chat.id}`",
                parse_mode="Markdown",
            )
        except TelegramError:
            pass

    # Ulanish/uzilish/huquq o'zgarishi
    if update.business_connection:
        conn = update.business_connection

        can_reply = getattr(conn, "can_reply", None)
        rights = getattr(conn, "rights", None)
        if can_reply is None and rights is not None:
            can_reply = bool(getattr(rights, "can_reply", False))
        if can_reply is None:
            # Fail-closed: ruxsatni aniqlab bo'lmasa, "yo'q" deb hisoblaymiz —
            # aks holda (fail-open, True) Telegram API javobi kutilmagan
            # shaklda kelgan holatda ham botga xabar yuborish huquqi
            # "sukut bo'yicha" berilib qolishi mumkin edi.
            logger.warning(
                "can_reply aniqlanmadi (owner=%s) — xavfsizlik uchun False deb qabul qilinmoqda",
                conn.user.id,
            )
            can_reply = False

        can_edit_bio = bool(getattr(rights, "can_edit_bio", False)) if rights is not None else False
        can_edit_name = bool(getattr(rights, "can_edit_name", False)) if rights is not None else False

        db.upsert_connection(
            owner_user_id=conn.user.id,
            business_connection_id=conn.id,
            can_reply=can_reply,
            is_enabled=conn.is_enabled,
            can_edit_bio=can_edit_bio,
            can_edit_name=can_edit_name,
        )
        if not conn.is_enabled or not can_edit_name:
            # Akkaunt uzildi yoki ism ruxsati olindi — soat endi ishlay olmaydi
            try:
                if db.get_settings(conn.user.id).get("name_clock_enabled"):
                    db.update_settings(conn.user.id, name_clock_enabled=False)
                    await _try_send(context.bot, conn.user_chat_id, t(get_lang(conn.user.id), "nc_rights_lost"))
            except Exception:
                logger.exception("Ism soatini o'chirishda xato (owner=%s)", conn.user.id)
        logger.info(
            "business account %s (owner=%s, can_reply=%s, can_edit_bio=%s)",
            "connected" if conn.is_enabled else "disconnected",
            conn.user.id,
            can_reply,
            can_edit_bio,
        )
        if not conn.is_enabled:
            try:
                db.delete_ai_data(conn.user.id)  # mijozlar yozishmasi tarixi qolmasin
            except Exception:
                logger.exception("AI ma'lumotlarini o'chirishda xato (owner=%s)", conn.user.id)
        try:
            ob_view = None
            if conn.is_enabled:
                try:
                    ob_view = onboarding_view_on_connection(conn.user.id)
                except Exception:
                    logger.exception("Onboarding: ulanish hodisasini qayta ishlashda xato (owner=%s)", conn.user.id)
            else:
                try:
                    db.set_onboarding_step(conn.user.id, "connect", only_from=("configure", "verify"))
                except Exception:
                    logger.exception("Onboarding: uzilishni qayta ishlashda xato (owner=%s)", conn.user.id)
            if ob_view is not None:
                await context.bot.send_message(
                    chat_id=conn.user_chat_id, text=ob_view[0], reply_markup=ob_view[1]
                )
            elif conn.is_enabled:
                await context.bot.send_message(
                    chat_id=conn.user_chat_id,
                    text=t(get_lang(conn.user.id), "connected"),
                )
            else:
                await context.bot.send_message(
                    chat_id=conn.user_chat_id,
                    text=t(get_lang(conn.user.id), "disconnected"),
                )
        except TelegramError as e:
            logger.info("Ulanish xabarnomasi yuborilmadi (owner=%s): %s", conn.user.id, e)
        return

    # Mijozdan kelgan xabar
    bm = update.business_message
    if bm is not None:
        connection = db.get_connection_by_business_id(bm.business_connection_id)
        if connection is None or not connection["is_enabled"] or not connection["can_reply"]:
            return

        owner_id = connection["owner_user_id"]

        # Admin tomonidan bloklangan foydalanuvchining akkountiga avtojavob berilmaydi.
        if connection.get("is_blocked"):
            return

        # Majburiy kanalga obuna bo'lmagan egasining avtojavobi/AI'si ishlamaydi.
        if not await is_subscribed_cached(context.bot, owner_id):
            await notify_subscription_lost(context.bot, owner_id)
            return

        # Bu SIZNING (akkaunt egasining) o'zi yozgan xabari — botlarga emas,
        # mijozlarga javob berishimiz kerak, shuning uchun o'tkazib yuboramiz.
        if bm.from_user and bm.from_user.id == owner_id:
            # Egasi chatga o'zi yozdi — AI shu chatda biroz jim turadi (botning o'z xabari bo'lsa — yo'q).
            if (bm.chat.id, bm.message_id) not in _bot_sent_ids:
                try:
                    adopt_new_base_name(owner_id, getattr(bm.from_user, "first_name", None), getattr(bm.from_user, "last_name", None))
                except Exception:
                    logger.exception("Ism soati: yangi ismni olishda xato (owner=%s)", owner_id)
                try:
                    if db.get_settings(owner_id).get("ai_enabled"):
                        db.pause_ai_chat(owner_id, bm.chat.id, AI_TAKEOVER_PAUSE_SECONDS)
                except Exception:
                    logger.exception("AI pauzasini yozishda xato (owner=%s)", owner_id)
            return

        # Statistika: akkauntga kelgan HAMMA mijoz xabari sanaladi (egasi onlayn bo'lsa yoki cooldown
        # sabab javob ketmasa ham) — shunda "kelgan" va "yuborilgan" farqi tushuntirib beriladi.
        if not (bm.from_user and bm.from_user.is_bot):
            track_analytics(owner_id, "incoming")

        settings = db.get_settings(owner_id)

        # Uxlash rejimi va Jadval BIR XIL vaqt zonasi bilan hisoblanadi: egasining zonasi (Ism soati sozlamasi), yo'q bo'lsa Toshkent
        sleeping, schedule_rule = reply_state(owner_id, settings)

        owner_lang = get_lang(owner_id)
        # Ustuvorlik: Sleep Mode -> Jadval -> (FAQ -> AI ->) oddiy avtojavob. Jadval oynasida bot Oflayn kabi ishlaydi,
        # lekin foydalanuvchining sozlamalari o'zgartirilmaydi.
        if sleeping:
            reply_text = sleep_text_for(settings, owner_lang)
        elif schedule_rule is not None:
            reply_text = schedule_text_for(owner_id, schedule_rule, settings, owner_lang)
        elif settings["offline"]:
            reply_text = auto_reply_text_for(settings, owner_lang)
        else:
            return
        effective_offline = bool(settings["offline"]) or schedule_rule is not None

        if bm.from_user and bm.from_user.is_bot:
            return

        chat_id = bm.chat.id
        label = f"sleeping={sleeping}" + (",schedule" if schedule_rule is not None else "")

        ai_usable = not sleeping and bool(settings.get("ai_enabled")) and ai.is_configured() and has_feature(owner_id, "ai")

        # Smart FAQ: faqat Oflayn holatda (uxlash vaqtida emas) va faqat aniq, yagona moslik bo'lsa
        if not sleeping and effective_offline and settings.get("faq_enabled", True):
            faq_text = (bm.text or bm.caption or "").strip()
            faq_answer = find_faq_answer(owner_id, faq_text) if faq_text else None
            if faq_answer:
                if settings.get("ai_enabled") and db.is_ai_paused(owner_id, chat_id):
                    return  # egasi shu chatda o'zi yozmoqda
                await send_faq_reply(
                    context.bot, bm, owner_id, chat_id, faq_answer, settings["cooldown_hours"], label + ",faq", ai_usable
                )
                return

        # AI-Yordamchi: odatiy matn o'rniga AI javob beradi (matn faqat zaxira sifatida qoladi)
        # Uxlash vaqtida AI ishlamaydi: Sleep Mode har doim ustun, egasining uxlash xabari ketadi
        if not sleeping and settings.get("ai_enabled") and ai.is_configured() and has_feature(owner_id, "ai"):
            if db.is_ai_paused(owner_id, chat_id):
                return  # egasi shu chatda o'zi yozmoqda
            text = (bm.text or bm.caption or "").strip()
            if text:
                spawn_background(
                    run_ai_reply(context.bot, bm, owner_id, chat_id, text, settings, reply_text, label)
                )
                return
            # Matnsiz xabar (rasm, ovoz, sticker...) — AI o'qiy olmaydi, odatiy matn ketadi

        await send_auto_reply(context.bot, bm, owner_id, chat_id, reply_text, settings["cooldown_hours"], label)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handlerlarda ushlanmagan xatolar: "Message is not modified" (tugma ikki marta bosilgan) — zararsiz,
    jim o'tkaziladi; qolganlari to'liq traceback bilan loglanadi (aks holda PTB "No error handlers" deb yozardi)."""
    err = context.error
    if isinstance(err, BadRequest) and "not modified" in str(err).lower():
        return
    logger.error("Handlerda ushlanmagan xato", exc_info=err)


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()

    # Faqat oddiy `message` yangilanishlari (bot bilan shaxsiy chat): business_message
    # (mijozlarning xabarlari), tahrirlangan xabarlar va kanal postlari handlerlarga
    # tushmasligi uchun. Aks holda har bir mijoz "foydalanuvchi" bo'lib bazaga yozilib,
    # reklama ro'yxatiga kirib qolardi.
    only_messages = filters.UpdateType.MESSAGE

    app.add_error_handler(on_error)

    # Bloklangan foydalanuvchini eng birinchi to'xtatadi (qolgan hamma handlerdan oldin)
    app.add_handler(TypeHandler(Update, block_gate), group=-3)
    # Keyin majburiy obuna: obuna bo'lmagan odam botning hech bir funksiyasidan foydalana olmaydi
    app.add_handler(TypeHandler(Update, subscribe_gate), group=-2)

    app.add_handler(CommandHandler("start", cmd_start, filters=only_messages))
    app.add_handler(CommandHandler("help", cmd_help, filters=only_messages))
    app.add_handler(CommandHandler("stats", cmd_stats, filters=only_messages))
    app.add_handler(CommandHandler("onboarding", cmd_onboarding, filters=only_messages))
    app.add_handler(CommandHandler("block", cmd_block, filters=only_messages))
    app.add_handler(CommandHandler("unblock", cmd_unblock, filters=only_messages))
    app.add_handler(CommandHandler("setplan", cmd_setplan, filters=only_messages))
    app.add_handler(CommandHandler("blocked", cmd_blocked, filters=only_messages))
    app.add_handler(CommandHandler("users", cmd_users, filters=only_messages))
    app.add_handler(CommandHandler("bots", cmd_bots, filters=only_messages))
    app.add_handler(CommandHandler("reklama", cmd_reklama, filters=only_messages))
    app.add_handler(CommandHandler("reklama_status", cmd_reklama_status, filters=only_messages))
    app.add_handler(CommandHandler("reklama_retry", cmd_reklama_retry, filters=only_messages))
    app.add_handler(CommandHandler("cancel", cmd_cancel, filters=only_messages))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & only_messages, on_text))
    app.add_handler(MessageHandler(~filters.TEXT & only_messages & filters.ChatType.PRIVATE, on_other_message))
    # Admin /reklama oqimi — istalgan turdagi xabarni ushlab qolish uchun alohida,
    # ustuvor guruhda (boshqa handler'larga to'sqinlik qilmaydi, chunki guruhlar
    # bir-biridan mustaqil ishlaydi).
    app.add_handler(
        MessageHandler(filters.ALL & ~filters.COMMAND & only_messages, on_admin_broadcast_content), group=-1
    )
    # Alohida guruhda — business_connection/business_message'larni hech narsaga
    # to'sqinlik qilmasdan tinglaydi.
    app.add_handler(TypeHandler(Update, on_raw_update), group=1)

    # BIO hisoblagichni kuniga bir marta, Toshkent vaqti bilan 00:05'da yangilaydi
    # (interval-based emas, aniq soatga bog'langan — shu bilan server qachon
    # ishga tushganidan qat'iy nazar barqaror jadval saqlanadi).
    if app.job_queue is not None:
        app.job_queue.run_daily(
            bio_daily_job,
            time=dtime(hour=0, minute=5, tzinfo=TASHKENT_TZ),
        )
        # AI suhbat tarixi/limit jadvallarini tozalash (har kuni 00:10, Toshkent vaqti)
        app.job_queue.run_daily(ai_cleanup_job, time=dtime(hour=0, minute=10, tzinfo=TASHKENT_TZ))
        # Server qayta ishga tushganda yarim qolgan reklamalarni davom ettirish
        app.job_queue.run_once(_resume_broadcasts_job_callback, when=5)
        # Server 00:05 da o'chiq bo'lgan bo'lsa, o'tkazib yuborilgan BIO yangilanishini yetkazish
        app.job_queue.run_once(bio_startup_job, when=10)
        # Eski foydalanuvchilarning username/ismini to'ldirish (/block @username ishlashi uchun)
        app.job_queue.run_once(profile_backfill_job, when=20)
        # Muddati tugagan tariflarni Bepulga qaytarish (har 10 daqiqada)
        app.job_queue.run_repeating(plan_expiry_job, interval=600, first=30)
        # Ism soati/BIO egalarining kanal a'zoligini yangilab turish (har daqiqada, faqat eskirganlarni)
        app.job_queue.run_repeating(subscription_refresh_job, interval=60, first=45)
        # Bepul tarifdagi ism soati egalarining BIO'siga reklama qo'yish/olib tashlash
        app.job_queue.run_repeating(clock_bio_ad_job, interval=60, first=50)
    else:
        logger.warning(
            "JobQueue mavjud emas — BIO hisoblagich avtomatik yangilanmaydi. "
            "requirements.txt'da 'python-telegram-bot[job-queue]' borligini tekshiring."
        )

    return app


class _HealthHandler(BaseHTTPRequestHandler):
    """Render Web Service uchun: portni tinglab, 'tirik' ekanini bildiradi."""

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # terminalni har bir ping bilan to'ldirmaslik uchun


def start_health_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        # Python 3.14+ asosiy oqimda avtomatik event loop yaratmaydi — qo'lda yaratamiz
        asyncio.set_event_loop(asyncio.new_event_loop())

    # Render Web Service portni tinglashni talab qiladi — shu uchun health server
    # alohida oqimda (thread) fonda ishga tushadi, asosiy bot esa polling bilan davom etadi.
    threading.Thread(target=start_health_server, daemon=True).start()

    db.init_db()
    app = build_app()
    logger.info("Bot ishga tushdi. Foydalanuvchilar /start yozishi mumkin.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
