# 🤖 AutoReplyer

**AutoReplyer** — an automatic reply and management bot for Telegram Business accounts.

The bot connects to a Telegram Business Account and automatically replies to incoming private messages when the user is offline. It also provides features such as cooldown, custom auto-reply, referral system, admin broadcast, BIO countdown, and statistics.

---

## ✨ Features

### 💬 Smart Auto-Reply

After connecting your Telegram Business account to the bot:

* It automatically replies to incoming messages when you are offline.
* The bot does not reply to messages sent by itself.
* It ignores messages sent by you.
* It checks Telegram Business permissions.
* It prevents unnecessary repeated replies using a per-chat cooldown.

---

### ⏱️ Custom Cooldown

You can set the time between automatic replies yourself.

Supported formats:

```text
3
1.5
45 minutes
2 hours 30 minutes
1:30
```

Default cooldown:

```text
3 hours
```

---

### ✏️ Custom Auto-Reply

You can customize the message that will be sent automatically.

For example:

> Hello! I’m currently busy. I’ve seen your message and I’ll reply when I get the chance. 😊

---

### 🔗 Referral System

AutoReplyer has a referral system.

Each user can invite new users through their own referral link.

The referral system:

* processes referral links;
* connects the inviter and referred user;
* blocks self-referrals;
* prevents duplicate referrals;
* stores referral statistics.

---

### 📊 Statistics

The admin can view user statistics and referral information through the bot.

Statistics can be used to monitor:

* total users;
* referral results;
* active systems.

---

### 📢 Admin Broadcast

The admin can send a message to all bot users.

The broadcast system uses the `copy_message` mechanism to work with different Telegram message formats.

The broadcast system includes:

* progress tracking;
* failed users tracking;
* retry functionality;
* job status;
* broadcast history.

> Telegram API rate limits should be taken into account for large user bases.

---

### 🔄 Broadcast Retry

If a message fails to send to some users during a broadcast, failed users can be retried.

This is useful for temporary Telegram API errors or other delivery problems.

---

### 🎉 BIO Countdown

AutoReplyer can automatically update the Telegram Business BIO.

Supported countdowns:

* 🎆 New Year
* 🌱 Navruz
* 🎂 Birthday

You can set a birthday date for the birthday countdown.

The BIO is automatically updated with countdown information.

---

### 🗄️ PostgreSQL

AutoReplyer stores data using PostgreSQL.

Main data includes:

* users
* Telegram Business connections
* user settings
* cooldown/reply cache
* referrals
* broadcast jobs
* broadcast failures

Connection pooling is used to make database operations more stable in production environments.

---

### 🩺 Health Check

The bot includes a health-check server for deployment platforms.

This allows platforms such as Render to check whether the bot process is alive.

---

## 🏗️ Architecture

AutoReplyer works approximately according to the following flow:

```text
┌─────────────────────────┐
│ Telegram Business      │
│ Account                │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│      AutoReplyer Bot    │
│                         │
│ • Auto Reply            │
│ • Cooldown              │
│ • Referral              │
│ • Broadcast             │
│ • BIO Countdown         │
│ • Admin                 │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│       PostgreSQL        │
│                         │
│ • Users                 │
│ • Connections           │
│ • Settings              │
│ • Referrals             │
│ • Broadcast Jobs        │
└─────────────────────────┘
```

---

## 📁 Project Structure

The current project is divided into the following main components:

```text
AutoReplyer/
├── bot.py
├── logic.py
├── db.py
├── requirements.txt
├── README.md
└── data.db
```

### `bot.py`

The main part of the bot:

* Telegram handlers
* Telegram Business events
* auto-reply
* admin functions
* referral
* broadcast
* BIO countdown
* health check
* startup

### `logic.py`

Pure application logic:

* cooldown parsing
* cooldown formatting
* birthday parsing
* date/countdown calculations

### `db.py`

PostgreSQL operations:

* database connection pool
* users
* settings
* connections
* referrals
* replied cache
* broadcast jobs
* broadcast failures

### `requirements.txt`

Python dependencies.

---

## 🛠️ Requirements

To run AutoReplyer, you need:

* Python 3.10+
* PostgreSQL
* Telegram Bot Token
* Telegram Business Account
* Telegram Business Bot connection
* Environment variables

---

## ⚙️ Installation

Clone the repository:

```bash
git clone https://github.com/TheBigChanges/AutoReplyer
cd AutoReplyer
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

### Linux / macOS

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

## 🚀 Quick Start

Use the following flow to run AutoReplyer for the first time:

### 1. Create a Bot

Create a new bot through **@BotFather** on Telegram and obtain your bot token.

Keep the token secure — never publish it on GitHub or anywhere else publicly.

---

### 2. Prepare a PostgreSQL Database

AutoReplyer uses PostgreSQL.

You can use:

* local PostgreSQL;
* PostgreSQL on a VPS;
* or a managed PostgreSQL service such as Render.

Obtain the database connection string.

---

### 3. Configure Environment Variables

Create a `.env` file in the project root:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=your_postgresql_database_url
ADMIN_ID=your_telegram_user_id
```

For example:

```env
BOT_TOKEN=123456:ABCDEF...
DATABASE_URL=postgresql://user:password@host:5432/database
ADMIN_ID=123456789
```

> Never expose real bot tokens or database credentials in the README, GitHub repository, or screenshots.

---

### 4. Start the Bot

```bash
python bot.py
```

Check that the bot starts successfully in the terminal.

If you are using a deployment server, also make sure that the process remains running.

---

### 5. Open the Bot in Telegram

Find the bot you created in Telegram and send:

```text
/start
```

The bot will show you the available settings and connection options.

---

### 6. Connect Your Telegram Business Account

In Telegram:

```text
Settings
   ↓
Telegram Business
   ↓
Chatbots
   ↓
Add Chatbot
```

Connect the AutoReplyer bot to your Business Account.

Check the Business permissions requested by Telegram and grant the required permissions to the bot.

---

### 7. Configure Auto-Reply

After the Business Account is successfully connected, configure settings such as:

```text
Auto Reply
Cooldown
Custom Reply
```

For example:

```text
Cooldown:
3 hours

Auto Reply:
Hello! I’m currently offline.
I’ve seen your message and I’ll reply when I get the chance. 😊
```

---

### 8. Test It

Send a message to your Business Account from another Telegram account.

Expected flow:

```text
Another user
    │
    │ Telegram message
    ▼
Telegram Business
    │
    ▼
AutoReplyer
    │
    ├── User offline?
    ├── Cooldown passed?
    └── Is reply allowed?
             │
             ▼
       Auto-reply message
```

If the conditions are met, AutoReplyer will automatically send a reply.

---

### 9. Check Admin Functions

Use the Telegram account specified as `ADMIN_ID` to access admin functions.

For example:

```text
/stats
```

to view user and referral statistics.

```text
/reklama
```

to start a broadcast.

```text
/cancel
```

to cancel an ongoing broadcast.

---

### 10. Deploy to Production

After successful local testing, you can deploy the bot to Render, a VPS, or another Python hosting platform.

For production, check that:

* PostgreSQL connection works;
* environment variables are configured correctly;
* the bot process remains running;
* the health-check endpoint works;
* Telegram Business permissions are configured correctly;
* `.env` and secrets are not exposed in the repository.

### Quick Start Summary

```text
1. @BotFather → Create a Bot
             ↓
2. PostgreSQL → Create a Database
             ↓
3. .env → Token + Database + Admin ID
             ↓
4. pip install -r requirements.txt
             ↓
5. python bot.py
             ↓
6. Telegram → /start
             ↓
7. Telegram Business → Connect Chatbot
             ↓
8. Permissions → Grant permissions
             ↓
9. Auto Reply + Cooldown → Configure
             ↓
10. From another account → Send a test message
```

---

## 🔐 Environment Variables

Create a `.env` file:

```env
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=your_postgresql_database_url
ADMIN_ID=your_telegram_user_id
```

> Do not upload the `.env` file to the GitHub repository.

---

## ▶️ Run

Start the bot:

```bash
python bot.py
```

If you are using a production server, using a process manager or deployment platform is recommended.

---

## 🤝 Telegram Business Connection

AutoReplyer does not work simply as a regular Telegram bot. It works through **Telegram Business Account integration**.

By connecting the bot to a Telegram Business Account, Business messages can be managed through a flow such as:

```text
Telegram
   ↓
Settings
   ↓
Telegram Business
   ↓
Chatbots
   ↓
AutoReplyer
```

The relevant Business permissions provided by Telegram are required for the bot to work.

---

## 🔒 Security

AutoReplyer stores user data and Telegram Business connections in PostgreSQL.

For production deployment:

* Keep the bot token secret.
* Keep database credentials secret.
* Do not commit the `.env` file.
* Do not upload local database files such as `data.db` to the repository.
* Use GitHub secrets/environment variables.
* Do not expose PostgreSQL credentials in logs.
* Do not unnecessarily log Telegram user information.

---

## 🧪 Testing

As the project develops, tests are planned for the following components:

```text
tests/
├── test_cooldown.py
├── test_bio.py
├── test_referrals.py
└── test_broadcast.py
```

The main edge cases that should be tested:

* cooldown parsing;
* invalid time formats;
* birthday date calculation;
* New Year/Navruz countdown;
* duplicate referrals;
* self-referral;
* Business message guards;
* broadcast failures;
* broadcast retry.

---

## 🚀 Roadmap

### Security & Privacy

* [ ] Remove `data.db` from repository/history
* [ ] Strengthen `.gitignore`
* [ ] Secrets audit
* [ ] Production security review

### Reliability

* [x] PostgreSQL
* [x] Connection pooling
* [x] Structured logging
* [x] Health check
* [ ] Broader exception recovery
* [ ] Monitoring

### Testing

* [ ] Cooldown tests
* [ ] Referral tests
* [ ] BIO tests
* [ ] Broadcast tests
* [ ] Business event tests

### Architecture

* [ ] Split into `handlers/`
* [ ] Split into `services/`
* [ ] Split into `database/` module
* [ ] Split into `utils/` module

Future structure:

```text
AutoReplyer/
├── bot.py
├── config.py
│
├── database/
│   ├── connection.py
│   ├── users.py
│   ├── settings.py
│   ├── referrals.py
│   └── connections.py
│
├── handlers/
│   ├── start.py
│   ├── panel.py
│   ├── referral.py
│   ├── admin.py
│   └── business.py
│
├── services/
│   ├── autoreply.py
│   ├── broadcast.py
│   └── bio.py
│
├── utils/
│   ├── cooldown.py
│   └── dates.py
│
└── tests/
```

### Scalability

* [ ] Broadcast queue
* [ ] Retry/backoff
* [ ] Background workers
* [ ] Redis integration if needed
* [ ] Advanced rate-limit handling
* [ ] Broadcast analytics

### Analytics

* [ ] Daily active users
* [ ] Referral conversion
* [ ] Business connection conversion
* [ ] Auto-reply usage
* [ ] Broadcast delivery statistics
* [ ] Feature usage analytics

---

## 📈 Future Architecture

For a large user base, the architecture can be expanded as follows:

```text
                 Telegram
                     │
                     ▼
              ┌─────────────┐
              │ AutoReplyer │
              │    Bot      │
              └──────┬──────┘
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   ┌─────────────┐       ┌─────────────┐
   │ PostgreSQL  │       │ Job Queue   │
   └─────────────┘       └──────┬──────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
                Broadcast      BIO         Workers
```

This architecture allows large broadcasts, background jobs, and other heavy tasks to be separated from the main Telegram update processing.

---

## 📊 Admin Commands

Main admin functions:

```text
/stats
```

View bot user statistics.

```text
/reklama
```

Send a broadcast to all users.

```text
/cancel
```

Cancel a pending admin broadcast.

Broadcast-related status/retry functions are also available.

---

## 🧠 Design Principles

AutoReplyer is being developed around the following principles:

* ⚡ Async Telegram API processing
* 🗄️ PostgreSQL persistence
* 🔐 Security-first configuration
* 🧩 Modular architecture
* 📊 Observable background jobs
* 🔄 Retryable operations
* 🚀 Scalable design
* 🧪 Testable business logic

---

## 📄 License

The license will be determined by the project owner later.

---

## 👨‍💻 Author

**Dilshodbek**

GitHub:

github.com/TheBigChanges

---

## ⭐ Support

If AutoReplyer is useful to you, consider giving the repository a ⭐ star.

For bugs or feature requests, use GitHub Issues.

---

> **AutoReplyer** — a Telegram automation bot that helps manage your Telegram Business account automatically while you are offline.
