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
