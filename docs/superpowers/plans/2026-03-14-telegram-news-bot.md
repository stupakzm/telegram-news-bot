# Telegram Personalized News Bot Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Telegram bot that delivers personalized AI-summarized news digests to individual users in DMs, with three paid tiers via Telegram Stars.

**Architecture:** Vercel serverless function handles all user-facing bot commands (webhook); GitHub Actions hourly cron handles scheduled news delivery. Both runtimes share a Turso (cloud SQLite) database — no user data ever touches the repo.

**Tech Stack:** Python 3.12 (Vercel runtime constraint) / 3.13 locally and in GH Actions, Turso HTTP API (via `requests`), `feedparser` for RSS, `google-generativeai` for Gemini, `requests` for Groq/Telegram/Turso, `pytest` for tests, Vercel Python runtime, GitHub Actions.

---

## File Map

```
telegram-news-bot/
├── api/
│   └── webhook.py              # Vercel entry point (imports from bot/)
├── bot/
│   ├── router.py               # routes messages + callback_query updates to handlers
│   ├── telegram.py             # thin wrapper: send_message, send_invoice
│   └── commands/
│       ├── start.py            # /start onboarding flow
│       ├── themes.py           # /themes add/remove
│       ├── schedule.py         # /schedule setup
│       ├── upgrade.py          # /upgrade tier comparison
│       ├── payments.py         # Stars invoice + successful_payment handler
│       ├── history.py          # /history (monthly tier)
│       ├── addtheme.py         # /addtheme (AI-suggested) + /addthememanual
│       └── settings.py         # /settings overview
├── delivery/
│   ├── scheduler.py            # query: which users are due this hour
│   ├── fetcher.py              # fetch RSS feeds, filter posted_articles
│   ├── ai.py                   # AI summarization with fallback chain
│   ├── cache.py                # quarter-based theme cache (read/write Turso)
│   └── poster.py               # fan-out: format + send digests to each user
├── db/
│   ├── client.py               # Turso HTTP API wrapper (execute, execute_many)
│   └── schema.sql              # all CREATE TABLE statements
├── themes/
│   └── default_themes.json     # 6 default themes with RSS feeds
├── tests/
│   ├── test_db_client.py
│   ├── test_fetcher.py
│   ├── test_cache.py
│   ├── test_ai.py
│   ├── test_poster.py
│   ├── test_scheduler.py
│   └── bot/
│       ├── test_router.py
│       ├── test_start.py
│       ├── test_themes.py
│       ├── test_schedule.py
│       ├── test_payments.py
│       └── test_history.py
├── .github/
│   └── workflows/
│       └── deliver.yml
├── vercel.json
├── requirements.txt
├── requirements-dev.txt
└── .env.example
```

---

## Chunk 1: Foundation — Project Setup, DB Schema, Turso Client

### Task 1: Project files

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `.env.example`
- Create: `vercel.json`
- Create: `.gitignore`

- [ ] **Step 1: Create `requirements.txt`**

```
feedparser==6.0.11
google-generativeai==0.8.3
requests==2.32.3
python-dotenv==1.0.1
```

- [ ] **Step 2: Create `requirements-dev.txt`**

```
pytest==8.3.4
pytest-mock==3.14.0
```

- [ ] **Step 3: Create `.env.example`**

```
TURSO_URL=https://your-db-name-org.turso.io
TURSO_TOKEN=your_turso_token_here
TELEGRAM_BOT_TOKEN=your_bot_token_here
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
STARS_ONETIME_PRICE=200
STARS_MONTHLY_PRICE=100
```

- [ ] **Step 4: Create `vercel.json`**

```json
{
  "functions": {
    "api/webhook.py": {
      "runtime": "python3.12"
    }
  },
  "routes": [
    { "src": "/webhook", "dest": "api/webhook.py" }
  ]
}
```

- [ ] **Step 5: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
venv/
```

- [ ] **Step 6: Commit**

```bash
git add requirements.txt requirements-dev.txt .env.example vercel.json .gitignore
git commit -m "chore: project setup — deps, env template, vercel config"
```

---

### Task 2: DB Schema

**Files:**
- Create: `db/schema.sql`
- Create: `db/__init__.py` (empty)

- [ ] **Step 1: Create `db/__init__.py`** (empty file)

- [ ] **Step 2: Create `db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id          INTEGER PRIMARY KEY,
    tier             TEXT    NOT NULL DEFAULT 'free',  -- 'free' | 'one_time' | 'monthly'
    tier_expires_at  INTEGER,                           -- NULL for free/one_time; Unix ts for monthly
    created_at       INTEGER NOT NULL,
    stars_paid       INTEGER NOT NULL DEFAULT 0,
    last_reminder_at INTEGER                            -- Unix ts of last expiry reminder; NULL if never
);

CREATE TABLE IF NOT EXISTS themes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT    NOT NULL,
    hashtag   TEXT    NOT NULL,
    rss_feeds TEXT    NOT NULL,  -- JSON array of URL strings
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS custom_themes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(user_id),
    name         TEXT    NOT NULL,
    hashtag      TEXT    NOT NULL,  -- e.g. '#evs', used in AI prompt and post formatting
    rss_feeds    TEXT    NOT NULL,  -- JSON array of URL strings
    ai_suggested INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_themes (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id            INTEGER NOT NULL REFERENCES users(user_id),
    theme_type         TEXT    NOT NULL,  -- 'default' | 'custom'
    theme_id           INTEGER NOT NULL,  -- references themes.id or custom_themes.id
    articles_per_theme INTEGER NOT NULL DEFAULT 1  -- count of news items (not posts): 1 free/one_time, 1-2 monthly
);

CREATE TABLE IF NOT EXISTS user_schedules (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    user_theme_id INTEGER REFERENCES user_themes(id),  -- NULL = global schedule (free tier)
    days          TEXT    NOT NULL,                     -- JSON array e.g. [1,3,5] (1=Mon...7=Sun)
    hour_utc      INTEGER NOT NULL                      -- 0-23
);

CREATE TABLE IF NOT EXISTS digest_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(user_id),
    theme_type TEXT    NOT NULL,
    theme_id   INTEGER NOT NULL,
    theme_name TEXT    NOT NULL,  -- snapshot at send time
    articles   TEXT    NOT NULL,  -- JSON array of article summaries
    sent_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS posted_articles (
    url       TEXT    PRIMARY KEY,
    posted_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS theme_cache (
    theme_type   TEXT    NOT NULL,
    theme_id     INTEGER NOT NULL,
    cache_date   TEXT    NOT NULL,  -- 'YYYY-MM-DD' UTC
    quarter      INTEGER NOT NULL,  -- 0-3 (hour // 6)
    articles     TEXT    NOT NULL,  -- JSON array of AI summaries
    generated_at INTEGER NOT NULL,
    PRIMARY KEY (theme_type, theme_id, cache_date, quarter)
);

CREATE TABLE IF NOT EXISTS user_pending_actions (
    user_id    INTEGER PRIMARY KEY REFERENCES users(user_id),
    action     TEXT    NOT NULL,  -- e.g. 'addtheme_ai_topic' | 'addtheme_ai_name' | 'addtheme_manual_name'
    data       TEXT,              -- JSON blob of intermediate state (e.g. selected feed URLs)
    created_at INTEGER NOT NULL
);
```

- [ ] **Step 3: Commit**

```bash
git add db/
git commit -m "feat: add database schema (all tables)"
```

---

### Task 3: Turso client

**Files:**
- Create: `db/client.py`
- Create: `tests/test_db_client.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_db_client.py
import pytest
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")


def _mock_resp(rows, cols):
    """Build a mock Turso HTTP response for a SELECT."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "results": [{
            "type": "ok",
            "response": {
                "type": "execute",
                "result": {
                    "cols": [{"name": c} for c in cols],
                    "rows": [
                        [{"type": "text", "value": str(v)} if isinstance(v, str)
                         else {"type": "integer", "value": str(v)} if isinstance(v, int)
                         else {"type": "null", "value": None}
                         for v in row]
                        for row in rows
                    ],
                    "affected_row_count": 0,
                    "last_insert_rowid": None,
                }
            }
        }]
    }
    return mock


def test_execute_returns_list_of_dicts():
    from db.client import execute
    with patch("db.client.requests.post", return_value=_mock_resp(
        rows=[[1, "free"]], cols=["user_id", "tier"]
    )):
        result = execute("SELECT user_id, tier FROM users WHERE user_id = ?", [1])
    assert result == [{"user_id": 1, "tier": "free"}]


def test_execute_handles_null_values():
    from db.client import execute
    with patch("db.client.requests.post", return_value=_mock_resp(
        rows=[[1, None]], cols=["user_id", "tier_expires_at"]
    )):
        result = execute("SELECT user_id, tier_expires_at FROM users", [])
    assert result[0]["tier_expires_at"] is None


def test_execute_empty_result():
    from db.client import execute
    with patch("db.client.requests.post", return_value=_mock_resp(rows=[], cols=["user_id"])):
        result = execute("SELECT * FROM users WHERE user_id = ?", [999])
    assert result == []


def test_execute_many_sends_multiple_statements():
    from db.client import execute_many
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"type": "ok", "response": {"type": "execute", "result": {"cols": [], "rows": [], "affected_row_count": 1, "last_insert_rowid": None}}},
            {"type": "ok", "response": {"type": "execute", "result": {"cols": [], "rows": [], "affected_row_count": 1, "last_insert_rowid": None}}},
        ]
    }
    with patch("db.client.requests.post", return_value=mock_resp) as mock_post:
        execute_many([
            ("INSERT INTO users (user_id, created_at) VALUES (?, ?)", [1, 1000]),
            ("INSERT INTO users (user_id, created_at) VALUES (?, ?)", [2, 1001]),
        ])
    payload = mock_post.call_args[1]["json"]
    assert len(payload["requests"]) == 2
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /c/Users/TopAide/projects/telegram-news-bot
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_db_client.py -v
```
Expected: `ModuleNotFoundError: No module named 'db.client'`

- [ ] **Step 3: Implement `db/client.py`**

```python
# db/client.py
import os
import requests


def _url() -> str:
    return os.environ["TURSO_URL"].rstrip("/")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['TURSO_TOKEN']}",
        "Content-Type": "application/json",
    }


def _coerce(v: dict):
    if v is None or v.get("type") == "null":
        return None
    t = v.get("type", "text")
    val = v.get("value")
    if t == "integer":
        return int(val)
    if t == "float":
        return float(val)
    return val


def _arg(a) -> dict:
    if a is None:
        return {"type": "null", "value": None}
    if isinstance(a, int):
        return {"type": "integer", "value": str(a)}
    if isinstance(a, float):
        return {"type": "float", "value": str(a)}
    return {"type": "text", "value": str(a)}


def execute(sql: str, args: list = None) -> list[dict]:
    """Execute a single SQL statement, return list of row dicts."""
    stmt = {"sql": sql, "args": [_arg(a) for a in (args or [])]}
    resp = requests.post(
        f"{_url()}/v2/pipeline",
        headers=_headers(),
        json={"requests": [{"type": "execute", "stmt": stmt}]},
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()["results"][0]["response"]["result"]
    cols = [c["name"] for c in result["cols"]]
    return [dict(zip(cols, [_coerce(v) for v in row])) for row in result["rows"]]


def execute_many(statements: list[tuple]) -> None:
    """Execute multiple SQL statements in a single pipeline request."""
    requests_body = [
        {"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in (args or [])]}}
        for sql, args in statements
    ]
    resp = requests.post(
        f"{_url()}/v2/pipeline",
        headers=_headers(),
        json={"requests": requests_body},
        timeout=10,
    )
    resp.raise_for_status()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_db_client.py -v
```
Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add db/client.py tests/test_db_client.py
git commit -m "feat: add Turso HTTP client with execute/execute_many"
```

---

### Task 4: Default themes JSON

**Files:**
- Create: `themes/default_themes.json`
- Create: `themes/__init__.py` (empty)

- [ ] **Step 1: Create `themes/default_themes.json`**

```json
[
  {
    "name": "Technology",
    "hashtag": "#tech",
    "rss_feeds": [
      "https://techcrunch.com/feed/",
      "https://www.theverge.com/rss/index.xml"
    ]
  },
  {
    "name": "Artificial Intelligence",
    "hashtag": "#ai",
    "rss_feeds": [
      "https://venturebeat.com/category/ai/feed/",
      "https://www.technologyreview.com/feed/"
    ]
  },
  {
    "name": "Privacy & Security",
    "hashtag": "#privacy",
    "rss_feeds": [
      "https://www.eff.org/rss/updates.xml",
      "https://www.wired.com/feed/category/security/latest/rss"
    ]
  },
  {
    "name": "Software Development",
    "hashtag": "#software",
    "rss_feeds": [
      "https://www.infoq.com/feed/",
      "https://news.ycombinator.com/rss"
    ]
  },
  {
    "name": "Tech Companies",
    "hashtag": "#techcompanies",
    "rss_feeds": [
      "https://feeds.reuters.com/reuters/technologyNews",
      "https://feeds.bloomberg.com/technology/news.rss"
    ]
  },
  {
    "name": "Hardware",
    "hashtag": "#hardware",
    "rss_feeds": [
      "https://www.anandtech.com/rss/",
      "https://www.tomshardware.com/feeds/all"
    ]
  }
]
```

- [ ] **Step 2: Create a one-time seed script `db/seed_themes.py`**

Run this once to populate Turso with the default themes:

```python
#!/usr/bin/env python3
# db/seed_themes.py
"""Run once: python db/seed_themes.py"""
import json, os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.client import execute_many

with open("themes/default_themes.json") as f:
    themes = json.load(f)

statements = [
    (
        "INSERT OR IGNORE INTO themes (name, hashtag, rss_feeds, is_active) VALUES (?, ?, ?, 1)",
        [t["name"], t["hashtag"], json.dumps(t["rss_feeds"])],
    )
    for t in themes
]
execute_many(statements)
print(f"Seeded {len(themes)} themes.")
```

- [ ] **Step 3: Also apply schema to Turso**

In the Turso dashboard (console.turso.tech) or via CLI, run the contents of `db/schema.sql` to create all tables.

Alternatively, create `db/init_db.py`:

```python
#!/usr/bin/env python3
# db/init_db.py
"""Run once to create schema: python db/init_db.py"""
import os, sys
from dotenv import load_dotenv
load_dotenv()
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.client import execute_many

with open("db/schema.sql") as f:
    raw = f.read()

# Split on semicolons, skip empty statements
statements = [(s.strip(), []) for s in raw.split(";") if s.strip()]
execute_many(statements)
print("Schema applied.")
```

- [ ] **Step 4: Commit**

```bash
git add themes/ db/seed_themes.py db/init_db.py db/__init__.py themes/__init__.py
git commit -m "feat: add default themes JSON and DB seed/init scripts"
```

---

## Chunk 2: Delivery Engine — Fetcher & Cache

### Task 5: RSS Fetcher

**Files:**
- Create: `delivery/__init__.py` (empty)
- Create: `delivery/fetcher.py`
- Create: `tests/test_fetcher.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fetcher.py
import pytest
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")


def _make_entry(url, title, summary):
    e = MagicMock()
    e.link = url
    e.title = title
    e.summary = summary
    return e


def _theme(hashtag="#ai", feeds=None):
    return {
        "id": 1,
        "theme_type": "default",
        "name": "AI",
        "hashtag": hashtag,
        "rss_feeds": feeds or ["https://feed.example.com/rss"],
    }


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.db.execute")
def test_fetch_articles_filters_posted(mock_execute, mock_parse):
    mock_execute.return_value = [{"url": "https://old.com/1"}]
    mock_parse.return_value = MagicMock(entries=[
        _make_entry("https://old.com/1", "Old", "Already posted"),
        _make_entry("https://new.com/2", "New", "Fresh article"),
    ])

    from delivery.fetcher import fetch_articles
    result = fetch_articles(_theme())

    assert len(result) == 1
    assert result[0]["url"] == "https://new.com/2"
    assert result[0]["title"] == "New"


@patch("delivery.fetcher.feedparser.parse")
@patch("delivery.fetcher.db.execute")
def test_fetch_articles_returns_correct_shape(mock_execute, mock_parse):
    mock_execute.return_value = []
    mock_parse.return_value = MagicMock(entries=[
        _make_entry("https://new.com/1", "Title", "Summary text"),
    ])

    from delivery.fetcher import fetch_articles
    result = fetch_articles(_theme(hashtag="#ai"))

    assert result[0] == {
        "url": "https://new.com/1",
        "title": "Title",
        "description": "Summary text",
        "theme_type": "default",
        "theme_id": 1,
        "hashtag": "#ai",
    }


@patch("delivery.fetcher.feedparser.parse", side_effect=Exception("network error"))
@patch("delivery.fetcher.db.execute")
def test_fetch_articles_skips_broken_feed(mock_execute, mock_parse):
    mock_execute.return_value = []

    from delivery.fetcher import fetch_articles
    result = fetch_articles(_theme())
    assert result == []
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_fetcher.py -v
```
Expected: `ModuleNotFoundError: No module named 'delivery.fetcher'`

- [ ] **Step 3: Implement `delivery/fetcher.py`**

```python
# delivery/fetcher.py
import json
import feedparser
import db.client as db


def fetch_articles(theme: dict) -> list[dict]:
    """
    Fetch new articles for a theme (default or custom).
    Filters out URLs already in posted_articles.
    Returns list of article dicts.

    theme dict keys: id, theme_type, name, hashtag, rss_feeds (list of URLs)
    """
    posted = {row["url"] for row in db.execute("SELECT url FROM posted_articles")}
    articles = []

    for feed_url in theme["rss_feeds"]:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                url = getattr(entry, "link", None)
                if not url or url in posted:
                    continue
                articles.append({
                    "url": url,
                    "title": getattr(entry, "title", ""),
                    "description": getattr(entry, "summary", ""),
                    "theme_type": theme["theme_type"],
                    "theme_id": theme["id"],
                    "hashtag": theme["hashtag"],
                })
        except Exception:
            continue  # skip broken feeds silently

    return articles
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_fetcher.py -v
```
Expected: 3 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add delivery/__init__.py delivery/fetcher.py tests/test_fetcher.py
git commit -m "feat: add RSS fetcher with posted_articles dedup"
```

---

### Task 6: Quarter Cache

**Files:**
- Create: `delivery/cache.py`
- Create: `tests/test_cache.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cache.py
import pytest
from unittest.mock import patch
import os
from datetime import datetime, timezone

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")


def test_current_quarter_maps_hours_correctly():
    from delivery.cache import current_quarter
    assert current_quarter(0) == 0
    assert current_quarter(5) == 0
    assert current_quarter(6) == 1
    assert current_quarter(11) == 1
    assert current_quarter(12) == 2
    assert current_quarter(17) == 2
    assert current_quarter(18) == 3
    assert current_quarter(23) == 3


@patch("delivery.cache.db.execute")
def test_get_cached_returns_articles_on_hit(mock_execute):
    import json
    cached = [{"title": "Test", "url": "https://x.com"}]
    mock_execute.return_value = [{"articles": json.dumps(cached)}]

    from delivery.cache import get_cached
    result = get_cached("default", 1, "2026-03-14", 2)
    assert result == cached


@patch("delivery.cache.db.execute")
def test_get_cached_returns_none_on_miss(mock_execute):
    mock_execute.return_value = []

    from delivery.cache import get_cached
    result = get_cached("default", 1, "2026-03-14", 2)
    assert result is None


@patch("delivery.cache.db.execute_many")
def test_set_cache_writes_correct_row(mock_execute_many):
    import json
    from delivery.cache import set_cache
    articles = [{"title": "News", "url": "https://example.com"}]
    set_cache("custom", 42, "2026-03-14", 1, articles)

    call_args = mock_execute_many.call_args[0][0]
    sql, args = call_args[0]
    assert "INSERT OR REPLACE" in sql
    assert args[0] == "custom"
    assert args[1] == 42
    assert args[2] == "2026-03-14"
    assert args[3] == 1
    assert json.loads(args[4]) == articles
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_cache.py -v
```
Expected: `ModuleNotFoundError: No module named 'delivery.cache'`

- [ ] **Step 3: Implement `delivery/cache.py`**

```python
# delivery/cache.py
import json
import time
import db.client as db


def current_quarter(hour: int) -> int:
    """Map UTC hour (0-23) to quarter index (0-3)."""
    return hour // 6


def get_cached(theme_type: str, theme_id: int, date: str, quarter: int) -> list[dict] | None:
    """Return cached article list, or None on cache miss."""
    rows = db.execute(
        "SELECT articles FROM theme_cache "
        "WHERE theme_type = ? AND theme_id = ? AND cache_date = ? AND quarter = ?",
        [theme_type, theme_id, date, quarter],
    )
    if not rows:
        return None
    return json.loads(rows[0]["articles"])


def set_cache(theme_type: str, theme_id: int, date: str, quarter: int, articles: list[dict]) -> None:
    """Write or replace a cache entry for this theme + quarter."""
    db.execute_many([
        (
            "INSERT OR REPLACE INTO theme_cache "
            "(theme_type, theme_id, cache_date, quarter, articles, generated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [theme_type, theme_id, date, quarter, json.dumps(articles), int(time.time())],
        )
    ])
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_cache.py -v
```
Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add delivery/cache.py tests/test_cache.py
git commit -m "feat: add quarter-based theme cache"
```

---

## Chunk 3: Delivery Engine — AI & Poster

### Task 7: AI Summarization

**Files:**
- Create: `delivery/ai.py`
- Create: `tests/test_ai.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ai.py
import pytest
from unittest.mock import patch, MagicMock
import json
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")


SAMPLE_ARTICLES = [
    {"url": "https://a.com/1", "title": "AI Regulation Passed", "description": "EU passes major AI act."},
    {"url": "https://b.com/2", "title": "New GPU Released", "description": "NVIDIA releases RTX 9090."},
]

EXPECTED_SUMMARIES = [
    {
        "url": "https://a.com/1",
        "title": "AI Regulation Passed",
        "summary": "The EU just passed landmark AI legislation.",
        "hashtags": ["#ai"],
        "is_important": True,
        "importance_detail": "This affects all AI companies operating in Europe.",
    },
    {
        "url": "https://b.com/2",
        "title": "New GPU Released",
        "summary": "NVIDIA launches RTX 9090 with massive performance gains.",
        "hashtags": ["#hardware"],
        "is_important": False,
        "importance_detail": "",
    },
]


@patch("delivery.ai._call_gemini", return_value=EXPECTED_SUMMARIES)
def test_summarize_uses_gemini_first(mock_gemini):
    from delivery.ai import summarize_articles
    result = summarize_articles(SAMPLE_ARTICLES, "#ai")
    assert mock_gemini.called
    assert result == EXPECTED_SUMMARIES


@patch("delivery.ai._call_groq", return_value=EXPECTED_SUMMARIES)
@patch("delivery.ai._call_gemini", side_effect=Exception("quota exceeded"))
def test_summarize_falls_back_to_groq_when_gemini_fails(mock_gemini, mock_groq):
    from delivery.ai import summarize_articles
    result = summarize_articles(SAMPLE_ARTICLES, "#ai")
    assert mock_groq.called
    assert result == EXPECTED_SUMMARIES


@patch("delivery.ai._call_groq", side_effect=Exception("groq down"))
@patch("delivery.ai._call_gemini", side_effect=Exception("quota exceeded"))
def test_summarize_returns_empty_when_all_fail(mock_gemini, mock_groq):
    from delivery.ai import summarize_articles
    result = summarize_articles(SAMPLE_ARTICLES, "#ai")
    assert result == []


def test_summarize_uses_gemini_35_before_groq():
    """Gemini 2.5 fails → Gemini 3.5 succeeds → Groq never called."""
    call_count = {"n": 0}

    def gemini_side_effect(prompt, model_name):
        call_count["n"] += 1
        if model_name == "gemini-2.5-flash":
            raise Exception("quota exceeded")
        return EXPECTED_SUMMARIES  # gemini-3.5-flash succeeds

    with patch("delivery.ai._call_gemini", side_effect=gemini_side_effect) as mock_g, \
         patch("delivery.ai._call_groq") as mock_groq:
        from delivery.ai import summarize_articles
        result = summarize_articles(SAMPLE_ARTICLES, "#ai")

    assert result == EXPECTED_SUMMARIES
    assert call_count["n"] == 2  # called twice: 2.5-flash (fail) then 3.5-flash (success)
    assert not mock_groq.called


def test_build_prompt_contains_articles_and_hashtag():
    from delivery.ai import _build_prompt
    prompt = _build_prompt(SAMPLE_ARTICLES, "#ai")
    assert "#ai" in prompt
    assert "AI Regulation Passed" in prompt
    assert "New GPU Released" in prompt
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_ai.py -v
```
Expected: `ModuleNotFoundError: No module named 'delivery.ai'`

- [ ] **Step 3: Implement `delivery/ai.py`**

```python
# delivery/ai.py
import json
import os
import requests
import google.generativeai as genai

GEMINI_PRIMARY = "gemini-2.5-flash"
GEMINI_FALLBACK = "gemini-3.5-flash"
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

PROMPT_TEMPLATE = """\
You are a news summarizer for a Telegram bot. Analyze the articles below and return a JSON array.

For each article return an object with exactly these keys:
- "url": the article url (unchanged from input)
- "title": the article title (unchanged from input)
- "summary": 2-3 punchy sentences for a tech-savvy reader
- "hashtags": JSON array of 1-2 hashtags chosen from: {hashtag}
- "is_important": true ONLY if major real-world impact (regulation, market crash, critical breach, major launch); false otherwise
- "importance_detail": if is_important true, one paragraph of context; else empty string ""

Return ONLY a valid JSON array. No markdown fences, no explanation.

Articles:
{articles_json}
"""


def _build_prompt(articles: list[dict], hashtag: str) -> str:
    slim = [{"url": a["url"], "title": a["title"], "description": a["description"]} for a in articles]
    return PROMPT_TEMPLATE.format(hashtag=hashtag, articles_json=json.dumps(slim, ensure_ascii=False))


def _parse_response(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _call_gemini(prompt: str, model_name: str) -> list[dict]:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt)
    return _parse_response(response.text)


def _call_groq(prompt: str) -> list[dict]:
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return _parse_response(resp.json()["choices"][0]["message"]["content"])


def summarize_articles(articles: list[dict], hashtag: str) -> list[dict]:
    """
    Summarize articles using AI. Returns list of summary dicts.
    Falls back: Gemini 2.5 Flash → Gemini 3.5 Flash → Groq Llama.
    Returns [] if all providers fail.
    """
    if not articles:
        return []

    prompt = _build_prompt(articles, hashtag)

    for attempt in [
        lambda: _call_gemini(prompt, GEMINI_PRIMARY),
        lambda: _call_gemini(prompt, GEMINI_FALLBACK),
        lambda: _call_groq(prompt),
    ]:
        try:
            return attempt()
        except Exception:
            continue

    return []
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_ai.py -v
```
Expected: 5 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add delivery/ai.py tests/test_ai.py
git commit -m "feat: add AI summarization with Gemini 2.5→3.5→Groq fallback chain"
```

---

### Task 8: Telegram Poster

**Files:**
- Create: `delivery/poster.py`
- Create: `tests/test_poster.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_poster.py
import pytest
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-bot-token")


ARTICLE = {
    "url": "https://example.com/article",
    "title": "Big AI Announcement",
    "summary": "OpenAI releases GPT-5. It is very powerful.",
    "hashtags": ["#ai"],
    "is_important": False,
    "importance_detail": "",
}

IMPORTANT_ARTICLE = {**ARTICLE, "is_important": True, "importance_detail": "This changes everything."}


def test_format_post_contains_title_summary_hashtags_link():
    from delivery.poster import format_post
    text = format_post(ARTICLE)
    assert "Big AI Announcement" in text
    assert "OpenAI releases GPT-5" in text
    assert "#ai" in text
    assert "https://example.com/article" in text


@patch("delivery.poster._send_message")
def test_post_article_sends_one_message_for_normal(mock_send):
    mock_send.return_value = {"message_id": 1}
    from delivery.poster import post_article
    post_article(user_id=123, article=ARTICLE)
    assert mock_send.call_count == 1


@patch("delivery.poster._send_message")
def test_post_article_sends_followup_for_important(mock_send):
    mock_send.return_value = {"message_id": 42}
    from delivery.poster import post_article
    post_article(user_id=123, article=IMPORTANT_ARTICLE)
    assert mock_send.call_count == 2
    # second call should reply to first message
    second_call_kwargs = mock_send.call_args_list[1][1]
    assert second_call_kwargs.get("reply_to_message_id") == 42


@patch("delivery.poster.requests.post")
def test_send_message_calls_telegram_api(mock_post):
    mock_post.return_value = MagicMock(json=lambda: {"ok": True, "result": {"message_id": 5}})
    mock_post.return_value.raise_for_status = MagicMock()
    from delivery.poster import _send_message
    result = _send_message(chat_id=123, text="Hello")
    assert mock_post.called
    call_json = mock_post.call_args[1]["json"]
    assert call_json["chat_id"] == 123
    assert call_json["text"] == "Hello"
    assert result["message_id"] == 5
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_poster.py -v
```
Expected: `ModuleNotFoundError: No module named 'delivery.poster'`

- [ ] **Step 3: Implement `delivery/poster.py`**

```python
# delivery/poster.py
import os
import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _bot_url(method: str) -> str:
    return TELEGRAM_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)


def _send_message(chat_id: int, text: str, reply_to_message_id: int = None) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id

    resp = requests.post(_bot_url("sendMessage"), json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["result"]


def format_post(article: dict) -> str:
    hashtags = " ".join(article.get("hashtags", []))
    return (
        f"🔹 *{article['title']}*\n\n"
        f"{article['summary']}\n\n"
        f"{hashtags}\n"
        f"🔗 {article['url']}"
    )


def post_article(user_id: int, article: dict) -> None:
    """Send one article to a user's DM. Sends a followup reply if important."""
    text = format_post(article)
    result = _send_message(chat_id=user_id, text=text)

    if article.get("is_important") and article.get("importance_detail"):
        followup = f"🧵 *Why this matters:*\n{article['importance_detail']}"
        _send_message(
            chat_id=user_id,
            text=followup,
            reply_to_message_id=result["message_id"],
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_poster.py -v
```
Expected: 4 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add delivery/poster.py tests/test_poster.py
git commit -m "feat: add Telegram poster with important-article followup"
```

---

## Chunk 4: Delivery Engine — Scheduler & GitHub Actions

### Task 9: Scheduler

**Files:**
- Create: `delivery/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_scheduler.py
import pytest
from unittest.mock import patch
import os, time

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _user(tier="free", expires=None, reminder=None):
    return {
        "user_id": 1,
        "tier": tier,
        "tier_expires_at": expires,
        "last_reminder_at": reminder,
    }


@patch("delivery.scheduler.db.execute")
def test_get_due_users_queries_by_hour_and_day(mock_execute):
    mock_execute.return_value = []
    from delivery.scheduler import get_due_deliveries
    get_due_deliveries(hour_utc=9, weekday=1)
    sql, args = mock_execute.call_args[0]
    assert "hour_utc" in sql
    assert 9 in args


@patch("delivery.scheduler.db.execute")
def test_expired_monthly_treated_as_free(mock_execute):
    expired_ts = int(time.time()) - 100
    mock_execute.return_value = [{
        "user_id": 1, "tier": "monthly", "tier_expires_at": expired_ts,
        "theme_type": "default", "theme_id": 2, "articles_per_theme": 2,
        "last_reminder_at": None,
    }]
    from delivery.scheduler import get_due_deliveries
    deliveries = get_due_deliveries(hour_utc=9, weekday=1)
    assert deliveries[0]["effective_articles_per_theme"] == 1  # free tier max


@patch("delivery.scheduler.db.execute")
def test_active_monthly_keeps_tier_limits(mock_execute):
    future_ts = int(time.time()) + 86400 * 30
    mock_execute.return_value = [{
        "user_id": 1, "tier": "monthly", "tier_expires_at": future_ts,
        "theme_type": "default", "theme_id": 2, "articles_per_theme": 2,
        "last_reminder_at": None,
    }]
    from delivery.scheduler import get_due_deliveries
    deliveries = get_due_deliveries(hour_utc=9, weekday=1)
    assert deliveries[0]["effective_articles_per_theme"] == 2


@patch("delivery.scheduler.requests.post")
@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_check_expiry_reminders_sends_message_and_updates_db(mock_execute, mock_execute_many, mock_post):
    now = int(time.time())
    expiring_soon = now + 86400  # 1 day from now (within 3-day window)
    mock_execute.return_value = [{
        "user_id": 99,
        "tier_expires_at": expiring_soon,
        "last_reminder_at": None,
    }]
    mock_post.return_value = MagicMock()

    from delivery.scheduler import check_expiry_reminders
    check_expiry_reminders(hour_utc=9)

    assert mock_post.called
    assert mock_execute_many.called
    # Verify last_reminder_at was updated for user 99
    update_sql, update_args = mock_execute_many.call_args[0][0][0]
    assert "last_reminder_at" in update_sql
    assert 99 in update_args


@patch("delivery.scheduler.db.execute")
def test_groups_by_theme(mock_execute):
    future_ts = int(time.time()) + 86400 * 30
    mock_execute.return_value = [
        {"user_id": 1, "tier": "free", "tier_expires_at": None,
         "theme_type": "default", "theme_id": 3, "articles_per_theme": 1, "last_reminder_at": None},
        {"user_id": 2, "tier": "free", "tier_expires_at": None,
         "theme_type": "default", "theme_id": 3, "articles_per_theme": 1, "last_reminder_at": None},
        {"user_id": 3, "tier": "free", "tier_expires_at": None,
         "theme_type": "custom", "theme_id": 1, "articles_per_theme": 1, "last_reminder_at": None},
    ]
    from delivery.scheduler import group_by_theme
    deliveries = mock_execute.return_value
    groups = group_by_theme(deliveries)
    assert ("default", 3) in groups
    assert len(groups[("default", 3)]) == 2
    assert ("custom", 1) in groups
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_scheduler.py -v
```
Expected: `ModuleNotFoundError: No module named 'delivery.scheduler'`

- [ ] **Step 3: Implement `delivery/scheduler.py`**

```python
# delivery/scheduler.py
import time
import db.client as db

FREE_ARTICLES_PER_THEME = 1
EXPIRY_REMINDER_WINDOW = 3 * 24 * 3600   # 3 days in seconds
REMINDER_COOLDOWN = 24 * 3600             # re-remind after 24h


def get_due_deliveries(hour_utc: int, weekday: int) -> list[dict]:
    """
    Query users scheduled for delivery at this hour on this weekday.
    weekday: 1=Mon, 2=Tue, ..., 7=Sun (ISO weekday).
    Returns list of delivery dicts with effective_articles_per_theme applied.
    """
    rows = db.execute(
        """
        SELECT
            u.user_id, u.tier, u.tier_expires_at, u.last_reminder_at,
            ut.theme_type, ut.theme_id, ut.articles_per_theme
        FROM user_schedules us
        JOIN users u ON u.user_id = us.user_id
        LEFT JOIN user_themes ut ON ut.id = us.user_theme_id
        WHERE us.hour_utc = ?
          AND EXISTS (
            SELECT 1 FROM json_each(us.days) WHERE CAST(value AS INTEGER) = ?
          )
        """,
        [hour_utc, weekday],
    )
    now = int(time.time())
    result = []
    for row in rows:
        effective_tier = row["tier"]
        if row["tier"] == "monthly" and row["tier_expires_at"] and row["tier_expires_at"] < now:
            effective_tier = "free"
            # Downgrade in DB
            db.execute_many([
                ("UPDATE users SET tier = 'free', tier_expires_at = NULL WHERE user_id = ?",
                 [row["user_id"]])
            ])

        max_articles = FREE_ARTICLES_PER_THEME if effective_tier == "free" else row["articles_per_theme"]
        result.append({**row, "effective_articles_per_theme": max_articles, "effective_tier": effective_tier})

    return result


def group_by_theme(deliveries: list[dict]) -> dict:
    """Group delivery rows by (theme_type, theme_id)."""
    groups: dict[tuple, list[dict]] = {}
    for d in deliveries:
        key = (d["theme_type"], d["theme_id"])
        groups.setdefault(key, []).append(d)
    return groups


def check_expiry_reminders(hour_utc: int) -> None:
    """
    Send renewal reminders to monthly users expiring within 3 days.
    Runs once per hourly cron. Uses last_reminder_at to avoid duplicate sends.
    """
    now = int(time.time())
    window_end = now + EXPIRY_REMINDER_WINDOW

    users = db.execute(
        """
        SELECT user_id, tier_expires_at, last_reminder_at
        FROM users
        WHERE tier = 'monthly'
          AND tier_expires_at IS NOT NULL
          AND tier_expires_at BETWEEN ? AND ?
          AND (last_reminder_at IS NULL OR last_reminder_at < ?)
        """,
        [now, window_end, now - REMINDER_COOLDOWN],
    )

    if not users:
        return

    # Import here to avoid circular dependency at module load
    import os
    import requests

    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    for user in users:
        days_left = max(0, (user["tier_expires_at"] - now) // 86400)
        text = (
            f"⏳ Your monthly subscription expires in {days_left} day(s). "
            f"Use /upgrade to renew and keep your personalized feed."
        )
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": user["user_id"], "text": text},
                timeout=10,
            )
            db.execute_many([
                ("UPDATE users SET last_reminder_at = ? WHERE user_id = ?",
                 [now, user["user_id"]])
            ])
        except Exception:
            continue
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/test_scheduler.py -v
```
Expected: 5 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add delivery/scheduler.py tests/test_scheduler.py
git commit -m "feat: add delivery scheduler with tier enforcement and expiry reminders"
```

---

### Task 10: Main delivery script & GitHub Actions workflow

**Files:**
- Create: `delivery/main.py`
- Create: `.github/workflows/deliver.yml`

- [ ] **Step 1: Create `delivery/main.py`**

This is the entry point called by GitHub Actions. No tests needed — it orchestrates already-tested modules.

```python
# delivery/main.py
"""
Main delivery orchestrator. Called by GitHub Actions every hour.
Usage: python -m delivery.main
"""
import json
import time
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

import db.client as db
from delivery.scheduler import get_due_deliveries, group_by_theme, check_expiry_reminders
from delivery.fetcher import fetch_articles
from delivery.ai import summarize_articles
from delivery import cache as theme_cache
from delivery.poster import post_article


def get_theme_info(theme_type: str, theme_id: int) -> dict | None:
    """Fetch theme details (name, hashtag, rss_feeds) from DB."""
    if theme_type == "default":
        rows = db.execute(
            "SELECT id, name, hashtag, rss_feeds FROM themes WHERE id = ? AND is_active = 1",
            [theme_id],
        )
    else:
        rows = db.execute(
            "SELECT id, name, hashtag, rss_feeds FROM custom_themes WHERE id = ?",
            [theme_id],
        )
    if not rows:
        return None
    row = rows[0]
    return {
        "id": row["id"],
        "theme_type": theme_type,
        "name": row["name"],
        "hashtag": row["hashtag"],
        "rss_feeds": json.loads(row["rss_feeds"]),
    }


def run():
    now_utc = datetime.now(timezone.utc)
    hour_utc = now_utc.hour
    weekday = now_utc.isoweekday()  # 1=Mon...7=Sun
    date_str = now_utc.strftime("%Y-%m-%d")
    quarter = theme_cache.current_quarter(hour_utc)

    print(f"[deliver] {date_str} Q{quarter} hour={hour_utc} weekday={weekday}")

    # Step 1: find users due this hour
    deliveries = get_due_deliveries(hour_utc=hour_utc, weekday=weekday)
    if not deliveries:
        print("[deliver] No users due this hour.")
        check_expiry_reminders(hour_utc)
        return

    # Step 2: group by theme
    groups = group_by_theme(deliveries)
    print(f"[deliver] {len(groups)} unique theme(s) to process for {len(deliveries)} delivery row(s)")

    all_posted_urls: list[str] = []

    for (theme_type, theme_id), users in groups.items():
        theme = get_theme_info(theme_type, theme_id)
        if not theme:
            print(f"[deliver] Theme ({theme_type}, {theme_id}) not found — skipping")
            continue

        # Step 3: cache check
        articles = theme_cache.get_cached(theme_type, theme_id, date_str, quarter)

        if articles is None:
            # Cache miss: fetch + summarize
            raw_articles = fetch_articles(theme)
            if not raw_articles:
                print(f"[deliver] No new articles for {theme['name']}")
                continue
            articles = summarize_articles(raw_articles, theme["hashtag"])
            if not articles:
                print(f"[deliver] AI returned no summaries for {theme['name']}")
                continue
            # Cache the result
            theme_cache.set_cache(theme_type, theme_id, date_str, quarter, articles)
        else:
            # Cache hit: still filter against posted_articles
            posted = {row["url"] for row in db.execute("SELECT url FROM posted_articles")}
            articles = [a for a in articles if a["url"] not in posted]

        # Step 4: fan out to each user
        for user in users:
            user_articles = articles[:user["effective_articles_per_theme"]]
            for article in user_articles:
                try:
                    post_article(user_id=user["user_id"], article=article)
                    all_posted_urls.append(article["url"])
                    time.sleep(0.1)  # avoid Telegram flood limits
                except Exception as e:
                    print(f"[deliver] Failed to post to user {user['user_id']}: {e}")

    # Step 5: mark URLs as posted (global dedup) — must run before digest_history
    if all_posted_urls:
        now_ts = int(time.time())
        statements = [
            ("INSERT OR IGNORE INTO posted_articles (url, posted_at) VALUES (?, ?)", [url, now_ts])
            for url in set(all_posted_urls)
        ]
        db.execute_many(statements)

    # Step 6: digest history for monthly users
    for (theme_type, theme_id), users in groups.items():
        theme = get_theme_info(theme_type, theme_id)
        if not theme:
            continue
        cached = theme_cache.get_cached(theme_type, theme_id, date_str, quarter)
        if not cached:
            continue
        for user in users:
            if user.get("effective_tier") != "monthly":
                continue
            user_articles = cached[:user["effective_articles_per_theme"]]
            try:
                db.execute_many([
                    (
                        "INSERT INTO digest_history "
                        "(user_id, theme_type, theme_id, theme_name, articles, sent_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        [user["user_id"], theme_type, theme_id,
                         theme["name"], json.dumps(user_articles), int(time.time())],
                    )
                ])
            except Exception as e:
                print(f"[deliver] Failed to write history for user {user['user_id']}: {e}")

    # Step 7: expiry reminders
    check_expiry_reminders(hour_utc)
    print("[deliver] Done.")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Create `.github/workflows/deliver.yml`**

```yaml
name: Deliver News Digests

on:
  schedule:
    - cron: "0 * * * *"   # every hour on the hour (UTC)
  workflow_dispatch:        # allow manual trigger

jobs:
  deliver:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run delivery
        env:
          TURSO_URL: ${{ secrets.TURSO_URL }}
          TURSO_TOKEN: ${{ secrets.TURSO_TOKEN }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
        run: python -m delivery.main
```

- [ ] **Step 3: Add all required secrets to GitHub repository**

In the repo → Settings → Secrets and variables → Actions, add:
- `TURSO_URL`
- `TURSO_TOKEN`
- `TELEGRAM_BOT_TOKEN`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`

- [ ] **Step 4: Commit**

```bash
git add delivery/main.py .github/
git commit -m "feat: add delivery orchestrator and GitHub Actions hourly cron"
```

---

## Chunk 5: Bot Core — Webhook Entry Point & /start

### Task 11: Webhook entry point & router

**Files:**
- Create: `api/__init__.py` (empty)
- Create: `api/webhook.py`
- Create: `bot/__init__.py` (empty)
- Create: `bot/router.py`
- Create: `bot/telegram.py`
- Create: `tests/bot/__init__.py` (empty)
- Create: `tests/bot/test_router.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/bot/test_router.py
import pytest
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _update(text="/start", user_id=123):
    return {
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "first_name": "Alice"},
            "chat": {"id": user_id},
            "text": text,
        }
    }


@patch("bot.commands.start.handle")
def test_router_dispatches_start(mock_handle):
    from bot.router import handle_update
    handle_update(_update("/start"))
    assert mock_handle.called


@patch("bot.commands.themes.handle")
def test_router_dispatches_themes(mock_handle):
    from bot.router import handle_update
    handle_update(_update("/themes"))
    assert mock_handle.called


def test_router_ignores_unknown_commands():
    from bot.router import handle_update
    # Should not raise
    handle_update(_update("/unknowncommand"))


def test_router_handles_missing_message_gracefully():
    from bot.router import handle_update
    handle_update({"update_id": 1})  # no message key
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_router.py -v
```

- [ ] **Step 3: Create `bot/telegram.py`** (shared Telegram API helpers)

```python
# bot/telegram.py
import os
import requests

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _url(method: str) -> str:
    return _BASE.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)


def send_message(chat_id: int, text: str, reply_markup: dict = None,
                 parse_mode: str = "Markdown") -> dict:
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode,
               "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    resp = requests.post(_url("sendMessage"), json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})


def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    requests.post(_url("answerCallbackQuery"),
                  json={"callback_query_id": callback_query_id, "text": text},
                  timeout=10)


def send_invoice(chat_id: int, title: str, description: str, payload: str,
                 currency: str, prices: list[dict]) -> dict:
    """Send a Telegram Stars payment invoice. currency must be 'XTR' for Stars."""
    data = {
        "chat_id": chat_id, "title": title, "description": description,
        "payload": payload, "currency": currency, "prices": prices,
        "provider_token": "",  # empty for Stars
    }
    resp = requests.post(_url("sendInvoice"), json=data, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", {})
```

- [ ] **Step 4: Create `bot/router.py`**

```python
# bot/router.py
from bot.commands import start, themes, schedule, upgrade, history, addtheme, settings
from bot.commands import payments as payments_cmd
import db.client as db

COMMAND_MAP = {
    "/start": start.handle,
    "/themes": themes.handle,
    "/schedule": schedule.handle,
    "/upgrade": upgrade.handle,
    "/history": history.handle,
    "/addtheme": addtheme.handle_ai,
    "/addthememanual": addtheme.handle_manual,
    "/settings": settings.handle,
}

# callback_data prefix → handler function
# Each handler receives (callback_query dict, data str)
def _handle_callback(callback_query: dict) -> None:
    data = callback_query.get("data", "")
    user_id = callback_query["from"]["id"]
    message = callback_query.get("message", {})

    if data.startswith("themes:add:"):
        _, _, theme_type, theme_id = data.split(":")
        themes.add_theme(user_id, theme_type, int(theme_id))
    elif data.startswith("themes:remove:"):
        _, _, theme_type, theme_id = data.split(":")
        themes.remove_theme(user_id, theme_type, int(theme_id))
    elif data.startswith("pay:"):
        tier = data.split(":")[1]
        payments_cmd.send_invoice(user_id, tier)
    elif data.startswith("upgrade:show"):
        upgrade.handle({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:ai"):
        addtheme.handle_ai({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:manual"):
        addtheme.handle_manual({"from": callback_query["from"], "chat": {"id": user_id}})
    elif data.startswith("addtheme:feed:"):
        idx = int(data.split(":")[2])
        addtheme.toggle_feed(user_id, idx)
    elif data == "addtheme:feeds_done":
        addtheme.feeds_done(user_id)
    # answer the callback to dismiss Telegram's loading indicator
    import bot.telegram as tg
    tg.answer_callback_query(callback_query["id"])


def _handle_pending_action(message: dict) -> bool:
    """
    If this user has a pending multi-step action, route their text to it.
    Returns True if handled, False if not.
    """
    user_id = message["from"]["id"]
    rows = db.execute(
        "SELECT action, data FROM user_pending_actions WHERE user_id = ?", [user_id]
    )
    if not rows:
        return False
    addtheme.handle_pending(message, rows[0]["action"], rows[0]["data"])
    return True


def handle_update(update: dict) -> None:
    """Route a Telegram update to the appropriate handler."""
    # callback_query (inline keyboard button press)
    if "callback_query" in update:
        _handle_callback(update["callback_query"])
        return

    message = update.get("message", {})
    if not message:
        return

    # successful_payment
    if "successful_payment" in message:
        payments_cmd.handle_successful_payment(message)
        return

    text = message.get("text", "")
    if not text:
        return

    # Check for pending multi-step action first
    if not text.startswith("/"):
        if _handle_pending_action(message):
            return

    # Extract command (strip @BotName suffix if present)
    command = text.split()[0].split("@")[0]
    handler = COMMAND_MAP.get(command)
    if handler:
        handler(message)
```

- [ ] **Step 5: Create `api/webhook.py`**

```python
# api/webhook.py
"""Vercel serverless entry point for Telegram webhook."""
import json
import sys
import os
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from bot.router import handle_update


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            update = json.loads(body)
            handle_update(update)
        except Exception as e:
            print(f"[webhook] error: {e}")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass  # suppress default HTTP logging
```

- [ ] **Step 6: Create empty `__init__.py` files for all command modules**

```bash
touch bot/__init__.py api/__init__.py tests/bot/__init__.py
mkdir -p bot/commands && touch bot/commands/__init__.py
```

- [ ] **Step 7: Create stub files for all command modules** (so router imports don't fail before they're implemented)

Each file should export a `handle` function that just passes:

```python
# bot/commands/settings.py (stub — implemented later)
def handle(message: dict) -> None:
    pass
```

Create stubs for: `themes.py`, `schedule.py`, `upgrade.py`, `history.py`, `addtheme.py`, `settings.py`, `payments.py`.

For `addtheme.py`:
```python
# bot/commands/addtheme.py (stub)
def handle_ai(message: dict) -> None:
    pass

def handle_manual(message: dict) -> None:
    pass
```

For `payments.py`:
```python
# bot/commands/payments.py (stub)
def handle_successful_payment(message: dict) -> None:
    pass
```

- [ ] **Step 8: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_router.py -v
```
Expected: 4 tests PASSED

- [ ] **Step 9: Commit**

```bash
git add api/ bot/ tests/bot/
git commit -m "feat: add Vercel webhook entry point and update router"
```

---

### Task 12: /start command

**Files:**
- Create (replace stub): `bot/commands/start.py`
- Create: `tests/bot/test_start.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/bot/test_start.py
import pytest
from unittest.mock import patch, MagicMock
import os, time

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _message(user_id=123, first_name="Alice"):
    return {"from": {"id": user_id, "first_name": first_name}, "chat": {"id": user_id}}


@patch("bot.commands.start.tg.send_message")
@patch("bot.commands.start.db.execute_many")
@patch("bot.commands.start.db.execute", return_value=[])
def test_start_creates_new_user(mock_execute, mock_execute_many, mock_send):
    from bot.commands.start import handle
    handle(_message())
    # Should insert new user
    inserts = [call[0][0] for call in mock_execute_many.call_args_list]
    assert any("INSERT" in str(s) for s in inserts)
    assert mock_send.called


@patch("bot.commands.start.tg.send_message")
@patch("bot.commands.start.db.execute_many")
@patch("bot.commands.start.db.execute", return_value=[{"user_id": 123, "tier": "free"}])
def test_start_does_not_duplicate_existing_user(mock_execute, mock_execute_many, mock_send):
    from bot.commands.start import handle
    handle(_message())
    # Should not insert again
    for call in mock_execute_many.call_args_list:
        statements = call[0][0]
        for sql, _ in statements:
            assert "INSERT" not in sql.upper()
    assert mock_send.called
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_start.py -v
```

- [ ] **Step 3: Implement `bot/commands/start.py`**

```python
# bot/commands/start.py
import time
import db.client as db
import bot.telegram as tg

WELCOME = """\
👋 *Welcome to NewsBot!*

I deliver personalized news digests straight to your DMs — summarized by AI, on your schedule.

*Free tier includes:*
• Up to 5 topic themes
• 1 article per theme per digest
• Custom delivery schedule (days + time)

Use the buttons below to get started, or type /upgrade to see paid options.
"""


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    first_name = message["from"].get("first_name", "there")

    # Register user if not exists
    existing = db.execute("SELECT user_id FROM users WHERE user_id = ?", [user_id])
    if not existing:
        db.execute_many([
            (
                "INSERT INTO users (user_id, tier, created_at, stars_paid) VALUES (?, 'free', ?, 0)",
                [user_id, int(time.time())],
            )
        ])

    keyboard = {
        "inline_keyboard": [
            [{"text": "📰 Browse Themes", "callback_data": "themes:browse"}],
            [{"text": "⏰ Set Schedule", "callback_data": "schedule:setup"}],
            [{"text": "⭐ View Paid Plans", "callback_data": "upgrade:show"}],
        ]
    }
    tg.send_message(chat_id=user_id, text=WELCOME, reply_markup=keyboard)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_start.py -v
```
Expected: 2 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/commands/start.py tests/bot/test_start.py
git commit -m "feat: implement /start command with user registration"
```

---

## Chunk 6: Bot — /themes & /schedule Commands

### Task 13: /themes command

**Files:**
- Create (replace stub): `bot/commands/themes.py`
- Create: `tests/bot/test_themes.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/bot/test_themes.py
import pytest
from unittest.mock import patch
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")

ALL_THEMES = [
    {"id": 1, "name": "Technology", "hashtag": "#tech"},
    {"id": 2, "name": "AI", "hashtag": "#ai"},
]
USER_THEMES = [{"theme_type": "default", "theme_id": 1}]


@patch("bot.commands.themes.tg.send_message")
@patch("bot.commands.themes.db.execute", side_effect=[ALL_THEMES, USER_THEMES])
def test_themes_shows_active_themes(mock_execute, mock_send):
    from bot.commands.themes import handle
    handle({"from": {"id": 1}, "chat": {"id": 1}})
    assert mock_send.called
    text = mock_send.call_args[1]["text"] or mock_send.call_args[0][1]
    assert "Technology" in text or mock_send.call_args[1].get("reply_markup")


@patch("bot.commands.themes.tg.send_message")
@patch("bot.commands.themes.db.execute")
@patch("bot.commands.themes.db.execute_many")
def test_add_theme_respects_free_tier_limit(mock_execute_many, mock_execute, mock_send):
    # User already has 5 themes
    mock_execute.side_effect = [
        ALL_THEMES,
        [{"theme_type": "default", "theme_id": i} for i in range(1, 6)],  # 5 themes
        [{"tier": "free"}],
    ]
    from bot.commands.themes import add_theme
    add_theme(user_id=1, theme_type="default", theme_id=6)
    # Should NOT insert
    assert not mock_execute_many.called


@patch("bot.commands.themes.tg.send_message")
@patch("bot.commands.themes.db.execute")
@patch("bot.commands.themes.db.execute_many")
def test_add_theme_inserts_when_under_limit(mock_execute_many, mock_execute, mock_send):
    mock_execute.side_effect = [
        [{"theme_type": "default", "theme_id": 1}],  # 1 existing theme
        [{"tier": "free"}],
    ]
    from bot.commands.themes import add_theme
    add_theme(user_id=1, theme_type="default", theme_id=2)
    assert mock_execute_many.called
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_themes.py -v
```

- [ ] **Step 3: Implement `bot/commands/themes.py`**

```python
# bot/commands/themes.py
import db.client as db
import bot.telegram as tg

TIER_THEME_LIMITS = {"free": 5, "one_time": 6, "monthly": 9}


def _get_user_tier(user_id: int) -> str:
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    return rows[0]["tier"] if rows else "free"


def _get_user_theme_count(user_id: int) -> int:
    rows = db.execute("SELECT COUNT(*) as c FROM user_themes WHERE user_id = ?", [user_id])
    return rows[0]["c"] if rows else 0


def _get_user_theme_ids(user_id: int) -> set[tuple]:
    rows = db.execute(
        "SELECT theme_type, theme_id FROM user_themes WHERE user_id = ?", [user_id]
    )
    return {(r["theme_type"], r["theme_id"]) for r in rows}


def add_theme(user_id: int, theme_type: str, theme_id: int) -> bool:
    """Add a theme to a user's subscription. Returns True if added, False if at limit."""
    tier = _get_user_tier(user_id)
    limit = TIER_THEME_LIMITS.get(tier, 5)
    count = _get_user_theme_count(user_id)
    if count >= limit:
        tg.send_message(
            chat_id=user_id,
            text=f"⚠️ You've reached the {limit}-theme limit for your plan. "
                 f"Use /upgrade to add more themes.",
        )
        return False
    articles = 1 if tier == "free" else 2
    db.execute_many([
        (
            "INSERT INTO user_themes (user_id, theme_type, theme_id, articles_per_theme) "
            "VALUES (?, ?, ?, ?)",
            [user_id, theme_type, theme_id, articles],
        )
    ])
    return True


def remove_theme(user_id: int, theme_type: str, theme_id: int) -> None:
    db.execute_many([
        (
            "DELETE FROM user_themes WHERE user_id = ? AND theme_type = ? AND theme_id = ?",
            [user_id, theme_type, theme_id],
        )
    ])


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    all_themes = db.execute(
        "SELECT id, name, hashtag FROM themes WHERE is_active = 1 ORDER BY id"
    )
    subscribed = _get_user_theme_ids(user_id)

    buttons = []
    for t in all_themes:
        is_sub = ("default", t["id"]) in subscribed
        label = f"{'✅' if is_sub else '➕'} {t['name']} {t['hashtag']}"
        action = "remove" if is_sub else "add"
        buttons.append([{
            "text": label,
            "callback_data": f"themes:{action}:default:{t['id']}",
        }])

    tier = _get_user_tier(user_id)
    if tier in ("one_time", "monthly"):
        buttons.append([{"text": "➕ Add Custom Theme (AI)", "callback_data": "addtheme:ai"}])
        buttons.append([{"text": "➕ Add Custom Theme (Manual)", "callback_data": "addtheme:manual"}])

    tg.send_message(
        chat_id=user_id,
        text="📰 *Your Themes*\n\nTap to subscribe or unsubscribe:",
        reply_markup={"inline_keyboard": buttons},
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_themes.py -v
```
Expected: 3 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/commands/themes.py tests/bot/test_themes.py
git commit -m "feat: implement /themes command with tier-aware limits"
```

---

### Task 14: /schedule command

**Files:**
- Create (replace stub): `bot/commands/schedule.py`
- Create: `tests/bot/test_schedule.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/bot/test_schedule.py
import pytest
from unittest.mock import patch
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


@patch("bot.commands.schedule.tg.send_message")
@patch("bot.commands.schedule.db.execute", return_value=[{"tier": "free"}])
def test_schedule_shows_day_picker(mock_execute, mock_send):
    from bot.commands.schedule import handle
    handle({"from": {"id": 1}, "chat": {"id": 1}})
    assert mock_send.called
    markup = mock_send.call_args[1].get("reply_markup", {})
    # Should show day buttons
    flat_buttons = [b for row in markup.get("inline_keyboard", []) for b in row]
    labels = [b["text"] for b in flat_buttons]
    assert any("Mon" in l or "Tue" in l for l in labels)


@patch("bot.commands.schedule.tg.send_message")
@patch("bot.commands.schedule.db.execute_many")
def test_set_global_schedule_upserts(mock_execute_many, mock_send):
    from bot.commands.schedule import set_global_schedule
    set_global_schedule(user_id=1, days=[1, 3, 5], hour_utc=9)
    assert mock_execute_many.called
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "user_schedules" in sql
    assert 9 in args
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_schedule.py -v
```

- [ ] **Step 3: Implement `bot/commands/schedule.py`**

```python
# bot/commands/schedule.py
import json
import db.client as db
import bot.telegram as tg

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # index+1 = ISO weekday


def set_global_schedule(user_id: int, days: list[int], hour_utc: int) -> None:
    """Upsert the global (all-themes) schedule for a user."""
    # Delete existing global schedule rows (user_theme_id IS NULL)
    db.execute_many([
        ("DELETE FROM user_schedules WHERE user_id = ? AND user_theme_id IS NULL", [user_id]),
        (
            "INSERT INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (?, NULL, ?, ?)",
            [user_id, json.dumps(days), hour_utc],
        ),
    ])


def set_theme_schedule(user_id: int, user_theme_id: int, days: list[int], hour_utc: int) -> None:
    """Upsert a per-theme schedule for a paid user."""
    db.execute_many([
        ("DELETE FROM user_schedules WHERE user_id = ? AND user_theme_id = ?",
         [user_id, user_theme_id]),
        (
            "INSERT INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (?, ?, ?, ?)",
            [user_id, user_theme_id, json.dumps(days), hour_utc],
        ),
    ])


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"

    # Show day selection keyboard (Mon=1 … Sun=7)
    day_buttons = [
        [{"text": day, "callback_data": f"schedule:day:{i + 1}"}]
        for i, day in enumerate(DAYS)
    ]
    day_buttons.append([{"text": "✅ Done selecting days", "callback_data": "schedule:days_done"}])

    text = (
        "⏰ *Set Your Schedule*\n\n"
        "Select the days you want to receive your digest.\n"
        "_(Tap multiple, then tap Done)_"
    )
    if tier in ("one_time", "monthly"):
        text += "\n\n💡 _You can also set per-theme schedules after this._"

    tg.send_message(chat_id=user_id, text=text, reply_markup={"inline_keyboard": day_buttons})
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_schedule.py -v
```
Expected: 2 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/commands/schedule.py tests/bot/test_schedule.py
git commit -m "feat: implement /schedule command with global and per-theme schedule support"
```

---

## Chunk 7: Bot — Upgrade, Payments, History, AddTheme & Settings

### Task 15: /upgrade & Stars payments

**Files:**
- Create (replace stub): `bot/commands/upgrade.py`
- Create (replace stub): `bot/commands/payments.py`
- Create: `tests/bot/test_payments.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/bot/test_payments.py
import pytest
from unittest.mock import patch, MagicMock
import os, time

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("STARS_ONETIME_PRICE", "200")
os.environ.setdefault("STARS_MONTHLY_PRICE", "100")


@patch("bot.commands.upgrade.tg.send_message")
@patch("bot.commands.upgrade.db.execute", return_value=[{"tier": "free"}])
def test_upgrade_sends_comparison_message(mock_execute, mock_send):
    from bot.commands.upgrade import handle
    handle({"from": {"id": 1}, "chat": {"id": 1}})
    assert mock_send.called
    text = mock_send.call_args[1].get("text", "") or mock_send.call_args[0][1]
    assert "One-time" in text or "Monthly" in text or "Stars" in text


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_successful_payment_one_time_sets_tier(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 1},
        "chat": {"id": 1},
        "successful_payment": {
            "invoice_payload": "tier:one_time",
            "total_amount": 200,
            "currency": "XTR",
        }
    })
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "one_time" in str(args)


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_successful_payment_monthly_sets_expiry(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 1},
        "chat": {"id": 1},
        "successful_payment": {
            "invoice_payload": "tier:monthly",
            "total_amount": 100,
            "currency": "XTR",
        }
    })
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "monthly" in str(args)
    # tier_expires_at should be set ~30 days from now
    expires = [a for a in args if isinstance(a, int) and a > int(time.time())]
    assert len(expires) > 0


@patch("bot.commands.payments.tg.send_invoice")
def test_send_invoice_uses_xtr_currency(mock_send_invoice):
    from bot.commands.payments import send_invoice
    send_invoice(user_id=1, tier="one_time")
    assert mock_send_invoice.called
    call_kwargs = mock_send_invoice.call_args[1]
    assert call_kwargs["currency"] == "XTR"
    assert call_kwargs["payload"] == "tier:one_time"


@patch("bot.commands.payments.tg.send_invoice")
def test_send_invoice_monthly_uses_xtr_currency(mock_send_invoice):
    from bot.commands.payments import send_invoice
    send_invoice(user_id=1, tier="monthly")
    call_kwargs = mock_send_invoice.call_args[1]
    assert call_kwargs["currency"] == "XTR"
    assert call_kwargs["payload"] == "tier:monthly"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_payments.py -v
```

- [ ] **Step 3: Implement `bot/commands/upgrade.py`**

```python
# bot/commands/upgrade.py
import os
import db.client as db
import bot.telegram as tg

COMPARISON = """\
⭐ *NewsBot Plans*

*Free*
• Up to 5 themes
• 1 article per theme
• One shared schedule

*One-time ({onetime} Stars)*
• Up to 6 themes
• 1 custom theme
• Per-theme schedules

*Monthly ({monthly} Stars/month)*
• Up to 9 themes
• Up to 3 custom themes
• 1–2 articles per theme
• Digest history (/history)
• Per-theme custom schedules
"""


def handle(message: dict) -> None:
    user_id = message["from"]["id"]
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"

    onetime = os.environ.get("STARS_ONETIME_PRICE", "200")
    monthly = os.environ.get("STARS_MONTHLY_PRICE", "100")

    text = COMPARISON.format(onetime=onetime, monthly=monthly)

    buttons = []
    if tier == "free":
        buttons.append([{"text": f"⭐ One-time — {onetime} Stars", "callback_data": "pay:one_time"}])
        buttons.append([{"text": f"⭐ Monthly — {monthly} Stars/mo", "callback_data": "pay:monthly"}])
    elif tier == "one_time":
        buttons.append([{"text": f"⭐ Upgrade to Monthly — {monthly} Stars/mo", "callback_data": "pay:monthly"}])
    else:
        text += "\n✅ _You are on the Monthly plan._"

    tg.send_message(
        chat_id=user_id, text=text,
        reply_markup={"inline_keyboard": buttons} if buttons else None,
    )
```

- [ ] **Step 4: Implement `bot/commands/payments.py`**

```python
# bot/commands/payments.py
import os
import time
import db.client as db
import bot.telegram as tg

MONTHLY_DURATION = 30 * 24 * 3600  # 30 days


def send_invoice(user_id: int, tier: str) -> None:
    """Send a Stars payment invoice for one_time or monthly tier."""
    if tier == "one_time":
        price = int(os.environ.get("STARS_ONETIME_PRICE", "200"))
        title = "NewsBot — One-time Upgrade"
        description = "Unlock 6 themes, 1 custom theme, per-theme schedules. Yours forever."
    else:
        price = int(os.environ.get("STARS_MONTHLY_PRICE", "100"))
        title = "NewsBot — Monthly Subscription"
        description = "Unlock all features: 9 themes, 3 custom themes, digest history."

    tg.send_invoice(
        chat_id=user_id,
        title=title,
        description=description,
        payload=f"tier:{tier}",
        currency="XTR",
        prices=[{"label": title, "amount": price}],
    )


def handle_successful_payment(message: dict) -> None:
    user_id = message["from"]["id"]
    payment = message["successful_payment"]
    payload = payment["invoice_payload"]  # e.g. "tier:one_time"
    tier = payload.split(":")[1]
    amount = payment["total_amount"]
    now = int(time.time())

    if tier == "one_time":
        db.execute_many([
            (
                "UPDATE users SET tier = 'one_time', stars_paid = stars_paid + ? WHERE user_id = ?",
                [amount, user_id],
            )
        ])
        tg.send_message(
            chat_id=user_id,
            text="🎉 *One-time upgrade activated!* You now have access to 6 themes and custom themes.",
        )
    elif tier == "monthly":
        expires_at = now + MONTHLY_DURATION
        db.execute_many([
            (
                "UPDATE users SET tier = 'monthly', tier_expires_at = ?, stars_paid = stars_paid + ? "
                "WHERE user_id = ?",
                [expires_at, amount, user_id],
            )
        ])
        tg.send_message(
            chat_id=user_id,
            text="🎉 *Monthly subscription activated!* All features unlocked for 30 days.",
        )
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_payments.py -v
```
Expected: 5 tests PASSED

- [ ] **Step 6: Commit**

```bash
git add bot/commands/upgrade.py bot/commands/payments.py tests/bot/test_payments.py
git commit -m "feat: implement /upgrade and Stars payment flow"
```

---

### Task 16: /history command

**Files:**
- Create (replace stub): `bot/commands/history.py`

- [ ] **Step 1: Implement `bot/commands/history.py`** (no dedicated test — uses mocked DB from router tests)

```python
# bot/commands/history.py
import json
from datetime import datetime, timezone
import db.client as db
import bot.telegram as tg

MAX_HISTORY = 30


def handle(message: dict) -> None:
    user_id = message["from"]["id"]

    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"

    if tier != "monthly":
        tg.send_message(
            chat_id=user_id,
            text="📚 Digest history is available on the *Monthly plan*.\n\nUse /upgrade to unlock.",
        )
        return

    history = db.execute(
        "SELECT theme_name, articles, sent_at FROM digest_history "
        "WHERE user_id = ? ORDER BY sent_at DESC LIMIT ?",
        [user_id, MAX_HISTORY],
    )

    if not history:
        tg.send_message(chat_id=user_id, text="📭 No digest history yet. Check back after your first delivery.")
        return

    lines = []
    for row in history:
        dt = datetime.fromtimestamp(row["sent_at"], tz=timezone.utc).strftime("%b %d %H:%M UTC")
        articles = json.loads(row["articles"])
        titles = ", ".join(a["title"][:40] for a in articles[:2])
        lines.append(f"• *{row['theme_name']}* — {dt}\n  _{titles}_")

    text = "📚 *Your Digest History* (last 30)\n\n" + "\n\n".join(lines)
    tg.send_message(chat_id=user_id, text=text)
```

- [ ] **Step 2: Commit**

- [ ] **Step 3: Write tests for `/history`**

Add to `tests/bot/test_history.py`:

```python
# tests/bot/test_history.py
import pytest
from unittest.mock import patch
import json, os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _msg(user_id=1):
    return {"from": {"id": user_id}, "chat": {"id": user_id}}


@patch("bot.commands.history.tg.send_message")
@patch("bot.commands.history.db.execute", return_value=[{"tier": "free"}])
def test_history_blocked_for_free_users(mock_execute, mock_send):
    from bot.commands.history import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "Monthly" in text or "upgrade" in text.lower()


@patch("bot.commands.history.tg.send_message")
@patch("bot.commands.history.db.execute", side_effect=[
    [{"tier": "monthly"}],  # user query
    [],                      # history query returns empty
])
def test_history_empty_message_for_monthly_with_no_history(mock_execute, mock_send):
    from bot.commands.history import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "No digest history" in text or "empty" in text.lower() or "yet" in text.lower()


@patch("bot.commands.history.tg.send_message")
@patch("bot.commands.history.db.execute", side_effect=[
    [{"tier": "monthly"}],
    [{"theme_name": "AI", "articles": json.dumps([{"title": "Test Article"}]), "sent_at": 1700000000}],
])
def test_history_shows_entries_for_monthly(mock_execute, mock_send):
    from bot.commands.history import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "AI" in text
    assert "Test Article" in text
```

- [ ] **Step 4: Run history tests**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/bot/test_history.py -v
```
Expected: 3 tests PASSED

- [ ] **Step 5: Commit**

```bash
git add bot/commands/history.py tests/bot/test_history.py
git commit -m "feat: implement /history command (monthly tier)"
```

---

### Task 17: /addtheme & /addthememanual commands

**Files:**
- Create (replace stub): `bot/commands/addtheme.py`

- [ ] **Step 1: Implement `bot/commands/addtheme.py`**

```python
# bot/commands/addtheme.py
import json
import time
import feedparser
import db.client as db
import bot.telegram as tg
import google.generativeai as genai
import os

RSS_SUGGEST_PROMPT = """\
Suggest 4-5 high-quality RSS feed URLs for the topic: "{topic}"
Return ONLY a JSON array of objects, each with "name" (feed source name) and "url" (RSS URL).
Example: [{{"name": "Example Blog", "url": "https://example.com/feed.xml"}}]
No explanation, no markdown.
"""


def _suggest_feeds(topic: str) -> list[dict]:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel("gemini-2.5-flash")
    resp = model.generate_content(RSS_SUGGEST_PROMPT.format(topic=topic))
    text = resp.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def _validate_feed(url: str) -> bool:
    try:
        feed = feedparser.parse(url)
        return len(feed.entries) > 0
    except Exception:
        return False


def _user_custom_theme_count(user_id: int) -> int:
    rows = db.execute(
        "SELECT COUNT(*) as c FROM user_themes WHERE user_id = ? AND theme_type = 'custom'",
        [user_id],
    )
    return rows[0]["c"] if rows else 0


def _tier_custom_limit(tier: str) -> int:
    return {"one_time": 1, "monthly": 3}.get(tier, 0)


def _check_access(user_id: int) -> tuple[bool, str]:
    rows = db.execute("SELECT tier FROM users WHERE user_id = ?", [user_id])
    tier = rows[0]["tier"] if rows else "free"
    if tier not in ("one_time", "monthly"):
        return False, "free"
    limit = _tier_custom_limit(tier)
    count = _user_custom_theme_count(user_id)
    if count >= limit:
        return False, tier
    return True, tier


def _set_pending(user_id: int, action: str, data: dict = None) -> None:
    db.execute_many([
        (
            "INSERT OR REPLACE INTO user_pending_actions (user_id, action, data, created_at) "
            "VALUES (?, ?, ?, ?)",
            [user_id, action, json.dumps(data or {}), int(time.time())],
        )
    ])


def _clear_pending(user_id: int) -> None:
    db.execute_many([
        ("DELETE FROM user_pending_actions WHERE user_id = ?", [user_id])
    ])


def _save_custom_theme(user_id: int, name: str, hashtag: str,
                        rss_feeds: list[str], ai_suggested: bool) -> None:
    """Insert custom theme into custom_themes and link it in user_themes."""
    rows = db.execute(
        "INSERT INTO custom_themes (user_id, name, hashtag, rss_feeds, ai_suggested) "
        "VALUES (?, ?, ?, ?, ?) RETURNING id",
        [user_id, name, hashtag, json.dumps(rss_feeds), 1 if ai_suggested else 0],
    )
    # RETURNING not supported by all Turso versions — use lastrowid workaround:
    # Instead, fetch the newly inserted row:
    rows = db.execute(
        "SELECT id FROM custom_themes WHERE user_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
        [user_id, name],
    )
    custom_id = rows[0]["id"]
    db.execute_many([
        (
            "INSERT INTO user_themes (user_id, theme_type, theme_id, articles_per_theme) "
            "VALUES (?, 'custom', ?, 1)",
            [user_id, custom_id],
        )
    ])


def handle_ai(message: dict) -> None:
    """Step 1 of AI flow: prompt user to describe topic, set pending action."""
    user_id = message["from"]["id"]
    allowed, _ = _check_access(user_id)
    if not allowed:
        tg.send_message(chat_id=user_id, text="🔒 Custom themes require a paid plan. Use /upgrade.")
        return
    _set_pending(user_id, "addtheme_ai_topic")
    tg.send_message(
        chat_id=user_id,
        text='🔍 *Add Custom Theme*\n\nDescribe the topic you want to follow:\n_(e.g. "electric vehicles", "NBA", "web security")_',
    )


def handle_manual(message: dict) -> None:
    """Step 1 of manual flow: prompt for RSS URLs, set pending action."""
    user_id = message["from"]["id"]
    allowed, _ = _check_access(user_id)
    if not allowed:
        tg.send_message(chat_id=user_id, text="🔒 Custom themes require a paid plan. Use /upgrade.")
        return
    _set_pending(user_id, "addtheme_manual_urls")
    tg.send_message(
        chat_id=user_id,
        text="📋 *Add Custom Theme (Manual)*\n\nPaste RSS feed URLs, one per line:",
    )


def handle_pending(message: dict, action: str, data_json: str) -> None:
    """
    Called by router when user sends a non-command message and has a pending action.
    Routes to the correct step based on action value.
    """
    user_id = message["from"]["id"]
    text = message.get("text", "").strip()
    data = json.loads(data_json or "{}")

    if action == "addtheme_ai_topic":
        # User just sent the topic description → call AI, show feed choices
        try:
            feeds = _suggest_feeds(text)
        except Exception:
            tg.send_message(chat_id=user_id, text="❌ Could not fetch feed suggestions. Try again later.")
            _clear_pending(user_id)
            return
        buttons = [
            [{"text": f"{'✅' if i == 0 else '➕'} {f['name']}", "callback_data": f"addtheme:feed:{i}"}]
            for i, f in enumerate(feeds)
        ]
        buttons.append([{"text": "✅ Done — name this theme", "callback_data": "addtheme:feeds_done"}])
        _set_pending(user_id, "addtheme_ai_feeds", {"feeds": feeds, "selected": [0]})
        tg.send_message(
            chat_id=user_id,
            text="Here are suggested feeds. Tap to toggle, then tap Done:",
            reply_markup={"inline_keyboard": buttons},
        )

    elif action == "addtheme_ai_name":
        # User sent the theme name → save
        feeds = data.get("feeds", [])
        selected = data.get("selected", [0])
        urls = [feeds[i]["url"] for i in selected if i < len(feeds)]
        hashtag = "#" + text.lower().replace(" ", "")[:15]
        _save_custom_theme(user_id, text, hashtag, urls, ai_suggested=True)
        _clear_pending(user_id)
        tg.send_message(chat_id=user_id, text=f"✅ Theme *{text}* added! Use /themes to manage it.")

    elif action == "addtheme_manual_urls":
        # User sent RSS URLs → validate, ask for name
        urls = [line.strip() for line in text.splitlines() if line.strip().startswith("http")]
        if not urls:
            tg.send_message(chat_id=user_id, text="❌ No valid URLs found. Send URLs starting with http.")
            return
        valid = [u for u in urls if _validate_feed(u)]
        if not valid:
            tg.send_message(chat_id=user_id, text="❌ None returned valid RSS entries. Check URLs and retry.")
            return
        _set_pending(user_id, "addtheme_manual_name", {"urls": valid})
        tg.send_message(
            chat_id=user_id,
            text=f"✅ {len(valid)} feed(s) validated. What should this theme be called?",
        )

    elif action == "addtheme_manual_name":
        # User sent the theme name → save
        urls = data.get("urls", [])
        hashtag = "#" + text.lower().replace(" ", "")[:15]
        _save_custom_theme(user_id, text, hashtag, urls, ai_suggested=False)
        _clear_pending(user_id)
        tg.send_message(chat_id=user_id, text=f"✅ Theme *{text}* added! Use /themes to manage it.")


def toggle_feed(user_id: int, feed_idx: int) -> None:
    """Toggle a feed selection in the addtheme_ai_feeds pending state."""
    rows = db.execute(
        "SELECT data FROM user_pending_actions WHERE user_id = ? AND action = 'addtheme_ai_feeds'",
        [user_id],
    )
    if not rows:
        return
    data = json.loads(rows[0]["data"])
    selected: list = data.get("selected", [])
    if feed_idx in selected:
        selected.remove(feed_idx)
    else:
        selected.append(feed_idx)
    data["selected"] = selected
    _set_pending(user_id, "addtheme_ai_feeds", data)

    # Redraw buttons with updated checkmarks
    feeds = data.get("feeds", [])
    buttons = [
        [{"text": f"{'✅' if i in selected else '➕'} {f['name']}", "callback_data": f"addtheme:feed:{i}"}]
        for i, f in enumerate(feeds)
    ]
    buttons.append([{"text": "✅ Done — name this theme", "callback_data": "addtheme:feeds_done"}])
    tg.send_message(
        chat_id=user_id,
        text="Toggle feeds, then tap Done:",
        reply_markup={"inline_keyboard": buttons},
    )


def feeds_done(user_id: int) -> None:
    """User confirmed feed selection → ask for theme name."""
    rows = db.execute(
        "SELECT data FROM user_pending_actions WHERE user_id = ? AND action = 'addtheme_ai_feeds'",
        [user_id],
    )
    if not rows:
        return
    data = json.loads(rows[0]["data"])
    _set_pending(user_id, "addtheme_ai_name", data)
    tg.send_message(
        chat_id=user_id,
        text="What should this theme be called? _(e.g. \"Electric Vehicles\")_",
    )
```

- [ ] **Step 2: Commit**

```bash
git add bot/commands/addtheme.py
git commit -m "feat: implement /addtheme (AI-suggested) and /addthememanual commands"
```

---

### Task 18: /settings command

**Files:**
- Create (replace stub): `bot/commands/settings.py`

- [ ] **Step 1: Implement `bot/commands/settings.py`**

```python
# bot/commands/settings.py
import json
from datetime import datetime, timezone
import db.client as db
import bot.telegram as tg


def handle(message: dict) -> None:
    user_id = message["from"]["id"]

    user = db.execute("SELECT tier, tier_expires_at FROM users WHERE user_id = ?", [user_id])
    if not user:
        tg.send_message(chat_id=user_id, text="Please /start the bot first.")
        return

    tier = user[0]["tier"]
    expires = user[0]["tier_expires_at"]

    themes = db.execute(
        """
        SELECT ut.theme_type, ut.theme_id, ut.articles_per_theme,
               t.name as default_name, ct.name as custom_name
        FROM user_themes ut
        LEFT JOIN themes t ON ut.theme_type = 'default' AND t.id = ut.theme_id
        LEFT JOIN custom_themes ct ON ut.theme_type = 'custom' AND ct.id = ut.theme_id
        WHERE ut.user_id = ?
        """,
        [user_id],
    )

    schedules = db.execute(
        "SELECT days, hour_utc, user_theme_id FROM user_schedules WHERE user_id = ?",
        [user_id],
    )

    tier_label = {"free": "Free", "one_time": "One-time", "monthly": "Monthly"}.get(tier, tier)
    if tier == "monthly" and expires:
        exp_dt = datetime.fromtimestamp(expires, tz=timezone.utc).strftime("%b %d, %Y")
        tier_label += f" (renews {exp_dt})"

    theme_lines = []
    for t in themes:
        name = t["default_name"] or t["custom_name"] or "?"
        tag = "(custom)" if t["theme_type"] == "custom" else ""
        theme_lines.append(f"  • {name} {tag} — {t['articles_per_theme']} article(s)/delivery")

    schedule_lines = []
    for s in schedules:
        days = json.loads(s["days"])
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        day_str = ", ".join(day_names[d - 1] for d in days)
        scope = "All themes" if s["user_theme_id"] is None else f"Theme {s['user_theme_id']}"
        schedule_lines.append(f"  • {scope}: {day_str} at {s['hour_utc']:02d}:00 UTC")

    text = (
        f"⚙️ *Your Settings*\n\n"
        f"*Plan:* {tier_label}\n\n"
        f"*Themes ({len(themes)}):*\n" + ("\n".join(theme_lines) or "  None set") + "\n\n"
        f"*Schedule:*\n" + ("\n".join(schedule_lines) or "  None set")
    )

    buttons = [
        [{"text": "📰 Manage Themes", "callback_data": "themes:browse"}],
        [{"text": "⏰ Change Schedule", "callback_data": "schedule:setup"}],
    ]
    if tier == "free":
        buttons.append([{"text": "⭐ Upgrade Plan", "callback_data": "upgrade:show"}])

    tg.send_message(chat_id=user_id, text=text, reply_markup={"inline_keyboard": buttons})
```

- [ ] **Step 2: Commit**

```bash
git add bot/commands/settings.py
git commit -m "feat: implement /settings overview command"
```

---

### Task 19: Register Telegram webhook with Vercel URL

After deploying to Vercel:

- [ ] **Step 1: Deploy to Vercel**

```bash
# Install Vercel CLI if not present
npm i -g vercel
vercel --prod
```

Note the production URL, e.g. `https://telegram-news-bot.vercel.app`

- [ ] **Step 2: Add environment variables in Vercel dashboard**

Settings → Environment Variables → add all variables from `.env.example`:
`TURSO_URL`, `TURSO_TOKEN`, `TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `STARS_ONETIME_PRICE`, `STARS_MONTHLY_PRICE`

- [ ] **Step 3: Register the webhook with Telegram**

```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://telegram-news-bot.vercel.app/webhook"}'
```

Expected response: `{"ok":true,"result":true,"description":"Webhook was set"}`

- [ ] **Step 4: Initialize Turso schema and seed themes**

```bash
python db/init_db.py
python db/seed_themes.py
```

- [ ] **Step 5: Run full test suite**

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/ -v
```
Expected: All tests PASSED

- [ ] **Step 6: Trigger a manual delivery run**

In GitHub → Actions → "Deliver News Digests" → Run workflow.

Check workflow logs confirm at least one theme was processed.

- [ ] **Step 7: Final commit**

```bash
git add .
git commit -m "chore: complete initial implementation — all modules wired up"
```

---

## Run All Tests

```bash
/c/Users/TopAide/AppData/Local/Programs/Python/Python313/Scripts/pytest.exe tests/ -v --tb=short
```

Expected: All tests pass across `test_db_client`, `test_fetcher`, `test_cache`, `test_ai`, `test_poster`, `test_scheduler`, `bot/test_router`, `bot/test_start`, `bot/test_themes`, `bot/test_schedule`, `bot/test_payments`, `bot/test_history`.
