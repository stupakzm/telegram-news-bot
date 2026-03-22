# Phase 2: Observability & Rate Limiting - Research

**Researched:** 2026-03-22
**Domain:** Python stdlib logging, in-memory rate limiting
**Confidence:** HIGH

## Summary

This phase replaces ad-hoc `print()` calls with Python's stdlib `logging` module and adds per-user command rate limiting. The entire implementation uses zero external dependencies -- Python's `logging` module and `collections`/`time` from stdlib are sufficient.

The codebase currently has 12 production `print()` calls (11 in `delivery/main.py`, 1 in `api/webhook.py`) plus several modules that use `logging.warning()` directly on the module instead of through a named logger. The changes are mechanical and well-scoped. The rate limiter is a straightforward sliding-window counter stored in a dict.

**Primary recommendation:** Create a centralized `bot/logging_config.py` module, migrate all print() to named loggers, add per-theme structured log entries in the delivery loop, and implement a pure-stdlib rate limiter in `bot/rate_limiter.py`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Create a centralized logging config module (e.g., `bot/logging_config.py`) that calls `logging.basicConfig()` once. Both `api/webhook.py` and `delivery/main.py` import and call it at startup.
- **D-02:** Log format: plain text with timestamp -- `%(asctime)s %(levelname)s %(name)s -- %(message)s`
- **D-03:** Every production module uses `logger = logging.getLogger(__name__)` at module level. No inline `import logging` inside functions or branches.
- **D-04:** Minimum log level: INFO. DEBUG is available but not shown by default.
- **D-05:** Migrate all `print()` calls in production runtime code: `delivery/main.py`, `api/webhook.py`. Do NOT migrate `db/init_db.py` or `db/seed_themes.py`.
- **D-06:** `bot/router.py` gets its inline `import logging` moved to module-level, plus `logger = logging.getLogger(__name__)`.
- **D-07:** Per-theme log entry emitted at INFO level includes: `theme_id`, `theme_type`, `theme_name`, `user_count`, `articles_fetched`, `articles_sent`, `status` (one of: `ok` / `no_articles` / `ai_empty` / `error`), and `error` message when status is `error`.
- **D-08:** Run summary emitted at INFO level at completion: `run complete: themes={N} users={N} articles_sent={N} errors={N} duration={N}s`. Replaces the current `print("[deliver] Done.")`.
- **D-09:** Status values for per-theme entries: `ok`, `no_articles`, `ai_empty`, `error`. Each is a distinct failure mode.
- **D-10:** `delivery/fetcher.py` already logs correctly; just needs module-level `logger = logging.getLogger(__name__)`.
- **D-11:** In-memory dict per process in a new `bot/rate_limiter.py` module, keyed by `user_id`. Zero external dependencies. Resets on worker restart.
- **D-12:** Sliding window -- store a list of command timestamps per user. Window: 5 commands per 60 seconds. On each command, evict timestamps older than 60s, then check count.
- **D-13:** Rate limiting applies to `/commands` only (text messages starting with `/`). Callback queries (inline button presses) are not rate-limited.
- **D-14:** User-facing message on limit hit: `"Slow down! You've sent too many commands. Try again in {X} seconds."` where X is seconds until the oldest command in the window expires.
- **D-15:** Rate check is applied in `bot/router.py`'s `handle_update()` before dispatching to command handlers.

### Claude's Discretion
- Exact module name for centralized logging config (`bot/logging_config.py` or `delivery/logging_config.py` -- pick what makes most sense given import structure)
- Whether to use `collections.deque` or plain `list` for per-user timestamp storage in the rate limiter
- Thread safety of the in-memory rate limiter (single-threaded WSGI worker is fine without locks)

### Deferred Ideas (OUT OF SCOPE)
- JSON structured log format for log aggregation (Datadog/CloudWatch) -- noted as v2 requirement INF-02
- Rate limiting callback queries -- could be added later if abuse is detected
- Startup env var validation -- v2 requirement INF-01
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-01 | All `print()` statements replaced with structured `logging.getLogger()` calls | Complete inventory of 12 print() calls across 2 files; 6 modules need `logger = logging.getLogger(__name__)` added; centralized config pattern documented |
| OBS-02 | Delivery runs emit structured log entries (theme_id, user_id, article count, status) | Delivery loop structure mapped; per-theme and run-summary log entry formats specified in D-07/D-08; insertion points identified |
| OBS-03 | Broken feed URLs surfaced in logs with enough context to diagnose | Already satisfied by `delivery/fetcher.py` line 41; only needs module-level logger migration per D-10 |
| SAFE-01 | Per-user command rate limiting (max 5 commands/minute, returns friendly message) | Sliding window algorithm documented; insertion point in `bot/router.py:handle_update()` mapped; stdlib-only implementation |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `logging` (stdlib) | Python 3.x | Structured logging with named loggers | Built-in, no dependencies, universally used in Python |
| `collections.deque` (stdlib) | Python 3.x | Per-user timestamp ring buffer for rate limiting | O(1) append and popleft; natural fit for sliding window |
| `time` (stdlib) | Python 3.x | Monotonic timestamps for rate limiter | `time.time()` sufficient for single-process use |
| `math.ceil` (stdlib) | Python 3.x | Computing "try again in X seconds" display value | Standard rounding-up |

### Supporting
No external dependencies needed. This phase is entirely stdlib.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `collections.deque` | Plain `list` | List requires manual slicing to evict old entries; deque with no maxlen is functionally equivalent but `.popleft()` is cleaner for eviction |
| `logging.basicConfig()` | `logging.config.dictConfig()` | dictConfig is more flexible but overkill for plain-text single-format setup; basicConfig is the right tool here |
| In-memory rate limiter | Redis-based rate limiter | Redis would survive restarts but adds a dependency explicitly out of scope per requirements |

## Architecture Patterns

### Recommended Module Structure
```
bot/
  logging_config.py    # NEW: centralized logging.basicConfig() call
  rate_limiter.py      # NEW: sliding-window rate limiter
  router.py            # MODIFIED: add rate limit check, fix inline import
  validation.py        # EXISTING: shared utility pattern to follow
```

### Pattern 1: Centralized Logging Config
**What:** A single module that configures the root logger once. Both entry points (`api/webhook.py` and `delivery/main.py`) call it at startup.
**When to use:** At application startup, before any logging calls.
**Recommendation:** Place in `bot/logging_config.py` because both `api/webhook.py` and `delivery/main.py` already import from `bot.*`. The `bot/` package is the shared foundation.
```python
# bot/logging_config.py
import logging

def setup():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    )
```

**Startup call pattern:**
```python
# At top of api/webhook.py and delivery/main.py, after dotenv:
from bot.logging_config import setup as setup_logging
setup_logging()
```

### Pattern 2: Module-Level Named Logger
**What:** Every production module declares `logger = logging.getLogger(__name__)` at module level and uses `logger.info()`, `logger.warning()`, etc.
**When to use:** In every production .py file that needs to log.
```python
# delivery/main.py (and all other production modules)
import logging
logger = logging.getLogger(__name__)

# Then use:
logger.info("run complete: themes=%d users=%d articles_sent=%d errors=%d duration=%.1fs",
            theme_count, user_count, articles_sent, error_count, duration)
```

### Pattern 3: Sliding Window Rate Limiter
**What:** In-memory dict mapping `user_id` to a `deque` of timestamps. On each command, evict expired entries, then check if count exceeds limit.
**When to use:** Before command dispatch in `bot/router.py`.
```python
# bot/rate_limiter.py
import time
from collections import deque
from math import ceil

_user_timestamps: dict[int, deque] = {}
MAX_COMMANDS = 5
WINDOW_SECONDS = 60

def check_rate_limit(user_id: int) -> tuple[bool, int]:
    """Check if user is rate-limited.
    Returns (allowed: bool, retry_after: int seconds).
    """
    now = time.time()
    timestamps = _user_timestamps.setdefault(user_id, deque())

    # Evict expired entries
    while timestamps and timestamps[0] < now - WINDOW_SECONDS:
        timestamps.popleft()

    if len(timestamps) >= MAX_COMMANDS:
        retry_after = ceil(WINDOW_SECONDS - (now - timestamps[0]))
        return False, max(retry_after, 1)

    timestamps.append(now)
    return True, 0
```

### Pattern 4: Per-Theme Structured Log Entry
**What:** A single `logger.info()` call with keyword-style values for each theme processed during delivery.
**When to use:** Inside the delivery loop, after processing each theme.
```python
logger.info(
    "theme_id=%d theme_type=%s theme_name=%s user_count=%d "
    "articles_fetched=%d articles_sent=%d status=%s",
    theme_id, theme_type, theme_name, user_count,
    articles_fetched, articles_sent, status
)
# On error, append: error=%s
```

### Anti-Patterns to Avoid
- **Inline `import logging` inside functions:** Creates confusion about which logger is used. Always use module-level `logger = logging.getLogger(__name__)`.
- **Using `logging.info()` (root logger) instead of `logger.info()` (named logger):** Named loggers enable per-module filtering and make log source immediately clear in output.
- **f-strings in logging calls:** Use %-style format strings (`logger.info("x=%s", x)` not `logger.info(f"x={x}")`). This is both the project's established pattern AND avoids formatting cost when the log level is filtered out.
- **Catching exceptions and only logging the message:** When logging errors in except blocks, include the exception with `logger.error("...: %s", e)` -- the project already follows this pattern consistently.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Log configuration | Custom log handler setup | `logging.basicConfig()` | Handles stream setup, formatting, level filtering in one call |
| Log formatting | Manual string building for log entries | `logging.Formatter` via basicConfig format param | Consistent timestamps, levels, logger names |
| Sliding window eviction | Manual list slicing with index tracking | `collections.deque` with `.popleft()` | O(1) eviction from left side; cleaner than `while list and list[0] < cutoff: list.pop(0)` |

**Key insight:** This phase is entirely stdlib. There is nothing to install and nothing that warrants a third-party library.

## Common Pitfalls

### Pitfall 1: basicConfig Called Too Late
**What goes wrong:** `logging.basicConfig()` is a no-op if the root logger already has handlers. If any module calls `logging.warning()` before `setup()` runs, Python auto-configures with defaults and the explicit basicConfig is silently ignored.
**Why it happens:** Import-time side effects. The current `api/webhook.py` already calls `logging.warning()` at module level (line 18) during import.
**How to avoid:** Call `setup_logging()` BEFORE any import that triggers logging. In `api/webhook.py`, the `logging.warning("WEBHOOK_SECRET not set...")` runs at import time. The setup call must come before that import, or refactor the warning to be inside a function.
**Warning signs:** Log output uses default format (`WARNING:root:message`) instead of the configured format.

### Pitfall 2: Rate Limiter Memory Leak
**What goes wrong:** `_user_timestamps` dict grows unboundedly as new users interact with the bot.
**Why it happens:** Entries for users who stop using the bot are never cleaned up.
**How to avoid:** This is acceptable for the current scale (single-worker, restarts clear state). For a future concern, could add periodic cleanup of entries with empty deques. Not needed now.
**Warning signs:** Worker memory growing over weeks without restarts.

### Pitfall 3: Logging in webhook.py at Module Level
**What goes wrong:** `api/webhook.py` line 18 does `logging.warning("WEBHOOK_SECRET not set...")` at import time. This uses the root logger directly before any config runs.
**Why it happens:** The warning check runs when the module is imported by Vercel's serverless runner.
**How to avoid:** Either (a) move the warning inside the `handler` class or `do_POST`, or (b) ensure `setup_logging()` is called before this line executes. Option (b) is cleaner -- put `setup_logging()` call right after `load_dotenv()` and before the warning check.

### Pitfall 4: Delivery Loop Restructuring for Structured Logs
**What goes wrong:** The current delivery loop has multiple `continue` statements with different failure reasons (theme not found, no articles, AI empty, exception). Adding per-theme structured logging means each exit path needs to emit a log entry with the correct `status`.
**Why it happens:** The loop was written for print-debugging, not structured observability.
**How to avoid:** Restructure the inner loop to track status and emit exactly one structured log entry per theme at the end, regardless of which code path was taken. Use a `status` variable set at each exit point.

### Pitfall 5: Existing Tests Mock `logging.warning` at Module Level
**What goes wrong:** `tests/test_fetcher.py` and `tests/test_webhook.py` use `@patch("delivery.fetcher.logging.warning")` and `@patch("api.webhook.logging.warning")`. After migration to named loggers, these patches will target the wrong object.
**Why it happens:** Tests patch the module-level `logging` reference, but after the change, calls go through `logger` (a `Logger` instance), not the `logging` module.
**How to avoid:** Update test patches to target the logger instance: `@patch("delivery.fetcher.logger")` or use `@patch.object(fetcher_module.logger, "warning")`. This is a required follow-up when migrating to named loggers.

## Code Examples

### Complete Logging Config Module
```python
# bot/logging_config.py
import logging

_configured = False

def setup():
    """Configure root logger. Safe to call multiple times."""
    global _configured
    if _configured:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s -- %(message)s",
    )
    _configured = True
```

### Rate Limiter Integration in router.py
```python
# In bot/router.py handle_update(), after confirming it's a command:
from bot.rate_limiter import check_rate_limit

# Inside handle_update, after text.startswith("/") is confirmed:
user_id = message["from"]["id"]
allowed, retry_after = check_rate_limit(user_id)
if not allowed:
    tg.send_message(
        chat_id=message["chat"]["id"],
        text=f"Slow down! You've sent too many commands. Try again in {retry_after} seconds.",
    )
    return
```

### Delivery Per-Theme Structured Log Entry
```python
# Inside delivery/main.py run() loop, after processing each theme:
logger.info(
    "theme_id=%d theme_type=%s theme_name=%s user_count=%d "
    "articles_fetched=%d articles_sent=%d status=%s",
    theme["id"], theme_type, theme["name"], len(users),
    articles_fetched, articles_sent, status
)
# When status == "error":
logger.info(
    "theme_id=%d theme_type=%s theme_name=%s user_count=%d "
    "articles_fetched=%d articles_sent=%d status=%s error=%s",
    theme["id"], theme_type, theme["name"], len(users),
    0, 0, "error", str(e)
)
```

## Current Code Inventory

### print() Calls to Migrate (12 total, 2 files)

**delivery/main.py (11 calls):**
| Line | Current print() | Replacement Level | Status Value |
|------|----------------|-------------------|--------------|
| 52 | `print(f"[deliver] {date_str} Q{quarter}...")` | `logger.info` | N/A (run start) |
| 57 | `print("[deliver] No users due this hour.")` | `logger.info` | N/A (early return) |
| 63 | `print(f"[deliver] {len(groups)} unique theme(s)...")` | `logger.info` | N/A (run info) |
| 76 | `print(f"[deliver] Theme ... not found")` | `logger.warning` | N/A (per-theme: treat as error in structured log) |
| 89 | `print(f"[deliver] No new articles...")` | `logger.info` | `no_articles` |
| 93 | `print(f"[deliver] AI returned no summaries...")` | `logger.info` | `ai_empty` |
| 96 | `print(f"[deliver] Error fetching/summarizing...")` | `logger.error` | `error` |
| 122 | `print(f"[deliver] Failed to post to user...")` | `logger.error` | N/A (per-user failure within theme) |
| 156 | `print(f"[deliver] Failed to write history...")` | `logger.error` | N/A (digest write failure) |
| 160 | `print("[deliver] Done.")` | `logger.info` (becomes run summary D-08) | N/A |

**api/webhook.py (1 call):**
| Line | Current print() | Replacement Level |
|------|----------------|-------------------|
| 38 | `print(f"[webhook] error: {e}")` | `logger.error` |

### Modules Needing logger = logging.getLogger(__name__)

| Module | Current State | Action |
|--------|--------------|--------|
| `delivery/main.py` | No logging import at all; uses print() | Add `import logging` + `logger = getLogger(__name__)` |
| `delivery/fetcher.py` | `import logging` at top; uses `logging.warning()` directly | Add `logger = logging.getLogger(__name__)`; change calls to `logger.warning()` |
| `delivery/ai.py` | `import logging` at top; uses `logging.warning()` directly | Add `logger = logging.getLogger(__name__)`; change calls to `logger.warning()` |
| `delivery/scheduler.py` | `import logging` at top; uses `logging.warning()` directly | Add `logger = logging.getLogger(__name__)`; change calls to `logger.warning()` |
| `api/webhook.py` | `import logging` at top; uses `logging.warning()` directly | Add `logger = logging.getLogger(__name__)`; change calls to `logger.warning()` and `logger.error()` |
| `bot/router.py` | Inline `import logging` on line 70 | Move to module-level; add `logger = logging.getLogger(__name__)` |
| `bot/commands/addtheme.py` | Inline `import logging` on line 202 | Move to module-level; add `logger = logging.getLogger(__name__)` |
| `bot/commands/payments.py` | `import logging` at top; uses `logging.error()` directly | Add `logger = logging.getLogger(__name__)`; change calls to `logger.error()` |

### Test Files Needing Patch Updates

| Test File | Current Patch Target | New Patch Target |
|-----------|---------------------|------------------|
| `tests/test_fetcher.py:79` | `delivery.fetcher.logging.warning` | `delivery.fetcher.logger.warning` (or `delivery.fetcher.logger`) |
| `tests/test_fetcher.py:91` | `delivery.fetcher.logging.warning` | `delivery.fetcher.logger.warning` (or `delivery.fetcher.logger`) |
| `tests/test_webhook.py:65` | `api.webhook.logging.warning` | `api.webhook.logger.warning` (or `api.webhook.logger`) |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `print()` debugging | `logging.getLogger(__name__)` | Always been best practice | Filterable, configurable, includes metadata |
| `logging.basicConfig()` at random | Single setup call at entry point | Always been best practice | Prevents "basicConfig ignored" bugs |
| Token bucket rate limiting | Sliding window | Both are valid | Sliding window is simpler to implement for small scale |

## Open Questions

1. **Module-level warning in webhook.py**
   - What we know: Line 18 calls `logging.warning()` at import time, before any basicConfig runs
   - What's unclear: Whether Vercel's serverless cold-start import order can be controlled
   - Recommendation: Place `setup_logging()` call immediately after `load_dotenv()` on line 13, before the warning check on line 17. This ensures config runs first.

2. **addtheme.py inline logging scope**
   - What we know: `bot/commands/addtheme.py` has inline `import logging` on line 202 (same pattern as router.py)
   - What's unclear: Whether D-06 was meant to cover only router.py or all inline logging
   - Recommendation: Fix it. D-03 says "every production module uses `logger = logging.getLogger(__name__)` at module level. No inline `import logging`." This covers addtheme.py too.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all production Python files
- Python stdlib `logging` module documentation (stable, well-known API)
- CONTEXT.md decisions D-01 through D-15

### Secondary (MEDIUM confidence)
- None needed -- this phase uses only Python stdlib with well-established patterns

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Python stdlib only, no version concerns
- Architecture: HIGH -- patterns are well-established Python conventions; code structure fully analyzed
- Pitfalls: HIGH -- identified from direct code analysis (import-time side effects, test patch targets, loop restructuring needs)

**Research date:** 2026-03-22
**Valid until:** Indefinite -- Python logging stdlib is stable; rate limiter is pure logic
