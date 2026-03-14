import pytest
from unittest.mock import patch, MagicMock
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
