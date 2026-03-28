import pytest
from unittest.mock import patch, MagicMock
import os, time, json, sqlite3

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


# ---------------------------------------------------------------------------
# Helpers: run the real get_due_deliveries SQL against an in-memory SQLite DB
# ---------------------------------------------------------------------------

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")


def _make_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with open(_SCHEMA_PATH) as f:
        conn.executescript(f.read())
    return conn


def _get_due_rows(conn, hour_utc: int, weekday: int) -> list[dict]:
    """Run the scheduler query directly on a SQLite connection."""
    cur = conn.execute(
        """
        SELECT
            u.user_id, u.tier, u.tier_expires_at, u.last_reminder_at,
            ut.theme_type, ut.theme_id, ut.articles_per_theme
        FROM user_schedules us
        JOIN users u ON u.user_id = us.user_id
        JOIN user_themes ut ON (
            (us.user_theme_id IS NOT NULL AND ut.id = us.user_theme_id)
            OR (us.user_theme_id IS NULL AND ut.user_id = u.user_id)
        )
        WHERE us.hour_utc = ?
          AND EXISTS (
            SELECT 1 FROM json_each(us.days) WHERE CAST(value AS INTEGER) = ?
          )
        """,
        [hour_utc, weekday],
    )
    return [dict(row) for row in cur.fetchall()]


def test_global_schedule_expands_to_all_user_themes():
    """A NULL user_theme_id (global schedule) must yield one row per subscribed theme."""
    conn = _make_db()
    now = int(time.time())
    conn.execute("INSERT INTO users (user_id, tier, created_at) VALUES (1, 'free', ?)", [now])
    conn.execute("INSERT INTO themes (id, name, hashtag, rss_feeds, is_active) VALUES (10, 'Tech', '#tech', '[]', 1)")
    conn.execute("INSERT INTO themes (id, name, hashtag, rss_feeds, is_active) VALUES (20, 'Sports', '#sports', '[]', 1)")
    conn.execute(
        "INSERT INTO user_themes (id, user_id, theme_type, theme_id, articles_per_theme) VALUES (1, 1, 'default', 10, 1)"
    )
    conn.execute(
        "INSERT INTO user_themes (id, user_id, theme_type, theme_id, articles_per_theme) VALUES (2, 1, 'default', 20, 1)"
    )
    # Global schedule — user_theme_id = NULL
    conn.execute(
        "INSERT INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (1, NULL, '[1,3,5]', 9)"
    )
    conn.commit()

    rows = _get_due_rows(conn, hour_utc=9, weekday=1)  # Monday

    assert len(rows) == 2, f"Expected 2 rows (one per theme), got {len(rows)}: {rows}"
    theme_ids = {r["theme_id"] for r in rows}
    assert theme_ids == {10, 20}
    for r in rows:
        assert r["theme_type"] == "default"


def test_global_schedule_wrong_hour_returns_nothing():
    conn = _make_db()
    now = int(time.time())
    conn.execute("INSERT INTO users (user_id, tier, created_at) VALUES (1, 'free', ?)", [now])
    conn.execute("INSERT INTO themes (id, name, hashtag, rss_feeds, is_active) VALUES (10, 'Tech', '#tech', '[]', 1)")
    conn.execute(
        "INSERT INTO user_themes (id, user_id, theme_type, theme_id, articles_per_theme) VALUES (1, 1, 'default', 10, 1)"
    )
    conn.execute(
        "INSERT INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (1, NULL, '[1]', 9)"
    )
    conn.commit()

    rows = _get_due_rows(conn, hour_utc=10, weekday=1)
    assert rows == []


def test_global_schedule_wrong_day_returns_nothing():
    conn = _make_db()
    now = int(time.time())
    conn.execute("INSERT INTO users (user_id, tier, created_at) VALUES (1, 'free', ?)", [now])
    conn.execute("INSERT INTO themes (id, name, hashtag, rss_feeds, is_active) VALUES (10, 'Tech', '#tech', '[]', 1)")
    conn.execute(
        "INSERT INTO user_themes (id, user_id, theme_type, theme_id, articles_per_theme) VALUES (1, 1, 'default', 10, 1)"
    )
    conn.execute(
        "INSERT INTO user_schedules (user_id, user_theme_id, days, hour_utc) VALUES (1, NULL, '[2,4]', 9)"
    )
    conn.commit()

    rows = _get_due_rows(conn, hour_utc=9, weekday=1)  # Monday = 1, but schedule is Tue/Thu
    assert rows == []


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
    check_expiry_reminders()

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
