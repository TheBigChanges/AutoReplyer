"""
Foydalanuvchi o'z akkountini Telegramning o'z "Chat Automation" (Telegram
Business -> Chatbots) funksiyasi orqali shu botga ulaydi. Hech qanday
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
import logging
import os
import re
import threading
import time
from datetime import datetime
from datetime import time as dtime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Forbidden, RetryAfter, TelegramError
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

import db
from logic import (
    BIO_EVENT_LABELS,
    DEFAULT_SLEEP_MESSAGE,
    compute_bio_text,
    format_cooldown,
    format_time_range,
    is_within_sleep_window,
    parse_birthday_input,
    parse_cooldown_input,
    parse_time_range_input,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
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


def track_user(user):
    """Foydalanuvchini (va uning username/ismini) bazaga yozadi. Username
    saqlanishi sababli admin /block @username bilan odamni topa oladi."""
    if user is None:
        return
    db.record_user(user.id, username=user.username, full_name=user.full_name)

HOW_CONNECT_TEXT = (
    "\U0001F517 Akkountni ulash — qadamma-qadam:\n\n"
    "1\uFE0F\u20E3 Telegram ilovangizda: Sozlamalar (Settings)\n"
    "2\uFE0F\u20E3 \"Telegram Business\" bo'limini toping va uni oching\n"
    "3\uFE0F\u20E3 \"Chatbots\" (yoki \"Chat Automation\") ni tanlang\n"
    f"4\uFE0F\u20E3 Kiritish maydoniga botning username'ini yozing: @{BOT_USERNAME}\n"
    "   Ro'yxatda chiqqach, ustiga bosib tanlang\n"
    "5\uFE0F\u20E3 \"Access to chats\" (qaysi chatlarga ruxsat) so'ralganda:\n"
    "   \u2022 \"All 1-to-1 Chats\" ni tanlang — bu barcha shaxsiy xabarlarga ruxsat beradi\n"
    "   \u2022 (\"Only Selected Chats\"ni tansangiz, faqat o'zingiz qo'shgan odamlarga javob beriladi)\n"
    "6\uFE0F\u20E3 \"Reply to messages\" (xabarlarga javob berish) ruxsatini albatta yoqing —\n"
    "   shu yoqilmasa, bot xabarlarni ko'radi lekin javob bera olmaydi\n\n"
    "Ulangach, shu yerga qaytib /start yozing \u2014 panel avtomatik ochiladi."
)


async def apply_bio_update(bot, owner_id: int) -> tuple[bool, str]:
    """Bitta foydalanuvchining BIO'sini hozirgi sozlamalariga qarab yangilaydi."""
    connection = db.get_connection(owner_id)
    settings = db.get_settings(owner_id)
    target = settings.get("bio_countdown_target")

    if not connection or not connection["is_enabled"]:
        return False, "Akkount ulanmagan."
    if not connection.get("can_edit_bio"):
        return False, "\"Edit bio\" ruxsati yoqilmagan."
    if not target:
        return False, "BIO hisoblagich o'chirilgan."

    text = compute_bio_text(
        target, settings.get("birthday_month"), settings.get("birthday_day"), today=today_tashkent()
    )
    if text is None:
        return False, "Tug'ilgan kun sanasi kiritilmagan."

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
        text = compute_bio_text(
            row["bio_countdown_target"], row["birthday_month"], row["birthday_day"], today=today
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
async def is_subscribed(bot, user_id: int) -> bool:
    """Majburiy kanalga a'zoligini tekshiradi. Sozlanmagan bo'lsa — har doim
    True (tekshiruv o'chirilgan). Xato chiqsa (masalan bot kanalda admin
    emas) — butun botni to'sib qo'ymaslik uchun xavfsiz tomonga (ruxsat
    berilgan deb) og'amiz, lekin loglab qo'yamiz, chunki bu sozlama xatosi
    belgisi bo'lishi mumkin."""
    if REQUIRED_CHANNEL_ID is None:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL_ID, user_id=user_id)
        return member.status not in ("left", "kicked")
    except TelegramError as e:
        logger.warning(
            "Obuna tekshiruvida xato (user=%s, channel=%s): %s — bot kanalda admin ekanini tekshiring",
            user_id, REQUIRED_CHANNEL_ID, e,
        )
        return True


def build_subscribe_gate_markup(inviter_id: int | None = None):
    # Taklif qilgan odamning ID'si tugma ichida (callback_data) olib yuriladi: shunda
    # foydalanuvchi obuna bo'lib "Tekshirish"ni bosganda referal yo'qolmaydi
    # (holat RAM'da emas — server restart bo'lsa ham saqlanadi). Limit 64 bayt.
    check_data = f"check_subscription:{inviter_id}" if inviter_id else "check_subscription"
    keyboard = [
        [InlineKeyboardButton("\U0001F4E2 Kanalga o'tish", url=REQUIRED_CHANNEL_LINK)],
        [InlineKeyboardButton("\u2705 Tekshirish", callback_data=check_data)],
    ]
    return InlineKeyboardMarkup(keyboard)


def parse_referral_arg(args) -> int | None:
    """/start ref_123 -> 123 (noto'g'ri bo'lsa None)."""
    if not args:
        return None
    arg = args[0]
    if not arg.startswith("ref_"):
        return None
    try:
        inviter_id = int(arg[4:])
    except ValueError:
        return None
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
            text="\U0001F389 Sizning havolangiz orqali yangi odam botga qo'shildi!",
        )
    except TelegramError as e:
        logger.info("Referral bildirishnomasi yuborilmadi (inviter=%s): %s", inviter_id, e)


SUBSCRIBE_GATE_TEXT = (
    "\U0001F512 Botdan foydalanish uchun avval kanalimizga obuna bo'ling.\n\n"
    "Obuna bo'lgach, pastdagi \"\u2705 Tekshirish\" tugmasini bosing."
)


def build_start_view(owner_id: int):
    """Bosh menyu matni va tugmalarini qaytaradi (obunadan o'tgan foydalanuvchi uchun)."""
    conn = db.get_connection(owner_id)
    if conn and conn["is_enabled"]:
        greeting = "Assalomu alaykum! Kerakli bo'limni tanlang:"
    else:
        greeting = (
            "Assalomu alaykum!\n\n"
            "Bu bot orqali o'z Telegram akkountingizni ulab, siz oflayn bo'lganingizda "
            "kiruvchi shaxsiy xabarlarga avtomatik javob berishni sozlashingiz mumkin."
        )
    return greeting, main_menu_markup(owner_id)


def main_menu_markup(owner_id: int):
    conn = db.get_connection(owner_id)
    rows = []
    if conn and conn["is_enabled"]:
        rows.append([InlineKeyboardButton("\U0001F39B Panelni ochish", callback_data="open_panel")])
    else:
        rows.append([InlineKeyboardButton("\u2139\uFE0F Qanday ulash mumkin?", callback_data="how_connect")])
    rows.append([InlineKeyboardButton("\U0001F381 Referal bonus", callback_data="referral")])
    if owner_id == ADMIN_ID:
        rows.append([InlineKeyboardButton("\U0001F4CA Referral statistikasi (admin)", callback_data="admin_referrals")])
    return InlineKeyboardMarkup(rows)


def build_referral_view(owner_id: int):
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{owner_id}"
    count = db.get_referral_count(owner_id)
    share_text = "Oflaynda ham javob beradigan Telegram botdan foydalaning:"
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}"

    text = (
        "\U0001F381 Referal bonus\n\n"
        f"Siz orqali botga ulangan do'stlar soni: {count}\n\n"
        "Shaxsiy havolangiz:\n"
        f"{link}\n\n"
        "Do'stlaringiz shu havola orqali botga kirsa, ular siz taklif qilgan hisoblanadi."
    )
    keyboard = [
        [InlineKeyboardButton("\U0001F4E4 Havolani ulashish", url=share_url)],
        [InlineKeyboardButton("\u2B05\uFE0F Orqaga", callback_data="back")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def build_admin_referrals_view(bot):
    rows = db.get_all_referral_counts()
    if not rows:
        body = "Hozircha hech kim hech kimni taklif qilmagan."
    else:
        lines = []
        for i, (inviter_id, cnt) in enumerate(rows):
            label = await _display_name_for(bot, inviter_id)
            lines.append(f"{i + 1}. {label} — {cnt} ta do'st")
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


def build_panel(owner_id: int):
    s = db.get_settings(owner_id)
    status_line = "\U0001F534 OFLAYN" if s["offline"] else "\U0001F7E2 ONLAYN"
    toggle_label = "\U0001F7E2 Onlaynga o'tish" if s["offline"] else "\U0001F534 Oflaynga o'tish"
    sleep_line = "yoqilgan \U0001F634" if s.get("sleep_mode_enabled") else "o'chirilgan"

    text = (
        "\U0001F39B Sizning panelingiz\n\n"
        f"Holat: {status_line}\n"
        f"Cooldown: {format_cooldown(s['cooldown_hours'])}\n"
        f"Xabar: {s['auto_reply_text']}\n"
        f"Uxlayapman rejimi: {sleep_line}"
    )
    keyboard = [
        [InlineKeyboardButton(toggle_label, callback_data="toggle_status")],
        [InlineKeyboardButton("\u23F1 Cooldownni o'zgartirish", callback_data="edit_cooldown")],
        [InlineKeyboardButton("\U0001F4DD Xabar matnini o'zgartirish", callback_data="edit_text")],
        [InlineKeyboardButton("\U0001F382 BIO hisoblagich", callback_data="bio_menu")],
        [InlineKeyboardButton("\U0001F634 Uxlayapman rejimi", callback_data="sleep_menu")],
        [InlineKeyboardButton("\u2B05\uFE0F Orqaga", callback_data="back")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_sleep_menu(owner_id: int):
    s = db.get_settings(owner_id)
    enabled = s.get("sleep_mode_enabled", False)
    start_minutes = s.get("sleep_start_minutes", 23 * 60)
    end_minutes = s.get("sleep_end_minutes", 7 * 60)
    sleep_text = s.get("sleep_reply_text") or DEFAULT_SLEEP_MESSAGE

    status_line = "\U0001F634 Yoqilgan" if enabled else "O'chirilgan"
    toggle_label = "\u274C O'chirish" if enabled else "\u2705 Yoqish"

    text = (
        "\U0001F634 Uxlayapman rejimi\n\n"
        f"Holat: {status_line}\n"
        f"Vaqt oralig'i: {format_time_range(start_minutes, end_minutes)}\n"
        f"Xabar: {sleep_text}\n\n"
        "Bu rejim yoqilgan bo'lsa, belgilangan vaqt oralig'ida (hatto \"Onlayn\" "
        "holatida ham) kiruvchi xabarlarga shu maxsus matn bilan avtomatik javob beriladi."
    )
    keyboard = [
        [InlineKeyboardButton(toggle_label, callback_data="sleep_toggle")],
        [InlineKeyboardButton("\u23F0 Vaqtni o'zgartirish", callback_data="sleep_edit_time")],
        [InlineKeyboardButton("\U0001F4DD Xabar matnini o'zgartirish", callback_data="sleep_edit_text")],
        [InlineKeyboardButton("\u2B05\uFE0F Orqaga", callback_data="open_panel")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def build_bio_menu(owner_id: int):
    connection = db.get_connection(owner_id)
    s = db.get_settings(owner_id)
    target = s.get("bio_countdown_target")

    if not connection or not connection.get("can_edit_bio"):
        text = (
            "\U0001F382 BIO hisoblagich\n\n"
            "Bu funksiya uchun \"Edit bio\" (BIO'ni tahrirlash) ruxsati kerak.\n\n"
            "Telegram: Sozlamalar \u2192 Telegram Business \u2192 Chatbots \u2192 botni bosing \u2192 "
            "\"Edit bio\" ruxsatini yoqing. Keyin shu tugmani qayta bosing."
        )
        keyboard = [[InlineKeyboardButton("\u2B05\uFE0F Orqaga", callback_data="open_panel")]]
        return text, InlineKeyboardMarkup(keyboard)

    if target:
        label = BIO_EVENT_LABELS.get(target, target)
        preview = compute_bio_text(
            target, s.get("birthday_month"), s.get("birthday_day"), today=today_tashkent()
        )
        status = f"Yoqilgan: {label}\nHozirgi matn: {preview or '(sana kiritilmagan)'}"
    else:
        status = "Hozircha o'chirilgan."

    text = (
        "\U0001F382 BIO hisoblagich\n\n"
        f"{status}\n\n"
        "BIO'ingizda avtomatik shu turdagi hisoblagich ko'rsatilsin:"
    )
    keyboard = [
        [InlineKeyboardButton("\U0001F386 Yangi yilgacha", callback_data="bio_set_new_year")],
        [InlineKeyboardButton("\U0001F33F Navro'zgacha", callback_data="bio_set_navroz")],
        [InlineKeyboardButton("\U0001F382 Tug'ilgan kunimgacha", callback_data="bio_set_birthday")],
    ]
    if target:
        keyboard.append([InlineKeyboardButton("\u274C O'chirish", callback_data="bio_disable")])
    keyboard.append([InlineKeyboardButton("\u2B05\uFE0F Orqaga", callback_data="open_panel")])
    return text, InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Buyruq va tugmalar
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    track_user(update.effective_user)
    clear_pending_action(owner_id)  # /start har doim tugallanmagan amalni tozalaydi

    inviter_id = parse_referral_arg(context.args)

    if not await is_subscribed(context.bot, owner_id):
        # Referal obuna bo'lgandan KEYIN hisoblanadi (tugma orqali olib o'tiladi)
        await update.message.reply_text(
            SUBSCRIBE_GATE_TEXT, reply_markup=build_subscribe_gate_markup(inviter_id)
        )
        return

    await process_referral(context.bot, owner_id, inviter_id)

    greeting, markup = build_start_view(owner_id)
    await update.message.reply_text(greeting, reply_markup=markup)


HELP_TEXT = (
    "\U0001F916 AutoReplyer — siz oflayn bo'lganingizda Telegram akkountingizdagi "
    "shaxsiy xabarlarga avtomatik javob beradi.\n\n"
    "Imkoniyatlar:\n"
    "\u2022 Oflayn avtojavob (cooldown bilan — bir chatga qayta-qayta yozmaydi)\n"
    "\u2022 Uxlayapman rejimi — tungi vaqt oralig'ida alohida javob\n"
    "\u2022 BIO hisoblagich — Yangi yil, Navro'z yoki tug'ilgan kuningizgacha qolgan kunlar\n"
    "\u2022 Referal bonus\n\n"
    "Buyruqlar:\n"
    "/start — bosh menyu va panel\n"
    "/help — shu yo'riqnoma\n\n"
    "Akkountni ulash: /start yozing va \"Qanday ulash mumkin?\" tugmasini bosing."
)

ADMIN_HELP_TEXT = (
    "\n\n\U0001F510 Admin buyruqlari:\n"
    "/stats — foydalanuvchilar soni\n"
    "/block @username [sabab] — foydalanuvchini bloklash (yoki /block 123456789)\n"
    "/unblock @username — blokdan chiqarish\n"
    "/blocked — bloklanganlar ro'yxati\n"
    "/reklama — barcha foydalanuvchilarga xabar yuborish (yuborishdan oldin tasdiqlanadi)\n"
    "/reklama_status — oxirgi reklama holati\n"
    "/reklama_retry — oxirgi reklamani qayta urinish\n"
    "/cancel — joriy admin amalini bekor qilish"
)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    track_user(update.effective_user)
    text = HELP_TEXT
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
    if data == "check_subscription" or data.startswith("check_subscription:"):
        if await is_subscribed(context.bot, owner_id):
            await query.answer("\u2705 Obuna tasdiqlandi!")
            inviter_id = None
            if ":" in data:
                try:
                    inviter_id = int(data.split(":", 1)[1])
                except ValueError:
                    inviter_id = None
            await process_referral(context.bot, owner_id, inviter_id)
            greeting, markup = build_start_view(owner_id)
            await query.edit_message_text(greeting, reply_markup=markup)
        else:
            await query.answer(
                "\u274C Siz hali kanalga obuna bo'lmagansiz. Avval obuna bo'lib, keyin qayta bosing.",
                show_alert=True,
            )
        return

    if data == "admin_referrals" and owner_id != ADMIN_ID:
        await query.answer("Ruxsat yo'q.", show_alert=True)
        return

    if data == "bc_cancel" or data.startswith("bc_confirm:"):
        await handle_broadcast_confirmation(query, context, data)
        return

    if data == "appeal_start":
        # Bloklangan foydalanuvchining bosishi block_gate'da ushlanadi. Bu yerga
        # faqat bloklanmagan (masalan blokdan chiqarilgan) odam eski tugmani
        # bossa keladi.
        await query.answer("Siz bloklanmagansiz.", show_alert=True)
        return

    if data.startswith("unblock:"):
        if owner_id != ADMIN_ID:
            await query.answer("Ruxsat yo'q.", show_alert=True)
            return
        try:
            target_id = int(data.split(":", 1)[1])
        except ValueError:
            await query.answer("Noto'g'ri tugma.", show_alert=True)
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
    clear_pending_action(owner_id)

    if data == "how_connect":
        await query.edit_message_text(HOW_CONNECT_TEXT, reply_markup=main_menu_markup(owner_id))
        return

    if data == "open_panel":
        conn = db.get_connection(owner_id)
        if not conn or not conn["is_enabled"]:
            await query.edit_message_text(HOW_CONNECT_TEXT, reply_markup=main_menu_markup(owner_id))
            return
        text, markup = build_panel(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "back":
        await query.edit_message_text("Bosh menyu:", reply_markup=main_menu_markup(owner_id))
        return

    if data == "referral":
        text, markup = build_referral_view(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "admin_referrals":
        text, markup = await build_admin_referrals_view(context.bot)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "toggle_status":
        s = db.get_settings(owner_id)
        db.update_settings(owner_id, offline=not s["offline"])

    elif data == "edit_cooldown":
        set_pending_action(owner_id, "cooldown")
        await query.message.reply_text(
            "Yangi cooldown qiymatini yuboring. Masalan:\n"
            "\u2022 2 soat 30 daqiqa\n"
            "\u2022 45 daqiqa\n"
            "\u2022 1:30 (1 soat 30 daqiqa)\n"
            "\u2022 3 (shunchaki 3 soat)\n\n"
            "\u26A0\uFE0F 0 qabul qilinmaydi — spamning oldini olish uchun eng kami 1 daqiqa bo'lishi kerak."
        )
        return

    elif data == "edit_text":
        set_pending_action(owner_id, "text")
        await query.message.reply_text("Yangi avtojavob matnini yuboring:")
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
            text += f"\n\n\u26A0\uFE0F BIO yangilanmadi: {info}"
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "bio_set_birthday":
        s = db.get_settings(owner_id)
        if s.get("birthday_month") and s.get("birthday_day"):
            db.update_settings(owner_id, bio_countdown_target="birthday")
            ok, info = await apply_bio_update(context.bot, owner_id)
            text, markup = build_bio_menu(owner_id)
            if not ok:
                text += f"\n\n\u26A0\uFE0F BIO yangilanmadi: {info}"
            await query.edit_message_text(text, reply_markup=markup)
        else:
            set_pending_action(owner_id, "birthday_date")
            await query.message.reply_text(
                "Tug'ilgan kuningizni kun.oy formatida yuboring (masalan: 15.03 — 15-mart):"
            )
        return

    if data == "bio_disable":
        db.update_settings(owner_id, bio_countdown_target=None)
        text, markup = build_bio_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "sleep_menu":
        text, markup = build_sleep_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "sleep_toggle":
        s = db.get_settings(owner_id)
        db.update_settings(owner_id, sleep_mode_enabled=not s.get("sleep_mode_enabled", False))
        text, markup = build_sleep_menu(owner_id)
        await query.edit_message_text(text, reply_markup=markup)
        return

    if data == "sleep_edit_time":
        set_pending_action(owner_id, "sleep_time")
        await query.message.reply_text(
            "Uxlash vaqt oralig'ini yuboring (masalan: 23:00-07:00):"
        )
        return

    if data == "sleep_edit_text":
        set_pending_action(owner_id, "sleep_text")
        await query.message.reply_text("Uxlash vaqtida yuboriladigan xabarni kiriting:")
        return

    text, markup = build_panel(owner_id)
    await query.edit_message_text(text, reply_markup=markup)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    track_user(update.effective_user)
    action = get_pending_action(owner_id)
    if action is None:
        return  # panelga aloqasi yo'q oddiy xabar

    value = update.message.text.strip()

    if action == "cooldown":
        hours = parse_cooldown_input(value)
        if hours is None or hours <= 0:
            await update.message.reply_text(
                "Noto'g'ri format yoki 0. Spamning oldini olish uchun cooldown 0 bo'lishi mumkin emas "
                "— eng kami 1 daqiqa kiriting. Masalan: '2 soat 30 daqiqa', '45 daqiqa', '1 daqiqa', '1:30' yoki '3'"
            )
            return
        db.update_settings(owner_id, cooldown_hours=hours)

    elif action == "text":
        db.update_settings(owner_id, auto_reply_text=value)

    elif action == "birthday_date":
        parsed = parse_birthday_input(value)
        if parsed is None:
            await update.message.reply_text(
                "Noto'g'ri format. Kun.oy ko'rinishida yuboring, masalan: 15.03"
            )
            return
        month, day = parsed
        db.update_settings(owner_id, birthday_month=month, birthday_day=day, bio_countdown_target="birthday")
        ok, info = await apply_bio_update(context.bot, owner_id)
        clear_pending_action(owner_id)
        text, markup = build_bio_menu(owner_id)
        if not ok:
            text += f"\n\n\u26A0\uFE0F BIO yangilanmadi: {info}"
        await update.message.reply_text("Saqlandi.")
        await update.message.reply_text(text, reply_markup=markup)
        return

    elif action == "sleep_time":
        parsed = parse_time_range_input(value)
        if parsed is None:
            await update.message.reply_text(
                "Noto'g'ri format. Masalan: 23:00-07:00"
            )
            return
        start_minutes, end_minutes = parsed
        db.update_settings(owner_id, sleep_start_minutes=start_minutes, sleep_end_minutes=end_minutes)
        clear_pending_action(owner_id)
        text, markup = build_sleep_menu(owner_id)
        await update.message.reply_text("Saqlandi.")
        await update.message.reply_text(text, reply_markup=markup)
        return

    elif action == "sleep_text":
        db.update_settings(owner_id, sleep_reply_text=value)
        clear_pending_action(owner_id)
        text, markup = build_sleep_menu(owner_id)
        await update.message.reply_text("Saqlandi.")
        await update.message.reply_text(text, reply_markup=markup)
        return

    clear_pending_action(owner_id)
    text, markup = build_panel(owner_id)
    await update.message.reply_text("Yangilandi.")
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
    if cleared_admin or cleared_panel:
        await update.message.reply_text("Bekor qilindi.")


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
        await query.answer("Ruxsat yo'q.", show_alert=True)
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
    except Exception:
        logger.exception("Reklama job#%d kutilmagan xato bilan to'xtadi", job_id)
        db.set_broadcast_status(job_id, "failed")
        if reply_to_chat_id is not None:
            try:
                await bot.send_message(
                    chat_id=reply_to_chat_id,
                    text=(
                        f"\u26A0\uFE0F Reklama job#{job_id} kutilmagan xato bilan to'xtadi.\n"
                        "Qaytadan boshlash uchun /reklama yozing."
                    ),
                )
            except TelegramError:
                pass
        return

    db.set_broadcast_status(job_id, "completed")
    logger.info("Reklama job#%d tugadi: %d muvaffaqiyatli, %d xato", job_id, sent, failed)

    if reply_to_chat_id is not None:
        try:
            await bot.send_message(
                chat_id=reply_to_chat_id,
                text=(
                    f"\u2705 Reklama tugadi (job#{job_id}).\n"
                    f"Muvaffaqiyatli: {sent}\nYuborib bo'lmadi: {failed}"
                    + ("\nQayta urinish uchun: /reklama_retry" if failed else "")
                ),
            )
        except TelegramError:
            pass


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
                db.record_broadcast_failure(job_id, user_id, "blocked/deleted")
            except TelegramError as e:
                failed += 1
                failed_delta = 1
                db.record_broadcast_failure(job_id, user_id, str(e))

            db.update_broadcast_progress(job_id, last_user_id, sent_delta=sent_delta, failed_delta=failed_delta)
            await asyncio.sleep(0.05)  # ~20 xabar/soniya — Telegram limitidan pastroq

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
    if raw.isdigit():
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


def build_block_notice(reason: str):
    text = "\U0001F6AB Siz admin tomonidan bloklandingiz.\n"
    if reason:
        text += f"Sabab: {reason}\n"
    text += (
        "\nBloklash davomida bot sizga xizmat ko'rsatmaydi: panel ishlamaydi, "
        "avtojavob va BIO yangilash to'xtatiladi.\n\n"
        "Agar bu xato deb o'ylasangiz, pastdagi tugma orqali izoh qoldiring — admin ko'rib chiqadi."
    )
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("\u270D\uFE0F Izoh qoldirish", callback_data="appeal_start")]]
    )
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

    text, markup = build_block_notice(reason)
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
        await _try_send(
            bot, target_id, "\u2705 Siz blokdan chiqarildingiz. Davom etish uchun /start yozing."
        )
    return changed


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
        lines.append(f"{i}. {label} — {row.get('reason') or 'sababsiz'} ({when})")
    text = f"\U0001F6AB Bloklanganlar ({total} ta):\n\n" + "\n".join(lines)
    if total > len(rows):
        text += f"\n\n... va yana {total - len(rows)} ta (eng oxirgi {limit} tasi ko'rsatildi)"
    await update.message.reply_text(text)


async def _begin_appeal(bot, user_id: int):
    """Bloklangan foydalanuvchi "Izoh qoldirish"ni bosdi."""
    used = db.count_recent_appeals(user_id, time.time() - 24 * 3600)
    if used >= APPEAL_MAX_PER_DAY:
        await _try_send(
            bot, user_id,
            f"Siz oxirgi 24 soat ichida {used} marta izoh qoldirgansiz. Keyinroq qayta urinib ko'ring.",
        )
        return
    pending_appeal[user_id] = time.time()
    await _try_send(
        bot, user_id,
        "\u270D\uFE0F Izohingizni bitta xabar qilib yuboring (ko'pi bilan "
        f"{APPEAL_MAX_LENGTH} belgi). Nima uchun bu xato deb o'ylayotganingizni yozing.\n"
        "Bekor qilish: /cancel",
    )


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
    if not delivered:
        await _try_send(
            bot, user.id,
            "Hozir izohingizni adminga yetkazib bo'lmadi. Keyinroq qayta urinib ko'ring.",
        )
        return
    db.add_appeal(user.id, text)
    pending_appeal.pop(user.id, None)
    await _try_send(
        bot, user.id,
        "\u2705 Izohingiz adminga yuborildi. Qaror qabul qilinsa, sizga xabar beriladi.",
    )


async def handle_blocked_update(update: Update, context: ContextTypes.DEFAULT_TYPE, block: dict):
    user = update.effective_user
    now = time.time()
    query = update.callback_query

    if query is not None:
        if query.data == "appeal_start":
            await query.answer()
            await _begin_appeal(context.bot, user.id)
        else:
            await query.answer("\U0001F6AB Siz bloklangansiz.", show_alert=True)
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
            await message.reply_text("Bekor qilindi.")
            return
        if text and not text.startswith("/"):
            if len(text) > APPEAL_MAX_LENGTH:
                await message.reply_text(
                    f"Izoh juda uzun ({len(text)} belgi). Ko'pi bilan {APPEAL_MAX_LENGTH} belgi — qisqaroq yozing."
                )
                return
            await _submit_appeal(context.bot, user, block, text)
            return

    # Oddiy xabar/buyruq: bloklangani haqida eslatma (bot spamga aylanmasligi uchun
    # bir foydalanuvchiga daqiqada ko'pi bilan bitta)
    if now - _last_block_notice.get(user.id, 0.0) < BLOCK_NOTICE_COOLDOWN_SECONDS:
        return
    _last_block_notice[user.id] = now
    notice, markup = build_block_notice(block.get("reason") or "")
    await message.reply_text(notice, reply_markup=markup)


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

        db.upsert_connection(
            owner_user_id=conn.user.id,
            business_connection_id=conn.id,
            can_reply=can_reply,
            is_enabled=conn.is_enabled,
            can_edit_bio=can_edit_bio,
        )
        logger.info(
            "business account %s (owner=%s, can_reply=%s, can_edit_bio=%s)",
            "connected" if conn.is_enabled else "disconnected",
            conn.user.id,
            can_reply,
            can_edit_bio,
        )
        try:
            if conn.is_enabled:
                await context.bot.send_message(
                    chat_id=conn.user_chat_id,
                    text="\u2705 Akkountingiz ulandi! Panelni ochish uchun /start yozing.",
                )
            else:
                await context.bot.send_message(
                    chat_id=conn.user_chat_id,
                    text="Akkount uzildi. Avtojavob endi ishlamaydi.",
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

        # Bu SIZNING (akkaunt egasining) o'zi yozgan xabari — botlarga emas,
        # mijozlarga javob berishimiz kerak, shuning uchun o'tkazib yuboramiz.
        if bm.from_user and bm.from_user.id == owner_id:
            return

        settings = db.get_settings(owner_id)

        now = datetime.now(TASHKENT_TZ)
        now_minutes = now.hour * 60 + now.minute
        sleeping = settings.get("sleep_mode_enabled") and is_within_sleep_window(
            now_minutes, settings.get("sleep_start_minutes", 0), settings.get("sleep_end_minutes", 0)
        )

        if sleeping:
            reply_text = settings.get("sleep_reply_text") or DEFAULT_SLEEP_MESSAGE
        elif settings["offline"]:
            reply_text = settings["auto_reply_text"]
        else:
            return

        if bm.from_user and bm.from_user.is_bot:
            return

        chat_id = bm.chat.id

        # Cooldown huquqini YUBORISHDAN OLDIN atomik band qilamiz (bitta SQL).
        # Oldingi "tekshir -> yubor -> belgila" ketma-ketligida ikkita xabar
        # (yoki ikkita instance) bir vaqtda kelsa, ikkalasi ham "cooldown yo'q"
        # deb ko'rib, ikki marta javob yuborishi mumkin edi.
        claimed_at = db.try_claim_reply(owner_id, chat_id, settings["cooldown_hours"])
        if claimed_at is None:
            return  # cooldown hali tugamagan

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=reply_text,
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
        logger.info("auto reply sent (owner=%s, chat=%s, sleeping=%s)", owner_id, chat_id, sleeping)


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()

    # Faqat oddiy `message` yangilanishlari (bot bilan shaxsiy chat): business_message
    # (mijozlarning xabarlari), tahrirlangan xabarlar va kanal postlari handlerlarga
    # tushmasligi uchun. Aks holda har bir mijoz "foydalanuvchi" bo'lib bazaga yozilib,
    # reklama ro'yxatiga kirib qolardi.
    only_messages = filters.UpdateType.MESSAGE

    # Bloklangan foydalanuvchini eng birinchi to'xtatadi (qolgan hamma handlerdan oldin)
    app.add_handler(TypeHandler(Update, block_gate), group=-2)

    app.add_handler(CommandHandler("start", cmd_start, filters=only_messages))
    app.add_handler(CommandHandler("help", cmd_help, filters=only_messages))
    app.add_handler(CommandHandler("stats", cmd_stats, filters=only_messages))
    app.add_handler(CommandHandler("block", cmd_block, filters=only_messages))
    app.add_handler(CommandHandler("unblock", cmd_unblock, filters=only_messages))
    app.add_handler(CommandHandler("blocked", cmd_blocked, filters=only_messages))
    app.add_handler(CommandHandler("reklama", cmd_reklama, filters=only_messages))
    app.add_handler(CommandHandler("reklama_status", cmd_reklama_status, filters=only_messages))
    app.add_handler(CommandHandler("reklama_retry", cmd_reklama_retry, filters=only_messages))
    app.add_handler(CommandHandler("cancel", cmd_cancel, filters=only_messages))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & only_messages, on_text))
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
        # Server qayta ishga tushganda yarim qolgan reklamalarni davom ettirish
        app.job_queue.run_once(_resume_broadcasts_job_callback, when=5)
        # Server 00:05 da o'chiq bo'lgan bo'lsa, o'tkazib yuborilgan BIO yangilanishini yetkazish
        app.job_queue.run_once(bio_startup_job, when=10)
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
