# tests/bot/test_history.py
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
@patch("bot.commands.history.db.execute", return_value=[{"tier": "one_time"}])
def test_history_blocked_for_one_time_users(mock_execute, mock_send):
    from bot.commands.history import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "Monthly" in text
    assert "switch" in text.lower()


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
