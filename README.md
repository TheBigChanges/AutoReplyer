# 🤖 AutoReplyer

**AutoReplyer** — a smart automatic reply bot for your Telegram Business account.

When you are offline, sleeping, or simply don't have time to reply — **AutoReplyer replies on your behalf.**

> ⚡ Set it up once. AutoReplyer does the rest.

## ✨ Features

### 📴 Offline Auto-Reply

Automatically replies to incoming messages when you are offline.

### 😴 Sleep Mode

Set your sleeping hours and let AutoReplyer automatically respond while you are sleeping.

### ⏱ Smart Cooldown

Prevents sending repeated replies to the same chat within a configured time period.

### 🎂 BIO Countdown

Shows countdowns to:

* 🎉 New Year
* 🌱 Navruz
* 🎂 Birthday

directly in your Telegram profile BIO.

### 💼 Telegram Business Integration

Works with Telegram Business accounts and automatically handles incoming Business messages.

### 👥 Referral System

Built-in referral functionality for growing your user base.

### 📢 Admin Broadcast

Administrators can send announcements to bot users with progress tracking.

### 🔄 Resumable Broadcast

If a broadcast is interrupted, it can continue from where it stopped.

### ♻️ Failed User Retry

Failed deliveries can be retried without sending the message again to users who already received it.

### 📊 Broadcast Statistics

Track sent messages, failed deliveries, and broadcast progress.

## 🔄 How It Works

```text
Telegram Business Account
          ↓
      AutoReplyer
          ↓
   Check user status
          ↓
 ┌────────┴─────────┐
 │                  │
Offline          Sleeping
 │                  │
 └────────┬─────────┘
          ↓
     Send Reply
```

AutoReplyer checks the configured conditions and sends the appropriate response automatically.

## 🛠 Tech Stack

* Python
* Telegram Bot API
* Telegram Business API
* PostgreSQL
* SQLite
* asyncio
* python-telegram-bot

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

## ⚡ Quick Start

Get AutoReplyer running in just a few steps.

### 1. Clone the repository

```bash
git clone https://github.com/TheBigChanges/AutoReplyer.git
cd AutoReplyer
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

Create a `.env` file and add:

```env
BOT_TOKEN=your_bot_token
DATABASE_URL=your_postgresql_url
ADMIN_ID=your_telegram_id
```

### 4. Start the bot

```bash
python bot.py
```

### 5. Open Telegram

Open your bot in Telegram and run:

```text
/start
```

That's it. 🎉

AutoReplyer is now ready to be configured and used with your Telegram Business account.

## 🚀 Installation

Clone the repository:

```bash
git clone https://github.com/TheBigChanges/AutoReplyer.git
cd AutoReplyer
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment variables:

```text
BOT_TOKEN=your_bot_token
DATABASE_URL=your_postgresql_url
ADMIN_ID=your_telegram_id
```

Then start the bot:

```bash
python bot.py
```

## 🧪 Tests

Run the test suite:

```bash
pytest
```

The project includes tests for:

* BIO countdown
* Broadcast system
* Cooldown system
* Sleep Mode

## 🤖 Commands

### User Commands

```text
/start
/help
```

### Admin Commands

```text
/stats
/reklama
/reklama_status
/reklama_retry
/cancel
```

## 🔐 Security & Reliability

AutoReplyer is designed with reliability and safe message handling in mind.

It includes:

* PostgreSQL persistence
* Connection pooling
* Per-chat cooldown
* Failed delivery tracking
* Broadcast job tracking
* Resumable broadcasts
* Retry support
* Telegram Business permissions handling
* Health-check server

## 📈 Built for Growth

AutoReplyer is designed to support a growing number of users while keeping the broadcast and reply systems manageable and reliable.

Its modular structure also makes it easier to add new features in the future.

## 💡 Why AutoReplyer?

Instead of manually replying to every message, let AutoReplyer handle repetitive responses automatically.

Whether you are:

* Away from Telegram
* Sleeping
* Busy
* Unable to reply immediately

AutoReplyer keeps your Telegram Business account responsive.

## 🔗 Repository

**GitHub:**
https://github.com/TheBigChanges/AutoReplyer

## 📄 License

This project is open source.

## ⭐ Support the Project

If you find AutoReplyer useful, consider giving the repository a ⭐ on GitHub.

Every star helps the project grow.
