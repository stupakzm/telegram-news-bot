---
phase: 03-new-features
verified: 2026-03-25T00:00:00Z
status: passed
score: 9/9 must-haves verified
re_verification: false
gaps: []
human_verification:
  - test: "Tap thumbs-up button on a delivered article in Telegram"
    expected: "Toast notification shows '👍 Noted!' and reaction is stored in article_reactions"
    why_human: "Requires live bot session and Telegram client to verify toast display and callback delivery"
  - test: "Run /admin as the bot owner in Telegram"
    expected: "Bot replies with formatted dashboard showing active users (7d), deliveries/hour, revenue, and recent errors"
    why_human: "Requires live Turso credentials and a populated DB to verify real data is returned and Markdown renders"
  - test: "Run /admin as a non-owner Telegram user"
    expected: "Bot replies 'Not authorized.' and nothing else"
    why_human: "Requires live bot session; can't simulate Telegram user_id comparison against env var in code-only check"
---

# Phase 3: New Features Verification Report

**Phase Goal:** Add the most-wanted capabilities: admin visibility, user feedback on articles, and delivery tracking.
**Verified:** 2026-03-25
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Delivery pipeline records 'sent' status per article per user on success | VERIFIED | `delivery/main.py` line 145-148: appends `(INSERT INTO delivery_log ... "sent" ...)` to accumulator in inner try block after successful `post_article()` call |
| 2 | Delivery pipeline records 'failed' status per article per user on exception | VERIFIED | `delivery/main.py` line 152-155: appends `(INSERT INTO delivery_log ... "failed" ...)` to accumulator in inner except block |
| 3 | Theme-level errors are captured in delivery_errors table | VERIFIED | `delivery/main.py` lines 161-167: outer except block calls `db.execute_many` with `INSERT INTO delivery_errors`, wrapped in its own try/except |
| 4 | Three new tables exist in schema: delivery_log, article_reactions, delivery_errors | VERIFIED | `db/schema.sql` lines 79-110: all three `CREATE TABLE IF NOT EXISTS` DDL blocks with correct columns, constraints, and indexes |
| 5 | Delivered articles show thumbs up and thumbs down reaction buttons | VERIFIED | `delivery/poster.py` lines 42-47: `post_article()` builds `reply_markup` with `inline_keyboard` containing two buttons, passed to `_send_message()` |
| 6 | Tapping a reaction button stores the reaction and shows a toast | VERIFIED | `bot/router.py` lines 58-72: `elif data.startswith("reaction:")` handler parses callback, executes `INSERT OR REPLACE INTO article_reactions`, calls `tg.answer_callback_query` with emoji toast, returns |
| 7 | Users can change their reaction (last reaction wins) | VERIFIED | `bot/router.py` line 64-69: uses `INSERT OR REPLACE INTO article_reactions` on composite PK `(user_id, article_url)` — overwrites any prior reaction |
| 8 | Bot owner can run /admin and see active users, deliveries/hour, errors, revenue | VERIFIED | `bot/commands/admin.py`: queries `digest_history` for active users (7d) and deliveries/hour, `users` for revenue, `delivery_errors` for last 5 errors; formats Markdown dashboard |
| 9 | Non-owner users get 'Not authorized.' when running /admin | VERIFIED | `bot/commands/admin.py` lines 16-19: `os.environ.get("OWNER_USER_ID")` compared to `user_id`; mismatch or missing env var returns `"Not authorized."` immediately |

**Score:** 9/9 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `db/schema.sql` | DDL for delivery_log, article_reactions, delivery_errors | VERIFIED | All three tables present (lines 79-110) with correct columns, FK references, composite PK on article_reactions, and three indexes |
| `delivery/main.py` | delivery_log and delivery_errors inserts in pipeline | VERIFIED | Accumulator initialized line 86, `"sent"` appended line 145, `"failed"` appended line 152, batch flush lines 200-204, delivery_errors insert lines 161-167 |
| `delivery/poster.py` | Reaction buttons on article messages | VERIFIED | `reply_markup` parameter added to `_send_message` (line 11), inline keyboard built in `post_article` (lines 42-47), passed on main article message only |
| `bot/router.py` | Reaction callback handler + /admin routing | VERIFIED | `reaction:` handler lines 58-72; `/admin` in COMMAND_MAP line 21; `admin` in import line 4 |
| `bot/commands/admin.py` | Admin command handler with `handle` export | VERIFIED | File exists, 67 lines, substantive implementation with 4 DB queries, authorization check, Markdown formatting |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `delivery/main.py` | `db.client.execute_many` | batch insert of delivery_log rows after theme loop | WIRED | `db.execute_many(delivery_log_statements)` at line 202, guarded by `if delivery_log_statements:` |
| `delivery/main.py` | `delivery_errors` table | INSERT in outer except block | WIRED | `db.execute_many([(INSERT INTO delivery_errors...)])` at line 162, in `except Exception as e` block (line 157) |
| `delivery/poster.py` | `bot/router.py` | callback_data format `reaction:up:<url>` and `reaction:down:<url>` | WIRED | poster.py lines 44-45 produce `f"reaction:up:{article['url']}"` and `f"reaction:down:{article['url']}"` matching router.py's `data.startswith("reaction:")` check |
| `bot/router.py` | `article_reactions` table | INSERT OR REPLACE into article_reactions | WIRED | `db.execute_many([(INSERT OR REPLACE INTO article_reactions ...)])` at router.py lines 64-69 |
| `bot/commands/admin.py` | `delivery_errors` table | SELECT from delivery_errors ORDER BY occurred_at DESC LIMIT 5 | WIRED | `db.execute("SELECT theme_id, theme_type, error_msg, occurred_at FROM delivery_errors ORDER BY occurred_at DESC LIMIT 5")` at admin.py lines 43-45 |
| `bot/router.py` | `bot/commands/admin.py` | COMMAND_MAP /admin entry | WIRED | `"/admin": ("bot.commands.admin", "handle")` at router.py line 21; `admin` imported on line 4 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `delivery/main.py` | `delivery_log_statements` | Per-article success/failure in inner loop | Yes — appended from live `post_article()` call outcomes | FLOWING |
| `bot/router.py` (reaction handler) | `reaction`, `article_url` | `callback_query["data"]` parsed via `split(":", 2)` | Yes — from Telegram callback payload | FLOWING |
| `bot/commands/admin.py` | `active_users`, `deliveries_hour`, `revenue`, `errors` | Four `db.execute()` calls against live tables | Yes — real SQL queries with time-window args | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED — all new code requires live Telegram callbacks or live Turso DB to exercise. No standalone runnable entry points can be checked without external services. Human verification items cover these behaviors (see below).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| FEAT-01 | 03-02-PLAN.md | `/admin` command (bot owner only) shows active users, deliveries/hour, recent errors | SATISFIED | `bot/commands/admin.py` fully implements all metrics; `/admin` registered in COMMAND_MAP; authorization check present |
| FEAT-02 | 03-02-PLAN.md | Article messages include reaction buttons; reactions stored per user per article | SATISFIED | `delivery/poster.py` adds inline keyboard; `bot/router.py` handles callback with INSERT OR REPLACE; toast returned |
| FEAT-03 | 03-01-PLAN.md | Delivery pipeline tracks sent/failed status per article per user | SATISFIED | `delivery/main.py` accumulates delivery_log rows with 'sent'/'failed' status and batch-flushes after each theme loop |

No orphaned requirements detected. All three FEAT-01, FEAT-02, FEAT-03 are claimed by plans and implemented.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `bot/commands/admin.py` | 31-35 | Uses `digest_history` for deliveries/hour count, not `delivery_log` | Info | FEAT-03 created `delivery_log` as the canonical per-article delivery record. The /admin deliveries/hour metric queries `digest_history` instead, which records per-theme digests for monthly users only — not every article delivery. This means the deliveries/hour count undercounts actual deliveries on non-monthly tiers and does not use the new table. It still compiles and works; it is a metric accuracy issue, not a blocker. |

No TODO/FIXME/placeholder comments found. No empty return stubs. No hardcoded empty data flowing to user-visible output.

### Human Verification Required

#### 1. Reaction toast and storage

**Test:** Subscribe a test user to a theme, trigger a delivery, receive an article message in Telegram, tap the thumbs-up button.
**Expected:** A toast notification appears showing "👍 Noted!". Query `article_reactions` in Turso and confirm a row exists with the correct `user_id`, `article_url`, and `reaction = 'up'`.
**Why human:** Requires live bot token, Turso credentials, and a Telegram client. Toast display is Telegram-side behavior that cannot be verified from code alone.

#### 2. /admin dashboard content

**Test:** Set `OWNER_USER_ID` env var to your Telegram user_id, run the bot, send `/admin` in a DM.
**Expected:** Bot replies with a Markdown message containing all four sections: active users (7d), deliveries (last hour), revenue (total Stars), and recent errors. Values should reflect actual DB state.
**Why human:** Requires populated Turso DB and live bot session. Markdown rendering and metric accuracy must be confirmed visually.

#### 3. /admin authorization rejection

**Test:** Send `/admin` from a Telegram account whose user_id does not match `OWNER_USER_ID`.
**Expected:** Bot replies only with "Not authorized." — no other content, no error.
**Why human:** Requires two distinct Telegram accounts or a bot session without `OWNER_USER_ID` set.

### Gaps Summary

No blocking gaps. All nine observable truths are verified against the actual codebase. All five required artifacts exist, are substantive, and are wired to their data sources. All six key links are confirmed present.

One informational note: the `/admin` deliveries/hour metric queries `digest_history` (per-theme digest records, monthly users only) rather than the new `delivery_log` table (per-article per-user records across all tiers). This does not block any requirement — FEAT-01 specifies showing deliveries/hour and this value is non-zero — but the metric undercounts actual deliveries. This can be improved in a future phase without any schema changes.

Three items are routed to human verification: reaction toast display, /admin dashboard rendering with real data, and /admin authorization rejection with a non-owner account. These require live Telegram sessions and cannot be verified programmatically.

---

_Verified: 2026-03-25_
_Verifier: Claude (gsd-verifier)_
