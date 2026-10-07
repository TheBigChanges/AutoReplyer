# 🤖 AutoReplyer

**AutoReplyer** is a Telegram Business automation bot that automatically replies to incoming messages when you are offline, sleeping, or unavailable.

Connect your Telegram Business account, configure your reply settings, and let AutoReplyer handle repetitive messages for you.

> ⚡ **Set it up once. AutoReplyer keeps your Telegram Business account responsive.**

---

## ✨ Features

### 📴 Offline Auto-Reply

Automatically replies to incoming Telegram Business messages when you are marked as offline.

You can configure your own reply message from the bot's control panel.

---

### 😴 Sleep Mode

Automatically enables a separate reply during your configured sleeping hours.

Features include:

- Custom sleep schedule
- Custom sleep reply
- Supports schedules crossing midnight
- Example: `23:00-07:00`
- Uses **Tashkent time (`Asia/Tashkent`)**

---

### ⏱ Smart Cooldown

Prevents AutoReplyer from repeatedly replying to the same chat within a configured period.

The cooldown system includes:

- Custom cooldown duration
- Minimum cooldown of 1 minute
- Multiple input formats
- Protection against invalid values such as `NaN` and `Infinity`
- Database-level atomic reply claiming to prevent concurrent duplicate replies

Examples:

```text
30 minutes
2 hours
2:30
1.5
```

---

### 🎂 BIO Countdown

Automatically updates your Telegram Business account BIO with a countdown to:

- 🎆 New Year
- 🌷 Navruz
- 🎂 Birthday

Examples:

```text
🎆 Yangi yilga 85 kun qoldi!
```

or:

```text
🎂 Bugun tug'ilgan kunim!
```

The countdown uses **Tashkent time** and automatically refreshes every day.

If the server was offline during the scheduled update, AutoReplyer performs a startup check and updates stale BIOs.

---

### 💼 Telegram Business Integration

AutoReplyer works through Telegram's official Business account automation flow.

You do **not** need to provide:

- Your phone number
- Telegram login code
- Telegram password
- Session files

Your Telegram Business account is connected through Telegram's own Business → Chatbots interface.

---

### 👥 Referral System

AutoReplyer includes a built-in referral system.

Each user receives a personal referral link that can be shared with friends.

The bot tracks:

- Referrer
- Referred users
- Referral counts

Administrators can also view referral statistics.

---

### 📢 Admin Broadcast

Administrators can send announcements to bot users.

The broadcast system provides:

- Progress tracking
- Sent message count
- Failed message count
- Persistent broadcast jobs
- Resume after restart
- Failed-user tracking
- Retry failed deliveries
- Protection against multiple broadcasts running simultaneously

---

### 🔄 Resumable Broadcasts

Broadcast progress is stored in PostgreSQL.

If the server restarts while a broadcast is running, AutoReplyer can continue the job using its stored progress.

This means a temporary deployment or server interruption does not automatically lose the entire broadcast job.

---

### ♻️ Failed User Retry

If some users cannot receive a broadcast, their IDs are stored as failed deliveries.

The administrator can later run:

```text
/reklama_retry
```

to retry the failed users without intentionally sending the retry broadcast to users who already succeeded.

---

### 📊 Admin Statistics

Administrators can view bot statistics and broadcast information directly from Telegram.

Available admin commands include:

```text
/stats
/reklama
/reklama_status
/reklama_retry
/cancel
```

---

## 🔄 How It Works

```text
                    Telegram Business Account
                              │
                              ▼
                         AutoReplyer
                              │
                              ▼
                    Incoming Business Message
                              │
                              ▼
                    Check account settings
                              │
                 ┌────────────┴────────────┐
                 │                         │
              Offline?                 Sleep Mode?
                 │                         │
                 └────────────┬────────────┘
                              │
                              ▼
                       Check Cooldown
                              │
                              ▼
                         Send Reply
```

AutoReplyer checks the user's configured state and determines whether an automatic reply should be sent.

---

## 🛠 Tech Stack

- **Python**
- **python-telegram-bot**
- **Telegram Bot API**
- **Telegram Business API**
- **PostgreSQL**
- **psycopg2**
- **asyncio**
- **python-dotenv**
- **Python `zoneinfo`**

The production database is **PostgreSQL**. AutoReplyer does not rely on SQLite for persistent production data.

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

### Main files

| File | Purpose |
|------|---------|
| `bot.py` | Telegram bot, Business messages, UI, commands, broadcasts and scheduled jobs |
| `db.py` | PostgreSQL connection pool, database schema and persistence |
| `logic.py` | Cooldown, BIO and Sleep Mode logic |
| `requirements.txt` | Production Python dependencies |
| `tests/` | Automated tests for core functionality |

---

# ⚡ Quick Start

Get AutoReplyer running in a few steps.

## 1. Clone the repository

```bash
git clone https://github.com/TheBigChanges/AutoReplyer.git
cd AutoReplyer
```

---

## 2. Create a virtual environment

Recommended:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
python -m venv .venv
.venv\Scripts\activate
```

---

## 3. Install dependencies

Install the production dependencies:

```bash
pip install -r requirements.txt
```

If you also want to run the test suite:

```bash
pip install pytest
```

---

## 4. Create a PostgreSQL database

AutoReplyer requires a PostgreSQL database.

You can use:

- Supabase
- Neon
- Render PostgreSQL
- Any PostgreSQL-compatible database

You will need a PostgreSQL connection URL such as:

```text
postgresql://username:password@host:5432/database
```

---

## 5. Create your `.env` file

Create a file named:

```text
.env
```

Add the required configuration:

```env
BOT_TOKEN=your_bot_token
DATABASE_URL=your_postgresql_url
ADMIN_ID=your_telegram_user_id
```

### Optional configuration

```env
BOT_USERNAME=your_bot_username

REQUIRED_CHANNEL_ID=-1001234567890
REQUIRED_CHANNEL_LINK=https://t.me/your_channel
```

### Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | ✅ | Telegram Bot API token |
| `DATABASE_URL` | ✅ | PostgreSQL connection URL |
| `ADMIN_ID` | ✅ | Telegram user ID of the administrator |
| `BOT_USERNAME` | ❌ | Bot username used by the referral system and connection instructions |
| `REQUIRED_CHANNEL_ID` | ❌ | Telegram channel ID for force subscription |
| `REQUIRED_CHANNEL_LINK` | ❌ | Link to the required channel |

`REQUIRED_CHANNEL_ID` and `REQUIRED_CHANNEL_LINK` should be configured together. If they are not both configured, force subscription is disabled.

---

## 6. Start the bot

```bash
python bot.py
```

On startup, AutoReplyer initializes the PostgreSQL database automatically.

No manual SQL migration is required for a fresh installation.

---

## 7. Open the bot in Telegram

Open your bot and send:

```text
/start
```

You can then configure your AutoReplyer settings from the Telegram interface.

🎉 **That's it! AutoReplyer is ready.**

---

# 💼 Connect Your Telegram Business Account

After starting AutoReplyer:

1. Open **Telegram Settings**
2. Open **Telegram Business**
3. Open **Chatbots** / **Chat Automation**
4. Add your AutoReplyer bot
5. Give the bot access to the chats you want it to manage
6. Enable the permission to **reply to messages**
7. Return to AutoReplyer and send:

```text
/start
```

AutoReplyer will detect the Business connection and open the configuration panel.

> Make sure the bot has the required Telegram Business permissions before testing automatic replies.

---

# 🎛 Available User Features

From the user panel you can configure:

```text
Offline / Online
        │
        ├── Auto-reply message
        │
        ├── Reply cooldown
        │
        ├── Sleep Mode
        │      ├── Enable / Disable
        │      ├── Sleep schedule
        │      └── Sleep reply
        │
        └── BIO Countdown
               ├── New Year
               ├── Navruz
               └── Birthday
```

---

# 🤖 Bot Commands

## User

```text
/start
```

`/start` opens the main AutoReplyer interface.

The rest of the user functionality is available through the interactive Telegram buttons.

---

## Admin

```text
/stats
```

View bot statistics.

```text
/reklama
```

Start a broadcast.

```text
/reklama_status
```

View the current broadcast status.

```text
/reklama_retry
```

Retry failed broadcast deliveries.

```text
/cancel
```

Cancel the current admin operation.

---

# 📢 Broadcast System

Broadcasts are stored in PostgreSQL as persistent jobs.

A broadcast tracks:

```text
Job
├── Status
├── Total users
├── Last processed user
├── Sent count
├── Failed count
└── Update timestamps
```

If a broadcast is interrupted, AutoReplyer can resume it from the stored progress.

The database also prevents multiple broadcast jobs from running simultaneously.

### Important reliability note

The broadcast system is designed for **persistent and resumable delivery**, but Telegram message delivery cannot be guaranteed to be mathematically exactly-once across every possible process crash.

For example, if Telegram accepts a message and the server crashes before AutoReplyer records the progress, the same user may be attempted again after restart.

---

# 🔐 Security & Reliability

AutoReplyer includes several protections for production use.

### Database

- PostgreSQL persistence
- Connection pooling
- Persistent broadcast jobs
- Database migrations during startup
- Safe settings-field whitelist
- Persistent referral data

### Reply system

- Per-chat cooldown
- Atomic database-level cooldown claim
- Minimum cooldown validation
- Protection against invalid numeric values
- Cooldown state stored in PostgreSQL

### Broadcast system

- Persistent job state
- Single-running-broadcast protection
- Failed-user tracking
- Retry support
- Resume after restart
- Progress tracking

### Telegram Business

- Uses Telegram Business connection IDs
- Respects Business permissions
- Checks whether the connected account can reply
- Checks whether BIO editing is available before changing the BIO

### Health Check

When deployed on platforms such as Render, AutoReplyer starts an HTTP health-check server using the platform-provided `PORT` environment variable.

---

# 🌍 Time Zone

AutoReplyer uses:

```text
Asia/Tashkent
```

for user-facing time-sensitive features.

This is especially important for:

- BIO countdowns
- Birthday countdowns
- Navruz countdown
- New Year countdown
- Sleep Mode

---

# 🧪 Tests

The repository includes tests for the main logic components.

Run the test suite with:

```bash
pip install pytest
pytest
```

Current test areas include:

```text
tests/
├── test_bio.py
├── test_broadcast.py
├── test_cooldown.py
└── test_sleep.py
```

The tests cover areas such as:

- BIO date calculations
- Tashkent date handling
- Cooldown parsing
- Invalid cooldown values
- Cooldown minimum limits
- Sleep schedule parsing
- Midnight-crossing sleep schedules
- Broadcast behavior
- Broadcast concurrency protection
- Retry behavior

---

# ☁️ Deployment

AutoReplyer is designed to run as a long-running Python service.

A typical production setup looks like:

```text
                Telegram
                    │
                    ▼
              AutoReplyer
                    │
          ┌─────────┴─────────┐
          │                   │
          ▼                   ▼
     Telegram API        PostgreSQL
                              │
                              ▼
                         Persistent Data
```

For platforms such as **Render**, configure the environment variables:

```env
BOT_TOKEN=...
DATABASE_URL=...
ADMIN_ID=...
BOT_USERNAME=...
```

Then start the service with:

```bash
python bot.py
```

The application also starts an HTTP health-check server using the `PORT` environment variable provided by the hosting platform.

---

# 📌 Production Notes

### PostgreSQL is required

The bot is designed around PostgreSQL persistence.

Do not rely on local SQLite files for production data.

### Protect your `.env`

Never commit your real credentials to GitHub.

Your `.env` should contain secrets such as:

```text
BOT_TOKEN
DATABASE_URL
```

and should remain private.

### Telegram permissions matter

For Telegram Business automation to work correctly, the connected bot must have the required Business permissions.

In particular, the bot needs permission to reply to messages.

---

# 🗺️ Roadmap

Possible future improvements include:

- More advanced reply rules
- More automation conditions
- Improved broadcast delivery guarantees
- Additional statistics
- More BIO customization
- Additional Telegram Business automation features
- Improved administration tools
- More automated integration tests

---

# 💡 Why AutoReplyer?

AutoReplyer is designed for people who want their Telegram Business account to remain responsive without manually answering every message.

Whether you are:

- 💤 Sleeping
- 📴 Offline
- 💼 Busy
- ⏳ Temporarily unavailable

AutoReplyer can handle repetitive replies automatically.

---

# 🔗 Repository

**GitHub:**

https://github.com/TheBigChanges/AutoReplyer

---

# 📄 License

This project is open source.

---

# ⭐ Support the Project

If you find **AutoReplyer** useful, consider giving the repository a ⭐ on GitHub.

Every star helps the project grow and motivates further development.

**Built with Python + Telegram + PostgreSQL. ❤️**
