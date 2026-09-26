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

import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

import db

load_dotenv()

BOT_TOKEN = os.environ["BOT_TOKEN"]
BOT_USERNAME = os.environ.get("BOT_USERNAME", "bot_username_bu_yerga")

# owner_user_id -> "cooldown" | "text"  (panel orqali nimani tahrirlayotgani)
pending_settings_action: dict[int, str] = {}

HOW_CONNECT_TEXT = (
    "Ulash uchun kodga yoki parolga ehtiyoj yo'q — bu Telegramning o'z, rasmiy "
    "funksiyasi orqali ishlaydi:\n\n"
    "1. Telegram ilovangizda: Sozlamalar \u2192 Telegram Business (yoki \"Chat Automation\")\n"
    "2. \"Chatbots\" bo'limiga kiring\n"
    f"3. Bu botning username'ini kiriting: @{BOT_USERNAME}\n"
    "4. \"Reply to messages\" (xabarlarga javob berish) ruxsatini yoqing\n\n"
    "Ulangach, shu yerga qaytib /start yozing \u2014 panel avtomatik ochiladi."
)


# ---------------------------------------------------------------------------
# Menyu va panel
# ---------------------------------------------------------------------------
def main_menu_markup(owner_id: int):
    conn = db.get_connection(owner_id)
    rows = []
    if conn and conn["is_enabled"]:
        rows.append([InlineKeyboardButton("\U0001F39B Panelni ochish", callback_data="open_panel")])
    else:
        rows.append([InlineKeyboardButton("\u2139\uFE0F Qanday ulash mumkin?", callback_data="how_connect")])
    return InlineKeyboardMarkup(rows)


def build_panel(owner_id: int):
    s = db.get_settings(owner_id)
    status_line = "\U0001F534 OFLAYN" if s["offline"] else "\U0001F7E2 ONLAYN"
    toggle_label = "\U0001F7E2 Onlaynga o'tish" if s["offline"] else "\U0001F534 Oflaynga o'tish"

    text = (
        "\U0001F39B Sizning panelingiz\n\n"
        f"Holat: {status_line}\n"
        f"Cooldown: {s['cooldown_hours']} soat\n"
        f"Xabar: {s['auto_reply_text']}"
    )
    keyboard = [
        [InlineKeyboardButton(toggle_label, callback_data="toggle_status")],
        [InlineKeyboardButton("\u23F1 Cooldownni o'zgartirish", callback_data="edit_cooldown")],
        [InlineKeyboardButton("\U0001F4DD Xabar matnini o'zgartirish", callback_data="edit_text")],
        [InlineKeyboardButton("\u2B05\uFE0F Orqaga", callback_data="back")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Buyruq va tugmalar
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    conn = db.get_connection(owner_id)
    if conn and conn["is_enabled"]:
        text, markup = build_panel(owner_id)
        await update.message.reply_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(HOW_CONNECT_TEXT, reply_markup=main_menu_markup(owner_id))


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    owner_id = query.from_user.id
    await query.answer()
    data = query.data

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

    if data == "toggle_status":
        s = db.get_settings(owner_id)
        db.update_settings(owner_id, offline=not s["offline"])

    elif data == "edit_cooldown":
        pending_settings_action[owner_id] = "cooldown"
        await query.message.reply_text("Yangi cooldown qiymatini soatlarda yuboring (masalan: 2):")
        return

    elif data == "edit_text":
        pending_settings_action[owner_id] = "text"
        await query.message.reply_text("Yangi avtojavob matnini yuboring:")
        return

    text, markup = build_panel(owner_id)
    await query.edit_message_text(text, reply_markup=markup)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.effective_user.id
    action = pending_settings_action.get(owner_id)
    if action is None:
        return  # panelga aloqasi yo'q oddiy xabar

    value = update.message.text.strip()

    if action == "cooldown":
        try:
            hours = float(value)
        except ValueError:
            await update.message.reply_text("Noto'g'ri format. Raqam yuboring, masalan: 2")
            return
        db.update_settings(owner_id, cooldown_hours=hours)

    elif action == "text":
        db.update_settings(owner_id, auto_reply_text=value)

    pending_settings_action.pop(owner_id, None)
    text, markup = build_panel(owner_id)
    await update.message.reply_text("Yangilandi.")
    await update.message.reply_text(text, reply_markup=markup)


# ---------------------------------------------------------------------------
# Business connection va business message (asosiy avtojavob logikasi)
# ---------------------------------------------------------------------------
async def on_raw_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Ulanish/uzilish/huquq o'zgarishi
    if update.business_connection:
        conn = update.business_connection

        can_reply = getattr(conn, "can_reply", None)
        rights = getattr(conn, "rights", None)
        if can_reply is None and rights is not None:
            can_reply = bool(getattr(rights, "can_reply", False))
        if can_reply is None:
            can_reply = True

        db.upsert_connection(
            owner_user_id=conn.user.id,
            business_connection_id=conn.id,
            can_reply=can_reply,
            is_enabled=conn.is_enabled,
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
        except Exception:
            pass
        return

    # Mijozdan kelgan xabar
    bm = update.business_message
    if bm is not None:
        connection = db.get_connection_by_business_id(bm.business_connection_id)
        if connection is None or not connection["is_enabled"] or not connection["can_reply"]:
            return

        owner_id = connection["owner_user_id"]
        settings = db.get_settings(owner_id)
        if not settings["offline"]:
            return

        if bm.from_user and bm.from_user.is_bot:
            return

        chat_id = bm.chat.id
        if db.already_replied_recently(owner_id, chat_id):
            return

        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=settings["auto_reply_text"],
                business_connection_id=bm.business_connection_id,
            )
            db.mark_replied(owner_id, chat_id)
        except Exception as e:
            print(f"[bot] avtojavob xatosi owner={owner_id}: {e}")


def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    # Alohida guruhda — business_connection/business_message'larni hech narsaga
    # to'sqinlik qilmasdan tinglaydi.
    app.add_handler(TypeHandler(Update, on_raw_update), group=1)
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
    import asyncio

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
    print("Bot ishga tushdi. Foydalanuvchilar /start yozishi mumkin.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)
