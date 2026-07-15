# Requirements: Telegram News Bot

**Defined:** 2026-03-21
**Core Value:** Users get relevant news delivered to them automatically — without having to seek it out.

## v1 Requirements

### Bug Fixes

- [x] **BUG-01**: Custom theme creation uses `RETURNING id` to avoid race condition (replaces `last_insert_rowid`)
- [x] **BUG-02**: Gemini fallback model name is correct and resolves without 404
- [x] **BUG-03**: Payment handler gracefully handles malformed invoice payload (no `IndexError`)
- [x] **BUG-04**: Broken RSS feeds are logged at warning level with URL and exception detail
- [x] **BUG-05**: Webhook endpoint verifies `X-Telegram-Bot-Api-Secret-Token` header; returns 403 on mismatch
- [x] **BUG-06**: RSS URL input validated against private IP ranges and enforces http/https scheme

### Observability

- [x] **OBS-01**: All `print()` statements replaced with structured `logging.getLogger()` calls
- [x] **OBS-02**: Delivery runs emit structured log entries (theme_id, user_id, article count, status)
- [x] **OBS-03**: Broken feed URLs surfaced in logs with enough context to diagnose

### Safety

- [x] **SAFE-01**: Per-user command rate limiting (max 5 commands/minute, returns friendly message)
- [x] **SAFE-02**: RSS feed URLs validated before storage (scheme, private IP block, redirect limit)

### Features

- [x] **FEAT-01**: `/admin` command (bot owner only) shows active users, deliveries/hour, recent errors
- [x] **FEAT-02**: Article messages include 👍/👎 reaction buttons; reactions stored per user per article
- [x] **FEAT-03**: Delivery pipeline tracks sent/failed status per article per user

## v2 Requirements — Reliability & Quality

> Architecture note: v2 targets the **current per-user pipeline** (feeds +
> keywords + in-code scoring, no shared cache). Old v2 items that assumed the
> retired themes/quarter-cache model (e.g. "cache invalidation on theme edit")
> have been dropped.

### Phase 4A — Harden now *(done 2026-07-15)*

- [x] **AI-03**: Prompt-injection hardening — user-supplied text wrapped in explicit untrusted-data markers, length-capped, forged markers stripped; prompt instructs the model to treat fenced content as data, never as instructions.
- [x] **AI-02**: AI provider resilience — per-provider retry with exponential backoff + jitter and a process-wide circuit breaker skipping a known-down provider for the rest of the run. *(Dynamic Gemini model resolution deferred to the 4A review — hard-pins retained for now.)*
- [x] **FEED-01**: Feed-health signal — unparseable/zero-entry feeds now raise and are recorded in `delivery_errors`; per-feed 7-day aggregation surfaced in `/admin`; `feedparser` bumped 6.0.11 → 6.0.12.

### Phase 4B — Concurrency *(plan-first, not started)*

- [ ] **DEL-01**: Concurrent/async delivery — bounded concurrency + Telegram rate-limit semaphore replaces the blocking sleep loop; per-user isolation so one slow provider can't stall the run.

### Phase 5 — Product Quality *(plan-first, not started)*

- [ ] **DQ-01**: Digest quality — collapse cross-feed near-duplicate stories in a run; act on stored 👍/👎 reactions to bias future picks (reaction-driven personalization).
- [ ] **UX-01**: Onboarding polish — new user reaches first useful digest in one step (starter pack + suggested keywords).

### Deferred / opportunistic

- **INF-01**: Startup env var validation (raise `RuntimeError` if required keys missing)
- **INF-02**: Structured JSON log format for production log aggregation
- **DEL-02**: Batch per-user DB queries during delivery run

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time chat between users | Not a social product |
| Mobile app | Telegram is the client |
| Web dashboard for non-admin | Bot-first UX |
| OAuth / external identity | Telegram user_id is sufficient |
| Stripe or other payment processors | Telegram Stars only |
| Redis / external cache | Turso cache table is sufficient for current scale |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BUG-01 | Phase 1 | Done |
| BUG-02 | Phase 1 | Done |
| BUG-03 | Phase 1 | Done |
| BUG-04 | Phase 1 | Done |
| BUG-05 | Phase 1 | Done |
| BUG-06 | Phase 1 | Done |
| OBS-01 | Phase 2 | Complete |
| OBS-02 | Phase 2 | Complete |
| OBS-03 | Phase 2 | Complete |
| SAFE-01 | Phase 2 | Complete |
| SAFE-02 | Phase 1 | Done |
| FEAT-01 | Phase 3 | Complete |
| FEAT-02 | Phase 3 | Complete |
| FEAT-03 | Phase 3 | Complete |

**Coverage:**
- v1 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-21*
*Last updated: 2026-07-15 — v2 (Reliability & Quality) requirements aligned to the per-user architecture.*
