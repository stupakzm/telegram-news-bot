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
    mock_execute_many.assert_not_called()
    assert mock_send.called
