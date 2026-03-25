---
phase: 03-new-features
plan: 02
subsystem: bot-features
tags: [reactions, admin, telegram-callbacks, inline-keyboard]

# Dependency graph
requires:
  - phase: 03-new-features
    plan: 01
    provides: article_reactions table, delivery_errors table, delivery_log table
provides:
  - reaction buttons on article messages (inline_keyboard with thumbs up/down)
  - reaction callback handler in router (stores to article_reactions via INSERT OR REPLACE)
  - /admin command handler (owner-only health dashboard)
  - /admin registered in COMMAND_MAP
affects: [03-03, article-delivery-UX, admin-monitoring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "reply_markup parameter: optional dict passed through to Telegram sendMessage payload"
    - "data.split(':', 2): limit splits to 3 parts so URLs containing colons do not break callback parsing"
    - "reaction handler returns after answering callback: prevents double answer_callback_query call"
    - "os.environ.get('OWNER_USER_ID'): avoids KeyError if env var absent, handles unauthenticated gracefully"

key-files:
  created:
    - bot/commands/admin.py
  modified:
    - delivery/poster.py
    - bot/router.py

key-decisions:
  - "D-07/D-08: reply_markup added as optional parameter to _send_message (not a separate wrapper) — minimal change, followup message correctly omits it"
  - "D-09: reaction callback uses data.split(':',2) — exactly 3 parts, URLs with colons parse correctly"
  - "D-10: reaction handler calls answer_callback_query with emoji toast then returns — prevents generic empty-text call at end of _handle_callback"
  - "D-01: os.environ.get (not os.environ[]) for OWNER_USER_ID — graceful when env var not set"

# Metrics
duration: 185s
completed: 2026-03-25
---

# Phase 3 Plan 02: Reaction Buttons and /admin Command Summary

**Inline keyboard reaction buttons added to article delivery; reaction callback handler stores votes to article_reactions; /admin command gives bot owner a health dashboard with active users, deliveries/hour, revenue, and recent errors**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T12:14:01Z
- **Completed:** 2026-03-25T12:17:06Z
- **Tasks:** 2
- **Files modified:** 3 (2 modified, 1 created)

## Accomplishments

- Updated `_send_message` in delivery/poster.py to accept `reply_markup: dict = None` parameter
- Built inline keyboard with thumbs-up and thumbs-down buttons in `post_article`, using `reaction:up:<url>` and `reaction:down:<url>` callback_data format
- Added `import time` and reaction callback handler to bot/router.py using `split(":", 2)` to safely handle URLs with colons
- Reaction handler stores vote via `INSERT OR REPLACE INTO article_reactions` and shows emoji toast, then returns to prevent double `answer_callback_query`
- Created bot/commands/admin.py with owner-only authorization (`OWNER_USER_ID` env var), 4 metric queries, and Markdown health dashboard
- Registered `/admin` in COMMAND_MAP and added `admin` to the import line in bot/router.py

## Task Commits

Each task was committed atomically:

1. **Task 1: Add reaction buttons to article delivery and reaction callback handler** - `b7d8724` (feat)
2. **Task 2: Create /admin command handler and register in router** - `1ce7cca` (feat)

**Plan metadata:** _(docs commit follows)_

## Files Created/Modified

- `delivery/poster.py` - `_send_message` extended with `reply_markup` param; `post_article` builds inline keyboard with reaction buttons
- `bot/router.py` - Added `import time`, reaction callback handler using `split(':', 2)`, `/admin` in COMMAND_MAP, `admin` in imports
- `bot/commands/admin.py` - New file: owner-only /admin handler with active users (7d), deliveries/hour, Stars revenue, recent errors

## Decisions Made

- `_send_message` receives reply_markup as optional parameter (not a new wrapper function) — minimal surface change; followup "why this matters" message correctly omits it by not passing reply_markup
- `data.split(":", 2)` limits to 3 parts — article URLs containing colons (e.g. `https://...`) parse correctly (per RESEARCH.md Pitfall 1)
- Reaction handler calls `tg.answer_callback_query` with toast text then `return` — avoids the generic empty-text call at the end of `_handle_callback` being issued a second time
- `os.environ.get("OWNER_USER_ID")` (not subscript access) — graceful when env var is absent, returns "Not authorized." without raising KeyError

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. Reaction buttons wire directly to article URLs from the delivery pipeline. Admin queries target live DB tables created in Plan 01. No mock data or placeholder text used.

## Self-Check

- [x] delivery/poster.py created/modified - verified
- [x] bot/router.py created/modified - verified
- [x] bot/commands/admin.py created - verified
- [x] Commit b7d8724 exists - verified
- [x] Commit 1ce7cca exists - verified
