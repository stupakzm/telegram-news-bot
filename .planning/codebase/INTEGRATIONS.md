# External Integrations

**Analysis Date:** 2026-03-21

## APIs & External Services

**AI/Summarization:**
- Google Gemini API - Primary AI provider for news article summarization
  - SDK/Client: `google-generativeai==0.8.3`
  - Models: `gemini-2.5-flash` (primary), `gemini-2.0-flash` (fallback)
  - Auth: `GEMINI_API_KEY` environment variable
  - Used in: `delivery/ai.py`

- Groq API - Fallback AI provider using Llama model
  - SDK/Client: `requests` (REST API)
  - Model: `llama-3.3-70b-versatile`
  - URL: `https://api.groq.com/openai/v1/chat/completions`
  - Auth: `GROQ_API_KEY` environment variable
  - Used in: `delivery/ai.py` (fallback when Gemini fails)

**Messaging/Platform:**
- Telegram Bot API - User interaction and message delivery
  - SDK/Client: `requests` (REST API calls)
  - Base URL: `https://api.telegram.org/bot{token}/{method}`
  - Auth: `TELEGRAM_BOT_TOKEN` environment variable
  - Methods used: `sendMessage`, `answerCallbackQuery`, `sendInvoice`
  - Supported features: Markdown formatting, inline keyboards, Stars payment integration
  - Used in: `bot/telegram.py`, `delivery/scheduler.py`, `delivery/poster.py`

**Content Aggregation:**
- RSS Feed Parsing - Multiple user-configured RSS feeds
  - SDK/Client: `feedparser==6.0.11`
  - Configuration: Per-theme RSS feed URLs stored as JSON array in database
  - Used in: `delivery/fetcher.py`
  - Fetches: Article URLs, titles, summaries/descriptions

## Data Storage

**Databases:**
- Turso - SQLite-compatible serverless database
  - Provider: Turso (https://turso.io)
  - Connection: HTTP API via `https://{TURSO_URL}/v2/pipeline`
  - Client: `requests` library (direct HTTP calls)
  - Auth: Bearer token in `TURSO_TOKEN` environment variable
  - Implementation: Custom HTTP wrapper in `db/client.py`
  - Tables: users, themes, custom_themes, user_themes, user_schedules, digest_history, posted_articles, theme_cache, user_pending_actions

**File Storage:**
- Local filesystem only - Theme definitions (JSON) in `themes/default_themes.json`

**Caching:**
- In-database cache: `theme_cache` table for storing AI-summarized articles
  - Scoped by: theme_type, theme_id, cache_date, quarter (6-hour intervals)
  - Used in: `delivery/cache.py`, `delivery/main.py`

## Authentication & Identity

**Auth Provider:**
- Telegram native - Users authenticate via Telegram user_id
  - Implementation: User identified by `user_id` (Telegram user ID)
  - No external OAuth/identity provider
  - Used in: `bot/router.py` (update parsing), all commands

## Payments

**Payment Processing:**
- Telegram Stars - Native Telegram in-app payment system
  - Currency: XTR (Telegram Stars)
  - Implementation: `send_invoice` API method in Telegram Bot API
  - Configuration: Prices set via `STARS_ONETIME_PRICE` and `STARS_MONTHLY_PRICE` env vars
  - Tracking: `users.stars_paid` column stores total Stars spent
  - Used in: `bot/commands/payments.py`, `bot/telegram.py`

## Monitoring & Observability

**Error Tracking:**
- None detected - No external error tracking service (Sentry, etc.)
- Logging: Python `logging` module for console output
- Error handling: Exceptions logged and printed, failures recorded in delivery logs

**Logs:**
- Standard output/print statements
- GitHub Actions job logs for scheduled delivery runs
- No centralized log aggregation

## CI/CD & Deployment

**Hosting:**
- Vercel - Serverless function hosting for Telegram webhook endpoint
  - Configuration: `vercel.json`
  - Function: `api/webhook.py` running Python 3.12
  - Endpoint: `/webhook` route

**CI Pipeline:**
- GitHub Actions (`.github/workflows/deliver.yml`)
  - Trigger: Hourly cron schedule (`0 * * * *` UTC) and manual workflow dispatch
  - Checkout: code at commit
  - Python 3.13 setup
  - Dependency installation from `requirements.txt`
  - Executes: `python -m delivery.main` with secrets injected
  - Runs delivery/summarization/posting orchestration

## Environment Configuration

**Required env vars:**
- `TURSO_URL` - Turso database URL (format: `https://your-db-name-org.turso.io`)
- `TURSO_TOKEN` - Turso bearer token for HTTP API authentication
- `TELEGRAM_BOT_TOKEN` - Telegram Bot API token
- `GEMINI_API_KEY` - Google Gemini API key
- `GROQ_API_KEY` - Groq API key
- `STARS_ONETIME_PRICE` - Telegram Stars price for one-time subscription (e.g., 200)
- `STARS_MONTHLY_PRICE` - Telegram Stars price for monthly subscription (e.g., 100)

**Secrets location:**
- GitHub Actions: Repository secrets (referenced in `.github/workflows/deliver.yml`)
- Local development: `.env` file (loaded by `python-dotenv`)
- Example template: `.env.example`

## Webhooks & Callbacks

**Incoming:**
- Telegram Webhook - Incoming user updates (messages, callbacks, payments)
  - Endpoint: `/webhook` (Vercel function at `api/webhook.py`)
  - Handler: `bot.router.handle_update(update)` processes JSON update object
  - Methods: Message text, callback queries, pre_checkout_query, successful_payment

**Outgoing:**
- Telegram API calls - All outbound communication uses direct HTTP POST to Telegram API
  - No webhooks for Telegram responses (request/response pattern)
- No webhooks to external services (all integrations are pull-based)

---

*Integration audit: 2026-03-21*
