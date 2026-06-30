import os
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _msg(text="", user_id=1):
    return {"from": {"id": user_id}, "chat": {"id": user_id}, "text": text}


def _cb(data, user_id=1):
    return {
        "id": "cb",
        "from": {"id": user_id},
        "message": {"chat": {"id": user_id}, "message_id": 3},
        "data": data,
    }


@patch("bot.commands.timezone.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.timezone.db.execute", return_value=[])
def test_view_unknown_user_prompts_start(mock_exec, mock_send):
    from bot.commands.timezone import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "/start" in text


@patch("bot.commands.timezone.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.timezone.db.execute")
def test_view_shows_current_tz_and_schedule(mock_exec, mock_send):
    mock_exec.return_value = [{"tier": "vip", "timezone": "Europe/Kyiv"}]
    from bot.commands.timezone import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "Europe/Kyiv" in text
    assert "13:00" in text and "20:00" in text  # VIP delivery hours


@patch("bot.commands.timezone.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.timezone.db.execute")
def test_view_svip_shows_4_delivery_hours(mock_exec, mock_send):
    mock_exec.return_value = [{"tier": "svip", "timezone": "UTC"}]
    from bot.commands.timezone import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    for hour in ("10:00", "14:00", "18:00", "22:00"):
        assert hour in text


@patch("bot.commands.timezone.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.timezone.tg.answer_callback_query")
@patch("bot.commands.timezone.db.execute_many")
@patch("bot.commands.timezone.db.execute")
def test_set_callback_saves_known_tz(mock_exec, mock_exec_many, mock_ack, mock_send):
    mock_exec.return_value = [{"tier": "vip", "timezone": "Europe/Berlin"}]
    from bot.commands.timezone import handle_set_callback
    handle_set_callback(_cb("tz:set:Europe/Berlin"), tz_name="Europe/Berlin")
    sql, args = mock_exec_many.call_args[0][0][0]
    assert "UPDATE users SET timezone" in sql
    assert "Europe/Berlin" in args


@patch("bot.commands.timezone.tg.answer_callback_query")
@patch("bot.commands.timezone.db.execute_many")
def test_set_callback_rejects_unknown_tz(mock_exec_many, mock_ack):
    from bot.commands.timezone import handle_set_callback
    handle_set_callback(_cb("tz:set:NotARealZone"), tz_name="NotARealZone")
    text = mock_ack.call_args[1].get("text", "")
    assert "Unknown" in text
    assert not mock_exec_many.called


@patch("bot.commands.timezone.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.timezone.tg.answer_callback_query")
@patch("bot.commands.timezone.db.execute_many")
def test_custom_callback_sets_pending_action(mock_exec_many, mock_ack, mock_send):
    from bot.commands.timezone import handle_custom_callback
    handle_custom_callback(_cb("tz:custom"))
    sql, _ = mock_exec_many.call_args[0][0][0]
    assert "timezone_set" in sql


@patch("bot.commands.timezone.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.timezone.db.execute_many")
@patch("bot.commands.timezone.db.execute")
def test_pending_valid_tz_saves_and_clears_pending(mock_exec, mock_exec_many, mock_send):
    mock_exec.return_value = [{"tier": "vip", "timezone": "America/Los_Angeles"}]
    from bot.commands.timezone import handle_pending
    handle_pending(_msg(text="America/Los_Angeles"), action="timezone_set", data_json="{}")
    sqls = [sql for call in mock_exec_many.call_args_list for sql, _ in call[0][0]]
    assert any("UPDATE users SET timezone" in s for s in sqls)
    assert any("DELETE FROM user_pending_actions" in s for s in sqls)


@patch("bot.commands.timezone.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.timezone.db.execute_many")
@patch("bot.commands.timezone.db.execute", return_value=[])
def test_pending_invalid_tz_does_not_save(mock_exec, mock_exec_many, mock_send):
    from bot.commands.timezone import handle_pending
    handle_pending(_msg(text="Mars/Phobos"), action="timezone_set", data_json="{}")
    text = mock_send.call_args[1].get("text", "")
    assert "not a valid" in text.lower()
    sqls = [sql for call in mock_exec_many.call_args_list for sql, _ in call[0][0]]
    assert not any("UPDATE users SET timezone" in s for s in sqls)
