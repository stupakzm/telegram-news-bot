import os
import requests


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


def execute(sql: str, args: list = None) -> list[dict]:
    """Execute a single SQL statement, return list of row dicts."""
    stmt = {"sql": sql, "args": [_arg(a) for a in (args or [])]}
    resp = requests.post(
        f"{_url()}/v2/pipeline",
        headers=_headers(),
        json={"requests": [{"type": "execute", "stmt": stmt}]},
        timeout=10,
    )
    resp.raise_for_status()
    result = resp.json()["results"][0]["response"]["result"]
    cols = [c["name"] for c in result["cols"]]
    return [dict(zip(cols, [_coerce(v) for v in row])) for row in result["rows"]]


def execute_many(statements: list[tuple]) -> None:
    """Execute multiple SQL statements in a single pipeline request."""
    requests_body = [
        {"type": "execute", "stmt": {"sql": sql, "args": [_arg(a) for a in (args or [])]}}
        for sql, args in statements
    ]
    resp = requests.post(
        f"{_url()}/v2/pipeline",
        headers=_headers(),
        json={"requests": requests_body},
        timeout=10,
    )
    resp.raise_for_status()
