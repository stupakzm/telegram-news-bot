import os
import json
import pytest
from unittest.mock import patch, MagicMock
from io import BytesIO

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")


def _make_handler(headers=None, body=b'{"update_id": 1}'):
    """Create a mock handler instance for testing do_POST."""
    from api.webhook import handler
    h = MagicMock(spec=handler)
    h.headers = headers or {}
    h.rfile = BytesIO(body)
    h.send_response = MagicMock()
    h.end_headers = MagicMock()
    h.wfile = BytesIO()
    return h


@patch("api.webhook.handle_update")
@patch.dict(os.environ, {"WEBHOOK_SECRET": "my-secret"})
def test_webhook_valid_secret_processes_request(mock_handle):
    from api.webhook import handler
    h = _make_handler(headers={"Content-Length": "18", "X-Telegram-Bot-Api-Secret-Token": "my-secret"})
    handler.do_POST(h)
    assert mock_handle.called
    h.send_response.assert_called_with(200)


@patch("api.webhook.handle_update")
@patch.dict(os.environ, {"WEBHOOK_SECRET": "my-secret"})
def test_webhook_wrong_secret_returns_403(mock_handle):
    from api.webhook import handler
    h = _make_handler(headers={"Content-Length": "18", "X-Telegram-Bot-Api-Secret-Token": "wrong-secret"})
    handler.do_POST(h)
    assert not mock_handle.called
    h.send_response.assert_called_with(403)


@patch("api.webhook.handle_update")
@patch.dict(os.environ, {"WEBHOOK_SECRET": "my-secret"})
def test_webhook_missing_secret_header_returns_403(mock_handle):
    from api.webhook import handler
    h = _make_handler(headers={"Content-Length": "18"})
    handler.do_POST(h)
    assert not mock_handle.called
    h.send_response.assert_called_with(403)


@patch("api.webhook.handle_update")
@patch.dict(os.environ, {}, clear=False)
def test_webhook_no_env_secret_allows_all(mock_handle):
    os.environ.pop("WEBHOOK_SECRET", None)
    from api.webhook import handler
    h = _make_handler(headers={"Content-Length": "18"})
    handler.do_POST(h)
    assert mock_handle.called
    h.send_response.assert_called_with(200)


@patch("api.webhook.logging.warning")
@patch.dict(os.environ, {}, clear=False)
def test_webhook_logs_warning_when_secret_absent(mock_warning):
    os.environ.pop("WEBHOOK_SECRET", None)
    # Force re-import to trigger module-level check
    import importlib
    import api.webhook
    importlib.reload(api.webhook)
    assert mock_warning.called
    log_msg = mock_warning.call_args[0][0]
    assert "WEBHOOK_SECRET" in log_msg
