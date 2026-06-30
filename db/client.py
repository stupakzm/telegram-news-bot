import os
import time as _time
import requests


_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF = [1, 2]  # seconds to wait before attempt 2, 3


def _url() -> str:
    return os.environ["TURSO_URL"].rstrip("/")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['TURSO_TOKEN']}",
        "Content-Type": "application/json",
    }


def _coerce(v: dict):
    if v is None or v.get("type") == "null":
        return None
    t = v.get("type", "text")
    val = v.get("value")
    if t == "integer":
        return int(val)
    if t == "float":
        return float(val)
    return val


def _arg(a) -> dict:
    if a is None:
        return {"type": "null", "value": None}
    if isinstance(a, int):
        return {"type": "integer", "value": str(a)}
    if isinstance(a, float):
        return {"type": "float", "value": str(a)}
    return {"type": "text", "value": str(a)}


def _post_with_retry(url: str, headers: dict, body: dict) -> requests.Response:
    """POST to Turso with retry on connection/timeout errors."""
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=15)
            return resp
        except (requests.exceptions.ConnectTimeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as exc:
            last_exc = exc
            if attempt < len(_RETRY_BACKOFF):
                _time.sleep(_RETRY_BACKOFF[attempt])
    raise last_exc


def execute(sql: str, args: list = None) -> list[dict]:
    """Execute a single SQL statement, return list of row dicts."""
    stmt = {"sql": sql, "args": [_arg(a) for a in (args or [])]}
    resp = _post_with_retry(
        f"{_url()}/v2/pipeline",
        _headers(),
        {"requests": [{"type": "execute", "stmt": stmt}]},
    )
    resp.raise_for_status()
    result_obj = resp.json()["results"][0]
    if result_obj.get("type") == "error":
        raise RuntimeError(f"Turso error: {result_obj['error']['message']}")
    result = result_obj["response"]["result"]
    cols = [c["name"] for c in result["cols"]]
    return [dict(zip(cols, [_coerce(v) for v in row])) for row in result["rows"]]


def execute_many(statements: list[tuple]) -> None:
    """Execute multiple SQL statements in a single pipeline request."""
    requests_body = [
        {"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in (args or [])]}}
        for sql, args in statements
    ]
    resp = _post_with_retry(
        f"{_url()}/v2/pipeline",
        _headers(),
        {"requests": requests_body},
    )
    resp.raise_for_status()
    results = resp.json()["results"]
    errors = [
        r["error"]["message"]
        for r in results
        if r.get("type") == "error"
    ]
    if errors:
        raise RuntimeError(f"Turso pipeline errors: {errors}")


def track_bot_message(user_id: int, message_id: int) -> None:
    """Record a bot-sent command message ID so /clear can delete it later."""
    execute_many([(
        "INSERT INTO bot_messages (user_id, message_id, sent_at) VALUES (?, ?, ?)",
        [user_id, message_id, int(_time.time())],
    )])
