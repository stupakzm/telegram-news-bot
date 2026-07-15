# Architecture

**Refreshed:** 2026-07-15 (supersedes the 2026-03 themes/shared-cache model)

## Pattern

**Dual-mode serverless architecture:**
- **Webhook mode** — Synchronous: Vercel serverless function handles Telegram updates (HTTP POST → router → command → DB)
- **Delivery mode** — Asynchronous: GitHub Actions cron (hourly) runs `delivery.main` to fetch → score → summarize → post per due user

The core model is **per-user**: each user owns a feed list and a keyword list;
there is no shared cross-user cache because every user's feed×keyword combination
is effectively unique.

## Layers

```
┌──────────────────────────────────────────────────────┐
│  Entry Points                                        │
│  api/webhook.py (Vercel)  │  delivery/main.py (GHA)  │
└──────────────┬────────────────────┬──────────────────┘
               │                    │
┌──────────────▼──────────┐  ┌──────▼───────────────────┐
│  Bot Layer              │  │  Delivery Pipeline        │
│  bot/router.py          │  │  scheduler → fetcher →    │
│  bot/commands/*.py      │  │  scoring → ai → poster    │
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
- Verifies `X-Telegram-Bot-Api-Secret-Token`, then calls `bot.router.handle_update(update)`
- Catches handler exceptions to return HTTP 200 (Telegram requirement)

### `bot/router.py`
- Routes `callback_query` events to inline handlers (reactions, admin refresh, pack pickers, etc.)
- Routes `message` text through `user_pending_actions` state machine, then `COMMAND_MAP`
- Applies per-user rate limiting to `/` commands (`bot/rate_limiter.py`)
- Routes `successful_payment` / `pre_checkout_query` to the payments command

### `bot/commands/`
- One module per command: `start`, `addurl`, `keywords`, `timezone`, `settings`, `plan`, `payments`, `clear`, `help`, `admin`
- Multi-step flows (add feed, name, etc.) persist intermediate state in `user_pending_actions`

### `bot/telegram.py`
- Thin wrapper around Telegram Bot API HTTP calls (`send_message`, `edit_message_text`, `answer_callback_query`, …)

### `delivery/scheduler.py`
- `get_due_users()` — users whose local schedule matches the current UTC hour/weekday
- Tier expiry handling; helpers for local "today start" timestamps; seen-article cleanup; expiry reminders

### `delivery/fetcher.py`
- `fetch_today_articles(feed_url, today_start_ts)` — validates URL (SSRF guard), GETs with timeout + UA, parses via `feedparser`, strips HTML, caps body, filters to today
- Raises `requests.RequestException` on transport errors so the caller logs to `delivery_errors` and skips the feed

### `delivery/scoring.py`
- `score_article(title, body, keywords)` — deterministic, case-insensitive, word-boundary keyword frequency; returns `(total, {keyword: count})`
- `format_relevance(breakdown)` — renders the user-visible match line

### `delivery/ai.py`
- Builds a single batch prompt from the top picks; fallback chain Gemini 2.5 → Gemini 2.0 → Groq
- Returns `{url, title, summary, is_important, importance_detail}` with `skip=true` items dropped

### `delivery/poster.py`
- Formats and sends one article message per user (title link, summary, importance detail, relevance line, 👍/👎 buttons)

### `db/client.py`
- HTTP client for Turso's `/v2/pipeline` API
- `execute(sql, args)` → row dicts; `execute_many(statements)` → batch pipeline
- `_post_with_retry` retries on connect/read timeouts and connection errors (Turso cold start)

## Data Flow

**Webhook (interactive):**
```
Telegram → POST /webhook → verify secret → bot/router.py
  → [rate limit] → [pending action?] → bot/commands/*.py
  → db/client.py → Turso
  → bot/telegram.py → Telegram API
```

**Delivery (scheduled, hourly):**
```
GitHub Actions cron → delivery/main.py
  → scheduler.get_due_users() → db/client.py → Turso
  → for each due user:
      fetcher.fetch_today_articles() per feed  (failures → delivery_errors)
      scoring.score_article() in code
      dedupe against seen_articles / recent delivery_log
      upsert scored pool → seen_articles
      pick top-N unsent (or random picks if user has no keywords)
      ai.summarize_articles()  (Gemini → Gemini → Groq)
      poster.post_article() per article  (flood pause between sends)
      write delivery_log (sent/failed/quiet)
  → check_expiry_reminders()
```

## State Machine (multi-step bot flows)

`user_pending_actions` stores intermediate state (e.g. awaiting a feed URL, a
name, a keyword). The router checks pending actions before command dispatch;
handlers clear state when the flow completes.

## Key Design Decisions

- **Per-user, no shared cache** — feed×keyword combos are unique; a shared cache would rarely hit
- **Relevance scored in code** — deterministic, cheap, and transparent to the user; the LLM only summarizes
- **No framework** — raw HTTP handler keeps Vercel cold start minimal
- **Turso over SQLite file** — serverless-compatible distributed SQLite via HTTP, with cold-start retry
- **GitHub Actions as scheduler** — hourly cron avoids a separate scheduler service
- **3-provider AI fallback** — delivery still succeeds if the primary model is down

## Known Structural Risks (see CONCERNS.md)

- Delivery is fully synchronous and per-user sequential — one slow AI provider or large user can stall the whole hourly run (→ DEL-01)
- AI providers get one attempt each at a 60s timeout, no backoff/circuit breaker (→ AI-02)
- User-supplied text flows into the AI prompt without delimiting/escaping (→ AI-03)
- Feed failures are logged per-run but not aggregated into a health view (→ FEED-01)

---
*Architecture refreshed: 2026-07-15*
