# AutoReplyer 🤖

**AutoReplyer** is a Telegram Business auto-reply bot designed to automatically respond to incoming messages when the account owner is offline, while providing smart cooldown control, Sleep Mode, BIO countdowns, referrals, and reliable administrator broadcast tools.

The project is built with **Python, python-telegram-bot, PostgreSQL, and asyncio**, with a focus on reliability, concurrency safety, and persistent state.

---

## ✨ Features

### 💬 Offline Auto-Reply

AutoReplyer automatically responds to incoming Telegram Business messages when the account owner is offline.

Features include:

- Custom auto-reply message
- Enable/disable auto-reply
- Telegram Business account integration
- Persistent settings
- Per-chat cooldown
- Atomic reply claiming to prevent duplicate replies during concurrent messages

---

### 😴 Sleep Mode

Sleep Mode allows users to automatically send a separate response during configured sleeping hours.

Example:

```text
23:00–07:00
```

During this period, AutoReplyer sends a customizable sleep message instead of the normal offline reply.

Features:

- Custom sleep schedule
- Midnight-crossing schedules
- Custom sleep reply
- Enable/disable Sleep Mode
- Same cooldown protection as normal auto-replies
- Tashkent timezone support

---

### ⏱️ Smart Cooldown

AutoReplyer prevents repeated replies to the same chat within the configured cooldown period.

Cooldown input supports values such as:

```text
1
0.5
1.5
2
1:30
```

The minimum allowed cooldown is **1 minute**.

Invalid values such as:

```text
0
-1
nan
inf
1e999
```

are rejected.

The reply system uses an **atomic PostgreSQL claim operation**, preventing concurrent messages from bypassing the cooldown.

---

### 🕐 BIO Countdown

AutoReplyer can automatically update a Telegram Business account BIO with countdown information for:

- 🎆 New Year
- 🌱 Navruz
- 🎂 Birthday

The BIO system uses the **Asia/Tashkent** timezone.

BIO refresh is handled in two ways:

- Daily refresh at **00:05 Tashkent time**
- Startup refresh shortly after the bot starts

The startup refresh only updates stale BIO records, avoiding unnecessary Telegram API calls.

---

### 📱 Telegram Business Integration

AutoReplyer works with Telegram Business accounts through Telegram Business connection updates.

The bot stores information such as:

- Business connection ID
- Owner ID
- Reply permissions
- BIO editing permissions
- Connection status

Architecture:

```text
Telegram Business Account
          ↓
     AutoReplyer Bot
          ↓
       PostgreSQL
```

---

### 👥 Referral System

AutoReplyer includes a referral system for tracking invited users.

The system:

- Stores inviter relationships
- Prevents self-referrals
- Prevents duplicate referral assignments
- Uses PostgreSQL persistence

---

### 📢 Admin Broadcast

Administrators can send broadcasts to eligible users.

The broadcast system supports:

- Text messages
- Telegram message content
- Progress tracking
- Failed-user tracking
- Retry functionality
- Persistent jobs
- Concurrent broadcast protection
- Broadcast resumption after restart
- Telegram `RetryAfter` handling
- Forbidden-user handling
- Database-backed progress

Only one broadcast job can be in the `running` state at a time.

---

### 🔄 Resumable Broadcasts

Broadcast jobs are stored in PostgreSQL.

If the bot restarts during a broadcast, the unfinished job can be resumed using its persisted progress.

The system tracks the last processed user so that it does not need to restart the entire broadcast from the beginning.

---

### ♻️ Failed User Retry

Users who could not receive a broadcast are recorded separately.

Administrators can retry failed deliveries without recreating the original broadcast manually.

This allows temporary Telegram/API failures to be retried later.

---

### 📊 Admin Statistics

Administrators can inspect bot statistics through the admin commands.

Statistics include information about registered users and connected Business accounts.

---

### 🆘 Help Command

The `/help` command provides users with the available bot functionality.

Regular users receive user-facing commands, while administrators also receive administrator commands.

---

## 🛡️ Reliability & Concurrency

AutoReplyer is designed to handle concurrent events safely.

Important protections include:

### Atomic reply claims

Instead of:

```text
check cooldown
      ↓
send message
      ↓
update cooldown
```

AutoReplyer uses an atomic database claim:

```text
Message A → claim ✅ → send
Message B → claim ❌ → ignored
```

This prevents two simultaneous messages from both passing the cooldown check.

### Broadcast locking

PostgreSQL prevents multiple broadcast jobs from running simultaneously.

If another broadcast is already running, the bot returns a user-friendly error instead of starting a second job.

---

## 🗄️ Database

AutoReplyer uses **PostgreSQL** for persistent production data.

Database responsibilities include:

- User data
- Business connections
- Settings
- Cooldown state
- Reply claims
- BIO refresh state
- Referral relationships
- Broadcast jobs
- Broadcast progress
- Failed broadcast deliveries

Database migrations are handled by the application during initialization.

---

## 🕐 Timezone

The application uses:

```text
Asia/Tashkent
```

for time-sensitive functionality such as:

- BIO countdowns
- Daily BIO refresh
- Sleep Mode

This ensures that scheduled functionality follows Uzbekistan local time.

---

## 📁 Project Structure

```text
AutoReplyer/
├── bot.py
├── db.py
├── logic.py
├── requirements.txt
├── .env
├── .gitignore
├── README.md
├── tests/
│   ├── test_bio.py
│   ├── test_bio_refresh.py
│   ├── test_bio_refresh_db
│   ├── test_bio_timezone.py
│   ├── test_broadcast.py
│   ├── test_broadcast_lock.py
│   ├── test_callbacks.py
│   ├── test_cooldown.py
│   ├── test_help.py
│   ├── test_reply_claim_db.py
│   ├── test_reply_flow.py
│   └── test_sleep.py
└── data.db
```

> `data.db` is ignored by Git and is not required for the production PostgreSQL deployment.

---

## 🧪 Tests

AutoReplyer currently contains **12 test files** covering core functionality, database behavior, concurrency, callbacks, cooldown validation, BIO handling, Sleep Mode, and command behavior.

### Test suite

| Test | Coverage |
|---|---|
| `test_bio.py` | BIO countdown calculations with custom dates |
| `test_bio_refresh.py` | Startup and daily BIO refresh behavior |
| `test_bio_refresh_db` | `bio_updated_on` database functionality |
| `test_bio_timezone.py` | BIO generation using Tashkent timezone |
| `test_broadcast.py` | Broadcast and concurrent broadcast handling |
| `test_broadcast_lock.py` | PostgreSQL broadcast locking and error handling |
| `test_callbacks.py` | Callback response behavior |
| `test_cooldown.py` | Cooldown parsing and minimum-value validation |
| `test_help.py` | `/help` behavior for users and administrators |
| `test_reply_claim_db.py` | Atomic PostgreSQL reply claims |
| `test_reply_flow.py` | Auto-reply claim flow and error handling |
| `test_sleep.py` | Sleep Mode parsing and time-window logic |

Run the test suite with:

```bash
pytest -q
```

For more detailed output:

```bash
pytest -v
```

---

## ⚙️ Requirements

- Python 3.10+
- PostgreSQL
- Telegram Bot Token
- Telegram Business account
- Telegram Business connection
- `python-telegram-bot`
- `psycopg2`
- `python-dotenv`

---

## 📦 Installation

Clone the repository:

```bash
git clone https://github.com/TheBigChanges/AutoReplyer.git
cd AutoReplyer
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

### Linux

```bash
source .venv/bin/activate
```

### Windows

```powershell
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 🔐 Environment Variables

Create a `.env` file:

```env
BOT_TOKEN=your_bot_token
DATABASE_URL=your_postgresql_database_url
ADMIN_ID=your_telegram_user_id
REQUIRED_CHANNEL_ID=your_channel_id
```

Depending on the enabled configuration, additional environment variables may be required by the application.

**Never commit `.env` to Git.**

---

## 🗃️ PostgreSQL Setup

Create a PostgreSQL database and provide its connection URL through:

```env
DATABASE_URL=postgresql://user:password@host:5432/database
```

On startup, AutoReplyer initializes the required database structures and migrations.

---

## ▶️ Running Locally

After configuring `.env`:

```bash
python bot.py
```

The application starts:

1. Database initialization
2. Telegram bot
3. Scheduled BIO jobs
4. Broadcast resume handling
5. Health-check server
6. Telegram polling

---

## 🤖 Bot Commands

### User commands

```text
/start
/help
```

### Administrator commands

```text
/stats
/reklama
/reklama_status
/reklama_retry
/cancel
```

Administrator commands are restricted to the configured `ADMIN_ID`.

---

## 📢 Broadcast Workflow

A typical administrator broadcast follows this flow:

```text
/reklama
      ↓
Select/send content
      ↓
Create broadcast job
      ↓
Send to eligible users
      ↓
Track progress
      ↓
Record failures
      ↓
Complete
```

If the bot restarts during a broadcast:

```text
PostgreSQL
    ↓
Load unfinished job
    ↓
Resume from saved progress
```

Failed users can later be retried separately.

### Delivery guarantee

Broadcast delivery is designed around persistent progress and retries, but it is not a strict exactly-once delivery system.

There is a small **at-least-once delivery edge case**:

```text
Telegram accepts message
        ↓
Process crashes
        ↓
Progress update is not saved
        ↓
Job resumes
        ↓
Same user may receive the message again
```

Therefore, duplicate delivery is possible in this rare crash window.

---

## 🔒 Security & Repository Hygiene

The repository includes a `.gitignore` covering local and sensitive files such as:

```text
.env
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
data.db
```

Production secrets should always be supplied through environment variables.

---

## 🚀 Deployment

AutoReplyer can be deployed on services such as **Render** with:

- Python runtime
- PostgreSQL database
- Environment variables
- Health-check endpoint

The application reads the platform-provided `PORT` environment variable for its health server.

Typical production flow:

```text
Render
 ├── AutoReplyer
 └── PostgreSQL
```

---

## ❤️ Project Goals

AutoReplyer is designed to be:

- Reliable
- Lightweight
- Easy to configure
- PostgreSQL-backed
- Concurrency-safe
- Telegram Business compatible
- Suitable for long-running deployment

The project continues to evolve through additional tests, reliability improvements, and new Telegram Business features.

---

## 🗺️ Roadmap

Possible future improvements include:

- GitHub Actions CI
- More integration tests
- Improved production diagnostics
- More advanced broadcast analytics
- Additional Business account automation
- Further database and deployment hardening

---

## 📄 License

This project is maintained by **TheBigChanges**.

See the repository for the current licensing information.

---

## 👨‍💻 Development

Contributions, bug reports, and feature ideas are welcome.

Before submitting changes:

```bash
pytest -q
```

Make sure sensitive configuration files remain untracked and that new functionality includes appropriate tests.

---

**AutoReplyer — smart Telegram Business automation with reliable replies, Sleep Mode, BIO countdowns, and production-ready broadcast tools.**
