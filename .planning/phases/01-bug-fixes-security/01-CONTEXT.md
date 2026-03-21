# Phase 1: Bug Fixes & Security - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix 6 known bugs (BUG-01 through BUG-06) and close SAFE-02. No new features, no refactoring beyond what the fixes require. All 7 requirements must pass tests; no regressions allowed.

</domain>

<decisions>
## Implementation Decisions

### BUG-01: Custom theme INSERT race condition
- Replace the two-step `INSERT` + `SELECT last_insert_rowid()` in `addtheme._save_custom_theme` with a single `INSERT INTO custom_themes (...) VALUES (...) RETURNING id` statement
- Use the returned `id` directly to drive the `user_themes` INSERT
- Turso HTTP API supports SQLite `RETURNING` — use `db.execute()` and read `rows[0]["id"]`

### BUG-02: Gemini fallback model name
- Verify the correct model ID for the fallback by checking the Gemini API docs / available models
- Update `GEMINI_FALLBACK` constant in `delivery/ai.py` to the verified correct name
- Update the docstring in `summarize_articles` to match actual model names

### BUG-03: Payment payload parsing
- Harden `handle_successful_payment` in `payments.py`: validate that `invoice_payload` contains `:` before splitting
- If payload is malformed: log an error with `logging.error(...)` including the raw payload, send the existing "could not be processed" message to the user, and return early (no DB write)

### BUG-04: Broken RSS feeds — silent swallow
- In `fetcher.fetch_articles`, replace `except Exception: continue` with `except Exception as e: logging.warning("RSS feed failed: url=%s error=%s", feed_url, e)`
- Log level: `warning` (not `error` — broken feeds are expected for 3rd-party URLs)
- Include both the URL and the exception in the log record

### BUG-05: Webhook secret token verification
- In `api/webhook.py`, read `X-Telegram-Bot-Api-Secret-Token` header in `do_POST`
- Compare against `os.environ.get("WEBHOOK_SECRET", "")` using constant-time comparison (`hmac.compare_digest`)
- **If env var is absent or empty:** skip the check entirely (allow all) — this preserves backwards-compat for deployments without a secret configured; log a one-time warning at startup
- **If env var is set and header mismatches:** return HTTP 403 with empty body, do not process the update

### BUG-06 / SAFE-02: RSS URL SSRF mitigation
- Add `_validate_url(url: str) -> bool` in `addtheme.py` (called before `_validate_feed`)
- Block: RFC 1918 ranges (10.x, 172.16–31.x, 192.168.x), loopback (127.x, ::1), link-local (169.254.x.x), and CGNAT (100.64.x.x–100.127.x.x)
- Enforce: scheme must be `http` or `https` only
- Use `urllib.parse.urlparse` + `ipaddress` stdlib — no new dependencies
- User-facing error when blocked: `"❌ That URL uses a restricted address and cannot be used as an RSS feed."`
- Apply validation in both `addtheme._validate_feed` (before any HTTP request) and `fetcher.fetch_articles` (skip with warning log if URL sneaked past storage)

### Claude's Discretion
- Exact regex/IP check implementation details
- Whether to extract the URL validator into `db/` or keep it in `addtheme.py` (prefer keeping in `addtheme.py` unless fetcher also needs it — then extract to a shared utility)
- Test fixtures and mock strategies

</decisions>

<specifics>
## Specific Ideas

- BUG-01: The comment in `addtheme.py:89` already says "avoids TOCTOU race" — but the code doesn't actually do that yet (still two queries). The fix is to make it one atomic query with `RETURNING`.
- BUG-05: Constant-time comparison is important to prevent timing attacks on the secret.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Affected source files
- `bot/commands/addtheme.py` — BUG-01, BUG-06/SAFE-02 (INSERT race, SSRF validation)
- `delivery/ai.py` — BUG-02 (Gemini fallback model name)
- `bot/commands/payments.py` — BUG-03 (payment payload parsing)
- `delivery/fetcher.py` — BUG-04 (silent RSS error swallow)
- `api/webhook.py` — BUG-05 (webhook secret verification)
- `db/client.py` — reference: how `execute()` returns rows (used for RETURNING fix)

### Existing tests (must remain passing + extend for new behavior)
- `tests/bot/test_addtheme.py`
- `tests/bot/test_payments.py`
- `tests/test_fetcher.py`
- `tests/test_ai.py`

### Requirements
- `.planning/REQUIREMENTS.md` — BUG-01 through BUG-06, SAFE-02 acceptance criteria

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.execute(sql, args)` — returns `list[dict]`; supports `RETURNING` (Turso HTTP API passes SQL through to SQLite)
- `db.execute_many(statements)` — for multi-statement atomicity where needed
- `hmac.compare_digest` (stdlib) — use for constant-time secret comparison in webhook
- `ipaddress` (stdlib) — use for SSRF IP range checking
- `urllib.parse.urlparse` (stdlib) — use for scheme + host extraction

### Established Patterns
- All DB writes use `db.execute()` or `db.execute_many()` — no raw SQL outside `db/client.py`
- Errors logged with `logging.warning(...)` or `logging.error(...)` — no `print()` in Phase 1 scope (Phase 2 handles full print cleanup)
- User-facing errors use `tg.send_message(chat_id=user_id, text="❌ ...")` pattern

### Integration Points
- `addtheme._save_custom_theme` → only caller of the buggy INSERT; fix is isolated to this function
- `webhook.do_POST` → entry point for all Telegram updates; secret check goes at the top of `do_POST`
- `fetcher.fetch_articles` → called by delivery pipeline; URL validation here is a safety net, not primary enforcement

</code_context>

<deferred>
## Deferred Ideas

- Full `print()` → `logging` replacement across codebase — Phase 2 (OBS-01)
- Structured JSON log format — Phase 2 (OBS-02)
- Dynamic Gemini model selection at startup — v2 backlog (AI-01)
- Redirect-following limits on RSS fetches — not in Phase 1 scope; captured for backlog

</deferred>

---

*Phase: 01-bug-fixes-security*
*Context gathered: 2026-03-21*
