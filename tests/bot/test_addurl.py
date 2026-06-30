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
        "message": {"chat": {"id": user_id}, "message_id": 9},
        "data": data,
    }


@patch("bot.commands.addurl.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.addurl.db.execute")
def test_view_vip_quota_is_7(mock_exec, mock_send):
    mock_exec.side_effect = [
        [{"tier": "vip"}],
        [],  # no feeds
    ]
    from bot.commands.addurl import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "0/7" in text


@patch("bot.commands.addurl.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.addurl.db.execute")
def test_view_svip_quota_is_15(mock_exec, mock_send):
    mock_exec.side_effect = [
        [{"tier": "svip"}],
        [],
    ]
    from bot.commands.addurl import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "0/15" in text


@patch("bot.commands.addurl.tg.answer_callback_query")
@patch("bot.commands.addurl.db.execute")
def test_add_callback_blocked_at_quota(mock_exec, mock_ack):
    # tier=vip (quota 7), 7 feeds already
    mock_exec.side_effect = [
        [{"tier": "vip"}],
        [{"id": i, "url": f"https://x{i}.example/feed"} for i in range(7)],
    ]
    from bot.commands.addurl import handle_add_callback
    handle_add_callback(_cb("url:add"))
    text = mock_ack.call_args[1].get("text", "")
    assert "quota" in text.lower()


@patch("bot.commands.addurl.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.addurl.tg.answer_callback_query")
@patch("bot.commands.addurl.db.execute_many")
@patch("bot.commands.addurl.db.execute")
def test_add_callback_under_quota_sets_pending(mock_exec, mock_exec_many, mock_ack, mock_send):
    mock_exec.side_effect = [
        [{"tier": "vip"}],
        [{"id": 1, "url": "https://x.example/feed"}],
    ]
    from bot.commands.addurl import handle_add_callback
    handle_add_callback(_cb("url:add"))
    sql, _ = mock_exec_many.call_args[0][0][0]
    assert "addurl_paste" in sql


@patch("bot.commands.addurl.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.addurl.db.execute_many")
@patch("bot.commands.addurl.db.execute")
def test_pending_no_urls_warns(mock_exec, mock_exec_many, mock_send):
    mock_exec.return_value = []
    from bot.commands.addurl import handle_pending
    handle_pending(_msg(text="not a url"), action="addurl_paste", data_json="{}")
    text = mock_send.call_args[1].get("text", "")
    assert "No URLs found" in text
    assert not mock_exec_many.called


@patch("bot.commands.addurl.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.addurl.db.execute_many")
@patch("bot.commands.addurl.db.execute")
@patch("bot.commands.addurl._validate_feed", return_value=(True, ""))
def test_pending_adds_valid_url(mock_validate, mock_exec, mock_exec_many, mock_send):
    # tier vip, existing feeds empty, post-add view
    mock_exec.side_effect = [
        [{"tier": "vip"}],
        [],
        [{"tier": "vip"}],
        [{"id": 1, "url": "https://example.com/feed"}],
    ]
    from bot.commands.addurl import handle_pending
    handle_pending(_msg(text="https://example.com/feed"), action="addurl_paste", data_json="{}")
    # First execute_many is the INSERT batch
    insert_call = mock_exec_many.call_args_list[0]
    statements = insert_call[0][0]
    inserted_urls = {args[1] for sql, args in statements}
    assert "https://example.com/feed" in inserted_urls


@patch("bot.commands.addurl.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.addurl.db.execute_many")
@patch("bot.commands.addurl.db.execute")
@patch("bot.commands.addurl._validate_feed", return_value=(False, "no RSS entries"))
def test_pending_rejects_invalid_url(mock_validate, mock_exec, mock_exec_many, mock_send):
    mock_exec.side_effect = [
        [{"tier": "vip"}],
        [],
        [{"tier": "vip"}],
        [],
    ]
    from bot.commands.addurl import handle_pending
    handle_pending(_msg(text="https://bad.example/feed"), action="addurl_paste", data_json="{}")
    # No INSERT INTO user_feeds was issued (validation failed)
    all_sqls = [
        sql
        for call in mock_exec_many.call_args_list
        for sql, _ in call[0][0]
    ]
    assert not any("INSERT" in s and "user_feeds" in s for s in all_sqls)
    err_text = " ".join(c[1].get("text", "") for c in mock_send.call_args_list)
    assert "no RSS entries" in err_text


@patch("bot.commands.addurl.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.addurl.db.execute_many")
@patch("bot.commands.addurl.db.execute")
def test_pending_skips_duplicate(mock_exec, mock_exec_many, mock_send):
    mock_exec.side_effect = [
        [{"tier": "vip"}],
        [{"id": 1, "url": "https://x.example/feed"}],
        [{"tier": "vip"}],
        [{"id": 1, "url": "https://x.example/feed"}],
    ]
    from bot.commands.addurl import handle_pending
    handle_pending(
        _msg(text="https://x.example/feed"),
        action="addurl_paste",
        data_json="{}",
    )
    all_sqls = [
        sql
        for call in mock_exec_many.call_args_list
        for sql, _ in call[0][0]
    ]
    assert not any("INSERT" in s and "user_feeds" in s for s in all_sqls)
    text = " ".join(c[1].get("text", "") for c in mock_send.call_args_list)
    assert "duplicate" in text.lower()
