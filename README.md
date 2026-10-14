<div align="center">

# 🤖 AutoReplyer

### Your Telegram Business assistant — replies, automation, and a live profile clock.

**Built with Python · Telegram Business · PostgreSQL · Google Gemini**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Try%20the%20bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/autoreplyer_dbot)
[![News](https://img.shields.io/badge/Telegram-Updates-26A5E4?logo=telegram&logoColor=white)](https://t.me/AutoReplyer_News)
[![GitHub issues](https://img.shields.io/github/issues/TheBigChanges/AutoReplyer)](https://github.com/TheBigChanges/AutoReplyer/issues)

[**🚀 Open Bot**](https://t.me/autoreplyer_dbot) · [**📢 News & Updates**](https://t.me/AutoReplyer_News) · [**🐛 Report a Bug**](https://github.com/TheBigChanges/AutoReplyer/issues) · [**💡 Request a Feature**](https://github.com/TheBigChanges/AutoReplyer/issues)

**Languages:** 🇺🇿 Uzbek · 🇬🇧 English · 🇷🇺 Russian

</div>

---

## ✨ What is AutoReplyer?

**AutoReplyer** is a Telegram Business automation bot that helps account owners stay responsive when they are away. Connect it through Telegram's official Business bot interface, configure replies and schedules, and optionally enable Gemini-powered AI responses.

It also supports a clock in your Telegram profile name, BIO countdowns, user plans, and operational tools for the bot administrator.

> **Important:** This project uses Telegram's **official Business bot connection**. It is **not** a userbot and does **not** require your Telegram password, login code, or session file. Telegram Business access and available permissions depend on Telegram's current account/client requirements.

## 📑 Contents

- [Features](#-features)
- [Plans & pricing](#-plans--pricing)
- [Getting started as a user](#-getting-started-as-a-user)
- [Run your own instance](#-run-your-own-instance)
- [Environment configuration](#-environment-configuration)
- [Deployment on Render](#-deployment-on-render)
- [Architecture & data](#-architecture--data)
- [Bot commands](#-bot-commands)
- [Testing](#-testing)
- [Privacy, security & limitations](#-privacy-security--limitations)
- [Contributing & support](#-contributing--support)
- [License](#-license)

## 🚀 Features

| Feature | Description |
|---|---|
| 📨 **Offline replies** | Automatically reply to incoming private Business messages when offline mode is enabled. |
| 🌙 **Sleep Mode** | Send a separate reply during configured sleeping hours, including overnight schedules. |
| ⏳ **Cooldown** | Avoid repeatedly responding to the same chat; persistent, atomic reply claims help with concurrency. |
| 🤖 **Gemini AI assistant** | Generate contextual replies with role presets and owner-provided instructions; falls back to a static reply on failure. |
| 🕒 **Profile name clock** | Show local time in a connected account's name, with selectable styles and time zones (plan-dependent). |
| 🎂 **BIO countdown** | Show a countdown to New Year, Navruz, or a birthday in the Telegram Business BIO (requires editing permission). |
| 🌍 **3 interface languages** | Uzbek, English, and Russian. AI aims to answer in the sender's language. |
| 👥 **Referrals** | Generate referral links and track invitations. |
| 💎 **Subscription plans** | Free, Plus, Pro, and Ultra tiers with feature access restrictions and expiry handling. |
| 📢 **Admin broadcasts** | Persistent broadcast jobs, progress tracking, retry of failed deliveries, and resume after restart. |
| 🛡️ **Moderation & support** | Admin user controls, feedback, appeals, and optional required-channel subscription checks. |

### AI assistant roles

The Gemini assistant can be configured as a **personal assistant**, **sales representative**, **customer-support assistant**, **friendly responder**, **developer representative**, or **formal business assistant**. It uses limited conversation history for context and pauses after the account owner intervenes in a chat.

AI-generated replies can be wrong. Never rely on them to commit to prices, appointments, transactions, or other important decisions without human review. Messages processed by the AI are sent to Google Gemini.

### Business automation details

- Static replies and Sleep Mode work without a Gemini API key.
- AI is an **Ultra** feature in the current plan configuration.
- Ordinary static replies support per-chat cooldowns; AI replies use a separate reply flow.
- The name clock updates periodically, subject to Telegram Business permissions and API rate limits.
- Free-tier accounts may see a promotional footer in auto-replies and a promotional BIO message when using the profile clock. Paid plans are configured as ad-free.

## 💎 Plans & pricing

Prices below are **the currently configured public bot prices for one month**, in Uzbek soʻm (UZS). They are defined in [`bot.py`](bot.py), so the live bot is the final reference if prices change.

| Included feature | 🆓 Free | ⏰ Plus | ✨ Pro | ⭐ Ultra |
|---|:---:|:---:|:---:|:---:|
| **Monthly price** | **0 UZS** | **2,000 UZS** | **5,000 UZS** | **10,000 UZS** |
| Offline auto-replies | ✅ | ✅ | ✅ | ✅ |
| Sleep Mode | ✅ | ✅ | ✅ | ✅ |
| Profile name clock (standard) | ✅ | ✅ | ✅ | ✅ |
| Ad-free experience | — | ✅ | ✅ | ✅ |
| Custom auto-reply and sleep text | — | — | ✅ | ✅ |
| BIO countdown | — | — | ✅ | ✅ |
| Gemini AI assistant | — | — | — | ✅ |
| Extra clock fonts | — | — | — | ✅ |
| Extra time zones | — | — | — | ✅ |

**Payment flow:** The bot displays payment details configured by the operator. Users submit proof of payment to the administrator, who activates the selected plan. Plan durations and expiration are handled by the bot; this is **manual verification**, not an automated payment gateway. Payment options for international users may vary.

> Plan access does not remove Telegram platform restrictions, Business permission requirements, or external Gemini API rate limits. Prices are not automatically converted into other currencies.

## 📱 Getting started as a user

1. Open **[@autoreplyer_dbot](https://t.me/autoreplyer_dbot)** and send `/start`.
2. Select your preferred language and review the control panel.
3. In Telegram, open **Settings → Telegram Business → Chatbots** (menu labels may vary by client).
4. Connect **@autoreplyer_dbot**, choose the chats it may access, and grant the permissions needed for the features you want (for example, replying to messages).
5. Enable **offline auto-replies**, configure **Sleep Mode**, or choose the **profile clock** from the bot's panel.
6. Visit **Plans** to see available upgrades and feature restrictions.

For feature announcements, visit **[@AutoReplyer_News](https://t.me/AutoReplyer_News)**.

## 🛠️ Run your own instance

### Prerequisites

- **Python 3.10+** (the project uses modern typing syntax).
- A Telegram bot token from [@BotFather](https://t.me/BotFather).
- A reachable **PostgreSQL** database (for example, Supabase).
- A Telegram user ID to configure as the administrator.
- An optional [Google AI Studio](https://aistudio.google.com/) API key for AI replies.
- A host that can run a long-lived Python process for polling; Render is one option.

### 1. Clone

```bash
git clone https://github.com/TheBigChanges/AutoReplyer.git
cd AutoReplyer
```

### 2. Create a virtual environment

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows PowerShell:**

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Configure the environment

Create a `.env` file in the project root (it is gitignored):

```dotenv
# Required
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
ADMIN_ID=YOUR_NUMERIC_TELEGRAM_USER_ID

# Recommended
BOT_USERNAME=your_bot_username_without_at

# Gemini (optional; only needed for AI)
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.1-flash-lite

# Optional Telegram channel membership gate: set both or neither
REQUIRED_CHANNEL_ID=
REQUIRED_CHANNEL_LINK=

# Manual payment information shown by the bot (optional)
PAYMENT_CARD_NUMBER=
PAYMENT_CARD_HOLDER=

# Optional: set to 0 to restrict public use of the name clock
NAME_CLOCK_PUBLIC=1

# Health-check HTTP port (hosting provider typically sets this)
PORT=10000
```

**Notes:**

- `GEMINI_MODEL=gemini-3.1-flash-lite` is an **example of the model used by the hosted project**; use a model actually enabled for your own Gemini API project. If `GEMINI_MODEL` is omitted, the current source code defaults to `gemini-2.5-flash`.
- `ADMIN_ID` should be a numeric Telegram user ID, not a username. Without a correctly set admin ID, privileged commands will not work as intended.
- Use a valid Supabase PostgreSQL connection string if you use Supabase. Follow your provider's SSL and pooling guidance; do not publish the URL.
- Set **both** required-channel variables to turn on the membership gate. Your bot needs suitable channel permissions to check membership.
- Do **not** publish payment card details in your repository. Set them in the hosting environment. Payment activation is handled by the bot operator.
- This repository is configured for the public **@autoreplyer_dbot** instance. If you run an independent fork, review hard-coded support links/usernames in `bot.py` and substitute your own.

### 5. Start the bot

```bash
python bot.py
```

On startup, the bot initializes PostgreSQL tables, starts polling, schedules recurring jobs, and serves a basic HTTP health endpoint on `PORT`.

> **Do not run multiple polling instances using the same bot token.** Stop the production instance before testing that token locally, or use a separate development bot token and database.

## ⚙️ Environment configuration

| Variable | Purpose | Required? |
|---|---|---|
| `BOT_TOKEN` | Telegram Bot API token | **Yes** |
| `DATABASE_URL` | PostgreSQL connection string | **Yes** |
| `ADMIN_ID` | Numeric admin Telegram ID | Strongly recommended |
| `BOT_USERNAME` | Bot username used for referral links | Recommended |
| `GEMINI_API_KEY` | Gemini API key | AI features only |
| `GEMINI_MODEL` | Gemini model ID; code default `gemini-2.5-flash` | Optional |
| `REQUIRED_CHANNEL_ID` | Channel ID/username for membership gate | Optional, paired |
| `REQUIRED_CHANNEL_LINK` | Public/invite link for membership gate | Optional, paired |
| `PAYMENT_CARD_NUMBER` | Operator's manual payment card | Optional |
| `PAYMENT_CARD_HOLDER` | Displayed payment recipient | Optional |
| `NAME_CLOCK_PUBLIC` | `0` restricts name clock to admin | Optional |
| `PORT` | HTTP health server port, default `10000` | Host-dependent |

Secrets belong in your local `.env` file or your provider's **environment variables**, never in committed files.

## ☁️ Deployment on Render

The current entrypoint runs **Telegram long polling** and starts a lightweight HTTP health server in a separate thread.

1. Create a new Render service linked to your GitHub repository.
2. Configure the runtime for Python and install dependencies with:

   ```bash
   pip install -r requirements.txt
   ```

3. Use this start command:

   ```bash
   python bot.py
   ```

4. Add `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_ID` and any optional variables in **Environment**.
5. Use a persistent external PostgreSQL database such as Supabase.
6. If running as a web service, let Render provide `PORT` and configure a health check at `/` as applicable.
7. Review logs after deployment. Keep **one polling replica** for a given bot token.

> A successful HTTP health response only means the local health server is responding; it does **not** guarantee Telegram polling, Gemini, or PostgreSQL is currently healthy. Use application logs and provider monitoring for those components.

## 🧱 Architecture & data

```text
Telegram users / Business messages
                │
                ▼
        python-telegram-bot
                │
       ┌────────┴─────────┐
       │                  │
       ▼                  ▼
    bot.py              ai.py ──► Google Gemini API
  handlers/jobs      optional AI replies
       │
       ├── logic.py  (pure business logic)
       ├── i18n.py   (Uzbek / English / Russian)
       │
       ▼
     db.py ───────────────► PostgreSQL / Supabase
       │                      settings, plans, connections,
       │                      broadcasts, conversation history
       ▼
  Render / Python host
```

| File | Responsibility |
|---|---|
| [`bot.py`](bot.py) | Telegram handlers, Business updates, interface, plans, scheduling, broadcasts, name clock, and health server |
| [`db.py`](db.py) | PostgreSQL access, schema initialization, stored settings, plans, and job persistence |
| [`ai.py`](ai.py) | Gemini requests, AI prompts, role presets, and response extraction |
| [`logic.py`](logic.py) | Cooldown parsing, time/date handling, countdowns, and name formatting |
| [`i18n.py`](i18n.py) | User-facing strings in three languages |
| [`tests/`](tests/) | Unit and behavior tests for key features |
| [`requirements.txt`](requirements.txt) | Python runtime dependencies |

**Operational notes:**

- PostgreSQL keeps account settings and jobs across Render restarts.
- Broadcasts persist progress, have a one-active-job database constraint, support recovery and retry, and handle Telegram rate limits.
- Exactly-once broadcast delivery is **not guaranteed**: an interruption between Telegram accepting a message and database progress being saved can produce a duplicate.
- Bot-level feature restrictions and subscription status are enforced in application logic; third-party services still enforce their own limits.
- The built-in health endpoint answers `GET /` with `OK`.

## ⌨️ Bot commands

Regular users use the **inline control panel** reached through `/start`.

| Command | Who | What it does |
|---|---|---|
| `/start` | Everyone | Open the bot and its menu |
| `/help` | Everyone | Help and available commands |
| `/stats` | Admin | Summary statistics |
| `/setplan` | Admin | Assign a user plan, optionally with an expiry |
| `/reklama` | Admin | Prepare a broadcast for confirmation |
| `/reklama_status` | Admin | View latest broadcast progress |
| `/reklama_retry` | Admin | Resume or retry a broadcast where applicable |
| `/users` | Admin | List users |
| `/bots` | Admin | Bot-like user checks/tools |
| `/block`, `/unblock`, `/blocked` | Admin | User moderation tools |
| `/cancel` | Admin / applicable flows | Cancel an in-progress action |

Example admin command:

```text
/setplan 123456789 ultra 1oy
```

This assigns a time-limited plan to the specified user ID; use the bot's help text for accepted user identifiers and duration formats. Administrator commands are checked against `ADMIN_ID`.

## 🧪 Testing

The repository includes tests for AI, cooldown and reply flows, admin broadcasting, Business-account state, the profile clock, BIO countdowns, permissions, and related utilities.

```bash
python -m pip install pytest
python -m pytest -q
```

For verbose output:

```bash
python -m pytest -v
```

Some tests use mocks; any database integration testing should use a **separate test database**. Never point destructive test fixtures at production Supabase data. The existence of tests does not imply that every deployment environment has been tested.

## 🔐 Privacy, security & limitations

- **Official permissions only:** use the Telegram Business connection flow. The bot should never request Telegram passwords or authentication codes.
- **AI message processing:** incoming text and relevant chat context may be sent to Google's Gemini API when AI replies are enabled. Ensure users understand this data flow.
- **Stored data:** PostgreSQL stores settings, Business connections, history for applicable AI features, referral and broadcast data, and related metadata. Check retention and deletion behavior in [`db.py`](db.py) before deployment.
- **Secrets:** never commit `.env`, API keys, database URLs, Telegram tokens, or customer information. Rotate any exposed secrets immediately.
- **AI limitations:** the model may be inaccurate, unavailable, or rate-limited. Static reply fallback is available, but delivery is not guaranteed under every failure mode.
- **Telegram restrictions:** Business rights, flood limits, profile editing privileges, and availability of features are controlled by Telegram.
- **Commercial use:** payment verification in the current code is manual; the repository does not provide a full automated billing provider integration.
- **Responsible broadcasting:** only message users who have opted to interact with the bot and comply with Telegram policies and local messaging rules.

## 🤝 Contributing & support

Feedback, bug reports, and suggestions are welcome. For code changes:

1. Open an [issue](https://github.com/TheBigChanges/AutoReplyer/issues) explaining the bug or proposed feature.
2. Make your change on a separate branch or fork.
3. Update or add tests where relevant.
4. Run `python -m pytest -q` and describe testing performed in your pull request.
5. Do not include private Telegram chats, credentials, or production database exports.

For user help or release notes, follow [@AutoReplyer_News](https://t.me/AutoReplyer_News) or open [@autoreplyer_dbot](https://t.me/autoreplyer_dbot).

## 📄 License

**No `LICENSE` file was present in the repository when this README was prepared.** Public visibility on GitHub does **not** automatically grant an open-source license. Unless the repository owner adds a license, reuse and redistribution remain subject to applicable copyright law. Contributors should request permission where needed.

---

<div align="center">

### 💙 AutoReplyer — stay responsive, even when you're away.

[**Start on Telegram**](https://t.me/autoreplyer_dbot) · [**Follow Updates**](https://t.me/AutoReplyer_News) · [**View Source**](https://github.com/TheBigChanges/AutoReplyer)

</div>