---
phase: 02-observability-rate-limiting
plan: 01
subsystem: logging
tags: [logging, observability, migration, named-loggers]
dependency_graph:
  requires: []
  provides: [bot/logging_config.py, named-loggers-in-all-modules]
  affects: [delivery/main.py, delivery/fetcher.py, delivery/ai.py, delivery/scheduler.py, api/webhook.py, bot/router.py, bot/commands/addtheme.py, bot/commands/payments.py]
tech_stack:
  added: []
  patterns: [logging.getLogger(__name__) per module, centralized basicConfig via bot/logging_config.setup()]
key_files:
  created:
    - bot/logging_config.py
  modified:
    - delivery/main.py
    - delivery/fetcher.py
    - delivery/ai.py
    - delivery/scheduler.py
    - api/webhook.py
    - bot/router.py
    - bot/commands/addtheme.py
    - bot/commands/payments.py
    - tests/test_fetcher.py
    - tests/test_webhook.py
decisions:
  - OBS-D-01: Idempotent setup() with _configured guard prevents double-configuration if both entry points import the same module
  - OBS-D-02: caplog fixture used instead of @patch("api.webhook.logger") for the reload test — importlib.reload() creates a new logger object that bypasses the pre-patched reference
metrics:
  duration_seconds: 278
  tasks_completed: 2
  files_changed: 10
  completed_date: "2026-03-22"
requirements_satisfied:
  - OBS-01
  - OBS-03
---

# Phase 02 Plan 01: Logging Migration Summary

**One-liner:** Centralized logging via bot/logging_config.py replaces 11 print() calls and 8 bare logging.* calls with named module loggers across all production files.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create logging config and migrate all modules | 144ba85 | bot/logging_config.py, delivery/main.py, delivery/fetcher.py, delivery/ai.py, delivery/scheduler.py, api/webhook.py, bot/router.py, bot/commands/addtheme.py, bot/commands/payments.py |
| 2 | Update test patches for named loggers | 02d8cc6 | tests/test_fetcher.py, tests/test_webhook.py |

## What Was Built

- `bot/logging_config.py`: Idempotent `setup()` function configuring root logger with `%(asctime)s %(levelname)s %(name)s -- %(message)s` format at INFO level.
- Both entry points (`api/webhook.py`, `delivery/main.py`) now call `setup_logging()` immediately after `load_dotenv()`, before any other logging occurs.
- 8 production modules each have `logger = logging.getLogger(__name__)` at module level.
- Inline `import logging` statements inside function bodies removed from `bot/router.py` and `bot/commands/addtheme.py`.
- All 11 `print()` calls in `delivery/main.py` replaced with appropriate `logger.info/warning/error` calls.
- `delivery/fetcher.py` broken-feed logging now uses named logger (OBS-03).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_webhook_logs_warning_when_secret_absent fails after logger migration**
- **Found during:** Task 2 verification
- **Issue:** The test used `@patch("api.webhook.logger")` then called `importlib.reload(api.webhook)`. On reload, Python re-executes `logger = logging.getLogger(__name__)` creating a new logger object — the patched reference is no longer the active one. The warning was emitted (visible in captured log) but `mock_logger.warning.called` remained False.
- **Fix:** Replaced `@patch("api.webhook.logger")` with `caplog` pytest fixture. Used `caplog.at_level(logging.WARNING, logger="api.webhook")` context manager around the reload, then asserted `any("WEBHOOK_SECRET" in r.message for r in caplog.records)`.
- **Files modified:** tests/test_webhook.py
- **Commit:** 02d8cc6

## Verification Results

- Zero `print()` calls in `delivery/main.py` and `api/webhook.py`
- 8 production modules have `logger = logging.getLogger(__name__)` (one per file)
- `bot/logging_config.py` exists with `setup()` function, correct format string, and INFO level
- Both entry points call `setup_logging()` before any logging occurs
- All 86 tests pass

## Known Stubs

None.

## Self-Check: PASSED

- `bot/logging_config.py` exists: FOUND
- Commit 144ba85 exists: FOUND
- Commit 02d8cc6 exists: FOUND
- 86 tests pass: CONFIRMED
