import os
import time
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _msg(user_id=1):
    return {"from": {"id": user_id}, "chat": {"id": user_id}}


@patch("bot.commands.settings.tg.send_message")
@patch("bot.commands.settings.db.execute", return_value=[])
def test_settings_prompts_start_for_unknown_user(mock_exec, mock_send):
    from bot.commands.settings import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "/start" in text


@patch("bot.commands.settings.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.settings.db.execute")
def test_settings_active_user_shows_plan_and_counts(mock_exec, mock_send):
    future = int(time.time()) + 86400
    mock_exec.side_effect = [
        [{"tier": "vip", "tier_expires_at": future, "timezone": "Europe/Kyiv"}],
        [{"url": "u1"}, {"url": "u2"}],
        [{"keyword": "AI"}, {"keyword": "Tesla"}, {"keyword": "GPU"}],
    ]
    from bot.commands.settings import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "VIP" in text
    assert "Europe/Kyiv" in text
    assert "*Feeds:* 2" in text
    assert "*Keywords:* 3" in text


@patch("bot.commands.settings.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.settings.db.execute_many")
@patch("bot.commands.settings.db.execute")
def test_settings_auto_expires_past_plan(mock_exec, mock_exec_many, mock_send):
    past = int(time.time()) - 86400
    mock_exec.side_effect = [
        [{"tier": "vip", "tier_expires_at": past, "timezone": "UTC"}],
        [],
        [],
    ]
    from bot.commands.settings import handle
    handle(_msg())
    sql, _ = mock_exec_many.call_args[0][0][0]
    assert "tier = 'expired'" in sql
    text = mock_send.call_args[1].get("text", "")
    assert "Expired" in text


@patch("bot.commands.settings.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.settings.db.execute")
def test_settings_default_timezone_is_utc(mock_exec, mock_send):
    mock_exec.side_effect = [
        [{"tier": "trial", "tier_expires_at": int(time.time()) + 86400, "timezone": None}],
        [],
        [],
    ]
    from bot.commands.settings import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "UTC" in text
    assert "Trial" in text
