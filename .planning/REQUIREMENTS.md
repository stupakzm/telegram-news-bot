# Requirements: Telegram News Bot

**Defined:** 2026-03-21
**Core Value:** Users get relevant news delivered to them automatically — without having to seek it out.

## v1 Requirements

### Bug Fixes

- [ ] **BUG-01**: Custom theme creation uses `RETURNING id` to avoid race condition (replaces `last_insert_rowid`)
- [ ] **BUG-02**: Gemini fallback model name is correct and resolves without 404
- [ ] **BUG-03**: Payment handler gracefully handles malformed invoice payload (no `IndexError`)
- [ ] **BUG-04**: Broken RSS feeds are logged at warning level with URL and exception detail
- [ ] **BUG-05**: Webhook endpoint verifies `X-Telegram-Bot-Api-Secret-Token` header; returns 403 on mismatch
- [ ] **BUG-06**: RSS URL input validated against private IP ranges and enforces http/https scheme

### Observability

- [ ] **OBS-01**: All `print()` statements replaced with structured `logging.getLogger()` calls
- [ ] **OBS-02**: Delivery runs emit structured log entries (theme_id, user_id, article count, status)
- [ ] **OBS-03**: Broken feed URLs surfaced in logs with enough context to diagnose

### Safety

- [ ] **SAFE-01**: Per-user command rate limiting (max 5 commands/minute, returns friendly message)
- [ ] **SAFE-02**: RSS feed URLs validated before storage (scheme, private IP block, redirect limit)

### Features

- [ ] **FEAT-01**: `/admin` command (bot owner only) shows active users, deliveries/hour, recent errors
- [ ] **FEAT-02**: Article messages include 👍/👎 reaction buttons; reactions stored per user per article
- [ ] **FEAT-03**: Delivery pipeline tracks sent/failed status per article per user

## v2 Requirements

### Delivery Improvements

- **DEL-01**: Async Telegram posting with rate-limit semaphore (replace 0.1s sleep loop)
- **DEL-02**: Batch DB queries during delivery run (eliminate per-theme round trips)
- **DEL-03**: Cache invalidation on theme edit (clear stale quarter cache)

### AI Improvements

- **AI-01**: Dynamic Gemini model selection (fetch available models at startup)
- **AI-02**: Exponential backoff + circuit breaker for AI provider timeouts
- **AI-03**: Input sanitization to prevent prompt injection from user-supplied text

### Infrastructure

- **INF-01**: Startup env var validation (raise `RuntimeError` if required keys missing)
- **INF-02**: Structured JSON log format for production log aggregation
- **INF-03**: Dead-letter handling for failed webhook updates

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
| BUG-01 | Phase 1 | Pending |
| BUG-02 | Phase 1 | Pending |
| BUG-03 | Phase 1 | Pending |
| BUG-04 | Phase 1 | Pending |
| BUG-05 | Phase 1 | Pending |
| BUG-06 | Phase 1 | Pending |
| OBS-01 | Phase 2 | Pending |
| OBS-02 | Phase 2 | Pending |
| OBS-03 | Phase 2 | Pending |
| SAFE-01 | Phase 2 | Pending |
| SAFE-02 | Phase 1 | Pending |
| FEAT-01 | Phase 3 | Pending |
| FEAT-02 | Phase 3 | Pending |
| FEAT-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-21*
*Last updated: 2026-03-21 after initial definition*
