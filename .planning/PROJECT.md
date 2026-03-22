# Telegram News Bot

## What This Is

A Telegram bot that delivers AI-summarized RSS news digests to subscribers on a user-defined schedule. Users pick topics (themes), configure delivery days/times, and receive curated article summaries directly in Telegram. Monetized via Telegram Stars (one-time and monthly tiers).

## Core Value

Users get relevant news delivered to them automatically — without having to seek it out.

## Requirements

### Validated

- ✓ User onboarding via `/start` — existing
- ✓ Browse and subscribe to built-in themes via `/themes` — existing
- ✓ Add custom themes via AI topic suggestion (`/addtheme`) — existing
- ✓ Add custom themes via manual RSS URLs (`/addthememanual`) — existing
- ✓ Per-user delivery scheduling (days + hour) via `/schedule` — existing
- ✓ AI-summarized article delivery via GitHub Actions hourly cron — existing
- ✓ Article deduplication (posted_articles, 24h window) — existing
- ✓ 6-hour article cache to avoid redundant AI calls — existing
- ✓ AI fallback chain (Gemini 2.5 Flash → Gemini 2.0 Flash → Groq Llama) — existing
- ✓ Digest history via `/history` — existing
- ✓ Settings overview via `/settings` — existing
- ✓ Telegram Stars payment flow (one-time + monthly) via `/upgrade` — existing
- ✓ Tier-based limits (free / paid) with expiry and downgrade logic — existing

### Active

**Phase 1 — Bug Fixes:**
- [ ] Fix race condition in custom theme creation (`RETURNING id` instead of `last_insert_rowid`)
- [ ] Fix Gemini fallback model name (verify correct `gemini-2.0-flash` model ID)
- [ ] Fix payment payload crash on malformed invoice (`IndexError` on missing colon)
- [ ] Fix silent RSS feed failures (log broken feeds at warning level)
- [ ] Add Telegram webhook secret verification (reject requests missing valid secret token)
- [ ] Fix RSS URL SSRF risk (validate against private IPs, enforce http/https scheme)

**Phase 2 — Observability & Rate Limiting:** *(Validated in Phase 02: observability-rate-limiting)*
- ✓ Structured logging with context (replaced bare `print()` / unstructured `logging`) — Validated Phase 02
- ✓ Rate limiting per user (5 commands/60s sliding window) — Validated Phase 02

### Out of Scope

- Real-time chat / DMs between users — not a social product
- Mobile app — Telegram is the client
- Web dashboard (non-admin) — bot-first UX
- OAuth / external identity — Telegram user_id is sufficient

## Context

- Deployed on Vercel (webhook) + GitHub Actions (hourly cron) + Turso (SQLite over HTTP)
- No framework — raw Python HTTP handler to minimize cold start
- Codebase has known bugs (documented in `.planning/codebase/CONCERNS.md`)
- Test suite exists but has coverage gaps: no payment tests, no webhook routing tests, no delivery E2E
- No error tracking service (Sentry etc.) — logs only to stdout / GitHub Actions logs

## Constraints

- **Tech stack**: Python 3.13, Vercel serverless, GitHub Actions, Turso — no infrastructure changes
- **No framework**: Keep raw HTTP handler pattern (no python-telegram-bot, no FastAPI)
- **DB**: Turso HTTP API only — no local SQLite, no connection pooling library
- **Payments**: Telegram Stars only — no Stripe or other payment processors

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Bug fixes before features | Known bugs affect reliability and security of existing users | — Pending |
| Coarse phase granularity | Project is brownfield with clear scope; fewer broader phases are sufficient | — Pending |
| No framework | Minimal cold start for Vercel serverless | ✓ Good |
| GitHub Actions as scheduler | Avoids dedicated scheduler service cost | ✓ Good |
| Turso over SQLite file | Serverless-compatible distributed SQLite | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

Last updated: 2026-03-22

---
*Last updated: 2026-03-21 after initialization*
