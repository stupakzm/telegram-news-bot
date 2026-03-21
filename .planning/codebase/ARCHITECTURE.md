# Architecture

**Analysis Date:** 2026-03-21

## Pattern

**Dual-mode serverless architecture:**
- **Webhook mode** — Synchronous: Vercel serverless function handles Telegram updates (HTTP POST → router → command → DB)
- **Delivery mode** — Asynchronous: GitHub Actions cron (hourly) runs `delivery.main` to fetch/summarize/post news

## Layers

```
┌──────────────────────────────────────────────────────┐
│  Entry Points                                        │
│  api/webhook.py (Vercel)  │  delivery/main.py (GHA) │
└──────────────┬────────────────────┬──────────────────┘
               │                    │
┌──────────────▼──────────┐  ┌──────▼───────────────────┐
│  Bot Layer              │  │  Delivery Pipeline        │
│  bot/router.py          │  │  scheduler → cache →      │
│  bot/commands/*.py      │  │  fetcher → ai → poster    │
│  bot/telegram.py        │  └──────────────────────────┘
└──────────────┬──────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│  Data Layer                                         │
│  db/client.py → Turso HTTP API → SQLite             │
└─────────────────────────────────────────────────────┘
```

## Components

### `api/webhook.py`
- Vercel `BaseHTTPRequestHandler` — receives Telegram POST updates
- Calls `bot.router.handle_update(update)`
- Catches all exceptions to always return HTTP 200 (Telegram requirement)

### `bot/router.py`
- Routes `callback_query` events to inline handler functions
- Routes `message` text to `COMMAND_MAP` dispatch
- Handles `user_pending_actions` state machine for multi-step flows
- Routes `successful_payment` to payments command

### `bot/commands/`
- One module per command: `start`, `themes`, `schedule`, `upgrade`, `history`, `addtheme`, `settings`, `payments`
- Each exports a `handle(message)` function; some export additional helpers (e.g., `toggle_feed`, `feeds_done`)
- Multi-step flows use `user_pending_actions` table as state machine

### `bot/telegram.py`
- Thin wrapper around Telegram Bot API HTTP calls
- `send_message`, `answer_callback_query`, etc.

### `delivery/scheduler.py`
- Queries `user_schedules` joined with `users` and `user_themes` for users due at current UTC hour/weekday
- Applies tier expiry logic inline (downgrades expired monthly → free)
- Groups deliveries by `(theme_type, theme_id)` for batch processing

### `delivery/cache.py`
- 6-hour quarters (0-3) keyed by `(theme_type, theme_id, date, quarter)`
- Stored in `theme_cache` table in Turso
- Cache hit: re-filters against recent `posted_articles`; Cache miss: fetch + summarize then store

### `delivery/fetcher.py`
- Parses RSS feeds via `feedparser` for each theme's `rss_feeds` list
- Filters articles already in `posted_articles` (last 24h)
- Silently skips broken feeds

### `delivery/ai.py`
- Builds prompt with article titles/descriptions + theme hashtag
- Fallback chain: Gemini 2.5 Flash → Gemini 2.0 Flash → Groq Llama-3.3-70b
- Returns structured JSON array (url, title, summary, hashtags, is_important, importance_detail)

### `delivery/poster.py`
- Formats and sends articles to users via Telegram

### `db/client.py`
- HTTP client for Turso's `/v2/pipeline` API
- `execute(sql, args)` → list of row dicts
- `execute_many(statements)` → batch pipeline request
- Type coercion for Turso's typed value format

## Data Flow

**Webhook (interactive):**
```
Telegram → POST /webhook → api/webhook.py → bot/router.py
  → [pending action check] → bot/commands/*.py
  → db/client.py → Turso
  → bot/telegram.py → Telegram API
```

**Delivery (scheduled, hourly):**
```
GitHub Actions cron → delivery/main.py
  → scheduler.get_due_deliveries() → db/client.py → Turso
  → group_by_theme()
  → cache.get_cached() [hit/miss]
    [miss] → fetcher.fetch_articles() → feedparser → RSS
           → ai.summarize_articles() → Gemini/Groq API
           → cache.set_cache()
    [hit]  → filter posted_articles
  → poster.post_article() → Telegram API (per user, 0.1s delay)
  → db.execute_many() → mark posted_articles, write digest_history
  → check_expiry_reminders()
```

## State Machine (multi-step bot flows)

`user_pending_actions` table stores intermediate state:
- `addtheme_ai_topic` → waiting for topic text
- `addtheme_ai_name` → waiting for custom name
- `addtheme_manual_name` → waiting for theme name
- `schedule_*` → waiting for schedule input

Router checks pending actions before command dispatch; handlers clear state when flow completes.

## Key Design Decisions

- **No framework** — raw Python HTTP handler instead of python-telegram-bot or FastAPI; keeps cold start minimal
- **Turso over SQLite file** — serverless-compatible distributed SQLite via HTTP
- **GitHub Actions as scheduler** — hourly cron avoids needing a separate scheduler service
- **Cache by quarter** — 6-hour windows prevent repeated AI calls for same theme across users
- **AI fallback chain** — 3-provider fallback ensures delivery even if primary AI is down

---
*Architecture analysis: 2026-03-21*
