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


@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.start.handle")
def test_router_dispatches_start(mock_handle, _rl):
    from bot.router import handle_update
    handle_update(_msg_update("/start"))
    assert mock_handle.called


@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.keywords.handle")
def test_router_dispatches_keywords(mock_handle, _rl):
    from bot.router import handle_update
    handle_update(_msg_update("/keywords"))
    assert mock_handle.called


@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.addurl.handle")
def test_router_dispatches_addurl(mock_handle, _rl):
    from bot.router import handle_update
    handle_update(_msg_update("/addurl"))
    assert mock_handle.called


@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.plan.handle")
def test_router_dispatches_plan(mock_handle, _rl):
    from bot.router import handle_update
    handle_update(_msg_update("/plan"))
    assert mock_handle.called


@patch("bot.router.check_rate_limit", return_value=(True, 0))
@patch("bot.commands.timezone.handle")
def test_router_dispatches_timezone(mock_handle, _rl):
    from bot.router import handle_update
    handle_update(_msg_update("/timezone"))
    assert mock_handle.called


def test_router_ignores_unknown_command():
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


@patch("bot.router.db.execute", return_value=[{"action": "keywords_add", "data": "{}"}])
@patch("bot.router.keywords.handle_pending")
def test_router_routes_pending_keywords_action(mock_pending, mock_execute):
    from bot.router import handle_update
    handle_update(_msg_update("AI, Tesla"))
    assert mock_pending.called


@patch("bot.router.db.execute", return_value=[{"action": "addurl_paste", "data": "{}"}])
@patch("bot.router.addurl.handle_pending")
def test_router_routes_pending_addurl_action(mock_pending, mock_execute):
    from bot.router import handle_update
    handle_update(_msg_update("https://example.com/feed"))
    assert mock_pending.called


@patch("bot.router.db.execute", return_value=[{"action": "timezone_set", "data": "{}"}])
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
