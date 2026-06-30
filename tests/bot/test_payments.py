import os
import time
from unittest.mock import patch

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("STARS_VIP_PRICE", "100")
os.environ.setdefault("STARS_SVIP_PRICE", "290")


@patch("bot.commands.payments.tg.send_invoice")
def test_send_invoice_vip_uses_xtr_and_correct_price(mock_invoice):
    from bot.commands.payments import send_invoice
    send_invoice(user_id=1, tier="vip")
    kwargs = mock_invoice.call_args[1]
    assert kwargs["currency"] == "XTR"
    assert kwargs["payload"] == "tier:vip"
    assert kwargs["prices"][0]["amount"] == 100


@patch("bot.commands.payments.tg.send_invoice")
def test_send_invoice_svip_uses_correct_price(mock_invoice):
    from bot.commands.payments import send_invoice
    send_invoice(user_id=1, tier="svip")
    kwargs = mock_invoice.call_args[1]
    assert kwargs["payload"] == "tier:svip"
    assert kwargs["prices"][0]["amount"] == 290


@patch("bot.commands.payments.tg.send_invoice")
def test_send_invoice_unknown_tier_silently_skips(mock_invoice):
    from bot.commands.payments import send_invoice
    send_invoice(user_id=1, tier="garbage")
    assert not mock_invoice.called


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_payment_activates_vip_for_30d(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    before = int(time.time())
    handle_successful_payment({
        "from": {"id": 42},
        "chat": {"id": 42},
        "successful_payment": {
            "invoice_payload": "tier:vip",
            "total_amount": 100,
            "currency": "XTR",
        },
    })
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "tier" in sql.lower()
    assert "vip" in args
    expires_at = next(a for a in args if isinstance(a, int) and a > before)
    # 30 days ± 5 seconds
    assert abs((expires_at - before) - 30 * 24 * 3600) < 5
    assert mock_send.called


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_payment_activates_svip(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 42},
        "chat": {"id": 42},
        "successful_payment": {
            "invoice_payload": "tier:svip",
            "total_amount": 290,
            "currency": "XTR",
        },
    })
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "svip" in args
    assert 290 in args  # stars_paid increment
    assert mock_send.called


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_payment_malformed_payload_does_not_update_db(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 42},
        "chat": {"id": 42},
        "successful_payment": {
            "invoice_payload": "garbage_no_colon",
            "total_amount": 100,
        },
    })
    assert not mock_execute_many.called
    assert mock_send.called


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_payment_unknown_tier_does_not_update_db(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 42},
        "chat": {"id": 42},
        "successful_payment": {
            "invoice_payload": "tier:platinum",
            "total_amount": 500,
        },
    })
    assert not mock_execute_many.called
    text = mock_send.call_args[1].get("text", "")
    assert "could not be processed" in text.lower() or "contact support" in text.lower()


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_payment_clears_last_reminder_at(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 42},
        "chat": {"id": 42},
        "successful_payment": {"invoice_payload": "tier:vip", "total_amount": 100},
    })
    sql, _ = mock_execute_many.call_args[0][0][0]
    assert "last_reminder_at = NULL" in sql
