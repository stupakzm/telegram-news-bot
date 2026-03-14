# Telegram Personalized News Bot — Design Spec

**Date:** 2026-03-14
**Status:** Approved
**Replaces:** `telegram-news-bot-channel` (single shared channel bot)

---

## Overview

A Telegram bot that delivers personalized news digests to individual users in DMs. Users subscribe to topic themes, configure their delivery schedule, and receive AI-summarized articles from curated RSS feeds. Monetized via Telegram Stars with three tiers: Free, One-time Paid, and Monthly Paid.

---

## Architecture

Two runtimes sharing one database:

```
USER
  │  commands, settings, Stars payment
  ▼
TELEGRAM WEBHOOK
  │  POST
  ▼
VERCEL SERVERLESS (bot/)
  │  reads/writes user prefs
  ▼
TURSO (cloud SQLite) ◄──── GITHUB ACTIONS (delivery/, hourly cron)
```

- **Vercel** handles all user-initiated interaction (commands, inline keyboards, payments). Instant response.
- **GitHub Actions** runs every hour, finds users due for delivery, fetches RSS, calls AI, sends digests.
- **Turso** is the single source of truth for all user and content data. Never stored in the repo.

---

## AI Model Fallback Chain

1. **Gemini 2.5 Flash** (primary)
2. **Gemini 3.5 Flash** (fallback on quota/error — confirmed present in API as of spec date)
3. **Groq Llama** (final fallback)

One AI call per theme per quarter-window, shared across all users subscribed to that theme.

The AI prompt instructs the model to return a JSON array where each article includes:
- `summary`: 2–3 punchy sentences
- `hashtags`: 1–2 from the theme's tag list
- `is_important`: boolean — true only if major real-world impact (market event, regulation, major breach, etc.)
- `importance_detail`: one paragraph of context if `is_important`, else empty string

`is_important` is AI-determined from article content. No RSS field or threshold is used.

---

## Quarter-Based Theme Cache

Each day is split into four 6-hour windows (UTC):

| Quarter | Hours |
|---------|-------|
| Q1 | 00:00 – 05:59 |
| Q2 | 06:00 – 11:59 |
| Q3 | 12:00 – 17:59 |
| Q4 | 18:00 – 23:59 |

Cache key: `(theme_type, theme_id, date, quarter)`. On cache hit, AI call is skipped and cached summaries are delivered. On cache miss (new quarter or unseen theme), RSS is fetched fresh and AI is called. News refreshes up to 4× per day.

Custom themes are cached the same way as default themes, distinguished by `theme_type = 'custom'`.

---

## Tiers

| Feature | Free | One-time Paid | Monthly Paid |
|---------|------|---------------|--------------|
| Default themes | up to 5 | up to 6 | up to 9 |
| Custom themes | ✗ | 1 | up to 3 |
| Articles per theme | 1 news item (2 posts if important) | 1 news item (2 posts if important) | 1–2 news items (up to 4 posts if important) |
| Schedule | one global (days + time) | per-theme custom | per-theme custom |
| Digest history | ✗ | ✗ | ✓ (last 30) |
| Payment | — | Telegram Stars, one-time | Telegram Stars, monthly |

**Post vs article distinction:**
- "Article" = one news item (one AI summary)
- "Post" = one Telegram message
- A non-important article = 1 post
- An important article = 2 posts (main message + "Why this matters" followup reply)
- `articles_per_theme` in the DB stores the count of **news items**, not posts

**Monthly tier expiry:** `tier_expires_at` is checked by the delivery engine at run time. If expired, the user is treated as Free tier for that run. The bot also sends a reminder 3 days before expiry. Tier reverts to `free` (not `one_time`) on expiry.

---

## Data Model (Turso)

### `users`
| field | type | notes |
|-------|------|-------|
| user_id | INTEGER PK | Telegram user ID |
| tier | TEXT | `free` / `one_time` / `monthly` |
| tier_expires_at | INTEGER | NULL for free/one-time; Unix ts for monthly; delivery engine checks before applying tier limits |
| created_at | INTEGER | Unix timestamp |
| stars_paid | INTEGER | lifetime Stars paid |
| last_reminder_at | INTEGER | Unix ts of last expiry reminder sent; NULL if never |

### `user_themes`
| field | type | notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER | FK → users |
| theme_type | TEXT | `default` or `custom` |
| theme_id | INTEGER | FK → themes.id if default; FK → custom_themes.id if custom |
| articles_per_theme | INTEGER | count of news items (not posts): 1 for free/one-time, 1–2 for monthly |

Note: `(theme_type, theme_id)` together identify the theme. The delivery engine uses both fields when grouping and cache-looking up.

### `user_schedules`
| field | type | notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER | FK → users |
| user_theme_id | INTEGER | NULL = global schedule (free tier); FK → user_themes.id for per-theme schedules (paid) |
| days | TEXT | JSON array e.g. `[1,3,5]` (Mon/Wed/Fri, 1=Monday) |
| hour_utc | INTEGER | 0–23 |

**Free tier enforcement:** the bot webhook enforces that free users may only have one `user_schedules` row (`user_theme_id = NULL`). Attempting to add a second schedule row for a free user is rejected at the application layer.

### `themes`
| field | type | notes |
|-------|------|-------|
| id | INTEGER PK | |
| name | TEXT | e.g. "Artificial Intelligence" |
| hashtag | TEXT | e.g. `#ai` |
| rss_feeds | TEXT | JSON array of URLs |
| is_active | INTEGER | 0/1, admin toggle |

### `custom_themes`
| field | type | notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER | FK → users |
| name | TEXT | user-defined |
| hashtag | TEXT | user-defined tag e.g. `#evs`; used in AI prompt and post formatting |
| rss_feeds | TEXT | JSON array of URLs |
| ai_suggested | INTEGER | 0/1 flag |

### `digest_history`
| field | type | notes |
|-------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER | FK → users |
| theme_type | TEXT | `default` or `custom` |
| theme_id | INTEGER | references themes.id or custom_themes.id depending on theme_type |
| theme_name | TEXT | snapshot of name at send time (for display even if theme later deleted) |
| articles | TEXT | JSON |
| sent_at | INTEGER | Unix timestamp |

### `posted_articles`
| field | type | notes |
|-------|------|-------|
| url | TEXT PK | article URL |
| posted_at | INTEGER | Unix timestamp |

**Dedup scope is global by design.** An article URL delivered via any theme is never delivered again, regardless of theme or user. This prevents the same news item appearing multiple times across overlapping themes in the same user's digest. Accepted trade-off: an article appearing in two theme feeds will only be delivered through whichever theme processes it first in that quarter.

### `theme_cache`
| field | type | notes |
|-------|------|-------|
| theme_type | TEXT | `default` or `custom` |
| theme_id | INTEGER | references themes.id or custom_themes.id |
| cache_date | TEXT | `YYYY-MM-DD` (UTC) |
| quarter | INTEGER | 0–3 |
| articles | TEXT | JSON summaries from AI |
| generated_at | INTEGER | Unix timestamp |

**Primary key:** `(theme_type, theme_id, cache_date, quarter)` — composite, enforces one cache entry per theme per quarter-window. Duplicate inserts are rejected or replaced via `INSERT OR REPLACE`.

---

## User Interaction (Vercel Webhook)

### Commands

| command | description | tier |
|---------|-------------|------|
| `/start` | onboarding wizard | all |
| `/themes` | browse and toggle subscribed themes | all |
| `/schedule` | set delivery days + time | all |
| `/settings` | current config overview | all |
| `/upgrade` | view tier comparison, pay with Stars | all |
| `/history` | view last 30 digests | monthly |
| `/addtheme` | AI-suggested custom theme (describe a topic) | one-time, monthly |
| `/addthememanual` | custom theme via manual RSS URL input | one-time, monthly |

### Onboarding Flow
```
/start
  → Welcome message + "Set up your feed" button
  → Browse themes (inline keyboard, paginated)
  → Select themes (up to tier limit)
  → Set schedule: pick days → pick hour (default: Mon–Fri, 9am UTC)
  → Confirm → queued for next scheduled run
```

### Upgrade Flow
```
/upgrade
  → Clean comparison message showing all 3 tiers + benefits
  → Inline buttons: "Pay X Stars (one-time)" | "Subscribe Y Stars/month"
  → Telegram native Stars invoice
  → successful_payment webhook → update user.tier (and tier_expires_at for monthly) in Turso
```

### Custom Theme — AI Flow (`/addtheme`)
```
/addtheme
  → "Describe a topic" prompt
  → user types e.g. "electric vehicles"
  → Gemini call → returns 3–5 RSS feed suggestions with descriptions
  → inline keyboard: user picks which feeds to include
  → user names the theme
  → saved to custom_themes, linked in user_themes (theme_type='custom')
```

### Custom Theme — Manual Flow (`/addthememanual`)
```
/addthememanual
  → "Paste RSS feed URLs (one per line)" prompt
  → user sends URLs
  → bot validates each feed (feedparser check)
  → user names the theme
  → saved to custom_themes, linked in user_themes (theme_type='custom')
```

---

## Delivery Engine (GitHub Actions)

**Cron:** every hour on the hour (UTC). 720 runs/month — within free tier.

**Run sequence:**
```
1. scheduler.py
   → query Turso: user_schedules WHERE hour_utc = now
               AND JSON_EACH(days) contains today's weekday integer (1=Mon…7=Sun)
               (SQLite JSON-contains check; no day_of_week column exists)
   → for each result, also fetch the linked user_themes row(s)
   → returns list of (user_id, theme_type, theme_id) tuples due this hour
   → check users.tier_expires_at; if expired, apply free-tier limits for that user

2. Group by (theme_type, theme_id)
   → ('default', 3) → [user1, user2, user5]     # #tech
   → ('default', 1) → [user1, user3]             # #ai
   → ('custom', 42) → [user7]                    # user7's custom theme

3. For each unique (theme_type, theme_id):
   → cache.py: check theme_cache WHERE theme_type=X AND theme_id=Y
               AND cache_date=today AND quarter=current_quarter
   → CACHE HIT → use cached articles JSON
               (cached article URLs are still filtered against posted_articles
                before sending — prevents edge case where same URL later
                appears in a different theme's cache)
   → CACHE MISS:
       → fetcher.py: fetch RSS feeds for this theme, filter posted_articles
       → ai.py: one AI call → summaries JSON (with is_important per article)
                fallback chain: Gemini 2.5 Flash → Gemini 3.5 Flash → Groq Llama
       → cache.py: INSERT OR REPLACE into theme_cache

4. poster.py: fan out per user
   → for each user due: trim article list to user's articles_per_theme limit
   → format_post() per article → send DM via Bot API
   → if article.is_important → send followup reply (reply_to main message_id)

5. Write delivered article URLs to posted_articles (global dedup)
6. For monthly users: write to digest_history (theme_type, theme_id, theme_name snapshot, articles JSON)
7. Expiry reminder check (runs once per hour, independent of user schedules):
   → query users WHERE tier='monthly'
     AND tier_expires_at BETWEEN now AND now+259200 (3 days)
     AND (last_reminder_at IS NULL OR last_reminder_at < now-86400)
   → for each match: send reminder DM via Bot API
   → update users.last_reminder_at = now
```

---

## Project Structure

```
telegram-news-bot/
├── .github/
│   └── workflows/
│       └── deliver.yml             # hourly cron
├── bot/
│   ├── webhook.py                  # Vercel entry point
│   ├── commands/
│   │   ├── start.py
│   │   ├── themes.py
│   │   ├── schedule.py
│   │   ├── upgrade.py
│   │   ├── history.py
│   │   └── addtheme.py             # handles both /addtheme and /addthememanual
│   └── payments.py                 # Stars invoice + successful_payment handler
├── delivery/
│   ├── scheduler.py
│   ├── fetcher.py
│   ├── ai.py
│   ├── cache.py
│   └── poster.py
├── db/
│   ├── client.py                   # Turso connection
│   ├── schema.sql                  # all table definitions including composite PKs
│   └── migrations/
├── themes/
│   └── default_themes.json         # admin-managed, 6 initial themes (expandable)
├── vercel.json
├── requirements.txt
└── .env.example
```

---

## Environment Variables

| variable | used by | notes |
|----------|---------|-------|
| `TURSO_URL` | both | Turso database URL |
| `TURSO_TOKEN` | both | Turso auth token |
| `TELEGRAM_BOT_TOKEN` | both | Bot API token |
| `GEMINI_API_KEY` | delivery | Google AI API key |
| `GROQ_API_KEY` | delivery | Groq fallback key |
| `STARS_ONETIME_PRICE` | bot | Stars amount for one-time tier |
| `STARS_MONTHLY_PRICE` | bot | Stars amount for monthly tier |

---

## Default Themes (Initial Library — 6 themes)

| hashtag | name | initial RSS sources |
|---------|------|-------------------|
| `#tech` | Technology | TechCrunch, The Verge |
| `#ai` | Artificial Intelligence | VentureBeat AI, MIT Tech Review |
| `#privacy` | Privacy & Security | EFF, Wired Security |
| `#software` | Software Development | InfoQ, Hacker News |
| `#techcompanies` | Tech Companies | Reuters Tech, Bloomberg Tech |
| `#hardware` | Hardware | AnandTech, Tom's Hardware |

Expandable without code changes via `default_themes.json` + a Turso insert. The `is_active` flag lets admin disable themes without deletion.

---

## Key Design Decisions

1. **Turso over repo SQLite** — user data must never be in the repo (privacy, security).
2. **Vercel + GitHub Actions split** — right tool for each job; both free at this scale.
3. **Quarter-based cache** — balances news freshness (4× daily) with AI quota efficiency.
4. **Unified (theme_type, theme_id) references** — default and custom themes share the same delivery and cache pipeline; theme_type distinguishes which table to look up.
5. **Global dedup** — simplest correct behavior; same news item never appears twice regardless of theme overlap.
6. **AI-determined importance** — `is_important` comes from the AI prompt response, same approach as the predecessor project.
7. **Three tiers** — free entry point, one-time for casual upgraders, monthly for power users.
8. **Telegram Stars** — native payment, no external billing, cashout via Fragment → TON.
9. **Application-layer tier enforcement** — free users limited to one global schedule row; enforced by the webhook handler, not DB constraints.
