# tests/bot/test_addtheme.py
import os, json
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("GEMINI_API_KEY", "test-key")


def _msg(user_id=1, text=""):
    return {"from": {"id": user_id}, "chat": {"id": user_id}, "text": text}


# --- handle_ai ---

@patch("bot.commands.addtheme.tg.send_message")
@patch("bot.commands.addtheme.db.execute", return_value=[{"tier": "free"}])
def test_handle_ai_blocked_for_free(mock_execute, mock_send):
    from bot.commands.addtheme import handle_ai
    handle_ai(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "paid plan" in text or "upgrade" in text.lower()


@patch("bot.commands.addtheme.tg.send_message")
@patch("bot.commands.addtheme.db.execute_many")
@patch("bot.commands.addtheme.db.execute", side_effect=[
    [{"tier": "one_time"}],  # _check_access: get tier
    [{"c": 0}],               # _check_access: custom theme count
])
def test_handle_ai_prompts_paid_user(mock_execute, mock_execute_many, mock_send):
    from bot.commands.addtheme import handle_ai
    handle_ai(_msg())
    assert mock_send.called
    text = mock_send.call_args[1].get("text", "")
    assert "topic" in text.lower() or "describe" in text.lower()


# --- handle_manual ---

@patch("bot.commands.addtheme.tg.send_message")
@patch("bot.commands.addtheme.db.execute", return_value=[{"tier": "free"}])
def test_handle_manual_blocked_for_free(mock_execute, mock_send):
    from bot.commands.addtheme import handle_manual
    handle_manual(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "paid plan" in text or "upgrade" in text.lower()


# --- handle_pending: addtheme_manual_urls ---

@patch("bot.commands.addtheme.tg.send_message")
@patch("bot.commands.addtheme.db.execute_many")
@patch("bot.commands.addtheme._validate_feed", return_value=True)
def test_handle_pending_manual_urls_valid(mock_validate, mock_execute_many, mock_send):
    from bot.commands.addtheme import handle_pending
    msg = _msg(text="https://example.com/feed.xml")
    handle_pending(msg, "addtheme_manual_urls", "{}")
    text = mock_send.call_args[1].get("text", "")
    assert "validated" in text or "called" in text.lower() or "feed" in text.lower()


@patch("bot.commands.addtheme.tg.send_message")
def test_handle_pending_manual_urls_no_valid_urls(mock_send):
    from bot.commands.addtheme import handle_pending
    msg = _msg(text="not a url at all")
    handle_pending(msg, "addtheme_manual_urls", "{}")
    text = mock_send.call_args[1].get("text", "")
    assert "No valid" in text or "http" in text.lower()


# --- handle_pending: unknown action ---

@patch("bot.commands.addtheme.tg.send_message")
@patch("bot.commands.addtheme.db.execute_many")
def test_handle_pending_unknown_action_clears_and_notifies(mock_execute_many, mock_send):
    from bot.commands.addtheme import handle_pending
    handle_pending(_msg(), "bogus_action", "{}")
    assert mock_send.called
    text = mock_send.call_args[1].get("text", "")
    assert "wrong" in text.lower() or "try" in text.lower() or "⚠️" in text


# --- feeds_done: empty selection guard ---

@patch("bot.commands.addtheme.tg.send_message")
@patch("bot.commands.addtheme.db.execute", return_value=[
    {"data": json.dumps({"feeds": [{"name": "Feed A", "url": "http://a.com"}], "selected": []})}
])
def test_feeds_done_empty_selection_warns_user(mock_execute, mock_send):
    from bot.commands.addtheme import feeds_done
    feeds_done(user_id=1)
    text = mock_send.call_args[1].get("text", "")
    assert "select" in text.lower() or "⚠️" in text


# --- BUG-01: _save_custom_theme uses RETURNING id, not last_insert_rowid ---

@patch("bot.commands.addtheme.tg.send_message")
@patch("bot.commands.addtheme.db.execute_many")
@patch("bot.commands.addtheme.db.execute", return_value=[{"id": 42}])
def test_save_custom_theme_uses_returning_id(mock_execute, mock_execute_many, mock_send):
    from bot.commands.addtheme import _save_custom_theme
    _save_custom_theme(user_id=1, name="Test", hashtag="#test", rss_feeds=["https://example.com/feed"], ai_suggested=False)
    sql = mock_execute.call_args[0][0]
    assert "RETURNING id" in sql
    assert "last_insert_rowid" not in sql
    # Verify user_themes INSERT uses the returned id (42)
    stmt_list = mock_execute_many.call_args[0][0]
    assert stmt_list[0][1][1] == 42  # theme_id arg should be 42
