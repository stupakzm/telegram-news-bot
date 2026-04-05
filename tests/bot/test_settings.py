# tests/bot/test_settings.py
import os, json
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _msg(user_id=1):
    return {"from": {"id": user_id}, "chat": {"id": user_id}}


@patch("bot.commands.settings.tg.send_message")
@patch("bot.commands.settings.db.execute", return_value=[])
def test_settings_prompts_start_for_unknown_user(mock_execute, mock_send):
    from bot.commands.settings import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "/start" in text


@patch("bot.commands.settings.tg.send_message")
@patch("bot.commands.settings.db.execute", side_effect=[
    [{"tier": "free", "tier_expires_at": None}],  # user query
    [],  # themes
    [],  # schedules
])
def test_settings_free_user_gets_upgrade_button(mock_execute, mock_send):
    from bot.commands.settings import handle
    handle(_msg())
    markup = mock_send.call_args[1].get("reply_markup", {})
    buttons = [btn for row in markup.get("inline_keyboard", []) for btn in row]
    # Upgrade button shown only when UPGRADE_ENABLED is True
    from bot.config import UPGRADE_ENABLED
    if UPGRADE_ENABLED:
        assert any("Upgrade" in b["text"] for b in buttons)
    else:
        assert not any("Upgrade" in b["text"] for b in buttons)


@patch("bot.commands.settings.tg.send_message")
@patch("bot.commands.settings.db.execute", side_effect=[
    [{"tier": "monthly", "tier_expires_at": None}],  # user query
    [],  # themes
    [],  # schedules
])
def test_settings_monthly_user_no_upgrade_button(mock_execute, mock_send):
    from bot.commands.settings import handle
    handle(_msg())
    markup = mock_send.call_args[1].get("reply_markup", {})
    buttons = [btn for row in markup.get("inline_keyboard", []) for btn in row]
    assert not any("Upgrade" in b["text"] for b in buttons)


@patch("bot.commands.settings.tg.send_message")
@patch("bot.commands.settings.db.execute", side_effect=[
    [{"tier": "free", "tier_expires_at": None}],
    [{"user_theme_id": 1, "theme_type": "default", "theme_id": 2, "articles_per_theme": 1,
      "default_name": "Technology", "custom_name": None}],
    [{"days": json.dumps([1, 2, 3]), "hour_utc": 8, "user_theme_id": None}],
])
def test_settings_shows_theme_and_schedule(mock_execute, mock_send):
    from bot.commands.settings import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "Technology" in text
    assert "Mon" in text
    assert "08:00" in text
