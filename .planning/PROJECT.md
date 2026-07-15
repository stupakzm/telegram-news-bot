# Telegram News Bot

## What This Is

A Telegram bot that delivers AI-summarized RSS news digests to subscribers on a
user-defined schedule. Each user builds their **own** feed list (raw RSS URLs or
curated URL packs) and a **keyword** watchlist; the bot fetches those feeds,
ranks articles by keyword relevance **in code**, has an LLM write short
summaries for the top picks, and posts them to the user in Telegram at their
scheduled local time. Monetized via Telegram Stars (one-time and monthly tiers).

## Core Value

Users get relevant news delivered to them automatically — filtered to the
keywords they care about — without having to seek it out.

---

## Architecture At A Glance

**Per-user pipeline (no shared cache).** Every user's feed × keyword combination
is unique, so there is no cross-user article cache; each user is fetched, scored,
summarized, and delivered independently by the hourly cron.

```
Webhook (interactive)          Delivery (hourly cron)
Vercel serverless              GitHub Actions
  api/webhook.py                 delivery/main.py
     │                              │  per due user:
  bot/router.py                     │   fetch feeds  → delivery/fetcher.py
  bot/commands/*.py                 │   score in code→ delivery/scoring.py
     │                              │   pick top-N, summarize → delivery/ai.py
  db/client.py ── Turso HTTP ───────┘   post → delivery/poster.py
```

- **Deterministic scoring** (`delivery/scoring.py`): case-insensitive,
  word-boundary keyword frequency; the user sees the match breakdown
  (`Tesla-12, Autopilot-8`). The LLM never decides relevance — only writes the
  summary and flags "important" items.
- **AI is summary-only** (`delivery/ai.py`): fallback chain
  Gemini 2.5 Flash → Gemini 2.0 Flash → Groq Llama-3.3-70b. Returns
  `{url, title, summary, is_important, importance_detail, skip}` per article.
- **No framework**: raw Python HTTP handler to keep Vercel cold-start minimal.
- **Turso HTTP** (`db/client.py`): `/v2/pipeline` API with connection retry on
  cold-start timeouts. No local SQLite, no pooling library.

## Feature Surface (as built)

**User commands** (`bot/commands/`):
- `/start` — onboarding
- `/addurl` — add an RSS feed URL, or pick a curated **URL pack** (`themes/url_packs.json`, seeded into `url_packs`)
- `/keywords` — manage the keyword watchlist that drives relevance scoring
- `/timezone` — set local timezone (schedule is interpreted in local time)
- `/settings` — overview of feeds, keywords, schedule, tier
- `/plan` — view current tier + upgrade pricing
- `/clear` — reset feeds/keywords
- `/help` — command reference
- `/admin` — owner-only health dashboard (active users 7d, deliveries/hour, revenue, recent errors)

**Delivery behaviors:**
- Keyword-matched digest for users with keywords; **random fresh picks** for users with feeds but no keywords yet (with a nudge to add keywords)
- "Quiet note" at most once per local day when nothing matched
- 👍/👎 reaction buttons on each article, stored per user per article (`article_reactions`)
- Per-article sent/failed/quiet tracking (`delivery_log`); per-feed failures logged (`delivery_errors`)

**Monetization:** Telegram Stars; tiers `trial` / `vip` / `svip` / `expired`
with expiry + downgrade (`bot/commands/plan.py`, `payments.py`).

**Safety / ops already in place:** webhook secret verification, RSS SSRF
validation (`bot/validation.py`), per-user command rate limiting
(`bot/rate_limiter.py`), structured logging (`bot/logging_config.py`).

## Data Model (Turso / `db/schema.sql`)

`users`, `user_feeds`, `user_keywords`, `seen_articles` (scored pool with
`sent_at`), `delivery_log`, `delivery_errors`, `url_packs`,
`user_pending_actions` (multi-step flow state), `bot_messages`,
`article_reactions`, `rate_limit_log`.

---

## Requirements

### Validated (shipped)

**Core product**
- ✓ Onboarding via `/start`
- ✓ Per-user RSS feeds via `/addurl` + curated URL packs
- ✓ Per-user keyword watchlist via `/keywords`, deterministic in-code scoring
- ✓ Timezone-aware per-user delivery schedule
- ✓ AI summary-only pipeline with 3-provider fallback
- ✓ Random-picks fallback for keyword-less users; once-a-day quiet note
- ✓ Article deduplication via `seen_articles` (per user, unique article_url)
- ✓ `/settings`, `/plan`, `/help`, `/clear`
- ✓ Telegram Stars payments (one-time + monthly), tier expiry/downgrade

**Reliability & safety** *(Phases 1–3, 2026-03)*
- ✓ Race-free feed/keyword inserts (`RETURNING id`)
- ✓ Payment payload parsing hardened; `pre_checkout_query` answered
- ✓ Webhook secret verification (403 on mismatch)
- ✓ RSS SSRF mitigation (scheme + private-IP block) in `bot/validation.py`
- ✓ Structured logging; per-feed failure logging to `delivery_errors`
- ✓ Per-user command rate limiting (5/60s sliding window)
- ✓ `/admin` health dashboard, 👍/👎 reactions, delivery tracking

**Post-v1 hardening** *(2026-07)*
- ✓ Turso cold-start timeout retry on hourly cron
- ✓ Dead-feed replacement across curated URL packs
- ✓ UX: command menu, `/help`, clickable titles, gentler empty states

**v2 — Reliability & Quality** *(2026-07-15, all shipped)*
- ✓ **AI-03** Prompt-injection hardening — feed text fenced as untrusted data, length-capped, forged markers stripped (`delivery/ai.py`)
- ✓ **AI-02** AI resilience — per-provider retry + backoff + jitter, process-wide circuit breaker (`delivery/ai.py`). *Dynamic model resolution deferred.*
- ✓ **FEED-01** Feed-health signal — broken feeds raise `FeedParseError` → `delivery_errors`; worst feeds (7d) in `/admin`; feedparser 6.0.12 (`delivery/feed_health.py`)
- ✓ **DEL-01** Delivery concurrency correct + tunable — process-wide Telegram token-bucket limiter (default 25 msg/s), per-thread sleeps removed, circuit breaker lock, concurrent per-user feed fetch, env-configurable workers (`delivery/ratelimit.py`, `delivery/main.py`)
- ✓ **DQ-01** Reaction-driven personalization — last-30d net 👍/👎 gently adjusts each feed's per-run pick quota + ordering; reaction totals in `/admin` (`delivery/personalize.py`). *(Cross-feed dedup already handled at insertion time.)*
- ✓ **UX-01** Onboarding — one-tap generic starter keywords (`kw:sugg:`) after pack import/skip
- ✓ **Command-flow hardening** — stale/abandoned `user_pending_actions` no longer swallow the next message (1h TTL + cleared on any command); add-flows send one combined message instead of two; reaction toast only claims "Noted" when actually stored

### Known issues / next candidates

- `/keywords` and `/addurl` lack the "Please /start first" guard that `/plan`, `/settings`, `/timezone` have → using them before `/start` can create orphan rows (no `users` row). Low frequency; fix = add the guard to those two `handle()` entrypoints.
- `_handle_reaction` matches the reaction button against only the last 200 `delivery_log` rows; a reaction on an older article silently isn't stored.
- Dynamic Gemini model resolution (deferred half of AI-02) — drop hard-pinned model names once validated.
- No full delivery E2E test; no error-tracking service (Sentry).

### Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time chat / DMs between users | Not a social product |
| Mobile app | Telegram is the client |
| Web dashboard (non-admin) | Bot-first UX |
| OAuth / external identity | Telegram user_id is sufficient |
| Stripe / other payment processors | Telegram Stars only |
| Redis / external cache | Per-user model has near-zero cache hit rate; not worth the infra |
| Shared cross-user article cache | Per-user feed×keyword combos are unique |

## Constraints

- **Stack**: Python 3.13, Vercel serverless, GitHub Actions cron, Turso — no infra changes
- **No framework**: keep the raw HTTP handler (no python-telegram-bot, no FastAPI)
- **DB**: Turso HTTP API only — no local SQLite, no pooling library
- **Payments**: Telegram Stars only

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Per-user feeds+keywords over shared themes | True personalization; users control exactly what they track | ✓ Current model |
| Scoring in code, not via LLM | Deterministic, cheap, transparent (user sees match counts) | ✓ Good |
| No shared cache | Per-user combos are unique → cache hit rate ≈ 0 | ✓ Good |
| No framework | Minimal cold start for Vercel serverless | ✓ Good |
| GitHub Actions as scheduler | Avoids a dedicated scheduler service cost | ✓ Good |
| Turso over SQLite file | Serverless-compatible distributed SQLite | ✓ Good |

## Context

- Deployed on Vercel (webhook) + GitHub Actions (hourly cron) + Turso (SQLite over HTTP)
- No error-tracking service (Sentry etc.) — logs to stdout / GitHub Actions logs
- Test suite: **166 passing** across bot commands, router, fetcher, scoring, scheduler, rate limiter, payments, AI, ratelimit, personalize, feed-health, webhook. Known gap: no full delivery E2E; one router test (`test_router_ignores_unknown_command`) makes a live Turso call and times out offline (deselect it when running offline).
- `.venv` in repo is built for a python3.11 that is no longer on this host; recreate against 3.13 (external drive lacks symlink support — build the venv on a native fs).

---

*This file is the single source of current project state. Last updated: 2026-07-15 — v2 (Reliability & Quality) complete: AI-02/03, FEED-01, DEL-01, DQ-01, UX-01, and command-flow hardening all shipped.*
