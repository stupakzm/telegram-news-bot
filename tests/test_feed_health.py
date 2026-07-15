"""Tests for delivery/feed_health.py (FEED-01)."""
import os
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")

from delivery import feed_health


@patch("delivery.feed_health.db.execute")
def test_report_queries_window_and_limit(mock_execute):
    mock_execute.return_value = []
    feed_health.feed_health_report(window_seconds=3600, limit=3, now_ts=10_000)

    sql, args = mock_execute.call_args[0]
    assert "delivery_errors" in sql
    assert "feed_url IS NOT NULL" in sql
    assert "GROUP BY feed_url" in sql
    # since = now_ts - window_seconds ; limit passed through
    assert args == [10_000 - 3600, 3]


def test_format_empty_shows_green_none():
    assert feed_health.format_feed_health([]) == ["None \U0001f7e2"]


def test_format_renders_counts_and_age():
    now = 100_000
    rows = [
        {"feed_url": "https://a.example/rss", "failures": 5,
         "last_at": now - 2 * 3600, "affected_users": 3},
        {"feed_url": "https://b.example/rss", "failures": 1,
         "last_at": now - 3600, "affected_users": 0},
    ]
    lines = feed_health.format_feed_health(rows, now_ts=now)
    assert "5×" in lines[0]
    assert "a.example" in lines[0]
    assert "last 2h ago" in lines[0]
    assert "3 user(s)" in lines[0]
    # zero affected users → no user note
    assert "user(s)" not in lines[1]


def test_format_shortens_long_urls():
    long_url = "https://example.com/" + "x" * 200
    rows = [{"feed_url": long_url, "failures": 1, "last_at": 0, "affected_users": 0}]
    line = feed_health.format_feed_health(rows, now_ts=0)[0]
    assert "…" in line
