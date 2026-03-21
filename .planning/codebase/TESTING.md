# Testing

**Analysis Date:** 2026-03-21

## Framework

- **pytest 8.3.4** — test runner
- **pytest-mock 3.14.0** — `patch` / `MagicMock` fixtures
- **unittest.mock** — used directly alongside pytest-mock

## Test Structure

```
tests/
├── bot/                    # Bot command tests (8 files)
│   ├── test_addtheme.py
│   ├── test_history.py
│   ├── test_payments.py
│   ├── test_router.py
│   ├── test_schedule.py
│   ├── test_settings.py
│   ├── test_start.py
│   └── test_themes.py
├── test_ai.py              # AI summarization tests
├── test_cache.py           # Theme cache tests
├── test_db_client.py       # DB client (Turso HTTP) tests
├── test_fetcher.py         # RSS feed fetcher tests
├── test_poster.py          # Article poster tests
└── test_scheduler.py       # Delivery scheduler tests
```

## Mocking Approach

**Environment setup at module level** (no conftest.py):
```python
os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
```

**HTTP calls mocked** — Turso and Telegram API calls patched with `unittest.mock.patch`:
```python
@patch("bot.commands.start.handle")
def test_router_dispatches_start(mock_handle):
    from bot.router import handle_update
    handle_update(_update("/start"))
    assert mock_handle.called
```

**Helper constructors** — Tests define local helpers to build message/update dicts:
```python
def _update(text="/start", user_id=123):
    return {"message": {"message_id": 1, "from": {"id": user_id, ...}, "text": text}}
```

## Test Patterns

- **Import inside test functions** — avoids import-time side effects from env-dependent modules
- **`@patch` decorator** — used for HTTP calls, DB calls, Telegram API calls
- **Assertion style:** `assert mock.called`, `assert result == expected`, `mock.assert_called_once_with(...)`
- **No fixtures file** — each test file sets up its own environment and mocks

## Coverage

- All 8 bot commands have dedicated test files
- Delivery pipeline components covered: `test_ai.py`, `test_cache.py`, `test_fetcher.py`, `test_poster.py`, `test_scheduler.py`
- DB client has dedicated tests: `test_db_client.py`
- Router dispatch logic tested in `test_router.py`

## Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific module
python -m pytest tests/bot/test_router.py -v

# Run with output
python -m pytest tests/ -s
```

## Gaps

- No `conftest.py` — env setup duplicated across test files
- No integration tests against real Turso instance
- Feed validation exceptions not explicitly tested in fetcher
- State machine transitions (pending_actions) not systematically covered
- AI fallback chain (Gemini→Groq) not explicitly tested for partial failures
- No coverage reporting configured

---
*Testing analysis: 2026-03-21*
