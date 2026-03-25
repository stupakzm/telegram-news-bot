---
phase: 03-new-features
plan: 01
subsystem: database
tags: [turso, sqlite, delivery-tracking, schema]

# Dependency graph
requires:
  - phase: 02-observability-rate-limiting
    provides: structured delivery logs and delivery pipeline (delivery/main.py)
provides:
  - delivery_log table: per-article per-user sent/failed delivery tracking
  - article_reactions table: up/down reaction storage with composite PK
  - delivery_errors table: theme-level pipeline error capture
  - delivery/main.py integration: inserts into delivery_log and delivery_errors during pipeline run
affects: [03-02, 03-03, admin-queries, reaction-handlers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "delivery_log_statements accumulator: collect rows during per-user loop, batch insert after theme loop"
    - "delivery_errors immediate insert in outer except: wrapped in own try/except to avoid masking original error"
    - "CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS: idempotent schema evolution pattern"

key-files:
  created: []
  modified:
    - db/schema.sql
    - delivery/main.py

key-decisions:
  - "D-13: delivery_log.status is 'sent' or 'failed' only — two terminal states per article per user"
  - "D-11: article_reactions uses composite PK (user_id, article_url) — one reaction per user per article, last write wins"
  - "D-15: delivery_errors captures theme_id, theme_type, error_msg, occurred_at for /admin display"
  - "Batch accumulator for delivery_log follows existing posted_articles pattern — collect then flush after theme loop"
  - "delivery_errors inserted immediately in outer except (not batched) because accumulator may be partial at that point"

patterns-established:
  - "Batch insert pattern: accumulate (sql, args) tuples in list, execute_many after loop completes"
  - "DB-write try/except isolation: wrap DB writes in own try/except to avoid masking application errors"

requirements-completed: [FEAT-03]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 3 Plan 01: Schema Foundation + Delivery Tracking Summary

**Three new Turso tables (delivery_log, article_reactions, delivery_errors) added to schema and delivery pipeline now records sent/failed status per article per user**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T13:07:17Z
- **Completed:** 2026-03-25T13:10:17Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added delivery_log, article_reactions, delivery_errors tables with correct indexes to db/schema.sql
- Integrated delivery_log accumulator into delivery/main.py inner loop (sent on success, failed on exception)
- Added delivery_errors insert in outer except block, isolated in its own try/except to avoid masking the original error
- Batch delivery_log flush follows existing posted_articles pattern (collect then execute_many after theme loop)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add delivery_log, article_reactions, delivery_errors tables to schema** - `6ff276a` (feat)
2. **Task 2: Add delivery_log and delivery_errors inserts to delivery pipeline** - `5619e12` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `db/schema.sql` - Three new tables and indexes appended following existing conventions
- `delivery/main.py` - delivery_log_statements accumulator, per-article status tracking, delivery_errors insert

## Decisions Made

- Batch accumulator for delivery_log: collect `(sql, args)` tuples in `delivery_log_statements` list during the per-user inner loop, flush with `execute_many` after the theme loop completes — matches posted_articles pattern
- delivery_errors inserted immediately in outer except (not batched): the accumulator may be incomplete at that point and the error is terminal for the theme
- delivery_errors insert wrapped in its own `try/except` so a DB failure does not mask the original exception

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `python db/init_db.py` requires live Turso credentials (`TURSO_URL`, `TURSO_TOKEN`). No `.env` file with real credentials exists in the worktree (only `.env.example`). The schema SQL is correct and idempotent (`CREATE TABLE IF NOT EXISTS`); the init_db.py step must be run manually with live credentials to apply to the Turso database. This is a deployment step, not a code issue.

## User Setup Required

Run `python db/init_db.py` with `.env` containing valid `TURSO_URL` and `TURSO_TOKEN` to apply the three new tables to the live Turso database.

## Next Phase Readiness

- Schema foundation complete: delivery_log, article_reactions, delivery_errors tables are defined and pipeline integration is live
- Phase 03 plans 02 and 03 can now build reaction handlers and admin queries on top of these tables
- Pending: manual `python db/init_db.py` run against live Turso to materialize the tables

---
*Phase: 03-new-features*
*Completed: 2026-03-25*
