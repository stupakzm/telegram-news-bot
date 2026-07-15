# Roadmap: Telegram News Bot

**Current milestone:** v2 — Reliability & Quality
**Updated:** 2026-07-15

---

## v1 — Stable & Featured ✅ (complete, 2026-03)

Shipped across three phases; full detail in `.planning/phases/01…03` and
`REQUIREMENTS.md`.

| Phase | Name | Outcome |
|-------|------|---------|
| 1 | Bug Fixes & Security | Race-free inserts, payment parsing, webhook secret, RSS SSRF guard |
| 2 | Observability & Rate Limiting | Structured logging, per-feed failure logs, per-user rate limiting |
| 3 | New Features | `/admin` dashboard, 👍/👎 reactions, per-article delivery tracking |

Plus post-v1 hardening (2026-07): Turso cold-start retry, curated-pack dead-feed
replacement, UX pass (command menu, `/help`, clickable titles, gentler empty
states), `pre_checkout_query` fix.

---

## v2 — Reliability & Quality

**Goal:** Make the hourly delivery run robust under provider slowness and abuse,
and raise the quality/personalization of what lands in each user's chat.

### Phase 4 — Delivery Robustness *(in progress)*

Order of execution reflects risk-reduction first, then a review checkpoint.

**4A — Harden now** *(done 2026-07-15)*
- [x] **AI-03** — Prompt-injection hardening: article text fenced in `<<<ARTICLES_JSON_UNTRUSTED>>>…<<<END>>>` markers, title/body length-capped, forged markers stripped, model instructed to treat fenced content as data only. (`delivery/ai.py`, `tests/test_ai.py`)
- [x] **AI-02** — AI provider resilience: per-provider retry with exponential backoff + jitter (`_call_with_retry`) and a process-wide circuit breaker (`_circuit_open_until`, 300s cooldown) so a failed provider is skipped for the rest of the hourly run. (`delivery/ai.py`, `tests/test_ai.py`)
  - ↪ *Deferred sub-part:* dynamic Gemini model resolution (drop the hard-pinned names) — intentionally held for the 4A review as the riskier, network-dependent piece; hard-pins retained for now.
- [x] **FEED-01** — Feed-health signal: broken feeds (200 OK but unparseable/zero-entry) now raise `FeedParseError` → recorded in `delivery_errors`; `delivery/feed_health.py` aggregates worst-offending feeds (7d) and `/admin` shows them. `feedparser` bumped 6.0.11 → 6.0.12. (`delivery/fetcher.py`, `delivery/feed_health.py`, `bot/commands/admin.py`, tests)

  **⏸ PAUSE for review after 4A — reached.**

**4B — Concurrency** *(plan-first, not started)*
- [ ] **DEL-01** — Concurrent/async delivery: replace the blocking per-article `sleep` loop and sequential per-user processing with bounded concurrency + a Telegram rate-limit semaphore, isolating users so one slow AI call or large batch can't stall the whole run. **Write a plan before implementing.**

### Phase 5 — Product Quality *(plan-first, not started)*

- [ ] **DQ-01** — Digest quality: collapse cross-feed near-duplicate stories in a run; start acting on the already-stored 👍/👎 reactions to bias future picks (reaction-driven personalization). **Write a plan before implementing.**
- [ ] **UX-01** — Onboarding polish: get a brand-new user to their first useful digest in a single step (starter pack + suggested keywords), reducing the empty feeds/keywords cold start. **Write a plan before implementing.**

---

## Execution Notes

- **4A** ships in this iteration, then we stop for review before touching concurrency.
- **DEL-01, DQ-01, UX-01** are explicitly plan-first: produce a phase plan
  (approach, files, tests, risks) and get sign-off before writing code.

## Phase Summary

| Phase | Name | Status |
|-------|------|--------|
| 1–3 | v1 (bugs, observability, features) | Complete |
| 4A | AI hardening + feed health | In progress |
| 4B | Async delivery (DEL-01) | Planned (plan-first) |
| 5 | Digest quality + onboarding | Planned (plan-first) |

---
*v1 roadmap created 2026-03-21; v2 opened 2026-07-15.*
