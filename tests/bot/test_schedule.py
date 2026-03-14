import pytest
from unittest.mock import patch
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


@patch("bot.commands.schedule.tg.send_message")
@patch("bot.commands.schedule.db.execute", return_value=[{"tier": "free"}])
def test_schedule_shows_day_picker(mock_execute, mock_send):
    from bot.commands.schedule import handle
    handle({"from": {"id": 1}, "chat": {"id": 1}})
    assert mock_send.called
    markup = mock_send.call_args[1].get("reply_markup", {})
    flat_buttons = [b for row in markup.get("inline_keyboard", []) for b in row]
    labels = [b["text"] for b in flat_buttons]
    assert any("Mon" in l or "Tue" in l for l in labels)


@patch("bot.commands.schedule.tg.send_message")
@patch("bot.commands.schedule.db.execute_many")
def test_set_global_schedule_upserts(mock_execute_many, mock_send):
    from bot.commands.schedule import set_global_schedule
    set_global_schedule(user_id=1, days=[1, 3, 5], hour_utc=9)
    assert mock_execute_many.called
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "user_schedules" in sql
    assert 9 in args
