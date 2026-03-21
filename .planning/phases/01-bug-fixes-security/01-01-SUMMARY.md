---
phase: 01-bug-fixes-security
plan: 01
subsystem: bot-core
tags: [bug-fix, database, ai, payments, rss, tdd]
dependency_graph:
  requires: []
  provides: [BUG-01-fix, BUG-02-fix, BUG-03-fix, BUG-04-fix]
  affects: [bot/commands/addtheme.py, delivery/ai.py, bot/commands/payments.py, delivery/fetcher.py]
tech_stack:
  added: []
  patterns: [INSERT RETURNING id, early-return guard, structured logging]
key_files:
  created:
    - tests/bot/test_addtheme.py (added test_save_custom_theme_uses_returning_id)
    - tests/test_ai.py (added test_gemini_fallback_constant_is_valid_model, test_summarize_docstring_matches_constants)
    - tests/bot/test_payments.py (added test_handle_successful_payment_malformed_payload_no_colon, test_handle_successful_payment_empty_payload)
    - tests/test_fetcher.py (added test_fetch_articles_logs_broken_feed_with_url)
  modified:
    - bot/commands/addtheme.py
    - delivery/ai.py
    - bot/commands/payments.py
    - delivery/fetcher.py
decisions:
  - "BUG-01: Use INSERT...RETURNING id in one atomic call rather than last_insert_rowid() to eliminate TOCTOU race"
  - "BUG-02: Constant value was already correct (gemini-2.0-flash); only the docstring needed updating from 3.5 to 2.0"
  - "BUG-03: Validate colon presence before split rather than catching IndexError — makes intent explicit"
  - "BUG-04: Use logging.warning with %-style format string so URL and exception are in the log record"
metrics:
  duration_seconds: 164
  completed_date: "2026-03-21"
  tasks_completed: 2
  files_modified: 8
---

# Phase 01 Plan 01: Fix Race Condition, Gemini Fallback, Payment Parsing, Feed Logging Summary

**One-liner:** Four independent bugs fixed — atomic INSERT RETURNING id, corrected Gemini docstring, malformed-payload early return in payments, and RSS warning logs with URL and exception.

## What Was Built

Four targeted bug fixes across four production files, each covered by new TDD tests written before the fix.

### BUG-01 — Custom Theme INSERT Race Condition (addtheme.py)

`_save_custom_theme` was calling `db.execute(INSERT)` then `db.execute(SELECT last_insert_rowid())` as two separate round-trips. Under concurrent writes this could return the wrong ID. Replaced with a single `INSERT ... RETURNING id` call; the returned row `rows[0]["id"]` is used directly.

### BUG-02 — Gemini Fallback Docstring Mismatch (ai.py)

`GEMINI_FALLBACK = "gemini-2.0-flash"` was already the correct constant. The bug was in the `summarize_articles` docstring which read "Gemini 3.5 Flash" instead of "Gemini 2.0 Flash". Updated docstring to match the constant.

### BUG-03 — Payment Payload Crash on Malformed Input (payments.py)

`payload.split(":", 1)[1]` raised `IndexError` when the payload contained no colon. Added an `if ":" not in payload:` guard that logs `logging.error` with the raw payload and user ID, sends a user-facing "could not be processed" message, and returns early before any DB write.

### BUG-04 — Silent Swallow of Broken RSS Feeds (fetcher.py)

`except Exception: continue` swallowed all feed errors with no trace. Added `import logging` and replaced the bare continue with `logging.warning("RSS feed failed: url=%s error=%s", feed_url, e)` so broken feeds are traceable with URL and exception detail.

## Test Results

```
67 passed in 1.07s
```

All pre-existing tests continued to pass. 5 new tests added.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 RED | 9fd1444 | test(01-01): add failing tests for BUG-01 RETURNING id and BUG-02 docstring |
| Task 1 GREEN | bc15a19 | fix(01-01): BUG-01 atomic INSERT RETURNING id, BUG-02 fix docstring |
| Task 2 RED | 207caea | test(01-01): add failing tests for BUG-03 malformed payload and BUG-04 feed logging |
| Task 2 GREEN | d50cecb | fix(01-01): BUG-03 payment payload guard, BUG-04 broken feed logging |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None. All fixes wire directly to production logic with no placeholders.

## Self-Check: PASSED
