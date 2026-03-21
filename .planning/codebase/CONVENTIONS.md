# Conventions

**Analysis Date:** 2026-03-21

## Code Style

- **Language version:** Python 3.12+ (3.13 in production on GitHub Actions)
- **Type hints:** Used on function signatures in core modules (`delivery/`, `db/client.py`); sparse in `bot/commands/`
- **Imports:** Standard library first, then third-party, then project modules; local imports sometimes deferred (inside functions) to avoid circular imports
- **Line length:** No explicit formatter config; follows ~100-char practical limit
- **No linter config:** No `pyproject.toml`, `.flake8`, or `ruff.toml` present

## Naming

- **Modules:** `snake_case` (e.g., `addtheme.py`, `db_client.py`)
- **Functions:** `snake_case` verbs (`handle`, `fetch_articles`, `get_cached`, `execute_many`)
- **Constants:** `UPPER_SNAKE_CASE` (`FREE_ARTICLES_PER_THEME`, `GEMINI_PRIMARY`, `COMMAND_MAP`)
- **DB tables:** `snake_case` plural (`users`, `user_themes`, `posted_articles`)
- **Private helpers:** Prefixed with `_` (`_url()`, `_headers()`, `_coerce()`, `_call_gemini()`)

## Patterns

### Command Handler Pattern
Each command module exposes a primary `handle(message: dict)` function:
```python
def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    # ... business logic ...
    tg.send_message(user_id, "text")
```

### DB Access Pattern
All DB calls go through `db/client.py`:
```python
rows = db.execute("SELECT ... FROM users WHERE user_id = ?", [user_id])
db.execute_many([("UPDATE users SET tier = ? WHERE user_id = ?", ["free", user_id])])
```
Row access by column name: `row["user_id"]`, `row["tier"]`

### JSON State Storage
Complex state stored as JSON strings in TEXT columns:
```python
# Write
json.dumps(feed_urls)  # → stored in rss_feeds column
# Read
json.loads(row["rss_feeds"])
```

### Pending Action State Machine
Multi-step flows write intermediate state to `user_pending_actions`:
```python
db.execute_many([("INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) VALUES (?, ?, ?, ?)",
    [user_id, "addtheme_ai_name", json.dumps({"feeds": selected_feeds}), int(time.time())])])
```
Router reads this before dispatching commands.

### Environment Variables
All secrets accessed via `os.environ["KEY"]` (raises `KeyError` if missing — intentional fail-fast):
```python
bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
key = os.environ.get("GEMINI_API_KEY")  # optional variant
```

## Error Handling

- **Delivery pipeline:** Broad `except Exception` with `print()/logging.warning()` + `continue` — errors skip the item, don't crash the run
- **Webhook:** Single top-level try/except in `api/webhook.py` to always return HTTP 200
- **Feed parsing:** Silent skip on broken feeds (`except Exception: continue` in `delivery/fetcher.py`)
- **DB client:** Raises `RuntimeError` on Turso API errors; HTTP errors via `resp.raise_for_status()`
- **Telegram calls:** Some have try/except (expiry reminders), others are fire-and-forget

## Logging

- `print()` used in `delivery/main.py` for structured operational output (`[deliver]` prefix)
- `logging.warning()` used in `delivery/scheduler.py` and `bot/router.py`
- No logging framework config; no structured JSON logging
- Webhook suppresses default HTTP access logs: `def log_message(self, *args): pass`

## Function Design

- Functions are small and single-purpose
- No classes used in business logic (functional style throughout)
- DB client is the only module with multiple closely-related helper functions
- AI module uses lambdas for the fallback chain to defer execution:
  ```python
  attempts = [
      lambda: _call_gemini(prompt, GEMINI_PRIMARY),
      lambda: _call_gemini(prompt, GEMINI_FALLBACK),
      lambda: _call_groq(prompt),
  ]
  ```

---
*Conventions analysis: 2026-03-21*
