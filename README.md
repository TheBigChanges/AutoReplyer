# 🤖 AutoReplyer

**AutoReplyer** — Telegram Business akkauntingiz uchun aqlli avtomatik javob beruvchi bot.

Siz offline bo‘lsangiz, uxlayotgan bo‘lsangiz yoki javob berishga vaqtingiz bo‘lmasa — **AutoReplyer sizning o‘rningizga javob beradi.**

> ⚡ Bir marta sozlang. Qolganini AutoReplyer qiladi.

---

## ✨ Features

### 📴 Offline Auto-Reply

Telegram Business akkauntingizga kimdir yozsa va siz **offline rejimda** bo‘lsangiz, AutoReplyer avtomatik javob yuboradi.

O‘zingiz xohlagan javob matnini sozlashingiz mumkin.

### 😴 Sleep Mode

Uyqu vaqtingizni belgilang:

```text
23:00–07:00
```

Belgilangan vaqt davomida AutoReplyer avtomatik ravishda **Sleep Mode** javobini yuboradi.

Sleep Mode siz online bo‘lganingizda ham ishlashi mumkin.

### ⏱ Smart Cooldown

Bir xil chatga ketma-ket javob yuborib, spamga aylanib qolmasligi uchun cooldown tizimi mavjud.

Masalan:

```text
3 soat
45 daqiqa
1 soat 30 daqiqa
```

Cooldown davomida bir chatga qayta avtomatik javob yuborilmaydi.

### 🎂 BIO Countdown

Telegram BIO orqali muhim sanalargacha qolgan kunlarni ko‘rsatish mumkin:

* 🎆 Yangi yil
* 🌷 Navro‘z
* 🎂 Tug‘ilgan kun

Masalan:

```text
🎂 Tug‘ilgan kunimga 12 kun qoldi!
```

### 👤 Telegram Business Integration

AutoReplyer Telegram Business akkauntingiz bilan ulanadi va Business API orqali xabarlarni boshqaradi.

Bot:

* Business akkauntni ulaydi
* Kerakli huquqlarni tekshiradi
* Business message'larni qabul qiladi
* Avtomatik javob yuboradi
* Ulanish holatini kuzatadi

### 🎁 Referral System

Foydalanuvchilar botni boshqalarga tavsiya qilishi mumkin.

Referral tizimi orqali:

* taklif qilgan foydalanuvchilarni hisoblash
* referral statistikasi
* foydalanuvchilarni kuzatish

imkoniyatlari mavjud.

### 📢 Admin Broadcast

Admin barcha foydalanuvchilarga xabar yuborishi mumkin.

Qo‘llab-quvvatlanadi:

* 📝 Text
* 🖼 Image
* 🎥 Video
* 📎 Boshqa Telegram message turlari

Broadcast tizimi katta foydalanuvchilar soni uchun **batch/keyset pagination** asosida ishlaydi.

### 🔄 Resumable Broadcast

Agar server restart bo‘lsa yoki broadcast kutilmaganda to‘xtasa, job holati PostgreSQL'da saqlanadi.

Shuning uchun tizim keyinchalik broadcastni davom ettira oladi.

### 🔁 Failed User Retry

Xabar yuborilmagan foydalanuvchilar alohida saqlanadi.

Admin:

```text
/reklama_retry
```

orqali muvaffaqiyatsiz yuborilgan foydalanuvchilarga qayta urinishi mumkin.

### 📊 Broadcast Statistics

Admin broadcast holatini tekshirishi mumkin:

```text
/reklama_status
```

Natijada:

```text
Holat: completed
Jami: 1000
Yuborildi: 970
Xato: 30
```

kabi ma'lumotlar ko‘rsatiladi.

---

## 🧠 How It Works

AutoReplyer quyidagi oqim asosida ishlaydi:

```text
Telegram Business Account
          │
          ▼
      AutoReplyer
          │
          ├── Online / Offline
          ├── Sleep Mode
          ├── Cooldown
          └── Custom Reply
          │
          ▼
      Telegram User
```

Barcha muhim ma'lumotlar **PostgreSQL** bazasida saqlanadi.

---

## 🛠 Tech Stack

| Technology             | Purpose             |
| ---------------------- | ------------------- |
| 🐍 Python              | Backend             |
| 🤖 python-telegram-bot | Telegram Bot API    |
| 🐘 PostgreSQL          | Persistent database |
| ⚡ asyncio              | Background tasks    |
| 🌐 Render              | Deployment          |
| 🧪 unittest            | Testing             |

---

## 📁 Project Structure

```text
AutoReplyer/
├── bot.py
├── db.py
├── logic.py
├── requirements.txt
├── README.md
└── tests/
    ├── test_bio.py
    ├── test_broadcast.py
    ├── test_cooldown.py
    └── test_sleep.py
```

### `bot.py`

Telegram botning asosiy logikasi:

* commands
* Telegram Business integration
* auto-reply
* Sleep Mode
* broadcast
* admin functions

### `db.py`

PostgreSQL bilan ishlash:

* users
* settings
* connections
* referrals
* cooldown cache
* broadcast jobs
* broadcast failures

### `logic.py`

Side-effect'siz helper funksiyalar:

* cooldown parsing
* time parsing
* Sleep Mode calculation
* BIO countdown

### `tests/`

Loyihaning asosiy funksiyalarini tekshiruvchi testlar.

---

## 🚀 Installation

Repository'ni clone qiling:

```bash
git clone https://github.com/TheBigChanges/AutoReplyer.git
cd AutoReplyer
```

Virtual environment yarating:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Dependencies o‘rnating:

```bash
pip install -r requirements.txt
```

---

## 🔐 Environment Variables

Quyidagi environment variable'lar kerak:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=your_postgresql_database_url
ADMIN_ID=your_telegram_user_id
REQUIRED_CHANNEL_ID=your_channel_id
```

**Bot token va database credentials'ni hech qachon GitHub'ga joylamang.**

---

## ▶️ Run

```bash
python bot.py
```

Production deployment uchun Render yoki boshqa Python hosting xizmatidan foydalanish mumkin.

---

## 🧪 Run Tests

Barcha testlarni ishga tushirish:

```bash
python -m unittest discover -s tests -v
```

Yoki alohida:

```bash
python -m unittest tests.test_sleep -v
```

---

## 🤖 Bot Commands

### User

```text
/start
```

Botni ishga tushirish va boshqaruv panelini ochish.

### Admin

```text
/stats
```

Foydalanuvchilar statistikasini ko‘rish.

```text
/reklama
```

Broadcast yaratish.

```text
/reklama_status
```

Joriy broadcast holatini ko‘rish.

```text
/reklama_retry
```

Yuborilmagan foydalanuvchilarga qayta urinib ko‘rish.

```text
/cancel
```

Joriy admin amalini bekor qilish.

---

## 🔒 Security & Reliability

AutoReplyer quyidagi himoya va ishonchlilik mexanizmlaridan foydalanadi:

* PostgreSQL persistent storage
* Settings whitelist
* Telegram Business permissions checking
* Per-chat cooldown
* Failed broadcast tracking
* Resumable broadcast jobs
* Background broadcast processing
* Error handling
* Telegram API error handling
* Input validation

---

## 📈 Built for Growth

AutoReplyer kichik foydalanuvchi bazasidan boshlab kattaroq audience'ga kengaytirish uchun ishlab chiqilgan.

Broadcast tizimida foydalanuvchilar birdaniga RAM'ga yuklanmaydi — ular **batch va keyset pagination** orqali bosqichma-bosqich qayta ishlanadi.

Bu katta foydalanuvchilar bazasida memory usage'ni nazorat qilishga yordam beradi.

---

## 💡 Why AutoReplyer?

Telegram Business akkauntingizni doim qo‘lda nazorat qilish shart emas.

AutoReplyer siz uchun:

**📩 xabarlarni kutadi
🤖 avtomatik javob beradi
😴 uyqu vaqtida ishlaydi
⏱ spamni kamaytiradi
🎂 BIO'ni yangilaydi
📢 admin broadcastlarni boshqaradi**

---

## 🌐 Repository

**GitHub:**
https://github.com/TheBigChanges/AutoReplyer

---

## 📄 License

This project is currently maintained by **TheBigChanges**.

---

### ⭐ Support the Project

Agar AutoReplyer foydali bo‘lsa, repository'ga ⭐ **Star** qoldirishni unutmang!

Har bir star loyiha rivojlanishiga yordam beradi. 🚀
