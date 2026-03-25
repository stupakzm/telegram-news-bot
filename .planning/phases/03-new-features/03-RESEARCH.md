# Phase 3: New Features - Research

**Researched:** 2026-03-25
**Domain:** Telegram bot feature expansion (admin metrics, user reactions, delivery tracking)
**Confidence:** HIGH

## Summary

Phase 3 adds three core user-facing and admin capabilities to the Telegram News Bot:

1. **`/admin` command** — Bot owner accesses health metrics (active users, deliveries/hour, recent errors, total revenue) in a single Markdown message
2. **Article reaction buttons** — Users tap 👍/👎 inline buttons on delivered articles; reactions stored per user per article with ability to change
3. **Delivery tracking** — Pipeline records sent/failed status for each article delivered to each user, enabling post-delivery analytics

All three features integrate seamlessly into the existing codebase using established patterns: command handlers in `bot/commands/`, callback routing in `bot/router.py`, and database operations via `db.client`.

**Primary recommendation:** Follow the locked decisions from CONTEXT.md exactly. All three features have dependencies on new DB tables that must be created first via schema migration. The delivery_log and delivery_errors tables require inserts in `delivery/main.py`, while the article_reactions table is updated by a new reaction callback handler in `bot/router.py`.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Admin Command (FEAT-01):**
- Owner identified via `OWNER_USER_ID` env var; command silently ignores non-owner calls
- "Active users" = 7-day rolling window (users with `sent_at > now - 7 days` in digest_history)
- "Recent errors" sourced from new `delivery_errors` table; show last 5 rows
- Output is single Markdown message with emoji headers (📊, ⚡, ⚠️, 💰)
- "Deliveries/hour" = count of rows in `digest_history` where `sent_at > now - 1 hour`
- "Payment revenue" = SUM of `stars_paid` from `users` table

**Reaction Buttons (FEAT-02):**
- Buttons (👍/👎) added via `reply_markup` to article sendMessage calls
- `delivery/poster.py` must add `reply_markup`; `bot/telegram.py` already supports this parameter
- Callback data format: `reaction:<reaction>:<article_url>` (e.g., `reaction:up:https://...`)
- On tap: INSERT OR REPLACE (last reaction wins), then `answerCallbackQuery` with toast
- Reactions table: `article_reactions(user_id, article_url, reaction TEXT, reacted_at INTEGER)` with PRIMARY KEY `(user_id, article_url)`
- Article identified by URL (consistent with `posted_articles` dedup table)

**Delivery Tracking (FEAT-03):**
- New table `delivery_log(id, user_id, article_url, status TEXT, sent_at INTEGER)`; status is 'sent' or 'failed'
- `delivery/main.py` inner try/except around `post_article()`: on success insert 'sent', on exception insert 'failed'
- New table `delivery_errors(id, theme_id, theme_type, error_msg TEXT, occurred_at INTEGER)`
- Populated from outer `except Exception as e` block in `delivery/main.py` (theme-level errors)
- Used by `/admin` for recent errors display

### Claude's Discretion

- Exact SQL DDL for new tables — follow `schema.sql` conventions (INTEGER PRIMARY KEY AUTOINCREMENT, NOT NULL, REFERENCES, CREATE INDEX)
- Batch vs. per-article insert for delivery_log — choose whichever keeps main.py clean
- Toast message text for reactions (e.g., "👍 Noted!") — keep short and emoji-friendly
- `/admin` edge case handling (no deliveries yet, no errors) — show "None" or "0" gracefully

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FEAT-01 | `/admin` command (bot owner only) shows active users (7d), deliveries/hour, recent errors (last 5 from DB), total Stars revenue | See "Admin Command Pattern" and "Database Schema" sections; OWNER_USER_ID env var validation; queries on digest_history and delivery_errors tables |
| FEAT-02 | Article messages include 👍/👎 reaction buttons; reactions stored per user per article with ability to change | See "Reaction Buttons Pattern" and "Callback Handler Integration" sections; INSERT OR REPLACE in article_reactions table; callback routing in bot/router.py |
| FEAT-03 | Delivery pipeline tracks sent/failed status per article per user in DB | See "Delivery Tracking Pattern" and "Pipeline Integration" sections; inserts in delivery_log and delivery_errors tables from delivery/main.py |

</phase_requirements>

## Standard Stack

### Core Dependencies (Already Installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.13+ | Language runtime | Project standard |
| requests | current | HTTP API calls (Telegram, Turso) | Existing dependency |
| dotenv | current | Environment variable loading | Existing dependency |

### No New Dependencies

This phase uses only the existing project stack. All features are built with:
- Python stdlib (json, time, datetime, logging)
- Existing `bot/telegram.py` API (send_message with reply_markup, answer_callback_query)
- Existing `db/client.py` API (execute, execute_many)
- Existing command handler pattern

**Installation:** No new packages required.

**Version verification:** Phase 3 requires no new external dependencies. All code changes are in-project.

## Architecture Patterns

### Database Schema Pattern

**Existing conventions in `db/schema.sql`:**
- INTEGER PRIMARY KEY AUTOINCREMENT for auto-increment IDs
- INTEGER for Unix timestamps (seconds since epoch)
- TEXT for strings and JSON blobs
- NOT NULL constraints on required fields
- REFERENCES clauses for foreign keys
- CREATE INDEX for performance-critical queries

**New tables to add:**

```sql
-- Table 1: Delivery tracking per user per article
CREATE TABLE IF NOT EXISTS delivery_log(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    article_url TEXT NOT NULL,
    status TEXT NOT NULL,  -- 'sent' | 'failed'
    sent_at INTEGER NOT NULL
);

-- Index for efficient queries by user and time range
CREATE INDEX IF NOT EXISTS idx_delivery_log_user_time
    ON delivery_log(user_id, sent_at DESC);

-- Table 2: User reactions to articles
CREATE TABLE IF NOT EXISTS article_reactions(
    user_id INTEGER NOT NULL REFERENCES users(user_id),
    article_url TEXT NOT NULL,
    reaction TEXT NOT NULL,  -- 'up' | 'down'
    reacted_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, article_url)
);

-- Index for efficient queries by reaction type
CREATE INDEX IF NOT EXISTS idx_article_reactions_reaction
    ON article_reactions(reaction);

-- Table 3: Theme-level delivery errors (for admin display)
CREATE TABLE IF NOT EXISTS delivery_errors(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme_id INTEGER NOT NULL,
    theme_type TEXT NOT NULL,  -- 'default' | 'custom'
    error_msg TEXT NOT NULL,
    occurred_at INTEGER NOT NULL
);

-- Index for efficient time-range queries
CREATE INDEX IF NOT EXISTS idx_delivery_errors_time
    ON delivery_errors(occurred_at DESC);
```

### Command Handler Pattern

**Established pattern from existing handlers (`bot/commands/*.py`):**

```python
import db.client as db
import bot.telegram as tg

def handle(message: dict) -> None:
    """Handle /command. Message dict has 'from' and 'chat' keys."""
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    # 1. Check authorization (e.g., OWNER_USER_ID for /admin)
    # 2. Query database as needed
    # 3. Format response text
    # 4. Send message(s) via tg.send_message()
```

**For `/admin` command:**
- File: `bot/commands/admin.py`
- Authorization: Check `user_id` against `OWNER_USER_ID` env var; silently return if not owner
- Queries:
  - Active users (7d): `SELECT COUNT(DISTINCT user_id) FROM digest_history WHERE sent_at > now_ts - 7*24*3600`
  - Deliveries/hour: `SELECT COUNT(*) FROM digest_history WHERE sent_at > now_ts - 3600`
  - Revenue: `SELECT SUM(stars_paid) FROM users`
  - Recent errors: `SELECT theme_id, theme_type, error_msg, occurred_at FROM delivery_errors ORDER BY occurred_at DESC LIMIT 5`
- Response: Single Markdown message formatted with emoji section headers

### Callback Handler Integration Pattern

**Established pattern in `bot/router.py` _handle_callback():**

```python
def _handle_callback(callback_query: dict) -> None:
    data = callback_query.get("data", "")
    user_id = callback_query["from"]["id"]

    if data.startswith("reaction:"):
        reaction, url = data.split(":", 2)[1:3]
        # Insert/replace reaction in DB
        # Call tg.answer_callback_query() with toast
```

**For reaction buttons:**
- Callback data: `reaction:<up|down>:<article_url>`
- Handler extracts reaction ('up'/'down') and URL
- Database: `INSERT OR REPLACE INTO article_reactions (user_id, article_url, reaction, reacted_at) VALUES (?, ?, ?, ?)`
- Toast: Short emoji-friendly message via `tg.answer_callback_query(callback_query["id"], text="👍 Noted!")`

### Delivery Pipeline Integration Pattern

**Location: `delivery/main.py` around post_article() calls**

**Existing code structure (lines 137-146):**
```python
for user in users:
    user_articles = articles[:user["effective_articles_per_theme"]]
    for article in user_articles:
        try:
            post_article(user_id=user["user_id"], article=article)
            all_posted_urls.append(article["url"])
            articles_sent += 1
            time.sleep(0.1)  # avoid Telegram flood limits
        except Exception as e:
            logger.error("Failed to post to user %d: %s", user["user_id"], e)
```

**To add delivery_log inserts:**
- Maintain list of `(sql, args)` tuples for delivery_log rows
- After inner try/except succeeds: append `("INSERT INTO delivery_log ...", [user_id, url, 'sent', now_ts])`
- After inner except catches exception: append `("INSERT INTO delivery_log ...", [user_id, url, 'failed', now_ts])`
- Batch insert all rows together via `db.execute_many()` after all users processed

**To add delivery_errors inserts:**
- Outer `except Exception as e` block (lines 148-151) already catches theme-level errors
- Insert into delivery_errors: `("INSERT INTO delivery_errors (theme_id, theme_type, error_msg, occurred_at) VALUES (?, ?, ?, ?)", [theme_id, theme_type, str(e), now_ts])`

### Reaction Button in Poster Pattern

**Location: `delivery/poster.py` in _send_message() and post_article()**

**Current code (lines 37-48):**
```python
def post_article(user_id: int, article: dict) -> None:
    text = format_post(article)
    result = _send_message(chat_id=user_id, text=text)

    if article.get("is_important") and article.get("importance_detail"):
        followup = ...
        _send_message(chat_id=user_id, text=followup, reply_to_message_id=...)
```

**To add reaction buttons:**
- Build inline keyboard with two buttons: 👍 and 👎
- Generate callback_data: `f"reaction:up:{article['url']}"` and `f"reaction:down:{article['url']}"`
- Pass `reply_markup` dict to _send_message():
  ```python
  reply_markup = {
      "inline_keyboard": [[
          {"text": "👍", "callback_data": f"reaction:up:{article['url']}"},
          {"text": "👎", "callback_data": f"reaction:down:{article['url']}"}
      ]]
  }
  ```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| **Admin authorization** | Custom user whitelist in code | `OWNER_USER_ID` env var with string comparison | Single source of truth; allows env-based deployment variance |
| **User reaction storage** | In-memory cache or separate API | `article_reactions` table with PRIMARY KEY (user_id, article_url) | INSERT OR REPLACE is atomic; survives bot restart; queryable for analytics |
| **Delivery audit trail** | Sparse logging only | Dedicated `delivery_log` and `delivery_errors` tables | Enables post-delivery analytics (conversion, failure patterns); queryable by /admin; complies with observability requirements |
| **Callback routing** | New if/elif chain in _handle_callback | Existing pattern: `data.startswith("reaction:")` | Consistent with themes, addtheme, schedule callback patterns |
| **Inline button formatting** | Manual JSON construction | Existing `reply_markup` dict pattern in bot/telegram.py | Reuses proven Telegram API integration |

**Key insight:** The delivery pipeline and reaction system must be durable (survive restarts) and queryable (for admin dashboard and analytics). Database tables are the only appropriate storage mechanism for these use cases.

## Common Pitfalls

### Pitfall 1: URL Encoding in Callback Data

**What goes wrong:** Article URLs contain special characters (`?`, `&`, `=`, `#`). Callback data is passed as strings and split by delimiters. Naive parsing breaks if URL contains colons.

**Why it happens:** Callback data format `reaction:up:https://example.com` assumes colons only at fixed positions. If URL contains colons, split() on ":" gives wrong parts.

**How to avoid:** Use `data.split(":", 2)` to split into at most 3 parts: prefix, reaction, and URL. The `2` limit prevents splitting the URL.

**Warning signs:** Test with URLs containing query parameters or fragments; mock callback_query data in tests.

### Pitfall 2: Reaction Toast Text Length

**What goes wrong:** Toast messages have a Telegram API limit (~200 chars). Complex or multiline text fails silently or truncates.

**Why it happens:** `answer_callback_query` text parameter is user-facing and has constraints; developers often add context/explanation instead of keeping it brief.

**How to avoid:** Keep toast text short: "👍 Noted!" or "👎 Got it!" (under 50 chars). Test with real Telegram bot (not mocks) if possible.

**Warning signs:** Toast text longer than 1 line; includes explanation rather than acknowledgment.

### Pitfall 3: Delivery Log Timing Window Mismatch

**What goes wrong:** `/admin` queries `digest_history` for "deliveries last hour" but delivery_log records are inserted at different times (during main.py execution vs. when digest_history is written). Counts diverge.

**Why it happens:** `digest_history` is only written for monthly users (lines 191-207 of delivery/main.py), but `delivery_log` is written for ALL users. Query logic in `/admin` is ambiguous about which table to use.

**How to avoid:** Be explicit: `/admin` shows "deliveries last hour" as count from `digest_history` (monthly users only, matches D-05). If broader delivery metrics are needed later, use `delivery_log` with clear semantics. Test both paths (monthly user, free user) in unit tests.

**Warning signs:** Counts don't match when both users and monthly users are present; query logic mixes tables.

### Pitfall 4: INSERT OR REPLACE Not Idempotent If Reacted_at Unchanged

**What goes wrong:** `INSERT OR REPLACE` in article_reactions updates `reacted_at` on every tap, even if user taps the same reaction twice. This can trigger false "reaction updated" logs.

**Why it happens:** INSERT OR REPLACE always replaces the entire row, including the timestamp.

**How to avoid:** This is the desired behavior (update timestamp to reflect most recent interaction). Toast feedback ("👍 Noted!") is the same whether reaction is new or updated. No code change needed; this is correct.

**Warning signs:** Overthinking this — it's fine. The "last reaction wins" semantic is intentional.

### Pitfall 5: OWNER_USER_ID Not Set in Env

**What goes wrong:** `/admin` command runs, but OWNER_USER_ID is not in .env or environment. Admin tries to run command and gets a cryptic error (missing OWNER_USER_ID or NameError).

**Why it happens:** OWNER_USER_ID is a required env var for /admin to work. If not set, `os.environ["OWNER_USER_ID"]` raises KeyError.

**How to avoid:** Use `os.environ.get("OWNER_USER_ID")` with a fallback, or document OWNER_USER_ID as required in .env.example. Fail fast with a clear error message during startup if missing. Add env var validation to logging_config.py or main.py init.

**Warning signs:** /admin handler crashes on startup or first call; KeyError in logs.

## Code Examples

### Example 1: Admin Command Handler (`bot/commands/admin.py`)

**Source:** Established pattern from `bot/commands/history.py` and `bot/commands/start.py`

```python
import os
import time
import logging
import db.client as db
import bot.telegram as tg

logger = logging.getLogger(__name__)

def handle(message: dict) -> None:
    """Admin command: show bot health metrics. Owner only."""
    user_id = message["from"]["id"]
    chat_id = message["chat"]["id"]

    # Authorization check (D-01)
    owner_id = os.environ.get("OWNER_USER_ID")
    if not owner_id or user_id != int(owner_id):
        # Silent ignore (or generic error)
        tg.send_message(chat_id=chat_id, text="Not authorized.")
        return

    now_ts = int(time.time())

    # Active users (7d) (D-02, D-03)
    active_users_rows = db.execute(
        "SELECT COUNT(DISTINCT user_id) as count FROM digest_history WHERE sent_at > ?",
        [now_ts - 7 * 24 * 3600]
    )
    active_users = active_users_rows[0]["count"] if active_users_rows else 0

    # Deliveries last hour (D-05)
    deliveries_rows = db.execute(
        "SELECT COUNT(*) as count FROM digest_history WHERE sent_at > ?",
        [now_ts - 3600]
    )
    deliveries_hour = deliveries_rows[0]["count"] if deliveries_rows else 0

    # Revenue (D-06)
    revenue_rows = db.execute("SELECT SUM(stars_paid) as total FROM users")
    revenue = revenue_rows[0]["total"] if revenue_rows and revenue_rows[0]["total"] else 0

    # Recent errors (D-03)
    errors = db.execute(
        "SELECT theme_id, theme_type, error_msg, occurred_at FROM delivery_errors "
        "ORDER BY occurred_at DESC LIMIT 5"
    )

    error_lines = []
    if errors:
        for err in errors:
            err_dt = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(err["occurred_at"]))
            error_lines.append(
                f"• `[{err_dt}]` theme_id={err['theme_id']} — {err['error_msg']}"
            )
    else:
        error_lines = ["None"]

    # Format message (D-04)
    text = (
        f"🤖 *Bot Status*\n\n"
        f"📊 *Active users (7d):* {active_users}\n"
        f"⚡ *Deliveries (last hour):* {deliveries_hour}\n"
        f"💰 *Revenue (total Stars):* {revenue}\n\n"
        f"⚠️ *Recent errors:*\n" + "\n".join(error_lines)
    )

    tg.send_message(chat_id=chat_id, text=text)
```

### Example 2: Reaction Callback Handler (in `bot/router.py`)

**Source:** Established pattern from _handle_callback() (lines 23-56)

```python
# In bot/router.py _handle_callback(), add new case:

elif data.startswith("reaction:"):
    # Parse callback data: reaction:up:https://...
    parts = data.split(":", 2)
    if len(parts) >= 3:
        reaction = parts[1]  # 'up' or 'down'
        url = parts[2]

        # Store reaction (D-10, D-11)
        db.execute_many([
            (
                "INSERT OR REPLACE INTO article_reactions (user_id, article_url, reaction, reacted_at) "
                "VALUES (?, ?, ?, ?)",
                [user_id, url, reaction, int(time.time())]
            )
        ])

        # Toast feedback (D-10)
        emoji = "👍" if reaction == "up" else "👎"
        tg.answer_callback_query(
            callback_query["id"],
            text=f"{emoji} Noted!"
        )
```

### Example 3: Delivery Log Insert (in `delivery/main.py`)

**Source:** Existing pattern from posted_articles insert (lines 176-181)

```python
# Track delivery outcomes for each user/article pair
delivery_log_statements = []

for user in users:
    user_articles = articles[:user["effective_articles_per_theme"]]
    for article in user_articles:
        try:
            post_article(user_id=user["user_id"], article=article)
            all_posted_urls.append(article["url"])
            articles_sent += 1
            time.sleep(0.1)

            # Insert success into delivery_log (D-13)
            delivery_log_statements.append((
                "INSERT INTO delivery_log (user_id, article_url, status, sent_at) VALUES (?, ?, ?, ?)",
                [user["user_id"], article["url"], "sent", now_ts]
            ))
        except Exception as e:
            logger.error("Failed to post to user %d: %s", user["user_id"], e)

            # Insert failure into delivery_log (D-13)
            delivery_log_statements.append((
                "INSERT INTO delivery_log (user_id, article_url, status, sent_at) VALUES (?, ?, ?, ?)",
                [user["user_id"], article["url"], "failed", now_ts]
            ))

# Batch insert all delivery_log rows after theme completes
if delivery_log_statements:
    try:
        db.execute_many(delivery_log_statements)
    except Exception as e:
        logger.error("Failed to write delivery_log for theme (%s, %d): %s", theme_type, theme_id, e)
```

### Example 4: Reaction Buttons in Poster (in `delivery/poster.py`)

**Source:** Existing pattern from _send_message() and format_post()

```python
def post_article(user_id: int, article: dict) -> None:
    """Send one article to a user's DM with reaction buttons. Sends a followup reply if important."""
    text = format_post(article)

    # Build reaction button keyboard (D-07, D-09)
    reply_markup = {
        "inline_keyboard": [[
            {"text": "👍", "callback_data": f"reaction:up:{article['url']}"},
            {"text": "👎", "callback_data": f"reaction:down:{article['url']}"}
        ]]
    }

    result = _send_message(chat_id=user_id, text=text, reply_markup=reply_markup)

    if article.get("is_important") and article.get("importance_detail"):
        followup = f"🧵 *Why this matters:*\n{article['importance_detail']}"
        _send_message(
            chat_id=user_id,
            text=followup,
            reply_to_message_id=result["message_id"],
        )
```

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13+ | All features | ✓ | Current (project standard) | — |
| Turso SQLite | Database operations | ✓ | Deployed via TURSO_URL | — |
| Telegram Bot API | Message sending, buttons | ✓ | Live service | — |
| OWNER_USER_ID env var | /admin command authorization | ✓ (set via .env) | User-provided | Fail with clear error if missing |

**Missing dependencies with no fallback:**
- OWNER_USER_ID env var must be set for /admin to work; no fallback behavior (error expected if missing)

**Missing dependencies with fallback:**
- None identified

## Validation Architecture

**nyquist_validation in .planning/config.json is `false`; validation section SKIPPED per configuration.**

## Open Questions

1. **Delivery log batch timing** — Should delivery_log rows be inserted per-article (within inner loop) or batched per-theme (after all users for theme complete)?
   - What we know: `delivery/main.py` already batches digest_history inserts per-theme (lines 190-207); batch is cleaner and fewer round-trips
   - What's unclear: Whether per-article inserts are needed for granular timing or if batch is acceptable
   - Recommendation: Use batch inserts per-theme, matching digest_history pattern. If granular timing is needed later, it can be added with schema migration.

2. **Reaction URL encoding edge cases** — How should callback data handle URLs with special characters or very long URLs?
   - What we know: Telegram callback_data limit is typically 64 bytes; long URLs may exceed this
   - What's unclear: Whether very long URLs are possible in this project's article corpus
   - Recommendation: Use `split(":", 2)` to safely extract URL. If URLs are too long, consider storing reactions by article_id (database reference) instead of URL. This can be added in future optimization.

3. **Admin command timezone** — Should timestamps in recent errors display use user timezone, server timezone, or always UTC?
   - What we know: Timestamps in the codebase are Unix seconds (UTC); datetime display uses `time.gmtime()` for UTC
   - What's unclear: User's timezone preference (not currently stored per user)
   - Recommendation: Display all admin metrics in UTC with "UTC" label. Users can infer local time from their own timezone. Matches existing PROJECT.md output format.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sparse delivery logging | Structured delivery_log table | Phase 3 (this phase) | Enables post-delivery analytics; audit trail |
| No admin dashboard | `/admin` command with Markdown output | Phase 3 (this phase) | Owner can monitor health without external tools |
| No user interaction with articles | Reaction buttons with persistence | Phase 3 (this phase) | Enables engagement metrics; user feedback loop |

**Deprecated/outdated:**
- Bare exception handling (no delivery tracking) — Phase 3 adds structured delivery_log and delivery_errors tables for observability

## Sources

### Primary (HIGH confidence)
- **CONTEXT.md** (`.planning/phases/03-new-features/03-CONTEXT.md`) — All locked decisions and code integration points
- **Existing codebase** (`delivery/main.py`, `bot/router.py`, `bot/telegram.py`, `bot/commands/*`) — Established patterns verified by reading actual code
- **REQUIREMENTS.md** (`.planning/REQUIREMENTS.md`) — FEAT-01, FEAT-02, FEAT-03 requirement IDs and acceptance criteria

### Secondary (MEDIUM confidence)
- **PROJECT.md** (`.planning/PROJECT.md`) — Context on constraints, tech stack, no-framework decision
- **schema.sql** (`db/schema.sql`) — Existing table conventions and foreign key patterns
- **db/client.py** (`db/client.py`) — Database API (execute, execute_many) verified by reading code

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — No new external dependencies; only stdlib and existing project patterns
- Architecture: HIGH — All patterns extracted from existing codebase and CONTEXT.md decisions
- Pitfalls: MEDIUM — Identified based on common callback/async patterns; would benefit from implementation testing

**Research date:** 2026-03-25
**Valid until:** 2026-04-25 (30 days; stable domain with no external API changes expected)

**Research approach:**
- Read all mandatory context files (CONTEXT.md, REQUIREMENTS.md, STATE.md)
- Read core codebase files to understand established patterns (bot/router.py, delivery/main.py, bot/commands/*, db/schema.sql)
- Verified no new external dependencies are needed
- Cross-checked CONTEXT.md decisions against existing code patterns to ensure consistency
- Identified integration points and pitfalls based on actual code structure
