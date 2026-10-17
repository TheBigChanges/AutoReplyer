<div align="center">

# 🤖 AutoReplyer

### Thoughtful auto-replies for Telegram Business — powered by rules, AI and your own knowledge.

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

It includes **Smart Onboarding**, **Smart FAQ**, and **AI Personal Knowledge**: an owner-managed collection of facts that Gemini can use to answer relevant questions. Profile name clocks, BIO countdowns, subscription plans, and administrator tools round out the experience.

**The goal is an auto-reply assistant, not an online shop or order-management system.** You can store information about yourself, your work, availability, services, or even prices as ordinary notes — no product catalogue is required.

> **Important:** This project uses Telegram's **official Business bot connection**. It is **not** a userbot and does **not** require your Telegram password, login code, or session file. Telegram Business access and available permissions depend on Telegram's current account/client requirements.

## 📑 Contents

- [Features](#-features)
- [Smart Onboarding (first-time setup)](#-smart-onboarding-first-time-setup)
- [Smart FAQ guide](#-smart-faq-guide)
- [AI Personal Knowledge guide](#-ai-personal-knowledge-guide)
- [How automatic replies are chosen](#-how-automatic-replies-are-chosen)
- [Plans & pricing](#-plans--pricing)
- [Getting started as a user](#-getting-started-as-a-user)
- [O‘zbekcha qisqa yo‘riqnoma](#-ozbekcha-qisqa-yoriqnoma)
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
| 🧠 **AI Personal Knowledge** | Owner-written facts, keywords and notes help Gemini reply with more relevant information; individual notes can be edited, paused, or deleted. **Ultra only**. |
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

### 🧠 AI Personal Knowledge guide

**AI Personal Knowledge** (called `kb` in the source) gives your AI auto-reply assistant a small, structured collection of **your own notes**. It is for personal and professional context, **not a separate sales bot**, inventory database, or order-taking feature.

**Availability:** **Ultra** plan; up to **55 entries per owner**. The bot's **Gemini AI Assistant must also be enabled** and have a working Gemini API key. Users outside Ultra see the feature as locked in the control panel; the administrator has access under the configured admin exception.

**Open it:** `/start` → **Control panel** → **AI Shaxsiy Bilimlar / AI Personal Knowledge / AI Личные знания**. The interface is translated into Uzbek, English, and Russian.

| Action | Available behavior |
|---|---|
| **Add entry** | Write a **title** (up to 100 characters), **text** (up to 1,000 characters), and optionally **keywords**; review the draft and explicitly save it. |
| **View and edit** | List entries; change their title, text, or keywords. |
| **Pause / resume** | Disable a single entry without deleting it. |
| **Delete** | See a confirmation screen before permanently deleting an entry. |
| **Settings** | Turn the entire knowledge base on or off; stored entries are retained while disabled. |

Keywords are optional (`-` skips them). You can enter up to **10 keywords/phrases, each up to 40 characters**. They are used with title/text matching to find relevant entries.

**Example — personal auto-reply context:**

```text
Title: When I'm usually available
Text: I usually reply personally after 18:00 on weekdays.
Keywords: available, free time, evening, bo'sh vaqt, kechqurun
```

If a contact asks when you can respond, Gemini may use this note to generate a natural answer. Notes can equally describe hobbies, ongoing projects, office hours, services, or business information. **You do not need to create product categories or a price list.**

**How retrieval works:** the bot looks at up to three recent incoming messages in that chat and ranks enabled notes using keyword phrases, title words and words in the note text. It ignores common question words, uses simple word-prefix matching, and sends at most **five relevant entries**, with approximately **4,000 characters of selected title/text** in total, to Gemini. **No match → no knowledge-base entries are attached.** This is heuristic keyword/text retrieval, **not semantic search**; it may miss paraphrases or match imperfectly. Entries are queried by the account owner's ID and aren't intentionally shared across owners.

**Safety and accuracy:** write only facts you are comfortable sharing with the people who message you. Do **not** store passwords, bank-card numbers, passport/ID data, private third-party details, or other secrets. **Relevant selected notes and the incoming chat context are sent to Google Gemini** when AI replies are generated. The model is instructed not to invent missing facts or reveal secrets, but AI responses and selection are **not guaranteed** to be correct or private in every case; review what you enter.

> Turning off AI or the knowledge-base toggle stops Knowledge Base content being used for new AI responses; it does **not** delete the stored notes. Deleting an entry is permanent. Plan downgrades restrict access without automatically deleting the owner's existing entries.

### 🔀 How automatic replies are chosen

When Telegram allows the bot to respond to a Business message, the code checks the account's connection rights, channel-membership rules (if enabled), Offline/Sleep settings, and other applicable restrictions.

```text
Incoming Telegram Business message
               │
               ▼
       Sleep Mode active? ── yes ──► Sleep reply path
               │ no
               ▼
      Offline replies enabled?
               │ yes
               ▼
   Smart FAQ confident match? ── yes ──► Saved FAQ answer
               │ no
               ▼
  Gemini AI available + enabled
          for this plan?
       │ yes             │ no
       ▼                 ▼
Relevant Personal      Standard
Knowledge notes        auto-reply
       │
       ▼
 Gemini-generated reply ──► Static fallback if generation fails
```

The diagram is a simplified overview: **cooldown/claim rules, manual-owner takeover pauses, account permissions and chat scope still apply**. Smart FAQ takes priority over AI on a confident match. When AI is enabled, **Personal Knowledge provides context to Gemini — it doesn't autonomously send a second message**. AI replies remain subject to the configured daily quota and external provider availability.

### AI assistant roles

The Gemini assistant can be configured as a **personal assistant**, **sales representative**, **customer-support assistant**, **friendly responder**, **developer representative**, or **formal business assistant**. It uses limited conversation history for context and pauses after the account owner intervenes in a chat.

AI-generated replies can be wrong. Never rely on them to commit to prices, appointments, transactions, or other important decisions without human review. Messages processed by the AI are sent to Google Gemini.

### Business automation details

- Static replies and Sleep Mode work without a Gemini API key.
- Gemini AI and AI Personal Knowledge are **Ultra** features in the current plan configuration. Ultra's AI reply quota is **50 per day** for a regular user; the configured administrator is exempt.
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
| Gemini AI assistant (50 replies/day*) | — | — | — | ✅ |
| AI Personal Knowledge (55 entries) | — | — | — | ✅ |
| Extra clock fonts | — | — | — | ✅ |
| Extra time zones | — | — | ✅ | ✅ |

*The administrator has a configured exception to the AI daily reply quota; Telegram and Gemini limits still apply.*

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
8. Use the control panel for **Sleep Mode**, **Smart FAQ** (Plus/Pro/Ultra), **AI Personal Knowledge** (Ultra), the **profile clock**, **BIO countdown**, and other plan-specific features.

**Want to set it up later?** Use **Skip** at any step. A **Continue setup** button appears in the main menu for users who skipped. Existing accounts are not forced into a new setup wizard.

**Safety:** do not provide your Telegram password, login code, or session file. Use only Telegram's own bot-connection controls and grant only the access you intend.

For feature announcements, visit **[@AutoReplyer_News](https://t.me/AutoReplyer_News)**.

### 🇺🇿 O‘zbekcha qisqa yo‘riqnoma

**AutoReplyer — avtomatik javob beruvchi Telegram bot**, savdo yoki buyurtma botiga aylantirilmagan. Ishni boshlash uchun:

1. [@autoreplyer_dbot](https://t.me/autoreplyer_dbot) ga `/start` yuboring va **O‘zbekcha**ni tanlang.
2. Zarur bo‘lsa, kanalga obuna bo‘ling. Telegram'da **Settings → My Profile → Chat Automations** orqali botni ulang va **Reply to messages** ruxsatini yoqing.
3. Onboarding’da **Auto-Reply**ni yoqing va boshqa akkauntdan sinov xabari yuboring.
4. **Smart FAQ** — kalit so‘zga mos tayyor javob; **AI Shaxsiy Bilimlar** (Ultra) — Gemini javob berayotganda foydalanadigan siz kiritgan ma’lumotlar.
5. AI Shaxsiy Bilimlar bo‘limiga **sarlavha + ma’lumot + ixtiyoriy kalit so‘zlar** qo‘shing. Mahsulot va narxlar uchun alohida savdo tizimi **shart emas**.
6. **Parol, karta yoki pasport ma’lumotlarini kiritmang.** AI javoblari xato qilishi mumkin.

Ilova menyulari Telegram versiyasiga qarab farq qilishi mumkin. Batafsil ma’lumot: [Smart Onboarding](#-smart-onboarding-first-time-setup) · [Smart FAQ](#-smart-faq-guide) · [AI Shaxsiy Bilimlar](#-ai-personal-knowledge-guide).

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
- Do **not** publish payment card details in your repository. Set them in the hosting environment. **Set `PAYMENT_CARD_HOLDER` explicitly when configuring `PAYMENT_CARD_NUMBER`**: the current code contains an operator-specific fallback name that may be inappropriate for a separate installation. Payment activation is handled by the bot operator.
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
| `PAYMENT_CARD_HOLDER` | Displayed payment recipient; **set explicitly if a card number is configured** | Recommended when card payments are shown |
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
  handlers/jobs      optional AI replies + selected notes
       │
       ├── logic.py  (FAQ rules and knowledge retrieval)
       ├── i18n.py   (Uzbek / English / Russian)
       │
       ▼
     db.py ───────────────► PostgreSQL / Supabase
       │                      settings, plans, connections,
       │                      FAQ and knowledge_entries,
       │                      broadcasts, conversation history
       ▼
  Render / Python host
```

| File | Responsibility |
|---|---|
| [`bot.py`](bot.py) | Telegram handlers, Business updates, onboarding, Smart FAQ and AI Personal Knowledge panels, AI reply routing, plans, scheduling, broadcasts, name clock, and health server |
| [`db.py`](db.py) | PostgreSQL access and schema initialization, onboarding progress, owner-scoped FAQ and knowledge CRUD, settings, AI conversation history, plans, and job persistence |
| [`ai.py`](ai.py) | Gemini requests, role presets, prompting with selected AI Personal Knowledge facts, and reply extraction |
| [`logic.py`](logic.py) | Cooldown/time handling, countdowns, name formatting, FAQ matching, Personal Knowledge parsing and relevance ranking |
| [`i18n.py`](i18n.py) | User-facing strings in three languages, including onboarding and Telegram connection instructions |
| [`tests/`](tests/) | Unit and behavior tests for key features |
| [`requirements.txt`](requirements.txt) | Python runtime dependencies |

**Operational notes:**

- PostgreSQL keeps account settings, onboarding progress, FAQ entries, Personal Knowledge entries, and jobs across Render restarts.
- On startup, `db.init_db()` adds missing onboarding columns and creates the `knowledge_entries` table and `kb_enabled` setting if needed. Existing users initially receive the `legacy` onboarding status; newly inserted users default to `welcome`.
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

The repository includes tests for AI and static reply flows, cooldown, broadcasts, Business connection state, name clock, BIO countdown, Smart FAQ, translations, **Smart Onboarding**, **AI Personal Knowledge**, and **test database safety guards**. The onboarding suite covers legacy/new users, channel-subscription transitions, connection permissions, skip/resume, localized default replies, completion checks, connection events, and admin statistics.

Install the development-only test runner and run the suite:

```bash
python -m pip install pytest
python -m pytest -q
```

**Onboarding and AI Personal Knowledge database tests require `TEST_DATABASE_URL`.** Without it, their database-backed classes are skipped (other unit tests can still run). **Run the suite with pytest**, which loads `tests/conftest.py` *before test modules are imported* and overrides `DATABASE_URL` with the provided test URL, or a fake URL when none is set. Use a **dedicated disposable PostgreSQL test database**; never production:

```bash
# Example: PostgreSQL running locally on your development machine.
# Replace with YOUR disposable local test database:
export TEST_DATABASE_URL='postgresql://TEST_USER:TEST_PASSWORD@localhost:5432/autoreplyer_test'
python -m pytest tests/test_knowledge.py tests/test_onboarding.py tests/test_db_guard.py -v
python -m pytest -q
```

Database integration suites call `db.init_db()` and create/update/delete records. Do not run them against real user data. The pytest guard accepts local hosts by default and **refuses remote test database hosts** unless `ALLOW_REMOTE_TEST_DB=1` is explicitly set. **That opt-in is not proof a remote database is safe**; use it only for a separately provisioned throwaway test database.

**Important limitation:** the database guard is implemented in `tests/conftest.py`, which **pytest** loads. Running test modules directly with `unittest` bypasses this protection; do not do so with any production credentials or `DATABASE_URL`. A skipped test is **not** a passed test. This README does not claim the latest commit passed CI — review real test results.

**Recommended deployment workflow:** develop on a separate branch, use a distinct Telegram test bot token and PostgreSQL test database, manually test onboarding and Knowledge Base (including owner isolation, deletion confirmation, FAQ priority, and a second Telegram account), then review and merge a pull request to `main`. Never run multiple polling processes with the production bot token.

## 🔐 Privacy, security & limitations

- **Official permissions only:** use the Telegram Business connection flow. The bot should never request Telegram passwords or authentication codes.
- **AI message processing:** incoming text and relevant chat context may be sent to Google's Gemini API when AI replies are enabled. **Relevant owner-authored Personal Knowledge entries are also sent to Gemini** when retrieved. Don't store information you aren't willing to disclose to a chat contact and the AI provider.
- **Stored data:** PostgreSQL stores settings, Business connections, **onboarding state/timestamps**, **Smart FAQ entries**, **AI Personal Knowledge titles, texts and keywords**, AI conversation history, referrals, broadcasts, and related metadata. AI history retrieval is limited to recent messages and a background cleanup job purges old history; verify retention and deletion behavior in [`db.py`](db.py) for your own deployment.
- **Secrets:** never commit `.env`, API keys, database URLs, Telegram tokens, or customer information. Rotate any exposed secrets immediately.
- **AI limitations:** the model may be inaccurate, unavailable, or rate-limited. Knowledge Base retrieval is heuristic, and even an instruction to avoid invented or confidential details **cannot guarantee** a safe or correct generated response. Static reply fallback is available, but delivery is not guaranteed under every failure mode.
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