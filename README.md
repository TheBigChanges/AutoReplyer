<div align="center">

# AutoReplyer 🤖

**Smart Telegram Business automation — even when you're offline.**

Automate personal-chat replies, let an AI assistant handle conversations, schedule Sleep Mode, refresh your BIO countdown, and manage broadcasts with persistent PostgreSQL storage.

[Repository](https://github.com/TheBigChanges/AutoReplyer) · [Report a bug](https://github.com/TheBigChanges/AutoReplyer/issues) · [Request a feature](https://github.com/TheBigChanges/AutoReplyer/issues)

</div>

---

## 📌 Overview

**AutoReplyer** is a Telegram bot that connects to a user's **Telegram Business account** through Telegram's official Business chatbot connection flow. It can reply while the owner is offline, use a configurable AI assistant, switch to a separate sleep message during chosen hours, and provide account-management tools.

The project is built with **Python, `python-telegram-bot`, PostgreSQL, asyncio, and the Google Gemini API**.

> **Important:** AutoReplyer does not need your Telegram login code or account password. Connect it through Telegram's own **Settings → Telegram Business → Chatbots / Chat Automation** flow and grant only the permissions you want it to use.

## ✨ Features

### 💬 Telegram Business auto-replies

- Reply to incoming private Business messages while the owner is offline.
- Customize the standard offline reply.
- Enable or disable auto-replies from the bot's control panel.
- Configure a per-chat cooldown to avoid repetitive messages.
- Use atomic PostgreSQL reply claims to prevent concurrent messages from bypassing cooldown checks.
- Keep existing static auto-replies available when AI replies are disabled, unavailable, or over quota.

### 🧠 AI-Yordamchi (Gemini-powered assistant)

Enable an AI assistant to generate natural replies on the owner's behalf.

- Powered by the Google Gemini API.
- Supports configurable owner information and style notes.
- Includes selectable conversation styles:
  - **Personal assistant**
  - **Sales manager**
  - **Customer support**
  - **Friendly conversation**
  - **Developer representative**
  - **Formal business**
- Uses recent conversation history to maintain context.
- Pauses AI replies in a chat after the owner takes over, so the bot is less likely to interrupt a live conversation.
- Falls back to the normal auto-reply when AI is disabled, not configured, over quota, or unable to generate a reply.
- Limits ordinary users to **10 AI replies per day**. The configured administrator has unlimited AI replies.
- Uses a PostgreSQL-backed quota counter designed for atomic updates.

AI-generated messages are not guaranteed to be correct. Review important replies and configure the assistant's owner information carefully.

### 😴 Sleep Mode

Set a separate reply for your sleeping hours, for example:

```text
23:00–07:00
```

- Configure the start and end time.
- Set a custom sleep message.
- Enable or disable Sleep Mode.
- Supports schedules that cross midnight.
- Uses the `Asia/Tashkent` timezone.
- Applies the configured cooldown behavior to sleep replies.

### ⏱️ Smart cooldown

Prevent the same chat from receiving repeated standard replies too frequently.

Examples of accepted cooldown input include:

```text
1
0.5
1.5
2
1:30
```

The minimum allowed cooldown is **1 minute**. Invalid, negative, zero, or non-finite values are rejected. Database-level atomic claims help protect the cooldown when multiple updates arrive close together.

### 🕐 BIO countdown

Automatically update a connected Business account's BIO with a countdown to:

- 🎆 New Year
- 🌱 Navruz
- 🎂 The owner's birthday

BIO updates use **Tashkent local time**. A scheduled refresh runs daily at **00:05**, and a startup check updates records that are stale for the current day. BIO editing must be enabled for the connected Business account.

### 👥 Referral tracking

- Generate a personal referral link.
- Record who invited a new user.
- Prevent self-referrals and duplicate referral assignments.
- Store referral data in PostgreSQL.
- Provide referral statistics to the configured administrator.

### 📢 Admin broadcasts

Administrator tools support sending broadcast content to eligible users.

- Track broadcast progress and failed deliveries.
- Retry failed recipients.
- Persist jobs and progress in PostgreSQL.
- Resume unfinished broadcasts after a restart.
- Handle Telegram rate limits (`RetryAfter`) and users who can no longer be reached.
- Prevent multiple broadcast jobs from running at the same time.

**Delivery note:** persistent progress and retries improve reliability, but strict exactly-once delivery is not guaranteed. If the process crashes after Telegram accepts a message but before progress is saved, a recipient could receive that message again after a resume.

### 🛠️ User and admin tools

Depending on the configured permissions and enabled features, the bot also includes:

- `/start` and `/help`
- Admin statistics and broadcast controls
- User blocking and unblocking tools
- User lookup/listing and appeal/feedback handling
- A support section for questions and suggestions
- Optional force-subscription checks for a configured channel

## 🧱 Tech stack

| Component | Technology |
|---|---|
| Language | Python 3.10+ |
| Telegram integration | `python-telegram-bot` |
| Persistent database | PostgreSQL |
| Async operations | `asyncio` |
| AI replies | Google Gemini API via `httpx` |
| Configuration | Environment variables / `.env` |
| Deployment target | Render or another Python host |

## ⚡ Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/TheBigChanges/AutoReplyer.git
cd AutoReplyer
```

### 2. Create and activate a virtual environment

**Linux / macOS**

```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
# Required
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
ADMIN_ID=your_telegram_user_id

# Optional: set BOTH values to enable force-subscription
REQUIRED_CHANNEL_ID=
REQUIRED_CHANNEL_LINK=

# Optional: needed only for AI-Yordamchi
GEMINI_API_KEY=
GEMINI_MODEL=gemini-2.5-flash

# Optional: used to build the bot's referral link
BOT_USERNAME=your_bot_username
```

Replace the example values with your own. Use a PostgreSQL database that the application can reach. If force-subscription is not needed, leave both `REQUIRED_CHANNEL_ID` and `REQUIRED_CHANNEL_LINK` empty.

**Never commit `.env`, bot tokens, database credentials, or API keys to Git.**

### 5. Start the bot

```bash
python bot.py
```

On startup, the application initializes its database structures, starts Telegram polling and scheduled jobs, checks for stale BIO updates, and starts its health-check server.

### 6. Connect your Telegram Business account

1. Open Telegram **Settings**.
2. Open **Telegram Business**.
3. Choose **Chatbots** or **Chat Automation** (the wording can vary by Telegram client).
4. Find and select your bot by its username.
5. Choose which chats it may access.
6. Enable the permission to **reply to messages**.
7. Return to the bot and send `/start` to open its control panel.

Only grant the access and permissions you intend to use. Availability of Telegram Business features may depend on your Telegram account and client.

## ⚙️ Configuration

### Environment variables

| Variable | Required? | Purpose |
|---|---|---|
| `BOT_TOKEN` | Yes | Token from BotFather |
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `ADMIN_ID` | Yes | Telegram user ID allowed to use admin tools |
| `REQUIRED_CHANNEL_ID` | Optional | Channel ID or username for force-subscription |
| `REQUIRED_CHANNEL_LINK` | Optional | Invite/public link for the required channel |
| `GEMINI_API_KEY` | AI only | Google Gemini API key |
| `GEMINI_MODEL` | Optional | Gemini model name; defaults to `gemini-2.5-flash` |
| `BOT_USERNAME` | Optional | Bot username used to create referral links |
| `PORT` | Host-dependent | Port used by the health-check server when supplied by the host |

For force-subscription to be enabled, configure **both** `REQUIRED_CHANNEL_ID` and `REQUIRED_CHANNEL_LINK`. If either value is missing, the check is disabled.

### PostgreSQL

AutoReplyer stores persistent application data in PostgreSQL, including user records, Business connections, settings, cooldown/reply-claim state, BIO refresh dates, referrals, broadcast jobs, and AI-related state.

The application initializes its required database structures during startup. Keep the database URL private and use a database with persistent storage for production deployments.

### AI-Yordamchi setup

1. Create or obtain a Gemini API key from Google AI Studio.
2. Set `GEMINI_API_KEY` in your local `.env` file or hosting provider's environment settings.
3. Optionally set `GEMINI_MODEL`; the default is `gemini-2.5-flash`.
4. Restart the application and enable **AI-Yordamchi** in the bot's panel.
5. Select a role and provide useful, non-sensitive owner information or style notes.

For ordinary users, the AI quota is **10 replies per day**. The configured administrator is exempt from that quota. When AI cannot answer or the quota is exhausted, the bot can use the normal static auto-reply instead.

## 🔐 AI data and privacy

When AI-Yordamchi is enabled:

- The incoming message text and relevant conversation history are sent to Google's Gemini API to generate a reply.
- AI conversation history and usage information are stored in the configured PostgreSQL database.
- Do not put passwords, authentication codes, payment details, or other sensitive information into the assistant's owner notes.
- Anyone deploying this project should clearly disclose AI processing and data handling to users, review Google's applicable terms and privacy documentation, and set a suitable data-retention policy.
- AI output can be mistaken or incomplete; important or business-critical replies should be checked by the account owner.

AutoReplyer is not a substitute for reviewing the permissions of a connected Telegram Business account.

## 🧪 Tests

The repository includes unit and flow tests for core behavior, including cooldown validation, Sleep Mode, BIO countdowns and timezone handling, reply flows, broadcast behavior, callbacks, AI prompt construction, AI generation errors, AI reply quotas, fallback behavior, and owner-takeover pauses.

Install the test runner if it is not already available:

```bash
python -m pip install pytest
```

Run all tests from the repository root:

```bash
pytest -q
```

For more detailed output:

```bash
pytest -v
```

Tests that require a real PostgreSQL database may need a test database configured separately. Do not point integration tests at production data.

## 🚀 Deployment

AutoReplyer can be deployed to **Render** or a compatible Python hosting service.

Typical setup:

1. Create a persistent PostgreSQL database.
2. Deploy the repository as a Python service.
3. Install dependencies from `requirements.txt`.
4. Add the required environment variables in the host's dashboard.
5. Set a health-check path if your hosting provider requires one.
6. Check service logs for startup and database errors.

```text
Hosting provider
├── AutoReplyer Python service
└── PostgreSQL database
```

For production, use persistent PostgreSQL rather than relying on a local SQLite file or other ephemeral filesystem storage. Never place secrets directly in source code.

## 🗂️ Project structure

```text
AutoReplyer/
├── ai.py                 # Gemini integration and prompt construction
├── bot.py                # Telegram handlers, panels, scheduling and flows
├── db.py                 # PostgreSQL persistence and database operations
├── logic.py              # Reusable validation and business logic
├── requirements.txt      # Runtime dependencies
├── README.md
└── tests/                # Unit and flow tests
```

The exact contents of `tests/` may evolve as features are added.

## 🛡️ Reliability and security

- PostgreSQL-backed state helps preserve settings and jobs across application restarts.
- Atomic database operations protect key concurrent workflows such as cooldown claims and AI quota usage.
- Admin commands are restricted to the configured administrator ID.
- Environment variables are used for credentials and deployment configuration.
- The HTTP client logging level is reduced to help avoid leaking token-bearing Telegram URLs into logs.
- Broadcast progress is persisted, although rare crash timing can still result in duplicate delivery.

Before deploying, verify that `.env`, virtual environments, local databases, caches, and credentials are excluded from version control. Rotate any credential that has accidentally been published.

## 🗺️ Roadmap

Ideas for future improvements include:

- Automated CI test runs
- More integration tests against PostgreSQL
- Improved operational monitoring and diagnostics
- More detailed broadcast analytics
- Additional Telegram Business automation features

These are possible future improvements, not promises of a particular release date.

## 🤝 Contributing

Bug reports, suggestions, and pull requests are welcome.

Before submitting a change:

1. Explain the problem or proposed improvement.
2. Keep secrets and personal data out of commits and test fixtures.
3. Add or update tests for changed behavior.
4. Run `pytest -q` and report any failures.

## 📄 License

Please check the repository for a `LICENSE` file and its terms before redistributing or using this project in ways that require a license grant.

---

<div align="center">

**AutoReplyer — reliable Telegram Business automation, with AI when you need it.**

</div>
