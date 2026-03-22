import pytest
from unittest.mock import patch


def setup_function():
    """Clear rate limiter state before each test."""
    from bot import rate_limiter
    rate_limiter._user_timestamps.clear()


def test_allows_up_to_max_commands():
    from bot.rate_limiter import check_rate_limit
    for i in range(5):
        allowed, retry = check_rate_limit(user_id=100)
        assert allowed is True, f"Command {i+1} should be allowed"
        assert retry == 0


def test_blocks_after_max_commands():
    from bot.rate_limiter import check_rate_limit
    for _ in range(5):
        check_rate_limit(user_id=100)
    allowed, retry = check_rate_limit(user_id=100)
    assert allowed is False
    assert retry > 0
    assert retry <= 60


@patch("bot.rate_limiter.time")
def test_allows_after_window_expires(mock_time):
    from bot.rate_limiter import check_rate_limit
    # Send 5 commands at t=1000
    mock_time.time.return_value = 1000.0
    for _ in range(5):
        check_rate_limit(user_id=100)
    # 6th at t=1000 should be blocked
    allowed, _ = check_rate_limit(user_id=100)
    assert allowed is False
    # Advance past window (61 seconds)
    mock_time.time.return_value = 1061.0
    allowed, retry = check_rate_limit(user_id=100)
    assert allowed is True
    assert retry == 0


def test_independent_user_limits():
    from bot.rate_limiter import check_rate_limit
    # Fill user A's limit
    for _ in range(5):
        check_rate_limit(user_id=100)
    # User A blocked
    allowed_a, _ = check_rate_limit(user_id=100)
    assert allowed_a is False
    # User B unaffected
    allowed_b, retry_b = check_rate_limit(user_id=200)
    assert allowed_b is True
    assert retry_b == 0


@patch("bot.rate_limiter.time")
def test_retry_after_value(mock_time):
    from bot.rate_limiter import check_rate_limit
    from math import ceil
    # 5 commands at t=1000
    mock_time.time.return_value = 1000.0
    for _ in range(5):
        check_rate_limit(user_id=100)
    # 6th at t=1030 (30s later)
    mock_time.time.return_value = 1030.0
    allowed, retry = check_rate_limit(user_id=100)
    assert allowed is False
    # Oldest is at t=1000, window is 60s, so expires at t=1060
    # retry_after = ceil(60 - (1030 - 1000)) = ceil(30) = 30
    assert retry == 30
