# Phase 2: Observability & Rate Limiting - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace all production-runtime `print()` calls with structured `logging.getLogger()` calls, add per-theme structured log entries to the delivery run, and implement per-user command rate limiting (5 commands/minute, sliding window). Utility scripts (`db/init_db.py`, `db/seed_themes.py`) are excluded.

</domain>

<decisions>
## Implementation Decisions

### Logging configuration
- **D-01:** Create a centralized logging config module (e.g., `bot/logging_config.py`) that calls `logging.basicConfig()` once. Both `api/webhook.py` and `delivery/main.py` import and call it at startup.
- **D-02:** Log format: plain text with timestamp — `%(asctime)s %(levelname)s %(name)s — %(message)s`
- **D-03:** Every production module uses `logger = logging.getLogger(__name__)` at module level. No inline `import logging` inside functions or branches.
- **D-04:** Minimum log level: INFO. DEBUG is available but not shown by default.

### Print() migration scope
- **D-05:** Migrate all `print()` calls in production runtime code: `delivery/main.py`, `api/webhook.py`. Do NOT migrate `db/init_db.py` or `db/seed_themes.py` — these are developer utility scripts where print is appropriate.
- **D-06:** `bot/router.py` gets its inline `import logging` moved to module-level, plus `logger = logging.getLogger(__name__)`.

### Delivery structured logs (OBS-02)
- **D-07:** Per-theme log entry emitted at INFO level includes: `theme_id`, `theme_type`, `theme_name`, `user_count`, `articles_fetched`, `articles_sent`, `status` (one of: `ok` / `no_articles` / `ai_empty` / `error`), and `error` message when status is `error`.
- **D-08:** Run summary emitted at INFO level at completion: `run complete: themes={N} users={N} articles_sent={N} errors={N} duration={N}s`. Replaces the current `print("[deliver] Done.")`.
- **D-09:** Status values for per-theme entries: `ok`, `no_articles`, `ai_empty`, `error`. Each is a distinct failure mode — avoids over-broad "skipped".

### Broken feed logs (OBS-03)
- **D-10:** `delivery/fetcher.py` already logs `logging.warning("RSS feed failed: url=%s error=%s", ...)`. This satisfies OBS-03 once fetcher.py uses `logger = logging.getLogger(__name__)` at module level (the existing call is already correct, just needs module-level logger).

### Rate limiting (SAFE-01)
- **D-11:** In-memory dict per process in a new `bot/rate_limiter.py` module, keyed by `user_id`. Zero external dependencies. Resets on worker restart — acceptable for single-worker webhook deployment.
- **D-12:** Sliding window — store a list of command timestamps per user. Window: 5 commands per 60 seconds. On each command, evict timestamps older than 60s, then check count.
- **D-13:** Rate limiting applies to `/commands` only (text messages starting with `/`). Callback queries (inline button presses) are not rate-limited — they're UI interactions.
- **D-14:** User-facing message on limit hit: `"Slow down! You've sent too many commands. Try again in {X} seconds."` where X is seconds until the oldest command in the window expires.
- **D-15:** Rate check is applied in `bot/router.py`'s `handle_update()` before dispatching to command handlers.

### Claude's Discretion
- Exact module name for centralized logging config (`bot/logging_config.py` or `delivery/logging_config.py` — pick what makes most sense given import structure)
- Whether to use `collections.deque` or plain `list` for per-user timestamp storage in the rate limiter
- Thread safety of the in-memory rate limiter (single-threaded WSGI worker is fine without locks)

</decisions>

<specifics>
## Specific Ideas

- The per-theme delivery log entry should be one `logger.info(...)` call with keyword-style values so it reads cleanly: `theme_id=3 theme_type=default theme_name="Tech News" user_count=5 articles_sent=3 status=ok`
- Rate limit wait time in the user message should be computed as `ceil(60 - (now - oldest_timestamp_in_window))`

</specifics>

<canonical_refs>
## Canonical References

No external specs — requirements are fully captured in decisions above.

### Project requirements
- `.planning/REQUIREMENTS.md` — OBS-01, OBS-02, OBS-03, SAFE-01 definitions
- `.planning/ROADMAP.md` — Phase 2 goal and deliverables

### Existing code to read before modifying
- `delivery/main.py` — 11 print() calls to migrate; add per-theme + run-summary log entries
- `delivery/fetcher.py` — Already has correct log message content; needs module-level logger
- `bot/router.py` — Inline import to fix; rate limit check insertion point is `handle_update()`
- `api/webhook.py` — 1 print() to migrate to logger

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `delivery/fetcher.py` logger pattern — already uses `logging.warning(...)` with `%`-style format; replicate this style everywhere
- `bot/validation.py` — shared module pattern (established in Phase 1); `bot/rate_limiter.py` should follow same structure

### Established Patterns
- Phase 1 established `bot/validation.py` as the shared utility module location; rate limiter follows this pattern
- `logging.warning("...: url=%s error=%s", url, e)` %-style format string used in fetcher/ai/payments — keep consistent

### Integration Points
- `bot/router.py:handle_update()` line 76 — rate limit check goes here, before command dispatch
- `delivery/main.py:run()` — per-theme log entries go inside the `for (theme_type, theme_id), users in groups.items()` loop
- `api/webhook.py` and `delivery/main.py` — both need to call centralized logging setup at startup

</code_context>

<deferred>
## Deferred Ideas

- JSON structured log format for log aggregation (Datadog/CloudWatch) — noted as v2 requirement INF-02, not in scope here
- Rate limiting callback queries — could be added later if abuse is detected
- Startup env var validation — v2 requirement INF-01, not in scope here

</deferred>

---

*Phase: 02-observability-rate-limiting*
*Context gathered: 2026-03-22*
