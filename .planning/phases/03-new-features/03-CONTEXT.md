# Phase 3: New Features - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Add three capabilities to the Telegram News Bot:
1. `/admin` command — bot owner sees health metrics at a glance
2. Article reaction buttons — users tap 👍/👎 on delivered articles; reactions stored per user per article
3. Delivery tracking — pipeline records sent/failed outcome per article per user in DB

This phase does NOT add search, filtering, bookmarking, or any other new user-facing capability beyond what's listed.

</domain>

<decisions>
## Implementation Decisions

### Admin Command (FEAT-01)

- **D-01:** Owner identified via `OWNER_USER_ID` env var. The `/admin` command silently ignores (or returns a generic error to) any caller whose `user_id` does not match.
- **D-02:** "Active users" = users with at least one row in `digest_history` where `sent_at > now - 7 days`. Reflects genuinely engaged users.
- **D-03:** "Recent errors" sourced from a new `delivery_errors` table. Delivery pipeline inserts a row on each caught exception: `(theme_id, theme_type, error_msg, occurred_at)`. Admin shows the last 5 rows.
- **D-04:** Output is a single Markdown message with emoji section headers: 📊 Active Users, ⚡ Deliveries/hour, ⚠️ Recent Errors, 💰 Revenue. Fast — one `sendMessage` call.
- **D-05:** "Deliveries/hour" = count of rows in `digest_history` where `sent_at > now - 1 hour`.
- **D-06:** "Payment revenue" = `SUM(stars_paid)` from `users` table (already populated by payment handler).

### Reaction Buttons (FEAT-02)

- **D-07:** Reaction buttons (👍/👎) added to each article message via `reply_markup` (inline keyboard). `delivery/poster.py` sends articles — it must add `reply_markup` to the sendMessage call.
- **D-08:** `bot/telegram.py` already supports `reply_markup` in `send_message`. `delivery/poster.py` has its own local `_send_message` — it should be refactored to use `bot/telegram.py` (or have `reply_markup` added to its local function).
- **D-09:** Callback data format: `reaction:<reaction>:<article_url>` (e.g., `reaction:up:https://...`). Router handles `data.startswith("reaction:")`.
- **D-10:** On tap: store reaction in DB via `INSERT OR REPLACE` (last reaction wins — users can change), then call `answerCallbackQuery` with a brief toast (e.g., "👍 Noted!").
- **D-11:** Reactions table: `article_reactions(user_id, article_url, reaction TEXT, reacted_at INTEGER)` with `PRIMARY KEY (user_id, article_url)`. `reaction` is `'up'` or `'down'`.
- **D-12:** Article identified by URL (`article_url`). Consistent with `posted_articles` dedup table.

### Delivery Tracking (FEAT-03)

- **D-13:** New table `delivery_log(id, user_id, article_url, status TEXT, sent_at INTEGER)`. `status` is `'sent'` or `'failed'` only.
- **D-14:** `delivery/main.py` inner try/except around `post_article(...)` already exists. On success → insert `(user_id, article_url, 'sent', now_ts)`. On exception → insert `(user_id, article_url, 'failed', now_ts)`.
- **D-15:** New table `delivery_errors(id, theme_id, theme_type, error_msg TEXT, occurred_at INTEGER)`. Populated from the outer `except Exception as e` block in `delivery/main.py` (theme-level errors). Used by `/admin` recent errors display.

### Claude's Discretion

- Exact SQL DDL for new tables (`delivery_log`, `delivery_errors`, `article_reactions`) — follow existing `schema.sql` conventions (INTEGER PRIMARY KEY AUTOINCREMENT, NOT NULL, REFERENCES, CREATE INDEX).
- Whether to batch-insert delivery_log rows per theme or insert per-article — choose whichever keeps main.py clean.
- Toast message text for reactions — keep short and emoji-friendly.
- How `/admin` handles edge cases (no deliveries yet, no errors) — show "None" or "0" gracefully.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Schema & Data Layer
- `db/schema.sql` — All existing table definitions; new tables must follow these conventions
- `db/client.py` — execute() and execute_many() API used for all DB calls

### Delivery Pipeline
- `delivery/main.py` — Orchestrator; delivery_log and delivery_errors inserts go here
- `delivery/poster.py` — post_article() function; reaction buttons (reply_markup) added here

### Bot Infrastructure
- `bot/telegram.py` — send_message() already supports reply_markup; answer_callback_query() used for reaction toasts
- `bot/router.py` — _handle_callback() dispatches by data prefix; add `reaction:` case here
- `bot/commands/` — Existing command handler pattern; /admin added here

### Requirements
- `.planning/REQUIREMENTS.md` — FEAT-01, FEAT-02, FEAT-03 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `bot/telegram.py send_message(reply_markup=...)`: Already supports inline keyboards — use this for reaction buttons
- `bot/telegram.py answer_callback_query(text=...)`: Use for reaction toast notifications
- `bot/router.py _handle_callback()`: All inline button callbacks route here — add `reaction:` prefix case
- `db/client.py execute_many()`: Use for batch delivery_log inserts

### Established Patterns
- Command handlers live in `bot/commands/<name>.py` with a `handle(message)` function — follow for `/admin`
- All DB queries use `db.execute(sql, params)` — no ORMs
- Error handling: bare `except Exception as e` with `logger.error(...)` — match this style
- Callback data uses colon-separated prefixes: `themes:add:type:id`, `pay:tier`, etc.

### Integration Points
- `delivery/main.py` inner loop (around `post_article`) — insert delivery_log rows here
- `delivery/main.py` outer `except Exception as e` (theme-level) — insert delivery_errors rows here
- `delivery/poster.py post_article()` — add `reply_markup` with reaction buttons to the sendMessage call
- `bot/router.py _handle_callback()` — add `reaction:` case to dispatch to new reaction handler
- `db/schema.sql` — add 3 new CREATE TABLE statements

</code_context>

<specifics>
## Specific Ideas

- Reaction callback data: `reaction:up:<url>` and `reaction:down:<url>` (matches existing `<prefix>:<value>` pattern in router.py)
- Toast text suggestion: "👍 Noted!" / "👎 Noted!" (brief, fits Telegram toast limit)
- `/admin` output structure:
  ```
  🤖 *Bot Status*

  📊 *Active users (7d):* 42
  ⚡ *Deliveries (last hour):* 8
  💰 *Revenue (total Stars):* 1,340

  ⚠️ *Recent errors:*
  • [2026-03-25 14:02] theme_id=3 — Connection timeout
  • [2026-03-25 13:45] theme_id=7 — Theme not found
  ```

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-new-features*
*Context gathered: 2026-03-25*
