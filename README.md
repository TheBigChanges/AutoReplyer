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

It includes **Smart Onboarding** for first-time setup, **Smart FAQ** for recurring questions, a clock in your Telegram profile name, BIO countdowns, subscription plans, and tools for the bot administrator.

> **Important:** This project uses Telegram's **official Business bot connection**. It is **not** a userbot and does **not** require your Telegram password, login code, or session file. Telegram Business access and available permissions depend on Telegram's current account/client requirements.

## 📑 Contents

- [Features](#-features)
- [Smart Onboarding (first-time setup)](#-smart-onboarding-first-time-setup)
- [Smart FAQ guide](#-smart-faq-guide)
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
| 🧭 **Smart Onboarding** | Optional three-step first-time setup: connect Telegram, enable auto-reply, and test it, with resumable progress. |
| 📚 **Smart FAQ** | Keyword-based answers for frequently asked Business-chat questions, without a Gemini API call; owner-managed entries and plan-based limits. |
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

### 🧭 Smart Onboarding (first-time setup)

**Smart Onboarding** guides new users through connecting Telegram, enabling an automatic reply, and testing it. It is offered on **all plans** in **Uzbek, English, and Russian**. It is optional: users may skip it and select **Continue setup** later in the main menu.

**Flow:** `/start` → choose language → pass the channel subscription check *if enabled by the operator* → guided setup → main menu. Existing users are marked `legacy` by the database migration and are not forced to repeat setup. A user who already connected Telegram and enabled auto-reply can begin at a later appropriate step.

| Stage | What users do |
|---|---|
| **1/3 — Connect Telegram** | In Telegram open **Settings → My Profile → Chat Automations**, connect `@autoreplyer_dbot`, choose the chats the bot may access, and grant **Reply to messages**. Return to the bot and tap **Check connection**. |
| **2/3 — Enable auto-reply** | Review the localized default reply (or your already saved reply), then explicitly tap **Turn on Auto-Reply**. The standard reply is available on Free; personalized replies are available on eligible paid plans through the control panel. |
| **3/3 — Test** | Send a message to your connected Telegram account **from another account in a permitted chat**. Tap **Reply arrived** if you received one, or **No reply** for troubleshooting of permissions, chat scope, cooldown, and Sleep Mode. |

**How connection verification works:** the wizard checks the **stored** Telegram Business connection record for an active connection and permission to reply (`is_enabled` and `can_reply`). Business connection update events can move the wizard to the next step automatically. These checks are not a live message-delivery test; account/permission changes may require refreshing the saved connection state.

**Completion and recovery:** the bot confirms that the connection can reply **and that Offline auto-reply is enabled** before marking onboarding `completed`. **Reply arrived** is the user's confirmation, not independent technical proof of delivery. The wizard is optional and resumable; the `skipped` state shows a **Continue setup** button. Completed and legacy users see the normal menu.

**Persistence:** `db.init_db()` adds `onboarding_step`, `onboarding_started_at`, and `onboarding_completed_at` to the `users` table where needed. Existing records retain a `legacy` state; newly created users default to `welcome`. Progress survives restarts.

**Admin statistics:** `/onboarding` reports started, connected, auto-reply enabled, completed, skipped, and in-progress counts. These are database-derived status snapshots, **not a historical conversion funnel**.

> **Menu names vary by Telegram version.** If the **My Profile → Chat Automations** path is absent, Telegram may use a **Telegram Business → Chatbots** menu instead. A different route does not guarantee access to features that Telegram restricts; any Premium prompts or eligibility requirements are controlled by Telegram.

### 📚 Smart FAQ guide

Smart FAQ is a **rule-based, non-AI** answer system for incoming Telegram Business messages. Account owners can configure questions, comma-separated keywords or phrases, and the exact reply text. This can help answer recurring questions such as delivery availability or opening hours without consuming Gemini API requests.

**Manage FAQs in the bot:** open `/start` → **Smart FAQ**. From the FAQ panel you can add and list entries, enable or disable the feature, and manage individual entries. Each entry supports **Edit Question**, **Edit Keywords**, **Edit Answer**, enable/disable, and delete. New entries are created through a step-by-step form and saved after confirmation. Editing is available in **Uzbek, English, and Russian**.

**Example**

```text
Question: Do you offer delivery?
Keywords: delivery, shipping, dostavka
Answer: Yes, we offer delivery within our supported area.
```

When a Business-chat message clearly matches a configured question or keyword phrase, the bot sends the stored answer. The matching logic normalizes text, matches whole words/phrases, rejects certain ambiguous negations and very long messages, and declines to choose when multiple entries tie. **It is not semantic search and does not guarantee that every paraphrase will match.** Unmatched messages follow the existing fallback path.

**Important behavior:**

- FAQ responses are evaluated **only when Offline mode is active and Sleep Mode is not currently taking precedence**.
- A confident FAQ match takes priority over Gemini AI; unmatched messages can continue to AI (when enabled and available) or the normal static reply.
- In ordinary static-reply mode, FAQ uses the configured per-chat cooldown. When AI mode is available, FAQ follows the AI-style reply path rather than the static cooldown.
- FAQ answers are stored in PostgreSQL under the account owner's ID; owner-scoped lookups and updates prevent cross-account editing via the application.
- There is a **global FAQ on/off switch** and a separate enable/disable switch for each entry.
- Entries per plan: **Free: unavailable; Plus: 15; Pro: 30; Ultra: 65**. If a plan is downgraded, only entries within its current allowance are considered for replies; upgrading restores access subject to the plan limit.
- The maximum size of an entry is **200 characters for the question, 10 keywords/phrases (40 characters each), and 1,000 characters for the answer**. Incoming messages exceeding 60 normalized tokens are not matched as FAQ.

**Privacy note:** FAQ answers are configured by the account owner and are sent automatically to relevant Business contacts. Avoid placing secrets or sensitive personal information in FAQ entries. Always review business-critical statements such as prices and availability.

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
| Guided Smart Onboarding | ✅ | ✅ | ✅ | ✅ |
| Offline auto-replies | ✅ | ✅ | ✅ | ✅ |
| Sleep Mode | ✅ | ✅ | ✅ | ✅ |
| Profile name clock (standard) | ✅ | ✅ | ✅ | ✅ |
| Ad-free experience | — | ✅ | ✅ | ✅ |
| Custom auto-reply and sleep text | — | ✅ | ✅ | ✅ |
| BIO countdown | — | — | ✅ | ✅ |
| Smart FAQ entries | — | **15** | **30** | **65** |
| Gemini AI assistant | — | — | — | ✅ |
| Extra clock fonts | — | — | — | ✅ |
| Extra time zones | — | — | ✅ | ✅ |

**Payment flow:** The bot displays payment details configured by the operator. Users submit proof of payment to the administrator, who activates the selected plan. Plan durations and expiration are handled by the bot; this is **manual verification**, not an automated payment gateway. Payment options for international users may vary.

> Plan access does not remove Telegram platform restrictions, Business permission requirements, or external Gemini API rate limits. Prices are not automatically converted into other currencies.

## 📱 Getting started as a user

1. Open **[@autoreplyer_dbot](https://t.me/autoreplyer_dbot)** and send `/start`.
2. Choose **Uzbek, English, or Russian**. If the operator enables required channel membership, join the channel and tap **Check** to continue onboarding.
3. In Telegram, open **Settings → My Profile → Chat Automations** (the menu name and location can vary by client).
4. Connect **@autoreplyer_dbot**, choose **only the chats you want the bot to access**, and enable the **Reply to messages** permission. Save the connection.
5. Return to AutoReplyer and tap **Check connection**. If Telegram already sent a connection update, the wizard may have advanced automatically.
6. Review the auto-reply text and tap **Turn on Auto-Reply** to enable it with your consent.
7. Send a test message **from another Telegram account** in a chat you authorized; select **Reply arrived** only if you actually receive a reply, or **No reply** for troubleshooting.
8. Use the control panel for **Sleep Mode**, **Smart FAQ** (Plus/Pro/Ultra), the **profile clock**, **BIO countdown**, and other plan-specific features.

**Want to set it up later?** Use **Skip** at any step. A **Continue setup** button appears in the main menu for users who skipped. Existing accounts are not forced into a new setup wizard.

**Safety:** do not provide your Telegram password, login code, or session file. Use only Telegram's own bot-connection controls and grant only the access you intend.

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

> A successful HTTP health response only means the local health server is responding; it does **not** guarantee Telegram polling, Gemini, or PostgreSQL is currently healthy. Use application logs and provider monitoring for those components. Test new features with an isolated bot and database before deploying to production.

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
| [`bot.py`](bot.py) | Telegram handlers, Business updates, onboarding screens and callbacks, Smart FAQ UI/editing and reply routing, plans, scheduling, broadcasts, name clock, and health server |
| [`db.py`](db.py) | PostgreSQL access and schema migrations, onboarding state/statistics, owner-scoped FAQ CRUD, settings, plans, and job persistence |
| [`ai.py`](ai.py) | Gemini requests, AI prompts, role presets, and response extraction |
| [`logic.py`](logic.py) | Cooldown parsing, time/date handling, countdowns, name formatting, FAQ keyword parsing and matching |
| [`i18n.py`](i18n.py) | User-facing strings in three languages, including onboarding and Telegram connection instructions |
| [`tests/`](tests/) | Unit and behavior tests for key features |
| [`requirements.txt`](requirements.txt) | Python runtime dependencies |

**Operational notes:**

- PostgreSQL keeps account settings, onboarding progress, FAQ entries, and jobs across Render restarts.
- `db.init_db()` adds onboarding columns on startup if needed. Existing users initially receive the `legacy` status; newly inserted rows default to `welcome`.
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
| `/onboarding` | Admin | Started, connected, auto-reply-enabled, completed, skipped, and in-progress onboarding counts |
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

The repository includes tests for AI and static reply flows, cooldown, broadcasts, Business connection state, name clock, BIO countdown, Smart FAQ (editing and plan limits), translations, and **Smart Onboarding**. The onboarding suite covers legacy/new users, channel-subscription transitions, connection permissions, skip/resume, localized default replies, completion checks, connection events, and admin statistics.

Install the development-only test runner and run the suite:

```bash
python -m pip install pytest
python -m pytest -q
```

**Onboarding database tests require `TEST_DATABASE_URL`.** Without it, the onboarding test class is skipped. Run against a **dedicated disposable PostgreSQL test database**, making sure neither URL points to production:

```bash
# Use a dedicated TEST database, never the live Supabase database:
export DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/autoreplyer_test'
export TEST_DATABASE_URL="$DATABASE_URL"
python -m pytest tests/test_onboarding.py -v
python -m pytest -q
```

The onboarding suite calls `db.init_db()` and creates/updates/deletes test records; do not run it against real user data. **A skipped test is not a passed test.** Tests existing in this repository do not prove that the latest commit passed CI; review actual test output.

**Recommended deployment workflow:** develop on a separate branch, use a distinct Telegram test bot token and PostgreSQL test database, manually test the full first-time setup and an existing account, then review and merge a pull request to `main`. Never run multiple polling processes with the production bot token.

## 🔐 Privacy, security & limitations

- **Official permissions only:** use the Telegram Business connection flow. The bot should never request Telegram passwords or authentication codes.
- **AI message processing:** incoming text and relevant chat context may be sent to Google's Gemini API when AI replies are enabled. Ensure users understand this data flow.
- **Stored data:** PostgreSQL stores settings, Business connections, **onboarding state and timestamps**, **Smart FAQ questions, keywords and answers**, history for applicable AI features, referral and broadcast data, and related metadata. Check retention and deletion behavior in [`db.py`](db.py) before deployment.
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