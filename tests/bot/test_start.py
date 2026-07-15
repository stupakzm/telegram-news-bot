import os
import time
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _msg(user_id=1):
    return {"from": {"id": user_id, "first_name": "Alice"}, "chat": {"id": user_id}}


def _cb(data, user_id=1):
    return {
        "id": "cb",
        "from": {"id": user_id},
        "message": {"chat": {"id": user_id}, "message_id": 1},
        "data": data,
    }


@patch("bot.commands.start.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.start.db.execute_many")
@patch("bot.commands.start.db.execute")
def test_new_user_starts_trial(mock_exec, mock_exec_many, mock_send):
    # First call (user lookup) returns no rows; second call (pack keyboard) returns packs
    mock_exec.side_effect = [[], [{"id": 1, "name": "Tech"}]]
    from bot.commands.start import handle
    before = int(time.time())
    handle(_msg())
    insert_sql, insert_args = mock_exec_many.call_args[0][0][0]
    assert "INSERT INTO users" in insert_sql
    assert "trial" in insert_sql
    expires = next(a for a in insert_args if isinstance(a, int) and a > before)
    assert abs((expires - before) - 3 * 24 * 3600) < 10
    markup = mock_send.call_args[1]["reply_markup"]
    assert markup is not None


@patch("bot.commands.start.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.start.db.execute_many")
@patch("bot.commands.start.db.execute")
def test_returning_active_user_no_trial_insert(mock_exec, mock_exec_many, mock_send):
    future = int(time.time()) + 86400
    mock_exec.return_value = [{"tier": "vip", "tier_expires_at": future}]
    from bot.commands.start import handle
    handle(_msg())
    if mock_exec_many.called:
        for call in mock_exec_many.call_args_list:
            sql, _ = call[0][0][0]
            assert "INSERT INTO users" not in sql
    text = mock_send.call_args[1].get("text", "")
    assert "Welcome back" in text


@patch("bot.commands.start.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.start.db.execute_many")
@patch("bot.commands.start.db.execute")
def test_expired_user_sees_expired_message(mock_exec, mock_exec_many, mock_send):
    past = int(time.time()) - 86400
    mock_exec.return_value = [{"tier": "vip", "tier_expires_at": past}]
    from bot.commands.start import handle
    handle(_msg())
    sql, _ = mock_exec_many.call_args[0][0][0]
    assert "tier = 'expired'" in sql
    text = mock_send.call_args[1].get("text", "")
    assert "expired" in text.lower()


@patch("bot.commands.start.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.start.tg.answer_callback_query")
@patch("bot.commands.start.db.execute_many")
@patch("bot.commands.start.db.execute")
def test_pack_callback_imports_feeds(mock_exec, mock_exec_many, mock_ack, mock_send):
    mock_exec.return_value = [{"name": "Tech", "urls": '["https://a.example/feed", "https://b.example/feed"]'}]
    from bot.commands.start import handle_pack_callback
    handle_pack_callback(_cb("start:pack:1"), pack_id=1)
    statements = mock_exec_many.call_args[0][0]
    assert len(statements) == 2
    for sql, _ in statements:
        assert "INSERT OR IGNORE INTO user_feeds" in sql


@patch("bot.commands.start.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.start.tg.answer_callback_query")
@patch("bot.commands.start.db.execute", return_value=[])
def test_pack_callback_missing_pack_does_not_send(mock_exec, mock_ack, mock_send):
    from bot.commands.start import handle_pack_callback
    handle_pack_callback(_cb("start:pack:99"), pack_id=99)
    mock_ack.assert_called_once()
    text = mock_ack.call_args[1].get("text", "")
    assert "not found" in text.lower()
    assert not mock_send.called


@patch("bot.commands.start.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.start.tg.answer_callback_query")
def test_skip_callback_sends_next_steps(mock_ack, mock_send):
    from bot.commands.start import handle_skip_callback
    handle_skip_callback(_cb("start:skip"))
    text = mock_send.call_args[1].get("text", "")
    markup = mock_send.call_args[1].get("reply_markup", {})
    # points to /addurl and offers one-tap keyword suggestions (UX-01)
    assert "/addurl" in text
    datas = [b["callback_data"] for row in markup["inline_keyboard"] for b in row]
    assert any(d.startswith("kw:sugg:") for d in datas)
