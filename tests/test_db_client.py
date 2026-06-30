import pytest
from unittest.mock import patch, MagicMock
import os

os.environ.setdefault("TURSO_URL", "https://test.turso.io")
os.environ.setdefault("TURSO_TOKEN", "test-token")


def _mock_resp(rows, cols):
    """Build a mock Turso HTTP response for a SELECT."""
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "results": [{
            "type": "ok",
            "response": {
                "type": "execute",
                "result": {
                    "cols": [{"name": c} for c in cols],
                    "rows": [
                        [{"type": "text", "value": str(v)} if isinstance(v, str)
                         else {"type": "integer", "value": str(v)} if isinstance(v, int)
                         else {"type": "null", "value": None}
                         for v in row]
                        for row in rows
                    ],
                    "affected_row_count": 0,
                    "last_insert_rowid": None,
                }
            }
        }]
    }
    return mock


def test_execute_returns_list_of_dicts():
    from db.client import execute
    with patch("db.client.requests.post", return_value=_mock_resp(
        rows=[[1, "free"]], cols=["user_id", "tier"]
    )):
        result = execute("SELECT user_id, tier FROM users WHERE user_id = ?", [1])
    assert result == [{"user_id": 1, "tier": "free"}]


def test_execute_handles_null_values():
    from db.client import execute
    with patch("db.client.requests.post", return_value=_mock_resp(
        rows=[[1, None]], cols=["user_id", "tier_expires_at"]
    )):
        result = execute("SELECT user_id, tier_expires_at FROM users", [])
    assert result[0]["tier_expires_at"] is None


def test_execute_empty_result():
    from db.client import execute
    with patch("db.client.requests.post", return_value=_mock_resp(rows=[], cols=["user_id"])):
        result = execute("SELECT * FROM users WHERE user_id = ?", [999])
    assert result == []


def test_execute_many_sends_multiple_statements():
    from db.client import execute_many
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "results": [
            {"type": "ok", "response": {"type": "execute", "result": {"cols": [], "rows": [], "affected_row_count": 1, "last_insert_rowid": None}}},
            {"type": "ok", "response": {"type": "execute", "result": {"cols": [], "rows": [], "affected_row_count": 1, "last_insert_rowid": None}}},
        ]
    }
    with patch("db.client.requests.post", return_value=mock_resp) as mock_post:
        execute_many([
            ("INSERT INTO users (user_id, created_at) VALUES (?, ?)", [1, 1000]),
            ("INSERT INTO users (user_id, created_at) VALUES (?, ?)", [2, 1001]),
        ])
    payload = mock_post.call_args[1]["json"]
    assert len(payload["requests"]) == 2


def test_execute_raises_on_turso_error():
    from db.client import execute
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "results": [{"type": "error", "error": {"message": "SQLITE_CONSTRAINT"}}]
    }
    with patch("db.client.requests.post", return_value=mock):
        with pytest.raises(RuntimeError, match="SQLITE_CONSTRAINT"):
            execute("INSERT INTO users VALUES (?)", [1])


def test_execute_many_raises_on_partial_failure():
    from db.client import execute_many
    mock = MagicMock()
    mock.raise_for_status = MagicMock()
    mock.json.return_value = {
        "results": [
            {"type": "ok", "response": {"type": "execute", "result": {"cols": [], "rows": [], "affected_row_count": 1, "last_insert_rowid": None}}},
            {"type": "error", "error": {"message": "UNIQUE constraint failed"}},
        ]
    }
    with patch("db.client.requests.post", return_value=mock):
        with pytest.raises(RuntimeError, match="UNIQUE constraint failed"):
            execute_many([
                ("INSERT INTO users VALUES (?)", [1]),
                ("INSERT INTO users VALUES (?)", [1]),
            ])
