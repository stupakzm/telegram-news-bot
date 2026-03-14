import pytest
from unittest.mock import patch, MagicMock
import os, time

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("STARS_ONETIME_PRICE", "200")
os.environ.setdefault("STARS_MONTHLY_PRICE", "100")


@patch("bot.commands.upgrade.tg.send_message")
@patch("bot.commands.upgrade.db.execute", return_value=[{"tier": "free"}])
def test_upgrade_sends_comparison_message(mock_execute, mock_send):
    from bot.commands.upgrade import handle
    handle({"from": {"id": 1}, "chat": {"id": 1}})
    assert mock_send.called
    text = mock_send.call_args[1].get("text", "") or mock_send.call_args[0][1]
    assert "One-time" in text or "Monthly" in text or "Stars" in text


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_successful_payment_one_time_sets_tier(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 1},
        "chat": {"id": 1},
        "successful_payment": {
            "invoice_payload": "tier:one_time",
            "total_amount": 200,
            "currency": "XTR",
        }
    })
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "one_time" in str(args)


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_successful_payment_monthly_sets_expiry(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 1},
        "chat": {"id": 1},
        "successful_payment": {
            "invoice_payload": "tier:monthly",
            "total_amount": 100,
            "currency": "XTR",
        }
    })
    sql, args = mock_execute_many.call_args[0][0][0]
    assert "monthly" in str(args)
    # tier_expires_at should be set ~30 days from now
    expires = [a for a in args if isinstance(a, int) and a > int(time.time())]
    assert len(expires) > 0


@patch("bot.commands.payments.tg.send_invoice")
def test_send_invoice_uses_xtr_currency(mock_send_invoice):
    from bot.commands.payments import send_invoice
    send_invoice(user_id=1, tier="one_time")
    assert mock_send_invoice.called
    call_kwargs = mock_send_invoice.call_args[1]
    assert call_kwargs["currency"] == "XTR"
    assert call_kwargs["payload"] == "tier:one_time"


@patch("bot.commands.payments.tg.send_invoice")
def test_send_invoice_monthly_uses_xtr_currency(mock_send_invoice):
    from bot.commands.payments import send_invoice
    send_invoice(user_id=1, tier="monthly")
    call_kwargs = mock_send_invoice.call_args[1]
    assert call_kwargs["currency"] == "XTR"
    assert call_kwargs["payload"] == "tier:monthly"


@patch("bot.commands.upgrade.tg.send_message")
@patch("bot.commands.upgrade.db.execute", return_value=[{"tier": "one_time"}])
def test_upgrade_handle_one_time_tier_shows_monthly_button(mock_execute, mock_send):
    from bot.commands.upgrade import handle
    handle({"from": {"id": 1}, "chat": {"id": 1}})
    assert mock_send.called
    call_kwargs = mock_send.call_args[1]
    markup = call_kwargs.get("reply_markup")
    assert markup is not None, "Expected an inline keyboard for one_time tier"
    buttons = markup["inline_keyboard"]
    assert len(buttons) == 1, "Expected exactly one button row for one_time tier"
    assert buttons[0][0]["callback_data"] == "pay:monthly"


@patch("bot.commands.upgrade.tg.send_message")
@patch("bot.commands.upgrade.db.execute", return_value=[{"tier": "monthly"}])
def test_upgrade_handle_monthly_tier_shows_no_buttons_and_confirmation(mock_execute, mock_send):
    from bot.commands.upgrade import handle
    handle({"from": {"id": 1}, "chat": {"id": 1}})
    assert mock_send.called
    call_kwargs = mock_send.call_args[1]
    text = call_kwargs.get("text", "")
    assert "Monthly" in text, "Expected confirmation note mentioning Monthly plan"
    markup = call_kwargs.get("reply_markup")
    assert markup is None, "Expected no inline keyboard for monthly tier"


@patch("bot.commands.payments.tg.send_message")
@patch("bot.commands.payments.db.execute_many")
def test_handle_successful_payment_unknown_tier_sends_error(mock_execute_many, mock_send):
    from bot.commands.payments import handle_successful_payment
    handle_successful_payment({
        "from": {"id": 1},
        "chat": {"id": 1},
        "successful_payment": {
            "invoice_payload": "tier:unknown_tier",
            "total_amount": 50,
            "currency": "XTR",
        }
    })
    assert not mock_execute_many.called, "DB should not be updated for unknown tier"
    assert mock_send.called, "Error message should be sent to user"
    text = mock_send.call_args[1].get("text", "") or mock_send.call_args[0][1]
    assert "contact support" in text.lower() or "⚠️" in text
