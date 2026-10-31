"""
Ko'p tillilik (uz / en / ru). Sof modul: muhit o'zgaruvchilari va bazaga bog'liq emas.

Foydalanish: `t(lang, "kalit", nom=qiymat)`. Noma'lum til yoki yo'q kalit bo'lsa o'zbekchaga
qaytadi (bot hech qachon yiqilmasin). Admin-only matnlar (/users, /stats, reklama...) bu yerda
emas — ular o'zbekcha qoladi.
"""

from __future__ import annotations

LANGS = ("uz", "en", "ru")
DEFAULT_LANG = "uz"
LANG_NAMES = {"uz": "\U0001F1FA\U0001F1FF O'zbekcha", "en": "\U0001F1EC\U0001F1E7 English", "ru": "\U0001F1F7\U0001F1FA Русский"}


def normalize_lang(lang) -> str:
    return lang if lang in LANGS else DEFAULT_LANG


def is_lang(lang) -> bool:
    return lang in LANGS


def _(uz: str, en: str, ru: str) -> dict:
    return {"uz": uz, "en": en, "ru": ru}


# Emoji kodlari matn ichida to'g'ridan-to'g'ri yozilgan (UTF-8).
T: dict[str, dict] = {
    # ---------------- umumiy ----------------
    "lang_pick": _(
        "\U0001F310 Tilni tanlang / Choose your language / Выберите язык",
        "\U0001F310 Tilni tanlang / Choose your language / Выберите язык",
        "\U0001F310 Tilni tanlang / Choose your language / Выберите язык",
    ),
    "lang_changed": _("✅ Til o'zgartirildi: O'zbekcha", "✅ Language changed: English", "✅ Язык изменён: Русский"),
    "btn_language": _("\U0001F310 Til: O'zbekcha", "\U0001F310 Language: English", "\U0001F310 Язык: Русский"),
    "btn_back": _("⬅️ Orqaga", "⬅️ Back", "⬅️ Назад"),
    "btn_enable": _("✅ Yoqish", "✅ Enable", "✅ Включить"),
    "btn_disable": _("❌ O'chirish", "❌ Disable", "❌ Выключить"),
    "status_on": _("\U0001F7E2 Yoqilgan", "\U0001F7E2 On", "\U0001F7E2 Включено"),
    "status_off": _("O'chirilgan", "Off", "Выключено"),
    "saved": _("✅ Saqlandi.", "✅ Saved.", "✅ Сохранено."),
    "saved_plain": _("Saqlandi.", "Saved.", "Сохранено."),
    "updated": _("Yangilandi.", "Updated.", "Обновлено."),
    "cancelled": _("Bekor qilindi.", "Cancelled.", "Отменено."),
    "no_permission": _("Ruxsat yo'q.", "No permission.", "Нет доступа."),
    "bad_button": _("Noto'g'ri tugma.", "Invalid button.", "Неверная кнопка."),
    "main_menu": _("Bosh menyu:", "Main menu:", "Главное меню:"),
    "cancel_hint": _("Bekor qilish: /cancel", "To cancel: /cancel", "Отмена: /cancel"),
    # ---------------- ulash / start ----------------
    "how_connect": _(
        "\U0001F517 Akkountni ulash — qadamma-qadam\n\n"
        "1️⃣ Telegram ilovasida Sozlamalar (Settings) bo'limini oching.\n\n"
        "2️⃣ Profilingiz — \"My Profile\" (Mening profilim) bo'limiga kiring.\n\n"
        "3️⃣ \"Chat Automations\" (Chat avtomatlashtirish) ni tanlang.\n\n"
        "4️⃣ Bot username'ini kiriting: @{bot}\n"
        "   Ro'yxatda chiqqach, ustiga bosib tanlang.\n\n"
        "5️⃣ Chatlarga ruxsat so'ralganda:\n"
        "   • \"All 1-to-1 Chats\" — barcha shaxsiy yozishmalarga javob beradi (tavsiya etiladi)\n"
        "   • \"Only Selected Chats\" — faqat o'zingiz tanlagan suhbatlarga\n\n"
        "6️⃣ \"Reply to messages\" (xabarlarga javob berish) ruxsatini albatta yoqing.\n"
        "   Busiz bot xabarlarni ko'radi, lekin javob yubora olmaydi.\n\n"
        "7️⃣ Tasdiqlang (Add / Save).\n\n"
        "✅ Ulangach, bot sizga xabar yuboradi. Shu yerga qaytib /start yozing — keyingi qadam ochiladi.\n\n"
        "ℹ️ Menyu nomlari Telegram versiyasiga qarab biroz farq qilishi mumkin.",
        "\U0001F517 Connecting your account — step by step\n\n"
        "1️⃣ Open Settings in the Telegram app.\n\n"
        "2️⃣ Go to your profile — \"My Profile\".\n\n"
        "3️⃣ Choose \"Chat Automations\".\n\n"
        "4️⃣ Enter the bot's username: @{bot}\n"
        "   When it appears in the list, tap it to select.\n\n"
        "5️⃣ When asked which chats to allow:\n"
        "   • \"All 1-to-1 Chats\" — replies in all private chats (recommended)\n"
        "   • \"Only Selected Chats\" — only the chats you pick\n\n"
        "6️⃣ Be sure to enable the \"Reply to messages\" permission.\n"
        "   Without it the bot can see messages but cannot reply.\n\n"
        "7️⃣ Confirm (Add / Save).\n\n"
        "✅ Once connected, the bot will message you. Come back here and send /start — the next step will open.\n\n"
        "ℹ️ Menu names may differ slightly depending on your Telegram version.",
        "\U0001F517 Подключение аккаунта — шаг за шагом\n\n"
        "1️⃣ Откройте Настройки (Settings) в приложении Telegram.\n\n"
        "2️⃣ Зайдите в свой профиль — \"My Profile\" (Мой профиль).\n\n"
        "3️⃣ Выберите \"Chat Automations\" (Автоматизация чатов).\n\n"
        "4️⃣ Введите username бота: @{bot}\n"
        "   Когда он появится в списке, нажмите на него.\n\n"
        "5️⃣ Когда спросят, каким чатам разрешить доступ:\n"
        "   • \"All 1-to-1 Chats\" — отвечает во всех личных чатах (рекомендуется)\n"
        "   • \"Only Selected Chats\" — только в выбранных вами чатах\n\n"
        "6️⃣ Обязательно включите разрешение \"Reply to messages\" (отвечать на сообщения).\n"
        "   Без него бот видит сообщения, но не может отвечать.\n\n"
        "7️⃣ Подтвердите (Add / Save).\n\n"
        "✅ После подключения бот напишет вам. Вернитесь сюда и отправьте /start — откроется следующий шаг.\n\n"
        "ℹ️ Названия пунктов меню могут немного отличаться в зависимости от версии Telegram.",
    ),
    "gate_text": _(
        "\U0001F512 Botdan foydalanish uchun avval kanalimizga obuna bo'ling.\n\n"
        "Obuna bo'lgach, pastdagi \"✅ Tekshirish\" tugmasini bosing.",
        "\U0001F512 To use the bot, please subscribe to our channel first.\n\n"
        "After subscribing, press the \"✅ Check\" button below.",
        "\U0001F512 Чтобы пользоваться ботом, сначала подпишитесь на наш канал.\n\n"
        "После подписки нажмите кнопку \"✅ Проверить\" ниже.",
    ),
    "gate_lost": _(
        "\U0001F512 Kanalimizdan obunangiz topilmadi, shuning uchun botning barcha funksiyalari "
        "(avtojavob, AI-Yordamchi, ism soati, BIO hisoblagich) vaqtincha to'xtatildi.\n\n"
        "Kanalga obuna bo'ling va \"✅ Tekshirish\" tugmasini bosing — hammasi qayta ishlaydi.",
        "\U0001F512 We couldn't find your subscription to our channel, so all bot features "
        "(auto-reply, AI Assistant, name clock, BIO countdown) are temporarily paused.\n\n"
        "Subscribe to the channel and press \"✅ Check\" — everything will work again.",
        "\U0001F512 Ваша подписка на наш канал не найдена, поэтому все функции бота "
        "(автоответ, AI-помощник, часы в имени, BIO-счётчик) временно приостановлены.\n\n"
        "Подпишитесь на канал и нажмите \"✅ Проверить\" — всё снова заработает.",
    ),
    "gate_btn_channel": _("\U0001F4E2 Kanalga o'tish", "\U0001F4E2 Go to channel", "\U0001F4E2 Перейти в канал"),
    "gate_btn_check": _("✅ Tekshirish", "✅ Check", "✅ Проверить"),
    "gate_ok": _("✅ Obuna tasdiqlandi!", "✅ Subscription confirmed!", "✅ Подписка подтверждена!"),
    "gate_fail": _(
        "❌ Siz hali kanalga obuna bo'lmagansiz. Avval obuna bo'lib, keyin qayta bosing.",
        "❌ You haven't subscribed to the channel yet. Subscribe first, then press again.",
        "❌ Вы ещё не подписались на канал. Сначала подпишитесь, затем нажмите снова.",
    ),
    "referral_joined": _(
        "\U0001F389 Sizning havolangiz orqali yangi odam botga qo'shildi!",
        "\U0001F389 A new person joined the bot through your link!",
        "\U0001F389 По вашей ссылке в бота пришёл новый человек!",
    ),
    "greeting_connected": _(
        "Assalomu alaykum! Kerakli bo'limni tanlang:",
        "Hello! Choose a section:",
        "Здравствуйте! Выберите нужный раздел:",
    ),
    "greeting_new": _(
        "Assalomu alaykum!\n\n"
        "Bu bot orqali o'z Telegram akkountingizni ulab, siz oflayn bo'lganingizda "
        "kiruvchi shaxsiy xabarlarga avtomatik javob berishni sozlashingiz mumkin.",
        "Hello!\n\n"
        "With this bot you can connect your own Telegram account and set up automatic replies "
        "to incoming private messages while you are offline.",
        "Здравствуйте!\n\n"
        "С помощью этого бота вы можете подключить свой аккаунт Telegram и настроить автоответ "
        "на входящие личные сообщения, пока вы офлайн.",
    ),
    "btn_open_panel": _("\U0001F39B Panelni ochish", "\U0001F39B Open panel", "\U0001F39B Открыть панель"),
    "btn_how_connect": _("ℹ️ Qanday ulash mumkin?", "ℹ️ How to connect?", "ℹ️ Как подключить?"),
    "btn_referral": _("\U0001F381 Referal bonus", "\U0001F381 Referral bonus", "\U0001F381 Реферальный бонус"),
    "btn_support": _("\U0001F6DF Qo'llab-quvvatlash xizmati", "\U0001F6DF Support", "\U0001F6DF Служба поддержки"),
    # ---------------- yordam ----------------
    "help": _(
        "\U0001F916 AutoReplyer — siz oflayn bo'lganingizda Telegram akkountingizdagi "
        "shaxsiy xabarlarga avtomatik javob beradi.\n\n"
        "Imkoniyatlar:\n"
        "• Oflayn avtojavob (cooldown bilan — bir chatga qayta-qayta yozmaydi)\n"
        "• Uxlayapman rejimi — tungi vaqt oralig'ida alohida javob\n"
        "• BIO hisoblagich — Yangi yil, Navro'z yoki tug'ilgan kuningizgacha qolgan kunlar\n"
        "• Referal bonus\n\n"
        "Buyruqlar:\n"
        "/start — bosh menyu va panel\n"
        "/help — shu yo'riqnoma\n\n"
        "Akkountni ulash: /start yozing va \"Qanday ulash mumkin?\" tugmasini bosing.",
        "\U0001F916 AutoReplyer — automatically replies to private messages in your Telegram account "
        "while you are offline.\n\n"
        "Features:\n"
        "• Offline auto-reply (with a cooldown — it won't write to one chat again and again)\n"
        "• Sleep mode — a separate reply during your night hours\n"
        "• BIO countdown — days left until New Year, Navruz or your birthday\n"
        "• Referral bonus\n\n"
        "Commands:\n"
        "/start — main menu and panel\n"
        "/help — this guide\n\n"
        "To connect your account: send /start and press \"How to connect?\".",
        "\U0001F916 AutoReplyer — автоматически отвечает на личные сообщения в вашем аккаунте Telegram, "
        "пока вы офлайн.\n\n"
        "Возможности:\n"
        "• Офлайн-автоответ (с кулдауном — не пишет в один чат снова и снова)\n"
        "• Режим сна — отдельный ответ в ночное время\n"
        "• BIO-счётчик — сколько дней осталось до Нового года, Навруза или вашего дня рождения\n"
        "• Реферальный бонус\n\n"
        "Команды:\n"
        "/start — главное меню и панель\n"
        "/help — эта справка\n\n"
        "Чтобы подключить аккаунт: отправьте /start и нажмите \"Как подключить?\".",
    ),
    # ---------------- qo'llab-quvvatlash ----------------
    "support_text": _(
        "\U0001F6DF Qo'llab-quvvatlash xizmati\n\n"
        "Savolingiz yoki taklifingiz bo'lsa, bemalol yozing — biz sizni eshitamiz.\n\n"
        "• Kanal — yangiliklar va e'lonlar\n"
        "• Admin bilan bog'lanish — shaxsiy yozishish\n"
        "• Fikr/taklif yozish — shu bot orqali to'g'ridan-to'g'ri adminga yuboriladi",
        "\U0001F6DF Support\n\n"
        "If you have a question or suggestion, feel free to write — we are listening.\n\n"
        "• Channel — news and announcements\n"
        "• Contact the admin — a private chat\n"
        "• Write feedback — sent directly to the admin through this bot",
        "\U0001F6DF Служба поддержки\n\n"
        "Если у вас есть вопрос или предложение, смело пишите — мы вас слушаем.\n\n"
        "• Канал — новости и объявления\n"
        "• Связаться с админом — личная переписка\n"
        "• Написать отзыв — отправляется админу напрямую через этого бота",
    ),
    "support_btn_channel": _("\U0001F4E2 Kanalimiz", "\U0001F4E2 Our channel", "\U0001F4E2 Наш канал"),
    "support_btn_admin": _("\U0001F464 Admin bilan bog'lanish", "\U0001F464 Contact the admin", "\U0001F464 Связаться с админом"),
    "support_btn_feedback": _("✍️ Fikr / taklif yozish", "✍️ Write feedback", "✍️ Написать отзыв"),
    "feedback_prompt": _(
        "✍️ Fikr yoki taklifingizni bitta xabar qilib yozing — u adminga yetkaziladi.\n"
        "Bekor qilish: /cancel",
        "✍️ Write your feedback or suggestion as a single message — it will be delivered to the admin.\n"
        "To cancel: /cancel",
        "✍️ Напишите свой отзыв или предложение одним сообщением — оно будет передано админу.\n"
        "Отмена: /cancel",
    ),
    "feedback_too_long": _(
        "Xabar juda uzun ({n} belgi). Iltimos, {max} belgidan qisqaroq yozing.",
        "The message is too long ({n} characters). Please keep it under {max} characters.",
        "Сообщение слишком длинное ({n} симв.). Пожалуйста, напишите короче {max} символов.",
    ),
    "feedback_rate": _(
        "⏳ Juda ko'p xabar yubordingiz. Iltimos, birozdan keyin qayta urinib ko'ring.",
        "⏳ You have sent too many messages. Please try again a bit later.",
        "⏳ Вы отправили слишком много сообщений. Пожалуйста, повторите попытку чуть позже.",
    ),
    "feedback_fail": _(
        "Hozir xabaringizni yetkazib bo'lmadi. Keyinroq qayta urinib ko'ring.",
        "Your message could not be delivered right now. Please try again later.",
        "Сейчас не удалось доставить ваше сообщение. Попробуйте позже.",
    ),
    "feedback_thanks": _(
        "✅ Rahmat! Fikringiz adminga yuborildi.",
        "✅ Thank you! Your feedback was sent to the admin.",
        "✅ Спасибо! Ваш отзыв отправлен админу.",
    ),
    "admin_reply_to_user": _(
        "\U0001F4AC Admin javobi:\n\n{text}",
        "\U0001F4AC Reply from the admin:\n\n{text}",
        "\U0001F4AC Ответ админа:\n\n{text}",
    ),
    # ---------------- referal ----------------
    "ref_view": _(
        "\U0001F381 Referal bonus\n\n"
        "Siz orqali botga ulangan do'stlar soni: {count}\n\n"
        "Shaxsiy havolangiz:\n{link}\n\n"
        "Do'stlaringiz shu havola orqali botga kirsa, ular siz taklif qilgan hisoblanadi.",
        "\U0001F381 Referral bonus\n\n"
        "Friends who joined through you: {count}\n\n"
        "Your personal link:\n{link}\n\n"
        "If your friends enter the bot through this link, they count as invited by you.",
        "\U0001F381 Реферальный бонус\n\n"
        "Друзей, пришедших через вас: {count}\n\n"
        "Ваша личная ссылка:\n{link}\n\n"
        "Если друзья зайдут в бота по этой ссылке, они будут считаться приглашёнными вами.",
    ),
    "ref_share_text": _(
        "Oflaynda ham javob beradigan Telegram botdan foydalaning:",
        "Try this Telegram bot that replies for you even when you're offline:",
        "Попробуйте Telegram-бота, который отвечает за вас, даже когда вы офлайн:",
    ),
    "ref_btn_share": _("\U0001F4E4 Havolani ulashish", "\U0001F4E4 Share the link", "\U0001F4E4 Поделиться ссылкой"),
    # ---------------- panel ----------------
    "panel": _(
        "\U0001F39B Sizning panelingiz\n\n"
        "Holat: {status}\n"
        "Cooldown: {cooldown}\n"
        "Xabar: {message}\n"
        "Uxlayapman rejimi: {sleep}\n"
        "AI-Yordamchi: {ai}",
        "\U0001F39B Your panel\n\n"
        "Status: {status}\n"
        "Cooldown: {cooldown}\n"
        "Message: {message}\n"
        "Sleep mode: {sleep}\n"
        "AI Assistant: {ai}",
        "\U0001F39B Ваша панель\n\n"
        "Статус: {status}\n"
        "Кулдаун: {cooldown}\n"
        "Сообщение: {message}\n"
        "Режим сна: {sleep}\n"
        "AI-помощник: {ai}",
    ),
    "btn_autoreply": _("\U0001F680 Auto-Reply", "\U0001F680 Auto-Reply", "\U0001F680 Auto-Reply"),
    "ar_menu": _(
        "\U0001F680 Auto-Reply\n\n"
        "Avtojavob: {status}\n"
        "Cooldown: {cooldown}\n"
        "Xabar: {message}\n"
        "Uxlayapman rejimi: {sleep}\n\n"
        "Avtojavob yoqilganda (Oflayn holat) mijozlar xabariga bot siz o'rningizga javob beradi.",
        "\U0001F680 Auto-Reply\n\n"
        "Auto-reply: {status}\n"
        "Cooldown: {cooldown}\n"
        "Message: {message}\n"
        "Sleep mode: {sleep}\n\n"
        "While auto-reply is on (Offline status), the bot answers your customers' messages for you.",
        "\U0001F680 Auto-Reply\n\n"
        "Автоответ: {status}\n"
        "Кулдаун: {cooldown}\n"
        "Сообщение: {message}\n"
        "Режим сна: {sleep}\n\n"
        "Пока автоответ включён (статус «Офлайн»), бот отвечает на сообщения ваших клиентов за вас.",
    ),
    "panel_offline": _("\U0001F534 OFLAYN", "\U0001F534 OFFLINE", "\U0001F534 ОФЛАЙН"),
    "panel_online": _("\U0001F7E2 ONLAYN", "\U0001F7E2 ONLINE", "\U0001F7E2 ОНЛАЙН"),
    "panel_go_online": _("\U0001F7E2 Onlaynga o'tish", "\U0001F7E2 Go online", "\U0001F7E2 Перейти в онлайн"),
    "panel_go_offline": _("\U0001F534 Oflaynga o'tish", "\U0001F534 Go offline", "\U0001F534 Перейти в офлайн"),
    "panel_sleep_on": _("yoqilgan \U0001F634", "on \U0001F634", "включён \U0001F634"),
    "panel_sleep_off": _("o'chirilgan", "off", "выключен"),
    "panel_ai_on": _("yoqilgan \U0001F916", "on \U0001F916", "включён \U0001F916"),
    "panel_ai_off": _("o'chirilgan", "off", "выключен"),
    "panel_ai_message": _(
        "AI-Yordamchi yoqilgan (matn o'rniga AI javob beradi)",
        "AI Assistant is on (AI replies instead of the text)",
        "AI-помощник включён (вместо текста отвечает AI)",
    ),
    "btn_edit_cooldown": _("⏱ Cooldownni o'zgartirish", "⏱ Change cooldown", "⏱ Изменить кулдаун"),
    "btn_edit_text": _("\U0001F4DD Xabar matnini o'zgartirish", "\U0001F4DD Change message text", "\U0001F4DD Изменить текст сообщения"),
    "btn_bio": _("\U0001F382 BIO hisoblagich", "\U0001F382 BIO countdown", "\U0001F382 BIO-счётчик"),
    "btn_sleep": _("\U0001F634 Uxlayapman rejimi", "\U0001F634 Sleep mode", "\U0001F634 Режим сна"),
    "btn_ai": _("\U0001F916 AI-Yordamchi", "\U0001F916 AI Assistant", "\U0001F916 AI-помощник"),
    "btn_name_clock": _("\U0001F552 Ism soati", "\U0001F552 Name clock", "\U0001F552 Часы в имени"),
    "cooldown_prompt": _(
        "Yangi cooldown qiymatini yuboring. Masalan:\n"
        "• 2 soat 30 daqiqa\n"
        "• 45 daqiqa\n"
        "• 1:30 (1 soat 30 daqiqa)\n"
        "• 3 (shunchaki 3 soat)\n\n"
        "⚠️ 0 qabul qilinmaydi — spamning oldini olish uchun eng kami 1 daqiqa bo'lishi kerak.",
        "Send the new cooldown value. For example:\n"
        "• 2 hours 30 minutes\n"
        "• 45 minutes\n"
        "• 1:30 (1 hour 30 minutes)\n"
        "• 3 (just 3 hours)\n\n"
        "⚠️ 0 is not accepted — to prevent spam it must be at least 1 minute.",
        "Отправьте новое значение кулдауна. Например:\n"
        "• 2 часа 30 минут\n"
        "• 45 минут\n"
        "• 1:30 (1 час 30 минут)\n"
        "• 3 (просто 3 часа)\n\n"
        "⚠️ 0 не принимается — для защиты от спама минимум 1 минута.",
    ),
    "cooldown_bad": _(
        "Noto'g'ri format yoki 0. Spamning oldini olish uchun cooldown 0 bo'lishi mumkin emas "
        "— eng kami 1 daqiqa kiriting. Masalan: '2 soat 30 daqiqa', '45 daqiqa', '1 daqiqa', '1:30' yoki '3'",
        "Invalid format or 0. To prevent spam the cooldown cannot be 0 "
        "— enter at least 1 minute. For example: '2 hours 30 minutes', '45 minutes', '1 minute', '1:30' or '3'",
        "Неверный формат или 0. Для защиты от спама кулдаун не может быть 0 "
        "— введите минимум 1 минуту. Например: '2 часа 30 минут', '45 минут', '1 минута', '1:30' или '3'",
    ),
    "text_prompt": _(
        "Yangi avtojavob matnini yuboring:",
        "Send the new auto-reply text:",
        "Отправьте новый текст автоответа:",
    ),
    "cd_always": _(
        "Har doim javob beradi (cooldown yo'q)",
        "Always replies (no cooldown)",
        "Отвечает всегда (без кулдауна)",
    ),
    "unit_hour": _("{n} soat", "{n} h", "{n} ч"),
    "unit_minute": _("{n} daqiqa", "{n} min", "{n} мин"),
    # ---------------- uxlash rejimi ----------------
    "sleep_menu": _(
        "\U0001F634 Uxlayapman rejimi\n\n"
        "Holat: {status}\n"
        "Vaqt oralig'i: {range}\n"
        "Xabar: {text}\n\n"
        "Bu rejim yoqilgan bo'lsa, belgilangan vaqt oralig'ida (hatto \"Onlayn\" "
        "holatida ham) kiruvchi xabarlarga shu maxsus matn bilan avtomatik javob beriladi.",
        "\U0001F634 Sleep mode\n\n"
        "Status: {status}\n"
        "Time range: {range}\n"
        "Message: {text}\n\n"
        "When this mode is on, incoming messages during the set time range (even while "
        "you are \"Online\") get this special text as an automatic reply.",
        "\U0001F634 Режим сна\n\n"
        "Статус: {status}\n"
        "Интервал: {range}\n"
        "Сообщение: {text}\n\n"
        "Когда режим включён, на входящие сообщения в заданный интервал (даже в статусе "
        "\"Онлайн\") автоматически отвечает этот особый текст.",
    ),
    "sleep_status_on": _("\U0001F634 Yoqilgan", "\U0001F634 On", "\U0001F634 Включён"),
    "btn_sleep_time": _("⏰ Vaqtni o'zgartirish", "⏰ Change time", "⏰ Изменить время"),
    "sleep_time_prompt": _(
        "Uxlash vaqt oralig'ini yuboring (masalan: 23:00-07:00):",
        "Send the sleep time range (for example: 23:00-07:00):",
        "Отправьте интервал времени сна (например: 23:00-07:00):",
    ),
    "sleep_time_bad": _(
        "Noto'g'ri format. Masalan: 23:00-07:00",
        "Invalid format. For example: 23:00-07:00",
        "Неверный формат. Например: 23:00-07:00",
    ),
    "sleep_text_prompt": _(
        "Uxlash vaqtida yuboriladigan xabarni kiriting:",
        "Enter the message to send during sleep time:",
        "Введите сообщение, которое будет отправляться во время сна:",
    ),
    # ---------------- BIO hisoblagich ----------------
    "bio_no_perm": _(
        "\U0001F382 BIO hisoblagich\n\n"
        "Bu funksiya uchun \"Edit bio\" (BIO'ni tahrirlash) ruxsati kerak.\n\n"
        "Telegram: Sozlamalar → My Profile → Chat Automations → botni bosing → "
        "\"Edit bio\" ruxsatini yoqing. Keyin shu tugmani qayta bosing.",
        "\U0001F382 BIO countdown\n\n"
        "This feature needs the \"Edit bio\" permission.\n\n"
        "Telegram: Settings → My Profile → Chat Automations → tap the bot → "
        "enable the \"Edit bio\" permission. Then press this button again.",
        "\U0001F382 BIO-счётчик\n\n"
        "Для этой функции нужно разрешение \"Edit bio\" (изменение BIO).\n\n"
        "Telegram: Настройки → My Profile → Chat Automations → нажмите на бота → "
        "включите разрешение \"Edit bio\". Затем снова нажмите эту кнопку.",
    ),
    "bio_menu": _(
        "\U0001F382 BIO hisoblagich\n\n{status}\n\nBIO'ingizda avtomatik shu turdagi hisoblagich ko'rsatilsin:",
        "\U0001F382 BIO countdown\n\n{status}\n\nChoose which countdown to show automatically in your BIO:",
        "\U0001F382 BIO-счётчик\n\n{status}\n\nВыберите, какой счётчик автоматически показывать в вашем BIO:",
    ),
    "bio_status_on": _(
        "Yoqilgan: {label}\nHozirgi matn: {preview}",
        "On: {label}\nCurrent text: {preview}",
        "Включено: {label}\nТекущий текст: {preview}",
    ),
    "bio_no_date": _("(sana kiritilmagan)", "(no date entered)", "(дата не указана)"),
    "bio_status_off": _("Hozircha o'chirilgan.", "Currently off.", "Сейчас выключено."),
    "bio_event_new_year": _("Yangi yil", "New Year", "Новый год"),
    "bio_event_navroz": _("Navro'z", "Navruz", "Навруз"),
    "bio_event_birthday": _("Tug'ilgan kunim", "My birthday", "Мой день рождения"),
    "btn_bio_new_year": _("\U0001F386 Yangi yilgacha", "\U0001F386 Until New Year", "\U0001F386 До Нового года"),
    "btn_bio_navroz": _("\U0001F33F Navro'zgacha", "\U0001F33F Until Navruz", "\U0001F33F До Навруза"),
    "btn_bio_birthday": _("\U0001F382 Tug'ilgan kunimgacha", "\U0001F382 Until my birthday", "\U0001F382 До моего дня рождения"),
    "bio_birthday_prompt": _(
        "Tug'ilgan kuningizni kun.oy formatida yuboring (masalan: 15.03 — 15-mart):",
        "Send your birthday in day.month format (for example: 15.03 — March 15):",
        "Отправьте дату рождения в формате день.месяц (например: 15.03 — 15 марта):",
    ),
    "bio_birthday_bad": _(
        "Noto'g'ri format. Kun.oy ko'rinishida yuboring, masalan: 15.03",
        "Invalid format. Send it as day.month, for example: 15.03",
        "Неверный формат. Отправьте в виде день.месяц, например: 15.03",
    ),
    "bio_failed": _(
        "⚠️ BIO yangilanmadi: {info}",
        "⚠️ BIO was not updated: {info}",
        "⚠️ BIO не обновлено: {info}",
    ),
    "bio_err_not_connected": _("Akkount ulanmagan.", "Account is not connected.", "Аккаунт не подключён."),
    "bio_err_no_perm": _(
        "\"Edit bio\" ruxsati yoqilmagan.",
        "The \"Edit bio\" permission is not enabled.",
        "Разрешение \"Edit bio\" не включено.",
    ),
    "bio_err_off": _("BIO hisoblagich o'chirilgan.", "BIO countdown is off.", "BIO-счётчик выключен."),
    "bio_err_no_birthday": _(
        "Tug'ilgan kun sanasi kiritilmagan.",
        "Birthday date is not entered.",
        "Дата рождения не указана.",
    ),
    # BIO matni (akkaunt BIO'siga yoziladi). {days} — son, {unit} — "kun"/"day(s)"/"дн."
    "bio_text_new_year": _("Yangi yilga {days} kun qoldi!", "{days} {unit} until New Year!", "До Нового года {days} {unit}!"),
    "bio_text_navroz": _("Navro'zga {days} kun qoldi!", "{days} {unit} until Navruz!", "До Навруза {days} {unit}!"),
    "bio_text_birthday": _("Tug'ilgan kunimga {days} kun qoldi!", "{days} {unit} until my birthday!", "До моего дня рождения {days} {unit}!"),
    "bio_today_new_year": _("Bugun yangi yil!", "Today is New Year!", "Сегодня Новый год!"),
    "bio_today_navroz": _("Bugun navro'z!", "Today is Navruz!", "Сегодня Навруз!"),
    "bio_today_birthday": _("Bugun tug'ilgan kunim!", "Today is my birthday!", "Сегодня мой день рождения!"),
    # ---------------- AI-Yordamchi ----------------
    "ai_menu": _(
        "\U0001F916 AI-Yordamchi\n\n"
        "Holat: {status}\n"
        "{usage}\n"
        "Rol: {role}\n"
        "Ma'lumot va uslub: {info}\n\n"
        "Yoqilganda, avtojavob ishlaydigan paytda (Oflayn holat yoki jadval oynasi) odatiy matn o'rniga "
        "sun'iy intellekt suhbatdoshingizga o'zi javob yozadi. Oddiy avtojavob matnlari o'chmaydi — "
        "AI o'chirilsa, kunlik limit tugasa yoki xato bo'lsa, ular ishlatiladi.\n"
        "Uxlash rejimi (Sleep Mode) vaqtida AI ishlamaydi — har doim uxlash xabaringiz yuboriladi.\n"
        "Chatga o'zingiz yozsangiz, AI shu chatda 2 soat jim turadi.",
        "\U0001F916 AI Assistant\n\n"
        "Status: {status}\n"
        "{usage}\n"
        "Role: {role}\n"
        "Info and style: {info}\n\n"
        "When on, while auto-reply is active (Offline status or a schedule window), artificial intelligence "
        "writes the reply to your contact instead of the usual text. The regular auto-reply texts are kept — "
        "they are used if AI is turned off, the daily limit runs out or an error occurs.\n"
        "During Sleep Mode the AI does not reply — your sleep message is always sent.\n"
        "If you write in a chat yourself, the AI stays silent in that chat for 2 hours.",
        "\U0001F916 AI-помощник\n\n"
        "Статус: {status}\n"
        "{usage}\n"
        "Роль: {role}\n"
        "Информация и стиль: {info}\n\n"
        "Когда включён, в моменты работы автоответа (статус Офлайн или окно расписания) вместо обычного текста "
        "собеседнику отвечает искусственный интеллект. Обычные тексты автоответа не удаляются — "
        "они используются, если AI выключен, закончился дневной лимит или произошла ошибка.\n"
        "Во время режима сна (Sleep Mode) AI не отвечает — всегда отправляется ваше сообщение о сне.\n"
        "Если вы сами напишете в чат, AI будет молчать в этом чате 2 часа.",
    ),
    "ai_usage_unlimited": _("Limit: cheklovsiz", "Limit: unlimited", "Лимит: без ограничений"),
    "ai_usage": _("Bugun: {used}/{limit} ta javob", "Today: {used}/{limit} replies", "Сегодня: {used}/{limit} ответов"),
    # ---------------- Smart FAQ ----------------
    "btn_faq": _("\U0001F4DA Smart FAQ", "\U0001F4DA Smart FAQ", "\U0001F4DA Smart FAQ"),
    "faq_menu": _(
        "\U0001F4DA SMART FAQ\n\nKo'p beriladigan savollar\n\n"
        "\U0001F4CA Saqlangan savollar: {count}/{max}\n"
        "Holat: {status}\n\n"
        "Mijoz savolingizga mos so'z yozsa, bot tayyor javobni o'zi yuboradi (AI ishlatilmaydi — tez va tejamkor). "
        "Faqat Oflayn holatda ishlaydi; uxlash vaqtida uxlash xabari ketadi.{notice}",
        "\U0001F4DA SMART FAQ\n\nFrequently Asked Questions\n\n"
        "\U0001F4CA Saved questions: {count}/{max}\n"
        "Status: {status}\n\n"
        "When a customer's message matches your keywords, the bot sends your ready answer (no AI used — fast and cheap). "
        "Works only while you are Offline; during sleep time the sleep message is sent.{notice}",
        "\U0001F4DA SMART FAQ\n\nЧасто задаваемые вопросы\n\n"
        "\U0001F4CA Сохранено вопросов: {count}/{max}\n"
        "Статус: {status}\n\n"
        "Если сообщение клиента совпадает с вашими ключевыми словами, бот отправит готовый ответ (без AI — быстро и дёшево). "
        "Работает только в статусе Офлайн; во время сна отправляется сообщение для сна.{notice}",
    ),
    "btn_faq_add": _("➕ Savol qo'shish", "➕ Add Question", "➕ Добавить вопрос"),
    "btn_faq_list": _("\U0001F4CB Savollarim", "\U0001F4CB My Questions", "\U0001F4CB Мои вопросы"),
    "btn_faq_settings": _("⚙️ Sozlamalar", "⚙️ Settings", "⚙️ Настройки"),
    "btn_faq_save": _("✅ Saqlash", "✅ Save", "✅ Сохранить"),
    "btn_faq_cancel": _("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"),
    "btn_faq_delete": _("\U0001F5D1 O'chirish", "\U0001F5D1 Delete", "\U0001F5D1 Удалить"),
    "btn_faq_entry_off": _("⏸ Vaqtincha o'chirish", "⏸ Pause", "⏸ Приостановить"),
    "btn_faq_entry_on": _("▶️ Yoqish", "▶️ Resume", "▶️ Включить"),
    "faq_q_prompt": _(
        "1/3. Savolni yozing (masalan: Yetkazib berish bormi?).\nBekor qilish: /cancel",
        "1/3. Write the question (e.g. Do you deliver?).\nCancel: /cancel",
        "1/3. Напишите вопрос (например: Есть доставка?).\nОтмена: /cancel",
    ),
    "faq_kw_prompt": _(
        "2/3. Kalit so'zlarni vergul bilan yozing (masalan: dostavka, delivery, yetkazish).\n"
        "Mijoz xabarida shu so'zlardan biri butun so'z sifatida bo'lsa, javob ketadi. "
        "So'zning turli shakllarini (dostavka, dostavkasi...) alohida yozing.\nBekor qilish: /cancel",
        "2/3. Write the keywords separated by commas (e.g. delivery, shipping, dostavka).\n"
        "If a customer's message contains one of them as a whole word, the answer is sent. "
        "Write different forms of a word (delivery, deliver...) separately.\nCancel: /cancel",
        "2/3. Напишите ключевые слова через запятую (например: доставка, delivery, dostavka).\n"
        "Если в сообщении клиента есть одно из них как целое слово, будет отправлен ответ. "
        "Разные формы слова (доставка, доставки...) пишите отдельно.\nОтмена: /cancel",
    ),
    "faq_ans_prompt": _(
        "3/3. Javob matnini yozing (eng ko'pi {max} belgi).\nBekor qilish: /cancel",
        "3/3. Write the answer text (up to {max} characters).\nCancel: /cancel",
        "3/3. Напишите текст ответа (до {max} символов).\nОтмена: /cancel",
    ),
    "faq_confirm": _(
        "Saqlashdan oldin tekshiring:\n\n❓ Savol: {q}\n\U0001F511 Kalit so'zlar: {kw}\n\U0001F4AC Javob: {a}",
        "Please check before saving:\n\n❓ Question: {q}\n\U0001F511 Keywords: {kw}\n\U0001F4AC Answer: {a}",
        "Проверьте перед сохранением:\n\n❓ Вопрос: {q}\n\U0001F511 Ключевые слова: {kw}\n\U0001F4AC Ответ: {a}",
    ),
    "faq_confirm_hint": _(
        "Pastdagi tugmalardan birini bosing: Saqlash yoki Bekor qilish.",
        "Please press one of the buttons below: Save or Cancel.",
        "Нажмите одну из кнопок ниже: Сохранить или Отмена.",
    ),
    "faq_too_long": _(
        "Matn juda uzun ({n} belgi, eng ko'pi {max}). Qisqartirib qayta yuboring.",
        "The text is too long ({n} characters, max {max}). Shorten it and send again.",
        "Текст слишком длинный ({n} симв., максимум {max}). Сократите и отправьте снова.",
    ),
    "faq_empty_text": _("Matn bo'sh bo'lmasligi kerak.", "The text can't be empty.", "Текст не должен быть пустым."),
    "faq_kw_bad": _(
        "Kalit so'zlar noto'g'ri: kamida 1 ta, ko'pi bilan {max} ta so'z/ibora kerak (har biri {len} belgigacha). "
        "Vergul bilan ajratib qayta yuboring.",
        "Invalid keywords: you need 1 to {max} words/phrases (each up to {len} characters). "
        "Separate them with commas and send again.",
        "Неверные ключевые слова: нужно от 1 до {max} слов/фраз (каждое до {len} символов). "
        "Разделите запятыми и отправьте снова.",
    ),
    "faq_saved": _("✅ Savol saqlandi.", "✅ Question saved.", "✅ Вопрос сохранён."),
    "faq_limit": _(
        "Savollar limiti to'lgan ({max} ta). Yangisini qo'shish uchun eskisini o'chiring.",
        "Question limit reached ({max}). Delete an old one to add a new one.",
        "Лимит вопросов исчерпан ({max}). Удалите старый, чтобы добавить новый.",
    ),
    "faq_cancelled": _("Bekor qilindi.", "Cancelled.", "Отменено."),
    "faq_draft_lost": _(
        "Qoralama yo'qolgan (vaqt o'tdi). Iltimos, boshidan boshlang.",
        "The draft was lost (timed out). Please start again.",
        "Черновик потерян (истекло время). Начните сначала.",
    ),
    "faq_list_empty": _(
        "Hali savol qo'shilmagan. \"➕ Savol qo'shish\" tugmasini bosing.",
        "No questions yet. Press \"➕ Add Question\".",
        "Вопросов пока нет. Нажмите «➕ Добавить вопрос».",
    ),
    "faq_list_title": _(
        "\U0001F4CB Savollarim ({count}/{max}). Ko'rish uchun tanlang:",
        "\U0001F4CB My Questions ({count}/{max}). Pick one to view:",
        "\U0001F4CB Мои вопросы ({count}/{max}). Выберите для просмотра:",
    ),
    "faq_entry_view": _(
        "❓ Savol: {q}\n\U0001F511 Kalit so'zlar: {kw}\n\U0001F4AC Javob: {a}\n\nHolat: {status}",
        "❓ Question: {q}\n\U0001F511 Keywords: {kw}\n\U0001F4AC Answer: {a}\n\nStatus: {status}",
        "❓ Вопрос: {q}\n\U0001F511 Ключевые слова: {kw}\n\U0001F4AC Ответ: {a}\n\nСтатус: {status}",
    ),
    "btn_faq_edit_q": _("✏️ Savol matnini o'zgartirish", "✏️ Edit question", "✏️ Изменить вопрос"),
    "btn_faq_edit_kw": _("\U0001F511 Kalit so'zlarni o'zgartirish", "\U0001F511 Edit keywords", "\U0001F511 Изменить ключевые слова"),
    "btn_faq_edit_ans": _("\U0001F4AC Javob matnini o'zgartirish", "\U0001F4AC Edit answer", "\U0001F4AC Изменить ответ"),
    "faq_edit_q_prompt": _(
        "✏️ Savolning yangi matnini yuboring (eng ko'pi {max} belgi).\n\nHozirgi: {cur}\n\nBekor qilish: /cancel",
        "✏️ Send the new question text (up to {max} characters).\n\nCurrent: {cur}\n\nCancel: /cancel",
        "✏️ Отправьте новый текст вопроса (до {max} символов).\n\nСейчас: {cur}\n\nОтмена: /cancel",
    ),
    "faq_edit_kw_prompt": _(
        "\U0001F511 Yangi kalit so'zlarni vergul bilan yuboring (ko'pi bilan 10 ta; eskilari almashtiriladi).\n\nHozirgi: {cur}\n\nBekor qilish: /cancel",
        "\U0001F511 Send the new keywords separated by commas (up to 10; the old ones are replaced).\n\nCurrent: {cur}\n\nCancel: /cancel",
        "\U0001F511 Отправьте новые ключевые слова через запятую (до 10; старые будут заменены).\n\nСейчас: {cur}\n\nОтмена: /cancel",
    ),
    "faq_edit_ans_prompt": _(
        "\U0001F4AC Javobning yangi matnini yuboring (eng ko'pi {max} belgi).\n\nHozirgi: {cur}\n\nBekor qilish: /cancel",
        "\U0001F4AC Send the new answer text (up to {max} characters).\n\nCurrent: {cur}\n\nCancel: /cancel",
        "\U0001F4AC Отправьте новый текст ответа (до {max} символов).\n\nСейчас: {cur}\n\nОтмена: /cancel",
    ),
    "faq_updated": _("✅ Savol yangilandi.", "✅ Question updated.", "✅ Вопрос обновлён."),
    "faq_entry_gone": _("Bu savol topilmadi.", "This question was not found.", "Этот вопрос не найден."),
    "faq_deleted": _("\U0001F5D1 Savol o'chirildi.", "\U0001F5D1 Question deleted.", "\U0001F5D1 Вопрос удалён."),
    "faq_settings": _(
        "⚙️ Smart FAQ sozlamalari\n\nHolat: {status}\n\n"
        "Ishlash tartibi: Oflayn holatda mijoz yozsa, avval Smart FAQ tekshiriladi. Aniq va yagona mos javob topilsa — "
        "o'sha yuboriladi. Aks holda AI-Yordamchi (yoqilgan bo'lsa) yoki oddiy avtojavob ishlaydi.\n\n"
        "Bot ehtiyotkor: inkor so'zi bor xabar (masalan \"yo'qmi\"), bir nechta javob bir xil darajada mos kelsa yoki "
        "mos kelish aniq bo'lmasa — FAQ javobi yuborilmaydi.",
        "⚙️ Smart FAQ settings\n\nStatus: {status}\n\n"
        "How it works: while you're Offline and a customer writes, Smart FAQ is checked first. If one clear match is found, "
        "that answer is sent. Otherwise the AI Assistant (if on) or the regular auto-reply works.\n\n"
        "The bot is careful: a message with a negation (e.g. \"no\", \"not\"), several equally good matches, or an unclear "
        "match gets no FAQ answer.",
        "⚙️ Настройки Smart FAQ\n\nСтатус: {status}\n\n"
        "Как работает: когда вы в статусе Офлайн и клиент пишет, сначала проверяется Smart FAQ. Если найдено одно чёткое "
        "совпадение — отправляется этот ответ. Иначе работает AI-помощник (если включён) или обычный автоответ.\n\n"
        "Бот осторожен: сообщение с отрицанием (например «нет», «не»), несколько одинаково подходящих ответов или "
        "неясное совпадение — ответ из FAQ не отправляется.",
    ),
    "ai_info_empty": _("kiritilmagan", "not set", "не указано"),
    "btn_ai_roles": _("\U0001F3AD Rolni tanlash", "\U0001F3AD Choose role", "\U0001F3AD Выбрать роль"),
    "btn_ai_info": _("\U0001F4DD Ma'lumot va uslub", "\U0001F4DD Info and style", "\U0001F4DD Информация и стиль"),
    "ai_roles_menu": _(
        "\U0001F3AD AI uchun rolni tanlang\n\n"
        "AI suhbatdoshingizga shu rolga mos ohang va uslubda javob beradi. "
        "Qo'shimcha ma'lumotni \"Ma'lumot va uslub\" bo'limida yozishingiz mumkin.",
        "\U0001F3AD Choose a role for the AI\n\n"
        "The AI will reply to your contact in a tone and style that fits this role. "
        "You can add more details in the \"Info and style\" section.",
        "\U0001F3AD Выберите роль для AI\n\n"
        "AI будет отвечать собеседнику в тоне и стиле, подходящих этой роли. "
        "Дополнительные сведения можно указать в разделе \"Информация и стиль\".",
    ),
    "role_assistant": _("\U0001F9D1‍\U0001F4BC Shaxsiy yordamchi", "\U0001F9D1‍\U0001F4BC Personal assistant", "\U0001F9D1‍\U0001F4BC Личный помощник"),
    "role_seller": _("\U0001F6D2 Sotuv menejeri", "\U0001F6D2 Sales manager", "\U0001F6D2 Менеджер по продажам"),
    "role_support": _("\U0001F6DF Mijozlarga yordam", "\U0001F6DF Customer support", "\U0001F6DF Помощь клиентам"),
    "role_friend": _("\U0001F44B Do'stona suhbatdosh", "\U0001F44B Friendly companion", "\U0001F44B Дружеский собеседник"),
    "role_developer": _("\U0001F468‍\U0001F4BB Dasturchi", "\U0001F468‍\U0001F4BB Developer", "\U0001F468‍\U0001F4BB Разработчик"),
    "role_business": _("\U0001F4BC Rasmiy / biznes", "\U0001F4BC Formal / business", "\U0001F4BC Официальный / бизнес"),
    "ai_not_configured": _(
        "⚠️ AI hozircha sozlanmagan (serverda GEMINI_API_KEY kiritilmagan).",
        "⚠️ AI is not configured yet (GEMINI_API_KEY is not set on the server).",
        "⚠️ AI пока не настроен (на сервере не задан GEMINI_API_KEY).",
    ),
    "ai_info_prompt": _(
        "AI uchun ma'lumot va uslubni yozing: siz kimsiz, nima ish qilasiz, qanday ohangda gaplashsin, "
        "nimalarni aytmasin (eng ko'pi {max} belgi).\n"
        "Tozalash uchun \"-\" yuboring. Bekor qilish: /cancel",
        "Write the info and style for the AI: who you are, what you do, what tone it should use, "
        "what it must not say (at most {max} characters).\n"
        "Send \"-\" to clear. To cancel: /cancel",
        "Напишите информацию и стиль для AI: кто вы, чем занимаетесь, каким тоном говорить, "
        "о чём не говорить (не более {max} символов).\n"
        "Отправьте \"-\", чтобы очистить. Отмена: /cancel",
    ),
    "ai_info_too_long": _(
        "Matn juda uzun ({n} belgi). {max} belgidan qisqaroq yozing.",
        "The text is too long ({n} characters). Keep it under {max} characters.",
        "Текст слишком длинный ({n} симв.). Напишите короче {max} символов.",
    ),
    # ---------------- ism soati ----------------
    "nc_menu": _(
        "\U0001F552 Ism soati\n\n"
        "Holat: {status}\n"
        "Vaqt zonasi: {zone}\n"
        "Raqamlar: {digits}\n"
        "Asl ism: {base}\n"
        "Ko'rinishi: {preview}\n\n"
        "Ismingizga har daqiqada joriy vaqt qo'shiladi. O'chirsangiz, asl ismingiz qaytadi.\n"
        "Telegram → Sozlamalar → Chat Automation → bot sozlamalarida \"Ismni o'zgartirish\" "
        "ruxsati yoqilgan bo'lishi shart.",
        "\U0001F552 Name clock\n\n"
        "Status: {status}\n"
        "Time zone: {zone}\n"
        "Digits: {digits}\n"
        "Base name: {base}\n"
        "Preview: {preview}\n\n"
        "The current time is added to your name every minute. If you turn it off, your original name comes back.\n"
        "In Telegram → Settings → Chat Automation → the bot's settings, the \"Edit name\" "
        "permission must be enabled.",
        "\U0001F552 Часы в имени\n\n"
        "Статус: {status}\n"
        "Часовой пояс: {zone}\n"
        "Цифры: {digits}\n"
        "Исходное имя: {base}\n"
        "Как выглядит: {preview}\n\n"
        "К вашему имени каждую минуту добавляется текущее время. Если выключить, вернётся исходное имя.\n"
        "В Telegram → Настройки → Chat Automation → в настройках бота должно быть включено "
        "разрешение \"Изменение имени\".",
    ),
    "nc_base_pending": _("yoqilganda Telegramdan olinadi", "taken from Telegram when enabled", "берётся из Telegram при включении"),
    "btn_nc_tz": _("\U0001F30D Vaqt zonasi", "\U0001F30D Time zone", "\U0001F30D Часовой пояс"),
    "btn_nc_style": _("\U0001F3A8 Shriftni tanlash", "\U0001F3A8 Choose font", "\U0001F3A8 Выбрать шрифт"),
    "btn_nc_edit": _("✏️ Asl ismni o'zgartirish", "✏️ Change base name", "✏️ Изменить исходное имя"),
    "nc_tz_title": _("\U0001F30D Vaqt zonasini tanlang:", "\U0001F30D Choose a time zone:", "\U0001F30D Выберите часовой пояс:"),
    "nc_style_title": _(
        "Profilga o'rnatiladigan raqamlar ko'rinishini tanlang:",
        "Choose how the digits will look in your profile:",
        "Выберите вид цифр, которые будут в вашем профиле:",
    ),
    "nc_off_restored": _(
        "✅ O'chirildi, asl ism qaytarildi.",
        "✅ Turned off, the original name was restored.",
        "✅ Выключено, исходное имя возвращено.",
    ),
    "nc_off_not_restored": _(
        "O'chirildi. Asl ismni qaytarib bo'lmadi — uni Telegramda o'zingiz tuzating.",
        "Turned off. The original name could not be restored — please fix it in Telegram yourself.",
        "Выключено. Не удалось вернуть исходное имя — исправьте его в Telegram самостоятельно.",
    ),
    "nc_name_prompt": _(
        "Asl ismingizni yuboring (soatsiz). Masalan: Dilshodbek yoki Dilshodbek Abdu.\nBekor qilish: /cancel",
        "Send your base name (without the clock). For example: John or John Smith.\nTo cancel: /cancel",
        "Отправьте исходное имя (без часов). Например: Иван или Иван Петров.\nОтмена: /cancel",
    ),
    "nc_name_empty": _(
        "Ism bo'sh bo'lishi mumkin emas. Qayta yuboring.",
        "The name cannot be empty. Please send it again.",
        "Имя не может быть пустым. Отправьте ещё раз.",
    ),
    "nc_need_connect": _(
        "⚠️ Avval akkauntingizni ulang (Telegram → Sozlamalar → Chat Automation).",
        "⚠️ Connect your account first (Telegram → Settings → Chat Automation).",
        "⚠️ Сначала подключите аккаунт (Telegram → Настройки → Chat Automation).",
    ),
    "nc_need_right": _(
        "⚠️ Botda ismni o'zgartirish ruxsati yo'q. Telegram → Sozlamalar → Chat Automation → "
        "bot → \"Ismni o'zgartirish\" (Edit name) ni yoqing va qayta urinib ko'ring.",
        "⚠️ The bot has no permission to change the name. Telegram → Settings → Chat Automation → "
        "the bot → enable \"Edit name\" and try again.",
        "⚠️ У бота нет разрешения менять имя. Telegram → Настройки → Chat Automation → "
        "бот → включите \"Изменение имени\" (Edit name) и повторите попытку.",
    ),
    "nc_name_unknown": _(
        "⚠️ Ismingizni aniqlab bo'lmadi. Keyinroq urinib ko'ring yoki \"Asl ismni o'zgartirish\" orqali yozing.",
        "⚠️ Could not determine your name. Try later or enter it via \"Change base name\".",
        "⚠️ Не удалось определить ваше имя. Повторите позже или введите его через \"Изменить исходное имя\".",
    ),
    "nc_need_bio": _(
        "⚠️ Bepul tarifda ism soati uchun \"Edit bio\" (BIO'ni tahrirlash) ruxsati ham yoqilgan bo'lishi shart — "
        "soat bilan birga BIO'ga bot haqida qisqa yozuv qo'yiladi.\n\n"
        "Telegram → Sozlamalar → My Profile → Chat Automations → botni bosing → \"Edit bio\" ni yoqing "
        "va qayta urinib ko'ring.\n\nPullik tariflarda bu talab yo'q.",
        "⚠️ On the Free plan the name clock also needs the \"Edit bio\" permission — "
        "a short note about the bot is placed in your bio together with the clock.\n\n"
        "Telegram → Settings → My Profile → Chat Automations → tap the bot → enable \"Edit bio\" "
        "and try again.\n\nPaid plans do not have this requirement.",
        "⚠️ На бесплатном тарифе для часов в имени нужно и разрешение \"Edit bio\" — "
        "вместе с часами в BIO ставится короткая заметка о боте.\n\n"
        "Telegram → Настройки → My Profile → Chat Automations → нажмите на бота → включите \"Edit bio\" "
        "и попробуйте снова.\n\nНа платных тарифах это не требуется.",
    ),
    "nc_bio_stopped": _(
        "⚠️ Ism soati to'xtatildi: \"Edit bio\" ruxsati yoqilmagan (Bepul tarifda soat uchun u shart). "
        "Ismingiz asl holiga qaytariladi.\n\n"
        "Telegram → Sozlamalar → My Profile → Chat Automations → botni bosing → \"Edit bio\" ni yoqing. "
        "Ruxsat yoqilishi bilan soat o'zi qayta ishga tushadi.",
        "⚠️ Name clock stopped: the \"Edit bio\" permission is not enabled (the Free plan requires it for the clock). "
        "Your name will be restored.\n\n"
        "Telegram → Settings → My Profile → Chat Automations → tap the bot → enable \"Edit bio\". "
        "The clock restarts by itself as soon as the permission is on.",
        "⚠️ Часы в имени остановлены: разрешение \"Edit bio\" не включено (на бесплатном тарифе оно обязательно). "
        "Ваше имя будет возвращено.\n\n"
        "Telegram → Настройки → My Profile → Chat Automations → нажмите на бота → включите \"Edit bio\". "
        "Как только разрешение включится, часы запустятся сами.",
    ),
    "nc_bio_restored": _(
        "✅ \"Edit bio\" ruxsati yoqildi — ism soati qayta ishga tushdi.",
        "✅ The \"Edit bio\" permission is on — the name clock is running again.",
        "✅ Разрешение \"Edit bio\" включено — часы в имени снова работают.",
    ),
    "nc_enabled": _("✅ Yoqildi.", "✅ Turned on.", "✅ Включено."),
    "nc_auto_disabled": _(
        "⚠️ Ism soati o'chirildi: {reason}",
        "⚠️ Name clock turned off: {reason}",
        "⚠️ Часы в имени выключены: {reason}",
    ),
    "nc_denied_reason": _(
        "Telegram ismni o'zgartirishga ruxsat bermadi. Telegram → Sozlamalar → "
        "Chat Automation → bot sozlamalarida \"Ismni o'zgartirish\" ruxsatini tekshiring.",
        "Telegram did not allow changing the name. Check the \"Edit name\" permission in "
        "Telegram → Settings → Chat Automation → the bot's settings.",
        "Telegram не разрешил менять имя. Проверьте разрешение \"Изменение имени\" в "
        "Telegram → Настройки → Chat Automation → настройки бота.",
    ),
    "nc_rights_lost": _(
        "⚠️ Ism soati o'chirildi: ismni o'zgartirish ruxsati yo'q. "
        "Ismingizdagi vaqtni Telegramda o'zingiz olib tashlang.",
        "⚠️ Name clock turned off: no permission to change the name. "
        "Please remove the time from your name in Telegram yourself.",
        "⚠️ Часы в имени выключены: нет разрешения менять имя. "
        "Уберите время из имени в Telegram самостоятельно.",
    ),
    # ---------------- ulanish xabarlari ----------------
    "connected": _(
        "✅ Akkountingiz ulandi! Panelni ochish uchun /start yozing.",
        "✅ Your account is connected! Send /start to open the panel.",
        "✅ Ваш аккаунт подключён! Отправьте /start, чтобы открыть панель.",
    ),
    "disconnected": _(
        "Akkount uzildi. Avtojavob endi ishlamaydi.",
        "The account was disconnected. Auto-reply no longer works.",
        "Аккаунт отключён. Автоответ больше не работает.",
    ),
    # ---------------- bloklash ----------------
    "block_notice": _(
        "\U0001F6AB Siz admin tomonidan bloklandingiz.\n{reason_line}"
        "\nBloklash davomida bot sizga xizmat ko'rsatmaydi: panel ishlamaydi, "
        "avtojavob va BIO yangilash to'xtatiladi.\n\n"
        "Agar bu xato deb o'ylasangiz, pastdagi tugma orqali izoh qoldiring — admin ko'rib chiqadi.",
        "\U0001F6AB You were blocked by the admin.\n{reason_line}"
        "\nWhile blocked, the bot will not serve you: the panel does not work, "
        "auto-reply and BIO updates are stopped.\n\n"
        "If you think this is a mistake, leave a comment with the button below — the admin will review it.",
        "\U0001F6AB Вы заблокированы админом.\n{reason_line}"
        "\nПока вы заблокированы, бот вас не обслуживает: панель не работает, "
        "автоответ и обновление BIO остановлены.\n\n"
        "Если вы считаете это ошибкой, оставьте комментарий кнопкой ниже — админ его рассмотрит.",
    ),
    "block_reason_line": _("Sabab: {reason}\n", "Reason: {reason}\n", "Причина: {reason}\n"),
    "btn_appeal": _("✍️ Izoh qoldirish", "✍️ Leave a comment", "✍️ Оставить комментарий"),
    "not_blocked": _("Siz bloklanmagansiz.", "You are not blocked.", "Вы не заблокированы."),
    "blocked_alert": _("\U0001F6AB Siz bloklangansiz.", "\U0001F6AB You are blocked.", "\U0001F6AB Вы заблокированы."),
    "unblocked_user": _(
        "✅ Siz blokdan chiqarildingiz. Davom etish uchun /start yozing.",
        "✅ You were unblocked. Send /start to continue.",
        "✅ Вы разблокированы. Отправьте /start, чтобы продолжить.",
    ),
    "appeal_limit": _(
        "Siz oxirgi 24 soat ichida {used} marta izoh qoldirgansiz. Keyinroq qayta urinib ko'ring.",
        "You have left {used} comments in the last 24 hours. Please try again later.",
        "За последние 24 часа вы оставили комментарий {used} раз. Повторите попытку позже.",
    ),
    "appeal_prompt": _(
        "✍️ Izohingizni bitta xabar qilib yuboring (ko'pi bilan {max} belgi). "
        "Nima uchun bu xato deb o'ylayotganingizni yozing.\nBekor qilish: /cancel",
        "✍️ Send your comment as a single message (at most {max} characters). "
        "Explain why you think this is a mistake.\nTo cancel: /cancel",
        "✍️ Отправьте комментарий одним сообщением (не более {max} символов). "
        "Объясните, почему вы считаете это ошибкой.\nОтмена: /cancel",
    ),
    "appeal_fail": _(
        "Hozir izohingizni adminga yetkazib bo'lmadi. Keyinroq qayta urinib ko'ring.",
        "Your comment could not be delivered to the admin right now. Please try again later.",
        "Сейчас не удалось доставить ваш комментарий админу. Повторите попытку позже.",
    ),
    "appeal_sent": _(
        "✅ Izohingiz adminga yuborildi. Qaror qabul qilinsa, sizga xabar beriladi.",
        "✅ Your comment was sent to the admin. You will be notified when a decision is made.",
        "✅ Ваш комментарий отправлен админу. Вы получите уведомление, когда будет принято решение.",
    ),
    "appeal_too_long": _(
        "Izoh juda uzun ({n} belgi). Ko'pi bilan {max} belgi — qisqaroq yozing.",
        "The comment is too long ({n} characters). At most {max} characters — please shorten it.",
        "Комментарий слишком длинный ({n} симв.). Не более {max} символов — сократите.",
    ),
    # ---------------- standart matnlar (egasining mijozlariga) ----------------
    "default_auto_reply": _(
        "Salom! Hozirda oflaynman, imkon qadar tezroq javob beraman \U0001F64F",
        "Hi! I'm offline at the moment, I'll reply as soon as I can \U0001F64F",
        "Здравствуйте! Сейчас я офлайн, отвечу как только смогу \U0001F64F",
    ),
    "default_sleep": _(
        "\U0001F634 Men hozir uxlayapman, ertalab uyg'onishim bilan albatta javob beraman!",
        "\U0001F634 I'm asleep right now, I'll definitely reply as soon as I wake up in the morning!",
        "\U0001F634 Сейчас я сплю, обязательно отвечу, как только проснусь утром!",
    ),
    # ---------------- tariflar ----------------
    "btn_plans": _("\U0001F3F7\uFE0F Tariflar", "\U0001F3F7\uFE0F Plans", "\U0001F3F7\uFE0F Тарифы"),
    "plans_menu": _(
        "\U0001F6D2 Tarif rejalarimiz\n\nTarifni bosing — unda qanday imkoniyatlar borligini ko'rasiz va xarid qilishingiz mumkin:",
        "\U0001F6D2 Our plans\n\nTap a plan to see exactly what it includes and to purchase it:",
        "\U0001F6D2 Наши тарифы\n\nНажмите на тариф, чтобы увидеть, что в него входит, и оформить покупку:",
    ),
    "plan_name_free": _("Bepul", "Free", "Бесплатный"),
    "plan_name_plus": _("Plus", "Plus", "Plus"),
    "plan_name_pro": _("Pro", "Pro", "Pro"),
    "plan_name_ultra": _("Ultra", "Ultra", "Ultra"),
    "plan_active": _("FAOL", "ACTIVE", "АКТИВЕН"),
    "plan_price": _("{price} so'm", "{price} UZS", "{price} сум"),
    "plan_free_info": _(
        "\U0001F530 Bepul tarif\n\nBarcha foydalanuvchilar shu tarifdan boshlaydi. To'lov talab qilinmaydi.",
        "\U0001F530 Free plan\n\nEveryone starts on this plan. No payment is required.",
        "\U0001F530 Бесплатный тариф\n\nВсе пользователи начинают с этого тарифа. Оплата не требуется.",
    ),
    "plan_current": _(
        "✅ Bu sizning hozirgi tarifingiz.",
        "✅ This is your current plan.",
        "✅ Это ваш текущий тариф.",
    ),
    "plan_title": _(
        "{emoji} {name} tarifi — {price}",
        "{emoji} {name} plan — {price}",
        "{emoji} Тариф {name} — {price}",
    ),
    "plan_includes": _("✅ Nimalar kiradi:", "✅ What's included:", "✅ Что входит:"),
    "plan_excludes": _(
        "\U0001F512 Bu tarifda yo'q (yuqoriroq tariflarda ochiladi):",
        "\U0001F512 Not included (unlocked on higher plans):",
        "\U0001F512 Не входит (открывается на более высоких тарифах):",
    ),
    "pf_autoreply": _(
        "Siz oflayn bo'lganingizda mijozlarga avtomatik javob (qayta-qayta yozmasligi uchun cooldown sozlanadi)",
        "Automatic reply to customers while you are offline (with a cooldown so it doesn't repeat itself)",
        "Автоответ клиентам, пока вы офлайн (с паузой, чтобы бот не писал одно и то же снова и снова)",
    ),
    "pf_sleep": _(
        "Uxlayapman rejimi — tunda alohida avtojavob yuboriladi",
        "Sleep mode — a separate auto-reply is sent during your night hours",
        "Режим сна — ночью отправляется отдельный автоответ",
    ),
    "pf_clock": _(
        "Ism soati — ismingiz yonida joriy vaqt (standart shrift, faqat O'zbekiston vaqti)",
        "Name clock — the current time next to your name (default font, Uzbekistan time only)",
        "Часы в имени — текущее время рядом с вашим именем (стандартный шрифт, только время Узбекистана)",
    ),
    "pf_clock_zones": _(
        "Ism soati — ismingiz yonida joriy vaqt (standart shrift, barcha shaharlar vaqti)",
        "Name clock — the current time next to your name (default font, all city time zones)",
        "Часы в имени — текущее время рядом с вашим именем (стандартный шрифт, время всех городов)",
    ),
    "pf_clock_fonts": _(
        "Ism soati — ismingiz yonida joriy vaqt (barcha shriftlar, faqat O'zbekiston vaqti)",
        "Name clock — the current time next to your name (all fonts, Uzbekistan time only)",
        "Часы в имени — текущее время рядом с вашим именем (все шрифты, только время Узбекистана)",
    ),
    "pf_clock_full": _(
        "Ism soati — ismingiz yonida joriy vaqt har daqiqada yangilanib turadi",
        "Name clock — the current time next to your name, updated every minute",
        "Часы в имени — текущее время рядом с вашим именем, обновляется каждую минуту",
    ),
    "pf_text": _(
        "Avtojavob va uxlash xabarini o'zingiz yozish (aks holda tayyor standart matn ketadi)",
        "Write your own auto-reply and sleep messages (otherwise a ready-made default text is sent)",
        "Свой текст автоответа и сообщения для сна (иначе отправляется готовый стандартный текст)",
    ),
    "pf_bio": _(
        "BIO hisoblagich — profilingizda Yangi yil, Navro'z yoki tug'ilgan kuningizgacha qolgan kunlar avtomatik yoziladi",
        "BIO countdown — your profile bio automatically shows the days left until New Year, Navruz or your birthday",
        "Счётчик в BIO — в описании профиля автоматически пишется, сколько дней осталось до Нового года, Навруза или вашего дня рождения",
    ),
    "pf_ai": _(
        "AI-Yordamchi — mijozlarga sun'iy intellekt o'zi javob yozadi (kuniga 50 tagacha javob, rolni tanlash mumkin)",
        "AI Assistant — artificial intelligence writes replies to your customers for you (up to 50 replies per day, you can pick a role)",
        "AI-помощник — искусственный интеллект сам отвечает вашим клиентам (до 50 ответов в день, можно выбрать роль)",
    ),
    "pf_ads_on": _("Reklama bilan", "With ads", "С рекламой"),
    "pf_ads_off": _("Reklama yo'q", "No ads", "Без рекламы"),
    "ad_reply": _(
        "\U0001F680 Ushbu xabar @autoreplyer_dbot orqali yuborildi!",
        "\U0001F680 This message was sent via @autoreplyer_dbot!",
        "\U0001F680 Это сообщение отправлено через @autoreplyer_dbot!",
    ),
    "ad_bio": _(
        "\U0001F680 Ushbu soat @autoreplyer_dbot orqali o'rnatildi!",
        "\U0001F680 This clock was set via @autoreplyer_dbot!",
        "\U0001F680 Эти часы установлены через @autoreplyer_dbot!",
    ),
    "pf_fonts": _(
        "Ism soati uchun {n} xil chiroyli shrift (qalin, yumaloq, chiziqli va boshqalar)",
        "{n} stylish fonts for the name clock (bold, circled, strikethrough and more)",
        "{n} красивых шрифтов для часов в имени (жирный, в кружках, зачёркнутый и другие)",
    ),
    "pf_zones": _(
        "Ism soati uchun {n} ta shahar vaqti (Toshkentdan tashqari: Moskva, Dubay, London, Nyu-York va boshqalar)",
        "{n} city time zones for the name clock (besides Tashkent: Moscow, Dubai, London, New York and more)",
        "{n} часовых поясов для часов в имени (кроме Ташкента: Москва, Дубай, Лондон, Нью-Йорк и другие)",
    ),
    "plan_pay": _(
        "Sotib olish uchun quyidagi kartaga to'lov qiling:\n\n"
        "\U0001F4B3 Karta raqami: {card}\n"
        "\U0001F464 Karta egasi: {holder}\n\n"
        "To'lovdan so'ng chekni (skrinshot) adminga yuboring — tarifingiz faollashtiriladi.",
        "To pay, transfer the amount to this card:\n\n"
        "\U0001F4B3 Card number: {card}\n"
        "\U0001F464 Card holder: {holder}\n\n"
        "After paying, send the receipt (screenshot) to the admin — your plan will be activated.",
        "Для оплаты переведите сумму на эту карту:\n\n"
        "\U0001F4B3 Номер карты: {card}\n"
        "\U0001F464 Владелец карты: {holder}\n\n"
        "После оплаты отправьте чек (скриншот) админу — тариф будет активирован.",
    ),
    "plan_no_card": _(
        "⚠️ To'lov kartasi hozircha sozlanmagan. Iltimos, admin bilan bog'laning.",
        "⚠️ The payment card is not set up yet. Please contact the admin.",
        "⚠️ Платёжная карта пока не настроена. Пожалуйста, свяжитесь с админом.",
    ),
    "plan_activated": _(
        "✅ Tarifingiz faollashtirildi: {name}",
        "✅ Your plan has been activated: {name}",
        "✅ Ваш тариф активирован: {name}",
    ),

    "plan_until": _(
        "⏳ Amal qilish muddati: {date} gacha",
        "⏳ Valid until: {date}",
        "⏳ Действует до: {date}",
    ),
    "plan_activated_until": _(
        "✅ Tarifingiz faollashtirildi: {name}\n⏳ Amal qilish muddati: {date} gacha",
        "✅ Your plan has been activated: {name}\n⏳ Valid until: {date}",
        "✅ Ваш тариф активирован: {name}\n⏳ Действует до: {date}",
    ),
    "plan_expired": _(
        "⌛ {name} tarifingiz muddati tugadi, Bepul tarifga qaytdingiz.\nQayta faollashtirish uchun \U0001F3F7\uFE0F Tariflar bo'limiga o'ting.",
        "⌛ Your {name} plan has expired and you are back on the Free plan.\nTo renew, open the \U0001F3F7\uFE0F Plans section.",
        "⌛ Срок вашего тарифа {name} истёк, вы вернулись на Бесплатный тариф.\nЧтобы продлить, откройте раздел \U0001F3F7\uFE0F Тарифы.",
    ),

    # ---------------- Payments v1.0 (Telegram Stars) ----------------
    "btn_pay_stars": _("⭐ Sotib olish (Stars)", "⭐ Buy with Stars", "⭐ Купить за Stars"),
    "btn_pay_extend": _("⭐ Uzaytirish (Stars)", "⭐ Extend with Stars", "⭐ Продлить за Stars"),
    "btn_pay_months": _("{n} oy — {price} ⭐", "{n} mo — {price} ⭐", "{n} мес — {price} ⭐"),
    "btn_pay_months_off": _("{n} oy — {price} ⭐ (−{pct}%)", "{n} mo — {price} ⭐ (−{pct}%)", "{n} мес — {price} ⭐ (−{pct}%)"),
    "btn_pay_go": _("⭐ To'lash: {pay}", "⭐ Pay: {pay}", "⭐ Оплатить: {pay}"),
    "btn_pay_switch": _("✅ Almashtirishni tasdiqlash", "✅ Confirm the switch", "✅ Подтвердить переход"),
    "pay_choose": _(
        "⭐ {name} tarifi\n\nMuddatni tanlang (uzoq muddatga chegirma bor):",
        "⭐ {name} plan\n\nChoose the duration (longer periods are cheaper):",
        "⭐ Тариф {name}\n\nВыберите срок (на длинный срок действует скидка):",
    ),
    "pay_card_title": _(
        "\U0001F4B3 Yoki karta orqali (admin tasdig'i bilan):",
        "\U0001F4B3 Or by card (confirmed by the admin):",
        "\U0001F4B3 Или картой (с подтверждением админа):",
    ),
    "pay_stars_hint": _(
        "⭐ Telegram Stars orqali to'lasangiz, tarif darhol faollashadi.",
        "⭐ If you pay with Telegram Stars, the plan is activated instantly.",
        "⭐ При оплате Telegram Stars тариф активируется сразу.",
    ),
    "pay_quote": _(
        "⭐ {name} tarifi — {months} oy\n\n{lines}\n\n⏳ Amal qilish muddati: {date} gacha\n\n{note}",
        "⭐ {name} plan — {months} mo\n\n{lines}\n\n⏳ Valid until: {date}\n\n{note}",
        "⭐ Тариф {name} — {months} мес\n\n{lines}\n\n⏳ Действует до: {date}\n\n{note}",
    ),
    "pay_quote_dg": _(
        "⭐ {name} tarifiga o'tish\n\nJoriy tarifingizning qolgan qiymati: {value} ⭐\nBu qiymat {name} tarifining taxminan {days} kuniga aylanadi.\nTo'lov kerak emas; oy tanlanmaydi — muddat qolgan qiymatdan avtomatik hisoblanadi.\n\n⏳ Amal qilish muddati: {date} gacha\n\n{note}",
        "⭐ Switch to the {name} plan\n\nRemaining value of your current plan: {value} ⭐\nIt is converted into about {days} days of the {name} plan.\nNo payment is needed; you don't choose months — the period is calculated automatically from the remaining value.\n\n⏳ Valid until: {date}\n\n{note}",
        "⭐ Переход на тариф {name}\n\nОстаток по текущему тарифу: {value} ⭐\nОн превращается примерно в {days} дн. тарифа {name}.\nОплата не нужна; месяцы не выбираются — срок рассчитывается автоматически из остатка.\n\n⏳ Действует до: {date}\n\n{note}",
    ),
    "pay_l_price": _("Narx: {v} ⭐", "Price: {v} ⭐", "Цена: {v} ⭐"),
    "pay_l_credit": _("Joriy tarifning qolgan qiymati: −{v} ⭐", "Remaining value of your current plan: −{v} ⭐", "Остаток по текущему тарифу: −{v} ⭐"),
    "pay_l_total": _("To'lanadi: {v} ⭐", "To pay: {v} ⭐", "К оплате: {v} ⭐"),
    "pay_l_free": _("To'lov kerak emas", "No payment needed", "Оплата не требуется"),
    "pay_note_new": _(
        "Tarif to'lovdan so'ng darhol faollashadi.",
        "The plan is activated right after payment.",
        "Тариф активируется сразу после оплаты.",
    ),
    "pay_note_extend": _(
        "Yangi muddat hozirgi muddat ustiga qo'shiladi — qolgan vaqt yo'qolmaydi.",
        "The new period is added on top of your current one — no remaining time is lost.",
        "Новый срок добавляется к текущему — оставшееся время не теряется.",
    ),
    "pay_note_upgrade": _(
        "Joriy tarifingizning qolgan qiymati hisobga olindi.",
        "The remaining value of your current plan has been taken into account.",
        "Остаток по вашему текущему тарифу учтён.",
    ),
    "pay_note_switch": _(
        "Joriy tarifingizning qolgan qiymati yangi tarif narxini qoplaydi, shuning uchun to'lov kerak emas. Ortiqcha qiymat qo'shimcha kunlarga aylantirildi.",
        "The remaining value of your current plan covers the new plan, so no payment is needed. Any surplus is converted into extra days.",
        "Остатка по текущему тарифу хватает на новый, поэтому оплата не нужна. Излишек превращён в дополнительные дни.",
    ),
    "pay_note_downgrade": _(
        "Past tarifga o'tish to'lovsiz: joriy tarifning qolgan qiymati arzonroq tarif kunlariga aylantiriladi (pul qaytarilmaydi).",
        "Switching to a cheaper plan is free: the remaining value of your current plan is converted into days of the cheaper plan (no money is refunded).",
        "Переход на более дешёвый тариф бесплатный: остаток по текущему тарифу превращается в дни дешёвого (деньги не возвращаются).",
    ),
    "pay_invoice_title": _("{name} tarifi — {months} oy", "{name} plan — {months} mo", "Тариф {name} — {months} мес"),
    "pay_invoice_desc": _(
        "AutoReplyer: {name} tarifi, {months} oy. To'lovdan so'ng darhol faollashadi.",
        "AutoReplyer: {name} plan, {months} mo. Activated right after payment.",
        "AutoReplyer: тариф {name}, {months} мес. Активируется сразу после оплаты.",
    ),
    "pay_invoice_sent": _(
        "⭐ To'lov hisobi yuborildi — {minutes} daqiqa ichida to'lang. Buyurtma: {token}",
        "⭐ The invoice has been sent — please pay within {minutes} minutes. Order: {token}",
        "⭐ Счёт отправлен — оплатите в течение {minutes} минут. Заказ: {token}",
    ),
    "pay_unlimited": _(
        "Sizning tarifingiz muddatsiz — uni to'lov orqali o'zgartirib bo'lmaydi. Kerak bo'lsa admin bilan bog'laning.",
        "Your plan has no expiry date, so it can't be changed by payment. Contact the admin if you need help.",
        "Ваш тариф бессрочный — его нельзя изменить оплатой. При необходимости свяжитесь с админом.",
    ),
    "pay_disabled": _(
        "⭐ Stars orqali to'lov hozircha o'chirilgan.",
        "⭐ Payment with Stars is currently turned off.",
        "⭐ Оплата Stars сейчас отключена.",
    ),
    "pay_state_changed": _(
        "⚠️ Tarifingiz holati o'zgargan. Iltimos, tarifni qaytadan tanlang.",
        "⚠️ Your plan status has changed. Please choose the plan again.",
        "⚠️ Состояние вашего тарифа изменилось. Выберите тариф заново.",
    ),
    "pay_bad_button": _("Bu tugma eskirgan. Tariflar bo'limidan qaytadan boshlang.", "This button is out of date. Start again from the Plans section.", "Эта кнопка устарела. Начните заново из раздела «Тарифы»."),
    "pay_invoice_active": _(
        "Bu buyurtma uchun to'lov hisobi allaqachon yuborilgan — pastdagi xabarga qarang yoki uni bekor qiling.",
        "The invoice for this order has already been sent — see the message below or cancel it.",
        "Счёт по этому заказу уже отправлен — посмотрите сообщение ниже или отмените его.",
    ),
    "pay_rate_limited": _(
        "Juda ko'p urinish. Bir necha daqiqadan keyin qayta urinib ko'ring.",
        "Too many attempts. Please try again in a few minutes.",
        "Слишком много попыток. Повторите через несколько минут.",
    ),
    "btn_pay_cancel": _("❌ Bekor qilish", "❌ Cancel", "❌ Отменить"),
    "pay_cancelled": _("Buyurtma bekor qilindi.", "The order has been cancelled.", "Заказ отменён."),
    "pay_cancel_na": _(
        "Bu buyurtmani bekor qilib bo'lmaydi (allaqachon to'langan yoki muddati o'tgan).",
        "This order can't be cancelled (already paid or expired).",
        "Этот заказ нельзя отменить (уже оплачен или истёк).",
    ),
    "pay_order_expired": _(
        "⌛ To'lov muddati ({minutes} daqiqa) tugadi — buyurtma bekor qilindi. Kerak bo'lsa, tarifni qaytadan tanlang.",
        "⌛ The payment window ({minutes} min) has ended — the order was cancelled. Choose the plan again if you still want it.",
        "⌛ Время на оплату ({minutes} мин) истекло — заказ отменён. При необходимости выберите тариф заново.",
    ),
    "pay_err_order": _("Buyurtma topilmadi yoki sizniki emas.", "The order was not found or is not yours.", "Заказ не найден или принадлежит не вам."),
    "pay_err_expired": _("Buyurtma muddati tugagan. Tarifni qaytadan tanlang.", "The order has expired. Please choose the plan again.", "Срок заказа истёк. Выберите тариф заново."),
    "pay_err_changed": _("Tarifingiz o'zgargan. Tarifni qaytadan tanlang.", "Your plan has changed. Please choose the plan again.", "Ваш тариф изменился. Выберите тариф заново."),
    "pay_err_blocked": _("To'lov qabul qilinmaydi.", "The payment can't be accepted.", "Платёж не может быть принят."),
    "pay_err_try_later": _("Vaqtinchalik xatolik. Birozdan keyin qayta urinib ko'ring.", "A temporary error. Please try again in a moment.", "Временная ошибка. Повторите попытку чуть позже."),
    "pay_success": _(
        "✅ To'lov qabul qilindi!\n{name} tarifi faollashtirildi.\n⏳ Amal qilish muddati: {date} gacha\n\nBuyurtma: {token}",
        "✅ Payment received!\nThe {name} plan has been activated.\n⏳ Valid until: {date}\n\nOrder: {token}",
        "✅ Платёж получен!\nТариф {name} активирован.\n⏳ Действует до: {date}\n\nЗаказ: {token}",
    ),
    "pay_unmatched": _(
        "⚠️ To'lovingiz qabul qilindi, lekin tarifni avtomatik faollashtirib bo'lmadi. Admin tez orada ko'rib chiqadi — /paysupport",
        "⚠️ Your payment was received, but the plan could not be activated automatically. The admin will review it shortly — /paysupport",
        "⚠️ Ваш платёж получен, но тариф не удалось активировать автоматически. Админ скоро проверит — /paysupport",
    ),
    "pay_delayed": _(
        "⏳ To'lovingiz qabul qilindi. Tarif bir necha daqiqa ichida faollashadi. Agar bo'lmasa — /paysupport",
        "⏳ Your payment was received. The plan will be activated within a few minutes. If it isn't — /paysupport",
        "⏳ Ваш платёж получен. Тариф активируется в течение нескольких минут. Если нет — /paysupport",
    ),
    "pay_switched": _(
        "✅ Tarif almashtirildi: {name}\n⏳ Amal qilish muddati: {date} gacha",
        "✅ Plan switched: {name}\n⏳ Valid until: {date}",
        "✅ Тариф изменён: {name}\n⏳ Действует до: {date}",
    ),
    "pay_refunded": _(
        "↩️ To'lovingiz qaytarildi ({stars} ⭐). Tarif muddati shunga mos qisqartirildi.\n{status}",
        "↩️ Your payment was refunded ({stars} ⭐). Your plan period was shortened accordingly.\n{status}",
        "↩️ Ваш платёж возвращён ({stars} ⭐). Срок тарифа соответственно сокращён.\n{status}",
    ),
    "pay_refunded_free": _("Tarifingiz Bepulga qaytdi.", "You are back on the Free plan.", "Вы вернулись на Бесплатный тариф."),
    "pay_support": _(
        "\U0001F4AC To'lov bo'yicha yordam\n\n"
        "To'lov bilan muammo bo'lsa, admin bilan bog'laning: @{admin}\nMurojaatda buyurtma raqamini yozing.\n\n"
        "• Tarif Stars to'lovidan so'ng darhol faollashadi.\n"
        "• To'lov qaytarilsa, tarifdan shu to'lovga mos kunlar ayriladi.\n"
        "• Tarif muddati tugasa, Bepul tarifga qaytasiz.\n\n"
        "So'nggi to'lovlaringiz:\n{list}",
        "\U0001F4AC Payment support\n\n"
        "If something is wrong with a payment, contact the admin: @{admin}\nInclude the order number in your message.\n\n"
        "• The plan is activated right after a Stars payment.\n"
        "• If a payment is refunded, the matching days are removed from your plan.\n"
        "• When the plan period ends, you return to the Free plan.\n\n"
        "Your recent payments:\n{list}",
        "\U0001F4AC Помощь по платежам\n\n"
        "Если с платежом что-то не так, свяжитесь с админом: @{admin}\nУкажите номер заказа.\n\n"
        "• Тариф активируется сразу после оплаты Stars.\n"
        "• Если платёж возвращён, из тарифа вычитаются соответствующие дни.\n"
        "• Когда срок тарифа заканчивается, вы возвращаетесь на Бесплатный.\n\n"
        "Ваши последние платежи:\n{list}",
    ),
    "pay_support_none": _("Hali to'lovlar yo'q.", "No payments yet.", "Платежей пока нет."),
    "pay_st_paid": _("to'langan", "paid", "оплачен"),
    "pay_st_refunded": _("qaytarilgan", "refunded", "возвращён"),
    "pay_st_refunding": _("qaytarilmoqda", "refunding", "возвращается"),
    "pay_st_switched": _("almashtirilgan", "switched", "переход"),
    "pay_st_pending": _("kutilmoqda", "pending", "ожидает"),
    "pay_st_expired": _("muddati o'tgan", "expired", "истёк"),
    "pay_st_unmatched": _("tekshiruvda", "under review", "на проверке"),
    # ---------------- tarif cheklovlari ----------------
    "feature_bio": _("BIO hisoblagich", "BIO countdown", "Счётчик в BIO"),
    "feature_text": _("Xabar matnini o'zgartirish", "Changing the message text", "Изменение текста сообщения"),
    "feature_ai": _("AI-Yordamchi", "AI Assistant", "AI-помощник"),
    "feature_fonts": _("Soat shriftlari", "Clock fonts", "Шрифты часов"),
    "feature_zones": _("Soat uchun boshqa vaqt zonalari", "Other time zones for the clock", "Другие часовые пояса для часов"),
    "feature_faq": _("Smart FAQ", "Smart FAQ", "Smart FAQ"),
    "btn_automation": _("\U0001F9E9 Avtomatlashtirish", "\U0001F9E9 Automation", "\U0001F9E9 Автоматизация"),
    "au_menu": _(
        "\U0001F9E9 Avtomatlashtirish\n\n"
        "Mijoz xabarida siz belgilagan so'z bo'lsa, bot unga maxsus javob yuboradi.\n\n"
        "Qoidalar: {count}/{max}\n\n"
        "Qoida faqat Oflayn rejimda ishlaydi (Uxlash rejimi va Jadval oynasida emas) va Smart FAQ hamda AI'dan oldin tekshiriladi. "
        "Matnli xabarlargagina javob beradi.",
        "\U0001F9E9 Automation\n\n"
        "If a customer's message contains a word you set, the bot sends them a custom reply.\n\n"
        "Rules: {count}/{max}\n\n"
        "A rule works only in Offline mode (not during Sleep Mode or a Schedule window) and is checked before Smart FAQ and AI. "
        "It answers text messages only.",
        "\U0001F9E9 Автоматизация\n\n"
        "Если в сообщении клиента есть заданное вами слово, бот отправит ему особый ответ.\n\n"
        "Правил: {count}/{max}\n\n"
        "Правило работает только в режиме «Офлайн» (не во время режима сна и окна расписания) и проверяется раньше Smart FAQ и AI. "
        "Отвечает только на текстовые сообщения.",
    ),
    "btn_au_add": _("➕ Qoida qo'shish", "➕ Add a rule", "➕ Добавить правило"),
    "btn_au_list": _("\U0001F4CB Qoidalarim", "\U0001F4CB My rules", "\U0001F4CB Мои правила"),
    "au_kw_prompt": _(
        "Kalit so'zni yuboring.\n\n"
        "• Butun so'z: narx — faqat «narx» so'zi mos keladi.\n"
        "• So'z boshi: narx* — «narxi», «narxlar» ham mos keladi.\n"
        "• Ibora ham mumkin: narx qancha\n\n"
        "Katta-kichik harf farq qilmaydi. «emas», «yo'q» kabi inkor so'zi bor xabarlarga javob berilmaydi.",
        "Send the keyword.\n\n"
        "• Whole word: price — only the word “price” matches.\n"
        "• Word start: price* — “prices”, “pricey” match too.\n"
        "• A phrase works too: how much\n\n"
        "Upper/lower case doesn't matter. Messages with a negation like “not” or “no” get no reply.",
        "Отправьте ключевое слово.\n\n"
        "• Целое слово: цена — подходит только слово «цена».\n"
        "• Начало слова: цен* — подойдут и «цены», «ценами».\n"
        "• Можно фразу: сколько стоит\n\n"
        "Регистр не важен. На сообщения с отрицанием («не», «нет») ответ не отправляется.",
    ),
    "au_kw_bad": _(
        "❌ Kalit so'z noto'g'ri. U bo'sh bo'lmasligi, {max} belgidan oshmasligi va ko'pi bilan {words} so'zdan iborat bo'lishi kerak. "
        "* belgisi faqat oxirida va kamida {prefix} harfdan keyin bo'ladi. Qayta yuboring.",
        "❌ Invalid keyword. It must not be empty, up to {max} characters and up to {words} words. "
        "The * sign is allowed only at the end and after at least {prefix} letters. Send it again.",
        "❌ Некорректное ключевое слово. Оно не должно быть пустым, длиной до {max} символов и не более {words} слов. "
        "Знак * допускается только в конце и после минимум {prefix} букв. Отправьте ещё раз.",
    ),
    "au_ans_prompt": _(
        "Mijozga yuboriladigan javob matnini yuboring (ko'pi bilan {max} belgi).",
        "Send the reply text for the customer (up to {max} characters).",
        "Отправьте текст ответа для клиента (до {max} символов).",
    ),
    "au_too_long": _(
        "❌ Matn juda uzun: {n} belgi (ko'pi bilan {max}). Qisqartirib qayta yuboring.",
        "❌ The text is too long: {n} characters (max {max}). Shorten it and send again.",
        "❌ Текст слишком длинный: {n} символов (максимум {max}). Сократите и отправьте ещё раз.",
    ),
    "au_empty_text": _("❌ Matn bo'sh bo'lmasligi kerak.", "❌ The text must not be empty.", "❌ Текст не должен быть пустым."),
    "au_confirm_hint": _(
        "Yuqoridagi xabardagi «Saqlash» yoki «Bekor qilish» tugmasini bosing.",
        "Press “Save” or “Cancel” in the message above.",
        "Нажмите «Сохранить» или «Отмена» в сообщении выше.",
    ),
    "au_confirm": _(
        "Qoidani tekshiring:\n\nKalit so'z: {kw}{extra}\n\nJavob:\n{a}",
        "Check the rule:\n\nKeyword: {kw}{extra}\n\nReply:\n{a}",
        "Проверьте правило:\n\nКлючевое слово: {kw}{extra}\n\nОтвет:\n{a}",
    ),
    "btn_au_save": _("✅ Saqlash", "✅ Save", "✅ Сохранить"),
    "btn_au_cancel": _("✖️ Bekor qilish", "✖️ Cancel", "✖️ Отмена"),
    "au_saved": _("✅ Qoida saqlandi va yoqildi.", "✅ Rule saved and turned on.", "✅ Правило сохранено и включено."),
    "au_cancelled": _("Bekor qilindi.", "Cancelled.", "Отменено."),
    "au_draft_lost": _(
        "⚠️ Qoralama topilmadi (vaqti o'tgan bo'lishi mumkin). Qaytadan boshlang.",
        "⚠️ The draft was not found (it may have expired). Start again.",
        "⚠️ Черновик не найден (возможно, истёк срок). Начните заново.",
    ),
    "au_limit": _(
        "❌ Qoidalar soni limitga yetdi ({max} ta). Keraksizini o'chiring.",
        "❌ You have reached the rule limit ({max}). Delete one you don't need.",
        "❌ Достигнут лимит правил ({max}). Удалите ненужное.",
    ),
    "au_list_empty": _(
        "Hali qoida yo'q. «Qoida qo'shish» tugmasini bosing.",
        "No rules yet. Press “Add a rule”.",
        "Правил пока нет. Нажмите «Добавить правило».",
    ),
    "au_list_title": _(
        "\U0001F4CB Qoidalaringiz ({count}/{max}). ⏸ — o'chirilgan.",
        "\U0001F4CB Your rules ({count}/{max}). ⏸ — turned off.",
        "\U0001F4CB Ваши правила ({count}/{max}). ⏸ — выключено.",
    ),
    "au_rule_view": _(
        "\U0001F9E9 Qoida\n\nHolat: {status}\nNomi: {name}\nKalit so'z: {kw}{extra}\nUstuvorlik: {prio}\nYuborilgan javoblar: {sent}\n\nJavob:\n{a}",
        "\U0001F9E9 Rule\n\nStatus: {status}\nName: {name}\nKeyword: {kw}{extra}\nPriority: {prio}\nReplies sent: {sent}\n\nReply:\n{a}",
        "\U0001F9E9 Правило\n\nСостояние: {status}\nНазвание: {name}\nКлючевое слово: {kw}{extra}\nПриоритет: {prio}\nОтправлено ответов: {sent}\n\nОтвет:\n{a}",
    ),
    "btn_au_on": _("✅ Yoqish", "✅ Turn on", "✅ Включить"),
    "btn_au_off": _("⏸ O'chirib turish", "⏸ Turn off", "⏸ Выключить"),
    "btn_au_delete": _("\U0001F5D1 O'chirish", "\U0001F5D1 Delete", "\U0001F5D1 Удалить"),
    "au_del_confirm": _(
        "Bu qoidani butunlay o'chirasizmi?\n\nKalit so'z: {kw}",
        "Delete this rule permanently?\n\nKeyword: {kw}",
        "Удалить это правило навсегда?\n\nКлючевое слово: {kw}",
    ),
    "btn_au_del_yes": _("\U0001F5D1 Ha, o'chirish", "\U0001F5D1 Yes, delete", "\U0001F5D1 Да, удалить"),
    "au_deleted": _("\U0001F5D1 Qoida o'chirildi.", "\U0001F5D1 Rule deleted.", "\U0001F5D1 Правило удалено."),
    "au_rule_gone": _("Bu qoida topilmadi (o'chirilgan bo'lishi mumkin).", "This rule was not found (it may have been deleted).", "Это правило не найдено (возможно, оно удалено)."),
    "feature_automation_conditions": _("Qoidalarda hafta kuni va vaqt shartlari", "Day-of-week and time conditions in rules", "Условия по дням недели и времени в правилах"),
    "btn_au_skip": _("⏭ O'tkazib yuborish", "⏭ Skip", "⏭ Пропустить"),
    "au_days_prompt": _(
        "\U0001F4C5 Qoida qaysi hafta kunlari ishlasin?\n\nKunlarni tanlang va «Keyingi»ni bosing. Hafta kuni sharti kerak bo'lmasa — «O'tkazib yuborish».",
        "\U0001F4C5 On which days of the week should the rule work?\n\nPick the days and press “Next”. If you don't need a day condition, press “Skip”.",
        "\U0001F4C5 В какие дни недели должно работать правило?\n\nВыберите дни и нажмите «Далее». Если условие по дням не нужно — «Пропустить».",
    ),
    "au_days_empty": _(
        "Kamida bitta kunni tanlang yoki «O'tkazib yuborish»ni bosing.",
        "Pick at least one day or press “Skip”.",
        "Выберите хотя бы один день или нажмите «Пропустить».",
    ),
    "au_days_hint": _(
        "Kunlarni yuqoridagi tugmalardan tanlang.",
        "Choose the days with the buttons above.",
        "Выберите дни кнопками выше.",
    ),
    "au_time_prompt": _(
        "\U0001F552 Qoida qaysi vaqt oralig'ida ishlasin?\n\nMasalan: 09:00-18:00. Yarim tundan o'tadigan oraliq ham mumkin (22:00-06:00; boshlangan kunga tegishli). "
        "Vaqt sharti kerak bo'lmasa — «O'tkazib yuborish».",
        "\U0001F552 In which time range should the rule work?\n\nFor example: 09:00-18:00. A range past midnight works too (22:00-06:00; it belongs to the day it starts). "
        "If you don't need a time condition, press “Skip”.",
        "\U0001F552 В какое время должно работать правило?\n\nНапример: 09:00-18:00. Можно и через полночь (22:00-06:00; относится ко дню начала). "
        "Если условие по времени не нужно — «Пропустить».",
    ),
    "au_time_bad": _(
        "❌ Vaqt oralig'i noto'g'ri. Shunday yozing: 09:00-18:00 (boshlanish va tugash bir xil bo'lmasin). Qayta yuboring.",
        "❌ Invalid time range. Write it like this: 09:00-18:00 (start and end must differ). Send it again.",
        "❌ Некорректный интервал. Напишите так: 09:00-18:00 (начало и конец не должны совпадать). Отправьте ещё раз.",
    ),
    "au_cond_days": _("Kunlar: {v}", "Days: {v}", "Дни: {v}"),
    "au_cond_time": _("Vaqt: {v}", "Time: {v}", "Время: {v}"),
    "au_or_join": _(" YOKI ", " OR ", " ИЛИ "),
    "au_kw_or_hint": _(
        "\n\n\U0001F500 Bir nechta kalit so'z (YOKI): vergul bilan ajrating, ko'pi bilan {n} ta. Masalan: narx*, qancha, price",
        "\n\n\U0001F500 Several keywords (OR): separate them with commas, up to {n}. For example: price*, how much, cost",
        "\n\n\U0001F500 Несколько ключевых слов (ИЛИ): разделите запятыми, не более {n}. Например: цен*, сколько, стоимость",
    ),
    "au_kw_count": _(
        "❌ Kalit so'zlar soni 2 dan {n} gacha bo'lishi kerak. Qayta yuboring.",
        "❌ The number of keywords must be between 2 and {n}. Send them again.",
        "❌ Количество ключевых слов должно быть от 2 до {n}. Отправьте ещё раз.",
    ),
    "au_kw_dup": _(
        "❌ Bir xil kalit so'z takrorlangan. Har birini bir martadan yozing.",
        "❌ A keyword is repeated. Write each one only once.",
        "❌ Ключевое слово повторяется. Напишите каждое только один раз.",
    ),
    "au_or_locked": _(
        "\U0001F512 Bir nechta kalit so'z (YOKI) Pro va Ultra tarifida ishlaydi. Hozir bitta kalit so'z yuboring.",
        "\U0001F512 Several keywords (OR) work on the Pro and Ultra plans. Send a single keyword for now.",
        "\U0001F512 Несколько ключевых слов (ИЛИ) работают на тарифах Pro и Ultra. Сейчас отправьте одно ключевое слово.",
    ),
    "au_rule_locked": _(
        "\U0001F512 Kun/vaqt va YOKI (bir nechta kalit so'z) shartlari Pro va Ultra tarifida ishlaydi. Hozirgi tarifda bu qoida ishlamaydi (o'chib ketmaydi).",
        "\U0001F512 Day/time and OR (several keywords) conditions work on the Pro and Ultra plans. On your current plan this rule does not run (it is not deleted).",
        "\U0001F512 Условия по дням/времени и ИЛИ (несколько ключевых слов) работают на тарифах Pro и Ultra. На текущем тарифе это правило не срабатывает (оно не удаляется).",
    ),
    "btn_au_edit": _("✏️ Tahrirlash", "✏️ Edit", "✏️ Изменить"),
    "au_edit_menu": _(
        "✏️ Qoidani tahrirlash\n\nQaysi qismini o'zgartirasiz?",
        "✏️ Edit rule\n\nWhich part do you want to change?",
        "✏️ Изменение правила\n\nЧто вы хотите изменить?",
    ),
    "btn_au_e_name": _("\U0001F4DD Nomi", "\U0001F4DD Name", "\U0001F4DD Название"),
    "btn_au_e_kw": _("\U0001F511 Kalit so'zlar", "\U0001F511 Keywords", "\U0001F511 Ключевые слова"),
    "btn_au_e_days": _("\U0001F4C5 Kunlar", "\U0001F4C5 Days", "\U0001F4C5 Дни"),
    "btn_au_e_time": _("\U0001F552 Vaqt", "\U0001F552 Time", "\U0001F552 Время"),
    "btn_au_e_reply": _("\U0001F4AC Javob", "\U0001F4AC Reply", "\U0001F4AC Ответ"),
    "btn_au_e_prio": _("⚡ Ustuvorlik", "⚡ Priority", "⚡ Приоритет"),
    "btn_au_e_clear": _("\U0001F9F9 Shartni olib tashlash", "\U0001F9F9 Remove the condition", "\U0001F9F9 Убрать условие"),
    "btn_au_e_done": _("✅ Tayyor", "✅ Done", "✅ Готово"),
    "au_e_name_prompt": _(
        "Qoidaning yangi nomini yuboring (ko'pi bilan {max} belgi).\nHozirgi: {cur}",
        "Send the new name of the rule (up to {max} characters).\nCurrent: {cur}",
        "Отправьте новое название правила (до {max} символов).\nСейчас: {cur}",
    ),
    "au_e_kw_prompt": _(
        "Yangi kalit so'z(lar)ni yuboring. Bir nechta bo'lsa (Pro/Ultra) vergul bilan ajrating, ko'pi bilan {max} ta.\nHozirgi: {cur}",
        "Send the new keyword(s). If several (Pro/Ultra), separate with commas, up to {max}.\nCurrent: {cur}",
        "Отправьте новые ключевые слова. Если несколько (Pro/Ultra) — через запятую, не более {max}.\nСейчас: {cur}",
    ),
    "au_e_time_prompt": _(
        "Yangi vaqt oralig'ini yuboring, masalan 09:00-18:00. Shartni butunlay olib tashlash uchun pastdagi tugmani bosing.\nHozirgi: {cur}",
        "Send the new time range, for example 09:00-18:00. To remove the condition completely, press the button below.\nCurrent: {cur}",
        "Отправьте новый интервал, например 09:00-18:00. Чтобы убрать условие совсем, нажмите кнопку ниже.\nСейчас: {cur}",
    ),
    "au_e_reply_prompt": _(
        "Yangi javob matnini yuboring (ko'pi bilan {max} belgi).\nHozirgi:\n{cur}",
        "Send the new reply text (up to {max} characters).\nCurrent:\n{cur}",
        "Отправьте новый текст ответа (до {max} символов).\nСейчас:\n{cur}",
    ),
    "au_e_prio_prompt": _(
        "Yangi ustuvorlikni yuboring: {min} dan {max} gacha butun son. Kichik son — oldin tekshiriladi.\nHozirgi: {cur}",
        "Send the new priority: a whole number from {min} to {max}. A smaller number is checked first.\nCurrent: {cur}",
        "Отправьте новый приоритет: целое число от {min} до {max}. Меньшее число проверяется раньше.\nСейчас: {cur}",
    ),
    "au_e_days_title": _(
        "\U0001F4C5 Qoida ishlaydigan kunlarni tanlang va «Tayyor»ni bosing.",
        "\U0001F4C5 Pick the days the rule works and press “Done”.",
        "\U0001F4C5 Выберите дни, когда работает правило, и нажмите «Готово».",
    ),
    "au_name_bad": _(
        "❌ Nom bo'sh bo'lmasligi va {max} belgidan oshmasligi kerak. Qayta yuboring.",
        "❌ The name must not be empty or longer than {max} characters. Send it again.",
        "❌ Название не должно быть пустым или длиннее {max} символов. Отправьте ещё раз.",
    ),
    "au_prio_bad": _(
        "❌ Ustuvorlik {min} dan {max} gacha butun son bo'lishi kerak. Qayta yuboring.",
        "❌ The priority must be a whole number from {min} to {max}. Send it again.",
        "❌ Приоритет должен быть целым числом от {min} до {max}. Отправьте ещё раз.",
    ),
    "au_updated": _("✅ O'zgarishlar saqlandi.", "✅ Changes saved.", "✅ Изменения сохранены."),
    "au_edit_lost": _(
        "⚠️ Tahrirlash sessiyasi topilmadi (vaqti o'tgan bo'lishi mumkin). Qoidani qaytadan oching.",
        "⚠️ The edit session was not found (it may have expired). Open the rule again.",
        "⚠️ Сессия изменения не найдена (возможно, истёк срок). Откройте правило заново.",
    ),
    "au_e_days_empty": _(
        "Kamida bitta kunni tanlang yoki «Shartni olib tashlash»ni bosing.",
        "Pick at least one day or press “Remove the condition”.",
        "Выберите хотя бы один день или нажмите «Убрать условие».",
    ),
    "au_e_none": _("yo'q", "none", "нет"),
    "btn_au_stats": _("\U0001F4CA Statistika", "\U0001F4CA Statistics", "\U0001F4CA Статистика"),
    "au_stats": _(
        "\U0001F4CA Automation statistikasi\n\n"
        "\U0001F9E9 Jami qoidalar: {total}\n✅ Faol qoidalar: {active}\n\n"
        "\U0001F4E8 Automation javoblari ({period}): {period_sent}\n"
        "\U0001F4E8 Automation javoblari (jami, {since} dan beri): {all_sent}\n\n"
        "\U0001F3C6 Eng ko'p ishlatilgan mavjud qoidalar:\n{top}\n\n"
        "\U0001F512 Mijoz xabarlari yoki chat ID saqlanmaydi — faqat sonlar.",
        "\U0001F4CA Automation statistics\n\n"
        "\U0001F9E9 Total rules: {total}\n✅ Active rules: {active}\n\n"
        "\U0001F4E8 Automation replies ({period}): {period_sent}\n"
        "\U0001F4E8 Automation replies (total, since {since}): {all_sent}\n\n"
        "\U0001F3C6 Most used existing rules:\n{top}\n\n"
        "\U0001F512 Customer messages and chat IDs are not stored — only counters.",
        "\U0001F4CA Статистика автоматизации\n\n"
        "\U0001F9E9 Всего правил: {total}\n✅ Активных правил: {active}\n\n"
        "\U0001F4E8 Ответов автоматизации ({period}): {period_sent}\n"
        "\U0001F4E8 Ответов автоматизации (всего, с {since}): {all_sent}\n\n"
        "\U0001F3C6 Самые используемые существующие правила:\n{top}\n\n"
        "\U0001F512 Сообщения клиентов и ID чатов не хранятся — только счётчики.",
    ),
    "au_stats_top_none": _("Hali javob yuborilmagan.", "No replies sent yet.", "Пока нет отправленных ответов."),
    "feature_automation": _("Avtomatlashtirish qoidalari", "Automation rules", "Правила автоматизации"),
    "pf_faq": _(
        "Smart FAQ — tayyor savol-javoblar bilan tez avtomatik javob (ko'pi bilan {n} ta savol)",
        "Smart FAQ — quick automatic answers from your ready Q&A (up to {n} questions)",
        "Smart FAQ — быстрые автоответы из ваших готовых вопросов и ответов (до {n} вопросов)",
    ),
    "pf_faq_locked": _(
        "Smart FAQ — tayyor savol-javoblar bilan tez avtomatik javob (savollar soni: {limits})",
        "Smart FAQ — quick automatic answers from your ready Q&A (number of questions: {limits})",
        "Smart FAQ — быстрые автоответы из ваших готовых вопросов и ответов (количество вопросов: {limits})",
    ),
    "locked_feature": _(
        "\U0001F512 «{feature}» faqat {plans} tariflarida mavjud.\n\nTarifni \U0001F3F7\uFE0F Tariflar bo'limidan o'zgartirishingiz mumkin.",
        "\U0001F512 “{feature}” is available only on the {plans} plans.\n\nYou can change your plan in the \U0001F3F7\uFE0F Plans section.",
        "\U0001F512 «{feature}» доступно только на тарифах {plans}.\n\nТариф можно изменить в разделе \U0001F3F7\uFE0F Тарифы.",
    ),
    "locked_unavailable": _(
        "\U0001F512 «{feature}» hozircha mavjud emas. Faqat standart shrift ishlaydi.",
        "\U0001F512 “{feature}” is not available right now. Only the default font is used.",
        "\U0001F512 «{feature}» пока недоступно. Используется только стандартный шрифт.",
    ),

    # ---------------- vaqt zonalari (shahar nomlari) ----------------
    "zone_tashkent": _("Toshkent", "Tashkent", "Ташкент"),
    "zone_moscow": _("Moskva", "Moscow", "Москва"),
    "zone_istanbul": _("Istanbul", "Istanbul", "Стамбул"),
    "zone_dubai": _("Dubay", "Dubai", "Дубай"),
    "zone_bishkek": _("Bishkek", "Bishkek", "Бишкек"),
    "zone_beijing": _("Pekin", "Beijing", "Пекин"),
    "zone_tokyo": _("Tokio", "Tokyo", "Токио"),
    "zone_london": _("London", "London", "Лондон"),
    "zone_berlin": _("Berlin", "Berlin", "Берлин"),
    "zone_newyork": _("Nyu-York", "New York", "Нью-Йорк"),
    # ---------------- Smart Onboarding ----------------
    "ob_welcome": _("\U0001F44B Xush kelibsiz!\n\n", "\U0001F44B Welcome!\n\n", "\U0001F44B Добро пожаловать!\n\n"),
    "ob_connect": _(
        "\U0001F517 1/3 — Telegram'ni ulang\n\n"
        "1. Telegram'da Settings ni oching.\n"
        "2. My Profile bo'limiga kiring.\n"
        "3. Chat Automations ni tanlang.\n"
        "4. @{bot} ni ulang.\n"
        "5. Kerakli chatlarni tanlang va Reply to messages ruxsatini yoqing.\n\n"
        "Menyu nomlari Telegram versiyasiga qarab biroz farq qilishi mumkin.",
        "\U0001F517 1/3 — Connect Telegram\n\n"
        "1. Open Settings in Telegram.\n"
        "2. Go to My Profile.\n"
        "3. Choose Chat Automations.\n"
        "4. Connect @{bot}.\n"
        "5. Pick the chats and enable the Reply to messages permission.\n\n"
        "Menu names may differ slightly depending on your Telegram version.",
        "\U0001F517 1/3 — Подключите Telegram\n\n"
        "1. Откройте Settings в Telegram.\n"
        "2. Зайдите в My Profile.\n"
        "3. Выберите Chat Automations.\n"
        "4. Подключите @{bot}.\n"
        "5. Выберите чаты и включите разрешение Reply to messages.\n\n"
        "Названия пунктов меню могут немного отличаться в зависимости от версии Telegram.",
    ),
    "ob_not_connected": _(
        "Hali ulanmagan. Yuqoridagi qadamlarni bajaring va yana bosing.",
        "Not connected yet. Follow the steps above and tap again.",
        "Пока не подключено. Выполните шаги выше и нажмите снова.",
    ),
    "ob_no_reply_perm": _(
        "Ulangan, lekin \"Reply to messages\" ruxsati yoqilmagan. Uni yoqing va qayta tekshiring.",
        "Connected, but the \"Reply to messages\" permission is off. Enable it and check again.",
        "Подключено, но разрешение \"Reply to messages\" выключено. Включите его и проверьте снова.",
    ),
    "ob_not_enabled": _(
        "Auto-Reply hali yoqilmagan. Avval uni yoqing.",
        "Auto-Reply is not turned on yet. Turn it on first.",
        "Автоответ ещё не включён. Сначала включите его.",
    ),
    "ob_configure": _(
        "✅ Telegram ulangan!\n\n"
        "\U0001F4AC 2/3 — Avtomatik javob\n\n"
        "Siz band yoki offline bo'lganingizda AutoReplyer xabarlarga javob beradi.\n\n"
        "\U0001F4DD Javob matni:\n«{text}»\n\n{plan_note}",
        "✅ Telegram is connected!\n\n"
        "\U0001F4AC 2/3 — Auto-reply\n\n"
        "When you are busy or offline, AutoReplyer answers messages for you.\n\n"
        "\U0001F4DD Reply text:\n«{text}»\n\n{plan_note}",
        "✅ Telegram подключён!\n\n"
        "\U0001F4AC 2/3 — Автоответ\n\n"
        "Когда вы заняты или офлайн, AutoReplyer отвечает на сообщения за вас.\n\n"
        "\U0001F4DD Текст ответа:\n«{text}»\n\n{plan_note}",
    ),
    "ob_plan_free": _(
        "Bepul tarifda standart javob ishlatiladi. O'z matningizni yozish pullik tariflarda mavjud.",
        "The Free plan uses the standard reply. Writing your own text is available on paid plans.",
        "На бесплатном тарифе используется стандартный ответ. Свой текст доступен на платных тарифах.",
    ),
    "ob_plan_paid": _(
        "Javob matnini keyinroq boshqaruv panelida o'zgartirishingiz mumkin.",
        "You can change the reply text later in the control panel.",
        "Текст ответа можно изменить позже в панели управления.",
    ),
    "ob_verify": _(
        "\U0001F9EA 3/3 — Botni sinab ko'ring\n\n{checks}\n\n"
        "Boshqa Telegram akkauntidan o'zingizga xabar yuboring.",
        "\U0001F9EA 3/3 — Try the bot\n\n{checks}\n\n"
        "Send yourself a message from another Telegram account.",
        "\U0001F9EA 3/3 — Проверьте бота\n\n{checks}\n\n"
        "Отправьте себе сообщение с другого аккаунта Telegram.",
    ),
    "ob_chk_connected": _("Telegram ulangan", "Telegram is connected", "Telegram подключён"),
    "ob_chk_reply": _("Javob berish ruxsati mavjud", "Reply permission is granted", "Разрешение на ответы есть"),
    "ob_chk_enabled": _("Auto-Reply yoqilgan", "Auto-Reply is on", "Автоответ включён"),
    "ob_fail": _(
        "\U0001F50E Javob kelmadi — tekshirib ko'ramiz:\n\n{checks}\n\n"
        "Yana bir nechta sabab:\n"
        "• Xabarni BOSHQA akkauntdan yuboring — o'zingizga yozsangiz ishlamaydi.\n"
        "• Bitta suhbatga {hours} soatda bir marta javob beriladi (cooldown).\n"
        "• Chat Automations'da shu suhbatga ruxsat berilganini tekshiring.{sleep}",
        "\U0001F50E No reply came — let's check:\n\n{checks}\n\n"
        "A few more possible reasons:\n"
        "• Send the message from ANOTHER account — writing to yourself does not work.\n"
        "• Each chat gets one reply per {hours} hours (cooldown).\n"
        "• Check that this chat is allowed in Chat Automations.{sleep}",
        "\U0001F50E Ответ не пришёл — проверим:\n\n{checks}\n\n"
        "Ещё несколько возможных причин:\n"
        "• Пишите с ДРУГОГО аккаунта — сообщение самому себе не сработает.\n"
        "• В один чат отвечаем раз в {hours} ч (кулдаун).\n"
        "• Проверьте, что этот чат разрешён в Chat Automations.{sleep}",
    ),
    "ob_fail_sleep": _(
        "\n• Sleep Mode yoqilgan — uyqu vaqtida u o'z matnini yuboradi.",
        "\n• Sleep Mode is on — during sleep hours it sends its own text.",
        "\n• Включён Sleep Mode — в часы сна он отправляет свой текст.",
    ),
    "ob_done": _(
        "\U0001F389 Tayyor! Auto-Reply ishlayapti. Mana boshqaruv paneli:",
        "\U0001F389 All set! Auto-Reply is working. Here is your control panel:",
        "\U0001F389 Готово! Автоответ работает. Вот ваша панель управления:",
    ),
    "ob_skipped": _(
        "Sozlash o'tkazib yuborildi. Istalgan payt \"\U0001F680 Sozlashni davom ettirish\" tugmasi orqali qaytishingiz mumkin.",
        "Setup skipped. You can come back any time with the \"\U0001F680 Continue setup\" button.",
        "Настройка пропущена. Вернуться можно в любой момент кнопкой \"\U0001F680 Продолжить настройку\".",
    ),
    "btn_ob_check": _("✅ Ulanishni tekshirish", "✅ Check connection", "✅ Проверить подключение"),
    "btn_ob_enable": _("✅ Auto-Reply'ni yoqish", "✅ Turn on Auto-Reply", "✅ Включить автоответ"),
    "btn_ob_ok": _("✅ Javob keldi", "✅ Reply arrived", "✅ Ответ пришёл"),
    "btn_ob_fail": _("❌ Javob kelmadi", "❌ No reply", "❌ Ответа нет"),
    "btn_ob_skip": _("⏭ O'tkazib yuborish", "⏭ Skip", "⏭ Пропустить"),
    "btn_ob_resume": _("\U0001F680 Sozlashni davom ettirish", "\U0001F680 Continue setup", "\U0001F680 Продолжить настройку"),
    "sleep_tz_note": _(
        "\U0001F30D Vaqt zonasi: {tz} (Uxlash rejimi va Smart Jadval bir xil zonada ishlaydi — «Ism soati»dagi zona, tanlanmagan bo'lsa Toshkent).",
        "\U0001F30D Time zone: {tz} (Sleep Mode and Smart Scheduler use the same zone - the one set in Name Clock, Tashkent if none).",
        "\U0001F30D Часовой пояс: {tz} (Режим сна и умное расписание работают в одном поясе — из «Часов в имени», если не выбран — Ташкент).",
    ),
    # ---------------- Smart Auto-Reply Scheduler ----------------
    "btn_sched": _("\U0001F4C5 Smart Jadval", "\U0001F4C5 Smart Scheduler", "\U0001F4C5 Умное расписание"),
    "feature_sched": _("Smart Jadval", "Smart Scheduler", "Умное расписание"),
    "pf_sched": _(
        "Smart Jadval — haftalik avtojavob jadvallari (ko'pi bilan {n} ta)",
        "Smart Scheduler - weekly auto-reply schedules (up to {n})",
        "Умное расписание — недельные расписания автоответа (до {n})",
    ),
    "sched_days_full": _(
        "Dushanba|Seshanba|Chorshanba|Payshanba|Juma|Shanba|Yakshanba",
        "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday",
        "Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье",
    ),
    "sched_days_short": _(
        "Du|Se|Ch|Pa|Ju|Sh|Ya", "Mon|Tue|Wed|Thu|Fri|Sat|Sun", "Пн|Вт|Ср|Чт|Пт|Сб|Вс",
    ),
    "sched_everyday": _("Har kuni", "Every day", "Каждый день"),
    "sched_all_day": _("Butun kun", "All day", "Весь день"),
    "sched_default_text": _("standart avtojavob matni", "your standard auto-reply text", "стандартный текст автоответа"),
    "sched_paused": _("⏸ to'xtatilgan", "⏸ paused", "⏸ приостановлено"),
    "sched_menu": _(
        "\U0001F4C5 SMART AUTO-REPLY SCHEDULER\n\n"
        "{status_icon} Holat: {status}\n"
        "\U0001F30D Vaqt zonasi: {tz}\n\n"
        "\U0001F4CB Jadvallarim ({count}/{max}):\n\n{rules}",
        "\U0001F4C5 SMART AUTO-REPLY SCHEDULER\n\n"
        "{status_icon} Status: {status}\n"
        "\U0001F30D Time zone: {tz}\n\n"
        "\U0001F4CB My schedules ({count}/{max}):\n\n{rules}",
        "\U0001F4C5 SMART AUTO-REPLY SCHEDULER\n\n"
        "{status_icon} Статус: {status}\n"
        "\U0001F30D Часовой пояс: {tz}\n\n"
        "\U0001F4CB Мои расписания ({count}/{max}):\n\n{rules}",
    ),
    "sched_none": _(
        "Hozircha jadval yo'q. «Jadval qo'shish» tugmasi bilan birinchisini yarating — masalan, ish kunlari 09:00–18:00.",
        "No schedules yet. Tap “Add schedule” to create the first one, for example weekdays 09:00–18:00.",
        "Расписаний пока нет. Нажмите «Добавить расписание» и создайте первое, например будни 09:00–18:00.",
    ),
    "sched_how": _(
        "ℹ️ Jadval vaqtida bot siz «Onlayn» bo'lsangiz ham javob beradi. Jadval tugagach avvalgi sozlamalaringiz o'zgarishsiz ishlaydi. Uxlash rejimi har doim ustun.",
        "ℹ️ During a schedule the bot replies even if you are “Online”. When it ends your previous settings apply unchanged. Sleep Mode always takes priority.",
        "ℹ️ Во время расписания бот отвечает, даже если вы «Онлайн». После его окончания работают прежние настройки без изменений. Режим сна всегда в приоритете.",
    ),
    "btn_sc_add": _("➕ Jadval qo'shish", "➕ Add schedule", "➕ Добавить расписание"),
    "btn_sc_edit": _("✏️ Jadvalni tahrirlash", "✏️ Edit schedule", "✏️ Редактировать расписание"),
    "btn_sc_delete": _("\U0001F5D1 Jadvalni o'chirish", "\U0001F5D1 Delete schedule", "\U0001F5D1 Удалить расписание"),
    "btn_sc_settings": _("⚙️ Sozlamalar", "⚙️ Settings", "⚙️ Настройки"),
    "btn_sc_continue": _("➡️ Davom etish", "➡️ Continue", "➡️ Продолжить"),
    "btn_sc_wd": _("Ish kunlari", "Weekdays", "Будни"),
    "btn_sc_we": _("Dam olish", "Weekend", "Выходные"),
    "btn_sc_all": _("Har kuni", "Every day", "Каждый день"),
    "btn_sc_allday": _("\U0001F334 Butun kun", "\U0001F334 All day", "\U0001F334 Весь день"),
    "btn_sc_deftext": _("Standart matn", "Standard text", "Стандартный текст"),
    "btn_sc_save": _("✅ Saqlash", "✅ Save", "✅ Сохранить"),
    "btn_sc_cancel": _("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"),
    "btn_sc_ed_days": _("\U0001F4C6 Kunlarni o'zgartirish", "\U0001F4C6 Change days", "\U0001F4C6 Изменить дни"),
    "btn_sc_ed_time": _("\U0001F558 Vaqtni o'zgartirish", "\U0001F558 Change time", "\U0001F558 Изменить время"),
    "btn_sc_ed_text": _("\U0001F4AC Matnni o'zgartirish", "\U0001F4AC Change text", "\U0001F4AC Изменить текст"),
    "btn_sc_pause": _("⏸ Vaqtincha to'xtatish", "⏸ Pause", "⏸ Приостановить"),
    "btn_sc_resume": _("▶️ Yoqish", "▶️ Resume", "▶️ Включить"),
    "btn_sc_del_yes": _("✅ Ha, o'chirish", "✅ Yes, delete", "✅ Да, удалить"),
    "btn_sc_toggle_on": _("⏸ Jadvallarni o'chirish", "⏸ Turn schedules off", "⏸ Выключить расписания"),
    "btn_sc_toggle_off": _("▶️ Jadvallarni yoqish", "▶️ Turn schedules on", "▶️ Включить расписания"),
    "sc_days_prompt": _(
        "\U0001F4C6 1/3 — Qaysi kunlarga jadval qo'yamiz? Kunlarni belgilang (qayta bossangiz — bekor bo'ladi), keyin «Davom etish»ni bosing.",
        "\U0001F4C6 1/3 — Which days should this schedule cover? Tick the days (tap again to untick), then press “Continue”.",
        "\U0001F4C6 1/3 — На какие дни поставить расписание? Отметьте дни (повторное нажатие снимает), затем нажмите «Продолжить».",
    ),
    "sc_days_none": _("Kamida bitta kunni belgilang.", "Select at least one day.", "Выберите хотя бы один день."),
    "sc_time_prompt": _(
        "\U0001F558 2/3 — Vaqt oralig'ini yuboring, masalan: 09:00-18:00. Yarim tundan o'tadigan oraliq ham mumkin (22:00-06:00). Yoki «Butun kun»ni bosing.",
        "\U0001F558 2/3 — Send the time range, for example: 09:00-18:00. Ranges past midnight work too (22:00-06:00). Or press “All day”.",
        "\U0001F558 2/3 — Отправьте промежуток времени, например: 09:00-18:00. Можно и через полночь (22:00-06:00). Или нажмите «Весь день».",
    ),
    "sc_time_bad": _(
        "Vaqt noto'g'ri. Namuna: 09:00-18:00 (boshlanish va tugash bir xil bo'lmasin).",
        "Invalid time. Example: 09:00-18:00 (start and end must differ).",
        "Неверное время. Пример: 09:00-18:00 (начало и конец не должны совпадать).",
    ),
    "sc_text_prompt": _(
        "\U0001F4AC 3/3 — Shu jadval uchun javob matnini yuboring (ko'pi bilan {max} belgi). Yoki «Standart matn»ni bosing — odatdagi avtojavob matni ishlatiladi.",
        "\U0001F4AC 3/3 — Send the reply text for this schedule (up to {max} characters). Or press “Standard text” to use your usual auto-reply text.",
        "\U0001F4AC 3/3 — Отправьте текст ответа для этого расписания (до {max} символов). Или нажмите «Стандартный текст» — будет использован обычный текст автоответа.",
    ),
    "sc_text_too_long": _(
        "Matn juda uzun: {n} belgi (ko'pi bilan {max}). Qisqartirib qayta yuboring.",
        "Text is too long: {n} characters (max {max}). Shorten it and send again.",
        "Текст слишком длинный: {n} символов (максимум {max}). Сократите и отправьте снова.",
    ),
    "sc_text_locked_note": _(
        "ℹ️ Alohida javob matni Plus tarifidan boshlab ochiladi — hozircha standart avtojavob matni ishlatiladi.",
        "ℹ️ A separate reply text is available from the Plus plan - for now your standard auto-reply text is used.",
        "ℹ️ Отдельный текст ответа доступен с тарифа Plus — пока используется стандартный текст автоответа.",
    ),
    "sc_confirm": _(
        "\U0001F4CB Yangi jadval:\n\n\U0001F4C6 {days}\n{time_icon} {time}\n\U0001F4AC {text}\n\nSaqlaymizmi?",
        "\U0001F4CB New schedule:\n\n\U0001F4C6 {days}\n{time_icon} {time}\n\U0001F4AC {text}\n\nSave it?",
        "\U0001F4CB Новое расписание:\n\n\U0001F4C6 {days}\n{time_icon} {time}\n\U0001F4AC {text}\n\nСохранить?",
    ),
    "sc_saved": _("✅ Jadval saqlandi.", "✅ Schedule saved.", "✅ Расписание сохранено."),
    "sc_updated": _("✅ Jadval yangilandi.", "✅ Schedule updated.", "✅ Расписание обновлено."),
    "sc_cancelled": _("Bekor qilindi.", "Cancelled.", "Отменено."),
    "sc_limit": _(
        "Jadvallar limiti to'ldi (ko'pi bilan {max} ta). Yangisini qo'shish uchun avval eskisini o'chiring yoki tarifingizni oshiring.",
        "Schedule limit reached (max {max}). Delete an old one first or upgrade your plan.",
        "Лимит расписаний исчерпан (максимум {max}). Сначала удалите старое или повысите тариф.",
    ),
    "sc_conflict": _(
        "⚠️ Bu kun va vaqt {n}-jadval bilan kesishadi. Kunlar yoki vaqtni o'zgartiring — bir vaqtda faqat bitta jadval ishlashi mumkin.",
        "⚠️ These days and times overlap schedule #{n}. Change the days or time - only one schedule can be active at a time.",
        "⚠️ Эти дни и время пересекаются с расписанием №{n}. Измените дни или время — одновременно может действовать только одно расписание.",
    ),
    "sc_draft_lost": _(
        "Jarayon eskirdi. «Jadval qo'shish»dan qaytadan boshlang.",
        "This flow has expired. Start again with “Add schedule”.",
        "Процесс устарел. Начните заново через «Добавить расписание».",
    ),
    "sc_page": _("Sahifa {p}/{n}", "Page {p}/{n}", "Страница {p}/{n}"),
    "sc_stale_button": _(
        "Bu tugma eskirgan. Joriy jarayonni oxirgi xabardagi tugmalar yoki yozuvingiz bilan davom ettiring.",
        "This button is out of date. Continue the current process with the latest message's buttons or your reply.",
        "Эта кнопка устарела. Продолжайте текущий процесс кнопками последнего сообщения или своим ответом.",
    ),
    "sc_gone": _("Bu jadval topilmadi (o'chirilgan bo'lishi mumkin).", "This schedule was not found (it may have been deleted).", "Это расписание не найдено (возможно, оно удалено)."),
    "sc_pick_edit": _("✏️ Qaysi jadvalni tahrirlaymiz?", "✏️ Which schedule do you want to edit?", "✏️ Какое расписание редактировать?"),
    "sc_pick_delete": _("\U0001F5D1 Qaysi jadvalni o'chiramiz?", "\U0001F5D1 Which schedule do you want to delete?", "\U0001F5D1 Какое расписание удалить?"),
    "sc_no_rules": _("Hali jadval yo'q.", "There are no schedules yet.", "Расписаний пока нет."),
    "sc_entry": _(
        "{n}. {days}\n{time_icon} {time}\n\U0001F4AC {text}\n{status_icon} Holat: {status}",
        "{n}. {days}\n{time_icon} {time}\n\U0001F4AC {text}\n{status_icon} Status: {status}",
        "{n}. {days}\n{time_icon} {time}\n\U0001F4AC {text}\n{status_icon} Статус: {status}",
    ),
    "sc_del_confirm": _(
        "\U0001F5D1 Bu jadvalni o'chirasizmi?\n\n{entry}\n\nBu amalni qaytarib bo'lmaydi.",
        "\U0001F5D1 Delete this schedule?\n\n{entry}\n\nThis cannot be undone.",
        "\U0001F5D1 Удалить это расписание?\n\n{entry}\n\nЭто действие нельзя отменить.",
    ),
    "sc_deleted": _("\U0001F5D1 Jadval o'chirildi.", "\U0001F5D1 Schedule deleted.", "\U0001F5D1 Расписание удалено."),
    "sc_settings": _(
        "⚙️ JADVAL SOZLAMALARI\n\n{status_icon} Holat: {status}\n\U0001F30D Vaqt zonasi: {tz}\n\n"
        "Vaqt zonasi «Ism soati» sozlamasidan olinadi (tanlanmagan bo'lsa — Toshkent). "
        "Jadvallarni o'chirib qo'ysangiz, ular saqlanib qoladi, faqat ishlamaydi.",
        "⚙️ SCHEDULER SETTINGS\n\n{status_icon} Status: {status}\n\U0001F30D Time zone: {tz}\n\n"
        "The time zone comes from your Name Clock setting (Tashkent if none is chosen). "
        "If you turn schedules off they are kept, they just stop working.",
        "⚙️ НАСТРОЙКИ РАСПИСАНИЯ\n\n{status_icon} Статус: {status}\n\U0001F30D Часовой пояс: {tz}\n\n"
        "Часовой пояс берётся из настройки «Часы в имени» (если не выбран — Ташкент). "
        "Если выключить расписания, они сохранятся, но не будут работать.",
    ),
    # ---------------- AutoReply Analytics ----------------
    "btn_analytics": _("\U0001F4CA Statistika", "\U0001F4CA Analytics", "\U0001F4CA Аналитика"),
    "btn_an_today": _("\U0001F4C5 Bugun", "\U0001F4C5 Today", "\U0001F4C5 Сегодня"),
    "btn_an_7": _("\U0001F4C6 7 kun", "\U0001F4C6 7 days", "\U0001F4C6 7 дней"),
    "btn_an_30": _("\U0001F5D3 30 kun", "\U0001F5D3 30 days", "\U0001F5D3 30 дней"),
    "btn_an_charts": _("\U0001F4CA Grafikni ko'rish", "\U0001F4CA View charts", "\U0001F4CA Показать графики"),
    "btn_an_detail": _("\U0001F4CB Batafsil", "\U0001F4CB Details", "\U0001F4CB Подробно"),
    "an_period_1": _("Bugun", "Today", "Сегодня"),
    "an_period_7": _("Oxirgi 7 kun", "Last 7 days", "Последние 7 дней"),
    "an_period_30": _("Oxirgi 30 kun", "Last 30 days", "Последние 30 дней"),
    "an_menu": _(
        "\U0001F4CA AUTOREPLY ANALYTICS\n\n"
        "\U0001F4C5 Davr: {period}\n\n"
        "\U0001F4E5 Kelgan xabarlar: {incoming}\n"
        "\U0001F4E4 Yuborilgan javoblar: {sent}\n"
        "  \u251C \U0001F4A1 Smart FAQ: {faq}\n"
        "  \u251C \U0001F916 Gemini AI: {ai}\n"
        "  \u251C \U0001F4DD Oddiy javoblar: {static}\n"
        "  \u251C \U0001F9E9 Automation: {automation}\n"
        "  \u2514 \U0001F634 Sleep Mode: {sleep}\n\n"
        "\u23F0 Eng faol vaqt: {peak}",
        "\U0001F4CA AUTOREPLY ANALYTICS\n\n"
        "\U0001F4C5 Period: {period}\n\n"
        "\U0001F4E5 Incoming messages: {incoming}\n"
        "\U0001F4E4 Replies sent: {sent}\n"
        "  \u251C \U0001F4A1 Smart FAQ: {faq}\n"
        "  \u251C \U0001F916 Gemini AI: {ai}\n"
        "  \u251C \U0001F4DD Standard replies: {static}\n"
        "  \u251C \U0001F9E9 Automation: {automation}\n"
        "  \u2514 \U0001F634 Sleep Mode: {sleep}\n\n"
        "\u23F0 Busiest time: {peak}",
        "\U0001F4CA AUTOREPLY ANALYTICS\n\n"
        "\U0001F4C5 Период: {period}\n\n"
        "\U0001F4E5 Входящие сообщения: {incoming}\n"
        "\U0001F4E4 Отправлено ответов: {sent}\n"
        "  \u251C \U0001F4A1 Smart FAQ: {faq}\n"
        "  \u251C \U0001F916 Gemini AI: {ai}\n"
        "  \u251C \U0001F4DD Обычные ответы: {static}\n"
        "  \u251C \U0001F9E9 Automation: {automation}\n"
        "  \u2514 \U0001F634 Sleep Mode: {sleep}\n\n"
        "\u23F0 Самое активное время: {peak}",
    ),
    "an_peak_none": _("ma'lumot yo'q", "no data", "нет данных"),
    "an_empty": _(
        "\u231B Ma'lumot yig'ilmoqda. Statistika yangi xabarlar kelgandan boshlab hisoblanadi — birozdan keyin qaytib ko'ring.",
        "\u231B Collecting data. Statistics are counted from new messages onwards, so check back a little later.",
        "\u231B Данные собираются. Статистика считается с новых сообщений — загляните чуть позже.",
    ),
    "an_note": _(
        "\u2139\uFE0F Kelgan xabarlar javoblardan ko'p bo'lishi mumkin: siz Onlayn bo'lganingizda yoki cooldown davomida avtojavob yuborilmaydi.",
        "\u2139\uFE0F Incoming can exceed replies: no auto-reply is sent while you are Online or during the cooldown.",
        "\u2139\uFE0F Входящих может быть больше, чем ответов: пока вы Онлайн или идёт cooldown, автоответ не отправляется.",
    ),
    "an_privacy": _(
        "\U0001F512 Analytics xabar matnlarini saqlamaydi — faqat vaqt va statistik hisoblagichlar saqlanadi. Gemini AI suhbat tarixi alohida boshqariladi.",
        "\U0001F512 Analytics does not store message texts - only time and statistical counters. Gemini AI chat history is managed separately.",
        "\U0001F512 Аналитика не хранит тексты сообщений — только время и статистические счётчики. История чатов Gemini AI управляется отдельно.",
    ),
    "an_charts_caption": _("\U0001F4CA Statistika: {name} ({period})", "\U0001F4CA Analytics: {name} ({period})", "\U0001F4CA Аналитика: {name} ({period})"),
    "an_charts_failed": _(
        "Grafikni yaratib bo'lmadi. Birozdan keyin qayta urinib ko'ring.",
        "Could not build the chart. Please try again in a moment.",
        "Не удалось построить график. Попробуйте ещё раз чуть позже.",
    ),
    "an_chart_line": _("Kunlik xabarlar", "Daily messages", "Сообщения по дням"),
    "an_chart_pie": _("Javob turlari ulushi", "Reply type share", "Доля типов ответов"),
    "an_chart_bar": _("Eng faol soatlar", "Busiest hours", "Самые активные часы"),
    "an_lbl_incoming": _("Kelgan", "Incoming", "Входящие"),
    "an_lbl_sent": _("Yuborilgan", "Sent", "Отправлено"),
    "an_lbl_faq": _("Smart FAQ javoblari", "Smart FAQ replies", "Ответы Smart FAQ"),
    "an_lbl_ai": _("Gemini AI javoblari", "Gemini AI replies", "Ответы Gemini AI"),
    "an_lbl_static": _("Oddiy javoblar", "Standard replies", "Обычные ответы"),
    "an_lbl_automation": _("Automation javoblari", "Automation replies", "Ответы Automation"),
    "an_lbl_sleep": _("Sleep Mode javoblari", "Sleep Mode replies", "Ответы Sleep Mode"),
    "an_lbl_none": _("Ma'lumot yo'q", "No data", "Нет данных"),
    "an_lbl_hour": _("Soat", "Hour", "Час"),
    "an_detail": _(
        "\U0001F4CB BATAFSIL STATISTIKA — {period}\n\n"
        "\U0001F4E5 Kelgan: {incoming}   \U0001F4E4 Yuborilgan: {sent}\n"
        "\u2705 Javob berish ulushi: {rate}%\n"
        "\u23F3 Cooldown tufayli o'tkazib yuborilgan: {skipped}\n"
        "\U0001F4C8 Kunlik o'rtacha: {avg}\n"
        "\U0001F525 Eng faol kun: {best_day}\n"
        "\u23F0 Eng faol vaqt: {peak}\n\n"
        "\U0001F551 Soatlar bo'yicha (kelgan xabarlar):\n{hours}\n\n"
        "\U0001F4C5 Kunlar bo'yicha (kelgan / yuborilgan):\n{days}",
        "\U0001F4CB DETAILED ANALYTICS - {period}\n\n"
        "\U0001F4E5 Incoming: {incoming}   \U0001F4E4 Sent: {sent}\n"
        "\u2705 Reply rate: {rate}%\n"
        "\u23F3 Skipped due to cooldown: {skipped}\n"
        "\U0001F4C8 Daily average: {avg}\n"
        "\U0001F525 Busiest day: {best_day}\n"
        "\u23F0 Busiest time: {peak}\n\n"
        "\U0001F551 By hour (incoming messages):\n{hours}\n\n"
        "\U0001F4C5 By day (incoming / sent):\n{days}",
        "\U0001F4CB ПОДРОБНАЯ СТАТИСТИКА — {period}\n\n"
        "\U0001F4E5 Входящие: {incoming}   \U0001F4E4 Отправлено: {sent}\n"
        "\u2705 Доля ответов: {rate}%\n"
        "\u23F3 Пропущено из-за cooldown: {skipped}\n"
        "\U0001F4C8 В среднем за день: {avg}\n"
        "\U0001F525 Самый активный день: {best_day}\n"
        "\u23F0 Самое активное время: {peak}\n\n"
        "\U0001F551 По часам (входящие):\n{hours}\n\n"
        "\U0001F4C5 По дням (входящие / отправлено):\n{days}",
    ),
    "feature_an7": _("7 kunlik statistika", "7-day analytics", "Аналитика за 7 дней"),
    "feature_an30": _("30 kunlik statistika", "30-day analytics", "Аналитика за 30 дней"),
    "feature_anfull": _("Batafsil statistika va barcha grafiklar", "Detailed analytics and all charts", "Подробная аналитика и все графики"),
    "feature_anch": _("Statistika grafiklari", "Analytics charts", "Графики аналитики"),
    "pf_an_free": _("Statistika — faqat bugungi kun", "Analytics - today only", "Аналитика — только за сегодня"),
    "pf_an_plus": _("Statistika — 7 kun + chiziqli grafik", "Analytics - 7 days + line chart", "Аналитика — 7 дней + линейный график"),
    "pf_an_pro": _("Statistika — 30 kun + chiziqli va doira grafik", "Analytics - 30 days + line and pie charts", "Аналитика — 30 дней + линейный и круговой графики"),
    "pf_an_ultra": _("Statistika — batafsil hisobot va barcha grafiklar", "Analytics - detailed report and all charts", "Аналитика — подробный отчёт и все графики"),
    # ---------------- AI Personal Knowledge (ichki nom: kb) ----------------
    "btn_kb": _("\U0001F9E0 AI Shaxsiy Bilimlar", "\U0001F9E0 AI Personal Knowledge", "\U0001F9E0 AI Личные знания"),
    "feature_kb": _("AI Shaxsiy Bilimlar", "AI Personal Knowledge", "AI Личные знания"),
    "pf_automation": _(
        "Automation Engine — kalit so'zga ko'ra maxsus javob ({n} ta qoida)",
        "Automation Engine — custom reply by keyword ({n} rules)",
        "Automation Engine — свой ответ по ключевому слову ({n} правил)",
    ),
    "pf_automation_locked": _(
        "Automation Engine — kalit so'zga ko'ra maxsus javob (qoidalar soni: {limits})",
        "Automation Engine — custom reply by keyword (number of rules: {limits})",
        "Automation Engine — свой ответ по ключевому слову (количество правил: {limits})",
    ),
    "pf_automation_smart": _(
        "Smart Conditions — vaqt, hafta kunlari va AND shartlari",
        "Smart Conditions — time, weekdays and AND conditions",
        "Smart Conditions — время, дни недели и условия И (AND)",
    ),
    "pf_kb": _(
        "AI Shaxsiy Bilimlar — AI siz yozgan ma'lumotlarga tayanib javob beradi (ko'pi bilan {n} ta yozuv)",
        "AI Personal Knowledge — the AI answers based on the facts you wrote (up to {n} entries)",
        "AI Личные знания — AI отвечает на основе написанных вами сведений (до {n} записей)",
    ),
    "kb_menu": _(
        "\U0001F9E0 AI SHAXSIY BILIMLAR\n\n"
        "\U0001F4DA Ma'lumotlar: {count}/{max}\n"
        "\U0001F7E2 Holat: {status}\n\n"
        "Bu yerga o'zingiz haqingizdagi yoki ishingizdagi ma'lumotlarni yozing. AI-Yordamchi mijozga javob berayotganda "
        "shulardan foydalanadi. Bazada yo'q narsani (narx, vaqt, manzil va h.k.) AI o'ylab topmaydi — "
        "o'zingiz keyin javob berishingizni aytadi. Faqat AI-Yordamchi yoqilgan bo'lsa ishlaydi.{notice}",
        "\U0001F9E0 AI PERSONAL KNOWLEDGE\n\n"
        "\U0001F4DA Entries: {count}/{max}\n"
        "\U0001F7E2 Status: {status}\n\n"
        "Write facts about yourself or your work here. The AI Assistant uses them when replying to people. "
        "The AI will not invent anything that is not in the base (prices, times, addresses, etc.) — "
        "it will say you will answer personally. Works only while the AI Assistant is on.{notice}",
        "\U0001F9E0 AI ЛИЧНЫЕ ЗНАНИЯ\n\n"
        "\U0001F4DA Записей: {count}/{max}\n"
        "\U0001F7E2 Статус: {status}\n\n"
        "Запишите сюда сведения о себе или о своей работе. AI-помощник использует их, отвечая людям. "
        "Чего нет в базе (цены, время, адрес и т. д.), AI не выдумывает — "
        "он скажет, что вы ответите лично. Работает только при включённом AI-помощнике.{notice}",
    ),
    "btn_kb_add": _("➕ Ma'lumot qo'shish", "➕ Add Entry", "➕ Добавить запись"),
    "btn_kb_list": _("\U0001F4CB Ma'lumotlarim", "\U0001F4CB My Entries", "\U0001F4CB Мои записи"),
    "btn_kb_settings": _("⚙️ Sozlamalar", "⚙️ Settings", "⚙️ Настройки"),
    "btn_kb_save": _("✅ Saqlash", "✅ Save", "✅ Сохранить"),
    "btn_kb_cancel": _("❌ Bekor qilish", "❌ Cancel", "❌ Отмена"),
    "btn_kb_delete": _("\U0001F5D1 O'chirish", "\U0001F5D1 Delete", "\U0001F5D1 Удалить"),
    "btn_kb_entry_off": _("⏸ Vaqtincha o'chirish", "⏸ Pause", "⏸ Приостановить"),
    "btn_kb_entry_on": _("▶️ Yoqish", "▶️ Resume", "▶️ Включить"),
    "btn_kb_edit_t": _("✏️ Sarlavhani o'zgartirish", "✏️ Edit title", "✏️ Изменить заголовок"),
    "btn_kb_edit_c": _("\U0001F4DD Ma'lumotni o'zgartirish", "\U0001F4DD Edit text", "\U0001F4DD Изменить текст"),
    "btn_kb_edit_kw": _("\U0001F511 Kalit so'zlarni o'zgartirish", "\U0001F511 Edit keywords", "\U0001F511 Изменить ключевые слова"),
    "kb_title_prompt": _(
        "1/3. Ma'lumot sarlavhasini yozing (masalan: Ish vaqtim, Qaysi tillarda gaplashaman, Hobbilarim).\n"
        "Eng ko'pi {max} belgi.\nBekor qilish: /cancel",
        "1/3. Write a title for the entry (e.g. My working hours, Languages I speak, My hobbies).\n"
        "Up to {max} characters.\nCancel: /cancel",
        "1/3. Напишите заголовок записи (например: Мои рабочие часы, Языки, на которых я говорю, Мои хобби).\n"
        "До {max} символов.\nОтмена: /cancel",
    ),
    "kb_content_prompt": _(
        "2/3. Ma'lumot matnini yozing — AI mijozga shunga tayanib javob beradi (eng ko'pi {max} belgi).\n"
        "Bekor qilish: /cancel",
        "2/3. Write the text — the AI will answer people based on it (up to {max} characters).\n"
        "Cancel: /cancel",
        "2/3. Напишите текст — AI будет отвечать людям на его основе (до {max} символов).\n"
        "Отмена: /cancel",
    ),
    "kb_kw_prompt": _(
        "3/3. Kalit so'zlarni vergul bilan yozing (ixtiyoriy, masalan: vaqt, soat, jadval). "
        "Baza katta bo'lganda AI aynan shu ma'lumotni topishi uchun kerak.\n"
        "Kerak bo'lmasa — «-» yuboring.\nBekor qilish: /cancel",
        "3/3. Write keywords separated by commas (optional, e.g. time, hours, schedule). "
        "When the base is large they help the AI find exactly this entry.\n"
        "If you don't need them, send «-».\nCancel: /cancel",
        "3/3. Напишите ключевые слова через запятую (необязательно, например: время, часы, график). "
        "Когда база большая, они помогают AI найти именно эту запись.\n"
        "Если не нужны — отправьте «-».\nОтмена: /cancel",
    ),
    "kb_confirm": _(
        "Saqlashdan oldin tekshiring:\n\n\U0001F4CC Sarlavha: {title}\n\U0001F4DD Ma'lumot: {content}\n\U0001F511 Kalit so'zlar: {kw}",
        "Please check before saving:\n\n\U0001F4CC Title: {title}\n\U0001F4DD Text: {content}\n\U0001F511 Keywords: {kw}",
        "Проверьте перед сохранением:\n\n\U0001F4CC Заголовок: {title}\n\U0001F4DD Текст: {content}\n\U0001F511 Ключевые слова: {kw}",
    ),
    "kb_confirm_hint": _(
        "Pastdagi tugmalardan birini bosing: Saqlash yoki Bekor qilish.",
        "Please press one of the buttons below: Save or Cancel.",
        "Нажмите одну из кнопок ниже: Сохранить или Отмена.",
    ),
    "kb_too_long": _(
        "Matn juda uzun ({n} belgi, eng ko'pi {max}). Qisqartirib qayta yuboring.",
        "The text is too long ({n} characters, max {max}). Shorten it and send again.",
        "Текст слишком длинный ({n} симв., максимум {max}). Сократите и отправьте снова.",
    ),
    "kb_empty_text": _("Matn bo'sh bo'lmasligi kerak.", "The text can't be empty.", "Текст не должен быть пустым."),
    "kb_kw_bad": _(
        "Kalit so'zlar noto'g'ri: ko'pi bilan {max} ta so'z/ibora (har biri {len} belgigacha). "
        "Vergul bilan ajratib qayta yuboring yoki «-» yuboring.",
        "Invalid keywords: up to {max} words/phrases (each up to {len} characters). "
        "Separate them with commas and send again, or send «-».",
        "Неверные ключевые слова: до {max} слов/фраз (каждое до {len} символов). "
        "Разделите запятыми и отправьте снова или отправьте «-».",
    ),
    "kb_no_keywords": _("yo'q", "none", "нет"),
    "kb_saved": _("✅ Ma'lumot saqlandi.", "✅ Entry saved.", "✅ Запись сохранена."),
    "kb_limit": _(
        "Ma'lumotlar limiti to'lgan ({max} ta). Yangisini qo'shish uchun eskisini o'chiring.",
        "Entry limit reached ({max}). Delete an old one to add a new one.",
        "Лимит записей исчерпан ({max}). Удалите старую, чтобы добавить новую.",
    ),
    "kb_cancelled": _("Bekor qilindi.", "Cancelled.", "Отменено."),
    "kb_draft_lost": _(
        "Qoralama yo'qolgan (vaqt o'tdi). Iltimos, boshidan boshlang.",
        "The draft was lost (timed out). Please start again.",
        "Черновик потерян (истекло время). Начните сначала.",
    ),
    "kb_list_empty": _(
        "Hali ma'lumot qo'shilmagan. \"➕ Ma'lumot qo'shish\" tugmasini bosing.",
        "No entries yet. Press \"➕ Add Entry\".",
        "Записей пока нет. Нажмите «➕ Добавить запись».",
    ),
    "kb_list_title": _(
        "\U0001F4CB Ma'lumotlarim ({count}/{max}). Ko'rish uchun tanlang:",
        "\U0001F4CB My Entries ({count}/{max}). Pick one to view:",
        "\U0001F4CB Мои записи ({count}/{max}). Выберите для просмотра:",
    ),
    "kb_entry_view": _(
        "\U0001F4CC Sarlavha: {title}\n\U0001F4DD Ma'lumot: {content}\n\U0001F511 Kalit so'zlar: {kw}\n\nHolat: {status}",
        "\U0001F4CC Title: {title}\n\U0001F4DD Text: {content}\n\U0001F511 Keywords: {kw}\n\nStatus: {status}",
        "\U0001F4CC Заголовок: {title}\n\U0001F4DD Текст: {content}\n\U0001F511 Ключевые слова: {kw}\n\nСтатус: {status}",
    ),
    "kb_edit_t_prompt": _(
        "✏️ Yangi sarlavhani yuboring (eng ko'pi {max} belgi).\n\nHozirgi: {cur}\n\nBekor qilish: /cancel",
        "✏️ Send the new title (up to {max} characters).\n\nCurrent: {cur}\n\nCancel: /cancel",
        "✏️ Отправьте новый заголовок (до {max} символов).\n\nСейчас: {cur}\n\nОтмена: /cancel",
    ),
    "kb_edit_c_prompt": _(
        "\U0001F4DD Yangi ma'lumot matnini yuboring (eng ko'pi {max} belgi).\n\nHozirgi: {cur}\n\nBekor qilish: /cancel",
        "\U0001F4DD Send the new text (up to {max} characters).\n\nCurrent: {cur}\n\nCancel: /cancel",
        "\U0001F4DD Отправьте новый текст (до {max} символов).\n\nСейчас: {cur}\n\nОтмена: /cancel",
    ),
    "kb_edit_kw_prompt": _(
        "\U0001F511 Yangi kalit so'zlarni vergul bilan yuboring (ko'pi bilan 10 ta; eskilari almashtiriladi). "
        "Olib tashlash uchun «-» yuboring.\n\nHozirgi: {cur}\n\nBekor qilish: /cancel",
        "\U0001F511 Send the new keywords separated by commas (up to 10; the old ones are replaced). "
        "Send «-» to remove them.\n\nCurrent: {cur}\n\nCancel: /cancel",
        "\U0001F511 Отправьте новые ключевые слова через запятую (до 10; старые будут заменены). "
        "Чтобы убрать их, отправьте «-».\n\nСейчас: {cur}\n\nОтмена: /cancel",
    ),
    "kb_updated": _("✅ Ma'lumot yangilandi.", "✅ Entry updated.", "✅ Запись обновлена."),
    "kb_entry_gone": _("Bu ma'lumot topilmadi.", "This entry was not found.", "Эта запись не найдена."),
    "kb_deleted": _("\U0001F5D1 Ma'lumot o'chirildi.", "\U0001F5D1 Entry deleted.", "\U0001F5D1 Запись удалена."),
    "kb_settings": _(
        "⚙️ AI Shaxsiy Bilimlar sozlamalari\n\nHolat: {status}\n\n"
        "Ishlash tartibi: AI-Yordamchi mijozga javob berishdan oldin bazadan mos ma'lumotlarni topadi va shularga tayanadi. "
        "AI'ga faqat mijoz xabariga mos yozuvlar beriladi (eng ko'pi 5 ta; kalit so'zlar, sarlavha va matn bo'yicha topiladi); mos yozuv bo'lmasa, baza AI'ga umuman yuborilmaydi. "
        "Bazada yo'q ma'lumotni AI to'qimaydi.\n\nO'chirib qo'ysangiz, ma'lumotlaringiz saqlanadi, lekin AI ulardan foydalanmaydi.",
        "⚙️ AI Personal Knowledge settings\n\nStatus: {status}\n\n"
        "How it works: before replying, the AI Assistant finds the matching entries and relies on them. "
        "Only the entries matching the customer's message are given to the AI (up to 5, found by keywords, title and text); if nothing matches, the base is not sent to the AI at all. "
        "The AI does not invent facts that are not in the base.\n\nIf you turn it off, your entries are kept but the AI does not use them.",
        "⚙️ Настройки AI Личные знания\n\nСтатус: {status}\n\n"
        "Как работает: перед ответом AI-помощник находит подходящие записи и опирается на них. "
        "AI получает только записи, подходящие к сообщению клиента (до 5; ищутся по ключевым словам, заголовку и тексту); если ничего не подошло, база AI не отправляется вовсе. "
        "AI не выдумывает факты, которых нет в базе.\n\nЕсли выключить, записи сохранятся, но AI не будет их использовать.",
    ),
    "kb_privacy": _(
        "⚠️ Parol, bank karta raqami, pasport va boshqa maxfiy ma'lumot yozmang. Yozganlaringiz AI (Google Gemini) ga "
        "yuboriladi va mijozga aytilishi mumkin — faqat mijozga ochiq bo'lishi mumkin bo'lgan ma'lumotni kiriting.",
        "⚠️ Do not write passwords, bank card numbers, passport data or other confidential information. What you write "
        "is sent to the AI (Google Gemini) and may be told to customers — enter only information that is fine to share.",
        "⚠️ Не пишите пароли, номера банковских карт, паспортные и другие конфиденциальные данные. Написанное "
        "отправляется в AI (Google Gemini) и может быть сообщено клиенту — вводите только то, чем можно делиться.",
    ),
    "kb_del_confirm": _(
        "\U0001F5D1 Ushbu ma'lumot o'chirilsinmi?\n\n\U0001F4CC {title}\n\nBu amalni qaytarib bo'lmaydi.",
        "\U0001F5D1 Delete this entry?\n\n\U0001F4CC {title}\n\nThis cannot be undone.",
        "\U0001F5D1 Удалить эту запись?\n\n\U0001F4CC {title}\n\nЭто действие нельзя отменить.",
    ),
    "btn_kb_del_yes": _("✅ Ha, o'chirish", "✅ Yes, delete", "✅ Да, удалить"),
}


def t(lang, key: str, **kw) -> str:
    entry = T.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry[DEFAULT_LANG]
    if kw:
        try:
            return text.format(**kw)
        except (KeyError, IndexError):
            return entry[DEFAULT_LANG].format(**kw)
    return text


def days_unit(lang, n: int) -> str:
    """BIO matnidagi "kun" so'zi (songa mos)."""
    if lang == "en":
        return "day" if n == 1 else "days"
    if lang == "ru":
        n10, n100 = n % 10, n % 100
        if n10 == 1 and n100 != 11:
            return "день"
        if 2 <= n10 <= 4 and not 12 <= n100 <= 14:
            return "дня"
        return "дней"
    return "kun"


def all_defaults(key: str) -> set[str]:
    """Standart matnning barcha tillardagi variantlari (bazada saqlangan matn standartmi, yo'qmi — aniqlash uchun)."""
    return set(T[key].values())
