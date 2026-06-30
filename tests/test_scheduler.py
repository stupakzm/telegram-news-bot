import os
import time
from datetime import datetime, timezone
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_matches_vip_local_hour(mock_exec, mock_exec_many):
    # UTC 17:00 → Europe/Kyiv (UTC+3 in summer DST) → 20:00, which is in VIP hours
    now = datetime(2026, 7, 15, 17, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 1, "tier": "vip", "tier_expires_at": future, "timezone": "Europe/Kyiv"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert len(due) == 1
    assert due[0]["user_id"] == 1


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_skips_off_hour(mock_exec, mock_exec_many):
    # UTC 02:00 → Europe/Kyiv 05:00 — not in VIP hours (13, 20)
    now = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 1, "tier": "vip", "tier_expires_at": future, "timezone": "Europe/Kyiv"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert due == []


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_get_due_users_expires_past_plan(mock_exec, mock_exec_many):
    now = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    past = int(now.timestamp()) - 86400
    mock_exec.return_value = [
        {"user_id": 5, "tier": "vip", "tier_expires_at": past, "timezone": "UTC"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert due == []
    # Auto-expire UPDATE was issued
    sql, args = mock_exec_many.call_args[0][0][0]
    assert "tier = 'expired'" in sql
    assert 5 in args


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_svip_due_at_one_of_four_hours(mock_exec, mock_exec_many):
    # UTC 14:00, UTC tz → 14:00 local → in SVIP hours
    now = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 9, "tier": "svip", "tier_expires_at": future, "timezone": "UTC"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert len(due) == 1


@patch("delivery.scheduler.db.execute_many")
@patch("delivery.scheduler.db.execute")
def test_trial_uses_vip_hours(mock_exec, mock_exec_many):
    now = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    future = int(now.timestamp()) + 86400
    mock_exec.return_value = [
        {"user_id": 7, "tier": "trial", "tier_expires_at": future, "timezone": "UTC"}
    ]
    from delivery.scheduler import get_due_users
    due = get_due_users(now)
    assert len(due) == 1
    assert due[0]["tier"] == "trial"


def test_user_today_start_utc_ts_handles_offset_tz():
    # 2026-07-15 02:00 UTC = 2026-07-15 05:00 Kyiv
    # midnight in Kyiv = 2026-07-14 21:00 UTC
    from delivery.scheduler import user_today_start_utc_ts
    now = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)
    ts = user_today_start_utc_ts("Europe/Kyiv", now)
    midnight_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert midnight_utc == datetime(2026, 7, 14, 21, 0, tzinfo=timezone.utc)


def test_user_today_start_utc_ts_defaults_to_utc():
    from delivery.scheduler import user_today_start_utc_ts
    now = datetime(2026, 7, 15, 14, 30, tzinfo=timezone.utc)
    ts = user_today_start_utc_ts(None, now)
    midnight_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert midnight_utc == datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)


def test_user_today_start_utc_ts_unknown_tz_falls_back_to_utc():
    from delivery.scheduler import user_today_start_utc_ts
    now = datetime(2026, 7, 15, 14, 30, tzinfo=timezone.utc)
    ts = user_today_start_utc_ts("Mars/Phobos", now)
    midnight_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    assert midnight_utc == datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)


@patch("delivery.scheduler.db.execute_many")
def test_cleanup_seen_articles_deletes_old(mock_exec_many):
    from delivery.scheduler import cleanup_seen_articles, SEEN_RETENTION_SECONDS
    before = int(time.time())
    cleanup_seen_articles()
    sql, args = mock_exec_many.call_args[0][0][0]
    assert "DELETE FROM seen_articles" in sql
    cutoff = args[0]
    # cutoff ≈ now - retention
    assert abs((before - cutoff) - SEEN_RETENTION_SECONDS) < 5
