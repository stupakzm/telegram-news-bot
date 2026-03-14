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
