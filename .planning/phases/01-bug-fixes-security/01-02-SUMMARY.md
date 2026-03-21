---
phase: 01-bug-fixes-security
plan: "02"
subsystem: api, security
tags: [hmac, ssrf, webhook, rss, ipaddress, validation]

# Dependency graph
requires:
  - phase: 01-bug-fixes-security/01-01
    provides: logging infrastructure in fetcher (import logging already present)
provides:
  - Webhook secret token verification with hmac.compare_digest
  - Module-level startup warning when WEBHOOK_SECRET is absent
  - Shared RSS URL validator blocking private IPs and non-http/https schemes
  - SSRF mitigation in addtheme command (primary) and fetcher (safety net)
affects: [delivery, api, bot/commands]

# Tech tracking
tech-stack:
  added: [hmac (stdlib), ipaddress (stdlib), socket (stdlib)]
  patterns:
    - Constant-time secret comparison via hmac.compare_digest
    - Shared validation module (bot/validation.py) imported by multiple subsystems
    - Early-rejection pattern — security check before body read in webhook

key-files:
  created:
    - api/webhook.py (modified — added secret verification)
    - bot/validation.py
    - tests/test_webhook.py
    - tests/test_url_validation.py
  modified:
    - bot/commands/addtheme.py
    - delivery/fetcher.py
    - tests/bot/test_addtheme.py
    - tests/test_fetcher.py

key-decisions:
  - "BUG-05: Use hmac.compare_digest for constant-time token comparison to prevent timing attacks"
  - "BUG-05: Emit startup warning at module import time (not per-request) when WEBHOOK_SECRET is absent"
  - "BUG-06/SAFE-02: Extract validator to bot/validation.py shared module so addtheme and fetcher both use the same logic"
  - "BUG-06/SAFE-02: SSRF mitigation uses ipaddress stdlib — no new dependencies required"

patterns-established:
  - "Security check before I/O: webhook rejects unauthorized requests before reading body"
  - "Shared validation: URL safety logic lives in one module imported by all callers"
  - "Layered defence: addtheme validates at user-input time, fetcher re-validates as safety net"

requirements-completed: [BUG-05, BUG-06, SAFE-02]

# Metrics
duration: 3min
completed: 2026-03-22
---

# Phase 1 Plan 02: Webhook Secret Verification and RSS SSRF Mitigation Summary

**Webhook secured with hmac.compare_digest header check; RSS SSRF blocked via shared ipaddress validator covering RFC 1918, loopback, link-local, and CGNAT ranges**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-22T11:01:59Z
- **Completed:** 2026-03-22T11:05:11Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Webhook endpoint now verifies `X-Telegram-Bot-Api-Secret-Token` header with constant-time comparison; returns 403 on mismatch
- Startup warning fires at module import when `WEBHOOK_SECRET` env var is absent (backwards compatible — unauthenticated mode still works)
- New shared module `bot/validation.py` with `validate_rss_url` blocking non-http/https schemes and all private IP ranges
- `_validate_feed` in addtheme calls URL validator before any HTTP request; handle_pending shows user-facing "restricted address" error
- `fetch_articles` in fetcher skips restricted URLs with a logged warning before invoking feedparser

## Task Commits

Each task was committed atomically:

1. **Task 1: Webhook secret token verification (BUG-05)** - `bcb726b` (feat)
2. **Task 2: RSS URL SSRF validation (BUG-06/SAFE-02)** - `52f1e7c` (feat)

**Plan metadata:** (docs commit — pending)

_Note: TDD tasks followed RED → GREEN flow. Tests written first, then implementation._

## Files Created/Modified
- `api/webhook.py` - Added `import hmac`, `import logging`, module-level startup warning, secret token check in do_POST
- `bot/validation.py` - New shared URL validator; rejects bad schemes and private IP ranges via ipaddress stdlib
- `bot/commands/addtheme.py` - Added validate_rss_url call in _validate_feed and user-facing error in handle_pending
- `delivery/fetcher.py` - Added validate_rss_url skip guard before feedparser.parse
- `tests/test_webhook.py` - 5 tests covering valid secret, wrong secret, missing header, no env secret, startup warning
- `tests/test_url_validation.py` - 12 tests covering valid URLs, ftp scheme, RFC 1918 ranges, loopback, CGNAT, IPv6, empty string
- `tests/bot/test_addtheme.py` - Added test_handle_pending_manual_urls_rejects_restricted_url
- `tests/test_fetcher.py` - Added test_fetch_articles_skips_restricted_url

## Decisions Made
- Used `hmac.compare_digest` for constant-time token comparison — prevents timing side-channel attacks
- Startup warning emitted at module import rather than per-request to avoid log spam while still alerting operators at deploy time
- Extracted URL validator to `bot/validation.py` so both addtheme and fetcher share identical logic with no duplication
- SSRF validation uses Python stdlib only (`ipaddress`, `socket`, `urllib.parse`) — no new third-party dependencies needed
- Layered approach: addtheme validates at user input time (primary gate with user-facing error); fetcher validates again as safety net

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Known Stubs

None — all validation logic is fully wired. No placeholder values or TODO stubs in produced code.

## User Setup Required

To enable webhook authentication, set the `WEBHOOK_SECRET` environment variable to a secret string and configure the same value in Telegram's setWebhook call (`secret_token` parameter). Without this env var the webhook remains unauthenticated but will log a warning at startup.

## Next Phase Readiness
- All Phase 1 security fixes complete (BUG-01 through BUG-06, SAFE-02)
- Ready to proceed to Phase 2: Observability & Rate Limiting
- No outstanding blockers

## Self-Check: PASSED

All files verified present. All commits verified in git log.

---
*Phase: 01-bug-fixes-security*
*Completed: 2026-03-22*
