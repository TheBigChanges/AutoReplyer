<div align="center">

# 🤖 AutoReplyer

### Telegram Business auto-replies, Automation Engine v1.2, smart scheduling, AI knowledge, analytics and Telegram Stars payments.

**Built with Python · Telegram Business · PostgreSQL · Google Gemini · Matplotlib · Telegram Stars**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Telegram](https://img.shields.io/badge/Telegram-Try%20the%20bot-26A5E4?logo=telegram&logoColor=white)](https://t.me/autoreplyer_dbot)
[![News](https://img.shields.io/badge/Telegram-Updates-26A5E4?logo=telegram&logoColor=white)](https://t.me/AutoReplyer_News)
[![GitHub issues](https://img.shields.io/github/issues/TheBigChanges/AutoReplyer)](https://github.com/TheBigChanges/AutoReplyer/issues)
[![Tests](https://github.com/TheBigChanges/AutoReplyer/actions/workflows/tests.yml/badge.svg)](https://github.com/TheBigChanges/AutoReplyer/actions/workflows/tests.yml)

[**🚀 Open Bot**](https://t.me/autoreplyer_dbot) · [**📢 News & Updates**](https://t.me/AutoReplyer_News) · [**🐛 Report a Bug**](https://github.com/TheBigChanges/AutoReplyer/issues) · [**💡 Request a Feature**](https://github.com/TheBigChanges/AutoReplyer/issues)

**Languages:** 🇺🇿 Uzbek · 🇬🇧 English · 🇷🇺 Russian

</div>

---

## ✨ What is AutoReplyer?

**AutoReplyer** is a Telegram Business automation bot that helps account owners stay responsive when they are away. Connect it through Telegram's official Business bot interface, configure replies and schedules, and optionally enable Gemini-powered AI responses.

It includes **Smart Onboarding**, **Smart FAQ**, **Automation Engine v1.2**, **AI Personal Knowledge**, **Smart Scheduler**, **AutoReply Analytics**, and **Payments v1.0** with Telegram Stars invoices for paid plans. Profile name clocks, BIO countdowns, administrator tools and support flows round out the experience.

**The goal is an auto-reply assistant, not an online shop or order-management system.** You can store information about yourself, your work, availability, services, or even prices as ordinary notes — no product catalogue is required.

> **Important:** This project uses Telegram's **official Business bot connection**. It is **not** a userbot and does **not** require your Telegram password, login code, or session file. Telegram Business access and available permissions depend on Telegram's current account/client requirements.

## 📑 Contents

- [Features](#-features)
- [Smart Onboarding (first-time setup)](#-smart-onboarding-first-time-setup)
- [Smart FAQ guide](#-smart-faq-guide)
- [Automation Engine v1.2 guide](#-automation-engine-v12-guide)
- [AI Personal Knowledge guide](#-ai-personal-knowledge-guide)
- [AutoReply Analytics guide](#-autoreply-analytics-guide)
- [Smart Auto-Reply Scheduler guide](#-smart-auto-reply-scheduler-guide)
- [How automatic replies are chosen](#-how-automatic-replies-are-chosen)
- [Plans & pricing](#-plans--pricing)
- [Telegram Stars Payments v1.0](#-telegram-stars-payments-v10)
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
| 🧩 **Automation Engine v1.2** | Fixed replies with one keyword or 2–5 OR alternatives (Pro/Ultra), optional day/time AND filters, a Telegram rule editor, priorities and per-rule statistics. Plus **2**, Pro **10**, Ultra **30** saved rules. |
| 🧠 **AI Personal Knowledge** | Owner-written facts, keywords and notes help Gemini reply with more relevant information; individual notes can be edited, paused, or deleted. **Ultra only**. |
| 📊 **AutoReply Analytics** | Per-owner counts of incoming Business messages and sent replies, time windows and activity charts; **today on Free**, richer views on paid plans. |
| 📅 **Smart Scheduler** | Weekly recurring day/time windows, overnight and all-day schedules, rule management and plan-based limits. |
| 📨 **Offline replies** | Automatically reply to incoming private Business messages when offline mode is enabled. |
| 🌙 **Sleep Mode** | Send a separate reply during configured sleeping hours, including overnight schedules. |
| ⏳ **Cooldown** | Avoid repeatedly responding to the same chat; persistent, atomic reply claims help with concurrency. |
| 🤖 **Gemini AI assistant** | Generate contextual replies with role presets and owner-provided instructions; falls back to a static reply on failure. |
| 🕒 **Profile name clock** | Show local time in a connected account's name, with selectable styles and time zones (plan-dependent). |
| 🎂 **BIO countdown** | Show a countdown to New Year, Navruz, or a birthday in the Telegram Business BIO (requires editing permission). |
| 🌍 **3 interface languages** | Uzbek, English, and Russian. AI aims to answer in the sender's language. |
| 👥 **Referrals** | Generate referral links and track invitations. |
| 💎 **Subscription plans** | Free, Plus, Pro, and Ultra tiers with feature access restrictions and expiry handling. |
| ⭐ **Payments v1.0** | Telegram Stars (XTR) invoices for 1/3/6/12-month plans, automatic activation after confirmed payment, plan changes, purchase history, refund administration and payment recovery. |
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

- FAQ responds in **Offline mode or during an active Scheduler window**, provided Sleep Mode is not taking precedence.
- During ordinary Offline mode, **Automation Engine is checked before Smart FAQ**. In a Scheduler window, Automation Engine is skipped; Smart FAQ can still match. A confident FAQ match takes priority over Gemini AI; unmatched messages continue to AI (when available) or to scheduled/standard fallback.
- In ordinary static-reply mode, FAQ uses the configured per-chat cooldown. When AI mode is available, FAQ follows the AI-style reply path rather than the static cooldown.
- FAQ answers are stored in PostgreSQL under the account owner's ID; owner-scoped lookups and updates prevent cross-account editing via the application.
- There is a **global FAQ on/off switch** and a separate enable/disable switch for each entry.
- Entries per plan: **Free: unavailable; Plus: 15; Pro: 30; Ultra: 65**. If a plan is downgraded, only entries within its current allowance are considered for replies; upgrading restores access subject to the plan limit.
- The maximum size of an entry is **200 characters for the question, 10 keywords/phrases (40 characters each), and 1,000 characters for the answer**. Incoming messages exceeding 60 normalized tokens are not matched as FAQ.

**Privacy note:** FAQ answers are configured by the account owner and are sent automatically to relevant Business contacts. Avoid placing secrets or sensitive personal information in FAQ entries. Always review business-critical statements such as prices and availability.

### 🧩 Automation Engine v1.2 guide

**Automation Engine v1.2** is a deterministic rule system that sends fixed replies to authorized Telegram Business messages, without calling Gemini. One rule can match **one keyword or any of 2–5 keywords (OR)**, optionally combined with **Days of Week** and/or **Time Between** filters (AND). v1.2 adds a Telegram-panel editor, custom rule priorities, per-rule sent counters, and Automation statistics. Existing v1.0 keyword-only and v1.1 day/time rules stay compatible.

#### Plan availability and limits

| Plan | Max saved rules | One keyword | 2–5 keywords (OR) | Day/time filters (AND) | Rule editor & statistics |
|---|---:|:---:|:---:|:---:|:---:|
| Free | **0** | 🔒 | 🔒 | 🔒 | 🔒 |
| Plus | **2** | ✅ | — | — | ✅ (basic edits) |
| Pro | **10** | ✅ | ✅ | ✅ | ✅ |
| Ultra | **30** | ✅ | ✅ | ✅ | ✅ |

The configured administrator has a feature-access exception. After a plan downgrade, **saved rules are not deleted**. Only the **oldest rules by ID up to the current plan's limit** can be considered for replies (disabled rules also occupy slots). Rules containing OR, day, or time conditions do **not** run if the current plan lacks advanced conditions. Re-upgrading restores eligible saved rules. Free cannot edit Automation rules; Plus can edit only their basic fields.

#### Create a rule in Telegram

1. Send `/start` to [@autoreplyer_dbot](https://t.me/autoreplyer_dbot) and open **Control panel → 🧩 Automation / Avtomatlashtirish → Add a rule**.
2. Enter a single keyword/phrase (e.g. `narx*`). **Pro/Ultra** may enter **2–5 alternative keywords** separated by commas, semicolons, or new lines, e.g. `narx*, qancha, price`. Any one of these alternatives is sufficient (**OR**). **Plus** accepts one keyword only.
3. **Pro/Ultra** can optionally select individual days or weekday/weekend/every-day presets, then optionally supply a time window such as `09:00-18:00`. Both filters can be skipped.
4. Enter the exact reply (**up to 500 characters**), review it, then tap **Save**. Rules created in the panel begin **enabled**; the initial rule name is derived from its keyword(s) and its default priority is **100**.
5. Open **My rules** to view named rules, edit, enable/disable, or delete them (deletion requires a current confirmation).

**Example — OR keywords with AND filters (Pro/Ultra):**

```text
IF message contains ANY: narx* OR qancha OR price
AND weekday is: Monday–Friday
AND local time is: 09:00–18:00
THEN send: Assalomu alaykum! Narxlar haqida ma'lumot beraman.
```

**Matching logic:** Exactly one keyword condition is required: either `keyword_contains` for a single word/phrase, or `keyword_any` for **2–5 alternatives**. Multiple alternatives use **OR** within that condition; any additional day/time filters still use **AND**. A day-only rule applies all day on the chosen days; a time-only rule applies every day. A range such as **Monday 22:00–06:00** continues into Tuesday morning and belongs to the **Monday window**. Rules follow the effective account time zone used for Scheduler/Sleep Mode (otherwise **Asia/Tashkent**).

Keywords and phrases match normalized whole words/consecutive phrases, case-insensitively. `narx` matches `narx` but not `narxi`, while `narx*` also matches `narxi` and `narxlar`, not `unarxon`. `*` is allowed only at the end, after at least **3 normalized characters** in the final token. Each keyword/phrase has a maximum of **50 characters / 5 normalized tokens**; duplicate OR alternatives after normalization are rejected. Recognized negations such as `emas` or `yo'q` block matches (a conservative heuristic, not semantic understanding).

#### Editing, priorities and safety

Open **My rules → a rule → Edit**. You can change its **name** (maximum **60 characters**), **keyword(s)**, **days**, **time**, **fixed reply** (maximum **500 characters**), and **priority** (integer **0–10000**). Optional days/time conditions can also be removed. **Pro/Ultra** is required for multiple-keyword OR, day, or time conditions. Plus may edit basic fields: a single keyword, name, reply, and priority. Edits preserve whether a rule is enabled and its accumulated sent counter.

When multiple active rules match a message, the **lowest numeric priority** is chosen; ties use the **lowest database rule ID**. Priority **0** is checked before **100**. Only **one Automation rule** is selected per incoming message.

Edits are validated and applied to the owner's own rule through a database transaction. Drafts, edit sessions and delete confirmations are held **in memory**, expire after roughly **10 minutes**, and do not survive a restart. Obsolete buttons cannot reuse a completed draft/confirmation. Current plan permissions are checked again during the flow, so a downgrade can prevent finishing an edit. Deleting a rule removes it while preserving its accumulated reply count in the historical total.

#### Automation statistics (v1.2)

Open **Automation → Statistics** to see the **number of stored rules**, **enabled rules**, **Automation replies in the last seven days** (for plans with 7-day Analytics), **cumulative counted replies since the recorded counter start date**, and the **top three existing rules** by cumulative successful replies. A rule's detail view shows its own count and priority. The cumulative total includes counts transferred from **deleted rules**; deleted rules no longer appear in the top-existing-rules list.

In the main **AutoReply Analytics** dashboard, successful Automation messages now have their **own “automation” reply type** instead of being counted as standard/static replies. They appear in sent totals and eligible pie charts. The hourly Analytics data and per-rule cumulative counters are different measurements.

**Counter limitations:** Cumulative rule counters start when the v1.2 counter columns/metadata are initialized and **do not backfill earlier replies**; the panel shows the recorded start date. Successful Telegram sends trigger **best-effort background counter writes**, which may be delayed or lost if writing fails or the process stops. Deletion transactionally transfers a rule's existing counter to the historical total; a delayed counter update for a now-deleted rule also falls back to that total. Dedicated counter tables do **not** store customer message content or chat IDs.

#### When Automation sends a reply

- An enabled rule requires an authorized **Telegram Business** connection and **ordinary Offline mode**. Automation is **not** evaluated during Sleep Mode, an active Scheduler window, or normal Online mode.
- In ordinary Offline mode, the order is **Automation → Smart FAQ → eligible Gemini AI → standard fallback**. A matching Automation rule sends its fixed reply without using a Gemini request.
- Normal **per-chat static cooldown**, Telegram Business permissions, and relevant owner-takeover protection still apply. Cooldown skips and failed sends do not count as successful Automation replies.
- Supported JSONB rule structure: **one** `keyword_contains` *or* `keyword_any` condition, optionally **one** `days_of_week` and **one** `time_between`, with top-level `operator: "all"` and a single `send_reply` action. Arbitrarily nested AND/OR trees, multiple actions, ignore/block actions, drag-and-drop rule editing and an Automation Web App editor are **not implemented**.
- PostgreSQL stores rules per owner with JSONB conditions/action, priority, enabled status, `sent_count` and `last_sent_at`. Drafts and confirmations are transient.

**Administrator text commands:** `/automation` lists the admin's own rules. `/automation add narx* | Reply text` creates a **disabled single-keyword** rule; `/automation on ID`, `/automation off ID` and `/automation del ID` manage it. Regular users and advanced rule editing use the inline Telegram panel; the admin text command does **not** accept a multi-keyword OR expression.

**Privacy:** The rule's fixed reply is supplied by the account owner and sent to matching Business contacts. Do not put secrets or sensitive contact details in auto-replies; review potentially consequential information such as prices or availability.

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

### 📊 AutoReply Analytics guide

**AutoReply Analytics** is an in-bot statistics dashboard for Telegram Business auto-replies. It helps account owners understand how often contacts write and which reply features actually send messages. **It is not a sales dashboard, visitor-tracking tool, or message-reading service.**

**Open it:** send `/start` → open the **Control panel** → **📊 Statistika** (Uzbek) / **📊 Analytics** (English) / **📊 Аналитика** (Russian). Unlike Gemini AI and AI Personal Knowledge, the basic Analytics dashboard is available on **Free**.

#### What the numbers mean

| Metric | What is counted |
|---|---|
| **Incoming messages** | Eligible incoming Telegram Business messages observed by the bot, including messages received while the owner has set Auto-Reply to Online. This is **not** a count of unique people or chats. |
| **Replies sent** | Successfully sent bot replies, separated into **Automation**, **Smart FAQ**, **Gemini AI**, **standard auto-replies**, and **Sleep Mode**. |
| **Busiest time** | The consecutive **two-hour window** with the largest incoming-message total in the selected period. |
| **Detailed report** | Incoming/sent totals, reply-to-incoming ratio, cooldown skips, daily average, busiest day, four-hour activity blocks, and per-day totals (**Ultra**). |
| **Cooldown skips** | Attempts where the normal cooldown claim blocked an auto-reply. This is **not** an exhaustive count of all reasons a message went unanswered. |

**Example (illustrative figures, not live bot data):**

```text
📊 AUTOREPLY ANALYTICS
📅 Last 7 days

📥 Incoming messages: 245
📤 Replies sent:     198
   Automation:         25
   Smart FAQ:          68
   Gemini AI:          72
   Standard replies:   20
   Sleep Mode:         13

⏰ Busiest time: 19:00–21:00
```

Incoming and sent counts are **different kinds of events**: not every incoming message results in a reply (for example, when Online, during cooldown, or when replies are unavailable). They should not be interpreted as a guaranteed one-to-one delivery or customer response rate. Counts start **when Analytics tracking is deployed and processing messages**; the feature does **not backfill old chats**.

#### Date ranges, charts and plans

| Plan | Available date range | Chart access | Detailed report |
|---|---|---|---|
| 🆓 **Free** | Today | — | — |
| ⏰ **Plus** | Today + last 7 days | 📈 **Line chart** | — |
| ✨ **Pro** | Today + last 7/30 days | 📈 **Line** + 🥧 **pie charts** | — |
| ⭐ **Ultra** | Today + last 7/30 days | 📈 **Line**, 🥧 **pie** + 📊 **hourly bar charts** | ✅ |

- **Line chart:** compares incoming and sent replies, **by hour for Today**, or **by day for 7/30 days**.
- **Pie chart:** share of successful replies sent by Automation, FAQ, Gemini AI, standard reply and Sleep Mode.
- **Bar chart:** incoming message activity by local hour (00–23), with the busiest window highlighted.
- Charts are generated with **Matplotlib** and delivered as **PNG images directly in Telegram**; no separate website is required.
- The selected period is preserved when opening charts or details. Feature and period permissions are checked against the user's **current** plan; older buttons do not grant upgraded history access after a downgrade.
- Dates are based on the account's **supported profile-name clock time zone** if one is set; otherwise they use **Asia/Tashkent**. A “7-day” window includes today and the preceding six local calendar days.

#### Privacy, storage and limitations

The dedicated Analytics table, `analytics_hourly`, stores **only the account owner ID, a UTC hour bucket, an event type and a count**. It does **not** add a column for message text, chat ID, or contact identity. All Analytics reads are scoped to the owner; data is aggregated in PostgreSQL and pruned by the scheduled cleanup job, with a configured **90-day retention window**.

> **Important distinction:** Analytics itself does not store chat texts, but **Gemini AI chat history is stored and managed separately** when that feature is used. See [Privacy, security & limitations](#-privacy-security--limitations).

Analytics writes run in the background and are best-effort: database outages, restarts, or delayed/background write failures can cause some counts to be missing or briefly delayed. Charts use a short (~60-second) cache to reduce rendering load. Historic data **before the feature was enabled** cannot be reconstructed from Analytics counters. Automation's per-rule cumulative counters and their start date are explained in the [Automation guide](#-automation-engine-v12-guide). Figures are operational indicators, not an audited record of all Telegram delivery outcomes.


### 📅 Smart Auto-Reply Scheduler guide

**Smart Scheduler** adds recurring weekly day/time rules to Telegram Business auto-replies. It does not modify the owner's existing Online/Offline setting: **when a schedule ends, the normal setting applies again automatically**. Open the feature via `/start` → **Control panel** → **📅 Smart Jadval** / **📅 Smart Scheduler** / **📅 Умное расписание**.

#### Create a schedule

1. Choose **Add schedule**; select individual days or a preset (**Weekdays**, **Weekend**, **Every day**) and press **Continue**.
2. Enter a window such as `09:00-18:00` or choose **All day**. A window like `22:00-06:00` continues past midnight into the *next* day.
3. For **Plus, Pro or Ultra**, write a reply (at most **500 characters**) or choose **Standard text**. **Free** uses the normal auto-reply text automatically.
4. Confirm the summary with **Save**. Overlapping windows are rejected: one scheduled rule can apply at a time.

**Example weekly setup:**

~~~text
1. Monday – Friday · 09:00–18:00
   "I'm busy with work and will reply soon."

2. Saturday · 10:00–14:00
   Standard auto-reply text

3. Sunday · All day
   "Today is my day off. I'll reply tomorrow."
~~~

From the Scheduler menu, **edit a rule's days, time or eligible custom text**, **pause/resume** it, or **delete** it with confirmation. The Scheduler **Settings** switch turns all rules on or off without deleting them. All three interface languages are supported.

| Plan | Maximum rules | Per-rule custom reply |
|---|---:|:---:|
| 🆓 Free | **1** | — (standard text) |
| ⏰ Plus | **3** | ✅ |
| ✨ Pro | **10** | ✅ |
| ⭐ Ultra | **30** | ✅ |

**How it works with other features:**

- **Sleep Mode takes priority** over Scheduler. During sleeping hours the sleep reply is used.
- During an active schedule, the bot can reply **even when the owner is Online**. **Smart FAQ** has priority for matching questions; if configured, eligible **Gemini AI** may respond next. Otherwise the scheduled text (or standard text fallback) is sent. Per-chat cooldown and Telegram Business permissions still apply.
- **Outside an active schedule**, the owner's ordinary settings apply: Online gives no automatic reply; Offline follows **Automation → FAQ → AI → standard fallback**, with Automation gated by the current paid plan.
- **Time zone:** Scheduler and Sleep Mode share the Name Clock time-zone setting if configured, otherwise **Asia/Tashkent**. The effective zone is shown in the Scheduler settings; access to extra selectable zones depends on the plan.
- When a plan expires or is downgraded, existing saved rules remain in PostgreSQL, but only the **earliest rules within the new plan's limit** run. Per-rule custom reply text requires eligible access at reply time.
- Owner-specific rules are persisted in the `schedule_rules` table. Reads use a **60-second in-memory cache** invalidated on local changes; on multi-worker deployments, another worker may briefly see old data until its cache expires. Unsaved editing drafts are temporary and may be lost on restart.

### 🔀 How automatic replies are chosen

When Telegram allows the bot to respond to a Business message, the code checks the account's connection rights, channel-membership rules (if enabled), Offline/Sleep settings, and other applicable restrictions.

~~~text
Incoming authorized Business message
                  |
                  v
       Sleep Mode active? ---- yes ---> Sleep reply
                  | no
                  v
       Scheduler rule active?
          | yes                         | no
          v                             v
    Smart FAQ -> AI             Offline mode enabled?
    -> scheduled fallback           | yes          | no
    (no Automation)                 v              v
                            Automation match?   No auto-reply
                               | yes    | no
                               v        v
                           Rule reply  Smart FAQ match?
                                         | yes   | no
                                         v       v
                                    FAQ reply   Gemini AI (if enabled)
                                                or standard reply
~~~

This diagram is simplified. **Sleep Mode takes precedence**; active Scheduler windows can send replies even when Online, with **Smart FAQ → eligible Gemini AI → scheduled-text fallback**. Automation is evaluated **only** outside Sleep/Scheduler windows while Offline, and **before Smart FAQ and Gemini AI**. Automation uses the existing static per-chat cooldown. Telegram Business permissions, account owner takeover pauses, AI usage quotas, and other delivery restrictions still apply. Personal Knowledge only supplies context to Gemini; it does not send another message.

### AI assistant roles

The Gemini assistant can be configured as a **personal assistant**, **sales representative**, **customer-support assistant**, **friendly responder**, **developer representative**, or **formal business assistant**. It uses limited conversation history for context and pauses after the account owner intervenes in a chat.

AI-generated replies can be wrong. Never rely on them to commit to prices, appointments, transactions, or other important decisions without human review. Messages processed by the AI are sent to Google Gemini.

### Business automation details

- Static replies and Sleep Mode work without a Gemini API key.
- Gemini AI and AI Personal Knowledge are **Ultra** features in the current plan configuration. Ultra's AI reply quota is **50 per day** for a regular user; the configured administrator is exempt.
- Ordinary static replies support per-chat cooldowns; AI replies use a separate reply flow.
- **AutoReply Analytics** collects hourly counters for supported incoming/reply events and produces statistics without an AI API key.
- **Smart Scheduler** controls recurring reply windows without AI requests and supports custom rule text on eligible plans.
- **Automation Engine v1.2** sends fixed keyword-based responses (no Gemini needed) in ordinary Offline mode, outside active Scheduler/Sleep windows. Pro/Ultra may use 2–5 OR keywords with optional weekday/time AND filters; users can edit rules and monitor their own per-rule counters.
- The name clock updates periodically, subject to Telegram Business permissions and API rate limits.
- Free-tier accounts may see a promotional footer in auto-replies and a promotional BIO message when using the profile clock. Paid plans are configured as ad-free.

## 💎 Plans & pricing

**UZS amounts below are the plan labels configured in `bot.py`**, not a conversion of Telegram Stars. The in-bot Stars checkout has a **separate XTR price table**, defined in `payments.py` and documented in [Payments v1.0](#-telegram-stars-payments-v10). Always confirm the checkout amount shown by the bot before purchasing.

| Included feature | 🆓 Free | ⏰ Plus | ✨ Pro | ⭐ Ultra |
|---|:---:|:---:|:---:|:---:|
| **Monthly price** | **0 UZS** | **2,000 UZS** | **5,000 UZS** | **10,000 UZS** |
| Guided Smart Onboarding | ✅ | ✅ | ✅ | ✅ |
| Offline auto-replies | ✅ | ✅ | ✅ | ✅ |
| Sleep Mode | ✅ | ✅ | ✅ | ✅ |
| Smart Scheduler — saved rules | **1** | **3** | **10** | **30** |
| Scheduler — custom text per rule | — | ✅ | ✅ | ✅ |
| Profile name clock (standard) | ✅ | ✅ | ✅ | ✅ |
| Ad-free experience | — | ✅ | ✅ | ✅ |
| Custom auto-reply and sleep text | — | ✅ | ✅ | ✅ |
| BIO countdown | — | — | ✅ | ✅ |
| Smart FAQ entries | — | **15** | **30** | **65** |
| 🧩 Automation Engine v1.2 — saved rules | 🔒 | **2** | **10** | **30** |
| Multiple keywords (2–5; OR) | 🔒 | — | ✅ | ✅ |
| Advanced Automation — days/time (AND) | 🔒 | — | ✅ | ✅ |
| Automation rule editing, priorities and statistics | 🔒 | ✅ (basic edits) | ✅ | ✅ |
| Gemini AI assistant (50 replies/day*) | — | — | — | ✅ |
| AI Personal Knowledge (55 entries) | — | — | — | ✅ |
| AutoReply Analytics — Today | ✅ | ✅ | ✅ | ✅ |
| Analytics — 7-day view | — | ✅ | ✅ | ✅ |
| Analytics — 30-day view | — | — | ✅ | ✅ |
| Analytics — line chart | — | ✅ | ✅ | ✅ |
| Analytics — pie chart | — | — | ✅ | ✅ |
| Analytics — hourly bar chart | — | — | — | ✅ |
| Analytics — detailed report | — | — | — | ✅ |
| Extra clock fonts | — | — | — | ✅ |
| Extra time zones | — | — | ✅ | ✅ |

*The administrator has a configured exception to the AI daily reply quota; Telegram and Gemini limits still apply.*

**Payment flow:** Telegram Stars is the automatic in-bot checkout when `PAYMENTS_STARS_ENABLED` is enabled (the default). After a verified `successful_payment`, the bot activates the subscription. The older card/admin-assisted UI is preserved in code but **disabled by default** (`PAYMENTS_CARD_ENABLED=0`); `/setplan` remains an administrator-only manual plan-management command. The legacy card route does not automatically verify card payments.

> Plan access does not remove Telegram platform restrictions, Business permission requirements, or external Gemini API rate limits. Prices are not automatically converted into other currencies.

## ⭐ Telegram Stars Payments v1.0

Payments v1.0 is implemented in [`payments.py`](payments.py) (prices and subscription arithmetic), [`bot.py`](bot.py) (Telegram invoice/checkout/refund handlers and scheduled jobs) and [`db.py`](db.py) (PostgreSQL payment records and transactions). It sells the bot's **digital subscription plans** through **Telegram Stars (XTR)**. These are **one-time purchases for a selected duration**, not automatically recurring charges.

### 💳 Stars prices and duration discounts

The source of truth is `STARS_PRICE_1M` and `DURATION_DISCOUNT` in [`payments.py`](payments.py). The code rounds percentage-discounted totals to the nearest whole Star, with half values rounded upward.

| Duration | Discount | Plus | Pro | Ultra |
|---|---:|---:|---:|---:|
| **1 month** | 0% | **15 ⭐** | **35 ⭐** | **70 ⭐** |
| **3 months** | 10% | **41 ⭐** | **95 ⭐** | **189 ⭐** |
| **6 months** | 15% | **77 ⭐** | **179 ⭐** | **357 ⭐** |
| **12 months** | 20% | **144 ⭐** | **336 ⭐** | **672 ⭐** |

The UZS labels in the [plan comparison](#-plans--pricing) are configured independently in `bot.py`; **the application does not convert UZS to XTR**. The Free tier requires no payment.

### 🛒 How the Stars purchase works

1. Open **Plans** in the bot, select **Plus**, **Pro**, or **Ultra**, and choose **Buy with Stars** (or renew the current tier). If enabled, the bot offers 1-, 3-, 6-, and 12-month options when a paid purchase is required.
2. Review the price, applicable credit from an active plan, and estimated expiry date. A lower-tier switch is shown separately without a new Stars payment when remaining subscription value can be carried over.
3. Confirm the quote. The bot creates or reuses a PostgreSQL order, then sends a Telegram `send_invoice` message with `currency="XTR"`. The invoice has a **Pay** button and a **Cancel** button.
4. Telegram sends a `pre_checkout_query`. The bot validates the pending order, buyer, currency, Stars amount, expiry and original plan snapshot **before approving checkout**. Pre-checkout alone **never** grants a plan.
5. Only a `successful_payment` event triggers paid-plan activation. The bot checks the payment against stored order data and records the Telegram `telegram_payment_charge_id` to prevent repeat activation of the same charge.
6. A pending invoice/order is valid for **15 minutes**; the scheduled expiry job closes overdue orders. Users may cancel a pending invoice from its message.

If Telegram refuses to send an invoice, the bot cancels the newly created order and releases its rate-limit attempt. If the network fails and the delivery outcome is unknown, the pending order is retained temporarily because the invoice **might** have been delivered; check the chat before trying again.

### 🔄 Renewal, upgrades and downgrades

These behaviors come from [`payments.py`](payments.py) and the transaction logic in [`db.py`](db.py):

- **New subscription:** starts at payment activation and expires after the selected calendar-month duration.
- **Same-plan renewal:** extends from the existing paid plan's expiry when the plan is still active.
- **Upgrade:** applies the remaining value of the current plan as a Stars credit against the higher-tier quote. If credit covers the price, the switch may be completed **without another payment**; otherwise an invoice is issued for the difference.
- **Downgrade:** needs no new Stars charge; remaining value is converted into time on the lower-priced plan. The interface skips month selection and displays the calculated duration.
- **Plan changed while an invoice was open:** the server checks the current plan again when processing the successful payment and uses its state-change handling rather than simply overwriting the subscription shown when the invoice was created.
- **Admin-issued plans:** `/setplan` sets/replaces a plan independently; it does **not** perform a Telegram Stars charge. An active paid plan with **no expiry** cannot be purchased over through the normal Stars checkout.

Subscription value transfers and refunds have special handling for overlapping purchases and pending operations. Read the source and tests for accounting behavior; the bot does not promise cash refunds for unused time when a user simply changes plans.

### ↩️ Refunds and payment support

- **`/paysupport` — all users:** provides payment-support information and recent payment history. It remains available even when the account is blocked or has left a required subscription channel.
- **`/payments` — admin only:** displays recent payment records and the number of pending orders.
- **`/refund <charge_id|order_token>` — admin only:** requests a Telegram Stars refund through `refund_star_payment`, then updates the payment state and the applicable unused subscription value if the refund succeeds.
- **`/setplan <user> <plan> [duration]` — admin only:** remains available for manual plan administration and support; it is not a card-payment verification API.

An unmatched successful charge (for example, an amount/order mismatch) is recorded for review **without granting a plan**, so the administrator can investigate and refund it. Refunds are not a self-service button. Telegram/network/database errors may require reconciliation or manual administrator attention.

### 🗄️ Reliability, database records and limits

- `payments` stores orders, plan changes, Stars amount, status, invoice message ID, charge ID, and purchase-value tracking fields.
- `payment_inbox` stores unprocessed payment notifications; `payment_audit` records payment actions, and `payment_recon` stores the last successful Telegram transaction reconciliation marker.
- Payment activation uses PostgreSQL transactions and a unique `charge_id`. An in-memory retry queue supplements the persistent inbox. Restarts and transient failures are handled on a **best-effort recovery** basis; do not treat this as a guarantee of uninterrupted processing.
- Scheduled jobs retry queued payments **every 30 seconds**, expire pending orders **every 60 seconds**, and compare against Telegram Star transactions **every 30 minutes** (after their respective initial delays). Reconciliation can also detect external refunds.
- A user may create at most **5 new invoice orders per 10 minutes** in the in-memory rate limiter; the bot tries to reuse an existing matching active order rather than always creating a second one.
- `PAYMENTS_STARS_ENABLED=0` disables **new Stars sales**, but reconciliation of previous transactions continues. `PAYMENTS_CARD_ENABLED=0` hides the preserved manual-card display route by default.

**Important:** the legacy card/admin flow is not an automatic payment gateway and is **not the default purchase route**. For digital goods and services inside Telegram, check Telegram's current [Stars payment rules](https://core.telegram.org/bots/payments-stars) and [Bot Developer Terms](https://telegram.org/tos/bot-developers) before enabling alternative checkout methods. Verify real transactions with a test bot and isolated test database before enabling public payments.

## 📱 Getting started as a user

1. Open **[@autoreplyer_dbot](https://t.me/autoreplyer_dbot)** and send `/start`.
2. Choose **Uzbek, English, or Russian**. If the operator enables required channel membership, join the channel and tap **Check** to continue onboarding.
3. In Telegram, open **Settings → My Profile → Chat Automations** (the menu name and location can vary by client).
4. Connect **@autoreplyer_dbot**, choose **only the chats you want the bot to access**, and enable the **Reply to messages** permission. Save the connection.
5. Return to AutoReplyer and tap **Check connection**. If Telegram already sent a connection update, the wizard may have advanced automatically.
6. Review the auto-reply text and tap **Turn on Auto-Reply** to enable it with your consent.
7. Send a test message **from another Telegram account** in a chat you authorized; select **Reply arrived** only if you actually receive a reply, or **No reply** for troubleshooting.
8. Use the control panel for **Sleep Mode**, **Smart FAQ** (Plus/Pro/Ultra), **🧩 Automation Engine** (Plus/Pro/Ultra), **AI Personal Knowledge** (Ultra), **📅 Smart Scheduler** (weekly reply windows), **📊 Analytics** (today on Free; 7/30-day views and charts on paid plans), the **profile clock**, **BIO countdown**, and other plan-specific features.
9. To purchase a paid tier, select it in **Plans → Buy with Stars** (if enabled), choose a duration, and confirm the Telegram Stars invoice. For a payment problem, send `/paysupport`; payment support does not require access to premium bot features.

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
6. **📅 Smart Jadval** orqali kun va vaqtni tanlang, masalan, ish kunlari `09:00-18:00`. Jadval tugagach avvalgi Online/Offline sozlamalari ishlaydi. Free — 1 ta, Plus — 3 ta, Pro — 10 ta, Ultra — 30 ta jadval.
7. **🧩 Avtomatlashtirish (Automation Engine v1.2)** — Plus: **2 ta**, Pro: **10 ta**, Ultra: **30 ta** qoida. Plus'da bitta kalit so‘z, Pro/Ultra'da **2–5 ta kalit so‘z (YOKI/OR)** va ixtiyoriy **kun/vaqt (VA/AND)** shartlari mavjud. Masalan, `narx*, qancha, price` so‘zlaridan istalgani mos kelsa javob yuboriladi. `narx*` prefiksi `narx`, `narxi` va `narxlar`ga mos keladi. Qoidalarni tahrirlash (nom, kalit so‘z, javob, ustuvorlik; mos tarifda kun/vaqt) va statistikasini ko‘rish mumkin. Qoidalar oddiy Oflayn rejimda ishlaydi; Sleep Mode va faol Smart Jadvalda ishlamaydi.
8. **📊 Statistika** tugmasi orqali kelgan xabarlar, **Automation** va boshqa javob turlari hamda eng faol vaqtni kuzating. **Free — bugun; Plus — 7 kun; Pro/Ultra — 30 kun**. Grafiklar Plus'dan, batafsil hisobot Ultra'dan boshlanadi. Automation bo‘limida qoida bo‘yicha javoblar soni va o‘chirilgan qoidalar hisobga olingan tarixiy jami ham ko‘rsatiladi.
9. **⭐ Payments v1.0:** pullik tarifni **Tariflar** bo‘limida tanlang, **Stars orqali sotib olish** tugmasini bosing va 1/3/6/12 oy muddatdan birini tanlang (zarur bo‘lsa). Narxlar Plus uchun 15 ⭐, Pro uchun 35 ⭐, Ultra uchun 70 ⭐ dan boshlanadi; uzoq muddatlarga chegirma bor. To‘lov tasdiqlangach tarif avtomatik faollashadi. To‘lov bo‘yicha savol uchun `/paysupport` ishlaydi.
10. **Telegram paroli, kirish kodi yoki pasport ma’lumotlarini botga bermang.** AI javoblari xato qilishi mumkin.

Ilova menyulari Telegram versiyasiga qarab farq qilishi mumkin. Batafsil ma’lumot: [Smart Onboarding](#-smart-onboarding-first-time-setup) · [Smart FAQ](#-smart-faq-guide) · [AI Shaxsiy Bilimlar](#-ai-personal-knowledge-guide) · [AutoReply Analytics](#-autoreply-analytics-guide) · [Smart Scheduler](#-smart-auto-reply-scheduler-guide) · [Automation Engine](#-automation-engine-v12-guide) · [Stars Payments](#-telegram-stars-payments-v10).

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

`requirements.txt` also installs **Matplotlib ≥ 3.8** for server-side Analytics charts. When deploying in a slim Linux image, make sure the image provides the system libraries/fonts needed for Matplotlib to generate readable PNGs. No graphical desktop is required (the code uses the non-interactive `Agg` backend).

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
GEMINI_MODEL=gemini-2.5-flash

# Optional Telegram channel membership gate: set both or neither
REQUIRED_CHANNEL_ID=
REQUIRED_CHANNEL_LINK=

# Payments v1.0 — Telegram Stars checkout is enabled by default
PAYMENTS_STARS_ENABLED=1
# Legacy manual-card display is disabled by default (see Telegram rules)
PAYMENTS_CARD_ENABLED=0
# Only if maintaining a separately compliant legacy/manual route:
PAYMENT_CARD_NUMBER=
PAYMENT_CARD_HOLDER=

# Optional: set to 0 to restrict public use of the name clock
NAME_CLOCK_PUBLIC=1

# Health-check HTTP port (hosting provider typically sets this)
PORT=10000
```

**Notes:**

- `GEMINI_MODEL=gemini-2.5-flash` matches the current code default; model availability and the production instance's configuration depend on your own Gemini API project.
- `ADMIN_ID` should be a numeric Telegram user ID, not a username. Without a correctly set admin ID, privileged commands will not work as intended.
- Use a valid Supabase PostgreSQL connection string if you use Supabase. Follow your provider's SSL and pooling guidance; do not publish the URL.
- Set **both** required-channel variables to turn on the membership gate. Your bot needs suitable channel permissions to check membership.
- **Stars checkout:** `PAYMENTS_STARS_ENABLED` defaults to enabled. `PAYMENTS_CARD_ENABLED` defaults to disabled. The older manual-card display code is retained for operator-managed legacy use; it does not verify card transfers or grant plans automatically. **Do not enable an alternative in-bot digital subscription checkout without checking Telegram's Stars rules.**
- Do **not** publish payment card details in your repository. If maintaining the legacy route, set `PAYMENT_CARD_NUMBER` and `PAYMENT_CARD_HOLDER` explicitly in the hosting environment; the current code has an operator-specific fallback holder name. `/setplan` is a separate admin-only command.
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
| `PAYMENTS_STARS_ENABLED` | Enable new Telegram Stars invoices and plan purchases; default **on**. Existing-payment reconciliation runs independently. | Optional |
| `PAYMENTS_CARD_ENABLED` | Show the preserved legacy manual-card/admin route; default **off**. Review Telegram's digital-goods payment rules first. | Optional |
| `PAYMENT_CARD_NUMBER` | Legacy manual payment card displayed only when its route is enabled | Optional |
| `PAYMENT_CARD_HOLDER` | Displayed legacy recipient; **set explicitly if enabling the manual-card route** | Optional for that legacy route |
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

4. Add `BOT_TOKEN`, `DATABASE_URL`, `ADMIN_ID` and any optional variables in **Environment**. For Payments v1.0, Stars sales are enabled by default (`PAYMENTS_STARS_ENABLED=1`), while the legacy card route is disabled by default (`PAYMENTS_CARD_ENABLED=0`).
5. Use a persistent external PostgreSQL database such as Supabase.
6. If running as a web service, let Render provide `PORT` and configure a health check at `/` as applicable.
7. Review logs after deployment. Keep **one polling replica** for a given bot token.

> A successful HTTP health response only means the local health server is responding; it does **not** guarantee Telegram polling, Gemini, PostgreSQL **or Stars checkout** is currently healthy. Use application logs and provider monitoring for those components. Verify purchase, plan switch, recovery and refund flows with an isolated bot and disposable database before production deployment.

## 🧱 Architecture & data

```text
Telegram users / Telegram Business messages
                │
                ▼
        python-telegram-bot  ◄────► Telegram Bot API / Stars (XTR)
                │                            │
       ┌────────┴─────────┐                 invoices / payment events
       │                  │
       ▼                  ▼
    bot.py              ai.py ──► Google Gemini API
  handlers/jobs     optional AI replies + selected notes
       │
       ├── payments.py  (Stars pricing, subscription value and refunds)
       ├── logic.py     (FAQ, knowledge and schedule helpers)
       ├── automation.py (single/OR keyword, optional AND conditions)
       ├── i18n.py      (Uzbek / English / Russian)
       ├── analytics.py (statistics and Matplotlib charts)
       └── Scheduler    (weekly rules in bot.py / logic.py)
       │
       ▼
     db.py ───────────────► PostgreSQL / Supabase
       │                    users, settings, plans, connections,
       │                    FAQ and knowledge entries,
       │                    Automation and scheduler rules,
       │                    Analytics and AI history, broadcasts,
       │                    payments, payment_inbox,
       │                    payment_audit, payment_recon
       ▼
  Render / Python host
```

| File | Responsibility |
|---|---|
| [`bot.py`](bot.py) | Telegram handlers and Business updates; onboarding, Automation v1.2/FAQ/Knowledge Base panels, Analytics/Scheduler, AI routing, **Stars invoice, pre-checkout, successful-payment, refund and reconciliation handlers**, plans, jobs, moderation and health server |
| [`db.py`](db.py) | PostgreSQL schema/init, owner-scoped data, subscription state, **atomic Stars order creation/reuse, charge processing, refund tracking, payment inbox/audit/reconciliation markers**, Automation counters, Analytics, AI history and broadcast persistence |
| [`payments.py`](payments.py) | Pure Stars price table, 1/3/6/12-month discounts, plan renewal/upgrade/downgrade arithmetic, remaining-value transfers and refund calculations |
| [`automation.py`](automation.py) | Pure single-keyword / 2–5-keyword OR matching, optional day/time AND validation, and one-rule selection by priority/ID |
| [`ai.py`](ai.py) | Gemini requests, role presets, prompting with selected AI Personal Knowledge facts, and reply extraction |
| [`analytics.py`](analytics.py) | Time-window aggregation, busiest-hour calculation, line/pie/bar PNG chart rendering and short-lived chart caching |
| [`logic.py`](logic.py) | Cooldown/time handling, weekly schedule overlap and midnight-wrap calculation, countdowns, name formatting, FAQ matching, Personal Knowledge parsing and relevance ranking |
| [`i18n.py`](i18n.py) | User-facing strings in three languages, including Payments v1.0, Automation v1.2 and onboarding |
| [`tests/`](tests/) | Unit and behavior tests for Business replies, plans, AI, FAQ, Analytics, Scheduler, broadcasts and other features |
| [`tests/test_automation.py`](tests/test_automation.py), [`tests/test_automation_panel.py`](tests/test_automation_panel.py) and [`tests/test_automation_v12.py`](tests/test_automation_v12.py) | Automation v1.0–v1.2 compatibility, OR/AND rules, editor, plan gates, owner isolation, counters, deletion races and stale-button regressions |
| [`tests/test_payments.py`](tests/test_payments.py) | Stars prices and quotes, invoice/pre-checkout/payment handlers, purchase idempotency, PostgreSQL concurrency, payment recovery, refunds, rate limits, plan changes and localized checkout |
| [`requirements.txt`](requirements.txt) | Python runtime dependencies |

**Operational notes:**

- PostgreSQL persists account settings, onboarding progress, FAQ, Personal Knowledge, Analytics counters, saved Scheduler/Automation rules, broadcasts and payment data across Render restarts.
- On startup, `db.init_db()` creates/updates application tables, including `payments`, `payment_inbox`, `payment_audit` and `payment_recon`, plus Automation counters and other feature tables.
- Payment retries run every **30 seconds**, pending-order expiry every **60 seconds**, transaction reconciliation every **30 minutes**, and paid-plan expiration every **10 minutes**. These jobs require `python-telegram-bot[job-queue]`.
- Payment processing stores each Telegram charge identifier uniquely and uses PostgreSQL transactions; reconciliation and in-memory retries help recover disruptions. External service errors and partial failures still require operational monitoring.
- Analytics uses atomic per-hour PostgreSQL UPSERT counters with a connection pool. Retention cleanup runs through the AI cleanup job.
- Broadcasts persist progress, have a one-active-job database constraint, support recovery and retry, and handle Telegram rate limits. Exactly-once broadcast delivery is **not guaranteed**: an interruption between Telegram accepting a message and database progress being saved can produce a duplicate.
- Feature access and subscription status are enforced in application logic; third-party services still enforce their own limits.
- The built-in health endpoint answers `GET /` with `OK`.

## ⌨️ Bot commands

Regular users use the **inline control panel** reached through `/start`.

| Command | Who | What it does |
|---|---|---|
| `/start` | Everyone | Open the bot and its menu |
| `/help` | Everyone | Help and available commands |
| `/paysupport` | Everyone (including blocked / not subscribed) | Payment support and recent payment records |
| `/stats` | Admin | Summary statistics |
| `/onboarding` | Admin | Started, connected, auto-reply-enabled, completed, skipped, and in-progress onboarding counts |
| `/automation` | Admin | List/create/enable/disable/delete the administrator's own **single-keyword** rules; the Telegram panel handles v1.2 OR rules, editing and statistics |
| `/setplan` | Admin | Manually assign/replace a user plan, optionally with an expiry; does not charge Stars |
| `/userplans` | Admin | List subscriptions by tier and expiry |
| `/payments` | Admin | View recent payment records and pending order count |
| `/refund <charge_id or token>` | Admin | Request a Telegram Stars refund and reconcile the associated subscription value |
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

This assigns a time-limited plan to the specified user ID **without charging through Stars**; use the bot's help text for accepted user identifiers and duration formats. Administrator commands are checked against `ADMIN_ID`. For user payment problems, use `/paysupport`; for administration, use `/payments` and `/refund`.

## 🧪 Testing

The repository includes tests for AI and static reply flows, cooldown, broadcasts, Business connection state, name clock, BIO countdown, Smart FAQ, translations, **Smart Onboarding**, **AI Personal Knowledge**, **AutoReply Analytics**, **Smart Scheduler**, **Automation Engine v1.2** (including OR keywords, rule editing, counters and deletion races), **Payments v1.0** (invoice lifecycle, quote calculation, recovery, refund and concurrent order handling), and **test database safety guards**. The onboarding suite covers legacy/new users, channel-subscription transitions, connection permissions, skip/resume, localized default replies, completion checks, connection events, and admin statistics.

Install the development-only test runner and run the suite:

```bash
python -m pip install pytest
python -m pytest -q
```

**Onboarding, AI Personal Knowledge, Analytics, Scheduler, Automation and Payments database tests require `TEST_DATABASE_URL`.** Without it, their database-backed classes are skipped (other unit tests can still run). **Run the suite with pytest**, which loads `tests/conftest.py` *before test modules are imported* and overrides `DATABASE_URL` with the provided test URL, or a fake URL when none is set. Use a **dedicated disposable PostgreSQL test database**; never production:

```bash
# Example: PostgreSQL running locally on your development machine.
# Replace with YOUR disposable local test database:
export TEST_DATABASE_URL='postgresql://TEST_USER:TEST_PASSWORD@localhost:5432/autoreplyer_test'
python -m pytest tests/test_automation.py tests/test_automation_panel.py tests/test_automation_v12.py tests/test_payments.py tests/test_scheduler.py tests/test_analytics.py tests/test_knowledge.py tests/test_onboarding.py tests/test_db_guard.py -v
python -m pytest -q
```

Database integration suites call `db.init_db()` and create/update/delete records. The Analytics suite includes **parallel database writes**, per-owner counters, date periods, chart rendering in Uzbek/English/Russian, and plan-gate tests. Scheduler tests cover owner isolation, weekday and overnight boundaries, stale draft buttons, concurrency, cache invalidation and reply priority. Automation tests cover single/OR keyword matching, optional day/time AND filters, input validation, plan downgrades, owner isolation, rule editing/priority, concurrent rule-limit protection, Analytics categories, cumulative/deleted-rule counters, parallel send/delete races, menu flows and expired/stale buttons. **Payments tests** include XTR prices, invoice creation/expiration/cancellation, buyer and amount validation, duplicate charge rejection, upgrade/downgrade/refund accounting, concurrent user/payment locks, recovery after restart, external refund reconciliation, network delivery failures, and rate limiting. Do not run them against real user data. The pytest guard accepts local hosts by default and **refuses remote test database hosts** unless `ALLOW_REMOTE_TEST_DB=1` is explicitly set. **That opt-in is not proof a remote database is safe**; use it only for a separately provisioned throwaway test database.

**Important limitation:** the database guard is implemented in `tests/conftest.py`, which **pytest** loads. Running test modules directly with `unittest` bypasses this protection; do not do so with any production credentials or `DATABASE_URL`. A skipped test is **not** a passed test.

**GitHub Actions CI:** [`.github/workflows/tests.yml`](.github/workflows/tests.yml) runs the full pytest suite on **pushes and pull requests** with **Python 3.13** and a disposable **PostgreSQL 16** service. Check the matching commit in [Actions](https://github.com/TheBigChanges/AutoReplyer/actions/workflows/tests.yml). Re-running an old workflow checks the **old commit**, not the latest `main` branch.

**Recommended deployment workflow:** develop on a separate branch, use a distinct Telegram test bot token and PostgreSQL test database, manually test onboarding, Knowledge Base, Analytics and **Stars invoice → pre-checkout → confirmed payment → plan renewal/change → refund/support** (including owner isolation, downgrade restrictions, current-period charts, Scheduler/FAQ priority, overnight transitions, and a second Telegram account), then review and merge a pull request to `main`. Never run multiple polling processes with the production bot token.

## 🔐 Privacy, security & limitations

- **Official permissions only:** use the Telegram Business connection flow. The bot should never request Telegram passwords or authentication codes.
- **AI message processing:** incoming text and relevant chat context may be sent to Google's Gemini API when AI replies are enabled. **Relevant owner-authored Personal Knowledge entries are also sent to Gemini** when retrieved. Don't store information you aren't willing to disclose to a chat contact and the AI provider.
- **Stored data:** PostgreSQL stores settings, Business connections, **payment orders and audit/history data (including buyer IDs, charge IDs, Stars amounts and refund status)**, **onboarding state/timestamps**, **Smart FAQ entries**, **Automation rule names, keyword(s), conditions, fixed reply, priority, enabled flag, sent count and last-sent timestamp (owner-scoped JSONB rules), historical counts of deleted rules and the counters' start date**, **AI Personal Knowledge titles, texts and keywords**, **owner-scoped hourly Analytics counters (without message text/chat IDs)**, **owner-scoped saved Scheduler days/hours and reply text**, AI conversation history, referrals, broadcasts, and related metadata. AI history retrieval is limited to recent messages and a background cleanup job purges old history; verify retention and deletion behavior in [`db.py`](db.py) for your own deployment.
- **Secrets:** never commit `.env`, API keys, database URLs, Telegram tokens, or customer information. Rotate any exposed secrets immediately.
- **Analytics limitations:** counters are best-effort, begin only after the feature is running, and cannot recover past chat activity. Charts may be cached briefly.
- **Scheduler limitations:** saved rules persist in PostgreSQL but unfinished drafts are temporary in-memory data. Replies require Telegram Business permissions, and separate worker instances can briefly see older rule data until cache expiry. Analytics and Gemini AI chat-history storage are separate.
- **Automation Engine v1.2 limitations:** one required keyword condition (a single keyword or 2–5 OR alternatives), optionally combined with one days filter and one time filter via AND, and a single fixed `send_reply` action. No arbitrary nested Boolean conditions, ignore/block actions, or Automation Web App editor. Only Pro/Ultra have advanced conditions. Saved rules and cumulative counters persist in PostgreSQL; unfinished drafts/edit sessions and deletion confirmations stay in memory. Counters are best-effort and start from their recorded initialization date; earlier activity cannot be backfilled, and crashes or DB failures can cause missed counts. Matching fixed rules does not send chat text to Gemini.
- **AI limitations:** the model may be inaccurate, unavailable, or rate-limited. Knowledge Base retrieval is heuristic, and even an instruction to avoid invented or confidential details **cannot guarantee** a safe or correct generated response. Static reply fallback is available, but delivery is not guaranteed under every failure mode.
- **Telegram restrictions:** Business rights, flood limits, profile editing privileges, Stars payment rules and availability of features are controlled by Telegram.
- **Payments:** Telegram Stars (XTR) is the implemented automatic checkout for digital subscriptions; the legacy manual-card/admin display route is disabled by default. Subscription purchases are **one-time**, not recurring auto-billing. Refunds and recovery can require administrator action after failures; do not assume every network error means a payment failed. See [Payments v1.0](#-telegram-stars-payments-v10).
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