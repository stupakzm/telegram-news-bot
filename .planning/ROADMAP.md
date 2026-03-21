# Roadmap: Telegram News Bot

**Milestone:** v1.0 — Stable & Featured
**Created:** 2026-03-21

---

## Phase 1 — Bug Fixes & Security

**Goal:** Eliminate all known bugs and close critical security gaps. Make the bot safe and reliable for existing users before adding anything new.

**Requirements:** BUG-01, BUG-02, BUG-03, BUG-04, BUG-05, BUG-06, SAFE-02

**Plans:** 2 plans

Plans:
- [ ] 01-01-PLAN.md — Fix race condition, Gemini fallback, payment parsing, feed logging (BUG-01, BUG-02, BUG-03, BUG-04)
- [ ] 01-02-PLAN.md — Webhook secret verification and RSS SSRF mitigation (BUG-05, BUG-06, SAFE-02)

**Deliverables:**
- `RETURNING id` in custom theme INSERT (eliminates race condition)
- Correct Gemini fallback model name verified and updated
- Payment payload parsing hardened (safe split + validation)
- Broken RSS feeds logged at warning level with URL + exception
- Webhook secret token header verified; 403 on mismatch
- RSS URL SSRF mitigation (private IP block + scheme validation)

**Done when:** All 6 bugs fixed, tests pass, no regressions.

---

## Phase 2 — Observability & Rate Limiting

**Goal:** Make production issues diagnosable and protect the bot from abuse.

**Requirements:** OBS-01, OBS-02, OBS-03, SAFE-01

**Deliverables:**
- Structured logging throughout (replace `print()` / bare `logging.warning()`)
- Delivery runs emit per-theme structured log entries
- Per-user command rate limiting (5 commands/minute)

**Done when:** Logs are structured and queryable; rate limit returns friendly message; delivery run logs show clear per-theme status.

---

## Phase 3 — New Features

**Goal:** Add the most-wanted capabilities: admin visibility, user feedback on articles, and delivery tracking.

**Requirements:** FEAT-01, FEAT-02, FEAT-03

**Deliverables:**
- `/admin` command (owner-only): active users, deliveries/hour, recent errors, payment revenue
- Reaction buttons on delivered articles; reactions stored per user per article
- Delivery pipeline tracks sent/failed status per article per user in DB

**Done when:** Admin can see bot health at a glance; users can react to articles; delivery failures are recorded and queryable.

---

## Phase Summary

| Phase | Name | Requirements | Status |
|-------|------|-------------|--------|
| 1 | Bug Fixes & Security | BUG-01-06, SAFE-02 | Pending |
| 2 | Observability & Rate Limiting | OBS-01-03, SAFE-01 | Pending |
| 3 | New Features | FEAT-01-03 | Pending |

---
*Roadmap created: 2026-03-21*
*Last updated: 2026-03-21 after phase 1 planning*
