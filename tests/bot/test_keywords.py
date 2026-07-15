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
        "message": {"chat": {"id": user_id}, "message_id": 7},
        "data": data,
    }


@patch("bot.commands.keywords.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.keywords.db.execute", return_value=[])
def test_view_empty_shows_hint(mock_exec, mock_send):
    from bot.commands.keywords import handle
    handle(_msg())
    text = mock_send.call_args[1].get("text", "")
    assert "No keywords set" in text


@patch("bot.commands.keywords.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.keywords.db.execute")
def test_view_populated_shows_remove_buttons(mock_exec, mock_send):
    mock_exec.return_value = [{"keyword": "Tesla"}, {"keyword": "AI"}]
    from bot.commands.keywords import handle
    handle(_msg())
    markup = mock_send.call_args[1]["reply_markup"]
    callbacks = [b[0]["callback_data"] for b in markup["inline_keyboard"]]
    assert "kw:rm:0" in callbacks
    assert "kw:rm:1" in callbacks
    assert "kw:add" in callbacks


@patch("bot.commands.keywords.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.keywords.tg.answer_callback_query")
@patch("bot.commands.keywords.db.execute_many")
def test_add_callback_sets_pending_action(mock_exec_many, mock_ack, mock_send):
    from bot.commands.keywords import handle_add_callback
    handle_add_callback(_cb("kw:add"))
    sql, _ = mock_exec_many.call_args[0][0][0]
    assert "user_pending_actions" in sql
    assert "keywords_add" in sql


@patch("bot.commands.keywords.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.keywords.db.execute_many")
@patch("bot.commands.keywords.db.execute")
def test_pending_add_splits_commas_and_newlines(mock_exec, mock_exec_many, mock_send):
    # _list_keywords is called multiple times; return empty + populated for the post-add view
    mock_exec.side_effect = [[], [{"keyword": "AI"}, {"keyword": "Tesla"}, {"keyword": "GPU"}]]
    from bot.commands.keywords import handle_pending
    handle_pending(_msg(text="AI, Tesla\nGPU"), action="keywords_add", data_json="{}")
    # First execute_many should be the INSERT batch
    insert_call = mock_exec_many.call_args_list[0]
    statements = insert_call[0][0]
    inserted_keywords = {args[1] for sql, args in statements}
    assert inserted_keywords == {"AI", "Tesla", "GPU"}


@patch("bot.commands.keywords.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.keywords.db.execute_many")
@patch("bot.commands.keywords.db.execute")
def test_pending_add_skips_duplicates(mock_exec, mock_exec_many, mock_send):
    # Existing keyword: AI. Then post-insert view query
    mock_exec.side_effect = [
        [{"keyword": "AI"}],          # existing
        [{"keyword": "AI"}, {"keyword": "Tesla"}],  # post-add view
    ]
    from bot.commands.keywords import handle_pending
    handle_pending(_msg(text="AI, Tesla"), action="keywords_add", data_json="{}")
    insert_call = mock_exec_many.call_args_list[0]
    statements = insert_call[0][0]
    inserted = {args[1] for sql, args in statements}
    assert inserted == {"Tesla"}  # AI skipped as duplicate


@patch("bot.commands.keywords.tg.send_message", return_value={"message_id": 1})
@patch("bot.commands.keywords.db.execute_many")
@patch("bot.commands.keywords.db.execute")
def test_pending_add_empty_input_warns(mock_exec, mock_exec_many, mock_send):
    mock_exec.return_value = []
    from bot.commands.keywords import handle_pending
    handle_pending(_msg(text="   ,, "), action="keywords_add", data_json="{}")
    text = mock_send.call_args[1].get("text", "")
    assert "No keywords found" in text
    assert not mock_exec_many.called


@patch("bot.commands.keywords.tg.answer_callback_query")
@patch("bot.commands.keywords.tg.edit_message_text")
@patch("bot.commands.keywords.db.execute_many")
@patch("bot.commands.keywords.db.execute")
def test_remove_callback_deletes_keyword(mock_exec, mock_exec_many, mock_edit, mock_ack):
    # First call lists current keywords for deletion lookup; second for view rebuild
    mock_exec.side_effect = [
        [{"keyword": "AI"}, {"keyword": "Tesla"}],
        [{"keyword": "AI"}],
    ]
    from bot.commands.keywords import handle_remove_callback
    handle_remove_callback(_cb("kw:rm:1"), index=1)
    sql, args = mock_exec_many.call_args[0][0][0]
    assert "DELETE FROM user_keywords" in sql
    assert args[1] == "Tesla"


# --- UX-01: one-tap suggested keywords ---------------------------------------

def test_suggested_keywords_markup_has_buttons_and_typeown():
    from bot.commands.keywords import suggested_keywords_markup, SUGGESTED_KEYWORDS
    markup = suggested_keywords_markup()
    flat = [b for row in markup["inline_keyboard"] for b in row]
    datas = [b["callback_data"] for b in flat]
    for kw in SUGGESTED_KEYWORDS:
        assert f"kw:sugg:{kw}" in datas
    assert "kw:add" in datas  # 'type my own' fallback


@patch("bot.commands.keywords.tg.answer_callback_query")
@patch("bot.commands.keywords.db.execute_many")
@patch("bot.commands.keywords.db.execute", return_value=[])
def test_suggest_callback_adds_keyword(mock_exec, mock_exec_many, mock_ack):
    from bot.commands.keywords import handle_suggest_callback
    handle_suggest_callback(_cb("kw:sugg:AI"), "AI")
    sql, args = mock_exec_many.call_args[0][0][0]
    assert "INSERT OR IGNORE INTO user_keywords" in sql
    assert "AI" in args
    assert mock_ack.called


@patch("bot.commands.keywords.tg.answer_callback_query")
@patch("bot.commands.keywords.db.execute_many")
@patch("bot.commands.keywords.db.execute", return_value=[{"keyword": "AI"}])
def test_suggest_callback_skips_duplicate(mock_exec, mock_exec_many, mock_ack):
    from bot.commands.keywords import handle_suggest_callback
    handle_suggest_callback(_cb("kw:sugg:AI"), "AI")
    assert not mock_exec_many.called
    assert "Already added" in mock_ack.call_args[1].get("text", "")
