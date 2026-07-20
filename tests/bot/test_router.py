import os
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _msg_update(text="/start", user_id=123):
    return {
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "first_name": "Alice"},
            "chat": {"id": user_id},
            "text": text,
        }
    }


def _callback_update(data, user_id=123):
    return {
        "callback_query": {
            "id": "cb1",
            "from": {"id": user_id},
            "message": {"chat": {"id": user_id}, "message_id": 7},
            "data": data,
        }
    }


@patch("bot.router.db.execute_many")
@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.start.handle")
def test_router_dispatches_start(mock_handle, _rl, _em):
    from bot.router import handle_update
    handle_update(_msg_update("/start"))
    assert mock_handle.called


@patch("bot.router.db.execute_many")
@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.keywords.handle")
def test_router_dispatches_keywords(mock_handle, _rl, _em):
    from bot.router import handle_update
    handle_update(_msg_update("/keywords"))
    assert mock_handle.called


@patch("bot.router.db.execute_many")
@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.addurl.handle")
def test_router_dispatches_addurl(mock_handle, _rl, _em):
    from bot.router import handle_update
    handle_update(_msg_update("/addurl"))
    assert mock_handle.called


@patch("bot.router.db.execute_many")
@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.plan.handle")
def test_router_dispatches_plan(mock_handle, _rl, _em):
    from bot.router import handle_update
    handle_update(_msg_update("/plan"))
    assert mock_handle.called


@patch("bot.router.db.execute_many")
@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.timezone.handle")
def test_router_dispatches_timezone(mock_handle, _rl, _em):
    from bot.router import handle_update
    handle_update(_msg_update("/timezone"))
    assert mock_handle.called


@patch("bot.router.check_rate_limit", return_value=(True, 0))
def test_router_ignores_unknown_command(mock_rl):
    # check_rate_limit runs before the command lookup, so without this patch the
    # test makes a real request to the placeholder TURSO_URL and blocks for the
    # full 30s read timeout.
    from bot.router import handle_update
    # Should not raise
    handle_update(_msg_update("/unknowncommand"))


def test_router_handles_missing_message():
    from bot.router import handle_update
    handle_update({"update_id": 1})


@patch("bot.router.start.handle_pack_callback")
def test_router_routes_start_pack_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("start:pack:3"))
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][1] == 3


@patch("bot.router.start.handle_skip_callback")
def test_router_routes_start_skip_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("start:skip"))
    assert mock_cb.called


@patch("bot.router.keywords.handle_add_callback")
def test_router_routes_keyword_add_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("kw:add"))
    assert mock_cb.called


@patch("bot.router.keywords.handle_remove_callback")
def test_router_routes_keyword_remove_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("kw:rm:2"))
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][1] == 2


@patch("bot.router.keywords.handle_suggest_callback")
def test_router_routes_keyword_suggest_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("kw:sugg:open source"))
    mock_cb.assert_called_once()
    assert mock_cb.call_args[0][1] == "open source"  # keyword preserved incl. space


@patch("bot.router.addurl.handle_add_callback")
def test_router_routes_url_add_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("url:add"))
    assert mock_cb.called


@patch("bot.router.timezone_cmd.handle_set_callback")
def test_router_routes_tz_set_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("tz:set:Europe/Berlin"))
    assert mock_cb.call_args[0][1] == "Europe/Berlin"


@patch("bot.router.timezone_cmd.handle_custom_callback")
def test_router_routes_tz_custom_callback(mock_cb):
    from bot.router import handle_update
    handle_update(_callback_update("tz:custom"))
    assert mock_cb.called


@patch("bot.router.tg.answer_callback_query")
@patch("bot.router.payments_cmd.send_invoice")
def test_router_routes_pay_callback_to_invoice(mock_invoice, mock_ack):
    from bot.router import handle_update
    handle_update(_callback_update("pay:vip"))
    mock_invoice.assert_called_once()
    assert mock_invoice.call_args[1]["tier"] == "vip"


@patch("bot.router.payments_cmd.handle_successful_payment")
def test_router_routes_successful_payment(mock_handler):
    from bot.router import handle_update
    handle_update({
        "message": {
            "from": {"id": 1},
            "chat": {"id": 1},
            "successful_payment": {"invoice_payload": "tier:vip"},
        }
    })
    assert mock_handler.called


@patch("bot.router.db.execute", return_value=[{"action": "keywords_add", "data": "{}", "created_at": 9_999_999_999}])
@patch("bot.router.keywords.handle_pending")
def test_router_routes_pending_keywords_action(mock_pending, mock_execute):
    from bot.router import handle_update
    handle_update(_msg_update("AI, Tesla"))
    assert mock_pending.called


@patch("bot.router.db.execute", return_value=[{"action": "addurl_paste", "data": "{}", "created_at": 9_999_999_999}])
@patch("bot.router.addurl.handle_pending")
def test_router_routes_pending_addurl_action(mock_pending, mock_execute):
    from bot.router import handle_update
    handle_update(_msg_update("https://example.com/feed"))
    assert mock_pending.called


@patch("bot.router.db.execute", return_value=[{"action": "timezone_set", "data": "{}", "created_at": 9_999_999_999}])
@patch("bot.router.timezone_cmd.handle_pending")
def test_router_routes_pending_timezone_action(mock_pending, mock_execute):
    from bot.router import handle_update
    handle_update(_msg_update("Europe/Kyiv"))
    assert mock_pending.called


@patch("bot.router.tg.send_message")
@patch("bot.router.check_rate_limit", return_value=(False, 30))
def test_router_rate_limit_blocks_commands(mock_rl, mock_send):
    from bot.router import handle_update
    handle_update(_msg_update("/start"))
    assert mock_send.called
    text = mock_send.call_args[1].get("text", "")
    assert "Slow down" in text


@patch("bot.router.tg.answer_pre_checkout_query")
def test_router_answers_pre_checkout_query(mock_answer):
    # Revenue-critical: Stars payment can't complete unless we ack the pre-checkout.
    from bot.router import handle_update
    handle_update({
        "pre_checkout_query": {
            "id": "pcq1",
            "from": {"id": 5},
            "invoice_payload": "tier:vip",
            "total_amount": 100,
        }
    })
    mock_answer.assert_called_once()
    assert mock_answer.call_args[0][0] == "pcq1"
    assert mock_answer.call_args[1]["ok"] is True


@patch("bot.router.tg.answer_callback_query")
@patch("bot.router.db.execute_many")
@patch("bot.router.db.execute")
def test_router_reaction_stores_reaction(mock_execute, mock_execute_many, mock_ack):
    import hashlib
    from bot.router import handle_update

    url = "https://example.com/story"
    url_key = hashlib.md5(url.encode()).hexdigest()[:16]
    mock_execute.return_value = [{"article_url": url}]

    handle_update(_callback_update(f"reaction:up:{url_key}"))

    assert mock_execute_many.called
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "INSERT OR REPLACE INTO article_reactions" in sql
    assert url in args and "up" in args
    assert mock_ack.called


@patch("bot.router.tg.answer_callback_query")
@patch("bot.router.db.execute_many")
@patch("bot.router.db.execute", return_value=[])
def test_router_reaction_unknown_url_does_not_store(mock_execute, mock_execute_many, mock_ack):
    # url_key with no matching delivery_log row -> no write, but still acks.
    from bot.router import handle_update
    handle_update(_callback_update("reaction:down:deadbeefdeadbeef"))
    assert not mock_execute_many.called
    assert mock_ack.called


# --- pending-action flow hardening (blocker fix) -----------------------------

@patch("bot.router.importlib.import_module")
@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.router.db.execute_many")
def test_router_command_clears_pending(mock_em, _rl, _imp):
    # Issuing a command must clear any half-finished multi-step flow so the
    # user's next free-text message isn't mis-consumed.
    from bot.router import handle_update
    handle_update(_msg_update("/settings"))
    deletes = [
        c.args[0][0][0] for c in mock_em.call_args_list
        if "DELETE FROM user_pending_actions" in c.args[0][0][0]
    ]
    assert deletes, "command dispatch should clear pending actions"


@patch("bot.router.keywords.handle_pending")
@patch("bot.router.db.execute_many")
@patch("bot.router.db.execute")
def test_router_stale_pending_is_ignored_and_cleared(mock_exec, mock_em, mock_pending):
    # A pending action older than the TTL must not consume the message.
    mock_exec.return_value = [{"action": "keywords_add", "data": "{}", "created_at": 0}]
    from bot.router import handle_update
    handle_update(_msg_update("some unrelated text"))
    assert not mock_pending.called  # not routed to the stale flow
    # and the stale row is deleted
    sql = mock_em.call_args[0][0][0][0]
    assert "DELETE FROM user_pending_actions" in sql
